# ABOUTME: Behaviour tests for per-player activity, interrupts and damage against the median.
# ABOUTME: Activity counts casts inside pulls only, so route downtime is not blamed on people.

from wowperf.domain.analysis.players import analyse_players, summarise_players
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, InterruptEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run

NAMES = ("Alpha", "Bravo", "Charlie", "Delta", "Echo")


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=100_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=100, count_required=100, npc_counts=(),
        players=tuple(
            Player(actor_id=index, name=name, class_name="Mage", spec="Arcane",
                   item_level=318)
            for index, name in enumerate(NAMES)
        ),
        pulls=pulls,
    )


def cast(actor_id: int, at: int, pull_index: int | None = 0) -> CastEvent:
    return CastEvent(actor_id=actor_id, ability_id=1, ability_name="Frostbolt",
                     timestamp_ms=at, pull_index=pull_index)


def hit(actor_id: int, amount: int, ability: int = 500) -> DamageTakenEvent:
    return DamageTakenEvent(actor_id=actor_id, ability_id=ability,
                            ability_name="Molten Scar", amount=amount,
                            timestamp_ms=1_000, pull_index=0)


def test_casts_outside_every_pull_do_not_count_towards_activity() -> None:
    summaries = summarise_players(
        a_run(), (cast(0, 1_000), cast(0, 2_000, pull_index=None)), (), ()
    )
    alpha = next(s for s in summaries if s.name == "Alpha")
    assert alpha.casts_in_pulls == 1


def test_interrupts_and_deaths_are_counted_per_player() -> None:
    summaries = summarise_players(
        a_run(),
        (),
        (Death(player_name="Bravo", actor_id=1, timestamp_ms=5_000,
               killing_blow="Molten Scar"),),
        (InterruptEvent(player_name="Bravo", actor_id=1, interrupted_ability_id=9,
                        target_id=99, target_instance=0, timestamp_ms=6_000),),
    )
    bravo = next(s for s in summaries if s.name == "Bravo")
    assert (bravo.interrupts, bravo.deaths) == (1, 1)


def test_every_player_gets_a_summary_even_with_no_events() -> None:
    assert len(summarise_players(a_run(), (), (), ())) == 5


def test_taking_far_more_than_the_median_of_one_ability_is_a_finding() -> None:
    damage = (
        hit(0, 100_000), hit(1, 10_000), hit(2, 10_000), hit(3, 10_000), hit(4, 10_000),
    )
    findings = analyse_players(a_run(), (), (), (), damage)
    outlier = next(f for f in findings if f.id.startswith("players.damage."))
    assert "Alpha" in outlier.title
    assert outlier.confidence is Confidence.DERIVED
    assert outlier.seconds_lost is None


def test_the_median_definition_is_stated_in_the_evidence() -> None:
    damage = (
        hit(0, 100_000), hit(1, 10_000), hit(2, 10_000), hit(3, 10_000), hit(4, 10_000),
    )
    findings = analyse_players(a_run(), (), (), (), damage)
    outlier = next(f for f in findings if f.id.startswith("players.damage."))
    assert any("median" in item and "took at least one" in item for item in outlier.evidence)


def test_too_few_players_took_an_ability_for_a_median_to_mean_anything() -> None:
    findings = analyse_players(a_run(), (), (), (), (hit(0, 100_000), hit(1, 1_000)))
    assert [f for f in findings if f.id.startswith("players.damage.")] == []


def test_damage_within_the_normal_range_is_not_flagged() -> None:
    damage = (
        hit(0, 12_000), hit(1, 10_000), hit(2, 10_000), hit(3, 10_000), hit(4, 11_000),
    )
    findings = analyse_players(a_run(), (), (), (), damage)
    assert [f for f in findings if f.id.startswith("players.damage.")] == []


def test_low_activity_inside_pulls_is_reported() -> None:
    # One cast in a 100s pull is far below the activity floor.
    findings = analyse_players(a_run(), (cast(0, 1_000),), (), (), ())
    assert any(f.id == "players.activity.Alpha" for f in findings)


def test_no_finding_claims_a_damage_ranking() -> None:
    damage = (hit(0, 100_000), hit(1, 10_000), hit(2, 10_000), hit(3, 10_000))
    findings = analyse_players(a_run(), (cast(0, 1_000),), (), (), damage)
    joined = " ".join(f"{f.title} {f.detail}" for f in findings).lower()
    for forbidden in ("dps", "damage done", "parse", "percentile"):
        assert forbidden not in joined
