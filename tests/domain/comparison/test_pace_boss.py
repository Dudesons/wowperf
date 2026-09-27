# ABOUTME: Which enemy actor is the boss: flagged a boss and named after the fight, exactly one.
# ABOUTME: Pins the same-named non-boss, the boss-framed adds, and a council.

from wowperf.domain.comparison.pace_boss import NpcActor, find_boss_actor

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
