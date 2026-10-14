# ABOUTME: Builders for the character tests: runs, findings and the comparison rows they carry.
# ABOUTME: Dungeon names only; every player in these fixtures is one of the sanctioned names.

from wowperf.domain.character.model import CharacterRun
from wowperf.domain.comparison.measures import (
    AbilityRate,
    AuraRow,
    AuraUptime,
    DebuffRow,
    DebuffTable,
    PlayerMeasures,
    StatShare,
    Stretch,
    Verdict,
)
from wowperf.domain.comparison.tempo import TempoMeasures
from wowperf.domain.findings import Confidence, Finding

DUNGEONS = ("Altar of Fangs", "Den of Nalorakk", "Kings' Rest", "Murder Row",
            "Ruby Life Pools", "Temple of Sethraliss", "The Blinding Vale", "Voidscar Arena")


def a_run(index: int, *, findings: tuple[Finding, ...] = (),
          measures: PlayerMeasures | None = None, tempo: TempoMeasures | None = None,
          slug: str = "emberkin-0", subject_deaths: int = 0, level: int = 18,
          in_time: bool = True) -> CharacterRun:
    return CharacterRun(
        report_code=f"code{index:03d}x", fight_id=index + 1,
        dungeon=DUNGEONS[index % len(DUNGEONS)],
        encounter_id=12000 + index % len(DUNGEONS), keystone_level=level, in_time=in_time,
        subject_slug=slug, subject_deaths=subject_deaths, findings=findings,
        measures=measures, tempo=tempo,
    )


def a_tempo(*, time: float = 1800.0, their_time: float | None = 1700.0, deaths: int = 2,
            downtime: float = 90.0, kick: float | None = 0.3) -> TempoMeasures:
    return TempoMeasures(members=5, our_time=time, their_time=their_time, our_deaths=deaths,
                         their_deaths=1.0, our_downtime=downtime, their_downtime=100.0,
                         our_kick_share=kick, their_kick_share=0.3)


def a_finding(finding_id: str, *, slug: str = "emberkin-0", ability_id: int | None = None,
              ability_name: str = "", title: str = "A run's own title",
              confidence: Confidence = Confidence.DERIVED) -> Finding:
    return Finding(id=finding_id, title=title, detail="", confidence=confidence,
                   ability_id=ability_id, ability_name=ability_name, player_slug=slug)


def a_rate(ability_id: int, ours: float, theirs: float, *, stretch: Stretch = Stretch.BOSS,
           verdict: Verdict = Verdict.LEVEL, name: str = "Vampiric Strike") -> AbilityRate:
    return AbilityRate(ability_id=ability_id, name=name, ours=ours, their_median=theirs,
                       their_rates=(theirs,), stretch=stretch, verdict=verdict)


def a_buff(ability_id: int, ours: float, theirs: float, *, verdict: Verdict = Verdict.LEVEL,
           name: str = "Visceral Strength") -> AuraRow:
    return AuraRow(uptime=AuraUptime(ability_id=ability_id, name=name, ours=ours,
                                     their_median=theirs, their_fractions=(theirs,),
                                     verdict=verdict))


def a_debuff(ability_id: int, ours: float, theirs: float, *, verdict: Verdict = Verdict.LEVEL,
             shared_with: tuple[int, ...] = (), name: str = "Blood Plague") -> DebuffRow:
    return DebuffRow(uptime=AuraUptime(ability_id=ability_id, name=name, ours=ours,
                                       their_median=theirs, their_fractions=(theirs,),
                                       verdict=verdict),
                     shared_with=shared_with)


def a_stat(name: str, ours: float, theirs: float, *,
           verdict: Verdict = Verdict.LEVEL) -> StatShare:
    return StatShare(name=name, ours=ours, their_median=theirs, their_shares=(theirs,),
                     our_rating=100, their_median_rating=100.0, their_ratings=(100.0,),
                     verdict=verdict)


def measures_of(*, boss: tuple[AbilityRate, ...] = (), trash: tuple[AbilityRate, ...] = (),
                auras: tuple[AuraRow, ...] = (), debuffs: tuple[DebuffRow, ...] = (),
                stats: tuple[StatShare, ...] = ()) -> PlayerMeasures:
    return PlayerMeasures(boss=boss, trash=trash, auras=auras, stats=stats,
                          debuffs=DebuffTable(rows=debuffs))
