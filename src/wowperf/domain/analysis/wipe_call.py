# ABOUTME: The wipe call: a pull is lost at its fourth roster death, and a kill past it is dirty.
# ABOUTME: One fixed count, the one raid leaders call, measured on twenty-player pulls only.

from collections.abc import Sequence

from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death

WIPE_CALL_DEATHS = 4
"""The roster death at which a wipe is lost and a kill is dirty.

Measured 2026-10-07 offline on 37 cached twenty-player pulls, 9 kills and 28
wipes (`cW38jmwdnZfbHVL4` Heroic, `6jHcTvtB4XAMGZag` Mythic). One kill reached
a fourth death, 12 s before the boss died; no other passed three. 26 wipes
reached it, a median 15 s before their end, and 77% of all wipe deaths came
after it. A fixed count rather than a share of the roster: no pull of another
size was measured, and four is the count raid leaders call. Design
`docs/plans/2026-10-07-wipe-call-design.md` section 3.
"""

CALL_ORDINAL = f"{WIPE_CALL_DEATHS}th"
"""How the page names the call's death. "th" is right for every count from 4 to 20."""


def death_order(death: Death) -> tuple[int, int]:
    """The order deaths are counted in: by time, ties to the lowest actor id.

    The rule `first_roster_death` breaks ties by, so a stream listing two
    simultaneous deaths in either order names the same call.
    """
    return (death.timestamp_ms, death.actor_id)


def roster_deaths_in_order(loaded: LoadedEncounter) -> tuple[Death, ...]:
    """Every roster player's death, in `death_order`.

    Filtered to `loaded.players` as `roster_deaths` filters: a pet or an
    unidentified actor dying is not a roster death. A player who is
    battle-resurrected and dies again is in here twice, as a raid leader
    counts them.
    """
    roster_ids = {player.actor_id for player in loaded.players}
    return tuple(
        sorted((death for death in loaded.deaths if death.actor_id in roster_ids), key=death_order)
    )


def lost_at(loaded: LoadedEncounter) -> Death | None:
    """The roster death a wipe is lost at, or None on a kill or a wipe short of the call."""
    if loaded.encounter.kill:
        return None
    ordered = roster_deaths_in_order(loaded)
    if len(ordered) < WIPE_CALL_DEATHS:
        return None
    return ordered[WIPE_CALL_DEATHS - 1]


def is_dirty(loaded: LoadedEncounter) -> bool:
    """A kill with the call's count of roster deaths or more. A wipe never is."""
    return loaded.encounter.kill and len(roster_deaths_in_order(loaded)) >= WIPE_CALL_DEATHS


def deaths_after(deaths: Sequence[Death], lost: Death) -> tuple[Death, ...]:
    """Every death strictly after the call, roster or not: what the death cards leave out.

    Not filtered to the roster, because the death cards are not: a card is
    drawn for every death the log lists, and this counts the cards not drawn.
    """
    return tuple(death for death in deaths if death_order(death) > death_order(lost))
