# ABOUTME: Behaviour tests for the sample types and which members each eligibility subset keeps.
# ABOUTME: The interesting cases are the keystone-level gate, the alignment gate, and the floor.

from wowperf.domain.comparison.alignment import Alignment, PullMatch
from wowperf.domain.comparison.reference import Comparability, SpeedRow
from wowperf.domain.comparison.sample import (
    MIN_SAMPLE_FOR_AGGREGATE,
    ParseMember,
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


def test_a_parse_member_carries_no_run() -> None:
    """The narrowing design 8.2 prescribes, pinned by absence.

    A raid reference has no `Run` to give. A member that still accepted one
    would let a caller pass a degenerate single-pull run, which design 5.3
    rejects because four analysers then compute quiet wrong answers.

    The field set is asserted whole rather than only for the absence of `run`:
    the cheapest way to satisfy an absence is to add back under another name
    whatever the aggregate used to supply, and a closed set is what stops that.
    `pulls` is here because three readers -- the boss-cast rule, the aura
    windows and the trash alignment -- read the reference's route and nothing
    else of its run; it is empty for a raid reference, which has no route.
    """
    assert "run" not in ParseMember.model_fields
    assert set(ParseMember.model_fields) == {
        "character_name",
        "report_code",
        "fight_id",
        "boss_seconds",
        "players",
        "casts",
        "auras",
        "ability_icons",
        "pulls",
    }
