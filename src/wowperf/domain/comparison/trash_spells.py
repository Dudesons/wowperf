# ABOUTME: Compares one player's cast rates on the trash packs two routes shared.
# ABOUTME: Only aligned packs count, so a rate measures play rather than the route.

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.model import Run

MIN_ALIGNED_TRASH_SECONDS = 60.0
"""Aligned trash seconds a side must reach before its rate is argued from.

Measured 2026-09-13 against the cached responses, over two distributions. The
first is 106 real trash packs across 19 keystone fights in five dungeons: the
median pack ran 80.9s, a quarter ran under 57.3s, ten ran under 20s and the
shortest ran 6.8s. The second is what two real routes through one dungeon
actually share — six cross-report pairs on Murder Row, whose weaker side ran
644.8s to 786.9s of aligned trash. Between those two lies a wide empty stretch,
and this floor sits in it: every complete route measured keeps every reference,
while three quarters of single packs clear it alone, so a route that lined up
with only one ordinary pack is still compared.

A minute is also the unit the rate is stated in. Below it a figure in casts per
minute is an extrapolation rather than a measurement, which is the failure the
floor exists to stop: two casts over twenty seconds is six a minute and means
nothing, and the rate rows have no other guard against a small denominator.
"""


class AlignedTrash(Frozen):
    """The trash packs two routes shared, and the seconds each side spent on them."""

    our_pulls: frozenset[int] = frozenset()
    their_pulls: frozenset[int] = frozenset()
    our_seconds: float = 0.0
    their_seconds: float = 0.0

    @property
    def pack_count(self) -> int:
        """Our packs that found a counterpart — the denominator a title states."""
        return len(self.our_pulls)


def aligned_trash(ours: Run, theirs: Run) -> AlignedTrash:
    """The packs both groups fought, as pull indices and seconds on each side.

    Indices are collected into sets before any duration is summed, and the
    reason differs on the two sides. `align_pulls` runs a sweep after its main
    pass that pairs each of their unclaimed trash pulls back to the best
    counterpart among ours, with nothing marked taken, so one chain-pulled
    stretch of ours can appear in several matches — summing per match would
    inflate our own denominator and depress our own rate. Their indices cannot
    repeat, because the main pass claims each one and the sweep visits only
    what it left; the set on that side is defensive, not load-bearing.
    """
    alignment = align_pulls(ours, theirs)
    packs = alignment.our_packs
    ours_by_index = {pull.index: pull for pull in ours.pulls}
    theirs_by_index = {pull.index: pull for pull in theirs.pulls}

    our_pulls = {match.ours_index for match in alignment.matched if match.ours_index in packs}
    their_pulls = {
        match.theirs_index for match in alignment.matched if match.ours_index in packs
    }
    return AlignedTrash(
        our_pulls=frozenset(our_pulls),
        their_pulls=frozenset(their_pulls),
        our_seconds=sum(ours_by_index[i].duration_seconds for i in our_pulls),
        their_seconds=sum(
            theirs_by_index[i].duration_seconds for i in their_pulls if i in theirs_by_index
        ),
    )


def is_comparable(aligned: AlignedTrash) -> bool:
    """Whether both sides spent long enough on shared packs to state a rate.

    Both, not either: a rate is a ratio of two denominators and a thin one on
    the reference's side skews it exactly as badly as a thin one on ours.
    """
    return (
        aligned.our_seconds >= MIN_ALIGNED_TRASH_SECONDS
        and aligned.their_seconds >= MIN_ALIGNED_TRASH_SECONDS
    )
