# ABOUTME: Behaviour tests for the report view model — frozen, hashable, no judgement.
# ABOUTME: The model is pure data; anything that decides something belongs in build.py.

import inspect

import pytest
from pydantic import BaseModel, ValidationError

from wowperf.domain.report import model as report_model
from wowperf.domain.report.model import (
    AvailabilityRow,
    DeathCard,
    Header,
    PlayerCard,
    Provenance,
    RecapRow,
    ReferenceRecord,
    Report,
    Section,
    SectionState,
    Timeline,
    TimelineBlock,
    TimelineTrack,
)


def a_section(state: SectionState = SectionState.PRESENT, reason: str = "") -> Section:
    return Section(state=state, reason=reason)


def test_a_present_section_needs_no_reason() -> None:
    assert a_section().reason == ""


def test_a_withheld_section_carries_its_reason() -> None:
    section = a_section(SectionState.WITHHELD, "no faster run was available")
    assert section.state is SectionState.WITHHELD
    assert section.reason == "no faster run was available"


def view_model_types() -> list[type[BaseModel]]:
    """Every pydantic model `wowperf.domain.report.model` defines, `Frozen` or not.

    Filtering on `BaseModel` rather than `Frozen` means a type someone adds
    straight off `BaseModel` — skipping `Frozen` by mistake — still shows up
    here and fails the assignment check below, instead of silently escaping
    a hand-written list. Exported for `test_html_invariants.py`, which walks
    the same types looking for a bare number rather than a broken freeze.
    """
    return [
        obj
        for _, obj in inspect.getmembers(report_model, inspect.isclass)
        if issubclass(obj, BaseModel) and obj.__module__ == report_model.__name__
    ]


def test_every_view_model_type_is_frozen() -> None:
    # `model_construct` skips required-field validation, so one call covers every
    # type regardless of its fields; a frozen model rejects the assignment before
    # it ever checks whether the field exists or the value is well-typed.
    for model_type in view_model_types():
        instance = model_type.model_construct()
        with pytest.raises(ValidationError):
            instance.a_field_that_need_not_exist = "something else"  # type: ignore[attr-defined]


def test_a_timeline_block_is_hashable_so_a_report_can_be_compared() -> None:
    block = TimelineBlock(label="Nalorakk", x=10.0, width=40.0, is_boss=True, kind="matched")
    assert hash(block) == hash(
        TimelineBlock(label="Nalorakk", x=10.0, width=40.0, is_boss=True, kind="matched")
    )


def test_a_report_holds_every_section() -> None:
    report = Report(
        header=Header(
            dungeon="Den of Nalorakk",
            keystone_level=16,
            affixes=("Tyrannical",),
            result="Timed by 2:14",
        ),
        narrative=None,
        ledger_decomposition=(),
        summary_pointers=(),
        timeline=Timeline(section=a_section(SectionState.WITHHELD, "no reference")),
        route=a_section(SectionState.WITHHELD, "no reference"),
        deaths=(),
        interrupts=(),
        players=(),
        observations=(),
        provenance=Provenance(
            report_code="abc123",
            fight_id=36,
            fetched_at="2026-09-05 14:02",
            speed_reference_url=None,
            parse_reference_url=None,
        ),
    )
    assert report.narrative is None
    assert report.timeline.section.state is SectionState.WITHHELD
    assert report.route.state is SectionState.WITHHELD


def test_a_player_card_declares_a_class_name_field_independent_of_colour() -> None:
    # A field never declared here could never reach the template, so the
    # guarantee that a reader sees the class as text -- not only as a colour
    # swatch -- rests on the type itself carrying two separate string fields
    # for it, rather than one field a caller is expected to derive the other
    # from. What build.py actually puts in each field (a name and its matching
    # CSS token, never the same string) is proven in
    # `test_a_card_names_the_class_in_text_beside_its_colour` in
    # `test_build_players.py`, and what the template does with them in
    # `test_a_player_card_prints_the_class_name_beside_the_colour` in
    # `test_html_sections.py`.
    fields = PlayerCard.model_fields
    assert fields["class_name"].annotation is str
    assert fields["colour"].annotation is str


def test_a_death_card_can_carry_no_timeline_and_no_availability() -> None:
    card = DeathCard(player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar")
    assert (card.timeline, card.availability, card.came_back) == ((), (), "")


def test_a_recap_row_and_an_availability_row_are_closed_vocabularies_plus_strings() -> None:
    row = RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                   detail="82,410 to health", health="61%", health_percent=61)
    state = AvailabilityRow(ability="Ironbark", owner="Leafy", state="cooldown",
                            detail="at most 14 s left")
    assert row.health_percent == 61 and state.owner == "Leafy"


def test_a_timeline_track_defaults_to_no_blocks() -> None:
    assert TimelineTrack(caption="Ours — 31:48").blocks == ()


def test_a_reference_record_defaults_to_loaded_and_used() -> None:
    """A record with no reason and no cache flag reads as a clean, fresh success —
    the shape every non-excluded, non-cached candidate leaves behind."""
    record = ReferenceRecord(
        report_code="abc123", fight_id=36, keystone_level=16,
        url="https://www.warcraftlogs.com/reports/abc123?fight=36", axis="speed",
    )
    assert record.loaded is True
    assert record.reason == ""
    assert record.from_cache is False
    assert record.fetched_at == ""


def test_a_reference_record_has_no_field_for_a_name_a_duration_or_a_death_count() -> None:
    # A closed field set is what keeps a `ReferenceRecord` a link rather than a
    # tabulation: there is no field this test would need to police for a stray
    # character name, a duration, or a death count, because none exists to fill.
    assert set(ReferenceRecord.model_fields) == {
        "report_code", "fight_id", "keystone_level", "url", "axis", "loaded", "reason",
        "from_cache", "fetched_at",
    }


def test_a_reference_record_states_why_it_was_not_used() -> None:
    record = ReferenceRecord(
        report_code="abc123", fight_id=36, keystone_level=16,
        url="https://www.warcraftlogs.com/reports/abc123?fight=36", axis="speed",
        loaded=False, reason="this is the run under analysis",
    )
    assert record.loaded is False
    assert record.reason == "this is the run under analysis"
