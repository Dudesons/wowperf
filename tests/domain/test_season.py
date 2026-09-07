# ABOUTME: Behaviour tests for the season constants the timer arithmetic depends on.
# ABOUTME: The threshold is a boundary, so both sides of it are pinned here.

import pytest
from pydantic import ValidationError

from wowperf.domain.season import DefensiveAbility, ExternalAbility, Externals, Roles, SeasonData


def a_season() -> SeasonData:
    return SeasonData(
        death_penalty_seconds=5.0,
        death_penalty_seconds_high_key=15.0,
        high_key_threshold=12,
    )


def test_a_low_key_uses_the_base_death_penalty() -> None:
    assert a_season().death_penalty(11) == 5.0


def test_the_threshold_itself_uses_the_high_penalty() -> None:
    assert a_season().death_penalty(12) == 15.0


def test_above_the_threshold_uses_the_high_penalty() -> None:
    assert a_season().death_penalty(20) == 15.0


def test_a_defensive_carries_the_cooldown_its_ceiling_is_computed_from() -> None:
    ability = DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0)

    assert ability.cooldown_seconds == 180.0
    assert ability.charges == 1


def test_a_defensive_with_two_charges_says_so() -> None:
    ability = DefensiveAbility(
        ability_id=55342, name="Mirror Image", cooldown_seconds=120.0, charges=2
    )

    assert ability.charges == 2


def test_a_defensive_without_a_cooldown_cannot_be_built() -> None:
    with pytest.raises(ValidationError):
        DefensiveAbility(ability_id=1, name="Nameless")  # type: ignore[call-arg]


def test_role_of_reads_the_spec_lists_and_defaults_to_damage() -> None:
    roles = Roles(tanks=("DeathKnight/Blood",), healers=("Paladin/Holy",))
    assert roles.role_of("DeathKnight", "Blood") == "tank"
    assert roles.role_of("Paladin", "Holy") == "healer"
    assert roles.role_of("Mage", "Arcane") == "damage"
    assert Roles().role_of("DeathKnight", "Blood") == "damage"


def test_externals_resolve_per_spec_and_default_to_none_listed() -> None:
    cocoon = ExternalAbility(ability_id=1, name="Life Cocoon", cooldown_seconds=120.0)
    externals = Externals(entries=(("Monk/Mistweaver", (cocoon,)),))
    assert externals.for_spec("Monk", "Mistweaver") == (cocoon,)
    assert externals.for_spec("Monk", "Windwalker") == ()
    assert Externals().for_spec("Monk", "Mistweaver") == ()
