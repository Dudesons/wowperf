# ABOUTME: Turns the execution leaderboard into reference kills a mechanics comparison can load.
# ABOUTME: A row with no loadable report is dropped, because it can never be fetched.

from wowperf.adapters.wcl.encounter_rankings import build_reference_kill_rows


def test_a_row_becomes_a_reference_kill() -> None:
    rows = build_reference_kill_rows(
        [
            {
                "report": {"code": "abc123", "fightID": 12},
                "difficulty": 4,
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
            {"report": {"code": "", "fightID": 13}, "difficulty": 4, "size": 20,
             "duration": 490000, "deaths": 0},
            {"report": {"code": "abc123", "fightID": 12}, "difficulty": 4, "size": 20,
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
            {"report": {"code": None, "fightID": None}, "difficulty": 4, "size": 20,
             "duration": 480000, "deaths": 0},
            {"report": {"code": "abc123", "fightID": 12}, "difficulty": 4, "size": 20,
             "duration": 500000, "deaths": 1},
        ]
    )
    assert [row.report_code for row in rows] == ["abc123"]
