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

    `on_self` is what the player carried; `on_targets` is what they kept up on
    enemies. The design calls these "on self and on target".
    """

    actor_id: int
    on_self: tuple[Aura, ...] = ()
    on_targets: tuple[Aura, ...] = ()


def uptime_seconds_in(aura: Aura, windows: tuple[tuple[int, int], ...]) -> float:
    """Seconds this aura was up inside the given millisecond windows.

    Bands are clipped to each window rather than counted whole, which is what
    makes a boss-pull-only figure exact rather than an approximation.
    """
    total_ms = 0
    for band in aura.bands:
        for start, end in windows:
            overlap = min(band.end_ms, end) - max(band.start_ms, start)
            if overlap > 0:
                total_ms += overlap
    return total_ms / 1000
