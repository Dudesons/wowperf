# ABOUTME: Compares one player's boss-pull casts and talent build against a top parse.
# ABOUTME: Boss pulls only: across trash an ability ratio measures the route, not the player.

from wowperf.domain.comparison.sample import ParseMember
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player, Run

MAX_SPELLS_REPORTED = 5
MIN_CASTS_TO_COMPARE = 3
"""Below this, the reference's own sample is too small to argue from."""

RATE_GAP_MULTIPLE = 1.5
"""How much more often they must cast something before it is worth reporting."""


def boss_seconds(run: Run) -> float:
    """Seconds spent on boss pulls — the only stretch where two runs fought the same thing."""
    return sum(pull.duration_seconds for pull in run.boss_pulls)


def boss_casts(
    run: Run, casts: tuple[CastEvent, ...], actor_id: int
) -> dict[int, tuple[str, int]]:
    """One player's casts inside boss pulls, as ability id to (name, count)."""
    boss_indices = {pull.index for pull in run.boss_pulls}
    counted: dict[int, tuple[str, int]] = {}
    for event in casts:
        if event.actor_id != actor_id or event.pull_index not in boss_indices:
            continue
        name, count = counted.get(event.ability_id, (event.ability_name, 0))
        counted[event.ability_id] = (name, count + 1)
    return counted


def _all_cast_ability_ids(casts: tuple[CastEvent, ...], actor_id: int) -> set[int]:
    """Every ability the player cast anywhere in the run, boss pull or not."""
    return {event.ability_id for event in casts if event.actor_id == actor_id}


def _their_actor_id(theirs: LoadedRun | ParseMember, their_name: str) -> int | None:
    folded = their_name.casefold()
    for player in theirs.run.players:
        if player.name.casefold() == folded:
            return player.actor_id
    return None


def compare_spells(
    ours: LoadedRun, our_player: Player, theirs: LoadedRun | ParseMember, their_name: str
) -> list[Finding]:
    """What the reference player cast on bosses that we did not, and how often."""
    their_actor_id = _their_actor_id(theirs, their_name)
    their_boss_seconds = boss_seconds(theirs.run)
    our_boss_seconds = boss_seconds(ours.run)

    if their_actor_id is None or their_boss_seconds <= 0 or our_boss_seconds <= 0:
        return [
            Finding(
                id="compare.spells.unavailable",
                title="The spell comparison could not be made",
                detail=(
                    "A spell comparison needs boss pulls on both sides and the reference "
                    "player present in their own report. One of those is missing, so no "
                    "ability numbers are reported rather than numbers from an unlike sample."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"our boss time {our_boss_seconds:.0f}s",
                    f"their boss time {their_boss_seconds:.0f}s",
                    f"reference player {their_name!r} "
                    f"{'found' if their_actor_id is not None else 'not found'}",
                ),
            )
        ]

    theirs_on_bosses = boss_casts(theirs.run, theirs.casts, their_actor_id)
    ours_on_bosses = boss_casts(ours.run, ours.casts, our_player.actor_id)
    ours_anywhere = _all_cast_ability_ids(ours.casts, our_player.actor_id)

    findings: list[Finding] = []

    # 1. Abilities they cast and we never cast at all. A set difference: the
    #    highest-signal comparison the design lists, and the one with no modelling in it.
    never = sorted(
        (
            (ability_id, name, count)
            for ability_id, (name, count) in theirs_on_bosses.items()
            if ability_id not in ours_anywhere
        ),
        key=lambda row: row[2],
        reverse=True,
    )
    for rank, (ability_id, name, count) in enumerate(never[:MAX_SPELLS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.spells.missing.{rank}",
                title=(
                    f"{their_name} cast {name} {count} times on bosses; "
                    f"{our_player.name} never cast it"
                ),
                detail=(
                    f"{name} does not appear anywhere in this run for {our_player.name} — not "
                    "on bosses and not on trash. That is either a talent not taken or a button "
                    "not pressed; the log cannot tell which."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"{count} casts across {their_boss_seconds:.0f}s of their boss pulls",
                    "zero casts in the whole of our run",
                ),
            )
        )

    # 2. Abilities both cast, where their rate on bosses is materially higher.
    gaps = []
    for ability_id, (name, their_count) in theirs_on_bosses.items():
        if their_count < MIN_CASTS_TO_COMPARE or ability_id not in ours_on_bosses:
            continue
        our_count = ours_on_bosses[ability_id][1]
        their_rate = their_count / their_boss_seconds * 60
        our_rate = our_count / our_boss_seconds * 60
        if our_rate <= 0 or their_rate / our_rate < RATE_GAP_MULTIPLE:
            continue
        gaps.append((their_rate - our_rate, ability_id, name, our_rate, their_rate))
    gaps.sort(reverse=True)

    for rank, (_, ability_id, name, our_rate, their_rate) in enumerate(gaps[:MAX_SPELLS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.spells.rate.{rank}",
                title=(
                    f"{their_name} cast {name} {their_rate:.1f} times a minute on bosses, "
                    f"{our_player.name} {our_rate:.1f}"
                ),
                detail=(
                    "Both rates are casts per minute of boss-pull time, which is the one stretch "
                    "of a dungeon where two runs fought the same encounter. A longer fight at a "
                    "higher key changes how many cooldowns fit, so treat a small gap as noise."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"ours over {our_boss_seconds:.0f}s of boss pulls",
                    f"theirs over {their_boss_seconds:.0f}s of boss pulls",
                ),
            )
        )

    return findings


def compare_talents(our_player: Player, their_player: Player | None) -> list[Finding]:
    """Whether the two builds differ, and the string needed to import theirs."""
    ours = our_player.talent_import_string
    theirs = their_player.talent_import_string if their_player else None

    if ours is None or theirs is None:
        return [
            Finding(
                id="compare.talents",
                title="The talent builds could not be compared",
                detail=(
                    "One of the two reports does not carry a talent import string for its "
                    "player, so the builds are not compared. An absent string is not evidence "
                    "that the builds match."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"ours {'present' if ours else 'absent'}",
                    f"theirs {'present' if theirs else 'absent'}",
                ),
            )
        ]

    if ours == theirs:
        return [
            Finding(
                id="compare.talents",
                title="The talent build matches the reference",
                detail="Both players imported the same build, so nothing here needs changing.",
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=("identical import strings",),
            )
        ]

    return [
        Finding(
            id="compare.talents",
            title="The talent build differs from the reference",
            detail=(
                "The import codes differ. They are opaque, so the difference is not spelled out "
                "here — paste the reference's string into the game to see it laid out on the "
                "tree. A different build is not automatically a worse one."
            ),
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            evidence=(f"theirs: {theirs}", f"ours: {ours}"),
        )
    ]
