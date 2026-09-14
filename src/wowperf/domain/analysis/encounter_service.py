# ABOUTME: Runs the analysers a single boss fight can support, and ranks the findings.
# ABOUTME: Deliberately dull: all the judgement lives in the analysers, none of it here.

from wowperf.domain.analysis.consumables import (
    analyse_consumables_at_death,
    analyse_consumables_never_used,
)
from wowperf.domain.analysis.deaths import analyse_deaths, fight_offset
from wowperf.domain.analysis.defensives import (
    analyse_defensives,
    analyse_defensives_at_death,
)
from wowperf.domain.analysis.interrupts import analyse_interrupts, reconstruct_enemy_casts
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Finding, rank_findings
from wowperf.domain.season import Consumables, Defensives, Roles


def analyse_encounter(
    loaded: LoadedEncounter,
    defensives: Defensives,
    consumables: Consumables,
    *,
    roles: Roles = Roles(),
) -> list[Finding]:
    """Every analyser a single boss fight supports, as one ranked list.

    Four of slice 1's analysers are absent, and their absence is the design
    rather than an omission. `decompose_time` and `analyse_trash` measure a
    keystone timer and an enemy-forces requirement, neither of which a boss
    fight has. `analyse_players` prices activity against pull windows. The
    throughput pair ranks pulls worth a cooldown. Their raid counterparts are
    comparisons against a reference sample and belong to the next plan, not
    here.
    """
    encounter = loaded.encounter
    enemy_casts = reconstruct_enemy_casts(loaded.enemy_cast_rows, loaded.interrupts)

    findings: list[Finding] = []
    findings += analyse_deaths(
        loaded.deaths,
        lambda death: fight_offset(encounter.start_ms, death),
        f"in {encounter.duration_seconds:.0f}s of {encounter.boss_name}",
    )
    findings += analyse_interrupts(enemy_casts, loaded.damage_taken)
    findings += analyse_defensives(
        encounter.players, encounter.duration_seconds, loaded.casts, defensives,
        loaded.deaths,
    )
    findings += analyse_defensives_at_death(
        encounter.players, loaded.casts, defensives, loaded.deaths,
        locate=lambda death: fight_offset(encounter.start_ms, death),
    )
    findings += analyse_consumables_at_death(
        encounter.players, encounter.start_ms, loaded.casts, consumables, loaded.deaths,
        locate=lambda death: fight_offset(encounter.start_ms, death),
    )
    findings += analyse_consumables_never_used(
        encounter.players, loaded.casts, consumables, loaded.deaths
    )
    return rank_findings(findings)
