# ABOUTME: The wipe call: which roster death loses a wipe, and which kills read as dirty.
# ABOUTME: Boundaries at three and four deaths, ties, pets, and a player who dies twice.

from wowperf.domain.analysis.wipe_call import (
    CALL_ORDINAL,
    WIPE_CALL_DEATHS,
    deaths_after,
    is_dirty,
    lost_at,
)
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.model import Player

ROSTER = (
    Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Frost", item_level=700),
    Player(actor_id=2, name="Stonewake", class_name="Warrior", spec="Protection", item_level=700),
    Player(actor_id=3, name="Bríala", class_name="Priest", spec="Holy", item_level=700),
    Player(actor_id=4, name="Кириллица", class_name="Rogue", spec="Subtlety", item_level=700),
)
PET = 99
"""An actor on no roster: a pet or an unidentified actor whose death the log still lists."""

START_MS = 10_000


def a_pull(*, kill: bool, deaths: tuple[tuple[int, int], ...]) -> LoadedEncounter:
    """A pull of `ROSTER`; each death is (actor id, seconds into the pull)."""
    names = {player.actor_id: player.name for player in ROSTER}
    encounter = Encounter(
        report_code="abc123", fight_id=7, encounter_id=3470, boss_name="Emberkin",
        difficulty=5, partition=1, size=20, kill=kill, start_ms=START_MS, end_ms=250_000,
        players=ROSTER,
    )
    return LoadedEncounter(
        encounter=encounter,
        deaths=tuple(
            Death(player_name=names.get(actor, "Stonewake"), actor_id=actor,
                  timestamp_ms=START_MS + seconds * 1_000, killing_blow="Ravenous Feast")
            for actor, seconds in deaths
        ),
    )


def test_the_call_is_four_deaths_named_the_fourth() -> None:
    assert WIPE_CALL_DEATHS == 4
    assert CALL_ORDINAL == "4th"


def test_three_roster_deaths_do_not_lose_a_wipe() -> None:
    assert lost_at(a_pull(kill=False, deaths=((1, 30), (2, 40), (3, 60)))) is None


def test_the_fourth_roster_death_in_time_order_loses_a_wipe() -> None:
    # Listed out of order, as a stream may list them: the call is the fourth by time.
    loaded = a_pull(kill=False, deaths=((4, 90), (1, 30), (2, 40), (1, 120), (3, 60)))

    lost = lost_at(loaded)

    assert lost is not None
    assert (lost.actor_id, lost.timestamp_ms) == (4, START_MS + 90_000)


def test_a_tie_breaks_on_the_lowest_actor_id() -> None:
    # Bríala (3) and Кириллица (4) die in the same millisecond: 3 is third, 4 is the call.
    loaded = a_pull(kill=False, deaths=((1, 30), (2, 40), (4, 60), (3, 60)))

    lost = lost_at(loaded)

    assert lost is not None
    assert lost.actor_id == 4


def test_a_death_off_the_roster_never_counts() -> None:
    three_and_a_pet = ((1, 30), (2, 40), (PET, 50), (3, 60))
    assert lost_at(a_pull(kill=False, deaths=three_and_a_pet)) is None

    lost = lost_at(a_pull(kill=False, deaths=(*three_and_a_pet, (4, 70))))
    assert lost is not None
    assert lost.actor_id == 4


def test_a_player_who_dies_twice_counts_twice() -> None:
    # Emberkin dies, is battle-rezzed, and dies again: two of the four.
    loaded = a_pull(kill=False, deaths=((1, 30), (1, 50), (2, 60), (3, 70)))

    lost = lost_at(loaded)

    assert lost is not None
    assert (lost.actor_id, lost.timestamp_ms) == (3, START_MS + 70_000)


def test_a_kill_is_never_lost_and_is_dirty_from_four_deaths() -> None:
    four = a_pull(kill=True, deaths=((1, 30), (2, 40), (3, 60), (4, 70)))
    three = a_pull(kill=True, deaths=((1, 30), (2, 40), (3, 60)))

    assert lost_at(four) is None
    assert is_dirty(four) is True
    assert is_dirty(three) is False


def test_a_pets_death_does_not_make_a_kill_dirty() -> None:
    assert is_dirty(a_pull(kill=True, deaths=((1, 30), (2, 40), (3, 60), (PET, 70)))) is False


def test_a_wipe_is_never_dirty() -> None:
    wipe = a_pull(kill=False, deaths=((1, 30), (2, 40), (3, 60), (4, 70), (1, 80)))
    assert is_dirty(wipe) is False


def test_deaths_after_the_call_count_every_actor_strictly_after_it() -> None:
    # The call is Кириллица at 60 s. A pet at 61 s and Emberkin again at 70 s follow it;
    # Stonewake in the call's own millisecond with a lower actor id does not.
    loaded = a_pull(
        kill=False,
        deaths=((1, 30), (2, 60), (3, 50), (4, 60), (PET, 61), (1, 70)),
    )
    lost = lost_at(loaded)
    assert lost is not None
    assert lost.actor_id == 4

    after = deaths_after(loaded.deaths, lost)

    assert sorted((one.actor_id, one.timestamp_ms - START_MS) for one in after) == [
        (1, 70_000), (PET, 61_000),
    ]
