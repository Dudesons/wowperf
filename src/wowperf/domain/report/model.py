# ABOUTME: Everything the HTML report shows, already formatted, as one frozen value.
# ABOUTME: No methods: a method here would be judgement the template could reach.

from enum import StrEnum

from wowperf.domain.base import Frozen


class SectionState(StrEnum):
    """Whether a section has data, or is reporting why it has none."""

    PRESENT = "present"
    WITHHELD = "withheld"


class Section(Frozen):
    """A section's state, and the reason when it has nothing to show.

    The reason is never written by the report: it is the detail of the
    `compare.*.unavailable` finding the comparison already emits.
    """

    state: SectionState
    reason: str = ""


class Badge(Frozen):
    """A confidence badge: a word plus a palette token, never a colour alone."""

    label: str
    tint: str


class LedgerRow(Frozen):
    """One finding, formatted for display."""

    finding_id: str
    title: str
    detail: str
    badge: Badge
    seconds: str | None = None
    nests_inside: str | None = None
    evidence: tuple[str, ...] = ()


class TimelineBlock(Frozen):
    """One pull, positioned in viewBox units. All arithmetic happened in build.py.

    `css_class` is the whole class attribute the template emits: `kind` and
    `is_boss` stay alongside it because tests key off them, not because the
    template still branches on them.
    """

    label: str
    x: float
    width: float
    is_boss: bool
    kind: str
    css_class: str = ""


class TimelineTrack(Frozen):
    """One run's blocks, and the y at which they and their caption sit."""

    caption: str
    baseline_y: float = 0.0
    blocks: tuple[TimelineBlock, ...] = ()


class Timeline(Frozen):
    """Both runs on one elapsed-time axis. Empty tracks when the section is withheld.

    Every coordinate the SVG needs lives here or on `TimelineTrack.baseline_y`
    so the template never computes one: `tick_y1`/`tick_y2` bound the tick
    lines, `tick_label_y` positions their text, `caption_x`/`caption_dy` place
    each track's caption, and `block_height` is shared by every block.
    """

    section: Section
    ours: TimelineTrack | None = None
    theirs: TimelineTrack | None = None
    ticks: tuple[tuple[float, str], ...] = ()
    width: float = 0.0
    height: float = 0.0
    tick_y1: float = 0.0
    tick_y2: float = 0.0
    tick_label_y: float = 0.0
    caption_x: float = 0.0
    caption_dy: float = 0.0
    block_height: float = 0.0


class DamageRow(Frozen):
    seconds_before: str
    ability: str
    amount: str


class DeathCard(Frozen):
    """One death, with the damage that caused it and what the player still had.

    `defensives_checked` and `defensives_available` are two facts, not one.
    An empty list under a checked spec says nothing was off cooldown, which
    exonerates the player; an unchecked spec says the data file does not cover
    them and the tool knows nothing. Rendering both as a blank would turn the
    second into the first.

    The consumable pair is shaped the same way but is a weaker claim, and
    `consumables_caveat` is why it must not read like the defensive one. A
    defensive is only named once the player has demonstrably cast it; a
    consumable never proves it was carried, because the log records one only
    when it is drunk. In practice `consumables_checked` is false only for a
    death by an actor missing from the roster.
    """

    player: str
    class_name: str
    when: str
    killing_blow: str
    last_ten_seconds: tuple[DamageRow, ...] = ()
    defensives_checked: bool = False
    defensives_available: tuple[str, ...] = ()
    defensives_badge: Badge | None = None
    consumables_checked: bool = False
    consumables_available: tuple[str, ...] = ()
    consumables_badge: Badge | None = None
    consumables_caveat: str = ""


class PlayerCard(Frozen):
    """One player's measured facts.

    `damage_rows` states damage against the group median, never as avoidable:
    the log does not record whether a hit could have been dodged, and this card
    follows the analyser that refuses that framing.

    `stats_line` states a cast count over the pull time it happened in, e.g.
    "182 casts in 31:49 of pulls · 1 death · 7 interrupts" — never a
    percentage. A player casting faster than once a second exceeds the pull
    time itself under the model this is measured with, so a share of it would
    read as more than 100% activity. Its death and interrupt counts are
    already pluralised, so nothing about this line is decided by the template.
    """

    name: str
    class_name: str
    spec: str
    colour: str
    stats_line: str
    damage_rows: tuple[LedgerRow, ...] = ()
    spell_and_talent: Section
    spell_and_talent_rows: tuple[LedgerRow, ...] = ()


class Header(Frozen):
    """No percentile: nothing this project fetches produces our own player's rank."""

    dungeon: str
    keystone_level: int
    affixes: tuple[str, ...] = ()
    result: str = ""


class Provenance(Frozen):
    report_code: str
    fight_id: int
    fetched_at: str
    speed_reference_url: str | None = None
    parse_reference_url: str | None = None
    withheld: tuple[str, ...] = ()


class Report(Frozen):
    header: Header
    narrative: str | None
    ledger_decomposition: tuple[LedgerRow, ...]
    timeline: Timeline
    # Withheld without a speed reference, with the reason the timeline reads too. The
    # rows beneath it that need no reference — gaps, trash — still render.
    route: Section
    # Gaps, downtime, the route comparison, trash and confounds: what the route cost.
    route_rows: tuple[LedgerRow, ...] = ()
    deaths: tuple[DeathCard, ...]
    # The death costs and what a dying player still had, beneath the death cards.
    death_rows: tuple[LedgerRow, ...] = ()
    interrupts: tuple[LedgerRow, ...]
    players: tuple[PlayerCard, ...]
    # Per-player rate rows — defensive and throughput — beneath the player cards.
    group_rows: tuple[LedgerRow, ...] = ()
    # Every finding no field above claimed — a structural catch-all, not a
    # whitelist of its own. See `build_observations`.
    observations: tuple[LedgerRow, ...]
    provenance: Provenance
