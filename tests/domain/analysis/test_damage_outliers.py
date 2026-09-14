# ABOUTME: The damage-outlier finding, exercised against a roster rather than a Run.
# ABOUTME: Guards the tank exclusion and the three-player floor a median needs.

from wowperf.domain.analysis.damage_outliers import analyse_damage_outliers
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.model import Player
from wowperf.domain.season import Roles

ROLES = Roles(tanks=("Warrior/Protection",), healers=("Priest/Holy",))


def player(actor_id: int, name: str, class_name: str, spec: str) -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name=class_name, spec=spec, item_level=600
    )


def hit(actor_id: int, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id,
        ability_id=400,
        ability_name="Ravenous Feast",
        amount=amount,
        timestamp_ms=1000,
    )


ROSTER = (
    player(1, "Emberkin", "Mage", "Frost"),
    player(2, "Stonewake", "Mage", "Frost"),
    player(3, "Bríala", "Mage", "Frost"),
    player(4, "Кириллица", "Warrior", "Protection"),
)


def test_a_player_far_above_the_median_of_one_ability_is_a_finding() -> None:
    # Median over the three who took it is 100; actor 1 took 400, a 4.0x multiple.
    findings = analyse_damage_outliers(
        ROSTER, (hit(1, 400), hit(2, 100), hit(3, 100)), ROLES
    )
    assert findings, "three takers clear the median floor, so one outlier is expected"
    assert findings[0].id == "players.damage.0"
    assert "4.0x" in findings[0].title
    assert findings[0].ability_id == 400


def test_the_tank_is_excluded_even_when_it_took_the_most() -> None:
    # The tank takes ten times the others. Excluding tanks is the point: as one of
    # two in a raid and one of one in a key, a tank has no honest median.
    findings = analyse_damage_outliers(
        ROSTER, (hit(4, 4000), hit(1, 100), hit(2, 100), hit(3, 100)), ROLES
    )
    # With the tank left out, the three survivors all took the same amount, so
    # nothing clears the median and the list is empty. Saying that is stronger
    # than an `all(...)` over it, which holds however the exclusion behaves.
    # Without the exclusion the tank is 40x the median of four and a finding.
    assert findings == [], "the tank reached a finding despite the role exclusion"


def test_two_takers_are_below_the_median_floor_and_produce_nothing() -> None:
    # MIN_PLAYERS_FOR_MEDIAN is 3. A median of two is a mean of two.
    findings = analyse_damage_outliers(ROSTER, (hit(1, 400), hit(2, 100)), ROLES)
    assert findings == []
