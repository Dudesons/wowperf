# ABOUTME: Whole-page rules for the raid report: its seven panels draw, and an ability named only
# ABOUTME: in a field unique to the raid model still reaches the icon resolver.

from wowperf.adapters.render.html import render_raid
from wowperf.adapters.render.icons import CdnIcons
from wowperf.domain.report.model import Badge, LedgerRow, Provenance, Section, SectionState
from wowperf.domain.report.raid_frame import RaidHeader
from wowperf.domain.report.raid_model import RaidReport

RAID_PANEL_ORDER = [
    "tab-summary",
    "tab-damage",
    "tab-mechanics",
    "tab-deaths",
    "tab-interrupts",
    "tab-players",
    "tab-provenance",
]
"""The exact seven top-level panel ids, in the order the page draws them.

Nothing in the templates or the renderer counts tabs -- the script matches a
button to a panel by string equality -- so this list is the only place the
count is stated, and a tab added without a line here is a tab no test sees.
"""


def a_raid_header(**overrides: object) -> RaidHeader:
    fields: dict[str, object] = {
        "boss": "Emberkin",
        "difficulty": "Mythic",
        "outcome": "Killed",
        "partition": "Partition 1",
        "size": 20,
    }
    fields.update(overrides)
    return RaidHeader(**fields)  # type: ignore[arg-type]


def a_ledger_row(**overrides: object) -> LedgerRow:
    fields: dict[str, object] = {
        "finding_id": "deaths.total",
        "title": "Two deaths cost the raid a wipe",
        "title_before": "Two deaths cost the raid a wipe",
        "detail": "Both deaths happened during the third intermission.",
        "badge": Badge(label="measured", tint="badge-measured"),
    }
    fields.update(overrides)
    return LedgerRow(**fields)  # type: ignore[arg-type]


def a_minimal_raid_report(**overrides: object) -> RaidReport:
    """The smallest raid report the template can render: every tab empty or withheld.

    A later task builds richer fixtures on top of this one -- see
    `a_raid_report_with_an_ability_only_in` below -- rather than replacing it,
    so keep new fields on top of these defaults instead of removing any.
    """
    fields: dict[str, object] = {
        "header": a_raid_header(),
        "ledger_decomposition": (),
        "damage": Section(state=SectionState.WITHHELD, reason="the attempt did not kill"),
        "deaths": (),
        "interrupts": (),
        "players": (),
        "observations": (),
        "provenance": Provenance(
            report_code="abc123", fight_id=2, fetched_at="2026-09-05 14:02",
        ),
    }
    fields.update(overrides)
    return RaidReport(**fields)  # type: ignore[arg-type]


def a_raid_report_with_an_ability_only_in(field: str, ability_id: int) -> RaidReport:
    """A raid report whose one resolvable ability id sits on a single named field.

    Named by field rather than by scenario, so a later task can reach for any
    of `all_raid_ledger_rows`' fields (or, for `damage_rows`, the tab it feeds)
    without a new fixture. `damage_rows` also needs its `Section` flipped to
    present, or the field would hold a row the Damage tab's own template never
    shows -- a fixture that renders nothing is not one this task's test can
    trust.
    """
    row = a_ledger_row(finding_id=f"finding-with-{field}", ability_id=ability_id)
    updates: dict[str, object] = {field: (row,)}
    if field == "damage_rows":
        updates["damage"] = Section(state=SectionState.PRESENT)
    return a_minimal_raid_report(**updates)


def test_a_raid_report_renders_its_seven_panels() -> None:
    html = render_raid(a_minimal_raid_report())

    assert html.count('<section class="panel"') == len(RAID_PANEL_ORDER)
    for panel in RAID_PANEL_ORDER:
        assert html.count(f'data-tab-for="{panel}"') == 1


def test_an_ability_a_damage_row_names_still_draws_its_icon() -> None:
    """The icon resolver walks the model, so a field it does not walk draws nothing.

    Every other icon failure is loud. This one is a missing picture on a page
    that otherwise renders, which is why the walk is asserted from a row in a
    field only the raid model has.
    """
    ability_id = 12345
    report = a_raid_report_with_an_ability_only_in(field="damage_rows", ability_id=ability_id)

    html = render_raid(report, CdnIcons({ability_id: "spell_holy_divineshield.jpg"}))

    assert f".i-{ability_id}" in html
