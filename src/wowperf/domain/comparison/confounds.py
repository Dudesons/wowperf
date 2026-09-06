# ABOUTME: States the differences between two runs that no arithmetic here can correct for.
# ABOUTME: Each is read off a roster, so the fact is measured even where its consequence is not.

from collections import Counter

from wowperf.domain.comparison.reference import Comparability
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player

ITEM_LEVEL_GAP = 5
"""Below this, an item-level difference is noise beside everything else that differs."""


def _mean_item_level(players: tuple[Player, ...]) -> float:
    if not players:
        return 0.0
    return sum(player.item_level for player in players) / len(players)


def _composition(players: tuple[Player, ...]) -> Counter[str]:
    return Counter(f"{player.class_name} {player.spec}" for player in players)


def _augmentation_evokers(players: tuple[Player, ...]) -> tuple[str, ...]:
    return tuple(
        player.name
        for player in players
        if player.class_name == "Evoker" and player.spec == "Augmentation"
    )


def declare_confounds(
    ours: LoadedRun, theirs: LoadedRun, rule: Comparability
) -> list[Finding]:
    """The differences a reader must hold in mind while reading every other finding."""
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
                    "Item level is the only gear difference this tool can see. Tier count, "
                    "trinkets and embellishments are uncorrected, and the Matrix Catalyst "
                    "preserves original secondary stats, so equal item level no longer implies "
                    "a similar stat profile."
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
                detail=(
                    "Group composition changes which packs can be held, which mechanics are "
                    "trivial, and how much damage a route can absorb. It is large and "
                    "uncorrectable, so it is stated rather than adjusted for."
                ),
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
