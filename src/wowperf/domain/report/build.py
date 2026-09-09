# ABOUTME: Turns a loaded run and its findings into the value the template renders.
# ABOUTME: Assembles what the modules beside it build; each judgement lives in one of those.

from collections.abc import Sequence

from wowperf.domain.comparison.sample import ParseSample, SpeedSample
from wowperf.domain.findings import Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.deaths import HEALTH_METHOD, build_deaths
from wowperf.domain.report.frame import (
    PARSE_UNAVAILABLE_ID,
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
from wowperf.domain.report.players import build_players
from wowperf.domain.report.timeline import build_timeline
from wowperf.domain.season import Consumables, Defensives, Externals, SelfResurrections


def build_report(
    loaded: LoadedRun,
    findings: Sequence[Finding],
    speed: SpeedSample | None,
    parse: ParseSample | None,
    subject: Player,
    narrative: str | None,
    fetched_at: str,
    defensives: Defensives,
    consumables: Consumables,
    externals: Externals = Externals(),
    self_resurrections: SelfResurrections = SelfResurrections(),
    reference_records: tuple[ReferenceRecord, ...] = (),
) -> Report:
    """Everything the page shows, decided here so the template decides nothing.

    `fetched_at` is a parameter rather than a clock read: the domain performs no
    I/O, and the same inputs must render the same report. `subject` is the
    player being analysed, from our own roster — it decides whose card carries
    the spell-and-talent and uptime comparison rows. `defensives` is passed in
    rather than read here for the same reason the clock is: the data file is an
    adapter's job to load. `externals` and `self_resurrections` are data files
    too, loaded by the same adapter; they default to empty so a caller without
    them still builds every other section.

    `speed` and `parse` are the samples themselves, not a pick from them: the
    timeline draws its best-aligned duration-eligible member out of `speed`,
    and both gate their sections on whether the leaderboard filled them at all.
    A single reference reconstructed for this signature would have to carry
    empty streams, and a reader of `speed.members[0].deaths` would then be told
    a fast run died nobody with no complaint from the type checker.
    `reference_records` is every candidate `_samples` weighed, loaded or not —
    carried onto the provenance unchanged, a link and never a figure.
    """
    compared_speed = sampled(speed)
    timeline_section = section_for(findings, SPEED_UNAVAILABLE_ID, compared_speed)

    withheld: list[str] = []
    if timeline_section.state is SectionState.WITHHELD:
        withheld.append(f"Aligned timeline: {timeline_section.reason}")

    comparison_section = section_for(findings, PARSE_UNAVAILABLE_ID, sampled(parse))
    if comparison_section.state is SectionState.WITHHELD:
        withheld.append(f"Spell and talent comparison: {comparison_section.reason}")

    route_section = section_for(findings, SPEED_UNAVAILABLE_ID, compared_speed)
    if route_section.state is SectionState.WITHHELD:
        withheld.append(f"Route and tempo: {route_section.reason}")

    titles_by_id = {finding.id: finding.title for finding in findings}

    ledger_decomposition = tuple(
        ledger_row(finding, titles_by_id)
        for finding in findings
        if finding.seconds_lost is not None and finding.id in DECOMPOSITION_IDS
    )
    decomposition_ids = {row.finding_id for row in ledger_decomposition}
    placed_rows = place_rows(findings, titles_by_id, exclude=decomposition_ids)
    summary_pointers = build_summary_pointers(findings, titles_by_id, exclude=decomposition_ids)
    players = build_players(loaded, findings, parse, subject, titles_by_id)
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
        observations=build_observations(findings, placed_ids, titles_by_id),
        provenance=Provenance(
            report_code=loaded.run.report_code,
            fight_id=loaded.run.fight_id,
            fetched_at=fetched_at,
            references=reference_records,
            withheld=tuple(withheld),
            methods=methods,
        ),
    )
