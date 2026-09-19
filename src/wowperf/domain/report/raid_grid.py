# ABOUTME: The per-player damage grid as a view model: one row per player, one column per ability.
# ABOUTME: A cell is tinted from a finding's own existence, never from a threshold recomputed here.

from collections.abc import Sequence

from wowperf.domain.analysis.damage_outliers import (
    MAX_OUTLIERS_REPORTED,
    damage_matrix,
    damage_outliers,
)
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.findings import Finding
from wowperf.domain.model import Player
from wowperf.domain.report.raid_model import GridCell, GridColumn, GridRow, RaidGrid
from wowperf.domain.season import Roles

MAX_GRID_COLUMNS = 5
"""How many abilities the grid may show at once.

Its own constant rather than `MAX_MECHANICS_REPORTED`, which already governs
three families: this one's constraint is table width and theirs is list
length, and one number serving two unrelated questions is how a change for one
silently reshapes the other. It starts at the same value only because five
columns is what fits.
"""

CAPTION = (
    "Each cell is what one player took from one ability, against the median of the "
    "players who took it. A highlighted cell means that player took far more of it "
    "than their raid did -- taking a tankbuster is correct, and soaking is doing the "
    "job. Tanks are shown but never highlighted, because taking more than the raid is "
    "the tank's role."
)
"""Design 7.3, on the page rather than only in the design document."""


def _columns(findings: Sequence[Finding]) -> tuple[GridColumn, ...]:
    """The abilities the ranked list reports, then the ones that killed somebody.

    Ranked first and capped, so where the two sources together name more than
    the grid can hold, the ranking decides. A lethal ability that does not fit
    is still named on the same tab by `mechanics.lethal.*`.
    """
    seen: dict[int, str] = {}
    for prefix in ("mechanics.ability.", "mechanics.lethal."):
        for finding in findings:
            if not finding.id.startswith(prefix):
                continue
            if finding.ability_id and finding.ability_id not in seen:
                seen[finding.ability_id] = finding.ability_name
    return tuple(
        GridColumn(ability_id=ability_id, ability_name=name)
        for ability_id, name in list(seen.items())[:MAX_GRID_COLUMNS]
    )


def build_raid_grid(
    players: tuple[Player, ...],
    damage_taken: tuple[DamageTakenEvent, ...],
    roles: Roles,
    findings: Sequence[Finding],
) -> RaidGrid | None:
    """Who took what, as a table, or None where no ability earned a column.

    The tint is the finding's own existence and not a threshold recomputed
    here, so the table can state nothing the page does not already say
    outright and the two cannot drift. It also settles tanks without a rule of
    its own: a tank is outside the median, so never an outlier, so never
    tinted.
    """
    columns = _columns(findings)
    if not columns:
        return None

    matrix = damage_matrix(players, damage_taken, roles)
    outliers = {
        (one.actor_id, one.ability_id)
        for one in damage_outliers(players, damage_taken, roles)[:MAX_OUTLIERS_REPORTED]
    }
    tank_ids = {
        player.actor_id
        for player in players
        if roles.role_of(player.class_name, player.spec) == "tank"
    }

    rows = []
    for player in players:
        cells = []
        for column in columns:
            totals = matrix.by_ability.get(column.ability_id)
            amount = totals.amounts.get(player.actor_id, 0) if totals else 0
            median_amount = totals.median_amount if totals else None
            multiple = (
                f"{amount / median_amount:.1f}x"
                if median_amount and amount > 0 and player.actor_id not in tank_ids
                else ""
            )
            cells.append(
                GridCell(
                    ability_id=column.ability_id,
                    amount=f"{amount:,}",
                    multiple=multiple,
                    tinted=(player.actor_id, column.ability_id) in outliers,
                )
            )
        rows.append(GridRow(player_name=player.name, cells=tuple(cells)))

    return RaidGrid(columns=columns, rows=tuple(rows), caption=CAPTION)
