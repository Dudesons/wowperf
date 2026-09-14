# ABOUTME: Compares one player's gear and stat ratings against a sample of top parses.
# ABOUTME: Resolves an item-sourced cast to its item, so advice names something pressable.

from collections.abc import Sequence

from wowperf.domain.comparison.sample import ParseMember, find_player
from wowperf.domain.loadout import EquippedItem, Loadout


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
