# ABOUTME: The last ten seconds of a death as one ordered timeline, with health after each event
# ABOUTME: reconstructed between the player's own readings. Every rule of spec §4.1 and §4.2.

from tests.domain.report.test_build_frame import a_pull, a_run
from wowperf.domain.analysis.recap import (
    ABSORB,
    CAST,
    HEAL,
    HIT,
    RecapEvent,
    recap_timeline,
    with_health,
)
from wowperf.domain.events import (
    CastEvent,
    DamageTakenEvent,
    Death,
    HealingEvent,
    HealthSample,
)
from wowperf.domain.model import LoadedRun, Player

DEATH_MS = 60_000
DUDE = Player(actor_id=1, name="Dudesons", class_name="DeathKnight", spec="Blood", item_level=680)


def a_death(at_ms: int = DEATH_MS, actor_id: int = 1) -> Death:
    return Death(player_name="Dudesons", actor_id=actor_id, timestamp_ms=at_ms,
                 killing_blow="Frigid Roar", pull_index=0)


def a_hit(at_ms: int, health_damage: int, absorbed: int = 0, actor_id: int = 1,
          ability: str = "Snowdrift") -> DamageTakenEvent:
    return DamageTakenEvent(actor_id=actor_id, ability_id=1, ability_name=ability,
                            amount=health_damage + absorbed, timestamp_ms=at_ms,
                            health_damage=health_damage, absorbed=absorbed)


def a_heal(at_ms: int, amount: int, absorbed: bool = False, actor_id: int = 1,
           ability: str = "Rejuvenation", source_id: int = 2) -> HealingEvent:
    return HealingEvent(actor_id=actor_id, source_id=source_id, ability_id=7,
                        ability_name=ability, amount=amount, timestamp_ms=at_ms,
                        absorbed=absorbed)


def a_cast(at_ms: int, actor_id: int = 1, ability: str = "Death Strike") -> CastEvent:
    return CastEvent(actor_id=actor_id, ability_id=9, ability_name=ability, timestamp_ms=at_ms)


def a_sample(
    at_ms: int, hit_points: int, maximum: int = 100_000, actor_id: int = 1
) -> HealthSample:
    return HealthSample(actor_id=actor_id, timestamp_ms=at_ms, hit_points=hit_points,
                        max_hit_points=maximum)


def loaded(**streams: object) -> LoadedRun:
    return LoadedRun(run=a_run(players=(DUDE,), pulls=(a_pull(0, 0, 120_000),)), **streams)  # type: ignore[arg-type]


def test_the_timeline_holds_hits_absorbs_heals_and_own_casts_inside_the_window_only() -> None:
    run = loaded(
        damage_taken=(a_hit(49_000, 10), a_hit(50_000, 20), a_hit(60_000, 30)),
        healing=(a_heal(52_000, 5), a_heal(53_000, 8, absorbed=True, ability="Blood Shield"),
                 a_heal(61_000, 9)),
        casts=(a_cast(51_000), a_cast(58_000, actor_id=3)),
    )
    kinds = [(e.kind, e.timestamp_ms) for e in recap_timeline(run, a_death())]
    assert kinds == [(HIT, 50_000), (CAST, 51_000), (HEAL, 52_000), (ABSORB, 53_000),
                     (HIT, 60_000)]


def test_events_sharing_a_timestamp_read_hit_absorb_heal_then_cast() -> None:
    run = loaded(
        damage_taken=(a_hit(55_000, 10),),
        healing=(a_heal(55_000, 5), a_heal(55_000, 3, absorbed=True)),
        casts=(a_cast(55_000),),
    )
    assert [e.kind for e in recap_timeline(run, a_death())] == [HIT, ABSORB, HEAL, CAST]


def test_a_hit_carries_its_health_damage_and_absorbed_share_and_a_heal_its_source() -> None:
    run = loaded(damage_taken=(a_hit(55_000, 1_000, absorbed=400),), healing=(a_heal(56_000, 5),))
    hit, heal = recap_timeline(run, a_death())
    assert (hit.amount, hit.absorbed, heal.amount, heal.source_id) == (1_000, 400, 5, 2)


def test_another_players_events_do_not_enter_the_timeline() -> None:
    run = loaded(
        damage_taken=(a_hit(55_000, 10, actor_id=3),),
        healing=(a_heal(56_000, 5, actor_id=3),),
    )
    assert recap_timeline(run, a_death()) == ()


# --- health -------------------------------------------------------------------


def test_the_anchor_is_the_latest_reading_at_or_before_the_window_opens() -> None:
    events = (RecapEvent(kind=HIT, timestamp_ms=55_000, ability_name="x", amount=10_000),)
    samples = (a_sample(40_000, 90_000), a_sample(50_000, 80_000), a_sample(70_000, 1))
    assert with_health(events, samples, 50_000)[0].health_percent == 70


def test_without_any_reading_before_the_first_event_the_rows_carry_no_health() -> None:
    events = (
        RecapEvent(kind=HIT, timestamp_ms=52_000, ability_name="x", amount=10_000),
        RecapEvent(kind=CAST, timestamp_ms=55_000, ability_name="y"),
        RecapEvent(kind=HIT, timestamp_ms=57_000, ability_name="x", amount=10_000),
    )
    percents = [e.health_percent for e in with_health(events, (a_sample(55_000, 50_000),), 50_000)]
    assert percents == [None, 50, 40]


def test_a_heal_is_capped_at_the_maximum_and_an_absorb_changes_nothing() -> None:
    events = (
        RecapEvent(kind=HEAL, timestamp_ms=51_000, ability_name="h", amount=50_000),
        RecapEvent(kind=ABSORB, timestamp_ms=52_000, ability_name="s", amount=30_000),
    )
    percents = [e.health_percent for e in with_health(events, (a_sample(50_000, 90_000),), 50_000)]
    assert percents == [100, 100]


def test_a_cast_with_no_reading_beside_it_leaves_the_running_health_alone() -> None:
    # A cast is on the timeline for what the player was doing, not for what it
    # cost them. Only a reading of their own moves the value, and this cast
    # carries none: every other test pairs its cast with a sample.
    events = (
        RecapEvent(kind=HIT, timestamp_ms=51_000, ability_name="x", amount=10_000),
        RecapEvent(kind=CAST, timestamp_ms=53_000, ability_name="y"),
        RecapEvent(kind=HIT, timestamp_ms=55_000, ability_name="x", amount=10_000),
    )
    samples = (a_sample(50_000, 100_000),)

    percents = [event.health_percent for event in with_health(events, samples, 50_000)]

    assert percents == [90, 90, 80]


def test_a_reading_inside_the_window_replaces_the_running_value() -> None:
    # The arithmetic drifted (a missed event), the reading wins, silently.
    events = (
        RecapEvent(kind=HIT, timestamp_ms=51_000, ability_name="x", amount=10_000),
        RecapEvent(kind=CAST, timestamp_ms=53_000, ability_name="y"),
        RecapEvent(kind=HIT, timestamp_ms=54_000, ability_name="x", amount=10_000),
    )
    samples = (a_sample(50_000, 100_000), a_sample(53_000, 60_000))
    percents = [e.health_percent for e in with_health(events, samples, 50_000)]
    assert percents == [90, 60, 50]


def test_the_killing_blow_clamps_at_zero_rather_than_going_negative() -> None:
    events = (RecapEvent(kind=HIT, timestamp_ms=60_000, ability_name="x", amount=500_000),)
    assert with_health(events, (a_sample(50_000, 20_000),), 50_000)[0].health_percent == 0


def test_the_percentage_uses_the_latest_sampled_maximum() -> None:
    events = (RecapEvent(kind=HIT, timestamp_ms=55_000, ability_name="x", amount=0),)
    samples = (a_sample(50_000, 60_000, maximum=120_000),)
    assert with_health(events, samples, 50_000)[0].health_percent == 50


def test_recap_timeline_reads_only_the_dying_players_samples() -> None:
    run = loaded(
        damage_taken=(a_hit(55_000, 10_000),),
        health_samples=(a_sample(50_000, 50_000, actor_id=3), a_sample(50_000, 100_000)),
    )
    assert recap_timeline(run, a_death())[0].health_percent == 90
