# ABOUTME: The damage-outlier finding, exercised against a roster rather than a Run.
# ABOUTME: Guards the tank exclusion and the three-player floor a median needs.

from wowperf.domain.analysis.damage_outliers import (
    analyse_damage_outliers,
    damage_matrix,
    damage_outliers,
)
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.model import Player
from wowperf.domain.season import Roles

ROLES = Roles(tanks=("Warrior/Protection",), healers=("Priest/Holy",))


def player(actor_id: int, name: str, class_name: str, spec: str) -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name=class_name, spec=spec, item_level=600
    )


def hit(
    actor_id: int, amount: int, *, ability_id: int = 400, ability_name: str = "Ravenous Feast"
) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id,
        ability_id=ability_id,
        ability_name=ability_name,
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


def test_the_matrix_keeps_tank_totals_that_the_median_excludes() -> None:
    """The grid shows a tank's row; the median must still not see it.

    A tank taking ten times what everyone else took is the job. Counting one
    into the baseline would raise it for every non-tank and silently retire
    findings that are correct.
    """
    players = (
        Player(actor_id=1, name="Raider 1", class_name="Mage", spec="Frost", item_level=690),
        Player(actor_id=2, name="Raider 2", class_name="Mage", spec="Frost", item_level=690),
        Player(actor_id=3, name="Raider 3", class_name="Mage", spec="Frost", item_level=690),
        Player(
            actor_id=4, name="Raider 4", class_name="DeathKnight", spec="Blood", item_level=690
        ),
    )
    hits = (
        hit(actor_id=1, ability_id=11, amount=100),
        hit(actor_id=2, ability_id=11, amount=100),
        hit(actor_id=3, ability_id=11, amount=100),
        hit(actor_id=4, ability_id=11, amount=9000),
    )

    # Roles() alone leaves every class/spec classified as "damage" -- pinned by
    # tests/domain/test_season.py -- so the tank in this fixture must be named
    # explicitly, the same way tests/domain/analysis/test_players.py does.
    matrix = damage_matrix(players, hits, Roles(tanks=("DeathKnight/Blood",)))
    totals = matrix.by_ability[11]

    assert totals.amounts[4] == 9000, "the tank's own total is not reported"
    assert totals.median_amount == 100, "the tank reached the median"
    assert totals.took_count == 3, "the tank was counted among those who took it"


def test_the_matrix_withholds_a_median_below_the_floor() -> None:
    """Two players is not a group baseline, and `None` says so rather than 0.0."""
    players = (
        Player(actor_id=1, name="Raider 1", class_name="Mage", spec="Frost", item_level=690),
        Player(actor_id=2, name="Raider 2", class_name="Mage", spec="Frost", item_level=690),
    )
    hits = (
        hit(actor_id=1, ability_id=11, amount=100),
        hit(actor_id=2, ability_id=11, amount=100),
    )

    assert damage_matrix(players, hits, Roles()).by_ability[11].median_amount is None


def test_damage_outliers_reports_exactly_what_it_did_before() -> None:
    """The refactor is behaviour-preserving, and this is what says so.

    Three players at the baseline and one at four times it: the same shape the
    finding was written against. If retaining tank totals moved any median,
    this is where it shows.
    """
    players = tuple(
        Player(actor_id=index, name=f"Raider {index}", class_name="Mage", spec="Frost",
               item_level=690)
        for index in range(1, 5)
    )
    hits = (
        hit(actor_id=1, ability_id=11, amount=100),
        hit(actor_id=2, ability_id=11, amount=100),
        hit(actor_id=3, ability_id=11, amount=100),
        hit(actor_id=4, ability_id=11, amount=400),
    )

    [outlier] = damage_outliers(players, hits, Roles())

    assert outlier.actor_id == 4
    assert outlier.ability_id == 11
    assert outlier.amount == 400
    assert outlier.median_amount == 100
    assert outlier.took_count == 4
