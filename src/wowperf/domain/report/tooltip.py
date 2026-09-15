# ABOUTME: What one event of a death is worth saying, as labelled lines the page prints.
# ABOUTME: Reports the fields of a single event and apportions none of them between causes.

from wowperf.domain.analysis.recap import HIT, RecapEvent
from wowperf.domain.auras import PlayerAuras
from wowperf.domain.events import CastEvent, DamageTakenEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.report.cover import clipped_bands, resolve_aura
from wowperf.domain.report.frame import badge_for
from wowperf.domain.report.model import Tooltip, TooltipLine

MITIGATION_IS_NOT_ATTRIBUTED = (
    "The log does not attribute what reduced this hit: armour, Versatility, spec passives, a "
    "defensive and a teammate's external all land in one figure."
)
"""Said wherever a single hit's `mitigated` is printed, in `hit_tooltip`.

The figure is real and the causes are not separable, so the tooltip states the
one and refuses the other. Printing the figure without this sentence invites
exactly the reading the design's section 5 forbids.
"""

MITIGATION_IS_NOT_ATTRIBUTED_OVER_A_RUN = (
    "The log does not attribute what reduced these hits: armour, Versatility, spec passives, a "
    "defensive and a teammate's external all land in one figure, for every hit summed here."
)
"""Said in `ability_tooltip`, which sums `mitigated` over every hit inside a run's window
rather than reporting one hit's own figure -- `MITIGATION_IS_NOT_ATTRIBUTED`'s "this hit"
does not fit a panel describing an ability across a run, not a single event of it."""

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
    """What share of the swing the game mitigated, as a whole percent.

    Computed from `mitigated` over `amount` -- the unmitigated swing --
    deliberately never from what reached health: `amount - health_damage`
    also carries `absorbed`, and a shield soaking a hit is not the game
    reducing it. `hit_tooltip` already keeps the two apart as "Mitigated" and
    "Reached health" (with a shield's own share on its own "Absorbed" line),
    and this rate follows the same split. An empty side reads as a dash
    rather than as zero: no hits is not the same claim as hits that were
    never reduced.
    """
    swung = sum(hit.amount for hit in hits)
    if swung == 0:
        return "--"
    mitigated = sum(hit.mitigated for hit in hits)
    return f"{round(100 * mitigated / swung)}%"


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
        # A base length from `data/defensives.toml`, not anything the log
        # said -- the same assumption the run timeline's own inferred badge
        # already grades on the drawing beside it.
        TooltipLine(
            label="Base cooldown", value=f"{cooldown_seconds:.0f} s",
            tier=badge_for(Confidence.INFERRED),
        ),
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
                tier=badge_for(Confidence.DERIVED),
            )
        )
    return Tooltip(
        lines=tuple(lines),
        note=f"{MITIGATION_IS_NOT_ATTRIBUTED_OVER_A_RUN} {RATE_GAP_IS_SUGGESTIVE}",
    )


def press_tooltip(
    band: tuple[int, int], death_ms: int, events: tuple[RecapEvent, ...]
) -> Tooltip:
    """What one press of a self-buff covered, and what arrived inside that cover.

    `band` is the one band of the press's own aura that holds the cast,
    already clipped to the run-up the card draws -- the same band, from the
    same call, that the card draws as a rectangle over its health curve. Every
    figure here is therefore scoped to what that rectangle claims, and the two
    cannot disagree: a press whose buff outlived the card reports only the
    part the card saw, never the buff's full length, and says the buff was
    still up rather than naming the death's own moment as an expiry.

    Hits are placed inside the cover by timestamp rather than by their own
    `buff_ids`, which is the opposite of `_inside`'s preference and is
    deliberate. `_inside` serves `ability_tooltip`, whose windows are merged
    across a whole run and so are coarser than the truth; one press's band is
    exactly the drawing beside it, and matching the drawing is what this panel
    is for.

    No mitigation figure appears, so no attribution note is needed. Summing
    `mitigated` over one press's own window is precisely the "this press
    prevented that much" reading the design's section 5 refuses, and there is
    no inside-versus-outside comparison here to give such a sum meaning.
    """
    start_ms, end_ms = band
    inside = tuple(
        event for event in events
        if event.kind == HIT and start_ms <= event.timestamp_ms <= end_ms
    )
    lines = [
        TooltipLine(label="Cover", value=f"{(end_ms - start_ms) / 1000:.1f} s"),
        TooltipLine(
            label="Ran out",
            value="still up at the death" if end_ms >= death_ms
            else f"{(death_ms - end_ms) / 1000:.1f} s before the death",
        ),
        TooltipLine(
            label="Arrived while it was up",
            value=f"{sum(event.unmitigated for event in inside):,}",
        ),
    ]
    absorbed = sum(event.absorbed for event in inside)
    if absorbed:
        lines.append(TooltipLine(label="Absorbed", value=f"{absorbed:,}"))
    lines.append(
        TooltipLine(
            label="Reached health", value=f"{sum(event.amount for event in inside):,}"
        )
    )
    return Tooltip(lines=tuple(lines))


def run_ability_tooltip(
    ability_id: int,
    ability_name: str,
    cooldown_seconds: float,
    owner_id: int,
    casts: tuple[CastEvent, ...],
    auras: PlayerAuras | None,
    hits: tuple[DamageTakenEvent, ...],
    window: tuple[int, int],
    on_target: int | None = None,
) -> Tooltip | None:
    """What the run measured about one ability, against one player's own aura table.

    None where no aura table was fetched for that player, or where neither the
    ability's own id nor its name matched an aura it carries -- the same two
    reasons a cooldown row's own cover can be empty, since both read the same
    table through `resolve_aura`.

    `on_target` scopes the press count to casts that could have been meant for
    the player in question: aimed at them, or aimed at no one in particular
    (an untargeted cast covers an area or the whole group). None on a player's
    own defensive, which needs no such scoping -- every press is already "for"
    them. Set to the subject's own id for a teammate's external, matching the
    rule `analysis/recap.py:state_of` already applies to that row's own
    PRESSED state: a cast on someone else was a use, not a save, and the
    tooltip beside that row must not disagree with it.

    Generic over its window, which is what lets a death card and a ledger card
    share it: a death passes the run-up it draws, a ledger card passes the
    whole run. Generic over its fight for the same reason, and by the same
    means: `casts` is the one stream this counts presses from, so a keystone
    run and a boss fight each hand over their own and neither is named here.
    """
    if auras is None:
        return None
    aura = resolve_aura(auras, ability_id, ability_name)
    if aura is None:
        return None
    start_ms, end_ms = window
    presses = sum(
        1 for cast in casts
        if cast.actor_id == owner_id and cast.ability_id == ability_id
        and (on_target is None or cast.target_id in (on_target, None))
    )
    return ability_tooltip(
        cooldown_seconds=cooldown_seconds,
        cover=clipped_bands(aura, start_ms, end_ms),
        hits=hits,
        # The aura table keys a buff on itself, not on the spell cast to apply
        # it -- `resolve_aura`'s own docstring names the abilities where the
        # two ids differ. Comparing a hit's `buff_ids` against the cast id
        # here would silently match nothing for exactly those abilities.
        buff_id=aura.ability_id,
        presses=presses,
    )
