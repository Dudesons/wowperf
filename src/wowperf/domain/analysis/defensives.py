# ABOUTME: Defensive claims a combat log can support: never cast at all, cast far below
# ABOUTME: the cooldown ceiling, or off cooldown at a death. All three are inferred.

from collections import defaultdict

from wowperf.domain.analysis.deaths import pull_offset
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run
from wowperf.domain.season import CooldownAbility, DefensiveAbility, Defensives

CEILING_USE_FRACTION = 0.2
"""How far below the ceiling a player must be before it is worth saying anything.

Measured, not chosen by taste: run against a realistic 28-minute dungeon run
with realistic press counts, a 0.5 fraction fired on seven of eight pressed
defensives, including "used Prismatic Barrier 12 of a possible 67 times" —
escaping that finding would take 34 presses in one dungeon. Using a defensive
at close to half its theoretical maximum is ordinary play, not neglect; 0.2
fires only on genuine near-neglect instead of on almost everything pressed.
"""

MIN_CEILING_USES = 3.0
"""Below this the ceiling itself is too small to argue from."""

RUN_UP_SECONDS = 10.0
"""How much of the run-up to a death counts as the damage that killed the player.

An ability that came off cooldown halfway through that run-up was never an
option anyone had, so availability is judged from when the damage began rather
than from the instant of death. The report's death card shows this same window,
so a reader sees the damage a defensive could have answered — long enough to
read the sequence, short enough that the card stays a card.
"""


def defensives_up_at(
    casts: tuple[CastEvent, ...],
    abilities: tuple[DefensiveAbility, ...],
    actor_id: int,
    death_ms: int,
) -> tuple[str, ...]:
    """Names of `abilities` this player had off cooldown when the killing damage began.

    Two conditions, and the first is the one that keeps this honest.

    **The player must have cast the ability somewhere in the run.** Several
    entries in the data file are talent-gated, and a player who did not take the
    talent casts it nowhere — which looks exactly like having it and never
    pressing it. Reporting silence as availability would accuse someone of not
    pressing a button they do not own. An ability never cast at all is the other
    analyser's subject, and that one says outright that a missing talent explains
    it just as well.

    **And they must have cast it at no point in `[death - (cooldown + run-up),
    death]`.** That one window does two jobs: it excludes an ability still on
    cooldown, and it excludes one they pressed during the run-up and died anyway.

    What remains resolves toward saying nothing. Base cooldowns are longer than
    talented ones; charges are ignored, so a spare charge reads as unavailable;
    the log emits no cooldown reset or reduction events, so a reset reads as
    unavailable; and casts are fetched for the fight, so one pressed before the
    timer started is invisible. Each understates what was up, and understating
    cannot produce a false accusation.

    Returned in the order the abilities were given, so a caller controls the
    reading order rather than inheriting a set's.
    """
    ours = [cast for cast in casts if cast.actor_id == actor_id]
    return tuple(
        ability.name
        for ability in abilities
        if any(cast.ability_id == ability.ability_id for cast in ours)
        and not any(
            cast.ability_id == ability.ability_id
            and death_ms - (ability.cooldown_seconds + RUN_UP_SECONDS) * 1000
            <= cast.timestamp_ms
            <= death_ms
            for cast in ours
        )
    )


def analyse_defensives_at_death(
    run: Run,
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
    deaths: tuple[Death, ...],
) -> list[Finding]:
    """Players who died while a personal defensive was off cooldown.

    One finding per player rather than per death, because the question a reader
    asks is about the player, and the evidence carries each death separately.

    `inferred`, like every other claim in this module: availability is
    reconstructed from cast timestamps and a base cooldown, and the log records
    no cooldown state to check it against. A defensive is also pressed into
    incoming damage rather than on cooldown, so an unpressed one that was up is
    a question worth asking, never a verdict.

    Only abilities the player cast somewhere in the run are considered, so a
    talent they never took cannot be held against them. That leaves the never-cast
    case entirely to `analyse_defensives`, which discloses the ambiguity.

    A spec absent from the data file produces nothing, which is not the same
    claim as a spec that had nothing available. The caller must keep those apart.
    """
    name_counts: dict[str, int] = defaultdict(int)
    for player in run.players:
        name_counts[player.name] += 1

    findings = []
    for player in run.players:
        abilities = defensives.for_spec(player.class_name, player.spec)
        if not abilities:
            continue

        lines = []
        first_pull: int | None = None
        for death in sorted(
            (death for death in deaths if death.actor_id == player.actor_id),
            key=lambda death: death.timestamp_ms,
        ):
            up = defensives_up_at(casts, abilities, player.actor_id, death.timestamp_ms)
            if not up:
                continue
            if first_pull is None:
                first_pull = death.pull_index
            lines.append(
                f"{pull_offset(run, death)} to {death.killing_blow}, with "
                f"{', '.join(up)} off cooldown"
            )

        if not lines:
            continue

        base_id = (
            player.name
            if name_counts[player.name] == 1
            else f"{player.name}.{player.actor_id}"
        )
        times = "once" if len(lines) == 1 else f"{len(lines)} times"
        findings.append(
            Finding(
                id=f"defensives.unused.{base_id}",
                title=f"{player.name} died {times} with a defensive available",
                detail=(
                    "Availability is read from this player's own casts against the "
                    "ability's base cooldown, judged from when the damage that killed "
                    "them began. Only abilities they cast somewhere in the run count, so "
                    "a talent they never took is never held against them, and spare "
                    "charges and cooldown resets are ignored because the log does not "
                    "record them. A defensive is pressed into damage rather than on "
                    "cooldown, so this is a question to ask, not a mistake to fix."
                ),
                confidence=Confidence.INFERRED,
                seconds_lost=None,
                evidence=(f"{player.class_name} {player.spec}", *lines),
                pull_index=first_pull,
            )
        )
    return findings


def alive_combat_seconds(run: Run, deaths: tuple[Death, ...], actor_id: int) -> float | None:
    """Combat time this player could actually have pressed a button in.

    Returns `None` when any of this player's deaths has `seconds_until_next_action`
    of `None` — that death's cost cannot be measured because the player's last
    recorded action in the run was dying, so nothing follows it to measure to.
    There is no honest dead-time figure to subtract in that case, so there is no
    honest alive-time figure either; the caller must report no ceiling finding
    for this player rather than treat the unmeasured death as zero seconds dead.

    Otherwise approximate on purpose, and one of the reasons the finding is
    `inferred`: a run-back can extend past the pull it started in, so the
    subtraction can overshoot. Overshooting lowers the ceiling, which makes the
    claim weaker rather than louder.
    """
    theirs = [death for death in deaths if death.actor_id == actor_id]
    if any(death.seconds_until_next_action is None for death in theirs):
        return None
    dead = sum(death.seconds_until_next_action or 0.0 for death in theirs)
    return max(run.total_pull_seconds - dead, 0.0)


def cooldown_ceiling(alive_seconds: float, ability: CooldownAbility) -> float:
    """How many times the cooldown alone would have allowed this to be pressed."""
    return alive_seconds / ability.cooldown_seconds * ability.charges


def analyse_defensives(
    run: Run,
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
    deaths: tuple[Death, ...],
) -> list[Finding]:
    """Defensives never pressed (§5.6), and defensives pressed far below their ceiling (§5.7).

    Both are `inferred`. The log emits no cooldown-reset or reduction events, so
    neither claim can be measured, and a defensive is pressed into damage rather
    than on cooldown — the ceiling bounds what was possible, not what was right.
    """
    cast_counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for cast in casts:
        cast_counts[cast.actor_id][cast.ability_id] += 1

    name_counts: dict[str, int] = defaultdict(int)
    for player in run.players:
        name_counts[player.name] += 1

    findings = []
    for player in run.players:
        known = defensives.for_spec(player.class_name, player.spec)
        for ability in known:
            base_id = (
                f"{player.name}.{ability.ability_id}"
                if name_counts[player.name] == 1
                else f"{player.name}.{player.actor_id}.{ability.ability_id}"
            )
            uses = cast_counts.get(player.actor_id, {}).get(ability.ability_id, 0)

            if uses:
                alive = alive_combat_seconds(run, deaths, player.actor_id)
                if alive is None:
                    continue
                ceiling = cooldown_ceiling(alive, ability)
                if ceiling < MIN_CEILING_USES or uses >= ceiling * CEILING_USE_FRACTION:
                    continue
                findings.append(
                    Finding(
                        id=f"defensives.ceiling.{base_id}",
                        title=(
                            f"{player.name} used {ability.name} {uses} "
                            f"of a possible {ceiling:.0f} times"
                        ),
                        detail=(
                            f"{ability.name} has a {ability.cooldown_seconds:.0f}s cooldown, "
                            f"which fits {ceiling:.0f} times into the {alive:.0f}s this player "
                            "spent alive and in combat. That is a ceiling, not a target: a "
                            "defensive is pressed into incoming damage, not on cooldown, so a "
                            "gap here is a question to ask rather than a mistake to fix."
                        ),
                        confidence=Confidence.INFERRED,
                        seconds_lost=None,
                        evidence=(
                            f"{player.class_name} {player.spec}",
                            f"ability {ability.ability_id}",
                            f"{uses} cast{'s' if uses != 1 else ''} in {alive:.0f}s alive",
                        ),
                    )
                )
                continue

            findings.append(
                Finding(
                    id=f"defensives.{base_id}",
                    title=f"{player.name} never cast {ability.name}",
                    detail=(
                        f"{ability.name} was not cast at any point in the run. This is "
                        "inferred, not measured: the log records no cooldown state, so it "
                        "may have been unavailable, or the talent may not be taken."
                    ),
                    confidence=Confidence.INFERRED,
                    seconds_lost=None,
                    evidence=(
                        f"{player.class_name} {player.spec}",
                        f"ability {ability.ability_id}",
                        "zero casts in the whole run",
                    ),
                )
            )
    return findings
