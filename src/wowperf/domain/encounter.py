# ABOUTME: One raid boss fight as a structure: who was there, how long it ran, whether it died.
# ABOUTME: A sibling of Run, not a subtype of it; it holds no keystone vocabulary at all.

from collections.abc import Mapping
from types import MappingProxyType

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.raid_reference import ReportRankings
from wowperf.domain.events import (
    CastEvent,
    DamageTakenEvent,
    Death,
    EnemyCastRow,
    HealingEvent,
    HealthSample,
    InterruptEvent,
    Resurrection,
)
from wowperf.domain.model import DamageDoneSeries, Player


class Encounter(Frozen):
    """One boss fight. Carries no pulls: a raid fight has none to carry.

    `fight_percentage` is the boss health remaining when the attempt ended, as
    Warcraft Logs reports it, and is None where the report does not say. A kill
    reports about 0.01 rather than 0, which is why `outcome` reads `kill`
    rather than comparing the percentage against zero.
    """

    report_code: str
    fight_id: int
    encounter_id: int
    boss_name: str
    difficulty: int
    partition: int
    size: int
    kill: bool
    fight_percentage: float | None = None
    start_ms: int
    end_ms: int
    owner_name: str | None = None
    players: tuple[Player, ...]

    @property
    def duration_seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000

    @property
    def outcome(self) -> str:
        """How the attempt ended, in the words the report and the findings use."""
        if self.kill:
            return "killed"
        if self.fight_percentage is None:
            return "wiped"
        return f"wiped at {self.fight_percentage:.1f}%"


class LoadedEncounter(Frozen):
    """Everything fetched about one boss fight. Pure data -- no adapter may leak in."""

    encounter: Encounter
    casts: tuple[CastEvent, ...] = ()
    deaths: tuple[Death, ...] = ()
    enemy_cast_rows: tuple[EnemyCastRow, ...] = ()
    interrupts: tuple[InterruptEvent, ...] = ()
    damage_taken: tuple[DamageTakenEvent, ...] = ()
    damage_done: tuple[DamageDoneSeries, ...] = ()
    health_samples: tuple[HealthSample, ...] = ()
    healing: tuple[HealingEvent, ...] = ()
    resurrections: tuple[Resurrection, ...] = ()
    ability_icons: tuple[tuple[int, str], ...] = ()
    auras: tuple[PlayerAuras, ...] = ()
    # The report's own rankings row, read once and kept here rather than
    # re-fetched: `standing` is `playerMetric: dps`, `boss_standing` is
    # `playerMetric: bossdps`. Each is `None` where its own query returned no
    # row, which is what a wipe does -- design section 14 item 7, measured
    # 2026-09-14.
    standing: ReportRankings | None = None
    boss_standing: ReportRankings | None = None
    # "report rankings" when `standing` supplied the partition,
    # "data/season.toml" when it did not.
    partition_source: str = ""

    @property
    def ability_icon_map(self) -> Mapping[int, str]:
        """Icon file names by ability game id, as a read-only mapping."""
        return MappingProxyType(dict(self.ability_icons))

    @property
    def auras_by_actor(self) -> Mapping[int, PlayerAuras]:
        """Buff bands by actor id, as a read-only mapping."""
        return MappingProxyType({one.actor_id: one for one in self.auras})
