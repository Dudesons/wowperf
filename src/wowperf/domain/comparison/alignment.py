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
    out_of_order: tuple[PullMatch, ...] = ()


def align_pulls(ours: Run, theirs: Run) -> Alignment:
    """Pair our pulls with theirs on pack composition, using the standard library.

    `Pull.signature` is the sorted multiset of the pack's enemy game IDs, so
    order within a pack does not matter and a repeated pack stays two packs.

    `SequenceMatcher.get_opcodes()` walks both sequences in step, so an "equal"
    block can only ever advance through both routes together: an unequal-length
    route (a skipped or extra pack) shows up as ordinary index drift between
    `matched` pairs, never as a signal that anything was reordered. A genuine
    reorder instead surfaces as the *same* pack signature landing on both sides
    of the split — once left over in our route, once left over in theirs. That
    is what `out_of_order` looks for: a pack signature present in both leftovers,
    paired up in route order (a signature left over twice on one side and once
    on the other yields one pair, with the extra index staying in the leftover
    list). Those paired-up indices are then removed from `only_ours` and
    `only_theirs`, so the three collections stay mutually exclusive.
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

    out_of_order, only_ours, only_theirs = _pair_by_signature(
        ours, theirs, only_ours, only_theirs
    )

    return Alignment(
        matched=tuple(matched),
        only_ours=tuple(only_ours),
        only_theirs=tuple(only_theirs),
        out_of_order=tuple(out_of_order),
    )


def _pair_by_signature(
    ours: Run,
    theirs: Run,
    only_ours: list[int],
    only_theirs: list[int],
) -> tuple[list[PullMatch], list[int], list[int]]:
    """Pair up leftover indices that share a pack signature, in route order.

    `only_ours` and `only_theirs` are already in route order (the opcodes that
    built them cover each sequence left to right), so grouping by signature
    while keeping insertion order is enough to pair the earliest occurrences
    first. Multiplicity is respected: a signature left over twice on one side
    and once on the other produces one pair and leaves one index behind.
    """
    ours_signature_by_index = {pull.index: pull.signature for pull in ours.pulls}
    theirs_signature_by_index = {pull.index: pull.signature for pull in theirs.pulls}

    ours_by_signature: dict[tuple[int, ...], list[int]] = {}
    for index in only_ours:
        ours_by_signature.setdefault(ours_signature_by_index[index], []).append(index)

    theirs_by_signature: dict[tuple[int, ...], list[int]] = {}
    for index in only_theirs:
        theirs_by_signature.setdefault(theirs_signature_by_index[index], []).append(index)

    out_of_order: list[PullMatch] = []
    paired_ours: set[int] = set()
    paired_theirs: set[int] = set()
    for signature, ours_indices in ours_by_signature.items():
        for ours_index, theirs_index in zip(
            ours_indices, theirs_by_signature.get(signature, []), strict=False
        ):
            out_of_order.append(PullMatch(ours_index=ours_index, theirs_index=theirs_index))
            paired_ours.add(ours_index)
            paired_theirs.add(theirs_index)

    out_of_order.sort(key=lambda pair: pair.ours_index)
    remaining_ours = [index for index in only_ours if index not in paired_ours]
    remaining_theirs = [index for index in only_theirs if index not in paired_theirs]
    return out_of_order, remaining_ours, remaining_theirs
