# ABOUTME: Behaviour tests for the deaths section: one recap per death, ordered by time, holding
# ABOUTME: a formatted timeline, three availability groups and a return line. Built from events.

from tests.domain.report.test_build_frame import (
    FETCHED,
    NO_CONSUMABLES,
    NO_DEFENSIVES,
    a_pull,
    a_run,
)
from tests.domain.report.test_build_observations import SUBJECT, a_finding, a_loaded
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.events import (
    CastEvent,
    DamageTakenEvent,
    Death,
    HealingEvent,
    HealthSample,
    Resurrection,
)
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_report
from wowperf.domain.report.deaths import (
    CONSUMABLE_CAVEAT,
    NO_CONSUMABLE_DATA,
    NO_TIMELINE_EVENT,
    build_deaths,
)
from wowperf.domain.report.model import DeathCard
from wowperf.domain.season import (
    ConsumableCategory,
    Consumables,
    DefensiveAbility,
    Defensives,
    ExternalAbility,
    Externals,
    SelfResurrections,
)

NO_EXTERNALS = Externals()
IRONBARK = ExternalAbility(ability_id=102342, name="Ironbark", cooldown_seconds=90.0)


def a_player(actor_id: int = 1, name: str = "Stonewake") -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=680
    )


def a_death(actor_id: int, at_ms: int, blow: str = "Frigid Roar") -> Death:
    return Death(
        player_name="Stonewake",
        actor_id=actor_id,
        timestamp_ms=at_ms,
        killing_blow=blow,
        pull_index=0,
    )


def a_hit(actor_id: int, at_ms: int, ability: str, amount: int) -> DamageTakenEvent:
    # `health_damage` matches `amount` here: nothing in these fixtures is
    # absorbed, so what the hit was worth is also what reached health.
    return DamageTakenEvent(
        actor_id=actor_id,
        ability_id=1,
        ability_name=ability,
        amount=amount,
        health_damage=amount,
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
    assert build_deaths(a_loaded_with((), ()), NO_DEFENSIVES, NO_CONSUMABLES) == ()


def test_a_death_names_the_player_and_the_killing_blow() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()), NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.player == "Stonewake"
    assert card.killing_blow == "Frigid Roar"


def test_a_death_names_the_class_so_the_colour_is_not_the_only_signal() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()), NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.class_name == "DeathKnight"


def test_a_death_by_an_actor_not_in_the_roster_still_renders() -> None:
    card = build_deaths(a_loaded_with((a_death(99, 60_000),), ()), NO_DEFENSIVES, NO_CONSUMABLES)[0]
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
    card = build_deaths(LoadedRun(run=run, deaths=(death,)), NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.player == "Sublime (actor 2)"


def test_the_run_up_holds_only_hits_on_the_player_who_died() -> None:
    hits = (a_hit(1, 55_000, "Frigid Roar", 900), a_hit(2, 55_000, "Snowdrift", 800))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits),
        NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert [row.ability for row in card.timeline] == ["Frigid Roar"]


def test_the_run_up_stops_ten_seconds_before_the_death() -> None:
    hits = (a_hit(1, 45_000, "Old news", 100), a_hit(1, 55_000, "Frigid Roar", 900))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits),
        NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert [row.ability for row in card.timeline] == ["Frigid Roar"]


def test_the_run_up_excludes_hits_landing_after_the_death() -> None:
    hits = (a_hit(1, 55_000, "Frigid Roar", 900), a_hit(1, 61_000, "Posthumous", 100))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits),
        NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert [row.ability for row in card.timeline] == ["Frigid Roar"]


def test_the_run_up_runs_oldest_first_so_it_reads_as_a_story() -> None:
    hits = (a_hit(1, 58_000, "Second", 200), a_hit(1, 52_000, "First", 100))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits),
        NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert [row.ability for row in card.timeline] == ["First", "Second"]


def test_each_hit_says_how_long_before_the_death_it_landed() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), (a_hit(1, 54_200, "Roar", 900),))
    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.timeline[0].seconds_before == "5.8 s"


def test_a_hits_amount_is_formatted_with_thousands_separators() -> None:
    hits = (a_hit(1, 54_200, "Snowdrift", 82_410),)
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits),
        NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.timeline[0].detail == "82,410 to health"


def test_the_timeline_rows_are_formatted_and_carry_their_kind() -> None:
    hits = (a_hit(1, 54_200, "Snowdrift", 82_410),)
    loaded = a_loaded_with((a_death(1, 60_000),), hits).model_copy(update={
        "health_samples": (HealthSample(actor_id=1, timestamp_ms=50_000, hit_points=100_000,
                                        max_hit_points=100_000),),
        "healing": (HealingEvent(actor_id=1, source_id=1, ability_id=7, ability_name="Death Strike",
                                 amount=9_100, timestamp_ms=55_000),),
    })
    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert [(r.seconds_before, r.kind, r.ability, r.detail, r.health) for r in card.timeline] == [
        ("5.8 s", "hit", "Snowdrift", "82,410 to health", "18%"),
        ("5.0 s", "heal", "Death Strike", "+9,100 from Stonewake", "27%"),
    ]
    assert card.health_badge is not None and card.health_badge.label == "derived"
    assert card.health_note == ""


def test_a_hit_that_a_shield_partly_soaked_says_so() -> None:
    hit = a_hit(1, 55_000, "Snowdrift", 10_000).model_copy(update={"absorbed": 4_000})
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), (hit,)), NO_DEFENSIVES,
                        NO_CONSUMABLES)[0]
    assert card.timeline[0].detail == "10,000 to health, 4,000 absorbed"


def test_an_absorb_row_names_the_shield_and_what_it_soaked() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(update={
        "healing": (HealingEvent(actor_id=1, source_id=2, ability_id=17,
                                 ability_name="Power Word: Shield", amount=12_000,
                                 timestamp_ms=55_000, absorbed=True),),
    })
    row = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0].timeline[0]
    assert (row.kind, row.ability, row.detail) == ("absorb", "Power Word: Shield", "12,000 soaked")


def test_without_a_health_reading_the_column_is_empty_and_the_card_says_why() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), (a_hit(1, 55_000, "x", 1),)),
                        NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.timeline[0].health == "" and card.timeline[0].health_percent is None
    assert card.health_badge is None
    assert "no health reading" in card.health_note


def test_cards_come_in_the_order_the_deaths_happened() -> None:
    deaths = (a_death(1, 90_000, "Late"), a_death(1, 30_000, "Early"))
    cards = build_deaths(a_loaded_with(deaths, ()), NO_DEFENSIVES, NO_CONSUMABLES)
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
        player_name="Stonewake", actor_id=1, timestamp_ms=1_830_000,
        killing_blow="Frigid Roar", pull_index=0,
    )
    card = build_deaths(LoadedRun(run=run, deaths=(death,)), NO_DEFENSIVES, NO_CONSUMABLES)[0]
    # 1_830_000 - 1_800_000 = 30_000ms = 0:30 elapsed into the run, not 30:30
    # as the absolute timestamp alone would read.
    assert card.when == "0:30, pull 0"


def test_a_death_before_the_first_pull_does_not_go_negative() -> None:
    run = a_run(players=(a_player(),), pulls=(a_pull(0, 1_800_000, 1_860_000),))
    death = Death(
        player_name="Stonewake", actor_id=1, timestamp_ms=1_700_000,
        killing_blow="Frigid Roar", pull_index=None,
    )
    card = build_deaths(LoadedRun(run=run, deaths=(death,)), NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.when == "0:00, between pulls"


def test_a_death_in_a_run_with_no_pulls_does_not_crash() -> None:
    """And names no pull, because a run with none has nothing to be between.

    The trailing phrase depends on whether the fight is cut into pulls, which
    this run is not. The death two tests above, on a run that does have one,
    still reads ", between pulls" -- that is the distinction the phrase makes,
    and it is a distinction this run does not have.
    """
    run = a_run(players=(a_player(),), pulls=())
    death = Death(
        player_name="Stonewake", actor_id=1, timestamp_ms=5_000,
        killing_blow="Frigid Roar", pull_index=None,
    )
    card = build_deaths(LoadedRun(run=run, deaths=(death,)), NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.when == "0:05"


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


def owns_icebound(at_ms: int) -> tuple[CastEvent, ...]:
    """A cast somewhere in the run, proving the player has the talent at all."""
    return (
        CastEvent(actor_id=1, ability_id=48792, ability_name="Icebound Fortitude",
                  timestamp_ms=at_ms, pull_index=0),
    )


def test_a_card_lists_a_defensive_that_was_off_cooldown_as_ready() -> None:
    # Pressed after the rez, so the ability is demonstrably theirs and the cast
    # falls outside the window that ends at the death.
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(
        update={"casts": owns_icebound(70_000)}
    )
    own = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0].availability[0]
    assert [(row.ability, row.state) for row in own.rows] == [("Icebound Fortitude", "ready")]
    assert own.badge is not None


def test_a_defensive_pressed_in_the_run_up_reads_as_pressed_not_as_a_blank() -> None:
    # "It was used" exonerates the player, and is as worth showing as the
    # accusation. It must not be renderable as the same blank as an unknown spec.
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(
        update={"casts": owns_icebound(55_000)}
    )
    own = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0].availability[0]
    assert [(row.state, row.detail) for row in own.rows] == [("pressed", "5.0 s before death")]
    assert own.badge is not None


def test_the_availability_groups_come_in_order_with_their_badges_and_notes() -> None:
    dude, tree = a_player(), Player(actor_id=2, name="Leafy", class_name="Druid",
                                    spec="Restoration", item_level=680)
    loaded = LoadedRun(
        run=a_run(players=(dude, tree), pulls=(a_pull(0, 0, 120_000),)),
        deaths=(a_death(1, 200_000),),
        # The stone is drunk at 100s, well outside the run-up the timeline
        # draws: since 2026-09-12 a category nobody drank from carries no row,
        # so without a press the consumables group this test is about is empty.
        casts=(CastEvent(actor_id=2, ability_id=102342, ability_name="Ironbark",
                         timestamp_ms=150_000, target_id=3),
               CastEvent(actor_id=1, ability_id=6262, ability_name="Healthstone",
                         timestamp_ms=100_000),),
    )
    defensives = Defensives(entries=(("DeathKnight/Blood", (
        DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=120.0),
    )),))
    consumables = Consumables(categories=(
        ConsumableCategory(name="healthstone", cooldown_seconds=60.0, ability_ids=(6262,)),
    ))
    card = build_deaths(loaded, defensives, consumables,
                        externals=Externals(entries=(("Druid/Restoration", (IRONBARK,)),)))[0]
    own, drinks, mates = card.availability
    assert [g.title for g in card.availability] == ["Defensives", "Consumables",
                                                    "Teammates' externals"]
    assert [(r.ability, r.state, r.detail) for r in own.rows] == [
        ("Icebound Fortitude", "unseen", "not seen this run")
    ]
    assert [(r.ability, r.state, r.detail) for r in drinks.rows] == [
        ("healthstone", "ready", "ready")
    ]
    assert drinks.note == CONSUMABLE_CAVEAT
    assert [(r.ability, r.owner, r.state, r.detail) for r in mates.rows] == [
        ("Ironbark", "Leafy", "cooldown", "at most 40 s left")
    ]
    assert all(g.badge is not None and g.badge.label == "inferred" for g in card.availability)


def test_a_spec_no_file_covers_gets_a_note_and_no_badge_rather_than_an_empty_list() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()), NO_DEFENSIVES,
                        NO_CONSUMABLES)[0]
    own, drinks, mates = card.availability
    assert own.rows == () and own.badge is None and "DeathKnight Blood" in own.note
    assert drinks.rows == () and drinks.badge is None
    assert mates.rows == () and mates.badge is None and "No teammate" in mates.note


def test_an_availability_row_carries_the_ability_id_it_names() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()), BLOOD, NO_CONSUMABLES)[0]
    defensives = card.availability[0]
    assert [row.ability_id for row in defensives.rows] == [48792]


def test_a_pressed_row_and_a_ready_for_row_carry_one_decimal() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(update={
        "casts": (CastEvent(actor_id=1, ability_id=48792, ability_name="IBF", timestamp_ms=56_600),
                  CastEvent(actor_id=1, ability_id=194679, ability_name="Rune Tap",
                            timestamp_ms=60_000 - 29_000)),
    })
    defensives = Defensives(entries=(("DeathKnight/Blood", (
        DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=120.0),
        DefensiveAbility(ability_id=194679, name="Rune Tap", cooldown_seconds=25.0),
    )),))
    own = build_deaths(loaded, defensives, NO_CONSUMABLES)[0].availability[0]
    assert [(r.state, r.detail) for r in own.rows] == [
        ("pressed", "3.4 s before death"), ("ready", "ready, for at least 4.0 s")
    ]


POTIONS = Consumables(
    categories=(
        ConsumableCategory(
            name="health potion", cooldown_seconds=300.0, ability_ids=(1234768,)
        ),
    )
)


# Late enough that the health-potion window (300s + the 10s run-up) fits inside
# the run: a death before then is one the log cannot see far enough back for.
LATE_ENOUGH_MS = 400_000


def test_a_card_lists_a_consumable_whose_cooldown_was_clear_as_ready() -> None:
    # Drunk early, outside the window, so the category is theirs to speak about.
    loaded = a_loaded_with((a_death(1, LATE_ENOUGH_MS),), ()).model_copy(
        update={
            "casts": (
                CastEvent(actor_id=1, ability_id=1234768, ability_name="Health Potion",
                          timestamp_ms=1_000, pull_index=0),
            )
        }
    )
    drinks = build_deaths(loaded, NO_DEFENSIVES, POTIONS)[0].availability[1]
    assert [(row.ability, row.state) for row in drinks.rows] == [("health potion", "ready")]
    assert drinks.badge is not None


def test_a_consumable_still_on_cooldown_states_an_upper_bound_never_a_value() -> None:
    # Drunk at 200s with a 300s cooldown, so a charge is free at 500s: the log
    # records no cooldown reduction, which makes 100 s a ceiling and not a figure.
    loaded = a_loaded_with((a_death(1, LATE_ENOUGH_MS),), ()).model_copy(
        update={
            "casts": (
                CastEvent(actor_id=1, ability_id=1234768, ability_name="Health Potion",
                          timestamp_ms=200_000, pull_index=0),
            )
        }
    )
    drinks = build_deaths(loaded, NO_DEFENSIVES, POTIONS)[0].availability[1]
    assert [(row.state, row.detail) for row in drinks.rows] == [
        ("cooldown", "at most 100 s left")
    ]


def test_an_empty_consumables_group_says_why_instead_of_the_caveat() -> None:
    # Two different situations produce an empty group: no consumable is listed
    # for the run at all, or every category's cooldown window reaches back
    # before the run began. Neither is "checked and found nothing on
    # cooldown", so the caveat — which qualifies rows that are there — must
    # not appear over an empty list.
    empty = build_deaths(a_loaded_with((a_death(1, LATE_ENOUGH_MS),), ()), NO_DEFENSIVES,
                         NO_CONSUMABLES)[0].availability[1]
    assert empty.rows == ()
    assert empty.note == NO_CONSUMABLE_DATA
    assert empty.note != CONSUMABLE_CAVEAT

    loaded = a_loaded_with((a_death(1, LATE_ENOUGH_MS),), ()).model_copy(
        update={
            "casts": (
                CastEvent(actor_id=1, ability_id=1234768, ability_name="Health Potion",
                          timestamp_ms=1_000, pull_index=0),
            )
        }
    )
    filled = build_deaths(loaded, NO_DEFENSIVES, POTIONS)[0].availability[1]
    assert filled.rows != ()
    assert filled.note == CONSUMABLE_CAVEAT


def test_an_actor_not_on_the_roster_gets_no_consumable_rows_either() -> None:
    # The findings file iterates the roster, so it says nothing for an actor it
    # cannot identify. The card must not claim more than the findings do.
    card = build_deaths(
        a_loaded_with((a_death(99, LATE_ENOUGH_MS),), ()), NO_DEFENSIVES, POTIONS
    )[0]
    own, drinks, _ = card.availability
    assert own.rows == () and own.badge is None
    assert drinks.rows == () and drinks.badge is None


def test_the_return_line_is_worded_per_outcome_and_badged() -> None:
    dude, thrall = a_player(), Player(actor_id=3, name="Thrall", class_name="DeathKnight",
                                      spec="Unholy", item_level=680)
    base = LoadedRun(run=a_run(players=(dude, thrall), pulls=(a_pull(0, 0, 120_000),)))
    raised = base.model_copy(update={
        "deaths": (a_death(1, 60_000).model_copy(update={"seconds_until_next_action": 12.0}),),
        "resurrections": (Resurrection(actor_id=1, caster_id=3, ability_id=61999,
                                       ability_name="Raise Ally", timestamp_ms=68_000),),
    })
    released = base.model_copy(update={
        "deaths": (a_death(1, 60_000).model_copy(update={"seconds_until_next_action": 34.2}),),
    })
    gone = base.model_copy(update={"deaths": (a_death(1, 60_000),)})
    cards = [
        build_deaths(run, NO_DEFENSIVES, NO_CONSUMABLES)[0]
        for run in (raised, released, gone)
    ]
    assert [(c.came_back, c.came_back_badge.label) for c in cards] == [  # type: ignore[union-attr]
        ("Resurrected by Thrall with Raise Ally, 8.0 s after death.", "measured"),
        ("Released; first action against an enemy 34.2 s after death.", "derived"),
        ("Not seen acting again this run.", "measured"),
    ]


def test_a_death_with_an_empty_run_up_carries_the_reason_as_a_note() -> None:
    # A timeline with nothing in it is a fact about the death, so the builder
    # states it. The template prints what it is handed and composes no sentence.
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()), NO_DEFENSIVES, NO_CONSUMABLES)[0]

    assert card.timeline == ()
    assert card.timeline_note == NO_TIMELINE_EVENT


def test_an_actor_whose_id_is_zero_is_named_like_any_other() -> None:
    # Zero is falsy, and both the healer and the resurrecting teammate are
    # looked up by id. Neither may fall through to the anonymous wording.
    naught = Player(actor_id=0, name="Naught", class_name="Priest", spec="Holy", item_level=680)
    loaded = LoadedRun(
        run=a_run(players=(a_player(), naught), pulls=(a_pull(0, 0, 120_000),)),
        deaths=(a_death(1, 60_000).model_copy(update={"seconds_until_next_action": 12.0}),),
        damage_taken=(a_hit(1, 55_000, "Snowdrift", 10_000),),
        healing=(HealingEvent(actor_id=1, source_id=0, ability_id=2061,
                              ability_name="Flash Heal", amount=9_000, timestamp_ms=56_000),),
        resurrections=(Resurrection(actor_id=1, caster_id=0, ability_id=61999,
                                    ability_name="Raise Ally", timestamp_ms=68_000),),
    )

    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]

    assert [row.detail for row in card.timeline if row.kind == "heal"] == ["+9,000 from Naught"]
    assert card.came_back == "Resurrected by Naught with Raise Ally, 8.0 s after death."


def test_a_self_resurrection_is_worded_as_the_players_own() -> None:
    # No resurrect event: the log records a self-resurrection cast, and the
    # listed spell id is what tells that apart from a release and a run back.
    loaded = a_loaded_with((), ()).model_copy(update={
        "deaths": (a_death(1, 60_000).model_copy(update={"seconds_until_next_action": 25.0}),),
        "casts": (CastEvent(actor_id=1, ability_id=21169, ability_name="Reincarnation",
                            timestamp_ms=78_000),),
    })
    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES, NO_EXTERNALS,
                        SelfResurrections(ability_ids=(21169,)))[0]
    assert card.came_back == "Self-resurrected with Reincarnation, 18.0 s after death."
    assert card.came_back_badge is not None and card.came_back_badge.label == "measured"


def test_the_provenance_states_the_health_method_only_when_a_card_has_a_health_column() -> None:
    with_reading = a_loaded_with((a_death(1, 60_000),), (a_hit(1, 55_000, "x", 1),)).model_copy(
        update={"health_samples": (HealthSample(actor_id=1, timestamp_ms=1, hit_points=1,
                                                max_hit_points=1),)})
    report = build_report(with_reading, (), None, None, a_player(), None, FETCHED,
                          NO_DEFENSIVES, NO_CONSUMABLES)
    assert any("reconstructed" in line for line in report.provenance.methods)
    bare = build_report(a_loaded_with((), ()), (), None, None, a_player(), None, FETCHED,
                        NO_DEFENSIVES, NO_CONSUMABLES)
    assert bare.provenance.methods == ()


def test_death_findings_are_placed_under_deaths_not_observations() -> None:
    findings = (
        a_finding(
            "defensives.unused.emberkin",
            title="Emberkin died once with a defensive available",
        ),
        a_finding(
            "consumables.unused.Emberkin",
            title="Emberkin died once with no healing consumable on cooldown",
        ),
        a_finding(
            "consumables.never.Emberkin",
            title="Emberkin died once and used no health potion",
        ),
        a_finding("trash.pull.0", title="Pull 4 bought 0.0 forces per second"),
    )
    report = build_report(a_loaded(), findings, None, None, SUBJECT, None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES)
    assert [row.finding_id for row in report.death_rows] == [
        "defensives.unused.emberkin",
        "consumables.unused.Emberkin",
        "consumables.never.Emberkin",
    ]
    assert [row.finding_id for row in report.route_rows] == ["trash.pull.0"]
    assert report.observations == ()


def a_reading(at_ms: int, hit_points: int, maximum: int = 100_000) -> HealthSample:
    return HealthSample(
        actor_id=1, timestamp_ms=at_ms, hit_points=hit_points, max_hit_points=maximum
    )


def test_a_death_card_carries_a_health_curve_when_the_run_up_reported_health() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), (a_hit(1, 54_200, "Snowdrift", 82_410),))
    loaded = loaded.model_copy(update={"health_samples": (a_reading(50_000, 100_000),)})
    curve = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0].health_curve
    assert curve is not None
    assert [reading.percent for reading in curve.readings] == [100]


def test_a_death_card_carries_no_curve_when_nothing_reported_health() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), (a_hit(1, 54_200, "Snowdrift", 82_410),))
    assert build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0].health_curve is None


def test_the_curve_omits_the_anchor_reading_taken_before_the_run_up_opened() -> None:
    # The reading at 49 s anchors the arithmetic but belongs to a moment the
    # axis does not cover, so drawing it would put a dot outside its own scale.
    loaded = a_loaded_with((a_death(1, 60_000),), (a_hit(1, 54_200, "Snowdrift", 10_000),))
    loaded = loaded.model_copy(
        update={"health_samples": (a_reading(49_000, 100_000), a_reading(55_000, 40_000))}
    )
    curve = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0].health_curve
    assert curve is not None
    assert [reading.percent for reading in curve.readings] == [40]


def test_the_recap_table_is_labelled_with_how_many_events_it_holds() -> None:
    hits = (a_hit(1, 54_200, "Snowdrift", 82_410), a_hit(1, 55_000, "Snowdrift", 900))
    card = build_deaths(
        a_loaded_with((a_death(1, 60_000),), hits), NO_DEFENSIVES, NO_CONSUMABLES
    )[0]
    assert card.timeline_summary == "2 events"


def test_a_recap_table_holding_one_event_is_labelled_in_the_singular() -> None:
    hits = (a_hit(1, 54_200, "Snowdrift", 82_410),)
    card = build_deaths(
        a_loaded_with((a_death(1, 60_000),), hits), NO_DEFENSIVES, NO_CONSUMABLES
    )[0]
    assert card.timeline_summary == "1 event"


def test_a_recap_row_carries_the_ability_id_the_page_draws_an_icon_from() -> None:
    hits = (a_hit(1, 54_200, "Snowdrift", 82_410),)
    card = build_deaths(
        a_loaded_with((a_death(1, 60_000),), hits), NO_DEFENSIVES, NO_CONSUMABLES
    )[0]
    assert card.timeline[0].ability_id == hits[0].ability_id


def test_a_recap_row_for_an_ability_id_of_zero_carries_none_not_zero() -> None:
    # Zero is the log's sentinel for "named no ability", not an ability of its
    # own. The ability dictionary maps zero to "Unknown Ability" with a real
    # icon file, so a bare zero on the row would draw art beside a hit nobody
    # identified; None is the only value that says the row has no ability.
    hit = a_hit(1, 54_200, "Snowdrift", 82_410).model_copy(update={"ability_id": 0})
    card = build_deaths(
        a_loaded_with((a_death(1, 60_000),), (hit,)), NO_DEFENSIVES, NO_CONSUMABLES
    )[0]
    assert card.timeline[0].ability_id is None


def test_a_death_card_carries_the_killing_blows_ability_id() -> None:
    death = a_death(1, 60_000).model_copy(update={"killing_blow_id": 1297749})
    card = build_deaths(
        a_loaded_with((death,), ()), NO_DEFENSIVES, NO_CONSUMABLES
    )[0]
    assert card.killing_blow_id == 1297749


def test_a_killing_blow_id_of_zero_carries_none_not_zero() -> None:
    # A death built with no killing_blow_id override defaults to 0, the log's
    # sentinel for "named no ability". The ability dictionary maps zero to
    # "Unknown Ability" with a real icon file, so a bare zero on the card
    # would draw art beside a killing blow nobody identified.
    card = build_deaths(
        a_loaded_with((a_death(1, 60_000),), ()), NO_DEFENSIVES, NO_CONSUMABLES
    )[0]
    assert card.killing_blow_id is None


def test_every_recap_row_carries_the_x_of_its_own_moment_on_the_curve() -> None:
    # The marker is drawn where the curve puts that instant, not where the
    # browser guesses: both come from `curve_x`, so a row and its mark cannot
    # drift apart.
    loaded = a_loaded_with((a_death(1, 60_000),), (a_hit(1, 54_200, "Snowdrift", 82_410),))
    loaded = loaded.model_copy(update={"health_samples": (a_reading(50_000, 100_000),)})
    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.health_curve is not None
    row = next(row for row in card.timeline if row.kind == "hit")
    assert row.marker_x is not None
    assert card.health_curve.plot_x0 <= row.marker_x <= card.health_curve.plot_x1


def test_a_recap_row_on_a_card_with_no_curve_carries_no_marker() -> None:
    # A marker with nothing to sit on is a mark floating over a table.
    loaded = a_loaded_with((a_death(1, 60_000),), (a_hit(1, 54_200, "Snowdrift", 82_410),))
    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.health_curve is None
    assert all(row.marker_x is None for row in card.timeline)


def test_every_marker_id_on_the_page_is_unique_across_cards() -> None:
    # Two deaths in one run each produce a row zero. The script looks a marker
    # up by id, so a collision would light the wrong card's curve.
    deaths = (a_death(1, 60_000), a_death(1, 160_000))
    hits = (a_hit(1, 54_200, "First", 900), a_hit(1, 154_200, "Second", 900))
    cards = build_deaths(a_loaded_with(deaths, hits), NO_DEFENSIVES, NO_CONSUMABLES)
    ids = [row.marker_id for card in cards for row in card.timeline]
    assert len(ids) == len(set(ids))


# `BLOOD` and `owns_icebound`, defined above, already give a defensive that is
# both owned and pressed inside the run-up; these two fixtures add the aura
# table's own account of the same press, or its deliberate absence.


def a_loaded_run_with_a_pressed_defensive_and_its_band() -> LoadedRun:
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(
        update={"casts": owns_icebound(55_000)}
    )
    return loaded.model_copy(update={
        "auras": (
            PlayerAuras(actor_id=1, on_self=(
                Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=6_000, uses=1,
                     bands=(AuraBand(start_ms=53_000, end_ms=59_000),)),
            )),
        ),
    })


def a_loaded_run_with_a_pressed_defensive_and_no_auras() -> LoadedRun:
    return a_loaded_with((a_death(1, 60_000),), ()).model_copy(
        update={"casts": owns_icebound(55_000)}
    )


def test_a_pressed_defensive_row_carries_the_window_that_press_covered() -> None:
    # The band is measured: the aura table states when the buff was up. Only
    # the width the reader sees is arithmetic, and it is arithmetic done here.
    loaded = a_loaded_run_with_a_pressed_defensive_and_its_band()
    card = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0]
    row = next(row for row in card.timeline if row.kind == "cast")
    assert row.cover_x is not None
    assert row.cover_width is not None
    assert row.cover_width > 0


def test_a_press_with_no_band_in_the_log_draws_no_cover_window() -> None:
    # A report fetched without an aura table, or a press whose buff the table
    # never recorded, must draw nothing rather than a window the width of a
    # guess. Since 2026-09-12 it draws no row either: a press the card cannot
    # place a window for has nothing left to tell a reader.
    loaded = a_loaded_run_with_a_pressed_defensive_and_no_auras()
    card = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0]
    assert [row.ability for row in card.timeline] == []


def test_a_press_whose_cast_id_differs_from_its_auras_id_still_draws_a_cover_window() -> None:
    # The regression this fix is for: Alter Time casts as 108978 but the aura
    # table keys the buff at 342246 (`.claude/skills/wcl-api/SKILL.md`,
    # 2026-09-11). A lookup keyed only on the cast's own id would find nothing
    # here forever; the name has to bridge the two.
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(update={
        "casts": (
            CastEvent(actor_id=1, ability_id=108_978, ability_name="Alter Time",
                      timestamp_ms=55_000, pull_index=0),
        ),
        "auras": (
            PlayerAuras(actor_id=1, on_self=(
                Aura(ability_id=342_246, name="Alter Time", total_uptime_ms=6_000, uses=1,
                     bands=(AuraBand(start_ms=55_000, end_ms=61_000),)),
            )),
        ),
    })
    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]
    row = next(row for row in card.timeline if row.kind == "cast")
    assert row.cover_x is not None
    assert row.cover_width is not None
    assert row.cover_width > 0


def test_a_defensive_row_carries_a_measured_tooltip_when_its_aura_is_known() -> None:
    # Of the inside hit's 900, only 350 was mitigated -- the other 250 that
    # never reached health (900 - 300 - 350) was a shield's absorb, which the
    # rate must not count as this ability's own reduction.
    loaded = a_loaded_run_with_a_pressed_defensive_and_its_band().model_copy(update={
        "damage_taken": (
            a_hit(1, 54_000, "Frigid Roar", 900).model_copy(
                update={"health_damage": 300, "mitigated": 350, "absorbed": 250}
            ),
            a_hit(1, 70_000, "Frigid Roar", 800),
        ),
    })
    card = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0]
    row = card.availability[0].rows[0]
    assert row.tooltip is not None
    labels = {line.label: line.value for line in row.tooltip.lines}
    assert labels["Base cooldown"] == "180 s"
    assert labels["Presses"] == "1"
    assert labels["Cover"] == "6.0 s"
    assert labels["Arrived while it was up"] == "900"
    assert labels["Reached health"] == "300"
    assert labels["Mitigated inside / outside"] == "39% / 0%"
    assert "suggestive, not attributable" in row.tooltip.note


def test_a_defensive_row_with_no_aura_table_carries_no_tooltip() -> None:
    # No aura table was fetched for this player, so `resolve_aura` has nothing
    # to check the id or the name against.
    loaded = a_loaded_run_with_a_pressed_defensive_and_no_auras()
    card = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0]
    row = card.availability[0].rows[0]
    assert row.tooltip is None


ALTER_TIME_DEFENSIVE = Defensives(entries=(
    ("DeathKnight/Blood", (
        DefensiveAbility(ability_id=108_978, name="Alter Time", cooldown_seconds=60.0),
    )),
))


def test_an_availability_tooltip_uses_the_resolved_aura_id_not_the_cast_id() -> None:
    # Alter Time casts as 108978 but the aura table keys the buff at 342246
    # (`.claude/skills/wcl-api/SKILL.md`, 2026-09-11). A hit's own `buff_ids`
    # list carries buff ids, so comparing it against the cast id would silently
    # match nothing and every hit would look like it landed outside the window,
    # which is exactly the bug Task 11 found and fixed for the cover window.
    loaded = a_loaded_with((a_death(1, 60_000),), (
        a_hit(1, 55_500, "Frigid Roar", 900).model_copy(
            update={"health_damage": 300, "buff_ids": (342_246,)}
        ),
    )).model_copy(update={
        "casts": (
            CastEvent(actor_id=1, ability_id=108_978, ability_name="Alter Time",
                      timestamp_ms=55_000, pull_index=0),
        ),
        "auras": (
            PlayerAuras(actor_id=1, on_self=(
                Aura(ability_id=342_246, name="Alter Time", total_uptime_ms=6_000, uses=1,
                     bands=(AuraBand(start_ms=55_000, end_ms=61_000),)),
            )),
        ),
    })
    card = build_deaths(loaded, ALTER_TIME_DEFENSIVE, NO_CONSUMABLES)[0]
    row = card.availability[0].rows[0]
    assert row.tooltip is not None
    labels = {line.label: line.value for line in row.tooltip.lines}
    assert labels["Arrived while it was up"] == "900"
    assert labels["Reached health"] == "300"


def test_an_externals_row_carries_a_tooltip_from_the_dying_players_own_aura_table() -> None:
    # An external's buff lands on the dying player regardless of who cast it,
    # so the tooltip reads the dying player's own aura table and their own
    # hits, not the caster's.
    dude, tree = a_player(), Player(actor_id=2, name="Leafy", class_name="Druid",
                                    spec="Restoration", item_level=680)
    loaded = LoadedRun(
        run=a_run(players=(dude, tree), pulls=(a_pull(0, 0, 120_000),)),
        deaths=(a_death(1, 60_000),),
        casts=(CastEvent(actor_id=2, ability_id=102342, ability_name="Ironbark",
                         timestamp_ms=55_000, target_id=1),),
        auras=(
            PlayerAuras(actor_id=1, on_self=(
                Aura(ability_id=102342, name="Ironbark", total_uptime_ms=8_000, uses=1,
                     bands=(AuraBand(start_ms=55_000, end_ms=63_000),)),
            )),
        ),
    )
    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES,
                        externals=Externals(entries=(("Druid/Restoration", (IRONBARK,)),)))[0]
    mates = card.availability[2]
    assert mates.rows[0].tooltip is not None
    labels = {line.label: line.value for line in mates.rows[0].tooltip.lines}
    assert labels["Base cooldown"] == "90 s"
    assert labels["Presses"] == "1"


def test_an_externals_tooltip_counts_only_presses_that_could_have_been_for_this_player() -> None:
    # F5: `state_of` already scopes an external's PRESSED state to a cast on
    # the dying player or with no target at all -- a cast on someone else was
    # a use, not a save -- and the tooltip's own press count must agree with
    # the row's own detail rather than reading every cast on any target. A
    # healer who shielded a different ally must not have that cast counted as
    # a press "for" the player who died.
    dude = a_player()
    caster = Player(actor_id=2, name="Emberkin", class_name="Druid", spec="Restoration",
                    item_level=680)
    bystander = Player(actor_id=3, name="Bríala", class_name="Priest", spec="Discipline",
                       item_level=670)
    loaded = LoadedRun(
        run=a_run(players=(dude, caster, bystander), pulls=(a_pull(0, 0, 120_000),)),
        deaths=(a_death(1, 60_000),),
        casts=(
            CastEvent(actor_id=2, ability_id=102342, ability_name="Ironbark",
                     timestamp_ms=55_000, target_id=1),
            # Same ability, same caster, earlier in the run, aimed at someone
            # else entirely -- never a save for the player who died at 60s.
            CastEvent(actor_id=2, ability_id=102342, ability_name="Ironbark",
                     timestamp_ms=20_000, target_id=3),
        ),
        auras=(
            PlayerAuras(actor_id=1, on_self=(
                Aura(ability_id=102342, name="Ironbark", total_uptime_ms=8_000, uses=1,
                     bands=(AuraBand(start_ms=55_000, end_ms=63_000),)),
            )),
        ),
    )
    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES,
                        externals=Externals(entries=(("Druid/Restoration", (IRONBARK,)),)))[0]
    mates = card.availability[2]
    assert mates.rows[0].tooltip is not None
    labels = {line.label: line.value for line in mates.rows[0].tooltip.lines}
    assert labels["Presses"] == "1"


def test_a_consumable_row_carries_no_tooltip() -> None:
    # A consumable category names a cooldown group, not one ability id, so
    # there is no aura to resolve it against.
    loaded = a_loaded_with((a_death(1, LATE_ENOUGH_MS),), ()).model_copy(update={
        "casts": (CastEvent(actor_id=1, ability_id=1234768, ability_name="Health Potion",
                            timestamp_ms=1_000, pull_index=0),),
    })
    drinks = build_deaths(loaded, NO_DEFENSIVES, POTIONS)[0].availability[1]
    assert all(row.tooltip is None for row in drinks.rows)


def test_a_hit_row_carries_a_tooltip_reporting_its_four_figures() -> None:
    hit = a_hit(1, 54_200, "Snowdrift", 82_410).model_copy(
        update={"amount": 145_434, "mitigated": 15_609}
    )
    card = build_deaths(
        a_loaded_with((a_death(1, 60_000),), (hit,)), NO_DEFENSIVES, NO_CONSUMABLES
    )[0]
    tooltip = card.timeline[0].tooltip
    assert tooltip is not None
    labels = {line.label: line.value for line in tooltip.lines}
    assert labels["Struck for"] == "145,434"
    assert labels["Mitigated"] == "15,609"
    assert labels["Reached health"] == "82,410"
    assert "does not attribute" in tooltip.note


def test_a_heal_row_carries_a_tooltip_naming_its_caster() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(update={
        "healing": (HealingEvent(actor_id=1, source_id=1, ability_id=7,
                                 ability_name="Death Strike", amount=9_100,
                                 timestamp_ms=55_000),),
    })
    tooltip = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0].timeline[0].tooltip
    assert tooltip is not None
    labels = {line.label: line.value for line in tooltip.lines}
    assert labels["Healed for"] == "9,100"
    assert labels["From"] == "Stonewake"
    assert "no overheal" in tooltip.note


def test_an_absorb_row_carries_a_tooltip_naming_the_shields_caster() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(update={
        "healing": (HealingEvent(actor_id=1, source_id=2, ability_id=17,
                                 ability_name="Power Word: Shield", amount=12_000,
                                 timestamp_ms=55_000, absorbed=True),),
    })
    tooltip = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0].timeline[0].tooltip
    assert tooltip is not None
    labels = {line.label: line.value for line in tooltip.lines}
    assert labels["Soaked"] == "12,000"


def test_every_cast_row_a_card_draws_carries_a_panel() -> None:
    # Was `test_a_cast_row_carries_no_tooltip`, which pinned that a bandless
    # press offered no panel. The card stopped drawing bandless presses on
    # 2026-09-12, so the fact worth holding is the complement: a cast row
    # always explains itself, because the band that earned it its row is the
    # same band its panel measures. The first assertion keeps the second from
    # passing over an empty list.
    loaded = a_loaded_run_with_a_pressed_defensive_and_its_band().model_copy(update={
        "casts": owns_icebound(55_000) + (
            CastEvent(actor_id=1, ability_id=116, ability_name="Frostbolt",
                      timestamp_ms=56_000, pull_index=0),
        ),
    })
    casts = [row for row in build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0].timeline
             if row.kind == "cast"]
    assert casts != []
    assert all(row.tooltip is not None for row in casts)


def test_a_press_row_carries_a_tooltip_measuring_its_own_cover_window() -> None:
    # Spec 4.3's fifth row. The band runs 53s to 59s against a death at 60s,
    # so both figures are subtractions on the same band the row draws.
    loaded = a_loaded_run_with_a_pressed_defensive_and_its_band()
    card = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0]
    row = next(row for row in card.timeline if row.kind == "cast")
    assert row.tooltip is not None
    labels = {line.label: line.value for line in row.tooltip.lines}
    assert labels["Cover"] == "6.0 s"
    assert labels["Ran out"] == "1.0 s before the death"


def test_a_press_tooltip_counts_only_the_damage_that_arrived_inside_its_band() -> None:
    # 51s falls in the run-up but before the band opens at 53s, and it is the
    # larger of the two, so a tooltip summing the whole run-up could not
    # report the inside figure by coincidence.
    loaded = a_loaded_run_with_a_pressed_defensive_and_its_band().model_copy(update={
        "damage_taken": (
            a_hit(1, 51_000, "Snowdrift", 82_410),
            a_hit(1, 54_000, "Frigid Roar", 9_001),
        ),
    })
    card = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0]
    row = next(row for row in card.timeline if row.kind == "cast")
    assert row.tooltip is not None
    labels = {line.label: line.value for line in row.tooltip.lines}
    assert labels["Arrived while it was up"] == "9,001"
    assert labels["Reached health"] == "9,001"


def test_a_press_with_no_band_goes_while_the_hits_around_it_stay() -> None:
    # The panel explains the rectangle beside it, so a press that draws no
    # rectangle has no row to hang one on. Anchored on the hit rows in the
    # same card, which the filter must not touch: only casts are judged on
    # whether the card can draw them.
    loaded = a_loaded_run_with_a_pressed_defensive_and_no_auras().model_copy(update={
        "damage_taken": (a_hit(1, 54_000, "Frigid Roar", 9_001),),
    })
    card = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0]
    assert [row.kind for row in card.timeline] == ["hit"]
    assert all(row.tooltip is not None for row in card.timeline if row.kind == "hit")


def test_an_ordinary_cast_that_leaves_no_self_buff_carries_no_tooltip() -> None:
    # `recap_timeline` emits a cast row for every spell the dying player cast,
    # not only defensives. A damaging cast resolves no aura, so it draws no
    # cover window and says nothing about one.
    loaded = a_loaded_run_with_a_pressed_defensive_and_its_band().model_copy(update={
        "casts": owns_icebound(55_000) + (
            CastEvent(actor_id=1, ability_id=116, ability_name="Frostbolt",
                      timestamp_ms=56_000, pull_index=0),
        ),
    })
    card = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0]
    rows = {row.ability: row for row in card.timeline if row.kind == "cast"}
    assert "Frostbolt" not in rows
    assert rows["Icebound Fortitude"].tooltip is not None


def a_card_with_casts(*casts: tuple[str, int], auras: PlayerAuras | None) -> DeathCard:
    """A card whose run-up holds nothing but the dying player's own presses."""
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(update={
        "casts": tuple(
            CastEvent(actor_id=1, ability_id=ability_id, ability_name=name,
                      timestamp_ms=55_000, pull_index=0)
            for name, ability_id in casts
        ),
        "auras": () if auras is None else (auras,),
    })
    return build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]


def auras_covering(name: str) -> PlayerAuras:
    """An aura table whose one band holds the press `a_card_with_casts` places.

    Keyed on the name rather than on the cast's own id, the way a real table
    keys Alter Time: `resolve_aura` tries the id first and falls back to the
    name, so this fixture exercises the fallback.
    """
    return PlayerAuras(actor_id=1, on_self=(
        Aura(ability_id=999_999, name=name, total_uptime_ms=6_000, uses=1,
             bands=(AuraBand(start_ms=53_000, end_ms=59_000),)),
    ))


def a_card_with_heal(amount: int) -> DeathCard:
    """A card whose run-up holds one heal, landed on the dying player by a teammate."""
    loaded = LoadedRun(
        run=a_run(players=(a_player(), a_player(actor_id=2, name="Emberkin")),
                  pulls=(a_pull(0, 0, 120_000),)),
        deaths=(a_death(1, 60_000),),
        healing=(HealingEvent(actor_id=1, source_id=2, ability_id=7, ability_name="Holy Light",
                              amount=amount, timestamp_ms=55_000),),
    )
    return build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]


def test_a_cast_with_no_resolvable_buff_is_not_a_row() -> None:
    """An offensive cast says nothing a death card can draw, so it is not drawn."""
    card = a_card_with_casts(("Rampage", 845_000), auras=None)
    assert [row.ability for row in card.timeline] == []


def test_a_cast_whose_buff_the_card_can_draw_stays() -> None:
    """A press with a cover band has a window and figures worth a row."""
    card = a_card_with_casts(("Whirlwind", 845_000), auras=auras_covering("Whirlwind"))
    assert [row.ability for row in card.timeline] == ["Whirlwind"]


def test_a_heal_that_landed_for_nothing_still_gets_a_row() -> None:
    """Overheal is a fact about who was healing; only casts are filtered."""
    card = a_card_with_heal(amount=0)
    assert [row.detail for row in card.timeline] == ["+0 from Emberkin"]
