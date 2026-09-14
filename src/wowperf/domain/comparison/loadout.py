# ABOUTME: Compares one player's gear and stat ratings against a sample of top parses.
# ABOUTME: Resolves an item-sourced cast to its item, so advice names something pressable.

from collections.abc import Sequence

from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, ParseMember, find_player
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.findings import Confidence, Finding, quantifier_for, quantity
from wowperf.domain.loadout import TIER_SLOTS, EquippedItem, Loadout


def loadouts_of(members: Sequence[ParseMember]) -> tuple[Loadout, ...]:
    """Each member's own player's loadout, skipping a member whose loadout was never fetched.

    `find_player` lives in `sample.py` rather than `service.py` for this: this
    module already has no reason to import `service.py`, and `service.py`
    already imports `sample.py`, so reading it from there is the one place that
    adds no cycle. A member whose player cannot be found in their own report,
    or whose loadout was never fetched, contributes nothing rather than a gap
    the caller would have to notice on its own.
    """
    loadouts = []
    for member in members:
        player = find_player(member.run, member.row.character_name)
        if player is not None and player.loadout is not None:
            loadouts.append(player.loadout)
    return tuple(loadouts)


def item_sourced(ability_name: str, loadouts: Sequence[Loadout]) -> EquippedItem | None:
    """The equipped item this ability's name identifies, if any of these wore it.

    Warcraft Logs names an on-use trinket's spell after the item, measured
    2026-09-14: of the 81 items equipped across one report's five players, five
    names were also ability names, four of them trinkets, out of ten trinkets
    worn. The other six trinkets are passive and fire no named spell.

    **The reading is asymmetric and callers must honour it.** A match is
    evidence the ability came from an item. A miss is *not* evidence it did
    not: an on-use effect named differently from its item would not be caught.
    A caller may act on a match; on a miss it may only say it does not know.

    The comparison is exact rather than case-folded or partial. A loose rule
    would fold every name sharing a word, and the join earns its place only by
    being precise.
    """
    for loadout in loadouts:
        found = loadout.item_named(ability_name)
        if found is not None:
            return found
    return None


def compare_enchants(
    our_loadout: Loadout | None, their_loadouts: Sequence[Loadout], our_name: str
) -> list[Finding]:
    """Slots every comparable reference enchanted and this player left bare.

    **The sample defines which slots take an enchant.** Measured 2026-09-14
    across ten players in two reports: eight slots were enchanted 10/10, nine
    were 0/10, and the off hand was 1/10 — enchantable for some specialisations
    and not others. A hardcoded list would have to be revised every expansion
    and would misjudge the off hand today; unanimity in the sample needs no
    revision and gets the off hand right by abstaining.

    A slot this player wears nothing in is not reported: an empty slot is a
    different claim from an unenchanted one.
    """
    if our_loadout is None or len(their_loadouts) < MIN_SAMPLE_FOR_AGGREGATE:
        return []

    ours_enchanted = our_loadout.enchanted_slots()
    ours_occupied = our_loadout.occupied_slots()
    unanimous = frozenset.intersection(
        *(loadout.enchanted_slots() for loadout in their_loadouts)
    )

    findings = []
    for slot in sorted(unanimous & ours_occupied - ours_enchanted):
        findings.append(
            Finding(
                # The slot is folded in before `_for_player` appends the
                # per-player suffix: two bare slots missing an enchant would
                # otherwise mint the identical id and collide into one page
                # element id, the same collision `compare.uptime.self.<rank>`
                # avoids by folding in a rank per aura.
                id=f"compare.gear.enchant.{slot}",
                title=(
                    f"{count_phrase(len(their_loadouts), len(their_loadouts))} top parses "
                    f"enchanted slot {slot}; {our_name} did not"
                ),
                detail=(
                    "Every reference in the sample carries an enchant in this slot and this "
                    "one does not. Which enchant is not stated: the sample may disagree among "
                    "themselves, and this tool does not rank enchants."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"slot {slot}",
                    f"{len(their_loadouts)} of {len(their_loadouts)} references enchanted it",
                ),
                quantifier=quantifier_for(len(their_loadouts), len(their_loadouts)),
            )
        )
    return findings


def compare_tier(
    our_loadout: Loadout | None, their_loadouts: Sequence[Loadout], our_name: str
) -> list[Finding]:
    """How many tier pieces this player wore, against the sample's median.

    `derived`, not `measured`: the API states no tier flag, and the rule that
    picks the tier set out of the gear — the set id occupying slots
    {0, 2, 4, 6, 9} — is inferred from seven sets observed on 2026-09-14, not
    something the log said.

    Reported only when below the sample. A player carrying more tier than the
    references has nothing to act on, and the report is a list of things to do
    differently rather than a scoreboard.
    """
    if our_loadout is None or len(their_loadouts) < MIN_SAMPLE_FOR_AGGREGATE:
        return []

    ours = our_loadout.tier_pieces()
    theirs = [float(loadout.tier_pieces()) for loadout in their_loadouts]
    their_median = median(theirs)
    if ours >= their_median:
        return []

    low, high = observed_range(theirs)
    return [
        Finding(
            id="compare.gear.tier",
            title=(
                f"{our_name} wore {quantity(ours, 'tier piece', 'tier pieces')}; "
                f"the sample's median is {their_median:g}"
            ),
            detail=(
                "A tier set bonus is throughput this player did not have and the references "
                "did. Read the cast and damage comparisons against this before reading them "
                "as things that went unpressed."
            ),
            confidence=Confidence.DERIVED,
            seconds_lost=None,
            evidence=(
                f"{ours} tier pieces in slots {sorted(TIER_SLOTS)}",
                f"sample median {their_median:g}, range {low:g} to {high:g} "
                f"across {len(their_loadouts)} references",
            ),
        )
    ]


STAT_GAP_SHARE = 0.15
"""How far a stat's share of the budget must move before the row is worth printing.

Two players of the same specialisation gemming the same way land within a few
points of each other, and a row for every stat every time would bury the one
that moved.
"""


def compare_stats(
    our_loadout: Loadout | None, their_loadouts: Sequence[Loadout], our_name: str
) -> list[Finding]:
    """Each secondary's rating against the sample's, and its share of the budget.

    Two readings, because one of them is misleading alone. The rating and its
    gap is the fact, and it is what a reader asked for; but a top parse
    out-gears this player, so it holds more of every stat and the raw gap
    largely restates the item-level confound `confounds.py` already reports.
    The share of the player's own secondary budget is item-level independent,
    and it is the part a decision — a gem, an enchant, which piece was kept —
    actually moves.

    Ratings only. Converting one to a percentage needs a per-level coefficient
    with no source in this API, so the only percentage here is a share.
    """
    if our_loadout is None or our_loadout.stats is None:
        return []
    theirs = [
        loadout.stats for loadout in their_loadouts if loadout.stats is not None
    ]
    if len(theirs) < MIN_SAMPLE_FOR_AGGREGATE:
        return []

    our_stats = our_loadout.stats
    our_budget = our_stats.total_secondary()
    findings = []
    for name, ours in our_stats.secondaries():
        ratings = [float(dict(stats.secondaries())[name]) for stats in theirs]
        their_median = median(ratings)
        if ours == their_median:
            continue
        our_share = ours / our_budget if our_budget else 0.0
        their_shares = [
            dict(stats.secondaries())[name] / stats.total_secondary()
            if stats.total_secondary()
            else 0.0
            for stats in theirs
        ]
        their_share = median(their_shares)
        if abs(our_share - their_share) < STAT_GAP_SHARE:
            continue
        low, high = observed_range(ratings)
        findings.append(
            Finding(
                id="compare.stats.rating",
                title=(
                    f"{our_name} carried {ours} {name} rating; "
                    f"the sample's median is {their_median:g}"
                ),
                detail=(
                    f"That is {our_share:.0%} of this player's secondary rating against "
                    f"{their_share:.0%} of the sample's. The share is the reading item level "
                    "cannot explain: a top parse holds more of every stat simply by "
                    "out-gearing this run."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"{name} rating {ours}",
                    f"sample median {their_median:g}, range {low:g} to {high:g} "
                    f"across {len(theirs)} references",
                    f"share of budget {our_share:.0%} against {their_share:.0%}",
                ),
            )
        )
    return findings
