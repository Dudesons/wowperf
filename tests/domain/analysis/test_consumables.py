# ABOUTME: Which healing consumables a player could have drunk when they died.
# ABOUTME: The category, not the item, is what a cooldown belongs to.

from wowperf.domain.analysis.consumables import analyse_consumables_at_death, consumables_up_at
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run
from wowperf.domain.season import ConsumableCategory, Consumables

POTION = ConsumableCategory(
    name="health potion", cooldown_seconds=300.0, ability_ids=(1234768, 1262857)
)
STONE = ConsumableCategory(name="healthstone", cooldown_seconds=60.0, ability_ids=(6262,))
CATEGORIES = (POTION, STONE)
CONSUMABLES = Consumables(categories=CATEGORIES)

DEATH_MS = 400_000
"""One death, at this timestamp, for every case below.

The health-potion window is (300 + 10) seconds, so it opens at 90_000; the
healthstone window is (60 + 10), so it opens at 330_000.
"""


def a_cast(ability_id: int, at_ms: int, actor_id: int = 11) -> CastEvent:
    return CastEvent(
        actor_id=actor_id, ability_id=ability_id, ability_name="x", timestamp_ms=at_ms
    )


def test_a_category_is_not_claimed_when_the_window_reaches_before_the_log_begins() -> None:
    """The one place dropping the ownership rule would otherwise accuse someone.

    Casts are fetched per fight, so a potion drunk before the timer started is
    invisible. Without proof of ownership to lean on, claiming the category was
    available there would be a false accusation rather than an understatement —
    the direction every other rule in this project leans away from.
    """
    # The health-potion window opens 310s before the death, so a death 100s into
    # a run cannot be judged: the log does not reach back that far.
    early = 100_000
    assert consumables_up_at((), CATEGORIES, 11, early, visible_from_ms=0) == ("healthstone",)


def test_a_window_opening_exactly_when_the_log_does_is_judged() -> None:
    # The boundary is inclusive: a window reaching back to the first visible
    # moment is fully covered, so there is nothing the log failed to see.
    death = 310_000
    assert "health potion" in consumables_up_at(
        (), CATEGORIES, 11, death, visible_from_ms=0
    )
    assert "health potion" not in consumables_up_at(
        (), CATEGORIES, 11, death - 1, visible_from_ms=0
    )


def test_a_player_who_drank_nothing_had_everything_available() -> None:
    # Unlike a defensive, nothing has to prove the player carried one: a potion
    # is a choice they control, and the log cannot tell an unused one from an
    # empty bag either way.
    assert consumables_up_at((), CATEGORIES, 11, DEATH_MS, visible_from_ms=0) == (
        "health potion",
        "healthstone",
    )


def test_any_id_in_a_category_blocks_the_whole_category() -> None:
    # A different health potion from the one listed first still puts the
    # category on cooldown — that is what a category is for.
    casts = (a_cast(1262857, 200_000),)
    assert consumables_up_at(casts, CATEGORIES, 11, DEATH_MS, visible_from_ms=0) == ("healthstone",)


def test_a_category_comes_back_once_its_own_cooldown_has_passed() -> None:
    # Drunk before the health-potion window opened at 90_000.
    casts = (a_cast(1234768, 80_000),)
    assert "health potion" in consumables_up_at(casts, CATEGORIES, 11, DEATH_MS, visible_from_ms=0)


def test_categories_do_not_block_each_other() -> None:
    # A healthstone has not shared a cooldown with health potions since patch
    # 8.0.1, which is why they are separate categories at all.
    casts = (a_cast(6262, 390_000),)
    up = consumables_up_at(casts, CATEGORIES, 11, DEATH_MS, visible_from_ms=0)
    assert up == ("health potion",)


def test_one_drunk_during_the_run_up_is_not_called_unused() -> None:
    casts = (a_cast(6262, 395_000),)
    up = consumables_up_at(casts, CATEGORIES, 11, DEATH_MS, visible_from_ms=0)
    assert "healthstone" not in up


def test_only_this_players_casts_count() -> None:
    casts = (a_cast(1234768, 200_000, actor_id=12),)
    assert "health potion" in consumables_up_at(casts, CATEGORIES, 11, DEATH_MS, visible_from_ms=0)


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=500_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=100, count_required=100, npc_counts=(),
        players=(
            Player(actor_id=11, name="Uglymage", class_name="Mage", spec="Arcane",
                   item_level=318),
        ),
        pulls=pulls,
    )


def a_death(actor_id: int = 11, at_ms: int = DEATH_MS) -> Death:
    return Death(
        player_name="Uglymage", actor_id=actor_id, timestamp_ms=at_ms,
        killing_blow="Shadow Bolt", pull_index=0, seconds_until_next_action=4.0,
    )


def test_a_death_with_a_consumable_available_is_a_finding() -> None:
    findings = analyse_consumables_at_death(a_run(), (), CONSUMABLES, (a_death(),))
    assert len(findings) == 1
    assert findings[0].id == "consumables.unused.Uglymage"
    assert findings[0].confidence is Confidence.INFERRED
    assert findings[0].seconds_lost is None


def test_a_death_with_everything_on_cooldown_says_nothing() -> None:
    casts = (a_cast(1234768, 395_000), a_cast(6262, 395_000))
    assert analyse_consumables_at_death(a_run(), casts, CONSUMABLES, (a_death(),)) == []


def test_the_detail_admits_it_cannot_see_an_empty_bag() -> None:
    # The log records a consumable only when it is drunk, so "available" means
    # "not on cooldown" and nothing more. Saying otherwise would accuse someone
    # of not pressing a button they never had.
    detail = analyse_consumables_at_death(a_run(), (), CONSUMABLES, (a_death(),))[0].detail
    assert "not that one was carried" in detail


def test_no_deaths_says_nothing() -> None:
    assert analyse_consumables_at_death(a_run(), (), CONSUMABLES, ()) == []
