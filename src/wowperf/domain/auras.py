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
    strips the auras the player was carrying, and on report cW38jmwdnZfbHVL4
    fight 30, all 21 player deaths, Warcraft Logs timestamps that strip at the
    millisecond the killing blow landed -- so a defensive that was genuinely up
    sits exactly on its band's *upper* boundary
    (`analysis/recap.py::_press_state`, design section 8). A press sits exactly
    on the *lower* boundary of the band it opened, which is what lets
    `report/deaths.py::_press_band` draw a cover window at all. Narrowing
    either end to a half-open interval would turn every correct `held` into a
    false accusation and leave every press without its rectangle, silently.
    `tests/domain/test_auras.py` pins both boundaries against the real
    timestamps that made this load-bearing.

    **Widening either end would not be the other half of that.** Across 105
    deaths on eleven fights the strip lands 1 to 3 ms *before* the blow on two
    of them, which a closed interval misses by a millisecond; the width that
    would cover it has no measurement behind it, so `strip_instant` answers
    that case instead and this stays exact (design section 8.3).
    """
    clipped = _clip_to_window(aura, start_ms, end_ms)
    holding = [(low, high) for low, high in clipped if low <= at_ms <= high]
    return holding[-1] if holding else None


STRIPPED_CO_ENDING_ABILITIES = 7
"""The bottom of the measured *stripped* cluster, counted in distinct abilities.

Design section 8.3 measured 7 to 21 co-ending **bands** where a death had
stripped an ability, against 0 or 1 where it had expired, with nothing in
between. This module counts distinct **abilities**, and the edge is the same 7
there: of the 140,366 runs of adjacent band ends in the 133 cached aura tables,
only 195 carry one ability twice and the largest of those holds 6 bands, so no
run of seven ends or more counts an ability twice and the two units coincide
exactly over the range this reads. Taken as the cluster's own edge rather than
as a midpoint: at or above it the death stripped the aura, and between the two
edges nothing measured decides, which `analysis/recap.py::_press_state` answers
with `pressed`.
"""

EXPIRED_CO_ENDING_ABILITIES = 1
"""The top of the measured *expired* cluster, counted in distinct abilities.

Re-derived in the same unit from the cached tables, over the rows section 8.3
calls genuinely expired, matched by the band lengths it records (Divine Shield
8010 ms, Divine Protection 8009, Spell Reflection 4995-4998, Feint 6013, Ice
Barrier 2411, Prismatic Barrier 18984, Dark Pact 3988): **0 co-ending abilities
15 times, 1 co-ending ability 20 times, and never more.** At or below this the
aura table's own reading stands, and a defensive that ran out still reads
`faded` rather than being softened into a doubt.
"""


def _instants(auras: PlayerAuras, at_ms: int) -> list[tuple[int, int, set[int]]]:
    """Every instant at or before `at_ms` where bands of this player end, oldest first.

    Each is the first and last millisecond of the instant and the abilities
    ending in it -- a span rather than a point, because the log spreads one
    removal over a few milliseconds.
    Band ends on consecutive milliseconds are one instant: a millisecond is the
    finest gap the log can express, so the width is the clock's own resolution
    rather than a number chosen to fit.

    **It is load-bearing even so, and calling it "not a tolerance" would
    overstate it.** Grouping only exact-equal milliseconds splits the worked
    example's strip into instants of one, four and five abilities, none of them
    a strip, and the ability in question loses its answer. What bounds the risk
    in the other direction is that adjacency does not chain: over the 133 cached
    aura tables, of 140,366 such runs 138,031 are a single millisecond wide and
    the widest is 4 ms.
    """
    ends = sorted(
        (band.end_ms, one.ability_id)
        for one in auras.on_self
        for band in one.bands
        if band.end_ms <= at_ms
    )
    instants: list[tuple[int, int, set[int]]] = []
    for end_ms, ability_id in ends:
        if not instants or end_ms - instants[-1][1] > 1:
            instants.append((end_ms, end_ms, set()))
        first_ms, _, abilities = instants[-1]
        abilities.add(ability_id)
        instants[-1] = (first_ms, end_ms, abilities)
    return instants


def last_band_end(aura: Aura, at_ms: int) -> int | None:
    """When this aura last stopped being up at or before `at_ms`, or None if never.

    The one band the strip reading is about: an ability pressed in a death's
    run-up has ended by the time the blow lands, or `band_holding` would have
    answered for it already.
    """
    ends = [band.end_ms for band in aura.bands if band.end_ms <= at_ms]
    return max(ends) if ends else None


def strip_instant(auras: PlayerAuras, since_ms: int, at_ms: int) -> tuple[int, int] | None:
    """The last instant at or before `at_ms` where a death unmistakably stripped this player.

    A death strips what the player was carrying, and Warcraft Logs timestamps
    that strip a few milliseconds before the death event -- sometimes before
    the killing blow as well, which is what `band_holding` alone cannot see
    (`analysis/recap.py::_press_state`, design section 8.3). Several of one
    player's *independent* auras ending at the same instant is that removal,
    not each of them expiring: on the worked example two raid buffs over 218
    seconds long and a 30.8-second rune end within 2 ms of each other, which no
    natural expiry explains.

    **The latest instant that is a strip, not the instant holding the latest
    band end.** An unrelated aura ending between the strip and the death would
    otherwise be anchored on, its instant would hold one ability, and every
    defensive the death had just stripped would fall back to `faded` -- the
    accusation this exists to withdraw. That shape is real: of the 188 runs of
    seven abilities or more in the cached tables, 14 are followed by another
    band end 2 to 60 ms later and 7 of those within 15 ms.

    An instant qualifies when it holds more than `STRIPPED_CO_ENDING_ABILITIES`
    abilities, so that any one of them has that many co-enders beside it. An
    older pile-up -- a keystone party leaving combat drops a dozen procs
    together -- is passed over for any strip after it, and a death strips
    everything the player carried, which is what usually makes one.

    Returns the instant's **first and last millisecond**, because a band counts
    as stripped by it only when it *ends inside* it. A band that merely runs
    through the instant and ends later was not removed by it, and reading it as
    though it were is a false credit that grows with the reach-back below.

    **`since_ms` is what stops the reach-back running away, and it is the
    press's own moment.** Where the death's removal does not qualify -- a player
    carrying fewer than eight auras when they died -- the search keeps walking
    back. Task 10 measured that on live data: no qualifying instant on 31 of 105
    deaths, and on 5 of them the search reached an older one, once by **1777
    seconds**. A band cannot end before the press that opened it, so no instant
    before the **earliest** press in the run-up can be the strip of a band
    those presses opened. `analysis/recap.py::state_of` passes the earliest and
    not the latest for exactly that reason. It is a bound the log itself
    provides, not a look-back tolerance in milliseconds -- the constant this
    design has refused throughout.

    **It is a cut rather than a proof in one direction, and saying otherwise
    would overstate it.** What is read is the aura's latest band end at or
    before the death, which can belong to a press older than the run-up, so
    "excludes nothing that could have been right" is not true as stated. What
    *is* exact: a death's own strip sits within milliseconds of the death, so no
    bound inside the run-up can exclude one. What the bound excludes is older
    instants -- the residual below -- and its worst-case reach is now
    `RUN_UP_SECONDS`, itself a chosen constant, pre-existing and justified
    elsewhere.

    **It was reachable, not merely untidy.** The tempting argument is that an
    ancient instant can never hold a run-up press's band, and that is true of
    the band *this press opened*. It is not true of what is read: the aura's
    latest band end at or before the death, which falls back to a previous use
    when the press has no band of its own. `tests/domain/analysis/` carries the
    death that answered `held` on a band 1777 seconds stale before this bound.

    **What remains is bounded, not gone.** An older pile-up *inside* the run-up
    can still answer for a death whose own removal is too small -- a keystone
    party leaving combat drops a dozen procs together -- and a defensive ending
    there reads `held` for an instant that was not the death's, which is the
    false credit design section 6 puts second. Separating those needs the
    tolerance above, so the residual is recorded rather than patched, now at the
    size of a run-up rather than of a fight. `analysis/recap.py` pins it.
    """
    for first_ms, last_ms, abilities in reversed(_instants(auras, at_ms)):
        if last_ms < since_ms:
            break
        if len(abilities) > STRIPPED_CO_ENDING_ABILITIES:
            return first_ms, last_ms
    return None


def co_ending_abilities(auras: PlayerAuras, aura: Aura, at_ms: int) -> int:
    """How many of this player's other abilities end with this one's last band.

    The band is this aura's latest ending at or before `at_ms`, and the count is
    of the other abilities ending at the same instant. What it is for is the
    reading between the two measured clusters: too many to be the expiry
    `EXPIRED_CO_ENDING_ABILITIES` describes, too few to be the strip
    `STRIPPED_CO_ENDING_ABILITIES` does. Zero when the aura has no band ended by
    then, which is nothing ending with it and reads as the expiry it looks like.
    """
    last = last_band_end(aura, at_ms)
    if last is None:
        return 0
    holding = next(
        (
            abilities
            for first_ms, _, abilities in reversed(_instants(auras, at_ms))
            if first_ms <= last
        ),
        set(),
    )
    return len(holding - {aura.ability_id})
