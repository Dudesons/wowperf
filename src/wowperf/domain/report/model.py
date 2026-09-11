# ABOUTME: Everything the HTML report shows, already formatted, as one frozen value.
# ABOUTME: No methods: a method here would be judgement the template could reach.

from collections.abc import Iterator
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

    `title` is the whole sentence and is what the compact summary pointer
    renders. The three `title_*` fields are that same sentence cut at the
    ability the finding names, for the card that draws an icon there:
    `title_before + title_ability + title_after == title` always holds. When
    the sentence was not cut, `title_before` carries all of it, the other two
    are empty, and `ability_id` is None, so the card has one shape to render
    and nothing to draw.
    """

    finding_id: str
    title: str
    title_before: str = ""
    title_ability: str = ""
    title_after: str = ""
    ability_id: int | None = None
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


class DamageBar(Frozen):
    """One bucket of damage taken, in viewBox units."""

    x: float
    width: float
    y: float
    height: float


class DamageTrack(Frozen):
    """Damage taken over the run, bucketed and scaled to this player's own peak.

    Never to the group's. A shared scale across five players would rank them,
    which the postmortem design's §5.5 refuses.

    `baseline_y` is the foot the bars stand on; `label_y` is where the track's
    name sits, centred on the band the bars grow through rather than on that
    foot, so the name reads level with what it names. `axis_top_y` is the
    same peak drawn as a line rather than implied by the tallest bar's own
    top edge, running from `axis_x0` to `axis_x1` -- the same track origin
    and end every bar and span on the chart already starts and stops at, not
    the label gutter on one side or the viewBox edge on the other --
    `axis_top_label` names the figure that line stands for, and
    `bucket_caption` states the bucket width so a bar's meaning does not have
    to be guessed from its own thickness.
    """

    baseline_y: float = 0.0
    label_y: float = 0.0
    bars: tuple[DamageBar, ...] = ()
    peak_label: str = ""
    axis_top_y: float = 0.0
    axis_x0: float = 0.0
    axis_x1: float = 0.0
    axis_top_label: str = ""
    bucket_caption: str = ""


class Press(Frozen):
    """One cast of a tracked cooldown, placed on its row's axis.

    Both fields are left edges, and both centre their own element on the same
    instant: an SVG element's `x` is its left edge, so a mark placed flush with
    the instant would sit wholly to the right of the moment it marks. `x` is
    the left edge of the narrow mark the template always draws, half its width
    before the instant; `icon_x` is the left edge of the ability's icon, drawn
    only once one resolves and several times wider, half of that before it.
    """

    x: float
    icon_x: float


class Span(Frozen):
    """A stretch of a cooldown row, in viewBox units."""

    x: float
    width: float


class CooldownRow(Frozen):
    """One ability this player owns, and what the run did with it.

    `not_judged` covers the run's opening, where the log cannot say whether the
    ability was available: casts are fetched per fight, so a press before the
    timer started is invisible.

    `baseline_y` is the row's top edge, which every rect on it hangs from;
    `label_y` is the row's middle, where its name sits. They differ because a
    name drawn from the top edge would fall across the row above.

    `ready_ticks` marks the instant each `unavailable` span ends -- the
    moment the ability came back -- but only for a press whose cooldown
    finished before the axis did. A cooldown still running when the run ends
    gets no tick: the log never says the ability came back, so nothing is
    drawn claiming it did.
    """

    label: str
    ability_id: int | None = None
    baseline_y: float = 0.0
    label_y: float = 0.0
    presses: tuple[Press, ...] = ()
    unavailable: tuple[Span, ...] = ()
    ready_ticks: tuple[float, ...] = ()
    not_judged: Span | None = None
    cover: tuple[Span, ...] = ()
    """Every stretch this ability's buff was actually up, from the aura table's
    own bands, clipped to the axis.

    Drawn at true scale and never floored: a five-second buff on a
    thirty-three-minute axis is about one and a half units wide, and widening it
    to make it visible would be a claim about duration the log did not make.
    Empty where no aura table was fetched for this player, where the table
    recorded no band for the ability, or where neither the ability's own id
    nor its name matched an aura the table carries -- `resolve_aura` tries the
    id first and the name second, because the table keys an aura on the buff
    it applies, not on the spell cast to apply it, and a few abilities cast as
    one spell and buff as another.
    """


class PlayerTimeline(Frozen):
    """One player's run on one axis. Every coordinate the SVG needs lives here.

    Each badge's caption is the claim it grades -- what the damage bars and
    press marks show, or what the dimming assumes -- so the words a reader
    checks against the drawing live beside the badge, not in the template.
    """

    section: Section
    title: str = ""
    width: float = 0.0
    height: float = 0.0
    pulls: tuple[TimelineBlock, ...] = ()
    band_y: float = 0.0
    column_height: float = 0.0
    pull_label_y: float = 0.0
    damage: DamageTrack | None = None
    cooldowns: tuple[CooldownRow, ...] = ()
    ticks: tuple[tuple[float, str], ...] = ()
    tick_y1: float = 0.0
    tick_y2: float = 0.0
    tick_label_y: float = 0.0
    label_x: float = 0.0
    row_height: float = 0.0
    press_width: float = 0.0
    legend: str = ""
    badge_measured: Badge | None = None
    badge_measured_caption: str = ""
    badge_inferred: Badge | None = None
    badge_inferred_caption: str = ""


class TooltipLine(Frozen):
    """One labelled figure of a tooltip. Formatted here; the template prints it."""

    label: str
    value: str


class Tooltip(Frozen):
    """What hovering an ability says: measured lines, and the caveat they need.

    A tooltip with no lines is never built: the panel exists to carry figures,
    and an empty one is a hover target that rewards nothing.
    """

    lines: tuple[TooltipLine, ...] = ()
    note: str = ""


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

    `tooltip` is what the log recorded about this one event, or None on a
    cast, which carries no figures of its own to show.
    """

    seconds_before: str
    kind: str
    ability: str
    detail: str = ""
    health: str = ""
    health_percent: int | None = None
    ability_id: int | None = None
    tooltip: Tooltip | None = None
    marker_id: str = ""
    """This row's own element id, shared with the marker it lights on the curve.

    Unique across the page: two deaths in one run each have a row zero, and the
    script resolves a marker by id.
    """
    marker_x: float | None = None
    """Where this row's moment falls on the curve, or None when there is no curve
    to place it on. In the curve's own coordinate space, from `curve_x`."""
    cover_x: float | None = None
    """The left edge of the window this press covered, in the curve's coordinate
    space, or None on a row that is not a press or whose buff the aura table
    never recorded. Drawn only where the log stated a band."""
    cover_width: float | None = None
    """How wide that window is, in the same coordinate space as `cover_x`.
    None exactly when `cover_x` is: the two are always set together."""


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
    plot_y0: float
    plot_y1: float
    plot_height: float
    """`plot_y1 - plot_y0`, computed once so a cover window's `<rect>` needs no
    arithmetic of its own to span the plot's full height."""
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
    """One saving tool at the death. `state` is "pressed", "ready", "cooldown" or "unseen".

    `ability_id` is None on a consumable row, which names a cooldown group
    rather than one item, so those rows carry no icon.

    `tooltip` carries what the run measured about this ability -- its
    presses, its cover, and the derived mitigation-rate gap the design's
    section 5 requires to be offered as suggestive rather than attributed --
    or None where the dying player's own aura table names no matching buff.
    """

    ability: str
    state: str
    owner: str = ""
    detail: str = ""
    ability_id: int | None = None
    tooltip: Tooltip | None = None


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

    `killing_blow_id` names the ability in the heading for an icon, or is None
    where the log named none. Zero is never used: the ability dictionary maps
    zero to "Unknown Ability" with a real icon file, so a zero would draw art
    beside a killing blow nobody identified.
    """

    player: str
    class_name: str
    when: str
    killing_blow: str
    killing_blow_id: int | None = None
    timeline: tuple[RecapRow, ...] = ()
    timeline_summary: str = ""
    timeline_note: str = ""
    health_badge: Badge | None = None
    health_curve: HealthCurve | None = None
    health_note: str = ""
    came_back: str = ""
    came_back_badge: Badge | None = None
    availability: tuple[AvailabilityGroup, ...] = ()
    slug: str = ""
    """This card's fragment id, unique within the report. Every marker id on the
    card is built from it."""


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
    slug: str = ""
    """This player's fragment id, unique within the report.

    Derived from the disambiguated display name and suffixed with the
    roster's own index, because two names can reduce to the same slug and a
    duplicate id would give one player another's sub-tab.
    """
    timeline: PlayerTimeline | None = None
    """This player's own run, drawn.

    `None` only on a card built without one: the builder always supplies a
    timeline, withheld when it has nothing to draw.
    """


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
    # Whose comparison weighed this candidate, from `slugs_by_actor`. Empty on a
    # speed candidate: the route is compared once for the run, not per player.
    player_slug: str = ""
    # The same player as `player_slug`, spelled the way the page spells them,
    # from `display_names`. Empty on a speed candidate for the same reason.
    # This is a member of our own roster, whose name every card already prints,
    # so it tabulates nothing about anybody else -- the rule this record keeps
    # is about other players' runs, and it still carries a link and no figure.
    player_name: str = ""


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


def all_ledger_rows(report: Report) -> Iterator[LedgerRow]:
    """Every finding row on the page, including the two nested in each player card.

    One place names the sections, so a caller cannot reach eight of the nine and
    lose the ninth in silence: a row whose ability reaches the page without
    reaching the icon resolver draws nothing and reports nothing.
    """
    yield from report.ledger_decomposition
    yield from report.summary_pointers
    yield from report.route_rows
    yield from report.death_rows
    yield from report.interrupts
    yield from report.group_rows
    yield from report.observations
    for player in report.players:
        yield from player.damage_rows
        yield from player.spell_and_talent_rows
