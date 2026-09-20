# ABOUTME: Aura intervals as pure values, plus the arithmetic that reads them: uptime over
# ABOUTME: an arbitrary window, resolving a cast id to its own aura, and clipping bands to a window.

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

    **The interval is closed at both ends, and callers depend on it.** A death
    strips the auras the player was carrying, and Warcraft Logs timestamps that
    strip at the millisecond the killing blow landed -- measured on report
    cW38jmwdnZfbHVL4 fight 30, all 23 player deaths -- so a defensive that was
    genuinely up sits exactly on its band's *upper* boundary and nowhere else
    (`analysis/recap.py::_press_state`, design section 8). A press sits exactly
    on the *lower* boundary of the band it opened, which is what lets
    `report/deaths.py::_press_band` draw a cover window at all. Narrowing
    either end to a half-open interval would turn every correct `held` into a
    false accusation and leave every press without its rectangle, silently.
    `tests/domain/test_auras.py` pins both boundaries against the real
    timestamps that made this load-bearing.
    """
    clipped = _clip_to_window(aura, start_ms, end_ms)
    holding = [(low, high) for low, high in clipped if low <= at_ms <= high]
    return holding[-1] if holding else None
