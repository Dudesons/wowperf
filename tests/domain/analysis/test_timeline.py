# ABOUTME: Behaviour tests for splitting a keystone time into pulls, deaths and travel.
# ABOUTME: The residual is the number a reader acts on, so its arithmetic is pinned exactly.

from wowperf.domain.analysis.timeline import MAX_GAPS_REPORTED, decompose_time, gaps_between_pulls
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run
from wowperf.domain.season import SeasonData

SEASON = SeasonData(
    death_penalty_seconds=5.0,
    death_penalty_seconds_high_key=15.0,
    high_key_threshold=12,
)


def a_run(keystone_level: int = 16) -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=60_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
        Pull(index=1, pull_id=2, name="Trash", encounter_id=0, start_ms=100_000,
             end_ms=160_000, killed=True, x=30, y=40,
             enemies=(EnemyNpc(actor_id=2, game_id=200),)),
        Pull(index=2, pull_id=3, name="Boss", encounter_id=99001, start_ms=170_000,
             end_ms=230_000, killed=True, x=50, y=60,
             enemies=(EnemyNpc(actor_id=3, game_id=300),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=keystone_level, affix_ids=(), keystone_time_ms=300_000,
        keystone_bonus=1, count_reached=744, count_required=729, npc_counts=(),
        players=(Player(actor_id=11, name="Uglymage", class_name="Mage", spec="Arcane",
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


def a_death(timestamp_ms: int) -> Death:
    return Death(player_name="Uglymage", actor_id=11, timestamp_ms=timestamp_ms,
                 killing_blow="Molten Scar")


def test_gaps_are_the_silence_between_consecutive_pulls() -> None:
    gaps = gaps_between_pulls(a_run())
    assert [(gap.after_pull_index, gap.seconds) for gap in gaps] == [(0, 40.0), (1, 10.0)]


def test_a_gap_carries_the_coordinates_of_the_pull_it_leads_to() -> None:
    worst = gaps_between_pulls(a_run())[0]
    assert (worst.x, worst.y) == (30, 40)


def test_a_run_with_one_pull_has_no_gaps() -> None:
    run = a_run()
    single = run.model_copy(update={"pulls": run.pulls[:1]})
    assert gaps_between_pulls(single) == []


def test_the_residual_is_keystone_time_less_pulls_and_death_penalties() -> None:
    # 300s keystone, 180s of pulls, two deaths at 15s each on a +16 -> 90s residual.
    findings = decompose_time(a_run(), (a_death(5_000), a_death(120_000)), SEASON)
    summary = next(f for f in findings if f.id == "time.residual")
    assert summary.seconds_lost == 90.0
    assert summary.confidence is Confidence.MEASURED


def test_a_low_key_uses_the_low_death_penalty() -> None:
    # 300s keystone, 180s of pulls, two deaths at 5s each on a +8 -> 110s residual.
    findings = decompose_time(a_run(keystone_level=8), (a_death(5_000), a_death(120_000)),
                              SEASON)
    summary = next(f for f in findings if f.id == "time.residual")
    assert summary.seconds_lost == 110.0


def test_the_worst_gap_is_reported_with_where_it_happened() -> None:
    findings = decompose_time(a_run(), (), SEASON)
    gap = next(f for f in findings if f.id == "time.gap.0")
    assert gap.seconds_lost == 40.0
    assert gap.pull_index == 1
    # "Where it happened" is now the pack it leads to, not a map coordinate.
    assert gap.evidence == ("Trash",)


def test_gaps_shorter_than_the_floor_are_not_reported() -> None:
    findings = decompose_time(a_run(), (), SEASON)
    # The 10s gap is below the 15s floor, so only the 40s gap earns a finding.
    assert [f.id for f in findings if f.id.startswith("time.gap.")] == ["time.gap.0"]


def test_every_finding_carries_a_confidence() -> None:
    findings = decompose_time(a_run(), (a_death(5_000),), SEASON)
    assert findings
    assert all(finding.confidence is Confidence.MEASURED for finding in findings)


def test_a_negative_residual_reports_no_seconds_lost() -> None:
    # 300s keystone, 180s of pulls, ten deaths at 15s each on a +16 -> -150s of
    # residual. Fighting and the death penalty alone already exceed the timer,
    # so there is nothing honest to report as seconds lost.
    deaths = tuple(a_death(1_000 * i) for i in range(10))
    findings = decompose_time(a_run(), deaths, SEASON)
    summary = next(f for f in findings if f.id == "time.residual")
    assert summary.seconds_lost is None
    assert "no measurable residual" in summary.detail.lower()


def many_gaps_run() -> Run:
    """Eight pulls with seven above-floor gaps, so the report cap can be exercised."""
    gap_seconds = (100, 90, 80, 70, 60, 50, 40)
    pulls = []
    cursor_ms = 0
    for index, gap in enumerate((0, *gap_seconds)):
        start_ms = cursor_ms + gap * 1000
        end_ms = start_ms + 30_000
        pulls.append(
            Pull(
                index=index, pull_id=index + 1, name="Trash", encounter_id=0,
                start_ms=start_ms, end_ms=end_ms, killed=True, x=index, y=index,
                enemies=(EnemyNpc(actor_id=index, game_id=100 + index),),
            )
        )
        cursor_ms = end_ms
    return a_run().model_copy(update={"pulls": tuple(pulls)})


def test_gap_findings_are_capped_at_the_worst_ones() -> None:
    findings = decompose_time(many_gaps_run(), (), SEASON)
    gap_findings = [f for f in findings if f.id.startswith("time.gap.")]
    assert len(gap_findings) == MAX_GAPS_REPORTED
    assert [f.seconds_lost for f in gap_findings] == [100.0, 90.0, 80.0, 70.0, 60.0]


def test_a_gaps_evidence_names_the_pack_it_leads_to() -> None:
    pulls = (
        a_pull(0, 0, 60_000),
        a_pull(1, 200_000, 260_000, name="Loa Speaker Nanea"),
    )
    run = a_run().model_copy(update={"pulls": pulls})
    findings = decompose_time(run, (), SEASON)
    gaps = [f for f in findings if f.id.startswith("time.gap.")]
    assert gaps
    assert gaps[0].evidence[0] == "Loa Speaker Nanea"


def test_no_finding_prints_a_map_position() -> None:
    for finding in decompose_time(a_run(), (), SEASON):
        for line in finding.evidence:
            assert "map position" not in line, finding.id
