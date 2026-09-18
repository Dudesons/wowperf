# ABOUTME: Turns the execution leaderboard into reference kills a mechanics comparison can load.
# ABOUTME: A row with no loadable report is dropped, because it can never be fetched.

import json
from pathlib import Path

import httpx
import pytest

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.encounter_rankings import (
    WclEncounterRankingRepository,
    build_reference_kill_rows,
)
from wowperf.adapters.wcl.errors import WclError

TOKEN = {"access_token": "t", "expires_in": 86400}


def test_a_row_becomes_a_reference_kill() -> None:
    rows = build_reference_kill_rows(
        [
            {
                "report": {"code": "abc123", "fightID": 12},
                "size": 20,
                "duration": 480000,
                "deaths": 0,
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0].report_code == "abc123"
    assert rows[0].fight_id == 12
    assert rows[0].size == 20
    assert rows[0].duration_seconds == 480.0


def test_a_blank_report_code_is_dropped() -> None:
    # The code is type-valid -- an empty string, not None -- so it would survive a
    # guard that only checked for `None`. This is the fixture that proves the
    # truthiness half of the guard: with no null row in the mix, a weakened guard
    # lets the blank row build cleanly (`report_code=""` is a valid `str`), and the
    # assertion below is what fails, not `ReferenceKillRow`'s own validation.
    rows = build_reference_kill_rows(
        [
            {"report": {"code": "", "fightID": 13}, "size": 20,
             "duration": 490000, "deaths": 0},
            {"report": {"code": "abc123", "fightID": 12}, "size": 20,
             "duration": 500000, "deaths": 1},
        ]
    )
    assert [row.report_code for row in rows] == ["abc123"]


def test_a_null_report_code_is_dropped() -> None:
    # Measured 2026-09-14: 39 of 50 `progress` rows carried a null report code.
    # `execution` carried none, but the shape exists and a row that cannot be
    # loaded is no use as a reference.
    #
    # A null code is type-invalid for `ReferenceKillRow` (`report_code: str`,
    # `fight_id: int`): a guard weakened to admit this row does not make the
    # assertion below fail, it makes `ReferenceKillRow(report_code=None, ...)`
    # raise `pydantic.ValidationError` during construction, before the assertion
    # ever runs. That crash is not proof the guard drops this row -- it is
    # Pydantic's type system catching a symptom of the same bug from a different
    # angle. The assertion-level proof that the guard itself does the dropping
    # lives in `test_a_blank_report_code_is_dropped`, above.
    rows = build_reference_kill_rows(
        [
            {"report": {"code": None, "fightID": None}, "size": 20,
             "duration": 480000, "deaths": 0},
            {"report": {"code": "abc123", "fightID": 12}, "size": 20,
             "duration": 500000, "deaths": 1},
        ]
    )
    assert [row.report_code for row in rows] == ["abc123"]


def test_top_parses_sends_its_own_arguments_and_returns_built_rows(tmp_path: Path) -> None:
    """`difficulty` and `partition` are both plain integers, and `class_name`,
    `spec` and `metric` are all strings -- a mis-keyed variable (`partition` sent
    where `difficulty` goes, say) would ship silently unless every argument here
    has a value distinct from every other. The handler records the exact
    variables dict the request carried, and the equality below checks it against
    the call's own arguments, under their own names, rather than trusting
    `top_parses` sent what it was given.
    """
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        captured.update(body["variables"])
        return httpx.Response(
            200,
            json={
                "data": {
                    "worldData": {
                        "encounter": {
                            "id": 3470,
                            "name": "Queen Ansurek",
                            "characterRankings": {
                                "rankings": [
                                    {
                                        "name": "Emberkin", "class": "Evoker",
                                        "spec": "Devastation", "amount": 247358.15773571,
                                        "duration": 407086, "size": 29, "bracketData": 325,
                                        "report": {"code": "cccccccccccccccc", "fightID": 5},
                                    }
                                ]
                            },
                        }
                    }
                }
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x")
    client = WclClient(TokenProvider("id", "secret", http), http)
    repository = WclEncounterRankingRepository(client, DiskCache(tmp_path))

    rows = repository.top_parses(
        encounter_id=3470,
        difficulty=4,
        partition=7,
        class_name="Evoker",
        spec="Devastation",
        metric="dps",
    )

    assert captured == {
        "encounterId": 3470,
        "difficulty": 4,
        "partition": 7,
        "page": 1,
        "className": "Evoker",
        "specName": "Devastation",
        "metric": "dps",
    }
    assert len(rows) == 1
    assert rows[0].report_code == "cccccccccccccccc"
    assert rows[0].fight_id == 5
    assert rows[0].character_name == "Emberkin"
    assert rows[0].amount == 247358.15773571


def test_a_mythic_row_without_size_takes_it_from_the_composition() -> None:
    """The execution board omits `size` on a difficulty whose raid size is fixed.

    Measured 2026-09-16 against encounter 3470 at difficulty 5: all 50 rows
    carried the four composition counts and none carried `size`, while the same
    board for encounter 3492 at difficulty 4 carried `size` on all 50. Reading
    `row["size"]` therefore crashed with `KeyError` on every Mythic boss fight
    ever passed to `wowperf raid`, before anything was written.

    The row below is that measured shape, with the composition of a real Mythic
    roster. It is the whole of the regression: against the previous code it does
    not fail an assertion, it raises `KeyError` inside the builder.
    """
    rows = build_reference_kill_rows(
        [
            {
                "report": {"code": "abc123", "fightID": 13},
                "duration": 533000,
                "deaths": 0,
                "tanks": 2,
                "healers": 4,
                "melee": 5,
                "ranged": 9,
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0].size == 20


def test_the_composition_is_summed_rather_than_assumed_to_be_twenty() -> None:
    """Pins the arithmetic, not the constant.

    Every Mythic row observed sums to 20, because Mythic raid size is fixed at
    20 -- so a fallback hardcoded to 20 passes the test above and is wrong for
    the reason that matters: it would not be reading the API's answer. This row
    sums to 25 instead. No board has been observed omitting `size` at a flexible
    difficulty, so this shape is chosen to discriminate between summing and
    guessing rather than to claim the API emits it.

    That `tanks + healers + melee + ranged` is the raid size is measured, not
    assumed: on the difficulty-4 board, where both are present, the sum equalled
    `size` on 50 of 50 rows with no disagreements.
    """
    rows = build_reference_kill_rows(
        [
            {
                "report": {"code": "abc123", "fightID": 13},
                "duration": 533000,
                "tanks": 2,
                "healers": 5,
                "melee": 8,
                "ranged": 10,
            }
        ]
    )
    assert rows[0].size == 25


def test_size_on_the_row_wins_over_a_composition_that_disagrees() -> None:
    """The API's own figure is the source; the composition is only a fallback.

    No row has been observed where the two disagree -- the 50 measured above all
    agreed -- so this fixture exists to say which one is authoritative rather
    than to describe a shape the board emits. Swap the preference and the
    assertion reads 25.
    """
    rows = build_reference_kill_rows(
        [
            {
                "report": {"code": "abc123", "fightID": 13},
                "size": 20,
                "duration": 533000,
                "tanks": 2,
                "healers": 5,
                "melee": 8,
                "ranged": 10,
            }
        ]
    )
    assert rows[0].size == 20


def test_a_row_missing_a_required_field_names_it() -> None:
    """A field this builder cannot do without is reported, not raised raw.

    `build_ability_taken_rows` in the neighbouring module already answers a
    malformed response with a `WclError` naming what was absent. This builder
    read `row["duration"]` bare, so a missing one escaped the command as a
    `KeyError` traceback -- which is how the `size` bug above presented, and why
    diagnosing it took a probe rather than reading one line of stderr.
    """
    with pytest.raises(WclError) as raised:
        build_reference_kill_rows(
            [{"report": {"code": "abc123", "fightID": 13}, "size": 20}]
        )
    assert "duration" in str(raised.value)
