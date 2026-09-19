# ABOUTME: The raid report's view model: every judgement its seven-tab page makes.
# ABOUTME: A sibling of `model.Report` -- reuses its rows, cards and provenance whole.

from collections.abc import Iterator

from wowperf.domain.base import Frozen
from wowperf.domain.report.model import (
    Badge,
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
    the report's cap problem five times over. The caption paraphrases design
    7.3's meaning, because a tint means "took far more of this than their raid
    did" and never that somebody made a mistake.
    """

    columns: tuple[GridColumn, ...]
    rows: tuple[GridRow, ...]
    caption: str


class AliveStep(Frozen):
    """One corner of the step function, in viewBox units."""

    x: float
    y: float


class AliveChart(Frozen):
    """How many of the raid were standing, across the attempt.

    Every coordinate the SVG needs lives here so the template computes none,
    exactly as `AttemptsChart` does for the progression page.

    One series, not two. There is no boss health curve to draw beside it:
    measured 2026-09-18, `graph(dataType: Resources, hostilityType: Enemies)`
    returns zero series. What the boss did is one note at the end point.

    The series is a floor on the living rather than a reading of them -- a
    player who releases and runs back leaves no record -- so it is badged
    `derived` wherever it is stated. `badge` carries that mark to the heading
    beside the chart, matching `ledger_row`'s own badge markup.
    """

    points: tuple[AliveStep, ...]
    ticks: tuple[tuple[float, str], ...]
    legend: str
    boss_note: str
    badge: Badge
    width: float
    height: float
    tick_x1: float
    tick_x2: float
    tick_label_x: float


class RaidReport(Frozen):
    header: RaidHeader
    verdict: LedgerRow | None = None
    """The wipe verdict, heading Summary. None on a kill, which produces none,
    and on a withheld wipe, whose reason is disclosed in Provenance instead:
    a landing tab whose first line announces that nothing was concluded is the
    complaint design section 11 exists to fix."""
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
    # The players-alive step chart. None where the attempt carries no duration.
    alive_chart: AliveChart | None = None


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

    `report.verdict` is the one deliberate exception: it heads Summary as its
    own headline rather than sitting in a tab's list, and `build_raid_report`
    already keeps its finding from also reaching `observations` -- walking it
    here too would count the same row twice for every caller of this
    function, including the once-only checks in the render invariants.
    `classify_attempt` never puts an ability on the verdict finding, so
    today's icon resolver loses nothing by not seeing it; a future verdict
    that named one would need its own arm in `_icon_addresses` instead.
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
