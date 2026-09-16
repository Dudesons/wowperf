# ABOUTME: The progression report's header and its one-row-per-attempt table.
# ABOUTME: Every percentage here is on the scale the header names, and never on the other.

from wowperf.domain.analysis.progression_best import roster_deaths
from wowperf.domain.progression import LoadedProgression, remaining_percent
from wowperf.domain.report.frame import format_seconds
from wowperf.domain.report.progression_model import AttemptRow, ProgressionHeader
from wowperf.domain.report.raid_frame import DIFFICULTY_NAMES

NO_READING = "—"
"""What an attempt with no figure prints. A zero would read as a kill, and an
empty cell reads as a rendering bug."""


def depth_label(uses_boss_health: bool) -> str:
    """Which percentage this page's figures are, in one phrase.

    The same two words `progression_service._depth_label` prints into the
    findings, so the page and the JSON cannot describe one night on two scales.
    """
    return "boss health" if uses_boss_health else "encounter progress"


def build_progression_header(series: LoadedProgression) -> ProgressionHeader:
    progression = series.progression
    attempts = progression.attempts
    killed = next((index for index, a in enumerate(attempts, start=1) if a.kill), None)
    if killed is not None:
        outcome = f"Killed on attempt {killed} of {len(attempts)}"
    else:
        outcome = f"No kill in {len(attempts)} attempt{'' if len(attempts) == 1 else 's'}"
    return ProgressionHeader(
        boss=progression.boss_name,
        difficulty=DIFFICULTY_NAMES.get(
            progression.difficulty, f"Difficulty {progression.difficulty}"
        ),
        size=progression.size,
        outcome=outcome,
        attempts_counted=len(attempts),
        attempts_discarded=len(progression.discarded),
        depth_label=depth_label(progression.uses_boss_health),
    )


def build_attempt_rows(series: LoadedProgression) -> tuple[AttemptRow, ...]:
    """One row per qualifying attempt, in pull order.

    Discarded attempts are not rows: they are excluded from every figure the
    series reports, so a row for one would invite a reader to compare it
    against figures it took no part in. The header states how many there were.

    The deaths column is filled only for an attempt that was deepened. An
    attempt nobody fetched events for has no death count, and printing 0 for it
    would claim nobody died.
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
                is_best=deepest is not None and attempt.fight_id == deepest.fight_id,
                is_kill=attempt.kill,
            )
        )
    return tuple(rows)
