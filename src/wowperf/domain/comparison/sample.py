# ABOUTME: The reference runs one comparison may draw on, and which of them each finding may use.
# ABOUTME: Members carry only the streams their axis reads, so absence cannot be read as fact.

from collections.abc import Sequence

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.alignment import MIN_ALIGNED_SHARE, Alignment
from wowperf.domain.comparison.reference import Comparability, ParseRow, SpeedRow
from wowperf.domain.events import CastEvent, Death, EnemyCastRow, InterruptEvent
from wowperf.domain.findings import Finding
from wowperf.domain.model import Run

SAMPLE_SIZE = 5
"""How many references to draw per axis.

The smallest sample at which one unusual reference cannot carry a finding
alone, and at which two candidates may fail to load and still leave enough to
aggregate.
"""

MIN_SAMPLE_FOR_AGGREGATE = 3
"""Below this many eligible members, state one reference rather than a statistic.

A median of two is a mean of two, and "1 of 2" is noise dressed as a statistic.
"""


class SpeedMember(Frozen):
    """One speed reference, with only the streams the speed comparisons read.

    There is deliberately no `casts` field: a speed reference never fetches
    that stream, and a field holding an empty tuple would read as "this run
    cast nothing".
    """

    row: SpeedRow
    run: Run
    comparability: Comparability
    alignment: Alignment
    deaths: tuple[Death, ...] = ()
    enemy_cast_rows: tuple[EnemyCastRow, ...] = ()
    interrupts: tuple[InterruptEvent, ...] = ()


class ParseMember(Frozen):
    """One parse reference, with only the streams the parse comparisons read.

    Absent auras are a real state, not a failure: `compare.uptime.unavailable`
    reports it.

    There is deliberately no `comparability`: nothing on the parse axis is
    shaped like a duration. Casts are compared as rates per minute of boss time
    and auras as fractions of it, and both mean the same thing at any keystone
    level, so the rule that gates `compare.duration` has nothing to gate here.
    """

    row: ParseRow
    run: Run
    casts: tuple[CastEvent, ...] = ()
    auras: PlayerAuras | None = None


class _Sample(Frozen):
    """What every sample can answer about its own size."""

    def can_aggregate(self, subset: Sequence[object]) -> bool:
        """Whether a subset is large enough to state as a statistic."""
        return len(subset) >= MIN_SAMPLE_FOR_AGGREGATE


class SpeedSample(_Sample):
    """The speed references this comparison may draw on."""

    members: tuple[SpeedMember, ...] = ()

    @property
    def duration_eligible(self) -> tuple[SpeedMember, ...]:
        """Members whose keystone level equals ours, so a duration means the same thing."""
        return tuple(
            member for member in self.members if member.comparability.durations_comparable
        )

    @property
    def route_eligible(self) -> tuple[SpeedMember, ...]:
        """Members whose route lined up well enough to price a pack as skipped.

        A member below the threshold contributes nothing here and still
        contributes to downtime, deaths and interrupts: the two logs cutting
        the route into pulls differently says nothing about either.
        """
        return tuple(
            member
            for member in self.members
            if member.alignment.matched_share >= MIN_ALIGNED_SHARE
        )


class ParseSample(_Sample):
    """The parse references this comparison may draw on."""

    members: tuple[ParseMember, ...] = ()

    @property
    def aura_eligible(self) -> tuple[ParseMember, ...]:
        return tuple(member for member in self.members if member.auras is not None)

    @property
    def top(self) -> ParseMember | None:
        """The highest-ranked member, which the talent row names.

        A talent build has no mean and no mode this project can compute, so
        that row stays one player's build.
        """
        return self.members[0] if self.members else None


def too_few(findings: list[Finding], eligible: int) -> list[Finding]:
    """Say plainly that a statistic was not computed, rather than computing a bad one.

    Stated as what the finding above it is, not as what it is not: at
    `eligible` zero the comparison was still made, against a reference that
    cleared no filter, and "only 0 comparable references" would read as though
    nothing had been compared at all.
    """
    note = (
        f"a single reference, not an aggregate: {eligible} of the sample "
        f"{'was' if eligible == 1 else 'were'} comparable, below the floor of "
        f"{MIN_SAMPLE_FOR_AGGREGATE}"
    )
    return [
        finding.model_copy(update={"evidence": (*finding.evidence, note)}) for finding in findings
    ]
