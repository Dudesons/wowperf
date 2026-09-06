# ABOUTME: The skills make mechanical claims about the code; these keep the two in step.
# ABOUTME: A reference that has quietly drifted from the code is worse than no reference.

import re
from pathlib import Path

from typer.testing import CliRunner

from wowperf.cli import app

REPO_ROOT = Path(__file__).resolve().parents[1]
WCL_API_SKILL = REPO_ROOT / ".claude" / "skills" / "wcl-api" / "SKILL.md"
QUERIES = REPO_ROOT / "src" / "wowperf" / "adapters" / "wcl" / "queries.py"
ANALYZING_SKILL = REPO_ROOT / ".claude" / "skills" / "analyzing-a-run" / "SKILL.md"

FIELD_ROW = re.compile(
    r"^\|\s*`(?P<field>[^`]+)`\s*\|[^|]*\|\s*(?P<verified>\d{4}-\d{2}-\d{2})\s*\|"
    r"\s*(?P<used>yes|no)\s*\|"
)

FLAG = re.compile(r"--[a-z][a-z-]+")


def field_rows() -> list[tuple[str, str]]:
    """(field name, "yes" or "no") for every row of the skill's field table."""
    rows = []
    for line in WCL_API_SKILL.read_text(encoding="utf-8").splitlines():
        match = FIELD_ROW.match(line.strip())
        if match:
            rows.append((match.group("field"), match.group("used")))
    return rows


def test_the_field_table_is_not_empty() -> None:
    # Guards the parser itself: a table this test cannot read would make every
    # assertion below pass vacuously.
    assert len(field_rows()) >= 20


def test_every_field_the_table_says_we_query_is_in_the_queries() -> None:
    queries = QUERIES.read_text(encoding="utf-8")
    missing = [field for field, used in field_rows() if used == "yes" and field not in queries]
    assert missing == [], f"documented as queried but absent from queries.py: {missing}"


def test_every_field_the_table_says_we_do_not_query_is_absent() -> None:
    queries = QUERIES.read_text(encoding="utf-8")
    present = [field for field, used in field_rows() if used == "no" and field in queries]
    assert present == [], f"documented as unused but present in queries.py: {present}"


def test_every_flag_the_workflow_tells_you_to_type_exists() -> None:
    # Asserted against the command's own help rather than against cli.py's text:
    # typer infers `--player` and `--narrative` from their parameter names, so
    # neither string appears in the source at all.
    help_text = CliRunner().invoke(app, ["analyze", "--help"]).output
    flags = set(FLAG.findall(ANALYZING_SKILL.read_text(encoding="utf-8")))
    assert flags, "the workflow names no flags at all, so this test proves nothing"
    missing = sorted(flag for flag in flags if flag not in help_text)
    assert missing == [], f"named in the skill but absent from the command: {missing}"


def test_every_flag_the_command_offers_is_named_in_the_workflow() -> None:
    # The reverse of the test above. A flag the command has and the workflow never
    # mentions is a feature nobody following the workflow can reach.
    help_text = CliRunner().invoke(app, ["analyze", "--help"]).output
    offered = set(FLAG.findall(help_text)) - {"--help"}
    named = set(FLAG.findall(ANALYZING_SKILL.read_text(encoding="utf-8")))
    missing = sorted(offered - named)
    assert missing == [], f"offered by the command but never named in the skill: {missing}"
