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
    player: str
    class_name: str
    when: str
    killing_blow: str
    last_ten_seconds: tuple[DamageRow, ...] = ()


class PlayerCard(Frozen):
    """One player's measured facts.

    `damage_rows` states damage against the group median, never as avoidable:
    the log does not record whether a hit could have been dodged, and this card
    follows the analyser that refuses that framing.
    """

    name: str
    class_name: str
    spec: str
    colour: str
    active_time: str
    deaths: int
    kicks: int
    damage_rows: tuple[LedgerRow, ...] = ()
    spell_and_talent: Section
    spell_and_talent_rows: tuple[LedgerRow, ...] = ()


class Header(Frozen):
    """No percentile: nothing this project fetches produces our own player's rank."""

    dungeon: str
    keystone_level: int
    affixes: tuple[str, ...] = ()
    result: str = ""
    warnings: tuple[str, ...] = ()


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
    ledger_losses: tuple[LedgerRow, ...]
    timeline: Timeline
    deaths: tuple[DeathCard, ...]
    interrupts: tuple[LedgerRow, ...]
    players: tuple[PlayerCard, ...]
    provenance: Provenance
