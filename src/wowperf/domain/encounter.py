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
from wowperf.domain.phases import Phase, PhaseTransition


class Encounter(Frozen):
    """One boss fight. Carries no pulls: a raid fight has none to carry.

    `fight_percentage` is the *encounter's* progress remaining when the attempt
    ended, as Warcraft Logs reports it, and is None where the report does not
    say. It is not boss health: `boss_percentage` below is, and the two diverge
    by 3 to 8 points on most attempts of the one night measured. A kill reports
    about 0.01 rather than 0, which is why `outcome` reads `kill` rather than
    comparing the percentage against zero.
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
    # `fightPercentage` is the encounter's own progress and `bossPercentage` is
    # the boss's health; they diverge sharply -- one measured attempt read 51.12
    # against 3.76 (skill file, 2026-09-16) -- so both are carried and every
    # figure printed anywhere names which one it is.
    boss_percentage: float | None = None
    # The phase the attempt ended in, as the report states it. None where the
    # report says nothing; 0 is a real answer meaning a boss with no phases.
    last_phase: int | None = None
    last_phase_is_intermission: bool = False
    phase_transitions: tuple[PhaseTransition, ...] = ()
    # The encounter's named phases, from `Report.phases`. Empty where the API
    # names none, which is a fact about the boss rather than a missing reading.
    # `phase_transitions` says when each began; this says what each is called,
    # and a phase claim needs both.
    phases: tuple[Phase, ...] = ()
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
    def players(self) -> tuple[Player, ...]:
        """Who was here, answered by the encounter itself. See `domain/fight.py`."""
        return self.encounter.players

    @property
    def window_ms(self) -> tuple[int, int]:
        """The stretch of the log this fight covers: the attempt's own bounds.

        A boss fight states its start and its end outright, so nothing has to
        be reconstructed from pulls it does not have. Design section 6.11
        names this as the figure a recap's `visible_from_ms` becomes -- the
        fight's start rather than the first pull's.
        """
        return (self.encounter.start_ms, self.encounter.end_ms)

    @property
    def has_pulls(self) -> bool:
        """A boss fight is one continuous window. See `domain/fight.py`.

        `Encounter` carries no pulls at all, which is the first thing its own
        docstring says, so this is a fact about the fight and not a figure
        that could come back otherwise.
        """
        return False

    @property
    def ability_icon_map(self) -> Mapping[int, str]:
        """Icon file names by ability game id, as a read-only mapping."""
        return MappingProxyType(dict(self.ability_icons))

    @property
    def auras_by_actor(self) -> Mapping[int, PlayerAuras]:
        """Buff bands by actor id, as a read-only mapping."""
        return MappingProxyType({one.actor_id: one for one in self.auras})
