# ABOUTME: Behaviour tests for the report's frame: header, narrative, provenance, withholding.
# ABOUTME: The withheld reason must come from the finding, never from a string in the template.

from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Pull, Run
from wowperf.domain.report.build import build_report, format_seconds
from wowperf.domain.report.model import SectionState

FETCHED = "2026-09-05 14:02"


def a_pull(index: int, start: int, end: int, encounter_id: int = 0) -> Pull:
    return Pull(
        index=index,
        pull_id=index,
        name=f"Pack {index}",
        encounter_id=encounter_id,
        start_ms=start,
        end_ms=end,
        killed=True,
        x=100,
        y=200,
        enemies=(),
    )


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "report_code": "abc123",
        "fight_id": 36,
        "dungeon_name": "Den of Nalorakk",
        "encounter_id": 12825,
        "keystone_level": 16,
        "affix_ids": (9, 10),
        "keystone_time_ms": 1_800_000,
        "keystone_bonus": 1,
        "count_reached": 100,
        "count_required": 100,
        "npc_counts": (),
        "players": (),
        "pulls": (a_pull(0, 0, 60_000),),
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_loaded(**overrides: object) -> LoadedRun:
    return LoadedRun(run=a_run(**overrides))


def unavailable(finding_id: str, detail: str) -> Finding:
    return Finding(
        id=finding_id,
        title="Nothing to compare against",
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
    )


def test_the_header_states_the_dungeon_and_the_key() -> None:
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.header.dungeon == "Den of Nalorakk"
    assert report.header.keystone_level == 16


def test_a_timed_run_says_so_and_by_how_much() -> None:
    # 60s of pulls against a 1800s key: timed with a lot to spare.
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.header.result.startswith("Timed")


def test_a_depleted_run_says_so_and_by_how_much() -> None:
    report = build_report(a_loaded(keystone_bonus=0), (), None, None, None, FETCHED)
    assert report.header.result.startswith("Depleted")


def test_no_narrative_leaves_the_section_absent_rather_than_withheld() -> None:
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.narrative is None


def test_a_narrative_is_carried_through_verbatim() -> None:
    report = build_report(a_loaded(), (), None, None, "Both losses were travel.", FETCHED)
    assert report.narrative == "Both losses were travel."


def test_a_withheld_section_takes_its_reason_from_the_finding() -> None:
    detail = "The speed leaderboard returned nothing for this dungeon."
    report = build_report(
        a_loaded(), (unavailable("compare.speed.unavailable", detail),), None, None, None, FETCHED
    )
    assert report.timeline.section.state is SectionState.WITHHELD
    assert report.timeline.section.reason == detail


def test_a_withheld_section_with_no_finding_still_says_something_true() -> None:
    # `--no-compare` emits no unavailable finding at all, because no comparison ran.
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.timeline.section.state is SectionState.WITHHELD
    assert report.timeline.section.reason


def test_provenance_lists_every_withheld_section() -> None:
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert any("timeline" in line.lower() for line in report.provenance.withheld)


def test_provenance_carries_the_report_code_and_the_fetch_time() -> None:
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.provenance.report_code == "abc123"
    assert report.provenance.fetched_at == FETCHED


def test_seconds_format_as_minutes_and_seconds() -> None:
    assert format_seconds(252.0) == "4:12"
    assert format_seconds(9.4) == "0:09"


def test_no_seconds_formats_as_nothing_rather_than_zero() -> None:
    assert format_seconds(None) is None
