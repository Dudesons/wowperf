# ABOUTME: Behaviour tests for the report's frame: header, narrative, provenance, withholding.
# ABOUTME: The withheld reason must come from the finding, never from a string in the template.

from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import EnemyNpc, LoadedRun, Player, Pull, Run
from wowperf.domain.report.build import _run_seconds, badge_for, build_report, format_seconds
from wowperf.domain.report.model import SectionState
from wowperf.domain.season import Consumables, Defensives

FETCHED = "2026-09-05 14:02"


NO_CONSUMABLES = Consumables()
"""As above, for consumables: the tool checked nothing."""

NO_DEFENSIVES = Defensives(entries=())
"""The report tests whose subject is not defensives. Says the tool checked nothing."""


def a_player(actor_id: int = 1, name: str = "Stonewake") -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=680
    )


def a_pull(
    index: int, start: int, end: int, encounter_id: int = 0, enemies: tuple[int, ...] = ()
) -> Pull:
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
        enemies=tuple(EnemyNpc(actor_id=n, game_id=n) for n in enemies),
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
    report = build_report(a_loaded(), (), None, None, a_player(), None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES)
    assert report.header.dungeon == "Den of Nalorakk"
    assert report.header.keystone_level == 16


def test_a_timed_run_states_the_verb_and_the_completion_time() -> None:
    # keystoneTime is Blizzard's penalty-inclusive completion time, not the key's
    # time limit: 1_908_000 ms is 31:48, whatever the dungeon's par time is.
    report = build_report(
        a_loaded(keystone_time_ms=1_908_000), (), None, None, a_player(), None, FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
    )
    assert report.header.result == "Timed in 31:48"


def test_a_depleted_run_states_the_verb_and_the_completion_time() -> None:
    report = build_report(
        a_loaded(keystone_bonus=0, keystone_time_ms=2_052_000),
        (),
        None,
        None,
        a_player(),
        None,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
    )
    assert report.header.result == "Depleted in 34:12"


def test_the_header_names_the_affixes_when_names_are_known() -> None:
    report = build_report(
        a_loaded(affix_ids=(9, 10), affix_names=("Tyrannical", "Fortified")),
        (), None, None, a_player(), None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )
    assert report.header.affixes == ("Tyrannical", "Fortified")


def test_the_header_falls_back_to_ids_when_no_name_was_resolved() -> None:
    report = build_report(
        a_loaded(affix_ids=(9, 10)),
        (), None, None, a_player(), None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )
    assert report.header.affixes == ("9", "10")


def test_no_narrative_leaves_the_section_absent_rather_than_withheld() -> None:
    report = build_report(a_loaded(), (), None, None, a_player(), None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES)
    assert report.narrative is None


def test_a_narrative_is_carried_through_verbatim() -> None:
    report = build_report(
        a_loaded(), (), None, None, a_player(), "Both losses were travel.", FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
    )
    assert report.narrative == "Both losses were travel."


def test_a_withheld_section_takes_its_reason_from_the_finding() -> None:
    detail = "The speed leaderboard returned nothing for this dungeon."
    report = build_report(
        a_loaded(),
        (unavailable("compare.speed.unavailable", detail),),
        None,
        None,
        a_player(),
        None,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
    )
    assert report.timeline.section.state is SectionState.WITHHELD
    assert report.timeline.section.reason == detail


def test_a_withheld_section_with_no_finding_still_says_something_true() -> None:
    # `--no-compare` emits no unavailable finding at all, because no comparison ran.
    report = build_report(a_loaded(), (), None, None, a_player(), None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES)
    assert report.timeline.section.state is SectionState.WITHHELD
    assert report.timeline.section.reason


def test_provenance_lists_every_withheld_section() -> None:
    report = build_report(a_loaded(), (), None, None, a_player(), None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES)
    assert any("timeline" in line.lower() for line in report.provenance.withheld)


def test_provenance_carries_the_report_code_and_the_fetch_time() -> None:
    report = build_report(a_loaded(), (), None, None, a_player(), None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES)
    assert report.provenance.report_code == "abc123"
    assert report.provenance.fetched_at == FETCHED


def test_seconds_format_as_minutes_and_seconds() -> None:
    assert format_seconds(252.0) == "4:12"
    assert format_seconds(9.4) == "0:09"


def test_no_seconds_formats_as_nothing_rather_than_zero() -> None:
    assert format_seconds(None) is None


def test_run_seconds_spans_first_pull_start_to_last_pull_end() -> None:
    run = a_run(pulls=(a_pull(0, 10_000, 40_000), a_pull(1, 50_000, 130_000)))
    assert _run_seconds(run) == 120.0


def test_run_seconds_is_zero_with_no_pulls() -> None:
    run = a_run(pulls=())
    assert _run_seconds(run) == 0.0


def test_badge_for_measured() -> None:
    badge = badge_for(Confidence.MEASURED)
    assert badge.label == "measured"
    assert badge.tint == "badge-measured"


def test_badge_for_derived() -> None:
    badge = badge_for(Confidence.DERIVED)
    assert badge.label == "derived"
    assert badge.tint == "badge-derived"


def test_badge_for_inferred() -> None:
    badge = badge_for(Confidence.INFERRED)
    assert badge.label == "inferred"
    assert badge.tint == "badge-inferred"
