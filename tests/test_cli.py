# ABOUTME: Dispatch tests for the wowperf CLI, driven through Typer's CliRunner.
# ABOUTME: Exercises argument parsing, error reporting and quota logging; makes no network call.

import json
from pathlib import Path
from typing import Any, cast

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


SPEED_REFERENCE_CODE = "71cv4MRdNCp8ZFjG"
SPEED_REFERENCE_FIGHT = 28
PARSE_REFERENCE_CODE = "37FzMg9pVPH6fnJT"
PARSE_REFERENCE_FIGHT = 16
# The character name the default `_parse_row()` puts on the top-parse leaderboard row.
# The parse reference's own roster fixture must carry an actor under this same name —
# see `build_analyze_transport`'s `fights_by_code` — or `find_player` can never resolve
# the counterpart and the counterpart's aura fetch silently never fires.
PARSE_REFERENCE_CHARACTER_NAME = "Críms"


def _fights_payload_for(code: str, fight_id: int, player_name: str) -> dict[str, Any]:
    """A copy of the shared fixture, addressed at one report code and fight id.

    The rankings tests need `WclRunRepository.load` to succeed for the two
    reference report codes as well as the main one, and the Fights query only
    carries `code` — `select_keystone_fight` picks the fight id afterwards, in
    Python — so the fixture returned for a code must already carry the fight id
    that code's caller is going to ask for.
    """
    payload: dict[str, Any] = json.loads(json.dumps(ANALYZE_FIGHTS_PAYLOAD))
    report = payload["reportData"]["report"]
    report["code"] = code
    # The API lowercases the report owner's name; the roster keeps the
    # character's own capitalisation, which is what the default-player test
    # relies on `find_player`'s case-folding to bridge.
    report["owner"] = {"name": player_name.lower()}
    report["fights"][0]["id"] = fight_id
    report["masterData"]["actors"][0]["name"] = player_name
    return payload


def _speed_row(bracket_data: int) -> dict[str, Any]:
    return {
        "duration": 1379452,
        "report": {"code": SPEED_REFERENCE_CODE, "fightID": SPEED_REFERENCE_FIGHT, "startTime": 1},
        "deaths": 0,
        "bracketData": bracket_data,
        "affixes": [9, 10, 147],
        "team": [{"class": "Warrior", "spec": "Protection"}],
        "medal": "silver",
        "score": 435.5,
    }


def _parse_row(bracket_data: int) -> dict[str, Any]:
    return {
        "name": PARSE_REFERENCE_CHARACTER_NAME,
        "class": "Mage",
        "spec": "Arcane",
        "duration": 1399143,
        "report": {"code": PARSE_REFERENCE_CODE, "fightID": PARSE_REFERENCE_FIGHT, "startTime": 1},
        "bracketData": bracket_data,
        "affixes": [9, 10, 147],
        "medal": "silver",
        "score": 435.1,
    }


def _broken_speed_row(code: str, fight_id: int) -> dict[str, Any]:
    """A speed-leaderboard row pointing at a report code the Fights handler does
    not recognise, so `WclRunRepository.load` raises `IngestError` for it."""
    return {
        "duration": 999999,
        "report": {"code": code, "fightID": fight_id, "startTime": 1},
        "deaths": 0,
        "bracketData": 16,
        "affixes": [9, 10, 147],
        "team": [{"class": "Warrior", "spec": "Protection"}],
        "medal": "silver",
        "score": 100.0,
    }


def _broken_parse_row(code: str, fight_id: int) -> dict[str, Any]:
    """A parse-leaderboard row pointing at a report code the Fights handler does
    not recognise, so `WclRunRepository.load` raises `IngestError` for it."""
    return {
        "name": "Nobody",
        "class": "Mage",
        "spec": "Arcane",
        "duration": 999999,
        "report": {"code": code, "fightID": fight_id, "startTime": 1},
        "bracketData": 16,
        "affixes": [9, 10, 147],
        "medal": "silver",
        "score": 100.0,
    }


def build_analyze_transport(
    player_name: str = "Uglymage",
    *,
    bracket_data: int = 16,
    rankings: list[dict[str, Any]] | None = None,
    speed_rows: list[dict[str, Any]] | None = None,
    parse_rows: list[dict[str, Any]] | None = None,
    calls: list[str] | None = None,
    aura_response: httpx.Response | None = None,
    boss_pull_reports: tuple[str, ...] = (),
    aura_rows_by_code: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
) -> httpx.MockTransport:
    """Answer every query `WclRunRepository.load` issues for report abc123, fight 36.

    Extends the `fetch` tests' single-fixture transport with the operation names
    `load` also fetches: abilities, the actor lookup, and the six paginated
    event streams. Every stream answers with no rows, which is enough for
    `analyse` to run without raising (see `test_an_empty_run_analyses_without_raising`
    in `tests/domain/analysis/test_service.py`) while still exercising a real run.

    Also answers `FightRankings` and `CharacterRankings`, so `analyze` can run its
    comparison unless `--no-compare` is passed. `rankings=None` answers with one
    row on each leaderboard (a working comparison by default); `rankings=[]`
    answers with no rows at all (an unavailable comparison, at every bracket the
    repository falls back through). `bracket_data` is the `bracketData` the rows
    claim, so a value other than the run's own keystone level exercises the
    bracket assertion. `speed_rows`/`parse_rows` override `rankings` for one
    leaderboard only — a caller wanting the two leaderboards to answer
    differently (e.g. a broken row ahead of a working one) passes those instead.
    A Fights query for a report code this transport does not recognise answers
    "report not found", so a reference row can point at a code that will fail
    to load without any extra wiring.

    Also answers `AuraTable` with an empty-but-valid pair of aura tables, so a
    comparison against a parse reference has real (if empty) aura data on both
    sides. `aura_response` overrides that answer for every `AuraTable` request,
    letting a caller simulate a fetch that fails. `calls` records every
    operation name this transport answers, in order, so a caller can prove a
    query was (or was not) issued rather than only checking the exit code.

    The parse reference's roster carries its own actor under
    `PARSE_REFERENCE_CHARACTER_NAME` rather than under `player_name`: the
    top-parse leaderboard row names that player as the one to compare against,
    and `find_player` must be able to find them on that report for the
    counterpart's aura fetch to fire at all.

    `boss_pull_reports` turns a named report's only dungeon pull from trash
    (encounter id 0) into a boss pull. `compare_uptime` measures only boss-pull
    time, so with the fixture's default all-trash pull every run reports zero
    boss seconds and any uptime comparison degrades to
    `compare.uptime.unavailable` regardless of aura content — this is what a
    caller needs to get a genuine, populated uptime finding instead.
    `aura_rows_by_code` answers `AuraTable` with real aura rows for the report
    codes named (`{"onSelf": [...], "onTargets": [...]}`, each a list of
    `{"guid", "name", "totalUptime", "totalUses", "bands"}` rows, the shape
    `build_player_auras` reads), in place of the default empty-but-valid tables
    — letting a caller give the two players aura data that actually differs.
    """
    fights_by_code = {
        code: _fights_payload_for(
            code,
            fight_id,
            PARSE_REFERENCE_CHARACTER_NAME if code == PARSE_REFERENCE_CODE else player_name,
        )
        for code, fight_id in (
            ("abc123", 36),
            (SPEED_REFERENCE_CODE, SPEED_REFERENCE_FIGHT),
            (PARSE_REFERENCE_CODE, PARSE_REFERENCE_FIGHT),
        )
    }
    for code in boss_pull_reports:
        fight = fights_by_code[code]["reportData"]["report"]["fights"][0]
        fight["dungeonPulls"] = [
            {**pull, "encounterID": fight["encounterID"]} for pull in fight["dungeonPulls"]
        ]

    abilities_payload: dict[str, Any] = {
        "reportData": {"report": {"masterData": {"abilities": []}}}
    }
    actors_payload: dict[str, Any] = {
        "reportData": {"report": {"masterData": {"actors": [{"id": 699, "gameID": 241874}]}}}
    }
    empty_events: dict[str, Any] = {
        "reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}
    }
    empty_auras: dict[str, Any] = {
        "reportData": {
            "report": {
                "onSelf": {"data": {"auras": [], "totalTime": 0}},
                "onTargets": {"data": {"auras": [], "totalTime": 0}},
            }
        }
    }
    if speed_rows is None:
        speed_rows = [_speed_row(bracket_data)] if rankings is None else rankings
    if parse_rows is None:
        parse_rows = [_parse_row(bracket_data)] if rankings is None else rankings

    def rankings_response(field: str, rows: list[dict[str, Any]]) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "worldData": {
                        "encounter": {
                            "id": 12660,
                            "name": "Den of Nalorakk",
                            field: {"page": 1, "hasMorePages": False, "rankings": rows},
                        }
                    }
                }
            },
        )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        body = json.loads(request.content)
        query = body["query"]
        name = query.split("query ")[1].split("(")[0].strip()
        if calls is not None:
            calls.append(name)
        if name == "Fights":
            code = body["variables"]["code"]
            payload = fights_by_code.get(code, {"reportData": {"report": None}})
            return httpx.Response(200, json={"data": payload})
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
        if name == "FightRankings":
            return rankings_response("fightRankings", speed_rows)
        if name == "CharacterRankings":
            return rankings_response("characterRankings", parse_rows)
        if name == "AuraTable":
            code = body["variables"]["code"]
            if aura_rows_by_code is not None and code in aura_rows_by_code:
                rows = aura_rows_by_code[code]
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "reportData": {
                                "report": {
                                    "onSelf": {
                                        "data": {
                                            "auras": rows.get("onSelf", []),
                                            "totalTime": 0,
                                        }
                                    },
                                    "onTargets": {
                                        "data": {
                                            "auras": rows.get("onTargets", []),
                                            "totalTime": 0,
                                        }
                                    },
                                }
                            }
                        }
                    },
                )
            return aura_response if aura_response is not None else httpx.Response(
                200, json={"data": empty_auras}
            )
        return httpx.Response(200, json={"data": empty_events})

    return httpx.MockTransport(handler)


def _invoke(tmp_path: Path, extra_args: list[str], transport: httpx.MockTransport) -> Any:
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


def invoke_analyze(tmp_path: Path, player_name: str = "Uglymage", *extra_args: str) -> Any:
    """Invoke `analyze abc123` against the mock transport, writing into tmp_path/out."""
    return _invoke(tmp_path, list(extra_args), build_analyze_transport(player_name))


def run_analyze(
    tmp_path: Path,
    *extra_args: str,
    bracket_data: int = 16,
    rankings: list[dict[str, Any]] | None = None,
    calls: list[str] | None = None,
    aura_response: httpx.Response | None = None,
    boss_pull_reports: tuple[str, ...] = (),
    aura_rows_by_code: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
) -> Any:
    """Invoke `analyze abc123`, mocking the report queries and both leaderboards."""
    transport = build_analyze_transport(
        bracket_data=bracket_data,
        rankings=rankings,
        calls=calls,
        aura_response=aura_response,
        boss_pull_reports=boss_pull_reports,
        aura_rows_by_code=aura_rows_by_code,
    )
    return _invoke(tmp_path, list(extra_args), transport)


def written_findings(tmp_path: Path) -> dict[str, Any]:
    """Read back the single findings file `analyze` wrote under `tmp_path/out`."""
    [written] = (tmp_path / "out").glob("*.findings.json")
    return cast(dict[str, Any], json.loads(written.read_text(encoding="utf-8")))


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
        "player": "Uglymage",
        "comparison": payload["comparison"],
        "findings_are_ranked_not_additive": payload["findings_are_ranked_not_additive"],
        "findings": payload["findings"],
    }
    sentence = payload["findings_are_ranked_not_additive"]
    assert "not additive" in sentence
    assert "compare.duration" in sentence
    assert "time.gap" in sentence
    assert "compare.downtime" in sentence
    assert "time.residual" in sentence
    assert "deaths.total" in sentence
    assert "compare.route.skipped" in sentence
    assert "trash.overage" in sentence
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


def test_analyze_writes_a_comparison_block(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, "--player", "Uglymage")

    assert result.exit_code == 0
    payload = written_findings(tmp_path)
    assert payload["player"] == "Uglymage"
    assert payload["comparison"]["compared"] is True
    assert payload["comparison"]["speed_reference"]["report_code"]
    assert any(f["id"].startswith("compare.") for f in payload["findings"])


def test_no_compare_skips_both_references(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, "--no-compare")

    assert result.exit_code == 0
    payload = written_findings(tmp_path)
    assert payload["comparison"]["compared"] is False
    assert payload["comparison"]["speed_reference"] is None
    assert not any(f["id"].startswith("compare.") for f in payload["findings"])


def test_an_unknown_player_exits_and_lists_the_roster(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, "--player", "Nobody")

    assert result.exit_code == 1
    assert "Uglymage" in result.output


def test_the_player_defaults_to_the_report_owner(tmp_path: Path) -> None:
    # The API lowercases the owner's name; the roster does not.
    result = run_analyze(tmp_path)

    assert result.exit_code == 0
    assert written_findings(tmp_path)["player"] == "Uglymage"


def test_a_bracket_that_lies_stops_the_command(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, bracket_data=11)

    assert result.exit_code == 1
    assert "bracket" in result.output.lower()


def test_a_reference_that_fails_to_load_falls_through_to_the_next_row(tmp_path: Path) -> None:
    """Reproduces a reference fight whose report cannot be loaded (deleted, private,
    an unfinished fight, or a roster gap): the first leaderboard row is unusable, so
    `analyze` must fall through to the next row rather than aborting the command."""
    transport = build_analyze_transport(
        speed_rows=[_broken_speed_row("brokenspeed1", 901), _speed_row(16)],
        parse_rows=[_broken_parse_row("brokenparse1", 902), _parse_row(16)],
    )
    result = _invoke(tmp_path, ["--player", "Uglymage"], transport)

    assert result.exit_code == 0, result.output
    payload = written_findings(tmp_path)
    assert payload["comparison"]["compared"] is True
    assert payload["comparison"]["speed_reference"]["report_code"] == SPEED_REFERENCE_CODE
    assert payload["comparison"]["parse_reference"]["report_code"] == PARSE_REFERENCE_CODE


def test_every_candidate_failing_to_load_yields_compared_false(tmp_path: Path) -> None:
    """Every row on both leaderboards fails to load: the command must still write
    the findings already computed for the run under analysis, with no reference."""
    transport = build_analyze_transport(
        speed_rows=[
            _broken_speed_row("brokenspeed1", 901),
            _broken_speed_row("brokenspeed2", 902),
        ],
        parse_rows=[
            _broken_parse_row("brokenparse1", 903),
            _broken_parse_row("brokenparse2", 904),
        ],
    )
    result = _invoke(tmp_path, [], transport)

    assert result.exit_code == 0, result.output
    payload = written_findings(tmp_path)
    assert payload["comparison"]["compared"] is False
    assert payload["comparison"]["speed_reference"] is None
    assert payload["comparison"]["parse_reference"] is None
    assert any(f["id"] == "compare.speed.unavailable" for f in payload["findings"])


def test_an_empty_leaderboard_degrades_to_no_comparison(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, rankings=[])

    assert result.exit_code == 0
    payload = written_findings(tmp_path)
    assert payload["comparison"]["compared"] is False
    assert any(f["id"] == "compare.speed.unavailable" for f in payload["findings"])


def test_comparison_fields_hold_correct_values(tmp_path: Path) -> None:
    """Asserts the values in speed_reference and parse_reference, not just their keys.

    The fixture's mock data is chosen to match the task brief's specimen values.
    This test pins the contract to fixed literals so a future swap (e.g. class_name
    and spec) would fail, not silently produce wrong output on screen.
    """
    result = run_analyze(tmp_path, "--player", "Uglymage")

    assert result.exit_code == 0
    payload = written_findings(tmp_path)

    # speed_reference fields
    assert payload["comparison"]["speed_reference"]["report_code"] == "71cv4MRdNCp8ZFjG"
    assert payload["comparison"]["speed_reference"]["fight_id"] == 28
    assert payload["comparison"]["speed_reference"]["keystone_level"] == 16
    assert payload["comparison"]["speed_reference"]["duration_seconds"] == 1379.452
    assert payload["comparison"]["speed_reference"]["medal"] == "silver"

    # parse_reference fields
    assert payload["comparison"]["parse_reference"]["report_code"] == "37FzMg9pVPH6fnJT"
    assert payload["comparison"]["parse_reference"]["fight_id"] == 16
    assert payload["comparison"]["parse_reference"]["keystone_level"] == 16
    assert payload["comparison"]["parse_reference"]["character_name"] == "Críms"
    assert payload["comparison"]["parse_reference"]["class_name"] == "Mage"
    assert payload["comparison"]["parse_reference"]["spec"] == "Arcane"
    assert payload["comparison"]["parse_reference"]["medal"] == "silver"


def test_a_compared_run_fetches_both_players_auras_and_reports_uptime(tmp_path: Path) -> None:
    """The defining feature of this task: two `AuraTable` queries, one per player,
    feeding a real, populated uptime finding — not the `unavailable` fallback a
    missing counterpart (or a fixture with no boss-pull time at all) would
    silently produce instead, satisfying `any(id.startswith("compare.uptime."))`
    either way and hiding the bug.

    The shared fixture's only pull is trash, so both runs need a boss pull
    (`boss_pull_reports`) before `compare_uptime` measures any boss-pull time at
    all; `aura_rows_by_code` then gives the reference a buff kept up for the
    whole pull that our side never had, so the gap actually clears the
    reporting thresholds in `wowperf.domain.comparison.uptime`.
    """
    calls: list[str] = []
    result = run_analyze(
        tmp_path,
        calls=calls,
        boss_pull_reports=("abc123", PARSE_REFERENCE_CODE),
        aura_rows_by_code={
            PARSE_REFERENCE_CODE: {
                "onSelf": [
                    {
                        "guid": 999,
                        "name": "Power Infusion",
                        "totalUptime": 4000,
                        "totalUses": 1,
                        "bands": [{"startTime": 1000, "endTime": 5000}],
                    }
                ],
            },
        },
    )

    payload = written_findings(tmp_path)
    ids = [f["id"] for f in payload["findings"]]

    assert result.exit_code == 0, result.output
    assert calls.count("AuraTable") == 2
    assert "compare.uptime.self.0" in ids


def test_no_compare_issues_no_aura_queries(tmp_path: Path) -> None:
    calls: list[str] = []
    result = run_analyze(tmp_path, "--no-compare", calls=calls)

    assert result.exit_code == 0
    assert "AuraTable" not in calls


def test_an_aura_fetch_that_fails_still_writes_the_report(tmp_path: Path) -> None:
    """Drives the `IngestError` branch of `cli._auras`: a null `data` block reaches
    `WclRunRepository._require_report`, which raises `IngestError`."""
    result = run_analyze(tmp_path, aura_response=httpx.Response(200, json={"data": None}))

    payload = written_findings(tmp_path)
    ids = [f["id"] for f in payload["findings"]]

    assert result.exit_code == 0, result.output
    assert "compare.uptime.unavailable" in ids


def test_a_graphql_error_on_the_aura_query_still_writes_the_report(tmp_path: Path) -> None:
    """Drives the `WclError` branch of `cli._auras`: a GraphQL `errors` array makes
    `WclClient.execute` raise `WclError`, the same shape `test_client.py` uses."""
    result = run_analyze(
        tmp_path,
        aura_response=httpx.Response(
            200, json={"errors": [{"message": "aura table is temporarily unavailable"}]}
        ),
    )

    payload = written_findings(tmp_path)
    ids = [f["id"] for f in payload["findings"]]

    assert result.exit_code == 0, result.output
    assert "compare.uptime.unavailable" in ids


def test_a_non_429_http_failure_on_the_aura_query_still_writes_the_report(tmp_path: Path) -> None:
    """A 500 on the aura query raises `httpx.HTTPStatusError` from
    `WclClient.execute`'s `response.raise_for_status()` — neither `IngestError` nor
    `WclError`, so `_auras` must catch `httpx.HTTPError` too or this kills the whole
    command and discards findings the user already paid quota for."""
    result = run_analyze(tmp_path, aura_response=httpx.Response(500, text="internal error"))

    payload = written_findings(tmp_path)
    ids = [f["id"] for f in payload["findings"]]

    assert result.exit_code == 0, result.output
    assert "compare.uptime.unavailable" in ids
