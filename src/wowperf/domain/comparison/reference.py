# ABOUTME: What a reference run is, and which comparisons a keystone-level gap invalidates.
# ABOUTME: Pure value objects; fetching a reference is an adapter's job, not this module's.

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.base import Frozen
from wowperf.domain.model import LoadedRun

MAX_LEVEL_GAP = 1
"""A reference further than this from our keystone level is not offered at all.

Two levels of enemy health is roughly a fifth more, which changes which packs a
group can hold together, not merely how long each one takes.
"""


class SpeedRow(Frozen):
    """One row of the speed leaderboard, in this project's vocabulary."""

    report_code: str
    fight_id: int
    keystone_level: int
    duration_ms: int
    deaths: int
    affix_ids: tuple[int, ...] = ()
    score: float = 0.0
    medal: str = ""
    # "Class Spec" per player, in the order the leaderboard listed them.
    team: tuple[str, ...] = ()

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000


class ParseRow(Frozen):
    """One row of a specialisation's score leaderboard."""

    report_code: str
    fight_id: int
    keystone_level: int
    duration_ms: int
    character_name: str
    class_name: str
    spec: str
    affix_ids: tuple[int, ...] = ()
    score: float = 0.0
    medal: str = ""

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000


class SpeedReference(Frozen):
    """A speed leaderboard row together with the run it points at."""

    row: SpeedRow
    loaded: LoadedRun


class ParseReference(Frozen):
    """A score leaderboard row together with the run it points at."""

    row: ParseRow
    loaded: LoadedRun
    # Absent is a real state, not a failure: `compare.uptime.unavailable` reports it.
    auras: PlayerAuras | None = None


class Comparability(Frozen):
    """Which comparisons survive the gap between two keystone levels.

    Enemy health scales about 10% a level and compounds, so anything shaped like
    a duration means something different on each side of a gap. Pull
    composition, pull order, packs skipped, death counts, missed interrupts and
    between-pull downtime do not depend on how much health a mob had.
    """

    our_level: int
    their_level: int

    @property
    def level_gap(self) -> int:
        return self.their_level - self.our_level

    @property
    def durations_comparable(self) -> bool:
        return self.level_gap == 0

    def withheld_because(self) -> str:
        """The sentence a reader gets in place of a number we refuse to print."""
        return (
            f"The reference is a +{self.their_level} and this run is a +{self.our_level}. "
            "Enemy health scales about 10% a keystone level and compounds, so pull "
            "durations and kill times are not comparable and are not shown."
        )
