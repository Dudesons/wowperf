# ABOUTME: Turns a Report into one self-contained HTML string. The only module importing jinja2.
# ABOUTME: The template loops and escapes; every decision was already made in report/build.py.

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from wowperf.domain.ports import IconSource
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


def _icon_uris(report: Report, icons: IconSource) -> dict[int, str]:
    """Every ability the page can draw, resolved once each, in the order it is met.

    Only the adapter can build this: which ids resolve is a question about a CDN
    and a cache, and the builder that made the report is forbidden from asking it.
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
            uri = icons.data_uri(ability_id)
            if uri is not None:
                resolved[ability_id] = uri
    for row in all_ledger_rows(report):
        if row.ability_id is None or row.ability_id in asked:
            continue
        asked.add(row.ability_id)
        uri = icons.data_uri(row.ability_id)
        if uri is not None:
            resolved[row.ability_id] = uri
    for player in report.players:
        if player.timeline is None:
            continue
        for cooldown in player.timeline.cooldowns:
            if cooldown.ability_id is None or cooldown.ability_id in asked:
                continue
            asked.add(cooldown.ability_id)
            uri = icons.data_uri(cooldown.ability_id)
            if uri is not None:
                resolved[cooldown.ability_id] = uri
    return resolved


def render(report: Report, icons: IconSource | None = None) -> str:
    """One self-contained HTML document: one inline script that only shows and hides,
    no network, no external font.

    Without an `icons` source the page is drawn exactly as it is without icons:
    the ids on the view model are inert until something can turn them into bytes.
    """
    uris = {} if icons is None else _icon_uris(report, icons)
    return _environment().get_template(TEMPLATE_NAME).render(report=report, icons_by_id=uris)
