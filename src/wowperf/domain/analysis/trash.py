# ABOUTME: How much trash was killed against how much was needed, and which packs paid worst.
# ABOUTME: The overage percentage is measured; its cost in seconds is a labelled estimate.

from collections import defaultdict

from wowperf.domain.events import EnemyDeath
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run

OVERKILL_FLOOR_PERCENT = 2.0
"""Below this an overage is a wandering patrol, not a routing decision."""

MAX_PULLS_REPORTED = 3


def analyse_trash(run: Run, enemy_deaths: tuple[EnemyDeath, ...]) -> list[Finding]:
    """Report trash killed beyond the requirement, and the packs that bought least."""
    if run.count_required <= 0:
        return []

    percent = run.count_reached / run.count_required * 100
    overage_percent = percent - 100
    trash_seconds = sum(pull.duration_seconds for pull in run.trash_pulls)

    findings: list[Finding] = []
    if overage_percent >= OVERKILL_FLOOR_PERCENT:
        wasted = trash_seconds * (overage_percent / percent)
        findings.append(
            Finding(
                id="trash.overage",
                title=f"{overage_percent:.0f}% more trash than the key required",
                detail=(
                    f"The group killed {run.count_reached} of {run.count_required} required "
                    f"forces. Spread across {trash_seconds:.0f}s of trash pulls, the excess "
                    f"is worth roughly {wasted:.0f}s."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=wasted,
                evidence=(
                    f"{run.count_reached}/{run.count_required} forces = {percent:.0f}%",
                    f"{trash_seconds:.0f}s spent in {len(run.trash_pulls)} trash pulls",
                    "seconds are apportioned from the percentage, not measured directly",
                ),
            )
        )

        # The per-pull ranking says where the overkill went, so it has nothing to
        # explain unless trash.overage actually fired.
        forces_by_pull: dict[int, int] = defaultdict(int)
        for death in enemy_deaths:
            if death.pull_index is not None:
                forces_by_pull[death.pull_index] += death.forces

        rates = [
            (pull.index, forces_by_pull.get(pull.index, 0) / pull.duration_seconds)
            for pull in run.trash_pulls
            if pull.duration_seconds > 0
        ]
        for rank, (pull_index, rate) in enumerate(sorted(rates, key=lambda item: item[1])):
            if rank >= MAX_PULLS_REPORTED:
                break
            pull = run.pulls[pull_index]
            findings.append(
                Finding(
                    id=f"trash.pull.{rank}",
                    title=f"Pull {pull_index} bought {rate:.1f} forces per second",
                    detail=(
                        f"{forces_by_pull.get(pull_index, 0)} forces over "
                        f"{pull.duration_seconds:.0f}s."
                    ),
                    confidence=Confidence.MEASURED,
                    seconds_lost=None,
                    evidence=(pull.name,),
                    pull_index=pull_index,
                )
            )
    return findings
