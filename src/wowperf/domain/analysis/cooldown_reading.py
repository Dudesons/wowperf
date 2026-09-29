# ABOUTME: Where one holder's cooldown stood at a moment: pressed, ready, out of reach, not judged.
# ABOUTME: One rule for every surface that asks, so two parts of a page cannot disagree on a press.

from collections.abc import Sequence
from enum import StrEnum

from wowperf.domain.analysis.throughput import ready_at
from wowperf.domain.base import Frozen
from wowperf.domain.events import CastEvent, Death, Resurrection
from wowperf.domain.season import CooldownAbility


class Reading(StrEnum):
    """What the log shows of one cooldown at one moment. Never "on cooldown": talents shorten
    some cooldowns, so a press within the base cooldown is stated as the press it was."""

    UNSEEN = "unseen"
    PRESSED = "pressed"
    DEAD = "dead"
    READY = "ready"
    WITHIN = "within"
    NOT_JUDGED = "unjudged"


class CooldownReading(Frozen):
    """One reading, and the press it rests on: the latest press in the window for PRESSED,
    the latest press inside the base cooldown for WITHIN, None otherwise."""

    reading: Reading
    press_ms: int | None = None


def dead_at(
    actor_id: int,
    at_ms: int,
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
) -> bool:
    """Dead at `at_ms`: died before it, with no resurrection and no cast since.

    A cast is a sign of life as good as a resurrection record, and the only
    one a player who released and ran back leaves: the log records no return.
    """
    before = [death.timestamp_ms for death in deaths if death.actor_id == actor_id]
    before = [when for when in before if when < at_ms]
    if not before:
        return False
    died = max(before)
    revived = any(
        one.actor_id == actor_id and died < one.timestamp_ms <= at_ms for one in resurrections
    )
    acted = any(one.actor_id == actor_id and died < one.timestamp_ms <= at_ms for one in casts)
    return not (revived or acted)


def read_cooldown(
    ability: CooldownAbility,
    actor_id: int,
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
    *,
    pressed_from_ms: int,
    judged_at_ms: int,
    pressed_until_ms: int,
    visible_from_ms: int,
) -> CooldownReading:
    """Where `ability`, held by `actor_id`, stood at `judged_at_ms`.

    UNSEEN when it was never pressed in the log read: whether it was talented
    cannot be told. PRESSED when a press falls in `[pressed_from_ms,
    pressed_until_ms]`, whatever its target. DEAD when its holder was dead at
    `judged_at_ms`. READY only where `ready_at()` says so. WITHIN when a press
    falls inside the base cooldown before `judged_at_ms`; NOT_JUDGED when none
    does but the base cooldown reaches back before `visible_from_ms`, where a
    press would be invisible.
    """
    own = [
        cast.timestamp_ms
        for cast in casts
        if cast.actor_id == actor_id and cast.ability_id == ability.ability_id
    ]
    if not own:
        return CooldownReading(reading=Reading.UNSEEN)
    pressed = [when for when in own if pressed_from_ms <= when <= pressed_until_ms]
    if pressed:
        return CooldownReading(reading=Reading.PRESSED, press_ms=max(pressed))
    if dead_at(actor_id, judged_at_ms, casts, deaths, resurrections):
        return CooldownReading(reading=Reading.DEAD)
    if ready_at(tuple(casts), (ability,), actor_id, judged_at_ms, visible_from_ms):
        return CooldownReading(reading=Reading.READY)
    cooldown_ms = ability.cooldown_seconds * 1000
    recent = [when for when in own if judged_at_ms - cooldown_ms <= when <= judged_at_ms]
    if recent:
        return CooldownReading(reading=Reading.WITHIN, press_ms=max(recent))
    return CooldownReading(reading=Reading.NOT_JUDGED)
