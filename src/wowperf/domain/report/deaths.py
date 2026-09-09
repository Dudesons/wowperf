# ABOUTME: One recap card per death: what killed the player, what was up, how they came back.
# ABOUTME: States what was pressed and what was ready, never what should have been pressed.

from wowperf.domain.analysis.players import display_names
from wowperf.domain.analysis.recap import (
    ABSENT,
    ABSORB,
    COOLDOWN,
    HEAL,
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
    readings_in_window,
    recap_timeline,
    return_of,
)
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import LoadedRun, Run
from wowperf.domain.report.frame import badge_for, format_seconds, plural, run_start_ms
from wowperf.domain.report.health_curve import build_health_curve
from wowperf.domain.report.model import (
    AvailabilityGroup,
    AvailabilityRow,
    Badge,
    DeathCard,
    RecapRow,
)
from wowperf.domain.season import Consumables, Defensives, Externals, SelfResurrections


def _when(death: Death, run: Run) -> str:
    """Elapsed time since the run's start, never the absolute report timestamp.

    Clamped to zero so a death logged before the first pull — or a run with
    no pulls at all, where the run's start is taken as zero — reads as the
    start of the run rather than as a negative time.
    """
    elapsed = max(death.timestamp_ms - run_start_ms(run), 0) / 1000
    at = format_seconds(elapsed)
    assert at is not None  # a float input always formats to a string
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

NO_TEAMMATE_EXTERNALS = "No teammate's specialisation has externals listed."

NO_CONSUMABLE_DATA = (
    "No consumable can be judged here: either none is listed for this run, or the death came "
    "too early for the log to show one's cooldown."
)


def _recap_row(event: RecapEvent, death: Death, names: dict[int, str]) -> RecapRow:
    if event.kind == HIT:
        detail = f"{event.amount:,} to health"
        if event.absorbed:
            detail += f", {event.absorbed:,} absorbed"
    elif event.kind == ABSORB:
        detail = f"{event.amount:,} soaked"
    elif event.kind == HEAL:
        source = event.source_id
        healer = "an unknown source" if source is None else names.get(source, "an unknown source")
        detail = f"+{event.amount:,} from {healer}"
    else:
        detail = ""
    return RecapRow(
        seconds_before=f"{(death.timestamp_ms - event.timestamp_ms) / 1000:.1f} s",
        kind=event.kind,
        ability=event.ability_name,
        detail=detail,
        health="" if event.health_percent is None else f"{event.health_percent}%",
        health_percent=event.health_percent,
        ability_id=event.ability_id or None,
    )


def _availability_row(state: AbilityState, names: dict[int, str]) -> AvailabilityRow:
    if state.state == PRESSED:
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
    return AvailabilityRow(
        ability=state.name,
        state=state.state,
        owner=names.get(state.owner_id, "") if state.owner_id is not None else "",
        detail=detail,
        ability_id=state.ability_id,
    )


def _group(
    title: str,
    states: tuple[AbilityState, ...] | None,
    names: dict[int, str],
    empty_note: str,
    caveat: str = "",
) -> AvailabilityGroup:
    """A group with rows carries the badge and any caveat; an empty one says why it is empty."""
    if not states:
        return AvailabilityGroup(title=title, note=empty_note)
    return AvailabilityGroup(
        title=title,
        rows=tuple(_availability_row(state, names) for state in states),
        badge=badge_for(Confidence.INFERRED),
        note=caveat,
    )


def _came_back(loaded: LoadedRun, death: Death, self_resurrections: SelfResurrections,
               names: dict[int, str]) -> tuple[str, Badge]:
    back = return_of(loaded, death, self_resurrections)
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
    loaded: LoadedRun,
    defensives: Defensives,
    consumables: Consumables,
    externals: Externals = Externals(),
    self_resurrections: SelfResurrections = SelfResurrections(),
) -> tuple[DeathCard, ...]:
    """One recap per death, oldest first.

    Built from events rather than findings: no finding carries the run-up,
    the health readings or the return, which is the reason this section
    exists at all. The same run-up window decides the timeline and the
    availability, so the card shows the damage and the answers side by side.
    """
    players_by_id = {player.actor_id: player for player in loaded.run.players}
    names = display_names(loaded.run)
    cards = []
    for death in sorted(loaded.deaths, key=lambda d: d.timestamp_ms):
        player = players_by_id.get(death.actor_id)
        events = recap_timeline(loaded, death)
        timeline = tuple(_recap_row(event, death, names) for event in events)
        has_health = any(row.health_percent is not None for row in timeline)
        at = availability_at(
            loaded, death, defensives, consumables, externals,
            visible_from_ms=run_start_ms(loaded.run),
        )
        spec = f"{player.class_name} {player.spec}" if player else "this player"
        came_back, came_back_badge = _came_back(loaded, death, self_resurrections, names)
        cards.append(
            DeathCard(
                # Falls back to the raw event name only for an actor id that is not
                # on the roster at all, which `display_names` cannot disambiguate.
                player=names.get(death.actor_id, death.player_name),
                class_name=player.class_name if player else "unknown class",
                when=_when(death, loaded.run),
                killing_blow=death.killing_blow,
                killing_blow_id=death.killing_blow_id or None,
                timeline=timeline,
                # Every other fact on this card is read straight from the log.
                # The health column is reconstructed, and says so in the same
                # words the ledger uses.
                health_badge=badge_for(Confidence.DERIVED) if has_health else None,
                health_curve=build_health_curve(
                    events, readings_in_window(loaded, death), death
                ),
                timeline_summary=f"{len(timeline)} {plural(len(timeline), 'event')}",
                timeline_note="" if timeline else NO_TIMELINE_EVENT,
                health_note="" if has_health or not timeline else NO_HEALTH_READING,
                came_back=came_back,
                came_back_badge=came_back_badge,
                availability=(
                    _group("Defensives", at.own, names, f"No data file covers {spec}."),
                    _group("Consumables", at.consumables, names, NO_CONSUMABLE_DATA,
                           CONSUMABLE_CAVEAT),
                    _group("Teammates' externals", at.externals, names, NO_TEAMMATE_EXTERNALS),
                ),
            )
        )
    return tuple(cards)
