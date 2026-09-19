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
    state_of,
)
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.events import CastEvent
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


def test_an_ability_never_pressed_is_unseen_not_judged() -> None:
    assert state_of((), "Icebound Fortitude", 120.0, 1, DEATH_MS).state == UNSEEN


def test_a_press_inside_the_run_up_is_pressed_with_the_seconds_before_death() -> None:
    state = state_of((press(48792, 1_000), press(48792, 56_600)), "IBF", 120.0, 1, DEATH_MS)
    assert (state.state, state.seconds) == (PRESSED, 3.4)


def test_a_defensive_still_up_at_the_death_reads_held() -> None:
    auras = _auras_with_band(ability_id=22812, name="Barkskin", start_ms=1000, end_ms=9000)

    state = state_of(
        _presses(22812, at_ms=2000), "Barkskin", 45.0, 1, death_ms=5000,
        ability_id=22812, auras=auras, window=(0, 10_000),
    )

    assert state.state == HELD


def test_a_defensive_that_lapsed_before_the_blow_reads_faded() -> None:
    """The overstatement this exists to correct: pressed, and gone by then."""
    auras = _auras_with_band(ability_id=22812, name="Barkskin", start_ms=1000, end_ms=3000)

    state = state_of(
        _presses(22812, at_ms=2000), "Barkskin", 45.0, 1, death_ms=5000,
        ability_id=22812, auras=auras, window=(0, 10_000),
    )

    assert state.state == FADED


def test_an_ability_with_no_aura_of_its_own_stays_pressed() -> None:
    """Silence, never an accusation: an unresolved ability is not faded."""
    auras = _auras_with_band(ability_id=99999, name="Something Else", start_ms=0, end_ms=9000)

    state = state_of(
        _presses(22812, at_ms=2000), "Barkskin", 45.0, 1, death_ms=5000,
        ability_id=22812, auras=auras, window=(0, 10_000),
    )

    assert state.state == PRESSED


def test_a_player_with_no_aura_table_stays_pressed() -> None:
    state = state_of(
        _presses(22812, at_ms=2000), "Barkskin", 45.0, 1, death_ms=5000,
        ability_id=22812, auras=None, window=(0, 10_000),
    )

    assert state.state == PRESSED


def test_the_name_fallback_resolves_a_buff_whose_id_differs_from_its_cast() -> None:
    """Greater Invisibility casts as 110959 and buffs as 110960."""
    auras = _auras_with_band(
        ability_id=110960, name="Greater Invisibility", start_ms=1000, end_ms=9000
    )

    state = state_of(
        _presses(110959, at_ms=2000), "Greater Invisibility", 90.0, 1, death_ms=5000,
        ability_id=110959, auras=auras, window=(0, 10_000),
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
        visible_from_ms=0, auras=auras, window=(0, 10_000),
    )

    assert at.own is not None
    assert [one.state for one in at.own if one.name == "Barkskin"] == [FADED]


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
        visible_from_ms=0, auras=auras, window=(190_000, 210_000),
    )

    assert [(s.name, s.state) for s in at.externals] == [("Ironbark", PRESSED)]
