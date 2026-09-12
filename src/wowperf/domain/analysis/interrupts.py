# ABOUTME: Reconstructs which enemy casts were kicked, which landed, and which are unknowable.
# ABOUTME: The combat log carries no interruptible flag, so outcomes are derived, not read.

from collections import defaultdict

from wowperf.domain.events import (
    DamageTakenEvent,
    EnemyCast,
    EnemyCastRow,
    InterruptEvent,
)
from wowperf.domain.findings import Confidence, Finding, FindingFact

FOLLOW_WINDOW_MS = 3_000
"""Damage from a spell lands within a few seconds of the cast completing."""

MAX_ABILITIES_REPORTED = 5

Identity = tuple[int, int, int]


def reconstruct_enemy_casts(
    rows: tuple[EnemyCastRow, ...],
    interrupts: tuple[InterruptEvent, ...],
) -> tuple[EnemyCast, ...]:
    """Pair each cast start with its outcome, leaving unresolvable starts unresolved.

    Identity is (source, instance, ability). Two copies of one NPC casting the
    same spell are different casters, and pairing across them would invent
    kicks that never happened.
    """
    starts: dict[Identity, list[EnemyCastRow]] = defaultdict(list)
    completions: dict[Identity, list[int]] = defaultdict(list)
    for cast_row in rows:
        identity = (cast_row.source_id, cast_row.source_instance, cast_row.ability_id)
        if cast_row.is_start:
            starts[identity].append(cast_row)
        else:
            completions[identity].append(cast_row.timestamp_ms)

    kicks: dict[Identity, list[InterruptEvent]] = defaultdict(list)
    for interrupt in interrupts:
        identity = (
            interrupt.target_id,
            interrupt.target_instance,
            interrupt.interrupted_ability_id,
        )
        kicks[identity].append(interrupt)

    resolved: list[EnemyCast] = []
    for identity, group in starts.items():
        group.sort(key=lambda start_row: start_row.timestamp_ms)
        landed_at = sorted(completions.get(identity, []))
        kicked_at = sorted(kicks.get(identity, []), key=lambda event: event.timestamp_ms)

        for position, start in enumerate(group):
            floor = start.timestamp_ms
            ceiling = (
                group[position + 1].timestamp_ms if position + 1 < len(group) else None
            )

            # Written as explicit comparisons rather than a closure: ruff's B023
            # rejects a function defined in a loop that captures the loop variable,
            # and it is right to — the bug it prevents is exactly the one that would
            # pair every start with the last iteration's window.
            completion = next(
                (
                    stamp
                    for stamp in landed_at
                    if floor <= stamp and (ceiling is None or stamp < ceiling)
                ),
                None,
            )
            kick = next(
                (
                    event
                    for event in kicked_at
                    if floor <= event.timestamp_ms
                    and (ceiling is None or event.timestamp_ms < ceiling)
                ),
                None,
            )

            if kick is not None and (completion is None or kick.timestamp_ms <= completion):
                resolved.append(
                    EnemyCast(
                        source_id=start.source_id,
                        source_instance=start.source_instance,
                        ability_id=start.ability_id,
                        ability_name=start.ability_name,
                        started_ms=start.timestamp_ms,
                        interrupted_by=kick.player_name,
                        pull_index=start.pull_index,
                    )
                )
            else:
                resolved.append(
                    EnemyCast(
                        source_id=start.source_id,
                        source_instance=start.source_instance,
                        ability_id=start.ability_id,
                        ability_name=start.ability_name,
                        started_ms=start.timestamp_ms,
                        completed_ms=completion,
                        pull_index=start.pull_index,
                    )
                )
    return tuple(sorted(resolved, key=lambda cast: cast.started_ms))


def _damage_after(cast: EnemyCast, damage_taken: tuple[DamageTakenEvent, ...]) -> int:
    if cast.completed_ms is None:
        return 0
    end = cast.completed_ms + FOLLOW_WINDOW_MS
    return sum(
        hit.amount
        for hit in damage_taken
        if hit.ability_id == cast.ability_id and cast.completed_ms <= hit.timestamp_ms < end
    )


def _interruptible(kicks: int) -> tuple[str, FindingFact]:
    """What the run proved about whether this spell can be stopped at all.

    The log carries no interruptible flag -- `.claude/skills/wcl-api/SKILL.md`
    lists the verified fields for `dataType: Interrupts` and holds none -- so
    this invents none. What it can say is narrower and real: a spell somebody
    kicked was interruptible, provably, because the kick is in the log.

    A spell nobody kicked is unknown, and says unknown. It must never read as
    a miss: a reader met a card saying a spell landed eighteen times with
    nothing on it about whether anyone could have stopped it, and supplied the
    missing half himself. The abstention carries no tier of its own because it
    grades no claim; the count behind a proven one is read straight from the
    log, and carries measured.
    """
    if kicks:
        claim = f"kicked {kicks} time{'s' if kicks != 1 else ''} this run"
        return (
            f"interruptible: {claim}",
            FindingFact(label="Interruptible", value=claim,
                        confidence=Confidence.MEASURED),
        )
    return (
        "never kicked this run; the log does not say whether it could be",
        FindingFact(label="Interruptible", value="unknown; never kicked this run"),
    )


def analyse_interrupts(
    casts: tuple[EnemyCast, ...],
    damage_taken: tuple[DamageTakenEvent, ...],
) -> list[Finding]:
    """Rank the enemy casts that landed by the damage they actually did to this group.

    No curated must-kick list: what hurt this group is a fact, and what a
    spreadsheet nominates is an opinion.
    """
    if not casts:
        return []

    landed = [cast for cast in casts if cast.landed]
    kicked = [cast for cast in casts if cast.was_kicked]
    excluded = [cast for cast in casts if not cast.outcome_known]

    findings = [
        Finding(
            id="interrupts.summary",
            title=(
                f"{len(landed)} cast{'s' if len(landed) != 1 else ''} landed, "
                f"{len(kicked)} {'was' if len(kicked) == 1 else 'were'} kicked"
            ),
            detail=(
                "Outcomes are reconstructed: the log records no interruptible flag. Casts "
                "whose outcome the log does not resolve are excluded rather than counted "
                "as missed."
            ),
            confidence=Confidence.DERIVED,
            seconds_lost=None,
            evidence=(
                f"{len(landed)} landed",
                f"{len(kicked)} kicked",
                f"{len(excluded)} excluded: caster died, was crowd-controlled, or cancelled",
            ),
        )
    ]

    # Counted across every cast of the run, not only the landed ones: a spell
    # is proven interruptible by any kick of it, and a kicked cast is by
    # definition not among the landed.
    kicks_by_ability: dict[int, int] = defaultdict(int)
    for cast in kicked:
        kicks_by_ability[cast.ability_id] += 1

    damage_by_ability: dict[int, int] = defaultdict(int)
    names: dict[int, str] = {}
    counts: dict[int, int] = defaultdict(int)
    for cast in landed:
        damage_by_ability[cast.ability_id] += _damage_after(cast, damage_taken)
        names[cast.ability_id] = cast.ability_name
        counts[cast.ability_id] += 1

    ranked = sorted(damage_by_ability.items(), key=lambda item: -item[1])
    for rank, (ability_id, damage) in enumerate(ranked[:MAX_ABILITIES_REPORTED]):
        if damage <= 0:
            break
        interruptible, fact = _interruptible(kicks_by_ability[ability_id])
        findings.append(
            Finding(
                id=f"interrupts.ability.{rank}",
                title=f"{names[ability_id]} landed {counts[ability_id]} times",
                detail=(
                    f"{names[ability_id]} was cast to completion {counts[ability_id]} times "
                    f"and did {damage:,} unmitigated damage to the group within "
                    f"{FOLLOW_WINDOW_MS // 1000}s of each cast."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"{damage:,} unmitigated damage attributed",
                    "unmitigated: before absorbs and mitigation",
                    interruptible,
                ),
                facts=(fact,),
                ability_id=ability_id,
                ability_name=names[ability_id],
            )
        )
    return findings
