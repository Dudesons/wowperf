# ABOUTME: Aura intervals as pure values, plus uptime over an arbitrary window.
# ABOUTME: Warcraft Logs hands back the bands already computed; this is what reads them.

from wowperf.domain.base import Frozen


class AuraBand(Frozen):
    """One unbroken stretch during which an aura was present.

    Milliseconds relative to report start, the same clock as `Pull.start_ms`.
    """

    start_ms: int
    end_ms: int


class Aura(Frozen):
    """One buff or debuff, with every interval it was up for.

    `icon` is the aura table's own `abilityIcon`, and it is the only source for
    a passive aura's art. A talent that is permanently applied is never cast,
    so its id reaches no cast dictionary and the report can address its icon
    from nowhere else. Empty when the table did not name one.
    """

    ability_id: int
    name: str
    total_uptime_ms: int
    uses: int
    icon: str = ""
    bands: tuple[AuraBand, ...] = ()


class PlayerAuras(Frozen):
    """What one player carried, as the aura table reports it.

    The design's other half, "on target", has no counterpart here: no query
    argument narrows the enemy-debuff table to one caster, so a per-player
    figure for what a player kept up on enemies is not available from this API
    (`.claude/skills/wcl-api/SKILL.md`, "The debuff half cannot be scoped to one
    caster").
    """

    actor_id: int
    on_self: tuple[Aura, ...] = ()


def uptime_seconds_in(aura: Aura, windows: tuple[tuple[int, int], ...]) -> float:
    """Seconds this aura was up, on at least one target, inside the given windows.

    Bands are clipped to each window rather than counted whole, which is what
    makes a boss-pull-only figure exact rather than an approximation. The
    clipped intervals are then merged before summing, so overlap contributes
    once rather than once per overlapping band or window: nothing in the aura
    table's own response promises the bands it hands back are disjoint, and
    summing the union rather than the parts is the only reading that cannot
    exceed the window length.
    """
    clipped: list[tuple[int, int]] = []
    for band in aura.bands:
        for start, end in windows:
            lo = max(band.start_ms, start)
            hi = min(band.end_ms, end)
            if hi > lo:
                clipped.append((lo, hi))

    if not clipped:
        return 0.0

    clipped.sort()
    total_ms = 0
    merged_start, merged_end = clipped[0]
    for lo, hi in clipped[1:]:
        if lo <= merged_end:
            merged_end = max(merged_end, hi)
        else:
            total_ms += merged_end - merged_start
            merged_start, merged_end = lo, hi
    total_ms += merged_end - merged_start

    return total_ms / 1000
