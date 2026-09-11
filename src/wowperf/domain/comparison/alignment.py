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
    our_pack_indices: tuple[int, ...] = ()
    boss_indices: tuple[int, ...] = ()

    @property
    def our_packs(self) -> frozenset[int]:
        """Our trash pulls a route decision could have taken or left.

        De-duplicated: `align_pulls` cannot emit an index twice, but this is a
        public model that tests and callers build by hand, and a repeated index
        would quietly deflate every share taken over it.
        """
        return frozenset(self.our_pack_indices)

    @property
    def matched_packs(self) -> frozenset[int]:
        """Our packs that found a counterpart, by our own pull index."""
        return frozenset(
            {match.ours_index for match in self.matched} & self.our_packs
        )

    @property
    def matched_share(self) -> float:
        """Our packs that found a counterpart, as a share of all our packs.

        Measured over `Pull.is_a_pack` rather than over every trash pull the log
        recorded. Bosses are left out because they match by encounter id and would
        flatter the share; a pull with no recorded enemies and a pull too short to
        be a pack are left out because neither can ever match, so counting them
        would dock a reference for how our own log was cut rather than for how
        either group ran the dungeon.

        Every reader-facing figure and `MIN_ALIGNED_SHARE` share this denominator,
        which is what keeps a finding from contradicting the rule that produced it.
        A run with no packs aligned everything it had.
        """
        if not self.our_packs:
            return 1.0
        return len(self.matched_packs) / len(self.our_packs)


MIN_ALIGNED_SHARE = 0.5
"""Below this share of our packs with a counterpart, no pack is priced as skipped.

When the two logs cut the route into pulls differently, an unmatched pull is not
a skipped pack; it is a segmentation difference, and pricing it would put the
largest wrong number on the page at the top of the ledger.
"""


def _types(pull: Pull) -> frozenset[int]:
    return frozenset(enemy.game_id for enemy in pull.enemies)


def _covers(a: frozenset[int], b: frozenset[int]) -> bool:
    """One pack's enemy types are all present in the other's."""
    return a <= b or b <= a


def _shared_fraction(a: frozenset[int], b: frozenset[int]) -> float:
    return len(a & b) / len(a | b)


def _best_counterpart(pull: Pull, candidates: list[Pull], taken: set[int]) -> Pull | None:
    """The candidate sharing the largest fraction of types, as design §6.3 requires.

    Shared fraction decides first and alone: a candidate that is the pack we
    fought must not lose to a distant one merely because nothing has claimed the
    distant one yet. Among candidates of equal fraction, one not yet paired wins
    — that is what keeps two identical packs on a route matched to two identical
    packs on the other, rather than both to the first — and the earliest pull in
    route order breaks what remains.
    """
    mine = _types(pull)
    covering = [c for c in candidates if _covers(mine, _types(c))]
    if not covering:
        return None
    return max(
        covering,
        key=lambda c: (_shared_fraction(mine, _types(c)), c.index not in taken, -c.index),
    )


def _reordered(matched: list[PullMatch]) -> list[PullMatch]:
    """The pairs that would have to move for their order to follow ours.

    One pair per our pull — its earliest counterpart — in our route order; the
    longest run whose reference indices do not decrease is the shared order, and
    everything outside it was taken in a different sequence. The comparison is
    non-strict because several of our pulls may share one counterpart: a stretch
    they fought as one pull and we cut into several is a segmentation difference,
    and pairs naming the same reference index never had to move for the two
    orders to agree.
    """
    first_by_ours: dict[int, PullMatch] = {}
    for match in sorted(matched, key=lambda m: (m.ours_index, m.theirs_index)):
        first_by_ours.setdefault(match.ours_index, match)
    pairs = list(first_by_ours.values())
    if not pairs:
        return []
    # Longest non-decreasing subsequence of theirs_index, O(n^2): a route has a dozen pulls.
    best_length = [1] * len(pairs)
    previous = [-1] * len(pairs)
    for i, pair in enumerate(pairs):
        for j in range(i):
            if pairs[j].theirs_index <= pair.theirs_index and best_length[j] + 1 > best_length[i]:
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
    2026-09-06, for why containment rather than exact signatures.
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
    # closest counterpart. This sweep-back only recovers their unpicked pulls:
    # because _covers is symmetric, pass 1 already matched every one of our
    # pulls that has any covering candidate, so there is never an unpaired
    # ours_index left here for "taken" to prefer.
    for pull in their_trash:
        if pull.index in taken_theirs:
            continue
        counterpart = _best_counterpart(pull, our_trash, set())
        if counterpart is not None:
            matched.append(PullMatch(ours_index=counterpart.index, theirs_index=pull.index))

    matched_ours = {match.ours_index for match in matched}
    matched_theirs = {match.theirs_index for match in matched}
    return Alignment(
        matched=tuple(matched),
        only_ours=tuple(pull.index for pull in ours.pulls if pull.index not in matched_ours),
        only_theirs=tuple(
            pull.index for pull in theirs.pulls if pull.index not in matched_theirs
        ),
        out_of_order=tuple(_reordered(matched)),
        our_pack_indices=tuple(
            pull.index for pull in ours.pulls if not pull.is_boss and pull.is_a_pack
        ),
        boss_indices=tuple(pull.index for pull in ours.pulls if pull.is_boss),
    )
