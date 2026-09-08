# ABOUTME: Behaviour tests for the reference-run value objects and the comparability rule.
# ABOUTME: The rule is what stops the tool printing a duration across a keystone-level gap.

from wowperf.domain.comparison.reference import (
    MAX_LEVEL_GAP,
    Comparability,
    ParseRow,
    SpeedRow,
)


def a_speed_row(level: int = 16) -> SpeedRow:
    return SpeedRow(
        report_code="71cv4MRdNCp8ZFjG",
        fight_id=28,
        keystone_level=level,
        duration_ms=1_379_452,
        deaths=0,
        affix_ids=(9, 10, 147),
        score=435.5,
        medal="silver",
        team=("Warrior Protection", "Evoker Preservation", "Rogue Subtlety"),
    )


def test_a_speed_row_reports_the_leaderboards_own_duration_in_seconds() -> None:
    assert a_speed_row().duration_seconds == 1379.452


def test_a_parse_row_names_the_character_it_belongs_to() -> None:
    row = ParseRow(
        report_code="37FzMg9pVPH6fnJT",
        fight_id=16,
        keystone_level=16,
        duration_ms=1_399_143,
        character_name="Bríala",
        class_name="Mage",
        spec="Arcane",
        affix_ids=(9, 10, 147),
        score=435.17,
        medal="silver",
    )
    assert row.character_name == "Bríala"
    assert row.duration_seconds == 1399.143


def test_matching_levels_leave_durations_comparable() -> None:
    rule = Comparability(our_level=16, their_level=16)
    assert rule.level_gap == 0
    assert rule.durations_comparable is True


def test_a_higher_reference_key_withholds_durations_and_says_why() -> None:
    rule = Comparability(our_level=16, their_level=17)
    assert rule.level_gap == 1
    assert rule.durations_comparable is False
    reason = rule.withheld_because()
    assert "+17" in reason
    assert "+16" in reason
    assert "health" in reason.lower()


def test_a_lower_reference_key_withholds_durations_too() -> None:
    rule = Comparability(our_level=16, their_level=15)
    assert rule.level_gap == -1
    assert rule.durations_comparable is False


def test_the_accepted_gap_is_one_level() -> None:
    assert MAX_LEVEL_GAP == 1
