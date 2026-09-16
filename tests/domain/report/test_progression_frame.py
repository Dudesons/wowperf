# ABOUTME: The progression header and one row per attempt, in the words the page prints.
# ABOUTME: Every percentage on the page names its scale, and the header is where it is named.

from tests.domain.progression_fixtures import PHASES, a_loaded_attempt, a_loaded_series, a_series
from tests.domain.test_progression import an_attempt
from wowperf.domain.progression import LoadedProgression, Progression
from wowperf.domain.report.progression_frame import build_attempt_rows, build_progression_header


def test_the_header_names_the_scale_the_page_is_on() -> None:
    """Boss health and encounter progress diverge 3 to 8 points, so the page says which."""
    on_boss_health = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0, boss_percentage=30.0),
        a_loaded_attempt(2, remaining=60.0, boss_percentage=40.0),
    )
    assert build_progression_header(on_boss_health).depth_label == "boss health"

    on_progress = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0),
        a_loaded_attempt(2, remaining=60.0),
    )
    assert build_progression_header(on_progress).depth_label == "encounter progress"


def test_the_header_counts_what_was_excluded() -> None:
    progression = Progression(
        report_code="abc123",
        encounter_id=3492,
        boss_name="Emberkin",
        difficulty=5,
        size=20,
        attempts=(an_attempt(1, 50.0, 200.0),),
        discarded=(an_attempt(2, 100.0, 15.8), an_attempt(3, 100.0, 17.1)),
    )
    header = build_progression_header(LoadedProgression(progression=progression))

    assert header.attempts_counted == 1
    assert header.attempts_discarded == 2
    assert header.difficulty == "Mythic"
    assert header.size == 20


def test_the_header_says_which_attempt_killed_it() -> None:
    killed = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0),
        a_loaded_attempt(2, remaining=0.01, kill=True),
    )
    assert build_progression_header(killed).outcome == "Killed on attempt 2 of 2"

    survived = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0),
        a_loaded_attempt(2, remaining=40.0),
    )
    assert build_progression_header(survived).outcome == "No kill in 2 attempts"


def test_a_row_per_attempt_in_pull_order_marks_the_deepest() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0, seconds=204.0, deaths_after_ms=(1_000, 2_000)),
        a_loaded_attempt(2, remaining=16.5, seconds=480.0, deaths_after_ms=(1_000,)),
        a_loaded_attempt(3, remaining=55.0, seconds=227.0),
    )

    rows = build_attempt_rows(series)

    assert [row.index for row in rows] == [1, 2, 3]
    assert [row.fight_id for row in rows] == [1, 2, 3]
    assert [row.is_best for row in rows] == [False, True, False]
    assert rows[0].depth == "60.0%"
    assert rows[1].duration == "8:00"
    assert rows[0].deaths == "2"


def test_an_attempt_with_no_reading_prints_no_figure() -> None:
    """A dash, never a zero: a zero here would read as a kill."""
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0),
        a_loaded_attempt(2, remaining=50.0, fight_percentage=None),
    )

    rows = build_attempt_rows(series)

    assert rows[0].depth == "60.0%"
    assert rows[1].depth == "—"


def test_an_attempt_nobody_deepened_prints_no_death_count() -> None:
    one = a_loaded_attempt(1, remaining=60.0, deaths_after_ms=(1_000,))
    two = a_loaded_attempt(2, remaining=50.0, deaths_after_ms=(1_000, 2_000))
    series = LoadedProgression(
        progression=a_series(one.encounter, two.encounter), loaded=(one,)
    )

    rows = build_attempt_rows(series)

    assert rows[0].deaths == "1"
    assert rows[1].deaths == "—"


def test_the_phase_column_is_empty_where_the_api_says_phases_do_not_separate_wipes() -> None:
    gated = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0, last_phase=3),
        a_loaded_attempt(2, remaining=50.0, last_phase=1),
        separates_wipes=False,
    )
    assert [row.phase for row in build_attempt_rows(gated)] == ["", ""]

    open_gate = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0, last_phase=3),
        a_loaded_attempt(2, remaining=50.0, last_phase=1),
        separates_wipes=True,
    )
    assert [row.phase for row in build_attempt_rows(open_gate)] == [
        "The Drowning",
        "The Gathering",
    ]
    assert PHASES[2].name == "The Drowning"


def test_a_discarded_attempt_gets_no_row() -> None:
    """It takes no part in any figure the series reports, so a row for it would
    invite a comparison against figures it was excluded from."""
    progression = Progression(
        report_code="abc123",
        encounter_id=3492,
        boss_name="Emberkin",
        difficulty=5,
        size=20,
        attempts=(an_attempt(1, 50.0, 200.0),),
        discarded=(an_attempt(2, 100.0, 15.8),),
    )

    rows = build_attempt_rows(LoadedProgression(progression=progression))

    assert [row.fight_id for row in rows] == [1]
