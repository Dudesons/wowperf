# ABOUTME: What one event of a death is worth saying, as labelled lines the page prints.
# ABOUTME: Reports the fields of a single event and apportions none of them between causes.

from wowperf.domain.analysis.recap import RecapEvent
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.report.model import Tooltip, TooltipLine

MITIGATION_IS_NOT_ATTRIBUTED = (
    "The log does not attribute what reduced this hit: armour, Versatility, spec passives, a "
    "defensive and a teammate's external all land in one figure."
)
"""Said wherever `mitigated` is printed.

The figure is real and the causes are not separable, so the tooltip states the
one and refuses the other. Printing the figure without this sentence invites
exactly the reading the design's section 5 forbids.
"""

NO_OVERHEAL_FIELD = (
    "The healing stream reports no overheal, so this is what landed, not what was wasted."
)
"""Recorded 2026-09-06 in the wcl-api skill. Saying so beats omitting the row in silence."""


def hit_tooltip(event: RecapEvent) -> Tooltip:
    """One hit, in the four figures the log gives for it.

    `unmitigated` is how hard it swung, `mitigated` what the game took off,
    `absorbed` what a shield soaked and `amount` what reached health. Overkill
    appears only where the log recorded it, which is only on a lethal blow.

    Names no source, though `event.source_id` carries the enemy that dealt the
    hit. `EnemyNpc` in `wowperf.domain.model` holds only `actor_id` and
    `game_id` -- no name -- so there is nothing here to resolve the id
    against. `masterData.actors` carries a name for every actor in the
    report, but ingest reads it only for player actors
    (`_build_players` in `adapters/wcl/ingest.py`); naming an enemy would need
    that same lookup carried onto `EnemyNpc` and through to `LoadedRun`, work
    the size of what Task 2 already did for the player roster, which this
    plan does not do.
    """
    lines = [
        TooltipLine(label="Struck for", value=f"{event.unmitigated:,}"),
        TooltipLine(label="Mitigated", value=f"{event.mitigated:,}"),
    ]
    if event.absorbed:
        lines.append(TooltipLine(label="Absorbed", value=f"{event.absorbed:,}"))
    lines.append(TooltipLine(label="Reached health", value=f"{event.amount:,}"))
    if event.overkill:
        lines.append(TooltipLine(label="Overkill", value=f"{event.overkill:,}"))
    if event.is_area:
        lines.append(TooltipLine(label="Area", value="yes"))
    if event.is_tick:
        lines.append(TooltipLine(label="Periodic", value="yes"))
    return Tooltip(lines=tuple(lines), note=MITIGATION_IS_NOT_ATTRIBUTED)


def caster_name(source_id: int | None, names: dict[int, str]) -> str:
    """Who cast something, by actor id.

    "an unknown source" when the log named no caster at all, or when the id it
    named is not one `names` covers.
    """
    return "an unknown source" if source_id is None else names.get(source_id, "an unknown source")


def heal_tooltip(event: RecapEvent, names: dict[int, str]) -> Tooltip:
    """One heal that landed, and who cast it."""
    return Tooltip(
        lines=(
            TooltipLine(label="Healed for", value=f"{event.amount:,}"),
            TooltipLine(label="From", value=caster_name(event.source_id, names)),
        ),
        note=NO_OVERHEAL_FIELD,
    )


def absorb_tooltip(event: RecapEvent, names: dict[int, str]) -> Tooltip:
    """One shield, and the hit it soaked."""
    return Tooltip(
        lines=(
            TooltipLine(label="Soaked", value=f"{event.amount:,}"),
            TooltipLine(label="Shield from", value=caster_name(event.source_id, names)),
        )
    )


RATE_GAP_IS_SUGGESTIVE = (
    "The gap between the two rates is suggestive, not attributable: this ability is one of "
    "several things reducing every hit, and the log separates none of them."
)


def _inside(hit: DamageTakenEvent, buff_id: int, cover: tuple[tuple[int, int], ...]) -> bool:
    """Whether this hit landed while the buff was up.

    The event's own `buffs` list is exact per hit and is the answer wherever the
    log wrote one. Only where it wrote none does this fall back to the aura
    table's bands, which place the hit by timestamp rather than by what the game
    said was on the player.
    """
    if hit.buff_ids:
        return buff_id in hit.buff_ids
    return any(start <= hit.timestamp_ms <= end for start, end in cover)


def _rate(hits: tuple[DamageTakenEvent, ...]) -> str:
    """What share of what swung never reached health, as a whole percent.

    An empty side reads as a dash rather than as zero: no hits is not the same
    claim as hits that were never reduced.
    """
    swung = sum(hit.amount for hit in hits)
    if swung == 0:
        return "--"
    landed = sum(hit.health_damage for hit in hits)
    return f"{round(100 * (swung - landed) / swung)}%"


def ability_tooltip(
    cooldown_seconds: float,
    cover: tuple[tuple[int, int], ...],
    hits: tuple[DamageTakenEvent, ...],
    buff_id: int,
    presses: int,
) -> Tooltip:
    """What the run measured about one ability, and what it refuses to conclude.

    Every figure is a field the log emitted, or a sum of such fields over a
    window the aura table stated. The inside/outside rates are derived from
    those sums and are offered as a comparison, never as damage this ability
    prevented -- see the design's section 5.
    """
    lines = [
        TooltipLine(label="Base cooldown", value=f"{cooldown_seconds:.0f} s"),
        TooltipLine(label="Presses", value=str(presses)),
    ]
    if cover:
        seconds = sum(end - start for start, end in cover) / 1000
        lines.append(TooltipLine(label="Cover", value=f"{seconds:.1f} s"))
        within = tuple(hit for hit in hits if _inside(hit, buff_id, cover))
        without = tuple(hit for hit in hits if not _inside(hit, buff_id, cover))
        lines.append(
            TooltipLine(
                label="Arrived while it was up",
                value=f"{sum(hit.amount for hit in within):,}",
            )
        )
        lines.append(
            TooltipLine(
                label="Reached health",
                value=f"{sum(hit.health_damage for hit in within):,}",
            )
        )
        lines.append(
            TooltipLine(
                label="Mitigated inside / outside",
                value=f"{_rate(within)} / {_rate(without)}",
            )
        )
    return Tooltip(
        lines=tuple(lines),
        note=f"{MITIGATION_IS_NOT_ATTRIBUTED} {RATE_GAP_IS_SUGGESTIVE}",
    )
