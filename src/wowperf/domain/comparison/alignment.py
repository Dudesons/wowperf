# ABOUTME: Lines our pull sequence up against a reference run's, by what each pack was made of.
# ABOUTME: Pure sequence matching over enemy game IDs; no Warcraft Logs vocabulary reaches here.

from difflib import SequenceMatcher

from wowperf.domain.base import Frozen
from wowperf.domain.model import Run


class PullMatch(Frozen):
    """One of our pulls paired with the pull of theirs that fought the same pack."""

    ours_index: int
    theirs_index: int


class Alignment(Frozen):
    """What two routes had in common, and what each did alone."""

    matched: tuple[PullMatch, ...] = ()
    only_ours: tuple[int, ...] = ()
    only_theirs: tuple[int, ...] = ()

    @property
    def out_of_order(self) -> tuple[PullMatch, ...]:
        """Matched pulls the two groups reached at different sequence positions.

        Any matched pull where ours and theirs indices differ means the groups
        encountered that pack at different points on the route.
        """
        return tuple(m for m in self.matched if m.ours_index != m.theirs_index)


def align_pulls(ours: Run, theirs: Run) -> Alignment:
    """Pair our pulls with theirs on pack composition, using the standard library.

    `Pull.signature` is the sorted multiset of the pack's enemy game IDs, so
    order within a pack does not matter and a repeated pack stays two packs.
    """
    ours_signatures = [pull.signature for pull in ours.pulls]
    theirs_signatures = [pull.signature for pull in theirs.pulls]

    # autojunk discards elements that appear in more than 1% of a sequence longer
    # than 200. A dungeon has a dozen pulls so it would never fire today, but the
    # element it would discard is exactly a pack repeated along a route, and
    # silently dropping those is the failure that would be hardest to notice.
    matcher = SequenceMatcher(a=ours_signatures, b=theirs_signatures, autojunk=False)

    matched: list[PullMatch] = []
    only_ours: list[int] = []
    only_theirs: list[int] = []
    for tag, ours_from, ours_to, theirs_from, theirs_to in matcher.get_opcodes():
        if tag == "equal":
            matched.extend(
                PullMatch(
                    ours_index=ours.pulls[i].index,
                    theirs_index=theirs.pulls[j].index,
                )
                for i, j in zip(range(ours_from, ours_to), range(theirs_from, theirs_to),
                                strict=True)
            )
            continue
        # delete, insert and replace all reduce to "these were only ours" and
        # "these were only theirs"; an empty range on either side handles itself.
        only_ours.extend(ours.pulls[i].index for i in range(ours_from, ours_to))
        only_theirs.extend(theirs.pulls[j].index for j in range(theirs_from, theirs_to))

    return Alignment(
        matched=tuple(matched),
        only_ours=tuple(only_ours),
        only_theirs=tuple(only_theirs),
    )
