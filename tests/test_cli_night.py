# ABOUTME: The `night` command end to end: its two refusals, its two files, and the tier it buys.
# ABOUTME: Holds loader and builder to one --deep and one --no-deaths, which nothing else does.

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from tests.test_cli import operation_name, plain, quota_response
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.cli import (
    PROGRESSION_FINDINGS_ARE_RANKED_NOT_ADDITIVE,
    RAID_FINDINGS_ARE_RANKED_NOT_ADDITIVE,
    app,
)
from wowperf.domain.report.night_build import CARD_TIER_NONE, build_night_report

runner = CliRunner()

NIGHT_REPORT_CODE = "night12"
NIGHT_FIRST_BOSS = 3492
NIGHT_SECOND_BOSS = 3493
NIGHT_DIFFICULTY = 5
NIGHT_SIZE = 20
NIGHT_KILLING_BLOW = 900

NIGHT_ROSTER: tuple[dict[str, Any], ...] = (
    {"actor_id": 101, "name": "Emberkin", "class_name": "Mage", "spec": "Arcane",
     "item_level": 700},
    {"actor_id": 102, "name": "Stonewake", "class_name": "Warrior", "spec": "Protection",
     "item_level": 702},
)
"""Two raiders, not none.

`night_subject` refuses a pull whose roster is empty, and `AuraTable` is
fetched once per roster player, so a fixture with no roster would make the
card tier cost nothing and hide exactly the difference `--no-deaths` makes."""

FIRST_PULL = 11
SECOND_PULL = 12
THIRD_PULL = 21
"""Fight ids, one boss's two attempts and another boss's one.

Two bosses because the night page groups by boss and one boss could not tell a
command that walked every boss from one that stopped after the first. Distinct
from the roster's actor ids above, so a command reading one where it meant the
other has nowhere to hide."""


FIRST_BOSS_NAME = "The Twin Fangs"
SECOND_BOSS_NAME = "The Hollow Warden"
"""Two boss names carrying no apostrophe.

The page escapes one, and an assertion written in the raw spelling would fail
for the escaping rather than for anything this file is about."""


def _night_fight(
    fight_id: int,
    *,
    encounter_id: int = NIGHT_FIRST_BOSS,
    boss_name: str = FIRST_BOSS_NAME,
    kill: bool = False,
    fight_percentage: float = 40.0,
    difficulty: int = NIGHT_DIFFICULTY,
    start_ms: int = 0,
    end_ms: int = 120_000,
) -> dict[str, Any]:
    """One boss attempt, long enough to count (`MIN_ATTEMPT_SECONDS` is 44s).

    Carries the whole roster, so every pull has a subject for its Players tab
    and an aura table per raider for the card tier to pay for.
    """
    return {
        "id": fight_id,
        "name": boss_name,
        "encounterID": encounter_id,
        "keystoneLevel": None,
        "difficulty": difficulty,
        "size": NIGHT_SIZE,
        "kill": kill,
        "fightPercentage": fight_percentage,
        "startTime": start_ms,
        "endTime": end_ms,
        "friendlyPlayers": [one["actor_id"] for one in NIGHT_ROSTER],
        "friendlySpecs": [one["spec"] for one in NIGHT_ROSTER],
        "friendlyItemLevels": [one["item_level"] for one in NIGHT_ROSTER],
    }


A_NIGHT = [
    _night_fight(FIRST_PULL, fight_percentage=40.0, start_ms=0, end_ms=120_000),
    _night_fight(SECOND_PULL, fight_percentage=20.0, start_ms=200_000, end_ms=320_000),
    _night_fight(
        THIRD_PULL,
        encounter_id=NIGHT_SECOND_BOSS,
        boss_name=SECOND_BOSS_NAME,
        fight_percentage=60.0,
        start_ms=400_000,
        end_ms=520_000,
    ),
]
"""Two bosses, three attempts: two at the first boss and one at the second."""


def _fights_payload(fights: list[dict[str, Any]]) -> dict[str, Any]:
    """The one `Fights` response `load_night` reads the whole report from."""
    return {
        "reportData": {
            "report": {
                "code": NIGHT_REPORT_CODE,
                "title": "Raid Night",
                "startTime": 0,
                "endTime": 700_000,
                "owner": {"name": NIGHT_ROSTER[0]["name"].lower()},
                "fights": fights,
                "masterData": {
                    "actors": [
                        {"id": one["actor_id"], "name": one["name"],
                         "subType": one["class_name"], "server": "Hyjal"}
                        for one in NIGHT_ROSTER
                    ]
                },
            }
        }
    }


def build_night_transport(
    fights: list[dict[str, Any]],
    calls: list[tuple[str, dict[str, Any]]] | None = None,
    *,
    deaths_on: tuple[int, ...] = (FIRST_PULL,),
    failing: frozenset[int] = frozenset(),
) -> httpx.MockTransport:
    """Answer every query a night issues, recording each operation and its variables.

    `deaths_on` names the fights whose `Deaths` stream carries a death. One by
    default rather than none: a healing window is fetched per death, so a night
    with no death at all would buy nothing for `--deep` and could not tell the
    deep tier from the trimmed one.

    `failing` names fights whose `DamageTaken` answers a transport error, which
    is how a single pull fails to deepen without the night failing with it.

    `calls` records `(operation, variables)` per request. Requests, not calls
    into the repository: a cached response is served without one, and the
    ability dictionary is fetched once for the whole report.
    """
    running = 100.0
    quota = [100.0, 140.0]

    def carrying_quota(payload: dict[str, Any]) -> httpx.Response:
        nonlocal running
        running += 1.0
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

    abilities: dict[str, Any] = {
        "reportData": {
            "report": {
                "masterData": {
                    "abilities": [
                        {"gameID": NIGHT_KILLING_BLOW, "name": "Venom Bolt",
                         "icon": "spell_venom.jpg"}
                    ]
                }
            }
        }
    }
    empty_events: dict[str, Any] = {
        "reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}
    }
    graph: dict[str, Any] = {
        "reportData": {
            "report": {"graph": {"data": {"series": [], "startTime": 0, "endTime": 120_000}}}
        }
    }
    auras: dict[str, Any] = {
        "reportData": {
            "report": {"onSelf": {"data": {"auras": [], "totalTime": 120_000}}}
        }
    }

    def deaths_payload(fight_id: int) -> dict[str, Any]:
        if fight_id not in deaths_on:
            return empty_events
        return {
            "reportData": {
                "report": {
                    "events": {
                        "data": [
                            {
                                "type": "death",
                                "targetID": NIGHT_ROSTER[0]["actor_id"],
                                "timestamp": 60_000,
                                "killingAbilityGameID": NIGHT_KILLING_BLOW,
                            }
                        ],
                        "nextPageTimestamp": None,
                    }
                }
            }
        }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        body = json.loads(request.content)
        name = operation_name(body["query"])
        variables = body.get("variables") or {}
        if calls is not None:
            calls.append((name, variables))
        if name == "RateLimit":
            return quota_response(quota.pop(0) if quota else 140.0)
        if name == "Fights":
            return carrying_quota(_fights_payload(fights))
        if name == "Abilities":
            return carrying_quota(abilities)
        if name == "Deaths":
            return carrying_quota(deaths_payload(int(variables["fightId"])))
        if name == "DamageTaken":
            if int(variables["fightId"]) in failing:
                raise httpx.ReadTimeout("damage taken timed out", request=request)
            return carrying_quota(empty_events)
        if name == "DamageDoneGraph":
            return carrying_quota(graph)
        if name == "AuraTable":
            return carrying_quota(auras)
        return carrying_quota(empty_events)

    return httpx.MockTransport(handler)


def run_night(
    tmp_path: Path,
    *extra_args: str,
    fights: list[dict[str, Any]] | None = None,
    calls: list[tuple[str, dict[str, Any]]] | None = None,
    deaths_on: tuple[int, ...] = (FIRST_PULL,),
    failing: frozenset[int] = frozenset(),
) -> Any:
    transport = build_night_transport(
        A_NIGHT if fights is None else fights,
        calls,
        deaths_on=deaths_on,
        failing=failing,
    )
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
                "night", NIGHT_REPORT_CODE,
                "--cache-dir", str(tmp_path / "cache"),
                "--out", str(tmp_path / "out"),
                *extra_args,
            ],
        )


def _written(tmp_path: Path) -> tuple[Path, Path]:
    out = tmp_path / "out"
    return out / f"{NIGHT_REPORT_CODE}.night.json", out / f"{NIGHT_REPORT_CODE}.night.html"


def _operations(calls: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [name for name, _ in calls]


def test_a_night_writes_both_files_at_the_documented_names(tmp_path: Path) -> None:
    """Exit 0, `<code>.night.json` and `<code>.night.html`, and both with something in them.

    The JSON is checked for the shape section 9 promises -- a boss list whose
    entries carry their own findings and their own pulls, each pull carrying
    its findings -- because a payload that wrote the report code and nothing
    else would satisfy "a file exists" without carrying a single reading.
    """
    result = run_night(tmp_path)

    assert result.exit_code == 0, result.output
    findings_file, report_file = _written(tmp_path)
    assert findings_file.exists()
    assert report_file.exists()

    payload = json.loads(findings_file.read_text(encoding="utf-8"))
    assert payload["report_code"] == NIGHT_REPORT_CODE
    assert [boss["encounter_id"] for boss in payload["bosses"]] == [
        NIGHT_FIRST_BOSS,
        NIGHT_SECOND_BOSS,
    ]
    assert [
        pull["fight_id"] for boss in payload["bosses"] for pull in boss["pulls"]
    ] == [FIRST_PULL, SECOND_PULL, THIRD_PULL]
    # A boss's findings are the progression analyser's, and every id it mints
    # carries that prefix. Truthiness alone would survive a command that wrote
    # the pull analyser's list here, which is the mirror of the mistake the
    # pull assertion below catches.
    assert payload["bosses"][0]["findings"], "a boss with no finding has nothing to say"
    assert all(
        finding["id"].startswith("progression.")
        for finding in payload["bosses"][0]["findings"]
    )
    # The pull that had a death: its own findings are the raid analyser's, not
    # the boss's, and a command that wrote the boss's list under every pull
    # would carry a `progression.` id here.
    first_pull = payload["bosses"][0]["pulls"][0]
    assert first_pull["findings"], "a pull with a death has something to say"
    assert all(
        not finding["id"].startswith("progression.") for finding in first_pull["findings"]
    )
    assert all(
        finding["confidence"] in ("measured", "derived", "inferred")
        for boss in payload["bosses"]
        for finding in boss["findings"] + [f for pull in boss["pulls"] for f in pull["findings"]]
    )
    # The rest of the payload's stated contract, which nothing else reads: what
    # the run was asked for, the two counts, and a ranking warning per family.
    # A file whose warning named the other family's rule would tell a reader to
    # sum figures that must not be summed.
    assert payload["asked_for"] == {
        "difficulty": None,
        "deep_fights": [],
        "death_cards": True,
    }
    assert payload["bosses_counted"] == 2
    assert payload["pulls_drawn"] == len(A_NIGHT)
    assert (
        payload["boss_findings_are_ranked_not_additive"]
        == PROGRESSION_FINDINGS_ARE_RANKED_NOT_ADDITIVE
    )
    assert (
        payload["pull_findings_are_ranked_not_additive"]
        == RAID_FINDINGS_ARE_RANKED_NOT_ADDITIVE
    )
    # Both families counted in the line the command prints, so a run that wrote
    # one list and announced the other's length is caught here.
    counted = sum(
        len(boss["findings"]) + sum(len(pull["findings"]) for pull in boss["pulls"])
        for boss in payload["bosses"]
    )
    assert f"{counted} findings written to" in plain(result.output)

    html = report_file.read_text(encoding="utf-8")
    assert FIRST_BOSS_NAME in html
    assert SECOND_BOSS_NAME in html


def test_each_boss_summary_draws_the_findings_the_file_writes_for_that_boss(
    tmp_path: Path,
) -> None:
    """One findings object, two readers: a summary drawn from another list is a defect.

    The first boss was pulled twice and has a summary; the second was pulled
    once and has none, so its findings are in the file and on no summary.
    """
    result = run_night(tmp_path)
    assert result.exit_code == 0, result.output
    findings_file, report_file = _written(tmp_path)
    payload = json.loads(findings_file.read_text(encoding="utf-8"))
    html = report_file.read_text(encoding="utf-8")

    written = {finding["id"] for finding in payload["bosses"][0]["findings"]}
    assert written, "a boss with no finding pins nothing"
    drawn = set(re.findall(r'id="b0-finding-([^"]+)"', html))
    assert drawn == written
    assert 'id="b1-summary"' not in html


def test_deep_and_no_deaths_together_is_refused_naming_both(tmp_path: Path) -> None:
    """Section 10's contradiction: one asks for a fuller card, the other for none.

    Refused before anything is fetched -- the assertion on `calls` is what
    stops a command that refuses only after paying for the report's fights.
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    result = run_night(tmp_path, "--deep", str(FIRST_PULL), "--no-deaths", calls=calls)

    assert result.exit_code != 0
    output = plain(result.output)
    assert "--deep" in output
    assert "--no-deaths" in output
    assert "Traceback" not in result.output
    assert calls == [], "a contradiction must be refused before it is paid for"
    findings_file, report_file = _written(tmp_path)
    assert not findings_file.exists()
    assert not report_file.exists()


def test_deep_naming_a_fight_the_night_has_no_attempt_for_names_the_ids_it_has(
    tmp_path: Path,
) -> None:
    """Section 10: refuse naming the ids that are, rather than deepening nothing.

    Every id the night does hold is asserted, so a message naming only the
    first of them -- or naming the unknown id alone -- fails.
    """
    result = run_night(tmp_path, "--deep", "99")

    assert result.exit_code != 0
    output = plain(result.output)
    assert "99" in output
    for fight_id in (FIRST_PULL, SECOND_PULL, THIRD_PULL):
        assert str(fight_id) in output, output
    assert "Traceback" not in result.output
    findings_file, report_file = _written(tmp_path)
    assert not findings_file.exists()
    assert not report_file.exists()


def test_deep_on_a_night_with_no_readable_attempt_says_so_rather_than_naming_nothing(
    tmp_path: Path,
) -> None:
    """The other half of the same refusal, on a night that has no id to offer back.

    Every fight here is under `MIN_ATTEMPT_SECONDS`, so the report holds bosses
    and the night holds no attempt. The list branch would print "its attempts
    are" followed by nothing, which reads as a bug rather than as an answer.
    """
    too_short = [
        _night_fight(FIRST_PULL, start_ms=0, end_ms=20_000),
        _night_fight(SECOND_PULL, start_ms=100_000, end_ms=130_000),
    ]
    result = run_night(tmp_path, "--deep", str(FIRST_PULL), fights=too_short)

    assert result.exit_code != 0
    output = plain(result.output)
    assert str(FIRST_PULL) in output
    assert "long enough" in output
    assert "its attempts are" not in output
    assert "Traceback" not in result.output


def test_a_report_with_no_boss_fight_is_refused_naming_the_report(tmp_path: Path) -> None:
    """Section 10: a report this command has nothing to read, named in the refusal.

    A Mythic+ report is the case that actually happens: `load_night` returns a
    `Night` with no boss at all, and only the command can name the report it
    was handed.
    """
    keystone = {
        "id": 1,
        "name": "Ara-Kara",
        "encounterID": None,
        "keystoneLevel": 12,
        "difficulty": 10,
        "size": 5,
        "kill": True,
        "fightPercentage": 0.0,
        "startTime": 0,
        "endTime": 120_000,
        "friendlyPlayers": [],
        "friendlySpecs": [],
        "friendlyItemLevels": [],
    }
    result = run_night(tmp_path, fights=[keystone])

    assert result.exit_code != 0
    output = plain(result.output)
    assert NIGHT_REPORT_CODE in output
    # And what is wrong with it. The report code alone would be printed by any
    # failure inside `load_night` that happened to echo it, including ones that
    # have nothing to do with the report holding no boss fight.
    assert "holds no boss fight" in output
    assert "Traceback" not in result.output
    findings_file, report_file = _written(tmp_path)
    assert not findings_file.exists()
    assert not report_file.exists()


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ((), (frozenset(), True)),
        (("--deep", str(FIRST_PULL)), (frozenset({FIRST_PULL}), True)),
        (("--deep", str(FIRST_PULL), "--deep", str(THIRD_PULL)),
         (frozenset({FIRST_PULL, THIRD_PULL}), True)),
        (("--no-deaths",), (frozenset(), False)),
    ],
)
def test_the_loader_and_the_builder_are_handed_the_same_tier(
    tmp_path: Path,
    flags: tuple[str, ...],
    expected: tuple[frozenset[int], bool],
) -> None:
    """One `deep_fights` and one `death_cards` reach both calls, or a card is empty for nothing.

    The loader decides what to fetch and the builder decides what to draw, from
    the same two arguments read independently. Neither can detect a
    disagreement: a pull fetched at the no-cards tier and drawn at the trimmed
    one renders a card with an empty timeline and no explanation at all, with
    every other test on this branch still green.

    Both halves are asserted. Equality between the two calls alone would pass
    for a command that ignored the flags and handed both sides
    `(frozenset(), True)`; equality with `expected` alone would pass for a
    command that read the flags twice and let the two readings drift.
    """
    seen: dict[str, tuple[frozenset[int], bool]] = {}

    real_load = WclRunRepository.load_night_attempts
    real_build = build_night_report

    def spy_load(
        self: WclRunRepository, night: Any, *, deep_fights: frozenset[int], death_cards: bool
    ) -> Any:
        seen["loader"] = (deep_fights, death_cards)
        return real_load(self, night, deep_fights=deep_fights, death_cards=death_cards)

    def spy_build(
        *args: Any, deep_fights: frozenset[int], death_cards: bool, **kwargs: Any
    ) -> Any:
        seen["builder"] = (deep_fights, death_cards)
        return real_build(*args, deep_fights=deep_fights, death_cards=death_cards, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(WclRunRepository, "load_night_attempts", spy_load)
        # By name, so the command's own module global is what is replaced: the
        # builder is a function the command looks up there, and patching the
        # module it was defined in would leave that lookup untouched.
        mp.setattr("wowperf.cli.build_night_report", spy_build)
        result = run_night(tmp_path, *flags)

    assert result.exit_code == 0, result.output
    assert seen["loader"] == seen["builder"]
    assert seen["loader"] == expected


def test_no_deaths_buys_no_aura_table_and_says_so_on_the_page(tmp_path: Path) -> None:
    """The cheapest tier, from the command line: no card work fetched, and the page says why.

    `AuraTable` and `Casts` are the pair the card tier pays for, and the
    default run below is what proves this fixture can ask for them at all --
    without it, a command that fetched neither under any flag would pass.
    """
    # A directory each, so the second run's count is what it fetched rather
    # than what the first run left in the cache.
    cheap: list[tuple[str, dict[str, Any]]] = []
    result = run_night(tmp_path / "cheap", "--no-deaths", calls=cheap)
    assert result.exit_code == 0, result.output
    assert "AuraTable" not in _operations(cheap)
    assert "Casts" not in _operations(cheap)
    assert CARD_TIER_NONE in _written(tmp_path / "cheap")[1].read_text(encoding="utf-8")

    trimmed: list[tuple[str, dict[str, Any]]] = []
    result = run_night(tmp_path / "trimmed", calls=trimmed)
    assert result.exit_code == 0, result.output
    # One table per raider per pull, which is what makes this tier the dear one.
    assert _operations(trimmed).count("AuraTable") == len(NIGHT_ROSTER) * len(A_NIGHT)
    assert CARD_TIER_NONE not in _written(tmp_path / "trimmed")[1].read_text(encoding="utf-8")


def test_deep_buys_a_healing_window_for_the_named_pull_alone(tmp_path: Path) -> None:
    """The dearest tier is per pull, not per night: `--deep` must not leak.

    A `--deep` read once for the night would put every pull on the dearest
    rung, which is the whole night at the price the flag exists to charge for
    one pull. Both fights carry a death here, so a leak has somewhere to show.
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    result = run_night(
        tmp_path,
        "--deep", str(FIRST_PULL),
        calls=calls,
        deaths_on=(FIRST_PULL, SECOND_PULL, THIRD_PULL),
    )

    assert result.exit_code == 0, result.output
    healed = [variables["fightId"] for name, variables in calls if name == "Healing"]
    assert healed, "a deep pull with a death buys a healing window"
    assert set(healed) == {FIRST_PULL}
    # And the page says which pull was named, which is the builder's half of
    # the same decision.
    _, report_file = _written(tmp_path)
    html = report_file.read_text(encoding="utf-8")
    assert f"--deep` named: {FIRST_PULL}" in html


def test_a_pull_that_will_not_load_shrinks_the_night_and_is_named(tmp_path: Path) -> None:
    """Section 10's last rule, at the command: the night still lands, minus that pull.

    The other two pulls are asserted present, so a command that failed the
    whole night -- or that dropped the boss the pull belonged to -- fails here
    rather than passing on the exit code alone.
    """
    result = run_night(tmp_path, failing=frozenset({SECOND_PULL}))

    assert result.exit_code == 0, result.output
    findings_file, report_file = _written(tmp_path)
    payload = json.loads(findings_file.read_text(encoding="utf-8"))
    assert [
        pull["fight_id"] for boss in payload["bosses"] for pull in boss["pulls"]
    ] == [FIRST_PULL, THIRD_PULL]
    assert [one["fight_id"] for one in payload["withheld_pulls"]] == [SECOND_PULL]
    # The page's own sentence, not the bare id: the report code is `night12`,
    # so a search for "12" in this page is true whatever it says about the
    # withheld pull, and would pass over a page that named it nowhere.
    assert (
        f"Fight {SECOND_PULL} is not on this page" in report_file.read_text(encoding="utf-8")
    )


def test_a_pull_with_no_roster_is_refused_naming_the_fight_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """A page that cannot be built leaves no file behind, and no traceback either.

    `night_frame.night_subject` refuses a pull whose roster is empty, naming the
    fight: `Encounter.players` carries no non-empty guarantee and the loader
    passes such a pull straight through, so the command meets it. Built after
    the findings were written, that refusal would hand a reader a findings file
    naming a report that does not exist and no page to open, with a stack trace
    where the reason should be.

    The first pull here carries the whole roster, so everything except the
    second pull is a night that would have rendered: an implementation that
    wrote the findings first leaves that file on disk, and this fails on it
    rather than on the exit code.
    """
    fights = [
        _night_fight(FIRST_PULL, start_ms=0, end_ms=120_000),
        {**_night_fight(SECOND_PULL, start_ms=200_000, end_ms=320_000),
         "friendlyPlayers": [], "friendlySpecs": [], "friendlyItemLevels": []},
    ]
    result = run_night(tmp_path, fights=fights)

    assert result.exit_code != 0
    output = plain(result.output)
    # The refusal's own sentence, which is the only thing that names which pull
    # could not be drawn. Reaching the output at all means it was caught and
    # printed rather than raised through the command.
    assert f"fight {SECOND_PULL}" in output
    assert "roster" in output
    assert "Traceback" not in result.output
    findings_file, report_file = _written(tmp_path)
    assert not findings_file.exists(), "a findings file for a page that was never built"
    assert not report_file.exists()


def test_difficulty_narrows_the_night_to_the_bosses_held_at_it(tmp_path: Path) -> None:
    """The flag is threaded to `load_night` and echoed, and nothing else passed it.

    A real raid night clears some bosses at one difficulty and pushes others at
    another, and `load_night` skips a boss the report holds only at a
    difficulty other than the one asked for. Two bosses at two difficulties
    here, so a command that dropped the flag on the floor draws both -- which
    is what a run with no `--difficulty` at all already draws, and why the
    fixture cannot be one difficulty throughout.
    """
    mixed = [
        _night_fight(FIRST_PULL, difficulty=NIGHT_DIFFICULTY, start_ms=0, end_ms=120_000),
        _night_fight(
            THIRD_PULL,
            encounter_id=NIGHT_SECOND_BOSS,
            boss_name=SECOND_BOSS_NAME,
            difficulty=NIGHT_DIFFICULTY - 1,
            start_ms=400_000,
            end_ms=520_000,
        ),
    ]
    result = run_night(tmp_path, "--difficulty", str(NIGHT_DIFFICULTY), fights=mixed)

    assert result.exit_code == 0, result.output
    findings_file, report_file = _written(tmp_path)
    payload = json.loads(findings_file.read_text(encoding="utf-8"))
    assert [boss["encounter_id"] for boss in payload["bosses"]] == [NIGHT_FIRST_BOSS]
    assert payload["bosses"][0]["difficulty"] == NIGHT_DIFFICULTY
    assert payload["bosses_counted"] == 1
    # Echoed as asked for, which is the half a reader cannot recover from the
    # findings: one boss at difficulty 5 looks the same whether the other was
    # skipped or never pulled.
    assert payload["asked_for"]["difficulty"] == NIGHT_DIFFICULTY
    assert SECOND_BOSS_NAME not in report_file.read_text(encoding="utf-8")


def test_night_states_what_it_spent(tmp_path: Path) -> None:
    """The promise every command that touches the network keeps.

    The breakdown names the dearest operation, so a command printing the
    sentence without the breakdown -- or the breakdown without the sentence --
    fails here.
    """
    result = run_night(tmp_path)

    assert result.exit_code == 0, result.output
    output = plain(result.output)
    assert "Rate limit:" in output
    assert "points spent" in output
    assert "Fights" in output
