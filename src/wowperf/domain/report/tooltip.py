# ABOUTME: What one event of a death is worth saying, as labelled lines the page prints.
# ABOUTME: Reports the fields of a single event and apportions none of them between causes.

from wowperf.domain.analysis.recap import RecapEvent
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


def heal_tooltip(event: RecapEvent, names: dict[int, str]) -> Tooltip:
    """One heal that landed, and who cast it."""
    source = event.source_id
    caster = "an unknown source" if source is None else names.get(source, "an unknown source")
    return Tooltip(
        lines=(
            TooltipLine(label="Healed for", value=f"{event.amount:,}"),
            TooltipLine(label="From", value=caster),
        ),
        note=NO_OVERHEAL_FIELD,
    )


def absorb_tooltip(event: RecapEvent, names: dict[int, str]) -> Tooltip:
    """One shield, and the hit it soaked."""
    source = event.source_id
    caster = "an unknown source" if source is None else names.get(source, "an unknown source")
    return Tooltip(
        lines=(
            TooltipLine(label="Soaked", value=f"{event.amount:,}"),
            TooltipLine(label="Shield from", value=caster),
        )
    )
