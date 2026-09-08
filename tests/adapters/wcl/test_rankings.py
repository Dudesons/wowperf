# ABOUTME: Behaviour tests for translating leaderboard rows and asserting the bracket rule.
# ABOUTME: Fixtures use the real row shape, captured from the live API on 2026-09-04.

import pytest

from wowperf.adapters.wcl.errors import BracketMismatch, WclError
from wowperf.adapters.wcl.rankings import (
    assert_bracket,
    bracket_for,
    build_parse_rows,
    build_speed_rows,
    rankings_block,
)

SPEED_ROW = {
    "server": {"id": None, "name": None, "region": ""},
    "duration": 1379452,
    "startTime": 1787940898991,
    "report": {"code": "71cv4MRdNCp8ZFjG", "fightID": 28, "startTime": 1787925567733},
    "damageTaken": 216419014,
    "deaths": 0,
    "tanks": 1,
    "healers": 1,
    "melee": 2,
    "ranged": 1,
    "bracketData": 16,
    "affixes": [9, 10, 147],
    "team": [
        {"id": 1, "name": "Dzonamvp", "class": "DeathKnight", "spec": "Frost", "role": "DPS"},
        {"id": 2, "name": "Uglydraenor", "class": "Warrior", "spec": "Protection", "role": "Tank"},
    ],
    "medal": "silver",
    "score": 435.557578125,
    "leaderboard": 0,
}

PARSE_ROW = {
    "name": "Bríala",
    "class": "Mage",
    "spec": "Arcane",
    "amount": -319999564.8270117,
    "hardModeLevel": 16,
    "duration": 1399143,
    "startTime": 1787850271519,
    "report": {"code": "37FzMg9pVPH6fnJT", "fightID": 16, "startTime": 1787833995139},
    "guild": {"id": 575362, "name": "Mental Apocalypse", "faction": 1},
    "server": {"id": 283, "name": "Draenor", "region": "EU"},
    "bracketData": 16,
    "faction": 0,
    "affixes": [9, 10, 147],
    "medal": "silver",
    "score": 435.17298828125,
    "leaderboard": 0,
}


def test_the_bracket_is_one_below_the_keystone_level() -> None:
    assert bracket_for(16) == 15


def test_a_rankings_error_is_raised_rather_than_read_as_rows() -> None:
    payload = {
        "worldData": {
            "encounter": {
                "id": 12825,
                "name": "Den of Nalorakk",
                "fightRankings": {"error": "Invalid difficulty setting or size specified."},
            }
        }
    }
    with pytest.raises(WclError, match="Invalid difficulty setting"):
        rankings_block(payload)


def test_a_missing_encounter_is_raised_rather_than_subscripted() -> None:
    with pytest.raises(WclError, match="no encounter"):
        rankings_block({"worldData": {"encounter": None}})


def test_a_healthy_payload_yields_the_rankings_object() -> None:
    payload = {
        "worldData": {
            "encounter": {
                "id": 12825,
                "name": "Den of Nalorakk",
                "characterRankings": {"page": 1, "hasMorePages": True, "rankings": [PARSE_ROW]},
            }
        }
    }
    block = rankings_block(payload)
    assert block["page"] == 1
    assert block["rankings"] == [PARSE_ROW]


def test_the_bracket_assertion_passes_when_the_convention_holds() -> None:
    assert_bracket([SPEED_ROW], keystone_level=16)


def test_the_bracket_assertion_fails_loudly_when_it_does_not() -> None:
    with pytest.raises(BracketMismatch, match="16"):
        assert_bracket([SPEED_ROW], keystone_level=17)


def test_rows_without_bracket_data_do_not_trip_the_assertion() -> None:
    assert_bracket([{"duration": 1}], keystone_level=16)


def test_a_speed_row_becomes_the_domains_own_shape() -> None:
    row = build_speed_rows([SPEED_ROW])[0]
    assert row.report_code == "71cv4MRdNCp8ZFjG"
    assert row.fight_id == 28
    assert row.keystone_level == 16
    assert row.duration_ms == 1379452
    assert row.deaths == 0
    assert row.affix_ids == (9, 10, 147)
    assert row.medal == "silver"
    assert row.team == ("DeathKnight Frost", "Warrior Protection")


def test_a_parse_row_becomes_the_domains_own_shape() -> None:
    row = build_parse_rows([PARSE_ROW])[0]
    assert row.report_code == "37FzMg9pVPH6fnJT"
    assert row.fight_id == 16
    assert row.keystone_level == 16
    assert row.character_name == "Bríala"
    assert row.class_name == "Mage"
    assert row.spec == "Arcane"
    assert row.score == pytest.approx(435.17298828125)


def test_a_row_with_no_report_is_skipped_rather_than_half_built() -> None:
    orphan = dict(SPEED_ROW)
    orphan["report"] = None
    assert build_speed_rows([orphan, SPEED_ROW]) == build_speed_rows([SPEED_ROW])
