# ABOUTME: The character command against the live API: one real character, every file it writes.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

"""Asserts shapes and invariants only, never a name: the character is a real person, named only
in the untracked `.env`."""

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wowperf.adapters.config.dotenv import apply_dotenv
from wowperf.cli import app
from wowperf.domain.character.patterns import DIRECTIONS_WITHHELD_ID

pytestmark = pytest.mark.e2e


def test_character_writes_a_page_whose_every_finding_is_badged(tmp_path: Path) -> None:
    apply_dotenv(Path.cwd() / ".env", os.environ)
    url = os.environ.get("WOWPERF_E2E_CHARACTER")
    if not url:
        pytest.fail(
            "Set WOWPERF_E2E_CHARACTER in .env to a character URL with ?zone=<id>; "
            "see .env.example."
        )

    result = CliRunner().invoke(app, ["character", url, "--out", str(tmp_path)])

    assert result.exit_code == 0, f"{result.stderr}\n{result.exception!r}"
    [directory] = [one for one in tmp_path.iterdir() if one.is_dir()]
    payload = json.loads((directory / "character.json").read_text(encoding="utf-8"))
    assert (directory / "character.html").is_file()
    # Not `not payload["failed"]`: one run may legitimately fail live. But when every chosen
    # run fails the command still exits 0, and the loop below would then check nothing.
    assert payload["runs"], "no run loaded, so the checks below assert nothing"
    for run in payload["runs"]:
        assert (directory / run["findings_file"]).is_file()
        assert (directory / run["report_file"]).is_file()
    ids = [finding["id"] for finding in payload["findings"]]
    assert len(ids) == len(set(ids))
    for finding in payload["findings"]:
        assert finding["confidence"] in {"measured", "derived", "inferred"}
        is_direction = (
            finding["id"].startswith("character.direction.")
            and finding["id"] != DIRECTIONS_WITHHELD_ID
        )
        if is_direction:
            assert finding["quantifier"] == "every"
