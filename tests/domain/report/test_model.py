# ABOUTME: Behaviour tests for the report view model — frozen, hashable, no judgement.
# ABOUTME: The model is pure data; anything that decides something belongs in build.py.

import inspect
from typing import get_args, get_origin

import pytest
from pydantic import BaseModel, ValidationError

from wowperf.domain.report import model as report_model
from wowperf.domain.report.model import (
    AvailabilityRow,
    Badge,
    DeathCard,
    Header,
    LedgerRow,
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
    all_ledger_rows,
)


def a_section(state: SectionState = SectionState.PRESENT, reason: str = "") -> Section:
    return Section(state=state, reason=reason)


def test_a_present_section_needs_no_reason() -> None:
    assert a_section().reason == ""


def test_a_withheld_section_carries_its_reason() -> None:
    section = a_section(SectionState.WITHHELD, "no faster run was available")
    assert section.state is SectionState.WITHHELD
    assert section.reason == "no faster run was available"


def a_ledger_row(**changes: object) -> LedgerRow:
    row = LedgerRow(
        finding_id="time.gap.0",
        title="A 41 second gap after pull 7",
        title_before="A 41 second gap after pull 7",
        detail="Travel, not combat.",
        badge=Badge(label="measured", tint="badge-measured"),
    )
    return row.model_copy(update=changes)


def a_report(**changes: object) -> Report:
    report = Report(
        header=Header(
            dungeon="Den of Nalorakk",
            keystone_level=16,
            affixes=("Tyrannical",),
            result="Timed by 2:14",
        ),
        narrative=None,
        ledger_decomposition=(),
        timeline=Timeline(section=a_section(SectionState.WITHHELD, "no reference")),
        route=a_section(SectionState.WITHHELD, "no reference"),
        deaths=(),
        interrupts=(),
        players=(),
        observations=(),
        provenance=Provenance(
            report_code="abc123", fight_id=36, fetched_at="2026-09-05 14:02",
        ),
    )
    return report.model_copy(update=changes)


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


def test_a_reference_record_has_no_field_for_a_figure() -> None:
    # A closed field set is what keeps a `ReferenceRecord` a link rather than a
    # tabulation: there is no field this test would need to police for a
    # duration, a death count or a score, because none exists to fill.
    # `player_slug` and `player_name` name one of our own roster, never the
    # reference's, and the report already prints that name on the player's card.
    assert set(ReferenceRecord.model_fields) == {
        "report_code", "fight_id", "keystone_level", "url", "axis", "loaded", "reason",
        "from_cache", "player_slug", "player_name",
    }


def test_a_reference_record_states_why_it_was_not_used() -> None:
    record = ReferenceRecord(
        report_code="abc123", fight_id=36, keystone_level=16,
        url="https://www.warcraftlogs.com/reports/abc123?fight=36", axis="speed",
        loaded=False, reason="this is the run under analysis",
    )
    assert record.loaded is False
    assert record.reason == "this is the run under analysis"


def test_all_ledger_rows_reaches_every_field_that_holds_them() -> None:
    """A tenth section that holds findings must be reached, or its icons vanish.

    The fields are discovered by walking every type `view_model_types()`
    returns, not by naming `Report` and `PlayerCard` here -- a third container
    gaining a `tuple[LedgerRow, ...]` field is found the same way a fourth or
    fifth would be, and fails this test if `all_ledger_rows` was never taught
    to reach it, instead of escaping an introspection that only ever checked
    two classes.
    """
    expected: set[str] = set()
    report_changes: dict[str, object] = {}
    nested: dict[type[BaseModel], dict[str, object]] = {}

    for model_type in view_model_types():
        row_fields = [
            name
            for name, field in model_type.model_fields.items()
            if field.annotation == tuple[LedgerRow, ...]
        ]
        if not row_fields:
            continue
        changes: dict[str, object] = {}
        for name in row_fields:
            finding_id = f"{model_type.__name__}.{name}"
            changes[name] = (a_ledger_row(finding_id=finding_id),)
            expected.add(finding_id)
        if model_type is Report:
            report_changes.update(changes)
        else:
            nested[model_type] = changes

    assert expected, "introspection found no row-bearing fields, so this proves nothing"

    report = a_report().model_copy(update=report_changes)
    for model_type, changes in nested.items():
        container_field = next(
            (
                name
                for name, field in Report.model_fields.items()
                if get_origin(field.annotation) is tuple
                and get_args(field.annotation) == (model_type, Ellipsis)
            ),
            None,
        )
        assert container_field is not None, (
            f"{model_type.__name__} holds a row-bearing field but is not nested "
            "under any tuple field of Report this test knows how to fill"
        )
        instance = model_type.model_construct(**changes)  # type: ignore[arg-type]
        report = report.model_copy(update={container_field: (instance,)})

    assert {row.finding_id for row in all_ledger_rows(report)} == expected
