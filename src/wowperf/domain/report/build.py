# ABOUTME: Turns a loaded run and its findings into the value the template renders.
# ABOUTME: Every judgement about what appears where lives here, and nowhere else.

from collections.abc import Sequence

from wowperf.domain.analysis.players import display_names, summarise_players
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
    recap_timeline,
    return_of,
)
from wowperf.domain.comparison.reference import ParseReference, SpeedReference
from wowperf.domain.comparison.sample import SpeedSample
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player, Run
from wowperf.domain.report.model import (
    AvailabilityGroup,
    AvailabilityRow,
    Badge,
    DeathCard,
    Header,
    LedgerRow,
    PlayerCard,
    Provenance,
    RecapRow,
    ReferenceRecord,
    Report,
    Section,
    SectionState,
    Timeline,
    TimelineBlock,
    TimelineTrack,
)
from wowperf.domain.season import Consumables, Defensives, Externals, SelfResurrections

SPEED_UNAVAILABLE_ID = "compare.speed.unavailable"
PARSE_UNAVAILABLE_ID = "compare.parse.unavailable"

# Said when `--no-compare` skipped the comparison entirely, so no finding explains the absence.
NO_COMPARISON_RAN = (
    "No reference run was fetched for this analysis, so there is nothing to compare against."
)

DECOMPOSITION_IDS = ("compare.duration", "time.residual", "deaths.total")
"""Figures that contain others. They head the ledger; everything else is ranked beneath."""

NESTS_INSIDE = (
    ("time.gap.", "time.residual"),
    ("compare.downtime", "time.residual"),
    ("deaths.single.", "deaths.total"),
    ("deaths.chain.", "deaths.total"),
    ("deaths.repeat.", "deaths.total"),
    ("compare.route.skipped.", "trash.overage"),
)
"""Which figures are already contained by which, copied from the findings file's own warning.

Stated rather than inferred: the relationships come from what the analysers
measure, and they change when an analyser changes, not when a report renders.
`compare.duration` measures the gap against the median of the sample, while
every figure here is priced against this run's own route, so the two overlap
without one containing the other; it is a decomposition row rather than a
parent, so repeating it on every line would be noise.

Entries must stay mutually non-overlapping: `parent_of` resolves by first match
in tuple order, so a broader prefix placed ahead of a narrower one would
silently win and misattribute nesting.
"""

TIMELINE_WIDTH = 680.0
TIMELINE_HEIGHT = 208.0
TRACK_X0 = 46.0
TRACK_X1 = 656.0
MIN_BLOCK_WIDTH = 2.0
"""A pull narrower than this reads as nothing at all, so it is drawn at this width."""

TICK_SECONDS = 600
"""One axis label every ten minutes: enough to place a pull, few enough to stay legible."""

AXIS_TOP = 46.0
"""Where the tick lines start: just above the top track's caption."""

AXIS_BOTTOM_MARGIN = 32.0
"""Gap between the tick lines' foot and the viewBox's bottom edge."""

TICK_LABEL_MARGIN = 16.0
"""Gap between the tick labels' baseline and the viewBox's bottom edge."""

CAPTION_DY = -10.0
"""How far above its track's baseline a caption's text sits."""

BLOCK_HEIGHT = 26.0
"""Every block's height, shared by both tracks."""

OURS_BASELINE_Y = 58.0
"""The y at which our track's blocks and caption sit."""

THEIRS_BASELINE_Y = 132.0
"""The y at which the reference track's blocks and caption sit."""


def badge_for(confidence: Confidence) -> Badge:
    """A word and a palette token. The word is what a reader without colour sees."""
    return Badge(label=str(confidence), tint=f"badge-{confidence}")


def format_seconds(seconds: float | None) -> str | None:
    """Minutes and seconds, or nothing at all.

    `None` stays `None` rather than becoming "0:00": a finding with no honest
    seconds figure must not read as one that cost no time.
    """
    if seconds is None:
        return None
    whole = int(round(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def _finding_by_id(findings: Sequence[Finding], finding_id: str) -> Finding | None:
    return next((finding for finding in findings if finding.id == finding_id), None)


def _section_for(findings: Sequence[Finding], unavailable_id: str, present: bool) -> Section:
    """Present, or withheld with the reason the comparison itself gave.

    When no comparison ran at all there is no finding to quote, so the fallback
    states that plainly rather than implying a leaderboard came back empty.
    """
    if present:
        return Section(state=SectionState.PRESENT)
    finding = _finding_by_id(findings, unavailable_id)
    return Section(
        state=SectionState.WITHHELD,
        reason=finding.detail if finding else NO_COMPARISON_RAN,
    )


def _run_start_ms(run: Run) -> int:
    """The run's own clock origin: the earliest pull's start, or zero with no pulls.

    Shared by `_run_seconds` and `_when` so a death's elapsed time and the
    run's span are measured from the same point and cannot drift apart.
    """
    return min((p.start_ms for p in run.pulls), default=0)


def _run_seconds(run: Run) -> float:
    """Wall-clock span from the first pull's start to the last pull's end.

    Not `total_pull_seconds`, which sums pull durations and so omits every
    second spent travelling — the very time this report exists to show.
    """
    if not run.pulls:
        return 0.0
    return (max(p.end_ms for p in run.pulls) - _run_start_ms(run)) / 1000


def _block_css_class(kind: str, is_boss: bool, track_class: str) -> str:
    """The whole class attribute for one block.

    `extra` gets its own tan fill but also a heavier outline, so the mark
    that matters most on this chart survives a colour-blind or greyscale
    reading rather than resting on hue alone. `skipped` is already
    unfilled and dashed, which is a shape difference and needs no help.
    """
    if kind == "extra":
        classes = ["block-extra"]
    elif kind == "skipped":
        classes = ["block-skipped"]
    else:
        classes = ["block", track_class] if track_class else ["block"]
    if is_boss:
        classes.append("block-boss")
    return " ".join(classes)


def _blocks(
    run: Run, kinds: dict[int, str], scale: float, origin_ms: int, track_class: str = ""
) -> tuple[TimelineBlock, ...]:
    blocks = []
    for pull in run.pulls:
        kind = kinds.get(pull.index, "matched")
        blocks.append(
            TimelineBlock(
                label=pull.name,
                x=TRACK_X0 + (pull.start_ms - origin_ms) / 1000 * scale,
                width=max(pull.duration_seconds * scale, MIN_BLOCK_WIDTH),
                is_boss=pull.is_boss,
                kind=kind,
                css_class=_block_css_class(kind, pull.is_boss, track_class),
            )
        )
    return tuple(blocks)


def _ticks(longest: float, scale: float) -> tuple[tuple[float, str], ...]:
    marks = []
    second = 0
    while second <= longest:
        label = format_seconds(float(second))
        assert label is not None  # a float input always formats to a string
        marks.append((TRACK_X0 + second * scale, label))
        second += TICK_SECONDS
    return tuple(marks)


def _timeline_caption(label: str, seconds: float, suffix: str = "") -> str:
    """State which span this caption measures, not just its length.

    `seconds` spans the first pull's start to the last pull's end. The
    header states a different, longer figure — `keystone_time_seconds`,
    which also counts the trip to the first pack and Blizzard's death
    penalties. Naming the span here keeps a reader from seeing two numbers
    for the same run and assuming one of them is wrong. `suffix`, when
    given, names the sample size a reference track was drawn from, so a
    reader never mistakes one picture for the whole sample.
    """
    formatted = format_seconds(seconds)
    assert formatted is not None  # a float input always formats to a string
    base = f"{label} — {formatted} from first pull to last"
    return f"{base}, {suffix}" if suffix else base


def build_timeline(ours: Run, sample: SpeedSample | None, section: Section) -> Timeline:
    """Both runs on one elapsed-time axis, scaled so the longer one fills the width.

    The space between blocks is travel. That is why this layout exists: a
    per-pull table compares durations, and durations are rarely where a
    Mythic+ run loses its time.

    Drawn from `sample.duration_eligible`'s best-aligned member — highest
    `Alignment.matched_share`, compared pairwise and never averaged — and from
    no one else: a member outside that subset sits at a different keystone
    level, where `compare.duration` already refuses to print a number, and a
    picture of its pull lengths would draw exactly what that finding withheld.
    No track is drawn when the subset is empty. The member's `Alignment` was
    computed once, when the sample was built, and is used as-is here rather
    than recomputed.
    """
    if section.state is SectionState.WITHHELD or sample is None or not sample.duration_eligible:
        return Timeline(section=section, width=TIMELINE_WIDTH, height=TIMELINE_HEIGHT)

    member = max(sample.duration_eligible, key=lambda candidate: candidate.alignment.matched_share)
    theirs = member.run

    our_seconds = _run_seconds(ours)
    their_seconds = _run_seconds(theirs)
    longest = max(our_seconds, their_seconds)
    scale = (TRACK_X1 - TRACK_X0) / longest if longest > 0 else 0.0

    our_kinds = {index: "extra" for index in member.alignment.only_ours}
    their_kinds = {index: "skipped" for index in member.alignment.only_theirs}

    return Timeline(
        section=section,
        ours=TimelineTrack(
            caption=_timeline_caption("Ours", our_seconds),
            baseline_y=OURS_BASELINE_Y,
            blocks=_blocks(ours, our_kinds, scale, _run_start_ms(ours)),
        ),
        theirs=TimelineTrack(
            caption=_timeline_caption(
                "Reference", their_seconds, suffix=f"one of {len(sample.members)} fast runs"
            ),
            baseline_y=THEIRS_BASELINE_Y,
            blocks=_blocks(
                theirs,
                their_kinds,
                scale,
                _run_start_ms(theirs),
                track_class="block-theirs",
            ),
        ),
        ticks=_ticks(longest, scale),
        width=TIMELINE_WIDTH,
        height=TIMELINE_HEIGHT,
        tick_y1=AXIS_TOP,
        tick_y2=TIMELINE_HEIGHT - AXIS_BOTTOM_MARGIN,
        tick_label_y=TIMELINE_HEIGHT - TICK_LABEL_MARGIN,
        caption_x=TRACK_X0,
        caption_dy=CAPTION_DY,
        block_height=BLOCK_HEIGHT,
    )


def _when(death: Death, run: Run) -> str:
    """Elapsed time since the run's start, never the absolute report timestamp.

    Clamped to zero so a death logged before the first pull — or a run with
    no pulls at all, where the run's start is taken as zero — reads as the
    start of the run rather than as a negative time.
    """
    elapsed = max(death.timestamp_ms - _run_start_ms(run), 0) / 1000
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
    "reading replaces the running value. The column is badged derived for that reason."
)

NO_HEALTH_READING = (
    "The log carries no health reading for this player before the death, so the health "
    "column is empty."
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
        timeline = tuple(
            _recap_row(event, death, names) for event in recap_timeline(loaded, death)
        )
        has_health = any(row.health_percent is not None for row in timeline)
        at = availability_at(
            loaded, death, defensives, consumables, externals,
            visible_from_ms=_run_start_ms(loaded.run),
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
                timeline=timeline,
                # Every other fact on this card is read straight from the log.
                # The health column is reconstructed, and says so in the same
                # words the ledger uses.
                health_badge=badge_for(Confidence.DERIVED) if has_health else None,
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


CLASS_COLOURS = (
    "DeathKnight", "DemonHunter", "Druid", "Evoker", "Hunter", "Mage", "Monk",
    "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Warrior",
)
"""Classes with a palette token. A class absent here still renders, in a neutral tone.

The colour never carries meaning alone: every card prints the class name too,
because several class colours are hard to tell apart and reports get
screenshotted and recompressed.
"""

COMPARISON_PREFIXES = ("compare.spells.", "compare.talents", "compare.uptime.")
"""Finding families that belong on the subject player's card rather than in the ledger."""


def class_colour(class_name: str) -> str:
    return f"class-{class_name.lower()}" if class_name in CLASS_COLOURS else "class-unknown"


def _plural(count: int, singular: str) -> str:
    """`singular` unless `count` is not one. The one pluralisation rule this report needs."""
    return singular if count == 1 else f"{singular}s"


PLACEMENTS: tuple[tuple[str, str], ...] = (
    ("defensives.unused.", "death_rows"),
    ("consumables.", "death_rows"),
    ("deaths.", "death_rows"),
    ("compare.deaths", "death_rows"),
    ("time.gap.", "route_rows"),
    ("compare.downtime", "route_rows"),
    ("compare.route.", "route_rows"),
    (SPEED_UNAVAILABLE_ID, "route_rows"),
    ("trash.", "route_rows"),
    ("compare.confound.", "route_rows"),
    ("interrupts.", "interrupts"),
    ("compare.interrupts", "interrupts"),
    (PARSE_UNAVAILABLE_ID, "group_rows"),
    ("defensives.", "group_rows"),
    ("throughput.", "group_rows"),
)
"""Which tab's rows a finding family lands in: the first prefix that matches wins.

Unlike `NESTS_INSIDE`, the entries here overlap on purpose — `defensives.unused.`
is a death-shaped claim and the bare `defensives.` prefix is a rate — so order is
the rule and the narrow families come first. A finding no prefix matches is not
dropped: `build_observations` picks up everything unplaced. The player-card
families (`players.damage.`, `compare.spells.`, `compare.talents`,
`compare.uptime.`) are placed by `build_players` and are deliberately absent.
"""


def _field_for(finding_id: str) -> str | None:
    return next((field for prefix, field in PLACEMENTS if finding_id.startswith(prefix)), None)


def place_rows(
    findings: Sequence[Finding], titles_by_id: dict[str, str], exclude: set[str]
) -> dict[str, tuple[LedgerRow, ...]]:
    """Every finding's row, keyed by the `Report` field it lands in.

    `exclude` holds the ids the decomposition already claimed, so a timed
    `deaths.total` heads the ledger and does not also sit beneath the death
    cards. Order within a field is the order the findings arrived in:
    `rank_findings` has already sorted them, and one ranking authority is enough.
    """
    placed: dict[str, list[LedgerRow]] = {field: [] for _, field in PLACEMENTS}
    for finding in findings:
        if finding.id in exclude:
            continue
        field = _field_for(finding.id)
        if field is not None:
            placed[field].append(_ledger_row(finding, titles_by_id))
    return {field: tuple(rows) for field, rows in placed.items()}


POINTER_COUNT = 5
"""How many losses the Summary points at: enough to show the run's shape, few enough to
stay a list."""


def build_summary_pointers(
    findings: Sequence[Finding], titles_by_id: dict[str, str], exclude: set[str]
) -> tuple[LedgerRow, ...]:
    """The first timed findings that are not decomposition rows, in the order given.

    `rank_findings` has already sorted the findings by seconds, descending, in
    the CLI. Re-sorting here would be a second ranking authority that could
    disagree with the findings file; taking the first few in order cannot.
    """
    timed = [
        finding
        for finding in findings
        if finding.seconds_lost is not None and finding.id not in exclude
    ]
    return tuple(_ledger_row(finding, titles_by_id) for finding in timed[:POINTER_COUNT])


def build_players(
    loaded: LoadedRun,
    findings: Sequence[Finding],
    parse: ParseReference | None,
    subject: Player,
    titles_by_id: dict[str, str],
) -> tuple[PlayerCard, ...]:
    """One card per player.

    Damage is stated as `players.damage.*` states it — a multiple of the group
    median, with the analyser's own caveat that this is a difference and not a
    mistake. The log does not record whether a hit could have been dodged;
    this card carries the analyser's findings unchanged and adds no framing
    of its own.

    `name` is the roster's disambiguated display name, not the raw one: two
    players who share a display name must never render as two identical-
    looking cards. `subject` is the player being analysed, from our own
    roster — never `parse.row.character_name`, which names the reference
    run's top parser, a different character in a different log. Matching by
    `actor_id` rather than name also keeps two players who share a display
    name from both receiving the comparison rows.
    """
    comparison_section = _section_for(findings, PARSE_UNAVAILABLE_ID, parse is not None)
    names_by_actor = display_names(loaded.run)

    untimed = [finding for finding in findings if finding.seconds_lost is None]
    damage = [finding for finding in untimed if finding.id.startswith("players.damage.")]
    comparison = [
        finding
        for finding in untimed
        if any(finding.id.startswith(prefix) for prefix in COMPARISON_PREFIXES)
    ]

    total_pulls = format_seconds(loaded.run.total_pull_seconds)
    assert total_pulls is not None  # a float input always formats to a string

    cards = []
    for summary in summarise_players(
        loaded.run, loaded.casts, loaded.deaths, loaded.interrupts
    ):
        display_name = names_by_actor[summary.actor_id]
        mine = tuple(
            _ledger_row(finding, titles_by_id)
            for finding in damage
            if finding.title.startswith(f"{display_name} took ")
        )
        is_subject = summary.actor_id == subject.actor_id
        stats_line = (
            f"{summary.casts_in_pulls} {_plural(summary.casts_in_pulls, 'cast')} "
            f"in {total_pulls} of pulls · "
            f"{summary.deaths} {_plural(summary.deaths, 'death')} · "
            f"{summary.interrupts} {_plural(summary.interrupts, 'interrupt')}"
        )
        cards.append(
            PlayerCard(
                name=display_name,
                class_name=summary.class_name,
                spec=summary.spec,
                colour=class_colour(summary.class_name),
                stats_line=stats_line,
                damage_rows=mine,
                spell_and_talent=comparison_section,
                spell_and_talent_rows=(
                    tuple(_ledger_row(finding, titles_by_id) for finding in comparison)
                    if is_subject
                    else ()
                ),
            )
        )
    return tuple(cards)


def _header(loaded: LoadedRun) -> Header:
    run = loaded.run
    verb = "Timed" if run.keystone_bonus >= 1 else "Depleted"
    duration = format_seconds(run.keystone_time_seconds)
    assert duration is not None  # keystone_time_seconds is never None
    return Header(
        dungeon=run.dungeon_name,
        keystone_level=run.keystone_level,
        affixes=(
            run.affix_names
            if run.affix_names
            else tuple(str(affix_id) for affix_id in run.affix_ids)
        ),
        result=f"{verb} in {duration}",
    )


def parent_of(finding_id: str) -> str | None:
    """The figure this one is already contained by, if any."""
    for prefix, parent in NESTS_INSIDE:
        if finding_id.startswith(prefix):
            return parent
    return None


def _ledger_row(finding: Finding, titles_by_id: dict[str, str]) -> LedgerRow:
    """Format one finding for display.

    `nests_inside` carries the parent finding's title, not its id: the id is
    an internal identifier and never belongs on a page a person reads. When
    the parent finding is not among this run's findings, `nests_inside` stays
    `None` — a pointer to a row that is not on the page is worse than silence.
    """
    parent_id = parent_of(finding.id)
    return LedgerRow(
        finding_id=finding.id,
        title=finding.title,
        detail=finding.detail,
        badge=badge_for(finding.confidence),
        seconds=format_seconds(finding.seconds_lost),
        nests_inside=titles_by_id.get(parent_id) if parent_id is not None else None,
        evidence=finding.evidence,
    )


def _placed_finding_ids(
    ledger_decomposition: Sequence[LedgerRow],
    placed_rows: dict[str, tuple[LedgerRow, ...]],
    players: Sequence[PlayerCard],
) -> set[str]:
    """Every finding id some field already claims.

    Read back off the fields themselves rather than recomputed from a prefix
    list: this is what keeps `build_observations` a structural partition
    instead of a second whitelist someone has to remember to update.
    """
    ids = {row.finding_id for row in ledger_decomposition}
    for rows in placed_rows.values():
        ids |= {row.finding_id for row in rows}
    for card in players:
        ids |= {row.finding_id for row in card.damage_rows}
        ids |= {row.finding_id for row in card.spell_and_talent_rows}
    return ids


def build_observations(
    findings: Sequence[Finding], placed_ids: set[str], titles_by_id: dict[str, str]
) -> tuple[LedgerRow, ...]:
    """Every finding no other section placed, in the order the analysis produced them.

    A finding lands here because it is missing from `placed_ids`, never
    because it matches an id prefix of its own — so an analyser that starts
    emitting a new finding family reaches the page automatically instead of
    being silently dropped until someone adds its prefix to a whitelist.
    """
    return tuple(
        _ledger_row(finding, titles_by_id) for finding in findings if finding.id not in placed_ids
    )


def build_report(
    loaded: LoadedRun,
    findings: Sequence[Finding],
    speed: SpeedReference | None,
    parse: ParseReference | None,
    subject: Player,
    narrative: str | None,
    fetched_at: str,
    defensives: Defensives,
    consumables: Consumables,
    externals: Externals = Externals(),
    self_resurrections: SelfResurrections = SelfResurrections(),
    speed_sample: SpeedSample | None = None,
    reference_records: tuple[ReferenceRecord, ...] = (),
) -> Report:
    """Everything the page shows, decided here so the template decides nothing.

    `fetched_at` is a parameter rather than a clock read: the domain performs no
    I/O, and the same inputs must render the same report. `subject` is the
    player being analysed, from our own roster — it decides whose card carries
    the spell-and-talent and uptime comparison rows. `defensives` is passed in
    rather than read here for the same reason the clock is: the data file is an
    adapter's job to load. `externals` and `self_resurrections` are data files
    too, loaded by the same adapter; they default to empty so a caller without
    them still builds every other section.

    `speed` alone still decides whether a speed comparison ran at all — the
    timeline and route sections stay gated on it. `speed_sample` is the full
    sample the timeline draws its best-aligned duration-eligible member from;
    a caller with no sample still gets a report, just with an empty timeline.
    `reference_records` is every candidate `_samples` weighed, loaded or not —
    carried onto the provenance unchanged, a link and never a figure.
    """
    timeline_section = _section_for(findings, SPEED_UNAVAILABLE_ID, speed is not None)

    withheld: list[str] = []
    if timeline_section.state is SectionState.WITHHELD:
        withheld.append(f"Aligned timeline: {timeline_section.reason}")

    comparison_section = _section_for(findings, PARSE_UNAVAILABLE_ID, parse is not None)
    if comparison_section.state is SectionState.WITHHELD:
        withheld.append(f"Spell and talent comparison: {comparison_section.reason}")

    route_section = _section_for(findings, SPEED_UNAVAILABLE_ID, speed is not None)
    if route_section.state is SectionState.WITHHELD:
        withheld.append(f"Route and tempo: {route_section.reason}")

    titles_by_id = {finding.id: finding.title for finding in findings}

    ledger_decomposition = tuple(
        _ledger_row(finding, titles_by_id)
        for finding in findings
        if finding.seconds_lost is not None and finding.id in DECOMPOSITION_IDS
    )
    decomposition_ids = {row.finding_id for row in ledger_decomposition}
    placed_rows = place_rows(findings, titles_by_id, exclude=decomposition_ids)
    summary_pointers = build_summary_pointers(findings, titles_by_id, exclude=decomposition_ids)
    players = build_players(loaded, findings, parse, subject, titles_by_id)
    placed_ids = _placed_finding_ids(ledger_decomposition, placed_rows, players)

    deaths = build_deaths(loaded, defensives, consumables, externals, self_resurrections)
    methods = (HEALTH_METHOD,) if any(card.health_badge for card in deaths) else ()

    return Report(
        header=_header(loaded),
        narrative=narrative,
        ledger_decomposition=ledger_decomposition,
        summary_pointers=summary_pointers,
        timeline=build_timeline(loaded.run, speed_sample, timeline_section),
        route=route_section,
        route_rows=placed_rows["route_rows"],
        deaths=deaths,
        death_rows=placed_rows["death_rows"],
        interrupts=placed_rows["interrupts"],
        players=players,
        group_rows=placed_rows["group_rows"],
        observations=build_observations(findings, placed_ids, titles_by_id),
        provenance=Provenance(
            report_code=loaded.run.report_code,
            fight_id=loaded.run.fight_id,
            fetched_at=fetched_at,
            references=reference_records,
            withheld=tuple(withheld),
            methods=methods,
        ),
    )
