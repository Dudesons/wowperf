# ABOUTME: One death's recap: the last seconds as a timeline with a reconstructed health column,
# ABOUTME: the state of every saving tool at the death, and how the player came back. Pure.

import math

from wowperf.domain.analysis.consumables import consumable_window_start
from wowperf.domain.analysis.defensives import RUN_UP_SECONDS
from wowperf.domain.base import Frozen
from wowperf.domain.events import CastEvent, Death, HealthSample
from wowperf.domain.model import LoadedRun
from wowperf.domain.season import (
    ConsumableCategory,
    Consumables,
    Defensives,
    Externals,
    SelfResurrections,
)

HIT = "hit"
ABSORB = "absorb"
HEAL = "heal"
CAST = "cast"
KIND_ORDER = {HIT: 0, ABSORB: 1, HEAL: 2, CAST: 3}
"""Tie-break for events sharing a timestamp: what struck, what soaked it, what healed, what
the player did. The vocabulary the report maps to row classes; nothing else reads it."""


class RecapEvent(Frozen):
    """One row of the timeline, before formatting.

    `amount` is what reached health for a hit, what a shield soaked for an
    absorb, what landed for a heal, and zero for the player's own cast.
    `absorbed` on a hit is the share a shield took beside the health damage.
    `health_percent` is the reconstructed health after the event, or None
    before the first reading.

    `ability_id` is the game id of the ability named, which the page uses to
    draw its icon. Zero means the log named no ability for this row.
    """

    kind: str
    timestamp_ms: int
    ability_name: str
    ability_id: int = 0
    amount: int = 0
    absorbed: int = 0
    source_id: int | None = None
    health_percent: int | None = None
    # What the hit was worth before mitigation and absorption, and what the game
    # reduced. `mitigated` is one figure the log never attributes to a cause.
    unmitigated: int = 0
    mitigated: int = 0
    overkill: int = 0
    is_area: bool = False
    is_tick: bool = False


def health_percent(hit_points: int, max_hit_points: int) -> int | None:
    """A health figure as a share of the maximum, or None when the maximum is unusable.

    Clamped to nought and a hundred. The arithmetic between two readings can
    overshoot either end — a hit landing after the log stopped reporting, a heal
    the reconstruction double-counts — and a figure outside the range would be a
    claim the log never made.
    """
    if max_hit_points <= 0:
        return None
    return max(0, min(100, round(100 * hit_points / max_hit_points)))


def window_start(death: Death) -> int:
    """Where the run-up opens: the same constant the availability rule reads."""
    return int(death.timestamp_ms - RUN_UP_SECONDS * 1000)


def readings_in_window(loaded: LoadedRun, death: Death) -> tuple[HealthSample, ...]:
    """The dying player's own health readings inside the run-up, oldest first.

    `with_health` also consults the latest reading taken before the window
    opens, as the anchor its arithmetic starts from. That one is deliberately
    absent here: it was read at a moment the card does not draw, and plotting
    it would place a measurement outside the axis it belongs to.
    """
    start, end = window_start(death), death.timestamp_ms
    return tuple(
        sorted(
            (
                sample
                for sample in loaded.health_samples
                if sample.actor_id == death.actor_id and start <= sample.timestamp_ms <= end
            ),
            key=lambda sample: sample.timestamp_ms,
        )
    )


def recap_timeline(loaded: LoadedRun, death: Death) -> tuple[RecapEvent, ...]:
    """Every event of the run-up where the player was hit, shielded, healed, or acted."""
    start, end, actor = window_start(death), death.timestamp_ms, death.actor_id
    events: list[RecapEvent] = []
    for hit in loaded.damage_taken:
        if hit.actor_id == actor and start <= hit.timestamp_ms <= end:
            events.append(
                RecapEvent(
                    kind=HIT,
                    timestamp_ms=hit.timestamp_ms,
                    ability_name=hit.ability_name,
                    ability_id=hit.ability_id,
                    amount=hit.health_damage,
                    absorbed=hit.absorbed,
                    unmitigated=hit.amount,
                    mitigated=hit.mitigated,
                    overkill=hit.overkill,
                    is_area=hit.is_area,
                    is_tick=hit.is_tick,
                )
            )
    for heal in loaded.healing:
        if heal.actor_id == actor and start <= heal.timestamp_ms <= end:
            events.append(
                RecapEvent(
                    kind=ABSORB if heal.absorbed else HEAL,
                    timestamp_ms=heal.timestamp_ms,
                    ability_name=heal.ability_name,
                    ability_id=heal.ability_id,
                    amount=heal.amount,
                    source_id=heal.source_id,
                )
            )
    for cast in loaded.casts:
        if cast.actor_id == actor and start <= cast.timestamp_ms <= end:
            events.append(
                RecapEvent(
                    kind=CAST, timestamp_ms=cast.timestamp_ms, ability_name=cast.ability_name,
                    ability_id=cast.ability_id,
                )
            )
    events.sort(key=lambda event: (event.timestamp_ms, KIND_ORDER[event.kind]))
    samples = tuple(
        sorted(
            (sample for sample in loaded.health_samples if sample.actor_id == actor),
            key=lambda sample: sample.timestamp_ms,
        )
    )
    return with_health(tuple(events), samples, start)


def with_health(
    events: tuple[RecapEvent, ...],
    samples: tuple[HealthSample, ...],
    window_start_ms: int,
) -> tuple[RecapEvent, ...]:
    """Reconstruct health after each event between the player's own readings.

    The anchor is the latest reading at or before the window opens, or failing
    that the first reading inside it; rows before any anchor carry no value.
    Walking forward, a hit subtracts what reached health, a heal adds its
    amount capped at the sampled maximum, an absorb changes nothing because the
    shield took it, a cast changes nothing because it is there for what the
    player was doing, and a reading replaces the running value outright. When a
    reading disagrees with the arithmetic the reading wins and nothing is said:
    the drift came from an event the log did not carry, and the reading is the
    only fact available. `samples` must be sorted by time.
    """
    running: int | None = None
    maximum = 0
    pending = list(samples)
    while pending and pending[0].timestamp_ms <= window_start_ms:
        sample = pending.pop(0)
        running, maximum = sample.hit_points, sample.max_hit_points

    rows = []
    for event in events:
        while pending and pending[0].timestamp_ms <= event.timestamp_ms:
            sample = pending.pop(0)
            running, maximum = sample.hit_points, sample.max_hit_points
        if running is not None:
            if event.kind == HIT:
                running -= event.amount
            elif event.kind == HEAL:
                running = min(running + event.amount, maximum)
        percent = None if running is None else health_percent(running, maximum)
        rows.append(event.model_copy(update={"health_percent": percent}))
    return tuple(rows)


PRESSED = "pressed"
READY = "ready"
COOLDOWN = "cooldown"
UNSEEN = "unseen"


class AbilityState(Frozen):
    """One saving tool at the moment of death.

    `seconds` means one thing per state. PRESSED: how many seconds before the
    death its owner cast it. COOLDOWN: the upper bound left, in whole seconds.
    READY: how long it had been ready when that fell inside the run-up, a lower
    bound, else None. UNSEEN: always None. `owner_id` is None for the dying
    player's own abilities and a teammate's actor id for an external.

    `ability_id` is the game id this state was judged from, and None for a
    consumable: a category is a cooldown group holding several ids, and no one
    of them is the item.
    """

    name: str
    state: str
    owner_id: int | None = None
    ability_id: int | None = None
    seconds: float | None = None


class AvailabilityAt(Frozen):
    """The three groups of a death's availability column.

    `own` and `consumables` are None when the tool has nothing to say — a spec
    absent from the data file, an actor off the roster — which is not the same
    as an empty tuple, where everything was checked and listed. Externals are
    one tuple over every teammate, empty when no teammate's spec is listed.
    """

    own: tuple[AbilityState, ...] | None = None
    consumables: tuple[AbilityState, ...] | None = None
    externals: tuple[AbilityState, ...] = ()


def state_of(
    presses: tuple[CastEvent, ...],
    name: str,
    cooldown_seconds: float,
    charges: int,
    death_ms: int,
    *,
    owner_id: int | None = None,
    on_target: int | None = None,
    ability_id: int | None = None,
) -> AbilityState:
    """Which of the four states one ability was in at the death.

    Never pressed in the fight is UNSEEN: a talent not taken looks exactly like
    a button never pressed, so it is listed and not judged. A press inside the
    run-up is PRESSED — for an external, only a press on the dying player
    (`on_target`) or with no target at all, since an untargeted cast covers an
    area or the whole group rather than aiming at one player, while a cast on
    someone else was a use, not a save. With
    `charges` or more presses inside one base cooldown before the death the
    ability is on COOLDOWN, and the bound is when the oldest of those presses
    frees its charge, rounded up. Otherwise READY.

    Every figure is bounded the safe way: the log records no cooldown reset,
    charge refresh or talent reduction, so the true remaining time is at most
    the bound and the true ready moment is no later than the one computed.
    """
    if not presses:
        return AbilityState(name=name, state=UNSEEN, owner_id=owner_id, ability_id=ability_id)
    run_up_start = death_ms - RUN_UP_SECONDS * 1000
    in_run_up = [
        press.timestamp_ms
        for press in presses
        if run_up_start <= press.timestamp_ms <= death_ms
        # A cast with no target (Power Word: Barrier, Spirit Link Totem, Rallying
        # Cry) hits an area or the whole group rather than one player, so it has no
        # other player it could have been for and counts here too.
        and (on_target is None or press.target_id in (on_target, None))
    ]
    if in_run_up:
        return AbilityState(
            name=name, state=PRESSED, owner_id=owner_id, ability_id=ability_id,
            seconds=(death_ms - max(in_run_up)) / 1000,
        )
    cooldown_ms = cooldown_seconds * 1000
    recent = sorted(
        press.timestamp_ms
        for press in presses
        if death_ms - cooldown_ms <= press.timestamp_ms <= death_ms
    )
    if len(recent) >= charges:
        frees_at = recent[len(recent) - charges] + cooldown_ms
        return AbilityState(
            name=name, state=COOLDOWN, owner_id=owner_id, ability_id=ability_id,
            seconds=math.ceil((frees_at - death_ms) / 1000),
        )
    # A charge comes free when the oldest of the last `charges` presses
    # recharges. An ability pressed fewer times than it has charges was never
    # fully spent, so it was ready throughout and says nothing about since when.
    before = sorted(press.timestamp_ms for press in presses if press.timestamp_ms <= death_ms)
    ready_since = (
        before[len(before) - charges] + cooldown_ms if len(before) >= charges else None
    )
    ready_for = (
        (death_ms - ready_since) / 1000
        if ready_since is not None and ready_since >= run_up_start
        else None
    )
    return AbilityState(
        name=name, state=READY, owner_id=owner_id, ability_id=ability_id, seconds=ready_for
    )


def consumable_state(
    presses: tuple[CastEvent, ...], category: ConsumableCategory, death_ms: int
) -> AbilityState | None:
    """A consumable category's state, or None where the player never drank from it all run.

    A category nobody touched is not an opportunity missed, it is a category
    the log says nothing about: a consumable reaches the log only when it is
    drunk, so silence cannot tell a bag with one in it from a bag without.
    `analysis/consumables.py::consumables_up_at` settled this for the finding
    and its docstring records the run that settled it — every death of every
    player carried a healthstone line, "true, unarguable and worth nothing".
    The card said the opposite of the finding on the same page until this
    returned None.
    """
    state = state_of(presses, category.name, category.cooldown_seconds, 1, death_ms)
    return None if state.state == UNSEEN else state


def availability_at(
    loaded: LoadedRun,
    death: Death,
    defensives: Defensives,
    consumables: Consumables,
    externals: Externals,
    visible_from_ms: int,
) -> AvailabilityAt:
    """The player's own defensives, the consumables, and every teammate's externals.

    A consumable category is judged only when its whole window lies inside the
    fight (`visible_from_ms`), the rule `consumables_up_at` applies: a potion
    drunk before the timer started is invisible. Externals come in roster
    order, each carrying its owner.
    """
    players = {player.actor_id: player for player in loaded.run.players}
    player = players.get(death.actor_id)
    death_ms = death.timestamp_ms

    def presses_of(actor_id: int, ability_ids: tuple[int, ...]) -> tuple[CastEvent, ...]:
        return tuple(
            cast
            for cast in loaded.casts
            if cast.actor_id == actor_id and cast.ability_id in ability_ids
        )

    own = None
    if player is not None:
        known = defensives.for_spec(player.class_name, player.spec)
        if known:
            own = tuple(
                state_of(
                    presses_of(death.actor_id, (ability.ability_id,)),
                    ability.name, ability.cooldown_seconds, ability.charges, death_ms,
                    ability_id=ability.ability_id,
                )
                for ability in known
            )

    drinks = None
    survival_categories = consumables.for_survival()
    if player is not None and survival_categories:
        drinks = tuple(
            state
            for category in survival_categories
            if consumable_window_start(category, death_ms) >= visible_from_ms
            and (state := consumable_state(
                presses_of(death.actor_id, category.ability_ids), category, death_ms
            )) is not None
        )

    mates = []
    for mate in loaded.run.players:
        if mate.actor_id == death.actor_id:
            continue
        for ability in externals.for_spec(mate.class_name, mate.spec):
            mates.append(
                state_of(
                    presses_of(mate.actor_id, (ability.ability_id,)),
                    ability.name, ability.cooldown_seconds, ability.charges, death_ms,
                    owner_id=mate.actor_id, on_target=death.actor_id,
                    ability_id=ability.ability_id,
                )
            )
    return AvailabilityAt(own=own, consumables=drinks, externals=tuple(mates))


RESURRECTED = "resurrected"
SELF_RESURRECTED = "self_resurrected"
RELEASED = "released"
ABSENT = "absent"


class Return(Frozen):
    """How and when the player came back, before formatting.

    `seconds_after` is from the death to the resurrection, or for a release to
    the player's first action against another actor — the anchor the death
    cost already uses, so the two figures agree by construction.
    """

    kind: str
    seconds_after: float | None = None
    caster_id: int | None = None
    ability_name: str = ""


def return_of(loaded: LoadedRun, death: Death, self_resurrections: SelfResurrections) -> Return:
    """Exactly one of four outcomes, in this precedence.

    A resurrect event targeting the player after the death and before their
    first action names how they came back: by a teammate, or by themselves
    when the caster is the player. Failing that, a cast of a listed
    self-resurrection spell in the same window is a self-resurrection. Failing
    that, a first action means they released, and no action at all means the
    log never saw them act again. A resurrection after the first action is a
    later death's and is ignored.
    """
    death_ms = death.timestamp_ms
    back_by = (
        death_ms + death.seconds_until_next_action * 1000
        if death.seconds_until_next_action is not None
        else None
    )

    def in_window(timestamp_ms: int) -> bool:
        return timestamp_ms > death_ms and (back_by is None or timestamp_ms <= back_by)

    revivals = sorted(
        (
            revival
            for revival in loaded.resurrections
            if revival.actor_id == death.actor_id and in_window(revival.timestamp_ms)
        ),
        key=lambda revival: revival.timestamp_ms,
    )
    if revivals:
        first = revivals[0]
        return Return(
            kind=SELF_RESURRECTED if first.caster_id == death.actor_id else RESURRECTED,
            seconds_after=(first.timestamp_ms - death_ms) / 1000,
            caster_id=first.caster_id,
            ability_name=first.ability_name,
        )
    own_spells = sorted(
        (
            cast
            for cast in loaded.casts
            if cast.actor_id == death.actor_id
            and cast.ability_id in self_resurrections.ability_ids
            and in_window(cast.timestamp_ms)
        ),
        key=lambda cast: cast.timestamp_ms,
    )
    if own_spells:
        return Return(
            kind=SELF_RESURRECTED,
            seconds_after=(own_spells[0].timestamp_ms - death_ms) / 1000,
            caster_id=death.actor_id,
            ability_name=own_spells[0].ability_name,
        )
    if death.seconds_until_next_action is not None:
        return Return(kind=RELEASED, seconds_after=death.seconds_until_next_action)
    return Return(kind=ABSENT)
