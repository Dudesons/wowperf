# ABOUTME: Behaviour tests for the group-axis comparisons that are not about the route.
# ABOUTME: The important one is the refusal: a duration is never printed across a key gap.

from wowperf.domain.comparison.reference import Comparability
from wowperf.domain.comparison.tempo import compare_tempo
from wowperf.domain.events import Death, EnemyCastRow, InterruptEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Pull, Run


def a_pull(index: int, start_s: float, seconds: float) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Pack",
        encounter_id=0,
        start_ms=int(start_s * 1000),
        end_ms=int((start_s + seconds) * 1000),
        killed=True,
        x=0,
        y=0,
        enemies=(),
    )


def a_loaded(
    *,
    level: int = 16,
    pulls: tuple[Pull, ...] = (),
    deaths: int = 0,
    kicked: int = 0,
    landed: int = 0,
    time_s: float = 1909.0,
) -> LoadedRun:
    run = Run(
        report_code="abc123",
        fight_id=36,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=level,
        affix_ids=(9, 10, 147),
        keystone_time_ms=int(time_s * 1000),
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=(),
        players=(),
        pulls=pulls,
    )
    rows = []
    interrupts = []
    for n in range(kicked + landed):
        rows.append(
            EnemyCastRow(
                source_id=500 + n,
                source_instance=0,
                ability_id=1000,
                ability_name="Shoot",
                timestamp_ms=n * 10_000,
                is_start=True,
            )
        )
        rows.append(
            EnemyCastRow(
                source_id=500 + n,
                source_instance=0,
                ability_id=1000,
                ability_name="Shoot",
                timestamp_ms=n * 10_000 + 1_000,
                is_start=False,
            )
        )
        if n < kicked:
            interrupts.append(
                InterruptEvent(
                    player_name="Emberkin",
                    actor_id=693,
                    interrupted_ability_id=1000,
                    target_id=500 + n,
                    target_instance=0,
                    timestamp_ms=n * 10_000 + 500,
                )
            )
    return LoadedRun(
        run=run,
        deaths=tuple(
            Death(player_name="Emberkin", actor_id=693, timestamp_ms=n, killing_blow="X")
            for n in range(deaths)
        ),
        enemy_cast_rows=tuple(rows),
        interrupts=tuple(interrupts),
    )


def one(findings: list[Finding], finding_id: str) -> Finding:
    matches = [finding for finding in findings if finding.id == finding_id]
    assert len(matches) == 1, f"expected exactly one {finding_id}, got {len(matches)}"
    return matches[0]


def test_our_extra_downtime_is_measured_and_priced() -> None:
    # Ours: 40s of walking between two pulls. Theirs: 10s.
    ours = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 100, 60)))
    theirs = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 70, 60)))

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.downtime")

    assert finding.seconds_lost == 30.0
    assert finding.confidence is Confidence.MEASURED


def test_less_downtime_than_the_reference_costs_nothing() -> None:
    ours = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 70, 60)))
    theirs = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 100, 60)))

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.downtime")

    assert finding.seconds_lost is None


def test_deaths_are_counted_and_never_priced_twice() -> None:
    ours = a_loaded(deaths=4)
    theirs = a_loaded(deaths=0)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.deaths")

    assert "4" in finding.title
    assert finding.seconds_lost is None
    assert any("deaths.total" in line for line in finding.evidence)


def test_missed_interrupts_are_derived_not_measured() -> None:
    ours = a_loaded(kicked=1, landed=3)
    theirs = a_loaded(kicked=3, landed=1)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.interrupts")

    assert finding.confidence is Confidence.DERIVED


def test_equal_levels_compare_the_total_time() -> None:
    ours = a_loaded(time_s=1909.0)
    theirs = a_loaded(time_s=1379.0)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.duration")

    assert finding.seconds_lost == 530.0
    assert finding.confidence is Confidence.MEASURED


def test_a_level_gap_withholds_the_duration_and_says_why() -> None:
    ours = a_loaded(level=16, time_s=1909.0)
    theirs = a_loaded(level=17, time_s=1379.0)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=17)),
                  "compare.duration")

    assert finding.seconds_lost is None
    assert "not comparable" in finding.detail
    assert "1379" not in finding.detail, "a withheld number must not appear anyway"


def test_a_run_with_no_pulls_compares_without_raising() -> None:
    findings = compare_tempo(a_loaded(), a_loaded(),
                             Comparability(our_level=16, their_level=16))

    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_every_finding_id_is_unique() -> None:
    ours = a_loaded(deaths=2, kicked=1, landed=1, pulls=(a_pull(0, 0, 60), a_pull(1, 100, 60)))
    theirs = a_loaded(deaths=0, kicked=2, landed=0)

    ids = [f.id for f in compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16))]

    assert len(ids) == len(set(ids))
