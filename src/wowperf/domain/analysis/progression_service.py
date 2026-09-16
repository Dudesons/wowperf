# ABOUTME: What a night of attempts may claim: where they sit, and whether the night moved.
# ABOUTME: It never claims a slope -- a real night's deepest attempt was its third of eight.

from statistics import median

from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import Progression, remaining_percent

MIN_ATTEMPTS_FOR_MOVEMENT = 6
"""Below this the night is not split into halves at all.

Six qualifying attempts is three a side. The keystone comparison falls back
below three comparable references for the same reason: two figures are an
anecdote, and a claim drawn from them reads exactly as confident as one drawn
from fifty.
"""


def _depth_label(progression: Progression) -> str:
    """Which percentage the figures in this report are, in one word."""
    uses_boss = any(a.boss_percentage is not None for a in progression.attempts)
    return "boss health" if uses_boss else "encounter progress"


def analyse_progression(progression: Progression) -> list[Finding]:
    """Layer 1: where the attempts sit. Reads metadata only and fetches nothing."""
    findings: list[Finding] = []
    depths = [
        left for left in (remaining_percent(a) for a in progression.attempts)
        if left is not None
    ]
    if not depths:
        return findings

    label = _depth_label(progression)
    deepest = progression.deepest

    if deepest is not None:
        left = remaining_percent(deepest)
        assert left is not None
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
