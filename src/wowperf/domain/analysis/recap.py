# ABOUTME: One death's recap: the last seconds as a timeline with a reconstructed health column,
# ABOUTME: the state of every saving tool at the killing blow, and how the player came back. Pure.

import math

from wowperf.domain.analysis.consumables import consumable_window_start
from wowperf.domain.analysis.defensives import RUN_UP_SECONDS
from wowperf.domain.auras import (
    EXPIRED_CO_ENDING_ABILITIES,
    PlayerAuras,
    band_holding,
    co_ending_abilities,
    last_band_end,
    resolve_aura,
    strip_instant,
)
from wowperf.domain.base import Frozen
from wowperf.domain.events import (
    CastEvent,
    DamageTakenEvent,
    Death,
    HealthSample,
    Resurrection,
)
from wowperf.domain.fight import LoadedFight
from wowperf.domain.model import Player
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


def readings_in_window(
    health_samples: tuple[HealthSample, ...], death: Death
) -> tuple[HealthSample, ...]:
    """The dying player's own health readings inside the run-up, oldest first.

    Takes the stream it reads rather than the fight that carries it, the way
    `analyse_interrupts(casts, damage_taken)` already does: nothing here is a
    claim about what kind of fight the readings came from.

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
                for sample in health_samples
                if sample.actor_id == death.actor_id and start <= sample.timestamp_ms <= end
            ),
            key=lambda sample: sample.timestamp_ms,
        )
    )


def recap_timeline(loaded: LoadedFight, death: Death) -> tuple[RecapEvent, ...]:
    """Every event of the run-up where the player was hit, shielded, healed, or acted.

    The one function here that keeps a whole fight, because it reads four of
    its streams and naming all four would be a parameter list nobody could
    read at the call site. `LoadedFight` is the whole set `build_deaths`
    reads, of which this takes four: damage taken, healing, casts and health
    samples.
    """
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
HELD = "held"
FADED = "faded"


class AbilityState(Frozen):
    """One saving tool at the moment of death.

    `seconds` means one thing per state. PRESSED, HELD and FADED: how many
    seconds before the death its owner cast it -- the three share one meaning
    because HELD and FADED are PRESSED refined by whether the aura was still up
    when the blow landed, which is a reading of the same press and not a
    different moment to count from. COOLDOWN: the upper bound left, in whole
    seconds. READY: how long it had been ready when that fell inside the
    run-up, a lower bound, else None. UNSEEN: always None. `owner_id` is None
    for the dying player's own abilities and a teammate's actor id for an
    external.

    `ability_id` is the game id this state was judged from, and None for a
    consumable: a category is a cooldown group holding several ids, and no one
    of them is the item.
    """

    name: str
    state: str
    owner_id: int | None = None
    ability_id: int | None = None
    seconds: float | None = None


def lethal_hit(
    damage_taken: tuple[DamageTakenEvent, ...], death: Death
) -> DamageTakenEvent | None:
    """The hit this death names as its killing blow, or None where the stream does not carry it.

    The one definition of "the hit that killed this player": the latest hit on
    the dying player carrying the death's own `killing_blow_id`, at or before
    the death. `killing_blow_ms` reads its moment and a progression finding
    reads its source, so both answer from the same row. A `killing_blow_id` of
    zero is the log naming no ability, and matches nothing.
    """
    if not death.killing_blow_id:
        return None
    hits = [
        hit
        for hit in damage_taken
        if hit.actor_id == death.actor_id
        and hit.ability_id == death.killing_blow_id
        and hit.timestamp_ms <= death.timestamp_ms
    ]
    return max(hits, key=lambda hit: hit.timestamp_ms) if hits else None


def killing_blow_ms(damage_taken: tuple[DamageTakenEvent, ...], death: Death) -> int | None:
    """When the blow this death names landed, or None where the stream does not carry it.

    Matched by the death's own `killing_blow_id` against the hits on the dying
    player, taking the latest at or before the death. Deliberately not "the
    last damage event before the death": a tick of something else routinely
    lands in the milliseconds between the lethal hit and the death event, and
    the two readings are different claims about which hit killed the player.

    Takes the stream it reads rather than the fight that carries it, as every
    other helper here does. None means the fetched stream holds no such hit,
    and it is an honest unknown rather than a moment to substitute for: a
    `killing_blow_id` of zero is the log naming no ability at all, and it
    matches nothing here rather than pairing the death with whatever hit the
    log also left unnamed.

    The match itself is `lethal_hit`'s; this reads only its moment.
    """
    hit = lethal_hit(damage_taken, death)
    return hit.timestamp_ms if hit is not None else None


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


def _press_state(
    auras: PlayerAuras | None,
    window: tuple[int, int] | None,
    ability_id: int | None,
    name: str,
    blow_ms: int | None,
    death_ms: int,
    pressed_ms: int,
) -> str:
    """Whether a press was still up when the blow landed, or PRESSED if unknowable.

    The moment asked about is the killing blow's, never the death's. A buff a
    player is carrying when they die is stripped *by* the death, and Warcraft
    Logs timestamps that strip 15 to 55 ms *before* the death event's own
    timestamp, so a band covering the death is structurally impossible for any
    aura a death removes -- which is every active defensive in
    `data/defensives.toml`. Asked about the death, report cW38jmwdnZfbHVL4
    fight 30 returned HELD for none of its 252 rows and FADED falsely for five
    of six. Design section 8 records that measurement.

    **The strip does not always land on the blow either.** Section 8.1 asserted
    it did, from 21 deaths on one fight; section 8.3 measured 105 deaths across
    eleven and found the strip landing 1 to 3 ms *before* the blow on two of
    them. The band then ends before the blow and the closed interval misses by
    a millisecond, which printed "over by then" over two defensives that were
    up. So a band ending at the instant the death stripped this player's auras
    counts as covering the blow: `auras.strip_instant` finds that instant and
    says why several independent auras ending together cannot be coincidence.
    The death's own moment is what anchors it, because the strip is the
    death's, and it is read after the blow rather than instead of it -- a band
    that covers the blow is HELD whatever the strip did.

    **The strip is looked for no earlier than `pressed_ms`, the *earliest*
    press in the run-up.** A band cannot end before the press that opened it,
    so no instant before that press can be the strip of a band those presses
    opened. Without the bound the search reaches back through the whole fight
    whenever the death's own removal is too small to qualify -- 1777 seconds on
    one of Task 10's 105 deaths -- and an aura whose run-up press left no band
    of its own answers from a previous use, which reads HELD on a band half an
    hour stale. That is not hypothetical: the test below fails without it.

    **The earliest press, not the latest, and the difference is the same
    conflation.** `last_band_end` may be answering for an earlier press while a
    later one landed after that band ended -- a second press inside the 15-to-55
    ms gap between the strip and the death is enough. Bounding at the later
    press would throw away the death's own strip and answer PRESSED where the
    band ended inside it, correctly HELD. `seconds` still counts from the latest
    press; only the search's floor moves.

    What the bound cannot claim is that it excludes nothing that could have been
    right: the band read may belong to a press older than the run-up. What it
    does claim exactly is that a death's own strip is within milliseconds of the
    death and so is never excluded, and that what is cut off is the older
    instants the residual describes.

    **The band must end *inside* the strip, not merely run through it.** This
    branch is reached only when no band covers the blow, so a band that spans
    the strip instant and does not cover the blow ended somewhere between the
    two: it outlived the removal and then ran out, which is the opposite of
    being stripped, and crediting it would assert the aura was up when its own
    band says it had ended. Such a band is read by its own last instant
    instead, rather than being condemned on position: a tail of three to seven
    abilities behind the strip answers PRESSED, where condemning it would
    answer FADED. Below three it answers FADED either way, so the silence this
    buys is narrow, and **a lone defensive trailing the run is the commonest
    split shape there is** -- `auras.strip_instant` measures that shape at 14 of
    188 runs. The residual is named under the strip states below.

    No state *becomes* unreachable this way: a band ending after the latest
    qualifying instant ends in one that does not qualify, or it would itself be
    the latest, so HELD was never available to it. Rows that used to read HELD
    do change, which is the point. Where the band ended *before* the strip the
    aura was already gone when the death took the rest, and that is FADED on
    position alone.

    **Where the strip does not settle it, the reading is three-way**, bounded
    by the edges of the two clusters section 8.3 measured rather than by a cut
    between them. At or below `auras.EXPIRED_CO_ENDING_ABILITIES` the band
    ended the way an expiry ends and FADED is a reading; at or above
    `auras.STRIPPED_CO_ENDING_ABILITIES` it ended the way a strip ends. Between
    them nothing measured decides, and the answer is PRESSED -- the same
    explicit unknown, reached by a fifth route. A band that was FADED on
    position under the previous reading and ends after the strip now reaches
    this count and can answer PRESSED: 24 of the 2760 defensive band ends in
    the cached tables, 0.87%.

    **The residual this leaves.** Where a death's removal really was logged
    across a gap wider than a millisecond, the tail is a strip and its members
    were up when the blow landed. Read here they answer FADED below two
    trailing abilities and PRESSED from three to seven, and only a tail of
    eight or more reads HELD -- by becoming the latest qualifying instant in
    its own right. So a small split tail is a false FADED, of the class section
    6 puts first. Nothing measured separates it from an ordinary expiry: both
    are a band ending with nothing much beside it, and the width that would
    join a tail to the run before it is the tolerance this design has refused
    throughout. Not observed in the cache -- no band there spans a qualifying
    strip and ends after it, at any window width up to 5 s -- and design
    section 3.1 records it.

    The four routes that were always there each say `pressed` rather than
    guessing: no aura table for this player, no window to clip bands to, an
    ability whose aura cannot be resolved -- which covers both an id the table
    does not carry under any name and an ability that raises no aura at all --
    and a death whose killing blow never reached the fetched stream. The damage
    stream cannot tell the unresolved cases apart; neither can this, and neither
    needs to, because they answer the same way.

    A resolved aura whose band covers neither the blow nor a strip, and ended
    as an expiry ends, is FADED. That is a reading and not an absence: the table
    lists every interval the aura was up, so a blow outside all of them is the
    table saying it was down, and softening that into a doubt would silence the
    11 correct `faded` rows section 8.3 counted.
    """
    if auras is None or window is None or ability_id is None or blow_ms is None:
        return PRESSED
    aura = resolve_aura(auras, ability_id, name)
    if aura is None:
        return PRESSED
    start_ms, end_ms = window
    if band_holding(aura, start_ms, end_ms, blow_ms):
        return HELD
    strip = strip_instant(auras, pressed_ms, death_ms)
    ended_ms = last_band_end(aura, death_ms)
    if strip is not None and ended_ms is not None:
        first_ms, last_ms = strip
        # An instant that *starts* before the press survives the search's break,
        # which stops at instant granularity. Clamping here keeps a band that
        # provably predates the press from being claimed by its first
        # millisecond -- at most the 4 ms an instant has ever spanned, but the
        # whole bound is the claim that such a band cannot be this strip's.
        if max(first_ms, pressed_ms) <= ended_ms <= last_ms:
            return HELD
        if ended_ms < first_ms:
            # The death's strip came after this band ended, so the aura was
            # already gone when it landed -- and the blow landed with it.
            return FADED
    if co_ending_abilities(auras, aura, death_ms) <= EXPIRED_CO_ENDING_ABILITIES:
        return FADED
    return PRESSED


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
    auras: PlayerAuras | None = None,
    window: tuple[int, int] | None = None,
    blow_ms: int | None = None,
) -> AbilityState:
    """Which of the six states one ability was in at the death.

    Never pressed in the fight is UNSEEN: a talent not taken looks exactly like
    a button never pressed, so it is listed and not judged. A press inside the
    run-up is PRESSED — for an external, only a press on the dying player
    (`on_target`) or with no target at all, since an untargeted cast covers an
    area or the whole group rather than aiming at one player, while a cast on
    someone else was a use, not a save. When `auras`, `window` and `blow_ms`
    are all given, a press is refined to HELD or FADED by whether the ability's
    own aura still had a band over the killing blow, or over the instant the
    death stripped that player's auras; PRESSED is what a press reads as when
    that refinement cannot be made, the explicit unknown rather than a guess.
    `death_ms` is not a substitute for a missing `blow_ms`: it locates the
    strip, and it does not answer for the blow. `_press_state` says why. With
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
            name=name,
            state=_press_state(
                auras, window, ability_id, name, blow_ms, death_ms, min(in_run_up)
            ),
            owner_id=owner_id, ability_id=ability_id,
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
    players: tuple[Player, ...],
    casts: tuple[CastEvent, ...],
    death: Death,
    defensives: Defensives,
    consumables: Consumables,
    externals: Externals,
    visible_from_ms: int,
    *,
    auras: PlayerAuras | None = None,
    window: tuple[int, int] | None = None,
    blow_ms: int | None = None,
) -> AvailabilityAt:
    """The player's own defensives, the consumables, and every teammate's externals.

    Takes the two things it reads -- who was there, and what they pressed --
    rather than the fight that carries them. A keystone run and a boss fight
    each have a roster and a cast stream, and neither of those facts is what
    this rule is about.

    A consumable category is judged only when its whole window lies inside the
    fight (`visible_from_ms`), the rule `consumables_up_at` applies: a potion
    drunk before the timer started is invisible. Externals come in roster
    order, each carrying its owner.

    `auras`, `window` and `blow_ms` reach only the dying player's own
    defensives, refining a press to HELD or FADED by whether its aura still had
    a band over the killing blow, or over the instant the death stripped that
    player's auras (`state_of`). Externals stay PRESSED
    regardless: an external's aura sits on the dying player but is resolved
    against the *caster's* ability id, and `resolve_aura` is scoped to one
    player's own `on_self` list, so a teammate's cooldown is not answerable
    this way without a second table.

    `blow_ms` is the moment `killing_blow_ms` read off the damage stream, and
    None where it found none. It is threaded in rather than derived here for
    the same reason the roster and the casts are: this rule is about who was
    there and what they pressed, and the stream that says which hit was lethal
    is a third thing its caller already holds.
    """
    by_actor = {player.actor_id: player for player in players}
    player = by_actor.get(death.actor_id)
    death_ms = death.timestamp_ms

    def presses_of(actor_id: int, ability_ids: tuple[int, ...]) -> tuple[CastEvent, ...]:
        return tuple(
            cast
            for cast in casts
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
                    auras=auras, window=window, blow_ms=blow_ms,
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
    for mate in players:
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


def return_of(
    resurrections: tuple[Resurrection, ...],
    casts: tuple[CastEvent, ...],
    death: Death,
    self_resurrections: SelfResurrections,
) -> Return:
    """Exactly one of four outcomes, in this precedence.

    Takes the two streams it reads. Neither of them is a keystone fact, and
    coming back from the dead works the same way on a boss.

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
            for revival in resurrections
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
            for cast in casts
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
