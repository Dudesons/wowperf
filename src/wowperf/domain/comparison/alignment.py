# ABOUTME: Lines our pull sequence up against a reference run's, by what each pack was made of.
# ABOUTME: Set containment over enemy game IDs, so a chain-pulled stretch finds the packs it covers.

from wowperf.domain.base import Frozen
from wowperf.domain.model import Pull, Run


class PullMatch(Frozen):
    """One of our pulls paired with the pull of theirs that fought the same pack."""

    ours_index: int
    theirs_index: int


class Alignment(Frozen):
    """What two routes had in common, and what each did alone.

    `matched` may pair one of our pulls with several of theirs, or several of
    ours with one of theirs: Warcraft Logs records a chain of packs fought
    without a break as one pull, and the other run may have taken them one at
    a time. A pull with several counterparts is still one matched pull.
    """

    matched: tuple[PullMatch, ...] = ()
    only_ours: tuple[int, ...] = ()
    only_theirs: tuple[int, ...] = ()
    out_of_order: tuple[PullMatch, ...] = ()
    our_trash_count: int = 0
    boss_indices: tuple[int, ...] = ()

    @property
    def matched_share(self) -> float:
        """Our trash pulls that found a counterpart, as a share of all our trash pulls.

        Bosses are left out: they match by encounter id and would flatter the share.
        A run with no trash pulls aligned everything it had.
        """
        if self.our_trash_count == 0:
            return 1.0
        matched_trash = {match.ours_index for match in self.matched} - set(self.boss_indices)
        return len(matched_trash) / self.our_trash_count


def _types(pull: Pull) -> frozenset[int]:
    return frozenset(enemy.game_id for enemy in pull.enemies)


def _covers(a: frozenset[int], b: frozenset[int]) -> bool:
    """One pack's enemy types are all present in the other's."""
    return a <= b or b <= a


def _shared_fraction(a: frozenset[int], b: frozenset[int]) -> float:
    return len(a & b) / len(a | b)


def _best_counterpart(pull: Pull, candidates: list[Pull], taken: set[int]) -> Pull | None:
    """The candidate sharing the largest fraction of types, preferring one not yet paired.

    Preferring an unpaired candidate is what keeps two identical packs on a
    route matched to two identical packs on the other, rather than both to the
    first. Ties go to the earliest pull in route order.
    """
    mine = _types(pull)
    covering = [c for c in candidates if _covers(mine, _types(c))]
    if not covering:
        return None
    unpaired = [c for c in covering if c.index not in taken]
    pool = unpaired or covering
    return max(pool, key=lambda c: (_shared_fraction(mine, _types(c)), -c.index))


def _reordered(matched: list[PullMatch]) -> list[PullMatch]:
    """The pairs that would have to move for their order to follow ours.

    One pair per our pull — its earliest counterpart — in our route order; the
    longest run whose reference indices also increase is the shared order, and
    everything outside it was taken in a different sequence.
    """
    first_by_ours: dict[int, PullMatch] = {}
    for match in sorted(matched, key=lambda m: (m.ours_index, m.theirs_index)):
        first_by_ours.setdefault(match.ours_index, match)
    pairs = list(first_by_ours.values())
    if not pairs:
        return []
    # Longest strictly increasing subsequence of theirs_index, O(n^2): a route has a dozen pulls.
    best_length = [1] * len(pairs)
    previous = [-1] * len(pairs)
    for i, pair in enumerate(pairs):
        for j in range(i):
            if pairs[j].theirs_index < pair.theirs_index and best_length[j] + 1 > best_length[i]:
                best_length[i] = best_length[j] + 1
                previous[i] = j
    end = max(range(len(pairs)), key=lambda i: (best_length[i], -i))
    in_order: set[int] = set()
    while end != -1:
        in_order.add(end)
        end = previous[end]
    return [pair for i, pair in enumerate(pairs) if i not in in_order]


def align_pulls(ours: Run, theirs: Run) -> Alignment:
    """Pair our pulls with theirs by what each contained.

    A boss pull matches the boss pull with the same encounter id, whatever
    adds either group happened to fight. Two trash pulls match when either
    one's set of enemy types is contained in the other's, so a stretch that
    Warcraft Logs recorded as one pull matches each separate pull it covers.
    Pulls with no recorded enemies match nothing. See design §6.3, amended
    2026-09-06, for why exact signatures were abandoned.
    """
    matched: list[PullMatch] = []

    their_bosses = {pull.encounter_id: pull for pull in theirs.pulls if pull.is_boss}
    for pull in ours.pulls:
        if pull.is_boss and pull.encounter_id in their_bosses:
            matched.append(
                PullMatch(
                    ours_index=pull.index, theirs_index=their_bosses[pull.encounter_id].index
                )
            )

    our_trash = [pull for pull in ours.pulls if not pull.is_boss and pull.enemies]
    their_trash = [pull for pull in theirs.pulls if not pull.is_boss and pull.enemies]

    taken_theirs: set[int] = set()
    for pull in our_trash:
        counterpart = _best_counterpart(pull, their_trash, taken_theirs)
        if counterpart is not None:
            matched.append(PullMatch(ours_index=pull.index, theirs_index=counterpart.index))
            taken_theirs.add(counterpart.index)

    # Their pulls nobody picked may still sit inside one of ours: a pack we
    # chain-pulled that they took alone, after our pull already chose its
    # closest counterpart.
    taken_ours = {match.ours_index for match in matched}
    for pull in their_trash:
        if pull.index in taken_theirs:
            continue
        counterpart = _best_counterpart(pull, our_trash, taken_ours)
        if counterpart is not None:
            matched.append(PullMatch(ours_index=counterpart.index, theirs_index=pull.index))
            taken_ours.add(counterpart.index)

    matched_ours = {match.ours_index for match in matched}
    matched_theirs = {match.theirs_index for match in matched}
    return Alignment(
        matched=tuple(matched),
        only_ours=tuple(pull.index for pull in ours.pulls if pull.index not in matched_ours),
        only_theirs=tuple(
            pull.index for pull in theirs.pulls if pull.index not in matched_theirs
        ),
        out_of_order=tuple(_reordered(matched)),
        our_trash_count=len(our_trash),
        boss_indices=tuple(pull.index for pull in ours.pulls if pull.is_boss),
    )
