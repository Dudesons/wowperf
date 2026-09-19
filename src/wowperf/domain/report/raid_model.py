# ABOUTME: The raid report's view model: every judgement its seven-tab page makes.
# ABOUTME: A sibling of `model.Report` -- reuses its rows, cards and provenance whole.

from collections.abc import Iterator

from wowperf.domain.base import Frozen
from wowperf.domain.report.model import (
    DeathCard,
    LedgerRow,
    PlayerCard,
    Provenance,
    Section,
)
from wowperf.domain.report.raid_frame import RaidHeader


class GridColumn(Frozen):
    """One ability's column heading. `ability_id` draws the icon."""

    ability_id: int
    ability_name: str


class GridCell(Frozen):
    """One player's total from one ability, formatted.

    `multiple` is "" where no ratio exists: a tank, who is outside the median
    by design, and a player who took none of the ability, where there is
    nothing to divide. Both still print an `amount`, and a player who took
    none prints "0" -- a reading, not a gap.

    `tinted` is set from the finding's own existence, never from a threshold
    recomputed here. See `build_raid_grid`.
    """

    ability_id: int
    amount: str
    multiple: str
    tinted: bool


class GridRow(Frozen):
    """One player's row, one cell per column, in column order."""

    player_name: str
    cells: tuple[GridCell, ...]


class RaidGrid(Frozen):
    """Who took what, as a table. A view model, never findings.

    Twenty players by five abilities is a hundred cells; as findings that is
    the report's cap problem five times over. The caption carries design 7.3's
    sentence, because a tint means "took far more of this than their raid did"
    and never that somebody made a mistake.
    """

    columns: tuple[GridColumn, ...]
    rows: tuple[GridRow, ...]
    caption: str


class RaidReport(Frozen):
    header: RaidHeader
    # Figures that contain others, heading the Summary.
    ledger_decomposition: tuple[LedgerRow, ...]
    # The biggest findings, in ranked order. Each equals its card on another
    # tab; the Summary renders a link to that card, never a second card.
    summary_pointers: tuple[LedgerRow, ...] = ()
    # The external frame's throughput half: damage against the sample, where it
    # went, and the percentile. Design section 6.1, 6.2 and 6.7.
    damage_rows: tuple[LedgerRow, ...] = ()
    # Withheld on an attempt that did not kill, with the reason the reader needs.
    damage: Section
    # What hit the raid, and who took more of it than the rest. Sections 6.8 and 6.9.
    mechanics_rows: tuple[LedgerRow, ...] = ()
    # The per-player damage grid: one row per player, one column per ability
    # that earned a `mechanics.ability.*` or `mechanics.lethal.*` finding.
    # None where no ability qualified.
    grid: RaidGrid | None = None
    deaths: tuple[DeathCard, ...]
    death_rows: tuple[LedgerRow, ...] = ()
    interrupts: tuple[LedgerRow, ...]
    players: tuple[PlayerCard, ...]
    group_rows: tuple[LedgerRow, ...] = ()
    # Every finding no field above claimed -- a structural catch-all, not a
    # whitelist of its own. See `build_observations`.
    observations: tuple[LedgerRow, ...]
    provenance: Provenance


def all_raid_ledger_rows(report: RaidReport) -> Iterator[LedgerRow]:
    """Every finding row on the raid page, including the two nested in each player card.

    One place names the fields, so a caller cannot reach six of the seven tabs
    and lose the seventh in silence: a row whose ability reaches the page
    without reaching the icon resolver draws nothing and reports nothing.

    `PlayerCard` is reused whole from the Mythic+ model, so its own two row
    fields are walked here too, exactly as `model.all_ledger_rows` walks them
    for the Mythic+ report -- a raider's per-card comparison rows (design
    section 6, `RAID_COMPARISON_PREFIXES`) land on `spell_and_talent_rows`,
    and are icons the resolver would otherwise never see.
    """
    yield from report.ledger_decomposition
    yield from report.summary_pointers
    yield from report.damage_rows
    yield from report.mechanics_rows
    yield from report.death_rows
    yield from report.interrupts
    yield from report.group_rows
    yield from report.observations
    for player in report.players:
        yield from player.damage_rows
        yield from player.spell_and_talent_rows
