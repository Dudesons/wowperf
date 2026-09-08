# ABOUTME: Behaviour tests for the event entities that analysers consume.
# ABOUTME: Covers only defaulting; the interesting logic lives in the analysers.

from wowperf.domain.events import (
    CastEvent,
    DamageTakenEvent,
    Death,
    EnemyCast,
    EnemyCastRow,
    HealingEvent,
    HealthSample,
    Resurrection,
)


def test_a_death_outside_any_pull_has_no_pull_index() -> None:
    death = Death(
        player_name="Someone",
        actor_id=1,
        timestamp_ms=5000,
        killing_blow="Void Bolt",
    )
    assert death.pull_index is None
    assert death.seconds_until_next_action is None


def test_a_cast_records_the_ability_by_id_and_name() -> None:
    cast = CastEvent(actor_id=1, ability_id=42, ability_name="Frostbolt", timestamp_ms=100)
    assert (cast.ability_id, cast.ability_name) == (42, "Frostbolt")


def test_an_enemy_cast_that_landed_records_when() -> None:
    cast = EnemyCast(
        source_id=699,
        source_instance=0,
        ability_id=1238440,
        ability_name="Molten Scar",
        started_ms=1000,
        completed_ms=2500,
    )
    assert cast.landed is True
    assert cast.was_kicked is False
    assert cast.outcome_known is True


def test_an_enemy_cast_that_was_kicked_names_the_interrupter() -> None:
    cast = EnemyCast(
        source_id=699,
        source_instance=0,
        ability_id=1238440,
        ability_name="Molten Scar",
        started_ms=1000,
        interrupted_by="Emberkin",
    )
    assert cast.was_kicked is True
    assert cast.landed is False
    assert cast.outcome_known is True


def test_an_enemy_cast_with_no_resolution_is_excluded() -> None:
    cast = EnemyCast(
        source_id=699,
        source_instance=0,
        ability_id=1238440,
        ability_name="Molten Scar",
        started_ms=1000,
    )
    assert cast.outcome_known is False
    assert cast.landed is False
    assert cast.was_kicked is False


def test_an_enemy_cast_row_that_starts_is_marked() -> None:
    cast_row = EnemyCastRow(
        source_id=699,
        source_instance=0,
        ability_id=1238440,
        ability_name="Molten Scar",
        timestamp_ms=1000,
        is_start=True,
    )
    assert cast_row.is_start is True
    assert cast_row.ability_name == "Molten Scar"
    assert cast_row.pull_index is None


def test_an_enemy_cast_row_that_completes_is_marked() -> None:
    cast_row = EnemyCastRow(
        source_id=699,
        source_instance=0,
        ability_id=1238440,
        ability_name="Molten Scar",
        timestamp_ms=2500,
        is_start=False,
    )
    assert cast_row.is_start is False
    assert cast_row.timestamp_ms == 2500


def test_an_enemy_cast_row_with_pull_index() -> None:
    cast_row = EnemyCastRow(
        source_id=699,
        source_instance=0,
        ability_id=1238440,
        ability_name="Molten Scar",
        timestamp_ms=1000,
        is_start=True,
        pull_index=5,
    )
    assert cast_row.pull_index == 5


def test_a_hit_keeps_what_reached_health_apart_from_what_a_shield_soaked() -> None:
    hit = DamageTakenEvent(
        actor_id=1, ability_id=5, ability_name="Molten Scar", amount=132_788,
        timestamp_ms=2500, health_damage=0, absorbed=123_570,
    )
    assert (hit.amount, hit.health_damage, hit.absorbed) == (132_788, 0, 123_570)


def test_a_hit_built_without_the_split_reads_as_nothing_absorbed() -> None:
    # Existing fixtures build hits with the unmitigated figure alone; they must
    # still construct, and a missing split must not invent an absorb.
    hit = DamageTakenEvent(actor_id=1, ability_id=5, ability_name="x", amount=9, timestamp_ms=1)
    assert (hit.health_damage, hit.absorbed) == (0, 0)


def test_a_health_sample_is_a_reading_of_the_players_own_health() -> None:
    sample = HealthSample(actor_id=1, timestamp_ms=1000, hit_points=61_200, max_hit_points=99_000)
    assert sample.hit_points < sample.max_hit_points


def test_a_healing_event_is_a_heal_unless_it_says_it_was_an_absorb() -> None:
    heal = HealingEvent(
        actor_id=1, source_id=2, ability_id=7, ability_name="Rejuvenation", amount=9_100,
        timestamp_ms=1000,
    )
    absorb = heal.model_copy(update={"absorbed": True, "ability_name": "Power Word: Shield"})
    assert (heal.absorbed, absorb.absorbed) == (False, True)


def test_a_resurrection_names_who_brought_the_player_back() -> None:
    back = Resurrection(
        actor_id=1, caster_id=3, ability_id=61999, ability_name="Raise Ally", timestamp_ms=5000
    )
    assert back.caster_id != back.actor_id
