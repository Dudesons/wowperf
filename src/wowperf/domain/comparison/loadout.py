# ABOUTME: Compares one player's gear and stat ratings against a sample of top parses.
# ABOUTME: Resolves an item-sourced cast to its item, so advice names something pressable.

from collections.abc import Sequence

from wowperf.domain.comparison.measures import StatShare, Verdict
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, ParseMember, find_player
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.findings import Confidence, Finding, quantifier_for, quantity
from wowperf.domain.loadout import TIER_SLOTS, EquippedItem, Loadout, StatBlock
from wowperf.domain.season import SlotNames

NO_SLOT_NAMES = SlotNames()
"""The default for every caller that has not loaded the slot-name data file.

`name_for` falls back to the raw index for every slot with an empty table, so
a caller without it still gets a usable, if unnamed, title.
"""


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
        player = find_player(member.run.players, member.row.character_name)
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


def _enchant_target(slot: int, slot_names: SlotNames) -> str:
    """The slot's name, phrased for "enchanted ...".

    A named slot reads naturally with an article in front of it --
    "enchanted the feet". The "slot N" fallback that `SlotNames.name_for`
    gives the two unidentified slots keeps its own phrasing instead:
    "enchanted the slot 3" would read as a mistake, not as a slot with no
    name.

    A name shared by more than one slot -- the two rings, the two trinkets --
    would otherwise produce two byte-identical titles for two different
    slots, and `mplus-analysis` tells a reader to find a finding by echoing
    its title. The slot index rides alongside the name for exactly those
    slots, carried generically off `SlotNames.is_ambiguous` rather than
    special-cased to rings: which ring is "left" and which is "right" is not
    something the measurement this table comes from can answer, so nothing
    here guesses at it.
    """
    name = slot_names.name_for(slot)
    if name == f"slot {slot}":
        return name
    if slot_names.is_ambiguous(slot):
        return f"the {name} (slot {slot})"
    return f"the {name}"


def compare_enchants(
    our_loadout: Loadout | None,
    their_loadouts: Sequence[Loadout],
    our_name: str,
    slot_names: SlotNames = NO_SLOT_NAMES,
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

    `slot_names` names the slot in the title, for a reader who must know
    where to act without knowing that slot 7 is feet. Two slots, 3 and 17,
    were never identified; `SlotNames.name_for` falls back to the raw index
    for those rather than guessing, and the default empty `SlotNames` falls
    back for every slot, which is what every caller that has not loaded the
    data file gets.
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
                    f"enchanted {_enchant_target(slot, slot_names)}; {our_name} did not"
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
                f"{ours} tier pieces, counted across slots {sorted(TIER_SLOTS)}",
                f"sample median {their_median:g}, range {low:g} to {high:g} "
                f"across {len(their_loadouts)} references",
            ),
        )
    ]


STAT_GAP_BEYOND_RANGE = 0.02
"""How far past the sample's own range a share must sit before it is worth a finding.

Replaces a flat fifteen-point gap from the median, which never fired on real
data and could not have. Measured 2026-09-14 across five players on report
43HaCNQwPrKqtYgn fight 2: within one specialisation the references' own shares
already span between 3.3 and 33.9 points, median 13.5. The old constant was
about the width of a typical range, so clearing it meant sitting outside where
every top parse of the specialisation had ever sat, twice over.

So the bar is the sample's range, not a constant: outside it, no reference
chose what this player chose, which is a claim the sample supports on its own
terms and the same one the card's table draws. The two agree by construction,
because both read `stat_measures`.

The two points are a floor on top of that, and they are what the range alone
cannot supply. Where every reference happens to land on the same share the
range collapses to a point, and a player a single point away is then "outside"
it. On the same five players the gaps beyond the range were 0.6, 0.7, 2.0,
2.2, 4.0 and 4.6 points; a floor here drops the first two, which are a player
sitting on the edge, and keeps the rest, which are a different choice.
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

    Built from `stat_measures`, the same measurements the card's stat table
    draws, so a row the table calls level can never also be a finding: the two
    would then be two answers to one question on one page.
    """
    findings = []
    for measure in stat_measures(our_loadout, their_loadouts):
        # A table is a reference and reports all seven stats. A finding is a
        # call to act, and leech, avoidance and speed are not chosen.
        if measure.name not in StatBlock.CHOSEN:
            continue
        # The title says "carried N rating; the sample's median is M". Where
        # those two numbers are the same it contradicts itself, whatever the
        # shares have done -- and they can diverge sharply while the ratings
        # coincide, because the share's denominator is the whole budget. The
        # table still carries the row and still calls the share what it is;
        # a finding that cannot state its own claim in its title does not.
        if measure.our_rating == measure.their_median_rating:
            continue
        share_low, share_high = observed_range(measure.their_shares)
        beyond = max(share_low - measure.ours, measure.ours - share_high, 0.0)
        if beyond < STAT_GAP_BEYOND_RANGE:
            continue

        name = measure.name
        ours = measure.our_rating
        their_median = measure.their_median_rating
        our_share = measure.ours
        their_share = measure.their_median
        theirs = measure.their_ratings
        low, high = observed_range(measure.their_ratings)
        findings.append(
            Finding(
                # The stat name is folded in before `_for_player` appends the
                # per-player suffix, the same way `compare_enchants` folds in
                # the slot and `compare_consumable_buffs` folds in the
                # category: a real gear difference routinely moves more than
                # one secondary's share past the gap at once, and two rows
                # minting the same id would collide into one page element id.
                # Every name comes from `StatBlock.secondaries()`, a fixed,
                # lowercase, space-free list, so it needs no `player_slug()`
                # folding first.
                id=f"compare.stats.rating.{name}",
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


def _share_of(stats: StatBlock, name: str) -> float:
    budget = stats.total_secondary()
    return dict(stats.secondaries())[name] / budget if budget else 0.0


def _readable_as_shares(stats: StatBlock) -> bool:
    """Whether this block can be read as shares of a budget at all.

    Measured 2026-09-14 on report 43HaCNQwPrKqtYgn fight 2: one reference came
    back from `combatantInfo` with a **negative** versatility rating, which put
    a share of -1.8% into an observed range. A share of a budget cannot be
    negative, so whatever that block records, it is not the thing this reads it
    as -- and the negative also shrinks the block's own budget, so every other
    share on it is off too.

    The damage is not cosmetic. A negative drags the low bound of the range
    down, and a player genuinely below every sound reference then lands inside
    it and reads as level. Discarding the block is the same withholding
    `build_loadouts` already does for a stat block whose readings disagree with
    each other: a reading that cannot mean what it says is not evidence.
    """
    return all(rating >= 0 for _, rating in stats.secondaries())


def stat_measures(
    our_loadout: Loadout | None, their_loadouts: Sequence[Loadout]
) -> tuple[StatShare, ...]:
    """Each secondary's share of the budget against the sample's, for the table.

    The verdict is the share's position against the **observed range** of the
    sample's own shares, not a gap somebody chose. Two reasons. A fixed
    threshold cannot tell a real difference from an unremarkable one, because
    what counts as a difference depends on how far the references themselves
    disagree -- the same figure means both things against two samples. And
    every threshold this area has carried so far was a guess: `STAT_GAP_SHARE`
    is fifteen percentage points of a player's own budget, which two players of
    one specialisation essentially never reach, which is why the finding beside
    this has never fired on real data.

    Inside the range reads as level, and honestly so: the reader sits where top
    parses of their own specialisation already sit. Outside it is a claim the
    sample supports on its own terms -- no reference chose what this player
    chose.

    Rows keep `secondaries()` order rather than sorting by the widest gap the
    way the cast tables do. A balance is read down a column, and a reader
    comparing two cards wants crit in the same place on both.
    """
    if our_loadout is None or our_loadout.stats is None:
        return ()
    if not _readable_as_shares(our_loadout.stats):
        return ()
    # The floor counts blocks that can be read, not blocks that were fetched:
    # discarding the unreadable ones first is what stops a sample of one
    # arguing from a range it drew on its own.
    theirs = [
        loadout.stats
        for loadout in their_loadouts
        if loadout.stats is not None and _readable_as_shares(loadout.stats)
    ]
    if len(theirs) < MIN_SAMPLE_FOR_AGGREGATE:
        return ()
    our_budget = our_loadout.stats.total_secondary()
    if not our_budget:
        return ()

    measures = []
    for name, our_rating in our_loadout.stats.secondaries():
        shares = [_share_of(stats, name) for stats in theirs]
        ratings = [float(dict(stats.secondaries())[name]) for stats in theirs]
        their_median_share = median(shares)
        # Leech, avoidance and speed are zero on most gear. A row reading 0%
        # against 0% is noise in a table whose whole job is to be read across
        # at a glance.
        if our_rating == 0 and their_median_share == 0.0:
            continue
        our_share = our_rating / our_budget
        low, high = observed_range(shares)
        if our_share > high:
            verdict = Verdict.ABOVE
        elif our_share < low:
            verdict = Verdict.BELOW
        else:
            verdict = Verdict.LEVEL
        measures.append(
            StatShare(
                name=name,
                ours=our_share,
                their_median=their_median_share,
                their_shares=tuple(shares),
                our_rating=our_rating,
                their_median_rating=median(ratings),
                their_ratings=tuple(ratings),
                verdict=verdict,
            )
        )
    return tuple(measures)
