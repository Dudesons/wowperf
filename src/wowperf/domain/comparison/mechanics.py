# ABOUTME: The per-ability landing profile of one fight, and how two of them compare.
# ABOUTME: Landings only -- the table's damage is mitigated and cannot meet the event stream's.

from wowperf.domain.base import Frozen


class AbilityTakenRow(Frozen):
    """One ability's damage-taken row, as `viewBy: Ability` reports it.

    Damage is deliberately absent. The table's `total` is mitigated -- it
    equals the event stream's health damage plus absorbs -- and the
    unmitigated figure `players.damage.*` ranks on is not exposed and not
    reconstructible. Carrying both would put two figures for one ability on
    one page, measured up to 4.61x apart on a real fight, with nothing a
    reader could reconcile them by.
    """

    ability_id: int
    ability_name: str
    hit_count: int = 0
    tick_count: int = 0
    miss_count: int = 0
    tick_miss_count: int = 0
    # Each source's `type`, verbatim: "Boss", "NPC" or "Pet" for a hostile
    # source, a class name for a player. Empty on a row whose sources array
    # was empty, which was observed carrying a miss count and no damage.
    source_types: tuple[str, ...] = ()

    @property
    def landings(self) -> int:
        """How many times this ability actually landed.

        No single field counts this. Measured 2026-09-14: hits, ticks, misses
        and tick misses summed over one fight's 26 rows equalled the event
        count exactly, so hits plus ticks is what landed and the two miss
        counts are what did not.
        """
        return self.hit_count + self.tick_count
