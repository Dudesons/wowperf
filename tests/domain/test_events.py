# ABOUTME: Behaviour tests for the event entities that analysers consume.
# ABOUTME: Covers only defaulting; the interesting logic lives in the analysers.

from wowperf.domain.events import CastEvent, Death, EnemyCast


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
        interrupted_by="Uglymage",
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
