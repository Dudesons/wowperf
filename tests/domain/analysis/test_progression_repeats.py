# ABOUTME: Behaviour tests for the phase a night's attempts most often ended in.
# ABOUTME: Every guard -- separatesWipes, an empty phase table, phase zero -- gets its own case.

from tests.domain.progression_fixtures import a_loaded_attempt, a_loaded_series
from tests.domain.progression_fixtures import a_series as series
from tests.domain.test_progression import an_attempt
from wowperf.domain.analysis.progression_repeats import (
    collapse,
    collapse_seconds,
    repeat_first_death,
    repeat_phase,
)
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import Player
from wowperf.domain.progression import LoadedProgression


def attempt(fight_id: int, *, last_phase: int | None = None) -> Encounter:
    """One qualifying attempt, 200 seconds long, at a stated ending phase."""
    return an_attempt(fight_id, 50.0, 200.0, last_phase=last_phase)


def test_names_the_phase_most_attempts_ended_in() -> None:
    finding = repeat_phase(
        series(
            attempt(1, last_phase=2),
            attempt(2, last_phase=2),
            attempt(3, last_phase=3),
        )
    )
    assert finding is not None
    assert "Intermission: Tide" in finding.title
    assert "2 of 3" in finding.title
    assert finding.confidence is Confidence.MEASURED


def test_is_silent_when_the_api_says_phases_do_not_separate_wipes() -> None:
    assert (
        repeat_phase(
            series(attempt(1, last_phase=2), attempt(2, last_phase=2), separates_wipes=False)
        )
        is None
    )


def test_is_silent_when_the_boss_has_no_phase_table() -> None:
    finding = repeat_phase(
        series(attempt(1, last_phase=2), attempt(2, last_phase=2), phases=())
    )
    assert finding is None


def test_treats_phase_zero_as_a_boss_without_phases_not_a_reading() -> None:
    assert repeat_phase(series(attempt(1, last_phase=0), attempt(2, last_phase=0))) is None


def test_is_silent_below_two_attempts_with_a_phase() -> None:
    assert repeat_phase(series(attempt(1, last_phase=2), attempt(2, last_phase=None))) is None


def test_names_an_unmatched_phase_id_by_number_rather_than_inventing_one() -> None:
    finding = repeat_phase(series(attempt(1, last_phase=9), attempt(2, last_phase=9)))
    assert finding is not None
    assert "phase 9" in finding.title


def test_says_nothing_about_failure() -> None:
    finding = repeat_phase(series(attempt(1, last_phase=3), attempt(2, last_phase=3)))
    assert finding is not None
    text = f"{finding.title} {finding.detail}".lower()
    for banned in ("fail", "failed", "missed", "mistake", "wrong"):
        assert banned not in text


def test_collapse_seconds_is_first_death_to_the_end_of_the_attempt() -> None:
    one = a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(70_000, 90_000))
    assert collapse_seconds(one) == 30.0


def test_collapse_seconds_is_none_without_a_death() -> None:
    assert collapse_seconds(a_loaded_attempt(1, seconds=100.0, deaths_after_ms=())) is None


def test_collapse_reports_a_median_and_a_range_never_a_mean() -> None:
    finding = collapse(a_loaded_series(
        a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(90_000,)),   # 10.0s
        a_loaded_attempt(2, seconds=100.0, deaths_after_ms=(80_000,)),   # 20.0s
        a_loaded_attempt(3, seconds=100.0, deaths_after_ms=(10_000,)),   # 90.0s
    ))
    assert finding is not None
    assert "20" in finding.title              # the median, not the 40.0 mean
    assert "40" not in finding.title
    assert "10" in " ".join(finding.evidence)
    assert "90" in " ".join(finding.evidence)


def test_collapse_is_withheld_below_two_attempts_with_a_death() -> None:
    assert collapse(a_loaded_series(
        a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(90_000,)),
        a_loaded_attempt(2, seconds=100.0, deaths_after_ms=()),
    )) is None


def test_collapse_counts_only_attempts_that_had_one() -> None:
    finding = collapse(a_loaded_series(
        a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(90_000,)),
        a_loaded_attempt(2, seconds=100.0, deaths_after_ms=(80_000,)),
        a_loaded_attempt(3, seconds=100.0, deaths_after_ms=()),
    ))
    assert finding is not None
    assert "2 attempts" in finding.detail


# --- progression.repeat.first_death ---

# A fixed two-player roster: `Frost DeathKnight` carries the lower actor id,
# so a tied pair of deaths resolves to it under the "lowest actor id" rule.
# `class_name` is unspaced -- `subType` off the live API, measured 2026-09-16.
ROSTER: tuple[Player, ...] = (
    Player(actor_id=1, name="Emberkin", class_name="DeathKnight", spec="Frost", item_level=600),
    Player(actor_id=2, name="Stonewake", class_name="Shaman", spec="Elemental", item_level=600),
)


def series_of(*loaded: LoadedEncounter) -> LoadedProgression:
    return a_loaded_series(*loaded)


def loaded_attempt_with_roster(fight_id: int, *, first_dead_index: int | None) -> LoadedEncounter:
    """One deepened attempt against `ROSTER`.

    `first_dead_index` names which roster member's death carries the earliest
    timestamp. `None` means the earliest death belongs to an actor absent
    from the roster entirely -- a pet or an unidentified actor, not a raider.
    """
    encounter = an_attempt(fight_id, 50.0, 200.0, players=ROSTER)
    start = encounter.start_ms
    deaths: tuple[Death, ...]
    if first_dead_index is None:
        deaths = (
            Death(
                player_name="Unidentified", actor_id=999, timestamp_ms=start + 1_000,
                killing_blow="x",
            ),
        )
    else:
        other_index = 1 - first_dead_index
        deaths = (
            Death(
                player_name=ROSTER[first_dead_index].name,
                actor_id=ROSTER[first_dead_index].actor_id,
                timestamp_ms=start + 1_000,
                killing_blow="x",
            ),
            Death(
                player_name=ROSTER[other_index].name,
                actor_id=ROSTER[other_index].actor_id,
                timestamp_ms=start + 5_000,
                killing_blow="x",
            ),
        )
    return LoadedEncounter(encounter=encounter, deaths=deaths)


def tied_attempt(fight_id: int, *, order: str) -> LoadedEncounter:
    """Two `ROSTER` deaths at the same instant, arriving in the order named.

    Both deaths share a timestamp, so a deterministic pick can only come from
    the actor-id tiebreak, never from which death the stream happened to list
    first.
    """
    encounter = an_attempt(fight_id, 50.0, 200.0, players=ROSTER)
    start = encounter.start_ms
    low = Death(
        player_name=ROSTER[0].name, actor_id=ROSTER[0].actor_id,
        timestamp_ms=start + 1_000, killing_blow="x",
    )
    high = Death(
        player_name=ROSTER[1].name, actor_id=ROSTER[1].actor_id,
        timestamp_ms=start + 1_000, killing_blow="x",
    )
    deaths = (low, high) if order == "forwards" else (high, low)
    return LoadedEncounter(encounter=encounter, deaths=deaths)


def test_counts_the_specialisation_that_died_first_most_often() -> None:
    finding = repeat_first_death(series_of(
        loaded_attempt_with_roster(1, first_dead_index=0),
        loaded_attempt_with_roster(2, first_dead_index=0),
        loaded_attempt_with_roster(3, first_dead_index=1),
    ))
    assert finding is not None
    assert "Frost DeathKnight" in finding.title
    assert "2 of 3" in finding.title
    assert finding.confidence is Confidence.MEASURED


def test_never_prints_a_player_name() -> None:
    finding = repeat_first_death(series_of(
        loaded_attempt_with_roster(1, first_dead_index=0),
        loaded_attempt_with_roster(2, first_dead_index=0),
    ))
    assert finding is not None
    text = f"{finding.title} {finding.detail} {' '.join(finding.evidence)}"
    for name in ("Emberkin", "Stonewake", "Bríala", "Кириллица"):
        assert name not in text


def test_a_death_with_no_roster_row_contributes_nothing() -> None:
    assert repeat_first_death(series_of(
        loaded_attempt_with_roster(1, first_dead_index=None),
        loaded_attempt_with_roster(2, first_dead_index=None),
    )) is None


def test_is_withheld_below_two_identified_not_just_at_zero() -> None:
    """Exactly one attempt's earliest death matches the roster, the other does not.

    `test_a_death_with_no_roster_row_contributes_nothing` only exercises the
    zero-identified case, which a guard of `if not specs` also satisfies. The
    requirement is "below two", so one identified attempt must withhold too --
    this is the boundary that guard would get wrong while still passing that
    other test.
    """
    assert repeat_first_death(series_of(
        loaded_attempt_with_roster(1, first_dead_index=0),
        loaded_attempt_with_roster(2, first_dead_index=None),
    )) is None


def test_ties_resolve_by_actor_id_not_by_stream_order() -> None:
    forwards = repeat_first_death(series_of(
        tied_attempt(1, order="forwards"), tied_attempt(2, order="forwards"),
    ))
    backwards = repeat_first_death(series_of(
        tied_attempt(1, order="backwards"), tied_attempt(2, order="backwards"),
    ))
    assert forwards is not None and backwards is not None
    assert forwards.title == backwards.title
    # Not just deterministic -- specifically the lower actor id (Frost
    # DeathKnight, id 1) wins the tie, per the requirement, in either direction.
    assert "Frost DeathKnight" in forwards.title
    assert "Frost DeathKnight" in backwards.title


def test_disclaims_blame_rather_than_naming_a_mistake() -> None:
    """The detail must read as a count, not an accusation.

    The design forbids naming a mechanic, or a person, as at fault -- this is
    the finding most easily misread that way, so both halves of the required
    framing (where the role stands, not who was playing it) are required
    parts of the text, not merely an absence of loaded words.
    """
    finding = repeat_first_death(series_of(
        loaded_attempt_with_roster(1, first_dead_index=0),
        loaded_attempt_with_roster(2, first_dead_index=0),
    ))
    assert finding is not None
    assert "about where that role stands" in finding.detail
    assert "not about the player" in finding.detail
    text = f"{finding.title} {finding.detail}".lower()
    for banned in ("fail", "failed", "missed", "mistake", "wrong", "fault"):
        assert banned not in text
