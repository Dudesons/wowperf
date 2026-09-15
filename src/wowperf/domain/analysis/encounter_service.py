# ABOUTME: Runs the analysers a single boss fight can support, and ranks the findings.
# ABOUTME: Deliberately dull: all the judgement lives in the analysers, none of it here.

from collections.abc import Sequence

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
from wowperf.domain.comparison.parse_axis import ParseSubject, compare_parse_axis
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Finding
from wowperf.domain.season import Consumables, Defensives, Roles


def _for_raider(findings: list[Finding], slug: str) -> list[Finding]:
    """Re-mint plain comparison ids as one raider's own.

    The comparison modules know nothing about who else is in the raid, so they
    mint `compare.talents` and this appends the player. Doing it in one place
    is what keeps six modules from each having to be told about the roster, and
    it is why the id is a suffix: every consumer of these ids matches by prefix,
    and a prefix survives anything appended to it.

    The Mythic+ path does the same thing at `comparison/service.py:_for_player`,
    byte for byte. Duplicated rather than shared on purpose: this plan's scope
    is the raid path, and lifting the two into one helper would edit
    `comparison/service.py`, which sits on the `analyze` call site this plan
    does not touch. The two must be kept in step by hand until a change that
    owns both sides lifts them into one.
    """
    return [
        finding.model_copy(update={"id": f"{finding.id}.{slug}", "player_slug": slug})
        for finding in findings
    ]


def analyse_encounter(
    loaded: LoadedEncounter,
    defensives: Defensives,
    consumables: Consumables,
    *,
    roles: Roles = Roles(),
    mechanics: MechanicsSample = MechanicsSample(),
    our_abilities: tuple[AbilityTakenRow, ...] = (),
    parse_subjects: Sequence[ParseSubject] = (),
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

    `parse_subjects` is the external frame, one entry per player asked for, each
    carrying what an adapter fetched on their behalf. It is a sequence and not
    one subject because `--all-players` compares a whole roster, and it is empty
    by default because `--no-compare` and a fight nobody named still analyse.
    Unlike `mechanics`, which is drawn once for the whole raid, this axis is
    drawn per player: a leaderboard exists per specialisation, and a percentile
    is a statement about one player.

    This axis is compared last, and `rank_raid_findings` decides where its rows
    land -- the order here is the order the analysers ran in, never an order a
    reader meets.
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
        our_abilities, encounter.duration_seconds, mechanics, scope="the raid"
    )
    for subject in parse_subjects:
        findings += _for_raider(
            compare_parse_axis(
                subject.player,
                subject.display_name,
                # The whole fight on our side, matching `whole_fight_casts` and
                # `whole_fight_uptime` inside: a raid fight has no shorter
                # stretch that both sides fought, the way a dungeon's boss
                # pulls do.
                encounter.duration_seconds,
                loaded.casts,
                subject.our_auras,
                subject.sample,
                loaded.standing,
                loaded.boss_standing,
                subject.board,
                subject.boss_board,
                subject.our_targets,
                subject.their_targets,
            ),
            subject.slug,
        )
    return rank_raid_findings(findings)
