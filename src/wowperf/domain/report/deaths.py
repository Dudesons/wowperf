# ABOUTME: One recap card per death: what killed the player, what was up, how they came back.
# ABOUTME: States what was pressed and what was ready, never what should have been pressed.

from wowperf.domain.analysis.recap import (
    ABSENT,
    ABSORB,
    CAST,
    COOLDOWN,
    FADED,
    HEAL,
    HELD,
    HIT,
    PRESSED,
    READY,
    RELEASED,
    RESURRECTED,
    SELF_RESURRECTED,
    UNSEEN,
    AbilityState,
    RecapEvent,
    availability_at,
    killing_blow_ms,
    readings_in_window,
    recap_timeline,
    return_of,
    window_start,
)
from wowperf.domain.analysis.roster import display_names
from wowperf.domain.auras import PlayerAuras, band_holding, resolve_aura
from wowperf.domain.events import Death
from wowperf.domain.fight import LoadedFight
from wowperf.domain.findings import Confidence
from wowperf.domain.report.frame import badge_for, format_seconds, plural
from wowperf.domain.report.health_curve import PRECISION, build_health_curve, curve_x
from wowperf.domain.report.model import (
    AvailabilityGroup,
    AvailabilityRow,
    Badge,
    DeathCard,
    RecapRow,
    Tooltip,
)
from wowperf.domain.report.tooltip import (
    absorb_tooltip,
    caster_name,
    heal_tooltip,
    hit_tooltip,
    press_tooltip,
    run_ability_tooltip,
)
from wowperf.domain.season import Consumables, Defensives, Externals, SelfResurrections


def _when(death: Death, start_ms: int, has_pulls: bool) -> str:
    """Elapsed time since the fight's start, never the absolute report timestamp.

    Clamped to zero so a death logged before the first pull — or a run with
    no pulls at all, where the run's start is taken as zero — reads as the
    start of the run rather than as a negative time.

    Takes the origin rather than the fight it came from: a keystone run reads
    it off its first pull and a boss fight off its own start, and this only
    subtracts.

    `has_pulls` is the fight's own answer to whether it is cut into pulls, and
    it is what the trailing phrase depends on. A fight with pulls names the one
    a death fell in, or says it fell between them. A fight with none is one
    continuous window: there is nothing to be between, so the elapsed time
    stands alone rather than carrying a phrase about a division this fight does
    not have. Read as a value, so a card never asks which kind of fight it was
    handed.
    """
    elapsed = max(death.timestamp_ms - start_ms, 0) / 1000
    at = format_seconds(elapsed)
    assert at is not None  # a float input always formats to a string
    if not has_pulls:
        return at
    if death.pull_index is None:
        return f"{at}, between pulls"
    return f"{at}, pull {death.pull_index}"


CONSUMABLE_CAVEAT = (
    "The log shows only what was drunk, so this says nothing was on cooldown, "
    "not that one was carried."
)
"""Printed under the consumable rows, qualifying every "ready" among them.

It sits on the card rather than in the ledger because that is where a reader
draws the conclusion, and the honest sentence has to be next to the claim it
qualifies rather than several screens below it.
"""


HEALTH_METHOD = (
    "Health on a death card is reconstructed: the log states a player's health only on their "
    "own casts, so between readings each hit is subtracted and each heal added, and the next "
    "reading replaces the running value. The curve's line and the recap's health column are "
    "badged derived for that reason, and the dots on the curve are the readings themselves."
)

NO_HEALTH_READING = (
    "The log carries no health reading for this player before the death, so this card "
    "draws no health curve and the health column of its recap is empty."
)

NO_TIMELINE_EVENT = "No event in the last seconds."

TRIMMED_CARD_NOTE = (
    "This card is trimmed: the timeline and health curve were not built for this pull. "
    "Re-run with --deep <fight> to render them."
)
"""Why a card has no timeline, when the reason is us rather than the log.

`NO_TIMELINE_EVENT` says the log recorded nothing in the window. This says the
run declined to build it. They look the same on the page and mean opposite
things, and a reader who takes this one for that concludes the pull was quiet.
"""

NO_TEAMMATE_EXTERNALS = "No teammate's specialisation has externals listed."

NO_CONSUMABLE_DATA = (
    "No consumable can be judged here: either none is listed for this run, or the death came "
    "too early for the log to show one's cooldown."
)


def _press_band(
    event: RecapEvent, death: Death, auras: PlayerAuras | None
) -> tuple[int, int] | None:
    """When this press's buff was up, in milliseconds, clipped to the card's window.

    The band containing the press, not the ability's whole history: the row
    describes one cast, and an earlier band of the same buff belongs to an
    earlier one. None where no aura table was fetched, where the table
    recorded no band for this ability, or where the press's own band does not
    reach into the run-up the card draws.

    The single source for both of the row's answers about the press -- the
    rectangle `_cover_of` places on the health curve, and the figures
    `press_tooltip` reports beside it -- so the drawing and the panel
    explaining it can never resolve different bands.
    """
    if auras is None or event.kind != CAST:
        return None
    aura = resolve_aura(auras, event.ability_id, event.ability_name)
    if aura is None:
        return None
    return band_holding(aura, window_start(death), death.timestamp_ms, event.timestamp_ms)


def _cover_of(
    band: tuple[int, int] | None, death: Death
) -> tuple[float | None, float | None]:
    """A press's band in the curve's coordinate space, or two Nones where there is none."""
    if band is None:
        return (None, None)
    start_x = curve_x(band[0], death)
    return (start_x, round(curve_x(band[1], death) - start_x, PRECISION))


def _recap_row(
    event: RecapEvent, death: Death, names: dict[int, str], marker_id: str, has_curve: bool,
    auras: PlayerAuras | None, events: tuple[RecapEvent, ...],
) -> RecapRow:
    """One row of the recap table.

    `events` is every row of the same run-up, which a press reads to sum what
    arrived while its buff was up. A row that is not a press ignores it.
    """
    if event.kind == HIT:
        detail = f"{event.amount:,} to health"
        if event.absorbed:
            detail += f", {event.absorbed:,} absorbed"
    elif event.kind == ABSORB:
        detail = f"{event.amount:,} soaked"
    elif event.kind == HEAL:
        detail = f"+{event.amount:,} from {caster_name(event.source_id, names)}"
    else:
        detail = ""
    if event.kind == HIT:
        tooltip = hit_tooltip(event)
    elif event.kind == HEAL:
        tooltip = heal_tooltip(event, names)
    elif event.kind == ABSORB:
        tooltip = absorb_tooltip(event, names)
    else:
        tooltip = None
    band = _press_band(event, death, auras)
    if band is not None:
        tooltip = press_tooltip(band, death.timestamp_ms, events)
    cover_x, cover_width = _cover_of(band, death)
    return RecapRow(
        seconds_before=f"{(death.timestamp_ms - event.timestamp_ms) / 1000:.1f} s",
        kind=event.kind,
        ability=event.ability_name,
        detail=detail,
        health="" if event.health_percent is None else f"{event.health_percent}%",
        health_percent=event.health_percent,
        ability_id=event.ability_id or None,
        tooltip=tooltip,
        marker_id=marker_id,
        # `curve_x` does not clamp its input to the run-up window: it trusts
        # that `recap_timeline` already filtered events to
        # [window_start(death), death.timestamp_ms] before any of them reached
        # this row. The two modules agree only because both read the same
        # window; a caller that handed an unfiltered event to a row builder
        # would get back an x that falls outside the plot it is drawn on.
        marker_x=curve_x(event.timestamp_ms, death) if has_curve else None,
        cover_x=cover_x,
        cover_width=cover_width,
    )


def _availability_tooltips(
    loaded: LoadedFight, death: Death, defensives: Defensives, externals: Externals,
) -> dict[tuple[int | None, int], Tooltip]:
    """Every availability row's tooltip, keyed as `_availability_row` looks it up.

    An external's buff lands on the dying player regardless of who cast it, so
    both groups are read against the dying player's own aura table and the
    hits they took across the whole run -- not scoped to this death's own
    run-up, which is a narrower window than what the ability actually covered.
    """
    player = next((p for p in loaded.players if p.actor_id == death.actor_id), None)
    auras = loaded.auras_by_actor.get(death.actor_id)
    hits = tuple(hit for hit in loaded.damage_taken if hit.actor_id == death.actor_id)
    window = loaded.window_ms

    tooltips: dict[tuple[int | None, int], Tooltip] = {}
    if player is not None:
        for defensive in defensives.for_spec(player.class_name, player.spec):
            tip = run_ability_tooltip(
                defensive.ability_id, defensive.name, defensive.cooldown_seconds, death.actor_id,
                loaded.casts, auras, hits, window,
            )
            if tip is not None:
                tooltips[(None, defensive.ability_id)] = tip
    for mate in loaded.players:
        if mate.actor_id == death.actor_id:
            continue
        for external in externals.for_spec(mate.class_name, mate.spec):
            tip = run_ability_tooltip(
                external.ability_id, external.name, external.cooldown_seconds, mate.actor_id,
                loaded.casts, auras, hits, window, on_target=death.actor_id,
            )
            if tip is not None:
                tooltips[(mate.actor_id, external.ability_id)] = tip
    return tooltips


def _availability_row(
    state: AbilityState, names: dict[int, str], tooltips: dict[tuple[int | None, int], Tooltip],
) -> AvailabilityRow:
    if state.state == HELD:
        detail = f"{state.seconds:.1f} s before death, still up"
    elif state.state == FADED:
        detail = f"{state.seconds:.1f} s before death, over by then"
    elif state.state == PRESSED:
        detail = f"{state.seconds:.1f} s before death"
    elif state.state == COOLDOWN:
        detail = f"at most {state.seconds:.0f} s left"
    elif state.state == READY and state.seconds is not None:
        detail = f"ready, for at least {state.seconds:.1f} s"
    elif state.state == READY:
        detail = "ready"
    elif state.state == UNSEEN:
        detail = "not seen this run"
    else:
        detail = ""
    tooltip = tooltips.get((state.owner_id, state.ability_id)) if state.ability_id is not None \
        else None
    return AvailabilityRow(
        ability=state.name,
        state=state.state,
        owner=names.get(state.owner_id, "") if state.owner_id is not None else "",
        detail=detail,
        ability_id=state.ability_id,
        tooltip=tooltip,
    )


def _group(
    title: str,
    states: tuple[AbilityState, ...] | None,
    names: dict[int, str],
    empty_note: str,
    tooltips: dict[tuple[int | None, int], Tooltip],
    caveat: str = "",
) -> AvailabilityGroup:
    """A group with rows carries the badge and any caveat; an empty one says why it is empty."""
    if not states:
        return AvailabilityGroup(title=title, note=empty_note)
    return AvailabilityGroup(
        title=title,
        rows=tuple(_availability_row(state, names, tooltips) for state in states),
        badge=badge_for(Confidence.INFERRED),
        note=caveat,
    )


def _came_back(loaded: LoadedFight, death: Death, self_resurrections: SelfResurrections,
               names: dict[int, str]) -> tuple[str, Badge]:
    back = return_of(loaded.resurrections, loaded.casts, death, self_resurrections)
    if back.kind == RESURRECTED:
        caster_id = back.caster_id
        caster = "a teammate" if caster_id is None else names.get(caster_id, "a teammate")
        return (
            f"Resurrected by {caster} with {back.ability_name}, "
            f"{back.seconds_after:.1f} s after death.",
            badge_for(Confidence.MEASURED),
        )
    if back.kind == SELF_RESURRECTED:
        return (
            f"Self-resurrected with {back.ability_name}, {back.seconds_after:.1f} s after death.",
            badge_for(Confidence.MEASURED),
        )
    if back.kind == RELEASED:
        return (
            f"Released; first action against an enemy {back.seconds_after:.1f} s after death.",
            badge_for(Confidence.DERIVED),
        )
    assert back.kind == ABSENT
    return ("Not seen acting again this run.", badge_for(Confidence.MEASURED))


def build_deaths(
    loaded: LoadedFight,
    defensives: Defensives,
    consumables: Consumables,
    externals: Externals = Externals(),
    self_resurrections: SelfResurrections = SelfResurrections(),
    *,
    trimmed: bool = False,
) -> tuple[DeathCard, ...]:
    """One recap per death, oldest first.

    Built from events rather than findings: no finding carries the run-up,
    the health readings or the return, which is the reason this section
    exists at all. The same run-up window decides the timeline and the
    availability, so the card shows the damage and the answers side by side.

    `trimmed` drops the timeline and the health curve, and nothing else: the
    six availability states below still come from `availability_at`, which
    reads the cast stream and the aura table directly rather than through the
    timeline this flag skips building. Skipping means what it says -- the
    timeline is never assembled and then discarded, which is the whole point
    of a tier that exists to avoid the work.
    """
    players_by_id = {player.actor_id: player for player in loaded.players}
    names = display_names(loaded.players)
    start_ms = loaded.window_ms[0]
    cards = []
    for index, death in enumerate(sorted(loaded.deaths, key=lambda d: d.timestamp_ms)):
        player = players_by_id.get(death.actor_id)
        slug = f"death-{index}"
        auras = loaded.auras_by_actor.get(death.actor_id)
        if trimmed:
            # Not computed and discarded: the tier exists to skip this work.
            curve = None
            timeline: tuple[RecapRow, ...] = ()
            has_health = False
        else:
            events = recap_timeline(loaded, death)
            curve = build_health_curve(
                events, readings_in_window(loaded.health_samples, death), death
            )
            # Every event still reaches the curve and the press tooltips below:
            # health is reconstructed from the whole run-up, and a press sums what
            # arrived inside its cover from the same unfiltered list. Only which
            # rows a reader is shown narrows here -- see design section 4.1.
            drawn = tuple(
                event
                for event in events
                if event.kind != CAST or _press_band(event, death, auras) is not None
            )
            timeline = tuple(
                _recap_row(event, death, names, f"{slug}-e{position}", curve is not None, auras,
                           events)
                for position, event in enumerate(drawn)
            )
            has_health = any(row.health_percent is not None for row in timeline)
        at = availability_at(
            loaded.players, loaded.casts, death, defensives, consumables, externals,
            visible_from_ms=start_ms,
            auras=auras, window=loaded.window_ms,
            # The instant a defensive's band is read against. Not the death's
            # own timestamp: the death strips the bands, 15 to 55 ms before it
            # is logged, so every held defensive would read as faded. None
            # where the fetched stream carries no such hit, which leaves the
            # press at `pressed`.
            blow_ms=killing_blow_ms(loaded.damage_taken, death),
        )
        spec = f"{player.class_name} {player.spec}" if player else "this player"
        came_back, came_back_badge = _came_back(loaded, death, self_resurrections, names)
        tooltips = _availability_tooltips(loaded, death, defensives, externals)
        cards.append(
            DeathCard(
                # Falls back to the raw event name only for an actor id that is not
                # on the roster at all, which `display_names` cannot disambiguate.
                player=names.get(death.actor_id, death.player_name),
                class_name=player.class_name if player else "unknown class",
                when=_when(death, start_ms, loaded.has_pulls),
                killing_blow=death.killing_blow,
                killing_blow_id=death.killing_blow_id or None,
                timeline=timeline,
                # Every other fact on this card is read straight from the log.
                # The health column is reconstructed, and says so in the same
                # words the ledger uses.
                health_badge=badge_for(Confidence.DERIVED) if has_health else None,
                health_curve=curve,
                timeline_summary=f"{len(timeline)} {plural(len(timeline), 'event')}",
                timeline_note=(
                    TRIMMED_CARD_NOTE if trimmed else ("" if timeline else NO_TIMELINE_EVENT)
                ),
                health_note="" if has_health or not timeline else NO_HEALTH_READING,
                came_back=came_back,
                came_back_badge=came_back_badge,
                availability=(
                    _group("Defensives", at.own, names, f"No data file covers {spec}.", tooltips),
                    _group("Consumables", at.consumables, names, NO_CONSUMABLE_DATA, tooltips,
                           CONSUMABLE_CAVEAT),
                    _group("Teammates' externals", at.externals, names, NO_TEAMMATE_EXTERNALS,
                           tooltips),
                ),
                slug=slug,
            )
        )
    return tuple(cards)
