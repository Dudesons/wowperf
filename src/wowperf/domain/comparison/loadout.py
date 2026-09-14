# ABOUTME: Compares one player's gear and stat ratings against a sample of top parses.
# ABOUTME: Resolves an item-sourced cast to its item, so advice names something pressable.

from collections.abc import Sequence

from wowperf.domain.loadout import EquippedItem, Loadout


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
