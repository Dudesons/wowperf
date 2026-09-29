# ABOUTME: Where one holder's cooldown stood at a moment, read the one way every surface reads it.
# ABOUTME: Pins each reading on a clock whose origin is not zero, so an origin slip cannot pass.

from wowperf.domain.analysis.cooldown_reading import (
    CooldownReading,
    Reading,
    dead_at,
    read_cooldown,
)
from wowperf.domain.events import CastEvent, Death, Resurrection
from wowperf.domain.season import CooldownAbility

ORIGIN = 3_000_000
"""The log's first second, far from zero: real timestamps are report-relative."""

TRANQUILITY = CooldownAbility(
    ability_id=740, name="Tranquility", cooldown_seconds=180.0, group=True
)
DRUID = 1


def at(second: float) -> int:
    return ORIGIN + int(second * 1000)


def press(second: float, actor_id: int = DRUID, ability_id: int = 740) -> CastEvent:
    return CastEvent(
        actor_id=actor_id, ability_id=ability_id, ability_name="Tranquility",
        timestamp_ms=at(second),
    )


def reading_at(
    second: float,
    casts: list[CastEvent],
    *,
    deaths: tuple[Death, ...] = (),
    resurrections: tuple[Resurrection, ...] = (),
    visible_from_ms: int = ORIGIN,
) -> CooldownReading:
    """Judged at `second`, pressed-window the ten seconds before it -- a death card's run-up."""
    return read_cooldown(
        TRANQUILITY, DRUID, casts, deaths, resurrections,
        pressed_from_ms=at(second - 10), judged_at_ms=at(second - 10),
        pressed_until_ms=at(second), visible_from_ms=visible_from_ms,
    )


def test_a_cooldown_never_pressed_in_the_log_is_unseen() -> None:
    other = press(50, ability_id=132158)
    assert reading_at(300, [other]) == CooldownReading(reading=Reading.UNSEEN)


def test_a_press_inside_the_window_is_pressed_and_carries_the_latest_press() -> None:
    assert reading_at(300, [press(293), press(296)]) == CooldownReading(
        reading=Reading.PRESSED, press_ms=at(296)
    )


def test_a_press_one_millisecond_before_the_window_is_not_pressed() -> None:
    before = CastEvent(
        actor_id=DRUID, ability_id=740, ability_name="Tranquility", timestamp_ms=at(290) - 1
    )
    assert reading_at(300, [before]).reading is Reading.WITHIN


def test_ready_only_where_ready_at_says_so() -> None:
    assert reading_at(300, [press(20)]) == CooldownReading(reading=Reading.READY)


def test_a_press_inside_the_base_cooldown_is_within_and_carries_that_press() -> None:
    assert reading_at(300, [press(20), press(200)]) == CooldownReading(
        reading=Reading.WITHIN, press_ms=at(200)
    )


def test_a_press_before_the_visible_origin_is_within_and_keeps_its_timestamp() -> None:
    pre_pull = press(-15)
    reading = reading_at(100, [pre_pull])
    assert reading == CooldownReading(reading=Reading.WITHIN, press_ms=at(-15))


def test_a_base_cooldown_reaching_before_the_log_is_not_judged() -> None:
    assert reading_at(100, [press(250)]) == CooldownReading(reading=Reading.NOT_JUDGED)


def test_the_visible_origin_is_what_decides_not_judged() -> None:
    later_origin = at(60)
    assert reading_at(200, [press(250)], visible_from_ms=later_origin).reading is (
        Reading.NOT_JUDGED
    )
    assert reading_at(200, [press(250)]).reading is Reading.READY


def test_a_holder_dead_at_the_judged_moment_reads_dead() -> None:
    died = Death(player_name="Emberkin", actor_id=DRUID, timestamp_ms=at(250),
                 killing_blow="Venom Bolt")
    assert reading_at(300, [press(20)], deaths=(died,)) == CooldownReading(reading=Reading.DEAD)


def test_a_press_in_the_window_outranks_a_death() -> None:
    died = Death(player_name="Emberkin", actor_id=DRUID, timestamp_ms=at(250),
                 killing_blow="Venom Bolt")
    assert reading_at(300, [press(20), press(295)], deaths=(died,)).reading is Reading.PRESSED


def test_dead_until_a_resurrection_or_a_cast_says_otherwise() -> None:
    died = Death(player_name="Emberkin", actor_id=DRUID, timestamp_ms=at(100),
                 killing_blow="Venom Bolt")
    back = Resurrection(actor_id=DRUID, caster_id=2, ability_id=20484, ability_name="Rebirth",
                        timestamp_ms=at(120))
    acted = press(130, ability_id=774)
    assert dead_at(DRUID, at(150), [], [died], []) is True
    assert dead_at(DRUID, at(150), [], [died], [back]) is False
    assert dead_at(DRUID, at(150), [acted], [died], []) is False
    assert dead_at(DRUID, at(90), [], [died], []) is False
