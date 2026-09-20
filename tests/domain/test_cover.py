# ABOUTME: Behaviour tests for clipping one aura's bands to a drawing's window.
# ABOUTME: Every edge a band can take against a window: before, after, straddling, touching.

from wowperf.domain.auras import (
    Aura,
    AuraBand,
    PlayerAuras,
    band_holding,
    clipped_bands,
    resolve_aura,
)


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


def test_two_separated_bands_both_survive_as_two_windows_in_order() -> None:
    # The one shape `clipped_bands`'s own return type promises and none of the
    # tests above exercise: a real gap between two bands inside the window
    # must come back as two windows, not folded into one by the merge step.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=4000, uses=2,
                bands=(AuraBand(start_ms=0, end_ms=2_000), AuraBand(start_ms=5_000, end_ms=7_000)))
    assert clipped_bands(aura, 0, 10_000) == ((0, 2_000), (5_000, 7_000))


# `band_holding` answers "what did this one press cover", which must not merge:
# two presses of the same defensive whose bands touch or overlap are still two
# different presses, and merging would let both claim the same window.


def test_band_holding_returns_the_single_band_containing_the_press() -> None:
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=6000, uses=1,
                bands=(AuraBand(start_ms=53_000, end_ms=59_000),))
    assert band_holding(aura, 50_000, 60_000, 55_000) == (53_000, 59_000)


def test_band_holding_gives_two_touching_presses_two_different_windows() -> None:
    # The regression this whole fix is about: `clipped_bands` would merge these
    # two touching bands into (0, 8_000), and a press inside each would then
    # resolve to the very same merged window -- each one's rectangle reaching
    # into the duration the other press actually earned. `band_holding` must
    # keep them apart.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=8000, uses=2,
                bands=(AuraBand(start_ms=0, end_ms=4_000), AuraBand(start_ms=4_000, end_ms=8_000)))
    first_press = band_holding(aura, 0, 8_000, 2_000)
    second_press = band_holding(aura, 0, 8_000, 6_000)
    assert first_press == (0, 4_000)
    assert second_press == (4_000, 8_000)
    assert first_press != second_press


def test_band_holding_is_none_when_no_band_contains_the_press() -> None:
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=1000, uses=1,
                bands=(AuraBand(start_ms=0, end_ms=1_000),))
    assert band_holding(aura, 0, 10_000, 5_000) is None


def test_band_holding_clips_the_band_it_returns_to_the_window() -> None:
    # The band reaches past both edges of the window; only the part the
    # drawing covers comes back, the same clipping `clipped_bands` does.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=10000, uses=1,
                bands=(AuraBand(start_ms=0, end_ms=10_000),))
    assert band_holding(aura, 4_000, 8_000, 6_000) == (4_000, 8_000)


def test_a_press_at_the_exact_join_of_two_touching_bands_resolves_to_the_later_one() -> None:
    # A press at 4_000 satisfies `low <= at_ms <= high` for both (0, 4_000) and
    # (4_000, 8_000): it is the last instant of the first band and the first
    # instant of the second. A press creates a band beginning at its own
    # timestamp, so the band that STARTS at the press is the one it began --
    # picking the one that ends there instead would draw a rectangle of zero
    # duration and tell a reader this cast covered nothing.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=8000, uses=2,
                bands=(AuraBand(start_ms=0, end_ms=4_000), AuraBand(start_ms=4_000, end_ms=8_000)))
    assert band_holding(aura, 0, 8_000, 4_000) == (4_000, 8_000)


def test_a_press_inside_two_overlapping_bands_resolves_to_the_one_that_started_later() -> None:
    # Same reasoning as the touching case, without a shared endpoint: a press
    # at 5_000 falls inside both (0, 6_000) and (4_000, 10_000), and the one it
    # began is the one with the later start.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=10000, uses=2,
                bands=(AuraBand(start_ms=0, end_ms=6_000), AuraBand(start_ms=4_000, end_ms=10_000)))
    assert band_holding(aura, 0, 10_000, 5_000) == (4_000, 10_000)


# `resolve_aura` bridges a cast id to the aura table's own key. The table keys
# an aura by the id of the buff itself, and `data/defensives.toml` (and
# `data/throughput_cooldowns.toml` beside it) records the id of the spell
# *cast* to apply it -- the same spell for most abilities, but not for Alter
# Time (cast 108978, buff 342246) or Greater Invisibility (cast 110959, buff
# 110960), measured against the cached aura tables for report
# `6Kx1P9GbNXrcLdHa` (`.claude/skills/wcl-api/SKILL.md`, 2026-09-11).


def test_resolve_aura_finds_an_aura_by_its_own_id() -> None:
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=8000, uses=1)
    auras = PlayerAuras(actor_id=1, on_self=(aura,))
    assert resolve_aura(auras, 48792, "Icebound Fortitude") is aura


def test_resolve_aura_falls_back_to_the_name_when_the_id_does_not_match() -> None:
    # The regression this resolver exists for: the cast id (108978, Alter
    # Time's spell) finds nothing in a table keyed by the buff's own id
    # (342246), so the name is what has to bridge the two.
    aura = Aura(ability_id=342246, name="Alter Time", total_uptime_ms=4000, uses=1)
    auras = PlayerAuras(actor_id=1, on_self=(aura,))
    assert resolve_aura(auras, 108978, "Alter Time") is aura


def test_resolve_aura_finds_nothing_when_neither_id_nor_name_match() -> None:
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=8000, uses=1)
    auras = PlayerAuras(actor_id=1, on_self=(aura,))
    assert resolve_aura(auras, 999_999, "Unrelated Buff") is None


def test_an_id_match_wins_over_a_name_match_when_both_are_possible() -> None:
    # The one case that matters: the name match is a heuristic and must never
    # override an exact id match. Two auras sit in this player's own table --
    # one whose id matches what was asked for but whose name does not, and a
    # separate one whose name matches but whose id does not -- and the id
    # match must win.
    by_id = Aura(ability_id=100, name="Wrong Name Entirely", total_uptime_ms=1000, uses=1)
    by_name = Aura(ability_id=999, name="Shield Wall", total_uptime_ms=2000, uses=1)
    auras = PlayerAuras(actor_id=1, on_self=(by_id, by_name))
    assert resolve_aura(auras, 100, "Shield Wall") is by_id
