# ABOUTME: The character report's view model: every judgement its four-tab page makes.
# ABOUTME: Reuses LedgerRow whole; run reports are linked by file name, never fetched.

from collections.abc import Iterator

from wowperf.domain.base import Frozen
from wowperf.domain.report.model import LedgerRow


class CharacterHeader(Frozen):
    """The facts printed above the character page's tabs, already strings."""

    name: str
    realm_line: str
    zone: str
    spec: str
    read_line: str


class RunRow(Frozen):
    """One read run on the Runs tab, linked to its own report beside the page."""

    dungeon: str
    level: str
    outcome: str
    report_file: str


class GroupRow(Frozen):
    """One run's row in the group ledger: ours against the fast runs' median, per column.

    `time_note` is empty unless the run's completion time was withheld, where
    it carries the reason the tempo findings give, so the cell that says "not
    compared" says why.
    """

    label: str
    report_file: str
    time: str
    time_note: str = ""
    deaths: str
    downtime: str
    kick_share: str
    your_deaths: str


class CharacterProvenance(Frozen):
    """`queries` names the operations that chose the runs; each run's own page
    states what was read for it. `withheld` carries the title of the finding that
    withholds the directions when too few runs loaded, and is empty otherwise."""

    read_line: str
    fetched_at: str
    warning: str
    queries: tuple[str, ...]
    withheld: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()


class CharacterReport(Frozen):
    header: CharacterHeader
    narrative: str | None
    direction_rows: tuple[LedgerRow, ...] = ()
    repeat_rows: tuple[LedgerRow, ...] = ()
    # Every finding neither list above claimed -- none today, the withheld
    # directions standing among the directions -- so a new family can never
    # vanish from the page.
    other_rows: tuple[LedgerRow, ...] = ()
    group_rows: tuple[GroupRow, ...] = ()
    group_counts: tuple[str, ...] = ()
    runs: tuple[RunRow, ...] = ()
    failed: tuple[str, ...] = ()
    left_out: tuple[str, ...] = ()
    provenance: CharacterProvenance


def all_character_ledger_rows(report: CharacterReport) -> Iterator[LedgerRow]:
    """Every finding row on the character page, in the order the page draws them."""
    yield from report.direction_rows
    yield from report.repeat_rows
    yield from report.other_rows
