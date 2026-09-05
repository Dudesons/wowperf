# ABOUTME: Turns a loaded run and its findings into the value the template renders.
# ABOUTME: Every judgement about what appears where lives here, and nowhere else.

from collections.abc import Sequence

from wowperf.domain.comparison.reference import ParseReference, SpeedReference
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Run
from wowperf.domain.report.model import (
    Badge,
    Header,
    LedgerRow,
    Provenance,
    Report,
    Section,
    SectionState,
    Timeline,
)

SPEED_UNAVAILABLE_ID = "compare.speed.unavailable"
PARSE_UNAVAILABLE_ID = "compare.parse.unavailable"

# Said when `--no-compare` skipped the comparison entirely, so no finding explains the absence.
NO_COMPARISON_RAN = (
    "No reference run was fetched for this analysis, so there is nothing to compare against."
)

REPORT_URL = "https://www.warcraftlogs.com/reports/{code}?fight={fight}"

DECOMPOSITION_IDS = ("compare.duration", "time.residual", "deaths.total")
"""Figures that contain others. They head the ledger; everything else is ranked beneath."""

NESTS_INSIDE = (
    ("time.gap.", "time.residual"),
    ("compare.downtime", "time.residual"),
    ("deaths.single.", "deaths.total"),
    ("deaths.chain.", "deaths.total"),
    ("compare.route.skipped.", "trash.overage"),
)
"""Which figures are already contained by which, copied from the findings file's own warning.

Stated rather than inferred: the relationships come from what the analysers
measure, and they change when an analyser changes, not when a report renders.
`compare.duration` contains every figure here and is a decomposition row rather
than a parent — repeating it on every line would be noise.

Entries must stay mutually non-overlapping: `parent_of` resolves by first match
in tuple order, so a broader prefix placed ahead of a narrower one would
silently win and misattribute nesting.
"""


def badge_for(confidence: Confidence) -> Badge:
    """A word and a palette token. The word is what a reader without colour sees."""
    return Badge(label=str(confidence), tint=f"badge-{confidence}")


def format_seconds(seconds: float | None) -> str | None:
    """Minutes and seconds, or nothing at all.

    `None` stays `None` rather than becoming "0:00": a finding with no honest
    seconds figure must not read as one that cost no time.
    """
    if seconds is None:
        return None
    whole = int(round(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def _finding_by_id(findings: Sequence[Finding], finding_id: str) -> Finding | None:
    return next((finding for finding in findings if finding.id == finding_id), None)


def _section_for(findings: Sequence[Finding], unavailable_id: str, present: bool) -> Section:
    """Present, or withheld with the reason the comparison itself gave.

    When no comparison ran at all there is no finding to quote, so the fallback
    states that plainly rather than implying a leaderboard came back empty.
    """
    if present:
        return Section(state=SectionState.PRESENT)
    finding = _finding_by_id(findings, unavailable_id)
    return Section(
        state=SectionState.WITHHELD,
        reason=finding.detail if finding else NO_COMPARISON_RAN,
    )


def _run_seconds(run: Run) -> float:
    """Wall-clock span from the first pull's start to the last pull's end.

    Not `total_pull_seconds`, which sums pull durations and so omits every
    second spent travelling — the very time this report exists to show.
    """
    if not run.pulls:
        return 0.0
    return (max(p.end_ms for p in run.pulls) - min(p.start_ms for p in run.pulls)) / 1000


def _header(loaded: LoadedRun) -> Header:
    run = loaded.run
    verb = "Timed" if run.keystone_bonus >= 1 else "Depleted"
    duration = format_seconds(run.keystone_time_seconds)
    assert duration is not None  # keystone_time_seconds is never None
    return Header(
        dungeon=run.dungeon_name,
        keystone_level=run.keystone_level,
        affixes=tuple(str(affix_id) for affix_id in run.affix_ids),
        result=f"{verb} in {duration}",
    )


def _reference_url(report_code: str, fight_id: int) -> str:
    return REPORT_URL.format(code=report_code, fight=fight_id)


def parent_of(finding_id: str) -> str | None:
    """The figure this one is already contained by, if any."""
    for prefix, parent in NESTS_INSIDE:
        if finding_id.startswith(prefix):
            return parent
    return None


def _ledger_row(finding: Finding, titles_by_id: dict[str, str]) -> LedgerRow:
    """Format one finding for display.

    `nests_inside` carries the parent finding's title, not its id: the id is
    an internal identifier and never belongs on a page a person reads. When
    the parent finding is not among this run's findings, `nests_inside` stays
    `None` — a pointer to a row that is not on the page is worse than silence.
    """
    parent_id = parent_of(finding.id)
    return LedgerRow(
        finding_id=finding.id,
        title=finding.title,
        detail=finding.detail,
        badge=badge_for(finding.confidence),
        seconds=format_seconds(finding.seconds_lost),
        nests_inside=titles_by_id.get(parent_id) if parent_id is not None else None,
        evidence=finding.evidence,
    )


def build_report(
    loaded: LoadedRun,
    findings: Sequence[Finding],
    speed: SpeedReference | None,
    parse: ParseReference | None,
    narrative: str | None,
    fetched_at: str,
) -> Report:
    """Everything the page shows, decided here so the template decides nothing.

    `fetched_at` is a parameter rather than a clock read: the domain performs no
    I/O, and the same inputs must render the same report.
    """
    timeline_section = _section_for(findings, SPEED_UNAVAILABLE_ID, speed is not None)

    withheld: list[str] = []
    if timeline_section.state is SectionState.WITHHELD:
        withheld.append(f"Aligned timeline: {timeline_section.reason}")

    titles_by_id = {finding.id: finding.title for finding in findings}

    return Report(
        header=_header(loaded),
        narrative=narrative,
        ledger_decomposition=tuple(
            _ledger_row(finding, titles_by_id)
            for finding in findings
            if finding.seconds_lost is not None and finding.id in DECOMPOSITION_IDS
        ),
        ledger_losses=tuple(
            _ledger_row(finding, titles_by_id)
            for finding in findings
            if finding.seconds_lost is not None and finding.id not in DECOMPOSITION_IDS
        ),
        timeline=Timeline(section=timeline_section),
        deaths=(),
        interrupts=(),
        players=(),
        provenance=Provenance(
            report_code=loaded.run.report_code,
            fight_id=loaded.run.fight_id,
            fetched_at=fetched_at,
            speed_reference_url=(
                _reference_url(speed.row.report_code, speed.row.fight_id) if speed else None
            ),
            parse_reference_url=(
                _reference_url(parse.row.report_code, parse.row.fight_id) if parse else None
            ),
            withheld=tuple(withheld),
        ),
    )
