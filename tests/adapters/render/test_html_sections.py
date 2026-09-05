# ABOUTME: Behaviour tests for the report's four data sections and the inline timeline SVG.
# ABOUTME: The template does no arithmetic: every coordinate here was computed in build_timeline.

from tests.adapters.render.test_html import a_report, a_row
from wowperf.adapters.render.html import render
from wowperf.domain.report.model import (
    DamageRow,
    DeathCard,
    PlayerCard,
    Section,
    SectionState,
    Timeline,
    TimelineBlock,
    TimelineTrack,
)

PRESENT = Section(state=SectionState.PRESENT)


def a_timeline() -> Timeline:
    return Timeline(
        section=PRESENT,
        ours=TimelineTrack(
            caption="Ours — 31:48",
            blocks=(
                TimelineBlock(label="Loa Speaker Nanea", x=46.0, width=50.0, is_boss=True,
                              kind="matched"),
                TimelineBlock(label="Frostbound trio", x=120.0, width=20.0, is_boss=False,
                              kind="extra"),
            ),
        ),
        theirs=TimelineTrack(
            caption="Reference — 27:30",
            blocks=(
                TimelineBlock(label="Shale Prowlers", x=60.0, width=15.0, is_boss=False,
                              kind="skipped"),
            ),
        ),
        ticks=((46.0, "0:00"), (240.0, "10:00")),
        width=680.0,
        height=208.0,
    )


def test_the_timeline_renders_as_inline_svg() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "<svg" in html
    assert 'viewBox="0 0 680.0 208.0"' in html


def test_every_block_carries_its_pack_name_as_a_tooltip() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "<title>Loa Speaker Nanea</title>" in html
    assert "<title>Frostbound trio</title>" in html


def test_a_boss_block_is_distinguishable_from_a_trash_block() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "block-boss" in html


def test_an_extra_pack_and_a_skipped_pack_are_marked_differently() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "block-extra" in html
    assert "block-skipped" in html


def test_both_captions_are_rendered() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "Ours — 31:48" in html
    assert "Reference — 27:30" in html


def test_the_axis_ticks_are_rendered() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert ">10:00<" in html


def test_a_death_card_shows_the_run_up() -> None:
    card = DeathCard(
        player="Dudesons",
        class_name="DeathKnight",
        when="12:04, pull 5",
        killing_blow="Frigid Roar",
        last_ten_seconds=(
            DamageRow(seconds_before="5.8s before", ability="Snowdrift", amount="82,410"),
        ),
    )
    html = render(a_report(deaths=(card,)))
    assert "Frigid Roar" in html
    assert "Snowdrift" in html
    assert "5.8s before" in html


def test_a_run_with_no_deaths_says_so_rather_than_showing_an_empty_heading() -> None:
    html = render(a_report(deaths=()))
    assert "No deaths" in html


def test_the_interrupts_section_renders_its_rows() -> None:
    html = render(a_report(interrupts=(a_row("interrupts.ability.0", title="Snowdrift, 3 casts"),)))
    assert "Snowdrift, 3 casts" in html


def test_a_player_card_prints_the_class_name_beside_the_colour() -> None:
    card = PlayerCard(
        name="Dudesons",
        class_name="DeathKnight",
        spec="Blood",
        colour="class-deathknight",
        active_time="412s in pulls (38%)",
        deaths=1,
        kicks=7,
        spell_and_talent=Section(state=SectionState.WITHHELD, reason="no ranked parse"),
    )
    html = render(a_report(players=(card,)))
    assert "DeathKnight" in html
    assert "Blood" in html
    assert "class-deathknight" in html


def test_a_player_cards_withheld_comparison_states_its_reason() -> None:
    card = PlayerCard(
        name="Dudesons",
        class_name="DeathKnight",
        spec="Blood",
        colour="class-deathknight",
        active_time="412s in pulls (38%)",
        deaths=0,
        kicks=0,
        spell_and_talent=Section(state=SectionState.WITHHELD, reason="no ranked parse was found"),
    )
    html = render(a_report(players=(card,)))
    assert "no ranked parse was found" in html


def test_the_template_still_fetches_nothing() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "<script" not in html.lower()
    assert "https://" not in html
