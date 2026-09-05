# ABOUTME: Behaviour tests for the report's catch-all section: every finding no other
# ABOUTME: section claims, computed structurally rather than by another id-prefix whitelist.

from tests.domain.report.test_build_frame import FETCHED, a_run
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_observations, build_report


def a_finding(finding_id: str, seconds: float | None = None, title: str = "x") -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail="detail",
        confidence=Confidence.DERIVED,
        seconds_lost=seconds,
    )


SUBJECT = Player(actor_id=1, name="Uglymage", class_name="Mage", spec="Arcane", item_level=680)


def a_loaded() -> LoadedRun:
    return LoadedRun(run=a_run(players=(SUBJECT,)))


def test_a_finding_no_section_claims_reaches_observations() -> None:
    # "trash.pull.0" and "defensives.Uglymage.45438" match no ledger prefix,
    # no "interrupts.", no "players.damage." and no comparison prefix —
    # findings that belong in observations, the catch-all section.
    findings = (
        a_finding("trash.pull.0", title="Pull 4 bought 0.0 forces per second"),
        a_finding("defensives.Uglymage.45438", title="Uglymage never cast Ice Block"),
    )
    report = build_report(a_loaded(), findings, None, None, SUBJECT, None, FETCHED)
    assert [row.finding_id for row in report.observations] == [
        "trash.pull.0",
        "defensives.Uglymage.45438",
    ]


def test_a_finding_claimed_by_the_ledger_does_not_also_reach_observations() -> None:
    findings = (a_finding("time.residual", seconds=300.0),)
    report = build_report(a_loaded(), findings, None, None, SUBJECT, None, FETCHED)
    assert report.observations == ()


def test_a_finding_claimed_by_interrupts_does_not_also_reach_observations() -> None:
    findings = (a_finding("interrupts.summary"),)
    report = build_report(a_loaded(), findings, None, None, SUBJECT, None, FETCHED)
    assert report.observations == ()


def test_a_finding_claimed_by_a_players_damage_row_does_not_also_reach_observations() -> None:
    findings = (a_finding("players.damage.0", title="Uglymage took 2.3x the group median"),)
    report = build_report(a_loaded(), findings, None, None, SUBJECT, None, FETCHED)
    assert report.observations == ()


def test_every_input_finding_is_placed_exactly_once() -> None:
    """The structural property the design demands: the union of every placed
    finding id — across the ledger, interrupts, every player card's damage and
    spell-and-talent rows, and observations — equals the input set exactly.
    Nothing dropped, nothing doubled.
    """
    findings = (
        a_finding("compare.duration", seconds=120.0, title="Total gap"),
        a_finding("time.gap.0", seconds=41.0, title="A 41 second gap"),
        a_finding("interrupts.summary", title="Three casts uninterrupted"),
        a_finding("players.damage.0", title="Uglymage took 2.3x the group median"),
        a_finding("trash.pull.0", title="Pull 4 bought 0.0 forces per second"),
        a_finding("defensives.Uglymage.45438", title="Uglymage never cast Ice Block"),
    )
    report = build_report(a_loaded(), findings, None, None, SUBJECT, None, FETCHED)

    placed_ids: list[str] = []
    placed_ids += [row.finding_id for row in report.ledger_decomposition]
    placed_ids += [row.finding_id for row in report.ledger_losses]
    placed_ids += [row.finding_id for row in report.interrupts]
    for card in report.players:
        placed_ids += [row.finding_id for row in card.damage_rows]
        placed_ids += [row.finding_id for row in card.spell_and_talent_rows]
    placed_ids += [row.finding_id for row in report.observations]

    assert sorted(placed_ids) == sorted(finding.id for finding in findings)
    assert len(placed_ids) == len(set(placed_ids))


def test_build_observations_takes_only_what_is_missing_from_placed_ids() -> None:
    findings = (a_finding("a.1"), a_finding("a.2"))
    rows = build_observations(findings, {"a.1"}, {})
    assert [row.finding_id for row in rows] == ["a.2"]
