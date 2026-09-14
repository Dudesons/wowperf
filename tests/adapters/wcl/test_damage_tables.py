# ABOUTME: Maps a viewBy-Target damage-done table into rows the comparison reads.
# ABOUTME: A row's kind is the API's own type; the adapter decides nothing about which is the boss.

import pytest

from wowperf.adapters.wcl.damage_tables import build_target_rows
from wowperf.adapters.wcl.errors import WclError

# F12's own measured shape (`.claude/skills/wcl-api/SKILL.md`, "A damage-done table split by
# target names the boss itself"): three entries whose `type` reads 'NPC', 'Boss', 'NPC', with
# `total` 144629000, 498963668 and 111365043. Keys are drawn only from the sixteen the skill
# verified for this table -- carrying one this project has not verified would be lying about
# what was measured.
PAYLOAD = {
    "reportData": {
        "report": {
            "targets": {
                "data": {
                    "entries": [
                        {
                            "id": 100,
                            "guid": 90001,
                            "name": "Writhing Ichorling",
                            "type": "NPC",
                            "total": 144629000,
                        },
                        {
                            "id": 57,
                            "guid": 90002,
                            "name": "The Hollow King",
                            "type": "Boss",
                            "total": 498963668,
                        },
                        {
                            "id": 101,
                            "guid": 90003,
                            "name": "Hollow Attendant",
                            "type": "NPC",
                            "total": 111365043,
                        },
                    ]
                }
            }
        }
    }
}


def test_the_boss_is_named_by_the_api_not_by_a_rule_this_project_wrote() -> None:
    rows = build_target_rows(PAYLOAD, "targets")
    assert [row.kind for row in rows] == ["NPC", "Boss", "NPC"]
    assert [row.is_boss for row in rows] == [False, True, False]


def test_the_rows_carry_the_measured_totals_in_order() -> None:
    rows = build_target_rows(PAYLOAD, "targets")
    assert [row.total for row in rows] == [144629000, 498963668, 111365043]


def test_a_missing_total_or_name_reads_as_zero_or_empty_rather_than_raising() -> None:
    payload = {
        "reportData": {
            "report": {"targets": {"data": {"entries": [{"id": 202, "type": "NPC"}]}}}
        }
    }
    rows = build_target_rows(payload, "targets")
    assert rows[0].total == 0
    assert rows[0].name == ""


def test_an_absent_selection_raises_naming_the_alias() -> None:
    # No `targets` key at all -- the alias the caller asked for was never in the
    # response, distinct from having been asked for and coming back null.
    with pytest.raises(WclError, match="`targets`"):
        build_target_rows({"reportData": {"report": {}}}, "targets")


def test_a_null_selection_raises_the_same_as_an_absent_one() -> None:
    # A selection that failed server-side comes back as `null`, not as a missing
    # key. Reading past it silently would report "no damage done" for a fight the
    # query never actually asked about successfully.
    with pytest.raises(WclError, match="`targets`"):
        build_target_rows({"reportData": {"report": {"targets": None}}}, "targets")
