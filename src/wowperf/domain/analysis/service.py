# ABOUTME: Runs every analyser over one loaded run and ranks the findings by time cost.
# ABOUTME: Deliberately dull: all the judgement lives in the analysers, none of it here.

from wowperf.domain.analysis.deaths import analyse_deaths
from wowperf.domain.analysis.defensives import analyse_defensives
from wowperf.domain.analysis.interrupts import analyse_interrupts, reconstruct_enemy_casts
from wowperf.domain.analysis.players import analyse_players
from wowperf.domain.analysis.timeline import decompose_time
from wowperf.domain.analysis.trash import analyse_trash
from wowperf.domain.findings import Finding, rank_findings
from wowperf.domain.model import LoadedRun
from wowperf.domain.season import Defensives, SeasonData


def analyse(loaded: LoadedRun, season: SeasonData, defensives: Defensives) -> list[Finding]:
    """Every analyser, one ranked list."""
    enemy_casts = reconstruct_enemy_casts(loaded.enemy_cast_rows, loaded.interrupts)

    findings: list[Finding] = []
    findings += decompose_time(loaded.run, loaded.deaths, season)
    findings += analyse_deaths(loaded.run, loaded.deaths)
    findings += analyse_interrupts(enemy_casts, loaded.damage_taken)
    findings += analyse_trash(loaded.run, loaded.enemy_deaths)
    findings += analyse_players(
        loaded.run, loaded.casts, loaded.deaths, loaded.interrupts, loaded.damage_taken
    )
    findings += analyse_defensives(loaded.run, loaded.casts, defensives, loaded.deaths)
    return rank_findings(findings)
