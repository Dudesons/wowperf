# ABOUTME: Behaviour tests for aura bands and the window intersection uptime rests on.
# ABOUTME: The interesting cases are a band straddling a window edge and a band outside it.

from wowperf.domain.auras import (
    Aura,
    AuraBand,
    PlayerAuras,
    band_holding,
    co_ending_abilities,
    strip_instant,
    uptime_seconds_in,
)


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


# --- the closed interval, which other code now depends on ---------------------

FIGHT = (9_990_000, 10_000_000)


def test_a_band_holds_both_of_its_own_boundaries_and_nothing_past_them() -> None:
    """The closed interval, pinned from the numbers that made it load-bearing.

    Report cW38jmwdnZfbHVL4 fight 30: a player died at 9997413 carrying a
    defensive, the death stripped it, and the log timestamps that strip at
    9997398 -- which is exactly where the killing blow landed. So every
    correct `held` sits on the band's *upper* boundary, and the press that
    opened the band sits on its *lower* one, which is how `_press_band` draws
    a cover window at all. Narrow either end to a half-open interval and both
    answers vanish: every `held` turns back into a false `faded`, and every
    press loses its rectangle. The moment after the strip -- the death event
    itself -- is outside, and that is the whole reason the judgement moved off
    it.
    """
    aura = an_aura((9_994_610, 9_997_398))

    assert band_holding(aura, *FIGHT, 9_994_610) == (9_994_610, 9_997_398)
    assert band_holding(aura, *FIGHT, 9_997_398) == (9_994_610, 9_997_398)
    assert band_holding(aura, *FIGHT, 9_997_413) is None


# --- the strip, told apart from an expiry -------------------------------------
#
# Every number here is read out of the cached aura table behind design section
# 8.3's worked example, report cW38jmwdnZfbHVL4 fight 26, cache file
# bf70363dd929264a36384ced3509dfcbc6df03030eb77c51d78cc1151671291f.json. The
# player died at 6987482 and the killing blow landed at 6987479; ten of their
# auras end at 6987475, 6987476 or 6987477 -- two raid buffs over 218 seconds
# long among them, which cannot all have expired naturally within 2 ms of each
# other. That instant is the death removing them.

STRIPPED_BANDS = (
    (381748, "Blessing of the Bronze", 6_987_475, 218_239),
    (1287771, "Rune of Masterful Cunning", 6_987_476, 30_758),
    (1241715, "Might of the Void", 6_987_476, 13_022),
    (363916, "Obsidian Scales", 6_987_476, 6_130),
    (370901, "Leaping Flames", 6_987_476, 3_416),
    (441248, "Unrelenting Siege", 6_987_477, 218_222),
    (374349, "Renewing Blaze", 6_987_477, 5_943),
    (372470, "Scarlet Adaptation", 6_987_477, 5_942),
    (436336, "Mass Disintegrate", 6_987_477, 3_417),
    (376850, "Power Swell", 6_987_477, 3_417),
)
STRIP_MS = 6_987_475
DEATH_MS = 6_987_482
# The strip is a span, not a point: the log spread this one over three
# milliseconds. A band counts as stripped only when it ends inside it.
STRIP = (6_987_475, 6_987_477)


def a_table(*rows: tuple[int, str, int, int]) -> PlayerAuras:
    """One player's aura table from `(ability_id, name, band end, band length)` rows."""
    return PlayerAuras(
        actor_id=1,
        on_self=tuple(
            Aura(
                ability_id=ability_id, name=name, total_uptime_ms=length, uses=1,
                bands=(AuraBand(start_ms=end_ms - length, end_ms=end_ms),),
            )
            for ability_id, name, end_ms, length in rows
        ),
    )


def test_several_independent_auras_ending_together_are_a_strip() -> None:
    """The instant the death removed them, read back as the span the log spread it over."""
    assert strip_instant(a_table(*STRIPPED_BANDS), DEATH_MS) == STRIP


def test_one_aura_ending_alone_is_an_expiry_and_marks_no_strip() -> None:
    """A defensive running out is one band ending, with nothing beside it.

    Measured across the eleven fights of design section 8.3: an expired band
    has 0 or 1 of the player's other bands ending with it, against 7 to 21 for
    a stripped one, and nothing in between.
    """
    table = a_table(
        (363916, "Obsidian Scales", 6_987_476, 6_130),
        (370901, "Leaping Flames", 6_987_476, 3_416),
    )

    assert strip_instant(table, DEATH_MS) is None


def test_the_strip_instant_is_bounded_by_the_measured_stripped_cluster() -> None:
    """Seven abilities beside the one judged, no fewer: the cluster's own edge.

    Section 8.3 measured 7 to 21 co-ending *bands* when a death stripped an
    ability. This counts distinct abilities, and the edge is the same 7 there:
    of the 140,366 runs in the cached tables only 195 carry one ability twice,
    and the largest of those holds 6 bands, so no run of seven ends or more
    counts an ability twice and the two units coincide exactly where this
    reads them. A run of eight abilities gives each of its members seven
    co-enders; seven gives six, which is between the clusters and not a strip.
    """
    seven = STRIPPED_BANDS[:7]
    eight = STRIPPED_BANDS[:8]

    assert strip_instant(a_table(*seven), DEATH_MS) is None
    assert strip_instant(a_table(*eight), DEATH_MS) == STRIP


# A real Holy Paladin's strip, from a cached aura table: nine of their auras end
# at 9993378 and 9993379, and one unrelated trinket buff ends 3 ms later.
PALADIN_STRIP = (
    (1244893, "Beacon of the Savior", 9_993_378, 95_763),
    (400745, "Afterimage", 9_993_379, 110_393),
    (54149, "Infusion of Light", 9_993_379, 20_261),
    (1292300, "Brittle Torga Totem", 9_993_379, 19_960),
    (31884, "Avenging Wrath", 9_993_379, 15_648),
    (1264050, "Born in Sunlight", 9_993_379, 15_648),
    (1241410, "Hammer of Wrath", 9_993_379, 15_648),
    (1287771, "Rune of Masterful Cunning", 9_993_379, 7_128),
    (448086, "Bestow Light", 9_993_379, 2_101),
    (1229746, "Arcanoweave Insight", 9_993_382, 6_322),
)


def test_a_lone_ending_after_the_strip_does_not_hide_it() -> None:
    """The instant read is the latest that is a strip, not the latest of any kind.

    Anchoring on the player's latest band end lands on that trinket buff at
    9993382, finds a run of one ability, and answers None -- which puts every
    defensive the death stripped at 9993379 back to `faded`, the accusation
    this whole change withdraws. The window is wide enough to matter: the blow
    sits 15 to 55 ms before the death on fight 30. Across the cached tables 14
    of the 188 runs of seven abilities or more are followed by another band end
    2 to 60 ms later, and 7 of those within 15 ms.
    """
    assert strip_instant(a_table(*PALADIN_STRIP), 9_993_390) == (9_993_378, 9_993_379)


def test_co_ending_abilities_counts_the_others_at_this_ones_last_instant() -> None:
    """What the three-way reading is read from, when no instant is a strip outright."""
    table = a_table(*STRIPPED_BANDS[:4])
    scales = next(aura for aura in table.on_self if aura.name == "Obsidian Scales")

    assert co_ending_abilities(table, scales, DEATH_MS) == 3


def test_the_strip_is_the_last_one_before_the_moment_asked_about() -> None:
    """An earlier pile-up is some other instant, not the one the death made.

    A keystone party leaving combat drops a dozen procs at once, and that is
    not a death. What is read is the *latest instant that is a strip*, so an
    older pile-up is passed over whenever a later one qualifies -- and a death
    strips everything the player carried, which is what usually makes one.
    Where the death's own instant does not qualify, the search reaches back to
    the older pile-up instead; `strip_instant` records that residual and
    `test_recap_availability.py` pins what it answers.
    """
    earlier = tuple(
        (ability_id + 1, name, end_ms - 30_000, length)
        for ability_id, name, end_ms, length in STRIPPED_BANDS
    )
    table = a_table(*earlier, *STRIPPED_BANDS)

    assert strip_instant(table, DEATH_MS - 29_000) == (STRIP[0] - 30_000, STRIP[1] - 30_000)
    assert strip_instant(table, DEATH_MS) == STRIP


def test_a_millisecond_with_nothing_ending_in_it_closes_the_run() -> None:
    """One millisecond is the finest gap the log can express, and it is the linkage.

    Measured over the 133 cached aura tables: of 140,366 runs of band ends on
    consecutive milliseconds, 138,031 are a single millisecond wide and the
    widest is 4 ms, so linking on adjacency does not chain away from the
    instant it started at.
    """
    table = a_table(
        *STRIPPED_BANDS,
        (48792, "Icebound Fortitude", STRIP_MS - 2, 8_000),
    )

    assert strip_instant(table, DEATH_MS) == STRIP


def test_bands_ending_after_the_moment_asked_about_are_not_part_of_it() -> None:
    """A later death's strip is not this death's, and the search must not reach it.

    The player is resurrected and dies again three seconds on, which strips ten
    more auras at 6990500. That is the latest qualifying instant in the whole
    table, so reading band ends without bounding them at the moment asked about
    answers this death with a strip that had not happened yet. The second
    assertion is what keeps the first honest: the later instant really does
    qualify, so the first is not passing because nothing was there. Masterful
    Ritual, which outlived the first death by two seconds, is the other half --
    a death does not strip every aura, and what outlived it is no part of it.
    """
    later_death = tuple(
        (ability_id + 1, name, 6_990_500, length)
        for ability_id, name, _, length in STRIPPED_BANDS
    )
    table = a_table(
        *STRIPPED_BANDS,
        (1295901, "Masterful Ritual", 6_989_464, 15_010),
        *later_death,
    )

    assert strip_instant(table, DEATH_MS) == STRIP
    assert strip_instant(table, 6_990_600) == (6_990_500, 6_990_500)


def test_a_player_with_no_bands_at_all_marks_no_strip() -> None:
    assert strip_instant(PlayerAuras(actor_id=1), DEATH_MS) is None
