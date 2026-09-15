# ABOUTME: Turns a Report into one HTML string that loads only its icons; the only jinja2 import.
# ABOUTME: The template loops and escapes; every decision was already made in report/build.py.

from collections.abc import Iterable, Sequence
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from wowperf.adapters.render.icons import CdnIcons
from wowperf.domain.report.model import DeathCard, LedgerRow, PlayerCard, Report, all_ledger_rows
from wowperf.domain.report.raid_model import RaidReport, all_raid_ledger_rows

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "report.html.j2"
RAID_TEMPLATE_NAME = "raid.html.j2"


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
) -> dict[int, str]:
    """Every ability the page can draw, resolved once each, in the order it is met.

    Only the adapter can build this: which ids resolve is a question about a CDN,
    and the builder that made the report is forbidden from asking it.

    Shared by `render` and `render_raid`, which is why it takes the three
    collections it walks rather than a whole `Report`: `deaths` and `players`
    are fields both view models carry verbatim (`DeathCard` and `PlayerCard`
    are reused whole), and `rows` is already the finished walk -- `render`
    passes `all_ledger_rows(report)`, `render_raid` passes
    `all_raid_ledger_rows(report)` -- so this function need not know which
    report shape it was given. Nothing here skips a raid player's timeline on
    purpose: `PlayerCard.timeline` is `None` on every card `build_raid_players`
    builds, so the loop below that walks a card's cooldowns is already a
    no-op for a raid page, exactly as if it had never been called.

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
    address it.
    """
    addresses = (
        {}
        if icons is None
        else _icon_addresses(report.deaths, all_raid_ledger_rows(report), report.players, icons)
    )
    return _environment().get_template(RAID_TEMPLATE_NAME).render(
        report=report, icons_by_id=addresses
    )
