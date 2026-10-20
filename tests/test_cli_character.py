# ABOUTME: Command-level tests for `character`, over the analyze mock transport plus two queries.
# ABOUTME: Six runs load, one fails to load, one dungeon is left out, and every file lands together.

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from tests.test_cli import (
    PARSE_REFERENCE_CHARACTER_NAME,
    PARSE_REFERENCE_FIGHT,
    SPEED_REFERENCE_CHARACTER_NAME,
    SPEED_REFERENCE_FIGHT,
    _fights_payload_for,
    _parse_row,
    _speed_row,
    build_analyze_transport,
    operation_name,
    plain,
)
from wowperf.adapters.wcl.client import RateLimitExceeded
from wowperf.cli import app
from wowperf.domain.character.patterns import (
    CHARACTER_FINDINGS_ARE_RANKED_NOT_ADDITIVE,
    DIRECTION_RATE_FLOOR,
    DIRECTION_SHARE_FLOOR,
    MIN_DIRECTION_RUNS,
    REPEAT_MIN_RUNS,
)
from wowperf.domain.character.selection import LEVELS_BELOW_TOP
from wowperf.domain.findings import Confidence, Finding

URL = "https://www.warcraftlogs.com/character/eu/argent-dawn/Emberkin?zone=55"
DIRECTORY = "eu-argent-dawn-emberkin"
DUNGEON_IDS = range(101, 109)
OAUTH = "oauth"
"""What `calls` records for a token request, which carries no operation name."""


def a_rank(code: str, fight: int | None, level: int = 16, start: int = 1) -> dict[str, Any]:
    return {"report": {"code": code, "fightID": fight, "startTime": start},
            "bracketData": level, "spec": "Protection", "startTime": start,
            "duration": 1_700_000, "medal": "bronze"}


def build_character_transport(*, difficulties: tuple[int, ...] = (10,),
                              hidden: bool = False,
                              calls: list[str] | None = None,
                              abilities: list[dict[str, Any]] | None = None,
                              player_name: str = "Emberkin",
                              aura_rows_by_code: dict[str, dict[str, list[dict[str, Any]]]]
                              | None = None,
                              death_events: list[dict[str, Any]] | None = None,
                              speed_codes: tuple[str, ...] = (),
                              parse_codes: tuple[str, ...] = (),
                              ) -> httpx.MockTransport:
    """The analyze transport, answering the zone and character-runs queries as well.

    Dungeons 101 to 106 rank the analyze fixture's own run, 107 ranks a report
    that does not exist, and 108 ranks a run with no public log. `calls` records
    every request in the order it was sent, by operation name, or `OAUTH`.
    `abilities` is the analysed run's ability dictionary and `player_name` the
    name on its roster, as the analyze transport takes them, and so are
    `aura_rows_by_code` and `death_events`. `speed_codes` and `parse_codes`, when
    given, replace the one fast run and the one top parse with one per code, each
    a loadable copy of it, so a sample can reach the size a median needs.
    """
    inner = build_analyze_transport(
        player_name, abilities=abilities, aura_rows_by_code=aura_rows_by_code,
        death_events=death_events,
        speed_rows=[{**_speed_row(16), "report": {
            "code": code, "fightID": SPEED_REFERENCE_FIGHT, "startTime": 1}}
            for code in speed_codes] or None,
        parse_rows=[{**_parse_row(16), "report": {
            "code": code, "fightID": PARSE_REFERENCE_FIGHT, "startTime": 1}}
            for code in parse_codes] or None,
    )
    reference_fights = {
        **{code: _fights_payload_for(code, SPEED_REFERENCE_FIGHT, SPEED_REFERENCE_CHARACTER_NAME)
           for code in speed_codes},
        **{code: _fights_payload_for(code, PARSE_REFERENCE_FIGHT, PARSE_REFERENCE_CHARACTER_NAME)
           for code in parse_codes},
    }
    ranks: dict[int, list[dict[str, Any]]] = {
        **{encounter: [a_rank("abc123", 36)] for encounter in range(101, 107)},
        107: [a_rank("zzz999", 1)],
        108: [a_rank("", None)],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            if calls is not None:
                calls.append(OAUTH)
        else:
            name = operation_name(json.loads(request.content)["query"])
            if calls is not None:
                calls.append(name)
            code = json.loads(request.content).get("variables", {}).get("code")
            if name == "Fights" and code in reference_fights:
                return httpx.Response(200, json={"data": reference_fights[code]})
            if name == "Zone":
                return httpx.Response(200, json={"data": {"worldData": {"zone": {
                    "id": 55, "name": "Mythic+ Season 2",
                    "difficulties": [{"id": one, "name": "x"} for one in difficulties],
                    "encounters": [{"id": one, "name": f"Dungeon {one}"} for one in DUNGEON_IDS],
                }}}})
            if name == "CharacterRuns":
                character: dict[str, Any] = {"id": 1, "hidden": hidden}
                character.update({f"e{one}": {"ranks": ranks[one]} for one in DUNGEON_IDS})
                return httpx.Response(
                    200, json={"data": {"characterData": {"character": character}}}
                )
        # `handle_request` is the transport's typed entry point; `.handler` is typed as
        # either a sync or an async handler, which strict mypy will not return as a Response.
        return inner.handle_request(request)

    return httpx.MockTransport(handler)


def invoke(tmp_path: Path, *args: str, transport: httpx.MockTransport | None = None) -> Any:
    chosen = transport or build_character_transport()
    real_client = httpx.Client

    def fake_client(*_: Any, **__: Any) -> httpx.Client:
        return real_client(transport=chosen)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "Client", fake_client)
        mp.setenv("WCL_CLIENT_ID", "id")
        mp.setenv("WCL_CLIENT_SECRET", "secret")
        return CliRunner().invoke(app, ["character", *args,
                                        "--cache-dir", str(tmp_path / "cache"),
                                        "--out", str(tmp_path / "out")])


def read_payload(tmp_path: Path) -> Any:
    return json.loads((tmp_path / "out" / DIRECTORY / "character.json").read_text(
        encoding="utf-8"))


def test_character_writes_its_page_and_every_run_beside_it(tmp_path: Path) -> None:
    result = invoke(tmp_path, URL)

    assert result.exit_code == 0, result.output
    directory = tmp_path / "out" / DIRECTORY
    for name in ("character.json", "character.html", "abc123-36.findings.json", "abc123-36.html"):
        assert (directory / name).is_file(), name
    assert 'href="abc123-36.html"' in (directory / "character.html").read_text(encoding="utf-8")


def character_url(name: str) -> str:
    return f"https://www.warcraftlogs.com/character/eu/argent-dawn/{name}?zone=55"


def written_directories(tmp_path: Path) -> set[str]:
    return {one.name for one in (tmp_path / "out").iterdir() if one.is_dir()}


def test_a_wholly_non_latin_name_keeps_its_own_directory(tmp_path: Path) -> None:
    """Design 3.4's amendment: the directory carries the name casefolded in its own
    script, not the HTML-id slug, which reduces every wholly non-Latin name to one
    fallback and would let a second such character on the realm overwrite the first."""
    name = "Кириллица"
    result = invoke(tmp_path, character_url(name),
                    transport=build_character_transport(player_name=name))

    assert result.exit_code == 0, result.output
    assert written_directories(tmp_path) == {"eu-argent-dawn-кириллица"}
    assert (tmp_path / "out" / "eu-argent-dawn-кириллица" / "character.json").is_file()


def test_two_names_one_slug_apart_write_two_directories(tmp_path: Path) -> None:
    """`Bríala` and `Briala` reduce to one player slug; as two characters on one
    realm they must not share a directory, so neither page overwrites the other."""
    for name in ("Bríala", "Briala"):
        result = invoke(tmp_path, character_url(name),
                        transport=build_character_transport(player_name=name))
        assert result.exit_code == 0, result.output

    assert written_directories(tmp_path) == {"eu-argent-dawn-bríala", "eu-argent-dawn-briala"}


@pytest.mark.parametrize("url", [
    character_url("Ember%2F..%2F..%2Fkin"),
    character_url("Ember%5C..%5C..%5Ckin"),
    "https://www.warcraftlogs.com/character/eu/argent%2F..%2F..%2Fdawn/Emberkin?zone=55",
], ids=["name-slash", "name-backslash", "realm-slash"])
def test_a_part_decoded_into_a_path_separator_is_refused_before_any_request(
    tmp_path: Path, url: str,
) -> None:
    """The URL's realm and name are percent-decoded, and each becomes part of a
    directory name."""
    calls: list[str] = []
    result = invoke(tmp_path, url, transport=build_character_transport(calls=calls))

    assert result.exit_code == 1
    assert "is not a realm or character name" in result.stderr
    assert calls == []


def test_a_cross_run_finding_draws_the_art_only_a_runs_dictionary_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The character page has no ability dictionary of its own: an ability a
    cross-run finding names is drawn from the loaded runs' merged icon names."""
    repeat = Finding(
        id="character.repeat.compare.spells.rate.47528", title="Mind Freeze, again and again",
        detail="", confidence=Confidence.DERIVED, ability_id=47528, ability_name="Mind Freeze",
    )
    monkeypatch.setattr("wowperf.cli.repeated_judgements", lambda _runs: [repeat])
    transport = build_character_transport(abilities=[
        {"gameID": 47528, "name": "Mind Freeze", "icon": "spell_deathknight_mindfreeze.jpg"}
    ])

    result = invoke(tmp_path, URL, transport=transport)

    assert result.exit_code == 0, result.output
    page = (tmp_path / "out" / DIRECTORY / "character.html").read_text(encoding="utf-8")
    assert "https://wow.zamimg.com/images/wow/icons/medium/spell_deathknight_mindfreeze.jpg" in page


def test_the_character_file_names_what_loaded_failed_and_was_left_out(tmp_path: Path) -> None:
    invoke(tmp_path, URL)
    payload = read_payload(tmp_path)

    assert payload["character"]["name"] == "Emberkin"
    assert payload["character"]["spec"] == "Protection"
    assert len(payload["runs"]) == 6
    assert [one["dungeon"] for one in payload["failed"]] == ["Dungeon 107"]
    assert payload["failed"][0]["reason"]
    assert [one["dungeon"] for one in payload["left_out"]] == ["Dungeon 108"]
    ids = [finding["id"] for finding in payload["findings"]]
    assert len(ids) == len(set(ids))
    assert all(finding["confidence"] in {"measured", "derived", "inferred"}
               for finding in payload["findings"])


def test_each_run_in_the_character_file_names_its_dungeon_and_its_two_files(
    tmp_path: Path,
) -> None:
    invoke(tmp_path, URL)
    runs = read_payload(tmp_path)["runs"]

    for one in runs:
        assert (tmp_path / "out" / DIRECTORY / one["findings_file"]).is_file()
        assert (tmp_path / "out" / DIRECTORY / one["report_file"]).is_file()
    assert [one["encounter_id"] for one in runs] == list(range(101, 107))
    assert [one["dungeon"] for one in runs] == [f"Dungeon {one}" for one in range(101, 107)]
    assert {(one["findings_file"], one["report_file"]) for one in runs} == {
        ("abc123-36.findings.json", "abc123-36.html")
    }


POWER_INFUSION = 999


def an_aura(seconds: int) -> dict[str, Any]:
    return {"guid": POWER_INFUSION, "name": "Power Infusion", "totalUptime": seconds * 1000,
            "totalUses": 1, "bands": [{"startTime": 0, "endTime": seconds * 1000}]}


def test_each_run_is_read_on_the_character_it_names(tmp_path: Path) -> None:
    """The join from one run's analysis to the cross-run reading: the subject's
    slug picks their judgements and their comparison table, the fast runs give
    the tempo, and the subject's own deaths are counted. A join that lost any of
    them would empty its part of the page with every run still loading.

    Each loaded run is the one fixture run, so what fires in one fires in all six:
    Power Infusion up half the key against all of it for three top parses is a
    repeated judgement and a direction; three fast runs make a median; and the
    subject dies once a run.
    """
    parse_codes = ("topParseA1", "topParseB2", "topParseC3")
    transport = build_character_transport(
        aura_rows_by_code={"abc123": {"onSelf": [an_aura(960)]},
                           **{code: {"onSelf": [an_aura(1920)]} for code in parse_codes}},
        death_events=[{"type": "death", "targetID": 693, "timestamp": 4000}],
        speed_codes=("fastRunA1", "fastRunB2", "fastRunC3"),
        parse_codes=parse_codes,
    )

    result = invoke(tmp_path, URL, transport=transport)

    assert result.exit_code == 0, result.output
    payload = read_payload(tmp_path)
    ids = {finding["id"] for finding in payload["findings"]}
    assert f"character.repeat.compare.uptime.self.{POWER_INFUSION}" in ids
    assert f"character.direction.buff.{POWER_INFUSION}" in ids
    ledger = payload["group_ledger"]
    assert ledger["deaths"]["compared"] == len(payload["runs"]) == 6
    assert ledger["subject_died_in"] == 6
    assert all(run["tempo"] is not None for run in payload["runs"])


def test_the_character_file_carries_the_warning_and_the_chosen_numbers(tmp_path: Path) -> None:
    invoke(tmp_path, URL)
    payload = read_payload(tmp_path)

    assert payload["findings_are_ranked_not_additive"] == CHARACTER_FINDINGS_ARE_RANKED_NOT_ADDITIVE
    rules = payload["rules"]
    assert rules["levels_below_top"] == LEVELS_BELOW_TOP
    assert rules["repeat_min_runs"] == REPEAT_MIN_RUNS
    assert rules["min_direction_runs"] == MIN_DIRECTION_RUNS
    assert rules["direction_rate_floor"] == DIRECTION_RATE_FLOOR
    assert rules["direction_share_floor"] == DIRECTION_SHARE_FLOOR
    assert "time_withheld_reason" in payload["group_ledger"]


def test_no_zone_stops_before_any_request(tmp_path: Path) -> None:
    calls: list[str] = []
    result = invoke(tmp_path, URL.split("?")[0], transport=build_character_transport(calls=calls))

    assert result.exit_code == 1
    assert "zone" in plain(result.output + result.stderr).lower()
    assert calls == []


def test_the_zone_flag_stands_in_for_the_urls_own(tmp_path: Path) -> None:
    result = invoke(tmp_path, URL.split("?")[0], "--zone", "55")

    assert result.exit_code == 0, result.output
    assert read_payload(tmp_path)["character"]["zone_id"] == 55


def test_a_narrative_stating_a_number_is_refused_before_any_request(tmp_path: Path) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("Died to the 3rd boss.\n", encoding="utf-8")
    calls: list[str] = []

    result = invoke(tmp_path, URL, "--narrative", str(notes),
                    transport=build_character_transport(calls=calls))

    assert result.exit_code == 1
    assert "states no numbers" in result.stderr
    assert calls == []


def test_a_raid_zone_is_refused_before_the_runs_are_listed(tmp_path: Path) -> None:
    calls: list[str] = []
    result = invoke(tmp_path, URL, transport=build_character_transport(
        difficulties=(3, 4, 5), calls=calls))

    assert result.exit_code == 1
    assert "not a Mythic+ zone" in result.stderr
    assert "Zone" in calls
    assert "CharacterRuns" not in calls


def test_hidden_rankings_are_refused(tmp_path: Path) -> None:
    result = invoke(tmp_path, URL, transport=build_character_transport(hidden=True))
    assert result.exit_code == 1
    assert "hidden" in result.stderr


def test_an_unknown_spec_names_the_ones_the_character_has(tmp_path: Path) -> None:
    result = invoke(tmp_path, URL, "--spec", "Frost")
    assert result.exit_code == 1
    assert "ranked as: Protection" in result.stderr


def test_a_spent_budget_stops_the_command_rather_than_shrinking_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def spent(*_: Any, **__: Any) -> Any:
        raise RateLimitExceeded("The hourly point budget is spent")

    monkeypatch.setattr("wowperf.cli.analyse_run", spent)
    result = invoke(tmp_path, URL)
    assert result.exit_code == 1
    assert "budget is spent" in result.stderr
    assert not (tmp_path / "out" / DIRECTORY / "character.json").exists()


def test_a_disk_failure_stops_the_command_rather_than_failing_one_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design 4.2's amendment: an `OSError` is the disk, not the run, so it is
    not listed as a failed run and the command stops naming it."""
    def unwritable(*_: Any, **__: Any) -> Any:
        raise OSError("No space left on device")

    monkeypatch.setattr("wowperf.cli.analyse_run", unwritable)
    result = invoke(tmp_path, URL)
    assert result.exit_code == 1
    assert "No space left on device" in result.stderr
    assert not (tmp_path / "out" / DIRECTORY / "character.json").exists()


def test_a_run_page_analyze_already_wrote_is_left_alone(tmp_path: Path) -> None:
    """Design 3.4: the character's runs go in its own directory, so a page another
    `analyze --narrative` wrote under the same `--out` keeps its narrative."""
    existing = tmp_path / "out" / "abc123-36.html"
    existing.parent.mkdir(parents=True)
    existing.write_text("written by analyze", encoding="utf-8")

    result = invoke(tmp_path, URL)

    assert result.exit_code == 0, result.output
    assert existing.read_text(encoding="utf-8") == "written by analyze"


def test_the_command_closes_with_what_it_spent(tmp_path: Path) -> None:
    result = invoke(tmp_path, URL)

    assert result.exit_code == 0, result.output
    assert "Rate limit:" in result.stderr
    assert "Where they went:" in result.stderr


def test_the_character_flags_are_offered_and_the_run_flags_are_not() -> None:
    options = plain(CliRunner().invoke(app, ["character", "--help"]).output).partition("Options")[2]
    for flag in ("--zone", "--spec", "--narrative", "--cache-dir", "--out"):
        assert flag in options, flag
    for flag in ("--player", "--all-players", "--no-compare", "--fight", "--throughput-ceiling"):
        assert flag not in options, flag
