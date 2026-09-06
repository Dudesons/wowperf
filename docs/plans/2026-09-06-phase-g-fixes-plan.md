# Phase G: Make the Current Page True — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the eleven defects the 2026-09-06 audit found in the shipped tool, so that every number on the report is one the reader can trust, before any new feature is built on top of it.

**Architecture:** No new layer. Each task changes one analyser, one comparison module, one adapter or one report builder, under the existing ports. Two changes amend the design (pull alignment and the death-cost anchor) and the amendments are already written into the design document, dated 2026-09-06; the rest are corrections to code that drifted from the design or from the game.

**Tech Stack:** Python 3.12+, `uv`, `pydantic` v2, `typer`, `httpx`, `jinja2`, `pytest`, `ruff`, `mypy`.

**Spec:** `docs/plans/2026-09-06-audit-and-improvement-roadmap.md` §2 (the defects, D1–D11) and §4 "Phase G". The design authority is `docs/plans/2026-09-03-mplus-postmortem-design.md`, amended 2026-09-06 in §3.3, §3.5, §3.6, §5.2, §5.5, §5.7, §6.2 and §6.3, and `docs/plans/2026-09-05-mplus-report-design.md` §5, amended the same day. Read the amendments before the task that implements them.

**Depends on:** everything merged on `master` at `069027e`. Read `src/wowperf/domain/analysis/service.py`, `src/wowperf/domain/comparison/service.py`, `src/wowperf/domain/report/build.py` and `src/wowperf/cli.py` before starting any task.

**Withdrawn from scope:** the audit's D4 ("a finished analyser is not wired in") was wrong. `analyse_consumables_never_used` is called from `service.py` and its three findings are in the real report. Nothing to do. The debuff half of the uptime comparison (D11, last bullet) is left for the per-player phase, where the decision to delete it or replace it with the group-wide figure belongs; nothing here touches it.

## Global Constraints

- **Python `>=3.12`.** `uv` is the only toolchain: no pip, no poetry, no hand-managed virtualenv.
- **`uv` is not on PATH.** Every bash command using it begins `export PATH="$HOME/.local/bin:$PATH"`.
- **`src/wowperf/domain/` performs no I/O.** No `httpx`, no file reads, no `tomllib`, no clock. Adapters do that.
- **Every `Finding` carries a `Confidence`** of `measured`, `derived`, or `inferred`, matching how the claim was obtained.
- **A finding with no honest seconds figure sets `seconds_lost=None`, never `0.0`.** Zero sorts above every `None`.
- **The LLM never computes a number.** Every metric comes from tested Python.
- **No hardcoded season data.** No zone, encounter, affix or ability ID as a literal in `src/`. Values with no API source live in `data/*.toml` with a `verified` date.
- **Cache every Warcraft Logs response.** The budget is 3600 points an hour.
- **Never invent a Warcraft Logs field name.** Every field this plan uses is in `.claude/skills/wcl-api/SKILL.md` with a date. The ones new to this plan — `gameData.affixes {id name}`, the absence of `Resurrects`, `targetID` on cast events — were verified 2026-09-06 and are recorded there under "The event stream, probed for a death recap".
- **Never accumulate a corpus of other players' logs.** RPGLogs terms §5d. Task 9 is what makes this true of the cache.
- **English** in code, comments, error strings, and commit messages.
- Commit style: imperative mood, no `feat:` / `fix:` prefix. The subject says what the commit does to the repository; the body explains **why**.
- **Never `--no-verify`, `--no-hooks`, or `--no-pre-commit-hook`.**
- Every file starts with two `# ABOUTME: ` comment lines. Empty `__init__.py` markers are exempt.
- The gate is `uv run pytest`, `uv run ruff check .`, `uv run mypy` (no path argument). Ruff's line length is 100.
- **Comments are evergreen.** No "new", "now", "recently", "fixed" in code comments. Amendment notes with dates belong in the design documents, not in code.
- **Never remove a code comment** unless it is now false. Update it instead.
- **Every existing test that a task breaks is updated by that task**, with the reason in the commit body. No test is deleted; a test that pins behaviour this plan deliberately changes is rewritten to pin the amended behaviour.
- **Git in this worktree.** The session's tool hook refuses a bare `git` inside a worktree, and refuses any command that names git twice. Call the executable by its path, `/cmd/git.exe`, and issue one git invocation per command: `/cmd/git.exe add -A src tests` and then `/cmd/git.exe commit ...` as two separate commands, never joined with `&&`.

## The real run is the acceptance test

Every defect here was found on report `6Kx1P9GbNXrcLdHa` fight 36, whose findings and page live in `out/` of the main checkout (`C:/Users/damien/claude_perso/wow_perf/out/6Kx1P9GbNXrcLdHa-36.findings.json`) and whose raw API responses are cached under `C:/Users/damien/claude_perso/wow_perf/cache/`. Task 11 re-runs the tool against it. Until then, the offline tests are the gate, but where a task says "replay against the cached run", do it: the offline fixtures did not catch any of these eleven defects.

---

### Task 1: Close the documentation drift

**Files:**
- Modify: `.claude/skills/wcl-api/SKILL.md` (add a section before "## Aura tables")
- Modify: `.claude/skills/analyzing-a-run/SKILL.md:11-19`
- Modify: `tests/test_skills.py`

**Interfaces:**
- Consumes: the event field table in `docs/plans/2026-09-04-mplus-analysers-plan.md:34-46`.
- Produces: nothing code-facing.

- [ ] **Step 1: Write the failing test** — every flag `analyze --help` offers is named in the workflow skill.

Add to `tests/test_skills.py`:

```python
def test_every_flag_the_command_offers_is_named_in_the_workflow() -> None:
    # The reverse of the test above. A flag the command has and the workflow never
    # mentions is a feature nobody following the workflow can reach.
    help_text = CliRunner().invoke(app, ["analyze", "--help"]).output
    offered = set(FLAG.findall(help_text)) - {"--help"}
    named = set(FLAG.findall(ANALYZING_SKILL.read_text(encoding="utf-8")))
    missing = sorted(offered - named)
    assert missing == [], f"offered by the command but never named in the skill: {missing}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_skills.py -q`
Expected: FAIL naming at least `--throughput-ceiling`, and probably `--cache-dir`, `--fight`, `--out`.

- [ ] **Step 3: Name every offered flag in `analyzing-a-run/SKILL.md`**

In step 1 of the workflow, after the sentence about `--no-compare`, add:

```markdown
   Add `--throughput-ceiling` only when the person asks how often a burst cooldown was pressed
   against what its cooldown allowed; it is off by default because a route, not a rotation,
   decides how many windows there were (`mplus-analysis`, "Throughput cooldowns ask about
   placement, not rate"). `--fight N` picks one keystone out of a report holding several,
   `--out DIR` moves the two output files, and `--cache-dir DIR` moves the response cache;
   none of the three changes what the report says.
```

- [ ] **Step 4: Run the skill tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_skills.py -q`
Expected: PASS.

- [ ] **Step 5: Carry the event field table into the API skill**

In `.claude/skills/wcl-api/SKILL.md`, immediately before `## The event stream, probed for a death recap`, add this section. The content is the table from `docs/plans/2026-09-04-mplus-analysers-plan.md` lines 34–46, kept verbatim in substance, with its original verification date:

```markdown
## Event streams `ingest.py` reads

Verified 2026-09-04 against report `6Kx1P9GbNXrcLdHa` fight 36 by live query, first recorded in
Plan B's implementation plan and carried here on 2026-09-06 because this file is the authority.
The design's §5.3 prose uses combat-log names (`SPELL_CAST_START`, `extraSpellId`,
`sourceInstanceID`) that do **not** exist in the API; the table below supersedes them.

| Stream | Query arguments | `type` values | Fields |
| --- | --- | --- | --- |
| Player casts | `dataType: Casts, hostilityType: Friendlies` | `begincast`, `cast` | `abilityGameID`, `fight`, `sourceID`, `sourceInstance`, `targetID`, `targetInstance`, `timestamp`, `type` — `targetID` is `-1` for a cast with no target (verified 2026-09-06) |
| Enemy casts | `dataType: Casts, hostilityType: Enemies` | `begincast`, `cast` | `abilityGameID`, `fight`, `sourceID`, `sourceInstance`, `sourceMarker`, `targetID`, `timestamp`, `type` |
| Interrupts | `dataType: Interrupts, hostilityType: Friendlies` | `interrupt`, `applydebuff` | `abilityGameID`, `extraAbilityGameID`, `fight`, `sourceID`, `sourceInstance`, `targetID`, `targetInstance`, `targetMarker`, `timestamp`, `type` |
| Player deaths | `dataType: Deaths` (default hostility) | `death` | `abilityGameID` (always 0), `fight`, `killerID`, `killerInstance`, `killingAbilityGameID`, `sourceID` (always -1), `targetID`, `timestamp`, `type` |
| Enemy deaths | `dataType: Deaths, hostilityType: Enemies` | `death` | `abilityGameID`, `fight`, `killerID`, `killerInstance`, `killingAbilityGameID`, `sourceID`, `targetID`, `targetInstance`, `targetMarker`, `timestamp`, `type` |
| Damage taken | `dataType: DamageTaken, hostilityType: Friendlies` | `damage` | `abilityGameID`, `absorbed`, `amount`, `blocked`, `buffs`, `fight`, `hitType`, `isAoE`, `mitigated`, `sourceID`, `sourceInstance`, `sourceMarker`, `targetID`, `tick`, `timestamp`, `type`, `unmitigatedAmount` |

- `sourceInstance` is absent when the instance is the first one; treat a missing value as `0`
  on both sides of any comparison. Two copies of one NPC are `(sourceID, sourceInstance)`.
- On an `interrupt` event, `abilityGameID` is the kick and `extraAbilityGameID` the spell
  interrupted; `targetID`/`targetInstance` is the enemy, `sourceID` the player.
- On a damage event `amount` excludes what was absorbed — a real row read `amount: 0,
  absorbed: 123570` — so "how hard did this hit" is `unmitigatedAmount`.
- `npcCountMap` keys are strings holding NPC game IDs; the join is enemy death `targetID` →
  `masterData.actors` → `gameID` → `npcCountMap[str(gameID)]`. `masterData.actors` accepts
  `type: "NPC"`, and `ReportActor` carries `gameID, icon, id, name, petOwner, server, subType,
  type`.
```

- [ ] **Step 6: Run the whole gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
/cmd/git.exe add .claude/skills tests/test_skills.py && git commit -m "Name every analyze flag in the workflow and carry the event fields into the API skill" -m "The drift test checked only that named flags exist, so --throughput-ceiling shipped without the workflow ever mentioning it. The event field table lived in a plan file the design says is not maintained, while CLAUDE.md names the skill as the only authority — the drift the skill exists to prevent."
```

---

### Task 2: Format every figure, and stop printing map coordinates

**Files:**
- Modify: `src/wowperf/domain/analysis/interrupts.py:176-180`
- Modify: `src/wowperf/domain/analysis/players.py:213-217`
- Modify: `src/wowperf/domain/analysis/timeline.py:88-92`
- Modify: `src/wowperf/domain/analysis/trash.py:68-73`
- Modify: `src/wowperf/domain/comparison/route.py:76-82`
- Test: `tests/domain/analysis/test_interrupts.py`, `tests/domain/analysis/test_players.py`, `tests/domain/analysis/test_timeline.py`, `tests/domain/analysis/test_trash.py`, `tests/domain/comparison/test_route.py`

**Interfaces:** none change.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/analysis/test_interrupts.py`, find the test that asserts on an `interrupts.ability.*` detail (search for `unmitigated damage`) and add beside it:

```python
def test_the_detail_formats_the_damage_with_thousands_separators() -> None:
    # Build the same casts and damage the neighbouring test builds, with damage large
    # enough to need a separator; reuse that test's helpers.
    findings = analyse_interrupts(casts_with_one_landed_cast(), damage_of(1_234_567))
    ability = next(f for f in findings if f.id.startswith("interrupts.ability."))
    assert "1,234,567 unmitigated damage" in ability.detail
    assert "1234567" not in ability.detail
```

Adapt `casts_with_one_landed_cast()` and `damage_of()` to whatever the file's existing helpers are called — the intent is one landed cast followed by one hit of 1,234,567 within the follow window.

In `tests/domain/analysis/test_players.py`, beside `test_taking_far_more_than_the_median_of_one_ability_is_a_finding`:

```python
def test_the_damage_detail_formats_the_amount_with_thousands_separators() -> None:
    findings = analyse_players(RUN, (), (), (), damage_where_one_player_takes(1_500_000))
    outlier = next(f for f in findings if f.id.startswith("players.damage."))
    assert "1,500,000 unmitigated damage" in outlier.detail
```

Again adapt the helper to the file's fixtures: three players hit by one ability, one of them for 1,500,000 and the others for 1,000.

In `tests/domain/analysis/test_timeline.py`, `tests/domain/analysis/test_trash.py` and `tests/domain/comparison/test_route.py`, add one test each of the same shape:

```python
def test_no_finding_prints_a_map_position() -> None:
    for finding in <call the module's analyser with the file's standard fixture>:
        for line in finding.evidence:
            assert "map position" not in line, finding.id
```

- [ ] **Step 2: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis/test_interrupts.py tests/domain/analysis/test_players.py tests/domain/analysis/test_timeline.py tests/domain/analysis/test_trash.py tests/domain/comparison/test_route.py -q`
Expected: the five new tests FAIL; existing ones that assert the `map position` line also FAIL — note their names.

- [ ] **Step 3: Make the changes**

`interrupts.py` detail: `f"and did {damage:,} unmitigated damage to the group within "`.

`players.py` detail: `f"{amount:,} unmitigated damage from {ability}. This states a difference, "`.

`timeline.py`: evidence becomes `(next_pull.name,)`. `trash.py`: evidence becomes `(pull.name,)`. `route.py` skipped finding: drop the `f"map position x={pull.x}, y={pull.y}"` line, keeping the other three.

The `x`/`y` fields stay on `Pull` and on `Gap`: the timeline SVG and a later phase may use them. Only the evidence strings go.

- [ ] **Step 4: Update the existing tests that pinned the old strings**

Each test named in step 2 is rewritten to assert the pack name is the evidence, and nothing else about position. Keep the test; change the assertion.

- [ ] **Step 5: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass. If the golden file `tests/adapters/render/golden/minimal.html` changed, run `uv run pytest tests/adapters/render -q --golden-update`, read the diff, and confirm the only change is a removed map-position line or a formatted number.

- [ ] **Step 6: Commit**

```bash
/cmd/git.exe add -A src tests && git commit -m "Format every damage figure and drop map coordinates from the evidence" -m "Two details printed raw integers beside evidence lines that were formatted, and three findings printed a map position no reader can use. The report design's §12 asked for the three to lead with the pack name, as the route findings already did."
```

---

### Task 3: Price a skipped pack by the forces its enemies awarded

**Files:**
- Modify: `src/wowperf/domain/analysis/trash.py` (extract `forces_by_pull`)
- Modify: `src/wowperf/domain/comparison/route.py:12-20, 66-82`
- Modify: `src/wowperf/domain/comparison/service.py:64-66`
- Test: `tests/domain/analysis/test_trash.py`, `tests/domain/comparison/test_route.py`, `tests/domain/comparison/test_service.py`

**Interfaces:**
- Produces: `forces_by_pull(enemy_deaths: tuple[EnemyDeath, ...]) -> dict[int, int]` in `trash.py`, mapping pull index to forces awarded by the deaths inside it.
- Changes: `compare_route(ours: Run, theirs: Run, alignment: Alignment, forces: Mapping[int, int]) -> list[Finding]`. Task 4 keeps this signature.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/analysis/test_trash.py`:

```python
from wowperf.domain.analysis.trash import forces_by_pull
from wowperf.domain.events import EnemyDeath


def test_forces_by_pull_sums_every_death_inside_a_pull() -> None:
    deaths = (
        EnemyDeath(game_id=100, actor_id=1, timestamp_ms=1_000, forces=6, pull_index=0),
        EnemyDeath(game_id=100, actor_id=2, timestamp_ms=2_000, forces=6, pull_index=0),
        EnemyDeath(game_id=200, actor_id=3, timestamp_ms=9_000, forces=4, pull_index=1),
        EnemyDeath(game_id=300, actor_id=4, timestamp_ms=9_500, forces=4, pull_index=None),
    )
    assert forces_by_pull(deaths) == {0: 12, 1: 4}
```

In `tests/domain/comparison/test_route.py`, beside `test_a_pack_they_skipped_is_priced_with_our_own_clock`:

```python
def test_a_skipped_pack_is_priced_by_the_forces_its_deaths_awarded() -> None:
    # Two copies of one NPC type died in the skipped pull. Pricing by type would say 6.
    ours = a_run((1,), (2,), (3,))
    theirs = a_run((1,), (3,))
    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {1: 12})
    skipped = next(f for f in findings if f.id == "compare.route.skipped.0")
    assert "12 enemy forces" in skipped.evidence
    assert "It awarded 12 enemy forces." in skipped.detail
```

Every other `compare_route(...)` call in that file gains a fourth argument `{}` (no deaths known), and any assertion on a forces figure that came from `npc_counts` is rewritten to pass the figure in the mapping instead.

- [ ] **Step 2: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis/test_trash.py tests/domain/comparison/test_route.py -q`
Expected: FAIL — `forces_by_pull` does not exist; `compare_route` takes three arguments.

- [ ] **Step 3: Extract and use `forces_by_pull`**

In `trash.py`, above `analyse_trash`:

```python
def forces_by_pull(enemy_deaths: tuple[EnemyDeath, ...]) -> dict[int, int]:
    """Enemy forces each pull actually awarded, summed from the deaths inside its window.

    `Pull.enemies` lists NPC *types*, not individuals — the schema exposes no
    instance count — so pricing a pull by its types under-counts a pack holding
    several copies of one mob. Deaths are the honest unit.
    """
    forces: dict[int, int] = defaultdict(int)
    for death in enemy_deaths:
        if death.pull_index is not None:
            forces[death.pull_index] += death.forces
    return dict(forces)
```

and replace the inline loop in `analyse_trash` (the `forces_by_pull` local) with a call to it.

In `route.py`, delete `_forces` and change the signature and the two uses:

```python
def compare_route(
    ours: Run, theirs: Run, alignment: Alignment, forces: Mapping[int, int]
) -> list[Finding]:
    """What the two routes did differently, priced where we honestly can.

    `forces` is enemy forces per pull index of our run, summed from enemy deaths
    by `analysis.trash.forces_by_pull`, so the route and the trash findings
    price the same pull with the same number.
    """
```

and in the skipped loop `forces_awarded = forces.get(pull.index, 0)`.

In `comparison/service.py`:

```python
from wowperf.domain.analysis.trash import forces_by_pull
...
        findings += compare_route(
            ours.run,
            speed.loaded.run,
            align_pulls(ours.run, speed.loaded.run),
            forces_by_pull(ours.enemy_deaths),
        )
```

- [ ] **Step 4: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
/cmd/git.exe add -A src tests && git commit -m "Price a skipped pack by the forces its enemy deaths awarded" -m "enemyNPCs lists NPC types, and the schema has no instance count (rejected live 2026-09-06), so summing npcCountMap over types priced a real pull at 83 forces while the trash finding on the same page counted 160 from its deaths. One helper now feeds both."
```

---

### Task 4: Align pulls by what they contain, and refuse to price what did not align

**Files:**
- Modify: `src/wowperf/domain/comparison/alignment.py` (replace the matcher; keep the public types)
- Modify: `src/wowperf/domain/comparison/route.py` (summary wording, the gate, `compare.route.unaligned`)
- Modify: `.claude/skills/mplus-analysis/SKILL.md` (one paragraph under "The confounds…")
- Test: `tests/domain/comparison/test_alignment.py`, `tests/domain/comparison/test_route.py`

**Interfaces:**
- Keeps: `align_pulls(ours: Run, theirs: Run) -> Alignment` with `matched`, `only_ours`, `only_theirs`, `out_of_order`. `matched` may now hold several `PullMatch` for one `ours_index` (a merged pull covering several of theirs) or one `theirs_index`.
- Produces: `Alignment.matched_share: float` property — distinct our trash pulls with a counterpart over our trash pulls, `1.0` when we have no trash pulls.
- Produces: `MIN_ALIGNED_SHARE = 0.5` and finding id `compare.route.unaligned` in `route.py`.

Read the amendment in design §6.3 first; it is the specification.

- [ ] **Step 1: Write the failing alignment tests**

Add to `tests/domain/comparison/test_alignment.py` (keep every existing test; some are rewritten in step 4):

```python
def a_boss(index: int, encounter_id: int, game_ids: tuple[int, ...]) -> Pull:
    return a_pull(index, game_ids).model_copy(update={"encounter_id": encounter_id})


def test_a_merged_pull_matches_each_separate_pull_it_covers() -> None:
    # We chain-pulled three packs; Warcraft Logs recorded one pull. They took them one by one.
    alignment = align_pulls(a_run((1, 2, 3, 4, 5)), a_run((1, 2), (3,), (4, 5)))
    assert sorted((m.ours_index, m.theirs_index) for m in alignment.matched) == [
        (0, 0), (0, 1), (0, 2),
    ]
    assert alignment.only_ours == ()
    assert alignment.only_theirs == ()
    assert alignment.matched_share == 1.0


def test_a_small_pull_matches_the_merged_pull_that_contains_it() -> None:
    alignment = align_pulls(a_run((1, 2), (3,)), a_run((1, 2, 3),))
    assert sorted((m.ours_index, m.theirs_index) for m in alignment.matched) == [(0, 0), (1, 0)]
    assert alignment.only_theirs == ()


def test_packs_sharing_no_enemy_type_do_not_match() -> None:
    alignment = align_pulls(a_run((1, 2),), a_run((3, 4),))
    assert alignment.matched == ()
    assert alignment.only_ours == (0,)
    assert alignment.only_theirs == (0,)
    assert alignment.matched_share == 0.0


def test_overlap_without_containment_does_not_match() -> None:
    # {1, 2} and {2, 3} share a type but neither contains the other.
    alignment = align_pulls(a_run((1, 2),), a_run((2, 3),))
    assert alignment.matched == ()


def test_the_candidate_sharing_the_most_types_wins() -> None:
    # Their pull 1 is the closer match for our {1, 2, 3}; their pull 0 is only a subset.
    alignment = align_pulls(a_run((1, 2, 3),), a_run((1,), (1, 2, 3)))
    assert (0, 1) in {(m.ours_index, m.theirs_index) for m in alignment.matched}


def test_bosses_match_by_encounter_id_whatever_adds_were_present() -> None:
    ours = a_run().model_copy(update={"pulls": (a_boss(0, 3207, (9, 10)),)})
    theirs = a_run().model_copy(update={"pulls": (a_boss(0, 3207, (9,)),)})
    alignment = align_pulls(ours, theirs)
    assert [(m.ours_index, m.theirs_index) for m in alignment.matched] == [(0, 0)]


def test_a_boss_never_matches_a_trash_pull_with_the_same_enemies() -> None:
    ours = a_run().model_copy(update={"pulls": (a_boss(0, 3207, (9,)),)})
    alignment = align_pulls(ours, a_run((9,)))
    assert alignment.matched == ()


def test_matched_share_counts_our_trash_pulls_with_a_counterpart() -> None:
    alignment = align_pulls(a_run((1,), (2,), (3,), (4,)), a_run((1,), (2,)))
    assert alignment.matched_share == 0.5


def test_a_run_with_no_trash_pulls_has_a_full_matched_share() -> None:
    ours = a_run().model_copy(update={"pulls": (a_boss(0, 3207, (9,)),)})
    assert align_pulls(ours, ours).matched_share == 1.0


def test_pairs_that_break_the_reference_order_are_out_of_order() -> None:
    alignment = align_pulls(a_run((1,), (2,), (3,)), a_run((2,), (1,), (3,)))
    assert len(alignment.out_of_order) == 1
    assert alignment.only_ours == () and alignment.only_theirs == ()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_alignment.py -q`
Expected: the new tests FAIL (`matched_share` missing; merged pulls unmatched).

- [ ] **Step 3: Replace the matcher**

Rewrite `alignment.py` below the two classes. Keep the `ABOUTME` lines, update the second to "Set containment over enemy game IDs, so a chain-pulled stretch still finds the packs it covers." Add the property to `Alignment`:

```python
class Alignment(Frozen):
    """What two routes had in common, and what each did alone.

    `matched` may pair one of our pulls with several of theirs, or several of
    ours with one of theirs: Warcraft Logs records a chain of packs fought
    without a break as one pull, and the other run may have taken them one at
    a time. A pull with several counterparts is still one matched pull.
    """

    matched: tuple[PullMatch, ...] = ()
    only_ours: tuple[int, ...] = ()
    only_theirs: tuple[int, ...] = ()
    out_of_order: tuple[PullMatch, ...] = ()
    our_trash_count: int = 0

    @property
    def matched_share(self) -> float:
        """Our trash pulls that found a counterpart, as a share of all our trash pulls.

        Bosses are left out: they match by encounter id and would flatter the share.
        A run with no trash pulls aligned everything it had.
        """
        if self.our_trash_count == 0:
            return 1.0
        matched_trash = {match.ours_index for match in self.matched} - self._boss_indices
        return len(matched_trash) / self.our_trash_count
```

`_boss_indices` needs storing too: add `boss_indices: tuple[int, ...] = ()` (our boss pull indices) and use `set(self.boss_indices)` in the property. Then:

```python
def _types(pull: Pull) -> frozenset[int]:
    return frozenset(enemy.game_id for enemy in pull.enemies)


def _covers(a: frozenset[int], b: frozenset[int]) -> bool:
    """One pack's enemy types are all present in the other's."""
    return a <= b or b <= a


def _shared_fraction(a: frozenset[int], b: frozenset[int]) -> float:
    return len(a & b) / len(a | b)


def _best_counterpart(
    pull: Pull, candidates: list[Pull], taken: set[int]
) -> Pull | None:
    """The candidate sharing the largest fraction of types, preferring one not yet paired.

    Preferring an unpaired candidate is what keeps two identical packs on a
    route matched to two identical packs on the other, rather than both to the
    first. Ties go to the earliest pull in route order.
    """
    mine = _types(pull)
    covering = [c for c in candidates if _covers(mine, _types(c))]
    if not covering:
        return None
    unpaired = [c for c in covering if c.index not in taken]
    pool = unpaired or covering
    return max(pool, key=lambda c: (_shared_fraction(mine, _types(c)), -c.index))


def _reordered(matched: list[PullMatch]) -> list[PullMatch]:
    """The pairs that would have to move for their order to follow ours.

    One pair per our pull — its earliest counterpart — in our route order; the
    longest run whose reference indices also increase is the shared order, and
    everything outside it was taken in a different sequence.
    """
    first_by_ours: dict[int, PullMatch] = {}
    for match in sorted(matched, key=lambda m: (m.ours_index, m.theirs_index)):
        first_by_ours.setdefault(match.ours_index, match)
    pairs = list(first_by_ours.values())
    if not pairs:
        return []
    # Longest strictly increasing subsequence of theirs_index, O(n^2): a route has a dozen pulls.
    best_length = [1] * len(pairs)
    previous = [-1] * len(pairs)
    for i, pair in enumerate(pairs):
        for j in range(i):
            if pairs[j].theirs_index < pair.theirs_index and best_length[j] + 1 > best_length[i]:
                best_length[i] = best_length[j] + 1
                previous[i] = j
    end = max(range(len(pairs)), key=lambda i: (best_length[i], -i))
    in_order: set[int] = set()
    while end != -1:
        in_order.add(end)
        end = previous[end]
    return [pair for i, pair in enumerate(pairs) if i not in in_order]


def align_pulls(ours: Run, theirs: Run) -> Alignment:
    """Pair our pulls with theirs by what each contained.

    A boss pull matches the boss pull with the same encounter id, whatever
    adds either group happened to fight. Two trash pulls match when either
    one's set of enemy types is contained in the other's, so a stretch that
    Warcraft Logs recorded as one pull matches each separate pull it covers.
    Pulls with no recorded enemies match nothing. See design §6.3, amended
    2026-09-06, for why exact signatures were abandoned.
    """
    matched: list[PullMatch] = []

    their_bosses = {pull.encounter_id: pull for pull in theirs.pulls if pull.is_boss}
    for pull in ours.pulls:
        if pull.is_boss and pull.encounter_id in their_bosses:
            matched.append(
                PullMatch(ours_index=pull.index, theirs_index=their_bosses[pull.encounter_id].index)
            )

    our_trash = [pull for pull in ours.pulls if not pull.is_boss and pull.enemies]
    their_trash = [pull for pull in theirs.pulls if not pull.is_boss and pull.enemies]

    taken_theirs: set[int] = set()
    for pull in our_trash:
        counterpart = _best_counterpart(pull, their_trash, taken_theirs)
        if counterpart is not None:
            matched.append(PullMatch(ours_index=pull.index, theirs_index=counterpart.index))
            taken_theirs.add(counterpart.index)

    # Their pulls nobody picked may still sit inside one of ours: a pack we
    # chain-pulled that they took alone, after our pull already chose its
    # closest counterpart.
    taken_ours = {match.ours_index for match in matched}
    for pull in their_trash:
        if pull.index in taken_theirs:
            continue
        counterpart = _best_counterpart(pull, our_trash, taken_ours)
        if counterpart is not None:
            matched.append(PullMatch(ours_index=counterpart.index, theirs_index=pull.index))
            taken_ours.add(counterpart.index)

    matched_ours = {match.ours_index for match in matched}
    matched_theirs = {match.theirs_index for match in matched}
    return Alignment(
        matched=tuple(matched),
        only_ours=tuple(pull.index for pull in ours.pulls if pull.index not in matched_ours),
        only_theirs=tuple(
            pull.index for pull in theirs.pulls if pull.index not in matched_theirs
        ),
        out_of_order=tuple(_reordered(matched)),
        our_trash_count=len(our_trash),
        boss_indices=tuple(pull.index for pull in ours.pulls if pull.is_boss),
    )
```

Delete `_pair_by_signature` and the `difflib` import. `Pull.signature` stays on the model (nothing else uses it; leave it and its docstring — it is a true statement about the pull).

- [ ] **Step 4: Rewrite the existing alignment tests that pinned the old behaviour**

Run the file. `test_a_route_run_in_a_different_order_is_reported`, `test_a_genuine_swap_is_reported_as_reordering_and_leaves_no_leftovers`, `test_leftover_multiplicity_pairs_only_as_many_as_both_sides_share` and `test_a_skipped_pack_is_not_reported_as_reordering` pin the leftover-pairing definition of reordering. Rewrite each to the amended definition — pairs outside the longest shared order — keeping its name where the name is still true and renaming it where it is not. A repeated pack (`test_a_repeated_pack_is_matched_twice_not_folded_into_one`) must still pass unchanged: the unpaired-first preference is what makes it pass.

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_alignment.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing route tests**

In `tests/domain/comparison/test_route.py`:

```python
from wowperf.domain.comparison.route import MIN_ALIGNED_SHARE


def test_the_summary_states_how_many_trash_pulls_found_a_counterpart() -> None:
    ours = a_run((1,), (2,), (3,), (4,))
    theirs = a_run((1,), (2,))
    summary = compare_route(ours, theirs, align_pulls(ours, theirs), {})[0]
    assert summary.id == "compare.route.summary"
    assert "2 of 4 trash pulls found a counterpart" in summary.detail


def test_below_the_aligned_share_no_pack_is_priced_as_skipped() -> None:
    # One of five trash pulls aligned: the two logs cut the route differently.
    ours = a_run((1,), (2,), (3,), (4,), (5,))
    theirs = a_run((1,), (6,), (7,))
    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {1: 10})
    ids = [f.id for f in findings]
    assert "compare.route.unaligned" in ids
    assert not any(i.startswith("compare.route.skipped.") for i in ids)
    assert not any(i.startswith("compare.route.extra.") for i in ids)
    assert "compare.route.order" not in ids
    unaligned = next(f for f in findings if f.id == "compare.route.unaligned")
    assert unaligned.seconds_lost is None
    assert unaligned.confidence is Confidence.MEASURED
    assert "1 of 5" in unaligned.title


def test_at_the_aligned_share_packs_are_priced() -> None:
    ours = a_run((1,), (2,), (3,), (4,))
    theirs = a_run((1,), (2,))
    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})
    assert any(f.id.startswith("compare.route.skipped.") for f in findings)
    assert MIN_ALIGNED_SHARE == 0.5
```

- [ ] **Step 6: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_route.py -q`
Expected: FAIL.

- [ ] **Step 7: Add the gate and the wording to `route.py`**

```python
MIN_ALIGNED_SHARE = 0.5
"""Below this share of our trash pulls with a counterpart, no pack is priced as skipped.

When the two logs cut the route into pulls differently, an unmatched pull is not
a skipped pack; it is a segmentation difference, and pricing it would put the
largest wrong number on the page at the top of the ledger.
"""
```

Summary detail becomes:

```python
            detail=(
                f"{matched_trash} of {alignment.our_trash_count} trash "
                f"pull{'s' if alignment.our_trash_count != 1 else ''} found a counterpart. "
                "Packs are matched by which enemies they contain, not by when either group "
                "fought them, so this comparison holds across a keystone-level difference. A "
                "stretch fought without a break is one pull to Warcraft Logs, and it matches "
                "each of the separate pulls it covers."
            ),
```

where `matched_trash = round(alignment.matched_share * alignment.our_trash_count)`. Keep the four evidence lines; "in common" counts distinct `ours_index` values in `matched`.

After the summary, before the skipped loop:

```python
    if alignment.matched_share < MIN_ALIGNED_SHARE:
        findings.append(
            Finding(
                id="compare.route.unaligned",
                title=(
                    f"Only {matched_trash} of {alignment.our_trash_count} trash pulls could be "
                    "matched to the reference's"
                ),
                detail=(
                    "The two logs cut the route into pulls differently — a chain of packs "
                    "fought without a break is one pull to Warcraft Logs — so no pack is priced "
                    "as skipped or listed as extra. The timeline still shows both routes."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"{len(alignment.only_ours)} of our pulls without a counterpart",
                    f"{len(alignment.only_theirs)} of theirs without a counterpart",
                ),
            )
        )
        return findings
```

- [ ] **Step 8: Update `mplus-analysis/SKILL.md`**

Under "The confounds the comparison declares rather than correct", add a bullet after the keystone-level one:

```markdown
- **Pull segmentation.** Warcraft Logs records a chain of packs fought without a break as one
  pull. Alignment matches a pull to every separate pull it covers, and the route summary says how
  many of our trash pulls found a counterpart. When fewer than half did, `compare.route.unaligned`
  appears and no `compare.route.skipped.*` or `compare.route.extra.*` finding does: the two logs
  cut the route differently, and an unmatched pull is not a skipped pack. Say that, not "the
  reference skipped it".
```

- [ ] **Step 9: Replay against the cached real run**

Write a throwaway script in the scratchpad (not in the repo) that loads the two cached `Fights` payloads for reports `6Kx1P9GbNXrcLdHa` (fight 36) and `71cv4MRdNCp8ZFjG` (fight 28) from `C:/Users/damien/claude_perso/wow_perf/cache/*.json` — find them by `report.code` — builds both `Run`s with `wowperf.adapters.wcl.ingest.build_run` and `select_keystone_fight`, and prints `align_pulls(ours, theirs)`: matched pairs, `only_ours`, `only_theirs`, `matched_share`. Before this task the share was 4 of 12 pulls overall with 8 unmatched on each side. Record the new figures in the commit body. If the share is still below `MIN_ALIGNED_SHARE`, stop and report to the orchestrator: the gate would withhold the route on the very run that motivated it, and the threshold or the rule needs a human decision.

- [ ] **Step 10: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 11: Commit**

```bash
/cmd/git.exe add -A src tests .claude/skills && git commit -m "Align pulls by the enemy types they contain and withhold skipped packs below half a match" -m "Exact signatures put the largest wrong number on the page: a 324-second chain pull matched nothing and was priced as a pack the reference skipped. Containment matches a merged pull to the separate pulls it covers, and when fewer than half our trash pulls align the route is described rather than priced, as design §6.3 (amended 2026-09-06) specifies. Replayed against the cached real run: <matched> of <total> trash pulls now align (was 4 of 12 overall)."
```

---

### Task 5: Measure a death until the player acted on the fight again

**Files:**
- Modify: `src/wowperf/domain/events.py:16-21` (`CastEvent.target_id`)
- Modify: `src/wowperf/adapters/wcl/ingest.py:165-218` (`build_casts`, `build_deaths`)
- Modify: `src/wowperf/domain/analysis/deaths.py:89-99` (the total's detail sentence)
- Modify: `.claude/skills/mplus-analysis/SKILL.md` (wherever it describes the death cost)
- Test: `tests/adapters/wcl/test_ingest_events.py`, `tests/domain/analysis/test_deaths.py`, `tests/domain/test_events.py`

**Interfaces:**
- Produces: `CastEvent.target_id: int | None = None` — the actor the cast was aimed at, `None` when the log recorded no target (`targetID: -1`).

Read design §5.2's amendment first.

- [ ] **Step 1: Write the failing tests**

In `tests/adapters/wcl/test_ingest_events.py`, replace `test_the_cost_of_a_death_is_measured_to_the_players_next_cast` with:

```python
def test_a_cast_carries_its_target_and_none_for_an_untargeted_one() -> None:
    casts = build_casts(
        [
            {"type": "cast", "sourceID": 11, "targetID": 501, "abilityGameID": 700,
             "timestamp": 11000},
            {"type": "cast", "sourceID": 11, "targetID": -1, "abilityGameID": 701,
             "timestamp": 12000},
            {"type": "cast", "sourceID": 11, "abilityGameID": 702, "timestamp": 13000},
        ],
        a_run(),
        ABILITY_NAMES,
    )
    assert [cast.target_id for cast in casts] == [501, None, None]


def test_the_cost_of_a_death_runs_until_the_player_cast_at_another_actor() -> None:
    # Respawned at the entrance, the player pops a self-only sprint at 15s and a
    # self-buff at 20s while running back, then heals an ally at 45s. Only the
    # heal is the fight resuming.
    casts = build_casts(
        [
            {"type": "cast", "sourceID": 11, "targetID": -1, "abilityGameID": 700,
             "timestamp": 15000},
            {"type": "cast", "sourceID": 11, "targetID": 11, "abilityGameID": 701,
             "timestamp": 20000},
            {"type": "cast", "sourceID": 11, "targetID": 12, "abilityGameID": 702,
             "timestamp": 45000},
        ],
        a_run(),
        ABILITY_NAMES,
    )
    events: list[dict[str, Any]] = [
        {"abilityGameID": 0, "fight": 2, "killerID": 999, "killingAbilityGameID": 900,
         "sourceID": -1, "targetID": 11, "timestamp": 12000, "type": "death"},
    ]
    death = build_deaths(events, a_run(), casts, ABILITY_NAMES)[0]
    assert death.seconds_until_next_action == 33.0


def test_a_death_followed_only_by_self_casts_has_no_measured_cost() -> None:
    casts = build_casts(
        [{"type": "cast", "sourceID": 11, "targetID": -1, "abilityGameID": 700,
          "timestamp": 15000}],
        a_run(),
        ABILITY_NAMES,
    )
    events: list[dict[str, Any]] = [
        {"abilityGameID": 0, "fight": 2, "killerID": 999, "killingAbilityGameID": 900,
         "sourceID": -1, "targetID": 11, "timestamp": 12000, "type": "death"},
    ]
    assert build_deaths(events, a_run(), casts, ABILITY_NAMES)[0].seconds_until_next_action is None
```

In `tests/domain/analysis/test_deaths.py`, add:

```python
def test_the_total_does_not_claim_to_exceed_the_timer_penalty() -> None:
    findings = analyse_deaths(a_run(), (a_death(seconds_until_next_action=3.0),))
    total = next(f for f in findings if f.id == "deaths.total")
    assert "longer than the timer penalty" not in total.detail
    assert "cast at another actor" in total.detail
```

using that file's existing death fixture helper (adapt the name).

- [ ] **Step 2: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl/test_ingest_events.py tests/domain/analysis/test_deaths.py -q`
Expected: FAIL — `CastEvent` has no `target_id`; the cost is 3.0; the detail still claims "longer than".

- [ ] **Step 3: Implement**

`events.py`:

```python
class CastEvent(Frozen):
    actor_id: int
    ability_id: int
    ability_name: str
    timestamp_ms: int
    pull_index: int | None = None
    # The actor the cast was aimed at. None when the log recorded no target,
    # which is how self-only movement and shield spells appear.
    target_id: int | None = None
```

`ingest.py`, `build_casts`:

```python
def _target_of(event: dict[str, Any]) -> int | None:
    """The cast's target actor, or None: the API writes -1 for a cast with no target."""
    target = event.get("targetID")
    if target is None or target == -1:
        return None
    return int(target)
```

and `target_id=_target_of(event)` in the `CastEvent(...)` call.

`build_deaths`: replace the `casts_by_actor` build and `later` with

```python
    # A cast aimed at another actor is the first moment the player affected the
    # fight again. A released player respawns alive at the entrance with no
    # event to say so, and presses self-only sprints and shields while running
    # back; counting those would end the death after a few seconds of a
    # twenty-second absence.
    acted_by_actor: dict[int, list[int]] = {}
    for cast in casts:
        if cast.target_id is not None and cast.target_id != cast.actor_id:
            acted_by_actor.setdefault(cast.actor_id, []).append(cast.timestamp_ms)
    ...
        later = [stamp for stamp in acted_by_actor.get(actor_id, []) if stamp > timestamp]
```

Update the function's docstring to say "until the player next acted on another actor".

`deaths.py`, the total's detail:

```python
        detail = (
            "Measured from each death to that player's first cast at another actor: the "
            "time the group played without them. The timer penalty is counted separately, "
            "in the time decomposition."
        )
```

- [ ] **Step 4: Update the skill**

In `.claude/skills/mplus-analysis/SKILL.md`, wherever the death cost is described (search for `next cast` and `deaths.total`), state the anchor: "measured to the player's first cast at another actor, because a respawned player casts self-only spells while running back".

- [ ] **Step 5: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass. `tests/domain/test_events.py` may construct `CastEvent` positionally; if so it still passes because the new field is last and defaulted.

- [ ] **Step 6: Commit**

```bash
/cmd/git.exe add -A src tests .claude/skills && git commit -m "Measure a death until the player's first cast at another actor" -m "A released player respawns alive with no event and casts self-only sprints while running back, so the next cast ended two twenty-second absences after three and six seconds, and the total's fixed claim of exceeding the timer penalty was false beside a penalty four times larger. Design §5.2, amended 2026-09-06."
```

---

### Task 6: Name the affixes, and state when the reference's differ

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py` (add `AFFIXES_QUERY`)
- Modify: `src/wowperf/adapters/wcl/repository.py` (`get`, `load` resolve names)
- Modify: `src/wowperf/domain/model.py:72` (`Run.affix_names`)
- Modify: `src/wowperf/domain/report/build.py:491` (`_header`)
- Modify: `src/wowperf/domain/comparison/confounds.py` (`compare.confound.affixes`)
- Modify: `.claude/skills/wcl-api/SKILL.md` (two table rows)
- Test: `tests/adapters/wcl/test_repository.py`, `tests/domain/report/test_build_frame.py`, `tests/domain/comparison/test_confounds.py`, `tests/test_cli.py` (the transport must answer the new query)

**Interfaces:**
- Produces: `Run.affix_names: tuple[str, ...] = ()`, index-aligned with `affix_ids` when non-empty.
- Produces: `AFFIXES_QUERY` — `query Affixes { gameData { affixes { id name } } }`.
- Produces: `WclRunRepository._affix_names(affix_ids: Sequence[int]) -> tuple[str, ...]`, falling back to the id as a string for an id the game data does not list.

- [ ] **Step 1: Write the failing tests**

`tests/adapters/wcl/test_repository.py` — read how it builds a repository over a mock transport, then add:

```python
def test_a_run_carries_its_affix_names_from_game_data(...) -> None:
    # The transport answers the Affixes query with [{"id": 9, "name": "Tyrannical"},
    # {"id": 10, "name": "Fortified"}] and the fixture fight lists affixes [9, 10, 147].
    run = repository.get("abc123", None)
    assert run.affix_ids == (9, 10, 147)
    assert run.affix_names == ("Tyrannical", "Fortified", "147")
```

`tests/domain/report/test_build_frame.py`:

```python
def test_the_header_names_the_affixes_when_names_are_known() -> None:
    report = build_report(
        a_loaded(run=a_run(affix_ids=(9, 10), affix_names=("Tyrannical", "Fortified"))),
        (), None, None, a_player(), None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )
    assert report.header.affixes == ("Tyrannical", "Fortified")


def test_the_header_falls_back_to_ids_when_no_name_was_resolved() -> None:
    report = build_report(
        a_loaded(run=a_run(affix_ids=(9, 10))),
        (), None, None, a_player(), None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )
    assert report.header.affixes == ("9", "10")
```

`tests/domain/comparison/test_confounds.py`:

```python
def test_differing_affixes_are_declared_by_name() -> None:
    ours = a_loaded(affix_ids=(9, 147), affix_names=("Tyrannical", "Xal'atath's Guile"))
    theirs = a_loaded(affix_ids=(10, 147), affix_names=("Fortified", "Xal'atath's Guile"))
    findings = declare_confounds(ours, theirs, Comparability(our_level=16, their_level=16))
    affixes = next(f for f in findings if f.id == "compare.confound.affixes")
    assert affixes.confidence is Confidence.MEASURED
    assert affixes.seconds_lost is None
    assert "only ours: Tyrannical" in affixes.evidence
    assert "only theirs: Fortified" in affixes.evidence


def test_identical_affixes_raise_no_confound() -> None:
    ours = a_loaded(affix_ids=(9, 147))
    findings = declare_confounds(ours, ours, Comparability(our_level=16, their_level=16))
    assert not any(f.id == "compare.confound.affixes" for f in findings)
```

Adapt `a_loaded` to that file's helper; if it builds a `Run` without exposing affixes, extend the helper with `affix_ids` and `affix_names` keyword arguments.

- [ ] **Step 2: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl/test_repository.py tests/domain/report/test_build_frame.py tests/domain/comparison/test_confounds.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`queries.py`:

```python
# Argument-free and game-wide, so one cached response serves every run.
AFFIXES_QUERY = """
query Affixes {
  gameData {
    affixes { id name }
  }
}
"""
```

`model.py`, on `Run` after `affix_ids`:

```python
    # Resolved from game data by the adapter, index-aligned with affix_ids.
    # Empty when no resolution ran; an id the game data does not list resolves
    # to the id as text, so the two tuples are equal in length whenever this
    # one is non-empty.
    affix_names: tuple[str, ...] = ()
```

`repository.py`:

```python
    def _affix_names(self, affix_ids: Sequence[int]) -> tuple[str, ...]:
        """Affix names from game data, with the bare id for anything unlisted.

        Cached indefinitely: the affix table is game-wide and changes only when
        Blizzard adds one, at which point the new id simply resolves to itself
        until the cache is cleared.
        """
        if not affix_ids:
            return ()
        payload = self._cache.get_or_fetch(
            cache_key(AFFIXES_QUERY, {}), lambda: self._client.execute(AFFIXES_QUERY, {})
        )
        rows = (payload.get("gameData") or {}).get("affixes") or []
        names = {int(row["id"]): str(row["name"]) for row in rows}
        return tuple(names.get(affix_id, str(affix_id)) for affix_id in affix_ids)
```

Note `_query` cannot be used here: `_require_report` expects `reportData`. Both `get` and `load` then do `run = run.model_copy(update={"affix_names": self._affix_names(run.affix_ids)})` after `build_run`.

`build.py`, `_header`:

```python
        affixes=(
            run.affix_names
            if run.affix_names
            else tuple(str(affix_id) for affix_id in run.affix_ids)
        ),
```

`confounds.py`, after the composition block:

```python
    our_affixes = set(ours.run.affix_ids)
    their_affixes = set(theirs.run.affix_ids)
    if our_affixes != their_affixes:
        names = dict(zip(ours.run.affix_ids, ours.run.affix_names, strict=False))
        names.update(zip(theirs.run.affix_ids, theirs.run.affix_names, strict=False))

        def named(ids: set[int]) -> str:
            return ", ".join(names.get(i, str(i)) for i in sorted(ids)) or "none"

        findings.append(
            Finding(
                id="compare.confound.affixes",
                title="The two runs were not on the same affixes",
                detail=(
                    "An affix changes which packs are dangerous and how long a boss lives. "
                    "Requiring the same affixes would usually leave nothing to compare "
                    "against, so the difference is stated rather than filtered on."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"only ours: {named(our_affixes - their_affixes)}",
                    f"only theirs: {named(their_affixes - our_affixes)}",
                ),
            )
        )
```

`.claude/skills/wcl-api/SKILL.md`, two rows in the field table:

```markdown
| `gameData` | `Query` | 2026-09-06 | yes |
| `affixes` | `GameData` | 2026-09-06 | yes |
```

`tests/test_cli.py`: `build_analyze_transport` must answer an operation named `Affixes` with `{"data": {"gameData": {"affixes": [{"id": 9, "name": "Tyrannical"}, {"id": 10, "name": "Fortified"}, {"id": 147, "name": "Xal'atath's Guile"}]}}}`. Read how it dispatches on operation name and add the branch. Then add:

```python
def test_the_report_names_the_affixes(tmp_path: Path) -> None:
    invoke_analyze(tmp_path)
    [html] = (tmp_path / "out").glob("*.html")
    assert "Tyrannical" in html.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass, including `tests/test_skills.py` (both new fields appear in `queries.py`).

- [ ] **Step 5: Commit**

```bash
/cmd/git.exe add -A src tests .claude/skills && git commit -m "Resolve affix names from game data and declare an affix difference" -m "The header printed 'Affixes 9, 10, 147' although design §3.5 said names come from gameData, and the affix difference §6.2 asked for was captured on both reference rows and never shown. gameData.affixes verified live 2026-09-06."
```

---

### Task 7: Know which specialisations tank

**Files:**
- Create: `data/roles.toml`
- Modify: `src/wowperf/domain/season.py` (`Roles`)
- Modify: `src/wowperf/adapters/config/toml.py` (`load_roles`)
- Modify: `src/wowperf/domain/analysis/players.py` (`_damage_outliers`, `analyse_players`)
- Modify: `src/wowperf/domain/analysis/service.py`, `src/wowperf/cli.py`
- Test: `tests/adapters/config/test_toml.py`, `tests/domain/test_season.py`, `tests/domain/analysis/test_players.py`, `tests/domain/analysis/test_service.py`

**Interfaces:**
- Produces: `Roles(Frozen)` with `tanks: tuple[str, ...]`, `healers: tuple[str, ...]` (each entry `"Class/Spec"`) and `role_of(class_name: str, spec: str) -> str` returning `"tank"`, `"healer"` or `"damage"`.
- Produces: `load_roles(path: Path = DEFAULT_ROLES_PATH) -> Roles`.
- Changes: `analyse_players(run, casts, deaths, interrupts, damage_taken, roles: Roles = Roles())` and `analyse(..., roles: Roles = Roles(), include_cooldown_ceiling=False)`.

- [ ] **Step 1: Write the failing tests**

`tests/domain/test_season.py`:

```python
from wowperf.domain.season import Roles


def test_role_of_reads_the_spec_lists_and_defaults_to_damage() -> None:
    roles = Roles(tanks=("DeathKnight/Blood",), healers=("Paladin/Holy",))
    assert roles.role_of("DeathKnight", "Blood") == "tank"
    assert roles.role_of("Paladin", "Holy") == "healer"
    assert roles.role_of("Mage", "Arcane") == "damage"
    assert Roles().role_of("DeathKnight", "Blood") == "damage"
```

`tests/adapters/config/test_toml.py`:

```python
from wowperf.adapters.config.toml import load_roles


def test_the_committed_roles_file_names_six_tanks_and_seven_healers() -> None:
    roles = load_roles()
    assert len(roles.tanks) == 6
    assert len(roles.healers) == 7
    assert not set(roles.tanks) & set(roles.healers)
    assert all(entry.count("/") == 1 for entry in roles.tanks + roles.healers)
```

`tests/domain/analysis/test_players.py`:

```python
from wowperf.domain.season import Roles

TANKS = Roles(tanks=("DeathKnight/Blood",))


def test_a_tank_is_left_out_of_the_damage_comparison() -> None:
    # The Blood Death Knight took forty times the others' melee damage. That is the job.
    run = a_run_with(  # adapt to this file's roster helper
        Player(actor_id=1, name="Tank", class_name="DeathKnight", spec="Blood", item_level=1),
        Player(actor_id=2, name="A", class_name="Mage", spec="Arcane", item_level=1),
        Player(actor_id=3, name="B", class_name="Mage", spec="Fire", item_level=1),
        Player(actor_id=4, name="C", class_name="Mage", spec="Frost", item_level=1),
    )
    hits = melee_hits(  # adapt: one DamageTakenEvent per actor, ability "Melee"
        {1: 4_000_000, 2: 100_000, 3: 100_000, 4: 100_000}
    )
    findings = analyse_players(run, (), (), (), hits, roles=TANKS)
    assert not any(f.id.startswith("players.damage.") for f in findings)


def test_a_tank_does_not_pull_the_median_down_for_everyone_else() -> None:
    # Without the tank, the three others' median is 100,000 and C's 300,000 is 3x it.
    run = ...same roster...
    hits = melee_hits({1: 5_000, 2: 100_000, 3: 100_000, 4: 300_000})
    findings = analyse_players(run, (), (), (), hits, roles=TANKS)
    outlier = next(f for f in findings if f.id.startswith("players.damage."))
    assert outlier.title.startswith("C took 3.0x")


def test_without_a_roles_table_nobody_is_a_tank() -> None:
    run = ...same roster...
    hits = melee_hits({1: 4_000_000, 2: 100_000, 3: 100_000, 4: 100_000})
    findings = analyse_players(run, (), (), (), hits)
    assert any(f.title.startswith("Tank took") for f in findings)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/test_season.py tests/adapters/config/test_toml.py tests/domain/analysis/test_players.py -q`
Expected: FAIL — `Roles` does not exist.

- [ ] **Step 3: Implement**

`data/roles.toml`:

```toml
# Which specialisations tank and which heal. No API field carries a role, so this
# is maintained by hand and dated. A specialisation absent from both lists is
# treated as damage, which is the safe direction: a tank mistaken for damage
# produces a loud false finding about melee damage, a damage player mistaken for
# a tank produces silence.
#
# Read from the game's class and specialisation list on the date below.
verified = "2026-09-06"

[tank]
specs = [
  "DeathKnight/Blood",
  "DemonHunter/Vengeance",
  "Druid/Guardian",
  "Monk/Brewmaster",
  "Paladin/Protection",
  "Warrior/Protection",
]

[healer]
specs = [
  "Druid/Restoration",
  "Evoker/Preservation",
  "Monk/Mistweaver",
  "Paladin/Holy",
  "Priest/Discipline",
  "Priest/Holy",
  "Shaman/Restoration",
]
```

`season.py`:

```python
class Roles(Frozen):
    """Which specialisations tank and which heal, as "Class/Spec" entries.

    Empty by default, so a caller without the data file treats everyone as
    damage — the direction that produces a finding rather than silence.
    """

    tanks: tuple[str, ...] = ()
    healers: tuple[str, ...] = ()

    def role_of(self, class_name: str, spec: str) -> str:
        key = f"{class_name}/{spec}"
        if key in self.tanks:
            return "tank"
        if key in self.healers:
            return "healer"
        return "damage"
```

`toml.py`:

```python
DEFAULT_ROLES_PATH = DATA_DIR / "roles.toml"


def load_roles(path: Path = DEFAULT_ROLES_PATH) -> Roles:
    """Tank and healer specialisations, from the committed TOML file."""
    raw = _read(path)
    tank = raw.get("tank")
    healer = raw.get("healer")
    assert isinstance(tank, dict) and isinstance(healer, dict)
    return Roles(
        tanks=tuple(str(spec) for spec in tank.get("specs", ())),
        healers=tuple(str(spec) for spec in healer.get("specs", ())),
    )
```

`players.py`: `_damage_outliers(run, damage_taken, roles)` builds `tank_ids = {p.actor_id for p in run.players if roles.role_of(p.class_name, p.spec) == "tank"}` and skips hits whose `actor_id` is in it before totalling. Replace the comment that begins "Melee damage on a tank is the job" with:

```python
        # Tanks are left out of this comparison altogether: as the only member of
        # their role they have no honest median. The class and spec still name
        # the player for a reader.
```

`analyse_players` gains `roles: Roles = Roles()` as its last parameter and passes it through. `service.analyse` gains `roles: Roles = Roles()` (keyword, before `include_cooldown_ceiling`) and passes it to `analyse_players`. `cli.py` passes `roles=load_roles()`.

- [ ] **Step 4: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
/cmd/git.exe add -A data src tests && git commit -m "Leave tanks out of the damage-against-median comparison" -m "The loudest finding on a real page was a Blood Death Knight taking two hundred times the group median from melee, which is the job. The roster carries the spec, and spec to role is a dated table of thirteen rows. Design §5.5, amended 2026-09-06."
```

---

### Task 8: Read the quota around `analyze`

**Files:**
- Modify: `src/wowperf/cli.py` (`analyze`; extract the sentence `fetch` prints)
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `_quota_sentence(before: RateLimit, after: RateLimit) -> str`, used by both commands.

- [ ] **Step 1: Write the failing test**

```python
def test_analyze_prints_the_points_it_spent_on_stderr(tmp_path: Path) -> None:
    result = invoke_analyze(tmp_path, "--no-compare")
    assert result.exit_code == 0, result.output
    assert "points spent, including the cost of these two quota reads" in result.stderr
    assert "of 3600 remain this hour" in result.stderr
```

`build_analyze_transport` must answer `RateLimit` queries; if it does not, add a branch mirroring `build_transport`'s, answering a rising count (`100.0` then `128.0`). `_invoke` may need `mix_stderr=False` or the runner may already separate streams — check how `test_fetch_prints_the_run_on_stdout_and_the_quota_on_stderr` reads `result.stderr` and do the same.

- [ ] **Step 2: Run it to verify it fails**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_cli.py -q -k points_it_spent`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
def _quota_sentence(before: RateLimit, after: RateLimit) -> str:
    spent = after.points_spent_this_hour - before.points_spent_this_hour
    remaining = after.limit_per_hour - after.points_spent_this_hour
    return (
        f"Rate limit: {spent:.2f} points spent, including the cost of these two "
        f"quota reads themselves; {remaining:.2f} of {after.limit_per_hour} remain this hour."
    )
```

`fetch` calls it. In `analyze`, `before = repository.rate_limit()` immediately after `build_repository`, `after = repository.rate_limit()` after the comparison block (still inside the `try`), and `typer.echo(_quota_sentence(before, after), err=True)` after the report is written. Import `RateLimit` from `wowperf.adapters.wcl.client`.

- [ ] **Step 4: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
/cmd/git.exe add -A src tests && git commit -m "Print the points analyze spent, as fetch already does" -m "Design §3.3 requires every phase to read rateLimitData before and after; only fetch did, so the skill's 'roughly 28 points' had no instrument behind it."
```

---

### Task 9: Expire what was fetched for a reference

**Files:**
- Modify: `src/wowperf/adapters/cache/disk.py`
- Modify: `src/wowperf/cli.py` (`build_repository`, `analyze`, `_references`, the parse aura fetch)
- Modify: `.claude/skills/analyzing-a-run/SKILL.md` step 5 (the "never expire" sentence)
- Test: `tests/adapters/cache/test_disk.py`, `tests/test_cli.py`

**Interfaces:**
- Changes: `DiskCache(directory: Path, max_age_seconds: float | None = None, now: Callable[[], float] = time.time)`. With a `max_age_seconds`, an entry older than it is refetched and overwritten, and `purge_expired()` — called from `__init__` — deletes expired files.
- Produces: `REFERENCE_CACHE_SECONDS = 24 * 3600` and `REFERENCE_CACHE_SUBDIR = "references"` in `cli.py`; `build_reference_repositories(client: WclClient, cache_dir: Path) -> tuple[WclRankingRepository, WclRunRepository]`.

Read design §3.3's amendment first.

- [ ] **Step 1: Write the failing cache tests**

```python
def test_an_entry_older_than_max_age_is_fetched_again(tmp_path: Path) -> None:
    clock = [1_000.0]
    calls: list[int] = []

    def fetch() -> dict[str, object]:
        calls.append(1)
        return {"at": clock[0]}

    cache = DiskCache(tmp_path, max_age_seconds=60, now=lambda: clock[0])
    assert cache.get_or_fetch("k", fetch) == {"at": 1_000.0}
    clock[0] = 1_030.0
    assert cache.get_or_fetch("k", fetch) == {"at": 1_000.0}
    clock[0] = 1_061.0
    assert cache.get_or_fetch("k", fetch) == {"at": 1_061.0}
    assert len(calls) == 2


def test_opening_a_cache_purges_its_expired_entries(tmp_path: Path) -> None:
    clock = [1_000.0]
    DiskCache(tmp_path, max_age_seconds=60, now=lambda: clock[0]).get_or_fetch(
        "old", lambda: {"v": 1}
    )
    clock[0] = 1_100.0
    DiskCache(tmp_path, max_age_seconds=60, now=lambda: clock[0]).get_or_fetch(
        "fresh", lambda: {"v": 2}
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fresh.json"]


def test_a_cache_without_a_max_age_keeps_everything(tmp_path: Path) -> None:
    clock = [0.0]
    cache = DiskCache(tmp_path, now=lambda: clock[0])
    cache.get_or_fetch("k", lambda: {"v": 1})
    clock[0] = 10**9
    assert DiskCache(tmp_path, now=lambda: clock[0]).get_or_fetch(
        "k", lambda: {"v": 2}
    ) == {"v": 1}
```

The age of an entry is read from the file's own modification time, so the tests must set it: after each write, `os.utime(path, (clock, clock))` is the cache's job — write the mtime from `now()` in `_write_atomically` so the clock injected in tests governs age. State this in the implementation.

- [ ] **Step 2: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/cache/test_disk.py -q`
Expected: FAIL — unexpected keyword `max_age_seconds`.

- [ ] **Step 3: Implement the cache**

```python
class DiskCache:
    """One JSON file per key. Entries live forever unless a maximum age is given.

    Two policies, one class: report data for a finished fight never changes and
    is kept indefinitely, while leaderboard rows and everything fetched for a
    reference run expire, so that no standing store of other players' logs
    accumulates. The age of an entry is its file's modification time, stamped
    from `now` at write time so a test can drive the clock.
    """

    def __init__(
        self,
        directory: Path,
        max_age_seconds: float | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._directory = directory
        self._max_age = max_age_seconds
        self._now = now
        self._directory.mkdir(parents=True, exist_ok=True)
        if self._max_age is not None:
            self.purge_expired()

    def _expired(self, path: Path) -> bool:
        return self._max_age is not None and self._now() - path.stat().st_mtime > self._max_age

    def purge_expired(self) -> None:
        """Delete every entry older than the maximum age. No-op without one."""
        if self._max_age is None:
            return
        for path in self._directory.glob("*.json"):
            if self._expired(path):
                path.unlink(missing_ok=True)

    def get_or_fetch(self, key: str, fetch: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        path = self._directory / f"{key}.json"
        if path.exists() and not self._expired(path):
            return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

        value = fetch()
        self._write_atomically(path, json.dumps(value))
        return value
```

In `_write_atomically`, after `os.replace(temporary, path)`, add `stamp = self._now(); os.utime(path, (stamp, stamp))`. Update the module's second `ABOUTME` line and the `_write_atomically` docstring sentence "Entries never expire" to "An entry may be read for a day or forever".

- [ ] **Step 4: Write the failing CLI tests**

```python
def test_reference_responses_are_cached_apart_from_the_runs_own(tmp_path: Path) -> None:
    result = invoke_analyze(tmp_path)
    assert result.exit_code == 0, result.output
    own = {p.name for p in (tmp_path / "cache").glob("*.json")}
    references = {p.name for p in (tmp_path / "cache" / "references").glob("*.json")}
    assert own and references
    assert not own & references


def test_no_compare_writes_nothing_under_references(tmp_path: Path) -> None:
    invoke_analyze(tmp_path, "--no-compare")
    assert not (tmp_path / "cache" / "references").exists()
```

Check how `invoke_analyze` passes `--cache-dir`; the assertions assume `tmp_path / "cache"`.

- [ ] **Step 5: Wire the CLI**

```python
REFERENCE_CACHE_SUBDIR = "references"
REFERENCE_CACHE_SECONDS = 24 * 3600.0
"""How long a leaderboard row or a reference run's responses are kept.

Long enough for the narrative re-run the analyzing-a-run skill relies on to be
served from cache; short enough that no standing store of other players' logs
accumulates (RPGLogs terms §5d). Our own run's responses never expire.
"""


def build_reference_repositories(
    client: WclClient, cache_dir: Path
) -> tuple[WclRankingRepository, WclRunRepository]:
    """The leaderboards and the reference runs, behind the expiring cache."""
    transient = DiskCache(cache_dir / REFERENCE_CACHE_SUBDIR, max_age_seconds=REFERENCE_CACHE_SECONDS)
    return WclRankingRepository(client, transient), WclRunRepository(client, transient)
```

In `analyze`, inside `if not no_compare:`, replace `rankings = WclRankingRepository(repository.client, repository.cache)` with `rankings, references = build_reference_repositories(repository.client, cache_dir)` and pass `references` as the `runs` argument of `_references` and as the repository for the parse counterpart's `_auras(...)` call (our own auras keep using `repository`).

- [ ] **Step 6: Update the workflow skill**

In `.claude/skills/analyzing-a-run/SKILL.md` step 5, replace "and cache entries never expire, so only then does the second run spend no API quota" with "and reference entries live a day, so a second run the same day spends no API quota".

- [ ] **Step 7: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
/cmd/git.exe add -A src tests .claude/skills && git commit -m "Expire leaderboard rows and reference-run responses after a day" -m "Every entry lived forever, so the fastest-run reference never refreshed and repeated use accumulated the standing store of other players' logs RPGLogs §5d forbids. Our own run's data still never expires. Design §3.3, amended 2026-09-06."
```

---

### Task 10: Let the Deaths section own the death findings

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`Report.death_findings`)
- Modify: `src/wowperf/domain/report/build.py` (`DEATH_FINDING_PREFIXES`, `build_death_findings`, `_placed_finding_ids`, `build_report`)
- Modify: `src/wowperf/adapters/render/report.html.j2` (rows after the death cards)
- Test: `tests/domain/report/test_build_deaths.py`, `tests/domain/report/test_build_observations.py`, `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Produces: `Report.death_findings: tuple[LedgerRow, ...]` and `DEATH_FINDING_PREFIXES = ("defensives.unused.", "consumables.unused.", "consumables.never.")`.

Read the report design §5 amendment first.

- [ ] **Step 1: Write the failing tests**

`tests/domain/report/test_build_deaths.py`:

```python
def test_death_findings_are_placed_under_deaths_not_observations() -> None:
    findings = (
        a_finding("defensives.unused.Uglymage", title="Uglymage died once with a defensive available"),
        a_finding("consumables.unused.Uglymage", title="Uglymage died once with no healing consumable on cooldown"),
        a_finding("consumables.never.Uglymage", title="Uglymage died once and used no health potion"),
        a_finding("trash.pull.0", title="Pull 4 bought 0.0 forces per second"),
    )
    report = build_report(a_loaded(), findings, None, None, SUBJECT, None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES)
    assert [row.finding_id for row in report.death_findings] == [
        "defensives.unused.Uglymage",
        "consumables.unused.Uglymage",
        "consumables.never.Uglymage",
    ]
    assert [row.finding_id for row in report.observations] == ["trash.pull.0"]
```

Reuse `a_finding`, `a_loaded`, `SUBJECT` from `test_build_observations.py` (import them, or move them into `test_build_frame.py` if that is cleaner — keep one definition).

`tests/adapters/render/test_html_sections.py`:

```python
def test_death_findings_render_inside_the_deaths_section() -> None:
    html = render(build_report(a_loaded(), (
        a_finding("defensives.unused.Uglymage", title="Uglymage died once with a defensive available"),
    ), None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES))
    deaths_start = html.index('<h2 id="deaths">')
    interrupts_start = html.index('<h2 id="interrupts">')
    title_at = html.index("Uglymage died once with a defensive available")
    assert deaths_start < title_at < interrupts_start
```

- [ ] **Step 2: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_deaths.py tests/adapters/render/test_html_sections.py -q`
Expected: FAIL — `Report` has no `death_findings`.

- [ ] **Step 3: Implement**

`model.py`, on `Report` after `deaths`:

```python
    # The per-player death findings — a defensive or a consumable available at
    # a death, a consumable never drunk — beneath the cards that show each death.
    death_findings: tuple[LedgerRow, ...] = ()
```

`build.py`:

```python
DEATH_FINDING_PREFIXES = ("defensives.unused.", "consumables.unused.", "consumables.never.")
"""Finding families that belong beneath the death cards rather than in the catch-all."""


def build_death_findings(
    findings: Sequence[Finding], titles_by_id: dict[str, str]
) -> tuple[LedgerRow, ...]:
    """The findings about what a dying player still had, placed with the deaths."""
    return tuple(
        _ledger_row(finding, titles_by_id)
        for finding in findings
        if finding.id.startswith(DEATH_FINDING_PREFIXES)
    )
```

`_placed_finding_ids` gains a `death_findings: Sequence[LedgerRow]` parameter and adds their ids. `build_report` builds `death_findings = build_death_findings(findings, titles_by_id)` and passes it to both.

`report.html.j2`, after the death cards' `{% endfor %}` and before `<h2 id="interrupts">`:

```jinja
{% for row in report.death_findings %}
{{ ledger_row(row) }}
{% endfor %}
```

- [ ] **Step 4: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass. `test_no_finding_reaches_the_page_twice` and `test_every_finding_reaches_the_page` are the ones that matter here. If the golden file changed, regenerate with `--golden-update` and confirm the diff is only a moved row.

- [ ] **Step 5: Commit**

```bash
/cmd/git.exe add -A src tests && git commit -m "Place the death findings beneath the death cards" -m "The catch-all repeated each card's one-line claim as a full card with a three-sentence caveat, six times on a real page. Report design §5, amended 2026-09-06."
```

---

### Task 11: Re-run the real report (orchestrator, needs credentials)

**Files:** none in the repo. Output under the worktree's `out/`.

This task is run by the orchestrating session, not a subagent: it needs `WCL_CLIENT_ID` and `WCL_CLIENT_SECRET`, which live in the main checkout's UTF-16 `.env` and are never printed. Reuse the main checkout's cache so the run spends only the new queries.

- [ ] **Step 1: Run the analysis**

From the worktree, with the credentials exported into the environment by a wrapper that reads `.env` the way the spikes did:

```
uv run wowperf analyze https://www.warcraftlogs.com/reports/6Kx1P9GbNXrcLdHa?fight=36 --cache-dir C:/Users/damien/claude_perso/wow_perf/cache
```

Expected on stderr: the quota sentence. Expected on stdout: the two file paths.

- [ ] **Step 2: Check every defect against the new findings file**

Open `out/6Kx1P9GbNXrcLdHa-36.findings.json` and confirm, one line each in the final report to RwlRwlRwlRwl:

- D1: no `compare.route.skipped.*` prices pull 10; either the pulls aligned and the skipped list is short and plausible, or `compare.route.unaligned` states the share.
- D2: any skipped pack's forces equal the `trash.pull.*` forces for the same pull.
- D3: `deaths.total` is not "15s"; Milkmystiel's and Uglymage's deaths cost over twenty seconds each; the detail no longer mentions the timer penalty.
- D5: the HTML header reads "Tyrannical, Fortified, Xal'atath's Guile", not "9, 10, 147".
- D6: no `players.damage.*` names Dudesons taking melee.
- D7: the stderr sentence reports points spent.
- D8: `cache/references/` exists and holds the two reference reports' responses; the root `cache/` gained only the affix and rate-limit responses.
- D9: the `defensives.unused.*` and `consumables.*` findings appear under "Deaths" in the HTML and not under "Other findings".
- D11: no `map position` string in the JSON; the interrupt details carry thousands separators; `compare.confound.affixes` is absent (both runs were on 9, 10, 147) or present with names.

- [ ] **Step 3: Open the HTML in the browser and read it once through**, as a player would. Note anything the checks above missed.

- [ ] **Step 4: Update `.claude/lessons.md`** only if RwlRwlRwlRwl corrects something during review; otherwise leave it.

---

## Self-review against the roadmap

| Roadmap defect | Task |
| --- | --- |
| D1 alignment artefact | 4 |
| D2 forces per type | 3 |
| D3 death cost anchor | 5 |
| D4 unwired analyser | withdrawn — it is wired (see "Withdrawn from scope") |
| D5 affix ids | 6 |
| D6 tank melee outlier | 7 |
| D7 no rate limit in analyze | 8 |
| D8 cache never expires | 9 |
| D9 death findings twice | 10 |
| D10 documentation drift | 1 (skills), design amendments committed with this plan |
| D11 formatting, map positions, affix confound, inert debuff half | 2, 2, 6, deferred to the per-player phase |
| Real-run acceptance | 11 |
