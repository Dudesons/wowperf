# ABOUTME: What repeated across a night's attempts: the phase, the collapse, who fell first.
# ABOUTME: Counts and presence only -- naming a mechanic as missed is the one claim forbidden here.

from collections import Counter

from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import Progression


def repeat_phase(progression: Progression) -> Finding | None:
    """How many attempts ended in the same phase, or nothing.

    Gated on `separates_wipes`, which is the API's own opinion about whether
    phase is a meaningful way to group this encounter's attempts. Two of the
    eight encounters measured on 2026-09-16 report no phase table at all and
    two more report `separatesWipes: false`, so silence is the common case
    rather than the defensive one.

    `last_phase` is a `PhaseMetadata.id` -- measured across all eight, and the
    reason the name is looked up rather than derived from `phase_transitions`,
    whose last entry disagreed with `last_phase` on one of them.
    """
    if not progression.separates_wipes or not progression.phases:
        return None

    ended_in = [
        a.last_phase for a in progression.attempts if a.last_phase is not None and a.last_phase
    ]
    if len(ended_in) < 2:
        return None

    phase_id, count = Counter(ended_in).most_common(1)[0]
    names = {phase.id: phase.name for phase in progression.phases}
    name = names.get(phase_id, f"phase {phase_id}")

    return Finding(
        id="progression.repeat.phase",
        title=f"{count} of {len(ended_in)} attempts ended in {name}",
        detail=(
            f"The report groups this encounter's attempts by phase, so where an attempt "
            f"ended is a fact it states outright. {count} of the {len(ended_in)} attempts "
            f"carrying a phase ended in {name}. This counts where attempts ended and says "
            "nothing about why."
        ),
        confidence=Confidence.MEASURED,
        evidence=(
            f"{count} of {len(ended_in)} attempts ended in {name}",
            f"phase table carries {len(progression.phases)} phases",
        ),
    )
