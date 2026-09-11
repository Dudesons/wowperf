# ABOUTME: Aura bands clipped to a drawing's window, merged, as milliseconds.
# ABOUTME: One piece of arithmetic behind every cover window the report draws.

from wowperf.domain.auras import Aura, PlayerAuras


def resolve_aura(auras: PlayerAuras, ability_id: int, ability_name: str) -> Aura | None:
    """This player's own aura for the ability that cast it, by id first and by name second.

    The aura table is keyed by the id of the buff itself, while
    `data/defensives.toml` and `data/throughput_cooldowns.toml` record the id of
    the spell *cast* to apply it. For most abilities those are the same spell,
    but not always: Alter Time casts as 108978 and buffs as 342246, Greater
    Invisibility casts as 110959 and buffs as 110960. The id match is exact and
    always tried first; the name match is a heuristic fallback, tried only when
    the id finds nothing, and scoped to one player's own `on_self` list, where
    an unrelated ability sharing a name is not a realistic collision.
    """
    aura = next((one for one in auras.on_self if one.ability_id == ability_id), None)
    if aura is not None:
        return aura
    return next((one for one in auras.on_self if one.name == ability_name), None)


def _clip_to_window(aura: Aura, start_ms: int, end_ms: int) -> list[tuple[int, int]]:
    """Every band of this aura clipped to the window, oldest first, not merged.

    The shared first step of `clipped_bands` and `band_holding`: both need the
    same clipping, and only the former sums it into a total.
    """
    return sorted(
        (max(band.start_ms, start_ms), min(band.end_ms, end_ms))
        for band in aura.bands
        if min(band.end_ms, end_ms) > max(band.start_ms, start_ms)
    )


def clipped_bands(aura: Aura, start_ms: int, end_ms: int) -> tuple[tuple[int, int], ...]:
    """Every stretch this aura was up inside the window, merged, oldest first.

    Clipped rather than counted whole, so a band that began before the window
    contributes only the part the drawing covers. Merged for the reason
    `auras.uptime_seconds_in` merges: nothing in the aura table's own response
    promises the bands it hands back are disjoint, and two overlapping bands
    drawn as two rectangles paint the same second twice.
    """
    clipped = _clip_to_window(aura, start_ms, end_ms)
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


def band_holding(aura: Aura, start_ms: int, end_ms: int, at_ms: int) -> tuple[int, int] | None:
    """The one band of this aura, clipped to the window, that covers `at_ms`.

    Clipped like `clipped_bands`, but never merged. Merging answers "how much
    of the window did this aura cover in total", which is right for an uptime
    figure and wrong for one press: measured against the cached aura tables
    for report `6Kx1P9GbNXrcLdHa` (`.claude/skills/wcl-api/SKILL.md`,
    2026-09-11), bands on one aura touch or overlap often enough that two
    separate casts of the same defensive can produce bands `clipped_bands`
    would fold into a single merged span. Every press whose own timestamp
    falls inside that merged span would then draw the same cover window,
    each one's rectangle reaching into the duration the *other* press
    actually earned — a claim about how long one cast protected the player
    that nothing in the log stated. Returns the single band containing
    `at_ms`, or None if none does. Among bands containing a press, the one
    that starts latest is the one that press began, so ties -- two touching
    or overlapping bands both containing `at_ms` -- resolve to the last match
    in ascending order, never the first.
    """
    clipped = _clip_to_window(aura, start_ms, end_ms)
    holding = [(low, high) for low, high in clipped if low <= at_ms <= high]
    return holding[-1] if holding else None
