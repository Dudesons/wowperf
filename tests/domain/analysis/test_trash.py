# ABOUTME: Behaviour tests for enemy-forces efficiency and the pulls that bought least.
# ABOUTME: The percentage is measured; turning it into seconds is derived and labelled so.

from wowperf.domain.analysis.trash import MAX_PULLS_REPORTED, analyse_trash, forces_by_pull
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
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=reached, count_required=required, npc_counts=(),
        players=(Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane",
                        item_level=318),),
        pulls=pulls,
    )


def a_pull(
    index: int, start_ms: int, end_ms: int, name: str = "Pack"
) -> Pull:
    return Pull(
        index=index, pull_id=index + 1, name=name, encounter_id=0,
        start_ms=start_ms, end_ms=end_ms, killed=True, x=index, y=index,
        enemies=(EnemyNpc(actor_id=index, game_id=100 + index),)
    )


def kill(pull_index: int, forces: int, at: int) -> EnemyDeath:
    return EnemyDeath(game_id=100 + pull_index, actor_id=pull_index, timestamp_ms=at,
                      forces=forces, pull_index=pull_index)


def a_run_with_pulls(pulls: tuple[Pull, ...], reached: int, required: int = 100) -> Run:
    """Like a_run, but with a caller-supplied set of pulls instead of the fixed three."""
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=reached, count_required=required, npc_counts=(),
        players=(Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane",
                        item_level=318),),
        pulls=pulls,
    )


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


def test_a_shortfall_reports_no_overage_and_no_pull_ranking() -> None:
    # Fell short of the requirement: nothing was overkilled, so there is nothing
    # to explain and no "worst pack" callout should appear either.
    findings = analyse_trash(a_run(reached=80), (kill(0, 50, 10_000), kill(1, 30, 50_000)))
    assert findings == []


def test_a_run_with_no_trash_pulls_reports_no_pull_ranking() -> None:
    # Only a boss pull exists, but the requirement was still overkilled (forces
    # can come from rares/bosses too). There is nothing to rank per-pull.
    pulls = (
        Pull(index=0, pull_id=1, name="Boss", encounter_id=99001, start_ms=0, end_ms=30_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    findings = analyse_trash(a_run_with_pulls(pulls, reached=112), ())
    assert any(f.id == "trash.overage" for f in findings)
    assert [f for f in findings if f.id.startswith("trash.pull.")] == []


def test_a_zero_duration_pull_is_excluded_from_the_ranking() -> None:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=0,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
        Pull(index=1, pull_id=2, name="Trash", encounter_id=0, start_ms=10_000,
             end_ms=40_000, killed=True, x=30, y=40,
             enemies=(EnemyNpc(actor_id=2, game_id=200),)),
    )
    findings = analyse_trash(
        a_run_with_pulls(pulls, reached=112),
        (kill(0, 5, 1_000), kill(1, 30, 20_000)),
    )
    pull_findings = [f for f in findings if f.id.startswith("trash.pull.")]
    assert all(f.pull_index != 0 for f in pull_findings)
    assert any(f.pull_index == 1 for f in pull_findings)


def test_count_required_zero_or_negative_reports_nothing() -> None:
    assert analyse_trash(a_run(reached=112, required=0), (kill(0, 112, 10_000),)) == []
    assert analyse_trash(a_run(reached=112, required=-5), (kill(0, 112, 10_000),)) == []


def test_max_pulls_reported_caps_the_ranking() -> None:
    pulls = tuple(
        Pull(index=i, pull_id=i + 1, name="Trash", encounter_id=0, start_ms=i * 10_000,
             end_ms=i * 10_000 + 10_000, killed=True, x=i, y=i,
             enemies=(EnemyNpc(actor_id=i, game_id=100 + i),))
        for i in range(MAX_PULLS_REPORTED + 2)
    )
    deaths = tuple(kill(i, forces=i + 1, at=i * 10_000 + 1_000) for i in range(len(pulls)))
    findings = analyse_trash(a_run_with_pulls(pulls, reached=112), deaths)
    pull_findings = [f for f in findings if f.id.startswith("trash.pull.")]
    assert len(pull_findings) == MAX_PULLS_REPORTED


def test_a_slow_pulls_evidence_names_the_pack() -> None:
    run = a_run_with_pulls((a_pull(0, 0, 300_000, name="Shale Prowlers"),), reached=112)
    findings = analyse_trash(run, (kill(0, 112, 10_000),))
    slow = [f for f in findings if f.id.startswith("trash.pull.")]
    assert slow
    assert slow[0].evidence[0] == "Shale Prowlers"


def test_no_finding_prints_a_map_position() -> None:
    findings = analyse_trash(
        a_run(reached=112), (kill(0, 40, 10_000), kill(1, 72, 50_000))
    )
    for finding in findings:
        for line in finding.evidence:
            assert "map position" not in line, finding.id


def test_forces_by_pull_sums_every_death_inside_a_pull() -> None:
    deaths = (
        EnemyDeath(game_id=100, actor_id=1, timestamp_ms=1_000, forces=6, pull_index=0),
        EnemyDeath(game_id=100, actor_id=2, timestamp_ms=2_000, forces=6, pull_index=0),
        EnemyDeath(game_id=200, actor_id=3, timestamp_ms=9_000, forces=4, pull_index=1),
        EnemyDeath(game_id=300, actor_id=4, timestamp_ms=9_500, forces=4, pull_index=None),
    )
    assert forces_by_pull(deaths) == {0: 12, 1: 4}


def test_a_sub_second_pull_is_not_ranked_on_the_forces_it_bought() -> None:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=500,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
        a_pull(1, 10_000, 40_000),
    )
    findings = analyse_trash(a_run_with_pulls(pulls, reached=112), (kill(1, 30, 20_000),))
    pull_findings = [f for f in findings if f.id.startswith("trash.pull.")]
    assert all(f.pull_index != 0 for f in pull_findings)
    assert any(f.pull_index == 1 for f in pull_findings)


def test_a_pull_with_no_recorded_enemies_is_not_ranked_on_the_forces_it_bought() -> None:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=20_000,
             killed=True, x=10, y=20, enemies=()),
        a_pull(1, 30_000, 60_000),
    )
    findings = analyse_trash(a_run_with_pulls(pulls, reached=112), (kill(1, 30, 40_000),))
    pull_findings = [f for f in findings if f.id.startswith("trash.pull.")]
    assert all(f.pull_index != 0 for f in pull_findings)
    assert any(f.pull_index == 1 for f in pull_findings)


def test_a_pack_that_awarded_no_forces_is_still_ranked() -> None:
    """The pack floor drops segmentation artefacts, not packs that paid nothing.

    A real pack of mobs awarding no enemy forces is exactly what this analyser
    exists to name, so filtering the ranking on the rate rather than on the
    pull's shape would suppress its strongest finding.
    """
    pulls = (a_pull(0, 0, 20_000), a_pull(1, 30_000, 60_000))
    findings = analyse_trash(a_run_with_pulls(pulls, reached=112), (kill(1, 30, 40_000),))
    named = [f for f in findings if f.pull_index == 0 and f.id.startswith("trash.pull.")]
    assert len(named) == 1
    assert named[0].title == "Pull 0 bought 0.0 forces per second"
    assert named[0].detail == "0 forces over 20s."


def test_a_pack_one_second_long_is_still_ranked() -> None:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=1_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
        a_pull(1, 10_000, 40_000),
    )
    findings = analyse_trash(
        a_run_with_pulls(pulls, reached=112), (kill(0, 1, 500), kill(1, 30, 20_000))
    )
    pull_findings = [f for f in findings if f.id.startswith("trash.pull.")]
    assert any(f.pull_index == 0 for f in pull_findings)
