# ABOUTME: Layer 3's claims: what the deepest attempt of a night did differently.
# ABOUTME: Internal comparison only -- no reference run, and never a named player.

from tests.domain.progression_fixtures import a_loaded_attempt, a_loaded_series, a_series
from wowperf.domain.analysis.progression_best import best_deaths, roster_deaths
from wowperf.domain.findings import Confidence
from wowperf.domain.progression import LoadedProgression


def test_a_deaths_count_ignores_an_actor_who_is_not_on_the_roster() -> None:
    """A pet or an unidentified actor dying is not a roster player's death.

    The same filter `_first_death_ms` applies, for the same reason: three
    analysers must agree about which deaths count.
    """
    one = a_loaded_attempt(3, deaths_after_ms=(1_000, 2_000, 3_000))

    # `a_loaded_attempt` deals every death to actor id 1 when no roster is
    # given, and `_DEFAULT_PLAYER` is that one actor, so all three count.
    assert roster_deaths(one) == 3

    orphan = a_loaded_attempt(4, deaths_after_ms=(1_000,))
    stripped = orphan.model_copy(
        update={"encounter": orphan.encounter.model_copy(update={"players": ()})}
    )
    assert roster_deaths(stripped) == 0


def test_the_best_attempt_taking_fewer_deaths_is_stated_with_both_figures() -> None:
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(1_000, 2_000))
    others = [
        a_loaded_attempt(2, remaining=60.0, deaths_after_ms=tuple(range(1_000, 10_000, 1_000))),
        a_loaded_attempt(3, remaining=70.0, deaths_after_ms=tuple(range(1_000, 10_000, 1_000))),
        a_loaded_attempt(4, remaining=80.0, deaths_after_ms=tuple(range(1_000, 12_000, 1_000))),
    ]

    finding = best_deaths(a_loaded_series(deepest, *others))

    assert finding is not None
    assert finding.id == "progression.best.deaths"
    # Two deaths on the deepest attempt, a median of 9 across the other three.
    assert "2" in finding.title
    assert "9" in finding.title
    assert finding.confidence is Confidence.MEASURED
    assert "wowperf raid abc123 --fight 1" in finding.detail


def test_the_best_attempt_taking_more_deaths_is_said_rather_than_hidden() -> None:
    """The best attempt is not always the cleanest, and that is worth reading.

    A finding that only speaks when the deepest attempt looks good is a finding
    that flatters the night rather than measuring it.
    """
    deepest = a_loaded_attempt(
        1, remaining=10.0, deaths_after_ms=tuple(range(1_000, 9_000, 1_000))
    )
    others = [
        a_loaded_attempt(2, remaining=60.0, deaths_after_ms=(1_000, 2_000)),
        a_loaded_attempt(3, remaining=70.0, deaths_after_ms=(1_000, 2_000)),
    ]

    finding = best_deaths(a_loaded_series(deepest, *others))

    assert finding is not None
    assert "8" in finding.title
    assert "2" in finding.title
    assert "more" in finding.title.lower()


def test_an_equal_count_is_reported_as_no_difference() -> None:
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(1_000, 2_000))
    others = [
        a_loaded_attempt(2, remaining=60.0, deaths_after_ms=(1_000, 2_000)),
        a_loaded_attempt(3, remaining=70.0, deaths_after_ms=(1_000, 2_000)),
    ]

    finding = best_deaths(a_loaded_series(deepest, *others))

    assert finding is not None
    assert "no difference" in finding.title.lower()


def test_the_count_is_stated_as_deaths_rather_than_players_lost() -> None:
    """A battle rez makes one player die twice, so this count outruns the roster.

    Measured 2026-09-16: a twenty-player night's deepest attempt logged 21
    roster deaths, and the title said it had lost 21 players. Here every death
    lands on `_DEFAULT_PLAYER`, a roster of one, so three deaths against a
    one-player raid reproduce that impossibility in miniature -- the title has
    to name deaths, and a title phrased as players lost fails both halves
    below.
    """
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(1_000, 2_000, 3_000))
    others = [
        a_loaded_attempt(2, remaining=60.0, deaths_after_ms=(1_000,)),
        a_loaded_attempt(3, remaining=70.0, deaths_after_ms=(1_000,)),
    ]

    finding = best_deaths(a_loaded_series(deepest, *others))

    assert finding is not None
    assert len(deepest.players) == 1, "the point of this fixture is more deaths than players"
    assert "3 roster deaths" in finding.title
    assert "players" not in finding.title


def test_one_other_attempt_is_not_a_comparison() -> None:
    """A median of one figure is that figure, and a claim drawn from it reads
    exactly as confident as one drawn from fifty."""
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(1_000,))
    other = a_loaded_attempt(2, remaining=60.0, deaths_after_ms=(1_000, 2_000, 3_000))

    assert best_deaths(a_loaded_series(deepest, other)) is None


def test_nothing_deepened_says_nothing() -> None:
    empty = LoadedProgression(progression=a_series(), loaded=())
    assert best_deaths(empty) is None

