# ABOUTME: The character command's domain types: a zone's dungeons, ranked runs, chosen runs,
# ABOUTME: and what one analysed run hands to the cross-run reading.

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.measures import PlayerMeasures
from wowperf.domain.comparison.tempo import TempoMeasures
from wowperf.domain.findings import Finding


class Dungeon(Frozen):
    encounter_id: int
    name: str


class Zone(Frozen):
    """A Warcraft Logs zone: its dungeons, and the difficulty ids it is ranked at."""

    zone_id: int
    name: str
    difficulty_ids: tuple[int, ...] = ()
    dungeons: tuple[Dungeon, ...] = ()


class RankedRun(Frozen):
    """One of the character's ranked runs, as their rankings list it.

    `report_code` and `fight_id` are None for a run with no public log: the
    rankings keep it, the analysis cannot read it.
    """

    encounter_id: int
    keystone_level: int
    spec: str
    start_time_ms: int
    report_code: str | None = None
    fight_id: int | None = None


class ChosenRun(Frozen):
    """A run the selection kept: always one with a public log to read."""

    dungeon: str
    encounter_id: int
    keystone_level: int
    start_time_ms: int
    report_code: str
    fight_id: int


class LeftOut(Frozen):
    dungeon: str
    reason: str


class Selection(Frozen):
    spec: str
    chosen: tuple[ChosenRun, ...] = ()
    left_out: tuple[LeftOut, ...] = ()


class CharacterRun(Frozen):
    """What one analysed run hands to the cross-run reading.

    `encounter_id` is the dungeon's, carried from the `ChosenRun` the run was
    read for. `subject_slug` is the character's slug in that run's own findings,
    which is their roster index there and can differ from run to run. `measures`
    is None when the run drew no parse sample, `tempo` when the speed sample sat
    under the aggregate floor.
    """

    report_code: str
    fight_id: int
    dungeon: str
    encounter_id: int
    keystone_level: int
    in_time: bool
    subject_slug: str
    subject_deaths: int = 0
    findings: tuple[Finding, ...] = ()
    measures: PlayerMeasures | None = None
    tempo: TempoMeasures | None = None


class FailedRun(Frozen):
    dungeon: str
    keystone_level: int
    report_code: str
    fight_id: int
    reason: str


class CharacterSubject(Frozen):
    """Who the page is about, as the command was asked."""

    name: str
    realm: str
    region: str
    zone_name: str
