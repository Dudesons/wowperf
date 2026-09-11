# ABOUTME: Aura bands clipped to a drawing's window, merged, as milliseconds.
# ABOUTME: One piece of arithmetic behind every cover window the report draws.

from wowperf.domain.auras import Aura


def clipped_bands(aura: Aura, start_ms: int, end_ms: int) -> tuple[tuple[int, int], ...]:
    """Every stretch this aura was up inside the window, merged, oldest first.

    Clipped rather than counted whole, so a band that began before the window
    contributes only the part the drawing covers. Merged for the reason
    `auras.uptime_seconds_in` merges: nothing in the aura table's own response
    promises the bands it hands back are disjoint, and two overlapping bands
    drawn as two rectangles paint the same second twice.
    """
    clipped = sorted(
        (max(band.start_ms, start_ms), min(band.end_ms, end_ms))
        for band in aura.bands
        if min(band.end_ms, end_ms) > max(band.start_ms, start_ms)
    )
    if not clipped:
        return ()
    merged = [clipped[0]]
    for low, high in clipped[1:]:
        last_low, last_high = merged[-1]
        if low <= last_high:
            merged[-1] = (last_low, max(last_high, high))
        else:
            merged.append((low, high))
    return tuple(merged)
