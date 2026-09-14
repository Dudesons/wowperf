# ABOUTME: The phrases a cast-rate or uptime sentence differs by, between a dungeon and a raid.
# ABOUTME: One named field per slot, never a bare scope string: a scope is a str, and so is a lie.

from wowperf.domain.base import Frozen


class Wording(Frozen):
    """What the spell and uptime sentences say about the stretch they measured.

    The comparisons under `spells.py` and `uptime.py` serve both axes and state
    the same judgements about either, but not in the same words: a dungeon
    measures boss pulls out of a longer run, and a raid fight measures the
    fight, which has no trash beside it and no keystone level above it. Every
    sentence that names one of those is built from a field here.

    A field per slot rather than one `scope: str` the way `compare_mechanics`
    takes one. Plan 2's rulings record that a scope shipped a false sentence,
    because a scope is a `str` and so is every other string a caller can pass;
    naming each slot is what makes a mismatch visible at the two instances
    below, which sit side by side so a reader can hold them against each other.

    Nothing here is interpolated into a number, and nothing here carries a
    judgement: these are the nouns and the hedges, and every figure beside them
    is computed elsewhere.
    """

    both_sides: str
    """What an availability sentence says the comparison needs on both sides."""

    over: str
    """What an evidence line's seconds were seconds of: "ours over 180s of ...."."""

    theirs_across: str
    """The same, possessive: "12 casts across 240s of ...."."""

    absent_from: str
    """Where an aura the sample carried was not seen: "absent from ...."."""

    rate_basis: str
    """What a per-minute rate, or a share of time, is measured against."""

    on_stretch: str
    """Where a title says a count or a rate was counted: "cast it 12 times ...."."""

    stretch_time: str
    """The denominator of a share, as a title or a fact names it: "46% of ...."."""

    reference_noun: str
    """What one reference is counted in, as a bare noun: "1 reference ....".

    The only bare noun here, and it has to be one: the slot counts a thing,
    where every field above names a stretch or hedges a claim. `run` next to it
    is the demonstrative -- "this run", "this fight" -- and reads "1 reference
    this fight" in this slot, which is why the two are separate fields rather
    than one doing both jobs.
    """

    run: str
    """The whole of our own side, as a detail sentence names it."""

    our_stretch: str
    """The whole of our own side, as an evidence line names it."""

    nowhere_else: str
    """The clause listing the other places an ability could have been cast and was not.

    Empty on an axis with no other place: a raid fight has no trash beside it,
    and a sentence offering to have looked there would be describing a search
    that never happened.
    """

    same_stretch_pairwise: str
    """Why the two sides' rates are comparable at all, against one reference."""

    same_stretch_sample: str
    """The same, against a sample."""

    rate_hedge: str
    """What could widen a rate gap without anybody having done anything."""

    above_hedge: str
    """The same, for a rate above the sample's rather than below it."""

    uptime_hedge: str
    """What could widen an uptime gap without anybody having done anything."""


DUNGEON = Wording(
    both_sides="boss pulls",
    over="boss pulls",
    theirs_across="their boss pulls",
    absent_from="our own boss pulls",
    rate_basis="boss-pull time",
    on_stretch="on bosses",
    stretch_time="boss time",
    reference_noun="run",
    run="this run",
    our_stretch="our run",
    nowhere_else=" — not on bosses and not on trash",
    same_stretch_pairwise=(
        "which is the one stretch of a dungeon where two runs fought the same encounter."
    ),
    same_stretch_sample=(
        "which is the one stretch of a dungeon where every run fought the same encounter."
    ),
    rate_hedge=(
        "A longer fight at a higher key changes how many cooldowns fit, so treat a small "
        "gap as noise."
    ),
    above_hedge=(
        "A defensive, a taunt or a movement button pressed more often may simply be what "
        "the run demanded, and a longer or harder key asks for more of them."
    ),
    uptime_hedge=(
        "A shorter fight at a different keystone level still changes what fits, so read a "
        "narrow gap as noise."
    ),
)
"""A Mythic+ run, where the comparable stretch is the boss pulls inside a longer route."""

RAID = Wording(
    both_sides="fight time",
    over="the fight",
    theirs_across="their fight",
    absent_from="our own fight",
    rate_basis="fight time",
    # "on this encounter" and not "in this fight": the same phrase has to be
    # true of our side and of every reference's, and a reference fought its own
    # fight, not this one. Not "on this boss" either -- the raid counting rule
    # counts every cast of the fight, adds included, so a phrase naming the
    # boss as the target would claim a scoping the measurement did not do.
    on_stretch="on this encounter",
    stretch_time="fight time",
    reference_noun="fight",
    run="this fight",
    our_stretch="this fight",
    nowhere_else="",
    same_stretch_pairwise=(
        "which is the whole of one boss fight and the same encounter on both sides."
    ),
    same_stretch_sample=(
        "which is the whole of one boss fight and the same encounter in every kill compared."
    ),
    rate_hedge="A longer attempt changes how many cooldowns fit, so treat a small gap as noise.",
    above_hedge=(
        "A defensive, a taunt or a movement button pressed more often may simply be what "
        "the fight demanded, and a longer or harder attempt asks for more of them."
    ),
    uptime_hedge="A shorter attempt still changes what fits, so read a narrow gap as noise.",
)
"""A raid boss fight, where the comparable stretch is the fight and there is nothing beside it."""
