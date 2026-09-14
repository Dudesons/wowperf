# ABOUTME: Runs every analyser over one loaded run and ranks the findings by time cost.
# ABOUTME: Deliberately dull: all the judgement lives in the analysers, none of it here.

from wowperf.domain.analysis.consumables import (
    analyse_consumables_at_death,
    analyse_consumables_never_used,
)
from wowperf.domain.analysis.deaths import analyse_deaths
from wowperf.domain.analysis.defensives import (
    analyse_defensives,
    analyse_defensives_at_death,
)
from wowperf.domain.analysis.interrupts import analyse_interrupts, reconstruct_enemy_casts
from wowperf.domain.analysis.players import analyse_players
from wowperf.domain.analysis.throughput import (
    analyse_cooldown_alignment,
    analyse_cooldown_ceiling,
)
from wowperf.domain.analysis.timeline import decompose_time
from wowperf.domain.analysis.trash import analyse_trash
from wowperf.domain.findings import Finding, rank_findings
from wowperf.domain.model import LoadedRun
from wowperf.domain.season import (
    Consumables,
    Defensives,
    Roles,
    SeasonData,
    ThroughputCooldowns,
)


def analyse(
    loaded: LoadedRun,
    season: SeasonData,
    defensives: Defensives,
    consumables: Consumables,
    throughput: ThroughputCooldowns,
    *,
    roles: Roles = Roles(),
    include_cooldown_ceiling: bool = False,
) -> list[Finding]:
    """Every analyser, one ranked list.

    `include_cooldown_ceiling` is off by default because that claim is the
    noisiest one here: a keystone's route decides how many packs are worth a
    burst cooldown, so pressing one far below its theoretical maximum is
    often correct. The alignment claim beside it asks the same question of
    the pulls where the answer means something, and needs no asking for.
    """
    enemy_casts = reconstruct_enemy_casts(loaded.enemy_cast_rows, loaded.interrupts)

    findings: list[Finding] = []
    findings += decompose_time(loaded.run, loaded.deaths, season)
    findings += analyse_deaths(loaded.run, loaded.deaths)
    findings += analyse_interrupts(enemy_casts, loaded.damage_taken)
    findings += analyse_trash(loaded.run, loaded.enemy_deaths)
    findings += analyse_players(
        loaded.run, loaded.casts, loaded.deaths, loaded.interrupts, loaded.damage_taken,
        roles=roles,
    )
    findings += analyse_defensives(
        loaded.run.players, loaded.run.total_pull_seconds, loaded.casts, defensives,
        loaded.deaths,
    )
    findings += analyse_defensives_at_death(
        loaded.run, loaded.casts, defensives, loaded.deaths
    )
    findings += analyse_consumables_at_death(
        loaded.run, loaded.casts, consumables, loaded.deaths
    )
    findings += analyse_consumables_never_used(
        loaded.run, loaded.casts, consumables, loaded.deaths
    )
    findings += analyse_cooldown_alignment(
        loaded.run, loaded.casts, throughput, loaded.enemy_deaths, loaded.deaths
    )
    if include_cooldown_ceiling:
        findings += analyse_cooldown_ceiling(
            loaded.run, loaded.casts, throughput, loaded.deaths
        )
    return rank_findings(findings)
