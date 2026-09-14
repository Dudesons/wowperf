# ABOUTME: Compares what a player drank before a pull against what the sample drank.
# ABOUTME: An absent aura table is unknown, never a player who drank nothing.

from collections.abc import Sequence

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, ParseSample
from wowperf.domain.comparison.statistics import count_phrase
from wowperf.domain.findings import Confidence, Finding, quantifier_for
from wowperf.domain.season import ConsumableBuffs
from wowperf.domain.slug import player_slug


def _carries(auras: PlayerAuras, ability_ids: Sequence[int]) -> bool:
    """Whether any id in this category was on the player at all.

    Any id, because a category is the unit: `Well Fed` spans six ability ids
    measured 2026-09-14, and which of them a player drank is not the question
    the finding asks.
    """
    wanted = frozenset(ability_ids)
    return any(aura.ability_id in wanted for aura in auras.on_self)


def compare_consumable_buffs(
    our_auras: PlayerAuras | None,
    our_name: str,
    sample: ParseSample,
    buffs: ConsumableBuffs,
) -> list[Finding]:
    """Consumable categories every comparable reference carried and this player did not.

    A member whose aura table was never fetched is left out of the count
    entirely rather than counted as lacking the buff — `ParseSample.aura_eligible`
    is what draws that line, and `compare.uptime.unavailable` already reports
    the absence once.
    """
    if our_auras is None:
        return []
    eligible = [member for member in sample.aura_eligible if member.auras is not None]
    if len(eligible) < MIN_SAMPLE_FOR_AGGREGATE:
        return []

    findings = []
    for category in buffs.categories():
        ability_ids = buffs.ids_for(category)
        if not ability_ids or _carries(our_auras, ability_ids):
            continue
        matching = sum(
            1
            for member in eligible
            if member.auras is not None and _carries(member.auras, ability_ids)
        )
        if matching < len(eligible):
            continue
        findings.append(
            Finding(
                # The category is folded in before `_for_player` appends the
                # per-player suffix, the same way `compare.uptime.self.<rank>`
                # keeps two auras from minting the same id: two categories a
                # player missed must not collide into one page element id.
                # `player_slug` is this codebase's one slugger for anything
                # that becomes an HTML id, not only a player name -- see its
                # own docstring -- and a category can hold a space
                # ("augment rune") that a raw id must not carry.
                id=f"compare.consumables.buff.{player_slug(category)}",
                title=(
                    f"{count_phrase(matching, len(eligible))} top parses carried a "
                    f"{category}; {our_name} did not"
                ),
                detail=(
                    f"No {category} buff appears on this player at any point in the run, and "
                    "every comparable reference carried one. What it was worth in damage is "
                    "not stated: nothing here can compute that."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"category {category}, {len(ability_ids)} known ability ids",
                    f"{matching} of {len(eligible)} references carried one",
                ),
                quantifier=quantifier_for(matching, len(eligible)),
            )
        )
    return findings
