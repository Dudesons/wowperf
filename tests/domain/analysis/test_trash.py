# ABOUTME: Behaviour tests for enemy-forces efficiency and the pulls that bought least.
# ABOUTME: The percentage is measured; turning it into seconds is derived and labelled so.

from wowperf.domain.analysis.trash import analyse_trash
from wowperf.domain.events import EnemyDeath
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run


def a_run(reached: int, required: int = 100) -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=30_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
        Pull(index=1, pull_id=2, name="Trash", encounter_id=0, start_ms=40_000,
             end_ms=100_000, killed=True, x=30, y=40,
             enemies=(EnemyNpc(actor_id=2, game_id=200),)),
        Pull(index=2, pull_id=3, name="Boss", encounter_id=99001, start_ms=110_000,
             end_ms=140_000, killed=True, x=50, y=60,
             enemies=(EnemyNpc(actor_id=3, game_id=300),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=reached, count_required=required, npc_counts=(),
        players=(Player(actor_id=11, name="Uglymage", class_name="Mage", spec="Arcane",
                        item_level=318),),
        pulls=pulls,
    )


def kill(pull_index: int, forces: int, at: int) -> EnemyDeath:
    return EnemyDeath(game_id=100 + pull_index, actor_id=pull_index, timestamp_ms=at,
                      forces=forces, pull_index=pull_index)


def test_reaching_exactly_the_requirement_reports_no_overage() -> None:
    findings = analyse_trash(a_run(reached=100), (kill(0, 100, 10_000),))
    assert [f.id for f in findings if f.id == "trash.overage"] == []


def test_a_large_overage_is_reported_as_wasted_trash_time() -> None:
    findings = analyse_trash(
        a_run(reached=112), (kill(0, 40, 10_000), kill(1, 72, 50_000))
    )
    overage = next(f for f in findings if f.id == "trash.overage")
    assert overage.confidence is Confidence.DERIVED
    assert overage.seconds_lost is not None
    # 12% over, 90s of trash pull time -> about 9.6s bought nothing.
    assert 9.0 < overage.seconds_lost < 10.5
    assert any("112" in item for item in overage.evidence)


def test_an_overage_under_the_floor_is_not_reported() -> None:
    findings = analyse_trash(a_run(reached=101), (kill(0, 101, 10_000),))
    assert [f.id for f in findings if f.id == "trash.overage"] == []


def test_the_least_efficient_trash_pull_is_named() -> None:
    findings = analyse_trash(
        a_run(reached=112), (kill(0, 90, 10_000), kill(1, 22, 50_000))
    )
    # Pull 0 bought 90 forces in 30s; pull 1 bought 22 in 60s. Pull 1 is worse.
    worst = next(f for f in findings if f.id.startswith("trash.pull."))
    assert worst.pull_index == 1


def test_boss_pulls_are_not_judged_on_forces() -> None:
    findings = analyse_trash(a_run(reached=112), (kill(0, 112, 10_000),))
    assert all(f.pull_index != 2 for f in findings if f.pull_index is not None)


def test_a_run_with_no_enemy_deaths_still_reports_the_count() -> None:
    findings = analyse_trash(a_run(reached=112), ())
    assert any(f.id == "trash.overage" for f in findings)
