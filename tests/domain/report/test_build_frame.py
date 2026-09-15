# ABOUTME: Behaviour tests for the report's frame: header, narrative, provenance, withholding.
# ABOUTME: The withheld reason must come from the finding, never from a string in the template.

import pytest

from wowperf.domain.comparison.measures import AbilityRate, PlayerMeasures, Stretch, Verdict
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import EnemyNpc, LoadedRun, Player, Pull, Run
from wowperf.domain.report.build import build_report
from wowperf.domain.report.frame import NO_COMPARISON_RAN, badge_for, format_seconds, run_seconds
from wowperf.domain.report.model import ReferenceRecord, SectionState
from wowperf.domain.season import Consumables, CooldownAbility, Defensives, ThroughputCooldowns

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


def test_two_findings_sharing_an_id_are_refused_rather_than_silently_collapsed() -> None:
    # This branch shipped the same defect three times: a finding id reused
    # across two rows, colliding into one DOM element id once the page
    # rendered. Each was only caught by hand, because `titles_by_id` right
    # below this guard is a plain dict keyed by `finding.id` and would
    # otherwise just drop one title with nothing to show for it. No fixture is
    # needed to keep this test alive: two findings sharing an id is enough.
    findings = (
        unavailable("compare.gear.tier", "first"),
        unavailable("compare.gear.tier", "second"),
    )
    with pytest.raises(ValueError) as excinfo:
        build_report(a_loaded(), findings, None, None, a_player(), None, FETCHED,
                      NO_DEFENSIVES, NO_CONSUMABLES)
    assert "compare.gear.tier" in str(excinfo.value)


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


def test_provenance_names_the_player_whose_comparison_was_withheld() -> None:
    # One line per player who was asked for and got nothing, naming them: with a
    # card per player, an unqualified "Spell and talent comparison" line no longer
    # says whose. The teammate nobody asked for is deliberately absent -- their
    # comparison was not withheld, it was never requested.
    loaded = a_loaded(players=(a_player(1, "Emberkin"), a_player(2, "Stonewake")))
    detail = "The score leaderboard returned nothing for this specialisation."
    report = build_report(
        loaded,
        (unavailable("compare.parse.unavailable.emberkin-0", detail),),
        None,
        frozenset({"emberkin-0"}),
        a_player(1, "Emberkin"),
        None,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
    )
    assert [line for line in report.provenance.withheld if "Spell and talent" in line] == [
        f"Spell and talent comparison for Emberkin: {detail}"
    ]


def test_no_compare_withholds_the_comparison_once_not_once_per_player() -> None:
    # `--no-compare` fetched no reference at all, so the whole run gets one
    # report-level line. A line per card here would say a comparison for each
    # of them was asked for and refused, when none was ever asked for.
    loaded = a_loaded(players=(a_player(1, "Emberkin"), a_player(2, "Stonewake")))
    report = build_report(
        loaded, (), None, None, a_player(1, "Emberkin"), None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
    )
    comparison_lines = [line for line in report.provenance.withheld if "Spell and talent" in line]
    assert comparison_lines == [f"Spell and talent comparison: {NO_COMPARISON_RAN}"]


def test_provenance_carries_the_report_code_and_the_fetch_time() -> None:
    report = build_report(a_loaded(), (), None, None, a_player(), None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES)
    assert report.provenance.report_code == "abc123"
    assert report.provenance.fetched_at == FETCHED


def _a_record(index: int, *, loaded: bool = True, reason: str = "") -> ReferenceRecord:
    return ReferenceRecord(
        report_code=f"ref{index}", fight_id=index, keystone_level=16,
        url=f"https://www.warcraftlogs.com/reports/ref{index}?fight={index}", axis="speed",
        loaded=loaded, reason=reason,
    )


def test_provenance_lists_every_candidate_considered() -> None:
    # Five loaded, two that failed: every row `_samples` weighed reaches the
    # report, not only the ones that ended up in the sample.
    records = (
        *(_a_record(i) for i in range(5)),
        _a_record(5, loaded=False, reason="this is the run under analysis"),
        _a_record(6, loaded=False, reason="the report failed to load"),
    )
    report = build_report(
        a_loaded(), (), None, None, a_player(), None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
        reference_records=records,
    )
    assert report.provenance.references == records
    assert len(report.provenance.references) == 7


def test_provenance_carries_no_reference_character_name() -> None:
    # `ReferenceRecord` has no field to hold a name in the first place (see
    # `test_a_reference_record_has_no_field_for_a_name_a_duration_or_a_death_count`
    # in test_model.py); this proves that `build_report`'s own wiring carries
    # the records through unchanged, over the whole serialised record rather
    # than one field, without smuggling anything else in beside it.
    record = _a_record(0, loaded=False, reason="the roster includes one of our own characters")
    report = build_report(
        a_loaded(), (), None, None, a_player(), None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
        reference_records=(record,),
    )
    for reference in report.provenance.references:
        dumped = reference.model_dump_json()
        assert "Stonewake" not in dumped  # a_player()'s own name
        assert "Fastclear" not in dumped  # a plausible reference character name


def test_seconds_format_as_minutes_and_seconds() -> None:
    assert format_seconds(252.0) == "4:12"
    assert format_seconds(9.4) == "0:09"


def test_no_seconds_formats_as_nothing_rather_than_zero() -> None:
    assert format_seconds(None) is None


def test_a_negative_figure_counts_back_from_zero_rather_than_wrapping() -> None:
    """Floor division and modulo disagree about sign, and the result reads as a
    time that is not close to the one meant.

    `-6 // 60` is -1 and `-6 % 60` is 54, so six seconds before an origin
    printed as "-1:54" -- off by nearly two minutes, and in the direction that
    makes it look like a real figure rather than a bug. It also ordered wrongly:
    across the minute boundary an earlier moment printed as the later one.
    """
    assert format_seconds(-6.0) == "-0:06"
    assert format_seconds(-9.8) == "-0:10"
    assert format_seconds(-110.0) == "-1:50"
    assert format_seconds(-117.0) == "-1:57"
    # Zero keeps no sign, and the boundary does not gain one by rounding.
    assert format_seconds(-0.4) == "0:00"


def test_negative_figures_keep_their_order_when_formatted() -> None:
    # The defect this replaces was not only a wrong figure: -10 printed as
    # "-1:50" and -3 as "-1:57", so a reader comparing two hovers read the
    # earlier moment as the later one.
    marks = [-117.0, -110.0, -60.0, -6.0, 0.0, 6.0]
    formatted = [format_seconds(second) for second in marks]
    assert formatted == ["-1:57", "-1:50", "-1:00", "-0:06", "0:00", "0:06"]


def test_run_seconds_spans_first_pull_start_to_last_pull_end() -> None:
    run = a_run(pulls=(a_pull(0, 10_000, 40_000), a_pull(1, 50_000, 130_000)))
    assert run_seconds(run) == 120.0


def test_run_seconds_is_zero_with_no_pulls() -> None:
    run = a_run(pulls=())
    assert run_seconds(run) == 0.0


def test_the_window_opens_at_the_first_pull_and_closes_at_the_last() -> None:
    run = a_run(pulls=(a_pull(0, 10_000, 40_000), a_pull(1, 50_000, 130_000)))
    assert run.window_ms == (10_000, 130_000)


def test_the_window_is_zero_wide_with_no_pulls() -> None:
    assert a_run(pulls=()).window_ms == (0, 0)


def test_the_windows_end_is_exactly_the_span_run_seconds_reports() -> None:
    """The one equality `model.py` and `frame.py` must hold to and cannot import.

    `Run.window_ms` computes the end in `domain/model.py`. `run_seconds`
    computes the same span in `domain/report/frame.py`, which `model.py` may
    not import and which does not read that property. Until this assertion
    nothing stated the agreement, so an edit to either side could diverge in
    silence -- and a divergence moves where an aura band gets clipped on real
    runs, which no other test would notice.

    The span is 1001 ms rather than a round number because the truncation is
    part of the equality: `int(1.001 * 1000)` is 1000, and an assertion
    written over a whole second would hold whichever way either side rounded.
    The start is not zero either, so an end computed from the span alone
    cannot pass by coincidence.
    """
    run = a_run(pulls=(a_pull(0, 10_000, 11_001),))

    start, end = run.window_ms

    assert end == start + int(run_seconds(run) * 1000)
    assert end != max(pull.end_ms for pull in run.pulls), "the span dodged the truncation"


def test_the_windows_end_keeps_the_millisecond_the_span_arithmetic_drops() -> None:
    """A deliberate quirk, pinned so nobody tidies it away without meaning to.

    The end is the start plus the span taken through `run_seconds`' float, and
    that round trip is a millisecond short for about one integer in a hundred
    and twenty -- 1001 ms is the smallest such span, and `int(1.001 * 1000)` is
    1000. Every reader of this window computed it exactly this way before
    `Run.window_ms` named it, so the arithmetic was preserved rather than
    corrected; correcting it moves where an aura band gets clipped on roughly
    one real run in a hundred, which is a change of behaviour and deserves its
    own commit saying so.
    """
    run = a_run(pulls=(a_pull(0, 0, 1_001),))

    assert run.window_ms == (0, 1_000)
    assert run.window_ms[1] != max(pull.end_ms for pull in run.pulls)


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


def test_the_report_builder_accepts_the_throughput_cooldowns_the_analysers_read() -> None:
    throughput = ThroughputCooldowns(
        entries=(("DeathKnight/Blood", (CooldownAbility(
            ability_id=1, name="Dancing Rune Weapon", cooldown_seconds=120.0
        ),)),)
    )
    report = build_report(
        a_loaded(), (), None, None, a_player(), None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
        throughput=throughput,
    )
    # a_loaded() carries no players, so this call shape produces no cards either
    # way -- the point of this test is that build_report takes the keyword at all.
    assert report.players == ()


def test_build_report_passes_measures_through_to_the_card() -> None:
    """One parameter, threaded rather than recomputed: the report layer must not
    reach back into the comparison for figures it was handed."""
    measures = {
        "emberkin-0": PlayerMeasures(
            boss=(
                AbilityRate(ability_id=1, name="Meteor", ours=2.0, their_median=9.0,
                            their_rates=(9.0,), stretch=Stretch.BOSS, verdict=Verdict.BELOW),
            ),
            boss_seconds=600.0,
        )
    }
    loaded = a_loaded(players=(a_player(1, "Emberkin"),))
    report = build_report(
        loaded, (), None, None, a_player(1, "Emberkin"), None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
        comparison_measures=measures,
    )

    card = next(c for c in report.players if c.slug == "emberkin-0")
    assert [t.heading for t in card.comparison_tables] == ["Casts on boss pulls"]
