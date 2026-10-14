# ABOUTME: Builds the character page's view model: sections, run links, ledger strings, provenance.
# ABOUTME: Pure: the CLI hands it the runs and findings, and it decides every word the page prints.

from collections.abc import Sequence

from wowperf.domain.character.ledger import GroupColumn, GroupLedger
from wowperf.domain.character.model import (
    CharacterRun,
    CharacterSubject,
    FailedRun,
    Selection,
)
from wowperf.domain.character.patterns import (
    ANALYSIS_FAMILIES_NOT_COUNTED,
    CHARACTER_FINDINGS_ARE_RANKED_NOT_ADDITIVE,
    COUNTED_NOT_SUMMED,
    DIRECTION_RULE,
    DIRECTIONS_WITHHELD_ID,
    REPEAT_RULE,
)
from wowperf.domain.character.selection import SELECTION_RULE
from wowperf.domain.comparison.tempo import DURATION_WITHHELD_REASON
from wowperf.domain.findings import Finding, quantity
from wowperf.domain.report.character_model import (
    CharacterHeader,
    CharacterProvenance,
    CharacterReport,
    GroupRow,
    RunRow,
)
from wowperf.domain.report.ledger import ledger_row

SELECTION_QUERIES = ("Zone", "CharacterRuns")
"""The two operations that chose the runs, named as the cost printout names them.

The domain may not import the queries, so it spells their names here, and a
test beside the queries holds the two spellings together.
"""

_DIRECTION = "direction"
_REPEAT = "repeat"
_OTHER = "other"


def run_file(report_code: str, fight_id: int) -> str:
    """The run report's file name, beside the character page in the same directory."""
    return f"{report_code}-{fight_id}.html"


def _figure(value: float) -> str:
    """A median that may be a half: `1`, `0.5`, never `1.0`."""
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _section(finding_id: str) -> str:
    """Which list a finding's row goes in.

    The withheld directions are not a direction, but they stand where the
    directions would: under that heading, the empty state would say the
    directions were tested and none held, when none were tested at all.
    """
    if finding_id.startswith("character.direction."):
        return _DIRECTION
    if finding_id.startswith("character.repeat."):
        return _REPEAT
    return _OTHER


def _group_row(run: CharacterRun) -> GroupRow:
    tempo = run.tempo
    label = f"{run.dungeon} +{run.keystone_level}"
    file = run_file(run.report_code, run.fight_id)
    if tempo is None:
        missing = "too few fast runs"
        return GroupRow(label=label, report_file=file, time=missing, deaths=missing,
                        downtime=missing, kick_share=missing, your_deaths=str(run.subject_deaths))
    if tempo.their_time is None:
        time = f"{tempo.our_time:.0f}s; not compared"
        time_note = DURATION_WITHHELD_REASON
    else:
        time = f"{tempo.our_time:.0f}s against {tempo.their_time:.0f}s"
        time_note = ""
    kick = (
        f"none resolved, against {tempo.their_kick_share:.0%}"
        if tempo.our_kick_share is None
        else f"{tempo.our_kick_share:.0%} against {tempo.their_kick_share:.0%}"
    )
    return GroupRow(
        label=label,
        report_file=file,
        time=time,
        time_note=time_note,
        deaths=f"{tempo.our_deaths} against {_figure(tempo.their_deaths)}",
        downtime=f"{tempo.our_downtime:.0f}s against {tempo.their_downtime:.0f}s",
        kick_share=kick,
        your_deaths=str(run.subject_deaths),
    )


def _count(column: GroupColumn) -> str:
    if column.compared == 0:
        return "not compared"
    return (
        f"{column.above} above, {column.below} below, {column.level} on the median, "
        f"of {column.compared} compared"
    )


def build_character_report(
    subject: CharacterSubject,
    selection: Selection,
    runs: Sequence[CharacterRun],
    failed: Sequence[FailedRun],
    findings: Sequence[Finding],
    ledger: GroupLedger,
    narrative: str | None,
    fetched_at: str,
) -> CharacterReport:
    titles = {finding.id: finding.title for finding in findings}
    rows = [(_section(finding.id), ledger_row(finding, titles)) for finding in findings]
    read_line = (
        f"{quantity(len(runs), 'run', 'runs')} read, {len(failed)} failed to load, "
        f"{quantity(len(selection.left_out), 'dungeon', 'dungeons')} left out"
    )
    return CharacterReport(
        header=CharacterHeader(
            name=subject.name,
            realm_line=f"{subject.realm} ({subject.region.upper()})",
            zone=subject.zone_name,
            spec=selection.spec,
            read_line=read_line,
        ),
        narrative=narrative,
        direction_rows=tuple(row for section, row in rows if section == _DIRECTION),
        repeat_rows=tuple(row for section, row in rows if section == _REPEAT),
        other_rows=tuple(row for section, row in rows if section == _OTHER),
        group_rows=tuple(_group_row(run) for run in runs),
        group_counts=(
            _count(ledger.time),
            _count(ledger.deaths),
            _count(ledger.downtime),
            _count(ledger.kick_share),
            f"you died in {ledger.subject_died_in} of {quantity(len(runs), 'run', 'runs')}",
        ),
        runs=tuple(
            RunRow(
                dungeon=run.dungeon,
                level=f"+{run.keystone_level}",
                outcome="timed" if run.in_time else "not timed",
                report_file=run_file(run.report_code, run.fight_id),
            )
            for run in runs
        ),
        failed=tuple(
            f"{one.dungeon} +{one.keystone_level} (report {one.report_code}, fight "
            f"{one.fight_id}): {one.reason}"
            for one in failed
        ),
        left_out=tuple(f"{one.dungeon}: {one.reason}" for one in selection.left_out),
        provenance=CharacterProvenance(
            read_line=read_line,
            fetched_at=fetched_at,
            warning=CHARACTER_FINDINGS_ARE_RANKED_NOT_ADDITIVE,
            queries=SELECTION_QUERIES,
            withheld=tuple(finding.title for finding in findings
                           if finding.id == DIRECTIONS_WITHHELD_ID),
            methods=(SELECTION_RULE, REPEAT_RULE, DIRECTION_RULE, COUNTED_NOT_SUMMED,
                     ANALYSIS_FAMILIES_NOT_COUNTED),
        ),
    )
