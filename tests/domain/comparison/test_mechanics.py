# ABOUTME: The mechanics comparison: which references it draws, and what it states.
# ABOUTME: Size is matched, not annotated, because the rate is over a whole raid.

from wowperf.domain.comparison.mechanics import ReferenceKillRow, select_reference_kills
from wowperf.domain.comparison.sample import SAMPLE_SIZE


def kill(code: str, size: int, difficulty: int = 4) -> ReferenceKillRow:
    return ReferenceKillRow(
        report_code=code, fight_id=1, difficulty=difficulty, size=size,
        duration_ms=480000, deaths=0,
    )


def test_only_references_of_our_own_size_are_drawn() -> None:
    rows = (kill("a", 20), kill("b", 30), kill("c", 20), kill("d", 14))
    drawn = select_reference_kills(rows, our_size=20, our_difficulty=4)
    assert [row.report_code for row in drawn] == ["a", "c"]


def test_a_reference_at_another_difficulty_is_refused() -> None:
    # Difficulty is matched exactly, never approximated: a Heroic pull against
    # Mythic references is meaningless, and design 13 refuses it rather than
    # annotating it.
    rows = (kill("a", 20, difficulty=5), kill("b", 20, difficulty=4))
    drawn = select_reference_kills(rows, our_size=20, our_difficulty=4)
    assert [row.report_code for row in drawn] == ["b"]


def test_no_more_than_the_sample_size_is_drawn() -> None:
    rows = tuple(kill(str(index), 20) for index in range(SAMPLE_SIZE + 3))
    drawn = select_reference_kills(rows, our_size=20, our_difficulty=4)
    assert len(drawn) == SAMPLE_SIZE
