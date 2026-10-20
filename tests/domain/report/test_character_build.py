# ABOUTME: Behaviour tests for the character page's builder: which row goes where, and the strings.
# ABOUTME: The template loops; every word and figure on the page is decided here.

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from tests.domain.character.builders import a_finding, a_run, a_tempo
from wowperf.domain.character.ledger import group_ledger
from wowperf.domain.character.model import (
    CharacterRun,
    CharacterSubject,
    FailedRun,
    LeftOut,
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
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.report.character_build import (
    SELECTION_QUERIES,
    build_character_report,
    run_file,
)
from wowperf.domain.report.character_model import (
    CharacterProvenance,
    CharacterReport,
    all_character_ledger_rows,
)

SUBJECT = CharacterSubject(name="Emberkin", realm="argent-dawn", region="eu",
                           zone_name="Mythic+ Season 2")
NARRATIVE = "Your losses are route, not rotation."
FINDINGS = (
    a_finding("character.direction.boss.433895", slug="", title="Direction title"),
    a_finding("character.repeat.compare.talents", slug="", title="Repeat title"),
    a_finding(DIRECTIONS_WITHHELD_ID, slug="", title="Withheld title",
              confidence=Confidence.MEASURED),
)


def two_runs() -> list[CharacterRun]:
    return [a_run(0, tempo=a_tempo()), a_run(1, in_time=False, subject_deaths=1)]


def a_report(*, findings: Sequence[Finding] = FINDINGS,
             narrative: str | None = NARRATIVE,
             runs: Sequence[CharacterRun] | None = None) -> CharacterReport:
    """Two runs read (one timed with a ledger, one not), one failed, one dungeon left out."""
    read = two_runs() if runs is None else list(runs)
    return build_character_report(
        SUBJECT,
        Selection(spec="Blood",
                  left_out=(LeftOut(dungeon="Murder Row", reason="no ranked run as Blood"),)),
        read,
        [FailedRun(dungeon="Kings' Rest", keystone_level=18, report_code="zzz999", fight_id=3,
                   reason="Report zzz999 was not found")],
        findings,
        group_ledger(read),
        narrative,
        "2026-10-14 09:30",
    )


def test_each_finding_lands_in_its_own_section() -> None:
    report = a_report(findings=FINDINGS[:2])
    assert [row.finding_id for row in report.direction_rows] == ["character.direction.boss.433895"]
    assert [row.finding_id for row in report.repeat_rows] == ["character.repeat.compare.talents"]
    assert report.other_rows == ()


def test_withheld_directions_sit_where_the_directions_would() -> None:
    """Under the directions' own heading, so the page never reads as though the
    directions were tested and none held, when none were tested at all."""
    report = a_report(findings=(FINDINGS[2], FINDINGS[1]))
    assert [row.finding_id for row in report.direction_rows] == [DIRECTIONS_WITHHELD_ID]
    assert report.other_rows == ()


def test_a_finding_of_an_unknown_family_is_kept_on_the_page() -> None:
    report = a_report(findings=(a_finding("character.someday.new", slug="", title="New"),))
    assert [row.finding_id for row in report.other_rows] == ["character.someday.new"]
    assert report.direction_rows == report.repeat_rows == ()


def test_a_row_carries_its_findings_title() -> None:
    [row] = a_report(findings=FINDINGS[:2]).direction_rows
    assert row.title == "Direction title"


def test_every_finding_row_is_walked_in_page_order() -> None:
    findings = (*FINDINGS[:2], a_finding("character.someday.new", slug="", title="New"))
    report = a_report(findings=tuple(reversed(findings)))
    assert [row.finding_id for row in all_character_ledger_rows(report)] == [
        "character.direction.boss.433895",
        "character.repeat.compare.talents",
        "character.someday.new",
    ]


def test_a_section_keeps_the_order_its_findings_came_in() -> None:
    ids = ("character.direction.trash.2", "character.repeat.deaths.total",
           "character.direction.boss.1", "character.repeat.compare.route.skipped")
    report = a_report(findings=tuple(a_finding(i, slug="", title=i) for i in ids))
    assert [row.finding_id for row in report.direction_rows] == [
        "character.direction.trash.2", "character.direction.boss.1",
    ]
    assert [row.finding_id for row in report.repeat_rows] == [
        "character.repeat.deaths.total", "character.repeat.compare.route.skipped",
    ]


def test_the_header_names_the_character_zone_and_spec() -> None:
    header = a_report().header
    assert header.name == "Emberkin"
    assert header.realm_line == "argent-dawn (EU)"
    assert header.zone == "Mythic+ Season 2"
    assert header.spec == "Blood"
    assert header.read_line == "2 runs read, 1 failed to load, 1 dungeon left out"


def test_the_read_line_counts_a_single_run_in_the_singular() -> None:
    assert a_report(runs=[a_run(0)]).header.read_line.startswith("1 run read, ")


def test_a_run_row_links_its_own_report_file() -> None:
    [first, second] = a_report().runs
    assert first.report_file == run_file("code000x", 1) == "code000x-1.html"
    assert first.dungeon == "Altar of Fangs"
    assert first.level == "+18"
    assert first.outcome == "timed"
    assert second.outcome == "not timed"


def test_the_group_rows_state_ours_against_the_median() -> None:
    [first, second] = a_report().group_rows
    assert first.label == "Altar of Fangs +18"
    assert first.report_file == "code000x-1.html"
    assert first.time == "1800s against 1700s"
    assert first.time_note == ""
    assert first.deaths == "2 against 1"
    assert first.downtime == "90s against 100s"
    assert first.kick_share == "30% against 30%"
    assert first.your_deaths == "0"
    assert second.time == "too few fast runs"
    assert second.your_deaths == "1"


def test_a_withheld_time_is_not_compared_and_says_why() -> None:
    [row] = a_report(runs=[a_run(0, tempo=a_tempo(their_time=None))]).group_rows
    assert row.time == "1800s; not compared"
    assert row.time_note == DURATION_WITHHELD_REASON


def test_a_withheld_time_says_why_whatever_ledger_it_is_built_with() -> None:
    runs = [a_run(0, tempo=a_tempo(their_time=None))]
    report = build_character_report(SUBJECT, Selection(spec="Blood"), runs, [], (),
                                    group_ledger([]), None, "2026-10-14 09:30")
    [row] = report.group_rows
    assert row.time_note == DURATION_WITHHELD_REASON


def test_a_run_with_no_resolved_kicks_states_none() -> None:
    [row] = a_report(runs=[a_run(0, tempo=a_tempo(kick=None))]).group_rows
    assert row.kick_share == "none resolved, against 30%"


def test_the_group_counts_state_sides_and_never_a_verdict() -> None:
    counts = a_report().group_counts
    assert counts == (
        "1 above, 0 below, 0 on the median, of 1 compared",
        "1 above, 0 below, 0 on the median, of 1 compared",
        "0 above, 1 below, 0 on the median, of 1 compared",
        "0 above, 0 below, 1 on the median, of 1 compared",
        "you died in 1 of 2 runs",
    )


def test_a_column_no_run_reached_says_so() -> None:
    counts = a_report(runs=[a_run(0)]).group_counts
    assert counts[0] == "not compared"


def test_failed_runs_and_left_out_dungeons_are_named_with_their_reasons() -> None:
    report = a_report()
    assert report.failed == (
        "Kings' Rest +18 (report zzz999, fight 3): Report zzz999 was not found",
    )
    assert report.left_out == ("Murder Row: no ranked run as Blood",)


def test_the_provenance_states_every_rule_and_the_warning() -> None:
    provenance = a_report().provenance
    assert provenance.warning == CHARACTER_FINDINGS_ARE_RANKED_NOT_ADDITIVE
    assert provenance.methods == (SELECTION_RULE, REPEAT_RULE, DIRECTION_RULE,
                                  COUNTED_NOT_SUMMED, ANALYSIS_FAMILIES_NOT_COUNTED)
    assert provenance.fetched_at == "2026-10-14 09:30"
    assert provenance.read_line == "2 runs read, 1 failed to load, 1 dungeon left out"


def test_the_provenance_names_the_queries_that_chose_the_runs() -> None:
    assert a_report().provenance.queries == SELECTION_QUERIES == ("Zone", "CharacterRuns")


def test_a_provenance_cannot_be_built_without_naming_its_queries() -> None:
    """An empty list would print "chosen by these queries: ." on the page."""
    with pytest.raises(ValidationError):
        CharacterProvenance(read_line="", fetched_at="", warning="")  # type: ignore[call-arg]


def test_the_provenance_lists_the_withheld_directions_by_their_title() -> None:
    assert a_report().provenance.withheld == ("Withheld title",)


def test_a_page_that_withheld_nothing_lists_nothing_withheld() -> None:
    report = a_report(findings=FINDINGS[:2])
    assert report.provenance.withheld == ()


def test_the_narrative_is_carried_as_given() -> None:
    assert a_report().narrative == "Your losses are route, not rotation."
    assert a_report(narrative=None).narrative is None
