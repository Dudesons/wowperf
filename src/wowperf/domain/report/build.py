# ABOUTME: Turns a loaded run and its findings into the value the template renders.
# ABOUTME: Assembles what the modules beside it build; each judgement lives in one of those.

from collections import Counter
from collections.abc import Mapping, Sequence

from wowperf.domain.analysis.defensives import CEILING_WITHHELD_ID
from wowperf.domain.comparison.measures import PlayerMeasures
from wowperf.domain.comparison.sample import SpeedSample
from wowperf.domain.findings import Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.deaths import HEALTH_METHOD, build_deaths
from wowperf.domain.report.finding_tooltip import tooltips_by_finding_id
from wowperf.domain.report.frame import (
    NO_COMPARISON_RAN,
    SPEED_UNAVAILABLE_ID,
    build_header,
    sampled,
    section_for,
)
from wowperf.domain.report.ledger import (
    DECOMPOSITION_IDS,
    build_observations,
    build_summary_pointers,
    ledger_row,
    place_rows,
    placed_finding_ids,
)
from wowperf.domain.report.model import Provenance, ReferenceRecord, Report, SectionState
from wowperf.domain.report.players import NO_MEASURES, build_players
from wowperf.domain.report.timeline import build_timeline
from wowperf.domain.season import (
    Consumables,
    Defensives,
    Externals,
    SelfResurrections,
    ThroughputCooldowns,
)


def _check_unique_finding_ids(findings: Sequence[Finding]) -> None:
    """Raise before two findings' ids collapse into one DOM element id.

    This branch shipped the same defect three times: a finding id reused
    across rows, each fixed by hand once somebody noticed. Nothing short of a
    fixture ever caught it, because the next line's `titles_by_id` is a plain
    dict keyed by `finding.id` -- a duplicate silently loses a title, and
    `nests_inside` then points whatever pointed at it to the wrong row. A
    `Counter` finds every culprit in one pass rather than comparing each pair.
    """
    counts = Counter(finding.id for finding in findings)
    duplicates = sorted(finding_id for finding_id, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate finding ids reached the report builder: {duplicates}")


def build_report(
    loaded: LoadedRun,
    findings: Sequence[Finding],
    speed: SpeedSample | None,
    compared_slugs: frozenset[str] | None,
    subject: Player,
    narrative: str | None,
    fetched_at: str,
    defensives: Defensives,
    consumables: Consumables,
    externals: Externals = Externals(),
    self_resurrections: SelfResurrections = SelfResurrections(),
    throughput: ThroughputCooldowns = ThroughputCooldowns(),
    reference_records: tuple[ReferenceRecord, ...] = (),
    comparison_measures: Mapping[str, PlayerMeasures] = NO_MEASURES,
) -> Report:
    """Everything the page shows, decided here so the template decides nothing.

    `fetched_at` is a parameter rather than a clock read: the domain performs no
    I/O, and the same inputs must render the same report. `subject` is the
    player being analysed, from our own roster — it decides which card comes
    first. `compared_slugs` is who a parse comparison was asked for, and it
    decides which cards carry a comparison section at all; `None` means none
    was asked for, whoever the subject is. `defensives` is passed in
    rather than read here for the same reason the clock is: the data file is an
    adapter's job to load. `externals` and `self_resurrections` are data files
    too, loaded by the same adapter; they default to empty so a caller without
    them still builds every other section.

    `speed` is the sample itself, not a pick from it: the timeline draws its
    best-aligned duration-eligible member out of it, and gates its section on
    whether the leaderboard filled it at all. A single reference reconstructed
    for this signature would have to carry empty streams, and a reader of
    `speed.members[0].deaths` would then be told a fast run died nobody with no
    complaint from the type checker.
    `reference_records` is every candidate `_samples` weighed, loaded or not —
    carried onto the provenance unchanged, a link and never a figure.
    `comparison_measures` is what the comparison measured, keyed by player
    slug — threaded onto each card rather than recomputed here, so this layer
    never reaches back into the comparison for a figure it was already handed.
    """
    compared_speed = sampled(speed)
    timeline_section = section_for(findings, SPEED_UNAVAILABLE_ID, compared_speed)
    route_section = section_for(findings, SPEED_UNAVAILABLE_ID, compared_speed)

    _check_unique_finding_ids(findings)

    # The defensive-ceiling withheld notice is disclosed in Provenance and
    # nowhere else: left among `findings` it would match `PLACEMENTS`' bare
    # `defensives.` prefix and rank on the Players tab beside real per-ability
    # judgements, where "I could not judge this" would read as one of them.
    ceiling_notices = [one for one in findings if one.id == CEILING_WITHHELD_ID]
    findings = [one for one in findings if one.id != CEILING_WITHHELD_ID]

    titles_by_id = {finding.id: finding.title for finding in findings}
    # Built once, here, because this is where `loaded`, the per-actor aura
    # tables and the defensives data file are all already in hand. Every row
    # builder below looks a panel up and none of them computes one.
    tooltips = tooltips_by_finding_id(findings, loaded, defensives)
    players = build_players(
        loaded, findings, compared_slugs, subject, titles_by_id, defensives, throughput,
        tooltips, measures=comparison_measures,
    )

    withheld: list[str] = []
    for notice in ceiling_notices:
        withheld.append(f"Defensive ceiling: {notice.detail}")
    if timeline_section.state is SectionState.WITHHELD:
        withheld.append(f"Aligned timeline: {timeline_section.reason}")

    # `--no-compare` fetched no reference at all, so the whole run gets one
    # report-level line rather than one per card -- a line per player here
    # would say a comparison for each of them was asked for and refused, when
    # none was ever asked for. When a comparison did run, a player nobody
    # asked for is left off this list for the same reason: their comparison
    # was not withheld, it was not requested, and one such line per teammate
    # on every default run would bury the ones that mean something.
    if compared_slugs is None:
        withheld.append(f"Spell and talent comparison: {NO_COMPARISON_RAN}")
    else:
        for card in players:
            if card.spell_and_talent.state is SectionState.WITHHELD and card.slug in compared_slugs:
                withheld.append(
                    f"Spell and talent comparison for {card.name}: {card.spell_and_talent.reason}"
                )

    if route_section.state is SectionState.WITHHELD:
        withheld.append(f"Route and tempo: {route_section.reason}")

    ledger_decomposition = tuple(
        ledger_row(finding, titles_by_id, tooltips)
        for finding in findings
        if finding.seconds_lost is not None and finding.id in DECOMPOSITION_IDS
    )
    decomposition_ids = {row.finding_id for row in ledger_decomposition}
    placed_rows = place_rows(findings, titles_by_id, decomposition_ids, tooltips)
    summary_pointers = build_summary_pointers(
        findings, titles_by_id, decomposition_ids, tooltips
    )
    placed_ids = placed_finding_ids(ledger_decomposition, placed_rows, players)

    deaths = build_deaths(loaded, defensives, consumables, externals, self_resurrections)
    methods = (HEALTH_METHOD,) if any(card.health_badge for card in deaths) else ()

    return Report(
        header=build_header(loaded),
        narrative=narrative,
        ledger_decomposition=ledger_decomposition,
        summary_pointers=summary_pointers,
        timeline=build_timeline(loaded.run, speed, timeline_section),
        route=route_section,
        route_rows=placed_rows["route_rows"],
        deaths=deaths,
        death_rows=placed_rows["death_rows"],
        interrupts=placed_rows["interrupts"],
        players=players,
        group_rows=placed_rows["group_rows"],
        observations=build_observations(findings, placed_ids, titles_by_id, tooltips),
        provenance=Provenance(
            report_code=loaded.run.report_code,
            fight_id=loaded.run.fight_id,
            fetched_at=fetched_at,
            references=reference_records,
            withheld=tuple(withheld),
            methods=methods,
        ),
    )
