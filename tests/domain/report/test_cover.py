# ABOUTME: Behaviour tests for clipping one aura's bands to a drawing's window.
# ABOUTME: Every edge a band can take against a window: before, after, straddling, touching.

from wowperf.domain.auras import Aura, AuraBand
from wowperf.domain.report.cover import clipped_bands


def test_a_band_is_clipped_to_the_window_rather_than_counted_whole() -> None:
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=8000, uses=1,
                bands=(AuraBand(start_ms=0, end_ms=10_000),))
    assert clipped_bands(aura, 4_000, 8_000) == ((4_000, 8_000),)


def test_overlapping_bands_are_merged_so_cover_never_exceeds_the_window() -> None:
    # Nothing in the aura table's response promises the bands it hands back are
    # disjoint, and two overlapping bands drawn as two rectangles would paint
    # the same second twice.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=8000, uses=2,
                bands=(AuraBand(start_ms=0, end_ms=6_000), AuraBand(start_ms=4_000, end_ms=9_000)))
    assert clipped_bands(aura, 0, 10_000) == ((0, 9_000),)


def test_a_band_wholly_outside_the_window_yields_nothing() -> None:
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=1000, uses=1,
                bands=(AuraBand(start_ms=0, end_ms=1_000),))
    assert clipped_bands(aura, 5_000, 9_000) == ()


# Edge cases the brief's three tests do not reach, added here per the task's own
# instruction to cover the arithmetic's boundaries before trusting it.


def test_a_band_wholly_after_the_window_yields_nothing() -> None:
    # The mirror of "wholly before": a band that starts only once the window has
    # already closed contributes nothing either.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=2000, uses=1,
                bands=(AuraBand(start_ms=10_000, end_ms=12_000),))
    assert clipped_bands(aura, 0, 5_000) == ()


def test_a_band_straddling_only_the_windows_start_is_clipped_to_it() -> None:
    # Begins before the window and ends inside it: only the tail past the
    # window's own start belongs to the drawing.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=3000, uses=1,
                bands=(AuraBand(start_ms=0, end_ms=3_000),))
    assert clipped_bands(aura, 2_000, 8_000) == ((2_000, 3_000),)


def test_a_band_straddling_only_the_windows_end_is_clipped_to_it() -> None:
    # Begins inside the window and runs past its end: only the head up to the
    # window's own end belongs to the drawing.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=6000, uses=1,
                bands=(AuraBand(start_ms=6_000, end_ms=12_000),))
    assert clipped_bands(aura, 2_000, 8_000) == ((6_000, 8_000),)


def test_two_bands_that_touch_exactly_merge_into_one() -> None:
    # One band's end is the next one's start. Nothing in between them is a gap
    # a reader could see, so they draw as one rectangle rather than two flush
    # against each other with a seam that means nothing.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=8000, uses=2,
                bands=(AuraBand(start_ms=0, end_ms=4_000), AuraBand(start_ms=4_000, end_ms=8_000)))
    assert clipped_bands(aura, 0, 8_000) == ((0, 8_000),)


def test_an_aura_with_no_bands_yields_nothing() -> None:
    # A `PlayerAuras` fetched for a player who never held this buff at all: the
    # table lists the ability with an empty band tuple rather than omitting it.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=0, uses=0, bands=())
    assert clipped_bands(aura, 0, 10_000) == ()
