# ABOUTME: Ingest tests for the phase fields, against response shapes measured 2026-09-16.
# ABOUTME: The fixtures copy the live shape, including the nulls a real report returns.

from typing import Any

from wowperf.adapters.wcl.ingest import build_encounter, build_phases


def a_report(**overrides: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "code": "abc123",
        "owner": {"name": "Emberkin"},
        "phases": [
            {
                "encounterID": 3492,
                "separatesWipes": True,
                "phases": [
                    {"id": 1, "name": "Stage One", "isIntermission": False},
                    {"id": 2, "name": "Stage Two", "isIntermission": False},
                    {"id": 3, "name": "Intermission", "isIntermission": True},
                ],
            },
            {"encounterID": 3445, "separatesWipes": False, "phases": [
                {"id": 1, "name": "Stage One", "isIntermission": False},
            ]},
        ],
        "masterData": {"actors": []},
    }
    report.update(overrides)
    return report


def a_fight(**overrides: Any) -> dict[str, Any]:
    fight: dict[str, Any] = {
        "id": 30,
        "name": "Emberkin",
        "encounterID": 3492,
        "difficulty": 5,
        "size": 20,
        "kill": False,
        "fightPercentage": 16.49,
        "bossPercentage": 23.15,
        "lastPhase": 3,
        "lastPhaseIsIntermission": False,
        "phaseTransitions": [
            {"id": 1, "startTime": 9518.2},
            {"id": 2, "startTime": 9682.4},
            {"id": 3, "startTime": 9827.7},
        ],
        "startTime": 0,
        "endTime": 480_000,
        "friendlyPlayers": [],
    }
    fight.update(overrides)
    return fight


def test_an_encounter_carries_both_percentages_from_the_response() -> None:
    encounter = build_encounter(a_report(), a_fight(), partition=1)

    assert encounter.fight_percentage == 16.49
    assert encounter.boss_percentage == 23.15


def test_transitions_are_truncated_to_whole_milliseconds() -> None:
    """The API reports a Float; truncating never reports a transition as later.

    The third transition's fractional part is 0.7: rounding would read 9828,
    so this fails if truncation is ever replaced by `round()`.
    """
    encounter = build_encounter(a_report(), a_fight(), partition=1)

    assert [(t.id, t.start_ms) for t in encounter.phase_transitions] == [
        (1, 9518),
        (2, 9682),
        (3, 9827),
    ]


def test_a_boss_with_no_phases_reads_as_no_phases_rather_than_an_error() -> None:
    """Two of eight bosses measured on 2026-09-16 looked exactly like this."""
    encounter = build_encounter(
        a_report(),
        a_fight(lastPhase=0, phaseTransitions=[]),
        partition=1,
    )

    assert encounter.last_phase == 0
    assert encounter.phase_transitions == ()


def test_a_response_silent_about_a_field_reads_as_absent() -> None:
    fight = a_fight()
    del fight["bossPercentage"]
    del fight["lastPhase"]

    encounter = build_encounter(a_report(), fight, partition=1)

    assert encounter.boss_percentage is None
    assert encounter.last_phase is None


def test_phases_are_matched_to_the_encounter_asked_for() -> None:
    phases, separates = build_phases(a_report(), 3492)

    assert [p.name for p in phases] == ["Stage One", "Stage Two", "Intermission"]
    assert [p.is_intermission for p in phases] == [False, False, True]
    assert separates is True


def test_a_different_encounter_gets_its_own_answer() -> None:
    """separatesWipes varies by encounter: measured true, true, false in one report."""
    phases, separates = build_phases(a_report(), 3445)

    assert [p.name for p in phases] == ["Stage One"]
    assert separates is False


def test_an_encounter_the_report_lists_no_phases_for_gets_none() -> None:
    phases, separates = build_phases(a_report(), 9999)

    assert phases == ()
    assert separates is False


def test_a_report_with_no_phases_key_at_all_gets_none() -> None:
    phases, separates = build_phases(a_report(phases=None), 3492)

    assert phases == ()
    assert separates is False
