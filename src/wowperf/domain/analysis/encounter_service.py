# ABOUTME: Runs the analysers a single boss fight can support, and ranks the findings.
# ABOUTME: Deliberately dull: all the judgement lives in the analysers, none of it here.

from wowperf.domain.analysis.consumables import (
    analyse_consumables_at_death,
    analyse_consumables_never_used,
)
from wowperf.domain.analysis.damage_outliers import analyse_damage_outliers
from wowperf.domain.analysis.deaths import analyse_deaths, fight_offset
from wowperf.domain.analysis.defensives import (
    analyse_defensives,
    analyse_defensives_at_death,
)
from wowperf.domain.analysis.interrupts import analyse_interrupts, reconstruct_enemy_casts
from wowperf.domain.analysis.severity import rank_raid_findings
from wowperf.domain.comparison.mechanics import AbilityTakenRow, MechanicsSample, compare_mechanics
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Finding
from wowperf.domain.season import Consumables, Defensives, Roles


def analyse_encounter(
    loaded: LoadedEncounter,
    defensives: Defensives,
    consumables: Consumables,
    *,
    roles: Roles = Roles(),
    mechanics: MechanicsSample = MechanicsSample(),
    our_abilities: tuple[AbilityTakenRow, ...] = (),
) -> list[Finding]:
    """Every analyser a single boss fight supports, as one ranked list.

    Three of slice 1's analysers are absent, and their absence is the design
    rather than an omission. `decompose_time` and `analyse_trash` measure a
    keystone timer and an enemy-forces requirement, neither of which a boss
    fight has. `analyse_players`' activity half prices activity against pull
    windows, which a boss fight also lacks; its outlier half needs only a
    roster and a set of hits, which a boss fight has, and runs here as
    `analyse_damage_outliers`. The throughput pair ranks pulls worth a
    cooldown, and belongs to the next plan, not here.

    `roles` feeds `analyse_damage_outliers`, which uses it to leave tanks out
    of a median they would only skew. `mechanics` and `our_abilities` feed
    `compare_mechanics`, the raid counterpart to a route comparison: both
    default to empty, so an encounter with no comparison sample simply runs
    the analysers a bare fight always supported.
    """
    encounter = loaded.encounter
    enemy_casts = reconstruct_enemy_casts(loaded.enemy_cast_rows, loaded.interrupts)

    def locate(death: Death) -> str:
        return fight_offset(encounter.start_ms, death)

    findings: list[Finding] = []
    findings += analyse_deaths(
        loaded.deaths,
        locate,
        f"in {encounter.duration_seconds:.0f}s of {encounter.boss_name}",
        cost_detail_suffix="",
    )
    findings += analyse_interrupts(enemy_casts, loaded.damage_taken)
    findings += analyse_defensives(
        encounter.players, encounter.duration_seconds, loaded.casts, defensives,
        loaded.deaths,
    )
    findings += analyse_defensives_at_death(
        encounter.players, loaded.casts, defensives, loaded.deaths,
        locate=locate,
    )
    findings += analyse_consumables_at_death(
        encounter.players, encounter.start_ms, loaded.casts, consumables, loaded.deaths,
        locate=locate,
    )
    findings += analyse_consumables_never_used(
        encounter.players, loaded.casts, consumables, loaded.deaths
    )
    findings += analyse_damage_outliers(encounter.players, loaded.damage_taken, roles)
    findings += compare_mechanics(
        our_abilities, encounter.duration_seconds, mechanics, scope=encounter.boss_name
    )
    return rank_raid_findings(findings)
