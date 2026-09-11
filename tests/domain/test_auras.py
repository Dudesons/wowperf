# ABOUTME: Behaviour tests for aura bands and the window intersection uptime rests on.
# ABOUTME: The interesting cases are a band straddling a window edge and a band outside it.

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras, uptime_seconds_in


def an_aura(*bands: tuple[int, int]) -> Aura:
    return Aura(
        ability_id=391477,
        name="Coagulopathy",
        total_uptime_ms=sum(end - start for start, end in bands),
        uses=len(bands),
        bands=tuple(AuraBand(start_ms=start, end_ms=end) for start, end in bands),
    )


def test_a_band_entirely_inside_a_window_counts_in_full() -> None:
    assert uptime_seconds_in(an_aura((1000, 4000)), ((0, 10000),)) == 3.0


def test_a_band_entirely_outside_every_window_counts_for_nothing() -> None:
    assert uptime_seconds_in(an_aura((20000, 24000)), ((0, 10000),)) == 0.0


def test_a_band_straddling_a_window_edge_is_clipped_to_the_window() -> None:
    assert uptime_seconds_in(an_aura((8000, 14000)), ((0, 10000),)) == 2.0


def test_a_band_spanning_two_windows_counts_only_the_covered_parts() -> None:
    aura = an_aura((0, 30000))

    assert uptime_seconds_in(aura, ((0, 5000), (20000, 22000))) == 7.0


def test_an_aura_with_no_bands_has_no_uptime() -> None:
    assert uptime_seconds_in(an_aura(), ((0, 10000),)) == 0.0


def test_no_windows_means_no_uptime_rather_than_the_whole_aura() -> None:
    assert uptime_seconds_in(an_aura((0, 5000)), ()) == 0.0


def test_player_auras_default_to_no_auras_at_all() -> None:
    auras = PlayerAuras(actor_id=7)

    assert auras.on_self == ()


def test_two_overlapping_bands_count_the_union_not_the_sum() -> None:
    # Nothing in the aura table's response promises the bands it returns are
    # disjoint, and the union is the only reading that cannot exceed the window.
    # The aura was up, without interruption, from 1000 to 7000: six seconds.
    aura = an_aura((1000, 5000), (3000, 7000))

    assert uptime_seconds_in(aura, ((0, 10000),)) == 6.0


def test_two_bands_that_touch_end_to_start_sum_without_gap_or_double_count() -> None:
    aura = an_aura((1000, 3000), (3000, 5000))

    assert uptime_seconds_in(aura, ((0, 10000),)) == 4.0


def test_a_band_spanning_two_overlapping_windows_counts_the_union() -> None:
    aura = an_aura((0, 10000))

    assert uptime_seconds_in(aura, ((0, 6000), (4000, 10000))) == 10.0


def test_a_band_with_end_before_start_contributes_nothing() -> None:
    assert uptime_seconds_in(an_aura((5000, 1000)), ((0, 10000),)) == 0.0
