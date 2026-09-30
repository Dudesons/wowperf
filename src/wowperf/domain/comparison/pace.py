# ABOUTME: A wipe's damage pace against the reference kills, and when that pace would have killed.
# ABOUTME: Two findings or one withheld notice, all read from `pace_curve`'s one reading.

from statistics import median

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace_curve import (
    BossDamage,
    PaceReading,
    PaceReference,
    PaceState,
    PlayerSeries,
    cumulative_at,
    earlier_behind,
    final_behind_start,
    read_pace,
)
from wowperf.domain.encounter import Encounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import MIN_ATTEMPT_SECONDS

PACE_PREFIX = "compare.pace."
PACE_ID = "compare.pace.boss"
PROJECTION_ID = "compare.pace.projection"
UNAVAILABLE_ID = "compare.pace.unavailable"

NO_BOSS = (
    "No enemy of this fight could be told apart as its boss: none carries the boss flag, "
    "or more than one is named after the fight."
)
GRIDS_DIFFER = (
    "This fight's bosses' damage graphs came back on different time grids, so their damage "
    "could not be added up."
)
NO_BOSS_DAMAGE = "The damage graph for this boss held no series to compare."
NO_REFERENCE_KILL = "No reference kill of this raid size could be loaded to compare against."
BOSS_IN_NO_REFERENCE = "This boss could not be found in any reference kill's fight."
NOTHING_TO_COMPARE = (
    "No second of this attempt could be compared: the reference kills had dealt the boss no "
    "damage by then, or the attempt ended within its first second."
)
PACE_NOT_FETCHED = "Warcraft Logs did not return what this comparison reads"


def not_fetched(message: str) -> str:
    """Why a wipe was not compared when a request it needed failed, in the error's own words.

    The opening is fixed so every such reason reads alike; the rest is the
    error's first line, as `FailedPull` keeps a failed pull's, because the
    exception says what went wrong better than a phrase chosen here would.
    Its later lines are a documentation pointer or context no reader can act on.
    """
    lines = message.strip().splitlines()
    first = lines[0].rstrip(".") if lines else "no message"
    return f"{PACE_NOT_FETCHED}: {first}."

BOSS_DETAIL = (
    "Cumulative damage to the boss, second by second from the pull, against the reference "
    "kills over the same seconds, both sides read from the same boss-only damage graph. "
    "Behind means below the kill that had dealt least by that second; ahead, above the one "
    "that had dealt most. Each graph is read within its own buckets, so a dip shorter than "
    "the coarsest bucket is not reported."
)
PROJECTION_DETAIL = (
    "Assumes the raid's average damage to the boss would have held for the rest of the "
    "fight. Phases, intermissions and a shrinking raid all break that, and a wipe is where "
    "the raid shrank. This is damage pace, not a forecast of the boss's health, and it says "
    "nothing about an enrage timer, for which this tool has no data."
)


class PaceSample(Frozen):
    """What the pace comparison was given: our boss damage and the kills', or why neither.

    `unavailable` is set exactly when nothing can be compared, and names why.
    `our_players` splits `ours` by player, for the per-player comparison.
    """

    ours: BossDamage | None = None
    references: tuple[PaceReference, ...] = ()
    unavailable: str = ""
    our_players: tuple[PlayerSeries, ...] = ()


def clock_text(seconds: float) -> str:
    """Seconds from the pull as a clock, "3:20"; shared with the per-player findings."""
    whole = int(round(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def share_of(value: float, of: float) -> int:
    """`value` as a whole percentage of `of`; shared with the per-player findings."""
    return round(100 * value / of)


def pace_reading(encounter: Encounter, sample: PaceSample) -> PaceReading | None:
    """The one reading both the findings and the chart draw from, or None."""
    if encounter.kill or sample.unavailable or sample.ours is None:
        return None
    return read_pace(sample.ours, sample.references, encounter.duration_seconds)


def _notice(reason: str) -> Finding:
    return Finding(
        id=UNAVAILABLE_ID,
        title="Damage pace against other kills was not compared",
        detail=reason,
        confidence=Confidence.MEASURED,
    )


def withheld_reason(encounter: Encounter, sample: PaceSample) -> str:
    """Why `analyse_pace` would withhold with `compare.pace.unavailable`, or "".

    The one predicate both the raid-wide and the per-player analyser read, so
    a wipe that withholds one withholds the other. Does not check
    `encounter.kill`: a kill withholds for a different reason (there is no
    pace comparison at all) that each caller already checks on its own.
    """
    if sample.unavailable or sample.ours is None:
        return sample.unavailable or NO_BOSS_DAMAGE
    reading = pace_reading(encounter, sample)
    if reading is None:
        return NO_REFERENCE_KILL
    if not reading.seconds or reading.seconds[-1].median <= 0:
        return NOTHING_TO_COMPARE
    return ""


def analyse_pace(encounter: Encounter, sample: PaceSample) -> list[Finding]:
    """`compare.pace.boss` and `compare.pace.projection`, or the notice saying why not.

    A kill is never compared: kills have the parse comparison. The notice is
    badged `measured` because what it states -- that a lookup found nothing --
    is a plain reading, and Provenance draws it rather than the Damage tab.
    """
    if encounter.kill:
        return []
    reason = withheld_reason(encounter, sample)
    if reason:
        return [_notice(reason)]
    reading = pace_reading(encounter, sample)
    assert reading is not None  # withheld_reason("") guarantees a usable reading
    assert sample.ours is not None  # same guarantee covers this

    total = cumulative_at(sample.ours, encounter.duration_seconds)
    withheld_projection = ""
    if encounter.duration_seconds < MIN_ATTEMPT_SECONDS:
        withheld_projection = (
            f"No projection: the attempt lasted under {int(MIN_ATTEMPT_SECONDS)} seconds"
        )
    elif total <= 0:
        withheld_projection = "No projection: the raid dealt the boss no damage"

    findings = [_pace_finding(reading, withheld_projection)]
    if not withheld_projection:
        findings.append(_projection(reading, total, encounter.duration_seconds))
    return findings


def _pace_finding(reading: PaceReading, withheld_projection: str) -> Finding:
    last = reading.seconds[-1]
    clock = clock_text(last.second)
    against = "the slowest kill's" if reading.single else "the kills'"
    of = "its boss damage" if reading.single else "their median boss damage"
    lead = {
        PaceState.BEHIND: f"Behind {against} pace",
        PaceState.ON_PACE: f"On {against} pace",
        PaceState.AHEAD: f"Ahead of {against} pace",
    }[last.state]

    evidence: list[str] = []
    if reading.single:
        evidence.append(
            "Against the one reference kill of this raid size: fewer than three were available"
            if reading.references == 1
            else f"Against the slowest of {reading.references} reference kills of this raid "
            "size: fewer than three were available"
        )
    else:
        evidence.append(f"Against {reading.references} reference kills of this raid size")
        evidence.append(
            f"Their range at {clock}: {share_of(last.low, last.median)}% to "
            f"{share_of(last.high, last.median)}% of their median"
        )
    if not reading.band_cut:
        evidence.append(f"Compared through the wipe at {clock}")
    elif reading.single:
        evidence.append(f"Compared through {clock}, when the reference kill ended")
    else:
        evidence.append(
            f"Compared through {clock}, after which fewer than three kills were still fighting"
        )
    start = final_behind_start(reading)
    if start is not None:
        evidence.append(f"Behind from {clock_text(start)} to {clock}")
        evidence.extend(
            f"Also behind between {clock_text(first)} and {clock_text(end)}"
            for first, end in earlier_behind(reading)
        )
    if withheld_projection:
        evidence.append(withheld_projection)

    return Finding(
        id=PACE_ID,
        title=f"{lead}: {share_of(last.ours, last.median)}% of {of} by {clock}",
        detail=BOSS_DETAIL,
        confidence=Confidence.DERIVED,
        evidence=tuple(evidence),
    )


def _projection(reading: PaceReading, total: float, duration_seconds: float) -> Finding:
    projected = reading.target / (total / duration_seconds)
    whose = "the slowest kill's" if reading.single else "the kills'"
    durations = reading.reference_durations
    if reading.single:
        evidence = (f"The reference kill took {clock_text(durations[0])}",)
    else:
        evidence = (
            f"The kills took {clock_text(durations[0])} to {clock_text(durations[-1])}, "
            f"median {clock_text(median(durations))}",
        )
    return Finding(
        id=PROJECTION_ID,
        title=(
            f"At its average pace this raid would have dealt {whose} boss damage by about "
            f"{clock_text(projected)}"
        ),
        detail=PROJECTION_DETAIL,
        confidence=Confidence.INFERRED,
        evidence=evidence,
    )
