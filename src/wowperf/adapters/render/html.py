# ABOUTME: Turns a Report into one self-contained HTML string. The only module importing jinja2.
# ABOUTME: The template loops and escapes; every decision was already made in report/build.py.

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from wowperf.domain.report.model import Report

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
        autoescape=select_autoescape(default_for_string=True, default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(report: Report) -> str:
    """One self-contained HTML document: no script, no network, no external font."""
    return _environment().get_template(TEMPLATE_NAME).render(report=report)
