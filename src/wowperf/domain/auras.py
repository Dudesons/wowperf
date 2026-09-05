# ABOUTME: Buff and debuff intervals as pure values, plus uptime over an arbitrary window.
# ABOUTME: Warcraft Logs hands back the bands already computed; this is what reads them.

from wowperf.domain.base import Frozen


class AuraBand(Frozen):
    """One unbroken stretch during which an aura was present.

    Milliseconds relative to report start, the same clock as `Pull.start_ms`.
    """

    start_ms: int
    end_ms: int


class Aura(Frozen):
    """One buff or debuff, with every interval it was up for."""

    ability_id: int
    name: str
    total_uptime_ms: int
    uses: int
    bands: tuple[AuraBand, ...] = ()


class PlayerAuras(Frozen):
    """The two halves of one player's aura picture.

    `on_self` is what the player carried; `on_targets` is meant to be what they
    kept up on enemies, but is always empty against the live API today —
    confirmed 2026-09-05, no query argument narrows the enemy-debuff table to
    one caster (`.claude/skills/wcl-api/SKILL.md`, "The debuff half cannot be
    scoped to one caster"). The design calls these "on self and on target".
    """

    actor_id: int
    on_self: tuple[Aura, ...] = ()
    on_targets: tuple[Aura, ...] = ()


def uptime_seconds_in(aura: Aura, windows: tuple[tuple[int, int], ...]) -> float:
    """Seconds this aura was up, on at least one target, inside the given windows.

    Bands are clipped to each window rather than counted whole, which is what
    makes a boss-pull-only figure exact rather than an approximation. The
    clipped intervals are then merged before summing, so overlap contributes
    once rather than once per overlapping band or window: a debuff table
    aggregates every enemy the player hit, and a damage-over-time effect
    ticking on several targets at once produces bands that overlap in
    wall-clock time. Summing the union rather than the parts is also the only
    reading that cannot exceed the window length.
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
