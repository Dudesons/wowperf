# ABOUTME: Per-player facts measured inside pull windows only, never a throughput ranking.
# ABOUTME: Damage taken is stated against the group median, never as "avoidable damage".

from collections import defaultdict

from wowperf.domain.analysis.damage_outliers import analyse_damage_outliers
from wowperf.domain.base import Frozen
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, InterruptEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run
from wowperf.domain.season import Roles

LOW_ACTIVITY_PERCENT = 60.0
"""Below this share of pull time spent casting, low activity is worth flagging."""


class PlayerSummary(Frozen):
    """One player's measured facts for the run: activity, interrupts, deaths."""

    name: str
    actor_id: int
    class_name: str
    spec: str
    casts_in_pulls: int
    active_seconds: float
    activity_percent: float
    interrupts: int
    deaths: int


def summarise_players(
    run: Run,
    casts: tuple[CastEvent, ...],
    deaths: tuple[Death, ...],
    interrupts: tuple[InterruptEvent, ...],
) -> tuple[PlayerSummary, ...]:
    """One row per player: `casts_in_pulls` counts only casts inside a pull window;
    `interrupt_counts` and `death_counts` count every interrupt and death in the
    run, in or out of a pull, since a death outside a pull still killed the player.
    """
    in_pull_seconds = sum(pull.duration_seconds for pull in run.pulls)

    cast_counts: dict[int, int] = defaultdict(int)
    for cast_event in casts:
        if cast_event.pull_index is not None:
            cast_counts[cast_event.actor_id] += 1

    interrupt_counts: dict[int, int] = defaultdict(int)
    for interrupt in interrupts:
        interrupt_counts[interrupt.actor_id] += 1

    death_counts: dict[int, int] = defaultdict(int)
    for death in deaths:
        death_counts[death.actor_id] += 1

    summaries = []
    for player in run.players:
        count = cast_counts.get(player.actor_id, 0)
        # One global-cooldown-ish second per cast. Deliberately coarse: this is a
        # floor on time spent acting, not a simulation of the rotation.
        active = float(count)
        summaries.append(
            PlayerSummary(
                name=player.name,
                actor_id=player.actor_id,
                class_name=player.class_name,
                spec=player.spec,
                casts_in_pulls=count,
                active_seconds=active,
                activity_percent=(
                    active / in_pull_seconds * 100 if in_pull_seconds > 0 else 0.0
                ),
                interrupts=interrupt_counts.get(player.actor_id, 0),
                deaths=death_counts.get(player.actor_id, 0),
            )
        )
    return tuple(summaries)


def analyse_players(
    run: Run,
    casts: tuple[CastEvent, ...],
    deaths: tuple[Death, ...],
    interrupts: tuple[InterruptEvent, ...],
    damage_taken: tuple[DamageTakenEvent, ...],
    roles: Roles = Roles(),
) -> list[Finding]:
    """Per-player facts, stated without ranking anyone's throughput."""
    findings: list[Finding] = []

    name_counts: dict[str, int] = defaultdict(int)
    for player in run.players:
        name_counts[player.name] += 1

    for summary in summarise_players(run, casts, deaths, interrupts):
        if summary.activity_percent >= LOW_ACTIVITY_PERCENT:
            continue
        # Two players can share a display name; disambiguate the id with the
        # actor id only when that happens, so the common case stays readable.
        activity_id = (
            f"players.activity.{summary.name}"
            if name_counts[summary.name] == 1
            else f"players.activity.{summary.name}.{summary.actor_id}"
        )
        findings.append(
            Finding(
                id=activity_id,
                title=f"{summary.name} cast {summary.casts_in_pulls} times inside pulls",
                detail=(
                    f"About {summary.activity_percent:.0f}% of pull time. Counted from "
                    "casts inside pull windows only, so waiting between packs is not "
                    "charged to the player."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"{summary.casts_in_pulls} casts in "
                    f"{sum(pull.duration_seconds for pull in run.pulls):.0f}s of pulls",
                    "cast-based, unlike Warcraft Logs' damage-based Activity figure",
                ),
            )
        )

    findings += analyse_damage_outliers(run.players, damage_taken, roles)
    return findings
