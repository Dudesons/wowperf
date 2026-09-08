# ABOUTME: Behaviour tests for the group-axis comparisons that are not about the route.
# ABOUTME: The important one is the refusal: a duration is never printed across a key gap.

from wowperf.domain.comparison.alignment import Alignment
from wowperf.domain.comparison.reference import Comparability, SpeedRow
from wowperf.domain.comparison.sample import SpeedMember, SpeedSample
from wowperf.domain.comparison.tempo import compare_tempo, compare_tempo_sample
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


def a_member(
    *,
    level: int = 16,
    our_level: int = 16,
    pulls: tuple[Pull, ...] = (),
    deaths: int = 0,
    kicked: int = 0,
    landed: int = 0,
    time_s: float = 1909.0,
    report_code: str = "REF1",
) -> SpeedMember:
    """A speed reference wrapping `a_loaded`, for the tests that need a `SpeedMember`.

    `alignment` is always the type's own empty default: nothing tempo compares
    reads a member's alignment, so a fixture asserting the fact would test
    nothing.
    """
    loaded = a_loaded(
        level=level, pulls=pulls, deaths=deaths, kicked=kicked, landed=landed, time_s=time_s
    )
    return SpeedMember(
        row=SpeedRow(
            report_code=report_code,
            fight_id=1,
            keystone_level=level,
            duration_ms=int(time_s * 1000),
            deaths=deaths,
        ),
        run=loaded.run,
        comparability=Comparability(our_level=our_level, their_level=level),
        alignment=Alignment(),
        deaths=loaded.deaths,
        enemy_cast_rows=loaded.enemy_cast_rows,
        interrupts=loaded.interrupts,
    )


def one(findings: list[Finding], finding_id: str) -> Finding:
    matches = [finding for finding in findings if finding.id == finding_id]
    assert len(matches) == 1, f"expected exactly one {finding_id}, got {len(matches)}"
    return matches[0]


# --- compare_tempo (pairwise) ----------------------------------------------


def test_our_extra_downtime_is_measured_and_priced() -> None:
    # Ours: 40s of walking between two pulls. Theirs: 10s.
    ours = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 100, 60)))
    theirs = a_member(pulls=(a_pull(0, 0, 60), a_pull(1, 70, 60)))

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.downtime")

    assert finding.seconds_lost == 30.0
    assert finding.confidence is Confidence.MEASURED


def test_less_downtime_than_the_reference_costs_nothing() -> None:
    ours = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 70, 60)))
    theirs = a_member(pulls=(a_pull(0, 0, 60), a_pull(1, 100, 60)))

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.downtime")

    assert finding.seconds_lost is None


def test_deaths_are_counted_and_never_priced_twice() -> None:
    ours = a_loaded(deaths=4)
    theirs = a_member(deaths=0)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.deaths")

    assert "4" in finding.title
    assert finding.seconds_lost is None
    assert any("deaths.total" in line for line in finding.evidence)


def test_missed_interrupts_are_derived_not_measured() -> None:
    ours = a_loaded(kicked=1, landed=3)
    theirs = a_member(kicked=3, landed=1)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.interrupts")

    assert finding.confidence is Confidence.DERIVED


def test_equal_levels_compare_the_total_time() -> None:
    ours = a_loaded(time_s=1909.0)
    theirs = a_member(time_s=1379.0)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.duration")

    assert finding.seconds_lost == 530.0
    assert finding.confidence is Confidence.MEASURED


def test_a_level_gap_withholds_the_duration_and_says_why() -> None:
    ours = a_loaded(level=16, time_s=1909.0)
    theirs = a_member(level=17, time_s=1379.0)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=17)),
                  "compare.duration")

    assert finding.seconds_lost is None
    assert "not comparable" in finding.detail
    assert "1379" not in finding.detail, "a withheld number must not appear anyway"


def test_a_run_with_no_pulls_compares_without_raising() -> None:
    findings = compare_tempo(a_loaded(), a_member(),
                             Comparability(our_level=16, their_level=16))

    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_every_finding_id_is_unique() -> None:
    ours = a_loaded(deaths=2, kicked=1, landed=1, pulls=(a_pull(0, 0, 60), a_pull(1, 100, 60)))
    theirs = a_member(deaths=0, kicked=2, landed=0)

    ids = [f.id for f in compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16))]

    assert len(ids) == len(set(ids))


# --- compare_tempo_sample ---------------------------------------------------


def test_a_wholly_empty_sample_produces_no_findings() -> None:
    # `service.compare()` already says "nothing to compare against" once, as
    # `compare.speed.unavailable`; this must not crash, and must not repeat it.
    findings = compare_tempo_sample(a_loaded(), SpeedSample())

    assert findings == []


def test_below_the_floor_the_pairwise_wording_is_used() -> None:
    ours = a_loaded(deaths=4)
    sample = SpeedSample(members=(a_member(deaths=1), a_member(deaths=2)))

    findings = compare_tempo_sample(ours, sample)

    deaths = one(findings, "compare.deaths")
    assert deaths.title == "We died 4 times, the reference died 1"
    assert any("too few comparable references to aggregate" in line for line in deaths.evidence)


def test_downtime_is_stated_against_the_median_with_its_range() -> None:
    # Sample downtimes: 100s, 120s, 150s -> median 120s, range 100s to 150s.
    ours = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 240, 60)))  # 180s of downtime
    sample = SpeedSample(
        members=(
            a_member(pulls=(a_pull(0, 0, 60), a_pull(1, 160, 60))),  # 100s
            a_member(pulls=(a_pull(0, 0, 60), a_pull(1, 180, 60))),  # 120s
            a_member(pulls=(a_pull(0, 0, 60), a_pull(1, 210, 60))),  # 150s
        )
    )

    findings = compare_tempo_sample(ours, sample)

    downtime = one(findings, "compare.downtime")
    assert downtime.title == "We spent 180s between packs; the median of 3 fast runs is 120s"
    assert "range 100s to 150s" in downtime.evidence
    assert downtime.confidence is Confidence.DERIVED
    assert downtime.seconds_lost == 60.0


def test_beating_the_median_is_not_a_loss() -> None:
    # Our downtime (90s) sits below the sample's median (120s).
    ours = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 150, 60)))  # 90s of downtime
    sample = SpeedSample(
        members=(
            a_member(pulls=(a_pull(0, 0, 60), a_pull(1, 160, 60))),  # 100s
            a_member(pulls=(a_pull(0, 0, 60), a_pull(1, 180, 60))),  # 120s
            a_member(pulls=(a_pull(0, 0, 60), a_pull(1, 210, 60))),  # 150s
        )
    )

    findings = compare_tempo_sample(ours, sample)

    assert one(findings, "compare.downtime").seconds_lost is None


def test_deaths_are_compared_against_the_median_and_never_priced() -> None:
    ours = a_loaded(deaths=4)
    sample = SpeedSample(
        members=(a_member(deaths=0), a_member(deaths=1), a_member(deaths=2)),
    )

    findings = compare_tempo_sample(ours, sample)

    deaths = one(findings, "compare.deaths")
    assert "4" in deaths.title
    assert "median of 3" in deaths.title
    assert deaths.confidence is Confidence.DERIVED
    assert deaths.seconds_lost is None


def test_completion_time_uses_only_the_members_at_our_keystone_level() -> None:
    # The brief's own sketch pairs this assertion with a three-member sample where
    # one member sits off our level, leaving 2 duration-eligible -- but the floor
    # for an aggregate is 3 (MIN_SAMPLE_FOR_AGGREGATE), so 2 eligible members
    # cannot produce "the median of 2" as an aggregate title; that would violate
    # the floor this comparison is built to enforce. Corrected here to four
    # members, one off-level, leaving exactly 3 duration-eligible -- enough to
    # clear the floor and still show the eligible count differs from the total.
    ours = a_loaded(level=16, time_s=1300.0)
    sample = SpeedSample(
        members=(
            a_member(level=15, time_s=1100.0),  # off our level: excluded
            a_member(level=16, time_s=1200.0),
            a_member(level=16, time_s=1250.0),
            a_member(level=16, time_s=1300.0),
        )
    )

    findings = compare_tempo_sample(ours, sample)

    duration = one(findings, "compare.duration")
    assert "median of 3" in duration.title
    assert duration.confidence is Confidence.DERIVED


def test_completion_time_is_withheld_when_no_member_shares_our_level() -> None:
    ours = a_loaded(level=16, time_s=1909.0)
    sample = SpeedSample(
        members=(
            a_member(level=17, time_s=1000.0),
            a_member(level=17, time_s=1100.0),
            a_member(level=15, time_s=1200.0),
        )
    )

    findings = compare_tempo_sample(ours, sample)

    duration = one(findings, "compare.duration")
    assert duration.title == "Completion times are not compared"
    assert "3 of 3 references were at a different keystone level" in duration.evidence
    assert duration.seconds_lost is None


def test_completion_time_is_withheld_when_too_few_share_our_level() -> None:
    # Two of four references share our level -- below the floor of 3, so this
    # collapses into the same withheld case as zero sharing it, per the plan's
    # own step 3: "when they do not [clear the floor]", not "when none do".
    ours = a_loaded(level=16, time_s=1909.0)
    sample = SpeedSample(
        members=(
            a_member(level=16, time_s=1000.0),
            a_member(level=16, time_s=1100.0),
            a_member(level=17, time_s=1200.0),
            a_member(level=15, time_s=1300.0),
        )
    )

    findings = compare_tempo_sample(ours, sample)

    duration = one(findings, "compare.duration")
    assert duration.title == "Completion times are not compared"
    assert "2 of 4 references were at a different keystone level" in duration.evidence


def test_the_kick_share_is_a_median_of_per_run_shares_not_a_pooled_ratio() -> None:
    # Members kicking 1 of 2 (0.5), 8 of 10 (0.8) and 0 of 2 (0.0): the median
    # share is 0.5. A pooled ratio would be (1+8+0)/(2+10+2) = 9/14 =~ 0.64,
    # dominated by the busiest reference -- the sample must not print that.
    ours = a_loaded(kicked=1, landed=1)
    sample = SpeedSample(
        members=(
            a_member(kicked=1, landed=1),
            a_member(kicked=8, landed=2),
            a_member(kicked=0, landed=2),
        )
    )

    findings = compare_tempo_sample(ours, sample)

    interrupts = one(findings, "compare.interrupts")
    assert "median 50%" in interrupts.title
    assert interrupts.confidence is Confidence.DERIVED
    assert interrupts.seconds_lost is None


def test_every_finding_id_is_unique_over_the_sample() -> None:
    ours = a_loaded(deaths=2, kicked=1, landed=1, pulls=(a_pull(0, 0, 60), a_pull(1, 100, 60)))
    sample = SpeedSample(
        members=(
            a_member(deaths=0, kicked=2, landed=0),
            a_member(deaths=1, kicked=1, landed=1),
            a_member(deaths=2, kicked=0, landed=2),
        )
    )

    ids = [f.id for f in compare_tempo_sample(ours, sample)]

    assert len(ids) == len(set(ids))
