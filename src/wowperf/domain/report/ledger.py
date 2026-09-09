# ABOUTME: Findings turned into rows, and which tab each row belongs on.
# ABOUTME: Nesting and placement are stated here, copied from what the analysers measure.

from collections.abc import Sequence

from wowperf.domain.findings import Finding
from wowperf.domain.report.frame import (
    PARSE_UNAVAILABLE_ID,
    SPEED_UNAVAILABLE_ID,
    badge_for,
    format_seconds,
)
from wowperf.domain.report.model import LedgerRow, PlayerCard

DECOMPOSITION_IDS = ("compare.duration", "time.residual", "deaths.total")
"""Figures that contain others. They head the ledger; everything else is ranked beneath."""

NESTS_INSIDE = (
    ("time.gap.", "time.residual"),
    ("compare.downtime", "time.residual"),
    ("deaths.single.", "deaths.total"),
    ("deaths.chain.", "deaths.total"),
    ("deaths.repeat.", "deaths.total"),
    ("compare.route.skipped.", "trash.overage"),
)
"""Which figures are already contained by which, copied from the findings file's own warning.

Stated rather than inferred: the relationships come from what the analysers
measure, and they change when an analyser changes, not when a report renders.
`compare.duration` measures the gap against the median of the sample, while
every figure here is priced against this run's own route, so the two overlap
without one containing the other; it is a decomposition row rather than a
parent, so repeating it on every line would be noise.

Entries must stay mutually non-overlapping: `parent_of` resolves by first match
in tuple order, so a broader prefix placed ahead of a narrower one would
silently win and misattribute nesting.
"""


PLACEMENTS: tuple[tuple[str, str], ...] = (
    ("defensives.unused.", "death_rows"),
    ("consumables.", "death_rows"),
    ("deaths.", "death_rows"),
    ("compare.deaths", "death_rows"),
    ("time.gap.", "route_rows"),
    ("compare.downtime", "route_rows"),
    ("compare.route.", "route_rows"),
    (SPEED_UNAVAILABLE_ID, "route_rows"),
    ("trash.", "route_rows"),
    ("compare.confound.", "route_rows"),
    ("interrupts.", "interrupts"),
    ("compare.interrupts", "interrupts"),
    (PARSE_UNAVAILABLE_ID, "group_rows"),
    ("defensives.", "group_rows"),
    ("throughput.", "group_rows"),
)
"""Which tab's rows a finding family lands in: the first prefix that matches wins.

Unlike `NESTS_INSIDE`, the entries here overlap on purpose — `defensives.unused.`
is a death-shaped claim and the bare `defensives.` prefix is a rate — so order is
the rule and the narrow families come first. A finding no prefix matches is not
dropped: `build_observations` picks up everything unplaced. The player-card
families (`players.damage.`, `compare.spells.`, `compare.talents`,
`compare.uptime.`) are placed by `build_players` and are deliberately absent.
"""


def parent_of(finding_id: str) -> str | None:
    """The figure this one is already contained by, if any."""
    for prefix, parent in NESTS_INSIDE:
        if finding_id.startswith(prefix):
            return parent
    return None


def _split_title(finding: Finding) -> tuple[str, str, str]:
    """A finding's title cut at the ability it names, or whole when it cannot be.

    The cut is made only when the name appears exactly once. Absent, the
    analyser and its own title disagree; twice, and there is no way to say
    which one a reader means. Either way the row keeps its whole title and
    draws no icon, which is the same silent fallback every other missing icon
    already uses.

    The identity always comes from `ability_id`. The name only locates a
    substring already known to be there, so this recovers nothing from prose.
    """
    name = finding.ability_name
    if finding.ability_id is None or not name or finding.title.count(name) != 1:
        return finding.title, "", ""
    before, after = finding.title.split(name)
    return before, name, after


def ledger_row(finding: Finding, titles_by_id: dict[str, str]) -> LedgerRow:
    """Format one finding for display.

    `nests_inside` carries the parent finding's title, not its id: the id is
    an internal identifier and never belongs on a page a person reads. When
    the parent finding is not among this run's findings, `nests_inside` stays
    `None` — a pointer to a row that is not on the page is worse than silence.
    """
    parent_id = parent_of(finding.id)
    before, ability, after = _split_title(finding)
    return LedgerRow(
        finding_id=finding.id,
        title=finding.title,
        title_before=before,
        title_ability=ability,
        title_after=after,
        # Set only when the cut succeeded, so one field answers both "where does
        # the icon go" and "is there one at all".
        ability_id=finding.ability_id if ability else None,
        detail=finding.detail,
        badge=badge_for(finding.confidence),
        seconds=format_seconds(finding.seconds_lost),
        nests_inside=titles_by_id.get(parent_id) if parent_id is not None else None,
        evidence=finding.evidence,
    )


def _field_for(finding_id: str) -> str | None:
    return next((field for prefix, field in PLACEMENTS if finding_id.startswith(prefix)), None)


def collapse_repeated_details(rows: Sequence[LedgerRow]) -> tuple[LedgerRow, ...]:
    """Hoist the explanation a run of neighbouring rows shares onto the run's first row.

    A run is two or more consecutive rows whose `detail` is the same non-empty
    string. Findings of one family routinely differ in their figures and agree
    word for word on what those figures mean, and the same paragraph under four
    cards teaches a reader to stop reading it.

    Order never changes. It is the ranking `rank_findings` settled, and
    gathering equal details from across a tab would both reorder the tab and
    put the note over rows that never carried that explanation.
    """
    collapsed: list[LedgerRow] = []
    start = 0
    while start < len(rows):
        detail = rows[start].detail
        end = start + 1
        while end < len(rows) and rows[end].detail == detail:
            end += 1
        run = rows[start:end]
        if detail and len(run) > 1:
            collapsed.append(run[0].model_copy(update={"detail": "", "group_note": detail}))
            collapsed.extend(row.model_copy(update={"detail": ""}) for row in run[1:])
        else:
            collapsed.extend(run)
        start = end
    return tuple(collapsed)


def place_rows(
    findings: Sequence[Finding], titles_by_id: dict[str, str], exclude: set[str]
) -> dict[str, tuple[LedgerRow, ...]]:
    """Every finding's row, keyed by the `Report` field it lands in.

    `exclude` holds the ids the decomposition already claimed, so a timed
    `deaths.total` heads the ledger and does not also sit beneath the death
    cards. Order within a field is the order the findings arrived in:
    `rank_findings` has already sorted them, and one ranking authority is enough.
    """
    placed: dict[str, list[LedgerRow]] = {field: [] for _, field in PLACEMENTS}
    for finding in findings:
        if finding.id in exclude:
            continue
        field = _field_for(finding.id)
        if field is not None:
            placed[field].append(ledger_row(finding, titles_by_id))
    return {field: collapse_repeated_details(rows) for field, rows in placed.items()}


POINTER_COUNT = 5
"""How many losses the Summary points at: enough to show the run's shape, few enough to
stay a list."""


def build_summary_pointers(
    findings: Sequence[Finding], titles_by_id: dict[str, str], exclude: set[str]
) -> tuple[LedgerRow, ...]:
    """The first timed findings that are not decomposition rows, in the order given.

    `rank_findings` has already sorted the findings by seconds, descending, in
    the CLI. Re-sorting here would be a second ranking authority that could
    disagree with the findings file; taking the first few in order cannot.
    """
    timed = [
        finding
        for finding in findings
        if finding.seconds_lost is not None and finding.id not in exclude
    ]
    return tuple(ledger_row(finding, titles_by_id) for finding in timed[:POINTER_COUNT])


def placed_finding_ids(
    ledger_decomposition: Sequence[LedgerRow],
    placed_rows: dict[str, tuple[LedgerRow, ...]],
    players: Sequence[PlayerCard],
) -> set[str]:
    """Every finding id some field already claims.

    Read back off the fields themselves rather than recomputed from a prefix
    list: this is what keeps `build_observations` a structural partition
    instead of a second whitelist someone has to remember to update.
    """
    ids = {row.finding_id for row in ledger_decomposition}
    for rows in placed_rows.values():
        ids |= {row.finding_id for row in rows}
    for card in players:
        ids |= {row.finding_id for row in card.damage_rows}
        ids |= {row.finding_id for row in card.spell_and_talent_rows}
    return ids


def build_observations(
    findings: Sequence[Finding], placed_ids: set[str], titles_by_id: dict[str, str]
) -> tuple[LedgerRow, ...]:
    """Every finding no other section placed, in the order the analysis produced them.

    A finding lands here because it is missing from `placed_ids`, never
    because it matches an id prefix of its own — so an analyser that starts
    emitting a new finding family reaches the page automatically instead of
    being silently dropped until someone adds its prefix to a whitelist.
    """
    return collapse_repeated_details(
        [ledger_row(finding, titles_by_id) for finding in findings if finding.id not in placed_ids]
    )
