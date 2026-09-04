# ABOUTME: Behaviour tests for the event entities that analysers consume.
# ABOUTME: Covers only defaulting; the interesting logic lives in the analysers.

from wowperf.domain.events import CastEvent, Death


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
