# Phase I: The Death Recap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn each death card into a recap — the last ten seconds as one timeline with a reconstructed health column, every saving tool the group had for the player with its state at death, and how the player came back — without a new finding, a new layer, or an invented field name.

**Architecture:** The Warcraft Logs adapter fetches three more things (casts with resources, and per death one scoped `Healing` stream and one scoped `All` stream) and translates them into three new frozen event records on `LoadedRun`. One pure module, `src/wowperf/domain/analysis/recap.py`, computes the timeline with health, the four-state availability of every ability, and the return. The report builder formats those into typed rows on `DeathCard`; the template loops over them and decides nothing. Two hand-maintained data files join `data/`: externals per specialisation, and (unless the spike proves it unnecessary) the self-resurrection spells.

**Tech Stack:** Python 3.12+, `uv`, `pydantic` v2, `jinja2`, `pytest`, `ruff`, `mypy`. No JavaScript changes.

**Spec:** `docs/plans/2026-09-07-death-recap-design.md`. Read it in full before any task; §2 before Tasks 1, 3 and 4; §3 before Tasks 2 and 5; §4 before Tasks 6 to 8; §5 and §6 before Task 9; §8 before Task 10.

**Depends on:** `master` at `0fdb381` (Phase H merged, this design committed). Read `src/wowperf/adapters/wcl/ingest.py`, `src/wowperf/adapters/wcl/repository.py`, `src/wowperf/domain/analysis/defensives.py`, `src/wowperf/domain/report/build.py` (`build_deaths`), `src/wowperf/domain/report/model.py` and `.claude/skills/wcl-api/SKILL.md` §"The event stream, probed for a death recap" before starting any task.

## Global Constraints

- **Python `>=3.12`.** `uv` is the only toolchain: no pip, no poetry, no hand-managed virtualenv.
- **`uv` is not on PATH.** Every bash command using it begins `export PATH="$HOME/.local/bin:$PATH"; `.
- **`src/wowperf/domain/` performs no I/O.** No `httpx`, no file reads, no `tomllib`, no clock, no `jinja2`. Adapters do that. `recap.py` takes data in and gives values out.
- **Never invent a Warcraft Logs field name.** Every field this plan reads is named in `.claude/skills/wcl-api/SKILL.md` with a date: `includeResources`, `hitPoints`, `maxHitPoints`, `amount`, `absorbed`, `unmitigatedAmount`, `extraAbilityGameID`, `sourceID`, `targetID`, `abilityGameID`, `timestamp`, `type`, the `dataType` values `Healing` and `All`, and the event types `heal`, `absorbed`, `resurrect`, `cast`, `damage`. Task 1 re-verifies the two the recap leans on hardest and records the cost; no later task uses anything else.
- **Every id in a data file is verified** the way `data/defensives.toml` was: read from the game's own spell data, one spell at a time, the returned name matching the ability intended, on the date the file's `verified` field carries. No id is written from memory.
- **The template decides nothing.** `kind` and `state` on the recap rows are closed vocabularies the template maps to CSS classes and to nothing else. Every string on a card is formatted in `build.py`.
- **Every badge is present.** A health column is `derived`; an availability group is `inferred`; a return is `measured` or `derived` as spec §4.4 says. A card with a claim and no badge is a bug.
- **A remaining cooldown is an upper bound**, worded "at most N s left", never a value.
- **No total row.** A numeric field added to a view model type is either a string or on `NUMBERS_THAT_ARE_NOT_TOTALS` in `tests/adapters/render/test_html_invariants.py` with its reason. This plan adds exactly one: `RecapRow.health_percent`.
- **No corpus.** The scoped queries are cached like every other response and nothing about another player's log is kept beyond that cache.
- **The LLM never computes a number.** Every metric comes from tested Python.
- **English** in code, comments, error strings, and commit messages.
- Commit style: imperative mood, no `feat:` / `fix:` prefix. The subject says what the commit does to the repository; the body explains **why**. End with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Never `--no-verify`, `--no-hooks`, or `--no-pre-commit-hook`.**
- Every file starts with two `# ABOUTME: ` comment lines (`{# ABOUTME: #}` in the template, `# ABOUTME:` in TOML). Empty `__init__.py` markers are exempt.
- The gate is `uv run pytest`, `uv run ruff check .`, `uv run mypy` (no path argument). Ruff's line length is 100.
- **Comments are evergreen.** No "new", "now", "recently", "fixed", no dates in code comments. Dated notes belong in the design documents and the skills.
- **Never remove a code comment** unless it is now false. Update it instead.
- **Every existing test that a task breaks is updated by that task**, with the reason in the commit body. No test is deleted; a test that pins behaviour this plan deliberately changes is rewritten to pin the amended behaviour. The tests named in each task are the ones known to break; if another breaks, fix it in the same task and say so.
- **The golden file** `tests/adapters/render/golden/minimal.html` is regenerated with `uv run pytest tests/adapters/render/test_html_invariants.py --golden-update` and its diff **read in full** before the commit that carries it. Only Task 9 regenerates it.
- **Git in a worktree.** The session's tool hook refuses a bare `git` inside a worktree, and refuses any command that names git twice. Call the executable by its path, `/cmd/git.exe`, and issue one git invocation per command. Stage files **by name**, never `git add -A`. Never `git stash`: the stash stack is shared with the main checkout.
- **For the controller:** never stage or commit anything while an implementer subagent is running; its `git add` would sweep your files into its commit.
- **Credentials.** `.env` at the repo root is UTF-16. Tasks 1 and 12 need it; never print, log or commit its values. Every other task runs offline.

## The real run is the acceptance test

Report `6Kx1P9GbNXrcLdHa` fight 36 (Den of Nalorakk +16, four deaths, two of them one player's, one Raise Ally) is the run the probe was measured on. Task 1 measures the new queries against it and Task 11 renders it. A cold fetch cost about thirty-five of the hourly 3600 points before this plan; Task 1 records what the recap adds.

---

### Task 1: The spike — measure the new queries and settle the self-resurrection mechanism (orchestrator, needs credentials)

**Files:**
- Modify: `.claude/skills/wcl-api/SKILL.md` (§"Fields" table; §"The event stream, probed for a death recap")
- Create (scratchpad, never the repo): `spike_recap.py`

**Interfaces:**
- Consumes: `WclClient.execute(query, variables)` and `WclClient.rate_limit()` from `src/wowperf/adapters/wcl/client.py`; `DiskCache` from `src/wowperf/adapters/cache/disk.py`.
- Produces: dated rows in the skill that Tasks 3, 4 and 8 cite. Task 8's mechanism depends on this task's answer to question 4.

Four questions, each answered by one query against the real run, each answer written into the skill with today's date. Write the script in the session's scratchpad directory, loading the two `WCL_*` variables from the UTF-16 `.env` the way `spike_death_anchor.py` did (`Path(".env").read_text(encoding="utf-16")`, `os.environ.setdefault`), and never printing them.

- [ ] **Step 1: Cost of casts with resources.** Read `rateLimitData` before and after fetching the full-fight `Casts` stream (`hostilityType: Friendlies`, `fightIDs: [36]`, the fight's `startTime`/`endTime`, `limit: 10000`, paginated on `nextPageTimestamp`) **with** `includeResources: true`, into a fresh cache directory. Record the points spent and the page count. Count how many `cast` events carry both `hitPoints` and `maxHitPoints`, and how many carry neither.

- [ ] **Step 2: The scoped healing window.** For the first death in the fight (from the cached `Deaths` stream: `type == "death"`, `targetID`, `timestamp`), fetch `events(dataType: Healing, fightIDs: [36], targetID: <actor>, startTime: <death − 10000>, endTime: <death>, limit: 10000)`. Record the points spent, the row count, and the `type` values seen. For one `absorbed` row, resolve both `abilityGameID` and `extraAbilityGameID` through the cached abilities master data and record **which one names the absorbing shield and which names the hit**. Spec §2 and the ingest in Task 3 assume `extraAbilityGameID` is the shield; if the run says otherwise, the skill row and Task 3's `build_healing` follow the run.

- [ ] **Step 3: The scoped return window.** For the death that was followed by a Raise Ally (the probe saw one), fetch `events(dataType: All, fightIDs: [36], targetID: <actor>, startTime: <death>, endTime: <death + 60000>, limit: 10000)`. Record the points spent, the row count, and the `resurrect` row's `sourceID`, `targetID`, `abilityGameID`, `timestamp`.

- [ ] **Step 4: Does a self-resurrection emit a `resurrect` event?** Search the same `All` stream, unscoped by actor, over the whole fight for every `type == "resurrect"` row and print `sourceID == targetID` for each. If the run holds no self-resurrection (likely: the probe saw Reincarnation as a cast in a different fight only if at all), record **"not observed on this run"**. Then the rule for Task 8 is: **a self-resurrection is recognised from the cast of a listed spell**, and `data/resurrections.toml` is built. Only a row that shows a `resurrect` event with `sourceID == targetID` lets Task 8 skip that file.

- [ ] **Step 5: Write the skill.** Under §"The event stream, probed for a death recap", add a dated paragraph "Measured <date> for the recap:" with the four answers — points per query, page and row counts, which field names the shield, the resurrect row's shape, and the self-resurrection answer. In the §"Fields" table add these rows (the test in `tests/test_skills.py` checks each "yes" row's field name appears in `queries.py`, so they become true when Task 4 lands; add them with "no" today and Task 4 flips them):

```markdown
| `includeResources` | `events` argument | <date> | no |
| `targetID` | `events` argument | <date> | no |
```

- [ ] **Step 6: Gate and commit.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_skills.py -q
```

Expected: pass (the two rows say "no", and neither string is in `queries.py` yet — confirm `includeResources` is absent from `queries.py` before committing; `targetID` already appears there as a `table` argument, so that row must say **yes**, not no. Correct the row rather than the test).

```bash
/cmd/git.exe add .claude/skills/wcl-api/SKILL.md
```

Commit subject: `Record what the recap's queries cost and how a self-resurrection is logged`. Body: the four numbers and the mechanism decision, so Task 8's branch is traceable to a measurement.

---

### Task 2: Three event records and two damage fields

**Files:**
- Modify: `src/wowperf/domain/events.py` (after `DamageTakenEvent`)
- Modify: `src/wowperf/domain/model.py:117-126` (`LoadedRun`)
- Test: `tests/domain/test_events.py`, `tests/domain/test_model.py`

**Interfaces:**
- Consumes: `Frozen` from `wowperf.domain.base`.
- Produces: `HealthSample(actor_id, timestamp_ms, hit_points, max_hit_points)`, `HealingEvent(actor_id, source_id, ability_id, ability_name, amount, timestamp_ms, absorbed: bool = False)`, `Resurrection(actor_id, caster_id, ability_id, ability_name, timestamp_ms)`; `DamageTakenEvent.health_damage: int = 0` and `.absorbed: int = 0`; `LoadedRun.health_samples`, `.healing`, `.resurrections`, each `tuple[...] = ()`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/domain/test_events.py`:

```python
def test_a_hit_keeps_what_reached_health_apart_from_what_a_shield_soaked() -> None:
    hit = DamageTakenEvent(
        actor_id=1, ability_id=5, ability_name="Molten Scar", amount=132_788,
        timestamp_ms=2500, health_damage=0, absorbed=123_570,
    )
    assert (hit.amount, hit.health_damage, hit.absorbed) == (132_788, 0, 123_570)


def test_a_hit_built_without_the_split_reads_as_nothing_absorbed() -> None:
    # Existing fixtures build hits with the unmitigated figure alone; they must
    # still construct, and a missing split must not invent an absorb.
    hit = DamageTakenEvent(actor_id=1, ability_id=5, ability_name="x", amount=9, timestamp_ms=1)
    assert (hit.health_damage, hit.absorbed) == (0, 0)


def test_a_health_sample_is_a_reading_of_the_players_own_health() -> None:
    sample = HealthSample(actor_id=1, timestamp_ms=1000, hit_points=61_200, max_hit_points=99_000)
    assert sample.hit_points < sample.max_hit_points


def test_a_healing_event_is_a_heal_unless_it_says_it_was_an_absorb() -> None:
    heal = HealingEvent(
        actor_id=1, source_id=2, ability_id=7, ability_name="Rejuvenation", amount=9_100,
        timestamp_ms=1000,
    )
    absorb = heal.model_copy(update={"absorbed": True, "ability_name": "Power Word: Shield"})
    assert (heal.absorbed, absorb.absorbed) == (False, True)


def test_a_resurrection_names_who_brought_the_player_back() -> None:
    back = Resurrection(
        actor_id=1, caster_id=3, ability_id=61999, ability_name="Raise Ally", timestamp_ms=5000
    )
    assert back.caster_id != back.actor_id
```

Add `DamageTakenEvent, HealingEvent, HealthSample, Resurrection` to that file's import from `wowperf.domain.events`. Append to `tests/domain/test_model.py`:

```python
def test_a_loaded_run_defaults_every_recap_stream_to_empty() -> None:
    loaded = LoadedRun(run=a_run())
    assert (loaded.health_samples, loaded.healing, loaded.resurrections) == ((), (), ())
```

(Use that file's existing `Run` fixture; if it has none named `a_run`, import `a_run` from `tests.domain.report.test_build_frame`.)

- [ ] **Step 2: Run them to see them fail.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/test_events.py tests/domain/test_model.py -q
```

Expected: ImportError on `HealthSample` / `HealingEvent` / `Resurrection`, and a `ValidationError` on `health_damage`.

- [ ] **Step 3: Implement.** In `src/wowperf/domain/events.py`, replace the `DamageTakenEvent` docstring and body with:

```python
class DamageTakenEvent(Frozen):
    """One hit on a player. `amount` is the unmitigated figure.

    A Warcraft Logs damage event's `amount` excludes what was absorbed, so a
    fully absorbed hit reads zero. `unmitigatedAmount` is the honest answer to
    "how hard did this hit", which is what the per-ability comparison asks.

    `health_damage` is that `amount`: what reached the player's health after
    mitigation and absorption, which is what a health curve subtracts.
    `absorbed` is what a shield soaked. A fully absorbed hit therefore reads as
    unmitigated damage above zero, health damage zero, and absorbed equal to
    the shield's share — three facts, not one.
    """

    actor_id: int
    ability_id: int
    ability_name: str
    amount: int
    timestamp_ms: int
    pull_index: int | None = None
    health_damage: int = 0
    absorbed: int = 0


class HealthSample(Frozen):
    """The player's own health, read off an event they were the source of.

    Only events a player causes carry their hit points; the hits they take do
    not. A health curve is therefore a sequence of these, sparse wherever the
    player was idle, and the recap reconstructs the gaps.
    """

    actor_id: int
    timestamp_ms: int
    hit_points: int
    max_hit_points: int


class HealingEvent(Frozen):
    """One heal landing on a player, or one hit a shield on them soaked.

    `absorbed` tells the two apart. A heal restores `amount` health. An absorb
    prevented `amount` damage without touching health, and `ability_name` then
    names the shield that soaked it rather than a heal.
    """

    actor_id: int
    source_id: int
    ability_id: int
    ability_name: str
    amount: int
    timestamp_ms: int
    absorbed: bool = False


class Resurrection(Frozen):
    """A dead player brought back by a spell.

    `caster_id` equal to `actor_id` is a self-resurrection. A player who
    released and ran back has no record here at all: the log emits nothing.
    """

    actor_id: int
    caster_id: int
    ability_id: int
    ability_name: str
    timestamp_ms: int
```

In `src/wowperf/domain/model.py`, import the three from `wowperf.domain.events` and extend `LoadedRun`:

```python
    damage_taken: tuple[DamageTakenEvent, ...] = ()
    # The three streams the death recap reads. Health samples come off the
    # player's own casts; healing and resurrections are fetched per death.
    health_samples: tuple[HealthSample, ...] = ()
    healing: tuple[HealingEvent, ...] = ()
    resurrections: tuple[Resurrection, ...] = ()
```

- [ ] **Step 4: Run the gate.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
/cmd/git.exe add src/wowperf/domain/events.py src/wowperf/domain/model.py tests/domain/test_events.py tests/domain/test_model.py
```

Subject: `Add the health, healing and resurrection records the death recap reads`. Body: why `amount` keeps its unmitigated meaning and the split is two new fields (every existing reader and the per-ability comparison depend on it), and why the three tuples default to empty.

---

### Task 3: Translate the new payloads in the ingest

**Files:**
- Modify: `src/wowperf/adapters/wcl/ingest.py` (`build_damage_taken`; add `build_health_samples`, `build_healing`, `build_resurrections`)
- Test: `tests/adapters/wcl/test_ingest_streams.py`

**Interfaces:**
- Consumes: Task 2's records; `_ability_name`, `pull_index_at` already in the module.
- Produces: `build_health_samples(events) -> tuple[HealthSample, ...]`, `build_healing(events, ability_names) -> tuple[HealingEvent, ...]`, `build_resurrections(events, ability_names) -> tuple[Resurrection, ...]`; `build_damage_taken` fills `health_damage` and `absorbed`.

Before writing `build_healing`, read the skill row Task 1 wrote about which field names the shield. The code below follows spec §2 (`extraAbilityGameID` is the shield); swap the two lookups if Task 1 recorded the opposite, and say so in the commit body.

- [ ] **Step 1: Write the failing tests.** Append to `tests/adapters/wcl/test_ingest_streams.py` (add `build_health_samples, build_healing, build_resurrections` to its import from `wowperf.adapters.wcl.ingest`, and `"Power Word: Shield"` under a new id in its `ABILITY_NAMES` if the dict is local to the file — otherwise pass a local dict as below):

```python
RECAP_NAMES = {1238440: "Molten Scar", 17: "Power Word: Shield", 774: "Rejuvenation",
               61999: "Raise Ally"}


def test_damage_taken_keeps_the_health_damage_and_the_absorbed_share() -> None:
    events: list[dict[str, Any]] = [
        {"type": "damage", "abilityGameID": 1238440, "targetID": 693, "amount": 9_218,
         "absorbed": 123_570, "unmitigatedAmount": 132_788, "timestamp": 2500},
    ]
    hit = build_damage_taken(events, a_run(), RECAP_NAMES)[0]
    assert (hit.amount, hit.health_damage, hit.absorbed) == (132_788, 9_218, 123_570)


def test_a_cast_carrying_hit_points_becomes_a_health_sample() -> None:
    events: list[dict[str, Any]] = [
        {"type": "cast", "sourceID": 693, "abilityGameID": 100, "timestamp": 2000,
         "hitPoints": 61_200, "maxHitPoints": 99_000},
        {"type": "cast", "sourceID": 693, "abilityGameID": 100, "timestamp": 2600},
        {"type": "begincast", "sourceID": 693, "abilityGameID": 100, "timestamp": 2900,
         "hitPoints": 50_000, "maxHitPoints": 99_000},
    ]
    samples = build_health_samples(events)
    # The bare cast carries no reading and must not become a zero; a begincast
    # is not a cast and is not a sample either.
    assert [(s.timestamp_ms, s.hit_points, s.max_hit_points) for s in samples] == [
        (2000, 61_200, 99_000)
    ]


def test_a_heal_and_an_absorb_become_healing_events_and_a_removebuff_does_not() -> None:
    events: list[dict[str, Any]] = [
        {"type": "heal", "abilityGameID": 774, "sourceID": 5, "targetID": 693, "amount": 9_100,
         "timestamp": 3000},
        {"type": "absorbed", "abilityGameID": 1238440, "extraAbilityGameID": 17, "sourceID": 5,
         "attackerID": 699, "targetID": 693, "amount": 12_000, "timestamp": 3100},
        {"type": "removebuff", "abilityGameID": 17, "sourceID": 5, "targetID": 693,
         "timestamp": 3200},
    ]
    healing = build_healing(events, RECAP_NAMES)
    assert [(h.ability_name, h.amount, h.absorbed, h.source_id) for h in healing] == [
        ("Rejuvenation", 9_100, False, 5),
        ("Power Word: Shield", 12_000, True, 5),
    ]
    assert all(h.actor_id == 693 for h in healing)


def test_a_resurrect_event_names_the_caster_and_the_spell() -> None:
    events: list[dict[str, Any]] = [
        {"type": "resurrect", "abilityGameID": 61999, "sourceID": 7, "targetID": 693,
         "timestamp": 9000},
        {"type": "applydebuff", "abilityGameID": 1, "sourceID": 7, "targetID": 693,
         "timestamp": 9000},
    ]
    back = build_resurrections(events, RECAP_NAMES)
    assert [(r.actor_id, r.caster_id, r.ability_name, r.timestamp_ms) for r in back] == [
        (693, 7, "Raise Ally", 9000)
    ]
```

- [ ] **Step 2: Run them to see them fail.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl/test_ingest_streams.py -q
```

Expected: ImportError on the three builders.

- [ ] **Step 3: Implement.** In `ingest.py`, import `HealingEvent, HealthSample, Resurrection` from `wowperf.domain.events`. In `build_damage_taken`, keep the docstring and add the two fields:

```python
        taken.append(
            DamageTakenEvent(
                actor_id=event["targetID"],
                ability_id=ability_id,
                ability_name=_ability_name(ability_names, ability_id),
                amount=int(amount),
                timestamp_ms=event["timestamp"],
                pull_index=pull_index_at(run, event["timestamp"]),
                health_damage=int(event.get("amount") or 0),
                absorbed=int(event.get("absorbed") or 0),
            )
        )
```

Then add, after `build_damage_taken`:

```python
def build_health_samples(events: list[dict[str, Any]]) -> tuple[HealthSample, ...]:
    """One reading per cast that carried the caster's hit points.

    `includeResources` attaches `hitPoints` and `maxHitPoints` to an event for
    its source actor. A cast carrying neither produces no sample rather than a
    zero — a zero would read as a dead player — and a `begincast` is not a cast.
    """
    samples = []
    for event in events:
        if event.get("type") != "cast" or "sourceID" not in event:
            continue
        hit_points = event.get("hitPoints")
        max_hit_points = event.get("maxHitPoints")
        if hit_points is None or max_hit_points is None or int(max_hit_points) <= 0:
            continue
        samples.append(
            HealthSample(
                actor_id=event["sourceID"],
                timestamp_ms=event["timestamp"],
                hit_points=int(hit_points),
                max_hit_points=int(max_hit_points),
            )
        )
    return tuple(samples)


def build_healing(
    events: list[dict[str, Any]], ability_names: dict[int, str]
) -> tuple[HealingEvent, ...]:
    """Heals landing on a player and hits their shields soaked, from a `Healing` stream.

    A `heal` names the healing spell in `abilityGameID`. An `absorbed` event
    names the hit in `abilityGameID` and the shield that soaked it in
    `extraAbilityGameID`; the shield is what a recap wants to show, so that is
    the ability the event keeps. The stream's `removebuff` rows are not healing.
    """
    healing = []
    for event in events:
        kind = event.get("type")
        if kind == "heal":
            ability_id = int(event["abilityGameID"])
        elif kind == "absorbed":
            ability_id = int(event.get("extraAbilityGameID") or event["abilityGameID"])
        else:
            continue
        healing.append(
            HealingEvent(
                actor_id=event["targetID"],
                source_id=int(event.get("sourceID") if event.get("sourceID") is not None else -1),
                ability_id=ability_id,
                ability_name=_ability_name(ability_names, ability_id),
                amount=int(event.get("amount") or 0),
                timestamp_ms=event["timestamp"],
                absorbed=kind == "absorbed",
            )
        )
    return tuple(healing)


def build_resurrections(
    events: list[dict[str, Any]], ability_names: dict[int, str]
) -> tuple[Resurrection, ...]:
    """Every `resurrect` row of a stream: who was brought back, by whom, with what."""
    return tuple(
        Resurrection(
            actor_id=event["targetID"],
            caster_id=event["sourceID"],
            ability_id=event["abilityGameID"],
            ability_name=_ability_name(ability_names, event["abilityGameID"]),
            timestamp_ms=event["timestamp"],
        )
        for event in events
        if event.get("type") == "resurrect"
    )
```

- [ ] **Step 4: Run the gate.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
/cmd/git.exe add src/wowperf/adapters/wcl/ingest.py tests/adapters/wcl/test_ingest_streams.py
```

Subject: `Translate health readings, healing and resurrections out of the event payloads`. Body: why a cast without hit points yields no sample, why an absorb keeps the shield's name, and which skill row settled the field.

---

### Task 4: Ask for resources on casts, and fetch the two scoped windows per death

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py` (`CASTS_QUERY`; add `HEALING_QUERY`, `RETURN_QUERY`)
- Modify: `src/wowperf/adapters/wcl/repository.py` (`load`)
- Modify: `.claude/skills/wcl-api/SKILL.md` (flip the `includeResources` row Task 1 added to "yes"; add two stream rows)
- Test: `tests/adapters/wcl/test_repository.py`

**Interfaces:**
- Consumes: Task 3's builders; `fetch_all_events`; `RUN_UP_SECONDS` from `wowperf.domain.analysis.defensives`; `Death.seconds_until_next_action`.
- Produces: `LoadedRun.health_samples`, `.healing`, `.resurrections` filled by `WclRunRepository.load`. Two GraphQL operations named `Healing` and `ReturnWindow`, each taking `$code, $fightId, $actorId, $startTime, $endTime`.

- [ ] **Step 1: Write the failing tests.** In `tests/adapters/wcl/test_repository.py`, extend `recording_repository`'s `event_payloads` with two entries (the fixture death is actor 693 at 5000 ms with no later cast aimed at anyone, so its return window runs to the fight's end, 1920000):

```python
        "Healing": events_payload(
            [{"type": "heal", "abilityGameID": 774, "sourceID": 5, "targetID": 693,
              "amount": 9100, "timestamp": 4500}]
        ),
        "ReturnWindow": events_payload(
            [{"type": "resurrect", "abilityGameID": 61999, "sourceID": 7, "targetID": 693,
              "timestamp": 9000}]
        ),
```

Give the `Casts` payload's one cast a reading by adding `"hitPoints": 61200, "maxHitPoints": 99000` to it. Then add:

```python
def test_load_fetches_one_healing_and_one_return_window_per_death(tmp_path: Path) -> None:
    calls: list[str] = []
    repository = recording_repository(calls, tmp_path)
    loaded = repository.load("abc123", None)
    assert calls.count("Healing") == 1
    assert calls.count("ReturnWindow") == 1
    assert [(h.ability_id, h.amount) for h in loaded.healing] == [(774, 9100)]
    assert [(r.caster_id, r.actor_id) for r in loaded.resurrections] == [(7, 693)]


def test_load_reads_health_samples_off_the_casts(tmp_path: Path) -> None:
    loaded = recording_repository([], tmp_path).load("abc123", None)
    assert [(s.hit_points, s.max_hit_points) for s in loaded.health_samples] == [(61200, 99000)]


def test_the_scoped_windows_are_bounded_by_the_death(tmp_path: Path) -> None:
    """The healing window ends at the death; the return window starts there."""
    from wowperf.adapters.wcl.queries import HEALING_QUERY, RETURN_QUERY

    repository = recording_repository([], tmp_path)
    repository.load("abc123", None)
    healing_key = cache_key(
        HEALING_QUERY,
        {"code": "abc123", "fightId": 36, "actorId": 693,
         "startTime": 5000.0 - 10_000, "endTime": 5000.0},
    )
    return_key = cache_key(
        RETURN_QUERY,
        {"code": "abc123", "fightId": 36, "actorId": 693,
         "startTime": 5000.0, "endTime": 1920000.0},
    )
    miss = "the repository did not cache this window"
    assert repository.cache.get_or_fetch(healing_key, lambda: miss) != miss
    assert repository.cache.get_or_fetch(return_key, lambda: miss) != miss


def test_the_casts_query_asks_for_the_casters_resources() -> None:
    from wowperf.adapters.wcl.queries import CASTS_QUERY

    assert "includeResources: true" in CASTS_QUERY
```

Read `src/wowperf/adapters/cache/disk.py` first: if `DiskCache` exposes a plain read, use it instead of the `get_or_fetch` sentinel, and if `get_or_fetch` validates its fetcher's return type, return a dict sentinel such as `{"miss": True}` and compare on that.

- [ ] **Step 2: Run them to see them fail.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl/test_repository.py -q
```

Expected: `KeyError: 'Healing'` from the recording handler, and the import of `HEALING_QUERY` failing.

- [ ] **Step 3: The queries.** In `queries.py`, add `includeResources: true` to `CASTS_QUERY`'s `events(...)` arguments, with this comment above the constant:

```python
# `includeResources` attaches the caster's own hitPoints and maxHitPoints to each
# cast, the only health reading the log offers for a player; the hits they take
# carry none for the target. See the wcl-api skill, "The event stream, probed
# for a death recap".
CASTS_QUERY = """
query Casts($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Casts
        hostilityType: Friendlies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        includeResources: true
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""
```

Add after `DAMAGE_TAKEN_QUERY`:

```python
# Both scoped queries below are issued once per death, bounded to one actor and
# a few seconds, so each returns a handful of rows. Scoping by `targetID` is what
# keeps a ten-death run from paying for ten full streams.
HEALING_QUERY = """
query Healing(
  $code: String!, $fightId: Int!, $actorId: Int!, $startTime: Float!, $endTime: Float!
) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Healing
        fightIDs: [$fightId]
        targetID: $actorId
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

# The All stream is the only one carrying `resurrect` events: there is no
# Resurrects data type. Scoped to the dead player as target and to the window
# between the death and their first action, it holds at most one resurrection.
RETURN_QUERY = """
query ReturnWindow(
  $code: String!, $fightId: Int!, $actorId: Int!, $startTime: Float!, $endTime: Float!
) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: All
        fightIDs: [$fightId]
        targetID: $actorId
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""
```

- [ ] **Step 4: The repository.** In `repository.py`, import `HEALING_QUERY, RETURN_QUERY` from queries, `build_healing, build_health_samples, build_resurrections` from ingest, `RUN_UP_SECONDS` from `wowperf.domain.analysis.defensives`, and `HealingEvent, Resurrection` from `wowperf.domain.events`. In `load`, after `damage_taken = build_damage_taken(...)`:

```python
        # Per death, two small windows scoped to the dying player. The healing
        # window is the run-up the death card shows. The return window runs from
        # the death to the player's first action against another actor, because
        # a resurrection that revived them necessarily precedes it, or to the
        # fight's end when they never acted again.
        healing: list[HealingEvent] = []
        resurrections: list[Resurrection] = []
        for death in deaths:
            scoped = {
                "code": report_code,
                "fightId": run.fight_id,
                "actorId": death.actor_id,
                "startTime": float(death.timestamp_ms - RUN_UP_SECONDS * 1000),
                "endTime": float(death.timestamp_ms),
            }
            healing.extend(
                build_healing(fetch_all_events(self._query, HEALING_QUERY, scoped), ability_names)
            )
            back_by = (
                death.timestamp_ms + death.seconds_until_next_action * 1000
                if death.seconds_until_next_action is not None
                else fight["endTime"]
            )
            return_window = {
                **scoped,
                "startTime": float(death.timestamp_ms),
                "endTime": float(back_by),
            }
            resurrections.extend(
                build_resurrections(
                    fetch_all_events(self._query, RETURN_QUERY, return_window), ability_names
                )
            )

        return LoadedRun(
            run=run,
            casts=casts,
            deaths=deaths,
            enemy_cast_rows=enemy_cast_rows,
            interrupts=interrupts,
            enemy_deaths=enemy_deaths,
            damage_taken=damage_taken,
            health_samples=build_health_samples(cast_events),
            healing=tuple(healing),
            resurrections=tuple(resurrections),
        )
```

- [ ] **Step 5: The skill.** In `.claude/skills/wcl-api/SKILL.md` §"Fields", flip the `includeResources` row to `yes`. Under §"Event streams `ingest.py` reads", add two table rows with today's date, the `type` values Task 1 observed, and the fields the ingest reads:

```markdown
| Healing received | <date> | `dataType: Healing, targetID: <actor>`, per death over the run-up | `heal`, `absorbed`, `removebuff` | `heal`: `abilityGameID`, `amount`, `sourceID`, `targetID`, `timestamp`. `absorbed`: as `heal`, plus `extraAbilityGameID` (the shield) and `attackerID`. `removebuff` is dropped. |
| Return window | <date> | `dataType: All, targetID: <actor>`, per death from the death to the first action | `resurrect` among many | `resurrect`: `abilityGameID`, `sourceID` (the caster), `targetID`, `timestamp`. Every other type is ignored. |
```

- [ ] **Step 6: Run the gate.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

Expected: all pass, including `tests/test_skills.py` now that `includeResources` is in `queries.py`.

- [ ] **Step 7: Commit.**

```bash
/cmd/git.exe add src/wowperf/adapters/wcl/queries.py src/wowperf/adapters/wcl/repository.py .claude/skills/wcl-api/SKILL.md tests/adapters/wcl/test_repository.py
```

Subject: `Fetch the casters' health and, per death, the healing and return windows`. Body: why the windows are scoped by target and bounded by the death and the first action, with Task 1's measured points.

---

### Task 5: Externals per specialisation, as data and as a loaded value

**Files:**
- Create: `data/externals.toml`
- Modify: `src/wowperf/domain/season.py` (after `Defensives`)
- Modify: `src/wowperf/adapters/config/toml.py` (`DEFAULT_EXTERNALS_PATH`, `load_externals`)
- Test: `tests/adapters/config/test_toml.py`, `tests/domain/test_season.py`

**Interfaces:**
- Consumes: `CooldownAbility` from `season.py`; `_read` from `toml.py`.
- Produces: `ExternalAbility(CooldownAbility)`; `Externals(entries).for_spec(class_name, spec) -> tuple[ExternalAbility, ...]`; `load_externals(path=DEFAULT_EXTERNALS_PATH) -> Externals`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/domain/test_season.py` (import `ExternalAbility, Externals` from `wowperf.domain.season`):

```python
def test_externals_resolve_per_spec_and_default_to_none_listed() -> None:
    cocoon = ExternalAbility(ability_id=1, name="Life Cocoon", cooldown_seconds=120.0)
    externals = Externals(entries=(("Monk/Mistweaver", (cocoon,)),))
    assert externals.for_spec("Monk", "Mistweaver") == (cocoon,)
    assert externals.for_spec("Monk", "Windwalker") == ()
    assert Externals().for_spec("Monk", "Mistweaver") == ()
```

Append to `tests/adapters/config/test_toml.py`:

```python
def test_the_committed_externals_file_parses_and_names_healer_externals() -> None:
    from wowperf.adapters.config.toml import DEFAULT_EXTERNALS_PATH, load_externals

    externals = load_externals(DEFAULT_EXTERNALS_PATH)
    names = {ability.name for _, abilities in externals.entries for ability in abilities}
    assert {"Pain Suppression", "Ironbark", "Life Cocoon", "Guardian Spirit"} <= names
    assert externals.for_spec("Bard", "Jazz") == ()


def test_every_external_has_a_positive_cooldown_and_a_valid_spec_key() -> None:
    from wowperf.adapters.config.toml import load_externals

    for key, abilities in load_externals().entries:
        class_name, _, spec = key.partition("/")
        assert class_name in WCL_CLASS_NAMES and spec, f"spec key can never match: {key}"
        for ability in abilities:
            assert ability.cooldown_seconds > 0, f"{key}: {ability.name} has no cooldown"
            assert ability.charges >= 1


def test_no_ability_lives_in_two_of_the_three_cooldown_files_for_one_spec() -> None:
    """Defensives, throughput cooldowns and externals ask three different questions.

    An ability answering two of them at once would be judged twice and could
    disagree with itself; the judgement of which file owns it is made once, in
    the data.
    """
    from wowperf.adapters.config.toml import (
        load_defensives,
        load_externals,
        load_throughput_cooldowns,
    )

    owners: dict[tuple[str, int], list[str]] = {}
    for label, loaded in (
        ("defensive", load_defensives()),
        ("throughput", load_throughput_cooldowns()),
        ("external", load_externals()),
    ):
        for key, abilities in loaded.entries:
            for ability in abilities:
                owners.setdefault((key, ability.ability_id), []).append(label)
    clashes = {k: v for k, v in owners.items() if len(v) > 1}
    assert clashes == {}, f"listed in more than one file: {clashes}"
```

Leave `test_no_ability_is_both_a_defensive_and_a_throughput_cooldown_for_one_spec` in place: it still holds, and the three-file test is broader, not a replacement.

- [ ] **Step 2: Run them to see them fail.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/test_season.py tests/adapters/config/test_toml.py -q
```

Expected: ImportError on `ExternalAbility` / `load_externals`.

- [ ] **Step 3: The model and the loader.** In `season.py`, after `Defensives`:

```python
class ExternalAbility(CooldownAbility):
    """One cooldown a player casts on someone else to keep them alive."""


class Externals(Frozen):
    """Externals per class and specialisation, keyed like the defensives.

    Kept apart from the defensives because the question differs: a defensive
    is the dying player's own answer, an external is a teammate's, and the
    death card names the owner of every external so nobody reads "Ironbark
    ready" as a button the dying player could have pressed.
    """

    entries: tuple[tuple[str, tuple[ExternalAbility, ...]], ...] = ()

    def for_spec(self, class_name: str, spec: str) -> tuple[ExternalAbility, ...]:
        """The known externals for a class/spec, or `()` if the list has none."""
        wanted = f"{class_name}/{spec}"
        for key, abilities in self.entries:
            if key == wanted:
                return abilities
        return ()
```

In `toml.py`, import `ExternalAbility, Externals`, add `DEFAULT_EXTERNALS_PATH = DATA_DIR / "externals.toml"` beside the other paths, and after `load_defensives`:

```python
def load_externals(path: Path = DEFAULT_EXTERNALS_PATH) -> Externals:
    """Read the hand-maintained list of cooldowns cast on other players."""
    raw = _read(path)
    entries = []
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue  # the top-level `verified` date
        abilities = value.get("abilities") or []
        entries.append(
            (
                key,
                tuple(
                    ExternalAbility(
                        ability_id=int(item["ability_id"]),
                        name=str(item["name"]),
                        cooldown_seconds=float(item["cooldown_seconds"]),
                        charges=int(item.get("charges", 1)),
                    )
                    for item in abilities
                ),
            )
        )
    return Externals(entries=tuple(entries))
```

- [ ] **Step 4: The data file.** Create `data/externals.toml` with the header below, then one table per specialisation. **The abilities are listed here by name only. Look up every `ability_id` and `cooldown_seconds` the way `data/defensives.toml`'s header describes, on the day you write the file, and put that day in `verified`.** Base cooldowns, no talent reductions. Do not copy an id from memory or from another file.

```toml
# ABOUTME: Cooldowns a player casts on someone else to keep them alive, by class and spec.
# ABOUTME: Read by the death recap to list what teammates had for the dying player.
#
# No API exposes this list or the cooldowns, so both are maintained by hand and dated.
# A spec absent from this file simply produces no external rows for that teammate.
#
# An ability must not appear here and in defensives.toml or throughput_cooldowns.toml
# for the same spec: the three files ask different questions, and a test enforces it.
#
# Cooldowns are base values in seconds, without talent reductions. A longer cooldown
# makes an external read as unavailable more often, which understates what was up
# and cannot produce a false accusation.
#
# Every ability id and cooldown here was read from the game's own spell data on the
# date below, one spell at a time, and the name returned had to match the ability
# intended. An id that matches nothing fails silently forever, so recall is not enough.
verified = "<date>"
```

Abilities to list, per spec key, each as `{ ability_id = <verified>, name = "<name>", cooldown_seconds = <verified> }`:

- `Priest/Discipline`: Pain Suppression, Power Word: Barrier
- `Priest/Holy`: Guardian Spirit
- `Druid/Restoration`: Ironbark
- `Monk/Mistweaver`: Life Cocoon
- `Shaman/Restoration`: Spirit Link Totem
- `Evoker/Preservation`: Time Dilation
- `Paladin/Holy`, `Paladin/Protection`, `Paladin/Retribution`: Blessing of Protection, Blessing of Sacrifice, Lay on Hands
- `Warrior/Arms`, `Warrior/Fury`, `Warrior/Protection`: Rallying Cry

If a name does not resolve to a live spell, leave it out and say so in the commit body rather than guessing. If an ability you add already sits in `defensives.toml` or `throughput_cooldowns.toml` for the same spec, the three-file test fails: an external is cast on another player and a self-only cooldown is not one, so decide which file owns it on that rule and record the reasoning in the commit body.

- [ ] **Step 5: Run the gate.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

Expected: all pass.

- [ ] **Step 6: Commit.**

```bash
/cmd/git.exe add data/externals.toml src/wowperf/domain/season.py src/wowperf/adapters/config/toml.py tests/domain/test_season.py tests/adapters/config/test_toml.py
```

Subject: `List the externals each specialisation can cast on a dying teammate`. Body: how and when the ids were verified, which names were left out and why, and why the externals are a fourth file rather than rows in the defensives.

---

### Task 6: The recap timeline with its reconstructed health column

**Files:**
- Create: `src/wowperf/domain/analysis/recap.py`
- Test: `tests/domain/analysis/test_recap_timeline.py`

**Interfaces:**
- Consumes: `LoadedRun`, `Death`, `HealthSample`, `RUN_UP_SECONDS`.
- Produces: `RecapEvent(kind, timestamp_ms, ability_name, amount=0, absorbed=0, source_id=None, health_percent=None)` with `kind` in `HIT, ABSORB, HEAL, CAST`; `recap_timeline(loaded, death) -> tuple[RecapEvent, ...]`; `with_health(events, samples, window_start_ms) -> tuple[RecapEvent, ...]`. Tasks 7 and 8 add to the same module; Task 9 formats these.

- [ ] **Step 1: Write the failing tests.** Create `tests/domain/analysis/test_recap_timeline.py`:

```python
# ABOUTME: The last ten seconds of a death as one ordered timeline, with health after each event
# ABOUTME: reconstructed between the player's own readings. Every rule of spec §4.1 and §4.2.

from tests.domain.report.test_build_frame import a_pull, a_run
from wowperf.domain.analysis.recap import (
    ABSORB,
    CAST,
    HEAL,
    HIT,
    RecapEvent,
    recap_timeline,
    with_health,
)
from wowperf.domain.events import (
    CastEvent,
    DamageTakenEvent,
    Death,
    HealingEvent,
    HealthSample,
)
from wowperf.domain.model import LoadedRun, Player

DEATH_MS = 60_000
DUDE = Player(actor_id=1, name="Dudesons", class_name="DeathKnight", spec="Blood", item_level=680)


def a_death(at_ms: int = DEATH_MS, actor_id: int = 1) -> Death:
    return Death(player_name="Dudesons", actor_id=actor_id, timestamp_ms=at_ms,
                 killing_blow="Frigid Roar", pull_index=0)


def a_hit(at_ms: int, health_damage: int, absorbed: int = 0, actor_id: int = 1,
          ability: str = "Snowdrift") -> DamageTakenEvent:
    return DamageTakenEvent(actor_id=actor_id, ability_id=1, ability_name=ability,
                            amount=health_damage + absorbed, timestamp_ms=at_ms,
                            health_damage=health_damage, absorbed=absorbed)


def a_heal(at_ms: int, amount: int, absorbed: bool = False, actor_id: int = 1,
           ability: str = "Rejuvenation", source_id: int = 2) -> HealingEvent:
    return HealingEvent(actor_id=actor_id, source_id=source_id, ability_id=7,
                        ability_name=ability, amount=amount, timestamp_ms=at_ms,
                        absorbed=absorbed)


def a_cast(at_ms: int, actor_id: int = 1, ability: str = "Death Strike") -> CastEvent:
    return CastEvent(actor_id=actor_id, ability_id=9, ability_name=ability, timestamp_ms=at_ms)


def a_sample(at_ms: int, hit_points: int, maximum: int = 100_000, actor_id: int = 1) -> HealthSample:
    return HealthSample(actor_id=actor_id, timestamp_ms=at_ms, hit_points=hit_points,
                        max_hit_points=maximum)


def loaded(**streams: object) -> LoadedRun:
    return LoadedRun(run=a_run(players=(DUDE,), pulls=(a_pull(0, 0, 120_000),)), **streams)  # type: ignore[arg-type]


def test_the_timeline_holds_hits_absorbs_heals_and_own_casts_inside_the_window_only() -> None:
    run = loaded(
        damage_taken=(a_hit(49_000, 10), a_hit(50_000, 20), a_hit(60_000, 30)),
        healing=(a_heal(52_000, 5), a_heal(53_000, 8, absorbed=True, ability="Blood Shield"),
                 a_heal(61_000, 9)),
        casts=(a_cast(51_000), a_cast(58_000, actor_id=3)),
    )
    kinds = [(e.kind, e.timestamp_ms) for e in recap_timeline(run, a_death())]
    assert kinds == [(HIT, 50_000), (CAST, 51_000), (HEAL, 52_000), (ABSORB, 53_000),
                     (HIT, 60_000)]


def test_events_sharing_a_timestamp_read_hit_absorb_heal_then_cast() -> None:
    run = loaded(
        damage_taken=(a_hit(55_000, 10),),
        healing=(a_heal(55_000, 5), a_heal(55_000, 3, absorbed=True)),
        casts=(a_cast(55_000),),
    )
    assert [e.kind for e in recap_timeline(run, a_death())] == [HIT, ABSORB, HEAL, CAST]


def test_a_hit_carries_its_health_damage_and_absorbed_share_and_a_heal_its_source() -> None:
    run = loaded(damage_taken=(a_hit(55_000, 1_000, absorbed=400),), healing=(a_heal(56_000, 5),))
    hit, heal = recap_timeline(run, a_death())
    assert (hit.amount, hit.absorbed, heal.amount, heal.source_id) == (1_000, 400, 5, 2)


def test_another_players_events_do_not_enter_the_timeline() -> None:
    run = loaded(damage_taken=(a_hit(55_000, 10, actor_id=3),), healing=(a_heal(56_000, 5, actor_id=3),))
    assert recap_timeline(run, a_death()) == ()


# --- health -------------------------------------------------------------------


def test_the_anchor_is_the_latest_reading_at_or_before_the_window_opens() -> None:
    events = (RecapEvent(kind=HIT, timestamp_ms=55_000, ability_name="x", amount=10_000),)
    samples = (a_sample(40_000, 90_000), a_sample(50_000, 80_000), a_sample(70_000, 1))
    assert with_health(events, samples, 50_000)[0].health_percent == 70


def test_without_any_reading_before_the_first_event_the_rows_carry_no_health() -> None:
    events = (
        RecapEvent(kind=HIT, timestamp_ms=52_000, ability_name="x", amount=10_000),
        RecapEvent(kind=CAST, timestamp_ms=55_000, ability_name="y"),
        RecapEvent(kind=HIT, timestamp_ms=57_000, ability_name="x", amount=10_000),
    )
    percents = [e.health_percent for e in with_health(events, (a_sample(55_000, 50_000),), 50_000)]
    assert percents == [None, 50, 40]


def test_a_heal_is_capped_at_the_maximum_and_an_absorb_changes_nothing() -> None:
    events = (
        RecapEvent(kind=HEAL, timestamp_ms=51_000, ability_name="h", amount=50_000),
        RecapEvent(kind=ABSORB, timestamp_ms=52_000, ability_name="s", amount=30_000),
    )
    percents = [e.health_percent for e in with_health(events, (a_sample(50_000, 90_000),), 50_000)]
    assert percents == [100, 100]


def test_a_reading_inside_the_window_replaces_the_running_value() -> None:
    # The arithmetic drifted (a missed event), the reading wins, silently.
    events = (
        RecapEvent(kind=HIT, timestamp_ms=51_000, ability_name="x", amount=10_000),
        RecapEvent(kind=CAST, timestamp_ms=53_000, ability_name="y"),
        RecapEvent(kind=HIT, timestamp_ms=54_000, ability_name="x", amount=10_000),
    )
    samples = (a_sample(50_000, 100_000), a_sample(53_000, 60_000))
    percents = [e.health_percent for e in with_health(events, samples, 50_000)]
    assert percents == [90, 60, 50]


def test_the_killing_blow_clamps_at_zero_rather_than_going_negative() -> None:
    events = (RecapEvent(kind=HIT, timestamp_ms=60_000, ability_name="x", amount=500_000),)
    assert with_health(events, (a_sample(50_000, 20_000),), 50_000)[0].health_percent == 0


def test_the_percentage_uses_the_latest_sampled_maximum() -> None:
    events = (RecapEvent(kind=HIT, timestamp_ms=55_000, ability_name="x", amount=0),)
    samples = (a_sample(50_000, 60_000, maximum=120_000),)
    assert with_health(events, samples, 50_000)[0].health_percent == 50


def test_recap_timeline_reads_only_the_dying_players_samples() -> None:
    run = loaded(
        damage_taken=(a_hit(55_000, 10_000),),
        health_samples=(a_sample(50_000, 50_000, actor_id=3), a_sample(50_000, 100_000)),
    )
    assert recap_timeline(run, a_death())[0].health_percent == 90
```

- [ ] **Step 2: Run them to see them fail.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis/test_recap_timeline.py -q
```

Expected: `ModuleNotFoundError: wowperf.domain.analysis.recap`.

- [ ] **Step 3: Implement.** Create `src/wowperf/domain/analysis/recap.py`:

```python
# ABOUTME: One death's recap: the last seconds as a timeline with a reconstructed health column,
# ABOUTME: the state of every saving tool at the death, and how the player came back. Pure.

from wowperf.domain.analysis.defensives import RUN_UP_SECONDS
from wowperf.domain.base import Frozen
from wowperf.domain.events import Death, HealthSample
from wowperf.domain.model import LoadedRun

HIT = "hit"
ABSORB = "absorb"
HEAL = "heal"
CAST = "cast"
KIND_ORDER = {HIT: 0, ABSORB: 1, HEAL: 2, CAST: 3}
"""Tie-break for events sharing a timestamp: what struck, what soaked it, what healed, what
the player did. The vocabulary the report maps to row classes; nothing else reads it."""


class RecapEvent(Frozen):
    """One row of the timeline, before formatting.

    `amount` is what reached health for a hit, what a shield soaked for an
    absorb, what landed for a heal, and zero for the player's own cast.
    `absorbed` on a hit is the share a shield took beside the health damage.
    `health_percent` is the reconstructed health after the event, or None
    before the first reading.
    """

    kind: str
    timestamp_ms: int
    ability_name: str
    amount: int = 0
    absorbed: int = 0
    source_id: int | None = None
    health_percent: int | None = None


def window_start(death: Death) -> int:
    """Where the run-up opens: the same constant the availability rule reads."""
    return int(death.timestamp_ms - RUN_UP_SECONDS * 1000)


def recap_timeline(loaded: LoadedRun, death: Death) -> tuple[RecapEvent, ...]:
    """Every event of the run-up where the player was hit, shielded, healed, or acted."""
    start, end, actor = window_start(death), death.timestamp_ms, death.actor_id
    events: list[RecapEvent] = []
    for hit in loaded.damage_taken:
        if hit.actor_id == actor and start <= hit.timestamp_ms <= end:
            events.append(
                RecapEvent(
                    kind=HIT,
                    timestamp_ms=hit.timestamp_ms,
                    ability_name=hit.ability_name,
                    amount=hit.health_damage,
                    absorbed=hit.absorbed,
                )
            )
    for heal in loaded.healing:
        if heal.actor_id == actor and start <= heal.timestamp_ms <= end:
            events.append(
                RecapEvent(
                    kind=ABSORB if heal.absorbed else HEAL,
                    timestamp_ms=heal.timestamp_ms,
                    ability_name=heal.ability_name,
                    amount=heal.amount,
                    source_id=heal.source_id,
                )
            )
    for cast in loaded.casts:
        if cast.actor_id == actor and start <= cast.timestamp_ms <= end:
            events.append(
                RecapEvent(kind=CAST, timestamp_ms=cast.timestamp_ms, ability_name=cast.ability_name)
            )
    events.sort(key=lambda event: (event.timestamp_ms, KIND_ORDER[event.kind]))
    samples = tuple(
        sorted(
            (sample for sample in loaded.health_samples if sample.actor_id == actor),
            key=lambda sample: sample.timestamp_ms,
        )
    )
    return with_health(tuple(events), samples, start)


def with_health(
    events: tuple[RecapEvent, ...],
    samples: tuple[HealthSample, ...],
    window_start_ms: int,
) -> tuple[RecapEvent, ...]:
    """Reconstruct health after each event between the player's own readings.

    The anchor is the latest reading at or before the window opens, or failing
    that the first reading inside it; rows before any anchor carry no value.
    Walking forward, a hit subtracts what reached health, a heal adds its
    amount capped at the sampled maximum, an absorb changes nothing because the
    shield took it, and a reading replaces the running value outright. When a
    reading disagrees with the arithmetic the reading wins and nothing is said:
    the drift came from an event the log did not carry, and the reading is the
    only fact available. `samples` must be sorted by time.
    """
    running: int | None = None
    maximum = 0
    pending = list(samples)
    while pending and pending[0].timestamp_ms <= window_start_ms:
        sample = pending.pop(0)
        running, maximum = sample.hit_points, sample.max_hit_points

    rows = []
    for event in events:
        while pending and pending[0].timestamp_ms <= event.timestamp_ms:
            sample = pending.pop(0)
            running, maximum = sample.hit_points, sample.max_hit_points
        if running is not None:
            if event.kind == HIT:
                running -= event.amount
            elif event.kind == HEAL:
                running = min(running + event.amount, maximum)
        percent = (
            None
            if running is None or maximum <= 0
            else max(0, min(100, round(100 * running / maximum)))
        )
        rows.append(event.model_copy(update={"health_percent": percent}))
    return tuple(rows)
```

- [ ] **Step 4: Run the gate.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

Expected: all pass. If ruff flags the long `RecapEvent(kind=CAST, ...)` line, wrap it.

- [ ] **Step 5: Commit.**

```bash
/cmd/git.exe add src/wowperf/domain/analysis/recap.py tests/domain/analysis/test_recap_timeline.py
```

Subject: `Build a death's timeline and reconstruct health between the player's own readings`. Body: why the readings come only from the player's casts, why a reading wins silently, and why the window constant is shared with the availability rule.

---

### Task 7: The four-state availability of every saving tool

**Files:**
- Modify: `src/wowperf/domain/analysis/recap.py`
- Test: `tests/domain/analysis/test_recap_availability.py`

**Interfaces:**
- Consumes: `CastEvent`, `Defensives`, `Consumables`, `ConsumableCategory`, `Externals`, `CooldownAbility`; `RUN_UP_SECONDS`.
- Produces: `PRESSED, READY, COOLDOWN, UNSEEN`; `AbilityState(name, state, owner_id=None, seconds=None)`; `AvailabilityAt(own=None, consumables=None, externals=())`; `state_of(presses, name, cooldown_seconds, charges, death_ms, *, owner_id=None, on_target=None) -> AbilityState`; `consumable_state(presses, category, death_ms) -> AbilityState`; `availability_at(loaded, death, defensives, consumables, externals, visible_from_ms) -> AvailabilityAt`.

The rule, from spec §4.3, with the one refinement Task 11 amends into the design: a **ready** row whose readiness arrived inside the run-up carries how long it had been ready, as a lower bound (base cooldowns are longer than talented ones, so the true moment was earlier).

- [ ] **Step 1: Write the failing tests.** Create `tests/domain/analysis/test_recap_availability.py`:

```python
# ABOUTME: The state of each saving tool at a death: pressed in the run-up, ready, on cooldown
# ABOUTME: with an upper bound, or never seen. Each doubt resolves toward saying less.

from tests.domain.analysis.test_recap_timeline import DUDE, a_cast, a_death, loaded
from wowperf.domain.analysis.recap import (
    COOLDOWN,
    PRESSED,
    READY,
    UNSEEN,
    availability_at,
    consumable_state,
    state_of,
)
from wowperf.domain.events import CastEvent
from wowperf.domain.model import Player
from wowperf.domain.season import (
    ConsumableCategory,
    Consumables,
    DefensiveAbility,
    Defensives,
    ExternalAbility,
    Externals,
)

DEATH_MS = 60_000
ICEBOUND = DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=120.0)
RUNE_TAP = DefensiveAbility(ability_id=194679, name="Rune Tap", cooldown_seconds=25.0, charges=2)
IRONBARK = ExternalAbility(ability_id=102342, name="Ironbark", cooldown_seconds=90.0)
STONE = ConsumableCategory(name="healthstone", cooldown_seconds=60.0, ability_ids=(6262,))
TREE = Player(actor_id=2, name="Leafy", class_name="Druid", spec="Restoration", item_level=680)


def press(ability_id: int, at_ms: int, actor_id: int = 1, target_id: int | None = None) -> CastEvent:
    return CastEvent(actor_id=actor_id, ability_id=ability_id, ability_name="x",
                     timestamp_ms=at_ms, target_id=target_id)


def test_an_ability_never_pressed_is_unseen_not_judged() -> None:
    assert state_of((), "Icebound Fortitude", 120.0, 1, DEATH_MS).state == UNSEEN


def test_a_press_inside_the_run_up_is_pressed_with_the_seconds_before_death() -> None:
    state = state_of((press(48792, 1_000), press(48792, 56_600)), "IBF", 120.0, 1, DEATH_MS)
    assert (state.state, state.seconds) == (PRESSED, 3.4)


def test_a_press_inside_one_cooldown_leaves_an_upper_bound_in_whole_seconds() -> None:
    # Pressed 100.2 s before death on a 120 s cooldown: at most 19.8 s left, said as 20.
    state = state_of((press(48792, DEATH_MS - 100_200),), "IBF", 120.0, 1, DEATH_MS)
    assert (state.state, state.seconds) == (COOLDOWN, 20)


def test_a_press_older_than_one_cooldown_leaves_the_ability_ready() -> None:
    state = state_of((press(48792, DEATH_MS - 135_000),), "IBF", 120.0, 1, DEATH_MS)
    assert (state.state, state.seconds) == (READY, None)


def test_readiness_that_arrived_inside_the_run_up_says_for_how_long_at_least() -> None:
    # Pressed 124 s before a 120 s cooldown's death: ready for 4 s by the base cooldown,
    # and longer if a talent shortened it — so "at least".
    state = state_of((press(48792, DEATH_MS - 124_000),), "IBF", 120.0, 1, DEATH_MS)
    assert (state.state, state.seconds) == (READY, 4.0)


def test_a_second_charge_keeps_an_ability_ready_until_both_are_spent() -> None:
    one = state_of((press(194679, DEATH_MS - 20_000),), "Rune Tap", 25.0, 2, DEATH_MS)
    two = state_of(
        (press(194679, DEATH_MS - 20_000), press(194679, DEATH_MS - 15_000)),
        "Rune Tap", 25.0, 2, DEATH_MS,
    )
    assert one.state == READY
    # The older press frees the next charge: 25 - 20 = 5 s left at most.
    assert (two.state, two.seconds) == (COOLDOWN, 5)


def test_an_external_counts_as_pressed_only_when_cast_on_the_dying_player() -> None:
    on_them = state_of((press(102342, 57_000, actor_id=2, target_id=1),), "Ironbark", 90.0, 1,
                       DEATH_MS, owner_id=2, on_target=1)
    on_other = state_of((press(102342, 57_000, actor_id=2, target_id=3),), "Ironbark", 90.0, 1,
                        DEATH_MS, owner_id=2, on_target=1)
    assert (on_them.state, on_them.owner_id) == (PRESSED, 2)
    assert (on_other.state, on_other.seconds) == (COOLDOWN, 87)


def test_a_consumable_never_drunk_is_ready_because_no_talent_gates_a_potion() -> None:
    assert consumable_state((), STONE, DEATH_MS).state == READY


def test_a_consumable_drunk_in_the_run_up_is_pressed() -> None:
    assert consumable_state((press(6262, 58_000),), STONE, DEATH_MS).state == PRESSED


def test_availability_groups_own_defensives_consumables_and_teammates_externals() -> None:
    run = loaded(
        casts=(press(48792, 1_000), press(102342, 150_000, actor_id=2, target_id=3)),
    )
    run = run.model_copy(update={"run": run.run.model_copy(update={"players": (DUDE, TREE)})})
    at = availability_at(
        run, a_death(at_ms=200_000), Defensives(entries=(("DeathKnight/Blood", (ICEBOUND, RUNE_TAP)),)),
        Consumables(categories=(STONE,)), Externals(entries=(("Druid/Restoration", (IRONBARK,)),)),
        visible_from_ms=0,
    )
    assert at.own is not None and [(s.name, s.state) for s in at.own] == [
        ("Icebound Fortitude", READY), ("Rune Tap", UNSEEN)
    ]
    assert at.consumables is not None and [(s.name, s.state) for s in at.consumables] == [
        ("healthstone", READY)
    ]
    assert [(s.name, s.owner_id, s.state, s.seconds) for s in at.externals] == [
        ("Ironbark", 2, COOLDOWN, 40)
    ]


def test_a_spec_absent_from_a_file_yields_none_for_that_group_not_an_empty_list() -> None:
    at = availability_at(loaded(), a_death(), Defensives(), Consumables(), Externals(),
                         visible_from_ms=0)
    assert (at.own, at.consumables, at.externals) == (None, None, ())


def test_a_consumable_whose_window_reaches_before_the_fight_is_not_judged() -> None:
    # The stone's window is 60 + 10 s; a death 40 s in cannot see far enough back.
    at = availability_at(loaded(), a_death(at_ms=40_000), Defensives(),
                         Consumables(categories=(STONE,)), Externals(), visible_from_ms=0)
    assert at.consumables == ()


def test_the_dying_player_is_not_their_own_teammate() -> None:
    run = loaded(casts=(press(102342, 1_000),))
    run = run.model_copy(update={"run": run.run.model_copy(update={"players": (
        Player(actor_id=1, name="Leafy", class_name="Druid", spec="Restoration", item_level=680),
    )})})
    at = availability_at(run, a_death(), Defensives(), Consumables(),
                         Externals(entries=(("Druid/Restoration", (IRONBARK,)),)), visible_from_ms=0)
    assert at.externals == ()
```

- [ ] **Step 2: Run them to see them fail.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis/test_recap_availability.py -q
```

Expected: ImportError on `state_of`.

- [ ] **Step 3: Implement.** Append to `recap.py` (add `math` to the imports, `CastEvent` to the events import, and `ConsumableCategory, Consumables, Defensives, Externals` from `wowperf.domain.season`):

```python
PRESSED = "pressed"
READY = "ready"
COOLDOWN = "cooldown"
UNSEEN = "unseen"


class AbilityState(Frozen):
    """One saving tool at the moment of death.

    `seconds` means one thing per state. PRESSED: how many seconds before the
    death its owner cast it. COOLDOWN: the upper bound left, in whole seconds.
    READY: how long it had been ready when that fell inside the run-up, a lower
    bound, else None. UNSEEN: always None. `owner_id` is None for the dying
    player's own abilities and a teammate's actor id for an external.
    """

    name: str
    state: str
    owner_id: int | None = None
    seconds: float | None = None


class AvailabilityAt(Frozen):
    """The three groups of a death's availability column.

    `own` and `consumables` are None when the tool has nothing to say — a spec
    absent from the data file, an actor off the roster — which is not the same
    as an empty tuple, where everything was checked and listed. Externals are
    one tuple over every teammate, empty when no teammate's spec is listed.
    """

    own: tuple[AbilityState, ...] | None = None
    consumables: tuple[AbilityState, ...] | None = None
    externals: tuple[AbilityState, ...] = ()


def state_of(
    presses: tuple[CastEvent, ...],
    name: str,
    cooldown_seconds: float,
    charges: int,
    death_ms: int,
    *,
    owner_id: int | None = None,
    on_target: int | None = None,
) -> AbilityState:
    """Which of the four states one ability was in at the death.

    Never pressed in the fight is UNSEEN: a talent not taken looks exactly like
    a button never pressed, so it is listed and not judged. A press inside the
    run-up is PRESSED — for an external, only a press on the dying player
    (`on_target`), since a cast on someone else was a use, not a save. With
    `charges` or more presses inside one base cooldown before the death the
    ability is on COOLDOWN, and the bound is when the oldest of those presses
    frees its charge, rounded up. Otherwise READY.

    Every figure is bounded the safe way: the log records no cooldown reset,
    charge refresh or talent reduction, so the true remaining time is at most
    the bound and the true ready moment is no later than the one computed.
    """
    if not presses:
        return AbilityState(name=name, state=UNSEEN, owner_id=owner_id)
    run_up_start = death_ms - RUN_UP_SECONDS * 1000
    in_run_up = [
        press.timestamp_ms
        for press in presses
        if run_up_start <= press.timestamp_ms <= death_ms
        and (on_target is None or press.target_id == on_target)
    ]
    if in_run_up:
        return AbilityState(
            name=name, state=PRESSED, owner_id=owner_id,
            seconds=(death_ms - max(in_run_up)) / 1000,
        )
    cooldown_ms = cooldown_seconds * 1000
    recent = sorted(
        press.timestamp_ms
        for press in presses
        if death_ms - cooldown_ms <= press.timestamp_ms <= death_ms
    )
    if len(recent) >= charges:
        frees_at = recent[len(recent) - charges] + cooldown_ms
        return AbilityState(
            name=name, state=COOLDOWN, owner_id=owner_id,
            seconds=math.ceil((frees_at - death_ms) / 1000),
        )
    before = [press.timestamp_ms for press in presses if press.timestamp_ms <= death_ms]
    ready_since = max(before) + cooldown_ms if before else None
    ready_for = (
        (death_ms - ready_since) / 1000
        if ready_since is not None and ready_since >= run_up_start
        else None
    )
    return AbilityState(name=name, state=READY, owner_id=owner_id, seconds=ready_for)


def consumable_state(
    presses: tuple[CastEvent, ...], category: ConsumableCategory, death_ms: int
) -> AbilityState:
    """A consumable category's state: as an ability's, except that never drunk is READY.

    No talent gates a potion, so silence is not ambiguity here — the caveat
    that the log never proves one was carried stays on the card instead.
    """
    state = state_of(presses, category.name, category.cooldown_seconds, 1, death_ms)
    if state.state == UNSEEN:
        return AbilityState(name=category.name, state=READY)
    return state


def availability_at(
    loaded: LoadedRun,
    death: Death,
    defensives: Defensives,
    consumables: Consumables,
    externals: Externals,
    visible_from_ms: int,
) -> AvailabilityAt:
    """The player's own defensives, the consumables, and every teammate's externals.

    A consumable category is judged only when its whole window lies inside the
    fight (`visible_from_ms`), the rule `consumables_up_at` applies: a potion
    drunk before the timer started is invisible. Externals come in roster
    order, each carrying its owner.
    """
    players = {player.actor_id: player for player in loaded.run.players}
    player = players.get(death.actor_id)
    death_ms = death.timestamp_ms

    def presses_of(actor_id: int, ability_ids: tuple[int, ...]) -> tuple[CastEvent, ...]:
        return tuple(
            cast
            for cast in loaded.casts
            if cast.actor_id == actor_id and cast.ability_id in ability_ids
        )

    own = None
    if player is not None:
        known = defensives.for_spec(player.class_name, player.spec)
        if known:
            own = tuple(
                state_of(
                    presses_of(death.actor_id, (ability.ability_id,)),
                    ability.name, ability.cooldown_seconds, ability.charges, death_ms,
                )
                for ability in known
            )

    drinks = None
    if player is not None and consumables.categories:
        drinks = tuple(
            consumable_state(presses_of(death.actor_id, category.ability_ids), category, death_ms)
            for category in consumables.categories
            if death_ms - (category.cooldown_seconds + RUN_UP_SECONDS) * 1000 >= visible_from_ms
        )

    mates = []
    for mate in loaded.run.players:
        if mate.actor_id == death.actor_id:
            continue
        for ability in externals.for_spec(mate.class_name, mate.spec):
            mates.append(
                state_of(
                    presses_of(mate.actor_id, (ability.ability_id,)),
                    ability.name, ability.cooldown_seconds, ability.charges, death_ms,
                    owner_id=mate.actor_id, on_target=death.actor_id,
                )
            )
    return AvailabilityAt(own=own, consumables=drinks, externals=tuple(mates))
```

- [ ] **Step 4: Run the gate.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
/cmd/git.exe add src/wowperf/domain/analysis/recap.py tests/domain/analysis/test_recap_availability.py
```

Subject: `Place every saving tool in one of four states at the moment of death`. Body: why the bound is an upper bound and readiness a lower bound, why an external is pressed only on the dying player, and why a consumable is never unseen.

---

### Task 8: How the player came back

**Files:**
- Modify: `src/wowperf/domain/analysis/recap.py`
- Modify: `src/wowperf/domain/season.py` (`SelfResurrections`)
- Modify: `src/wowperf/adapters/config/toml.py` (`DEFAULT_RESURRECTIONS_PATH`, `load_self_resurrections`)
- Create: `data/resurrections.toml` — **only if Task 1's skill row says a self-resurrection emits no `resurrect` event, or was not observed.** If the row shows one with `sourceID == targetID`, skip Steps 4 and 5, pass `SelfResurrections()` everywhere, and say so in the commit body.
- Test: `tests/domain/analysis/test_recap_return.py`, `tests/adapters/config/test_toml.py`

**Interfaces:**
- Consumes: `Resurrection`, `Death.seconds_until_next_action`, `CastEvent`.
- Produces: `RESURRECTED, SELF_RESURRECTED, RELEASED, ABSENT`; `Return(kind, seconds_after=None, caster_id=None, ability_name="")`; `return_of(loaded, death, self_resurrections) -> Return`; `SelfResurrections(ability_ids=())`; `load_self_resurrections(path=DEFAULT_RESURRECTIONS_PATH)`.

- [ ] **Step 1: Write the failing tests.** Create `tests/domain/analysis/test_recap_return.py`:

```python
# ABOUTME: How a dead player came back: a teammate's resurrection, their own, a release, or not
# ABOUTME: at all. A resurrection after the first action belongs to a later death and is ignored.

from tests.domain.analysis.test_recap_timeline import a_cast, loaded
from wowperf.domain.analysis.recap import (
    ABSENT,
    RELEASED,
    RESURRECTED,
    SELF_RESURRECTED,
    return_of,
)
from wowperf.domain.events import Death, Resurrection
from wowperf.domain.season import SelfResurrections

REINCARNATION = SelfResurrections(ability_ids=(21169,))


def dead(at_ms: int = 60_000, back_after: float | None = None) -> Death:
    return Death(player_name="Dudesons", actor_id=1, timestamp_ms=at_ms, killing_blow="x",
                 pull_index=0, seconds_until_next_action=back_after)


def raised(at_ms: int, caster_id: int = 3, actor_id: int = 1) -> Resurrection:
    return Resurrection(actor_id=actor_id, caster_id=caster_id, ability_id=61999,
                        ability_name="Raise Ally", timestamp_ms=at_ms)


def test_a_teammates_resurrection_before_the_first_action_wins() -> None:
    back = return_of(loaded(resurrections=(raised(68_000),)), dead(back_after=12.0), REINCARNATION)
    assert (back.kind, back.seconds_after, back.caster_id, back.ability_name) == (
        RESURRECTED, 8.0, 3, "Raise Ally"
    )


def test_a_resurrection_event_by_the_player_themselves_is_a_self_resurrection() -> None:
    back = return_of(loaded(resurrections=(raised(65_000, caster_id=1),)), dead(back_after=9.0),
                     SelfResurrections())
    assert (back.kind, back.seconds_after) == (SELF_RESURRECTED, 5.0)


def test_a_listed_spell_cast_by_the_dead_player_is_a_self_resurrection() -> None:
    cast = a_cast(66_000, ability="Reincarnation").model_copy(update={"ability_id": 21169})
    back = return_of(loaded(casts=(cast,)), dead(back_after=15.0), REINCARNATION)
    assert (back.kind, back.seconds_after, back.ability_name) == (
        SELF_RESURRECTED, 6.0, "Reincarnation"
    )


def test_no_resurrection_and_a_later_action_is_a_release() -> None:
    back = return_of(loaded(), dead(back_after=34.2), REINCARNATION)
    assert (back.kind, back.seconds_after) == (RELEASED, 34.2)


def test_no_resurrection_and_no_action_is_absent() -> None:
    assert return_of(loaded(), dead(), REINCARNATION).kind == ABSENT


def test_a_resurrection_after_the_first_action_belongs_to_a_later_death() -> None:
    back = return_of(loaded(resurrections=(raised(90_000),)), dead(back_after=12.0), REINCARNATION)
    assert back.kind == RELEASED


def test_another_players_resurrection_is_not_this_ones() -> None:
    back = return_of(loaded(resurrections=(raised(65_000, actor_id=2),)), dead(back_after=12.0),
                     REINCARNATION)
    assert back.kind == RELEASED
```

If the data file is built, append to `tests/adapters/config/test_toml.py`:

```python
def test_the_committed_resurrections_file_lists_self_resurrection_spells() -> None:
    from wowperf.adapters.config.toml import DEFAULT_RESURRECTIONS_PATH, load_self_resurrections

    spells = load_self_resurrections(DEFAULT_RESURRECTIONS_PATH)
    assert spells.ability_ids, "the file lists no spell at all"
    assert len(set(spells.ability_ids)) == len(spells.ability_ids)
```

- [ ] **Step 2: Run them to see them fail.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis/test_recap_return.py tests/adapters/config/test_toml.py -q
```

Expected: ImportError on `return_of` / `SelfResurrections`.

- [ ] **Step 3: The model and the function.** In `season.py`, after `Consumables`:

```python
class SelfResurrections(Frozen):
    """Spells a dead player casts to bring themselves back.

    A player who returns without a resurrect event either released or cast one
    of these; the list is what tells the two apart. Empty when the log itself
    records a self-resurrection as a resurrect event, in which case nothing
    here is consulted.
    """

    ability_ids: tuple[int, ...] = ()
```

Append to `recap.py` (import `Resurrection` from events and `SelfResurrections` from season):

```python
RESURRECTED = "resurrected"
SELF_RESURRECTED = "self_resurrected"
RELEASED = "released"
ABSENT = "absent"


class Return(Frozen):
    """How and when the player came back, before formatting.

    `seconds_after` is from the death to the resurrection, or for a release to
    the player's first action against another actor — the anchor the death
    cost already uses, so the two figures agree by construction.
    """

    kind: str
    seconds_after: float | None = None
    caster_id: int | None = None
    ability_name: str = ""


def return_of(loaded: LoadedRun, death: Death, self_resurrections: SelfResurrections) -> Return:
    """Exactly one of four outcomes, in this precedence.

    A resurrect event targeting the player after the death and before their
    first action names how they came back: by a teammate, or by themselves
    when the caster is the player. Failing that, a cast of a listed
    self-resurrection spell in the same window is a self-resurrection. Failing
    that, a first action means they released, and no action at all means the
    log never saw them act again. A resurrection after the first action is a
    later death's and is ignored.
    """
    death_ms = death.timestamp_ms
    back_by = (
        death_ms + death.seconds_until_next_action * 1000
        if death.seconds_until_next_action is not None
        else None
    )

    def in_window(timestamp_ms: int) -> bool:
        return timestamp_ms > death_ms and (back_by is None or timestamp_ms <= back_by)

    revivals = sorted(
        (
            revival
            for revival in loaded.resurrections
            if revival.actor_id == death.actor_id and in_window(revival.timestamp_ms)
        ),
        key=lambda revival: revival.timestamp_ms,
    )
    if revivals:
        first = revivals[0]
        return Return(
            kind=SELF_RESURRECTED if first.caster_id == death.actor_id else RESURRECTED,
            seconds_after=(first.timestamp_ms - death_ms) / 1000,
            caster_id=first.caster_id,
            ability_name=first.ability_name,
        )
    own_spells = sorted(
        (
            cast
            for cast in loaded.casts
            if cast.actor_id == death.actor_id
            and cast.ability_id in self_resurrections.ability_ids
            and in_window(cast.timestamp_ms)
        ),
        key=lambda cast: cast.timestamp_ms,
    )
    if own_spells:
        return Return(
            kind=SELF_RESURRECTED,
            seconds_after=(own_spells[0].timestamp_ms - death_ms) / 1000,
            caster_id=death.actor_id,
            ability_name=own_spells[0].ability_name,
        )
    if death.seconds_until_next_action is not None:
        return Return(kind=RELEASED, seconds_after=death.seconds_until_next_action)
    return Return(kind=ABSENT)
```

- [ ] **Step 4 (conditional): The loader.** In `toml.py`, add `DEFAULT_RESURRECTIONS_PATH = DATA_DIR / "resurrections.toml"` and:

```python
def load_self_resurrections(path: Path = DEFAULT_RESURRECTIONS_PATH) -> SelfResurrections:
    """Read the short list of spells a dead player casts to bring themselves back."""
    raw = _read(path)
    ids = raw.get("ability_ids") or []
    assert isinstance(ids, list)
    return SelfResurrections(ability_ids=tuple(int(item) for item in ids))
```

- [ ] **Step 5 (conditional): The data file.** Create `data/resurrections.toml`. **Look up each id the way the other data files describe, on the day you write it; do not write one from memory.** The spells to list by name: Reincarnation (Shaman), and the resurrection a Soulstone grants its bearer. If either name resolves to more than one live spell, record the one a player casts on themselves after dying, and note the other in a comment.

```toml
# ABOUTME: Spells a dead player casts to bring themselves back to life.
# ABOUTME: Read by the death recap to tell a self-resurrection from a release.
#
# A player who comes back with no resurrect event in the log either released and
# ran back, or cast one of these. The list is short and maintained by hand: no API
# exposes it. Every id was read from the game's own spell data on the date below,
# one spell at a time, and the name returned had to match the spell intended.
verified = "<date>"

ability_ids = [
  <verified id>,  # Reincarnation
  <verified id>,  # <the Soulstone self-resurrection's name as the spell data gives it>
]
```

- [ ] **Step 6: Run the gate.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

Expected: all pass.

- [ ] **Step 7: Commit.**

```bash
/cmd/git.exe add src/wowperf/domain/analysis/recap.py src/wowperf/domain/season.py tests/domain/analysis/test_recap_return.py
```

plus `src/wowperf/adapters/config/toml.py data/resurrections.toml tests/adapters/config/test_toml.py` when Steps 4 and 5 ran. Subject: `Say how a dead player came back, and tell a self-resurrection from a release`. Body: the precedence and why a resurrection after the first action is ignored; which mechanism Task 1's measurement chose and why.

---

### Task 9: The view model, the builder, the template and the golden

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`DamageRow` → `RecapRow`; add `AvailabilityRow`, `AvailabilityGroup`; `DeathCard`; `Provenance.methods`)
- Modify: `src/wowperf/domain/report/build.py` (`build_deaths`, `build_report`, `CONSUMABLE_CAVEAT` neighbours)
- Modify: `src/wowperf/adapters/render/report.html.j2` (the death card inside `<section id="tab-deaths">`; the stylesheet; one provenance loop)
- Modify: `src/wowperf/cli.py` (`analyze`: load and pass externals and self-resurrections)
- Modify: `tests/e2e/test_report_e2e.py` (pass the two new values; assert a recap on a real death)
- Regenerate: `tests/adapters/render/golden/minimal.html`
- Test: `tests/domain/report/test_build_deaths.py`, `tests/domain/report/test_model.py`, `tests/adapters/render/test_html_invariants.py` (`NUMBERS_THAT_ARE_NOT_TOTALS`), `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Consumes: Tasks 6 to 8; `display_names(run) -> dict[int, str]` from `wowperf.domain.analysis.players`; `badge_for`; `_run_start_ms`.
- Produces: the view model of spec §5, with `Provenance.methods: tuple[str, ...] = ()`; `build_deaths(loaded, defensives, consumables, externals=Externals(), self_resurrections=SelfResurrections()) -> tuple[DeathCard, ...]`; `build_report(..., defensives, consumables, externals=Externals(), self_resurrections=SelfResurrections())`. Both new parameters are keyword-with-default so the dozens of existing `build_report` call sites in tests stay valid; the CLI and the e2e test pass them explicitly.

This task is one commit on purpose. The template renders the old card's fields, so a view model change without the template change makes the golden fail; splitting them would leave the gate red in between. Model, builder, template, stylesheet and golden move together, and the golden's diff is read in full before the commit.

- [ ] **Step 1: Write the failing model tests.** In `tests/domain/report/test_model.py`, replace `test_a_death_card_can_carry_no_damage_rows` with:

```python
def test_a_death_card_can_carry_no_timeline_and_no_availability() -> None:
    card = DeathCard(player="Dudesons", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar")
    assert (card.timeline, card.availability, card.came_back) == ((), (), "")


def test_a_recap_row_and_an_availability_row_are_closed_vocabularies_plus_strings() -> None:
    row = RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                   detail="82,410 to health", health="61%", health_percent=61)
    state = AvailabilityRow(ability="Ironbark", owner="Leafy", state="cooldown",
                            detail="at most 14 s left")
    assert row.health_percent == 61 and state.owner == "Leafy"
```

(import `AvailabilityRow, RecapRow`.) In `tests/adapters/render/test_html_invariants.py`, add to `NUMBERS_THAT_ARE_NOT_TOTALS`:

```python
    (RecapRow, "health_percent"),  # a share of the player's own health, not a duration
```

and import `RecapRow`.

- [ ] **Step 2: Write the failing builder tests.** Rewrite `tests/domain/report/test_build_deaths.py`. Keep every test that asserts on `player`, `class_name`, `killing_blow`, `when`, ordering, disambiguation and the roster gate; rewrite every test that reads `last_ten_seconds`, `defensives_checked`, `defensives_available`, `defensives_badge`, `consumables_checked`, `consumables_available`, `consumables_badge` or `consumables_caveat` to read the new fields, pinning the same behaviour. Add these, with the file's existing helpers (`a_player`, `a_death`, `a_hit`, `a_loaded_with`) extended so `a_hit` also sets `health_damage=amount`:

```python
from wowperf.domain.events import HealingEvent, HealthSample, Resurrection
from wowperf.domain.season import ExternalAbility, Externals, SelfResurrections

NO_EXTERNALS = Externals()
IRONBARK = ExternalAbility(ability_id=102342, name="Ironbark", cooldown_seconds=90.0)


def test_the_timeline_rows_are_formatted_and_carry_their_kind() -> None:
    hits = (a_hit(1, 54_200, "Snowdrift", 82_410),)
    loaded = a_loaded_with((a_death(1, 60_000),), hits).model_copy(update={
        "health_samples": (HealthSample(actor_id=1, timestamp_ms=50_000, hit_points=100_000,
                                        max_hit_points=100_000),),
        "healing": (HealingEvent(actor_id=1, source_id=1, ability_id=7, ability_name="Death Strike",
                                 amount=9_100, timestamp_ms=55_000),),
    })
    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert [(r.seconds_before, r.kind, r.ability, r.detail, r.health) for r in card.timeline] == [
        ("5.8 s", "hit", "Snowdrift", "82,410 to health", "18%"),
        ("5.0 s", "heal", "Death Strike", "+9,100 from Dudesons", "27%"),
    ]
    assert card.health_badge is not None and card.health_badge.label == "derived"
    assert card.health_note == ""


def test_a_hit_that_a_shield_partly_soaked_says_so() -> None:
    hit = a_hit(1, 55_000, "Snowdrift", 10_000).model_copy(update={"absorbed": 4_000})
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), (hit,)), NO_DEFENSIVES,
                        NO_CONSUMABLES)[0]
    assert card.timeline[0].detail == "10,000 to health, 4,000 absorbed"


def test_an_absorb_row_names_the_shield_and_what_it_soaked() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(update={
        "healing": (HealingEvent(actor_id=1, source_id=2, ability_id=17,
                                 ability_name="Power Word: Shield", amount=12_000,
                                 timestamp_ms=55_000, absorbed=True),),
    })
    row = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0].timeline[0]
    assert (row.kind, row.ability, row.detail) == ("absorb", "Power Word: Shield", "12,000 soaked")


def test_without_a_health_reading_the_column_is_empty_and_the_card_says_why() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), (a_hit(1, 55_000, "x", 1),)),
                        NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.timeline[0].health == "" and card.timeline[0].health_percent is None
    assert card.health_badge is None
    assert "no health reading" in card.health_note


def test_the_availability_groups_come_in_order_with_their_badges_and_notes() -> None:
    dude, tree = a_player(), Player(actor_id=2, name="Leafy", class_name="Druid",
                                    spec="Restoration", item_level=680)
    loaded = LoadedRun(
        run=a_run(players=(dude, tree), pulls=(a_pull(0, 0, 120_000),)),
        deaths=(a_death(1, 200_000),),
        casts=(CastEvent(actor_id=2, ability_id=102342, ability_name="Ironbark",
                         timestamp_ms=150_000, target_id=3),),
    )
    defensives = Defensives(entries=(("DeathKnight/Blood", (
        DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=120.0),
    )),))
    consumables = Consumables(categories=(
        ConsumableCategory(name="healthstone", cooldown_seconds=60.0, ability_ids=(6262,)),
    ))
    card = build_deaths(loaded, defensives, consumables,
                        externals=Externals(entries=(("Druid/Restoration", (IRONBARK,)),)))[0]
    own, drinks, mates = card.availability
    assert [g.title for g in card.availability] == ["Defensives", "Consumables",
                                                    "Teammates' externals"]
    assert [(r.ability, r.state, r.detail) for r in own.rows] == [
        ("Icebound Fortitude", "unseen", "not seen this run")
    ]
    assert [(r.ability, r.state, r.detail) for r in drinks.rows] == [("healthstone", "ready", "")]
    assert drinks.note == CONSUMABLE_CAVEAT
    assert [(r.ability, r.owner, r.state, r.detail) for r in mates.rows] == [
        ("Ironbark", "Leafy", "cooldown", "at most 40 s left")
    ]
    assert all(g.badge is not None and g.badge.label == "inferred" for g in card.availability)


def test_a_spec_no_file_covers_gets_a_note_and_no_badge_rather_than_an_empty_list() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()), NO_DEFENSIVES,
                        NO_CONSUMABLES)[0]
    own, drinks, mates = card.availability
    assert own.rows == () and own.badge is None and "DeathKnight Blood" in own.note
    assert drinks.rows == () and drinks.badge is None
    assert mates.rows == () and mates.badge is None and "No teammate" in mates.note


def test_a_pressed_row_and_a_ready_for_row_carry_one_decimal() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(update={
        "casts": (CastEvent(actor_id=1, ability_id=48792, ability_name="IBF", timestamp_ms=56_600),
                  CastEvent(actor_id=1, ability_id=194679, ability_name="Rune Tap",
                            timestamp_ms=60_000 - 29_000)),
    })
    defensives = Defensives(entries=(("DeathKnight/Blood", (
        DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=120.0),
        DefensiveAbility(ability_id=194679, name="Rune Tap", cooldown_seconds=25.0),
    )),))
    own = build_deaths(loaded, defensives, NO_CONSUMABLES)[0].availability[0]
    assert [(r.state, r.detail) for r in own.rows] == [
        ("pressed", "3.4 s before death"), ("ready", "for at least 4.0 s")
    ]


def test_the_return_line_is_worded_per_outcome_and_badged() -> None:
    dude, thrall = a_player(), Player(actor_id=3, name="Thrall", class_name="DeathKnight",
                                      spec="Unholy", item_level=680)
    base = LoadedRun(run=a_run(players=(dude, thrall), pulls=(a_pull(0, 0, 120_000),)))
    raised = base.model_copy(update={
        "deaths": (a_death(1, 60_000).model_copy(update={"seconds_until_next_action": 12.0}),),
        "resurrections": (Resurrection(actor_id=1, caster_id=3, ability_id=61999,
                                       ability_name="Raise Ally", timestamp_ms=68_000),),
    })
    released = base.model_copy(update={
        "deaths": (a_death(1, 60_000).model_copy(update={"seconds_until_next_action": 34.2}),),
    })
    gone = base.model_copy(update={"deaths": (a_death(1, 60_000),)})
    cards = [build_deaths(l, NO_DEFENSIVES, NO_CONSUMABLES)[0] for l in (raised, released, gone)]
    assert [(c.came_back, c.came_back_badge.label) for c in cards] == [  # type: ignore[union-attr]
        ("Resurrected by Thrall with Raise Ally, 8.0 s after death.", "measured"),
        ("Released; first action against an enemy 34.2 s after death.", "derived"),
        ("Not seen acting again this run.", "measured"),
    ]


def test_the_provenance_states_the_health_method_only_when_a_card_has_a_health_column() -> None:
    with_reading = a_loaded_with((a_death(1, 60_000),), (a_hit(1, 55_000, "x", 1),)).model_copy(
        update={"health_samples": (HealthSample(actor_id=1, timestamp_ms=1, hit_points=1,
                                                max_hit_points=1),)})
    report = build_report(with_reading, (), None, None, a_player(), None, FETCHED,
                          NO_DEFENSIVES, NO_CONSUMABLES)
    assert any("reconstructed" in line for line in report.provenance.methods)
    bare = build_report(a_loaded_with((), ()), (), None, None, a_player(), None, FETCHED,
                        NO_DEFENSIVES, NO_CONSUMABLES)
    assert bare.provenance.methods == ()
```

Add the imports these need (`CastEvent`, `ConsumableCategory`, `Consumables`, `DefensiveAbility`, `Defensives`, `LoadedRun`, `Player`, `a_pull`, `a_run`, `FETCHED`, `CONSUMABLE_CAVEAT` from `wowperf.domain.report.build`).

In `tests/adapters/render/test_html_sections.py`, rewrite `test_a_death_card_shows_the_run_up` as:

```python
def test_a_death_card_renders_its_recap() -> None:
    card = DeathCard(
        player="Dudesons",
        class_name="DeathKnight",
        when="12:04, pull 5",
        killing_blow="Frigid Roar",
        timeline=(
            RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                     detail="82,410 to health", health="61%", health_percent=61),
        ),
        health_badge=Badge(label="derived", tint="badge-derived"),
        came_back="Released; first action against an enemy 34.2 s after death.",
        came_back_badge=Badge(label="derived", tint="badge-derived"),
        availability=(
            AvailabilityGroup(title="Defensives", rows=(
                AvailabilityRow(ability="Icebound Fortitude", state="cooldown",
                                detail="at most 14 s left"),
            ), badge=Badge(label="inferred", tint="badge-inferred")),
            AvailabilityGroup(title="Consumables", note="nothing judged"),
            AvailabilityGroup(title="Teammates' externals", rows=(
                AvailabilityRow(ability="Ironbark", owner="Leafy", state="ready"),
            ), badge=Badge(label="inferred", tint="badge-inferred")),
        ),
    )
    # Escaped on comparison: real ability names commonly carry an apostrophe
    # (e.g. "Nature's Wrath"), which autoescape would transform.
    html = render(a_report(deaths=(card,)))
    deaths = html[html.index('<h2 id="deaths">'):html.index('<h2 id="interrupts">')]
    assert str(escape("Frigid Roar")) in deaths
    assert '<tr class="hit">' in deaths and str(escape("Snowdrift")) in deaths
    assert 'style="width: 61%"' in deaths and "61%" in deaths
    assert "34.2 s after death" in deaths
    assert '<li class="cooldown">' in deaths and "at most 14 s left" in deaths
    assert "Leafy" in deaths and "nothing judged" in deaths
    assert deaths.count('href="#provenance"') >= 4  # health, return, two groups
```

(import `AvailabilityGroup, AvailabilityRow, Badge, RecapRow`; drop `DamageRow`.) Add one more test there:

```python
def test_the_provenance_lists_the_methods_the_builder_named() -> None:
    from wowperf.domain.report.model import Provenance

    report = a_report()
    provenance = report.provenance.model_copy(update={"methods": ("Health is reconstructed.",)})
    html = render(report.model_copy(update={"provenance": provenance}))
    assert "Health is reconstructed." in html[html.index('<h2 id="provenance">'):]
```

(`a_report` takes field overrides, so `a_report(provenance=...)` also works.)

- [ ] **Step 3: Run them to see them fail.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report tests/adapters/render -q
```

Expected: ImportError on `RecapRow`, then `ValidationError`s on `DeathCard`.

- [ ] **Step 4: The view model.** In `model.py`, replace `DamageRow` and `DeathCard` with:

```python
class RecapRow(Frozen):
    """One event of a death's last seconds, formatted.

    `kind` is one of "hit", "absorb", "heal", "cast": a row class the template
    maps to colour and to nothing else. `health` is the reconstructed health
    after the event as "62%", or "" before the first reading; `health_percent`
    is the same figure as a number, so the template can draw a bar without
    computing one. A share of the player's own health, never a duration.
    """

    seconds_before: str
    kind: str
    ability: str
    detail: str = ""
    health: str = ""
    health_percent: int | None = None


class AvailabilityRow(Frozen):
    """One saving tool at the death. `state` is "pressed", "ready", "cooldown" or "unseen"."""

    ability: str
    state: str
    owner: str = ""
    detail: str = ""


class AvailabilityGroup(Frozen):
    """One of the three availability groups: own defensives, consumables, teammates' externals.

    A group with rows carries the inferred badge. A group with none and a
    `note` is a group the tool could say nothing about — a spec absent from a
    file — which is not the same as a checked group that found nothing: that
    one has rows in the ready state. Rendering both as blank would merge them.
    """

    title: str
    rows: tuple[AvailabilityRow, ...] = ()
    badge: Badge | None = None
    note: str = ""


class DeathCard(Frozen):
    """One death as a recap: what killed the player, what was up, how they came back.

    Every string is formatted by the builder. `health_badge` is None when no
    row carries health and `health_note` then says why. `came_back` is one of
    the four return lines and always carries its badge.
    """

    player: str
    class_name: str
    when: str
    killing_blow: str
    timeline: tuple[RecapRow, ...] = ()
    health_badge: Badge | None = None
    health_note: str = ""
    came_back: str = ""
    came_back_badge: Badge | None = None
    availability: tuple[AvailabilityGroup, ...] = ()
```

Add to `Provenance`:

```python
    # Methods the page relied on that a reader might dispute, stated once here
    # rather than on every card: today, how a death card's health column is built.
    methods: tuple[str, ...] = ()
```

- [ ] **Step 5: The builder.** In `build.py`, replace the imports of `DamageRow`/`defensives_up_at`/`consumables_up_at` with the recap module and the new view types, and replace `build_deaths` wholesale:

```python
from wowperf.domain.analysis.recap import (
    ABSENT,
    ABSORB,
    CAST,
    COOLDOWN,
    HEAL,
    HIT,
    PRESSED,
    READY,
    RELEASED,
    RESURRECTED,
    SELF_RESURRECTED,
    UNSEEN,
    AbilityState,
    RecapEvent,
    availability_at,
    recap_timeline,
    return_of,
)
from wowperf.domain.report.model import AvailabilityGroup, AvailabilityRow, RecapRow
from wowperf.domain.season import Consumables, Defensives, Externals, SelfResurrections

HEALTH_METHOD = (
    "Health on a death card is reconstructed: the log states a player's health only on their "
    "own casts, so between readings each hit is subtracted and each heal added, and the next "
    "reading replaces the running value. The column is badged derived for that reason."
)

NO_HEALTH_READING = (
    "The log carries no health reading for this player before the death, so the health "
    "column is empty."
)

NO_TEAMMATE_EXTERNALS = "No teammate's specialisation has externals listed."


def _recap_row(event: RecapEvent, death: Death, names: dict[int, str]) -> RecapRow:
    if event.kind == HIT:
        detail = f"{event.amount:,} to health"
        if event.absorbed:
            detail += f", {event.absorbed:,} absorbed"
    elif event.kind == ABSORB:
        detail = f"{event.amount:,} soaked"
    elif event.kind == HEAL:
        healer = names.get(event.source_id or -1, "an unknown source")
        detail = f"+{event.amount:,} from {healer}"
    else:
        detail = ""
    return RecapRow(
        seconds_before=f"{(death.timestamp_ms - event.timestamp_ms) / 1000:.1f} s",
        kind=event.kind,
        ability=event.ability_name,
        detail=detail,
        health="" if event.health_percent is None else f"{event.health_percent}%",
        health_percent=event.health_percent,
    )


def _availability_row(state: AbilityState, names: dict[int, str]) -> AvailabilityRow:
    if state.state == PRESSED:
        detail = f"{state.seconds:.1f} s before death"
    elif state.state == COOLDOWN:
        detail = f"at most {state.seconds:.0f} s left"
    elif state.state == READY and state.seconds is not None:
        detail = f"for at least {state.seconds:.1f} s"
    elif state.state == UNSEEN:
        detail = "not seen this run"
    else:
        detail = ""
    return AvailabilityRow(
        ability=state.name,
        state=state.state,
        owner=names.get(state.owner_id, "") if state.owner_id is not None else "",
        detail=detail,
    )


def _group(
    title: str, states: tuple[AbilityState, ...] | None, names: dict[int, str], note: str
) -> AvailabilityGroup:
    """A group with rows carries the badge; a group with nothing to say carries the note."""
    if not states:
        return AvailabilityGroup(title=title, note=note)
    return AvailabilityGroup(
        title=title,
        rows=tuple(_availability_row(state, names) for state in states),
        badge=badge_for(Confidence.INFERRED),
        note=note if title == "Consumables" else "",
    )


def _came_back(loaded: LoadedRun, death: Death, self_resurrections: SelfResurrections,
               names: dict[int, str]) -> tuple[str, Badge]:
    back = return_of(loaded, death, self_resurrections)
    if back.kind == RESURRECTED:
        caster = names.get(back.caster_id or -1, "a teammate")
        return (
            f"Resurrected by {caster} with {back.ability_name}, "
            f"{back.seconds_after:.1f} s after death.",
            badge_for(Confidence.MEASURED),
        )
    if back.kind == SELF_RESURRECTED:
        return (
            f"Self-resurrected with {back.ability_name}, {back.seconds_after:.1f} s after death.",
            badge_for(Confidence.MEASURED),
        )
    if back.kind == RELEASED:
        return (
            f"Released; first action against an enemy {back.seconds_after:.1f} s after death.",
            badge_for(Confidence.DERIVED),
        )
    assert back.kind == ABSENT
    return ("Not seen acting again this run.", badge_for(Confidence.MEASURED))


def build_deaths(
    loaded: LoadedRun,
    defensives: Defensives,
    consumables: Consumables,
    externals: Externals = Externals(),
    self_resurrections: SelfResurrections = SelfResurrections(),
) -> tuple[DeathCard, ...]:
    """One recap per death, oldest first.

    Built from events rather than findings: no finding carries the run-up,
    the health readings or the return, which is the reason this section
    exists at all. The same run-up window decides the timeline and the
    availability, so the card shows the damage and the answers side by side.
    """
    players_by_id = {player.actor_id: player for player in loaded.run.players}
    names = display_names(loaded.run)
    cards = []
    for death in sorted(loaded.deaths, key=lambda d: d.timestamp_ms):
        player = players_by_id.get(death.actor_id)
        timeline = tuple(
            _recap_row(event, death, names) for event in recap_timeline(loaded, death)
        )
        has_health = any(row.health_percent is not None for row in timeline)
        at = availability_at(
            loaded, death, defensives, consumables, externals,
            visible_from_ms=_run_start_ms(loaded.run),
        )
        spec = f"{player.class_name} {player.spec}" if player else "this player"
        came_back, came_back_badge = _came_back(loaded, death, self_resurrections, names)
        cards.append(
            DeathCard(
                # Falls back to the raw event name only for an actor id that is not
                # on the roster at all, which `display_names` cannot disambiguate.
                player=names.get(death.actor_id, death.player_name),
                class_name=player.class_name if player else "unknown class",
                when=_when(death, loaded.run),
                killing_blow=death.killing_blow,
                timeline=timeline,
                # Every other fact on this card is read straight from the log.
                # The health column is reconstructed, and says so in the same
                # words the ledger uses.
                health_badge=badge_for(Confidence.DERIVED) if has_health else None,
                health_note="" if has_health or not timeline else NO_HEALTH_READING,
                came_back=came_back,
                came_back_badge=came_back_badge,
                availability=(
                    _group("Defensives", at.own, names, f"No data file covers {spec}."),
                    _group("Consumables", at.consumables, names, CONSUMABLE_CAVEAT),
                    _group("Teammates' externals", at.externals, names, NO_TEAMMATE_EXTERNALS),
                ),
            )
        )
    return tuple(cards)
```

Keep `CONSUMABLE_CAVEAT` and its docstring where they are. Remove the now-unused imports of `defensives_up_at`, `consumables_up_at` and `DamageRow` (orphans of this change; `RUN_UP_SECONDS` is no longer read here either — check with ruff). In `build_report`, add the two keyword parameters after `consumables` and thread them:

```python
    externals: Externals = Externals(),
    self_resurrections: SelfResurrections = SelfResurrections(),
) -> Report:
```

```python
    deaths = build_deaths(loaded, defensives, consumables, externals, self_resurrections)
    methods = (HEALTH_METHOD,) if any(card.health_badge for card in deaths) else ()
```

and use `deaths=deaths` and `methods=methods` in the `Report(...)`/`Provenance(...)` construction. Extend the docstring's last sentence: "`externals` and `self_resurrections` are data files too, loaded by the same adapter; they default to empty so a caller without them still builds every other section."

- [ ] **Step 6: The CLI and the e2e test.** In `cli.py`, import `load_externals` and (if Task 8 built it) `load_self_resurrections`, and in `analyze` pass `externals=load_externals(), self_resurrections=load_self_resurrections()` to `build_report`. Mirror that in `tests/e2e/test_report_e2e.py`'s `build_report` call, and add after `html = render(report)`:

```python
    # Every death on a real run renders a recap: a timeline, three availability
    # groups, and one return line with its badge.
    for card in report.deaths:
        assert card.timeline, f"{card.player}: no timeline"
        assert [group.title for group in card.availability] == [
            "Defensives", "Consumables", "Teammates' externals"
        ]
        assert card.came_back and card.came_back_badge is not None
```

- [ ] **Step 7: The template.** In `report.html.j2`, inside `<section ... id="tab-deaths">`, replace the card body — everything from `<p class="detail">{{ death.class_name }}</p>` through the closing `</table>{% endif %}` of the run-up — with:

```jinja
  <p class="detail">{{ death.class_name }}</p>
  <div class="recap">
    <div class="recap-timeline">
      {% if death.timeline %}
      <table class="timeline">
        <thead><tr><th>Before</th><th>Event</th><th>Detail</th><th>Health</th></tr></thead>
        <tbody>
        {% for row in death.timeline %}
        <tr class="{{ row.kind }}">
          <td>{{ row.seconds_before }}</td>
          <td>{{ row.ability }}</td>
          <td>{{ row.detail }}</td>
          <td class="hp">
            {%- if row.health_percent is not none %}<span class="hp-bar" style="width: {{ row.health_percent }}%"></span>{% endif -%}
            {{ row.health }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}
      <p class="sub">No event in the last seconds.</p>
      {% endif %}
      {% if death.health_badge %}
      <p class="nests">Health after each event
        <a class="badge {{ death.health_badge.tint }}" href="#provenance">{{ death.health_badge.label }}</a></p>
      {% endif %}
      {% if death.health_note %}
      <p class="nests">{{ death.health_note }}</p>
      {% endif %}
      {% if death.came_back %}
      <p class="detail">{{ death.came_back }}
        {%- if death.came_back_badge %} <a class="badge {{ death.came_back_badge.tint }}"
           href="#provenance">{{ death.came_back_badge.label }}</a>{% endif %}</p>
      {% endif %}
    </div>
    <div class="recap-availability">
      {% for group in death.availability %}
      <div class="avail">
        <p class="avail-title">{{ group.title }}
          {%- if group.badge %} <a class="badge {{ group.badge.tint }}"
             href="#provenance">{{ group.badge.label }}</a>{% endif %}</p>
        {% if group.rows %}
        <ul>
          {% for row in group.rows %}
          <li class="{{ row.state }}">
            <span class="avail-name">{{ row.ability }}
              {%- if row.owner %} <span class="owner">{{ row.owner }}</span>{% endif %}</span>
            <span class="avail-detail">{{ row.detail }}</span>
          </li>
          {% endfor %}
        </ul>
        {% endif %}
        {% if group.note %}
        <p class="nests">{{ group.note }}</p>
        {% endif %}
      </div>
      {% endfor %}
    </div>
  </div>
```

In the provenance panel, after the `withheld` loop, add:

```jinja
{% for line in report.provenance.methods %}
<p class="sub">{{ line }}</p>
{% endfor %}
```

The template still decides nothing: `row.kind` and `row.state` become class names and nothing else; every visible word came from the builder.

- [ ] **Step 8: The stylesheet.** In the `<style>` block, add `--hit: #e07a7a;` to `:root`, replace the three `.runup` rules (orphaned by this change) with:

```css
.recap { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 14px;
  margin: 8px 0 0; }
@media (max-width: 640px) { .recap { grid-template-columns: 1fr; } }
.timeline { width: 100%; border-collapse: collapse; font-size: 13px; }
.timeline th { text-align: left; color: var(--ink-faint); font-weight: 500;
  padding: 0 8px 3px 0; }
.timeline td { padding: 3px 8px 3px 0; border-top: 1px solid var(--line); color: var(--ink-dim);
  vertical-align: top; }
.timeline tr.hit td:nth-child(2) { color: var(--hit); }
.timeline tr.absorb td:nth-child(2) { color: var(--ours); }
.timeline tr.heal td:nth-child(2) { color: var(--badge-measured); }
.timeline tr.cast td { color: var(--ink-faint); }
.hp { position: relative; width: 84px; text-align: right; font-variant-numeric: tabular-nums; }
.hp-bar { position: absolute; left: 0; bottom: 4px; height: 3px; background: var(--badge-measured); }
.avail-title { font-size: 13px; color: var(--ink-dim); margin: 0 0 4px; }
.avail ul { list-style: none; margin: 0 0 10px; padding: 0; font-size: 13px; }
.avail li { display: flex; justify-content: space-between; gap: 8px; padding: 2px 0;
  border-top: 1px solid var(--line); }
.avail li.pressed .avail-detail { color: var(--badge-measured); }
.avail li.cooldown .avail-detail { color: var(--extra); }
.avail li.unseen { color: var(--ink-faint); }
.owner { color: var(--ink-faint); font-size: 12px; }
```

- [ ] **Step 9: Regenerate the golden and read its diff in full.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py --golden-update -q
```

```bash
/cmd/git.exe diff tests/adapters/render/golden/minimal.html
```

The diff must show: the run-up table replaced by a `.timeline` table with `tr class="hit"` rows and an empty health cell (the minimal fixture has no health sample), the health note, three availability groups (the fixture passes `NO_DEFENSIVES`/`NO_CONSUMABLES`, so each carries a note and no badge), one return line, and no other change outside the Deaths panel and the stylesheet. Anything else is a defect to fix before committing.

- [ ] **Step 10: Run the gate.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

Expected: all pass, including `test_the_page_hides_nothing_before_the_script_runs`, `test_the_report_carries_no_total_row` and the one-inline-script assertions, which this task must not disturb.

- [ ] **Step 11: Commit.**

```bash
/cmd/git.exe add src/wowperf/domain/report/model.py src/wowperf/domain/report/build.py src/wowperf/adapters/render/report.html.j2 src/wowperf/cli.py tests/domain/report/test_build_deaths.py tests/domain/report/test_model.py tests/adapters/render/test_html_invariants.py tests/adapters/render/test_html_sections.py tests/adapters/render/golden/minimal.html tests/e2e/test_report_e2e.py
```

Subject: `Render each death as a recap: timeline with health, availability groups, and the return`. Body: why the two new parameters default (call-site churn for a value only the deaths read), why the health method sits on provenance, why model, template and golden move in one commit, and what the golden diff showed.

---

### Task 10: Amend the documents the design supersedes, and teach the skills the recap

**Files:**
- Modify: `docs/plans/2026-09-05-mplus-report-design.md` (§4 after the `DeathCard` sketch; §5 row 5)
- Modify: `docs/plans/2026-09-03-mplus-postmortem-design.md` (§5.2 last paragraph; §5.8; §5.9)
- Modify: `docs/plans/2026-09-06-audit-and-improvement-roadmap.md` (the D3 heading and its first paragraph)
- Modify: `docs/plans/2026-09-07-death-recap-design.md` (§4.3, the ready-row refinement Task 7 built)
- Modify: `.claude/skills/mplus-analysis/SKILL.md` (a new section after "The two consumable claims")

**Interfaces:**
- Consumes: spec §8; Task 7's ready-for rule; Task 8's mechanism decision.
- Produces: prose only. The check is `uv run pytest tests/test_skills.py -q` still passing and a read-through of each amendment against the code it describes.

- [ ] **Step 1: Report design §4.** After the `DeathCard` sketch (the block ending `last_ten_seconds: tuple[DamageRow, ...] = ()`), add:

```markdown
*Amended <date>:* `DamageRow` and this `DeathCard` are superseded by the recap card of
`2026-09-07-death-recap-design.md` §5: a `RecapRow` timeline with a reconstructed health column,
three `AvailabilityGroup`s (own defensives, consumables, teammates' externals) of four-state
`AvailabilityRow`s, and one return line with its badge. `Provenance` gains `methods`, the
sentences a reader might dispute, stated once — today the health reconstruction.
```

- [ ] **Step 2: Report design §5.** After the table's amendments, add:

```markdown
*Amended <date>:* row 5 is fed by `loaded.deaths`, `loaded.damage_taken`, `loaded.healing`,
`loaded.health_samples`, `loaded.resurrections`, and the defensives, consumables and externals
data files. See `2026-09-07-death-recap-design.md`.
```

- [ ] **Step 3: Postmortem design §5.2, §5.8, §5.9.** Replace §5.2's closing sentence "How a player came back … is recorded by the death recap in a later phase, not here." with "How a player came back — a `resurrect` event targeting them, a self-resurrection, or a release with no event at all — is recorded on the death card by `2026-09-07-death-recap-design.md` §4.4, using this same anchor for a release." At the end of §5.8 and again at the end of §5.9, add:

```markdown
*Amended <date>:* on the death card the two-state answer becomes four — pressed in the run-up,
ready, on cooldown with an upper bound, not seen this run — and teammates' externals join it, each
with its owner named. The finding keeps its wording. See `2026-09-07-death-recap-design.md` §4.3.
```

- [ ] **Step 4: Roadmap D3.** Change the heading `### D3. The death cost anchor produces impossible numbers — confirmed, cause open` to `### D3. The death cost anchor produces impossible numbers — amended 2026-09-06; the return recorded by Phase I`, and add one sentence at the end of its first paragraph: "The §5.2 amendment of 2026-09-06 re-anchored the cost on the first cast aimed at another actor; Phase I's recap says how each player came back."

- [ ] **Step 5: This design's §4.3.** Under the table, add:

```markdown
*Amended <date>:* a **ready** row whose readiness arrived inside the run-up says for how long,
as a lower bound — "ready, for at least 4 s" — because base cooldowns are longer than talented
ones, so the true moment was no later. Without this, an ability that came off cooldown mid-burst
would read exactly like one ready all along.
```

Also correct §3.3's phrase "every id verified against the API's ability lookup on the dated day" to "every id verified from the game's own spell data on the dated day, the way `data/defensives.toml` was", and record in §3.4 which mechanism Task 1's measurement chose.

- [ ] **Step 6: The mplus-analysis skill.** After the section "Reading either of them", add:

```markdown
## What a death recap can honestly say

Each death card carries a timeline of the last ten seconds, the state of every saving tool, and a
return line. Three of its claims need care.

**The health column is reconstructed**, badged `derived`. The log states a player's health only on
their own casts; between readings each hit is subtracted and each heal added, and the next reading
replaces the running value. Write "was around", never a flat figure, and expect the column to be
empty for a player who never cast in the window.

**A remaining cooldown is an upper bound.** "At most 14 s left" means the base cooldown says so;
a talent or a reset could have made it ready. "Ready, for at least 4 s" is the mirror: a lower
bound. "Not seen this run" is a fact about the log, not about the player — a talent not taken
looks the same. An external marked ready is a fact about a teammate's cooldown; the report draws
no finding from it, and neither should you.

**"Released" is a reading, not an event.** A resurrection is logged; a release is not. The card
says "released" when no resurrection preceded the player's first action against an enemy, and
gives that action as the return time, which is the same anchor the death cost uses. It is badged
`derived` for that reason. "Not seen acting again this run" means exactly that.
```

- [ ] **Step 7: Gate and commit.**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_skills.py -q
```

```bash
/cmd/git.exe add docs/plans/2026-09-05-mplus-report-design.md docs/plans/2026-09-03-mplus-postmortem-design.md docs/plans/2026-09-06-audit-and-improvement-roadmap.md docs/plans/2026-09-07-death-recap-design.md .claude/skills/mplus-analysis/SKILL.md
```

Subject: `Amend the older designs for the death recap and teach the analysis skill to read one`. Body: which sections each amendment supersedes and why the D3 heading was stale.

---

### Task 11: Re-run the real report and check the recap in a browser (orchestrator, needs credentials)

**Files:**
- Read: `out/6Kx1P9GbNXrcLdHa-36.html`, `out/6Kx1P9GbNXrcLdHa-36.findings.json`
- Modify (if a defect is found): whichever task's files, with its tests, as a fix commit on this branch

**Interfaces:**
- Consumes: every task above; the scratchpad loader `run_real_analyze.py` pattern (UTF-16 `.env`, values never printed, a fresh `--cache-dir` inside the worktree).
- Produces: a green real run, a recorded spend, and either a clean browser check or fix commits.

- [ ] **Step 1: Run the analysis.** From the worktree, with the credentials loaded into the subprocess environment and never printed:

```bash
python -m wowperf.cli analyze https://www.warcraftlogs.com/reports/6Kx1P9GbNXrcLdHa?fight=36 --cache-dir cache --out out
```

Expected: `49 findings written …` (or the current count), `report written …`, and the quota sentence on stderr. Record the points spent against Task 1's estimate; if the cold run exceeds it by more than the two scoped queries per death explain, stop and report.

- [ ] **Step 2: Check the cards in the findings and the page.** Write a scratchpad script that parses `out/6Kx1P9GbNXrcLdHa-36.html` and asserts, for each of the four deaths: a `.timeline` table with at least one `tr class="hit"` row; a health cell that is non-empty on at least one row (or the health note present); three `.avail` groups titled Defensives, Consumables, Teammates' externals; a return line matching one of the four wordings; and every badge linking to `#provenance`. Print each card's return line. One of the four deaths was followed by a Raise Ally: its line must read "Resurrected by … with Raise Ally". Print the provenance's methods paragraph.

- [ ] **Step 3: Browser check.** Serve `out/` over localhost in a background Bash (`python -m http.server 8765 --directory out --bind 127.0.0.1`) and open `http://127.0.0.1:8765/6Kx1P9GbNXrcLdHa-36.html#deaths` in a **new** browser-pane tab (the pane loads local files as inert snapshots; see the memory file `browser-pane-serves-snapshots.md`). With the JavaScript tool: the Deaths panel is active; each card's `.recap` has two columns wider than 640px and one below (resize to the mobile preset and confirm `getComputedStyle(...).gridTemplateColumns` has one track); hit rows are tinted, the health bar widths match the percentages, cooldown rows show "at most", the return line is present. Screenshots time out in that pane; use `get_page_text` and the JavaScript tool.

- [ ] **Step 4: Run the e2e tests** with `WOWPERF_E2E_REPORT` set to the report URL:

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -m e2e -q
```

Expected: pass, including the recap assertions Task 9 added to `test_report_e2e.py`.

- [ ] **Step 5: Record.** Add the measured cold spend for the whole run to the wcl-api skill's recap paragraph (one dated sentence). Commit any fix with its test; commit the skill line:

```bash
/cmd/git.exe add .claude/skills/wcl-api/SKILL.md
```

Subject: `Record what a full recap run costs`. Body: the number and the date.

---

## Self-review against the spec

- **§1 timeline first, availability beside:** Task 9's template puts the timeline in the left column and the groups on the right; Task 11 checks the two-column layout.
- **§2 fetched:** Task 4 adds `includeResources` and the two scoped queries; Task 3 keeps `amount`/`absorbed`; Task 1 measures the cost first.
- **§3.1–3.2 records and fields:** Task 2.
- **§3.3 externals:** Task 5, with the three-file exclusivity test.
- **§3.4 self-resurrection mechanism:** Task 1 decides, Task 8 implements both branches, Task 10 records the choice in the design.
- **§4.1 timeline, §4.2 health:** Task 6, including the re-anchor, the cap, the clamp, and the no-reading case.
- **§4.3 four states:** Task 7, with charges, externals on target, consumables never unseen, visibility rule; the ready-for refinement is amended into the design by Task 10.
- **§4.4 return:** Task 8, four outcomes with the precedence and the ignored later resurrection; badges in Task 9.
- **§5 view model:** Task 9, with `health_percent` on the allowlist and `Provenance.methods` added (the spec placed the method "on the provenance tab" without naming a field; this plan names it).
- **§6 template and CSS:** Task 9; the inline script is untouched.
- **§7 testing:** every layer has its tests in Tasks 2–9; the golden is regenerated once, in Task 9; e2e assertions in Task 9, run in Task 11; the spike is Task 1.
- **§8 amendments:** Task 10, plus the skill rows in Tasks 1 and 4.
- **§9 out of scope:** no task adds a finding, ranks damage, or touches the comparison.
- **Placeholder scan:** the `<date>` and `<verified>` markers are instructions to write the day's date and a looked-up id, never a value to copy; no "TBD", no "similar to Task N".
- **Type consistency:** `RecapEvent.kind` uses `HIT/ABSORB/HEAL/CAST`; `RecapRow.kind` carries the same strings; `AbilityState.state` and `AvailabilityRow.state` share `PRESSED/READY/COOLDOWN/UNSEEN`; `Return.kind` uses `RESURRECTED/SELF_RESURRECTED/RELEASED/ABSENT`; `build_deaths` and `build_report` take `externals` and `self_resurrections` in that order in Tasks 9 and 11; `availability_at`'s keyword `visible_from_ms` is passed by name in Tasks 7 and 9.
