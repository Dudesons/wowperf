# ABOUTME: The state of each saving tool at a death: pressed in the run-up, ready, on cooldown
# ABOUTME: with an upper bound, or never seen. Each doubt resolves toward saying less.

from tests.domain.analysis.test_recap_timeline import DUDE, a_death
from tests.domain.test_auras import STRIPPED_BANDS, a_table
from wowperf.adapters.config.toml import load_consumables
from wowperf.domain.analysis.recap import (
    COOLDOWN,
    FADED,
    HELD,
    PRESSED,
    READY,
    UNSEEN,
    availability_at,
    consumable_state,
    killing_blow_ms,
    lethal_hit,
    state_of,
)
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death
from wowperf.domain.model import Player
from wowperf.domain.season import (
    ConsumableCategory,
    Consumables,
    DefensiveAbility,
    Defensives,
    ExternalAbility,
    Externals,
)

DEATH_MS = 60_000
ICEBOUND = DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=120.0)
RUNE_TAP = DefensiveAbility(ability_id=194679, name="Rune Tap", cooldown_seconds=25.0, charges=2)
BARKSKIN = DefensiveAbility(ability_id=22812, name="Barkskin", cooldown_seconds=45.0)
IRONBARK = ExternalAbility(ability_id=102342, name="Ironbark", cooldown_seconds=90.0)
STONE = ConsumableCategory(name="healthstone", cooldown_seconds=60.0, ability_ids=(6262,))
TREE = Player(actor_id=2, name="Leafy", class_name="Druid", spec="Restoration", item_level=680)


def press(
    ability_id: int, at_ms: int, actor_id: int = 1, target_id: int | None = None
) -> CastEvent:
    return CastEvent(actor_id=actor_id, ability_id=ability_id, ability_name="x",
                     timestamp_ms=at_ms, target_id=target_id)


def _presses(ability_id: int, at_ms: int) -> tuple[CastEvent, ...]:
    return (press(ability_id, at_ms),)


def _auras_with_band(ability_id: int, name: str, start_ms: int, end_ms: int) -> PlayerAuras:
    aura = Aura(
        ability_id=ability_id, name=name, total_uptime_ms=end_ms - start_ms, uses=1,
        bands=(AuraBand(start_ms=start_ms, end_ms=end_ms),),
    )
    return PlayerAuras(actor_id=1, on_self=(aura,))


# --- the blow's own moment ----------------------------------------------------
#
# Every number below comes from report cW38jmwdnZfbHVL4 fight 30: a death at
# 9997413 whose killing blow landed at 9997398, and the strip of every aura the
# player was carrying timestamped at that same 9997398. That 15 ms is the whole
# subject -- a band that ends before the death and at or after the blow.

BLOW_ID = 1_309_919  # Frigid Roar, the id the ability dictionaries carry
OTHER_ID = 999_999
BLOW_MS = 9_997_398
DEATH_MS_AT_THE_BLOW = 9_997_413
FIGHT_WINDOW = (9_900_000, 10_000_000)


def a_hit(at_ms: int, ability_id: int, actor_id: int = 1) -> DamageTakenEvent:
    return DamageTakenEvent(actor_id=actor_id, ability_id=ability_id, ability_name="x",
                            amount=1, health_damage=1, timestamp_ms=at_ms)


def a_death_by(ability_id: int, at_ms: int = DEATH_MS_AT_THE_BLOW) -> Death:
    return Death(player_name="Stonewake", actor_id=1, timestamp_ms=at_ms,
                 killing_blow="Frigid Roar", killing_blow_id=ability_id)


def test_the_blows_moment_is_the_hit_the_death_names_not_the_last_hit_before_it() -> None:
    """Two different claims, and only one of them is the killing blow.

    A tick of something else lands between the blow and the death event, so
    "the last damage event before the death" picks the wrong row here.
    """
    stream = (a_hit(BLOW_MS, BLOW_ID), a_hit(9_997_405, OTHER_ID))

    assert killing_blow_ms(stream, a_death_by(BLOW_ID)) == BLOW_MS


def test_the_blows_moment_is_the_latest_matching_hit_at_or_before_the_death() -> None:
    # The same ability hit this player three times: eight seconds earlier, at
    # the blow, and again after the death -- the latter belonging to whoever
    # died next, never to this death.
    stream = (a_hit(9_989_000, BLOW_ID), a_hit(BLOW_MS, BLOW_ID), a_hit(9_999_000, BLOW_ID))

    assert killing_blow_ms(stream, a_death_by(BLOW_ID)) == BLOW_MS


def test_the_same_ability_hitting_a_teammate_is_not_this_players_blow() -> None:
    # An area ability hits the raid; the nearer row belongs to someone else.
    stream = (a_hit(BLOW_MS, BLOW_ID, actor_id=1), a_hit(9_997_410, BLOW_ID, actor_id=2))

    assert killing_blow_ms(stream, a_death_by(BLOW_ID)) == BLOW_MS


def test_a_killing_blow_absent_from_the_fetched_stream_has_no_moment() -> None:
    """The honest unknown: pagination need not have reached the lethal hit."""
    assert killing_blow_ms((a_hit(BLOW_MS, OTHER_ID),), a_death_by(BLOW_ID)) is None


def test_a_death_naming_no_ability_at_all_has_no_moment() -> None:
    # `killing_blow_id` defaults to zero, meaning the log named no ability.
    # Matching on it would pair the death with any hit the log left unnamed.
    assert killing_blow_ms((a_hit(BLOW_MS, 0),), a_death_by(0)) is None


# --- the blow itself ------------------------------------------------------------
#
# `killing_blow_ms` answers when; `lethal_hit` answers which row, so a caller can
# read who dealt it. The two must agree on every death, or one page would name a
# moment another reader traces to a different hit.


def a_hit_from(at_ms: int, ability_id: int, source_id: int | None) -> DamageTakenEvent:
    return DamageTakenEvent(actor_id=1, ability_id=ability_id, ability_name="x",
                            amount=1, health_damage=1, timestamp_ms=at_ms,
                            source_id=source_id)


def test_the_lethal_hit_is_the_row_the_moment_is_read_from() -> None:
    """The same stream `killing_blow_ms` is tested against, returning the row itself."""
    blow = a_hit_from(BLOW_MS, BLOW_ID, source_id=4242)
    stream = (a_hit_from(9_989_000, BLOW_ID, 1111), blow, a_hit_from(9_997_405, OTHER_ID, 2222))

    assert lethal_hit(stream, a_death_by(BLOW_ID)) == blow
    hit = lethal_hit(stream, a_death_by(BLOW_ID))
    assert hit is not None
    assert hit.source_id == 4242


def test_a_hit_after_the_death_is_never_its_lethal_hit() -> None:
    stream = (a_hit_from(BLOW_MS, BLOW_ID, 1), a_hit_from(9_999_000, BLOW_ID, 2))

    hit = lethal_hit(stream, a_death_by(BLOW_ID))
    assert hit is not None
    assert hit.timestamp_ms == BLOW_MS


def test_no_lethal_hit_where_the_stream_lacks_it_or_the_log_named_nothing() -> None:
    assert lethal_hit((a_hit(BLOW_MS, OTHER_ID),), a_death_by(BLOW_ID)) is None
    assert lethal_hit((a_hit(BLOW_MS, 0),), a_death_by(0)) is None


def test_an_ability_never_pressed_is_unseen_not_judged() -> None:
    assert state_of((), "Icebound Fortitude", 120.0, 1, DEATH_MS).state == UNSEEN


def test_a_press_inside_the_run_up_is_pressed_with_the_seconds_before_death() -> None:
    state = state_of((press(48792, 1_000), press(48792, 56_600)), "IBF", 120.0, 1, DEATH_MS)
    assert (state.state, state.seconds) == (PRESSED, 3.4)


def test_a_defensive_the_death_stripped_still_reads_held_at_the_blow() -> None:
    """The case the whole judgement turns on.

    The timings are the Protection Warrior's Shield Wall on the canonical
    wipe, carried by this module's Barkskin fixture: pressed 2803 ms before
    the death, on a band that ends 15 ms before the death -- not because it
    expired, but because the death stripped it, and the log timestamps that
    strip at the very millisecond the killing blow landed. Asked about the
    death the answer is structurally `faded`, a false accusation about a buff
    the same page's tooltip credits with mitigation. Asked about the blow it is
    `held`.
    """
    auras = _auras_with_band(
        ability_id=22812, name="Barkskin", start_ms=9_994_610, end_ms=BLOW_MS
    )

    state = state_of(
        _presses(22812, at_ms=9_994_610), "Barkskin", 45.0, 1, DEATH_MS_AT_THE_BLOW,
        ability_id=22812, auras=auras, window=FIGHT_WINDOW, blow_ms=BLOW_MS,
    )

    assert state.state == HELD
    # `seconds` was never falsified and does not move: it is still how long
    # before the *death* the button was pressed, which is what the card says.
    assert state.seconds == 2.803


def test_a_defensive_that_lapsed_before_the_blow_reads_faded() -> None:
    """The overstatement this exists to correct, from the one press that really had faded.

    The timings are the Rogue's Feint on the canonical wipe: pressed 9609 ms
    before the death on a band 6013 ms long, so it was over 3596 ms before the
    blow -- far outside anything a strip could explain, and the one row of the
    six the live run judged that was judged rightly.
    """
    auras = _auras_with_band(
        ability_id=22812, name="Barkskin", start_ms=9_987_804, end_ms=9_993_817
    )

    state = state_of(
        _presses(22812, at_ms=9_987_804), "Barkskin", 45.0, 1, DEATH_MS_AT_THE_BLOW,
        ability_id=22812, auras=auras, window=FIGHT_WINDOW, blow_ms=BLOW_MS,
    )

    assert state.state == FADED


# --- the strip that lands before the blow -------------------------------------
#
# Design section 8.3's worked example, report cW38jmwdnZfbHVL4 fight 26. The
# death is at 6987482 and the killing blow at 6987479, but the strip of ten of
# that player's auras is timestamped 6987475 to 6987477 -- two to three
# milliseconds BEFORE the blow rather than on it, as section 8.1 had asserted
# from one fight. The defensive's band therefore ends before the blow, asking
# `band_holding` about the blow alone answers None, and the card printed "over
# by then" over an ability that was up when the blow landed.

EVOKER_BLOW_MS = 6_987_479
EVOKER_DEATH_MS = 6_987_482
EVOKER_WINDOW = (6_900_000, 7_000_000)
SCALES = 363916
SCALES_LENGTH = 6_130
# The band's own start is the press: 6987476 - 6130.
SCALES_PRESSED_MS = 6_981_346


def _without_the_defensive() -> tuple[tuple[int, str, int, int], ...]:
    return tuple(row for row in STRIPPED_BANDS if row[0] != SCALES)


def test_a_defensive_stripped_before_the_blow_reads_held() -> None:
    """The two false accusations this change exists to withdraw.

    Nine of this player's other auras end in the same two milliseconds, two of
    them raid buffs over 218 seconds long, which cannot all have expired
    naturally together. That instant is the death removing them, so the
    ability was up when the blow landed three milliseconds later.
    """
    state = state_of(
        _presses(SCALES, at_ms=SCALES_PRESSED_MS), "Obsidian Scales", 30.0, 1,
        EVOKER_DEATH_MS, ability_id=SCALES, auras=a_table(*STRIPPED_BANDS),
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == HELD
    # Untouched: still how long before the *death* the button was pressed.
    assert state.seconds == 6.136


def test_a_defensive_that_lapsed_before_the_strip_still_reads_faded() -> None:
    """The strip is not an amnesty, and this is the shape that proves it.

    The same death, the same nine co-enders at the same strip, but this
    defensive's band ended 200 ms before the blow -- the closest any genuinely
    expired band came to a blow across section 8.3's eleven fights. Counting
    co-enders anywhere between the band's end and the blow would find all nine
    of them and call this held; so would widening `band_holding` by enough
    milliseconds to cover the real strip. Both answers are false accusations
    in the other direction.
    """
    lapsed = (*_without_the_defensive(),
              (SCALES, "Obsidian Scales", EVOKER_BLOW_MS - 200, SCALES_LENGTH))

    state = state_of(
        _presses(SCALES, at_ms=EVOKER_BLOW_MS - 200 - SCALES_LENGTH), "Obsidian Scales",
        30.0, 1, EVOKER_DEATH_MS, ability_id=SCALES, auras=a_table(*lapsed),
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == FADED


def test_a_count_between_the_two_clusters_answers_pressed() -> None:
    """The honest unknown, and the one row that tells this rule from a tolerance.

    Four of this player's abilities end together at the real strip -- the same
    four rows `test_auras.py` reads, at the same real death and blow -- which
    is three beside Obsidian Scales. Three is above the expired cluster's 1 and
    below the stripped cluster's 7, so nothing measured here says whether the
    death removed the aura or it ran out, and §5's explicit unknown is the
    answer. A few-millisecond tolerance on the interval would say `held`, since
    the band ends 3 ms before the blow; the measured rule refuses to guess.
    """
    state = state_of(
        _presses(SCALES, at_ms=SCALES_PRESSED_MS), "Obsidian Scales", 30.0, 1,
        EVOKER_DEATH_MS, ability_id=SCALES, auras=a_table(*STRIPPED_BANDS[:4]),
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == PRESSED


def test_the_top_of_the_expired_cluster_still_reads_faded() -> None:
    """One ability ending beside it is an expiry measured, not a doubt.

    Re-derived in the unit the code counts: the rows section 8.3 calls
    genuinely expired, matched in the cached tables by the band lengths it
    records, carry 0 co-ending abilities 15 times and 1 co-ending ability 20
    times, and never more. One neighbour is still inside that cluster, so the
    aura table's own reading stands rather than being replaced by a doubt.
    """
    table = a_table(
        (1287771, "Rune of Masterful Cunning", 6_987_476, 30_758),
        (SCALES, "Obsidian Scales", 6_987_476, SCALES_LENGTH),
    )

    state = state_of(
        _presses(SCALES, at_ms=SCALES_PRESSED_MS), "Obsidian Scales", 30.0, 1,
        EVOKER_DEATH_MS, ability_id=SCALES, auras=table,
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == FADED


def test_an_older_pile_up_of_endings_is_not_this_deaths_strip() -> None:
    """Auras end together for reasons besides dying, and only the last instant answers.

    A keystone party leaving combat drops a dozen procs at once. Here a dozen
    of this player's auras end four seconds before the death with the
    defensive's band among them, and the death strips what was left three
    milliseconds before the blow. The ability was down for those four seconds
    and the page must keep saying so.
    """
    pile_up_ms = EVOKER_DEATH_MS - 4_000
    older = tuple(
        (ability_id + 1, name, pile_up_ms, length)
        for ability_id, name, _, length in _without_the_defensive()
    )
    table = a_table(
        *_without_the_defensive(), *older,
        (SCALES, "Obsidian Scales", pile_up_ms, 3_000),
    )

    state = state_of(
        _presses(SCALES, at_ms=pile_up_ms - 3_000), "Obsidian Scales", 30.0, 1,
        EVOKER_DEATH_MS, ability_id=SCALES, auras=table,
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == FADED


def test_a_reach_back_past_a_small_death_credits_the_older_strip() -> None:
    """The rule's recorded residual, pinned rather than left to be discovered.

    The anchor is the latest instant that *is* a strip. When the death's own
    removal is too small to qualify -- three abilities here, against a player
    who normally carries a dozen -- the search keeps walking back, and an older
    pile-up four seconds earlier answers in its place. The defensive ends at
    that pile-up, so it reads `held` for an instant that was not this death's.

    **That is a false `held`, and it is the answer the measurement gives.** The
    discriminator reads shape, and a pull-end proc drop has a death strip's
    shape exactly. Position rules an older instant out when a later one
    qualifies, and the search's floor rules out everything before the run-up's
    first press -- but between those two, inside the run-up, nothing measured
    separates them. Doing so needs a look-back bound in milliseconds, the
    unjustified constant this design has refused four times.

    The pile-up here is four seconds before the death and so inside the run-up,
    which is what the bound leaves reachable; design section 3.1 records that
    this is the residual's whole remaining size.
    """
    pile_up_ms = EVOKER_DEATH_MS - 4_000
    older = tuple(
        (ability_id + 1, name, pile_up_ms, length)
        for ability_id, name, _, length in _without_the_defensive()
    )
    small_death = tuple(
        (ability_id + 2, name, 6_987_476, length)
        for ability_id, name, _, length in STRIPPED_BANDS[:3]
    )
    table = a_table(*older, (SCALES, "Obsidian Scales", pile_up_ms, 3_000), *small_death)

    state = state_of(
        _presses(SCALES, at_ms=pile_up_ms - 3_000), "Obsidian Scales", 30.0, 1,
        EVOKER_DEATH_MS, ability_id=SCALES, auras=table,
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == HELD


def test_a_band_spanning_a_strip_but_ending_before_the_blow_is_not_held() -> None:
    """Ending at the strip is the claim; running through it is not.

    The defensive was pressed before an older pile-up, was still up when those
    ten auras dropped, and ran out a second later -- a second before the blow.
    Asking whether the band *covers* the strip instant answers `held`, which
    asserts the aura was up when the blow landed while its own band says it had
    ended. The strip branch is only reached when no band covers the blow, so a
    band covering the strip and not the blow always ended between the two.

    It reads as its own last instant says, which is what the count is for: the
    band ends alone here, inside the expired cluster, so `faded`.

    **`held` stays reachable, but rows that read `held` before do move**, and
    that is the fix rather than a side effect. A band ending after the latest
    qualifying instant ends in an instant that does not qualify -- if it did,
    it would itself be the latest qualifying one and the band would have ended
    *at* a strip -- so `held` was never on offer for this band. Over the cached
    tables 1430 rows move from `held` to `faded` this way and 77 to `pressed`.
    """
    pile_up_ms = EVOKER_DEATH_MS - 4_000
    older = tuple(
        (ability_id + 1, name, pile_up_ms, length)
        for ability_id, name, _, length in _without_the_defensive()
    )
    small_death = tuple(
        (ability_id + 2, name, 6_987_476, length)
        for ability_id, name, _, length in STRIPPED_BANDS[:3]
    )
    # Runs from before the pile-up to a second before the blow: it spans the
    # strip instant without ending in it.
    spanning = (SCALES, "Obsidian Scales", EVOKER_DEATH_MS - 1_000, SCALES_LENGTH)
    table = a_table(*older, spanning, *small_death)

    state = state_of(
        _presses(SCALES, at_ms=EVOKER_DEATH_MS - 1_000 - SCALES_LENGTH), "Obsidian Scales",
        30.0, 1, EVOKER_DEATH_MS, ability_id=SCALES, auras=table,
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == FADED


def test_a_band_trailing_the_strip_among_others_answers_pressed_not_faded() -> None:
    """Ending after the strip is read by the count, not condemned on position.

    Nine auras end at 6987475 and the defensive ends at 6987478 with three
    others, three milliseconds past the strip and one before the blow. Two
    explanations fit and the log does not choose between them: the aura
    outlived the removal and ran out, or the removal was logged across a gap
    wider than a millisecond and this is its tail. A four-ability instant is
    inside the no-man's land, so the answer is silence.

    **This is the shape that separates the three readings**, and it is the one
    the cascade was argued over: asking whether the band *covers* the strip
    answers `held`, condemning it on position alone answers `faded`, and
    reading its own instant answers `pressed`. It is a constructed shape -- no
    band in the cached tables spans a qualifying strip and ends after it -- so
    it pins the decision rather than a measurement.

    The silence is narrow and worth stating plainly: with one or two abilities
    trailing instead of three the count lands in the expired cluster and the
    answer is `faded` again. A lone defensive trailing the run is the commonest
    split shape there is, so this buys silence only for tails of three to seven.
    """
    strip = tuple(
        (ability_id + 1, name, 6_987_475, length)
        for ability_id, name, _, length in _without_the_defensive()
    )
    trailing = tuple(
        (ability_id + 2, name, 6_987_478, length)
        for ability_id, name, _, length in STRIPPED_BANDS[:3]
    )
    table = a_table(*strip, *trailing, (SCALES, "Obsidian Scales", 6_987_478, SCALES_LENGTH))

    state = state_of(
        _presses(SCALES, at_ms=6_987_478 - SCALES_LENGTH), "Obsidian Scales", 30.0, 1,
        EVOKER_DEATH_MS, ability_id=SCALES, auras=table,
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == PRESSED


def test_an_ancient_strip_cannot_claim_a_press_from_the_run_up() -> None:
    """The reach-back is bounded below by the run-up's first press, which no band can predate.

    Task 10 saw the search reach back 1777 seconds on a real death. The tempting
    argument is that it cannot matter: the refinement only runs for a press
    inside the run-up, and the band of that press cannot end before the press
    began, so an instant half an hour earlier can never hold it. **That
    argument is sound about the press's own band and the code does not require
    it.** `last_band_end` reads the whole resolved aura, not the band this press
    opened, so where a run-up press has no band of its own -- a cast the log
    recorded and the aura table did not -- the aura's previous use answers
    instead, and an ancient instant claims it.

    Here the press is five seconds before the death and the only band this aura
    carries ended 1777 seconds earlier, inside a ten-ability instant. Unbounded,
    that reads `held`: a defensive credited as up at the blow on the strength of
    a band that ended half an hour before. Bounded at the press, no instant in
    reach qualifies, and the count answers the honest unknown.
    """
    ancient_ms = EVOKER_DEATH_MS - 1_777_000
    ancient = tuple(
        (ability_id + 1, name, ancient_ms, length)
        for ability_id, name, _, length in _without_the_defensive()
    )
    small_death = tuple(
        (ability_id + 2, name, 6_987_476, length)
        for ability_id, name, _, length in STRIPPED_BANDS[:3]
    )
    table = a_table(
        *ancient, (SCALES, "Obsidian Scales", ancient_ms, SCALES_LENGTH), *small_death
    )

    state = state_of(
        _presses(SCALES, at_ms=EVOKER_DEATH_MS - 5_000), "Obsidian Scales", 30.0, 1,
        EVOKER_DEATH_MS, ability_id=SCALES, auras=table,
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == PRESSED


def test_a_second_press_after_the_strip_does_not_throw_the_strip_away() -> None:
    """The bound is the *earliest* press in the run-up, not the latest.

    The same conflation the bound exists to fix, mirrored: `last_band_end` may
    be answering for an earlier press while the latest one landed after the
    band ended. Here the ability is pressed six seconds before the death and
    again at 6987478, in the 15-to-55 ms gap between the strip and the death.
    The band ends at 6987476, **inside the death's own strip** -- a correct
    `held` -- and bounding at the later press would cut that strip off and
    answer the unknown instead. Nothing a press opened can end before the
    earliest press, so that is where the search stops.
    """
    table = a_table(*STRIPPED_BANDS)
    presses = (press(SCALES, SCALES_PRESSED_MS), press(SCALES, 6_987_478))

    state = state_of(
        presses, "Obsidian Scales", 30.0, 1, EVOKER_DEATH_MS, ability_id=SCALES,
        auras=table, window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == HELD
    # `seconds` still counts from the latest press, which is untouched by this.
    assert state.seconds == 0.004


def test_an_instant_straddling_the_first_press_cannot_claim_a_band_before_it() -> None:
    """The clamp's only shape, and the reason it is a clamp and not a wider search.

    `strip_instant` breaks at instant granularity, so an instant that *starts*
    before the earliest run-up press survives the floor -- the whole instant
    does, not the part of it after the press. Here it spans 6987475 to 6987478,
    four milliseconds, the widest any instant in the cached tables has ever
    been; the press is at 6987477 and the band ends at 6987476, one millisecond
    before it. Matching on the instant's first millisecond would credit a band
    that provably predates its press, which is the 1777-second defect at a
    millisecond's scale.

    **It answers `pressed`, not `faded`.** The instant qualifies, so the count
    it falls to is the whole instant's -- ten co-enders, far above the expired
    cluster -- and the row goes silent rather than accusing. That is the trade
    the clamp makes in both directions: a genuine strip straddling the first
    press is silenced too, and neither error can print "over by then".
    """
    straddling = (*STRIPPED_BANDS, (381749, "Blessing of the Bronze", 6_987_478, 218_242))
    table = a_table(*straddling)

    state = state_of(
        _presses(SCALES, at_ms=6_987_477), "Obsidian Scales", 30.0, 1,
        EVOKER_DEATH_MS, ability_id=SCALES, auras=table,
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == PRESSED


def test_a_band_ending_just_before_the_strip_is_condemned_on_position() -> None:
    """The leading side, which is deliberately not the mirror of the trailing one.

    A band ending after the strip falls to the count and can answer `pressed`;
    a band ending *before* it is `faded` on position, with the count never
    consulted. That asymmetry is a decision, not an oversight, and this pins it:
    without the position branch the three co-enders here would answer `pressed`.

    Measured over the 133 cached tables, the leading side is as real as the
    trailing one: **13 qualifying strips are preceded by a band end 2 to 60 ms
    earlier, 5 of them within 15 ms** -- counting runs of seven abilities or
    more, the population section 3.1 uses throughout; at the qualifying floor of
    eight it is 11 and 3. Every one of those fragments holds a single ability
    except one, which holds two. **This fixture holds three**, one more than the
    cache has ever shown, because at one or two the count answers `faded` as
    well and the two readings cannot be told apart. Making the sides symmetric
    would need a width in milliseconds, which is the tolerance refused four
    times over.
    """
    leading = tuple(
        (ability_id + 1, name, 6_987_471, length)
        for ability_id, name, _, length in STRIPPED_BANDS[:2]
    )
    table = a_table(
        *_without_the_defensive(), *leading,
        (SCALES, "Obsidian Scales", 6_987_471, SCALES_LENGTH),
    )

    state = state_of(
        _presses(SCALES, at_ms=6_987_471 - SCALES_LENGTH), "Obsidian Scales", 30.0, 1,
        EVOKER_DEATH_MS, ability_id=SCALES, auras=table,
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == FADED


def test_a_band_before_an_ancient_strip_is_not_condemned_by_it() -> None:
    """The floor's other half: without it an ancient instant can accuse, not just credit.

    `test_an_ancient_strip_cannot_claim_a_press_from_the_run_up` covers a band
    ending *inside* a reached-back instant, and the clamp happens to catch that
    one too. This covers a band ending *before* it, which only the floor
    catches: unbounded, the search selects the ancient instant, the band ends
    before it, and the position branch answers `faded` -- an accusation sourced
    from an instant half an hour away. Bounded, no instant is in reach and the
    band's own two co-enders put it in the no-man's land, where it belongs.
    """
    ancient_ms = EVOKER_DEATH_MS - 1_777_000
    older_ms = EVOKER_DEATH_MS - 1_800_000
    ancient = tuple(
        (ability_id + 1, name, ancient_ms, length)
        for ability_id, name, _, length in _without_the_defensive()
    )
    beside = tuple(
        (ability_id + 2, name, older_ms, length)
        for ability_id, name, _, length in STRIPPED_BANDS[:2]
    )
    table = a_table(*ancient, *beside, (SCALES, "Obsidian Scales", older_ms, SCALES_LENGTH))

    state = state_of(
        _presses(SCALES, at_ms=EVOKER_DEATH_MS - 5_000), "Obsidian Scales", 30.0, 1,
        EVOKER_DEATH_MS, ability_id=SCALES, auras=table,
        window=EVOKER_WINDOW, blow_ms=EVOKER_BLOW_MS,
    )

    assert state.state == PRESSED


def test_a_death_whose_blow_never_reached_the_stream_stays_pressed() -> None:
    """The fixture that reads `faded` with a blow reads `pressed` without one.

    Falling back to the death's own timestamp would answer `faded` here and
    look right, while quietly reinstating the judgement this change removes.
    The honest answer to "which hit killed them" being unfetched is silence.
    """
    auras = _auras_with_band(
        ability_id=22812, name="Barkskin", start_ms=9_987_804, end_ms=9_993_817
    )

    state = state_of(
        _presses(22812, at_ms=9_987_804), "Barkskin", 45.0, 1, DEATH_MS_AT_THE_BLOW,
        ability_id=22812, auras=auras, window=FIGHT_WINDOW, blow_ms=None,
    )

    assert state.state == PRESSED


def test_an_ability_with_no_aura_of_its_own_stays_pressed() -> None:
    """Silence, never an accusation: an unresolved ability is not faded.

    The blow is given, so the `pressed` here is the unresolved ability's and
    not a missing blow's.
    """
    auras = _auras_with_band(ability_id=99999, name="Something Else", start_ms=0, end_ms=9000)

    state = state_of(
        _presses(22812, at_ms=2000), "Barkskin", 45.0, 1, death_ms=5000,
        ability_id=22812, auras=auras, window=(0, 10_000), blow_ms=4900,
    )

    assert state.state == PRESSED


def test_a_player_with_no_aura_table_stays_pressed() -> None:
    state = state_of(
        _presses(22812, at_ms=2000), "Barkskin", 45.0, 1, death_ms=5000,
        ability_id=22812, auras=None, window=(0, 10_000), blow_ms=4900,
    )

    assert state.state == PRESSED


def test_the_name_fallback_resolves_a_buff_whose_id_differs_from_its_cast() -> None:
    """Greater Invisibility casts as 110959 and buffs as 110960."""
    auras = _auras_with_band(
        ability_id=110960, name="Greater Invisibility", start_ms=1000, end_ms=9000
    )

    state = state_of(
        _presses(110959, at_ms=2000), "Greater Invisibility", 90.0, 1, death_ms=5000,
        ability_id=110959, auras=auras, window=(0, 10_000), blow_ms=4900,
    )

    assert state.state == HELD


def test_a_press_inside_one_cooldown_leaves_an_upper_bound_in_whole_seconds() -> None:
    # Pressed 100.2 s before death on a 120 s cooldown: at most 19.8 s left, said as 20.
    state = state_of((press(48792, DEATH_MS - 100_200),), "IBF", 120.0, 1, DEATH_MS)
    assert (state.state, state.seconds) == (COOLDOWN, 20)


def test_a_press_older_than_one_cooldown_leaves_the_ability_ready() -> None:
    state = state_of((press(48792, DEATH_MS - 135_000),), "IBF", 120.0, 1, DEATH_MS)
    assert (state.state, state.seconds) == (READY, None)


def test_readiness_that_arrived_inside_the_run_up_says_for_how_long_at_least() -> None:
    # Pressed 124 s before a 120 s cooldown's death: ready for 4 s by the base cooldown,
    # and longer if a talent shortened it — so "at least".
    state = state_of((press(48792, DEATH_MS - 124_000),), "IBF", 120.0, 1, DEATH_MS)
    assert (state.state, state.seconds) == (READY, 4.0)


def test_a_second_charge_keeps_an_ability_ready_until_both_are_spent() -> None:
    one = state_of((press(194679, DEATH_MS - 20_000),), "Rune Tap", 25.0, 2, DEATH_MS)
    two = state_of(
        (press(194679, DEATH_MS - 20_000), press(194679, DEATH_MS - 15_000)),
        "Rune Tap", 25.0, 2, DEATH_MS,
    )
    assert one.state == READY
    # The older press frees the next charge: 25 - 20 = 5 s left at most.
    assert (two.state, two.seconds) == (COOLDOWN, 5)


def test_a_charge_never_spent_says_nothing_about_since_when() -> None:
    # Two charges, one press: a charge was never spent, so the ability was
    # ready throughout the run-up and there is nothing to say about since when.
    state = state_of((press(194679, DEATH_MS - 20_000),), "Rune Tap", 25.0, 2, DEATH_MS)
    assert (state.state, state.seconds) == (READY, None)


def test_readiness_comes_from_the_charge_that_recharged_not_the_last_press() -> None:
    # Two charges, both spent: a charge comes free when the OLDER of the two
    # presses recharges, not when the most recent one does. Pressed 32 s and
    # 22 s before death on a 25 s cooldown, the older press's charge frees up
    # 32 - 25 = 7 s before death, and that is the lower bound reported.
    state = state_of(
        (press(194679, DEATH_MS - 32_000), press(194679, DEATH_MS - 22_000)),
        "Rune Tap", 25.0, 2, DEATH_MS,
    )
    assert (state.state, state.seconds) == (READY, 7.0)


def test_readiness_uses_the_oldest_of_the_last_charges_presses_not_the_oldest_of_the_run() -> None:
    # Two charges, 25 s cooldown, pressed three times: 200 s, 32 s and 20 s before death.
    # The 200 s press is old enough to be irrelevant -- both charges had long since
    # recharged by the time the other two presses happened, and neither the run-up nor
    # the cooldown window reaches back that far. What decides readiness is the second-
    # oldest of the three, the 32 s press, because it is the older of the last two
    # presses and so the one whose recharge freed the last charge that had been spent:
    # 32 - 25 = 7 s before death, inside the ten-second run-up, so a lower bound is
    # reported. Using the 200 s press instead (the oldest of the whole run) would push
    # readiness outside the run-up and report nothing; using the 20 s press instead
    # (the most recent) would put readiness after the death and report a negative
    # duration -- the defect corrected in 2eaa7f8.
    state = state_of(
        (
            press(194679, DEATH_MS - 200_000),
            press(194679, DEATH_MS - 32_000),
            press(194679, DEATH_MS - 20_000),
        ),
        "Rune Tap", 25.0, 2, DEATH_MS,
    )
    assert (state.state, state.seconds) == (READY, 7.0)


def test_an_external_counts_as_pressed_only_when_cast_on_the_dying_player() -> None:
    on_them = state_of((press(102342, 57_000, actor_id=2, target_id=1),), "Ironbark", 90.0, 1,
                       DEATH_MS, owner_id=2, on_target=1)
    on_other = state_of((press(102342, 57_000, actor_id=2, target_id=3),), "Ironbark", 90.0, 1,
                        DEATH_MS, owner_id=2, on_target=1)
    assert (on_them.state, on_them.owner_id) == (PRESSED, 2)
    assert (on_other.state, on_other.seconds) == (COOLDOWN, 87)


def test_an_untargeted_external_reads_as_pressed_for_the_dying_player() -> None:
    # Power Word: Barrier, Spirit Link Totem and Rallying Cry cover an area or the
    # whole group, and the log writes target_id=None for them. An untargeted cast
    # has no other player it could have been for, so it must not fall through to
    # the cooldown branch the way a cast aimed at someone else does.
    untargeted = state_of((press(97462, 57_000, actor_id=2, target_id=None),), "Rallying Cry",
                          180.0, 1, DEATH_MS, owner_id=2, on_target=1)
    on_other = state_of((press(97462, 57_000, actor_id=2, target_id=3),), "Rallying Cry",
                        180.0, 1, DEATH_MS, owner_id=2, on_target=1)
    assert (untargeted.state, untargeted.owner_id) == (PRESSED, 2)
    assert (on_other.state, on_other.seconds) == (COOLDOWN, 177)


def test_a_category_never_drunk_is_not_listed_at_all() -> None:
    # Was `..._is_ready_because_no_talent_gates_a_potion` until 2026-09-12.
    # The log proves nothing about a consumable nobody used: the run-level
    # finding says so once, and the card says nothing.
    assert consumable_state((), STONE, DEATH_MS) is None


def test_a_category_drunk_long_ago_is_listed_as_ready() -> None:
    late = 400_000
    state = consumable_state((press(6262, late - 300_000),), STONE, late)
    assert state is not None and state.state == READY


def test_a_consumable_drunk_in_the_run_up_is_pressed() -> None:
    state = consumable_state((press(6262, 58_000),), STONE, DEATH_MS)
    assert state is not None and state.state == PRESSED


def test_availability_omits_the_row_for_a_category_never_drunk() -> None:
    # Paired against the same category drunk on the same window, because the
    # rule that hides a category whose window reaches back before the fight
    # would otherwise be what empties this list, and the test would pass
    # without the new rule existing.
    drunk = availability_at(
        (DUDE,), (press(6262, 100_000),), a_death(at_ms=200_000), Defensives(),
        Consumables(categories=(STONE,)), Externals(), visible_from_ms=0,
    )
    never = availability_at(
        (DUDE,), (), a_death(at_ms=200_000), Defensives(),
        Consumables(categories=(STONE,)), Externals(), visible_from_ms=0,
    )
    assert drunk.consumables is not None
    assert [state.name for state in drunk.consumables] == ["healthstone"]
    assert never.consumables == ()


def test_availability_groups_own_defensives_consumables_and_teammates_externals() -> None:
    # The stone is drunk at 100s: since 2026-09-12 a category nobody drank
    # from is not listed at all, so a fixture that never drinks one asserts
    # an empty group rather than the three-group shape this test is about.
    casts = (press(48792, 1_000), press(6262, 100_000),
             press(102342, 150_000, actor_id=2, target_id=3))
    at = availability_at(
        (DUDE, TREE), casts, a_death(at_ms=200_000),
        Defensives(entries=(("DeathKnight/Blood", (ICEBOUND, RUNE_TAP)),)),
        Consumables(categories=(STONE,)), Externals(entries=(("Druid/Restoration", (IRONBARK,)),)),
        visible_from_ms=0,
    )
    assert at.own is not None and [(s.name, s.state) for s in at.own] == [
        ("Icebound Fortitude", READY), ("Rune Tap", UNSEEN)
    ]
    assert at.consumables is not None and [(s.name, s.state) for s in at.consumables] == [
        ("healthstone", READY)
    ]
    assert [(s.name, s.ability_id, s.owner_id, s.state, s.seconds) for s in at.externals] == [
        ("Ironbark", 102342, 2, COOLDOWN, 40)
    ]


def test_a_defensives_state_carries_the_ability_id_it_was_judged_from() -> None:
    at = availability_at(
        (DUDE,), (), a_death(), Defensives(entries=(("DeathKnight/Blood", (ICEBOUND,)),)),
        Consumables(), Externals(), visible_from_ms=0,
    )
    assert at.own is not None
    assert [state.ability_id for state in at.own] == [48792]


def test_a_consumable_state_carries_no_ability_id() -> None:
    # Drunk inside the run-up, so the state is PRESSED and flows straight out
    # of `state_of` rather than through the UNSEEN override, which is the path
    # that would carry an id through if one were ever passed in.
    at = availability_at(
        (DUDE,), (press(6262, 195_000),), a_death(at_ms=200_000), Defensives(),
        Consumables(categories=(STONE,)), Externals(), visible_from_ms=0,
    )
    assert at.consumables is not None
    assert all(state.ability_id is None for state in at.consumables)


def test_a_spec_absent_from_a_file_yields_none_for_that_group_not_an_empty_list() -> None:
    at = availability_at((DUDE,), (), a_death(), Defensives(), Consumables(), Externals(),
                         visible_from_ms=0)
    assert (at.own, at.consumables, at.externals) == (None, None, ())


def test_a_consumable_whose_window_reaches_before_the_fight_is_not_judged() -> None:
    # The stone's window is 60 + 10 s; a death 40 s in cannot see far enough back.
    at = availability_at((DUDE,), (), a_death(at_ms=40_000), Defensives(),
                         Consumables(categories=(STONE,)), Externals(), visible_from_ms=0)
    assert at.consumables == ()


def test_availability_from_the_real_consumables_file_excludes_combat_potion() -> None:
    """Regression: the death card's own availability column must never gain a

    combat potion row. Built through `load_consumables()` on the committed
    file rather than a hand-built `Consumables`, because a fixture the test
    wrote itself cannot expose a call site that reads `.categories` instead
    of the survival accessor -- that is exactly how this leaked past the
    offline suite the first time.
    """
    # Potion of Recklessness, drunk once well outside the run-up and outside
    # its own 300s cooldown window, so it reads as READY -- the state a
    # pressed-then-recovered combat potion would show on the card.
    at = availability_at(
        (DUDE,), (press(1236994, 50_000),), a_death(at_ms=400_000), Defensives(),
        load_consumables(), Externals(), visible_from_ms=0,
    )
    assert at.consumables == ()


def test_the_dying_player_is_not_their_own_teammate() -> None:
    healer = Player(
        actor_id=1, name="Leafy", class_name="Druid", spec="Restoration", item_level=680
    )
    at = availability_at(
        (healer,), (press(102342, 1_000),), a_death(), Defensives(), Consumables(),
        Externals(entries=(("Druid/Restoration", (IRONBARK,)),)), visible_from_ms=0,
    )
    assert at.externals == ()


def test_the_dying_players_own_defensives_are_judged_against_their_bands() -> None:
    auras = _auras_with_band(ability_id=22812, name="Barkskin", start_ms=0, end_ms=3000)

    at = availability_at(
        (DUDE,), _presses(22812, at_ms=2000), a_death(at_ms=5000),
        Defensives(entries=(("DeathKnight/Blood", (BARKSKIN,)),)), Consumables(), Externals(),
        visible_from_ms=0, auras=auras, window=(0, 10_000), blow_ms=4900,
    )

    assert at.own is not None
    assert [one.state for one in at.own if one.name == "Barkskin"] == [FADED]


def test_the_dying_players_own_defensives_are_judged_at_the_blow_not_the_death() -> None:
    # The band ends 15 ms before the death because the death stripped it, and
    # exactly where the blow landed. Judged at the death this reads FADED; the
    # whole point of threading the blow through is that it does not.
    auras = _auras_with_band(
        ability_id=22812, name="Barkskin", start_ms=9_994_610, end_ms=BLOW_MS
    )

    at = availability_at(
        (DUDE,), _presses(22812, at_ms=9_994_610), a_death(at_ms=DEATH_MS_AT_THE_BLOW),
        Defensives(entries=(("DeathKnight/Blood", (BARKSKIN,)),)), Consumables(), Externals(),
        visible_from_ms=0, auras=auras, window=FIGHT_WINDOW, blow_ms=BLOW_MS,
    )

    assert at.own is not None
    assert [one.state for one in at.own if one.name == "Barkskin"] == [HELD]


def test_a_defensive_stays_pressed_when_no_blow_reached_the_stream() -> None:
    # Same band as the FADED case above, and no blow: the answer is the
    # explicit unknown, never the death's own timestamp standing in for one.
    auras = _auras_with_band(ability_id=22812, name="Barkskin", start_ms=0, end_ms=3000)

    at = availability_at(
        (DUDE,), _presses(22812, at_ms=2000), a_death(at_ms=5000),
        Defensives(entries=(("DeathKnight/Blood", (BARKSKIN,)),)), Consumables(), Externals(),
        visible_from_ms=0, auras=auras, window=(0, 10_000), blow_ms=None,
    )

    assert at.own is not None
    assert [one.state for one in at.own if one.name == "Barkskin"] == [PRESSED]


def test_externals_keep_pressed_even_when_a_matching_aura_band_would_flip_them() -> None:
    # If auras/window leaked into the externals loop, this band -- coincidentally
    # keyed to Ironbark's own ability id, on the dying player's own aura table --
    # would read FADED, because it lapsed five seconds before the death. An
    # external's aura sits on the dying player but is resolved against the
    # caster's ability id, and `auras` here (scoped to actor_id=1, the dying
    # player) cannot answer that, so externals must stay PRESSED regardless.
    auras = _auras_with_band(ability_id=102342, name="Ironbark", start_ms=190_000, end_ms=195_000)
    casts = (press(102342, 195_000, actor_id=2, target_id=1),)

    at = availability_at(
        (DUDE, TREE), casts, a_death(at_ms=200_000), Defensives(), Consumables(),
        Externals(entries=(("Druid/Restoration", (IRONBARK,)),)),
        visible_from_ms=0, auras=auras, window=(190_000, 210_000), blow_ms=199_900,
    )

    assert [(s.name, s.state) for s in at.externals] == [("Ironbark", PRESSED)]
