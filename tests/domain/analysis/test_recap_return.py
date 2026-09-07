# ABOUTME: How a dead player came back: a teammate's resurrection, their own, a release, or not
# ABOUTME: at all. A resurrection after the first action belongs to a later death and is ignored.

from tests.domain.analysis.test_recap_timeline import a_cast, loaded
from wowperf.domain.analysis.recap import (
    ABSENT,
    RELEASED,
    RESURRECTED,
    SELF_RESURRECTED,
    return_of,
)
from wowperf.domain.events import Death, Resurrection
from wowperf.domain.season import SelfResurrections

REINCARNATION = SelfResurrections(ability_ids=(20608,))


def dead(at_ms: int = 60_000, back_after: float | None = None) -> Death:
    return Death(player_name="Dudesons", actor_id=1, timestamp_ms=at_ms, killing_blow="x",
                 pull_index=0, seconds_until_next_action=back_after)


def raised(at_ms: int, caster_id: int = 3, actor_id: int = 1) -> Resurrection:
    return Resurrection(actor_id=actor_id, caster_id=caster_id, ability_id=61999,
                        ability_name="Raise Ally", timestamp_ms=at_ms)


def test_a_teammates_resurrection_before_the_first_action_wins() -> None:
    back = return_of(loaded(resurrections=(raised(68_000),)), dead(back_after=12.0), REINCARNATION)
    assert (back.kind, back.seconds_after, back.caster_id, back.ability_name) == (
        RESURRECTED, 8.0, 3, "Raise Ally"
    )


def test_a_resurrection_event_by_the_player_themselves_is_a_self_resurrection() -> None:
    back = return_of(loaded(resurrections=(raised(65_000, caster_id=1),)), dead(back_after=9.0),
                     SelfResurrections())
    assert (back.kind, back.seconds_after) == (SELF_RESURRECTED, 5.0)


def test_a_listed_spell_cast_by_the_dead_player_is_a_self_resurrection() -> None:
    cast = a_cast(66_000, ability="Reincarnation").model_copy(update={"ability_id": 20608})
    back = return_of(loaded(casts=(cast,)), dead(back_after=15.0), REINCARNATION)
    assert (back.kind, back.seconds_after, back.ability_name) == (
        SELF_RESURRECTED, 6.0, "Reincarnation"
    )


def test_no_resurrection_and_a_later_action_is_a_release() -> None:
    back = return_of(loaded(), dead(back_after=34.2), REINCARNATION)
    assert (back.kind, back.seconds_after) == (RELEASED, 34.2)


def test_no_resurrection_and_no_action_is_absent() -> None:
    assert return_of(loaded(), dead(), REINCARNATION).kind == ABSENT


def test_a_resurrection_after_the_first_action_belongs_to_a_later_death() -> None:
    back = return_of(loaded(resurrections=(raised(90_000),)), dead(back_after=12.0), REINCARNATION)
    assert back.kind == RELEASED


def test_another_players_resurrection_is_not_this_ones() -> None:
    back = return_of(loaded(resurrections=(raised(65_000, actor_id=2),)), dead(back_after=12.0),
                     REINCARNATION)
    assert back.kind == RELEASED
