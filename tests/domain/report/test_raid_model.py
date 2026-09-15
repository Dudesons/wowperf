# ABOUTME: Behaviour tests for the raid report view model and its row walker.
# ABOUTME: The walker is checked against the model's own fields, not a hand-kept list.

import inspect

import pytest
from pydantic import BaseModel, ValidationError

from wowperf.domain.report import raid_frame, raid_model
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

RAID_VIEW_MODEL_MODULES = (raid_model, raid_frame)
"""Where the raid page's view model is defined.

Two modules, where the Mythic+ model is one: `Report` and its `Header` are both
declared in `report.model`, while `RaidReport`'s header is a type of its own in
`raid_frame` -- a boss fight has no dungeon and no keystone level, so the
header could not be reused. A scan of `raid_model` alone would walk exactly one
class and miss the only bare number the raid page carries.
"""


def raid_view_model_types() -> list[type[BaseModel]]:
    """Every pydantic model the raid view model defines, `Frozen` or not.

    The raid counterpart of `test_model.view_model_types`, and filtering on
    `BaseModel` for the same reason: a type someone adds straight off
    `BaseModel` -- skipping `Frozen` by mistake -- still shows up here and fails
    the freeze check below instead of escaping a hand-written list. Exported for
    `test_raid_html_invariants.py`, which walks the same types against the
    allowlist of numbers that cannot hold a total.
    """
    return [
        obj
        for module in RAID_VIEW_MODEL_MODULES
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, BaseModel) and obj.__module__ == module.__name__
    ]


def test_the_raid_view_model_scan_reaches_both_of_its_modules() -> None:
    """The guard under every rule that walks these types.

    A scan that found nothing, or that found `RaidReport` and stopped, would
    leave the freeze check below and the no-total rule in the render invariants
    passing over an empty list. Both types are named because each stands for one
    of the two modules the scan has to reach.
    """
    found = raid_view_model_types()

    assert RaidReport in found
    assert RaidHeader in found


def test_every_raid_view_model_type_is_frozen() -> None:
    # `model_construct` skips required-field validation, so one call covers every
    # type regardless of its fields; a frozen model rejects the assignment before
    # it ever checks whether the field exists or the value is well-typed.
    for model_type in raid_view_model_types():
        instance = model_type.model_construct()
        with pytest.raises(ValidationError):
            instance.a_field_that_need_not_exist = "something else"  # type: ignore[attr-defined]


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
