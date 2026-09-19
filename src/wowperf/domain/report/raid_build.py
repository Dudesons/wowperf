# ABOUTME: Turns a loaded boss fight and its findings into the value the raid template renders.
# ABOUTME: A sibling of build.py: no route and no timeline, and a Damage tab a wipe withholds.

from collections.abc import Sequence

from wowperf.domain.analysis.attempt_shape import WITHHELD_ID
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Finding
from wowperf.domain.model import Player
from wowperf.domain.report.alive_chart import build_alive_chart
from wowperf.domain.report.build import _check_unique_finding_ids
from wowperf.domain.report.deaths import HEALTH_METHOD, build_deaths
from wowperf.domain.report.finding_tooltip import tooltips_by_finding_id
from wowperf.domain.report.frame import NO_COMPARISON_RAN, PARSE_UNAVAILABLE_ID
from wowperf.domain.report.ledger import (
    build_observations,
    build_summary_pointers,
    ledger_row,
    place_rows,
    placed_finding_ids,
)
from wowperf.domain.report.model import (
    LedgerRow,
    Provenance,
    ReferenceRecord,
    Section,
    SectionState,
)
from wowperf.domain.report.raid_frame import build_raid_header
from wowperf.domain.report.raid_grid import build_raid_grid
from wowperf.domain.report.raid_ledger import RAID_DECOMPOSITION_IDS, RAID_PLACEMENTS
from wowperf.domain.report.raid_model import RaidReport
from wowperf.domain.report.raid_players import build_raid_players
from wowperf.domain.season import Consumables, Defensives, Externals, Roles, SelfResurrections

VERDICT_ID = "wipe.cause"
"""`classify_attempt`'s id for the verdict it reaches, when it reaches one.

Matched on the whole id, like `WITHHELD_ID` beside it: `wipe.cause` is never
re-minted per raider, so a prefix match would buy nothing a whole-id match
does not already have, and would silently widen to any future `wipe.cause.*`
sibling that is not the verdict itself.
"""


def _damage_section(findings: Sequence[Finding], rows: tuple[LedgerRow, ...]) -> Section:
    """The Damage tab: present when it has rows, withheld with the comparison's own reason.

    Matched by prefix and never by id. `compare_parse_axis` mints
    `compare.parse.unavailable` and `analyse_encounter` re-mints it as
    `compare.parse.unavailable.<slug>`, one per raider, so an equality test
    against the bare id matches nothing on any raid page: a wipe would then be
    withheld under "no reference run was fetched", which is false of an
    analysis that fetched one and was told the boss lived. Every consumer of
    these ids matches by prefix, and a prefix survives a suffix.

    Gated on the rows rather than on that finding's absence, because the two
    disagree on a kill where one raider's leaderboard answered and another's
    did not: that page has damage rows to show, and withholding the whole tab
    would hide one raider's measured figures because of another raider's
    missing sample.

    `section_for` is not reused for the same reason: its reason is resolved
    through `finding_by_id`, an exact match, which is the half that cannot
    hold here.
    """
    if rows:
        return Section(state=SectionState.PRESENT)
    unavailable = next(
        (finding for finding in findings if finding.id.startswith(PARSE_UNAVAILABLE_ID)), None
    )
    return Section(
        state=SectionState.WITHHELD,
        reason=unavailable.detail if unavailable else NO_COMPARISON_RAN,
    )


def build_raid_report(
    loaded: LoadedEncounter,
    findings: Sequence[Finding],
    subject: Player,
    compared_slugs: frozenset[str] | None,
    fetched_at: str,
    defensives: Defensives,
    consumables: Consumables,
    roles: Roles,
    externals: Externals = Externals(),
    self_resurrections: SelfResurrections = SelfResurrections(),
    reference_records: tuple[ReferenceRecord, ...] = (),
) -> RaidReport:
    """Everything the raid page shows, decided here so the template decides nothing.

    `build_report`'s shape with the keystone half absent. `fetched_at` is a
    parameter rather than a clock read, because the domain performs no I/O and
    the same inputs must render the same report; `defensives`, `consumables`,
    `roles`, `externals` and `self_resurrections` are data files an adapter
    loads for the same reason. `subject` is the raider who was asked about and
    decides which card the Players tab opens on, nothing else: which card a
    comparison row reaches is decided by the slug the finding carries.
    `compared_slugs` is who a comparison was asked for, and `None` means none
    was asked for at all.

    Four of `build_report`'s parameters are deliberately absent, and each
    absence is a fact about a raid rather than an omission. There is no
    `narrative`: section 11 does not give `raid` that flag. There is no
    `speed`: a boss fight has no route to compare, which is why this page has
    no Route and tempo tab either. There is no `throughput`:
    `--throughput-ceiling` is not a raid flag. And there are no
    `comparison_measures`: a raid card carries no comparison tables, and the
    measures themselves are computed from a `LoadedRun`, which this path never
    holds. A parameter accepted and ignored is a lie the type system helps
    tell.
    """
    _check_unique_finding_ids(findings)

    # The attempt verdict's withheld notice is disclosed in Provenance and
    # nowhere else, so it is taken out before anything below can place it.
    # `severity.SEVERITY_BY_FAMILY` ranks the `wipe` family first, because a
    # verdict frames every row under it; a notice saying there is no verdict
    # inherits that rank, and would take the Summary's headline to say
    # nothing. Matched on the whole id rather than a prefix: `wipe.cause` is
    # the verdict itself and belongs on the page. It is read out here rather
    # than stripped, so it can still reach `titles_by_id` and `tooltips`
    # below; `placed_ids`, further down, keeps it from also falling through
    # `build_observations`'s catch-all once `report.verdict` has claimed it.
    verdict_notices = [one for one in findings if one.id == WITHHELD_ID]
    verdict_finding = next((one for one in findings if one.id == VERDICT_ID), None)
    findings = [one for one in findings if one.id != WITHHELD_ID]

    titles_by_id = {finding.id: finding.title for finding in findings}
    # Built once, here, because this is where `loaded`, the per-actor aura
    # tables and the defensives data file are all already in hand. Every row
    # builder below looks a panel up and none of them computes one.
    tooltips = tooltips_by_finding_id(findings, loaded, defensives)
    verdict = (
        ledger_row(verdict_finding, titles_by_id, tooltips) if verdict_finding else None
    )
    players = build_raid_players(
        loaded, findings, subject, compared_slugs, titles_by_id, tooltips
    )
    grid = build_raid_grid(loaded.players, loaded.damage_taken, roles, findings)
    # `Death.timestamp_ms` and `Resurrection.timestamp_ms` sit on the report's
    # own clock -- the one `Encounter.start_ms` sits on too, per
    # `deaths.py::_when`'s identical subtraction -- while `build_alive_chart`'s
    # x axis expects an elapsed clock starting at zero, the clock its own
    # tests are written against. Passing the raw timestamps through would
    # collapse every event onto the chart's right edge on any fight that does
    # not start at report time zero, which no real fight does.
    fight_start_ms = loaded.encounter.start_ms
    alive_chart = build_alive_chart(
        loaded.encounter.size or len(loaded.players),
        tuple(
            death.model_copy(
                update={"timestamp_ms": max(death.timestamp_ms - fight_start_ms, 0)}
            )
            for death in loaded.deaths
        ),
        tuple(
            rez.model_copy(update={"timestamp_ms": max(rez.timestamp_ms - fight_start_ms, 0)})
            for rez in loaded.resurrections
        ),
        duration_ms=loaded.encounter.end_ms - fight_start_ms,
        boss_percentage=loaded.encounter.boss_percentage,
    )

    ledger_decomposition = tuple(
        ledger_row(finding, titles_by_id, tooltips)
        for finding in findings
        if finding.seconds_lost is not None and finding.id in RAID_DECOMPOSITION_IDS
    )
    decomposition_ids = {row.finding_id for row in ledger_decomposition}
    placed_rows = place_rows(
        findings, titles_by_id, decomposition_ids, tooltips, placements=RAID_PLACEMENTS
    )
    summary_pointers = build_summary_pointers(
        findings, titles_by_id, decomposition_ids, tooltips
    )
    placed_ids = placed_finding_ids(ledger_decomposition, placed_rows, players)
    # `report.verdict` claims `wipe.cause` on its own, outside every field
    # `placed_finding_ids` reads back from -- no `RAID_PLACEMENTS` prefix
    # matches it, and it is left in `findings` rather than stripped, so
    # without this it would still fall through to `build_observations`'s
    # catch-all and draw the same finding a second time under "Other findings".
    if verdict_finding:
        placed_ids.add(verdict_finding.id)

    damage = _damage_section(findings, placed_rows["damage_rows"])

    withheld: list[str] = []
    for notice in verdict_notices:
        withheld.append(f"Why this attempt ended: {notice.detail}")
    if damage.state is SectionState.WITHHELD:
        withheld.append(f"Damage against other kills: {damage.reason}")

    # One line per distinct reason, never one per raider. A wipe withholds
    # every raider's comparison for the same reason -- the boss lived, which is
    # a fact about the attempt and not about any of them -- and the Damage line
    # above has already given it, so restating it once per card would print the
    # same paragraph twenty-one times on a twenty-player page.
    #
    # `build_report` does restate it per card, and this is the one place the
    # two siblings deliberately differ: the rule was always "say it once when
    # the reason is about the whole fight, per card when it is about that
    # card", and a keystone roster of five made the repetition read as emphasis
    # rather than as the bug it is at twenty. Do not fix this back.
    #
    # A raider whose reason differs is untouched: that reason is about them,
    # and the fight-wide line does not cover it. And the suppression is on this
    # list alone -- every card keeps its own withheld reason on the card, where
    # a reader looking at one raider needs it without scrolling here.
    #
    # No branch on the Damage section's own state is needed: `Section.reason` is
    # "" unless a section was withheld, so a present Damage tab has stated
    # nothing and suppresses nothing.
    stated_for_the_whole_fight = damage.reason

    # `--no-compare` fetched no reference at all, so the whole fight gets one
    # report-level line rather than one per card -- a line per raider here
    # would say a comparison for each of them was asked for and refused, when
    # none was ever asked for. When a comparison did run, a raider nobody
    # asked for is left off this list for the same reason: their comparison
    # was not withheld, it was not requested.
    if compared_slugs is None:
        withheld.append(f"Spell and talent comparison: {NO_COMPARISON_RAN}")
    else:
        for card in players:
            if (
                card.spell_and_talent.state is SectionState.WITHHELD
                and card.slug in compared_slugs
                and card.spell_and_talent.reason != stated_for_the_whole_fight
            ):
                withheld.append(
                    f"Spell and talent comparison for {card.name}: {card.spell_and_talent.reason}"
                )

    deaths = build_deaths(loaded, defensives, consumables, externals, self_resurrections)
    methods = (HEALTH_METHOD,) if any(card.health_badge for card in deaths) else ()

    return RaidReport(
        header=build_raid_header(loaded.encounter),
        verdict=verdict,
        ledger_decomposition=ledger_decomposition,
        summary_pointers=summary_pointers,
        damage_rows=placed_rows["damage_rows"],
        damage=damage,
        mechanics_rows=placed_rows["mechanics_rows"],
        grid=grid,
        deaths=deaths,
        death_rows=placed_rows["death_rows"],
        interrupts=placed_rows["interrupts"],
        players=players,
        group_rows=placed_rows["group_rows"],
        observations=build_observations(findings, placed_ids, titles_by_id, tooltips),
        provenance=Provenance(
            report_code=loaded.encounter.report_code,
            fight_id=loaded.encounter.fight_id,
            fetched_at=fetched_at,
            references=reference_records,
            withheld=tuple(withheld),
            methods=methods,
        ),
        alive_chart=alive_chart,
    )
