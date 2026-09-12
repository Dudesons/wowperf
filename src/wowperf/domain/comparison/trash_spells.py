# ABOUTME: Compares one player's cast rates on the trash packs two routes shared.
# ABOUTME: Only aligned packs count, so a rate measures play rather than the route.

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.model import Run


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
