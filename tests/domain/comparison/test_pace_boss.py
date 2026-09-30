# ABOUTME: Which enemy actor is the boss: flagged a boss and named after the fight, exactly one.
# ABOUTME: Pins the same-named non-boss, the boss-framed adds, and a council.

from wowperf.domain.comparison.pace_boss import NpcActor, find_boss_actor, find_bosses

FIGHT = "The Test Colossus"


def actor(actor_id: int, name: str, sub_type: str, game_id: int = 900) -> NpcActor:
    return NpcActor(actor_id=actor_id, game_id=game_id, name=name, sub_type=sub_type)


def test_the_one_boss_named_after_the_fight_is_the_boss() -> None:
    actors = (
        actor(57, FIGHT, "Boss"),
        actor(58, "Colossal Rattle", "Boss", 901),
        actor(59, "Colossal Heart", "Boss", 902),
        actor(60, FIGHT, "NPC", 903),
    )
    boss = find_boss_actor(actors, FIGHT)
    assert boss is not None and boss.actor_id == 57


def test_a_council_names_no_boss_after_the_fight() -> None:
    actors = (actor(10, "First Warden", "Boss"), actor(11, "Second Warden", "Boss", 901))
    assert find_boss_actor(actors, "The Wardens") is None


def test_two_bosses_named_after_the_fight_are_not_one_boss() -> None:
    actors = (actor(10, FIGHT, "Boss"), actor(11, FIGHT, "Boss", 901))
    assert find_boss_actor(actors, FIGHT) is None


def ids(bosses: tuple[NpcActor, ...]) -> list[int]:
    return [one.actor_id for one in bosses]


def test_a_boss_named_after_the_fight_wins_over_boss_framed_adds() -> None:
    actors = (
        actor(27, FIGHT, "Boss", 1),
        actor(106, "Drowned Whisper", "Boss", 2),
        actor(116, "Echo of the Deep", "Boss", 3),
    )
    assert ids(find_bosses(actors, frozenset({27, 106, 116}), FIGHT)) == [27]


def test_a_boss_whose_name_begins_the_fight_name_is_the_boss() -> None:
    actors = (actor(203, "Grimtooth", "Boss", 5), actor(174, "Grimtooth", "NPC", 6))
    assert ids(find_bosses(actors, frozenset({203, 174}), "Grimtooth the Vile")) == [203]


def test_a_name_that_is_only_a_prefix_of_a_word_is_not_named_after_the_fight() -> None:
    actors = (actor(1, "Grim", "Boss", 5), actor(2, "Grimtooth", "Boss", 6))
    assert ids(find_bosses(actors, frozenset({1, 2}), "Grimtooth the Vile")) == [2]


def test_a_lone_boss_flagged_enemy_under_another_name_is_the_boss() -> None:
    actors = (actor(9, "Heart of the Colossus", "Boss", 5),)
    assert ids(find_bosses(actors, frozenset({9}), FIGHT)) == [9]


def test_several_boss_flagged_enemies_none_named_after_the_fight_are_a_council() -> None:
    actors = (
        actor(131, "Blood of the Twins", "Boss", 11),
        actor(130, "Breath of the Twins", "Boss", 12),
        actor(126, "Venom Pool", "NPC", 13),
    )
    assert ids(find_bosses(actors, frozenset({131, 130, 126}), "The Entombed Twins")) == [
        131,
        130,
    ]


def test_a_boss_flagged_actor_from_another_fight_is_not_a_candidate() -> None:
    # Neither is named after the fight, so without the enemy filter both would be
    # read as a council.
    actors = (actor(27, "Another Boss", "Boss", 1), actor(9, "Heart of the Colossus", "Boss", 5))
    assert ids(find_bosses(actors, frozenset({9}), FIGHT)) == [9]


def test_two_bosses_named_after_the_fight_are_no_boss() -> None:
    actors = (actor(10, FIGHT, "Boss", 1), actor(11, FIGHT, "Boss", 2))
    assert find_bosses(actors, frozenset({10, 11}), FIGHT) == ()


def test_a_fight_listing_no_boss_flagged_enemy_has_no_boss() -> None:
    actors = (actor(60, FIGHT, "NPC", 1),)
    assert find_bosses(actors, frozenset({60}), FIGHT) == ()
