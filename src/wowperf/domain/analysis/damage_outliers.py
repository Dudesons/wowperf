# ABOUTME: The damage-outlier finding: whoever took far more than their group's median.
# ABOUTME: Reads a roster and a set of hits, never a Run, so a boss fight can reuse it.

from collections import defaultdict
from statistics import median

from wowperf.domain.analysis.roster import display_names
from wowperf.domain.base import Frozen
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.findings import Confidence, Finding, FindingFact
from wowperf.domain.model import Player
from wowperf.domain.season import Roles

MEDIAN_MULTIPLE = 2.0
"""Taking this many times the group median of one ability is worth saying out loud."""

MIN_PLAYERS_FOR_MEDIAN = 3
"""Fewer than this and a median is not a group baseline."""

MAX_OUTLIERS_REPORTED = 5


class AbilityTotals(Frozen):
    """One ability's damage across the raid, and the baseline it is read against.

    `amounts` includes tanks, because the grid shows a tank's row. The median
    does not, because a tank taking ten times what the raid took is the job and
    not a finding -- the same exclusion `damage_outliers` has always applied,
    now stated once here and read by both consumers.

    `median_amount` is None below `MIN_PLAYERS_FOR_MEDIAN`, where a median is
    not a group baseline. None rather than 0.0: a zero baseline would divide.
    """

    ability_id: int
    ability_name: str
    amounts: dict[int, int]
    median_amount: float | None
    took_count: int


class DamageMatrix(Frozen):
    """Every ability that hit the raid, keyed by id."""

    by_ability: dict[int, AbilityTotals]


def damage_matrix(
    players: tuple[Player, ...], damage_taken: tuple[DamageTakenEvent, ...], roles: Roles
) -> DamageMatrix:
    """Per-ability, per-player totals with each ability's non-tank median.

    One walk over the hits, serving both the outlier findings and the report's
    per-player grid. Keyed by actor id throughout, never by display name, so
    two players sharing a name are never conflated.
    """
    tank_ids = {
        player.actor_id
        for player in players
        if roles.role_of(player.class_name, player.spec) == "tank"
    }

    amounts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    ability_names: dict[int, str] = {}
    for hit in damage_taken:
        amounts[hit.ability_id][hit.actor_id] += hit.amount
        ability_names[hit.ability_id] = hit.ability_name

    by_ability: dict[int, AbilityTotals] = {}
    for ability_id, per_player in amounts.items():
        took = [
            amount
            for actor_id, amount in per_player.items()
            if amount > 0 and actor_id not in tank_ids
        ]
        by_ability[ability_id] = AbilityTotals(
            ability_id=ability_id,
            ability_name=ability_names[ability_id],
            amounts=dict(per_player),
            median_amount=median(took) if len(took) >= MIN_PLAYERS_FOR_MEDIAN else None,
            took_count=len(took),
        )
    return DamageMatrix(by_ability=by_ability)


class DamageOutlier(Frozen):
    """One player's total from one ability, against the median of those who took it.

    Carries the median and how many players it was taken over, not only the
    multiple, because the finding states all three: the title the multiple, the
    detail the amount, and the hover panel both sides of the division.
    """

    actor_id: int
    ability_id: int
    player_name: str
    ability_name: str
    amount: int
    median_amount: float
    took_count: int

    @property
    def multiple(self) -> float:
        """Held as a property rather than a field so it cannot drift from its inputs.

        `median_amount` is a median over amounts greater than zero, so it is
        never zero itself and this never divides by zero.
        """
        return self.amount / self.median_amount


def damage_outliers(
    players: tuple[Player, ...], damage_taken: tuple[DamageTakenEvent, ...], roles: Roles
) -> list[DamageOutlier]:
    """Every player far above the median of one ability, worst first.

    Keyed by actor id throughout, not display name, so two players sharing a
    name are never conflated. The caller disambiguates the title with the
    actor id only when a collision is possible, matching the other analysers.
    """
    names = {player.actor_id: player.name for player in players}
    tank_ids = {
        player.actor_id
        for player in players
        if roles.role_of(player.class_name, player.spec) == "tank"
    }
    matrix = damage_matrix(players, damage_taken, roles)

    outliers = []
    for totals in matrix.by_ability.values():
        if totals.median_amount is None:
            continue
        for actor_id, amount in totals.amounts.items():
            # Tanks are outside the baseline, so they are outside the finding.
            if actor_id in tank_ids:
                continue
            if amount / totals.median_amount >= MEDIAN_MULTIPLE:
                outliers.append(
                    DamageOutlier(
                        actor_id=actor_id,
                        ability_id=totals.ability_id,
                        player_name=names.get(actor_id, f"Actor {actor_id}"),
                        ability_name=totals.ability_name,
                        amount=amount,
                        median_amount=totals.median_amount,
                        took_count=totals.took_count,
                    )
                )
    return sorted(outliers, key=lambda row: -row.multiple)


def analyse_damage_outliers(
    players: tuple[Player, ...],
    damage_taken: tuple[DamageTakenEvent, ...],
    roles: Roles = Roles(),
) -> list[Finding]:
    """Every player far above their own group's median for one ability.

    Takes a roster rather than a `Run` because a boss fight has no pulls and
    this comparison never needed them: the median is over whoever took the
    ability, and the roster is only there to name them and to find the tanks.
    """
    names_by_actor = display_names(players)
    players_by_id = {player.actor_id: player for player in players}
    findings: list[Finding] = []
    for rank, outlier in enumerate(
        damage_outliers(players, damage_taken, roles)[:MAX_OUTLIERS_REPORTED]
    ):
        # Two players can share a display name; `display_names` disambiguates
        # with the actor id, matching the roster-wide rule used elsewhere.
        # The outlier's own `player_name` is the fallback for an actor id that
        # is not on the roster at all, which `display_names` cannot map.
        display_name = names_by_actor.get(
            outlier.actor_id, f"{outlier.player_name} (actor {outlier.actor_id})"
        )
        taker = players_by_id.get(outlier.actor_id)
        # Tanks are left out of this comparison altogether: as the only member of
        # their role they have no honest median. The class and spec still name
        # the player for a reader.
        class_and_spec = f"{taker.class_name} {taker.spec}" if taker else "unknown class"
        findings.append(
            Finding(
                id=f"players.damage.{rank}",
                title=(
                    f"{display_name} took {outlier.multiple:.1f}x the group median "
                    f"from {outlier.ability_name}"
                ),
                detail=(
                    f"{outlier.amount:,} unmitigated damage from {outlier.ability_name}. "
                    "This states a difference, not a mistake: whether any single hit was "
                    "avoidable is not something the log records."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"{outlier.multiple:.1f}x the median",
                    "median is over the players who took at least one hit of this ability",
                    "unmitigated: before absorbs and mitigation",
                    class_and_spec,
                ),
                # The same figures the title and detail state, as labels and
                # values a panel can lay out -- this finding's two sides side
                # by side, which is what earns it a panel where
                # `compare.spells.missing.*` has only one side and gets none.
                # Both amounts are sums of logged hits and the last line is a
                # count, so each is measured, which `FindingFact` spells as no
                # tier at all. The multiple is the one division done here.
                facts=(
                    FindingFact(label="This player", value=f"{outlier.amount:,} unmitigated"),
                    FindingFact(
                        label="Group median", value=f"{outlier.median_amount:,.0f} unmitigated"
                    ),
                    FindingFact(
                        label="Multiple",
                        value=f"{outlier.multiple:.1f}x",
                        confidence=Confidence.DERIVED,
                    ),
                    FindingFact(
                        label="Median over",
                        value=f"{outlier.took_count} players who took it",
                    ),
                ),
                ability_id=outlier.ability_id,
                ability_name=outlier.ability_name,
            )
        )
    return findings
