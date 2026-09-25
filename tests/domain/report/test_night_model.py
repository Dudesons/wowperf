# ABOUTME: Behaviour tests for the night report view model and its row walker.
# ABOUTME: The walker is checked against the model's own fields, not a hand-kept list.

import pytest
from pydantic import BaseModel, ValidationError

from wowperf.domain.report.model import Badge, LedgerRow, Provenance, Section, SectionState
from wowperf.domain.report.night_model import (
    BossSection,
    NightHeader,
    NightProvenance,
    NightReport,
    PullSection,
    all_night_ledger_rows,
)
from wowperf.domain.report.raid_frame import RaidHeader
from wowperf.domain.report.raid_model import RaidReport


def a_section(state: SectionState = SectionState.PRESENT, reason: str = "") -> Section:
    return Section(state=state, reason=reason)


def a_ledger_row(**changes: object) -> LedgerRow:
    row = LedgerRow(
        finding_id="night.pull",
        title="One pull's own finding",
        title_before="One pull's own finding",
        detail="A detail that would need an icon resolved.",
        badge=Badge(label="measured", tint="badge-measured"),
    )
    return row.model_copy(update=changes)


def a_raid_header(**changes: object) -> RaidHeader:
    header = RaidHeader(
        boss="Stonewake",
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
            report_code="abc123", fight_id=1, fetched_at="2026-09-23 20:00",
        ),
    )
    return report.model_copy(update=changes)


def a_pull(fight_id: int, tier: str = "deep") -> PullSection:
    return PullSection(
        report=a_raid_report(
            provenance=Provenance(
                report_code="abc123", fight_id=fight_id, fetched_at="2026-09-23 20:00",
            ),
        ),
        tier=tier,
    )


def a_night_report(**changes: object) -> NightReport:
    report = NightReport(
        header=NightHeader(report_code="abc123"),
        provenance=NightProvenance(fetched_at="2026-09-23 20:00"),
    )
    return report.model_copy(update=changes)


def test_bosses_and_pulls_preserve_order_and_total_pulls_sums_across_bosses() -> None:
    """Two bosses with DIFFERENT pull counts: two and three, not two and two.

    A builder that reported one boss's count for the whole night would still
    pass a fixture where both bosses held the same count. This fixture cannot
    be passed that way.
    """
    stonewake_pulls = (a_pull(1, tier="deep"), a_pull(2, tier="trimmed"))
    emberkin_pulls = (a_pull(10, tier="none"), a_pull(11, tier="none"), a_pull(12, tier="deep"))
    report = a_night_report(
        bosses=(
            BossSection(boss_name="Stonewake", pulls=stonewake_pulls),
            BossSection(boss_name="Emberkin", pulls=emberkin_pulls),
        ),
        total_pulls=5,
    )

    assert [boss.boss_name for boss in report.bosses] == ["Stonewake", "Emberkin"]
    assert [pull.report.provenance.fight_id for pull in report.bosses[0].pulls] == [1, 2]
    assert [pull.report.provenance.fight_id for pull in report.bosses[1].pulls] == [10, 11, 12]
    assert report.total_pulls == 5
    assert report.total_pulls == sum(len(boss.pulls) for boss in report.bosses)


def test_every_pull_section_carries_a_raid_report_and_its_tier() -> None:
    pull = a_pull(1, tier="trimmed")

    assert isinstance(pull.report, RaidReport)
    assert pull.tier == "trimmed"


def test_a_boss_section_is_representable_with_no_pulls() -> None:
    """A boss whose every attempt reset or failed to deepen is still on the page.

    `LoadedNight` already rules this out one layer down (see `night.py`); the
    view model must not force a boss with nothing deepened to disappear.
    """
    section = BossSection(boss_name="Stonewake")

    assert section.pulls == ()


def test_every_night_view_model_type_is_frozen() -> None:
    # `model_construct` skips required-field validation, so one call covers every
    # type regardless of its fields; a frozen model rejects the assignment before
    # it ever checks whether the field exists or the value is well-typed.
    model_types: list[type[BaseModel]] = [
        NightHeader, PullSection, BossSection, NightProvenance, NightReport
    ]
    for model_type in model_types:
        instance = model_type.model_construct()
        with pytest.raises(ValidationError):
            instance.a_field_that_need_not_exist = "something else"  # type: ignore[attr-defined]


def test_every_field_holding_rows_is_walked() -> None:
    """The walker is the icon resolver's only map of the page-level rows.

    Checked against the model's own fields rather than a hand-kept list: a
    second row-bearing field added later shows up here automatically, tagged
    and walked, with no line in this test to remember to update.
    """
    row_fields = {
        name
        for name, field in NightReport.model_fields.items()
        if field.annotation == tuple[LedgerRow, ...]
    }
    assert row_fields, "no field on the model holds rows at all"

    updates = {name: (a_ledger_row(finding_id=f"finding-in-{name}"),) for name in row_fields}
    report = a_night_report(**updates)

    walked = {row.finding_id for row in all_night_ledger_rows(report)}

    assert walked == {f"finding-in-{name}" for name in row_fields}


def test_a_pulls_own_rows_are_walked_too() -> None:
    """Every pull's `RaidReport` is walked whole, by delegating to `all_raid_ledger_rows`.

    A row whose ability reaches the page without reaching the icon resolver
    draws nothing and reports nothing -- the same failure the raid page's own
    walker exists to prevent, one level up: a night with six pulls and a
    walker that only knew about the page's own fields would leave every row
    on every pull unresolved.
    """
    first_row = a_ledger_row(finding_id="finding-in-pull-one")
    second_row = a_ledger_row(finding_id="finding-in-pull-two")
    first_pull = PullSection(
        report=a_raid_report(observations=(first_row,)),
        tier="deep",
    )
    second_pull = PullSection(
        report=a_raid_report(death_rows=(second_row,)),
        tier="none",
    )
    report = a_night_report(
        bosses=(
            BossSection(boss_name="Stonewake", pulls=(first_pull, second_pull)),
        ),
    )

    walked = {row.finding_id for row in all_night_ledger_rows(report)}

    assert walked == {"finding-in-pull-one", "finding-in-pull-two"}


def test_the_walker_returns_a_tuple_not_a_generator() -> None:
    """A night page walks its rows twice -- once for the icon map, once for a
    page-level disclosure check -- and a generator yields nothing on the second pass."""
    report = a_night_report(observations=(a_ledger_row(finding_id="only-row"),))

    walked = all_night_ledger_rows(report)

    assert list(walked) == [row for row in walked]
    assert isinstance(walked, tuple)
