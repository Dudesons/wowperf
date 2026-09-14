# Loadout and Consumables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every player a `Loadout` — equipped items and secondary stat ratings — so the cast
comparison stops advising a player to press an item they do not own, and so gear, stats and
consumables become comparable against a sample.

**Architecture:** One new query, `playerDetails(includeCombatantInfo: true)`, populates a
`Loadout` on `Player` for the analysed run and for each parse reference. A pure name join
resolves an ability to the item that fired it, which splits `compare.spells.missing` into a cast
finding and a gear finding. Four new comparison families live under
`src/wowperf/domain/comparison/`, one per concern, following the one-family-per-module convention
already set by `route.py`, `tempo.py` and `spells.py`.

**Tech Stack:** Python 3.12, `uv`, pydantic (`Frozen`), pytest, ruff, mypy, Jinja2, httpx.

**Spec:** `docs/plans/2026-09-14-loadout-and-consumables-design.md` — read it first. Every
measurement this plan relies on is recorded there in §2 with the date it was taken.

## Global Constraints

Every task's requirements implicitly include all of these.

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`,
  `jinja2`, or touches network, disk or template. Adapters do that, behind `domain/ports.py`.
- **Every finding carries a confidence badge** — `measured`, `derived` or `inferred`. A finding
  without one is a bug.
- **Never invent an API field name.** `.claude/skills/wcl-api/SKILL.md` is the verified
  reference; every field this plan uses is already recorded there under 2026-09-14.
- **No hardcoded season data.** Constants with no API source live in `data/*.toml` with a
  `verified` date.
- **The LLM never computes a number.** Every metric here is tested Python.
- **The report loads nothing.** One HTML file, no remote `src`, exactly one inline script.
  `tests/adapters/render/test_html_invariants.py` enforces it.
- **Test data:** the only character names permitted in `tests/` are `Emberkin`, `Stonewake`,
  `Bríala` and `Кириллица`. No real character name, and no item name taken from a real player's
  gear, enters this repository.
- **Never use `--no-verify`, `--no-hooks`, or `--no-pre-commit-hook`.** If a pre-commit hook
  fails, fix the cause.
- **Toolchain:** `uv` only. In the Bash tool `uv` is off PATH — every command must begin
  `export PATH="$HOME/.local/bin:$PATH"`. In this worktree the RTK hook makes a bare `git`
  refusable; use `/mingw64/bin/git`.
- **Commit messages:** plain ASCII only (non-ASCII is mangled in transit here), imperative mood,
  no `feat:`/`fix:` prefix, body explains *why*. End every commit message with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Gate before every commit:** `uv run ruff check .`, `uv run mypy`, `uv run pytest`.

---

## File Structure

**Created**

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/loadout.py` | `EquippedItem`, `StatBlock`, `Loadout` — pure values plus the tier-slot and enchant rules |
| `src/wowperf/adapters/wcl/loadouts.py` | Turns a `playerDetails` payload into `dict[actor_id, Loadout]` |
| `src/wowperf/domain/comparison/loadout.py` | `item_sourced`, `compare_enchants`, `compare_tier`, `compare_stats` |
| `src/wowperf/domain/comparison/consumables.py` | `compare_consumable_buffs`, `compare_potions` |
| `data/consumable_buffs.toml` | Curated flask / food / augment-rune buff ids, dated |
| `tests/domain/test_loadout.py` | Behaviour of the pure values |
| `tests/adapters/wcl/test_loadouts.py` | Ingest of the payload, including its empty-`combatantInfo` case |
| `tests/domain/comparison/test_loadout_comparison.py` | The four gear and stat families |
| `tests/domain/comparison/test_comparison_consumables.py` | The two consumable families |

**Modified**

| File | Change |
| --- | --- |
| `src/wowperf/domain/model.py` | `Player` gains `loadout: Loadout \| None = None` |
| `src/wowperf/adapters/wcl/queries.py` | `PLAYER_DETAILS_QUERY` |
| `src/wowperf/adapters/wcl/ingest.py` | `_build_players` and `build_run` accept loadouts |
| `src/wowperf/adapters/wcl/repository.py` | `_loadouts` helper; wired into `_load` for every profile but speed |
| `src/wowperf/domain/comparison/spells.py` | `_missing_sample` and its pairwise twin gain three branches |
| `src/wowperf/domain/comparison/service.py` | Fans in the six new families |
| `src/wowperf/domain/report/players.py` | `COMPARISON_PREFIXES` gains the new prefixes |
| `src/wowperf/adapters/config/toml.py` | `load_consumable_buffs` |
| `src/wowperf/domain/season.py` | `ConsumableBuffs` value object |
| `data/consumables.toml` | A `combat potion` category, and an amended header |
| `.claude/skills/wcl-api/SKILL.md` | Flip the two 2026-09-14 rows to `yes` once the query ships |

---

## Task 1: The pure loadout values

**Files:**
- Create: `src/wowperf/domain/loadout.py`
- Test: `tests/domain/test_loadout.py`

**Interfaces:**
- Consumes: `wowperf.domain.base.Frozen`
- Produces: `EquippedItem(item_id, slot, name, item_level, enchant_id, enchant_name, set_id)`;
  `StatBlock(crit, haste, mastery, versatility, leech, avoidance, speed)` with
  `.secondaries() -> tuple[tuple[str, int], ...]` and `.total_secondary() -> int`;
  `Loadout(items, stats)` with `.item_named(name) -> EquippedItem | None`,
  `.has_item(item_id) -> bool`, `.tier_pieces() -> int`, `.enchanted_slots() -> frozenset[int]`,
  `.occupied_slots() -> frozenset[int]`; and `TIER_SLOTS`.

- [ ] **Step 1: Write the failing tests**

```python
# ABOUTME: Behaviour tests for the pure loadout values: items, stat ratings, and the tier rule.
# ABOUTME: The tier-slot rule is the one inference here, so it carries the most cases.

from wowperf.domain.loadout import TIER_SLOTS, EquippedItem, Loadout, StatBlock


def an_item(**changes: object) -> EquippedItem:
    fields: dict[str, object] = {
        "item_id": 271465,
        "slot": 0,
        "name": "Emberkin Helm",
        "item_level": 321,
        "enchant_id": 8017,
        "enchant_name": "Enchant Helm - Empowered Rune of Avoidance",
        "set_id": 2062,
    }
    fields.update(changes)
    return EquippedItem(**fields)  # type: ignore[arg-type]


def test_an_item_is_found_by_name() -> None:
    loadout = Loadout(items=(an_item(name="Stonewake Tablet"),))
    found = loadout.item_named("Stonewake Tablet")
    assert found is not None
    assert found.item_id == 271465


def test_a_name_that_is_not_equipped_finds_nothing() -> None:
    assert Loadout(items=(an_item(),)).item_named("Bríala's Pendant") is None


def test_an_item_is_found_by_id() -> None:
    assert Loadout(items=(an_item(item_id=99),)).has_item(99)
    assert not Loadout(items=(an_item(item_id=99),)).has_item(100)


def test_tier_pieces_counts_only_the_set_sitting_in_the_tier_slots() -> None:
    # Measured 2026-09-14: the tier set occupies slots {0, 2, 4, 6, 9} and is
    # class-specific, while set 2070 spans classes in slots 12 and 15. Counting
    # equal set ids without the slot rule would call this seven pieces.
    loadout = Loadout(
        items=(
            an_item(slot=0, set_id=2062),
            an_item(slot=2, set_id=2062),
            an_item(slot=4, set_id=2062),
            an_item(slot=12, set_id=2070),
            an_item(slot=15, set_id=2070),
        )
    )
    assert loadout.tier_pieces() == 3


def test_tier_pieces_is_zero_when_no_item_carries_a_set() -> None:
    assert Loadout(items=(an_item(slot=0, set_id=None),)).tier_pieces() == 0


def test_tier_pieces_picks_the_larger_set_when_two_sit_in_tier_slots() -> None:
    loadout = Loadout(
        items=(
            an_item(slot=0, set_id=2062),
            an_item(slot=2, set_id=2062),
            an_item(slot=4, set_id=2055),
        )
    )
    assert loadout.tier_pieces() == 2


def test_the_tier_slots_are_the_five_measured_ones() -> None:
    assert TIER_SLOTS == frozenset({0, 2, 4, 6, 9})


def test_enchanted_slots_lists_only_slots_carrying_an_enchant() -> None:
    loadout = Loadout(
        items=(
            an_item(slot=0, enchant_id=8017),
            an_item(slot=1, enchant_id=None),
            an_item(slot=2, enchant_id=0),
        )
    )
    assert loadout.enchanted_slots() == frozenset({0})


def test_occupied_slots_lists_every_slot_holding_an_item() -> None:
    loadout = Loadout(items=(an_item(slot=0), an_item(slot=7)))
    assert loadout.occupied_slots() == frozenset({0, 7})


def test_the_secondaries_are_the_four_a_player_gems_for_plus_the_three_tertiaries() -> None:
    stats = StatBlock(crit=904, haste=865, mastery=1196, versatility=0, leech=82, avoidance=226)
    assert stats.secondaries() == (
        ("crit", 904),
        ("haste", 865),
        ("mastery", 1196),
        ("versatility", 0),
        ("leech", 82),
        ("avoidance", 226),
        ("speed", 0),
    )


def test_the_total_secondary_rating_is_the_sum_of_them() -> None:
    stats = StatBlock(crit=100, haste=200, mastery=300, versatility=400)
    assert stats.total_secondary() == 1000


def test_a_loadout_has_no_stats_until_it_is_given_some() -> None:
    # Stats are None rather than a zeroed block: a player whose stats could not
    # be read must not compare as a player with none of every stat.
    assert Loadout().stats is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/test_loadout.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'wowperf.domain.loadout'`.

- [ ] **Step 3: Write the implementation**

```python
# ABOUTME: What a player brought: the items they equipped and the stat ratings those gave them.
# ABOUTME: Pure data with derived readings; imports nothing that performs I/O.

from wowperf.domain.base import Frozen

TIER_SLOTS = frozenset({0, 2, 4, 6, 9})
"""Head, shoulder, chest, legs and hands, where a tier set sits.

Measured 2026-09-14 across ten players in two reports: the tier set is
class-specific and occupies exactly these five slots, at four or five pieces.
Set 2070 spanned four different classes in slots 12 and 15 and is not tier, so
counting items that share a set id without this rule over-counts. Recorded in
`.claude/skills/wcl-api/SKILL.md` under "Gear and the secondary stat block".
"""


class EquippedItem(Frozen):
    """One item in one slot, as the gear array reports it."""

    item_id: int
    slot: int
    name: str
    item_level: int
    enchant_id: int | None = None
    enchant_name: str | None = None
    set_id: int | None = None


class StatBlock(Frozen):
    """One player's secondary and tertiary stats, as ratings.

    Ratings, never percentages: converting one needs a per-level coefficient
    that has no source in this API, so no caller is given the chance to present
    a percentage this project cannot compute.
    """

    crit: int = 0
    haste: int = 0
    mastery: int = 0
    versatility: int = 0
    leech: int = 0
    avoidance: int = 0
    speed: int = 0

    def secondaries(self) -> tuple[tuple[str, int], ...]:
        """Every stat as (name, rating), in a fixed order so two blocks line up."""
        return (
            ("crit", self.crit),
            ("haste", self.haste),
            ("mastery", self.mastery),
            ("versatility", self.versatility),
            ("leech", self.leech),
            ("avoidance", self.avoidance),
            ("speed", self.speed),
        )

    def total_secondary(self) -> int:
        """The whole rating budget, which a share is taken against."""
        return sum(rating for _, rating in self.secondaries())


class Loadout(Frozen):
    """What one player equipped, and what it gave them.

    `stats` is None rather than a zeroed `StatBlock` when the log did not offer
    a usable reading: a player whose stats could not be read must not compare
    as a player who has none of every stat.
    """

    items: tuple[EquippedItem, ...] = ()
    stats: StatBlock | None = None

    def item_named(self, name: str) -> EquippedItem | None:
        """The equipped item with this exact name, if any."""
        for item in self.items:
            if item.name == name:
                return item
        return None

    def has_item(self, item_id: int) -> bool:
        return any(item.item_id == item_id for item in self.items)

    def tier_pieces(self) -> int:
        """How many pieces of the tier set this player wore.

        The tier set is whichever set id occupies the most tier slots; a set id
        appearing outside them is some other set and is not counted.
        """
        counts: dict[int, int] = {}
        for item in self.items:
            if item.slot in TIER_SLOTS and item.set_id:
                counts[item.set_id] = counts.get(item.set_id, 0) + 1
        return max(counts.values(), default=0)

    def enchanted_slots(self) -> frozenset[int]:
        return frozenset(item.slot for item in self.items if item.enchant_id)

    def occupied_slots(self) -> frozenset[int]:
        return frozenset(item.slot for item in self.items)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/test_loadout.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/domain/loadout.py tests/domain/test_loadout.py
```

Commit message:

```
Give the domain a value for what a player brought

The tier rule is the reason this is a type rather than a dict. One observed
set spans four classes in a trinket and a weapon slot, so pieces sharing a
set id are not a tier count and the slot rule has to live somewhere tested.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 2: `Player` carries a loadout

**Files:**
- Modify: `src/wowperf/domain/model.py:22-29`
- Test: `tests/domain/test_loadout.py` (append)

**Interfaces:**
- Consumes: `Loadout` from Task 1
- Produces: `Player.loadout: Loadout | None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/test_loadout.py`:

```python
from wowperf.domain.model import Player


def test_a_player_has_no_loadout_until_one_is_fetched() -> None:
    # Optional on purpose: the speed axis fetches none, and every run already
    # in the cache predates the query, so every consumer must handle None.
    player = Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane", item_level=318)
    assert player.loadout is None


def test_a_player_carries_the_loadout_it_is_given() -> None:
    loadout = Loadout(items=(an_item(),), stats=StatBlock(crit=904))
    player = Player(
        actor_id=1,
        name="Emberkin",
        class_name="Mage",
        spec="Arcane",
        item_level=318,
        loadout=loadout,
    )
    assert player.loadout is not None
    assert player.loadout.stats is not None
    assert player.loadout.stats.crit == 904
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/test_loadout.py -k loadout_until -v
```

Expected: FAIL — pydantic rejects the unexpected keyword `loadout`.

- [ ] **Step 3: Write the implementation**

In `src/wowperf/domain/model.py`, add the import beside the existing `from wowperf.domain.auras import PlayerAuras`:

```python
from wowperf.domain.loadout import Loadout
```

and extend `Player`:

```python
class Player(Frozen):
    actor_id: int
    name: str
    class_name: str
    spec: str
    item_level: int
    # Absent until a talent query runs; `get` never pays for one.
    talent_import_string: str | None = None
    # Absent on the speed axis, which never fetches one, and on every run
    # cached before this query existed. None means unknown, never "wore nothing".
    loadout: Loadout | None = None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/test_loadout.py -q
```

Expected: 14 passed.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/domain/model.py tests/domain/test_loadout.py
```

Commit message:

```
Let a player carry the loadout they brought

Optional, because the speed axis never fetches one and every run already in
the cache predates the query. None has to mean unknown rather than empty, or
a comparison would read a missing fetch as a player wearing nothing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 3: The query

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py`
- Modify: `.claude/skills/wcl-api/SKILL.md` (flip two rows to `yes`)
- Test: `tests/adapters/wcl/test_queries.py` (append to the existing file; match its import style)

**Interfaces:**
- Produces: `PLAYER_DETAILS_QUERY`, an operation named `PlayerDetails` taking `$code: String!`
  and `$fightId: Int!`

- [ ] **Step 1: Write the failing test**

```python
def test_the_player_details_query_asks_for_combatant_info() -> None:
    # The flag defaults off, and without it combatantInfo comes back as an
    # empty list rather than an error, so a query missing it fails silently.
    # Measured 2026-09-14; see the wcl-api skill.
    assert "includeCombatantInfo: true" in PLAYER_DETAILS_QUERY


def test_the_player_details_query_is_named_for_its_operation() -> None:
    assert operation_name(PLAYER_DETAILS_QUERY) == "PlayerDetails"


def test_the_player_details_query_allows_an_unlisted_report() -> None:
    assert "allowUnlisted: true" in PLAYER_DETAILS_QUERY
```

Add the imports at the top of the file:

```python
from wowperf.adapters.wcl.queries import PLAYER_DETAILS_QUERY, operation_name
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_queries.py -v
```

Expected: `ImportError: cannot import name 'PLAYER_DETAILS_QUERY'`.

- [ ] **Step 3: Write the implementation**

In `src/wowperf/adapters/wcl/queries.py`, beside `AURA_TABLE_QUERY`:

```python
PLAYER_DETAILS_QUERY = """
query PlayerDetails($code: String!, $fightId: Int!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      playerDetails(fightIDs: [$fightId], includeCombatantInfo: true)
    }
  }
}
"""
"""Gear and the secondary stat block for every player in one fight.

`includeCombatantInfo` defaults to false, and a query without it returns
`combatantInfo: []` — an empty list, not an error — so omitting the flag fails
silently. Measured 2026-09-14 at 2.00 points; see `.claude/skills/wcl-api/SKILL.md`.
"""
```

Then in `.claude/skills/wcl-api/SKILL.md`, change the two rows added on 2026-09-14 from `no` to
`yes` in the "In queries.py" column:

```
| `playerDetails` | `Report` | 2026-09-14 | yes |
| `includeCombatantInfo` | `playerDetails` argument | 2026-09-14 | yes |
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_queries.py tests/test_skills.py -q
```

Expected: all passed. `tests/test_skills.py` holds the skill's table against `queries.py` in both
directions, so it fails if the rows and the code disagree.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/adapters/wcl/queries.py .claude/skills/wcl-api/SKILL.md tests/adapters/wcl/test_queries.py
```

Commit message:

```
Ask Warcraft Logs what each player equipped

includeCombatantInfo defaults off and a query without it returns an empty
list rather than an error, so the field looks useless on a first read and a
query missing the flag would have failed silently.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 4: Ingest the payload

**Files:**
- Create: `src/wowperf/adapters/wcl/loadouts.py`
- Test: `tests/adapters/wcl/test_loadouts.py`

`ingest.py` is already 21K and covers the fight, the roster and five event streams; this payload
has its own shape and its own failure modes, so it gets its own module rather than growing that
one further.

**Interfaces:**
- Consumes: `EquippedItem`, `StatBlock`, `Loadout` from Task 1
- Produces: `build_loadouts(payload: dict[str, Any]) -> dict[int, Loadout]`, keyed by actor id

- [ ] **Step 1: Write the failing tests**

```python
# ABOUTME: Behaviour tests for turning a playerDetails payload into loadouts by actor id.
# ABOUTME: The empty-combatantInfo case is the one a missing query argument produces.

from typing import Any

from wowperf.adapters.wcl.loadouts import build_loadouts


def a_payload(*players: dict[str, Any]) -> dict[str, Any]:
    return {
        "reportData": {
            "report": {
                "playerDetails": {"data": {"playerDetails": {"dps": list(players)}}}
            }
        }
    }


def a_player(**changes: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": 4,
        "name": "Emberkin",
        "type": "Mage",
        "combatantInfo": {
            "stats": {
                "Crit": {"min": 904, "max": 904},
                "Haste": {"min": 865, "max": 865},
                "Mastery": {"min": 1196, "max": 1196},
                "Versatility": {"min": 0, "max": 0},
                "Leech": {"min": 82, "max": 82},
                "Avoidance": {"min": 226, "max": 226},
                "Speed": {"min": 0, "max": 0},
                "Item Level": {"min": 320, "max": 320},
            },
            "gear": [
                {
                    "id": 271465,
                    "slot": 0,
                    "name": "Emberkin Helm",
                    "itemLevel": 321,
                    "permanentEnchant": 8017,
                    "permanentEnchantName": "Enchant Helm - Empowered Rune",
                    "setID": 2062,
                },
                {"id": 251234, "slot": 1, "name": "Stonewake Pendant", "itemLevel": 311},
            ],
        },
    }
    fields.update(changes)
    return fields


def test_a_player_becomes_a_loadout_keyed_by_actor_id() -> None:
    loadouts = build_loadouts(a_payload(a_player()))
    assert set(loadouts) == {4}


def test_the_stat_ratings_are_read_from_min() -> None:
    stats = build_loadouts(a_payload(a_player()))[4].stats
    assert stats is not None
    assert (stats.crit, stats.haste, stats.mastery) == (904, 865, 1196)


def test_item_level_is_not_a_secondary_stat() -> None:
    # "Item Level" sits in the same block and is not a rating; leaking it into
    # a stat field would put a 320 beside a 904 as though they were comparable.
    stats = build_loadouts(a_payload(a_player()))[4].stats
    assert stats is not None
    assert stats.total_secondary() == 904 + 865 + 1196 + 0 + 82 + 226 + 0


def test_gear_is_read_with_its_enchant_and_set() -> None:
    items = build_loadouts(a_payload(a_player()))[4].items
    assert len(items) == 2
    helm = items[0]
    assert (helm.item_id, helm.slot, helm.item_level) == (271465, 0, 321)
    assert helm.enchant_id == 8017
    assert helm.set_id == 2062


def test_an_item_with_no_enchant_or_set_reads_as_having_neither() -> None:
    pendant = build_loadouts(a_payload(a_player()))[4].items[1]
    assert pendant.enchant_id is None
    assert pendant.set_id is None


def test_an_empty_combatant_info_yields_no_loadout_at_all() -> None:
    # This is exactly what a query missing `includeCombatantInfo: true` returns.
    # It must not read as a player who equipped nothing.
    assert build_loadouts(a_payload(a_player(combatantInfo=[]))) == {}


def test_a_missing_combatant_info_yields_no_loadout() -> None:
    assert build_loadouts(a_payload(a_player(combatantInfo=None))) == {}


def test_stats_are_withheld_when_a_rating_moved_during_the_fight() -> None:
    # min equalled max for every stat of every player measured on 2026-09-14.
    # A divergence means the reading is not a single number, and guessing which
    # end to take would be a modelling choice nothing here can justify.
    player = a_player()
    player["combatantInfo"]["stats"]["Crit"] = {"min": 900, "max": 1100}
    loadout = build_loadouts(a_payload(player))[4]
    assert loadout.stats is None
    assert len(loadout.items) == 2


def test_a_stat_absent_from_the_block_reads_as_zero() -> None:
    player = a_player()
    del player["combatantInfo"]["stats"]["Leech"]
    stats = build_loadouts(a_payload(player))[4].stats
    assert stats is not None
    assert stats.leech == 0


def test_every_role_group_is_read() -> None:
    payload = {
        "reportData": {
            "report": {
                "playerDetails": {
                    "data": {
                        "playerDetails": {
                            "tanks": [a_player(id=1)],
                            "healers": [a_player(id=2)],
                            "dps": [a_player(id=3)],
                        }
                    }
                }
            }
        }
    }
    assert set(build_loadouts(payload)) == {1, 2, 3}


def test_a_payload_with_no_player_details_yields_nothing() -> None:
    assert build_loadouts({"reportData": {"report": {}}}) == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_loadouts.py -v
```

Expected: collection error — `No module named 'wowperf.adapters.wcl.loadouts'`.

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_loadouts.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/adapters/wcl/loadouts.py tests/adapters/wcl/test_loadouts.py
```

Commit message:

```
Read gear and stat ratings out of a player details payload

An empty combatantInfo is what the API returns when the query forgets its
flag, so it yields no loadout rather than an empty one: an empty loadout
would compare as a player who equipped nothing.

A stat whose min and max disagree withholds the whole block. Every reading
measured had them equal, so a divergence means the rating moved and picking
an end would be a modelling choice with nothing behind it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 5: Wire the fetch into the repository

**Files:**
- Modify: `src/wowperf/adapters/wcl/ingest.py:55-90` (`_build_players`), `:131-153` (`build_run`)
- Modify: `src/wowperf/adapters/wcl/repository.py` (new `_loadouts`, wired into `_load`)
- Test: `tests/adapters/wcl/test_ingest.py` (append), `tests/adapters/wcl/test_repository.py` (append)

**Interfaces:**
- Consumes: `build_loadouts` (Task 4), `PLAYER_DETAILS_QUERY` (Task 3), `Player.loadout` (Task 2)
- Produces: `build_run(report, fight, talents=None, loadouts=None)`;
  `WclRunRepository._loadouts(report_code, fight, hits) -> dict[int, Loadout]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/adapters/wcl/test_ingest.py`:

```python
def test_a_player_is_given_the_loadout_matching_their_actor_id() -> None:
    fight = a_minimal_fight()
    run = build_run(
        a_report_for(fight),
        fight,
        None,
        {693: Loadout(stats=StatBlock(crit=904))},
    )
    by_id = {player.actor_id: player for player in run.players}
    assert by_id[693].loadout is not None


def test_a_player_with_no_loadout_in_the_map_keeps_none() -> None:
    fight = a_minimal_fight()
    run = build_run(a_report_for(fight), fight, None, {})
    assert all(player.loadout is None for player in run.players)
```

Adjust `a_report_for` / `a_minimal_fight` to whatever the existing file already provides — read
`tests/adapters/wcl/test_ingest.py:175` before writing, and reuse its builders rather than adding
new ones. `693` must be an actor id that builder's fight already lists in `friendlyPlayers`.

Append to `tests/adapters/wcl/test_repository.py`:

```python
def test_a_speed_reference_fetches_no_loadouts() -> None:
    # The speed axis compares a group, not a player. One player's crit rating
    # against five players in five specialisations is a number with no meaning,
    # so the 2.00 points are not spent.
    repository = a_repository()
    repository.load_speed_reference("71cv4MRdNCp8ZFjG", 28)
    assert "PlayerDetails" not in issued_operations(repository)


def test_a_parse_reference_fetches_loadouts() -> None:
    repository = a_repository()
    repository.load_parse_reference("71cv4MRdNCp8ZFjG", 28)
    assert "PlayerDetails" in issued_operations(repository)
```

`issued_operations` reads the operation names the fake client recorded; follow whatever
`a_repository()` at `tests/adapters/wcl/test_repository.py:86` already exposes, and add the
helper there if it does not exist.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_ingest.py tests/adapters/wcl/test_repository.py -v -k loadout
```

Expected: FAIL — `build_run()` takes 3 positional arguments, and no `PlayerDetails` operation is
ever issued.

- [ ] **Step 3: Write the implementation**

In `src/wowperf/adapters/wcl/ingest.py`, extend `_build_players`:

```python
def _build_players(
    fight: dict[str, Any],
    actors: list[dict[str, Any]],
    talents: dict[int, str],
    loadouts: dict[int, Loadout],
) -> tuple[Player, ...]:
```

and inside the `Player(...)` construction, beside `talent_import_string`:

```python
                talent_import_string=talents.get(actor_id),
                loadout=loadouts.get(actor_id),
```

Extend `build_run`:

```python
def build_run(
    report: dict[str, Any],
    fight: dict[str, Any],
    talents: dict[int, str] | None = None,
    loadouts: dict[int, Loadout] | None = None,
) -> Run:
```

and its `players=` argument:

```python
        players=_build_players(fight, actors, talents or {}, loadouts or {}),
```

In `src/wowperf/adapters/wcl/repository.py`, add the helper beside `_talents`:

```python
    def _loadouts(
        self, report_code: str, fight: dict[str, Any], hits: list[bool] | None = None
    ) -> dict[int, Loadout]:
        """Gear and stat ratings per player, keyed by actor id.

        Costs 2.00 points, measured 2026-09-14. A report that returns nothing
        usable yields an empty map, and every consumer reads that as unknown.
        """
        payload = self._query(
            PLAYER_DETAILS_QUERY, {"code": report_code, "fightId": fight["id"]}, hits
        )
        return build_loadouts(payload)
```

and in `_load`, beside the talents line:

```python
        talents = {} if profile == "speed" else self._talents(report_code, fight, hits)
        loadouts = {} if profile == "speed" else self._loadouts(report_code, fight, hits)
        run = build_run(report, fight, talents, loadouts)
```

Add the imports at the top of `repository.py`:

```python
from wowperf.adapters.wcl.loadouts import build_loadouts
from wowperf.adapters.wcl.queries import PLAYER_DETAILS_QUERY
from wowperf.domain.loadout import Loadout
```

and to `ingest.py`:

```python
from wowperf.domain.loadout import Loadout
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl -q
```

Expected: all passed.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/adapters/wcl/ingest.py src/wowperf/adapters/wcl/repository.py tests/adapters/wcl/
```

Commit message:

```
Fetch a loadout for the run and for every parse reference

Not for the speed axis. That axis compares a group against a group, and one
player's crit rating against five players in five specialisations is a number
with no meaning, so the two points a report costs are not spent there.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 6: `item_sourced`, the join the refusal needed

**Files:**
- Create: `src/wowperf/domain/comparison/loadout.py`
- Test: `tests/domain/comparison/test_loadout_comparison.py`

**Interfaces:**
- Consumes: `Loadout`, `EquippedItem` from Task 1
- Produces: `item_sourced(ability_name: str, loadouts: Sequence[Loadout]) -> EquippedItem | None`

- [ ] **Step 1: Write the failing tests**

```python
# ABOUTME: Behaviour tests for the gear and stat comparison families.
# ABOUTME: item_sourced is asymmetric on purpose: a match is evidence, a miss is not.

from collections.abc import Sequence

from wowperf.domain.comparison.loadout import item_sourced
from wowperf.domain.loadout import EquippedItem, Loadout


def an_item(**changes: object) -> EquippedItem:
    fields: dict[str, object] = {
        "item_id": 250225,
        "slot": 12,
        "name": "Tablet of the Stonewake",
        "item_level": 331,
        "enchant_id": None,
        "enchant_name": None,
        "set_id": None,
    }
    fields.update(changes)
    return EquippedItem(**fields)  # type: ignore[arg-type]


def a_loadout(*items: EquippedItem) -> Loadout:
    return Loadout(items=items or (an_item(),))


def test_an_ability_named_after_an_equipped_item_resolves_to_it() -> None:
    # Measured 2026-09-14: Warcraft Logs names an on-use trinket's spell after
    # the item. Four of ten equipped trinkets matched the ability dictionary.
    found = item_sourced("Tablet of the Stonewake", [a_loadout()])
    assert found is not None
    assert found.item_id == 250225


def test_an_ability_matching_no_equipped_item_resolves_to_nothing() -> None:
    # A miss means unknown, never "this is a class spell". The measurement
    # shows a match indicates an item source; it does not show every
    # item-sourced ability matches by name.
    assert item_sourced("Arcane Blast", [a_loadout()]) is None


def test_any_loadout_in_the_sample_can_supply_the_match() -> None:
    others = [a_loadout(an_item(name="Bríala's Ember")), a_loadout(an_item(name="Ashen Coil"))]
    found = item_sourced("Ashen Coil", others)
    assert found is not None
    assert found.name == "Ashen Coil"


def test_no_loadouts_at_all_resolve_to_nothing() -> None:
    assert item_sourced("Ashen Coil", []) is None


def test_the_match_is_exact_rather_than_loose() -> None:
    # A substring rule would fold "Rune of Sanguination" into a rune consumable
    # and a "Tablet" into every tablet; the join is worth having only if it is
    # precise.
    assert item_sourced("Tablet", [a_loadout()]) is None
    assert item_sourced("tablet of the stonewake", [a_loadout()]) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_loadout_comparison.py -v
```

Expected: collection error — `No module named 'wowperf.domain.comparison.loadout'`.

- [ ] **Step 3: Write the implementation**

```python
# ABOUTME: Compares one player's gear and stat ratings against a sample of top parses.
# ABOUTME: Resolves an item-sourced cast to its item, so advice names something pressable.

from collections.abc import Sequence

from wowperf.domain.loadout import EquippedItem, Loadout


def item_sourced(ability_name: str, loadouts: Sequence[Loadout]) -> EquippedItem | None:
    """The equipped item this ability's name identifies, if any of these wore it.

    Warcraft Logs names an on-use trinket's spell after the item, measured
    2026-09-14: of the 81 items equipped across one report's five players, five
    names were also ability names, four of them trinkets, out of ten trinkets
    worn. The other six trinkets are passive and fire no named spell.

    **The reading is asymmetric and callers must honour it.** A match is
    evidence the ability came from an item. A miss is *not* evidence it did
    not: an on-use effect named differently from its item would not be caught.
    A caller may act on a match; on a miss it may only say it does not know.

    The comparison is exact rather than case-folded or partial. A loose rule
    would fold every name sharing a word, and the join earns its place only by
    being precise.
    """
    for loadout in loadouts:
        found = loadout.item_named(ability_name)
        if found is not None:
            return found
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_loadout_comparison.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/loadout.py tests/domain/comparison/test_loadout_comparison.py
```

Commit message:

```
Resolve an item-sourced cast to the item that fired it

The join is asymmetric and the docstring says so. A name match is evidence an
ability came from an item; a miss is not evidence it did not, because an
on-use effect named differently from its item would not be caught. Callers
may act on a match and may only plead ignorance on a miss.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 7: The refusal — three branches instead of two

**Files:**
- Modify: `src/wowperf/domain/comparison/spells.py:181-204` (pairwise), `:322-368` (`_missing_sample`)
- Test: `tests/domain/comparison/test_spells.py` (append)

This is the correctness fix the whole design exists for. Note that the third branch works with no
loadout at all, so it must be implemented and tested independently of the fetch.

**Interfaces:**
- Consumes: `item_sourced` (Task 6), `Player.loadout` (Task 2)
- Produces: `_missing_sample(..., our_loadout: Loadout | None, their_loadouts: Sequence[Loadout])`;
  a new finding family `compare.gear.missing_item`

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/comparison/test_spells.py`:

```python
def test_an_unresolved_missing_cast_names_all_three_possibilities() -> None:
    # The old wording offered a talent or a button and stated a false dichotomy
    # for any item-sourced ability. This branch is reached with no loadout at
    # all, which is every cached run and the whole speed axis, so the fix must
    # not depend on the fetch.
    findings = compare_spells_sample(ours_without(1234), OURS, OUR_NAME, a_sample_casting(1234))
    missing = [f for f in findings if f.id.startswith("compare.spells.missing")]
    assert missing
    assert "an item not owned" in missing[0].detail


def test_a_cast_from_an_item_we_do_not_own_becomes_a_gear_finding() -> None:
    sample = a_sample_casting(1234, name="Tablet of the Stonewake", wearing_it=True)
    findings = compare_spells_sample(
        ours_without(1234), OURS_WITHOUT_THE_TABLET, OUR_NAME, sample
    )
    assert not [f for f in findings if f.id.startswith("compare.spells.missing")]
    gear = [f for f in findings if f.id.startswith("compare.gear.missing_item")]
    assert len(gear) == 1
    assert gear[0].confidence is Confidence.MEASURED
    assert "Tablet of the Stonewake" in gear[0].title


def test_a_cast_from_an_item_we_do_own_stays_a_cast_finding_and_says_so() -> None:
    sample = a_sample_casting(1234, name="Tablet of the Stonewake", wearing_it=True)
    findings = compare_spells_sample(ours_without(1234), OURS_WEARING_THE_TABLET, OUR_NAME, sample)
    assert not [f for f in findings if f.id.startswith("compare.gear.missing_item")]
    missing = [f for f in findings if f.id.startswith("compare.spells.missing")]
    assert len(missing) == 1
    assert "had it equipped" in missing[0].detail
    assert "a talent not taken" not in missing[0].detail


def test_a_gear_finding_costs_no_time_and_so_ranks_with_the_rest() -> None:
    sample = a_sample_casting(1234, name="Tablet of the Stonewake", wearing_it=True)
    findings = compare_spells_sample(
        ours_without(1234), OURS_WITHOUT_THE_TABLET, OUR_NAME, sample
    )
    gear = [f for f in findings if f.id.startswith("compare.gear.missing_item")]
    assert gear[0].seconds_lost is None
```

Write `ours_without`, `a_sample_casting`, `OURS_WITHOUT_THE_TABLET` and `OURS_WEARING_THE_TABLET`
as local builders in that file, following the existing `boss_pull` / `OURS` / `THEIRS` style at
`tests/domain/comparison/test_spells.py:23-50`. `a_sample_casting(ability_id, name=..., wearing_it=...)`
must build at least `MIN_SAMPLE_FOR_AGGREGATE` members, each casting the ability at least
`MIN_CASTS_TO_COMPARE` times on a boss pull, and — when `wearing_it` — each carrying a `Loadout`
holding an `EquippedItem` of that name.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_spells.py -v -k "three_possibilities or gear_finding or do_own"
```

Expected: FAIL — the detail still reads "either a talent not taken or a button not pressed", and
no `compare.gear.missing_item` is ever produced.

- [ ] **Step 3: Write the implementation**

In `spells.py`, import the join and the type:

```python
from wowperf.domain.comparison.loadout import item_sourced
from wowperf.domain.loadout import Loadout
```

Replace the body of the candidate loop in `_missing_sample` so each candidate takes one of three
branches. The signature gains two parameters, which `compare_spells_sample` supplies from
`our_player.loadout` and from each member's own player:

```python
def _missing_sample(
    our_name: str,
    ours_anywhere: set[int],
    names: dict[int, str],
    per_member: Sequence[tuple[float, dict[int, int]]],
    total: int,
    our_loadout: Loadout | None,
    their_loadouts: Sequence[Loadout],
) -> list[Finding]:
    """Abilities enough of the sample cast on bosses that we never cast anywhere.

    Three branches, because the log supports three explanations and the two the
    detail used to offer made a false dichotomy of it. An ability that resolves
    to an item the player does not own is a gear finding, not a cast finding:
    telling somebody to press a button they do not have is advice they cannot
    take, and it carried a `measured` badge while doing so.

    The third branch is reached whenever the join cannot answer — an ability
    matching no item name, or a player whose loadout was never fetched — and it
    widens the wording rather than claiming anything. That is what keeps the
    speed axis and every already-cached run honest without the new query.
    """
    ...
    findings = []
    for matching, ability_id, name in candidates:
        source = item_sourced(name, their_loadouts)
        if source is not None and our_loadout is not None and not our_loadout.has_item(
            source.item_id
        ):
            findings.append(_missing_item(our_name, matching, total, source, ability_id))
            continue
        findings.append(
            _missing_cast(our_name, matching, total, ability_id, name, owned=source is not None)
        )
    return _one_row_per_sentence(findings)
```

with the two row builders:

```python
def _missing_cast(
    our_name: str, matching: int, total: int, ability_id: int, name: str, *, owned: bool
) -> Finding:
    """A cast the sample made and we did not, in whichever of two wordings is true."""
    if owned:
        detail = (
            f"{our_name} had it equipped and never used it. The count is over the "
            "sample, not one parse, so no single reference needs naming to make the point."
        )
    else:
        detail = (
            f"{name} does not appear anywhere in this run for {our_name} — not on bosses "
            "and not on trash. That is a talent not taken, a button not pressed, or an "
            "item not owned; the log cannot tell which. The count is over the sample, not "
            "one parse, so no single reference needs naming to make the point."
        )
    return Finding(
        id="compare.spells.missing",
        title=(
            f"{count_phrase(matching, total)} top parses cast {name} on bosses; "
            f"{our_name} never did"
        ),
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(
            f"ability {ability_id}",
            f"{matching} of {total} top parses cast it at least "
            f"{MIN_CASTS_TO_COMPARE} times on bosses",
            "zero casts in the whole of our run",
        ),
        quantifier=quantifier_for(matching, total),
        ability_id=ability_id,
        ability_name=name,
    )


def _missing_item(
    our_name: str, matching: int, total: int, source: EquippedItem, ability_id: int
) -> Finding:
    """An item the sample equipped and we did not, reached through a cast we lacked."""
    return Finding(
        id="compare.gear.missing_item",
        title=(
            f"{count_phrase(matching, total)} top parses equipped {source.name}; "
            f"{our_name} did not"
        ),
        detail=(
            f"{source.name} fires the ability those parses cast and this run never did. "
            f"{our_name} does not have it equipped, so this is a difference in gear rather "
            "than a button that went unpressed."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(
            f"item {source.item_id} in slot {source.slot}",
            f"ability {ability_id}",
            f"{matching} of {total} top parses equipped it",
        ),
        quantifier=quantifier_for(matching, total),
        ability_id=ability_id,
        ability_name=source.name,
    )
```

Apply the same three branches to the pairwise twin at `spells.py:181-204`, passing the single
reference's loadout as a one-element sequence. Add `EquippedItem` to the imports.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_spells.py -q
```

Expected: all passed, including every pre-existing test in that file.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/spells.py tests/domain/comparison/test_spells.py
```

Commit message:

```
Stop telling a player to press an item they do not own

The detail offered a talent or a button and called that the whole of what the
log supports. For a trinket on-use it is neither, and the finding said so
under a measured badge, which is the failure the badge exists to prevent.

An ability that resolves to an item the sample wore and the player did not is
now a gear finding. One that resolves to an item they do own keeps the cast
finding and states the stronger fact. One that resolves to nothing widens the
wording to three possibilities, which is the branch every already-cached run
and the whole speed axis take, so the correction does not wait on the fetch.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 8: `compare.gear.enchant`

**Files:**
- Modify: `src/wowperf/domain/comparison/loadout.py`
- Test: `tests/domain/comparison/test_loadout_comparison.py` (append)

**Interfaces:**
- Produces: `compare_enchants(our_loadout: Loadout | None, their_loadouts: Sequence[Loadout], our_name: str) -> list[Finding]`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_slot_everyone_enchanted_and_we_did_not_is_a_finding() -> None:
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(5)]
    ours = a_loadout(an_item(slot=7, enchant_id=None))
    findings = compare_enchants(ours, theirs, OUR_NAME)
    assert len(findings) == 1
    assert findings[0].id == "compare.gear.enchant"
    assert findings[0].confidence is Confidence.MEASURED
    assert "slot 7" in findings[0].evidence[0]


def test_a_slot_the_sample_left_bare_is_not_a_finding() -> None:
    # Measured 2026-09-14: the off hand was enchanted by 1 of 10 players. A
    # hardcoded enchantable-slot list would flag nine of them; letting the
    # sample define the rule flags none.
    theirs = [a_loadout(an_item(slot=16, enchant_id=None)) for _ in range(5)]
    ours = a_loadout(an_item(slot=16, enchant_id=None))
    assert compare_enchants(ours, theirs, OUR_NAME) == []


def test_a_slot_only_some_of_the_sample_enchanted_is_not_a_finding() -> None:
    theirs = [a_loadout(an_item(slot=16, enchant_id=8017))] + [
        a_loadout(an_item(slot=16, enchant_id=None)) for _ in range(4)
    ]
    assert compare_enchants(a_loadout(an_item(slot=16, enchant_id=None)), theirs, OUR_NAME) == []


def test_a_slot_we_enchanted_too_is_not_a_finding() -> None:
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(5)]
    ours = a_loadout(an_item(slot=7, enchant_id=9000))
    assert compare_enchants(ours, theirs, OUR_NAME) == []


def test_a_slot_we_have_no_item_in_is_not_a_finding() -> None:
    # An empty slot is a different claim from an unenchanted one, and the tool
    # has no opinion about a player choosing to wear nothing there.
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(5)]
    assert compare_enchants(a_loadout(an_item(slot=0)), theirs, OUR_NAME) == []


def test_nothing_is_compared_without_our_loadout() -> None:
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(5)]
    assert compare_enchants(None, theirs, OUR_NAME) == []


def test_nothing_is_compared_below_the_sample_floor() -> None:
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(2)]
    assert compare_enchants(a_loadout(an_item(slot=7, enchant_id=None)), theirs, OUR_NAME) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_loadout_comparison.py -v -k enchant
```

Expected: `ImportError: cannot import name 'compare_enchants'`.

- [ ] **Step 3: Write the implementation**

```python
def compare_enchants(
    our_loadout: Loadout | None, their_loadouts: Sequence[Loadout], our_name: str
) -> list[Finding]:
    """Slots every comparable reference enchanted and this player left bare.

    **The sample defines which slots take an enchant.** Measured 2026-09-14
    across ten players in two reports: eight slots were enchanted 10/10, nine
    were 0/10, and the off hand was 1/10 — enchantable for some specialisations
    and not others. A hardcoded list would have to be revised every expansion
    and would misjudge the off hand today; unanimity in the sample needs no
    revision and gets the off hand right by abstaining.

    A slot this player wears nothing in is not reported: an empty slot is a
    different claim from an unenchanted one.
    """
    if our_loadout is None or len(their_loadouts) < MIN_SAMPLE_FOR_AGGREGATE:
        return []

    ours_enchanted = our_loadout.enchanted_slots()
    ours_occupied = our_loadout.occupied_slots()
    unanimous = frozenset.intersection(
        *(loadout.enchanted_slots() for loadout in their_loadouts)
    )

    findings = []
    for slot in sorted(unanimous & ours_occupied - ours_enchanted):
        findings.append(
            Finding(
                id="compare.gear.enchant",
                title=(
                    f"{count_phrase(len(their_loadouts), len(their_loadouts))} top parses "
                    f"enchanted slot {slot}; {our_name} did not"
                ),
                detail=(
                    "Every reference in the sample carries an enchant in this slot and this "
                    "one does not. Which enchant is not stated: the sample may disagree among "
                    "themselves, and this tool does not rank enchants."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"slot {slot}",
                    f"{len(their_loadouts)} of {len(their_loadouts)} references enchanted it",
                ),
                quantifier=quantifier_for(len(their_loadouts), len(their_loadouts)),
            )
        )
    return findings
```

Add the imports `MIN_SAMPLE_FOR_AGGREGATE` from `sample`, `count_phrase` from `statistics`, and
`Confidence`, `Finding`, `quantifier_for` from `findings`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_loadout_comparison.py -q
```

Expected: 13 passed.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/loadout.py tests/domain/comparison/test_loadout_comparison.py
```

Commit message:

```
Report a slot the whole sample enchanted and this player did not

No list of enchantable slots is hardcoded. Unanimity in the sample defines
the rule, which needs no revision when an expansion changes what takes an
enchant, and which abstains on the off hand, where one player in ten carried
one because it is enchantable for some specialisations and not others.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 9: `compare.gear.tier`

**Files:**
- Modify: `src/wowperf/domain/comparison/loadout.py`
- Test: `tests/domain/comparison/test_loadout_comparison.py` (append)

**Interfaces:**
- Produces: `compare_tier(our_loadout, their_loadouts, our_name) -> list[Finding]`

- [ ] **Step 1: Write the failing tests**

```python
def a_tier_loadout(pieces: int) -> Loadout:
    slots = sorted(TIER_SLOTS)[:pieces]
    return Loadout(items=tuple(an_item(slot=slot, set_id=2062) for slot in slots))


def test_fewer_tier_pieces_than_the_sample_median_is_a_finding() -> None:
    findings = compare_tier(a_tier_loadout(2), [a_tier_loadout(4) for _ in range(5)], OUR_NAME)
    assert len(findings) == 1
    assert findings[0].id == "compare.gear.tier"
    assert findings[0].confidence is Confidence.DERIVED


def test_the_tier_finding_is_derived_because_the_slot_rule_is_inferred() -> None:
    # The API states no tier flag. The rule is read off seven observed sets,
    # so the badge must not claim the log said it.
    findings = compare_tier(a_tier_loadout(2), [a_tier_loadout(4) for _ in range(5)], OUR_NAME)
    assert findings[0].confidence is Confidence.DERIVED


def test_matching_the_sample_median_is_not_a_finding() -> None:
    assert compare_tier(a_tier_loadout(4), [a_tier_loadout(4) for _ in range(5)], OUR_NAME) == []


def test_more_tier_pieces_than_the_sample_is_not_a_finding() -> None:
    assert compare_tier(a_tier_loadout(5), [a_tier_loadout(4) for _ in range(5)], OUR_NAME) == []


def test_the_finding_states_the_median_and_the_range() -> None:
    theirs = [a_tier_loadout(2), a_tier_loadout(4), a_tier_loadout(4), a_tier_loadout(5),
              a_tier_loadout(5)]
    findings = compare_tier(a_tier_loadout(0), theirs, OUR_NAME)
    joined = " ".join(findings[0].evidence)
    assert "4" in joined
    assert "2" in joined and "5" in joined


def test_nothing_is_compared_below_the_sample_floor() -> None:
    assert compare_tier(a_tier_loadout(0), [a_tier_loadout(4) for _ in range(2)], OUR_NAME) == []


def test_nothing_is_compared_without_our_loadout() -> None:
    assert compare_tier(None, [a_tier_loadout(4) for _ in range(5)], OUR_NAME) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_loadout_comparison.py -v -k tier
```

Expected: `ImportError: cannot import name 'compare_tier'`.

- [ ] **Step 3: Write the implementation**

```python
def compare_tier(
    our_loadout: Loadout | None, their_loadouts: Sequence[Loadout], our_name: str
) -> list[Finding]:
    """How many tier pieces this player wore, against the sample's median.

    `derived`, not `measured`: the API states no tier flag, and the rule that
    picks the tier set out of the gear — the set id occupying slots
    {0, 2, 4, 6, 9} — is inferred from seven sets observed on 2026-09-14, not
    something the log said.

    Reported only when below the sample. A player carrying more tier than the
    references has nothing to act on, and the report is a list of things to do
    differently rather than a scoreboard.
    """
    if our_loadout is None or len(their_loadouts) < MIN_SAMPLE_FOR_AGGREGATE:
        return []

    ours = our_loadout.tier_pieces()
    theirs = [float(loadout.tier_pieces()) for loadout in their_loadouts]
    their_median = median(theirs)
    if ours >= their_median:
        return []

    low, high = observed_range(theirs)
    return [
        Finding(
            id="compare.gear.tier",
            title=(
                f"{our_name} wore {quantity(ours, 'tier piece', 'tier pieces')}; "
                f"the sample's median is {their_median:g}"
            ),
            detail=(
                "A tier set bonus is throughput this player did not have and the references "
                "did. Read the cast and damage comparisons against this before reading them "
                "as things that went unpressed."
            ),
            confidence=Confidence.DERIVED,
            seconds_lost=None,
            evidence=(
                f"{ours} tier pieces in slots {sorted(TIER_SLOTS)}",
                f"sample median {their_median:g}, range {low:g} to {high:g} "
                f"across {len(their_loadouts)} references",
            ),
        )
    ]
```

Add `median`, `observed_range` and `quantity` to the imports, and `TIER_SLOTS` from
`wowperf.domain.loadout`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_loadout_comparison.py -q
```

Expected: 20 passed.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/loadout.py tests/domain/comparison/test_loadout_comparison.py
```

Commit message:

```
Count the tier pieces a player wore against the sample

Badged derived rather than measured. The API states no tier flag, and the
rule that picks the tier set out of the gear is read off seven observed sets,
so the badge must not claim the log said it.

A player short of the sample's tier has throughput the cast comparison would
otherwise blame on them.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 10: `compare.stats.rating`

**Files:**
- Modify: `src/wowperf/domain/comparison/loadout.py`
- Test: `tests/domain/comparison/test_loadout_comparison.py` (append)

**Interfaces:**
- Produces: `compare_stats(our_loadout, their_loadouts, our_name) -> list[Finding]`

- [ ] **Step 1: Write the failing tests**

```python
def a_stat_loadout(**ratings: int) -> Loadout:
    return Loadout(items=(an_item(),), stats=StatBlock(**ratings))


def test_each_secondary_that_differs_gets_a_row() -> None:
    ours = a_stat_loadout(crit=900, haste=900, mastery=400, versatility=0)
    theirs = [a_stat_loadout(crit=900, haste=900, mastery=1400, versatility=0) for _ in range(5)]
    findings = compare_stats(ours, theirs, OUR_NAME)
    assert [f.id for f in findings] == ["compare.stats.rating"]
    assert "mastery" in findings[0].title


def test_the_row_states_our_rating_the_median_and_the_range() -> None:
    ours = a_stat_loadout(mastery=400)
    theirs = [a_stat_loadout(mastery=r) for r in (1290, 1400, 1480, 1500, 1602)]
    findings = compare_stats(ours, theirs, OUR_NAME)
    joined = " ".join(findings[0].evidence)
    assert "400" in joined
    assert "1480" in joined
    assert "1290" in joined and "1602" in joined


def test_the_row_also_states_the_share_of_the_secondary_budget() -> None:
    # The raw gap between a top parse and this player largely restates item
    # level. The share is the part a decision can change.
    ours = a_stat_loadout(crit=800, mastery=200)
    theirs = [a_stat_loadout(crit=200, mastery=800) for _ in range(5)]
    findings = compare_stats(ours, theirs, OUR_NAME)
    joined = " ".join(f.detail for f in findings)
    assert "%" in joined


def test_a_stat_nobody_has_produces_no_row() -> None:
    ours = a_stat_loadout(crit=900)
    theirs = [a_stat_loadout(crit=900) for _ in range(5)]
    assert compare_stats(ours, theirs, OUR_NAME) == []


def test_rows_are_badged_derived() -> None:
    ours = a_stat_loadout(mastery=400)
    theirs = [a_stat_loadout(mastery=1400) for _ in range(5)]
    assert compare_stats(ours, theirs, OUR_NAME)[0].confidence is Confidence.DERIVED


def test_no_row_states_a_percentage_of_the_rating_itself() -> None:
    # Converting a rating to a percentage needs a per-level coefficient with no
    # source in this API. The only percentage permitted is the share of budget.
    ours = a_stat_loadout(mastery=400)
    theirs = [a_stat_loadout(mastery=1400) for _ in range(5)]
    finding = compare_stats(ours, theirs, OUR_NAME)[0]
    assert "1400%" not in finding.title and "400%" not in finding.title


def test_nothing_is_compared_when_our_stats_were_withheld() -> None:
    ours = Loadout(items=(an_item(),), stats=None)
    theirs = [a_stat_loadout(mastery=1400) for _ in range(5)]
    assert compare_stats(ours, theirs, OUR_NAME) == []


def test_a_reference_whose_stats_were_withheld_is_not_counted() -> None:
    ours = a_stat_loadout(mastery=400)
    theirs = [a_stat_loadout(mastery=1400) for _ in range(3)] + [
        Loadout(items=(an_item(),), stats=None) for _ in range(2)
    ]
    findings = compare_stats(ours, theirs, OUR_NAME)
    assert "3 references" in " ".join(findings[0].evidence)


def test_nothing_is_compared_below_the_sample_floor() -> None:
    ours = a_stat_loadout(mastery=400)
    theirs = [a_stat_loadout(mastery=1400) for _ in range(2)]
    assert compare_stats(ours, theirs, OUR_NAME) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_loadout_comparison.py -v -k stat
```

Expected: `ImportError: cannot import name 'compare_stats'`.

- [ ] **Step 3: Write the implementation**

```python
STAT_GAP_SHARE = 0.15
"""How far a stat's share of the budget must move before the row is worth printing.

Two players of the same specialisation gemming the same way land within a few
points of each other, and a row for every stat every time would bury the one
that moved.
"""


def compare_stats(
    our_loadout: Loadout | None, their_loadouts: Sequence[Loadout], our_name: str
) -> list[Finding]:
    """Each secondary's rating against the sample's, and its share of the budget.

    Two readings, because one of them is misleading alone. The rating and its
    gap is the fact, and it is what a reader asked for; but a top parse
    out-gears this player, so it holds more of every stat and the raw gap
    largely restates the item-level confound `confounds.py` already reports.
    The share of the player's own secondary budget is item-level independent,
    and it is the part a decision — a gem, an enchant, which piece was kept —
    actually moves.

    Ratings only. Converting one to a percentage needs a per-level coefficient
    with no source in this API, so the only percentage here is a share.
    """
    if our_loadout is None or our_loadout.stats is None:
        return []
    theirs = [
        loadout.stats for loadout in their_loadouts if loadout.stats is not None
    ]
    if len(theirs) < MIN_SAMPLE_FOR_AGGREGATE:
        return []

    our_stats = our_loadout.stats
    our_budget = our_stats.total_secondary()
    findings = []
    for name, ours in our_stats.secondaries():
        ratings = [float(dict(stats.secondaries())[name]) for stats in theirs]
        their_median = median(ratings)
        if ours == their_median:
            continue
        our_share = ours / our_budget if our_budget else 0.0
        their_shares = [
            dict(stats.secondaries())[name] / stats.total_secondary()
            if stats.total_secondary()
            else 0.0
            for stats in theirs
        ]
        their_share = median(their_shares)
        if abs(our_share - their_share) < STAT_GAP_SHARE:
            continue
        low, high = observed_range(ratings)
        findings.append(
            Finding(
                id="compare.stats.rating",
                title=(
                    f"{our_name} carried {ours} {name} rating; "
                    f"the sample's median is {their_median:g}"
                ),
                detail=(
                    f"That is {our_share:.0%} of this player's secondary rating against "
                    f"{their_share:.0%} of the sample's. The share is the reading item level "
                    "cannot explain: a top parse holds more of every stat simply by "
                    "out-gearing this run."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"{name} rating {ours}",
                    f"sample median {their_median:g}, range {low:g} to {high:g} "
                    f"across {len(theirs)} references",
                    f"share of budget {our_share:.0%} against {their_share:.0%}",
                ),
            )
        )
    return findings
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_loadout_comparison.py -q
```

Expected: 29 passed.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/loadout.py tests/domain/comparison/test_loadout_comparison.py
```

Commit message:

```
Compare each secondary rating against the sample, and its share

The rating and its gap is the fact. The share of the player's own secondary
budget is the part item level cannot explain, because a top parse holds more
of every stat simply by out-gearing the run, and the raw gap alone would
restate a confound the report already prints.

No rating is converted to a percentage anywhere. That needs a per-level
coefficient with no source in this API.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 11: The curated consumable buff list

**Files:**
- Create: `data/consumable_buffs.toml`
- Modify: `src/wowperf/adapters/config/toml.py`, `src/wowperf/domain/season.py`
- Modify: `data/consumables.toml` (header amendment plus a `combat potion` category)
- Test: `tests/adapters/config/test_toml.py` (append)

**Interfaces:**
- Produces: `ConsumableBuffs(entries)` in `season.py` with
  `.ids_for(category: str) -> tuple[int, ...]` and `.categories() -> tuple[str, ...]`;
  `load_consumable_buffs(path=DEFAULT_CONSUMABLE_BUFFS_PATH) -> ConsumableBuffs`

- [ ] **Step 1: Write the failing tests**

```python
def test_the_consumable_buffs_file_loads_its_three_categories() -> None:
    buffs = load_consumable_buffs()
    assert set(buffs.categories()) == {"flask", "food", "augment rune"}


def test_well_fed_carries_every_id_it_was_measured_under() -> None:
    # Measured 2026-09-14: `Well Fed` spans six ability ids. One id per
    # category would miss five of them and report a fed player as unfed.
    assert len(load_consumable_buffs().ids_for("food")) >= 6


def test_an_unknown_category_has_no_ids() -> None:
    assert load_consumable_buffs().ids_for("weapon oil") == ()


def test_the_combat_potion_category_is_loaded_from_consumables() -> None:
    names = {category.name for category in load_consumables().categories}
    assert "combat potion" in names
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/config/test_toml.py -v -k "consumable_buffs or combat_potion"
```

Expected: `ImportError: cannot import name 'load_consumable_buffs'`.

- [ ] **Step 3: Write the implementation**

`data/consumable_buffs.toml`:

```toml
# Consumable buffs a player applies before a pull, grouped by what they are.
# No API exposes this list, so it is maintained by hand and dated.
#
# Ids, never names. Measured 2026-09-14 over the aura tables already in this
# project's response cache: `Rune Mastery` (374585) and `Rune of Sanguination`
# (326808) are Death Knight abilities, so any prefix match on "Rune" mislabels
# them as consumables.
#
# One id per category is not enough either. `Well Fed` alone spans six ability
# ids, and `Hearty Well Fed` is a further variant, so a list carrying one would
# report a fed player as unfed whenever the food changed.
#
# `Vantus Rune: ...` is deliberately absent: it is a per-boss buff, not the
# augment rune this category is about.
verified = "2026-09-14"

[flask]
ability_ids = [
  1235057,  # Flask of Thalassian Resistance
  1235110,  # Flask of the Blood Knights
  1235108,  # Flask of the Magisters
  1235111,  # Flask of the Shattered Sun
  1250533,  # Freightrunner's Flask
]

[food]
ability_ids = [
  451920,
  1219182,
  1219185,
  1232490,
  1232585,
  1294727,   # the six ids all reported as `Well Fed`
  1233724,
  1284644,   # the two reported as `Hearty Well Fed`
]

["augment rune"]
ability_ids = [
  1287770,  # Rune of the Versatile Warrior
  1287771,  # Rune of Masterful Cunning
  1287772,  # Rune of Critical Power
  1287774,  # Rune of Burning Haste
  1287665,  # Rune of Lingering
  1287955,  # Rune of Void-Tainted Shell
  1287978,  # Rune of Lynxlike Reflexes
]
```

In `data/consumables.toml`, amend the header note that excludes the combat potion group — do not
delete it — adding:

```toml
# Amended 2026-09-14: the combat potion group below is read for comparison
# against a sample. It stays out of the death-gated survival analysis, which is
# what the exclusion above was about: a damage potion shares no cooldown with a
# health potion in the sense that matters there.
```

and add the category:

```toml
["combat potion"]
cooldown_seconds = 300.0
ability_ids = [
  1236994,  # Potion of Recklessness
]
```

In `src/wowperf/domain/season.py`, beside `Consumables`:

```python
class ConsumableBuffs(Frozen):
    """Buff ability ids by consumable category, from the committed TOML file.

    A tuple of pairs rather than a mapping, like every other curated list here:
    the domain layer's values are frozen and hashable, and a dict is neither.
    """

    entries: tuple[tuple[str, tuple[int, ...]], ...] = ()

    def categories(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.entries)

    def ids_for(self, category: str) -> tuple[int, ...]:
        """The ability ids in this category, or `()` if the list has none."""
        for name, ability_ids in self.entries:
            if name == category:
                return ability_ids
        return ()
```

In `src/wowperf/adapters/config/toml.py`:

```python
DEFAULT_CONSUMABLE_BUFFS_PATH = DATA_DIR / "consumable_buffs.toml"


def load_consumable_buffs(
    path: Path = DEFAULT_CONSUMABLE_BUFFS_PATH,
) -> ConsumableBuffs:
    """Consumable buff ids by category, from the committed TOML file.

    `verified` is a date the file carries for a reader, not a field the domain
    uses, so it is skipped like any other non-table key.
    """
    raw = _read(path)
    entries = []
    for name, block in raw.items():
        if not isinstance(block, dict):
            continue
        entries.append((name, tuple(block.get("ability_ids", ()))))
    return ConsumableBuffs(entries=tuple(entries))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/config/ -q
```

Expected: all passed.

Then confirm the wheel still carries the data files, since none of them is a `.py` and no test
running from the source tree would notice one missing:

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_packaging.py -q
```

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add data/consumable_buffs.toml data/consumables.toml src/wowperf/adapters/config/toml.py src/wowperf/domain/season.py tests/adapters/config/
```

Commit message:

```
List the consumable buffs by id, and date the list

By id and never by name. Two Death Knight abilities are called Rune Mastery
and Rune of Sanguination, so a prefix rule on "Rune" would report a class
ability as a consumable. Well Fed spans six ids, so a list carrying one would
report a fed player as unfed whenever the food changed.

The combat potion group joins consumables.toml with the reason it was
excluded left standing and narrowed, rather than deleted: it stays out of the
death-gated survival analysis and is read only for comparison.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 12: `compare.consumables.buff`

**Files:**
- Create: `src/wowperf/domain/comparison/consumables.py`
- Test: `tests/domain/comparison/test_comparison_consumables.py`

**Interfaces:**
- Consumes: `ConsumableBuffs` (Task 11), `PlayerAuras`, `ParseSample`
- Produces: `compare_consumable_buffs(our_auras: PlayerAuras | None, our_name: str, sample: ParseSample, buffs: ConsumableBuffs) -> list[Finding]`

- [ ] **Step 1: Write the failing tests**

```python
# ABOUTME: Behaviour tests for comparing what a player drank against what the sample drank.
# ABOUTME: Absent auras are a real state; a player with no aura table is not a player with none.

from wowperf.domain.auras import Aura, PlayerAuras
from wowperf.domain.comparison.consumables import compare_consumable_buffs
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.findings import Confidence
from wowperf.domain.season import ConsumableBuffs

BUFFS = ConsumableBuffs(
    entries=(("flask", (1235057, 1235110)), ("food", (451920, 1219182)))
)
OUR_NAME = "Emberkin (actor 693)"


def auras_with(*ability_ids: int) -> PlayerAuras:
    return PlayerAuras(
        actor_id=693,
        on_self=tuple(
            Aura(ability_id=i, name=f"aura {i}", total_uptime_ms=600_000, uses=1)
            for i in ability_ids
        ),
    )


def a_sample_with(*per_member: tuple[int, ...]) -> ParseSample:
    """One member per tuple, each carrying the auras that tuple names."""
    ...  # build ParseMember values following tests/domain/comparison/test_uptime.py


def test_a_category_the_whole_sample_had_and_we_did_not_is_a_finding() -> None:
    sample = a_sample_with((1235057,), (1235110,), (1235057,), (1235057,), (1235110,))
    findings = compare_consumable_buffs(auras_with(451920), OUR_NAME, sample, BUFFS)
    assert [f.id for f in findings] == ["compare.consumables.buff"]
    assert "flask" in findings[0].title
    assert findings[0].confidence is Confidence.MEASURED


def test_any_id_in_the_category_counts_as_having_it() -> None:
    # Well Fed spans six ids. Which one a player drank is not the question.
    sample = a_sample_with(*[(451920,)] * 5)
    assert compare_consumable_buffs(auras_with(1219182), OUR_NAME, sample, BUFFS) == []


def test_a_category_only_some_of_the_sample_had_is_not_a_finding() -> None:
    sample = a_sample_with((1235057,), (1235057,), (), (), ())
    assert compare_consumable_buffs(auras_with(), OUR_NAME, sample, BUFFS) == []


def test_nothing_is_compared_when_our_aura_table_is_absent() -> None:
    # Absent auras are a real state and not an empty one: a player whose table
    # was never fetched must not be reported as having drunk nothing.
    sample = a_sample_with(*[(1235057,)] * 5)
    assert compare_consumable_buffs(None, OUR_NAME, sample, BUFFS) == []


def test_a_member_with_no_aura_table_is_not_counted_as_lacking_it() -> None:
    sample = a_sample_with((1235057,), (1235057,), (1235057,), None, None)
    findings = compare_consumable_buffs(auras_with(), OUR_NAME, sample, BUFFS)
    assert "3 of 3" in " ".join(findings[0].evidence)


def test_nothing_is_compared_below_the_sample_floor() -> None:
    sample = a_sample_with((1235057,), (1235057,))
    assert compare_consumable_buffs(auras_with(), OUR_NAME, sample, BUFFS) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_comparison_consumables.py -v
```

Expected: collection error — `No module named 'wowperf.domain.comparison.consumables'`.

- [ ] **Step 3: Write the implementation**

```python
# ABOUTME: Compares what a player drank before a pull against what the sample drank.
# ABOUTME: An absent aura table is unknown, never a player who drank nothing.

from collections.abc import Sequence

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, ParseSample
from wowperf.domain.comparison.statistics import count_phrase
from wowperf.domain.findings import Confidence, Finding, quantifier_for
from wowperf.domain.season import ConsumableBuffs


def _carries(auras: PlayerAuras, ability_ids: Sequence[int]) -> bool:
    """Whether any id in this category was on the player at all.

    Any id, because a category is the unit: `Well Fed` spans six ability ids
    measured 2026-09-14, and which of them a player drank is not the question
    the finding asks.
    """
    wanted = frozenset(ability_ids)
    return any(aura.ability_id in wanted for aura in auras.on_self)


def compare_consumable_buffs(
    our_auras: PlayerAuras | None,
    our_name: str,
    sample: ParseSample,
    buffs: ConsumableBuffs,
) -> list[Finding]:
    """Consumable categories every comparable reference carried and this player did not.

    A member whose aura table was never fetched is left out of the count
    entirely rather than counted as lacking the buff — `ParseSample.aura_eligible`
    is what draws that line, and `compare.uptime.unavailable` already reports
    the absence once.
    """
    if our_auras is None:
        return []
    eligible = [member for member in sample.aura_eligible if member.auras is not None]
    if len(eligible) < MIN_SAMPLE_FOR_AGGREGATE:
        return []

    findings = []
    for category in buffs.categories():
        ability_ids = buffs.ids_for(category)
        if not ability_ids or _carries(our_auras, ability_ids):
            continue
        matching = sum(
            1
            for member in eligible
            if member.auras is not None and _carries(member.auras, ability_ids)
        )
        if matching < len(eligible):
            continue
        findings.append(
            Finding(
                id="compare.consumables.buff",
                title=(
                    f"{count_phrase(matching, len(eligible))} top parses carried a "
                    f"{category}; {our_name} did not"
                ),
                detail=(
                    f"No {category} buff appears on this player at any point in the run, and "
                    "every comparable reference carried one. What it was worth in damage is "
                    "not stated: nothing here can compute that."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"category {category}, {len(ability_ids)} known ability ids",
                    f"{matching} of {len(eligible)} references carried one",
                ),
                quantifier=quantifier_for(matching, len(eligible)),
            )
        )
    return findings
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_comparison_consumables.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/consumables.py tests/domain/comparison/test_comparison_consumables.py
```

Commit message:

```
Report a consumable the whole sample carried and this player did not

The category is the unit, not the id: Well Fed spans six ability ids and
which one a player drank is not the question. A reference whose aura table
was never fetched is left out of the count rather than counted as lacking
one, because an absent table is unknown and not an empty one.

What a missing flask cost in damage is not stated. Nothing here can compute
it, and a finding that guessed would be the kind of number this project
exists to refuse.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 13: `compare.consumables.potion`

**Files:**
- Modify: `src/wowperf/domain/comparison/consumables.py`
- Test: `tests/domain/comparison/test_comparison_consumables.py` (append)

**Interfaces:**
- Produces: `compare_potions(ours: LoadedRun, our_player: Player, our_name: str, sample: ParseSample, potion_ids: Sequence[int]) -> list[Finding]`

- [ ] **Step 1: Write the failing tests**

```python
def test_fewer_potions_than_the_sample_median_is_a_finding() -> None:
    findings = compare_potions(
        ours_casting(POTION, times=0), OURS, OUR_NAME, a_sample_casting_potion(2), (POTION,)
    )
    assert [f.id for f in findings] == ["compare.consumables.potion"]
    assert findings[0].confidence is Confidence.MEASURED


def test_matching_the_sample_median_is_not_a_finding() -> None:
    assert (
        compare_potions(
            ours_casting(POTION, times=2), OURS, OUR_NAME, a_sample_casting_potion(2), (POTION,)
        )
        == []
    )


def test_more_potions_than_the_sample_is_not_a_finding() -> None:
    assert (
        compare_potions(
            ours_casting(POTION, times=4), OURS, OUR_NAME, a_sample_casting_potion(2), (POTION,)
        )
        == []
    )


def test_the_finding_states_the_median_and_the_range() -> None:
    findings = compare_potions(
        ours_casting(POTION, times=0), OURS, OUR_NAME, a_sample_casting_potion(2), (POTION,)
    )
    joined = " ".join(findings[0].evidence)
    assert "2" in joined


def test_nothing_is_compared_below_the_sample_floor() -> None:
    sample = a_sample_casting_potion(2, members=2)
    assert compare_potions(ours_casting(POTION, times=0), OURS, OUR_NAME, sample, (POTION,)) == []


def test_no_potion_ids_means_no_comparison() -> None:
    assert compare_potions(ours_casting(POTION, 0), OURS, OUR_NAME, a_sample_casting_potion(2), ()) == []
```

Define `POTION = 1236994`, and write `ours_casting` / `a_sample_casting_potion` as local builders
following the same style as Task 7's.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_comparison_consumables.py -v -k potion
```

Expected: `ImportError: cannot import name 'compare_potions'`.

- [ ] **Step 3: Write the implementation**

```python
def _potion_casts(
    casts: Sequence[CastEvent], actor_id: int, potion_ids: frozenset[int]
) -> int:
    return sum(
        1
        for event in casts
        if event.actor_id == actor_id and event.ability_id in potion_ids
    )


def compare_potions(
    ours: LoadedRun,
    our_player: Player,
    our_name: str,
    sample: ParseSample,
    potion_ids: Sequence[int],
) -> list[Finding]:
    """How many combat potions this player drank, against the sample's median.

    Counted from casts rather than from auras. A damage potion is observable
    both ways, and the aura would give uptime, but the claim this finding makes
    is about presses and a press is what a cast is.

    Reported only when below the sample: a player who drank more has nothing to
    act on.
    """
    wanted = frozenset(potion_ids)
    if not wanted or not sample.can_aggregate(sample.members):
        return []

    ours_count = _potion_casts(ours.casts, our_player.actor_id, wanted)
    theirs: list[float] = []
    for member in sample.members:
        actor_id = their_actor_id(member, member.row.character_name)
        if actor_id is None:
            continue
        theirs.append(float(_potion_casts(member.casts, actor_id, wanted)))
    if len(theirs) < MIN_SAMPLE_FOR_AGGREGATE:
        return []

    their_median = median(theirs)
    if ours_count >= their_median:
        return []

    low, high = observed_range(theirs)
    return [
        Finding(
            id="compare.consumables.potion",
            title=(
                f"{our_name} drank {quantity(ours_count, 'combat potion', 'combat potions')}; "
                f"the sample's median is {their_median:g}"
            ),
            detail=(
                "Counted as presses across the whole run. What the difference was worth in "
                "damage is not stated: nothing here can compute that."
            ),
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            evidence=(
                f"{ours_count} combat potion casts in this run",
                f"sample median {their_median:g}, range {low:g} to {high:g} "
                f"across {len(theirs)} references",
            ),
        )
    ]
```

Add the imports: `CastEvent` from `events`, `LoadedRun`/`Player` from `model`, `their_actor_id`
from `comparison.spells`, `median`/`observed_range` from `comparison.statistics`, and `quantity`
from `findings`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_comparison_consumables.py -q
```

Expected: 12 passed.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/consumables.py tests/domain/comparison/test_comparison_consumables.py
```

Commit message:

```
Count combat potions against what the sample drank

From casts rather than auras. A damage potion is observable both ways and the
aura would give uptime, but the claim here is about presses and a press is
what a cast is.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 14: Fan the new families into the service

**Files:**
- Modify: `src/wowperf/domain/comparison/service.py:86-127`
- Modify: `src/wowperf/domain/report/players.py:54`
- Test: `tests/domain/comparison/test_service.py` (append), `tests/domain/report/test_build_players.py` (append)

**Interfaces:**
- Consumes: every family from Tasks 7 to 13
- Produces: ids `compare.gear.*`, `compare.stats.*` and `compare.consumables.*` carrying a
  `player_slug`, routed to the Players tab

- [ ] **Step 1: Write the failing tests**

```python
def test_the_gear_and_stat_families_reach_the_comparison() -> None:
    findings = compare(a_loaded_run(), [a_subject_with_a_loadout()], ...)
    ids = {finding.id.rsplit(".", 1)[0] for finding in findings}
    assert any(i.startswith("compare.stats.") for i in ids)


def test_every_new_family_carries_the_player_it_is_about() -> None:
    findings = compare(a_loaded_run(), [a_subject_with_a_loadout()], ...)
    new = [
        f
        for f in findings
        if f.id.startswith(("compare.gear.", "compare.stats.", "compare.consumables."))
    ]
    assert new
    assert all(f.player_slug for f in new)
```

and in `tests/domain/report/test_build_players.py`:

```python
def test_the_new_comparison_families_land_on_a_player_card() -> None:
    for prefix in ("compare.gear.", "compare.stats.", "compare.consumables."):
        assert any(prefix.startswith(known) or known.startswith(prefix)
                   for known in COMPARISON_PREFIXES), prefix
```

Follow the existing builders in `tests/domain/comparison/test_service.py` for `a_loaded_run` and
the subject; do not invent new ones.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/comparison/test_service.py tests/domain/report/test_build_players.py -v -k "gear or stat or consumable"
```

Expected: FAIL — no such families are produced, and `COMPARISON_PREFIXES` names none of them.

- [ ] **Step 3: Write the implementation**

In `service.py`, extend the return of `_compare_player`:

```python
    their_loadouts = tuple(
        loadout
        for member in parse.members
        for loadout in (_loadout_of(member),)
        if loadout is not None
    )
    return [
        *compare_spells_sample(ours, subject.player, subject.display_name, parse),
        *compare_trash_spells_sample(ours, subject.player, subject.display_name, parse),
        *compare_talents(...),
        *compare_uptime_sample(ours.run, subject.our_auras, subject.display_name, parse),
        *compare_enchants(subject.player.loadout, their_loadouts, subject.display_name),
        *compare_tier(subject.player.loadout, their_loadouts, subject.display_name),
        *compare_stats(subject.player.loadout, their_loadouts, subject.display_name),
        *compare_consumable_buffs(
            subject.our_auras, subject.display_name, parse, subject.consumable_buffs
        ),
        *compare_potions(
            ours, subject.player, subject.display_name, parse, subject.potion_ids
        ),
    ]
```

with the helper:

```python
def _loadout_of(member: ParseMember) -> Loadout | None:
    """That member's own player's loadout, found the way every other row finds them."""
    player = find_player(member.run, member.row.character_name)
    return player.loadout if player is not None else None
```

`ComparisonSubject` gains the two curated-data fields, following the pattern by which
`build_players` already takes `defensives` and `throughput` as explicit parameters:

```python
    consumable_buffs: ConsumableBuffs = ConsumableBuffs()
    potion_ids: tuple[int, ...] = ()
```

The caller in `cli.py` supplies them from `load_consumable_buffs()` and from the `combat potion`
category of `load_consumables()`.

In `report/players.py`:

```python
COMPARISON_PREFIXES = (
    "compare.spells.",
    "compare.talents",
    "compare.uptime.",
    "compare.gear.",
    "compare.stats.",
    "compare.consumables.",
)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q
```

Expected: the whole offline suite passes. If a golden render test now differs, inspect the diff
before regenerating: a new family on the page is expected, a changed existing row is not.

- [ ] **Step 5: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/service.py src/wowperf/domain/report/players.py src/wowperf/cli.py tests/
```

Commit message:

```
Put gear, stats and consumables on the player's card

The comparison modules still know nothing about the roster. The service
appends the slug, as it already does for the four families before these, and
the report routes by prefix, which is why the id is a suffix.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Task 15: End to end against the real API

**Files:**
- Test: `tests/e2e/test_loadout_e2e.py`

Real data has found the worst defect in every plan this project has run; the offline suite passed
each time. This task is not optional.

**Interfaces:**
- Consumes: everything above

- [ ] **Step 1: Write the test**

```python
# ABOUTME: End-to-end: a real report's loadouts, against the live API, no mocks.
# ABOUTME: Spends quota. Marked e2e so the offline gate never runs it.

import os
from pathlib import Path

import pytest

from wowperf.cli import build_repository
from wowperf.domain.loadout import TIER_SLOTS
from wowperf.urls import parse_report_url

pytestmark = pytest.mark.e2e

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


def a_loaded_report(tmp_path: Path):
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )
    code, fight = parse_report_url(REPORT)
    return build_repository(tmp_path).load(code, fight)


def test_every_player_in_a_real_report_gets_a_loadout(tmp_path: Path) -> None:
    loaded = a_loaded_report(tmp_path)
    assert loaded.run.players
    assert all(player.loadout is not None for player in loaded.run.players)


def test_a_real_loadout_carries_eighteen_slots_and_a_stat_block(tmp_path: Path) -> None:
    loaded = a_loaded_report(tmp_path)
    player = loaded.run.players[0]
    assert player.loadout is not None
    assert len(player.loadout.items) == 18
    assert player.loadout.stats is not None
    assert player.loadout.stats.total_secondary() > 0


def test_a_real_loadout_counts_tier_pieces_in_the_plausible_range(tmp_path: Path) -> None:
    # Measured 2026-09-14: real counts ran 4 or 5. A count above 5 means the
    # slot rule folded a non-tier set in, which is the defect this guards.
    loaded = a_loaded_report(tmp_path)
    for player in loaded.run.players:
        assert player.loadout is not None
        assert 0 <= player.loadout.tier_pieces() <= len(TIER_SLOTS)
```

There is no `repository` fixture in `tests/e2e/` — the established pattern is
`build_repository(tmp_path)` plus a `WOWPERF_E2E_REPORT` environment variable, and
`repository.load(code, fight)` returns a single `LoadedRun`, not a pair. Read
`tests/e2e/test_compare_e2e.py` before writing this file and follow it; do not add a second way
of building a repository.

- [ ] **Step 2: Run it**

```bash
export PATH="$HOME/.local/bin:$PATH" && WOWPERF_E2E_REPORT=VCGkLQtPwNRA8HhD uv run pytest tests/e2e/test_loadout_e2e.py -m e2e -q
```

Expected: passed. This spends roughly 2 points per report against a 3600-point hour, and the
command prints where the points went.

- [ ] **Step 3: Run the full analysis on a real run and read the output**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run wowperf analyze VCGkLQtPwNRA8HhD --fight 1 --all-players
```

Read the findings JSON. Confirm by eye, and report to RwlRwlRwlRwl rather than asserting it
silently:

- no `compare.spells.missing` detail still reads "either a talent not taken or a button not
  pressed"
- any `compare.gear.missing_item` names an item the analysed player genuinely lacks
- no stat row states a percentage of a rating
- the point total printed at the end rose by roughly 12, not by more

- [ ] **Step 4: Commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy && uv run pytest -q
```

```bash
/mingw64/bin/git add tests/e2e/test_loadout_e2e.py
```

Commit message:

```
Hold the loadout to a real report

Every plan in this project has had its worst defect survive the offline suite
and appear on the first live run. The tier bound is the one that matters
here: a count above five means the slot rule folded a non-tier set in, which
is exactly what the naive reading of a set id does.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Self-Review

**Spec coverage.** §2.1 stat block → Tasks 3, 4, 10. §2.2 talents absent → no task, correctly:
the plan changes nothing about talents. §2.3 gear → Tasks 3, 4. §2.4 slots → Task 1 (`TIER_SLOTS`).
§2.5 name join → Tasks 6, 7. §2.6 tier rule → Tasks 1, 9. §2.7 enchant rule → Task 8.
§2.8 consumable ids → Task 11. §3.1 items 1–5 → Tasks 1–13. §4 fetch scope → Task 5, whose test
asserts the speed axis spends nothing. §5 three branches → Task 7. §6.1–6.5 → Tasks 7–13.
§7 domain model → Tasks 1, 2. §8 report → Task 14. §9 amendment → **gap**, see below.
§10 testing → every task, plus Task 15.

**One gap found and left deliberate.** Design §9 narrows the confound disclaimer at
`confounds.py:110`, and no task above touches it. It is one sentence of prose in a module this
plan otherwise does not enter, and folding it into Task 9 would mix a wording change into a
finding's test cycle. **Do it as a trailing commit after Task 14**, once
`compare.gear.missing_item` actually exists to be pointed at — amending the disclaimer before the
finding ships would make the file claim something untrue.

**Placeholder scan.** Three steps say "follow the existing builders rather than inventing new
ones" — Tasks 5, 7, 12, 13, 15. That is deliberate and is not a placeholder: this repository has
no shared test-factory module, every test file defines its own local `a_*` helpers, and naming a
factory here that does not exist would be worse than pointing at the file that has one. Every such
reference names the exact file and line to read.

**Type consistency.** `Loadout.stats` is `StatBlock | None` in Task 1 and read as optional in
Tasks 4, 10. `item_sourced` returns `EquippedItem | None` in Task 6 and is consumed that way in
Task 7. `compare_enchants`, `compare_tier` and `compare_stats` all take
`(our_loadout, their_loadouts, our_name)` in that order, Tasks 8–10 and 14.
`build_run(report, fight, talents=None, loadouts=None)` is defined in Task 5 and called that way
nowhere else. `ConsumableBuffs.ids_for` / `.categories` are defined in Task 11 and used in
Task 12.
