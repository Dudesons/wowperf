# ABOUTME: The night page's view model: every judgement its two-dropdown page makes.
# ABOUTME: A sibling of RaidReport and ProgressionReport -- it reuses RaidReport whole, per pull.

from wowperf.domain.base import Frozen
from wowperf.domain.night import FailedPull
from wowperf.domain.report.model import LedgerRow
from wowperf.domain.report.raid_model import RaidReport, all_raid_ledger_rows


class NightHeader(Frozen):
    """The one fact printed above a night report's two dropdowns.

    Neither a boss name nor a single outcome belongs here the way `RaidHeader`
    and `ProgressionHeader` carry one apiece: this page covers every boss the
    report pulled, at whatever difficulty each was pulled, so there is no one
    boss or verdict to head the page with.
    """

    report_code: str


class PullSection(Frozen):
    """One pull, already analysed as a full raid report, and which stream tier produced it.

    `report` is the same view model `wowperf raid` builds for one pull on its
    own; the night page reuses it whole rather than inventing a second shape
    for the same judgement, so a death card or a grid cell means the same
    thing whichever command drew it.

    `tier` is one of "none", "trimmed" or "deep" -- the stream depth the pull
    was deepened at. A reader comparing two pulls needs to know they were not
    fetched at the same depth before reading anything into a difference
    between them, which is a fact a bare `RaidReport` cannot state on its own.
    """

    report: RaidReport
    tier: str


class BossSection(Frozen):
    """One boss's pulls, in the order the report's fight list gave them.

    Present even when `pulls` is empty: a boss whose every attempt was a
    reset, or whose every attempt failed to deepen, is still a boss the night
    pulled, and the page says so rather than dropping it -- the same ruling
    `LoadedNight` already makes one layer down, in `night.py`.
    """

    boss_name: str
    pulls: tuple[PullSection, ...] = ()


class NightReport(Frozen):
    """Every boss and every pull in one report, as the night page renders it.

    `total_pulls` is the sum of every `BossSection.pulls` length, stated once
    rather than left for a reader to add up themselves -- the figure a
    builder that grouped a pull under the wrong boss would get wrong first.

    `failed_pulls` carries the pulls a report held but could not deepen, so a
    night is never shown as shrunk without saying why -- the same records
    `LoadedNight.failed_pulls` already carries, reused here rather than
    reduced to a count.

    `observations` is this page's own catch-all, distinct from the
    `observations` nested inside each pull's own `PullSection.report`: a
    finding true of the whole night rather than of any one pull -- today,
    that the page draws no parse axis at all -- is stated here once instead
    of being repeated on every pull's tab.
    """

    header: NightHeader
    bosses: tuple[BossSection, ...] = ()
    total_pulls: int = 0
    failed_pulls: tuple[FailedPull, ...] = ()
    observations: tuple[LedgerRow, ...] = ()


def all_night_ledger_rows(report: NightReport) -> tuple[LedgerRow, ...]:
    """Every finding row on the night page: each pull's own rows, plus the page's own.

    A tuple rather than the `Iterator` its raid-page sibling returns: a night
    page walks this more than once -- once for the icon address map, once for
    a page-level check that a disclosure appears exactly once -- and a
    generator yields nothing on the second pass.

    Delegates each pull to `all_raid_ledger_rows` rather than re-listing
    `RaidReport`'s row fields here, so the two walkers cannot drift apart: a
    row family added to the raid page is reached by every pull on the night
    page without this function changing.
    """
    rows: list[LedgerRow] = []
    for boss in report.bosses:
        for pull in boss.pulls:
            rows.extend(all_raid_ledger_rows(pull.report))
    rows.extend(report.observations)
    return tuple(rows)
