# ABOUTME: Behaviour tests for the placement table: every finding family lands on one tab's rows.
# ABOUTME: Order in the table is the rule — the narrow death families precede the bare prefixes.

from collections.abc import Sequence

import pytest

from tests.domain.report.test_build_frame import FETCHED, NO_CONSUMABLES, NO_DEFENSIVES, a_run
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_report
from wowperf.domain.report.ledger import PLACEMENTS, place_rows
from wowperf.domain.report.model import LedgerRow, Report

SUBJECT = Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane", item_level=680)


def a_finding(finding_id: str, seconds: float | None = None, title: str = "x") -> Finding:
    # The title never starts with "<player> took ", so build_players never claims it.
    return Finding(
        id=finding_id,
        title=title,
        detail="detail",
        confidence=Confidence.DERIVED,
        seconds_lost=seconds,
    )


def a_loaded() -> LoadedRun:
    return LoadedRun(run=a_run(players=(SUBJECT,)))


def a_report_of(*findings: Finding) -> Report:
    return build_report(
        a_loaded(), findings, None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES
    )


def ids(rows: Sequence[LedgerRow]) -> list[str]:
    return [row.finding_id for row in rows]


# One representative id per family the analysers and comparisons emit today, and the
# field the design's table (spec §5.1) sends it to. `deaths.total`, `time.residual` and
# `compare.duration` are decomposition rows and are tested separately below.
FAMILY_HOMES = {
    "time.gap.0": "route_rows",
    "compare.downtime": "route_rows",
    "compare.route.skipped.0": "route_rows",
    "compare.route.extra.0": "route_rows",
    "compare.route.summary": "route_rows",
    "compare.route.unaligned": "route_rows",
    "compare.speed.unavailable": "route_rows",
    "trash.overage": "route_rows",
    "trash.pull.0": "route_rows",
    "compare.confound.affixes": "route_rows",
    "deaths.single.0": "death_rows",
    "deaths.chain.0": "death_rows",
    "deaths.repeat.Emberkin": "death_rows",
    "defensives.unused.45438": "death_rows",
    "consumables.unused.6262": "death_rows",
    "consumables.never.6262": "death_rows",
    "compare.deaths": "death_rows",
    "interrupts.ability.0": "interrupts",
    "interrupts.summary": "interrupts",
    "compare.interrupts": "interrupts",
    "compare.parse.unavailable": "group_rows",
    "defensives.emberkin.45438": "group_rows",
    "defensives.ceiling.45438": "group_rows",
    "throughput.alignment.12345": "group_rows",
    "throughput.ceiling.12345": "group_rows",
}

ROW_FIELDS = ("route_rows", "death_rows", "interrupts", "group_rows")


@pytest.mark.parametrize(("finding_id", "home"), sorted(FAMILY_HOMES.items()))
def test_each_family_lands_on_the_field_the_table_says(finding_id: str, home: str) -> None:
    report = a_report_of(a_finding(finding_id))
    assert ids(getattr(report, home)) == [finding_id]
    for other in ROW_FIELDS:
        if other != home:
            assert ids(getattr(report, other)) == [], other
    assert report.observations == ()


def test_a_family_the_table_does_not_know_reaches_the_catch_all() -> None:
    report = a_report_of(a_finding("healing.overheal.0"))
    assert ids(report.observations) == ["healing.overheal.0"]
    for field in ROW_FIELDS:
        assert ids(getattr(report, field)) == [], field


def test_a_timed_row_keeps_its_seconds_where_it_lands() -> None:
    # There is no page-wide list of losses; a gap is a route row with its cost.
    report = a_report_of(a_finding("time.gap.0", seconds=41.0))
    assert ids(report.route_rows) == ["time.gap.0"]
    assert report.route_rows[0].seconds == "0:41"


def test_a_timed_death_family_finding_lands_once_beneath_the_deaths() -> None:
    # A death-family finding carrying seconds stays with the deaths, with its
    # seconds, and nowhere else -- there is no page-wide ledger of losses.
    report = a_report_of(a_finding("defensives.unused.45438", seconds=12.0))
    assert ids(report.death_rows) == ["defensives.unused.45438"]
    assert report.death_rows[0].seconds == "0:12"
    assert report.observations == ()


def test_a_decomposition_row_is_never_placed_twice() -> None:
    # `deaths.total` matches the `deaths.` prefix, but a timed one heads the ledger and
    # must not also appear beneath the death cards.
    report = a_report_of(a_finding("deaths.total", seconds=64.0))
    assert ids(report.ledger_decomposition) == ["deaths.total"]
    assert report.death_rows == ()


def test_a_decomposition_id_without_seconds_falls_through_to_its_family() -> None:
    # A withheld `deaths.total` (no honest seconds) is still about deaths, and the Deaths
    # tab is where its reason belongs — not the catch-all.
    report = a_report_of(a_finding("deaths.total"))
    assert report.ledger_decomposition == ()
    assert ids(report.death_rows) == ["deaths.total"]


def test_rows_keep_the_order_they_arrived_in() -> None:
    # `rank_findings` already ordered them; placement must not re-sort.
    report = a_report_of(a_finding("time.gap.0", 90.0), a_finding("compare.downtime", 40.0))
    assert ids(report.route_rows) == ["time.gap.0", "compare.downtime"]


def test_the_narrow_death_families_precede_the_bare_defensives_prefix() -> None:
    # The table overlaps on purpose and resolves by order. If someone sorts it, this fails.
    prefixes = [prefix for prefix, _ in PLACEMENTS]
    assert prefixes.index("defensives.unused.") < prefixes.index("defensives.")


def test_place_rows_excludes_what_it_is_told_to() -> None:
    rows = place_rows(
        (a_finding("time.gap.0"), a_finding("time.gap.1")), {}, exclude={"time.gap.0"}
    )
    assert ids(rows["route_rows"]) == ["time.gap.1"]


def test_the_route_section_is_withheld_without_a_speed_reference() -> None:
    report = a_report_of(
        Finding(
            id="compare.speed.unavailable",
            title="No speed reference",
            detail="No timed run of this dungeon at this level was found.",
            confidence=Confidence.MEASURED,
        )
    )
    assert report.route.state.value == "withheld"
    assert report.route.reason == "No timed run of this dungeon at this level was found."
    # The finding itself still reaches the page once, on the tab it explains.
    assert ids(report.route_rows) == ["compare.speed.unavailable"]


def test_a_withheld_route_is_listed_under_provenance() -> None:
    report = a_report_of()
    assert any(line.startswith("Route and tempo: ") for line in report.provenance.withheld)
