# ABOUTME: Behaviour tests for the deaths section: ordered by time, expanded into the last ten
# ABOUTME: seconds. Built from raw events, not findings, since no finding carries the run-up.

from tests.domain.report.test_build_frame import a_pull, a_run
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_deaths
from wowperf.domain.season import DefensiveAbility, Defensives

NO_DEFENSIVES = Defensives(entries=())
"""For the cards whose subject is not defensives. Says the tool checked nothing."""


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
    assert build_deaths(a_loaded_with((), ()), NO_DEFENSIVES) == ()


def test_a_death_names_the_player_and_the_killing_blow() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()), NO_DEFENSIVES)[0]
    assert card.player == "Dudesons"
    assert card.killing_blow == "Frigid Roar"


def test_a_death_names_the_class_so_the_colour_is_not_the_only_signal() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()), NO_DEFENSIVES)[0]
    assert card.class_name == "DeathKnight"


def test_a_death_by_an_actor_not_in_the_roster_still_renders() -> None:
    card = build_deaths(a_loaded_with((a_death(99, 60_000),), ()), NO_DEFENSIVES)[0]
    assert card.class_name == "unknown class"


def test_a_death_by_a_player_sharing_a_name_is_disambiguated() -> None:
    # Cross-realm groups ordinarily produce two players with the same display
    # name; the actor id disambiguates the death card the same way it already
    # disambiguates the matching player card, so the two are never confused.
    players = (a_player(1, "Sublime"), a_player(2, "Sublime"))
    run = a_run(players=players, pulls=(a_pull(0, 0, 120_000),))
    death = Death(
        player_name="Sublime", actor_id=2, timestamp_ms=60_000,
        killing_blow="Frigid Roar", pull_index=0,
    )
    card = build_deaths(LoadedRun(run=run, deaths=(death,)), NO_DEFENSIVES)[0]
    assert card.player == "Sublime (actor 2)"


def test_the_run_up_holds_only_hits_on_the_player_who_died() -> None:
    hits = (a_hit(1, 55_000, "Frigid Roar", 900), a_hit(2, 55_000, "Snowdrift", 800))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits), NO_DEFENSIVES)[0]
    assert [row.ability for row in card.last_ten_seconds] == ["Frigid Roar"]


def test_the_run_up_stops_ten_seconds_before_the_death() -> None:
    hits = (a_hit(1, 45_000, "Old news", 100), a_hit(1, 55_000, "Frigid Roar", 900))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits), NO_DEFENSIVES)[0]
    assert [row.ability for row in card.last_ten_seconds] == ["Frigid Roar"]


def test_the_run_up_excludes_hits_landing_after_the_death() -> None:
    hits = (a_hit(1, 55_000, "Frigid Roar", 900), a_hit(1, 61_000, "Posthumous", 100))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits), NO_DEFENSIVES)[0]
    assert [row.ability for row in card.last_ten_seconds] == ["Frigid Roar"]


def test_the_run_up_runs_oldest_first_so_it_reads_as_a_story() -> None:
    hits = (a_hit(1, 58_000, "Second", 200), a_hit(1, 52_000, "First", 100))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits), NO_DEFENSIVES)[0]
    assert [row.ability for row in card.last_ten_seconds] == ["First", "Second"]


def test_each_hit_says_how_long_before_the_death_it_landed() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), (a_hit(1, 54_200, "Roar", 900),))
    card = build_deaths(loaded, NO_DEFENSIVES)[0]
    assert card.last_ten_seconds[0].seconds_before == "5.8s before"


def test_a_hits_amount_is_formatted_with_thousands_separators() -> None:
    hits = (a_hit(1, 54_200, "Snowdrift", 82_410),)
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits), NO_DEFENSIVES)[0]
    assert card.last_ten_seconds[0].amount == "82,410"


def test_cards_come_in_the_order_the_deaths_happened() -> None:
    deaths = (a_death(1, 90_000, "Late"), a_death(1, 30_000, "Early"))
    cards = build_deaths(a_loaded_with(deaths, ()), NO_DEFENSIVES)
    assert [card.killing_blow for card in cards] == ["Early", "Late"]


def test_a_deaths_time_is_measured_from_the_runs_start_not_from_report_zero() -> None:
    # `timestamp_ms` is an absolute report timestamp, not an offset from the
    # first pull. A pull starting at 0 would let a regression to the raw
    # timestamp pass unnoticed, so this run's first pull starts well after
    # the report's own zero, the way a real Warcraft Logs report does.
    run = a_run(
        players=(a_player(),),
        pulls=(a_pull(0, 1_800_000, 1_860_000),),
    )
    death = Death(
        player_name="Dudesons", actor_id=1, timestamp_ms=1_830_000,
        killing_blow="Frigid Roar", pull_index=0,
    )
    card = build_deaths(LoadedRun(run=run, deaths=(death,)), NO_DEFENSIVES)[0]
    # 1_830_000 - 1_800_000 = 30_000ms = 0:30 elapsed into the run, not 30:30
    # as the absolute timestamp alone would read.
    assert card.when == "0:30, pull 0"


def test_a_death_before_the_first_pull_does_not_go_negative() -> None:
    run = a_run(players=(a_player(),), pulls=(a_pull(0, 1_800_000, 1_860_000),))
    death = Death(
        player_name="Dudesons", actor_id=1, timestamp_ms=1_700_000,
        killing_blow="Frigid Roar", pull_index=None,
    )
    card = build_deaths(LoadedRun(run=run, deaths=(death,)), NO_DEFENSIVES)[0]
    assert card.when == "0:00, between pulls"


def test_a_death_in_a_run_with_no_pulls_does_not_crash() -> None:
    run = a_run(players=(a_player(),), pulls=())
    death = Death(
        player_name="Dudesons", actor_id=1, timestamp_ms=5_000,
        killing_blow="Frigid Roar", pull_index=None,
    )
    card = build_deaths(LoadedRun(run=run, deaths=(death,)), NO_DEFENSIVES)[0]
    assert card.when == "0:05, between pulls"


BLOOD = Defensives(
    entries=(
        (
            "DeathKnight/Blood",
            (
                DefensiveAbility(
                    ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0
                ),
            ),
        ),
    )
)


def test_a_card_names_the_defensives_that_were_off_cooldown() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()), BLOOD)[0]
    assert card.defensives_checked is True
    assert card.defensives_available == ("Icebound Fortitude",)


def test_a_card_says_the_defensives_were_checked_even_when_none_were_up() -> None:
    # "Nothing was off cooldown" exonerates the player, and is as worth showing
    # as the accusation. It must not be renderable as the same blank as an
    # unknown spec.
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(
        update={
            "casts": (
                CastEvent(
                    actor_id=1, ability_id=48792, ability_name="Icebound Fortitude",
                    timestamp_ms=55_000, pull_index=0,
                ),
            )
        }
    )
    card = build_deaths(loaded, BLOOD)[0]
    assert card.defensives_checked is True
    assert card.defensives_available == ()


def test_a_spec_the_data_file_does_not_cover_is_marked_unchecked() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()), Defensives(entries=()))[0]
    assert card.defensives_checked is False
    assert card.defensives_available == ()
