# ABOUTME: The progression header and one row per attempt, in the words the page prints.
# ABOUTME: Every percentage on the page names its scale, and the header is where it is named.

from tests.domain.comparison.test_pace_night import THREE_KILLS, a_sample
from tests.domain.progression_fixtures import PHASES, a_loaded_attempt, a_loaded_series, a_series
from tests.domain.test_progression import an_attempt
from wowperf.domain.analysis.attempt_shape import VERDICT_HEADLINES, WITHHELD_ID
from wowperf.domain.comparison.pace import NO_BOSS, PaceSample
from wowperf.domain.comparison.pace_curve import BossDamage
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.progression import LoadedProgression, Progression
from wowperf.domain.report.progression_build import build_progression_report
from wowperf.domain.report.progression_frame import (
    NO_READING,
    build_attempt_rows,
    build_progression_header,
)
from wowperf.domain.report.progression_model import AttemptRow


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


def test_the_header_states_how_many_attempts_were_read_in_the_singular_and_the_plural() -> None:
    one_attempt = a_loaded_series(a_loaded_attempt(1, remaining=50.0))
    three = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0),
        a_loaded_attempt(2, remaining=40.0),
        a_loaded_attempt(3, remaining=45.0),
    )

    assert build_progression_header(one_attempt).read_line == "1 attempt read"
    assert build_progression_header(three).read_line == "3 attempts read"


def test_the_header_read_line_counts_what_was_excluded() -> None:
    progression = Progression(
        report_code="abc123",
        encounter_id=3492,
        boss_name="Emberkin",
        difficulty=5,
        size=20,
        attempts=(an_attempt(1, 50.0, 200.0),),
        discarded=(an_attempt(2, 100.0, 15.8),),
    )
    header = build_progression_header(LoadedProgression(progression=progression))

    assert header.read_line == "1 attempt read, 1 excluded as too short"


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


def test_a_killed_boss_headline_is_its_outcome() -> None:
    killed = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0),
        a_loaded_attempt(2, remaining=0.01, kill=True),
        a_loaded_attempt(3, remaining=40.0),
    )

    header = build_progression_header(killed)

    assert header.headline == "Killed on attempt 2 of 3"
    assert header.headline == header.outcome


def test_an_unkilled_boss_headline_names_its_deepest_attempt() -> None:
    survived = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0, boss_percentage=61.0),
        a_loaded_attempt(2, remaining=40.0, boss_percentage=23.4),
        a_loaded_attempt(3, remaining=45.0, boss_percentage=37.0),
        a_loaded_attempt(4, remaining=55.0, boss_percentage=48.0),
    )

    header = build_progression_header(survived)

    assert header.headline == "No kill in 4 attempts; the deepest left 23.4% boss health"
    assert header.outcome == "No kill in 4 attempts"


def test_an_unkilled_boss_headline_names_the_scale_the_series_is_on() -> None:
    """Without a boss-health reading on every attempt, the figure is encounter progress."""
    survived = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0),
        a_loaded_attempt(2, remaining=12.0),
    )

    header = build_progression_header(survived)

    assert header.headline == "No kill in 2 attempts; the deepest left 12.0% encounter progress"


def test_an_unkilled_boss_with_no_reading_has_its_outcome_for_a_headline() -> None:
    """Nothing to name a depth from: the outcome alone, never a figure invented for it."""
    unread = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0, fight_percentage=None),
        a_loaded_attempt(2, remaining=50.0, fight_percentage=None),
    )

    header = build_progression_header(unread)

    assert header.headline == "No kill in 2 attempts"


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


FROST_MAGE = Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Frost", item_level=600)
KILLING_ABILITY = "Glacial Sweep"
"""An invented ability, named by no other test, so the cell can only have read it off the death."""


def a_verdict(kind: str) -> Finding:
    """A pull's `wipe.cause`, worded the way `classify_attempt` words its title."""
    return Finding(
        id="wipe.cause",
        title=f"This attempt ended on {VERDICT_HEADLINES[kind]}",
        detail="d",
        confidence=Confidence.INFERRED,
    )


def a_withheld_verdict() -> Finding:
    return Finding(
        id=WITHHELD_ID, title="Why this attempt ended is not said", detail="d",
        confidence=Confidence.MEASURED,
    )


def first_death_at(one: LoadedEncounter, offset_ms: int) -> LoadedEncounter:
    """`one` with a single roster death at `offset_ms`, dealt by `KILLING_ABILITY`."""
    death = Death(
        player_name=FROST_MAGE.name,
        actor_id=FROST_MAGE.actor_id,
        timestamp_ms=one.encounter.start_ms + offset_ms,
        killing_blow=KILLING_ABILITY,
    )
    return one.model_copy(update={"deaths": (death,)})


def a_night_of_three() -> tuple[LoadedProgression, dict[int, tuple[Finding, ...]],
                                dict[int, PaceSample]]:
    """An execution wipe behind pace, a withheld wipe with no sample, and a kill.

    The kill is handed a sample that could not be read, the one state the
    other two leave out. Each pull also carries a finding that is no verdict,
    which a cell reading the first finding it is handed would print instead.
    """
    series = a_loaded_series(
        first_death_at(
            a_loaded_attempt(1, remaining=40.0, seconds=120.0, players=(FROST_MAGE,)), 42_000
        ),
        a_loaded_attempt(2, remaining=30.0, seconds=150.0, players=(FROST_MAGE,)),
        a_loaded_attempt(3, remaining=0.01, seconds=180.0, players=(FROST_MAGE,), kill=True),
    )
    other = Finding(id="deaths.total", title="t", detail="d", confidence=Confidence.MEASURED)
    pull_findings = {
        1: (other, a_verdict("execution")),
        2: (other, a_withheld_verdict()),
        3: (other,),
    }
    pace = {1: a_sample(80, 120), 3: PaceSample(unavailable=NO_BOSS)}
    return series, pull_findings, pace


def new_cells(rows: tuple[AttemptRow, ...]) -> list[tuple[str, str, str, str]]:
    """The four cells this table reads off a pull's findings, its sample and its deaths."""
    return [(row.verdict, row.pace, row.first_death, row.held) for row in rows]


def test_each_attempt_row_carries_its_verdict_pace_first_death_and_hold() -> None:
    series, pull_findings, pace = a_night_of_three()

    rows = build_attempt_rows(series, pull_findings=pull_findings, pace=pace)

    assert new_cells(rows) == [
        ("execution", "behind", f"Emberkin (Frost Mage), to {KILLING_ABILITY}", "1:18"),
        ("withheld", NO_READING, NO_READING, NO_READING),
        ("kill", "not compared", NO_READING, NO_READING),
    ]


def test_the_verdict_cell_names_both_in_full_and_the_other_kinds_bare() -> None:
    """"both" alone leaves a reader to ask both of what; the rollup's title says it in full."""
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=40.0),
        a_loaded_attempt(2, remaining=30.0),
        a_loaded_attempt(3, remaining=20.0),
    )

    rows = build_attempt_rows(
        series,
        pull_findings={
            1: (a_verdict("both"),), 2: (a_verdict("execution"),), 3: (a_verdict("throughput"),)
        },
    )

    assert [row.verdict for row in rows] == [
        "both execution and throughput", "execution", "throughput"
    ]


def test_the_pace_cell_reads_each_state_at_the_attempts_end() -> None:
    """On pace and ahead as well as behind, each read at the last second compared.

    The third attempt is ahead of the kills for its first hundred seconds and
    deals nothing after, so it ends behind: a cell read at any second but the
    last would print "ahead" for it.
    """
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=40.0, seconds=200.0),
        a_loaded_attempt(2, remaining=30.0, seconds=200.0),
        a_loaded_attempt(3, remaining=20.0, seconds=200.0),
    )
    fell_away = PaceSample(
        ours=BossDamage(interval_ms=1000.0, amounts=(130,) * 100 + (0,) * 100),
        references=THREE_KILLS,
    )

    rows = build_attempt_rows(
        series, pace={1: a_sample(110), 2: a_sample(130), 3: fell_away}
    )

    assert [row.pace for row in rows] == ["on pace", "ahead", "behind"]


def test_the_pace_cell_of_a_cut_reading_names_where_the_comparison_stopped() -> None:
    """The kills end at 400 s and the wipe at 430 s: its last state is the comparison's end.

    The uncut attempt beside it keeps the bare state, so a cell that appended
    the clock to every reading would fail on it.
    """
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=40.0, seconds=430.0),
        a_loaded_attempt(2, remaining=30.0, seconds=200.0),
    )

    rows = build_attempt_rows(series, pace={1: a_sample(80, 430), 2: a_sample(80)})

    assert [row.pace for row in rows] == ["behind, stopped at 6:40", "behind"]


def test_an_attempt_nobody_fetched_events_for_has_no_reading_in_any_new_cell() -> None:
    """Pulled, never drawn: no findings, no sample and no deaths reach it, so nothing is claimed."""
    drawn = a_loaded_attempt(1, remaining=60.0, deaths_after_ms=(1_000,))
    never = a_loaded_attempt(2, remaining=50.0, deaths_after_ms=(1_000,))
    series = LoadedProgression(
        progression=a_series(drawn.encounter, never.encounter), loaded=(drawn,)
    )

    rows = build_attempt_rows(
        series, pull_findings={1: (a_verdict("throughput"),)}, pace={1: a_sample(80)}
    )

    assert new_cells(rows)[0] == ("throughput", "behind", "Emberkin (Holy Paladin), to x", "3:19")
    assert new_cells(rows)[1] == (NO_READING, NO_READING, NO_READING, NO_READING)


def test_a_series_given_no_pull_findings_is_not_compared() -> None:
    series, _, _ = a_night_of_three()

    assert build_progression_report(series, (), "2026-10-01 09:00").compared is False


def test_a_series_given_pace_samples_is_compared() -> None:
    series, pull_findings, pace = a_night_of_three()

    report = build_progression_report(
        series, (), "2026-10-01 09:00", pull_findings=pull_findings, pace=pace
    )

    assert report.compared is True
    assert new_cells(report.attempts)[0][:2] == ("execution", "behind")


def test_a_series_handed_an_empty_pace_mapping_is_not_compared() -> None:
    """A `--no-compare` night hands no sample at all: an empty mapping compares nothing."""
    series, pull_findings, _ = a_night_of_three()

    report = build_progression_report(
        series, (), "2026-10-01 09:00", pull_findings=pull_findings, pace={}
    )

    assert report.compared is False
