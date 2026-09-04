# ABOUTME: Dispatch tests for the wowperf CLI, driven through Typer's CliRunner.
# ABOUTME: Exercises argument parsing, error reporting and quota logging; makes no network call.

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from wowperf.cli import app

runner = CliRunner()

FIXTURE = Path(__file__).parent / "adapters" / "wcl" / "fixtures" / "report_fights.json"


def quota_response(spent: float) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": {
                "rateLimitData": {
                    "limitPerHour": 3600,
                    "pointsSpentThisHour": spent,
                    "pointsResetIn": 900,
                }
            }
        },
    )


def build_transport(quota: list[float]) -> httpx.MockTransport:
    """Answer the fights query from the fixture and report a rising point count."""
    fights = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        if "rateLimitData" in json.loads(request.content)["query"]:
            return quota_response(quota.pop(0))
        return httpx.Response(200, json={"data": fights})

    return httpx.MockTransport(handler)


@pytest.fixture
def wired_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the CLI at a mock transport, keeping the real wiring otherwise intact."""
    transport = build_transport([100.0, 112.5])
    real_client = httpx.Client

    def fake_client(*args: Any, **kwargs: Any) -> httpx.Client:
        return real_client(transport=transport)

    monkeypatch.setattr(httpx, "Client", fake_client)
    monkeypatch.setenv("WCL_CLIENT_ID", "id")
    monkeypatch.setenv("WCL_CLIENT_SECRET", "secret")


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

    assert result.exit_code == 1
    assert "is not a Warcraft Logs report code or URL" in result.stderr
    assert "Traceback" not in result.output
    assert not isinstance(result.exception, ValueError)
    assert "unexpected extra argument" not in result.output.lower()


def test_fetch_without_credentials_names_the_missing_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WCL_CLIENT_ID", raising=False)
    monkeypatch.delenv("WCL_CLIENT_SECRET", raising=False)

    result = runner.invoke(app, ["fetch", "aBc123XyZ"])

    assert result.exit_code != 0
    assert "WCL_CLIENT_ID" in result.output
    assert "Traceback" not in result.output


def test_an_unreadable_report_is_reported_as_a_message_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        if "rateLimitData" in json.loads(request.content)["query"]:
            return quota_response(100.0)
        return httpx.Response(200, json={"data": {"reportData": {"report": None}}})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def fake_client(*args: Any, **kwargs: Any) -> httpx.Client:
        return real_client(transport=transport)

    monkeypatch.setattr(httpx, "Client", fake_client)
    monkeypatch.setenv("WCL_CLIENT_ID", "id")
    monkeypatch.setenv("WCL_CLIENT_SECRET", "secret")

    result = runner.invoke(app, ["fetch", "aBc123XyZ", "--cache-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "Report aBc123XyZ was not found" in result.stderr
    assert "Traceback" not in result.output
    assert result.stdout == ""


def test_fetch_prints_the_run_on_stdout_and_the_quota_on_stderr(
    wired_cli: None, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["fetch", "abc123", "--cache-dir", str(tmp_path / "cache")])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["dungeon_name"] == "Murder Row"
    assert "12.50 points spent, including the cost of these two quota reads" in result.stderr
    assert "3487.50 of 3600 remain" in result.stderr


ANALYZE_FIGHTS_PAYLOAD: dict[str, Any] = {
    "reportData": {
        "report": {
            "code": "abc123",
            "title": "Keys",
            "startTime": 0,
            "endTime": 1920000,
            "fights": [
                {
                    "id": 36,
                    "name": "Den of Nalorakk",
                    "encounterID": 12660,
                    "startTime": 0,
                    "endTime": 1920000,
                    "kill": True,
                    "keystoneLevel": 16,
                    "keystoneAffixes": [9, 10, 147],
                    "keystoneTime": 1909000,
                    "keystoneBonus": 1,
                    "countReached": 744,
                    "countRequired": 729,
                    "npcCountMap": {"241874": 5},
                    "friendlyPlayers": [693],
                    "friendlySpecs": ["Arcane"],
                    "friendlyItemLevels": [318],
                    "dungeonPulls": [
                        {
                            "id": 1, "name": "Trash", "encounterID": 0,
                            "startTime": 1000, "endTime": 5000, "kill": True,
                            "x": 10, "y": 20,
                            "enemyNPCs": [{"id": 699, "gameID": 241874}],
                        },
                    ],
                }
            ],
            "masterData": {
                "actors": [
                    {"id": 693, "name": "Uglymage", "subType": "Mage", "server": "Hyjal"},
                ]
            },
        }
    }
}


def build_analyze_transport(player_name: str = "Uglymage") -> httpx.MockTransport:
    """Answer every query `WclRunRepository.load` issues for report abc123, fight 36.

    Extends the `fetch` tests' single-fixture transport with the operation names
    `load` also fetches: abilities, the actor lookup, and the six paginated
    event streams. Every stream answers with no rows, which is enough for
    `analyse` to run without raising (see `test_an_empty_run_analyses_without_raising`
    in `tests/domain/analysis/test_service.py`) while still exercising a real run.
    """
    fights_payload = json.loads(json.dumps(ANALYZE_FIGHTS_PAYLOAD))
    fights_payload["reportData"]["report"]["masterData"]["actors"][0]["name"] = player_name

    abilities_payload: dict[str, Any] = {
        "reportData": {"report": {"masterData": {"abilities": []}}}
    }
    actors_payload: dict[str, Any] = {
        "reportData": {"report": {"masterData": {"actors": [{"id": 699, "gameID": 241874}]}}}
    }
    empty_events: dict[str, Any] = {
        "reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        query = json.loads(request.content)["query"]
        name = query.split("query ")[1].split("(")[0].strip()
        if name == "Fights":
            return httpx.Response(200, json={"data": fights_payload})
        if name == "Abilities":
            return httpx.Response(200, json={"data": abilities_payload})
        if name == "Actors":
            return httpx.Response(200, json={"data": actors_payload})
        if name == "Talents":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "reportData": {"report": {"fights": [{"id": 36, "a693": "C4DAAAAA"}]}}
                    }
                },
            )
        return httpx.Response(200, json={"data": empty_events})

    return httpx.MockTransport(handler)


def invoke_analyze(tmp_path: Path, player_name: str = "Uglymage", *extra_args: str) -> Any:
    """Invoke `analyze abc123` against the mock transport, writing into tmp_path/out."""
    transport = build_analyze_transport(player_name)
    real_client = httpx.Client

    def fake_client(*args: Any, **kwargs: Any) -> httpx.Client:
        return real_client(transport=transport)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "Client", fake_client)
        mp.setenv("WCL_CLIENT_ID", "id")
        mp.setenv("WCL_CLIENT_SECRET", "secret")
        return runner.invoke(
            app,
            [
                "analyze", "abc123",
                "--cache-dir", str(tmp_path / "cache"),
                "--out", str(tmp_path / "out"),
                *extra_args,
            ],
        )


def test_analyze_writes_a_findings_file(tmp_path: Path) -> None:
    result = invoke_analyze(tmp_path)
    assert result.exit_code == 0, result.output
    written = tmp_path / "out" / "abc123-36.findings.json"
    assert written.is_file()
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["report_code"] == "abc123"
    assert payload["keystone_level"] == 16
    assert isinstance(payload["findings"], list)


def test_every_written_finding_carries_a_confidence(tmp_path: Path) -> None:
    invoke_analyze(tmp_path)
    payload = json.loads(
        (tmp_path / "out" / "abc123-36.findings.json").read_text(encoding="utf-8")
    )
    for finding in payload["findings"]:
        assert finding["confidence"] in {"measured", "derived", "inferred"}


def test_analyze_writes_the_full_findings_shape(tmp_path: Path) -> None:
    result = invoke_analyze(tmp_path)
    assert result.exit_code == 0, result.output
    payload = json.loads(
        (tmp_path / "out" / "abc123-36.findings.json").read_text(encoding="utf-8")
    )
    assert payload == {
        "report_code": "abc123",
        "fight_id": 36,
        "dungeon_name": "Den of Nalorakk",
        "keystone_level": 16,
        "keystone_time_seconds": 1909.0,
        "in_time": True,
        "findings_are_ranked_not_additive": payload["findings_are_ranked_not_additive"],
        "findings": payload["findings"],
    }
    assert "not additive" in payload["findings_are_ranked_not_additive"]
    assert "time.gap" in payload["findings_are_ranked_not_additive"]
    assert "deaths.total" in payload["findings_are_ranked_not_additive"]
    for finding in payload["findings"]:
        assert set(finding.keys()) == {
            "id", "title", "detail", "confidence", "seconds_lost", "evidence", "pull_index",
        }


def test_analyze_is_a_subcommand_of_its_own() -> None:
    result = CliRunner().invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--out" in result.output


def test_analyze_reports_a_bad_url_as_a_message_not_a_traceback() -> None:
    result = CliRunner().invoke(app, ["analyze", "https://example.com/nope"])
    assert result.exit_code != 0
    assert not isinstance(result.exception, ValueError)
    assert "is not a Warcraft Logs report code or URL" in result.stderr


def test_analyze_reports_a_missing_data_file_as_a_message_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A missing data/*.toml file raises FileNotFoundError, an OSError subclass.

    load_season_data runs after the report has already been fetched, so this is
    also a case where the user has already spent quota by the time it fails;
    it must still be reported as a message, not a traceback.
    """
    def raise_missing_file() -> None:
        raise FileNotFoundError("No data file at data/season.toml")

    monkeypatch.setattr("wowperf.cli.load_season_data", raise_missing_file)
    result = invoke_analyze(tmp_path)

    assert result.exit_code == 1
    assert "No data file at data/season.toml" in result.stderr
    assert "Traceback" not in result.output


def test_analyze_writes_non_ascii_player_names_intact(tmp_path: Path) -> None:
    """A real roster contains non-ASCII names; the write must not mangle them,
    the way `fetch` had to reconfigure stdout to survive a cp1252 console."""
    result = invoke_analyze(tmp_path, player_name="Бубатурбина")
    assert result.exit_code == 0, result.output
    written = tmp_path / "out" / "abc123-36.findings.json"
    raw = written.read_bytes()
    assert "Бубатурбина".encode() in raw


def test_fetch_prints_non_ascii_names_intact_on_a_non_utf8_console(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Real rosters carry non-ASCII names, and Windows gives the process a
    locale-dependent stdout encoding (commonly cp1252) that cannot hold them.
    A CliRunner with charset="cp1252" reproduces exactly that: without the
    stdout reconfigure, writing the JSON raises UnicodeEncodeError, the same
    crash seen against the real report, after the API quota was already spent.
    """
    fights = json.loads(FIXTURE.read_text(encoding="utf-8"))
    report = fights["reportData"]["report"]
    report["fights"][1]["name"] = "Подземелье"
    report["masterData"]["actors"][0]["name"] = "Бубатурбина"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        if "rateLimitData" in json.loads(request.content)["query"]:
            return quota_response(100.0)
        return httpx.Response(200, json={"data": fights})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def fake_client(*args: Any, **kwargs: Any) -> httpx.Client:
        return real_client(transport=transport)

    monkeypatch.setattr(httpx, "Client", fake_client)
    monkeypatch.setenv("WCL_CLIENT_ID", "id")
    monkeypatch.setenv("WCL_CLIENT_SECRET", "secret")

    cp1252_runner = CliRunner(charset="cp1252")
    result = cp1252_runner.invoke(
        app, ["fetch", "abc123", "--cache-dir", str(tmp_path / "cache")]
    )

    assert result.exit_code == 0, result.output
    assert result.exception is None
    # result.stdout would mis-decode: the runner's own charset is cp1252, but the
    # bytes it captured are UTF-8 once the command reconfigures stdout. Decode the
    # raw bytes as UTF-8 to check what actually reached the stream.
    payload = json.loads(result.stdout_bytes.decode("utf-8"))
    assert payload["dungeon_name"] == "Подземелье"
    assert payload["players"][0]["name"] == "Бубатурбина"
