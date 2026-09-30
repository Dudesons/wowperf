# ABOUTME: Reads cached Warcraft Logs pages for the ability ids they cast and the names they give.
# ABOUTME: Only cast rows and ability tables are read; actors, and so player names, never are.

import json
from collections import Counter
from pathlib import Path
from typing import NamedTuple


class CachedIds(NamedTuple):
    """What the cache says about ability ids: how often each was cast, and every id a name has."""

    pages: int
    casts: dict[int, int]
    named: dict[str, frozenset[int]]


def scan_cache(directory: Path) -> CachedIds:
    """Every cast row and every ability-table entry across the pages under `directory`.

    A page is read wherever its rows sit, since a query can nest them under any
    alias: a cast row is any object with `type` "cast" and an integer
    `abilityGameID`, and an ability-table entry is any object inside an
    `abilities` list with an integer `gameID` and a string `name`. Paginated
    streams repeat rows at their boundaries, so a cast row is counted once per
    fight, caster, ability and timestamp.
    """
    rows: set[tuple[object, object, int, object]] = set()
    named: dict[str, set[int]] = {}
    pages = 0

    def walk(node: object, in_abilities: bool) -> None:
        if isinstance(node, dict):
            ability_id = node.get("abilityGameID")
            if node.get("type") == "cast" and isinstance(ability_id, int):
                rows.add((node.get("fight"), node.get("sourceID"), ability_id,
                          node.get("timestamp")))
            game_id, name = node.get("gameID"), node.get("name")
            if in_abilities and isinstance(game_id, int) and isinstance(name, str):
                named.setdefault(name.casefold(), set()).add(game_id)
            for key, value in node.items():
                walk(value, key == "abilities")
        elif isinstance(node, list):
            for item in node:
                walk(item, in_abilities)

    for path in sorted(directory.glob("*.json")):
        walk(json.loads(path.read_text(encoding="utf-8")), False)
        pages += 1
    counts = Counter(ability_id for _fight, _source, ability_id, _at in rows)
    return CachedIds(
        pages=pages,
        casts=dict(counts),
        named={name: frozenset(ids) for name, ids in named.items()},
    )
