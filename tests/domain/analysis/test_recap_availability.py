# ABOUTME: The state of each saving tool at a death: pressed in the run-up, ready, on cooldown
# ABOUTME: with an upper bound, or never seen. Each doubt resolves toward saying less.

from tests.domain.analysis.test_recap_timeline import DUDE, a_death, loaded
from wowperf.domain.analysis.recap import (
    COOLDOWN,
    PRESSED,
    READY,
    UNSEEN,
    availability_at,
    consumable_state,
    state_of,
)
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
IRONBARK = ExternalAbility(ability_id=102342, name="Ironbark", cooldown_seconds=90.0)
STONE = ConsumableCategory(name="healthstone", cooldown_seconds=60.0, ability_ids=(6262,))
TREE = Player(actor_id=2, name="Leafy", class_name="Druid", spec="Restoration", item_level=680)


def press(
    ability_id: int, at_ms: int, actor_id: int = 1, target_id: int | None = None
) -> CastEvent:
    return CastEvent(actor_id=actor_id, ability_id=ability_id, ability_name="x",
                     timestamp_ms=at_ms, target_id=target_id)


def test_an_ability_never_pressed_is_unseen_not_judged() -> None:
    assert state_of((), "Icebound Fortitude", 120.0, 1, DEATH_MS).state == UNSEEN


def test_a_press_inside_the_run_up_is_pressed_with_the_seconds_before_death() -> None:
    state = state_of((press(48792, 1_000), press(48792, 56_600)), "IBF", 120.0, 1, DEATH_MS)
    assert (state.state, state.seconds) == (PRESSED, 3.4)


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


def test_an_external_counts_as_pressed_only_when_cast_on_the_dying_player() -> None:
    on_them = state_of((press(102342, 57_000, actor_id=2, target_id=1),), "Ironbark", 90.0, 1,
                       DEATH_MS, owner_id=2, on_target=1)
    on_other = state_of((press(102342, 57_000, actor_id=2, target_id=3),), "Ironbark", 90.0, 1,
                        DEATH_MS, owner_id=2, on_target=1)
    assert (on_them.state, on_them.owner_id) == (PRESSED, 2)
    assert (on_other.state, on_other.seconds) == (COOLDOWN, 87)


def test_a_consumable_never_drunk_is_ready_because_no_talent_gates_a_potion() -> None:
    assert consumable_state((), STONE, DEATH_MS).state == READY


def test_a_consumable_drunk_in_the_run_up_is_pressed() -> None:
    assert consumable_state((press(6262, 58_000),), STONE, DEATH_MS).state == PRESSED


def test_availability_groups_own_defensives_consumables_and_teammates_externals() -> None:
    run = loaded(
        casts=(press(48792, 1_000), press(102342, 150_000, actor_id=2, target_id=3)),
    )
    run = run.model_copy(update={"run": run.run.model_copy(update={"players": (DUDE, TREE)})})
    at = availability_at(
        run, a_death(at_ms=200_000),
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
    assert [(s.name, s.owner_id, s.state, s.seconds) for s in at.externals] == [
        ("Ironbark", 2, COOLDOWN, 40)
    ]


def test_a_spec_absent_from_a_file_yields_none_for_that_group_not_an_empty_list() -> None:
    at = availability_at(loaded(), a_death(), Defensives(), Consumables(), Externals(),
                         visible_from_ms=0)
    assert (at.own, at.consumables, at.externals) == (None, None, ())


def test_a_consumable_whose_window_reaches_before_the_fight_is_not_judged() -> None:
    # The stone's window is 60 + 10 s; a death 40 s in cannot see far enough back.
    at = availability_at(loaded(), a_death(at_ms=40_000), Defensives(),
                         Consumables(categories=(STONE,)), Externals(), visible_from_ms=0)
    assert at.consumables == ()


def test_the_dying_player_is_not_their_own_teammate() -> None:
    run = loaded(casts=(press(102342, 1_000),))
    run = run.model_copy(update={"run": run.run.model_copy(update={"players": (
        Player(actor_id=1, name="Leafy", class_name="Druid", spec="Restoration", item_level=680),
    )})})
    at = availability_at(
        run, a_death(), Defensives(), Consumables(),
        Externals(entries=(("Druid/Restoration", (IRONBARK,)),)), visible_from_ms=0,
    )
    assert at.externals == ()
