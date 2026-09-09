# ABOUTME: Dispatch tests for the wowperf CLI, driven through Typer's CliRunner.
# ABOUTME: Exercises argument parsing, error reporting and quota logging; makes no network call.

import json
import re
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from markupsafe import escape
from typer.testing import CliRunner

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import RateLimit, WclClient
from wowperf.adapters.wcl.cost import CostLedger
from wowperf.adapters.wcl.ranking_repository import WclRankingRepository
from wowperf.adapters.wcl.rankings import bracket_for
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.cli import (
    FINDINGS_ARE_RANKED_NOT_ADDITIVE,
    _cost_breakdown,
    _fetch_parse_auras,
    _quota_sentence,
    _samples,
    app,
)
from wowperf.domain.comparison.alignment import Alignment
from wowperf.domain.comparison.reference import ParseRow
from wowperf.domain.comparison.sample import SAMPLE_SIZE, ParseMember, ParseSample
from wowperf.domain.model import Player, Run
from wowperf.domain.report.ledger import DECOMPOSITION_IDS, NESTS_INSIDE

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


def operation_name(query: str) -> str:
    """The GraphQL operation name.

    Every query also selects `rateLimitData`, so only the name distinguishes
    a quota read from a real query that happens to carry its own reading. An
    operation takes variables or it does not, so the name ends at whichever of
    `(` or `{` follows it.
    """
    return query.split("query ")[1].split("(")[0].split("{")[0].strip()


def build_transport(quota: list[float], step: float = 1.0) -> httpx.MockTransport:
    """Answer the fights query from the fixture and report a rising point count.

    Every response carries a quota block, as the live API's do when each query
    selects one: the explicit reads report `quota` in order, and each real query
    reports a counter climbing from the first of them by `step`.
    """
    running = quota[0] if quota else 0.0

    def carrying_quota(payload: dict[str, Any]) -> httpx.Response:
        nonlocal running
        running += step
        return httpx.Response(
            200,
            json={
                "data": {
                    **payload,
                    "rateLimitData": {
                        "limitPerHour": 3600,
                        "pointsSpentThisHour": running,
                        "pointsResetIn": 900,
                    },
                }
            },
        )

    fights = json.loads(FIXTURE.read_text(encoding="utf-8"))
    affixes: dict[str, Any] = {
        "gameData": {
            "affixes": [{"id": 9, "name": "Tyrannical"}, {"id": 10, "name": "Fortified"}]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        name = operation_name(json.loads(request.content)["query"])
        if name == "RateLimit":
            return quota_response(quota.pop(0))
        return carrying_quota(affixes if name == "Affixes" else fights)

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
        if operation_name(json.loads(request.content)["query"]) == "RateLimit":
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
    assert "12.50 points spent, the opening quota read included" in result.stderr
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
                    {"id": 693, "name": "Emberkin", "subType": "Mage", "server": "Hyjal"},
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
PARSE_REFERENCE_CHARACTER_NAME = "Bríala"
# The speed reference's own roster fixture carries an actor under this name rather
# than under the analysed player's own name: `_samples` now excludes a candidate
# whose roster holds one of our own characters, and the speed reference must
# survive that check in every test that does not deliberately exercise it.
SPEED_REFERENCE_CHARACTER_NAME = "Speedrunner"


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
    player_name: str = "Emberkin",
    *,
    bracket_data: int = 16,
    rankings: list[dict[str, Any]] | None = None,
    speed_rows: list[dict[str, Any]] | None = None,
    parse_rows: list[dict[str, Any]] | None = None,
    calls: list[str] | None = None,
    aura_response: httpx.Response | None = None,
    boss_pull_reports: tuple[str, ...] = (),
    aura_rows_by_code: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
    abilities: list[dict[str, Any]] | None = None,
    death_events: list[dict[str, Any]] | None = None,
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

    `abilities` answers `Abilities` with the rows given (each a `gameID`,
    `name` and `icon`) in place of the default empty dictionary, and
    `death_events` answers `Deaths` with the raw events given in place of the
    default empty stream — together letting a caller put a real death, with a
    real killing blow, on the report a death card is built from.

    Every answer, `RateLimit` included, carries a quota block off one rising
    counter. Two counters would let the closing read fall below the reading before
    it, which the ledger would take for an hour rollover — silently dropping the
    last query and putting the printed table out of step with the spent sentence.
    """
    reference_roster_name = {
        SPEED_REFERENCE_CODE: SPEED_REFERENCE_CHARACTER_NAME,
        PARSE_REFERENCE_CODE: PARSE_REFERENCE_CHARACTER_NAME,
    }
    fights_by_code = {
        code: _fights_payload_for(
            code, fight_id, reference_roster_name.get(code, player_name)
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
        "reportData": {"report": {"masterData": {"abilities": abilities or []}}}
    }
    actors_payload: dict[str, Any] = {
        "reportData": {"report": {"masterData": {"actors": [{"id": 699, "gameID": 241874}]}}}
    }
    affixes_payload: dict[str, Any] = {
        "gameData": {
            "affixes": [
                {"id": 9, "name": "Tyrannical"},
                {"id": 10, "name": "Fortified"},
                {"id": 147, "name": "Xal'atath's Guile"},
            ]
        }
    }
    empty_events: dict[str, Any] = {
        "reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}
    }
    deaths_payload: dict[str, Any] = {
        "reportData": {
            "report": {"events": {"data": death_events or [], "nextPageTimestamp": None}}
        }
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

    def rankings_response(
        field: str, rows: list[dict[str, Any]], requested_bracket: int
    ) -> httpx.Response:
        # The run under analysis is always a +16, so its own bracket is the only
        # one these rows belong to; every other bracket `_samples`' widening now
        # tries (to fill the sample past what one bracket offers) must answer
        # empty, or a fixture built for a single row would fail the live
        # bracket-convention assertion the moment it widened past that row.
        matching = rows if requested_bracket == bracket_for(16) else []
        return httpx.Response(
            200,
            json={
                "data": {
                    "worldData": {
                        "encounter": {
                            "id": 12660,
                            "name": "Den of Nalorakk",
                            field: {"page": 1, "hasMorePages": False, "rankings": matching},
                        }
                    }
                }
            },
        )

    running = 100.0

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        body = json.loads(request.content)
        name = operation_name(body["query"])
        if calls is not None:
            calls.append(name)
        if name == "RateLimit":
            # The block the wrapper adds below is the whole answer.
            return httpx.Response(200, json={"data": {}})
        if name == "Fights":
            code = body["variables"]["code"]
            payload = fights_by_code.get(code, {"reportData": {"report": None}})
            return httpx.Response(200, json={"data": payload})
        if name == "Abilities":
            return httpx.Response(200, json={"data": abilities_payload})
        if name == "Deaths":
            return httpx.Response(200, json={"data": deaths_payload})
        if name == "Actors":
            return httpx.Response(200, json={"data": actors_payload})
        if name == "Affixes":
            return httpx.Response(200, json={"data": affixes_payload})
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
            return rankings_response("fightRankings", speed_rows, body["variables"]["bracket"])
        if name == "CharacterRankings":
            return rankings_response(
                "characterRankings", parse_rows, body["variables"]["bracket"]
            )
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

    def handler(request: httpx.Request) -> httpx.Response:
        """Every answer leaves carrying a quota block, as the live API's do."""
        nonlocal running
        response = answer(request)
        if response.status_code != httpx.codes.OK:
            # A fixture standing in for a 500 carries no JSON to add a block to,
            # and the real API sends no reading with a failure either.
            return response

        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, dict) or "rateLimitData" in data:
            return response

        running += 1.0
        data["rateLimitData"] = {
            "limitPerHour": 3600,
            "pointsSpentThisHour": running,
            "pointsResetIn": 900,
        }
        return httpx.Response(response.status_code, json=payload)

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


def invoke_analyze(tmp_path: Path, player_name: str = "Emberkin", *extra_args: str) -> Any:
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
    abilities: list[dict[str, Any]] | None = None,
    death_events: list[dict[str, Any]] | None = None,
) -> Any:
    """Invoke `analyze abc123`, mocking the report queries and both leaderboards."""
    transport = build_analyze_transport(
        bracket_data=bracket_data,
        rankings=rankings,
        calls=calls,
        aura_response=aura_response,
        boss_pull_reports=boss_pull_reports,
        abilities=abilities,
        death_events=death_events,
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


def test_analyze_prints_the_points_it_spent_on_stderr(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, "--no-compare")
    assert result.exit_code == 0, result.output
    assert "points spent, the opening quota read included and the closing one" in result.stderr
    assert "of 3600 remain this hour" in result.stderr


def test_analyze_prints_which_operations_the_points_went_on(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, "--no-compare")
    assert result.exit_code == 0, result.output

    normalised = " ".join(result.stderr.split())
    assert "Where they went:" in normalised
    assert "Fights" in normalised and "points" in normalised
    assert "ran last, so one of its calls is unpriced" in normalised


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
        "player": "Emberkin",
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
            "ability_id", "ability_name", "quantifier",
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
    result = invoke_analyze(tmp_path, player_name="Кириллица")
    assert result.exit_code == 0, result.output
    written = tmp_path / "out" / "abc123-36.findings.json"
    raw = written.read_bytes()
    assert "Кириллица".encode() in raw


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
    report["masterData"]["actors"][0]["name"] = "Кириллица"
    affixes: dict[str, Any] = {
        "gameData": {
            "affixes": [{"id": 9, "name": "Tyrannical"}, {"id": 10, "name": "Fortified"}]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        name = operation_name(json.loads(request.content)["query"])
        if name == "RateLimit":
            return quota_response(100.0)
        if name == "Affixes":
            return httpx.Response(200, json={"data": affixes})
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
    assert payload["players"][0]["name"] == "Кириллица"


def test_analyze_writes_a_comparison_block(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, "--player", "Emberkin")

    assert result.exit_code == 0
    payload = written_findings(tmp_path)
    assert payload["player"] == "Emberkin"
    assert payload["comparison"]["compared"] is True
    assert payload["comparison"]["sample_size"] == {"speed": 1, "parse": 1}
    assert any(reference["report_code"] for reference in payload["comparison"]["references"])
    assert any(f["id"].startswith("compare.") for f in payload["findings"])


def test_the_findings_json_names_no_reference_character(tmp_path: Path) -> None:
    """The comparison block carries a link, never who ran the reference: the
    findings file is kept forever, and a table of other players' names is
    exactly the corpus the reference cache exists to avoid accumulating.

    Scoped to the comparison block rather than the whole file: the below-floor
    spells fallback (see `compare_spells_sample`'s docstring) is a documented,
    unrelated exception that still names one reference player in its own
    finding, kept deliberately because there it is one pairwise comparison,
    not a population claim drawn from the sample.

    Dumped with `ensure_ascii=False`: the default `ensure_ascii=True` would
    escape "Bríala" to `\\u00ed` and let the name's presence pass unnoticed.
    """
    result = run_analyze(tmp_path, "--player", "Emberkin")

    assert result.exit_code == 0
    payload = written_findings(tmp_path)
    dumped = json.dumps(payload["comparison"], ensure_ascii=False)
    assert PARSE_REFERENCE_CHARACTER_NAME not in dumped
    assert SPEED_REFERENCE_CHARACTER_NAME not in dumped


def test_every_reference_in_the_json_carries_a_url_and_no_duration(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, "--player", "Emberkin")

    assert result.exit_code == 0
    payload = written_findings(tmp_path)
    references = payload["comparison"]["references"]
    assert references, "the fixture must produce at least one reference to make this a real test"
    for reference in references:
        assert reference["url"].startswith("https://www.warcraftlogs.com/reports/")
        assert "duration_seconds" not in reference
        assert "character_name" not in reference
        assert "medal" not in reference


def test_a_reference_does_not_pay_for_the_streams_no_comparison_reads(tmp_path: Path) -> None:
    """Our own run loads every stream. A reference loads only the five that are read.

    Counted at the boundary rather than in the repository, because the saving is
    only real if the command actually asks for references the trimmed way.
    """
    calls: list[str] = []

    result = run_analyze(tmp_path, "--player", "Emberkin", calls=calls)

    assert result.exit_code == 0, result.output
    # More than one Casts proves references were loaded at all, so the counts
    # of one below are a trimmed reference and not an absent one.
    assert calls.count("Casts") > 1
    assert calls.count("DamageTaken") == 1
    assert calls.count("EnemyDeaths") == 1
    assert calls.count("Resurrects") == 1
    assert calls.count("Actors") == 1


def test_no_compare_skips_both_references(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, "--no-compare")

    assert result.exit_code == 0
    payload = written_findings(tmp_path)
    assert payload["comparison"]["compared"] is False
    assert payload["comparison"]["sample_size"] == {"speed": 0, "parse": 0}
    assert payload["comparison"]["references"] == []
    assert not any(f["id"].startswith("compare.") for f in payload["findings"])


def test_reference_responses_are_cached_apart_from_the_runs_own(tmp_path: Path) -> None:
    result = invoke_analyze(tmp_path)
    assert result.exit_code == 0, result.output
    own = [p.read_text(encoding="utf-8") for p in (tmp_path / "cache").glob("*.json")]
    references = [
        p.read_text(encoding="utf-8")
        for p in (tmp_path / "cache" / "references").glob("*.json")
    ]
    assert own and references
    # The leaderboard rows and the reference report's own responses name its code;
    # nothing fetched for our own run does. (The affix table, argument-free, may
    # legitimately be cached in both tiers.)
    assert not any(SPEED_REFERENCE_CODE in text for text in own)
    assert any(SPEED_REFERENCE_CODE in text for text in references)


def test_no_compare_writes_nothing_under_references(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, "--no-compare")
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "cache" / "references").exists()


def test_an_unknown_player_exits_and_lists_the_roster(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, "--player", "Nobody")

    assert result.exit_code == 1
    assert "Emberkin" in result.output


def test_the_player_defaults_to_the_report_owner(tmp_path: Path) -> None:
    # The API lowercases the owner's name; the roster does not.
    result = run_analyze(tmp_path)

    assert result.exit_code == 0
    assert written_findings(tmp_path)["player"] == "Emberkin"


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
    result = _invoke(tmp_path, ["--player", "Emberkin"], transport)

    assert result.exit_code == 0, result.output
    payload = written_findings(tmp_path)
    assert payload["comparison"]["compared"] is True
    references = payload["comparison"]["references"]
    loaded_speed = [r["report_code"] for r in references if r["axis"] == "speed" and r["loaded"]]
    loaded_parse = [r["report_code"] for r in references if r["axis"] == "parse" and r["loaded"]]
    assert loaded_speed == [SPEED_REFERENCE_CODE]
    assert loaded_parse == [PARSE_REFERENCE_CODE]


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
    assert payload["comparison"]["sample_size"] == {"speed": 0, "parse": 0}
    assert all(not r["loaded"] for r in payload["comparison"]["references"])
    assert any(f["id"] == "compare.speed.unavailable" for f in payload["findings"])


def test_an_empty_leaderboard_degrades_to_no_comparison(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, rankings=[])

    assert result.exit_code == 0
    payload = written_findings(tmp_path)
    assert payload["comparison"]["compared"] is False
    assert any(f["id"] == "compare.speed.unavailable" for f in payload["findings"])


def test_comparison_fields_hold_correct_values(tmp_path: Path) -> None:
    """Asserts the values in the references list, not just their keys.

    The fixture's mock data is chosen to match the task brief's specimen values.
    This test pins the contract to fixed literals so a future swap (e.g. report
    code or keystone level) would fail, not silently produce wrong output on
    screen.
    """
    result = run_analyze(tmp_path, "--player", "Emberkin")

    assert result.exit_code == 0
    payload = written_findings(tmp_path)
    references = {r["axis"]: r for r in payload["comparison"]["references"]}

    speed_reference = references["speed"]
    assert speed_reference["report_code"] == "71cv4MRdNCp8ZFjG"
    assert speed_reference["fight_id"] == 28
    assert speed_reference["keystone_level"] == 16
    assert (
        speed_reference["url"] == "https://www.warcraftlogs.com/reports/71cv4MRdNCp8ZFjG?fight=28"
    )
    assert speed_reference["loaded"] is True
    assert speed_reference["reason"] == ""
    assert set(speed_reference.keys()) == {
        "axis", "report_code", "fight_id", "keystone_level", "url", "loaded", "reason",
        "from_cache",
    }

    parse_reference = references["parse"]
    assert parse_reference["report_code"] == "37FzMg9pVPH6fnJT"
    assert parse_reference["fight_id"] == 16
    assert parse_reference["keystone_level"] == 16
    assert (
        parse_reference["url"] == "https://www.warcraftlogs.com/reports/37FzMg9pVPH6fnJT?fight=16"
    )
    assert parse_reference["loaded"] is True
    assert parse_reference["reason"] == ""
    assert set(parse_reference.keys()) == {
        "axis", "report_code", "fight_id", "keystone_level", "url", "loaded", "reason",
        "from_cache",
    }


def test_a_compared_run_fetches_both_players_auras_and_reports_uptime(tmp_path: Path) -> None:
    """The defining feature of this task: two `AuraTable` queries, one per player,
    feeding a real, populated uptime finding — not the `unavailable` fallback a
    missing counterpart (or a fixture with no boss-pull time at all) would
    silently produce instead, satisfying `any(id.startswith("compare.uptime."))`
    either way and hiding the bug.

    The shared fixture's only pull is trash, so both runs need a boss pull
    (`boss_pull_reports`) before `compare_uptime` measures any boss-pull time at
    all; `aura_rows_by_code` then gives both sides the same ability at
    different uptimes, so the gap actually clears the reporting thresholds in
    `wowperf.domain.comparison.uptime` — and, since Task 10, our own side must
    carry the ability at all, or `_gap_findings` now drops it as attributed to
    someone else's kit rather than this player's.
    """
    calls: list[str] = []
    result = run_analyze(
        tmp_path,
        calls=calls,
        boss_pull_reports=("abc123", PARSE_REFERENCE_CODE),
        aura_rows_by_code={
            "abc123": {
                "onSelf": [
                    {
                        "guid": 999,
                        "name": "Power Infusion",
                        "totalUptime": 1000,
                        "totalUses": 1,
                        "bands": [{"startTime": 1000, "endTime": 2000}],
                    }
                ],
            },
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


def test_a_counterpart_missing_from_the_references_own_roster_fetches_no_auras(
    tmp_path: Path,
) -> None:
    """When the parse leaderboard names a player the reference's own roster does
    not contain, `find_player` can never resolve the counterpart, and the
    counterpart's aura fetch never fires — a state `cli.analyze` already handles.
    Our own auras must be fetched only once that counterpart is known to resolve,
    or this state pays for one `AuraTable` query it then has no use for."""
    calls: list[str] = []
    ghost_row = {**_parse_row(16), "name": "Ghost"}
    transport = build_analyze_transport(parse_rows=[ghost_row], calls=calls)
    result = _invoke(tmp_path, [], transport)

    assert result.exit_code == 0, result.output
    assert "AuraTable" not in calls


def test_no_compare_issues_no_aura_queries(tmp_path: Path) -> None:
    calls: list[str] = []
    result = run_analyze(tmp_path, "--no-compare", calls=calls)

    assert result.exit_code == 0
    assert "AuraTable" not in calls


def test_an_aura_fetch_that_fails_still_writes_the_report(tmp_path: Path) -> None:
    """Drives the `WclError` branch of `cli._auras`: a null `data` block now makes
    `WclClient.execute` itself raise `WclError`, before `WclRunRepository`'s own
    `_require_report` guard is ever reached."""
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


# ---------------------------------------------------------------------------
# `_samples`: drawing up to `SAMPLE_SIZE` references per axis, and recording
# every candidate the leaderboard offered along the way. Exercised directly,
# against a `WclRankingRepository`/`WclRunRepository` pair backed by a mock
# transport, rather than through the full `analyze` command: what matters here
# is the sampling and exclusion logic, not argument parsing or file output.
# ---------------------------------------------------------------------------

OUR_RUN = Run(
    report_code="abc123",
    fight_id=36,
    dungeon_name="Den of Nalorakk",
    encounter_id=12660,
    keystone_level=16,
    affix_ids=(9, 10, 147),
    keystone_time_ms=1909000,
    keystone_bonus=1,
    count_reached=744,
    count_required=729,
    npc_counts=(),
    players=(
        Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane", item_level=300),
    ),
    pulls=(),
)
SUBJECT = OUR_RUN.players[0]

# A second roster member, distinct from `SUBJECT`, so a test can pin "excludes
# a candidate containing one of our teammates" apart from "excludes a
# candidate containing the analysed player" — every other roster-exclusion
# test below gives `OUR_RUN` a single-player roster, which cannot tell the
# two apart.
OUR_TEAMMATE = Player(
    actor_id=2, name="Shieldmate", class_name="Warrior", spec="Protection", item_level=300
)
OUR_RUN_WITH_TEAMMATE = OUR_RUN.model_copy(update={"players": (*OUR_RUN.players, OUR_TEAMMATE)})


def _candidate_speed_row(code: str, fight_id: int = 1, level: int = 16) -> dict[str, Any]:
    return {
        "duration": 1000000,
        "report": {"code": code, "fightID": fight_id, "startTime": 1},
        "deaths": 0,
        "bracketData": level,
        "affixes": [9, 10, 147],
        "team": [{"class": "Warrior", "spec": "Protection"}],
        "medal": "silver",
        "score": 400.0,
    }


def _candidate_parse_row(
    code: str, fight_id: int = 1, level: int = 16, character_name: str = "Someone"
) -> dict[str, Any]:
    return {
        "name": character_name,
        "class": "Mage",
        "spec": "Arcane",
        "duration": 1000000,
        "report": {"code": code, "fightID": fight_id, "startTime": 1},
        "bracketData": level,
        "affixes": [9, 10, 147],
        "medal": "silver",
        "score": 400.0,
    }


def _candidate_fights_payload(
    code: str,
    fight_id: int = 1,
    roster: tuple[str, ...] = ("Someone",),
    keystone_level: int = 16,
) -> dict[str, Any]:
    actors = [
        {"id": index + 1, "name": name, "subType": "Mage", "server": "Hyjal"}
        for index, name in enumerate(roster)
    ]
    return {
        "reportData": {
            "report": {
                "code": code,
                "title": "Keys",
                "startTime": 0,
                "endTime": 1000000,
                "owner": {"name": roster[0].lower()},
                "fights": [
                    {
                        "id": fight_id,
                        "name": "Den of Nalorakk",
                        "encounterID": 12660,
                        "startTime": 0,
                        "endTime": 1000000,
                        "kill": True,
                        "keystoneLevel": keystone_level,
                        "keystoneAffixes": [9, 10, 147],
                        "keystoneTime": 900000,
                        "keystoneBonus": 1,
                        "countReached": 100,
                        "countRequired": 100,
                        "npcCountMap": {},
                        "friendlyPlayers": [actor["id"] for actor in actors],
                        "friendlySpecs": ["Arcane"] * len(actors),
                        "friendlyItemLevels": [300] * len(actors),
                        "dungeonPulls": [],
                    }
                ],
                "masterData": {"actors": actors},
            }
        }
    }


def _samples_run_repository(
    tmp_path: Path, fights_by_code: dict[str, dict[str, Any]]
) -> WclRunRepository:
    """A `WclRunRepository` whose Fights query answers from `fights_by_code`; a
    code it does not recognise answers "report not found", reproducing a
    leaderboard row that fails to load. Every other query answers with the
    emptiest shape the speed and parse profiles accept."""
    abilities: dict[str, Any] = {"reportData": {"report": {"masterData": {"abilities": []}}}}
    actors_payload: dict[str, Any] = {"reportData": {"report": {"masterData": {"actors": []}}}}
    affixes_payload: dict[str, Any] = {"gameData": {"affixes": [{"id": 9, "name": "Tyrannical"}]}}
    empty_events: dict[str, Any] = {
        "reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        body = json.loads(request.content)
        query = body["query"]
        name = query.split("query ")[1].split("(")[0].split("{")[0].strip()
        if name == "Fights":
            code = body["variables"]["code"]
            payload = fights_by_code.get(code, {"reportData": {"report": None}})
            return httpx.Response(200, json={"data": payload})
        if name == "Abilities":
            return httpx.Response(200, json={"data": abilities})
        if name == "Actors":
            return httpx.Response(200, json={"data": actors_payload})
        if name == "Affixes":
            return httpx.Response(200, json={"data": affixes_payload})
        if name == "Talents":
            return httpx.Response(
                200, json={"data": {"reportData": {"report": {"fights": [{"id": 1}]}}}}
            )
        return httpx.Response(200, json={"data": empty_events})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRunRepository(client, DiskCache(tmp_path / "runs"))


def _samples_ranking_repository(
    tmp_path: Path,
    speed_rows_by_bracket: dict[int, list[dict[str, Any]]] | None = None,
    parse_rows_by_bracket: dict[int, list[dict[str, Any]]] | None = None,
) -> WclRankingRepository:
    """A `WclRankingRepository` answering FightRankings/CharacterRankings by
    whichever bracket the query actually asked for, so a fixture with rows in
    only one bracket does not fail `assert_bracket` the moment `_samples`
    widens past it looking for more."""
    speed_by_bracket = speed_rows_by_bracket or {}
    parse_by_bracket = parse_rows_by_bracket or {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        body = json.loads(request.content)
        variables = body["variables"]
        bracket = variables["bracket"]
        is_parse = "className" in variables
        field = "characterRankings" if is_parse else "fightRankings"
        rows = (parse_by_bracket if is_parse else speed_by_bracket).get(bracket, [])
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

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRankingRepository(client, DiskCache(tmp_path / "rankings"))


def test_the_sample_stops_at_the_configured_size(tmp_path: Path) -> None:
    codes = [f"ref{i}" for i in range(SAMPLE_SIZE + 1)]
    fights_by_code = {
        code: _candidate_fights_payload(code, roster=(f"Player{i}",))
        for i, code in enumerate(codes)
    }
    rankings = _samples_ranking_repository(
        tmp_path,
        speed_rows_by_bracket={bracket_for(16): [_candidate_speed_row(code) for code in codes]},
    )
    runs = _samples_run_repository(tmp_path, fights_by_code)

    speed, _parse, records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    assert len(speed.members) == SAMPLE_SIZE
    # The row past the sample size was never even weighed, once the sample was full.
    assert len([record for record in records if record.axis == "speed"]) == SAMPLE_SIZE


def test_our_own_run_is_never_a_member(tmp_path: Path) -> None:
    codes = [f"ref{i}" for i in range(SAMPLE_SIZE)]
    fights_by_code = {
        code: _candidate_fights_payload(code, roster=(f"Player{i}",))
        for i, code in enumerate(codes)
    }
    rows = [_candidate_speed_row(OUR_RUN.report_code, OUR_RUN.fight_id)] + [
        _candidate_speed_row(code) for code in codes
    ]
    rankings = _samples_ranking_repository(tmp_path, speed_rows_by_bracket={bracket_for(16): rows})
    runs = _samples_run_repository(tmp_path, fights_by_code)

    speed, _parse, records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    assert all(member.row.report_code != OUR_RUN.report_code for member in speed.members)
    self_record = next(record for record in records if record.report_code == OUR_RUN.report_code)
    assert self_record.loaded is False
    assert self_record.reason


def test_a_candidate_whose_roster_holds_one_of_our_characters_is_skipped(tmp_path: Path) -> None:
    fights_by_code = {
        "cleanrun": _candidate_fights_payload("cleanrun", roster=("Someone",)),
        # The second leaderboard row's roster contains SUBJECT's own name.
        "sameplayer": _candidate_fights_payload("sameplayer", roster=(SUBJECT.name,)),
    }
    rows = [_candidate_speed_row("cleanrun"), _candidate_speed_row("sameplayer")]
    rankings = _samples_ranking_repository(tmp_path, speed_rows_by_bracket={bracket_for(16): rows})
    runs = _samples_run_repository(tmp_path, fights_by_code)

    speed, _parse, records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    assert all(member.row.report_code != "sameplayer" for member in speed.members)
    assert len(speed.members) == 1
    excluded = next(record for record in records if record.report_code == "sameplayer")
    # The load itself succeeded — the roster is what got it rejected — so it is
    # recorded as loaded, with the reason carrying the actual verdict.
    assert excluded.loaded is True
    assert excluded.reason


def test_a_candidate_whose_roster_holds_one_of_our_teammates_is_skipped(tmp_path: Path) -> None:
    """The self-match check reads the whole roster (`run.players`, plural), not
    only the analysed player's own name — "the fast runs did this" would still
    be a small lie if one of them fielded a teammate rather than the player
    under analysis. Uses `OUR_RUN_WITH_TEAMMATE` because `OUR_RUN` itself has a
    single-player roster and so cannot distinguish this case from
    `test_a_candidate_whose_roster_holds_one_of_our_characters_is_skipped`."""
    fights_by_code = {
        "cleanrun": _candidate_fights_payload("cleanrun", roster=("Someone",)),
        # The second row's roster carries our teammate's name, not SUBJECT's own.
        "teammate": _candidate_fights_payload("teammate", roster=(OUR_TEAMMATE.name,)),
    }
    rows = [_candidate_speed_row("cleanrun"), _candidate_speed_row("teammate")]
    rankings = _samples_ranking_repository(tmp_path, speed_rows_by_bracket={bracket_for(16): rows})
    runs = _samples_run_repository(tmp_path, fights_by_code)

    speed, _parse, records = _samples(rankings, runs, OUR_RUN_WITH_TEAMMATE, SUBJECT)

    assert all(member.row.report_code != "teammate" for member in speed.members)
    excluded = next(record for record in records if record.report_code == "teammate")
    assert excluded.loaded is True
    assert excluded.reason == "the roster includes one of our own characters"


def test_a_candidate_that_failed_to_load_is_recorded_with_its_reason(tmp_path: Path) -> None:
    fights_by_code = {"cleanrun": _candidate_fights_payload("cleanrun", roster=("Someone",))}
    rows = [_candidate_speed_row("brokenrun"), _candidate_speed_row("cleanrun")]
    rankings = _samples_ranking_repository(tmp_path, speed_rows_by_bracket={bracket_for(16): rows})
    runs = _samples_run_repository(tmp_path, fights_by_code)

    _speed, _parse, records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    failed = next(
        record for record in records if not record.loaded and record.report_code == "brokenrun"
    )
    assert failed.reason


def test_a_short_leaderboard_yields_a_short_sample_rather_than_an_error(tmp_path: Path) -> None:
    fights_by_code = {
        "ref0": _candidate_fights_payload("ref0", roster=("Player0",)),
        "ref1": _candidate_fights_payload("ref1", roster=("Player1",)),
    }
    rows = [_candidate_speed_row("ref0"), _candidate_speed_row("ref1")]
    rankings = _samples_ranking_repository(tmp_path, speed_rows_by_bracket={bracket_for(16): rows})
    runs = _samples_run_repository(tmp_path, fights_by_code)

    speed, _parse, _records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    assert len(speed.members) == 2


def test_a_narrow_bracket_widens_to_the_next_one_to_fill_the_sample(tmp_path: Path) -> None:
    fights_by_code = {
        code: _candidate_fights_payload(code, roster=(name,))
        for code, name in (
            ("near0", "PlayerA"), ("near1", "PlayerB"), ("far0", "PlayerC"),
            ("far1", "PlayerD"), ("far2", "PlayerE"),
        )
    }
    rankings = _samples_ranking_repository(
        tmp_path,
        speed_rows_by_bracket={
            bracket_for(16): [_candidate_speed_row("near0"), _candidate_speed_row("near1")],
            # One level down from our own, which is what `_samples` asks
            # `fastest_runs` to widen into once the first bracket falls short
            # of `SAMPLE_SIZE`.
            bracket_for(15): [
                _candidate_speed_row("far0", level=15),
                _candidate_speed_row("far1", level=15),
                _candidate_speed_row("far2", level=15),
            ],
        },
    )
    runs = _samples_run_repository(tmp_path, fights_by_code)

    speed, _parse, _records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    assert len(speed.members) == SAMPLE_SIZE
    assert {member.row.report_code for member in speed.members} == {
        "near0", "near1", "far0", "far1", "far2",
    }


def test_the_parse_axis_mirrors_every_speed_exclusion(tmp_path: Path) -> None:
    """One fixture exercising all four outcomes on the parse axis: our own run,
    a load failure, a roster self-match, and a clean member — proving the
    parse loop was actually wired the same way as the speed loop, not merely
    written to look the same."""
    fights_by_code = {
        "selfmatch": _candidate_fights_payload("selfmatch", roster=(SUBJECT.name,)),
        "cleanparse": _candidate_fights_payload("cleanparse", roster=("Someone",)),
    }
    rows = [
        _candidate_parse_row(OUR_RUN.report_code, OUR_RUN.fight_id),
        _candidate_parse_row("brokenparse"),
        _candidate_parse_row("selfmatch"),
        _candidate_parse_row("cleanparse"),
    ]
    rankings = _samples_ranking_repository(tmp_path, parse_rows_by_bracket={bracket_for(16): rows})
    runs = _samples_run_repository(tmp_path, fights_by_code)

    _speed, parse, records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    assert [member.row.report_code for member in parse.members] == ["cleanparse"]

    by_code = {record.report_code: record for record in records if record.axis == "parse"}
    assert by_code[OUR_RUN.report_code].loaded is False
    assert by_code[OUR_RUN.report_code].reason == "this is the run under analysis"
    assert by_code["brokenparse"].loaded is False
    assert by_code["brokenparse"].reason
    assert by_code["selfmatch"].loaded is True
    assert by_code["selfmatch"].reason
    assert by_code["cleanparse"].loaded is True
    assert by_code["cleanparse"].reason == ""
    assert by_code["cleanparse"].from_cache is False


def test_the_parse_sample_also_stops_at_the_configured_size(tmp_path: Path) -> None:
    codes = [f"parseref{i}" for i in range(SAMPLE_SIZE + 1)]
    fights_by_code = {
        code: _candidate_fights_payload(code, roster=(f"ParsePlayer{i}",))
        for i, code in enumerate(codes)
    }
    rankings = _samples_ranking_repository(
        tmp_path,
        parse_rows_by_bracket={
            bracket_for(16): [_candidate_parse_row(code) for code in codes]
        },
    )
    runs = _samples_run_repository(tmp_path, fights_by_code)

    _speed, parse, records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    assert len(parse.members) == SAMPLE_SIZE
    assert len([record for record in records if record.axis == "parse"]) == SAMPLE_SIZE


def test_a_fresh_candidate_is_recorded_as_not_from_the_cache(tmp_path: Path) -> None:
    fights_by_code = {"cleanrun": _candidate_fights_payload("cleanrun", roster=("Someone",))}
    rows = [_candidate_speed_row("cleanrun")]
    rankings = _samples_ranking_repository(tmp_path, speed_rows_by_bracket={bracket_for(16): rows})
    runs = _samples_run_repository(tmp_path, fights_by_code)

    _speed, _parse, records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    [record] = records
    assert record.from_cache is False


def test_a_reused_candidate_is_recorded_as_served_from_the_cache(tmp_path: Path) -> None:
    fights_by_code = {"cleanrun": _candidate_fights_payload("cleanrun", roster=("Someone",))}
    rows = [_candidate_speed_row("cleanrun")]
    rankings = _samples_ranking_repository(tmp_path, speed_rows_by_bracket={bracket_for(16): rows})
    runs = _samples_run_repository(tmp_path, fights_by_code)

    _samples(rankings, runs, OUR_RUN, SUBJECT)
    _speed, _parse, records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    [record] = records
    assert record.from_cache is True


def test_a_record_names_its_report_fight_level_axis_and_url(tmp_path: Path) -> None:
    fights_by_code = {"cleanrun": _candidate_fights_payload("cleanrun", roster=("Someone",))}
    rows = [_candidate_speed_row("cleanrun", fight_id=7)]
    rankings = _samples_ranking_repository(tmp_path, speed_rows_by_bracket={bracket_for(16): rows})
    runs = _samples_run_repository(tmp_path, fights_by_code)

    _speed, _parse, records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    [record] = records
    assert record.report_code == "cleanrun"
    assert record.fight_id == 7
    assert record.keystone_level == 16
    assert record.axis == "speed"
    assert record.url == "https://www.warcraftlogs.com/reports/cleanrun?fight=7"


def test_each_speed_member_carries_its_own_comparability_and_alignment(tmp_path: Path) -> None:
    # One level below ours, so `Comparability` has something other than a zero
    # gap to report — reached by `_samples`' own widening, the same as a real
    # short bracket would be, rather than asserting on a bracket 16 rows can
    # never legitimately arrive on.
    fights_by_code = {
        "cleanrun": _candidate_fights_payload("cleanrun", roster=("Someone",), keystone_level=15)
    }
    rows = [_candidate_speed_row("cleanrun", level=15)]
    rankings = _samples_ranking_repository(tmp_path, speed_rows_by_bracket={bracket_for(15): rows})
    runs = _samples_run_repository(tmp_path, fights_by_code)

    speed, _parse, _records = _samples(rankings, runs, OUR_RUN, SUBJECT)

    [member] = speed.members
    assert member.comparability.our_level == 16
    assert member.comparability.their_level == 15
    assert isinstance(member.alignment, Alignment)


# ---------------------------------------------------------------------------
# `_fetch_parse_auras`: every parse member's own aura data, and our own side's,
# fetched at most once. Before this fix, `cli.analyze` fetched auras for only
# `parse_sample.members[0]`, so `ParseSample.aura_eligible` could never hold
# more than one member and `compare_uptime_sample`'s aggregate path
# (`MIN_SAMPLE_FOR_AGGREGATE`) was dead code against a real run. Exercised
# directly against `ParseMember`/`ParseSample` values built in memory, with a
# `WclRunRepository` backed by a mock transport that records every `AuraTable`
# query it answers.
# ---------------------------------------------------------------------------


def _member_run(actor_id: int, name: str) -> Run:
    """A minimal reference run whose roster holds exactly one player, for
    `find_player` to resolve (or fail to resolve) a `ParseRow`'s character
    name against."""
    return Run(
        report_code="irrelevant",
        fight_id=1,
        dungeon_name="Den of Nalorakk",
        encounter_id=12660,
        keystone_level=16,
        affix_ids=(9, 10, 147),
        keystone_time_ms=1000000,
        keystone_bonus=1,
        count_reached=100,
        count_required=100,
        npc_counts=(),
        players=(
            Player(actor_id=actor_id, name=name, class_name="Mage", spec="Arcane", item_level=300),
        ),
        pulls=(),
    )


def _parse_member(code: str, actor_id: int, roster_name: str, row_name: str) -> ParseMember:
    """One parse member whose row names `row_name` and whose own roster names
    `roster_name` — the same name for a resolvable counterpart, different
    names to reproduce a leaderboard row `find_player` can never resolve."""
    return ParseMember(
        row=ParseRow(
            report_code=code,
            fight_id=1,
            keystone_level=16,
            duration_ms=1000000,
            character_name=row_name,
            class_name="Mage",
            spec="Arcane",
        ),
        run=_member_run(actor_id, roster_name),
    )


def _aura_repository(
    tmp_path: Path, subdir: str, calls: list[tuple[str, int, int]]
) -> WclRunRepository:
    """A `WclRunRepository` that answers only `AuraTable`, with empty-but-valid
    aura tables, recording each query's (report_code, fight_id, actor_id) so a
    caller can assert on exactly which aura queries fired and how many times —
    not merely on the outcome."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        variables = json.loads(request.content)["variables"]
        calls.append((variables["code"], variables["fightId"], variables["actorId"]))
        return httpx.Response(
            200,
            json={
                "data": {
                    "reportData": {
                        "report": {
                            "onSelf": {"data": {"auras": [], "totalTime": 0}},
                            "onTargets": {"data": {"auras": [], "totalTime": 0}},
                        }
                    }
                }
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRunRepository(client, DiskCache(tmp_path / subdir))


def test_every_resolvable_parse_member_fetches_its_own_auras(tmp_path: Path) -> None:
    """A five-member parse sample, each member's own roster naming exactly the
    player its row does, so every counterpart resolves — proving the fetch is
    no longer scoped to the sample's top member alone."""
    aura_calls: list[tuple[str, int, int]] = []
    references = _aura_repository(tmp_path, "references", aura_calls)
    ours = _aura_repository(tmp_path, "ours", aura_calls)
    sample = ParseSample(
        members=tuple(
            _parse_member(f"ref{i}", 100 + i, f"Player{i}", f"Player{i}") for i in range(5)
        )
    )

    updated, our_auras = _fetch_parse_auras(sample, ours, references, OUR_RUN, SUBJECT)

    assert len(updated.aura_eligible) == 5
    assert our_auras is not None


def test_our_auras_is_fetched_exactly_once_across_every_member(tmp_path: Path) -> None:
    """`our_auras` is our own player's data, shared across every member inside
    `compare_uptime_sample` — not a per-member fetch. Asserts on the fake's
    call count, not just on the result, so a regression that re-fetched it per
    member would be caught even though every member's own auras would still
    end up populated either way."""
    aura_calls: list[tuple[str, int, int]] = []
    references = _aura_repository(tmp_path, "references", aura_calls)
    ours = _aura_repository(tmp_path, "ours", aura_calls)
    sample = ParseSample(
        members=tuple(
            _parse_member(f"ref{i}", 100 + i, f"Player{i}", f"Player{i}") for i in range(5)
        )
    )

    _fetch_parse_auras(sample, ours, references, OUR_RUN, SUBJECT)

    our_side_calls = [call for call in aura_calls if call[0] == OUR_RUN.report_code]
    assert len(our_side_calls) == 1
    assert len(aura_calls) == 6  # 5 counterparts + our own side, fetched once


def test_a_member_whose_counterpart_cannot_be_resolved_keeps_auras_none(tmp_path: Path) -> None:
    """One member's row names a player its own roster does not contain —
    `find_player` can never resolve them, so that member's `auras` stays
    `None` — while a second, resolvable member still gets its own aura data.
    A member that cannot resolve must not block the ones that can."""
    aura_calls: list[tuple[str, int, int]] = []
    references = _aura_repository(tmp_path, "references", aura_calls)
    ours = _aura_repository(tmp_path, "ours", aura_calls)
    resolvable = _parse_member("ref0", 101, "Player0", "Player0")
    ghost = _parse_member("ref1", 102, "Player1", "Ghost")
    sample = ParseSample(members=(resolvable, ghost))

    updated, our_auras = _fetch_parse_auras(sample, ours, references, OUR_RUN, SUBJECT)

    by_code = {member.row.report_code: member for member in updated.members}
    assert by_code["ref0"].auras is not None
    assert by_code["ref1"].auras is None
    assert our_auras is not None
    # One counterpart query (ref0) plus our own side, fetched once — the
    # unresolvable member costs no query at all, ours included.
    assert len(aura_calls) == 2


def test_no_member_resolving_fetches_our_own_auras_not_at_all(tmp_path: Path) -> None:
    """When not one member's counterpart can be resolved, `our_auras` is never
    fetched either — there is nothing for it to be compared against."""
    aura_calls: list[tuple[str, int, int]] = []
    references = _aura_repository(tmp_path, "references", aura_calls)
    ours = _aura_repository(tmp_path, "ours", aura_calls)
    ghost = _parse_member("ref0", 101, "Player0", "Ghost")
    sample = ParseSample(members=(ghost,))

    updated, our_auras = _fetch_parse_auras(sample, ours, references, OUR_RUN, SUBJECT)

    assert updated.members[0].auras is None
    assert our_auras is None
    assert aura_calls == []


def test_analyze_writes_an_html_report_beside_the_findings(tmp_path: Path) -> None:
    result = run_analyze(tmp_path)
    assert result.exit_code == 0, result.output
    written = tmp_path / "out" / "abc123-36.html"
    assert written.exists()
    assert written.read_text(encoding="utf-8").lstrip().lower().startswith("<!doctype html>")


KILLING_BLOW_ABILITY_ID = 1234
KILLING_BLOW_ICON = "spell_frost_frostbolt02.jpg"


def test_analyze_writes_a_report_whose_icons_are_embedded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The CLI wires a real `BlizzardIcons` into `render`, built from the run's own
    ability dictionary: a death card's killing blow draws its icon embedded as a
    data URI, never linked to the CDN it came from. `httpx.Client` is not what
    `build_icons`' fetcher calls, so `httpx.get` is stubbed here directly — the
    stubbed CDN answers every request with the same fake image; the point is
    that the CLI wires an icon source in at all, not what image it returns."""

    def fake_get(url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8fake")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = run_analyze(
        tmp_path,
        abilities=[
            {"gameID": KILLING_BLOW_ABILITY_ID, "name": "Frostbolt", "icon": KILLING_BLOW_ICON}
        ],
        death_events=[
            {
                "type": "death",
                "targetID": 693,
                "timestamp": 4000,
                "killingAbilityGameID": KILLING_BLOW_ABILITY_ID,
            }
        ],
    )
    assert result.exit_code == 0, result.output

    html = (tmp_path / "out" / "abc123-36.html").read_text(encoding="utf-8")
    assert "url(data:image/jpeg;base64," in html
    assert "url(http" not in html


def test_a_failed_icon_fetch_does_not_abort_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`build_icons`' fetcher sits inside the `render(...)` call, which runs after
    `analyze`'s own try/except around the API calls has already closed. A
    transport failure fetching one icon among the dozens a real report fetches
    must not escape uncaught and abort the run after the findings file has
    already been written but before the report has."""

    def fake_get(url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("connection reset")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = run_analyze(
        tmp_path,
        abilities=[
            {"gameID": KILLING_BLOW_ABILITY_ID, "name": "Frostbolt", "icon": KILLING_BLOW_ICON}
        ],
        death_events=[
            {
                "type": "death",
                "targetID": 693,
                "timestamp": 4000,
                "killingAbilityGameID": KILLING_BLOW_ABILITY_ID,
            }
        ],
    )
    assert result.exit_code == 0, result.output

    html = (tmp_path / "out" / "abc123-36.html").read_text(encoding="utf-8")
    assert "url(data:image" not in html


def _analyze_with_an_unusable_icon_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """Run `analyze` with a file sitting where the icon cache directory belongs.

    `IconStore` creates its directory when it is constructed, and a file of the
    same name makes that `mkdir` raise however permissive its flags are -- the
    same shape of failure as a directory the process may not write to, without
    needing a permission this suite cannot portably arrange. The stubbed CDN
    answers every request with a real image, so an icon missing from the page
    can only be the store's doing.
    """

    def fake_get(url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8fake")

    monkeypatch.setattr(httpx, "get", fake_get)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "icons").write_text("a file, where a directory belongs", encoding="utf-8")

    return run_analyze(
        tmp_path,
        abilities=[
            {"gameID": KILLING_BLOW_ABILITY_ID, "name": "Frostbolt", "icon": KILLING_BLOW_ICON}
        ],
        death_events=[
            {
                "type": "death",
                "targetID": 693,
                "timestamp": 4000,
                "killingAbilityGameID": KILLING_BLOW_ABILITY_ID,
            }
        ],
    )


def test_an_icon_store_that_cannot_be_created_does_not_abort_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The store is built as an argument to `render`, which runs after `analyze`'s own
    try/except has closed and after the findings file has been written. Icons are
    decorative, so a cache directory that cannot be created costs the page its art and
    nothing else: the report is still written, and it still names the ability."""
    result = _analyze_with_an_unusable_icon_store(monkeypatch, tmp_path)
    assert result.exit_code == 0, result.output

    html = (tmp_path / "out" / "abc123-36.html").read_text(encoding="utf-8")
    assert "url(data:image" not in html
    assert "Frostbolt" in html


def test_an_icon_store_that_cannot_be_created_says_so_on_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One icon Blizzard does not serve is silent by design: the page draws the name and
    the reader loses nothing they could act on. A store that cannot be created costs
    every icon on the page at once, for a reason on this machine that the reader can
    fix, so that one is said out loud rather than left to look like a plain report."""
    result = _analyze_with_an_unusable_icon_store(monkeypatch, tmp_path)
    assert result.exit_code == 0, result.output
    assert "writing the report without icons" in result.stderr


def test_an_out_directory_that_cannot_be_created_fails_without_a_traceback(
    tmp_path: Path,
) -> None:
    """Unlike the icons, the output is the run: there is no degraded page to fall back
    to, so this ends the run. It ends it the way every other failure does -- one red
    line naming the path -- rather than as the traceback the unguarded write phase gave.

    A file where the directory belongs makes `mkdir` raise however permissive its
    flags are, which is the same shape of failure as a directory this process may not
    create, without needing a permission the suite cannot portably arrange.
    """
    (tmp_path / "reports").write_text("a file, where a directory belongs", encoding="utf-8")

    result = run_analyze(tmp_path, "--no-compare", "--out", str(tmp_path / "reports"))

    assert result.exit_code == 1
    assert "reports" in result.stderr
    assert "Traceback" not in result.output
    assert not isinstance(result.exception, OSError)


def test_a_findings_file_that_cannot_be_written_fails_without_a_traceback(
    tmp_path: Path,
) -> None:
    """A directory standing where the findings file goes makes the write raise -- an
    `IsADirectoryError` here, a `PermissionError` on Windows, both `OSError`. It stands
    in for the disk being full or the volume read-only, neither of which a test can ask
    for, and it reaches the same handler."""
    (tmp_path / "out" / "abc123-36.findings.json").mkdir(parents=True)

    result = run_analyze(tmp_path, "--no-compare")

    assert result.exit_code == 1
    assert "abc123-36.findings.json" in result.stderr
    assert "Traceback" not in result.output
    assert not isinstance(result.exception, OSError)


def test_a_report_that_cannot_be_written_fails_after_the_findings_were_written(
    tmp_path: Path,
) -> None:
    """The findings land, the page does not. This is the one that matters: the run has
    already told the reader where the findings went, so the failure has to arrive as a
    statement about the page rather than as a traceback under a success line."""
    (tmp_path / "out" / "abc123-36.html").mkdir(parents=True)

    result = run_analyze(tmp_path, "--no-compare")

    assert result.exit_code == 1
    assert (tmp_path / "out" / "abc123-36.findings.json").is_file()
    assert "findings written to" in result.stdout
    assert "abc123-36.html" in result.stderr
    assert "Traceback" not in result.output
    assert not isinstance(result.exception, OSError)


def test_the_html_report_fetches_nothing_from_the_network(tmp_path: Path) -> None:
    """Mirrors `test_the_page_executes_only_its_own_script` in `test_html_invariants.py`: an
    `href` to the reference run on warcraftlogs.com is a link the reader may follow,
    not a resource the page loads, so only `src=` and script/stylesheet tags are checked."""
    result = run_analyze(tmp_path)
    assert result.exit_code == 0, result.output
    html = (tmp_path / "out" / "abc123-36.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script\b([^>]*)>", html, flags=re.I)
    assert len(scripts) == 1 and "src=" not in scripts[0].lower()
    assert "@import" not in html.lower()
    assert "<link rel=" not in html.lower()
    for src in re.findall(r'src="([^"]*)"', html, flags=re.IGNORECASE):
        assert not src.startswith(("http://", "https://", "//")), src


def test_the_report_names_the_affixes(tmp_path: Path) -> None:
    invoke_analyze(tmp_path)
    [html] = (tmp_path / "out").glob("*.html")
    assert "Tyrannical" in html.read_text(encoding="utf-8")


def test_no_compare_still_writes_a_report(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, "--no-compare")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out" / "abc123-36.html").exists()


def test_a_narrative_file_reaches_the_report(tmp_path: Path) -> None:
    # Escaped on comparison: a hand-written narrative file is free text and
    # can carry an apostrophe or ampersand, which autoescape would transform.
    text = "Both of your largest losses were travel."
    notes = tmp_path / "notes.md"
    notes.write_text(text, encoding="utf-8")
    result = run_analyze(tmp_path, "--narrative", str(notes))
    assert result.exit_code == 0, result.output
    html = (tmp_path / "out" / "abc123-36.html").read_text(encoding="utf-8")
    assert str(escape(text)) in html


def test_a_missing_narrative_file_fails_before_anything_is_fetched(tmp_path: Path) -> None:
    calls: list[str] = []
    result = run_analyze(
        tmp_path, "--narrative", str(tmp_path / "absent.md"), calls=calls
    )
    assert result.exit_code == 1
    assert "absent.md" in result.output
    # The whole point: a typo must not cost an API round trip.
    assert calls == []


def test_an_undecodable_narrative_file_names_the_path_before_anything_is_fetched(
    tmp_path: Path,
) -> None:
    """`UnicodeDecodeError`'s own message never names the file it came from — without
    the wrapping in `cli.analyze`, a bad-encoding narrative would print only a codec
    complaint, leaving the reader no way to tell which path caused it."""
    notes = tmp_path / "notes.md"
    notes.write_bytes(b"\xff\xfe not valid utf-8")
    calls: list[str] = []
    result = run_analyze(tmp_path, "--narrative", str(notes), calls=calls)
    assert result.exit_code == 1
    assert "notes.md" in result.output
    assert calls == []


def test_a_narrative_with_markup_is_escaped_in_the_report(tmp_path: Path) -> None:
    """A narrative file containing markup must be escaped before rendering, or a
    malicious narrative could inject scripts or break the page structure. This test
    asserts both that the raw tag does not appear and that the escaped form does."""
    notes = tmp_path / "notes.md"
    notes.write_text(
        "<script>alert('x')</script> and <b>bold</b> text", encoding="utf-8"
    )
    result = run_analyze(tmp_path, "--narrative", str(notes))
    assert result.exit_code == 0, result.output
    html = (tmp_path / "out" / "abc123-36.html").read_text(encoding="utf-8")
    # Assert the raw tags do NOT appear
    assert "<script>alert('x')</script>" not in html
    assert "<b>bold</b>" not in html
    # Assert the escaped forms DO appear
    assert "&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;" in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


def test_a_narrative_with_numbers_fails_before_anything_is_fetched(tmp_path: Path) -> None:
    """Every figure lives in a section that owns it, so a number in the narrative is a
    second unbadged claim. The refusal must cost no API quota, exactly as an unreadable
    narrative path does."""
    notes = tmp_path / "notes.md"
    notes.write_text("Fine.\nTravel cost 3:13.\nAlso fine.\nYou died 4 times.", encoding="utf-8")
    calls: list[str] = []
    result = run_analyze(tmp_path, "--narrative", str(notes), calls=calls)
    assert result.exit_code == 1
    assert calls == []
    assert "notes.md" in result.output
    # Every offending line, not only the first.
    assert "line 2" in result.output
    assert "line 4" in result.output
    assert "Travel cost 3:13." in result.output
    assert "You died 4 times." in result.output


def test_a_narrative_without_numbers_is_accepted(tmp_path: Path) -> None:
    notes = tmp_path / "notes.md"
    notes.write_text("Your losses are route, not execution.", encoding="utf-8")
    result = run_analyze(tmp_path, "--narrative", str(notes))
    assert result.exit_code == 0, result.output
    html = (tmp_path / "out" / "abc123-36.html").read_text(encoding="utf-8")
    assert "Your losses are route, not execution." in html


def test_no_compare_report_contains_the_withheld_reason(tmp_path: Path) -> None:
    """When `--no-compare` is passed, many report sections are withheld and
    replaced with a reason message. The reader must be told explicitly why those
    sections are empty, not left guessing."""
    result = run_analyze(tmp_path, "--no-compare")
    assert result.exit_code == 0, result.output
    html = (tmp_path / "out" / "abc123-36.html").read_text(encoding="utf-8")
    assert (
        "No reference run was fetched for this analysis, so there is nothing to compare against."
        in html
    )


# A finding id as the warning writes it: dotted, lower-case, optionally a `.*` suffix.
FINDING_ID_IN_PROSE = re.compile(r"[a-z]+(?:\.[a-z]+)+\.?\*?")


def test_the_warning_names_exactly_the_nestings_the_report_draws() -> None:
    """The warning and NESTS_INSIDE are one claim written twice; hold them in step.

    Nothing copies one from the other, so they drift silently, and each
    direction of drift lies to a different reader. A containment the warning
    omits invites whoever reads the findings file to sum two figures that
    overlap. A containment NESTS_INSIDE omits drops the "Already counted
    inside" note from the row that needs it, and invites the same addition of
    whoever reads the report instead.
    """
    named = {
        match.rstrip("*").rstrip(".")
        for match in FINDING_ID_IN_PROSE.findall(FINDINGS_ARE_RANKED_NOT_ADDITIVE)
    }
    drawn = {prefix.rstrip(".") for prefix, _ in NESTS_INSIDE}
    drawn |= {parent for _, parent in NESTS_INSIDE}

    # The decomposition ids head the ledger rather than nesting, so the warning
    # may name them without NESTS_INSIDE carrying an entry for them.
    assert named - set(DECOMPOSITION_IDS) == drawn - set(DECOMPOSITION_IDS)


def test_the_throughput_ceiling_is_offered_by_analyze_and_not_by_fetch() -> None:
    """The noisier of the two throughput claims, so it is asked for rather than given.

    Its behaviour is covered where the decision lives, in the analysis service.
    What this pins is that only the command which runs analysers offers it — a
    bulk edit once put it on `fetch`, which runs none and would have advertised
    output it cannot produce.
    """
    from typer.testing import CliRunner

    runner = CliRunner()
    assert "--throughput-ceiling" in runner.invoke(app, ["analyze", "--help"]).output
    assert "--throughput-ceiling" not in runner.invoke(app, ["fetch", "--help"]).output


def test_the_breakdown_names_each_operation_its_calls_and_its_points() -> None:
    ledger = CostLedger()
    ledger.record("Fights", 100.0)
    ledger.record("Casts", 102.0)
    ledger.record("Casts", 103.5)
    ledger.record("RateLimit", 112.5)

    # Column padding is presentation; pinning it would make this brittle without
    # protecting anything. The order, counts, plural and rounding are the claims.
    lines = [" ".join(line.split()) for line in _cost_breakdown(ledger).splitlines()]

    assert lines == [
        "Where they went:",
        "Casts 2 calls 10.50 points",
        "Fights 1 call 2.00 points",
        "RateLimit 1 call 0.00 points",
        "RateLimit ran last, so one of its calls is unpriced: a query's cost is only "
        "known once the next one runs.",
    ]


def test_the_breakdown_of_an_empty_ledger_is_empty() -> None:
    """--no-compare on a fully cached run can spend nothing worth listing."""
    assert _cost_breakdown(CostLedger()) == ""


def test_fetch_prints_where_the_points_went(wired_cli: None, tmp_path: Path) -> None:
    result = runner.invoke(app, ["fetch", "abc123", "--cache-dir", str(tmp_path / "cache")])

    assert result.exit_code == 0, result.output
    normalised = " ".join(result.stderr.split())
    assert "Where they went:" in normalised
    assert "Affixes 1 call 10.50 points" in normalised
    assert "RateLimit ran last" in normalised


def test_the_breakdown_accounts_for_exactly_the_points_the_sentence_reports(
    wired_cli: None, tmp_path: Path
) -> None:
    """The two figures come from different arithmetic and must still agree.

    The sentence subtracts one quota reading from another. The table sums a
    difference per query. They match only if every point is attributed to
    exactly one operation — and their agreement is what shows the sentence
    counts the opening quota read but not the closing one, since the table
    cannot price its own last query.
    """
    result = runner.invoke(app, ["fetch", "abc123", "--cache-dir", str(tmp_path / "cache")])
    assert result.exit_code == 0, result.output

    normalised = " ".join(result.stderr.split())
    [spent] = re.findall(r"Rate limit: ([\d.]+) points spent", normalised)
    tabled = [float(points) for points in re.findall(r"([\d.]+) points\b", normalised)[1:]]

    assert tabled, "the table listed nothing, so this proves nothing"
    assert round(sum(tabled), 2) == float(spent)


def test_a_quota_sentence_across_an_hour_boundary_reports_no_spend() -> None:
    """Points reset on a fixed one-hour cycle. Subtracting across the reset used
    to print a negative spend, which the cost table beside it already refuses."""
    before = RateLimit(limit_per_hour=3600, points_spent_this_hour=3550.0, points_reset_in=5)
    after = RateLimit(limit_per_hour=3600, points_spent_this_hour=40.0, points_reset_in=3595)

    sentence = _quota_sentence(before, after)

    assert "-" not in sentence
    assert "reset" in sentence
    assert "3560.00 of 3600 remain" in sentence


def test_a_compared_analyze_accounts_for_every_point_it_reports(tmp_path: Path) -> None:
    """The same invariant as for `fetch`, on the run that issues thirty queries.

    The two figures come from different arithmetic — one subtraction of readings
    against a sum of per-query differences — so they agree only if every point
    lands on exactly one operation. A run this long is also the one where an
    off-by-one, a dropped pair or a miscounted call has room to hide.
    """
    result = invoke_analyze(tmp_path)
    assert result.exit_code == 0, result.output

    normalised = " ".join(result.stderr.split())
    [spent] = re.findall(r"Rate limit: ([\d.]+) points spent", normalised)
    tabled = [float(points) for points in re.findall(r"([\d.]+) points", normalised)[1:]]

    assert len(tabled) > 5, "a compared run touches many operations; this listed few"
    assert round(sum(tabled), 2) == float(spent)
