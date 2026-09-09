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
    """One finding, formatted for display.

    `group_note` carries the explanation shared by a run of neighbouring rows
    that all gave the same one, and is set on the run's first row only; those
    rows then hold no `detail` of their own. Several findings of one family
    often differ in their figures and agree word for word on what the figures
    mean, and a reader who meets that paragraph four times learns to skip it.
    Which rows form a run is decided in `build.py`, so the template renders
    whichever of the two fields it is given and chooses nothing.
    """

    finding_id: str
    title: str
    detail: str
    badge: Badge
    seconds: str | None = None
    nests_inside: str | None = None
    evidence: tuple[str, ...] = ()
    group_note: str = ""


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
    # What the marks on the blocks mean, or why only one track is drawn. Written
    # here rather than in the template because it depends on whether a reference
    # was drawable, which is a judgement the renderer must not make.
    legend: str = ""
    ticks: tuple[tuple[float, str], ...] = ()
    width: float = 0.0
    height: float = 0.0
    tick_y1: float = 0.0
    tick_y2: float = 0.0
    tick_label_y: float = 0.0
    caption_x: float = 0.0
    caption_dy: float = 0.0
    block_height: float = 0.0


class RecapRow(Frozen):
    """One event of a death's last seconds, formatted.

    `kind` is one of "hit", "absorb", "heal", "cast": a row class the template
    maps to colour and to nothing else. `health` is the reconstructed health
    after the event as "62%", or "" before the first reading; `health_percent`
    is the same figure as a number, so the template can draw a bar without
    computing one. A share of the player's own health, never a duration.

    `ability_id` names the ability for an icon, or is None where the log named
    none. Zero is never used: the ability dictionary maps zero to "Unknown
    Ability" with a real icon file, so a zero would draw art beside a row
    nobody identified.
    """

    seconds_before: str
    kind: str
    ability: str
    detail: str = ""
    health: str = ""
    health_percent: int | None = None
    ability_id: int | None = None


class CurvePoint(Frozen):
    """One corner of the health curve, in viewBox units. All arithmetic happened in the builder."""

    x: float
    y: float


class CurveReading(Frozen):
    """One health reading the log stated, drawn apart from the line that joins the events.

    The line is arithmetic — hits subtracted, heals added — between moments the
    log actually reported a figure. These are those moments, so they carry the
    measured badge while the line carries the derived one, and a dot sitting off
    the line is the drift between the two made visible rather than resolved in
    silence.
    """

    x: float
    y: float
    percent: int


class CurveTick(Frozen):
    """One mark on the health curve's time axis: where it sits and what it says."""

    x: float
    label: str


class CurveGuide(Frozen):
    """One horizontal line across the health curve, and the health it stands for."""

    y: float
    label: str


class HealthCurve(Frozen):
    """A death's health across the run-up, as coordinates the template only prints.

    A card carries None rather than an empty curve when no event of the run-up
    reported health: an axis with no line on it reads as a flat line at zero.
    """

    width: float
    height: float
    plot_x0: float
    plot_x1: float
    label_x: float
    tick_label_y: float
    points: tuple[CurvePoint, ...] = ()
    readings: tuple[CurveReading, ...] = ()
    ticks: tuple[CurveTick, ...] = ()
    guides: tuple[CurveGuide, ...] = ()
    reading_legend: str = ""
    line_legend: str = ""
    line_badge: Badge | None = None
    reading_badge: Badge | None = None


class AvailabilityRow(Frozen):
    """One saving tool at the death. `state` is "pressed", "ready", "cooldown" or "unseen"."""

    ability: str
    state: str
    owner: str = ""
    detail: str = ""


class AvailabilityGroup(Frozen):
    """One of the three availability groups: own defensives, consumables, teammates' externals.

    A group with rows carries the inferred badge. A group with none and a
    `note` is empty for one of two reasons: a spec absent from a file, which
    the tool could say nothing about at all, or — for consumables — every
    category's cooldown window reaching back before the run began, which is a
    group that was checked and still has nothing to show. Either way the note
    says why; rendering both as blank would merge them with a checked group
    that found rows in the ready state.
    """

    title: str
    rows: tuple[AvailabilityRow, ...] = ()
    badge: Badge | None = None
    note: str = ""


class DeathCard(Frozen):
    """One death as a recap: what killed the player, what was up, how they came back.

    Every string is formatted by the builder. `timeline_summary` labels the table
    with what it holds and `timeline_note` says why it is empty when it is.
    `health_badge` is None when no row carries health and `health_note` then says
    why. `health_curve` is None then too, and on the rarer condition that the
    line would have no length to draw, so a card never carries an axis with
    nothing on it. `came_back` is one of the four return lines and always
    carries its badge.
    """

    player: str
    class_name: str
    when: str
    killing_blow: str
    timeline: tuple[RecapRow, ...] = ()
    timeline_summary: str = ""
    timeline_note: str = ""
    health_badge: Badge | None = None
    health_curve: HealthCurve | None = None
    health_note: str = ""
    came_back: str = ""
    came_back_badge: Badge | None = None
    availability: tuple[AvailabilityGroup, ...] = ()


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


class ReferenceRecord(Frozen):
    """One candidate the comparison considered, whether or not it was used.

    Carries a link and never a figure: the findings JSON and this report are
    kept forever, and a file that tabulates other players' durations and death
    counts is the corpus the 24-hour reference cache exists to avoid.
    """

    report_code: str
    fight_id: int
    keystone_level: int
    url: str
    axis: str
    loaded: bool = True
    reason: str = ""
    # Every query this reference needed was already on disk, so nothing was
    # fetched for it. The reference cache is shared across analyses, and this
    # is where a report that discloses every candidate discloses that too.
    from_cache: bool = False


class Provenance(Frozen):
    report_code: str
    fight_id: int
    fetched_at: str
    # Every candidate the comparison weighed, loaded or not, in the order `_samples`
    # considered it. A link and never a figure — see `ReferenceRecord`.
    references: tuple[ReferenceRecord, ...] = ()
    withheld: tuple[str, ...] = ()
    # Methods the page relied on that a reader might dispute, stated once here
    # rather than on every card: today, how a death card's health column is built.
    methods: tuple[str, ...] = ()


class Report(Frozen):
    header: Header
    narrative: str | None
    ledger_decomposition: tuple[LedgerRow, ...]
    # The biggest timed losses, in the order the findings arrived. Each equals its
    # card on another tab; the Summary renders it as a link to that card, never as
    # a second card.
    summary_pointers: tuple[LedgerRow, ...] = ()
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
