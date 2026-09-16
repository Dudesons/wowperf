# ABOUTME: Layer 3's claims: what the deepest attempt of a night did differently.
# ABOUTME: Internal comparison only -- no reference run, and never a named player.

from tests.domain.progression_fixtures import a_loaded_attempt, a_loaded_series, a_series
from wowperf.domain.analysis.progression_best import (
    MAX_SURVIVORS,
    best_deaths,
    best_survived,
    roster_deaths,
)
from wowperf.domain.findings import Confidence
from wowperf.domain.model import Player
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


ROSTER = (
    Player(actor_id=1, name="Emberkin", class_name="Paladin", spec="Holy", item_level=600),
    Player(actor_id=2, name="Stonewake", class_name="Warrior", spec="Protection", item_level=600),
    Player(actor_id=3, name="Bríala", class_name="Mage", spec="Frost", item_level=600),
)


def test_a_specialisation_that_stopped_dying_on_the_best_attempt_is_named() -> None:
    """The deepest attempt's roster is the control: who died everywhere else and not there."""
    # `a_loaded_attempt` deals deaths round-robin over `players`, so one death
    # reaches actor 1 (Holy Paladin), two reach actors 1 and 2, and so on.
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(1_000,), players=ROSTER)
    others = [
        a_loaded_attempt(n, remaining=60.0, deaths_after_ms=(1_000, 2_000), players=ROSTER)
        for n in (2, 3, 4)
    ]

    finding = best_survived(a_loaded_series(deepest, *others))

    assert finding is not None
    assert finding.id == "progression.best.survived"
    assert "Protection Warrior" in finding.detail
    # Holy Paladin died on every attempt including the deepest, so it is not named.
    assert "Holy Paladin" not in finding.detail
    # Frost Mage died on none of them, so it never stopped dying.
    assert "Frost Mage" not in finding.detail
    assert finding.confidence is Confidence.DERIVED
    assert "wowperf raid abc123 --fight 1" in finding.detail


def test_no_real_player_name_reaches_the_finding() -> None:
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(1_000,), players=ROSTER)
    others = [
        a_loaded_attempt(n, remaining=60.0, deaths_after_ms=(1_000, 2_000), players=ROSTER)
        for n in (2, 3, 4)
    ]

    finding = best_survived(a_loaded_series(deepest, *others))

    assert finding is not None
    printed = finding.title + finding.detail + " ".join(finding.evidence)
    for player in ROSTER:
        assert player.name not in printed


def test_a_specialisation_absent_from_the_best_attempts_roster_is_not_a_survivor() -> None:
    """A swap out is not a survival, and the log cannot tell the two apart by itself."""
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(), players=ROSTER[:1])
    others = [
        a_loaded_attempt(n, remaining=60.0, deaths_after_ms=(1_000, 2_000), players=ROSTER)
        for n in (2, 3, 4)
    ]

    finding = best_survived(a_loaded_series(deepest, *others))

    # Protection Warrior died in all three others but was not on the deepest
    # attempt's roster at all, so there is nothing to name. Holy Paladin was
    # there and died in all three others, so it is what the finding reports --
    # this asserts the roster guard, not silence.
    assert finding is not None
    assert "Protection Warrior" not in finding.detail
    assert "Holy Paladin" in finding.detail


def test_a_specialisation_dying_in_half_the_others_is_not_enough() -> None:
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(), players=ROSTER)
    others = [
        a_loaded_attempt(2, remaining=60.0, deaths_after_ms=(1_000,), players=ROSTER),
        a_loaded_attempt(3, remaining=70.0, deaths_after_ms=(), players=ROSTER),
    ]

    # Holy Paladin died in 1 of 2 others: exactly half, which is not "usually".
    assert best_survived(a_loaded_series(deepest, *others)) is None


def test_one_other_attempt_is_not_a_comparison_for_survivors_either() -> None:
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(), players=ROSTER)
    other = a_loaded_attempt(2, remaining=60.0, deaths_after_ms=(1_000,), players=ROSTER)

    assert best_survived(a_loaded_series(deepest, other)) is None


SANCTIONED_NAMES = ("Emberkin", "Stonewake", "Bríala", "Кириллица")
"""CLAUDE.md's whole permitted set. Nothing below reads a name -- `best_survived`
labels a player by spec and class alone -- so these repeat around a roster longer
than four rather than inventing a fifth."""

SPECS = (
    ("Paladin", "Holy"),
    ("Warrior", "Protection"),
    ("Mage", "Frost"),
    ("Priest", "Discipline"),
    ("Druid", "Balance"),
    ("Rogue", "Outlaw"),
)
"""Six distinct specialisations, one more than `MAX_SURVIVORS`."""


def a_roster(size: int) -> tuple[Player, ...]:
    """`size` players, every one a different specialisation."""
    return tuple(
        Player(
            actor_id=index + 1,
            name=SANCTIONED_NAMES[index % len(SANCTIONED_NAMES)],
            class_name=class_name,
            spec=spec,
            item_level=600,
        )
        for index, (class_name, spec) in enumerate(SPECS[:size])
    )


def _everyone_came_through(size: int) -> LoadedProgression:
    """A night where `size` specialisations died in every other attempt and in none
    of the deepest one, so every one of them qualifies.

    Deaths are dealt round-robin over the roster, so one death per player in
    each of the three others puts every specialisation at 3 of 3 -- past the
    "more than half" bar -- while the deepest attempt lost nobody.
    """
    roster = a_roster(size)
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(), players=roster)
    round_robin = tuple(1_000 * (n + 1) for n in range(size))
    others = [
        a_loaded_attempt(n, remaining=60.0, deaths_after_ms=round_robin, players=roster)
        for n in (2, 3, 4)
    ]
    return a_loaded_series(deepest, *others)


def test_a_night_most_of_the_raid_came_through_is_withheld_rather_than_trimmed() -> None:
    """`MAX_SURVIVORS`'s own docstring: at six this stops being a difference and
    starts being the roster.

    Trimming to the top five would print a list that reads as the whole
    difference while the condition that makes it meaningless -- that nearly
    everyone came through -- goes unsaid. Silence is the honest answer, and
    this fails the moment the cap goes back to slicing.
    """
    series = _everyone_came_through(MAX_SURVIVORS + 1)

    assert best_survived(series) is None


def test_the_cap_names_every_survivor_up_to_its_own_limit() -> None:
    """The other side of the same cap, without which withholding everything passes.

    At exactly `MAX_SURVIVORS` the finding still speaks, and it names all of
    them rather than a sample: a cap that trimmed here would print fewer
    evidence lines than there are qualifying specialisations.
    """
    series = _everyone_came_through(MAX_SURVIVORS)

    finding = best_survived(series)

    assert finding is not None
    assert finding.title.startswith(f"{MAX_SURVIVORS} specialisations")
    assert len(finding.evidence) == MAX_SURVIVORS
    for class_name, spec in SPECS[:MAX_SURVIVORS]:
        assert f"{spec} {class_name}" in finding.detail
