# ABOUTME: The progression report's view model: every judgement its five-tab page makes.
# ABOUTME: A sibling of RaidReport -- it reuses LedgerRow whole and carries no reference at all.

from collections.abc import Iterator

from wowperf.domain.base import Frozen
from wowperf.domain.report.model import LedgerRow, Section


class ProgressionHeader(Frozen):
    """The facts printed above a progression report's tabs.

    `depth_label` names the scale every percentage on this page is on, once,
    where a reader meets it first. Section 2.4: a printed percentage that does
    not say which one it is, is a figure nobody can act on.

    `outcome` is the fact alone ("Killed on attempt 3 of 7"). `headline` is what
    the Summary opens on: the same sentence for a kill, and for a boss not yet
    killed the outcome followed by how deep the deepest attempt got.
    `read_line` is how many attempts were read and how many left out, already
    in the right number, for the line under the title.
    """

    boss: str
    difficulty: str
    size: int
    outcome: str
    headline: str
    read_line: str
    attempts_counted: int
    attempts_discarded: int
    depth_label: str


class AttemptRow(Frozen):
    """One attempt in the Attempts table. Every field is already a string to print.

    `depth` and `deaths` are strings rather than numbers because both have an
    honest empty state -- an attempt the report gave no percentage for, and an
    attempt that was never deepened -- and a zero standing in for either would
    read as a measurement.

    `verdict`, `pace`, `first_death` and `held` are how the attempt ended: the
    pull's own wipe verdict, its pace state at the end, who died first and to
    what, and how long the raid held after that death. The page draws the first
    two only when `ProgressionReport.compared` says a comparison ran.
    """

    index: int
    fight_id: int
    depth: str
    duration: str
    phase: str = ""
    deaths: str
    verdict: str = ""
    pace: str = ""
    first_death: str = ""
    held: str = ""
    is_best: bool = False
    is_kill: bool = False


class AttemptBar(Frozen):
    """One attempt's bar, in viewBox units. All arithmetic happened in the builder."""

    x: float
    y: float
    width: float
    height: float
    css_class: str
    hover: str


class AttemptsChart(Frozen):
    """The night's shape as one drawing. Withheld when no attempt carries a reading.

    Every coordinate the SVG needs lives here so the template computes none:
    `tick_x1`/`tick_x2` bound the horizontal gridlines, `tick_label_x` places
    their text, and `baseline_y` is the floor every bar stands on.
    """

    section: Section
    bars: tuple[AttemptBar, ...] = ()
    ticks: tuple[tuple[float, str], ...] = ()
    legend: str = ""
    width: float = 0.0
    height: float = 0.0
    tick_x1: float = 0.0
    tick_x2: float = 0.0
    tick_label_x: float = 0.0
    baseline_y: float = 0.0


class ProgressionProvenance(Frozen):
    """What was read, and what was withheld. No references, by construction.

    `Provenance` is deliberately not reused. It carries a `fight_id`, and a
    night is not one fight; and it carries `references`, the external
    candidates a comparison weighed. This command draws no external sample at
    all (section 7.1), which is what makes it an order of magnitude cheaper
    than a compared raid analysis -- and a type with nowhere to put another
    player's run cannot grow into a corpus by accident.
    """

    report_code: str
    encounter_id: int
    # How many attempts were read and how many deepened, already in the right
    # number, for the line the Provenance tab opens on.
    read_line: str
    attempts_counted: int
    attempts_deepened: int
    fetched_at: str
    withheld: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()


class ProgressionReport(Frozen):
    header: ProgressionHeader
    chart: AttemptsChart
    attempts: tuple[AttemptRow, ...] = ()
    # Whether the attempts were read against reference kills: true on a night
    # page drawn with comparison on, and the only thing that draws the Verdict
    # and Pace columns. The standalone progression page compares nothing.
    compared: bool = False
    # The boss-level rollups a night summary opens on: kill speed, why wipes
    # ended, what kept landing that no reference kill took, what kept
    # over-landing. Empty on the standalone progression page.
    lead_rows: tuple[LedgerRow, ...] = ()
    # Where attempts sat: the cluster, the movement, what was discarded.
    attempt_rows: tuple[LedgerRow, ...] = ()
    # What repeated: the phase, who fell first, what kept landing, the collapse.
    repeat_rows: tuple[LedgerRow, ...] = ()
    # Points at the killing-blow, first-death and ability cards on the Repeats
    # tab, in that order and each only if the night carries it. The cards stay
    # on Repeats; the Summary links to them. Each equals its card.
    repeat_pointers: tuple[LedgerRow, ...] = ()
    # What the deepest attempt did differently, and which attempt it was.
    best_rows: tuple[LedgerRow, ...] = ()
    # Withheld when no attempt was deepened, with the reason a reader needs.
    best: Section
    # Every finding no field above claimed -- a structural catch-all, not a
    # whitelist of its own, so a new family can never vanish from the page.
    observations: tuple[LedgerRow, ...] = ()
    provenance: ProgressionProvenance


def all_progression_ledger_rows(report: ProgressionReport) -> Iterator[LedgerRow]:
    """Every finding row on the progression page.

    One place names the fields, so a caller cannot reach four of the five tabs
    and lose the fifth in silence: a row whose ability reaches the page without
    reaching the icon resolver draws nothing and reports nothing.

    `report.repeat_pointers` is the deliberate exception: it repeats cards
    `repeat_rows` already carries, as links, so walking it would count each of
    those rows twice for every caller, including the once-only checks.
    """
    yield from report.lead_rows
    yield from report.attempt_rows
    yield from report.repeat_rows
    yield from report.best_rows
    yield from report.observations
