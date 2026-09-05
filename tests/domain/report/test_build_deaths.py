# ABOUTME: Behaviour tests for the deaths section: ordered by time, expanded into the last ten
# ABOUTME: seconds. Built from raw events, not findings, since no finding carries the run-up.

from tests.domain.report.test_build_frame import a_pull, a_run
from wowperf.domain.events import DamageTakenEvent, Death
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_deaths


def a_player(actor_id: int = 1, name: str = "Dudesons") -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=680
    )


def a_death(actor_id: int, at_ms: int, blow: str = "Frigid Roar") -> Death:
    return Death(
        player_name="Dudesons",
        actor_id=actor_id,
        timestamp_ms=at_ms,
        killing_blow=blow,
        pull_index=0,
    )


def a_hit(actor_id: int, at_ms: int, ability: str, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id,
        ability_id=1,
        ability_name=ability,
        amount=amount,
        timestamp_ms=at_ms,
        pull_index=0,
    )


def a_loaded_with(deaths: tuple[Death, ...], hits: tuple[DamageTakenEvent, ...]) -> LoadedRun:
    return LoadedRun(
        run=a_run(players=(a_player(),), pulls=(a_pull(0, 0, 120_000),)),
        deaths=deaths,
        damage_taken=hits,
    )


def test_a_run_with_no_deaths_yields_no_cards() -> None:
    assert build_deaths(a_loaded_with((), ())) == ()


def test_a_death_names_the_player_and_the_killing_blow() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()))[0]
    assert card.player == "Dudesons"
    assert card.killing_blow == "Frigid Roar"


def test_a_death_names_the_class_so_the_colour_is_not_the_only_signal() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()))[0]
    assert card.class_name == "DeathKnight"


def test_a_death_by_an_actor_not_in_the_roster_still_renders() -> None:
    card = build_deaths(a_loaded_with((a_death(99, 60_000),), ()))[0]
    assert card.class_name == "unknown class"


def test_the_run_up_holds_only_hits_on_the_player_who_died() -> None:
    hits = (a_hit(1, 55_000, "Frigid Roar", 900), a_hit(2, 55_000, "Snowdrift", 800))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits))[0]
    assert [row.ability for row in card.last_ten_seconds] == ["Frigid Roar"]


def test_the_run_up_stops_ten_seconds_before_the_death() -> None:
    hits = (a_hit(1, 45_000, "Old news", 100), a_hit(1, 55_000, "Frigid Roar", 900))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits))[0]
    assert [row.ability for row in card.last_ten_seconds] == ["Frigid Roar"]


def test_the_run_up_excludes_hits_landing_after_the_death() -> None:
    hits = (a_hit(1, 55_000, "Frigid Roar", 900), a_hit(1, 61_000, "Posthumous", 100))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits))[0]
    assert [row.ability for row in card.last_ten_seconds] == ["Frigid Roar"]


def test_the_run_up_runs_oldest_first_so_it_reads_as_a_story() -> None:
    hits = (a_hit(1, 58_000, "Second", 200), a_hit(1, 52_000, "First", 100))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits))[0]
    assert [row.ability for row in card.last_ten_seconds] == ["First", "Second"]


def test_each_hit_says_how_long_before_the_death_it_landed() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), (a_hit(1, 54_200, "Roar", 900),)))[0]
    assert card.last_ten_seconds[0].seconds_before == "5.8s before"


def test_cards_come_in_the_order_the_deaths_happened() -> None:
    deaths = (a_death(1, 90_000, "Late"), a_death(1, 30_000, "Early"))
    cards = build_deaths(a_loaded_with(deaths, ()))
    assert [card.killing_blow for card in cards] == ["Early", "Late"]
