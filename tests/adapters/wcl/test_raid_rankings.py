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


def test_a_raid_row_becomes_a_row_carrying_a_rate() -> None:
    # `class_name`, `spec` and `character_name` are asserted on both rows, not
    # only the first: `ROWS` gives each row its own distinct triple (Evoker /
    # Devastation / Emberkin against Warrior / Arms / Stonewake), so a builder
    # that misread one field for another -- `row["spec"]` into `class_name`, say
    # -- would still produce a type-correct `RaidParseRow` unless both rows are
    # checked against their own literals here.
    built = build_raid_parse_rows(ROWS)
    assert len(built) == 2
    assert built[0].character_name == "Emberkin"
    assert built[0].class_name == "Evoker"
    assert built[0].spec == "Devastation"
    assert built[0].amount == 247358.15773571
    assert built[0].duration_seconds == 407.086
    assert built[1].character_name == "Stonewake"
    assert built[1].class_name == "Warrior"
    assert built[1].spec == "Arms"
    assert built[1].spec == "Arms"


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
    assert built[0].class_name != built[1].class_name
    assert built[0].report_code != built[1].report_code
    assert built[0].fight_id != built[1].fight_id


def test_a_mythic_row_carrying_no_size_still_builds() -> None:
    """The character board omits `size` where the difficulty fixes the raid size.

    Measured 2026-09-18 against encounter 3470 at difficulty 5: none of the 100
    rows carried `size`, and none carried the role counts the execution board
    falls back on either. Reading `row["size"]` here crashed `wowperf raid` on
    every Mythic boss fight, one board further along than the execution board
    did. Against the previous code this raises `KeyError` inside the builder
    rather than failing an assertion.

    The row is otherwise the measured shape, including the `hardModeLevel` and
    absent `guild` that real rows carry and this builder ignores.
    """
    built = build_raid_parse_rows(
        [
            {"name": "Emberkin", "class": "DeathKnight", "spec": "Blood",
             "amount": 129284.9969043, "duration": 452240, "bracketData": 325,
             "hardModeLevel": 0,
             "report": {"code": "aaaaaaaaaaaaaaaa", "fightID": 13}},
        ]
    )
    assert len(built) == 1
    assert built[0].character_name == "Emberkin"
    assert built[0].spec == "Blood"


def test_the_row_carries_no_raid_size() -> None:
    """Nothing reads it, and on half the boards the API does not supply it.

    `cli.py` records the decision this rests on: the parse boards are
    deliberately not filtered by raid size, because our own raid's references
    ran 11 to 30 and a size filter would empty most samples. So the field was
    carried and never read -- and a field nobody reads is what took the command
    down on every Mythic fight. The same rule as `bracketData` above: a field
    this project does not use is a field it does not carry.
    """
    assert "size" not in RaidParseRow.model_fields
