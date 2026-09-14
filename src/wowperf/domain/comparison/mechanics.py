# ABOUTME: The per-ability landing profile of one fight, and how two of them compare.
# ABOUTME: Landings only -- the table's damage is mitigated and cannot meet the event stream's.

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.sample import SAMPLE_SIZE


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


class ReferenceKillRow(Frozen):
    """One kill from the `execution` leaderboard, as a reference candidate.

    Carries no keystone level, no bracket and no affixes: a boss fight has
    none of them, and a row that cannot express a keystone level cannot be
    handed to a Mythic+ comparison by accident.
    """

    report_code: str
    fight_id: int
    difficulty: int
    size: int
    duration_ms: int
    deaths: int = 0

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000


def select_reference_kills(
    rows: tuple[ReferenceKillRow, ...],
    *,
    our_size: int,
    our_difficulty: int,
    limit: int = SAMPLE_SIZE,
) -> tuple[ReferenceKillRow, ...]:
    """References comparable to our own fight, in leaderboard order.

    Both filters refuse rather than annotate. Difficulty because the master
    design already refuses a cross-difficulty comparison outright. Size because
    this comparison is a landing rate over a whole raid: measured 2026-09-14, a
    single page spanned 14 to 30 against our 20, and a 30-player reference
    reports half again as many landings for headcount alone. A page holds
    fifty rows, so matching exactly usually leaves plenty.
    """
    matching = [
        row for row in rows if row.size == our_size and row.difficulty == our_difficulty
    ]
    return tuple(matching[:limit])
