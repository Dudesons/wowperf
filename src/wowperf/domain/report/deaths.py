# ABOUTME: One recap card per death: what killed the player, what was up, how they came back.
# ABOUTME: States what was pressed and what was ready, never what should have been pressed.

from wowperf.domain.analysis.cooldown_reading import Reading
from wowperf.domain.analysis.defensives import RUN_UP_SECONDS
from wowperf.domain.analysis.healer_side import HealerCooldown, HealerSide, healer_side
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
    UNJUDGED,
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
from wowperf.domain.comparison.pace import clock_text
from wowperf.domain.comparison.pace_player import pair_label
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
    HealerGroup,
    HealerLine,
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
from wowperf.domain.season import (
    Consumables,
    Defensives,
    Externals,
    Roles,
    SelfResurrections,
    ThroughputCooldowns,
)


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

NO_CARDS_ASKED = (
    "No death card was built for this pull, because the run asked for none with "
    "--no-deaths. This is not a claim that nobody died: any death finding below was "
    "measured without a card."
)
"""Why a Deaths tab is empty, when the reason is us rather than the log.

Names the flag, as `TRIMMED_CARD_NOTE` above already names `--deep` from this
same shared module. The flag it names is the one to drop rather than the one to
add, because this absence was asked for rather than declined: `--no-deaths` is
the only route to this tier, so a reader who meets this sentence typed that
flag or inherited a command line that did. A reader who opens the Deaths tab
and reads no further is then told what emptied it, without having to find the
Provenance line that says the same thing about the whole page.

"No deaths." is a reading of the log, and it is the right sentence wherever the
log is what was read. At this tier it would be a lie: the tab is empty because
nobody asked for a card, and the death-cost ledger a few lines below it on the
same tab may be listing what those very deaths cost -- so the page would
contradict itself on one screen.

The same family as `TRIMMED_CARD_NOTE` above, one level out: that one says the
run declined to build a card's insides, this one says it declined to build the
card. Both deny the reading a reader would otherwise take, because the two
sentences sit in the same place and mean opposite things.
"""

NO_TEAMMATE_EXTERNALS = "No teammate's specialisation has externals listed."


def not_judged_detail(setting: str) -> str:
    """What a row says of a cooldown whose base cooldown reaches before the log's first second.

    One sentence for every group on the card -- a defensive, an external, a
    group healing cooldown -- so the rows beside each other say it one way.
    """
    return f"not judged, its base cooldown reaches before the {setting}'s first second"


NO_OTHER_HEALER = "No other healer was in the group."

HEALER_AIM = (
    "Casts are counted where they were aimed, not by whom they healed: a smart heal or a heal "
    "over time can reach this player with no cast aimed at them, and a cast at an enemy can "
    "still heal, as Discipline's Atonement does."
)
HEALER_LANDED = "The heals that landed on this player are in this card's timeline, named by caster."
"""Left out of the note whenever the card draws no timeline row: trimmed, or its timeline is
empty. `.recap` is a two-column grid, so the Healers group can sit beside the timeline rather
than below it, and either way a card with no timeline row has nothing for this sentence to
point at."""

HEALER_COOLDOWNS = (
    "A group healing cooldown reads as ready only when it was pressed somewhere in the log read "
    "for this {setting}, not within its base cooldown before the damage began, and that base "
    "cooldown reaches back no further than the {setting}'s first second. Talents that shorten "
    "a cooldown are not modelled, a second charge reads as not ready, and a cooldown never "
    "pressed is not listed, so ready is understated, never invented. The log cannot show the "
    "healers' plan: a ready cooldown is a fact about the log, not a verdict on a healer."
)

_AIMS = (
    ("at this player", "at this player"),
    ("at themselves", "at themselves"),
    ("at another player", "at other players"),
    ("at a non-player", "at non-players"),
    ("untargeted", "untargeted"),
)

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
    setting: str,
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
    elif state.state == UNJUDGED:
        detail = not_judged_detail(setting)
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
    *,
    setting: str,
) -> AvailabilityGroup:
    """A group with rows carries the badge and any caveat; an empty one says why it is empty."""
    if not states:
        return AvailabilityGroup(title=title, note=empty_note)
    return AvailabilityGroup(
        title=title,
        rows=tuple(_availability_row(state, names, tooltips, setting) for state in states),
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


def _healer_summary(side: HealerSide, death: Death) -> str:
    """Alive or dead, the run-up's casts by where they were aimed, and the last at this player."""
    parts = ["dead when this player died" if side.dead else "alive when this player died"]
    counts = side.casts
    window = f"in the last {RUN_UP_SECONDS:g} seconds"
    if not counts.total:
        parts.append(f"no cast {window}")
        return "; ".join(parts)
    aimed = [
        f"{count} {one if count == 1 else many}"
        for count, (one, many) in zip(
            (counts.at_player, counts.at_self, counts.at_other_players, counts.at_non_players,
             counts.untargeted),
            _AIMS,
            strict=True,
        )
        if count
    ]
    parts.append(f"{counts.total} {plural(counts.total, 'cast')} {window}: {', '.join(aimed)}")
    if side.last_at_player_ms is None:
        parts.append("none at this player")
    else:
        seconds = (death.timestamp_ms - side.last_at_player_ms) / 1000
        parts.append(f"the last at this player {seconds:.1f} s before death")
    return "; ".join(parts)


def _healer_cooldown_row(cooldown: HealerCooldown, death: Death, setting: str) -> AvailabilityRow:
    """One group healing cooldown, timed back from the death like the rest of the card."""
    reading = cooldown.reading
    ability = cooldown.ability
    if reading.reading is Reading.PRESSED:
        assert reading.press_ms is not None  # PRESSED always carries its press
        detail = f"pressed {(death.timestamp_ms - reading.press_ms) / 1000:.1f} s before death"
    elif reading.reading is Reading.READY:
        detail = "ready"
    elif reading.reading is Reading.WITHIN:
        assert reading.press_ms is not None  # WITHIN always carries its press
        detail = (
            f"pressed {clock_text((death.timestamp_ms - reading.press_ms) / 1000)} before death, "
            f"within its base cooldown of {clock_text(ability.cooldown_seconds)}"
        )
    elif reading.reading is Reading.DEAD:
        detail = "its holder was dead when the damage began"
    else:
        detail = not_judged_detail(setting)
    return AvailabilityRow(
        ability=ability.name,
        state=str(reading.reading),
        detail=detail,
        ability_id=ability.ability_id,
    )


def _healers(
    sides: tuple[HealerSide, ...], death: Death, names: dict[int, str], setting: str,
    has_timeline: bool, unknown: int,
) -> HealerGroup:
    """The Healers group: one line per other healer, or the one line saying there was none.

    `unknown` is how many other roster players carry no specialisation the log
    named -- `Roles.role_of` reads that as damage, so a healer among them would
    silently drop out of the group. The note says so instead of staying quiet.
    """
    if not sides:
        if not unknown:
            return HealerGroup(note=NO_OTHER_HEALER)
        return HealerGroup(
            note=(
                "No other player's specialisation reads as a healer's, and the log names no "
                f"specialisation for {unknown} other {plural(unknown, 'player')}: a healer "
                "among them would not be listed."
            )
        )
    lines = []
    for side in sides:
        healer = side.healer
        label = pair_label(healer.class_name, healer.spec, plural=False)
        if side.dead:
            note = ""
        elif not side.listed:
            note = f"No group healing cooldown is listed for {label}."
        elif not side.cooldowns:
            note = (
                "None of their group healing cooldowns was pressed in the log read for this "
                f"{setting}."
            )
        else:
            note = ""
        lines.append(
            HealerLine(
                holder=f"{label}, {names.get(healer.actor_id, healer.name)}",
                summary=_healer_summary(side, death),
                cooldowns=tuple(
                    _healer_cooldown_row(one, death, setting) for one in side.cooldowns
                ),
                note=note,
            )
        )
    note = " ".join(
        [HEALER_AIM, *([HEALER_LANDED] if has_timeline else []),
         HEALER_COOLDOWNS.format(setting=setting)]
    )
    if unknown:
        note += (
            f" The log names no specialisation for {unknown} other {plural(unknown, 'player')}, "
            "so a healer among them is not listed here."
        )
    return HealerGroup(
        lines=tuple(lines),
        badge=badge_for(Confidence.MEASURED),
        cooldown_badge=(
            badge_for(Confidence.DERIVED) if any(line.cooldowns for line in lines) else None
        ),
        note=note,
    )


def build_deaths(
    loaded: LoadedFight,
    defensives: Defensives,
    consumables: Consumables,
    externals: Externals = Externals(),
    self_resurrections: SelfResurrections = SelfResurrections(),
    *,
    trimmed: bool = False,
    roles: Roles | None = None,
    throughput: ThroughputCooldowns = ThroughputCooldowns(),
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

    `roles` draws the Healers group: without it nothing says who heals, so no
    card carries the group. `throughput` names each healer's group healing
    cooldowns, read by the same rule the heavy-moment finding reads them.
    """
    players_by_id = {player.actor_id: player for player in loaded.players}
    names = display_names(loaded.players)
    start_ms = loaded.window_ms[0]
    setting = "run" if loaded.has_pulls else "fight"
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
                    _group("Defensives", at.own, names, f"No data file covers {spec}.", tooltips,
                           setting=setting),
                    _group("Consumables", at.consumables, names, NO_CONSUMABLE_DATA, tooltips,
                           CONSUMABLE_CAVEAT, setting=setting),
                    _group("Teammates' externals", at.externals, names, NO_TEAMMATE_EXTERNALS,
                           tooltips, setting=setting),
                ),
                healers=(
                    None
                    if roles is None
                    else _healers(
                        healer_side(
                            death, loaded.players, loaded.casts, loaded.deaths,
                            loaded.resurrections, roles, throughput, start_ms,
                        ),
                        death, names, setting, bool(timeline),
                        sum(
                            1 for mate in loaded.players
                            if mate.actor_id != death.actor_id and mate.spec == ""
                        ),
                    )
                ),
                slug=slug,
            )
        )
    return tuple(cards)
