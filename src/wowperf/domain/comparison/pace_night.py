# ABOUTME: One boss's wipes on the night page, each read by slice 1's own pace comparison.
# ABOUTME: A count and one line per wipe pull, in pull order; no new arithmetic and no trend.

from collections.abc import Mapping, Sequence

from wowperf.domain.comparison.pace import PaceSample, clock_text, pace_reading, withheld_reason
from wowperf.domain.comparison.pace_curve import (
    PaceReading,
    PaceState,
    final_behind_start,
    pace_end,
)
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding

NIGHT_PACE_ID = "progression.attempts.pace"

MIN_COMPARED_PULLS = 2
"""Below this many compared wipes the line would only repeat one pull's own finding."""

NIGHT_PACE_DETAIL = (
    "Each line is one wipe's own damage pace against the reference kills, as that pull's "
    "Damage tab draws it: behind means below the kill that had dealt the boss least by the "
    "pull's last compared second. The count is over the compared wipes only; a wipe that "
    "could not be compared is listed and not counted. The order is pull order, and no trend "
    "is drawn from it."
)


def analyse_night_pace(
    attempts: Sequence[LoadedEncounter], samples: Mapping[int, PaceSample]
) -> list[Finding]:
    """`progression.attempts.pace` for one boss, or nothing.

    `attempts` is the boss's drawn pulls in pull order; `samples` is each
    pull's pace sample by fight id, as the night command loaded it. A kill is
    not listed, whatever sample it carries, since the line counts wipes; nor is
    a pull with no sample, as on a night read with `--no-compare`.
    Every clock and state is the one `pace_reading` already gives that pull, so
    this line and the pull's own finding cannot disagree.
    """
    wipes = [
        one.encounter
        for one in attempts
        if not one.encounter.kill and one.encounter.fight_id in samples
    ]
    lines: list[str] = []
    compared = 0
    behind = 0
    for encounter in wipes:
        sample = samples[encounter.fight_id]
        reason = withheld_reason(encounter, sample)
        if reason:
            lines.append(f"Fight {encounter.fight_id}: not compared. {reason}")
            continue
        reading = pace_reading(encounter, sample)
        assert reading is not None  # withheld_reason("") guarantees a usable reading
        compared += 1
        state, _ = pace_end(reading)
        if state is PaceState.BEHIND:
            behind += 1
        lines.append(_pull_line(encounter.fight_id, reading))
    if compared < MIN_COMPARED_PULLS:
        return []

    sizes: dict[int, list[int]] = {}
    for encounter in wipes:
        sizes.setdefault(encounter.size, []).append(encounter.fight_id)
    if len(sizes) > 1:
        parts = [
            f"{'Fights' if len(ids) > 1 else 'Fight'} {', '.join(str(one) for one in ids)} "
            f"at {size} players"
            for size, ids in sizes.items()
        ]
        lines.append("; ".join(parts) + ": each against kills of its own size")

    count = f"{behind} of {compared}" if behind else f"None of {compared}"
    return [
        Finding(
            id=NIGHT_PACE_ID,
            title=f"{count} wipes ended behind the kills' pace",
            detail=NIGHT_PACE_DETAIL,
            confidence=Confidence.DERIVED,
            evidence=tuple(lines),
        )
    ]


def _pull_line(fight_id: int, reading: PaceReading) -> str:
    """One wipe's state at its last compared second, and where the comparison stopped."""
    last = reading.seconds[-1]
    clock = clock_text(last.second)
    if not reading.band_cut:
        end = f"the wipe at {clock}"
    elif reading.single:
        end = f"{clock}, when the reference kill ended"
    else:
        end = f"{clock}, where fewer than three kills were still fighting"

    if last.state is PaceState.BEHIND:
        start = final_behind_start(reading)
        assert start is not None  # a reading that ends behind has a final behind stretch
        state = f"behind from {clock_text(start)} to {end}"
    elif last.state is PaceState.ON_PACE:
        state = f"on pace through {end}"
    else:
        state = f"ahead through {end}"
    against = ", against the slowest kill alone" if reading.single else ""
    return f"Fight {fight_id}{against}: {state}"
