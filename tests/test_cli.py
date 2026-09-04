# ABOUTME: Dispatch tests for the wowperf CLI, driven through Typer's CliRunner.
# ABOUTME: Exercises argument parsing and command dispatch; makes no network call.

import pytest
from typer.testing import CliRunner

from wowperf.cli import app

runner = CliRunner()


def test_fetch_help_exits_cleanly() -> None:
    result = runner.invoke(app, ["fetch", "--help"])
    assert result.exit_code == 0
    assert "report" in result.output.lower()
    assert "--fight" in result.output
    assert "--cache-dir" in result.output


def test_top_level_help_lists_fetch_as_a_subcommand() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Commands" in result.output
    assert "fetch" in result.output


def test_fetch_rejects_a_value_that_is_not_a_report_url() -> None:
    result = runner.invoke(app, ["fetch", "https://example.com/nope"])
    assert result.exit_code != 0
    assert "unexpected extra argument" not in result.output.lower()


def test_fetch_without_credentials_names_the_missing_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WCL_CLIENT_ID", raising=False)
    monkeypatch.delenv("WCL_CLIENT_SECRET", raising=False)

    result = runner.invoke(app, ["fetch", "aBc123XyZ"])

    assert result.exit_code != 0
    assert "WCL_CLIENT_ID" in result.output
