# ABOUTME: Turns a Report into one HTML string that loads only its icons; the only jinja2 import.
# ABOUTME: The template loops and escapes; every decision was already made in report/build.py.

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from wowperf.adapters.render.icons import CdnIcons
from wowperf.domain.report.model import Report, all_ledger_rows

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "report.html.j2"


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


def _icon_addresses(report: Report, icons: CdnIcons) -> dict[int, str]:
    """Every ability the page can draw, resolved once each, in the order it is met.

    Only the adapter can build this: which ids resolve is a question about a CDN,
    and the builder that made the report is forbidden from asking it.

    A player card's comparison tables are deliberately not walked, so a table
    draws art only for an ability the page already carries for another reason --
    a death card, a ledger row or a player timeline. That is the fallback the
    comparison table design names in its §12, and the `ability` macro already
    renders a bare name for an id absent here.
    """
    resolved: dict[int, str] = {}
    asked: set[int] = set()
    for card in report.deaths:
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
    for row in all_ledger_rows(report):
        if row.ability_id is None or row.ability_id in asked:
            continue
        asked.add(row.ability_id)
        address = icons.url(row.ability_id)
        if address is not None:
            resolved[row.ability_id] = address
    for player in report.players:
        if player.timeline is None:
            continue
        for cooldown in player.timeline.cooldowns:
            if cooldown.ability_id is None or cooldown.ability_id in asked:
                continue
            asked.add(cooldown.ability_id)
            address = icons.url(cooldown.ability_id)
            if address is not None:
                resolved[cooldown.ability_id] = address
    return resolved


def render(report: Report, icons: CdnIcons | None = None) -> str:
    """One HTML document: one inline script that only shows and hides, no external
    font, and no request of its own but the icons.

    Without an `icons` source the page is drawn exactly as it is without icons:
    the ids on the view model are inert until something can address them.
    """
    addresses = {} if icons is None else _icon_addresses(report, icons)
    return _environment().get_template(TEMPLATE_NAME).render(
        report=report, icons_by_id=addresses
    )
