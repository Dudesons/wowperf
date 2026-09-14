# ABOUTME: Turns one playerDetails payload into a Loadout per actor id.
# ABOUTME: An unreadable stat block yields no stats rather than a guessed number.

from typing import Any

from wowperf.domain.loadout import EquippedItem, Loadout, StatBlock

ROLE_GROUPS = ("tanks", "healers", "dps")

STAT_FIELDS = {
    "Crit": "crit",
    "Haste": "haste",
    "Mastery": "mastery",
    "Versatility": "versatility",
    "Leech": "leech",
    "Avoidance": "avoidance",
    "Speed": "speed",
}
"""The stat block's own spellings, mapped to `StatBlock`'s fields.

`Item Level`, `Strength` and `Stamina` sit in the same block and are
deliberately absent: an item level is not a rating, and a primary stat is not
one a player trades against another.
"""


def _stats(block: Any) -> StatBlock | None:
    """The stat block, or None where it cannot be read as one number per stat.

    Every stat of every player measured on 2026-09-14 had `min` equal to `max`.
    A divergence means the rating moved during the fight, and choosing an end
    would be a modelling choice nothing here can justify, so the whole block is
    withheld. The items are still kept: they did not move.
    """
    if not isinstance(block, dict):
        return None
    values: dict[str, int] = {}
    for wire_name, field in STAT_FIELDS.items():
        reading = block.get(wire_name)
        if not isinstance(reading, dict):
            continue
        low, high = reading.get("min"), reading.get("max")
        if low is None or low != high:
            return None
        values[field] = int(low)
    return StatBlock(**values)


def _items(gear: Any) -> tuple[EquippedItem, ...]:
    if not isinstance(gear, list):
        return ()
    items = []
    for entry in gear:
        if not isinstance(entry, dict) or entry.get("id") is None:
            continue
        items.append(
            EquippedItem(
                item_id=int(entry["id"]),
                slot=int(entry.get("slot") or 0),
                name=str(entry.get("name") or ""),
                item_level=int(entry.get("itemLevel") or 0),
                enchant_id=entry.get("permanentEnchant") or None,
                enchant_name=entry.get("permanentEnchantName") or None,
                set_id=entry.get("setID") or None,
            )
        )
    return tuple(items)


def build_loadouts(payload: dict[str, Any]) -> dict[int, Loadout]:
    """One loadout per actor id, from a `PlayerDetails` response.

    A player whose `combatantInfo` is an empty list contributes nothing rather
    than an empty loadout: that is precisely what a query missing
    `includeCombatantInfo: true` returns for everybody, and an empty loadout
    would read as a player who equipped nothing.
    """
    details = ((payload.get("reportData") or {}).get("report") or {}).get("playerDetails")
    if not isinstance(details, dict):
        return {}
    roster = (details.get("data") or {}).get("playerDetails")
    if not isinstance(roster, dict):
        return {}

    loadouts: dict[int, Loadout] = {}
    for group in ROLE_GROUPS:
        for entry in roster.get(group) or []:
            info = entry.get("combatantInfo")
            if not isinstance(info, dict):
                continue
            actor_id = entry.get("id")
            if actor_id is None:
                continue
            loadouts[int(actor_id)] = Loadout(
                items=_items(info.get("gear")), stats=_stats(info.get("stats"))
            )
    return loadouts
