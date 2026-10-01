# ABOUTME: The progression report's header and its one-row-per-attempt table.
# ABOUTME: Every percentage here is on the scale the header names, and never on the other.

from collections.abc import Mapping, Sequence

from wowperf.domain.analysis.attempt_shape import verdict_kind, verdict_words
from wowperf.domain.analysis.progression_best import roster_deaths
from wowperf.domain.analysis.progression_repeats import collapse_seconds
from wowperf.domain.comparison.pace import PaceSample, pace_reading, withheld_reason
from wowperf.domain.comparison.pace_curve import pace_end
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.findings import Finding, quantity
from wowperf.domain.progression import LoadedProgression, remaining_percent
from wowperf.domain.report.frame import format_seconds
from wowperf.domain.report.progression_model import AttemptRow, ProgressionHeader
from wowperf.domain.report.raid_frame import DIFFICULTY_NAMES, first_death_named

NO_READING = "—"
"""What an attempt with no figure prints. A zero would read as a kill, and an
empty cell reads as a rendering bug."""

KILL_VERDICT = "kill"
"""The Verdict cell of a kill: no wipe to explain, and a fact the fight list states."""

NOT_COMPARED = "not compared"
"""The Pace cell of a pull handed a sample its own pace comparison withheld."""

PACE_CUT_CELL = "{state}, stopped at {clock}"
"""The Pace cell of a reading whose band ran out before the attempt ended (`pace_end`)."""


def depth_label(uses_boss_health: bool) -> str:
    """Which percentage this page's figures are, in one phrase.

    The same two words `progression_service._depth_label` prints into the
    findings, so the page and the JSON cannot describe one night on two scales.
    """
    return "boss health" if uses_boss_health else "encounter progress"


def _headline(outcome: str, series: LoadedProgression) -> str:
    """What the Summary opens on: the outcome, and for a boss not killed how deep it got.

    A kill's outcome already says everything a headline should. Otherwise the
    deepest attempt's own figure follows it, on the scale the header names;
    with no attempt carrying a reading there is no depth to name, so the
    outcome stands alone rather than carry a figure made up for it.
    """
    progression = series.progression
    if any(attempt.kill for attempt in progression.attempts):
        return outcome
    deepest = progression.deepest
    left = (
        None
        if deepest is None
        else remaining_percent(deepest, uses_boss_health=progression.uses_boss_health)
    )
    if left is None:
        return outcome
    return f"{outcome}; the deepest left {left:.1f}% {depth_label(progression.uses_boss_health)}"


def _read_line(counted: int, discarded: int) -> str:
    """How many attempts were read, and how many left out for being too short."""
    line = f"{quantity(counted, 'attempt', 'attempts')} read"
    return f"{line}, {discarded} excluded as too short" if discarded else line


def build_progression_header(series: LoadedProgression) -> ProgressionHeader:
    progression = series.progression
    attempts = progression.attempts
    killed = next((index for index, a in enumerate(attempts, start=1) if a.kill), None)
    if killed is not None:
        outcome = f"Killed on attempt {killed} of {len(attempts)}"
    else:
        outcome = f"No kill in {quantity(len(attempts), 'attempt', 'attempts')}"
    return ProgressionHeader(
        boss=progression.boss_name,
        difficulty=DIFFICULTY_NAMES.get(
            progression.difficulty, f"Difficulty {progression.difficulty}"
        ),
        size=progression.size,
        outcome=outcome,
        headline=_headline(outcome, series),
        read_line=_read_line(len(attempts), len(progression.discarded)),
        attempts_counted=len(attempts),
        attempts_discarded=len(progression.discarded),
        depth_label=depth_label(progression.uses_boss_health),
    )


def _verdict(kill: bool, findings: Sequence[Finding]) -> str:
    """The pull's own wipe verdict, "kill" on a kill, or no reading.

    The first finding that states a verdict, so the pull's other findings are
    passed over; a pull carrying none -- never drawn, or one the verdict was
    not minted for -- has no reading rather than a verdict made up for it.
    The kind is printed in the words the boss rollup's title uses, so "both"
    names what it is both of.
    """
    if kill:
        return KILL_VERDICT
    return next(
        (verdict_words(kind) for finding in findings if (kind := verdict_kind(finding))),
        NO_READING,
    )


def _pace(encounter: Encounter, sample: PaceSample | None) -> str:
    """The pace state at the attempt's last compared second.

    A pull handed no sample has no reading. One handed a sample its own pace
    comparison withheld reads "not compared": `withheld_reason` is the
    predicate the pull's `compare.pace.unavailable` notice is minted from, so
    the cell and the pull's own panel cannot disagree about whether it ran.

    A reading whose band ran out before the attempt did names the clock it
    stopped at, read by `pace_end` exactly as the pull's own Summary line reads
    it, so a state the comparison left early is never taken for the attempt's end.
    """
    if sample is None:
        return NO_READING
    if withheld_reason(encounter, sample):
        return NOT_COMPARED
    reading = pace_reading(encounter, sample)
    assert reading is not None  # withheld_reason("") guarantees a usable reading
    state, cut = pace_end(reading)
    if cut is None:
        return state.value
    return PACE_CUT_CELL.format(state=state.value, clock=format_seconds(cut))


def _first_death(loaded: LoadedEncounter | None) -> str:
    """Who died first, as what, and to which ability; no reading when nobody did."""
    named = first_death_named(loaded) if loaded is not None else None
    if named is None:
        return NO_READING
    death, who = named
    return f"{who}, to {death.killing_blow}"


def build_attempt_rows(
    series: LoadedProgression,
    *,
    pull_findings: Mapping[int, Sequence[Finding]] | None = None,
    pace: Mapping[int, PaceSample] | None = None,
) -> tuple[AttemptRow, ...]:
    """One row per qualifying attempt, in pull order.

    Discarded attempts are not rows: they are excluded from every figure the
    series reports, so a row for one would invite a reader to compare it
    against figures it took no part in. The header states how many there were.

    The deaths column is filled only for an attempt that was deepened. An
    attempt nobody fetched events for has no death count, and printing 0 for it
    would claim nobody died.

    `pull_findings` and `pace` are each pull's own findings and pace sample,
    keyed by fight id, and read as empty when `None`: the standalone page
    hands neither. The first death and how long the raid held after it are
    read off the attempt's own deaths, so a pull nobody fetched events for has
    no reading in either.
    """
    progression = series.progression
    uses_boss_health = progression.uses_boss_health
    deepest = progression.deepest
    phase_names = {phase.id: phase.name for phase in progression.phases}
    deepened = {one.encounter.fight_id: one for one in series.loaded}

    rows: list[AttemptRow] = []
    for index, attempt in enumerate(progression.attempts, start=1):
        left = remaining_percent(attempt, uses_boss_health=uses_boss_health)
        loaded = deepened.get(attempt.fight_id)
        phase = ""
        if progression.separates_wipes and attempt.last_phase is not None:
            phase = phase_names.get(attempt.last_phase, "")
        rows.append(
            AttemptRow(
                index=index,
                fight_id=attempt.fight_id,
                depth=NO_READING if left is None else f"{left:.1f}%",
                duration=format_seconds(attempt.duration_seconds) or NO_READING,
                phase=phase,
                deaths=NO_READING if loaded is None else str(roster_deaths(loaded)),
                verdict=_verdict(attempt.kill, (pull_findings or {}).get(attempt.fight_id, ())),
                pace=_pace(attempt, (pace or {}).get(attempt.fight_id)),
                first_death=_first_death(loaded),
                held=(
                    NO_READING
                    if loaded is None
                    else format_seconds(collapse_seconds(loaded)) or NO_READING
                ),
                is_best=deepest is not None and attempt.fight_id == deepest.fight_id,
                is_kill=attempt.kill,
            )
        )
    return tuple(rows)
