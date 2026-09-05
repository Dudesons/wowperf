# ABOUTME: Behaviour tests for the report view model — frozen, hashable, no judgement.
# ABOUTME: The model is pure data; anything that decides something belongs in build.py.

import pytest
from pydantic import ValidationError

from wowperf.domain.report.model import (
    Badge,
    DeathCard,
    Header,
    LedgerRow,
    PlayerCard,
    Provenance,
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


def test_every_view_model_type_is_frozen() -> None:
    row = LedgerRow(
        finding_id="time.residual",
        title="Time outside pulls",
        detail="Travel, waiting and run-backs.",
        badge=Badge(label="measured", tint="measured"),
        seconds="4:12",
        nests_inside=None,
    )
    with pytest.raises(ValidationError):
        row.title = "something else"


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
        ledger_losses=(),
        timeline=Timeline(section=a_section(SectionState.WITHHELD, "no reference")),
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


def test_a_player_card_names_the_class_in_text_not_only_in_colour() -> None:
    card = PlayerCard(
        name="Dudesons",
        class_name="DeathKnight",
        spec="Blood",
        colour="class-deathknight",
        casts_summary="182 casts in 31:49 of pulls",
        deaths=1,
        kicks=7,
        spell_and_talent=a_section(SectionState.WITHHELD, "no ranked parse"),
    )
    assert card.class_name in ("DeathKnight",)
    assert card.colour != card.class_name


def test_a_death_card_can_carry_no_damage_rows() -> None:
    card = DeathCard(
        player="Dudesons",
        class_name="DeathKnight",
        when="12:04, pull 5",
        killing_blow="Frigid Roar",
    )
    assert card.last_ten_seconds == ()


def test_a_timeline_track_defaults_to_no_blocks() -> None:
    assert TimelineTrack(caption="Ours — 31:48").blocks == ()
