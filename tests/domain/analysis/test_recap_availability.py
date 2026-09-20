# ABOUTME: The state of each saving tool at a death: pressed in the run-up, ready, on cooldown
# ABOUTME: with an upper bound, or never seen. Each doubt resolves toward saying less.

from tests.domain.analysis.test_recap_timeline import DUDE, a_death
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

BLOW_ID = 1_214_063
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
