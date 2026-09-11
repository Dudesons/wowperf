# ABOUTME: Behaviour tests for the sample types and which members each eligibility subset keeps.
# ABOUTME: The interesting cases are the keystone-level gate, the alignment gate, and the floor.

from wowperf.domain.comparison.alignment import Alignment, PullMatch
from wowperf.domain.comparison.reference import Comparability, SpeedRow
from wowperf.domain.comparison.sample import (
    MIN_SAMPLE_FOR_AGGREGATE,
    SpeedMember,
    SpeedSample,
)
from wowperf.domain.model import Run


def _run(keystone_level: int) -> Run:
    return Run(
        report_code="aBcD1234",
        fight_id=1,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=keystone_level,
        affix_ids=(),
        keystone_time_ms=1_380_000,
        keystone_bonus=1,
        count_reached=100,
        count_required=100,
        npc_counts=(),
        players=(),
        pulls=(),
    )


def _member(their_level: int, matched_share_numerator: int) -> SpeedMember:
    """A speed member at `their_level` whose alignment matched N of 10 trash pulls."""
    return SpeedMember(
        row=SpeedRow(
            report_code="aBcD1234", fight_id=1, keystone_level=their_level,
            duration_ms=1_380_000, deaths=0,
        ),
        run=_run(their_level),
        comparability=Comparability(our_level=16, their_level=their_level),
        alignment=Alignment(
            matched=tuple(
                PullMatch(ours_index=i, theirs_index=i)
                for i in range(matched_share_numerator)
            ),
            our_pack_indices=tuple(range(10)),
        ),
    )


def test_only_members_at_our_keystone_level_are_duration_eligible() -> None:
    sample = SpeedSample(members=(_member(16, 10), _member(15, 10), _member(16, 10)))

    assert len(sample.duration_eligible) == 2


def test_a_member_below_the_alignment_threshold_is_not_route_eligible() -> None:
    sample = SpeedSample(members=(_member(16, 9), _member(16, 4)))

    assert len(sample.route_eligible) == 1


def test_a_member_that_aligned_badly_still_counts_for_everything_else() -> None:
    sample = SpeedSample(members=(_member(16, 9), _member(16, 4)))

    assert len(sample.duration_eligible) == 2


def test_below_the_floor_a_subset_cannot_be_aggregated() -> None:
    sample = SpeedSample(members=tuple(_member(16, 10) for _ in range(2)))

    assert not sample.can_aggregate(sample.duration_eligible)


def test_at_the_floor_a_subset_can_be_aggregated() -> None:
    sample = SpeedSample(
        members=tuple(_member(16, 10) for _ in range(MIN_SAMPLE_FOR_AGGREGATE))
    )

    assert sample.can_aggregate(sample.duration_eligible)
