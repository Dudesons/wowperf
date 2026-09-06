# ABOUTME: Per-player facts measured inside pull windows only, never a throughput ranking.
# ABOUTME: Damage taken is stated against the group median, never as "avoidable damage".

from collections import defaultdict
from statistics import median

from wowperf.domain.base import Frozen
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, InterruptEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run
from wowperf.domain.season import Roles

MEDIAN_MULTIPLE = 2.0
"""Taking this many times the group median of one ability is worth saying out loud."""

MIN_PLAYERS_FOR_MEDIAN = 3
"""Fewer than this and a median is not a group baseline."""

LOW_ACTIVITY_PERCENT = 60.0
"""Below this share of pull time spent casting, low activity is worth flagging."""

MAX_OUTLIERS_REPORTED = 5


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


def display_names(run: Run) -> dict[int, str]:
    """Map each player's actor id to the name a report should show for them.

    Two players can share a display name (cross-realm groups ordinarily
    produce this); when that happens the actor id disambiguates both, so a
    reader — and any code matching against a finding's title — is never
    handed one name that could mean two different people. A name held by
    exactly one player stays plain, since the common case needs no clutter.
    Computed once from the roster, the same rule `analyse_players` applies
    to its own damage-outlier titles.
    """
    name_counts: dict[str, int] = defaultdict(int)
    for player in run.players:
        name_counts[player.name] += 1
    return {
        player.actor_id: (
            player.name
            if name_counts[player.name] == 1
            else f"{player.name} (actor {player.actor_id})"
        )
        for player in run.players
    }


def _damage_outliers(
    run: Run, damage_taken: tuple[DamageTakenEvent, ...], roles: Roles
) -> list[tuple[int, str, str, int, float]]:
    """(actor id, player name, ability name, amount, multiple of the median), worst first.

    Keyed by actor id throughout, not display name, so two players sharing a
    name are never conflated. The caller disambiguates the title with the
    actor id only when a collision is possible, matching the other analysers.
    """
    names = {player.actor_id: player.name for player in run.players}
    tank_ids = {
        player.actor_id
        for player in run.players
        if roles.role_of(player.class_name, player.spec) == "tank"
    }
    totals: dict[tuple[int, int], int] = defaultdict(int)
    ability_names: dict[int, str] = {}
    for hit in damage_taken:
        if hit.actor_id in tank_ids:
            continue
        totals[(hit.ability_id, hit.actor_id)] += hit.amount
        ability_names[hit.ability_id] = hit.ability_name

    by_ability: dict[int, dict[int, int]] = defaultdict(dict)
    for (ability_id, actor_id), amount in totals.items():
        by_ability[ability_id][actor_id] = amount

    outliers = []
    for ability_id, per_player in by_ability.items():
        took = [amount for amount in per_player.values() if amount > 0]
        if len(took) < MIN_PLAYERS_FOR_MEDIAN:
            continue
        baseline = median(took)
        for actor_id, amount in per_player.items():
            multiple = amount / baseline
            if multiple >= MEDIAN_MULTIPLE:
                outliers.append(
                    (
                        actor_id,
                        names.get(actor_id, f"Actor {actor_id}"),
                        ability_names[ability_id],
                        amount,
                        multiple,
                    )
                )
    return sorted(outliers, key=lambda row: -row[4])


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
    players_by_id = {player.actor_id: player for player in run.players}
    names_by_actor = display_names(run)

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

    for rank, (actor_id, name, ability, amount, multiple) in enumerate(
        _damage_outliers(run, damage_taken, roles)[:MAX_OUTLIERS_REPORTED]
    ):
        # Two players can share a display name; `display_names` disambiguates
        # with the actor id, matching the roster-wide rule used elsewhere.
        # `name` (from `_damage_outliers`) is the fallback for an actor id
        # that is not on the roster at all, which `display_names` cannot map.
        display_name = names_by_actor.get(actor_id, f"{name} (actor {actor_id})")
        taker = players_by_id.get(actor_id)
        # Tanks are left out of this comparison altogether: as the only member of
        # their role they have no honest median. The class and spec still name
        # the player for a reader.
        class_and_spec = f"{taker.class_name} {taker.spec}" if taker else "unknown class"
        findings.append(
            Finding(
                id=f"players.damage.{rank}",
                title=f"{display_name} took {multiple:.1f}x the group median from {ability}",
                detail=(
                    f"{amount:,} unmitigated damage from {ability}. This states a difference, "
                    "not a mistake: whether any single hit was avoidable is not something "
                    "the log records."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"{multiple:.1f}x the median",
                    "median is over the players who took at least one hit of this ability",
                    "unmitigated: before absorbs and mitigation",
                    class_and_spec,
                ),
            )
        )
    return findings
