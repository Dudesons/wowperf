# ABOUTME: The skills make mechanical claims about the code; these keep the two in step.
# ABOUTME: A reference that has quietly drifted from the code is worse than no reference.

import re
from pathlib import Path

from typer.testing import CliRunner

from tests.test_cli import plain
from wowperf.cli import app
from wowperf.domain.findings import Finding
from wowperf.domain.report.model import ReferenceRecord

REPO_ROOT = Path(__file__).resolve().parents[1]
WCL_API_SKILL = REPO_ROOT / ".claude" / "skills" / "wcl-api" / "SKILL.md"
QUERIES = REPO_ROOT / "src" / "wowperf" / "adapters" / "wcl" / "queries.py"
ANALYZING_SKILL = REPO_ROOT / ".claude" / "skills" / "analyzing-a-run" / "SKILL.md"
MPLUS_SKILL = REPO_ROOT / ".claude" / "skills" / "mplus-analysis" / "SKILL.md"

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
    help_text = plain(CliRunner().invoke(app, ["analyze", "--help"]).output)
    flags = set(FLAG.findall(ANALYZING_SKILL.read_text(encoding="utf-8")))
    assert flags, "the workflow names no flags at all, so this test proves nothing"
    missing = sorted(flag for flag in flags if flag not in help_text)
    assert missing == [], f"named in the skill but absent from the command: {missing}"


def test_every_flag_the_command_offers_is_named_in_the_workflow() -> None:
    # The reverse of the test above. A flag the command has and the workflow never
    # mentions is a feature nobody following the workflow can reach.
    help_text = plain(CliRunner().invoke(app, ["analyze", "--help"]).output)
    offered = set(FLAG.findall(help_text)) - {"--help"}
    assert offered, "the command's help names no flags at all, so this test proves nothing"
    named = set(FLAG.findall(ANALYZING_SKILL.read_text(encoding="utf-8")))
    missing = sorted(offered - named)
    assert missing == [], f"offered by the command but never named in the skill: {missing}"


def test_the_template_the_workflow_tells_you_to_copy_is_one_the_repository_ships() -> None:
    # The workflow opens by sending a reader to copy a template into place. A
    # rename that misses the skill sends them to a file that is not there, and
    # the failure surfaces as "no credentials" rather than as a missing file.
    workflow = ANALYZING_SKILL.read_text(encoding="utf-8")
    templates = set(re.findall(r"`([\w.-]+\.example)`", workflow))
    assert templates, "the workflow names no template to copy, so setup is undocumented"
    missing = sorted(name for name in templates if not (REPO_ROOT / name).is_file())
    assert missing == [], f"named in the workflow but not shipped: {missing}"


def paragraph_naming(marker: str) -> str:
    """The one paragraph of the interpretation skill that contains `marker`.

    Scoped to a paragraph rather than searched over the whole file: the skill
    names `player_slug` in two unrelated places, so "the string appears
    somewhere" would pass without either enumeration mentioning it.
    """
    blocks = [
        block for block in MPLUS_SKILL.read_text(encoding="utf-8").split("\n\n") if marker in block
    ]
    assert len(blocks) == 1, f"{marker!r} appears in {len(blocks)} paragraphs, not one"
    return blocks[0]


def test_every_field_a_finding_carries_is_enumerated_by_the_interpretation_skill() -> None:
    # "Reading the file" enumerates a finding's fields for a reader who will never
    # open the model. A field the findings JSON emits and that enumeration never
    # names is one the narrative writer cannot know is there to be read.
    enumeration = paragraph_naming("the findings themselves")
    missing = [name for name in Finding.model_fields if f"`{name}`" not in enumeration]
    assert missing == [], f"carried by every finding but never enumerated: {missing}"


def test_every_field_a_reference_carries_is_enumerated_by_the_interpretation_skill() -> None:
    # The same guard over `comparison.references`, whose emitted keys
    # `tests/test_cli.py` holds equal to `ReferenceRecord.model_fields`.
    enumeration = paragraph_naming("`comparison.references` lists")
    missing = [name for name in ReferenceRecord.model_fields if f"`{name}`" not in enumeration]
    assert missing == [], f"carried by every reference but never enumerated: {missing}"
