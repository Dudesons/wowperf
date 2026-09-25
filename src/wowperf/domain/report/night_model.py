# ABOUTME: The night page's view model: every judgement its two-dropdown page makes.
# ABOUTME: A sibling of RaidReport and ProgressionReport -- it reuses RaidReport whole, per pull.

from wowperf.domain.base import Frozen
from wowperf.domain.night import FailedPull
from wowperf.domain.report.model import LedgerRow
from wowperf.domain.report.progression_model import ProgressionReport, all_progression_ledger_rows
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
    """One pull, already analysed as a full raid report, and which tier it was drawn at.

    `report` is the same view model `wowperf raid` builds for one pull on its
    own; the night page reuses it whole rather than inventing a second shape
    for the same judgement, so a death card or a grid cell means the same
    thing whichever command drew it.

    `tier` is one of "none", "trimmed" or "deep" -- the depth this page drew
    the pull at. It is the builder's own reading of `--deep` and `--no-deaths`,
    not a record of what the loader bought; the two agree because one pair of
    values reaches both. A reader comparing two pulls needs to know they were
    not drawn at the same depth before reading anything into a difference
    between them, which is a fact a bare `RaidReport` cannot state on its own.
    """

    report: RaidReport
    tier: str


class BossSection(Frozen):
    """One boss's pulls, in the order the report's fight list gave them, and its summary.

    Present even when `pulls` is empty: a boss whose every attempt was a
    reset, or whose every attempt failed to deepen, is still a boss the night
    pulled, and the page says so rather than dropping it -- the same ruling
    `LoadedNight` already makes one layer down, in `night.py`.

    `summary` is the progression page for this boss, built whole by
    `build_progression_report`, or None when fewer than two pulls were drawn:
    nearly every progression finding compares attempts with each other, and one
    attempt leaves nothing to compare.
    """

    boss_name: str
    pulls: tuple[PullSection, ...] = ()
    summary: ProgressionReport | None = None


class NightProvenance(Frozen):
    """When the night was read, and what it could not show.

    `Provenance` is deliberately not reused, for the reason
    `ProgressionProvenance` already gives: it carries a `fight_id`, and a night
    is not one fight, and it carries `references`, the external candidates a
    comparison weighed, which this command never fetches at all. Each pull
    keeps its own `Provenance` inside its `RaidReport`, where a fight id is a
    fact rather than a guess.

    `fetched_at` is stated here rather than read off a pull, because a night
    whose every pull failed to load still has to say when it was read.

    `withheld` is prose built from `NightReport.failed_pulls` and from nothing
    else. Two independently gathered representations of the same fact drift,
    and then the page names one set of pulls in a list and another in a
    paragraph.

    `methods` states what depth the run asked for. It is prose rather than a
    `tier` field because on a `--deep` night the tier is per pull by design,
    and one field would be false of every pull the flag did not name --
    `PullSection.tier` is where a pull's own tier is stated. Without it, a
    reader who did not type the command cannot tell a Deaths tab that was
    suppressed from one that failed, and these pages get shared.
    """

    fetched_at: str
    withheld: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()


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
    provenance: NightProvenance
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
    page without this function changing. A boss's summary rows are walked
    through `all_progression_ledger_rows` for the same reason pulls go through
    `all_raid_ledger_rows`.
    """
    rows: list[LedgerRow] = []
    for boss in report.bosses:
        for pull in boss.pulls:
            rows.extend(all_raid_ledger_rows(pull.report))
        if boss.summary is not None:
            rows.extend(all_progression_ledger_rows(boss.summary))
    rows.extend(report.observations)
    return tuple(rows)
