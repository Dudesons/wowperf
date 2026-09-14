# ABOUTME: States the differences between two runs that no arithmetic here can correct for.
# ABOUTME: Each is read off a roster, so the fact is measured even where its consequence is not.

from collections import Counter
from collections.abc import Sequence

from wowperf.domain.comparison.reference import Comparability
from wowperf.domain.comparison.sample import SpeedMember, SpeedSample, too_few
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.comparison.tempo import DURATION_WITHHELD_REASON
from wowperf.domain.findings import Confidence, Finding, quantifier_for
from wowperf.domain.model import LoadedRun, Player

ITEM_LEVEL_GAP = 5
"""Below this, an item-level difference is noise beside everything else that differs."""

_COMPOSITION_DETAIL = (
    "Group composition changes which packs can be held, which mechanics are trivial, and how "
    "much damage a route can absorb. It is large and uncorrectable, so it is stated rather "
    "than adjusted for."
)
"""Shared verbatim across every composition finding, so the posture cannot drift between them."""


def _mean_item_level(players: tuple[Player, ...]) -> float:
    if not players:
        return 0.0
    return sum(player.item_level for player in players) / len(players)


def _composition(players: tuple[Player, ...]) -> Counter[str]:
    """Specs counted by the name a player would say out loud: "Augmentation Evoker".

    Spec before class, because that is the order every finding here reads the
    name in and the order the report's own prose uses. Reversing it at the
    point of use would need to split a two-word class ("Death Knight") from a
    two-word spec ("Beast Mastery"), which no whitespace rule can do.
    """
    return Counter(f"{player.spec} {player.class_name}" for player in players)


def _augmentation_evokers(players: tuple[Player, ...]) -> tuple[str, ...]:
    return tuple(
        player.name
        for player in players
        if player.class_name == "Evoker" and player.spec == "Augmentation"
    )


def _article(word: str) -> str:
    """"a" or "an", by the first letter of the word the title is about to name."""
    return "an" if word[:1].upper() in "AEIOU" else "a"


def declare_confounds(ours: LoadedRun, theirs: SpeedMember, rule: Comparability) -> list[Finding]:
    """The differences a reader must hold in mind while reading every other finding.

    The below-floor branch of `declare_confounds_sample` delegates to this when
    a sample has too few members to state a statistic.
    """
    findings: list[Finding] = []
    our_players = ours.run.players
    their_players = theirs.run.players

    augmenters = _augmentation_evokers(our_players) + _augmentation_evokers(their_players)
    if augmenters:
        findings.append(
            Finding(
                id="compare.confound.augmentation",
                title="An Augmentation Evoker makes per-player damage attribution unreliable",
                detail=(
                    "Blizzard's support-attribution hooks are documented as faulty: throughput "
                    "debuffs go unaccounted, reattribution can subtract damage, and shared "
                    "health pools generate duplicate events. This cannot be corrected here, so "
                    "treat every per-player damage figure in this report as approximate."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=tuple(f"{name} is an Augmentation Evoker" for name in augmenters),
            )
        )

    if not rule.durations_comparable:
        findings.append(
            Finding(
                id="compare.confound.keystone_level",
                title=f"The reference is a +{rule.their_level} and this run is a +{rule.our_level}",
                detail=rule.withheld_because(),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"ours +{rule.our_level}",
                    f"theirs +{rule.their_level}",
                    "route, deaths, interrupts and downtime remain comparable",
                ),
            )
        )

    our_ilvl = _mean_item_level(our_players)
    their_ilvl = _mean_item_level(their_players)
    if our_players and their_players and abs(their_ilvl - our_ilvl) >= ITEM_LEVEL_GAP:
        findings.append(
            Finding(
                id="compare.confound.item_level",
                title=(
                    f"The reference group averages {their_ilvl:.0f} item level against our "
                    f"{our_ilvl:.0f}"
                ),
                detail=(
                    "Item level is no longer the only gear difference this tool can see: a "
                    "bare enchant slot and tier count each raise their own finding, and the "
                    "secondary-stat comparison reports each rating directly, catching what the "
                    "Matrix Catalyst hides behind an unchanged item level. An item the "
                    "references wore and this player does not own is deliberately not "
                    "reported, because it is not a difference the player can act on. "
                    "Embellishments are not compared, and the aggregate throughput effect of "
                    "better gear remains uncorrected outside those findings."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(f"ours {our_ilvl:.1f}", f"theirs {their_ilvl:.1f}"),
            )
        )

    ours_comp = _composition(our_players)
    theirs_comp = _composition(their_players)
    if our_players and their_players and ours_comp != theirs_comp:
        only_theirs = theirs_comp - ours_comp
        only_ours = ours_comp - theirs_comp
        findings.append(
            Finding(
                id="compare.confound.composition",
                title="The two groups were not the same composition",
                detail=_COMPOSITION_DETAIL,
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    "only theirs: " + (", ".join(sorted(only_theirs.elements())) or "none"),
                    "only ours: " + (", ".join(sorted(only_ours.elements())) or "none"),
                ),
            )
        )

    our_affixes = set(ours.run.affix_ids)
    their_affixes = set(theirs.run.affix_ids)
    if our_affixes != their_affixes:
        names: dict[int, str] = {}
        for run in (ours.run, theirs.run):
            if run.affix_names:
                names.update(zip(run.affix_ids, run.affix_names, strict=True))

        def named(ids: set[int]) -> str:
            return ", ".join(names.get(i, str(i)) for i in sorted(ids)) or "none"

        findings.append(
            Finding(
                id="compare.confound.affixes",
                title="The two runs were not on the same affixes",
                detail=(
                    "An affix changes which packs are dangerous and how long a boss lives. "
                    "Requiring the same affixes would usually leave nothing to compare "
                    "against, so the difference is stated rather than filtered on."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"only ours: {named(our_affixes - their_affixes)}",
                    f"only theirs: {named(their_affixes - our_affixes)}",
                ),
            )
        )

    return findings


def declare_confounds_sample(ours: LoadedRun, sample: SpeedSample) -> list[Finding]:
    """The confounds a sample of fast runs raises, aggregated where the floor allows it.

    An empty sample means there was nothing to compare against at all;
    `service.compare()` already says so once, as `compare.speed.unavailable`, so
    returning nothing here avoids repeating that finding for a comparison that
    never ran. Below the floor, only one reference's confounds can honestly be
    counted, so this falls back to the pairwise `declare_confounds`, the same
    way `compare_route_sample` and `compare_tempo_sample` fall back to their
    own pairwise functions.
    """
    if not sample.members:
        return []

    if not sample.can_aggregate(sample.members):
        first = sample.members[0]
        return too_few(declare_confounds(ours, first, first.comparability), len(sample.members))

    members = sample.members
    findings: list[Finding] = []

    augmentation = _confound_augmentation(ours, members)
    if augmentation is not None:
        findings.append(augmentation)

    keystone = _confound_keystone_level(sample)
    if keystone is not None:
        findings.append(keystone)

    item_level = _confound_item_level(ours, members)
    if item_level is not None:
        findings.append(item_level)

    composition = _confound_composition(ours, members)
    if composition is not None:
        findings.append(composition)

    affixes = _confound_affixes(ours, members)
    if affixes is not None:
        findings.append(affixes)

    return findings


def _confound_augmentation(ours: LoadedRun, members: Sequence[SpeedMember]) -> Finding | None:
    """One Augmentation Evoker anywhere is enough: the claim is about attribution being
    unreliable, not about how many rosters carried the class."""
    our_augmenters = _augmentation_evokers(ours.run.players)
    rosters_with_one = sum(1 for member in members if _augmentation_evokers(member.run.players))
    if not our_augmenters and rosters_with_one == 0:
        return None

    total = len(members)
    return Finding(
        id="compare.confound.augmentation",
        title="An Augmentation Evoker makes per-player damage attribution unreliable",
        detail=(
            "Blizzard's support-attribution hooks are documented as faulty: throughput "
            "debuffs go unaccounted, reattribution can subtract damage, and shared health "
            "pools generate duplicate events. This cannot be corrected here, so treat every "
            "per-player damage figure in this report as approximate."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(
            *(f"{name} is an Augmentation Evoker" for name in our_augmenters),
            f"{count_phrase(rosters_with_one, total)} fast run rosters contained an "
            "Augmentation Evoker",
        ),
    )


def _confound_keystone_level(sample: SpeedSample) -> Finding | None:
    """Members off our keystone level, counted the way `compare.duration` already excludes them."""
    total = len(sample.members)
    off_level = total - len(sample.duration_eligible)
    if off_level == 0:
        return None

    return Finding(
        id="compare.confound.keystone_level",
        title=f"{count_phrase(off_level, total)} fast runs were at a different keystone level",
        detail=DURATION_WITHHELD_REASON,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(
            f"{off_level} of {total} references were at a different keystone level",
            "route, deaths, interrupts and downtime remain comparable",
        ),
        quantifier=quantifier_for(off_level, total),
    )


def _confound_item_level(ours: LoadedRun, members: Sequence[SpeedMember]) -> Finding | None:
    """Our mean item level against the median of each member's own roster mean.

    A per-member mean feeds the median, never a mean pooled across every player
    in the sample: pooling would let a five-player reference outweigh a
    four-player one for no gearing reason.
    """
    # All-or-nothing, unlike route_eligible/duration_eligible, which drop a single
    # ineligible member and keep the rest: the title and evidence below name the
    # statistic against `len(members)` fast runs, so quietly excluding the one with an
    # empty roster and computing the median over what remains would have the title claim
    # more runs than the statistic was actually drawn from.
    if not ours.run.players or any(not member.run.players for member in members):
        return None

    our_ilvl = _mean_item_level(ours.run.players)
    group_means = [_mean_item_level(member.run.players) for member in members]
    their_median = median(group_means)
    if abs(their_median - our_ilvl) < ITEM_LEVEL_GAP:
        return None

    low, high = observed_range(group_means)
    total = len(members)
    return Finding(
        id="compare.confound.item_level",
        title=(
            f"Our group averages {our_ilvl:.0f} item level; the median of {total} fast runs "
            f"is {their_median:.0f}"
        ),
        detail=(
            "Item level is no longer the only gear difference this tool can see: a bare "
            "enchant slot and tier count each raise their own finding, and the secondary-stat "
            "comparison reports each rating directly, catching what the Matrix Catalyst hides "
            "behind an unchanged item level. An item the references wore and this player does "
            "not own is deliberately not reported, because it is not a difference the player "
            "can act on. Embellishments are not compared, and the aggregate throughput effect "
            "of better gear remains uncorrected outside those findings."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            f"ours {our_ilvl:.1f}",
            f"median {their_median:.1f}",
            f"range {low:.1f} to {high:.1f}",
        ),
    )


def _confound_composition(ours: LoadedRun, members: Sequence[SpeedMember]) -> Finding | None:
    """Specs the fast runs brought that we did not, counted per spec across the sample.

    Only specs absent from our own roster are counted or named: the finding
    states what the fast runs had that we lacked, and stops there. When
    nothing is absent from ours, the two groups may still disagree on how many
    of a spec each fielded; that difference falls back to the pairwise title,
    unranked, because no single spec led it.
    """
    our_comp = _composition(ours.run.players)
    our_specs = set(our_comp)
    total = len(members)

    member_comps = [_composition(member.run.players) for member in members]
    absent_counts: Counter[str] = Counter()
    for comp in member_comps:
        absent_counts.update(spec for spec in comp if spec not in our_specs)

    if absent_counts:
        ranked = sorted(absent_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        top_spec, top_count = ranked[0]
        all_member_specs: set[str] = set()
        for comp in member_comps:
            all_member_specs.update(comp)
        # A plain set difference, unlike the pairwise Counter difference in
        # `declare_confounds`: there is no single "their count" for a spec to subtract
        # against many rosters, so this can only say a spec was absent from every member,
        # never by how many copies our own roster exceeded it.
        only_ours = our_specs - all_member_specs

        return Finding(
            id="compare.confound.composition",
            title=(
                f"{count_phrase(top_count, total)} fast runs brought {_article(top_spec)} "
                f"{top_spec}; your group did not"
            ),
            detail=_COMPOSITION_DETAIL,
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            evidence=(
                *(f"{spec}: {count_phrase(count, total)}" for spec, count in ranked),
                "only ours: " + (", ".join(sorted(only_ours)) or "none"),
            ),
            quantifier=quantifier_for(top_count, total),
        )

    differing = sum(1 for comp in member_comps if comp != our_comp)
    if differing:
        return Finding(
            id="compare.confound.composition",
            title="The two groups were not the same composition",
            detail=_COMPOSITION_DETAIL,
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            evidence=(
                f"{count_phrase(differing, total)} fast run rosters differed from ours in "
                "spec count",
            ),
        )

    return None


def _confound_affixes(ours: LoadedRun, members: Sequence[SpeedMember]) -> Finding | None:
    """How many of the sample ran the same affix set as us, never the affixes we lacked.

    An affix set is compared whole, not per affix: two runs sharing three of
    four affixes still faced a materially different dungeon.
    """
    our_affixes = set(ours.run.affix_ids)
    total = len(members)
    matching = sum(1 for member in members if set(member.run.affix_ids) == our_affixes)
    if matching >= total:
        return None

    return Finding(
        id="compare.confound.affixes",
        title=f"{count_phrase(matching, total)} fast runs ran your affix set",
        detail=(
            "An affix changes which packs are dangerous and how long a boss lives. Requiring "
            "the same affixes would usually leave nothing to compare against, so the "
            "difference is stated rather than filtered on."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(f"{matching} of {total} fast runs shared our affix set",),
        quantifier=quantifier_for(matching, total),
    )
