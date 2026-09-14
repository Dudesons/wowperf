# ABOUTME: Turns a raid characterRankings row into RaidParseRow, this axis's own shape.
# ABOUTME: Covers the report guard, the field set this row refuses to carry, and row diversity.

from wowperf.adapters.wcl.raid_rankings import build_raid_parse_rows
from wowperf.domain.comparison.raid_reference import RaidParseRow

ROWS = [
    {"name": "Emberkin", "class": "Evoker", "spec": "Devastation",
     "amount": 247358.15773571, "duration": 407086, "size": 29, "bracketData": 325,
     "report": {"code": "aaaaaaaaaaaaaaaa", "fightID": 3}},
    {"name": "Stonewake", "class": "Warrior", "spec": "Arms",
     "amount": 236147.44130323, "duration": 321355, "size": 30, "bracketData": 321,
     "report": {"code": "bbbbbbbbbbbbbbbb", "fightID": 7}},
    {"name": "Bríala", "class": "Priest", "spec": "Shadow",
     "amount": 190000.0, "duration": 300000, "size": 20, "bracketData": 319},
]


def test_a_raid_row_becomes_a_row_carrying_a_rate_and_a_size() -> None:
    built = build_raid_parse_rows(ROWS)
    assert len(built) == 2
    assert built[0].character_name == "Emberkin"
    assert built[0].amount == 247358.15773571
    assert built[0].duration_seconds == 407.086
    assert built[0].size == 29
    assert built[1].size == 30


def test_a_row_with_no_report_is_dropped_because_it_cannot_be_fetched() -> None:
    assert all(row.character_name != "Bríala" for row in build_raid_parse_rows(ROWS))


def test_the_row_carries_no_keystone_level_and_no_bracket_data() -> None:
    """Measured 2026-09-14: `bracketData` reads 319 to 325 on a raid board, which
    is not a keystone level, and what it does mean is not verified. A field this
    project cannot explain is a field it does not carry."""
    assert "keystone_level" not in RaidParseRow.model_fields
    assert "bracket_data" not in RaidParseRow.model_fields
    assert "score" not in RaidParseRow.model_fields


def test_the_two_rows_differ_in_every_field_a_comparison_reads() -> None:
    built = build_raid_parse_rows(ROWS)
    assert built[0].amount != built[1].amount
    assert built[0].duration_ms != built[1].duration_ms
    assert built[0].size != built[1].size
    assert built[0].report_code != built[1].report_code
    assert built[0].fight_id != built[1].fight_id
