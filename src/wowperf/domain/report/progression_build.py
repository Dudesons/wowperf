# ABOUTME: Turns a night of attempts and its findings into the value the page renders.
# ABOUTME: A sibling of raid_build.py with no death cards, no subject and no reference.

from collections.abc import Sequence

from wowperf.domain.findings import Finding
from wowperf.domain.progression import LoadedProgression
from wowperf.domain.report.build import _check_unique_finding_ids
from wowperf.domain.report.ledger import build_observations, place_rows, placed_finding_ids
from wowperf.domain.report.model import Section, SectionState
from wowperf.domain.report.progression_chart import build_attempts_chart
from wowperf.domain.report.progression_frame import build_attempt_rows, build_progression_header
from wowperf.domain.report.progression_ledger import PROGRESSION_PLACEMENTS
from wowperf.domain.report.progression_model import ProgressionProvenance, ProgressionReport

NOTHING_DEEPENED = (
    "No attempt was deepened, so there is nothing to compare the best one against."
)

METHOD_DEPTH_SCALE = (
    "Every percentage on this page is the same scale, chosen once for the whole series: "
    "boss health where every qualifying attempt carried one, and the encounter's own "
    "progress otherwise. Both count down -- a kill reads about 0.01 and an instant wipe "
    "reads 100 -- and the header names which scale this night is on."
)

METHOD_NO_ANATOMY = (
    "This page draws the night, never one attempt's internals. The health curves, what hit "
    "whom and what each player still had are `wowperf raid --fight N`'s work, and the "
    "findings that want them carry the invocation."
)


def build_progression_report(
    series: LoadedProgression,
    findings: Sequence[Finding],
    fetched_at: str,
) -> ProgressionReport:
    """Everything the progression page shows, decided here so the template decides nothing.

    `fetched_at` is a parameter rather than a clock read, because the domain
    performs no I/O and the same inputs must render the same page.

    Several of `build_raid_report`'s parameters are deliberately absent, and
    each absence is a fact about a night rather than an omission. There is no
    `subject`: a series is about a boss, not a raider, and no card on this page
    belongs to one. There are no `defensives`, `consumables`, `externals` or
    `self_resurrections`: those four exist to build death cards, and section 8
    forbids this page from redrawing one fight's anatomy. There are no
    `reference_records` and no `compared_slugs`: this command draws no external
    sample at all, which is what makes it an order of magnitude cheaper.
    """
    _check_unique_finding_ids(findings)
    titles_by_id = {finding.id: finding.title for finding in findings}
    placed = place_rows(findings, titles_by_id, set(), {}, placements=PROGRESSION_PLACEMENTS)

    deepened = len(series.loaded)
    best = (
        Section(state=SectionState.PRESENT)
        if deepened
        else Section(state=SectionState.WITHHELD, reason=NOTHING_DEEPENED)
    )
    withheld = (
        (f"Best attempt: {best.reason}",) if best.state is SectionState.WITHHELD else ()
    )

    placed_ids = placed_finding_ids((), placed, ())
    return ProgressionReport(
        header=build_progression_header(series),
        chart=build_attempts_chart(series),
        attempts=build_attempt_rows(series),
        attempt_rows=placed["attempt_rows"],
        repeat_rows=placed["repeat_rows"],
        best_rows=placed["best_rows"],
        best=best,
        observations=build_observations(findings, placed_ids, titles_by_id, {}),
        provenance=ProgressionProvenance(
            report_code=series.progression.report_code,
            encounter_id=series.progression.encounter_id,
            attempts_counted=len(series.progression.attempts),
            attempts_deepened=deepened,
            fetched_at=fetched_at,
            withheld=withheld,
            methods=(METHOD_DEPTH_SCALE, METHOD_NO_ANATOMY),
        ),
    )
