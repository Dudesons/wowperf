# Night comparison coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every boss on the night page is compared against reference kills: the mechanics
axis on every pull, the boss found by the fight's own enemies, a council's bosses summed, and
kill speed on kills.

**Architecture:** Our own fight's enemy list rides in the one `Fights` query the report
already issues. A pure domain rule picks the boss (or a council's bosses) from it, and a pure
helper sums a council's damage graphs. The pace comparison loses its kill gate and gains kill
wording; a new `compare.kill.time` finding reads the reference kills' durations the mechanics
sample already carries. `raid` loads pace on kills, and `night` draws the mechanics sample and
pace for every pull exactly as `raid` does for one.

**Tech Stack:** Python 3.12, `uv`, pytest, pydantic `Frozen` models, httpx `MockTransport` for
offline adapter and CLI tests, Typer CLI, Jinja2 (untouched here).

**Spec:** `docs/plans/2026-10-01-raid-leader-night-design.md`, section 4 (sub-slice 1). Read §4
and §6 to §9 before any task. Sub-slice 2 (§5, the page) is a separate plan.

## Global Constraints

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`,
  `jinja2`, or touches the disk.
- **Every finding carries a confidence badge.** `compare.kill.time` is `measured`;
  `compare.pace.boss` stays `derived` on a kill as on a wipe.
- **Never invent an API field.** The only new field is fight-level `enemyNPCs { id gameID }` on
  `Fights`, already read on the same `ReportFight` type by `REFERENCE_FIGHT_QUERY` and probed
  live on 2026-10-01 (Task 1 records it).
- **No hand-written boss knowledge.** The boss is found from the log's own boss flag, the
  fight's own enemies and the fight's own name. No data file maps encounters to bosses.
- **Every code file starts with two `ABOUTME: ` lines.**
- **Tests never carry a real character name.** Use `Emberkin`, `Stonewake`, `Bríala`,
  `Кириллица`. Boss names in tests are invented ("The Test Colossus", "Grimtooth the Vile").
- **Commits:** imperative subject, no `feat:`/`fix:` prefix, body says why, plain ASCII only,
  ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never `--no-verify`.
  Commit with `/mingw64/bin/git` (the bare `git` is rewritten by a hook and can refuse).
- **Toolchain:** every Bash command that runs `uv` starts with
  `export PATH="$HOME/.local/bin:$PATH";`. Tests: `uv run pytest`, lint `uv run ruff check .`,
  types `uv run mypy` (no paths).
- **The brief's code is a strong default, not scripture.** If a worked test or snippet fails,
  diagnose whether the fixture or the implementation is wrong before changing either, and
  report the evidence.
- **Before asserting on a literal, grep the tree for it.** If it is already on the page or in
  the output for another reason, the assertion is vacuous; pick a literal only this change
  can produce.
- **A test changed on purpose is named, not silently edited.** Where this plan changes what an
  existing test pins, the task lists that test and the new expectation. Any other existing test
  that fails is a finding to report, not a test to rewrite.

## File Structure

| File | Change | Responsibility |
| --- | --- | --- |
| `src/wowperf/adapters/wcl/queries.py` | modify | `FIGHTS_QUERY` reads each fight's `enemyNPCs` |
| `src/wowperf/adapters/wcl/ingest.py` | modify | `build_encounter` carries them as `Encounter.enemies` |
| `src/wowperf/domain/encounter.py` | modify | `Encounter.enemies: tuple[EnemyNpc, ...] = ()` |
| `src/wowperf/domain/comparison/pace_boss.py` | modify | `find_bosses` replaces `find_boss_actor` |
| `src/wowperf/domain/comparison/pace_curve.py` | modify | `sum_boss_damage` |
| `src/wowperf/domain/comparison/pace.py` | modify | `NO_BOSS`, `GRIDS_DIFFER`, kill wording, no kill gate |
| `src/wowperf/adapters/wcl/pace.py` | modify | `load_pace_sample` over one boss or a council |
| `src/wowperf/domain/comparison/kill_time.py` | create | `compare.kill.time` |
| `src/wowperf/domain/report/raid_ledger.py` | modify | place `compare.kill.` on the Damage tab |
| `src/wowperf/domain/analysis/encounter_service.py` | modify | run `analyse_kill_time` |
| `src/wowperf/cli.py` | modify | `raid` loads pace on kills; `night` draws mechanics and pace for every pull |
| `src/wowperf/domain/analysis/attempt_shape.py` | modify | remove `no_sample_on_the_night` |
| `src/wowperf/domain/comparison/night_axis.py` | modify | the page-level sentence names what the night now compares |
| `src/wowperf/domain/report/night_build.py` | modify | a kill pull's parse sentence is the night's, not a wipe's |
| `.claude/skills/wcl-api/SKILL.md` | modify | dated rows: fight enemies, boss-framed adds, council grids, costs |
| `.claude/skills/analyzing-a-run/SKILL.md` | modify | the `night` section says what it now draws |

---

### Task 1: Our own fight carries its enemy list

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py` (`FIGHTS_QUERY`, the `fights(translate: true)` selection)
- Modify: `src/wowperf/domain/encounter.py` (`Encounter`)
- Modify: `src/wowperf/adapters/wcl/ingest.py` (`build_encounter`)
- Modify: `.claude/skills/wcl-api/SKILL.md`
- Test: `tests/adapters/wcl/test_ingest.py`

**Interfaces:**
- Produces: `Encounter.enemies: tuple[EnemyNpc, ...]` (default `()`), `EnemyNpc` from
  `wowperf.domain.model` (`actor_id: int`, `game_id: int`), in the order the log lists them.

- [ ] **Step 1: Write the failing tests**

Add beside the existing `build_encounter` tests in `tests/adapters/wcl/test_ingest.py` (they use
`a_raid_report()` and `a_raid_fight(**overrides)`; `EnemyNpc` imports from
`wowperf.domain.model`):

```python
def test_a_boss_fight_carries_its_own_enemies_in_the_order_the_log_lists_them() -> None:
    fight = a_raid_fight(
        enemyNPCs=[{"id": 203, "gameID": 259181}, {"id": 174, "gameID": 266403}]
    )
    encounter = build_encounter(a_raid_report(), fight, partition=1)
    assert encounter.enemies == (
        EnemyNpc(actor_id=203, game_id=259181),
        EnemyNpc(actor_id=174, game_id=266403),
    )


def test_a_boss_fight_without_an_enemy_list_carries_none() -> None:
    encounter = build_encounter(a_raid_report(), a_raid_fight(), partition=1)
    assert encounter.enemies == ()
```

If `a_raid_fight` already sets `enemyNPCs`, the second test is vacuous: check first, and pass
`enemyNPCs=None` explicitly if it does.

- [ ] **Step 2: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl/test_ingest.py -k enemies -v`
Expected: FAIL, `Encounter` has no attribute `enemies`.

- [ ] **Step 3: Implement**

In `FIGHTS_QUERY`, add the fight-level selection directly after `friendlyItemLevels` (the
`dungeonPulls { ... enemyNPCs }` selection stays as it is):

```
        friendlyItemLevels
        enemyNPCs { id gameID }
        dungeonPulls {
```

In `src/wowperf/domain/encounter.py`, import `EnemyNpc` beside the existing
`from wowperf.domain.model import DamageDoneSeries, Player`, and add after `phases`:

```python
    # This fight's own enemy actors, as the log lists them. The boss lookup reads
    # these rather than the report's whole actor list: a report's `masterData`
    # spans every fight, and some adds carry a boss frame (wcl-api skill,
    # 2026-10-01). Empty where the response carried no list.
    enemies: tuple[EnemyNpc, ...] = ()
```

In `build_encounter`, pass it (import `EnemyNpc` from `wowperf.domain.model`):

```python
        enemies=tuple(
            EnemyNpc(actor_id=int(npc["id"]), game_id=int(npc["gameID"]))
            for npc in fight.get("enemyNPCs") or ()
            if npc.get("id") is not None and npc.get("gameID") is not None
        ),
```

- [ ] **Step 4: Record the probe in the API skill**

Add a dated section to `.claude/skills/wcl-api/SKILL.md` near the existing "A damage graph can be
scoped to the boss..." section (2026-09-27), stating what was measured on 2026-10-01 against
report `6jHcTvtB4XAMGZag` with `REFERENCE_FIGHT_QUERY` on our own fights and
`BOSS_DAMAGE_GRAPH_QUERY`:

- Fight-level `enemyNPCs { id gameID }` is read on our own report's fights too; `FIGHTS_QUERY`
  now carries it.
- A boss-flagged actor's name can differ from the fight's: fights 20, 29 and 38, named
  "Vashnik the Malignant", list one boss-flagged enemy, named "Vashnik" (id 203, gameID
  259181). The exact-name rule found no boss on every such pull.
- A single-boss fight can list boss-flagged adds: fight 3 ("Nek'zali the Soulcoiler") lists
  three boss-flagged enemies, the boss plus "Drowned Echo" and "Echo of Jawae".
- A council lists its bosses and no boss-flagged actor named after the fight: fights 8 and 15
  ("Entombed Sentinels") list "Blood of Ula'tek" (gameID 258558) and "Breath of Ula'tek"
  (258557). Their two boss-scoped graphs came back on one grid: interval 952.2875 ms on fight
  8 and 1657.2875 ms on fight 15, lead 0, 241 buckets each.
- The probe cost 17 points for six `ReferenceFight` lookups (2 points each) and four graphs.

Name no player. The skill's prose is checked by `tests/test_skills.py` for command flags only.

- [ ] **Step 5: Run the tests and the suite**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl -q`
Expected: PASS. If a test pins `FIGHTS_QUERY`'s text or its cache key, read it: a changed
query is intended here, and the test's own docstring says whether it should follow.

- [ ] **Step 6: Commit**

```bash
/mingw64/bin/git add src/wowperf/adapters/wcl/queries.py src/wowperf/domain/encounter.py src/wowperf/adapters/wcl/ingest.py tests/adapters/wcl/test_ingest.py .claude/skills/wcl-api/SKILL.md
/mingw64/bin/git commit -m "Carry each boss fight's own enemy list" -m "The boss lookup needs to know which actors fought in this fight; the report's actor list spans every fight and flags some adds as bosses." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Find the boss, or a council's bosses, among the fight's enemies

**Files:**
- Modify: `src/wowperf/domain/comparison/pace_boss.py`
- Test: `tests/domain/comparison/test_pace_boss.py`

**Interfaces:**
- Produces: `find_bosses(actors: tuple[NpcActor, ...], enemy_ids: frozenset[int], fight_name: str) -> tuple[NpcActor, ...]`.
  `()` is no boss; one actor is a single boss; two or more is a council, in `actors` order.
- `find_boss_actor` stays until Task 4 removes it with its last caller.

The rule, in order:

1. Candidates are actors with `sub_type == "Boss"` whose `actor_id` is in `enemy_ids`.
2. Among them, the ones *named after the fight*: the name equals the fight name, or the fight
   name begins with the name followed by a space ("Vashnik" / "Vashnik the Malignant"; never
   "Vash").
3. Exactly one named after the fight: that one, alone, even beside boss-flagged adds.
4. Two or more named after the fight: `()`. Unmeasured, so not guessed at.
5. None named after the fight: every candidate. One is a single boss under another name; two or
   more is a council; none is no boss.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/comparison/test_pace_boss.py` (keep the existing tests until Task 4):

```python
from wowperf.domain.comparison.pace_boss import find_bosses


def ids(bosses: tuple[NpcActor, ...]) -> list[int]:
    return [one.actor_id for one in bosses]


def test_a_boss_named_after_the_fight_wins_over_boss_framed_adds() -> None:
    actors = (
        actor(27, FIGHT, "Boss", 1),
        actor(106, "Drowned Whisper", "Boss", 2),
        actor(116, "Echo of the Deep", "Boss", 3),
    )
    assert ids(find_bosses(actors, frozenset({27, 106, 116}), FIGHT)) == [27]


def test_a_boss_whose_name_begins_the_fight_name_is_the_boss() -> None:
    actors = (actor(203, "Grimtooth", "Boss", 5), actor(174, "Grimtooth", "NPC", 6))
    assert ids(find_bosses(actors, frozenset({203, 174}), "Grimtooth the Vile")) == [203]


def test_a_name_that_is_only_a_prefix_of_a_word_is_not_named_after_the_fight() -> None:
    actors = (actor(1, "Grim", "Boss", 5), actor(2, "Grimtooth", "Boss", 6))
    assert ids(find_bosses(actors, frozenset({1, 2}), "Grimtooth the Vile")) == [2]


def test_a_lone_boss_flagged_enemy_under_another_name_is_the_boss() -> None:
    actors = (actor(9, "Heart of the Colossus", "Boss", 5),)
    assert ids(find_bosses(actors, frozenset({9}), FIGHT)) == [9]


def test_several_boss_flagged_enemies_none_named_after_the_fight_are_a_council() -> None:
    actors = (
        actor(131, "Blood of the Twins", "Boss", 11),
        actor(130, "Breath of the Twins", "Boss", 12),
        actor(126, "Venom Pool", "NPC", 13),
    )
    assert ids(find_bosses(actors, frozenset({131, 130, 126}), "The Entombed Twins")) == [
        131, 130,
    ]


def test_a_boss_flagged_actor_from_another_fight_is_not_a_candidate() -> None:
    actors = (actor(27, "Another Boss", "Boss", 1), actor(203, "Grimtooth", "Boss", 5))
    assert ids(find_bosses(actors, frozenset({203}), "Grimtooth the Vile")) == [203]


def test_two_bosses_named_after_the_fight_are_no_boss() -> None:
    actors = (actor(10, FIGHT, "Boss", 1), actor(11, FIGHT, "Boss", 2))
    assert find_bosses(actors, frozenset({10, 11}), FIGHT) == ()


def test_a_fight_listing_no_boss_flagged_enemy_has_no_boss() -> None:
    actors = (actor(60, FIGHT, "NPC", 1),)
    assert find_bosses(actors, frozenset({60}), FIGHT) == ()
```

Each test clears the other gates on purpose: the "another fight" test would still return `[27,
203]` as a council if the enemy filter were dropped, and the "prefix of a word" test would return
both if the space were dropped from the prefix rule.

- [ ] **Step 2: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_pace_boss.py -v`
Expected: FAIL, `ImportError: cannot import name 'find_bosses'`.

- [ ] **Step 3: Implement**

Add to `src/wowperf/domain/comparison/pace_boss.py`, and rewrite its two `ABOUTME` lines to:
`# ABOUTME: Picks the boss, or a council's bosses, out of one fight's own enemy actors.` and
`# ABOUTME: Boss flag, the fight's enemy list and the fight's name; no hand-written boss list.`

```python
def _named_after(name: str, fight_name: str) -> bool:
    """The fight's name, or its opening words: "Grimtooth" names "Grimtooth the Vile"."""
    return bool(name) and (name == fight_name or fight_name.startswith(f"{name} "))


def find_bosses(
    actors: tuple[NpcActor, ...], enemy_ids: frozenset[int], fight_name: str
) -> tuple[NpcActor, ...]:
    """The fight's boss, a council's bosses, or none, read from its own enemies.

    Measured 2026-10-01: a boss-flagged actor's name can differ from the
    fight's ("Vashnik" in "Vashnik the Malignant"), a single-boss fight can
    list boss-flagged adds beside its boss, and a council lists its bosses
    with none named after the fight. So the candidates are the boss-flagged
    actors this fight lists; one named after the fight is the boss alone;
    otherwise every candidate is, one being a boss under another name and
    several a council. Two named after the fight is a shape never measured,
    and is no boss rather than a guess.
    """
    candidates = tuple(
        one for one in actors if one.sub_type == BOSS_SUB_TYPE and one.actor_id in enemy_ids
    )
    named = [one for one in candidates if _named_after(one.name, fight_name)]
    if len(named) == 1:
        return (named[0],)
    if named:
        return ()
    return candidates
```

- [ ] **Step 4: Run to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_pace_boss.py -v`
Expected: PASS, eleven tests.

- [ ] **Step 5: Mutation check**

In a scratch copy (never the repository), remove each of: the `enemy_ids` filter, the space in
`f"{name} "`, the `if named: return ()` branch. Each must fail a distinct test above. Report the
three results.

- [ ] **Step 6: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/pace_boss.py tests/domain/comparison/test_pace_boss.py
/mingw64/bin/git commit -m "Find a fight's boss among its own enemies, or a council's bosses" -m "An exact name match missed a boss whose actor name is shorter than its fight's, and every council; the fight's own enemy list tells a boss from a boss-framed add." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Sum a council's damage onto one grid

**Files:**
- Modify: `src/wowperf/domain/comparison/pace_curve.py`
- Test: `tests/domain/comparison/test_pace_curve.py`

**Interfaces:**
- Produces: `sum_boss_damage(parts: Sequence[BossDamage]) -> BossDamage | None`. `None` for no
  parts or for parts on different grids (`interval_ms` or `lead_ms` differ). One part comes
  back equal to itself.

- [ ] **Step 1: Write the failing tests**

```python
from wowperf.domain.comparison.pace_curve import sum_boss_damage


def test_two_bosses_on_one_grid_sum_bucket_by_bucket_through_the_longer() -> None:
    blood = BossDamage(interval_ms=950.0, amounts=(10, 20, 30), lead_ms=0)
    breath = BossDamage(interval_ms=950.0, amounts=(1, 2), lead_ms=0)
    assert sum_boss_damage((blood, breath)) == BossDamage(
        interval_ms=950.0, amounts=(11, 22, 30), lead_ms=0
    )


def test_one_boss_sums_to_itself() -> None:
    one = BossDamage(interval_ms=1000.0, amounts=(4, 5), lead_ms=250)
    assert sum_boss_damage((one,)) == one


def test_parts_on_different_intervals_do_not_sum() -> None:
    parts = (BossDamage(interval_ms=950.0, amounts=(1,)), BossDamage(interval_ms=1000.0, amounts=(1,)))
    assert sum_boss_damage(parts) is None


def test_parts_with_different_leads_do_not_sum() -> None:
    parts = (
        BossDamage(interval_ms=1000.0, amounts=(1,), lead_ms=0),
        BossDamage(interval_ms=1000.0, amounts=(1,), lead_ms=500),
    )
    assert sum_boss_damage(parts) is None


def test_no_parts_is_no_damage() -> None:
    assert sum_boss_damage(()) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_pace_curve.py -k sum -v`
Expected: FAIL, `ImportError`.

- [ ] **Step 3: Implement**

Add after `BossDamage` in `pace_curve.py` (import `Sequence` from `collections.abc`):

```python
def sum_boss_damage(parts: Sequence[BossDamage]) -> BossDamage | None:
    """Several bosses' damage as one series, bucket by bucket, or None.

    A council's bosses are each read through their own graph. Measured
    2026-10-01, two such graphs of one fight came back on one grid, so their
    buckets add directly; parts on different grids are refused rather than
    resampled, since no fight measured has needed it. A shorter part adds
    nothing past its end.
    """
    if not parts:
        return None
    first = parts[0]
    if any(
        part.interval_ms != first.interval_ms or part.lead_ms != first.lead_ms
        for part in parts[1:]
    ):
        return None
    length = max(len(part.amounts) for part in parts)
    return BossDamage(
        interval_ms=first.interval_ms,
        amounts=tuple(
            sum(part.amounts[index] for part in parts if index < len(part.amounts))
            for index in range(length)
        ),
        lead_ms=first.lead_ms,
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_pace_curve.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/pace_curve.py tests/domain/comparison/test_pace_curve.py
/mingw64/bin/git commit -m "Sum a council's boss damage onto one grid" -m "A council's bosses each have their own graph; the pace comparison reads the raid's damage to all of them." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `load_pace_sample` reads one boss or a whole council

**Files:**
- Modify: `src/wowperf/domain/comparison/pace.py` (constants)
- Modify: `src/wowperf/adapters/wcl/pace.py`
- Modify: `src/wowperf/domain/comparison/pace_boss.py` (remove `find_boss_actor`)
- Test: `tests/adapters/wcl/test_pace.py`, `tests/domain/comparison/test_pace_boss.py`
- Test fixtures: `tests/test_cli.py` (`_raid_fights_payload`), `tests/test_cli_night.py` (`_night_fight`)

**Interfaces:**
- Consumes: `Encounter.enemies` (Task 1), `find_bosses` (Task 2), `sum_boss_damage` (Task 3).
- Produces: `NO_BOSS` and `GRIDS_DIFFER` in `wowperf.domain.comparison.pace` (replacing
  `NO_SINGLE_BOSS`); `GRIDS_DIFFER_REASON` in `wowperf.adapters.wcl.pace`.
  `load_pace_sample`'s signature is unchanged.

Wording:

```python
NO_BOSS = (
    "No enemy of this fight could be told apart as its boss: none carries the boss flag, "
    "or more than one is named after the fight."
)
GRIDS_DIFFER = (
    "This fight's bosses' damage graphs came back on different time grids, so their damage "
    "could not be added up."
)
```

and in the adapter `GRIDS_DIFFER_REASON = "the bosses' damage graphs came back on different time grids"`.

- [ ] **Step 1: Write the failing adapter tests**

In `tests/adapters/wcl/test_pace.py`:

- Give `_encounter()`'s default fields `enemies=(EnemyNpc(actor_id=OUR_BOSS_ACTOR_ID,
  game_id=BOSS_GAME_ID),)`, so every existing single-boss test still names its boss.
- **Deliberately replaced:** `test_a_council_report_finds_no_single_boss_and_asks_for_no_graph`
  pinned the old refusal. Replace it with the two tests below; its "asks for no graph" half
  survives in the no-boss test.

```python
def test_a_fight_with_no_boss_among_its_enemies_asks_for_no_graph(tmp_path: Path) -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        name = operation_name(json.loads(request.content)["query"]) or ""
        calls.append(name)
        if name == "NpcActors":
            return _npc_actors_response(_our_boss_actors())
        raise AssertionError(f"unexpected operation: {name}")

    encounter = _encounter(enemies=(EnemyNpc(actor_id=99, game_id=999),))
    sample, records = load_pace_sample(
        _client(handle), DiskCache(tmp_path / "own"), DiskCache(tmp_path / "ref"),
        encounter, (ReferenceKillRow(report_code="ref1", fight_id=1, size=20, duration_ms=300_000),),
    )

    assert sample.unavailable == NO_BOSS
    assert records == ()
    assert "BossDamageGraph" not in calls


def test_a_council_sums_its_bosses_on_both_sides(tmp_path: Path) -> None:
    """Two boss-flagged enemies, neither named after the fight: one graph each, summed.

    Our bosses deal 3 and 4 a second, so a sum reads 7 and either boss alone
    reads 3 or 4. The reference's two bosses sit at actor ids 31 and 32, not
    ours, so a lookup that reused our actor ids would ask for the wrong graphs.
    """
    graphs: list[tuple[str, int]] = []
    council = [
        {"id": 10, "gameID": 900, "name": "First Warden", "subType": "Boss"},
        {"id": 11, "gameID": 901, "name": "Second Warden", "subType": "Boss"},
    ]

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        name = operation_name(body["query"]) or ""
        variables = body.get("variables") or {}
        if name == "NpcActors":
            return _npc_actors_response(council)
        if name == "ReferenceFight":
            return _reference_fight_response(
                0, 300_000, [{"id": 31, "gameID": 900}, {"id": 32, "gameID": 901}]
            )
        if name == "BossDamageGraph":
            target = int(variables["targetId"])
            graphs.append((str(variables["code"]), target))
            per_second = {10: 3.0, 11: 4.0, 31: 30.0, 32: 40.0}[target]
            return _graph_response([per_second] * 300, point_start=0, interval=1000.0)
        raise AssertionError(f"unexpected operation: {name}")

    encounter = _encounter(
        boss_name="The Wardens",
        enemies=(EnemyNpc(actor_id=10, game_id=900), EnemyNpc(actor_id=11, game_id=901)),
    )
    row = ReferenceKillRow(report_code="ref1", fight_id=1, size=20, duration_ms=300_000)
    sample, records = load_pace_sample(
        _client(handle), DiskCache(tmp_path / "own"), DiskCache(tmp_path / "ref"),
        encounter, (row,),
    )

    assert sample.unavailable == ""
    assert sample.ours is not None and sample.ours.amounts[:2] == (7, 7)
    [reference] = sample.references
    assert reference.damage.amounts[:2] == (70, 70)
    assert sorted(graphs) == [(OUR_REPORT, 10), (OUR_REPORT, 11), ("ref1", 31), ("ref1", 32)]
    assert [one.loaded for one in records] == [True]
```

Also add:

- `test_a_reference_missing_one_of_the_councils_bosses_is_dropped`: the same council, a
  reference whose `enemyNPCs` lists only gameID 900; assert that reference's record is
  `loaded=False` with `reason == BOSS_NOT_AMONG_ENEMIES`, and `sample.unavailable ==
  BOSS_IN_NO_REFERENCE`.
- `test_our_councils_graphs_on_different_grids_withhold_with_that_reason`: our boss 10 answers
  `interval=1000.0` and boss 11 `interval=950.0`; assert `sample.unavailable == GRIDS_DIFFER`
  and `records == ()`.

Check `_graph_response`'s helper and `_reference_fight_response`'s signature against the file
before relying on them; both exist today.

- [ ] **Step 2: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl/test_pace.py -v`
Expected: the four new tests FAIL (`NO_BOSS` does not exist; the council withholds).

- [ ] **Step 3: Implement**

In `src/wowperf/domain/comparison/pace.py`: replace `NO_SINGLE_BOSS` with `NO_BOSS` and add
`GRIDS_DIFFER` (wording above). `grep -rn NO_SINGLE_BOSS src tests` and update every
reference; the night and raid CLI tests import it in their docstrings and comments only, but
check.

In `src/wowperf/adapters/wcl/pace.py`, replace the single-boss lookup and both graph reads
(new imports: `Sequence` from `collections.abc`, `find_bosses`, `BossDamage` and
`sum_boss_damage`, `NO_BOSS` and `GRIDS_DIFFER`). Keep everything else in the function as it is (the deaths read, the `PlayerSeries` building,
the `SAMPLE_SIZE` break, the error handling):

```python
def _boss_graphs(
    client: WclClient,
    cache: DiskCache,
    *,
    code: str,
    fight_id: int,
    start_ms: int,
    end_ms: int,
    target_ids: Sequence[int],
) -> tuple[BossDamage | None, bool, dict[int, BossDamage], bool]:
    """One graph per boss, summed: (total, grids differ, per-player, all from cache).

    The total is None when any graph carried no boss series, or when the
    graphs sat on different grids -- the second flag says which. A player's
    series sums their part of every graph they appear in.
    """
    totals: list[BossDamage | None] = []
    players: dict[int, list[BossDamage]] = {}
    all_hit = True
    for target_id in target_ids:
        payload, hit = _fetch(
            client, cache, BOSS_DAMAGE_GRAPH_QUERY,
            {"code": code, "fightId": fight_id, "startTime": float(start_ms),
             "endTime": float(end_ms), "targetId": target_id},
        )
        all_hit = all_hit and hit
        totals.append(build_boss_damage(payload, fight_start_ms=start_ms))
        for actor_id, series in build_player_boss_damage(payload, fight_start_ms=start_ms).items():
            players.setdefault(actor_id, []).append(series)
    if any(total is None for total in totals):
        return None, False, {}, all_hit
    summed = sum_boss_damage([total for total in totals if total is not None])
    if summed is None:
        return None, True, {}, all_hit
    per_player = {
        actor_id: combined
        for actor_id, parts in players.items()
        if (combined := sum_boss_damage(parts)) is not None
    }
    return summed, False, per_player, all_hit
```

Then in `load_pace_sample`:

```python
    bosses = find_bosses(
        build_npc_actors(actors_payload),
        frozenset(enemy.actor_id for enemy in encounter.enemies),
        encounter.boss_name,
    )
    if not bosses:
        return PaceSample(unavailable=NO_BOSS), ()

    if not references:
        ...unchanged...

    ours, grids_differ, our_series, _ = _boss_graphs(
        client, own_cache, code=encounter.report_code, fight_id=encounter.fight_id,
        start_ms=encounter.start_ms, end_ms=encounter.end_ms,
        target_ids=[boss.actor_id for boss in bosses],
    )
    if ours is None:
        return PaceSample(unavailable=GRIDS_DIFFER if grids_differ else NO_BOSS_DAMAGE), ()
```

`our_players` is built from `our_series` exactly as today. Inside the reference loop, replace
the one-boss `matching` block with a lookup per boss:

```python
            target_ids: list[int] = []
            absent = duplicated = False
            for boss in bosses:
                matching = [
                    enemy.actor_id for enemy in fight.enemies if enemy.game_id == boss.game_id
                ]
                absent = absent or not matching
                duplicated = duplicated or len(matching) > 1
                if len(matching) == 1:
                    target_ids.append(matching[0])
            if absent:
                boss_absent_count += 1
                records.append(_record(row, loaded=False, reason=BOSS_NOT_AMONG_ENEMIES))
                continue
            if duplicated:
                records.append(_record(row, loaded=False, reason=BOSS_APPEARS_TWICE))
                continue

            damage, grids_differ, series, damage_hit = _boss_graphs(
                client, reference_cache, code=row.report_code, fight_id=row.fight_id,
                start_ms=fight.start_ms, end_ms=fight.end_ms, target_ids=target_ids,
            )
            if damage is None:
                records.append(
                    _record(row, loaded=False,
                            reason=GRIDS_DIFFER_REASON if grids_differ else NO_BOSS_SERIES)
                )
                continue
```

and keep the rest of the loop body, reading `series` as before. Update the module docstring and
`load_pace_sample`'s docstring: the boss is found among the fight's own enemies, and a council's
bosses are each read and summed.

Remove `find_boss_actor` from `pace_boss.py` (its last caller is gone) and the three tests that
exercised it from `test_pace_boss.py` (**deliberately removed**: `find_bosses`' tests cover the
same three shapes — the named boss beside boss-framed adds and a same-named NPC, a council, and
two named after the fight).

- [ ] **Step 4: Give the CLI harnesses their fight's enemies**

Without this, every CLI test's pace withholds with `NO_BOSS`.

- `tests/test_cli_night.py`, `_night_fight`: add `"enemyNPCs"` naming the boss's own actor in
  `NpcActors`' answer: `[{"id": 8001, "gameID": FIRST_BOSS_GAME_ID}]` for
  `encounter_id == NIGHT_FIRST_BOSS`, else `[{"id": 8002, "gameID": SECOND_BOSS_GAME_ID}]`.
- `tests/test_cli.py`, `_raid_fights_payload`: the wipe fight (named "Ula'tek") gets
  `enemyNPCs=[{"id": PACE_BOSS_OUR_ACTOR_ID, "gameID": PACE_BOSS_GAME_ID}]`.

- [ ] **Step 5: Run the pace tests and the whole offline suite**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q`
Expected: PASS. Report any other test that changed outcome.

- [ ] **Step 6: Lint, types, commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run ruff check . && uv run mypy
/mingw64/bin/git add -A src tests
/mingw64/bin/git commit -m "Read the pace comparison over a fight's boss or a council's bosses" -m "Every wipe at a boss whose actor name differed from its fight's withheld as a council, and real councils were never compared." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Pace on a kill

**Files:**
- Modify: `src/wowperf/domain/comparison/pace.py`
- Test: `tests/domain/comparison/test_pace.py`

**Interfaces:**
- Produces: `analyse_pace(encounter, sample)` answers a kill with `compare.pace.boss` (no
  `compare.pace.projection`) or `compare.pace.unavailable`; `pace_reading` reads kills too.
  `KILL_DETAIL` constant. Per-player pace (`pace_player.py`) and the night's boss line
  (`pace_night.py`) keep their own kill gates: out of scope (design §8).

```python
TOP_KILLS_CAVEAT = (
    "The reference kills are the execution leaderboard's, among the best kills of this boss, "
    "so a kill behind their pace is the expected result; what this reads is from when it fell "
    "behind."
)
KILL_DETAIL = f"{BOSS_DETAIL} {TOP_KILLS_CAVEAT}"
```

- [ ] **Step 1: Write the failing tests**

```python
def _kill(duration_seconds: int) -> Encounter:
    return Encounter(
        report_code="ourreport0000000A", fight_id=4, encounter_id=3001,
        boss_name="The Test Colossus", difficulty=5, partition=1, size=20, kill=True,
        start_ms=0, end_ms=duration_seconds * 1000, players=(),
    )


def _per_second(amount: int, seconds: int) -> BossDamage:
    return BossDamage(interval_ms=1000.0, amounts=(amount,) * seconds)


KILL_SAMPLE = PaceSample(
    ours=_per_second(10, 200),
    references=tuple(
        PaceReference(duration_seconds=300, damage=_per_second(amount, 300))
        for amount in (18, 20, 22)
    ),
)
"""Our kill at 10 a second over 200 s against three kills at 18, 20 and 22 over 300 s.

The references outlast our kill, so the band is never cut and the comparison runs
through our own last second; 20 is the median and neither end, so the share names
the median."""


def test_a_kill_is_compared_through_its_last_second_with_the_kill_wording() -> None:
    [finding] = analyse_pace(_kill(200), KILL_SAMPLE)
    assert finding.id == PACE_ID
    assert finding.title == "Behind the kills' pace: 50% of their median boss damage by 3:20"
    assert "Compared through the kill at 3:20" in finding.evidence
    assert finding.detail == KILL_DETAIL


def test_a_kill_draws_no_projection() -> None:
    ids = [one.id for one in analyse_pace(_kill(200), KILL_SAMPLE)]
    assert ids == [PACE_ID]
    assert PROJECTION_ID not in ids


def test_a_wipe_keeps_the_wipe_wording_and_its_projection() -> None:
    wipe = _kill(200).model_copy(update={"kill": False})
    findings = analyse_pace(wipe, KILL_SAMPLE)
    assert [one.id for one in findings] == [PACE_ID, PROJECTION_ID]
    assert "Compared through the wipe at 3:20" in findings[0].evidence
    assert findings[0].detail == BOSS_DETAIL
```

Adjust imports and helper names to the file's own (`Encounter`, `BossDamage`, `PaceReference`,
`PaceSample`, `PACE_ID`, `PROJECTION_ID`, `BOSS_DETAIL`, `KILL_DETAIL`). If `test_pace.py`
already pins "A kill is never compared" (grep `kill=True` in it), that test is **deliberately
replaced** by the three above; name it in the report.

- [ ] **Step 2: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_pace.py -v`
Expected: the kill tests FAIL (`analyse_pace` returns `[]` on a kill).

- [ ] **Step 3: Implement**

In `pace.py`:

- `pace_reading`: drop `encounter.kill or` from its guard.
- `analyse_pace`: drop the kill early return. Compute `withheld_projection` only on a wipe; on
  a kill no projection line and no projection finding:

```python
    reason = withheld_reason(encounter, sample)
    if reason:
        return [_notice(reason)]
    reading = pace_reading(encounter, sample)
    assert reading is not None
    assert sample.ours is not None
    if encounter.kill:
        return [_pace_finding(reading, "", kill=True)]
    ...the wipe path, unchanged, calling _pace_finding(reading, withheld_projection, kill=False)
```

- `_pace_finding(reading, withheld_projection, *, kill: bool)`: the unbroken-band evidence line
  reads `f"Compared through the {'kill' if kill else 'wipe'} at {clock}"`, and
  `detail=KILL_DETAIL if kill else BOSS_DETAIL`.
- Update the docstrings of `analyse_pace` ("A kill is never compared" is now false) and of
  `withheld_reason` (drop the sentence about kills).

- [ ] **Step 4: Run the pace tests, then everything**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain -q`
Expected: PASS. `tests/domain/comparison/test_pace_player.py` and `test_pace_night.py` must
stay green untouched: they pin their own kill gates.

- [ ] **Step 5: Check the chart on a kill**

`raid_build` draws the pace chart when `pace_reading` returns a reading and the finding is on
the page, which is now true on a kill. `grep -rn -i "wipe" src/wowperf/domain/report/pace_chart.py src/wowperf/adapters/render/templates/` and fix any chart caption or label that
states a wipe, with a test asserting the kill's caption. Report what the grep found, even if
nothing.

- [ ] **Step 6: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/pace.py tests/domain/comparison/test_pace.py
/mingw64/bin/git commit -m "Read a kill's damage pace against the reference kills" -m "A kill has no comparison on the night page; where its damage fell behind the best kills is the kill-speed question a raid leader asks." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `compare.kill.time`

**Files:**
- Create: `src/wowperf/domain/comparison/kill_time.py`
- Modify: `src/wowperf/domain/analysis/encounter_service.py`
- Modify: `src/wowperf/domain/report/raid_ledger.py`
- Test: `tests/domain/comparison/test_kill_time.py`, `tests/domain/analysis/test_encounter_service.py`

**Interfaces:**
- Consumes: `MechanicsSample` / `MechanicsMember` / `ReferenceKillRow` from
  `wowperf.domain.comparison.mechanics`; `clock_text` from `wowperf.domain.comparison.pace`.
- Produces: `analyse_kill_time(encounter: Encounter, sample: MechanicsSample) -> list[Finding]`,
  `KILL_TIME_ID = "compare.kill.time"`, `KILL_TIME_DETAIL`.

- [ ] **Step 1: Write the failing tests**

`tests/domain/comparison/test_kill_time.py`:

```python
# ABOUTME: A kill's duration against the reference kills' own: median and range, or the slowest.
# ABOUTME: Pins the wording, the fallback below three kills, and silence on a wipe.

from wowperf.domain.comparison.kill_time import KILL_TIME_DETAIL, KILL_TIME_ID, analyse_kill_time
from wowperf.domain.comparison.mechanics import MechanicsMember, MechanicsSample, ReferenceKillRow
from wowperf.domain.encounter import Encounter
from wowperf.domain.findings import Confidence


def _encounter(*, kill: bool = True, seconds: float = 397.0) -> Encounter:
    return Encounter(
        report_code="ourreport0000000A", fight_id=4, encounter_id=3001,
        boss_name="The Test Colossus", difficulty=5, partition=1, size=20, kill=kill,
        start_ms=0, end_ms=int(seconds * 1000), players=(),
    )


def _sample(*seconds: int) -> MechanicsSample:
    return MechanicsSample(
        members=tuple(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code=f"ref{index}", fight_id=1, size=20, duration_ms=one * 1000
                ),
                abilities=(),
            )
            for index, one in enumerate(seconds)
        )
    )


def test_a_kill_is_read_against_the_kills_median_and_range() -> None:
    # Leaderboard order, not sorted: 300 s is the median, 320 s the mean, and
    # neither end of the range, so each figure can only come from its own rule.
    [finding] = analyse_kill_time(_encounter(), _sample(310, 240, 500, 300, 250))
    assert finding.id == KILL_TIME_ID
    assert finding.confidence is Confidence.MEASURED
    assert finding.title == "The kill took 6:37 against the kills' median of 5:00"
    assert finding.evidence == ("Against 5 reference kills", "Their range: 4:00 to 8:20")
    assert finding.detail == KILL_TIME_DETAIL


def test_below_three_kills_the_slowest_stands_alone() -> None:
    [finding] = analyse_kill_time(_encounter(), _sample(250, 300))
    assert finding.title == "The kill took 6:37 against the slowest reference kill's 5:00"
    assert finding.evidence == (
        "Against the slowest of 2 reference kills: fewer than three were available",
    )


def test_one_kill_is_named_as_the_one_reference() -> None:
    [finding] = analyse_kill_time(_encounter(), _sample(250))
    assert finding.title == "The kill took 6:37 against the slowest reference kill's 4:10"
    assert finding.evidence == (
        "Against the one reference kill of this raid size: fewer than three were available",
    )


def test_a_wipe_has_no_kill_time() -> None:
    assert analyse_kill_time(_encounter(kill=False), _sample(310, 240, 500)) == []


def test_no_reference_kill_is_no_kill_time() -> None:
    assert analyse_kill_time(_encounter(), MechanicsSample()) == []
```

Check `MechanicsMember`'s fields against `mechanics.py` before running (`row`, `abilities`).

In `tests/domain/analysis/test_encounter_service.py`, add one test that `analyse_encounter` on a
kill handed a three-member `MechanicsSample` returns a finding with id `compare.kill.time`,
using that file's own loaded-encounter helper.

- [ ] **Step 2: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_kill_time.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/wowperf/domain/comparison/kill_time.py`:

```python
# ABOUTME: A kill's duration against the reference kills' own durations, never a mean.
# ABOUTME: Median and observed range from three kills up; the slowest kill alone below that.

from statistics import median

from wowperf.domain.comparison.mechanics import MechanicsSample
from wowperf.domain.comparison.pace import clock_text
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE
from wowperf.domain.encounter import Encounter
from wowperf.domain.findings import Confidence, Finding

KILL_TIME_ID = "compare.kill.time"

KILL_TIME_DETAIL = (
    "Our kill's duration against the reference kills' own, read off the leaderboard rows the "
    "mechanics comparison draws: a median and an observed range, never an average, or the "
    "slowest kill alone when fewer than three were available. The kills are not adjusted for "
    "roster, item level or strategy. They are the execution leaderboard's, among the best "
    "kills of this boss, so a kill slower than theirs is the expected result rather than a "
    "fault; the damage pace beside this says where the time went."
)


def analyse_kill_time(encounter: Encounter, sample: MechanicsSample) -> list[Finding]:
    """`compare.kill.time` on a kill with any reference kill, or nothing.

    Below three kills the slowest stands alone, as the pace comparison's band
    does: it is the kinder reference, so "slower" against it can only
    understate. `seconds_lost` stays None: a raid kill is not a race against
    a timer, and the title carries both clocks.
    """
    if not encounter.kill or not sample.members:
        return []
    durations = sorted(member.row.duration_seconds for member in sample.members)
    ours = clock_text(encounter.duration_seconds)
    if len(durations) < MIN_SAMPLE_FOR_AGGREGATE:
        title = (
            f"The kill took {ours} against the slowest reference kill's "
            f"{clock_text(durations[-1])}"
        )
        evidence: tuple[str, ...] = (
            "Against the one reference kill of this raid size: fewer than three were available"
            if len(durations) == 1
            else f"Against the slowest of {len(durations)} reference kills: fewer than three "
            "were available",
        )
    else:
        title = f"The kill took {ours} against the kills' median of {clock_text(median(durations))}"
        evidence = (
            f"Against {len(durations)} reference kills",
            f"Their range: {clock_text(durations[0])} to {clock_text(durations[-1])}",
        )
    return [
        Finding(
            id=KILL_TIME_ID,
            title=title,
            detail=KILL_TIME_DETAIL,
            confidence=Confidence.MEASURED,
            evidence=evidence,
        )
    ]
```

Wire it in `analyse_encounter`, directly after `compare_lethal_abilities`:

```python
    findings += analyse_kill_time(encounter, mechanics)
```

Place it in `raid_ledger.RAID_PLACEMENTS`, directly after `("compare.pace.", "damage_rows")`:

```python
    ("compare.kill.", "damage_rows"),
```

Add a family severity for `compare.kill` if `wowperf.domain.analysis.severity`'s
`SEVERITY_BY_FAMILY` requires one (the raid e2e asserts no finding has `UNKNOWN_SEVERITY`); use
the same severity `compare.pace` has, and say so in the commit body.

- [ ] **Step 4: Run to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/kill_time.py src/wowperf/domain/analysis/encounter_service.py src/wowperf/domain/report/raid_ledger.py src/wowperf/domain/analysis/severity.py tests/domain
/mingw64/bin/git commit -m "State a kill's duration against the reference kills" -m "A kill had nothing measured against other kills on the night page; its time against the best kills is the first half of kill speed." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `raid` reads pace on a kill

**Files:**
- Modify: `src/wowperf/cli.py` (`raid`, the `if not encounter.kill:` block around the
  `load_pace_sample` call)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Tasks 4 to 6.

- [ ] **Step 1: Give the raid harness a kill whose boss can be found**

In `tests/test_cli.py`:

- Add constants `KILL_BOSS_GAME_ID = 951`, `KILL_BOSS_OUR_ACTOR_ID = 71`,
  `KILL_BOSS_REFERENCE_ACTOR_ID = 72`.
- `npc_actors_payload` in `build_raid_transport` gains
  `{"id": KILL_BOSS_OUR_ACTOR_ID, "gameID": KILL_BOSS_GAME_ID, "name": "The Twin Fangs", "subType": "Boss"}`.
- `_raid_fights_payload`: the kill fight gets
  `enemyNPCs=[{"id": KILL_BOSS_OUR_ACTOR_ID, "gameID": KILL_BOSS_GAME_ID}]`.
- `reference_fight_payload`'s `enemyNPCs` lists both
  `{"id": PACE_BOSS_REFERENCE_ACTOR_ID, "gameID": PACE_BOSS_GAME_ID}` and
  `{"id": KILL_BOSS_REFERENCE_ACTOR_ID, "gameID": KILL_BOSS_GAME_ID}`.

- [ ] **Step 2: Write the failing test**

```python
def test_a_kill_reads_its_damage_pace_and_its_time_against_the_kills(tmp_path: Path) -> None:
    result = run_raid(tmp_path)

    assert result.exit_code == 0, result.output
    payload = json.loads(
        (tmp_path / "out" / f"{RAID_REPORT_CODE}-{RAID_FIGHT_ID}.findings.json").read_text(
            encoding="utf-8"
        )
    )
    ids = [one["id"] for one in payload["findings"]]
    assert "compare.pace.boss" in ids
    assert "compare.kill.time" in ids
    assert "compare.pace.projection" not in ids
    assert "compare.pace.player" not in " ".join(ids)
```

Use the path helper the neighbouring raid tests use if there is one. `run_raid` defaults to
the kill (`RAID_FIGHT_ID`).

- [ ] **Step 3: Run to verify it fails**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_cli.py -k "kill_reads_its_damage_pace" -v`
Expected: FAIL: no `compare.pace.boss` on a kill.

- [ ] **Step 4: Implement**

In `raid`, drop the `if not encounter.kill:` guard so `load_pace_sample` runs for any fight read
with comparison, still over `tuple(member.row for member in mechanics_sample.members)`. Rewrite
the comment above it: both a kill and a wipe read pace against the mechanics sample's own
members, so the page's comparisons stand on one sample; per-player pace stays a wipe's
(`pace_player.py` gates it). Update the `raid` docstring if it says pace is a wipe's.

- [ ] **Step 5: Run the CLI suite**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_cli.py -q`
Expected: PASS. Kill tests that count requests or read the Damage tab or Provenance may move:
the kill now asks for `NpcActors`, `ReferenceFight` and `BossDamageGraph`. For each test whose
expectation changes, confirm the new value is the pace comparison's and name the test in the
report.

- [ ] **Step 6: Commit**

```bash
/mingw64/bin/git add src/wowperf/cli.py tests/test_cli.py
/mingw64/bin/git commit -m "Read a raid kill's damage pace against its reference kills" -m "raid --fight N on a kill now says where its damage fell behind the kills, as the night page will." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `night` draws the mechanics sample and pace for every pull

**Files:**
- Modify: `src/wowperf/cli.py` (`night`; remove `_pace_references` only if Step 4's refill
  ordering no longer needs it)
- Modify: `src/wowperf/domain/analysis/attempt_shape.py` (remove `no_sample_on_the_night`)
- Modify: `src/wowperf/domain/comparison/night_axis.py`
- Modify: `src/wowperf/domain/report/night_build.py`
- Modify: `.claude/skills/analyzing-a-run/SKILL.md` (the `night` section)
- Test: `tests/test_cli_night.py`, `tests/domain/comparison/test_night_axis.py`,
  `tests/domain/report/test_night_build.py`, `tests/domain/analysis/test_attempt_shape.py`,
  `tests/domain/analysis/test_encounter_service.py`

**Interfaces:**
- Consumes: `_mechanics_sample`, `_ability_taken` (existing, in `cli.py`), Tasks 4 to 6.
- Produces: `parse_axis_not_drawn(*, compared: bool = False)`, `COMPARED_TITLE`,
  `NOT_DRAWN_COMPARED_DETAIL` in `night_axis.py` (renamed from `pace_compared`, `PACE_TITLE`,
  `NOT_DRAWN_PACE_DETAIL`).

`NOT_DRAWN_COMPARED_DETAIL`:

```python
NOT_DRAWN_COMPARED_DETAIL = (
    "wowperf night does not draw the parse axis at all: this page never asks a parse "
    "leaderboard for a comparison, on a kill or on a wipe. What it compares against the "
    "execution leaderboard's kills is what hit and killed the raid, each attempt's damage "
    "pace, and each kill's time. Every family the parse axis carries is absent from this page "
    "as a result: damage against the board, damage by target, casts a minute, talents, buff "
    "uptime, and the percentile. wowperf raid --fight N is what draws them, for one kill."
)
```

- [ ] **Step 1: Teach the night harness the mechanics queries**

In `build_night_transport`, answer `AbilityTakenTable` before the fallback: our own report
(`variables["code"] == NIGHT_REPORT_CODE`) with 20 landings of `NIGHT_KILLING_BLOW` ("Venom
Bolt") from a `Boss` source, a reference with 5, so the mechanics comparison has a difference
to find:

```python
        if name == "AbilityTakenTable":
            hits = 20 if variables.get("code") == NIGHT_REPORT_CODE else 5
            return carrying_quota({"reportData": {"report": {"taken": {"data": {"entries": [
                {"guid": NIGHT_KILLING_BLOW, "name": "Venom Bolt", "hitCount": hits,
                 "sources": [{"type": "Boss"}]},
            ]}}}}})
```

Add `"AbilityTakenTable"` to `PACE_OPERATIONS` if that tuple is what the `--no-compare` test
checks is never requested (grep it).

- [ ] **Step 2: Write the failing tests**

In `tests/test_cli_night.py`:

```python
def test_a_kill_pull_is_compared_against_the_reference_kills(tmp_path: Path) -> None:
    fights = [_night_fight(FIRST_PULL, kill=True, fight_percentage=0.01)]
    calls: list[tuple[str, dict[str, Any]]] = []
    result = run_night(tmp_path, fights=fights, kill_rankings=PACE_KILL_RANKINGS, calls=calls)

    assert result.exit_code == 0, result.output
    [pull] = _pulls_by_fight(tmp_path).values()
    ids = _finding_ids(pull["findings"])
    assert {"compare.kill.time", "compare.pace.boss"} <= ids
    assert any(one.startswith("mechanics.ability.") for one in ids)
    assert "AbilityTakenTable" in _operations(calls)


def test_a_compared_wipe_reads_its_verdict_against_the_reference_kills(tmp_path: Path) -> None:
    """Nobody dies, the boss holds at 60% and we outlast the kills' 300 s median.

    That is the throughput shape, which `classify_attempt` can only reach
    with the reference kills' durations -- the mechanics sample the night
    now draws.
    """
    fights = [{**_night_fight(FIRST_PULL, end_ms=320_000), "bossPercentage": 60.0}]
    result = run_night(tmp_path, fights=fights, deaths_on=(), kill_rankings=PACE_KILL_RANKINGS)

    assert result.exit_code == 0, result.output
    [pull] = _pulls_by_fight(tmp_path).values()
    [verdict] = [one for one in pull["findings"] if one["id"].startswith("wipe.cause")]
    assert verdict["id"] == "wipe.cause"
```

Read `classify_attempt` before trusting the second test's fixture: if the throughput shape needs
another fact this fixture lacks, fix the fixture and say which.

**Deliberately changed** existing tests:

- `test_a_night_of_only_kills_fetches_no_reference_kill`: kills are now compared. Replace it
  with the first test above; its "`--no-compare` fetches nothing" twin stays as it is.
- `test_a_compared_night_says_on_each_wipe_what_raid_says_on_that_wipe`: its verdict half
  asserted `no_sample_on_the_night`. The verdict is now read against the reference kills, so
  assert instead that no pull's verdict notice says `NO_REFERENCE_SAMPLE` and that none says
  "draws no mechanics sample"; keep its parse-axis half (`WITHHELD_DETAIL` on the wipes).
- `test_a_night_read_with_no_compare_keeps_the_sentences_for_a_night_that_drew_nothing`:
  should stay green unchanged. If it does not, report why before editing it.
- In `tests/domain/analysis/test_attempt_shape.py` and `test_encounter_service.py`, the tests
  of `no_sample_on_the_night` go with the function (**deliberately removed**; `NO_SAMPLE` keeps
  its own tests).
- In `tests/domain/comparison/test_night_axis.py` and `tests/domain/report/test_night_build.py`,
  rename to the new names and assert the new sentence where the old one was asserted.

Add to `tests/domain/report/test_night_build.py` one test that a **kill** pull handed a pace
sample renders its Damage tab's parse line with `NOT_DRAWN_COMPARED_DETAIL`, not
`WITHHELD_DETAIL` (whose first words say the attempt did not kill the boss), using that file's
own builders.

- [ ] **Step 3: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_cli_night.py tests/domain/report/test_night_build.py -q`
Expected: the new tests FAIL.

- [ ] **Step 4: Implement the command**

In `night`, replace the pace-only loop with one that draws, per pull, what `raid` draws for one:

```python
        mechanics_by_fight: dict[int, MechanicsSample] = {}
        abilities_by_fight: dict[int, tuple[AbilityTakenRow, ...]] = {}
        pace_by_fight: dict[int, PaceSample] = {}
        records_by_fight: dict[int, tuple[ReferenceRecord, ...]] = {}
        if not no_compare:
            transient = DiskCache(
                cache_dir / REFERENCE_CACHE_SUBDIR, max_age_seconds=REFERENCE_CACHE_SECONDS
            )
            encounter_rankings = WclEncounterRankingRepository(repository.client, transient)
            for attempt in drawn:
                encounter = attempt.encounter
                try:
                    mechanics_sample, mechanics_records = _mechanics_sample(
                        encounter_rankings, repository.client, transient, encounter
                    )
                    abilities, _ = _ability_taken(
                        repository.client, repository.cache, encounter.report_code,
                        encounter.fight_id,
                    )
                    members = tuple(member.row for member in mechanics_sample.members)
                    pace_sample, pace_records = load_pace_sample(
                        repository.client, repository.cache, transient, encounter,
                        members + tuple(
                            row for row in _pace_references(encounter_rankings, encounter)
                            if row not in members
                        ),
                    )
                except RateLimitExceeded:
                    raise
                except (ValueError, WclError, httpx.HTTPError, OSError) as error:
                    mechanics_sample, mechanics_records, abilities = MechanicsSample(), (), ()
                    pace_sample, pace_records = (
                        PaceSample(unavailable=not_fetched(str(error))), ()
                    )
                mechanics_by_fight[encounter.fight_id] = mechanics_sample
                abilities_by_fight[encounter.fight_id] = abilities
                pace_by_fight[encounter.fight_id] = pace_sample
                records_by_fight[encounter.fight_id] = mechanics_records + pace_records
```

The pace references are the mechanics sample's members first, then the rest of the board: with
no failure that is `raid`'s own sample, and a member whose pace graph fails is still refilled
from the rows behind it, which `test_a_reference_kill_that_fails_is_replaced_by_the_next_on_the_board`
pins. `_pace_references` stays for that reason; update its docstring to say so.

Hand both to `analyse_encounter`, and drop the night-only verdict notice:

```python
            attempt.encounter.fight_id: analyse_encounter(
                attempt,
                defensives,
                consumables,
                roles=roles,
                mechanics=mechanics_by_fight.get(attempt.encounter.fight_id, MechanicsSample()),
                our_abilities=abilities_by_fight.get(attempt.encounter.fight_id, ()),
                pace=pace_by_fight.get(attempt.encounter.fight_id),
                answers=answers_for(attempt.encounter.players, throughput, externals, roles),
            )
```

Rewrite the comments around both blocks and the `night` docstring to say what it now draws: the
mechanics sample and pace for every pull, kills included, against one reference sample per
boss shared through the one-day cache; still no parse axis. Update `--no-compare`'s help to
`"Fetch no reference kill: no pull is compared against the kills"`.

Delete `no_sample_on_the_night` from `attempt_shape.py` and its import in `cli.py`; update
`NO_SAMPLE`'s docstring (the night no longer passes its own).

- [ ] **Step 5: Implement the wording**

- `night_axis.py`: rename as in Interfaces; `NOT_DRAWN_COMPARED_DETAIL` as above; rewrite its
  docstring.
- `night_build.py`: `parse_axis_not_drawn(compared=bool(pace_by_fight))`; and the parse line
  per pull:

```python
                        parse_withheld=(
                            None if pace_sample is None
                            else NOT_DRAWN_COMPARED_DETAIL if attempt.encounter.kill
                            else WITHHELD_DETAIL
                        ),
```

  with the docstring above `build_night_report` saying why a kill gets the night's sentence.

- [ ] **Step 6: Update the `analyzing-a-run` skill**

In `.claude/skills/analyzing-a-run/SKILL.md`, rewrite the `night` section's paragraphs on what
it draws: the mechanics axis and damage pace for every pull, kills included, and kill time on
kills; `wipe.cause` read against the reference kills; still no parse axis, and why. Remove every
sentence that says the night draws no mechanics axis, that a kill draws no pace, or that the
verdict notice says the night draws no mechanics sample. Keep flag names exactly as `--help`
prints them (`tests/test_skills.py` checks them).

- [ ] **Step 7: Run everything**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS. Name every existing test whose expectation moved, and why.

- [ ] **Step 8: Commit**

```bash
/mingw64/bin/git add -A src tests .claude/skills/analyzing-a-run/SKILL.md
/mingw64/bin/git commit -m "Compare every night pull against its boss's reference kills" -m "The night design kept the mechanics axis and the shipped command dropped it, so no wipe had a verdict and no kill had any comparison. Each pull now draws what raid --fight N draws for it, except the parse axis." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Live verification, end-to-end tests and the cost

Run by the controller, not a subagent: it spends quota and reads real players' logs.

**Files:**
- Modify: `tests/e2e/test_raid_e2e.py`, `tests/e2e/test_night_e2e.py`
- Modify: `.claude/skills/wcl-api/SKILL.md`

- [ ] **Step 1: Write the end-to-end tests**

Against `cW38jmwdnZfbHVL4`, with the canonical fights from `.env.example` (fight 2 the kill,
fight 30 the wipe), following the existing e2e pattern (`CliRunner`, fresh `--cache-dir`,
assertions reduced to bools with messages naming a shape, never a title):

- `raid` on the canonical kill: `compare.kill.time` appears once, badged `measured`;
  `compare.pace.boss` appears once, badged `derived`, and no `compare.pace.projection`. Fight 2
  is the boss whose fight lists boss-flagged adds, so this is the name tie-break on live data.
- `raid` on an Entombed Sentinels wipe in the same report (fight 8 in the 2026-10-01 cache
  probe; confirm the fight id from the report before hard-coding it): `compare.pace.boss`
  appears, not `compare.pace.unavailable`. This is the council on live data.
- `night` on the report: every pull carries either `compare.pace.boss` or
  `compare.pace.unavailable` with a detail other than `NO_BOSS`, and no pull's verdict notice
  says the night draws no mechanics sample.

- [ ] **Step 2: Run them**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -m e2e tests/e2e/test_raid_e2e.py tests/e2e/test_night_e2e.py -q`
Expected: PASS. Record each command's "Rate limit: ... points spent" line.

- [ ] **Step 3: The live distribution on `6jHcTvtB4XAMGZag`**

Run `uv run wowperf night 6jHcTvtB4XAMGZag` with a fresh `--cache-dir` so the cost is cold, and
report from the findings file, per boss:

- how the boss lookup ended (single, council, none);
- each `wipe.cause` verdict's count, the withheld ones by reason;
- pace behind / on pace / ahead / withheld (by reason), wipes and kills separately;
- each kill's `compare.kill.time` title and whether it used the median or the fallback;
- how many pulls carry `mechanics.ability.*` and `mechanics.lethal.*`.

A state the design names that occurs zero times is investigated before this plan is called
done, not accepted.

- [ ] **Step 4: Record the cost**

Add a dated row to `.claude/skills/wcl-api/SKILL.md` with the cold night's total, its per
operation breakdown, and the delta against 575.80 (2026-10-01, before this plan). Say whether
`Fights` cost more with `enemyNPCs` than before.

- [ ] **Step 5: Commit**

```bash
/mingw64/bin/git add tests/e2e .claude/skills/wcl-api/SKILL.md
/mingw64/bin/git commit -m "Pin the night's comparison coverage against live logs, and its cost" -m "The council, the boss-framed adds and the kill comparison each depend on shapes only a real report has." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
