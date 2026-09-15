# ABOUTME: Behaviour tests for the raid report view model and its row walker.
# ABOUTME: The walker is checked against the model's own fields, not a hand-kept list.

from wowperf.domain.report.model import (
    Badge,
    LedgerRow,
    PlayerCard,
    Provenance,
    Section,
    SectionState,
)
from wowperf.domain.report.raid_frame import RaidHeader
from wowperf.domain.report.raid_model import RaidReport, all_raid_ledger_rows


def a_section(state: SectionState = SectionState.PRESENT, reason: str = "") -> Section:
    return Section(state=state, reason=reason)


def a_ledger_row(**changes: object) -> LedgerRow:
    row = LedgerRow(
        finding_id="deaths.total",
        title="Two deaths cost the raid a wipe",
        title_before="Two deaths cost the raid a wipe",
        detail="Both deaths happened during the third intermission.",
        badge=Badge(label="measured", tint="badge-measured"),
    )
    return row.model_copy(update=changes)


def a_raid_header(**changes: object) -> RaidHeader:
    header = RaidHeader(
        boss="Emberkin",
        difficulty="Mythic",
        outcome="Killed",
        partition="Partition 1",
        size=20,
    )
    return header.model_copy(update=changes)


def a_raid_report(**changes: object) -> RaidReport:
    report = RaidReport(
        header=a_raid_header(),
        ledger_decomposition=(),
        damage=a_section(SectionState.WITHHELD, "the attempt did not kill"),
        deaths=(),
        interrupts=(),
        players=(),
        observations=(),
        provenance=Provenance(
            report_code="abc123", fight_id=2, fetched_at="2026-09-05 14:02",
        ),
    )
    return report.model_copy(update=changes)


def a_raid_report_with_one_row_in_every_field(row_fields: set[str]) -> RaidReport:
    updates = {name: (a_ledger_row(finding_id=f"finding-in-{name}"),) for name in row_fields}
    return a_raid_report(**updates)


def test_every_field_holding_rows_is_walked() -> None:
    """The walker is the icon resolver's only map of the page.

    A row whose ability reaches the page without reaching the resolver draws
    nothing and reports nothing -- the failure is a missing picture, which no
    other test would see. So the walker is checked against the model's own
    fields rather than against a list somebody kept in step by hand.
    """
    row_fields = {
        name
        for name, field in RaidReport.model_fields.items()
        if field.annotation == tuple[LedgerRow, ...]
    }
    assert row_fields, "no field on the model holds rows at all"

    report = a_raid_report_with_one_row_in_every_field(row_fields)
    walked = {row.finding_id for row in all_raid_ledger_rows(report)}

    assert walked == {f"finding-in-{name}" for name in row_fields}


def test_a_players_own_rows_are_walked_too() -> None:
    """`PlayerCard` is reused whole, including the two row fields it already carries.

    Task 6's per-card comparison rows land on `spell_and_talent_rows`, exactly
    as they do on the Mythic+ page's own player cards, and a walker that only
    knew about `RaidReport`'s own fields would leave every one of those icons
    unresolved -- the same failure this whole function exists to prevent, one
    level deeper.
    """
    card = PlayerCard(
        name="Emberkin",
        class_name="Druid",
        spec="Balance",
        colour="#ff7c0a",
        stats_line="140 casts in 6:12 of the fight",
        damage_rows=(a_ledger_row(finding_id="finding-in-player-damage"),),
        spell_and_talent=a_section(),
        spell_and_talent_rows=(a_ledger_row(finding_id="finding-in-player-spell"),),
    )
    report = a_raid_report(players=(card,))

    walked = {row.finding_id for row in all_raid_ledger_rows(report)}

    assert walked == {"finding-in-player-damage", "finding-in-player-spell"}
