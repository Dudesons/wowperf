# ABOUTME: What a night of attempts may claim: where they sit, and whether the night moved.
# ABOUTME: It never claims a slope -- a real night's deepest attempt was its third of eight.

from statistics import median

from wowperf.domain.analysis.progression_best import best_deaths
from wowperf.domain.analysis.progression_repeats import (
    collapse,
    repeat_ability,
    repeat_first_death,
    repeat_phase,
)
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import LoadedProgression, Progression, remaining_percent

MIN_ATTEMPTS_FOR_MOVEMENT = 6
"""Below this the night is not split into halves at all.

Six qualifying attempts is three a side. The keystone comparison falls back
below three comparable references for the same reason: two figures are an
anecdote, and a claim drawn from them reads exactly as confident as one drawn
from fifty.
"""


def _depth_label(progression: Progression) -> str:
    """Which percentage the figures in this report are, in one word.

    Reads `Progression.uses_boss_health` rather than deciding again from the
    attempts itself -- that decision has exactly one home, so the label and
    the figures it names cannot drift onto different scales.
    """
    return "boss health" if progression.uses_boss_health else "encounter progress"


def analyse_progression(series: LoadedProgression) -> list[Finding]:
    """Layer 1's findings from fight metadata, then Layer 2's and Layer 3's from the
    deepened attempts.

    Layer 1 reads `series.progression` alone and fetches nothing; it is
    untouched by R6 and its findings are neither reworded nor renumbered here.
    Layer 2 reads `series` itself -- `repeat_phase` excepted, which reads only
    `series.progression` because a phase is fight metadata, not something a
    deepened attempt adds. Layer 3 compares the deepest deepened attempt
    against the rest, reading only `deepest_loaded` and the other deepened
    attempts. Both layers are appended after Layer 1, in a fixed order,
    skipping any analyser that found nothing to say. A night where every
    attempt falls below the duration floor leaves both
    `series.progression.attempts` and `series.loaded` empty: Layer 1 still
    reports the discard, and every Layer 2 and Layer 3 analyser below returns
    `None` on an empty `attempts_with_events` rather than raising, so a night
    where nothing was deepened leaves Layer 3 silent too.
    """
    progression = series.progression
    findings: list[Finding] = []
    uses_boss_health = progression.uses_boss_health
    depths = [
        left
        for left in (
            remaining_percent(a, uses_boss_health=uses_boss_health) for a in progression.attempts
        )
        if left is not None
    ]

    # A night that qualifies nothing still has something to say: whatever was
    # excluded, below. Only the figures that depend on a qualifying attempt --
    # best, cluster, movement -- are skipped when there are none.
    if depths:
        label = _depth_label(progression)
        deepest = progression.deepest

        if deepest is not None:
            left = remaining_percent(deepest, uses_boss_health=uses_boss_health)
            if left is None:
                raise AssertionError(
                    "deepest was chosen by remaining_percent, so it must have a reading"
                )
            position = progression.attempts.index(deepest) + 1
            findings.append(
                Finding(
                    id="progression.best",
                    title=f"The best attempt left {left:.1f}% ({label})",
                    detail=(
                        f"Attempt {position} of {len(progression.attempts)} got furthest, "
                        f"lasting {deepest.duration_seconds:.0f} seconds. The deepest attempt "
                        "of a night is often not its last."
                    ),
                    confidence=Confidence.MEASURED,
                    evidence=(
                        f"Attempt {position} of {len(progression.attempts)}, "
                        f"fight {deepest.fight_id}",
                        f"{deepest.duration_seconds:.0f} seconds",
                    ),
                )
            )

        findings.append(
            Finding(
                id="progression.cluster",
                title=f"Attempts sat at a median of {median(depths):.1f}% ({label})",
                detail=(
                    f"Across {len(depths)} attempts the observed range ran "
                    f"{min(depths):.1f}% to {max(depths):.1f}%. A median and a range, "
                    "never an average: one attempt that went deep does not move a median, "
                    "but it would drag an average down."
                ),
                confidence=Confidence.MEASURED,
                evidence=(
                    f"{len(depths)} attempts counted",
                    f"range {min(depths):.1f}% to {max(depths):.1f}%",
                ),
            )
        )

        findings.append(_movement(progression, depths, label))

    if progression.discarded:
        n = len(progression.discarded)
        findings.append(
            Finding(
                id="progression.attempts.discarded",
                title=(
                    f"{n} attempt{'' if n == 1 else 's'} excluded as too short to read"
                ),
                detail=(
                    "An attempt that ends in seconds is a reset or an instant disaster "
                    "rather than a pull whose depth says anything about the night. "
                    "Excluded from every figure above, and counted here so the "
                    "exclusion is visible."
                ),
                confidence=Confidence.MEASURED,
                evidence=tuple(
                    f"fight {a.fight_id}, {a.duration_seconds:.1f} seconds"
                    for a in progression.discarded
                ),
            )
        )

    for deeper in (
        repeat_phase(progression),
        repeat_first_death(series),
        repeat_ability(series),
        collapse(series),
        best_deaths(series),
    ):
        if deeper is not None:
            findings.append(deeper)

    return findings


def _movement(progression: Progression, depths: list[float], label: str) -> Finding:
    """Whether the later half of the night sat deeper than the earlier half.

    Withheld below `MIN_ATTEMPTS_FOR_MOVEMENT`, and allowed to conclude nothing
    above it. "No movement we can distinguish" is the truthful answer to a real
    measured night, and a tool that manufactures a slope from that data is worse
    than one that stays quiet.

    `derived` rather than `measured`: splitting a night into halves is a
    modelling choice that could be wrong. The detail says so.
    """
    if len(depths) < MIN_ATTEMPTS_FOR_MOVEMENT:
        return Finding(
            id="progression.movement",
            title="Movement across the night is not compared",
            detail=(
                f"{len(depths)} attempts qualified and at least "
                f"{MIN_ATTEMPTS_FOR_MOVEMENT} are needed to split a night into halves "
                "worth comparing. Below that the two sides are anecdotes."
            ),
            confidence=Confidence.DERIVED,
        )

    half = len(depths) // 2
    early, late = median(depths[:half]), median(depths[len(depths) - half:])
    gap = early - late

    if abs(gap) < 5.0:
        title = "No movement we can distinguish across the night"
        detail = (
            f"The earlier attempts sat at a median of {early:.1f}% and the later ones "
            f"at {late:.1f}% ({label}). That is not a difference this tool will call a "
            "direction. A raid that pushes deep once and does not repeat it is the "
            "ordinary shape of progression, not a decline."
        )
    elif gap > 0:
        title = f"Later attempts went deeper, by {gap:.1f} points of median ({label})"
        detail = (
            f"The earlier attempts sat at a median of {early:.1f}% and the later ones "
            f"at {late:.1f}% ({label}). Splitting a night in half is a modelling "
            "choice, and this states the two halves rather than a rate."
        )
    else:
        title = f"Later attempts sat shallower, by {-gap:.1f} points of median ({label})"
        detail = (
            f"The earlier attempts sat at a median of {early:.1f}% and the later ones "
            f"at {late:.1f}% ({label}). Fatigue, a roster change and a strategy "
            "experiment all look like this, and the log distinguishes none of them."
        )

    return Finding(
        id="progression.movement",
        title=title,
        detail=detail,
        confidence=Confidence.DERIVED,
        evidence=(
            f"earlier half median {early:.1f}%",
            f"later half median {late:.1f}%",
            f"{len(depths)} attempts, split into halves of {half}",
        ),
    )
