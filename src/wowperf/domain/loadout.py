# ABOUTME: What a player brought: the items they equipped and the stat ratings those gave them.
# ABOUTME: Pure data with derived readings; imports nothing that performs I/O.

from typing import ClassVar

from wowperf.domain.base import Frozen

TIER_SLOTS = frozenset({0, 2, 4, 6, 9})
"""Head, shoulder, chest, legs and hands, where a tier set sits.

Measured 2026-09-14 across ten players in two reports: the tier set is
class-specific and occupies exactly these five slots, at four or five pieces.
Set 2070 spanned four different classes in slots 12 and 15 and is not tier, so
counting items that share a set id without this rule over-counts. Recorded in
`.claude/skills/wcl-api/SKILL.md` under "Gear and the secondary stat block".
"""


class EquippedItem(Frozen):
    """One item in one slot, as the gear array reports it."""

    item_id: int
    slot: int
    name: str
    item_level: int
    enchant_id: int | None = None
    enchant_name: str | None = None
    set_id: int | None = None


class StatBlock(Frozen):
    """One player's secondary and tertiary stats, as ratings.

    Ratings, never percentages: converting one needs a per-level coefficient
    that has no source in this API, so no caller is given the chance to present
    a percentage this project cannot compute.
    """

    crit: int = 0
    haste: int = 0
    mastery: int = 0
    versatility: int = 0
    leech: int = 0
    avoidance: int = 0
    speed: int = 0

    CHOSEN: ClassVar[frozenset[str]] = frozenset({"crit", "haste", "mastery", "versatility"})
    """The four a player itemises between, as opposed to the three that arrive by chance.

    Leech, avoidance and speed appear on a piece or they do not; nobody builds
    towards them, and measured on report 43HaCNQwPrKqtYgn fight 2 they hold
    between 0% and 10% of a budget while the four below hold the rest. A table
    reports all seven, because a table is a reference and hiding a row a reader
    can see in game would only puzzle them. A finding is a call to act, so it
    is confined to the four a reader can act on.
    """

    def secondaries(self) -> tuple[tuple[str, int], ...]:
        """Every stat as (name, rating), in a fixed order so two blocks line up."""
        return (
            ("crit", self.crit),
            ("haste", self.haste),
            ("mastery", self.mastery),
            ("versatility", self.versatility),
            ("leech", self.leech),
            ("avoidance", self.avoidance),
            ("speed", self.speed),
        )

    def total_secondary(self) -> int:
        """The whole rating budget, which a share is taken against."""
        return sum(rating for _, rating in self.secondaries())


class Loadout(Frozen):
    """What one player equipped, and what it gave them.

    `stats` is None rather than a zeroed `StatBlock` when the log did not offer
    a usable reading: a player whose stats could not be read must not compare
    as a player who has none of every stat.
    """

    items: tuple[EquippedItem, ...] = ()
    stats: StatBlock | None = None

    def item_named(self, name: str) -> EquippedItem | None:
        """The equipped item with this exact name, if any."""
        for item in self.items:
            if item.name == name:
                return item
        return None

    def has_item(self, item_id: int) -> bool:
        return any(item.item_id == item_id for item in self.items)

    def tier_pieces(self) -> int:
        """How many pieces of the tier set this player wore.

        The tier set is whichever set id occupies the most tier slots; a set id
        appearing outside them is some other set and is not counted.
        """
        counts: dict[int, int] = {}
        for item in self.items:
            if item.slot in TIER_SLOTS and item.set_id:
                counts[item.set_id] = counts.get(item.set_id, 0) + 1
        return max(counts.values(), default=0)

    def enchanted_slots(self) -> frozenset[int]:
        return frozenset(item.slot for item in self.items if item.enchant_id)

    def occupied_slots(self) -> frozenset[int]:
        return frozenset(item.slot for item in self.items)
