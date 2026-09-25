# ABOUTME: Turns a Report into one HTML string that loads only its icons; the only jinja2 import.
# ABOUTME: The template loops and escapes; every decision was already made in report/build.py.

from collections.abc import Iterable, Sequence
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from wowperf.adapters.render.icons import CdnIcons
from wowperf.domain.report.model import DeathCard, LedgerRow, PlayerCard, Report, all_ledger_rows
from wowperf.domain.report.night_model import NightReport, all_night_ledger_rows
from wowperf.domain.report.progression_model import (
    ProgressionReport,
    all_progression_ledger_rows,
)
from wowperf.domain.report.raid_model import GridColumn, RaidReport, all_raid_ledger_rows

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "report.html.j2"
RAID_TEMPLATE_NAME = "raid.html.j2"
PROGRESSION_TEMPLATE_NAME = "progression.html.j2"
NIGHT_TEMPLATE_NAME = "night.html.j2"


def _environment() -> Environment:
    """Autoescaping is mandatory, not a default worth overriding.

    Player names, pack names and killing blows all come from an external API
    and all land in HTML. A `|safe` anywhere in this template would let a
    character name execute markup in whoever opens the file.
    """
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        # Jinja drops a template's own final newline by default; keeping it means
        # the rendered file ends the same way any other text file in this repo does.
        keep_trailing_newline=True,
    )


def _icon_addresses(
    deaths: Sequence[DeathCard],
    rows: Iterable[LedgerRow],
    players: Sequence[PlayerCard],
    icons: CdnIcons,
    grid_columns: Sequence[GridColumn] = (),
) -> dict[int, str]:
    """Every ability the page can draw, resolved once each, in the order it is met.

    Only the adapter can build this: which ids resolve is a question about a CDN,
    and the builder that made the report is forbidden from asking it.

    Shared by `render` and `render_raid`, which is why it takes the collections
    it walks rather than a whole `Report`: `deaths` and `players` are fields
    both view models carry verbatim (`DeathCard` and `PlayerCard` are reused
    whole), and `rows` is already the finished walk -- `render` passes
    `all_ledger_rows(report)`, `render_raid` passes
    `all_raid_ledger_rows(report)` -- so this function need not know which
    report shape it was given. Nothing here skips a raid player's timeline on
    purpose: `PlayerCard.timeline` is `None` on every card `build_raid_players`
    builds, so the loop below that walks a card's cooldowns is already a
    no-op for a raid page, exactly as if it had never been called.

    `grid_columns` defaults to empty because only the raid page has a grid at
    all -- `render` never passes it. It cannot be folded into `rows`:
    `_columns()` in `raid_grid.py` reads `Finding.ability_id` unconditionally,
    while `ledger_row()` only copies `ability_id` onto a row when
    `_split_title` can cut the finding's title at its own ability name exactly
    once. A `mechanics.ability.*` finding whose title cannot be cut that way
    still earns a grid column with an id `all_raid_ledger_rows` never carries,
    so the grid has to be walked on its own rather than trusted to arrive
    through a row that may have dropped it.

    Comparison tables are walked last. They were once left out, because every
    icon was embedded as base64 and these tables run to dozens of rows per
    player; walking them then meant carrying the art of every aura the sample
    kept up. An icon is an address now, so a row costs its URL and nothing
    else, and the reason for the exclusion went with the bytes. The `ability`
    macro still renders a bare name for an id that does not resolve, so the
    fallback the comparison table design names in its §12 is unchanged.

    Last, rather than first, because `asked` makes this first-one-wins and the
    page's own order is the one worth keeping: a death card's art is the same
    art either way, but resolving it there keeps the walk reading in the order
    a reader meets it.
    """
    resolved: dict[int, str] = {}
    asked: set[int] = set()
    for card in deaths:
        candidates = [card.killing_blow_id]
        candidates.extend(row.ability_id for row in card.timeline)
        for group in card.availability:
            candidates.extend(row.ability_id for row in group.rows)
        for ability_id in candidates:
            if ability_id is None or ability_id in asked:
                continue
            asked.add(ability_id)
            address = icons.url(ability_id)
            if address is not None:
                resolved[ability_id] = address
    for row in rows:
        if row.ability_id is None or row.ability_id in asked:
            continue
        asked.add(row.ability_id)
        address = icons.url(row.ability_id)
        if address is not None:
            resolved[row.ability_id] = address
    for player in players:
        if player.timeline is None:
            continue
        for cooldown in player.timeline.cooldowns:
            if cooldown.ability_id is None or cooldown.ability_id in asked:
                continue
            asked.add(cooldown.ability_id)
            address = icons.url(cooldown.ability_id)
            if address is not None:
                resolved[cooldown.ability_id] = address
    for player in players:
        for table in player.comparison_tables:
            for compared in table.rows:
                if compared.ability_id is None or compared.ability_id in asked:
                    continue
                asked.add(compared.ability_id)
                address = icons.url(compared.ability_id)
                if address is not None:
                    resolved[compared.ability_id] = address
    for column in grid_columns:
        if column.ability_id in asked:
            continue
        asked.add(column.ability_id)
        address = icons.url(column.ability_id)
        if address is not None:
            resolved[column.ability_id] = address
    return resolved


def render(report: Report, icons: CdnIcons | None = None) -> str:
    """One HTML document: one inline script that only shows and hides, no external
    font, and no request of its own but the icons.

    Without an `icons` source the page is drawn exactly as it is without icons:
    the ids on the view model are inert until something can address them.
    """
    addresses = (
        {}
        if icons is None
        else _icon_addresses(report.deaths, all_ledger_rows(report), report.players, icons)
    )
    return _environment().get_template(TEMPLATE_NAME).render(
        report=report, icons_by_id=addresses
    )


def render_raid(report: RaidReport, icons: CdnIcons | None = None) -> str:
    """`render`'s counterpart for the seven-tab raid page: same environment,
    same icon resolver, one different template and one different row walk.

    Without an `icons` source the page draws exactly as `render` does without
    one: every ability id on the view model is inert until something can
    address it. `grid_columns` is passed separately from `report.grid` rather
    than left for `_icon_addresses` to find on its own -- see that function's
    docstring for why a grid column cannot be trusted to reach the resolver
    through a ledger row.
    """
    addresses = (
        {}
        if icons is None
        else _icon_addresses(
            report.deaths,
            all_raid_ledger_rows(report),
            report.players,
            icons,
            grid_columns=report.grid.columns if report.grid else (),
        )
    )
    return _environment().get_template(RAID_TEMPLATE_NAME).render(
        report=report, icons_by_id=addresses
    )


def _night_scopes(report: NightReport) -> dict[int, str]:
    """The id prefix each pull's markup is drawn under, keyed by the fight it came from.

    Every id under a pull carries this in front of it. Panel ids, finding ids
    and player slugs are unique inside one pull's report and repeat across
    pulls -- every pull draws its findings from the same analysers and its
    cards from the same roster -- so without a prefix one night page would
    carry the same element id once per pull, and every link into one of them
    would open whichever copy the browser reached first.

    A fight id is what the report itself calls a pull, and one report never
    gives two fights the same one, so it tells every pull on the page apart
    whichever boss it sits under, with no index to keep in step.

    Minted here and not in the template, which loops and decides nothing, and
    not in the builder either: which strings a document needs to keep its
    anchors apart is a fact about HTML, and `NightReport` is the same value
    whether anything renders it or not.
    """
    return {
        pull.report.provenance.fight_id: f"f{pull.report.provenance.fight_id}-"
        for boss in report.bosses
        for pull in boss.pulls
    }


def render_night(report: NightReport, icons: CdnIcons | None = None) -> str:
    """`render_raid`'s counterpart for a whole report: every pull on one page.

    The page is the raid page's seven panels drawn once per pull, so the icon
    walk is the raid page's walk widened to the night. `_icon_addresses` takes
    the collections it walks rather than a report -- its own docstring says why
    -- and that is what lets it be called once here over the night's
    collections instead of once per pull: what it is handed is every pull's
    deaths, every pull's players and every pull's grid columns, chained. One
    call means one `asked` set, so an ability met on two pulls is resolved once
    and the first occurrence wins, exactly as within a single page.

    `all_night_ledger_rows` is the row walk, and it already reaches the night's
    own `observations` as well as every pull's rows -- the disclosure that no
    parse axis was drawn lives there and nowhere else, so a per-pull walk would
    never meet it.

    Without an `icons` source the page draws exactly as the other three do
    without one: every ability id on the view model is inert until something
    can address it, and the `ability` macro renders a bare name.
    """
    pulls = [pull.report for boss in report.bosses for pull in boss.pulls]
    addresses = (
        {}
        if icons is None
        else _icon_addresses(
            tuple(card for one in pulls for card in one.deaths),
            all_night_ledger_rows(report),
            tuple(card for one in pulls for card in one.players),
            icons,
            grid_columns=tuple(
                column for one in pulls if one.grid for column in one.grid.columns
            ),
        )
    )
    return _environment().get_template(NIGHT_TEMPLATE_NAME).render(
        report=report, icons_by_id=addresses, scopes=_night_scopes(report)
    )


def render_progression(report: ProgressionReport, icons: CdnIcons | None = None) -> str:
    """`render_raid`'s counterpart for the five-tab progression page.

    `_icon_addresses` is not reused: it walks death cards and player cards, and
    this page has neither. Only a ledger row can name an ability here --
    `progression.repeat.ability` is the one finding that does -- so the walk is
    that single loop rather than a third caller of a function whose other two
    arguments would every time be empty.

    Without an `icons` source the page draws exactly as the other two do
    without one: every ability id on the view model is inert until something
    can address it, and the `ability` macro renders a bare name.
    """
    addresses: dict[int, str] = {}
    if icons is not None:
        for row in all_progression_ledger_rows(report):
            if row.ability_id is None or row.ability_id in addresses:
                continue
            address = icons.url(row.ability_id)
            if address is not None:
                addresses[row.ability_id] = address
    return _environment().get_template(PROGRESSION_TEMPLATE_NAME).render(
        report=report, icons_by_id=addresses
    )
