# Raid HTML Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `wowperf raid` writes one self-contained HTML report beside its findings JSON, with the seven tabs design section 10 fixes.

**Architecture:** A raid report model, builder and template set sit *beside* the Mythic+ ones rather than inside them, sharing the vocabulary below them whole — `LedgerRow`, `Badge`, `Tooltip`, `Section`, `ledger_row`, `place_rows`, `collapse_repeated_details`, `build_observations`, the macros, the CSS, the inline script and the icon pipeline. Nothing in `analyze` changes behaviour. The one change reaching outside the report layer is the first task: the raid parse axis must mint a finding id per player before any page can key an element id on one.

**Tech Stack:** Python 3.12, pydantic frozen models, Jinja2, pytest, `uv` as the only toolchain.

**Spec:** `docs/plans/2026-09-13-raid-analysis-design.md` — section 10 (the report), section 11 (command line), section 6 (which analyser produces what), section 12 (testing). The master design `docs/plans/2026-09-03-mplus-postmortem-design.md` remains the authority on architecture, badges and refusals; section 9 of the raid design records which of its rules do not reach raid. Section 14 was resolved by measurement and wins wherever an unamended section disagrees with it.

**Plans this one follows:** `2026-09-14-raid-foundation-plan.md` (plan 1), `2026-09-14-raid-mechanics-plan.md` (plan 2), `2026-09-14-raid-parse-axis-plan.md` (plan 3a). This is plan 3b, the second half of the design's plan 3.

## Global Constraints

Every task's requirements implicitly include this section.

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or touches the network, the disk or a template. Adapters do that, behind the ports in `src/wowperf/domain/ports.py`.
- **Every finding carries a confidence badge** — `measured`, `derived` or `inferred`. A finding without one is a bug.
- **The report loads its icons and nothing else.** One HTML file, no stylesheet link, no `@import`, no remote `src`, exactly one inline script. That script may show, hide and highlight what is already on the page; it may not fetch, write text, or read storage. The single exception is icon art at `https://wow.zamimg.com/images/wow/icons/medium/` — one host, and no other. `tests/adapters/render/test_html_invariants.py` governs the raid report exactly as it governs the Mythic+ one.
- **Every href on the page** starts with `#`, `https://www.warcraftlogs.com/reports/`, or the icon host. Nothing else.
- **No new `.j2` file may contain `|sum`, `sum(`, or `{% set`**, and no new view-model field may be a bare `int`/`float` without being added to `NUMBERS_THAT_ARE_NOT_TOTALS` in `tests/adapters/render/test_html_invariants.py`. The test globs `src/wowperf/adapters/render/*.j2` unscoped, so a new raid template is covered the moment it exists.
- **Never put a real character name in `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`, `Bríala` and `Кириллица`, plus the accent-stripped spelling of one of those where a test needs two names that reduce to one slug. `tests/domain/comparison/test_spells.py` carries pre-existing fixture names outside that set; they are not this plan's to change.
- **Reports `cW38jmwdnZfbHVL4` (twenty real people) and `6Kx1P9GbNXrcLdHa` (five) name real people.** Refer to them by class, specialisation, role or index — in code, in tests, in commit messages and in documents. A character id and a realm name identify a person as surely as a name does.
- **No hardcoded season data**, and **never invent an API field name**. The verified schema reference is `.claude/skills/wcl-api/SKILL.md`, where every claim carries the date it was checked.
- **Test quality (design section 12).** This repository's failure mode is a test that could never have failed, not a wrong implementation. Every assertion here must fail against a deliberate mutation of the arithmetic or the string it claims to check, and any test reading a table, a set difference or a ranked list carries a guard asserting the collection is non-empty before asserting anything about its contents. Each task below names the mutation that must break it.
- **Commits.** Imperative mood, no `feat:`/`fix:` prefix, plain ASCII, body explains why. End every commit message with a blank line and then the fixed literal `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` — never the acting model's name. Verify with `git log -1 --format="%(trailers:key=Co-Authored-By)"`.
- **NEVER** `--no-verify`, `--no-hooks`, `--no-pre-commit-hook`.
- **Toolchain.** `uv` only. `uv run pytest`, `uv run ruff check .`, `uv run mypy` (paths come from `pyproject.toml`; pass none). On this machine `uv` is off PATH in Bash — use `/c/Users/damien/.local/bin/uv.exe` — and bare `git` is refusable under the RTK hook — use `/mingw64/bin/git`.

**Baseline at the plan's base commit `3ca97ea`:** 1880 passed, 16 deselected; ruff clean; mypy clean over 204 source files. Confirm it before Task 1 and after every task.

---

## Rulings made while writing this plan

Recorded here so an implementer does not re-litigate them, and so a reviewer can see what was decided rather than inferred.

**Ruling 1 — the raid parse axis re-mints its finding ids with the player's slug.** This reverses a decision plan 3a wrote down. `ParseSubject`'s own docstring (`src/wowperf/domain/comparison/parse_axis.py:63-70`) states: *"A raid finding keeps its plain id and names the player in its title instead, so there is no slug here to be minted, stamped or left empty by mistake."* That was sound while nothing consumed the ids. It is false the moment a page exists, for three measured reasons: `build_report` raises on duplicate ids before drawing anything (`_check_unique_finding_ids`, `src/wowperf/domain/report/build.py:40-53`); `COMPARISON_PREFIXES` routes a comparison row to a player card *by the slug the finding carries* (`src/wowperf/domain/report/players.py:64-70`), and every raid finding's slug is empty; and a finding id becomes an element id, where a duplicate is invalid HTML. **Cost if wrong:** the raid findings JSON's comparison ids gain a `.<slug>` suffix. Every consumer matches by prefix and a prefix survives anything appended to it — which is the reason the Mythic+ path chose a suffix (`src/wowperf/domain/comparison/service.py:81-93`). Task 2 rewrites that docstring; leaving it in place would be the defect, not the change.

**Ruling 2 — `PLACEMENTS` gets a raid sibling, not new entries.** `PLACEMENTS` maps a finding prefix to a *`Report` field name* — `route_rows`, `death_rows`, `group_rows`. A raid report has no `route_rows` and has two fields the Mythic+ one does not. Adding raid families to the shared tuple would file them into fields that do not exist on the model being built, and `place_rows` builds its buckets from `PLACEMENTS` itself (`src/wowperf/domain/report/ledger.py:186`). So Task 5 adds `RAID_PLACEMENTS` and a raid `place_rows` caller, and `place_rows` is narrowed to take the table it should use. **Cost if wrong:** one more small table to keep in step with the raid `Report`'s fields; the alternative silently mixes two tab vocabularies.

**Ruling 3 — which family lands on which of the seven tabs is taken from the design's own section order**, not invented here. Section 10 fixes the tab names and no more. Section 6 groups the analysers, and that grouping is the registry: 6.1 `damage.total`, 6.2 `damage.targets` and 6.7 `rank` are the Damage tab; 6.3 `casts.count`, 6.4 `casts.missing`, 6.5 `talents` and 6.6 `uptime.buffs` are per-player measures and belong on the player cards, where the equivalent Mythic+ families already go; 6.8 `mechanics.ability` and 6.9 `damage.taken.outlier` are both "what hit us" and are the Mechanics tab; 6.10 to 6.12 are Deaths. **Cost if wrong:** a row a reader looks for under the wrong heading, fixed by moving one line of `RAID_PLACEMENTS`.

**Ruling 4 — the raid golden fixture carries a real reference sample.** The Mythic+ golden fixture does not: `minimal_html()` passes `None` for `speed` and hand-authors its comparison rows as `Finding` literals, so no `compare.*` family reaches the page it renders and a wording mutation leaves `test_the_rendered_page_matches_the_golden_file` green. This was discovered by mutation during plan 3a, after the file had been cited as proof in three review briefs. Task 11 gives the raid fixture a real sample so the same hole does not reopen one slice wider. **Cost if wrong:** a slower, larger fixture. The Mythic+ golden file is not this plan's to change.

**Ruling 5 — this plan measures nothing it can read.** Plan 3a's live figures are in `.claude/skills/wcl-api/SKILL.md`, dated. Task 13's live run exists to find user-visible falsehoods that a green offline suite cannot, which is what happened on plan 3a's first live run and on plan 2's. It re-uses the warm caches from plan 3a rather than fetching cold, and states what it spent rather than projecting.

---

## What this plan does not do

- **It adds no analyser and no query.** Every figure the page draws is already computed by plans 1, 2 and 3a. The one domain change is Task 2's id minting.
- **It does not touch `analyze`.** The Mythic+ report, its golden file, its `PLACEMENTS` entries and its wording are unchanged. Any task that finds itself editing a Mythic+ string has gone wrong.
- **It adds no `--narrative` to `raid`.** Section 11 lists the raid flags and that is not among them.
- **It does not resolve the parked items from plan 3a that are not about the page**: `_boss_share` taking the first `Boss` row (`src/wowperf/domain/comparison/targets.py`) stays as it is and stays recorded, because no council fight has been read and a change on no evidence is worse than a documented unknown.

---

## File Structure

**Created**

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/report/raid_model.py` | `RaidReport`, `RaidHeader`, `RaidProvenance`-shaped fields, and `all_raid_ledger_rows`. The raid view model, beside `Report` and never inside it. |
| `src/wowperf/domain/report/raid_frame.py` | `RAID_PANELS`, `build_raid_header`, and the raid-side section gating. |
| `src/wowperf/domain/report/raid_ledger.py` | `RAID_PLACEMENTS`, `RAID_COMPARISON_PREFIXES`, `RAID_DECOMPOSITION_IDS`, `RAID_NESTS_INSIDE`. |
| `src/wowperf/domain/report/raid_build.py` | `build_raid_report` — the pure builder. |
| `src/wowperf/domain/report/raid_players.py` | `build_raid_players` — one card per raider. |
| `src/wowperf/adapters/render/raid.html.j2` | Root raid template: skeleton, header, seven-tab nav, seven includes, one script. |
| `src/wowperf/adapters/render/_raid_summary.html.j2` | Summary tab. |
| `src/wowperf/adapters/render/_raid_damage.html.j2` | Damage tab. |
| `src/wowperf/adapters/render/_raid_mechanics.html.j2` | Mechanics tab. |
| `src/wowperf/adapters/render/_raid_provenance.html.j2` | Provenance tab, raid vocabulary. |
| `tests/domain/report/test_raid_build.py` | The builder's tests. |
| `tests/domain/report/test_raid_ledger.py` | The registry's tests. |
| `tests/adapters/render/test_raid_html_invariants.py` | The raid page's invariants. |
| `tests/adapters/render/golden/raid.html` | The raid golden file. |

**Modified**

| File | Change |
| --- | --- |
| `src/wowperf/domain/report/players.py` | `slugs_by_actor` narrowed from `Run` to a roster (Task 1). |
| `src/wowperf/domain/comparison/parse_axis.py` | `ParseSubject` gains `slug`; its docstring is rewritten (Task 2). |
| `src/wowperf/domain/analysis/encounter_service.py` | The parse loop re-mints per player (Task 2). |
| `src/wowperf/domain/report/ledger.py` | `place_rows` takes its placement table (Task 5). |
| `src/wowperf/adapters/render/html.py` | `render_raid` beside `render` (Task 9). |
| `src/wowperf/adapters/render/report.css.j2` | Rules the Damage and Mechanics tabs need, if any (Task 8). |
| `src/wowperf/cli.py` | `raid` writes the HTML (Task 12). |
| `tests/e2e/test_raid_e2e.py` | The `--all-players` collision test (Task 13). |
| `.claude/skills/wcl-api/SKILL.md` | The live run's reading (Task 14). |
| `CLAUDE.md` | The repository overview's report paragraph, and the raid report's own line in the commands table (Task 14). |

---

## Task 1: Narrow `slugs_by_actor` to the roster it reads

A raid has no `Run`, and this function reads only `run.players`. Narrowing it is the same move plan 3a made on `ParseMember` and `casts_in`, and it is the whole of what a raid needs from it. Nothing else in this task.

**Files:**
- Modify: `src/wowperf/domain/report/players.py:93-113`
- Modify: every caller (find them in step 1)
- Test: `tests/domain/report/test_players.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `slugs_by_actor(players: tuple[Player, ...]) -> dict[int, str]`. Task 2 calls it with `encounter.players`.

- [ ] **Step 1: Find every caller**

```bash
grep -rn "slugs_by_actor" src/ tests/
```

Record the list. Every one of them currently passes a `Run` and becomes `<expr>.players`.

- [ ] **Step 2: Write the failing test**

Append to `tests/domain/report/test_players.py`:

```python
def test_a_roster_is_all_the_slugs_need() -> None:
    """The function reads `players` and nothing else, so it takes `players`.

    A raid has no `Run` to hand it. Narrowing rather than widening is this
    project's rule at every seam plan 3a touched, and the alternative --
    a second function, or an `Encounter | Run` union -- leaves the wrong
    argument representable.
    """
    players = (
        Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane"),
        Player(actor_id=12, name="Stonewake", class_name="DeathKnight", spec="Blood"),
    )

    slugs = slugs_by_actor(players)

    assert slugs == {11: "emberkin-0", 12: "stonewake-1"}


def test_two_names_that_reduce_to_one_slug_stay_apart() -> None:
    """`Bríala` and `Briala` decompose to the same slug, so the index separates them.

    The index is the roster's own order, not the order cards are drawn in, so
    a deep link survives a re-run that named a different subject. Without the
    suffix both players own the fragment id `briala` and the page sends every
    link to whichever the browser picks first.
    """
    players = (
        Player(actor_id=21, name="Bríala", class_name="Priest", spec="Discipline"),
        Player(actor_id=22, name="Briala", class_name="Priest", spec="Shadow"),
    )

    slugs = slugs_by_actor(players)

    assert slugs[21] != slugs[22]
    assert set(slugs.values()) == {"briala-0", "briala-1"}
```

- [ ] **Step 3: Run it and watch it fail**

```bash
uv run pytest tests/domain/report/test_players.py -k "roster_is_all_the_slugs or reduce_to_one_slug" -v
```

Expected: FAIL — `slugs_by_actor()` receives a tuple where it expects a `Run` and raises `AttributeError: 'tuple' object has no attribute 'players'`.

- [ ] **Step 4: Narrow the signature**

In `src/wowperf/domain/report/players.py`, change the signature and the one line that dereferences:

```python
def slugs_by_actor(players: tuple[Player, ...]) -> dict[int, str]:
```

and inside it, `display_names(players)` and `enumerate(players)` in place of `display_names(run.players)` and `enumerate(run.players)`. Keep the docstring; add one sentence to it saying the function takes a roster because both a run and an encounter have one and neither is what it reads.

- [ ] **Step 5: Update every caller from step 1**

Each becomes `slugs_by_actor(<expr>.players)`. Do not change any other line at those call sites.

- [ ] **Step 6: Run the whole suite**

```bash
uv run pytest
```

Expected: 1882 passed, 16 deselected. Then `uv run ruff check .` and `uv run mypy`, both clean.

- [ ] **Step 7: Mutation check — the test must be able to fail**

Delete the `-{index}` from the returned f-string in `slugs_by_actor`. `test_two_names_that_reduce_to_one_slug_stay_apart` must fail. Restore it.

- [ ] **Step 8: Commit**

```bash
git add src/wowperf/domain/report/players.py tests/domain/report/test_players.py
git commit -m "$(cat <<'EOF'
Take a roster where a slug map read only a roster

A raid encounter has no Run to offer this function, and the function never
wanted one: it reads the player list and nothing else. Narrowing at the seam
is what plan 3a did to ParseMember and casts_in, and it keeps one slug map
serving both commands instead of two that can drift.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Mint one finding id per raider on the raid parse axis

The load-bearing task. Nothing downstream can draw a page until this is done: `build_report` raises on duplicate ids, and a comparison row is routed to a player's card by the slug the finding carries. Measured on plan 3a's own live `--all-players` run (`cW38jmwdnZfbHVL4` fight 2, twenty raiders): **266 findings, 79 distinct ids, 206 findings sharing an id across 19 families, and `player_slug` empty on all 266.**

**Files:**
- Modify: `src/wowperf/domain/comparison/parse_axis.py:63-86` (`ParseSubject`)
- Modify: `src/wowperf/domain/analysis/encounter_service.py:98-115` (the parse loop)
- Modify: `src/wowperf/cli.py:966` (`_parse_samples`, which builds the subjects)
- Test: `tests/domain/analysis/test_encounter_service.py`

**Interfaces:**
- Consumes: `slugs_by_actor(players)` from Task 1.
- Produces: every finding `compare_parse_axis` returns carries `player_slug=<slug>` and an id ending `.<slug>`. Tasks 5, 6 and 7 rely on both.

- [ ] **Step 1: Write the failing test**

Create or append to `tests/domain/analysis/test_encounter_service.py`:

```python
def test_two_raiders_compared_at_once_never_share_a_finding_id() -> None:
    """Under `--all-players` each subject's comparison is its own row.

    Two subjects reach `compare_parse_axis` through the same loop, and the
    comparison modules know nothing about who else is in the raid -- they mint
    `compare.talents` and the loop appends the player. Without that the two
    calls return the identical id twice, `build_raid_report` refuses the list,
    and the page could not key an element id on one anyway.
    """
    encounter, loaded = a_two_raider_encounter()
    subjects = two_comparable_subjects(encounter)

    findings = analyse_encounter(
        loaded, NO_DEFENSIVES, NO_CONSUMABLES, parse_subjects=subjects
    )

    compared = [f for f in findings if f.id.startswith("compare.")]
    assert compared, "the fixture produced no comparison findings to distinguish"
    ids = [f.id for f in compared]
    assert len(ids) == len(set(ids)), sorted(i for i in ids if ids.count(i) > 1)


def test_every_compared_finding_names_the_raider_it_is_about() -> None:
    """The slug is a field as well as a suffix, because two consumers read it.

    `RAID_COMPARISON_PREFIXES` routes a row to a card by `player_slug`, and the
    page anchors `#finding-...` on the id. A suffix with no field leaves the
    first consumer matching nothing, and a field with no suffix leaves the
    second with duplicate element ids.
    """
    encounter, loaded = a_two_raider_encounter()
    subjects = two_comparable_subjects(encounter)

    findings = analyse_encounter(
        loaded, NO_DEFENSIVES, NO_CONSUMABLES, parse_subjects=subjects
    )

    compared = [f for f in findings if f.id.startswith("compare.")]
    assert compared, "the fixture produced no comparison findings to distinguish"
    slugs = {subject.slug for subject in subjects}
    for finding in compared:
        assert finding.player_slug in slugs, finding.id
        assert finding.id.endswith(f".{finding.player_slug}"), finding.id


def test_two_raiders_whose_names_reduce_to_one_slug_stay_apart() -> None:
    """The defect the last whole-branch review found, at the layer above it.

    Plan 3a joined a rankings row on a disambiguated display name and told a
    duplicate-named raider their kill was not a kill. The same two raiders
    reach this loop, and here the failure would be quieter: both cards would
    draw the same rows under two names.
    """
    encounter, loaded = a_two_raider_encounter(names=("Bríala", "Briala"))
    subjects = two_comparable_subjects(encounter)

    findings = analyse_encounter(
        loaded, NO_DEFENSIVES, NO_CONSUMABLES, parse_subjects=subjects
    )

    compared = [f for f in findings if f.id.startswith("compare.")]
    assert compared, "the fixture produced no comparison findings to distinguish"
    ids = [f.id for f in compared]
    assert len(ids) == len(set(ids))
    assert len({f.player_slug for f in compared}) == 2
```

Write `a_two_raider_encounter(names=...)` and `two_comparable_subjects(encounter)` as module-level helpers in the same file, building a `LoadedEncounter` with two roster members and a `ParseSample` with enough members that both subjects reach the real comparison rather than an `unavailable` finding. Use only sanctioned names. Assert inside `two_comparable_subjects` that the sample it returns is non-empty, so a fixture that stopped producing comparisons fails loudly rather than passing three tests vacuously.

- [ ] **Step 2: Run them and watch them fail**

```bash
uv run pytest tests/domain/analysis/test_encounter_service.py -k "never_share_a_finding_id or names_the_raider or reduce_to_one_slug" -v
```

Expected: FAIL. The first on duplicate ids, the second on `player_slug` being `""`, the third on both.

- [ ] **Step 3: Give `ParseSubject` its slug**

In `src/wowperf/domain/comparison/parse_axis.py`, add the field and **replace the second paragraph of the docstring**, which currently argues the opposite:

```python
class ParseSubject(Frozen):
    """One player to measure against the world, and everything that measurement reads.

    A sibling of `service.ComparisonSubject`, not a reuse of it: that one carries
    a whole `LoadedRun` behind it. The slug is here for the same reason it is
    there -- a report card is matched by it, and a finding id becomes an element
    id on the page, where two raiders sharing one id is invalid HTML. It is
    minted from the roster by `slugs_by_actor`, never from the display name,
    because two names can reduce to one slug and the roster index is what keeps
    them apart.

    Every field but the player and the slug is what an adapter fetched, arriving
    as a value: the domain performs no I/O, and each of these is one query
    somebody paid for. An empty default is the honest reading of "not fetched"
    for all of them -- `compare_parse_axis` says so in the tool's own words
    rather than treating an empty sample as a clean result.
    """

    player: Player
    slug: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    ...
```

`slug` has no default: a subject built without one must not compile past mypy, which is the whole reason for the field.

- [ ] **Step 4: Re-mint in the loop**

In `src/wowperf/domain/analysis/encounter_service.py`, add the sibling of `comparison/service.py:81-93` beside the loop:

```python
def _for_raider(findings: list[Finding], slug: str) -> list[Finding]:
    """Re-mint plain comparison ids as one raider's own.

    The comparison modules know nothing about who else is in the raid, so they
    mint `compare.talents` and this appends the player. Doing it in one place
    is what keeps six modules from each having to be told about the roster, and
    it is why the id is a suffix: every consumer of these ids matches by prefix,
    and a prefix survives anything appended to it.

    The Mythic+ path does the same thing at `comparison/service.py:_for_player`.
    Two call sites rather than one shared helper, because the two loops carry
    different subject types and a shared helper would need a protocol to
    describe a `str` field.
    """
    return [
        finding.model_copy(update={"id": f"{finding.id}.{slug}", "player_slug": slug})
        for finding in findings
    ]
```

and change the loop body to wrap its result:

```python
    for subject in parse_subjects:
        findings += _for_raider(
            compare_parse_axis(
                subject.player,
                subject.display_name,
                ...
            ),
            subject.slug,
        )
```

- [ ] **Step 5: Fill the slug where subjects are built**

In `src/wowperf/cli.py`'s `_parse_samples` (line 966), compute `slugs = slugs_by_actor(encounter.players)` once before the loop and pass `slug=slugs[player.actor_id]` into each `ParseSubject`. Do not compute a slug from the display name.

- [ ] **Step 6: Run the tests, then the suite**

```bash
uv run pytest tests/domain/analysis/test_encounter_service.py -v
uv run pytest
```

Expected: the three new tests pass; the suite passes with the three added. Fix any test that constructed a `ParseSubject` without a slug by giving it one — do not give the field a default to avoid the work.

- [ ] **Step 7: Mutation check**

Three separate mutations, each of which must break a named test:

1. Drop `f"{finding.id}.{slug}"` back to `finding.id` → `test_two_raiders_compared_at_once_never_share_a_finding_id` fails.
2. Drop `"player_slug": slug` from the update → `test_every_compared_finding_names_the_raider_it_is_about` fails.
3. In `cli.py`, pass `slug=player_slug(subject.display_name)` instead of the roster slug → `test_two_raiders_whose_names_reduce_to_one_slug_stay_apart` fails (write the equivalent mutation directly in the test fixture if the CLI is not under test here).

Restore all three.

- [ ] **Step 8: Commit**

```bash
git add src/wowperf/domain/comparison/parse_axis.py src/wowperf/domain/analysis/encounter_service.py src/wowperf/cli.py tests/domain/analysis/test_encounter_service.py
git commit -m "$(cat <<'EOF'
Mint a comparison finding id per raider

Plan 3a left every raid comparison id plain and said so in ParseSubject's
docstring, which was true while nothing consumed the ids. A page consumes
them three ways: the builder refuses a duplicate outright, a card is matched
to its rows by the slug the finding carries, and a finding id becomes an
element id, where two raiders sharing one is invalid HTML. One live run at
twenty raiders produced 206 findings sharing an id across 19 families.

The slug comes from the roster rather than the display name, because two
names can reduce to one slug and only the roster index keeps them apart.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: A raid header, and a difficulty a reader can read

Design section 10: *"The header prints boss, difficulty by name, kill or best percentage, and the partition."* `Header` carries `dungeon`, `keystone_level` and `affixes` (`src/wowperf/domain/report/model.py:624-630`) and has no field that means any of those, so the raid header is a type of its own.

`Encounter.difficulty` is an `int` (`src/wowperf/domain/encounter.py:36`). **No name for it exists anywhere in this repository** — searched `src/`, `data/` and `.claude/skills/wcl-api/SKILL.md` on 2026-09-15.

**Files:**
- Create: `src/wowperf/domain/report/raid_frame.py`
- Modify: `data/season.toml` (only if step 1 says so)
- Test: `tests/domain/report/test_raid_frame.py`

**Interfaces:**
- Consumes: `Encounter` (`src/wowperf/domain/encounter.py`).
- Produces: `RaidHeader` and `build_raid_header(encounter: Encounter) -> RaidHeader`. Task 4 puts `RaidHeader` on the model; Task 8's template prints it.

- [ ] **Step 1: Find out whether the API names a difficulty, before writing a table**

Read `.claude/skills/wcl-api/SKILL.md` first, then introspect the live schema for a field that returns a difficulty's name (start from `worldData`, which already supplies zones and encounters at runtime, and from `ReportFight`). **Do not guess a field name.**

- If one exists: resolve the name at runtime through the adapter, add a dated row to the skill file's table, and skip step 2. The invariant is "no hardcoded season data" and an API source always wins.
- If none exists: this is a constant with no API source, so step 2 applies. Record the negative result in the skill file with the date — a search that came back empty is worth exactly as much as one that did not, and the next person should not repeat it.

- [ ] **Step 2 (only if step 1 found nothing): Add the mapping where constants live**

In `data/season.toml`, under the existing `[raid]` table:

```toml
# Warcraft Logs' own difficulty numbers for a raid encounter. The API takes
# `difficulty` as a request argument and echoes no name for it (verified
# 2026-09-15; `fightRankings` echoes no `difficulty` per row at all, recorded
# in the skill file on 2026-09-14). A report that printed the number would be
# asking its reader to know the table.
[raid.difficulty_names]
3 = "Normal"
4 = "Heroic"
5 = "Mythic"
verified = "2026-09-15"
```

**Verify each number against a live fight before writing it down.** Plan 3a's own measurements ran at `difficulty: 4`; confirm from a report whose difficulty is known what that number is called on the Warcraft Logs page, and only then record it. An unverified row here is exactly the invented technical detail `CLAUDE.md` forbids. If a number cannot be verified, omit it — step 3's fallback covers it.

- [ ] **Step 3: Write the failing test**

Create `tests/domain/report/test_raid_frame.py`:

```python
def test_a_kill_reads_as_a_kill_and_names_its_difficulty() -> None:
    encounter = an_encounter(kill=True, difficulty=5, fight_percentage=0.0, partition=1)

    header = build_raid_header(encounter)

    assert header.boss == "Emberkin"
    assert header.difficulty == "Mythic"
    assert header.outcome == "Killed"
    assert header.partition == "Partition 1"


def test_a_wipe_states_how_far_the_raid_got() -> None:
    """A wipe's headline is the best percentage, because there is no kill to state.

    `fight_percentage` is the boss's remaining health at the end of the
    attempt, so the figure a reader wants is what is left, stated as such
    rather than subtracted into a progress number the log never recorded.
    """
    encounter = an_encounter(kill=False, difficulty=5, fight_percentage=12.4, partition=1)

    header = build_raid_header(encounter)

    assert header.outcome == "Wiped at 12.4% remaining"


def test_a_difficulty_nobody_recorded_prints_the_number_rather_than_a_guess() -> None:
    """An unmapped difficulty says what it knows, and does not invent a name.

    The table is hand-maintained and dated. A number it does not carry means
    the table is stale, and a report that guessed `Heroic` for it would be
    confidently wrong -- which is the one thing the badges exist to prevent.
    """
    encounter = an_encounter(kill=True, difficulty=99, fight_percentage=0.0, partition=1)

    header = build_raid_header(encounter)

    assert header.difficulty == "Difficulty 99"
```

Write `an_encounter(**kwargs)` as a module-level helper building a minimal `Encounter` with `boss_name="Emberkin"`.

- [ ] **Step 4: Run them and watch them fail**

```bash
uv run pytest tests/domain/report/test_raid_frame.py -v
```

Expected: FAIL with `ImportError` / `NameError` — `build_raid_header` does not exist.

- [ ] **Step 5: Write the header**

In `src/wowperf/domain/report/raid_frame.py`, with the two ABOUTME lines every file here carries:

```python
class RaidHeader(Frozen):
    boss: str
    difficulty: str
    outcome: str
    partition: str
    size: int
```

and `build_raid_header(encounter: Encounter) -> RaidHeader`, whose outcome is `"Killed"` when `encounter.kill` and `f"Wiped at {encounter.fight_percentage:.1f}% remaining"` otherwise, and whose difficulty falls back to `f"Difficulty {encounter.difficulty}"` when the table has no entry. `size` is an `int` on a view model, so add it to `NUMBERS_THAT_ARE_NOT_TOTALS` in `tests/adapters/render/test_html_invariants.py` in the same commit — it is a raid size, never a summable duration.

- [ ] **Step 6: Run the suite, ruff and mypy**

- [ ] **Step 7: Mutation check**

Change the fallback to return `"Heroic"` for an unknown difficulty. `test_a_difficulty_nobody_recorded_prints_the_number_rather_than_a_guess` must fail. Change `:.1f` to `:.0f`; the wipe test must fail. Restore both.

- [ ] **Step 8: Commit**

```bash
git add src/wowperf/domain/report/raid_frame.py tests/domain/report/test_raid_frame.py data/season.toml tests/adapters/render/test_html_invariants.py
git commit -m "$(cat <<'EOF'
Head a raid report with the fight rather than a keystone

Header carries a dungeon, a keystone level and affixes, none of which a boss
fight has. The raid header states what design section 10 asks for: the boss,
the difficulty by name, whether it died or how much of it was left, and the
partition the leaderboard was read at.

The difficulty numbers are hand-maintained with a verified date because the
API takes difficulty as an argument and echoes no name for it. A number the
table does not carry prints as a number: a report that guessed would be
confidently wrong, which is the failure the badges exist to prevent.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: The raid view model and its one row-walking authority

Design section 10: *"A raid report needs a model of its own rather than empty stand-ins in the Mythic+ one."* Seven tabs, and one function that names every field holding rows so a caller cannot reach six of the seven and lose the seventh in silence.

**Files:**
- Create: `src/wowperf/domain/report/raid_model.py`
- Test: `tests/domain/report/test_raid_model.py`

**Interfaces:**
- Consumes: `RaidHeader` (Task 3); `LedgerRow`, `Section`, `DeathCard`, `PlayerCard`, `Provenance` from `src/wowperf/domain/report/model.py`, reused whole.
- Produces: `RaidReport` and `all_raid_ledger_rows(report: RaidReport) -> Iterator[LedgerRow]`. Task 7 builds one; Task 9's renderer walks it for icons.

- [ ] **Step 1: Write the failing test**

Create `tests/domain/report/test_raid_model.py`:

```python
def test_every_field_holding_rows_is_walked() -> None:
    """The walker is the icon resolver's only map of the page.

    A row whose ability reaches the page without reaching the resolver draws
    nothing and reports nothing -- the failure is a missing picture, which no
    other test would see. So the walker is checked against the model's own
    fields rather than against a list somebody kept in step by hand.
    """
    row_fields = {
        name
        for name, field in RaidReport.model_fields.items()
        if field.annotation == tuple[LedgerRow, ...]
    }
    assert row_fields, "no field on the model holds rows at all"

    report = a_raid_report_with_one_row_in_every_field(row_fields)
    walked = {row.finding_id for row in all_raid_ledger_rows(report)}

    assert walked == {f"finding-in-{name}" for name in row_fields}
```

`a_raid_report_with_one_row_in_every_field` builds a `RaidReport` putting exactly one `LedgerRow` with `finding_id=f"finding-in-{name}"` into each named field. Written this way the test cannot go stale: a field added in a later task and not walked fails it immediately.

- [ ] **Step 2: Run it and watch it fail**

Expected: FAIL — `RaidReport` does not exist.

- [ ] **Step 3: Write the model**

```python
class RaidReport(Frozen):
    header: RaidHeader
    # Figures that contain others, heading the Summary.
    ledger_decomposition: tuple[LedgerRow, ...]
    # The biggest findings, in ranked order. Each equals its card on another
    # tab; the Summary renders a link to that card, never a second card.
    summary_pointers: tuple[LedgerRow, ...] = ()
    # The external frame's throughput half: damage against the sample, where it
    # went, and the percentile. Design section 6.1, 6.2 and 6.7.
    damage_rows: tuple[LedgerRow, ...] = ()
    # Withheld on an attempt that did not kill, with the reason the reader needs.
    damage: Section
    # What hit the raid, and who took more of it than the rest. Sections 6.8 and 6.9.
    mechanics_rows: tuple[LedgerRow, ...] = ()
    deaths: tuple[DeathCard, ...]
    death_rows: tuple[LedgerRow, ...] = ()
    interrupts: tuple[LedgerRow, ...]
    players: tuple[PlayerCard, ...]
    group_rows: tuple[LedgerRow, ...] = ()
    # Every finding no field above claimed -- a structural catch-all, not a
    # whitelist of its own. See `build_observations`.
    observations: tuple[LedgerRow, ...]
    provenance: Provenance
```

and `all_raid_ledger_rows`, yielding from every `tuple[LedgerRow, ...]` field above in tab order.

- [ ] **Step 4: Run the test, the suite, ruff and mypy**

- [ ] **Step 5: Mutation check**

Delete one `yield from` line in `all_raid_ledger_rows`. The test must fail and must name the field it lost. Restore it.

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/report/raid_model.py tests/domain/report/test_raid_model.py
git commit -m "$(cat <<'EOF'
Give a raid report a model of its own

Design section 10 asks for a model rather than empty stand-ins in the Mythic+
one, and the two pages genuinely differ: a raid has no route and no tempo, and
has a damage tab and a mechanics tab the dungeon report has no figures for.
Everything below the model is reused whole -- the rows, the badges, the
tooltips, the sections, the death cards and the player cards.

The row walker is checked against the model's own fields rather than a list
kept in step by hand, because the failure it guards is a missing icon, which
nothing else would notice.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: The raid placement registry

Where each finding family lands, for a page whose fields are not the Mythic+ page's. Ruling 2 says this is a sibling table; Ruling 3 says the mapping comes from design section 6's own grouping.

**Files:**
- Create: `src/wowperf/domain/report/raid_ledger.py`
- Modify: `src/wowperf/domain/report/ledger.py:175-193` (`place_rows` takes its table)
- Test: `tests/domain/report/test_raid_ledger.py`

**Interfaces:**
- Consumes: `place_rows`, `build_observations`, `collapse_repeated_details` from `ledger.py`.
- Produces: `RAID_PLACEMENTS`, `RAID_COMPARISON_PREFIXES`, `RAID_DECOMPOSITION_IDS`, `RAID_NESTS_INSIDE`. Tasks 6 and 7 read all four.

- [ ] **Step 1: Write the failing test**

Create `tests/domain/report/test_raid_ledger.py`:

```python
RAID_FAMILIES = (
    "deaths.total", "deaths.single.0", "deaths.chain.0", "deaths.repeat.emberkin",
    "defensives.never.emberkin.0", "defensives.ceiling.emberkin.0",
    "defensives.unused.emberkin", "consumables.never.emberkin",
    "consumables.unused.emberkin", "interrupts.summary", "interrupts.ability.0",
    "mechanics.ability.0", "players.damage.0",
    "compare.damage.total.emberkin-0", "compare.damage.targets.emberkin-0",
    "compare.rank.emberkin-0", "compare.parse.unavailable.emberkin-0",
    "compare.spells.missing.0.emberkin-0", "compare.spells.rate.0.emberkin-0",
    "compare.spells.above.0.emberkin-0", "compare.spells.level.emberkin-0",
    "compare.talents.emberkin-0", "compare.uptime.self.0.emberkin-0",
    "compare.uptime.unjudged.emberkin-0",
)
"""Every family `analyse_encounter` can emit, as it is emitted after Task 2.

Enumerated rather than generated: a family this list forgets is a row that
falls silently through to `observations`, which is a tab a reader does not
look under for it. `test_the_family_list_matches_what_the_service_emits`
below holds the list against the service.
"""


def test_every_raid_family_lands_somewhere_deliberate() -> None:
    """No raid family reaches the catch-all by accident.

    `build_observations` is a structural catch-all so a new family is never
    dropped, which is right -- but every family this slice already emits has a
    tab it belongs on, and falling through means nobody chose.
    """
    for finding_id in RAID_FAMILIES:
        placed = _raid_field_for(finding_id)
        on_a_card = any(
            finding_id.startswith(prefix) for prefix in RAID_COMPARISON_PREFIXES
        )
        assert placed is not None or on_a_card, finding_id


def test_the_mechanics_family_is_placed_at_all() -> None:
    """The defect this task exists to fix, named on its own.

    Plan 2 shipped `mechanics.ability.*` and the shared `PLACEMENTS` has no
    `mechanics.` prefix, so on a page built from the Mythic+ table every
    mechanics finding falls through to the observations catch-all.
    """
    assert _raid_field_for("mechanics.ability.0") == "mechanics_rows"


def test_the_throughput_families_reach_the_damage_tab() -> None:
    """Design section 6 groups 6.1, 6.2 and 6.7 together, and so does the page."""
    assert _raid_field_for("compare.damage.total.emberkin-0") == "damage_rows"
    assert _raid_field_for("compare.damage.targets.emberkin-0") == "damage_rows"
    assert _raid_field_for("compare.rank.emberkin-0") == "damage_rows"


def test_no_broader_prefix_sits_ahead_of_a_narrower_one() -> None:
    """`PLACEMENTS` resolves by first match, so order is the whole rule.

    A broader prefix ahead of a narrower one silently wins and files a row on
    the wrong tab. `defensives.unused.` is a death-shaped claim and must beat
    the bare `defensives.`; the shared table documents exactly this hazard.
    """
    for index, (prefix, _) in enumerate(RAID_PLACEMENTS):
        for later_prefix, _ in RAID_PLACEMENTS[index + 1:]:
            assert not later_prefix.startswith(prefix) or later_prefix == prefix, (
                f"{later_prefix!r} is narrower than {prefix!r} but sits after it"
            )


def test_the_family_list_matches_what_the_service_emits() -> None:
    """Holds `RAID_FAMILIES` against the service, so the list cannot go stale.

    Built from a fixture rich enough to emit every family -- a kill, two
    compared raiders, deaths, a mechanics sample. A family the fixture cannot
    reach is a family this test does not cover, so the assertion is that the
    service emits nothing outside the list, and the guard below is that the
    fixture emitted a useful number of families at all.
    """
    findings = analyse_encounter(*a_rich_encounter())
    emitted = {_family(finding.id) for finding in findings}
    assert len(emitted) >= 8, sorted(emitted)
    assert emitted <= {_family(known) for known in RAID_FAMILIES}, sorted(
        emitted - {_family(known) for known in RAID_FAMILIES}
    )
```

`_family` reduces an id to its placement-relevant prefix; `_raid_field_for` is the raid sibling of `ledger.py`'s private `_field_for`, exported from `raid_ledger.py` for this test.

- [ ] **Step 2: Run them and watch them fail**

- [ ] **Step 3: Write the registry**

```python
RAID_DECOMPOSITION_IDS = ("deaths.total",)
"""A raid has one figure that contains others. `compare.duration` and
`time.residual` are keystone shapes with no raid meaning."""

RAID_NESTS_INSIDE = (
    ("deaths.single.", "deaths.total"),
    ("deaths.chain.", "deaths.total"),
    ("deaths.repeat.", "deaths.total"),
)

RAID_PLACEMENTS: tuple[tuple[str, str], ...] = (
    ("defensives.unused.", "death_rows"),
    ("consumables.", "death_rows"),
    ("deaths.", "death_rows"),
    ("mechanics.", "mechanics_rows"),
    ("players.damage.", "mechanics_rows"),
    ("interrupts.", "interrupts"),
    ("compare.damage.", "damage_rows"),
    ("compare.rank", "damage_rows"),
    ("defensives.", "group_rows"),
)
"""Which tab's rows a raid finding family lands in: the first prefix that matches wins.

Order is the rule, and the narrow families come first, exactly as in the
Mythic+ table beside this one: `defensives.unused.` is a death-shaped claim
while `defensives.ceiling.` and `defensives.never.` are claims about the whole
fight and fall through to the bare `defensives.`.

`players.damage.` sits on the mechanics tab rather than a player card, unlike
Mythic+: design section 6.9 measures it per ability against the group median,
which is the same question section 6.8 asks, and the two read together.

The per-card families are in `RAID_COMPARISON_PREFIXES` and are deliberately
absent here, as they are in the Mythic+ table.
"""

RAID_COMPARISON_PREFIXES = (
    "compare.spells.",
    "compare.talents",
    "compare.uptime.",
    "compare.gear.",
    "compare.stats.",
    "compare.consumables.",
    "compare.parse.unavailable",
)
"""Families that belong on a raider's card rather than in the ledger.

Which card is decided by the slug the finding carries, never by who the
subject is -- Task 2 is what puts a slug on every one of them.
`compare.parse.unavailable` is here rather than in the Mythic+ table's
`group_rows`, because on a wipe every raider gets one and a single shared row
beneath the cards would say it once for twenty people.
"""
```

- [ ] **Step 4: Let `place_rows` take its table**

In `src/wowperf/domain/report/ledger.py`, give `place_rows` and `_field_for` a `placements: tuple[tuple[str, str], ...] = PLACEMENTS` keyword argument, defaulting to the Mythic+ table so no existing caller changes. Do not add a branch on which command is running; the table is the argument.

- [ ] **Step 5: Run everything, then the mutation check**

Move `("defensives.", "group_rows")` above `("defensives.unused.", "death_rows")` — `test_no_broader_prefix_sits_ahead_of_a_narrower_one` must fail. Delete the `("mechanics.", "mechanics_rows")` row — `test_the_mechanics_family_is_placed_at_all` must fail. Restore both.

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/report/raid_ledger.py src/wowperf/domain/report/ledger.py tests/domain/report/test_raid_ledger.py
git commit -m "$(cat <<'EOF'
Place every raid finding family on a tab somebody chose

The shared placement table maps a family to a Report field name, and a raid
report has fields the dungeon report does not and lacks the ones it routes to.
So the raid table is a sibling and place_rows takes the table it should use
rather than branching on which command is running.

This also closes two families that had no placement anywhere: the mechanics
findings plan 2 shipped, which fell through to the observations catch-all, and
the throughput half plan 3a shipped, which had no tab to fall to at all.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: One card per raider

`build_players` is written against `LoadedRun` and reads `run.pulls` for its timeline and its trash-packs comparison table, neither of which a boss fight has. The raid card is a narrower sibling: the player's facts, their comparison section, and the tables that are not route-shaped.

**Files:**
- Create: `src/wowperf/domain/report/raid_players.py`
- Test: `tests/domain/report/test_raid_players.py`

**Interfaces:**
- Consumes: `RAID_COMPARISON_PREFIXES` (Task 5), `slugs_by_actor` (Task 1), `PlayerCard` and `_comparison_section`'s three states from `players.py`.
- Produces: `build_raid_players(loaded: LoadedEncounter, findings: Sequence[Finding], subject: Player, compared_slugs: frozenset[str] | None, ...) -> tuple[PlayerCard, ...]`. Task 7 calls it.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_raiders_rows_land_on_their_own_card() -> None:
    """Routed by the slug the finding carries, never by who the subject is.

    A raid compares twenty people at once, so routing to the subject's card
    would put nineteen raiders' rows under one name.
    """
    cards = build_raid_players(*two_compared_raiders())

    by_slug = {card.slug: card for card in cards}
    assert set(by_slug) == {"emberkin-0", "stonewake-1"}
    for slug, card in by_slug.items():
        ids = [row.finding_id for row in comparison_rows(card)]
        assert ids, f"{slug} drew no comparison rows at all"
        assert all(finding_id.endswith(f".{slug}") for finding_id in ids), ids


def test_the_card_nobody_asked_for_says_so_rather_than_looking_clean() -> None:
    """Three states, and the difference between them is the whole point.

    A raider nobody named, a raider whose leaderboard offered nothing, and a
    raider compared and found level are three different pages. Silence reads
    as the third.
    """
    cards = build_raid_players(*one_compared_one_not())

    asked, not_asked = cards[0], cards[1]
    assert NOT_REQUESTED in not_asked.comparison.withheld_reason
    assert not_asked.comparison.present is False
    assert asked.comparison.present is True


def test_a_wipe_tells_every_raider_why_their_comparison_is_empty() -> None:
    """Design section 13: an empty section teaches nothing.

    Warcraft Logs computes no rankings row for an attempt that did not kill,
    so the external frame is withheld for everybody -- and the page has to say
    that, in words, on each card.
    """
    cards = build_raid_players(*a_wiped_attempt())

    assert cards, "the fixture built no cards"
    for card in cards:
        ids = [row.finding_id for row in comparison_rows(card)]
        assert any(
            finding_id.startswith("compare.parse.unavailable") for finding_id in ids
        ), card.slug
```

- [ ] **Step 2: Run them and watch them fail**

- [ ] **Step 3: Write the builder**

Follow `players.py`'s shape: `slugs_by_actor(encounter.players)` for the fragment ids, `_comparison_section`'s three-state logic reused rather than re-derived, and a per-card row list filtered by `RAID_COMPARISON_PREFIXES` **and** by `finding.player_slug == slug`. Do not build a timeline: a boss fight has no pulls to band, and a timeline with one band is a chart that says nothing. Do not build the trash-packs comparison table.

If `_comparison_section` cannot be reused without reading a `Run`, narrow it in this task the way Task 1 narrowed `slugs_by_actor` — take the values it reads, not the aggregate — rather than copying it.

- [ ] **Step 4: Run everything, then the mutation check**

Drop the `finding.player_slug == slug` half of the filter, keeping the prefix half. `test_a_raiders_rows_land_on_their_own_card` must fail, because every card would carry both raiders' rows. Restore it.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/domain/report/raid_players.py tests/domain/report/test_raid_players.py
git commit -m "$(cat <<'EOF'
Draw a card for every raider

The Mythic+ card builder reads run.pulls for its timeline and for its trash
packs table, and a boss fight has neither. The raid card is the narrower
sibling: the raider's facts, their comparison section in whichever of its
three states it is in, and the tables that are not route shaped.

A row reaches a card by the slug it carries rather than by who the subject is.
Comparing twenty people at once is the case that makes the difference: routed
to the subject, nineteen raiders' rows would sit under one name.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `build_raid_report`

The pure builder that decides every judgement the page makes, so the template decides nothing.

**Files:**
- Create: `src/wowperf/domain/report/raid_build.py`
- Test: `tests/domain/report/test_raid_build.py`

**Interfaces:**
- Consumes: Tasks 3 to 6 whole.
- Produces: `build_raid_report(loaded: LoadedEncounter, findings: Sequence[Finding], subject: Player, compared_slugs: frozenset[str] | None, fetched_at: str, defensives: Defensives, consumables: Consumables, externals: Externals = Externals(), self_resurrections: SelfResurrections = SelfResurrections(), reference_records: tuple[ReferenceRecord, ...] = (), comparison_measures: Mapping[str, PlayerMeasures] = NO_MEASURES) -> RaidReport`. Task 12's CLI calls it.

No `narrative` parameter: section 11 does not give `raid` that flag. No `speed`: there is no route to compare. No `throughput`: `--throughput-ceiling` is not a raid flag either.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_builder_refuses_two_findings_that_share_an_id() -> None:
    """The gate Task 2 exists to get through, asserted rather than assumed.

    A duplicate id silently loses a title from `titles_by_id` and sends every
    pointer at it to the wrong row. Raising here is what turned a defect that
    shipped three times into one that cannot ship again.
    """
    loaded, subject = a_raid_fixture()
    twice = [a_finding("compare.talents.emberkin-0"), a_finding("compare.talents.emberkin-0")]

    with pytest.raises(ValueError, match="compare.talents.emberkin-0"):
        build_raid_report(loaded, twice, subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES)


def test_every_finding_reaches_exactly_one_field() -> None:
    """Placed, carded, or caught -- once each, never twice and never none.

    The page renders each field in turn, so a finding in two fields is drawn
    twice under two headings and a finding in none is measured and never
    shown.
    """
    loaded, subject = a_raid_fixture()
    findings = one_of_every_raid_family()

    report = build_raid_report(
        loaded, findings, subject, frozenset({"emberkin-0"}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
    )

    drawn = [row.finding_id for row in all_raid_ledger_rows(report)]
    drawn += [
        row.finding_id for card in report.players for row in comparison_rows(card)
    ]
    assert drawn, "the report drew no rows at all"
    assert sorted(drawn) == sorted({f.id for f in findings}), (
        sorted(set(drawn) ^ {f.id for f in findings})
    )


def test_a_wipe_withholds_the_damage_tab_and_says_why() -> None:
    """Design section 13, and the risk it names: an empty section teaches nothing."""
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, a_wipes_findings(), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )

    assert report.damage.present is False
    assert report.damage.withheld_reason
    assert "did not kill" in report.damage.withheld_reason


def test_a_kill_with_a_sample_opens_the_damage_tab() -> None:
    """The other half of the branch above, so neither reads as the default."""
    loaded, subject = a_raid_fixture(kill=True)

    report = build_raid_report(
        loaded, a_kills_findings(), subject, frozenset({"emberkin-0"}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
    )

    assert report.damage.present is True
    assert report.damage_rows, "an open damage tab with no rows on it"
```

- [ ] **Step 2: Run them and watch them fail**

- [ ] **Step 3: Write the builder**

Mirror `build_report`'s control flow, with the raid registry in place of the Mythic+ one and the route/timeline half absent:

1. `_check_unique_finding_ids(findings)` — import the existing one rather than writing a second.
2. `titles_by_id`, then the tooltips.
3. `build_raid_players(...)`.
4. The damage `Section`, gated on `PARSE_UNAVAILABLE_ID`'s presence exactly as `section_for` gates the Mythic+ parse section — and append its reason to `withheld`.
5. `ledger_row` over `RAID_DECOMPOSITION_IDS`.
6. `place_rows(findings, titles_by_id, exclude, placements=RAID_PLACEMENTS)`.
7. `build_summary_pointers`.
8. `placed_finding_ids`, including the ids the cards claimed.
9. `build_deaths(...)`.
10. `build_observations(findings, placed_ids, titles_by_id, tooltips)`.
11. One `RaidReport`.

- [ ] **Step 4: Run everything, then the mutation check**

Remove the card ids from `placed_finding_ids` in step 8. `test_every_finding_reaches_exactly_one_field` must fail with the carded families named on both sides. Restore it.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/domain/report/raid_build.py tests/domain/report/test_raid_build.py
git commit -m "$(cat <<'EOF'
Assemble the raid page as one frozen value

Every judgement the page makes is made here so the template makes none, which
is the arrangement the Mythic+ report already has and the reason its templates
loop and decide nothing.

The builder takes no narrative, no speed sample and no throughput ceiling: the
raid command has none of those flags, a boss fight has no route to compare,
and a parameter accepted and ignored is a lie the type system helps tell.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Seven tabs of markup

A tab is two independently hand-written halves matched by string equality — a `<button data-tab-for="tab-X">` in the nav and a `<section class="panel" data-tab-panel="main" id="tab-X">` at the top of its partial. Nothing loops over them and nothing counts them, so the count lives in the test file (Task 10) and nowhere else.

**Files:**
- Create: `src/wowperf/adapters/render/raid.html.j2`, `_raid_summary.html.j2`, `_raid_damage.html.j2`, `_raid_mechanics.html.j2`, `_raid_provenance.html.j2`
- Reuse unchanged: `_macros.html.j2`, `_deaths.html.j2`, `_interrupts.html.j2`, `_players.html.j2`, `report.css.j2`, `report.js.j2`
- Test: covered by Task 10

**Interfaces:**
- Consumes: a `RaidReport` bound as `report`, and `icons_by_id`, exactly as the Mythic+ root does.
- Produces: the seven panel ids `tab-summary`, `tab-damage`, `tab-mechanics`, `tab-deaths`, `tab-interrupts`, `tab-players`, `tab-provenance`, in that order.

- [ ] **Step 1: Check what the shared partials actually read**

```bash
grep -n "report\.[a-z_]*" src/wowperf/adapters/render/_deaths.html.j2 src/wowperf/adapters/render/_interrupts.html.j2 src/wowperf/adapters/render/_players.html.j2
```

Every name that comes back must be a field on `RaidReport`. Where it is, include the partial unchanged. Where it is not, write a raid sibling rather than adding a conditional to the shared file — a template that asks which command produced its model is the branching this project narrows away from. Record in the commit body which of the three were reusable and which were not; the answer is a fact about the code, not a prediction.

`_players.html.j2` draws `player_timeline(player.timeline)`, and that macro already renders a withheld message when handed `None` — check that it does before relying on it. A raid card carries no timeline (Task 6).

- [ ] **Step 2: Write the root template**

`raid.html.j2`, copying `report.html.j2`'s skeleton — the same single `<style>` holding `{% include "report.css.j2" %}` plus one `.i-<id>` rule per icon, the same hidden `<svg class="icon-defs">`, the same single `<script>` holding `{% include "report.js.j2" %}` — and differing in three places:

```jinja
<title>{{ report.header.boss }} {{ report.header.difficulty }}</title>
```
```jinja
<h1>{{ report.header.boss }} {{ report.header.difficulty }}</h1>
<p class="subhead">{{ report.header.outcome }} &middot; {{ report.header.partition }}</p>
```
and a nav of seven buttons:

```jinja
<nav class="tabs" data-tab-group="main" aria-label="Sections">
  <button type="button" class="tab" data-tab-for="tab-summary">Summary</button>
  <button type="button" class="tab" data-tab-for="tab-damage">Damage</button>
  <button type="button" class="tab" data-tab-for="tab-mechanics">Mechanics</button>
  <button type="button" class="tab" data-tab-for="tab-deaths">Deaths</button>
  <button type="button" class="tab" data-tab-for="tab-interrupts">Interrupts</button>
  <button type="button" class="tab" data-tab-for="tab-players">Players</button>
  <button type="button" class="tab" data-tab-for="tab-provenance">Provenance</button>
</nav>
```

followed by seven `{% include %}` lines in the same order. **Keep the blank lines between the includes**: `report.html.j2:37-38` carries a comment saying they are page output rather than source spacing, and removing one changes the rendered page.

- [ ] **Step 3: Write the four new partials**

Each opens with its own `<section class="panel" data-tab-panel="main" id="tab-X">` and uses `ledger_row` from `_macros.html.j2` for every row. None of them may contain `|sum`, `sum(` or `{% set` — the invariants test globs every `.j2` in the directory.

- `_raid_summary.html.j2` — the decomposition ledger, then the pointers, then the observations. Three `<h2>` anchors: `id="ledger"`, `id="losses"`, `id="observations"`. Omit the losses heading entirely when `report.summary_pointers` is empty, as the Mythic+ summary does.
- `_raid_damage.html.j2` — `<h2 id="damage">`; when `report.damage.present` is false, render the `class="withheld"` block carrying `report.damage.withheld_reason` and nothing else; otherwise one `ledger_row` per `report.damage_rows` entry.
- `_raid_mechanics.html.j2` — `<h2 id="mechanics">`, one `ledger_row` per `report.mechanics_rows` entry. Where there are none, render nothing rather than an empty `<div class="findings">`: the invariants test rejects an empty findings wrapper.
- `_raid_provenance.html.j2` — a copy of `_provenance.html.j2` with `+{{ record.keystone_level }}` replaced by the raid vocabulary the reference record carries. **Read `ReferenceRecord` before writing this line**; if it has no raid-shaped field, that is Task 8's work and belongs in this commit, with the Mythic+ field left alone.

- [ ] **Step 4: Render one by hand and look at it**

There is no test yet — Task 10 writes them. Build a `RaidReport` in a scratch script, render it, write the HTML to the scratchpad and open it. Confirm by eye: seven tabs that switch, no tab open that should not be, the header reading as a sentence. This is a look, not a test; the tests come next and are what the commit stands on.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/adapters/render/raid.html.j2 src/wowperf/adapters/render/_raid_summary.html.j2 src/wowperf/adapters/render/_raid_damage.html.j2 src/wowperf/adapters/render/_raid_mechanics.html.j2 src/wowperf/adapters/render/_raid_provenance.html.j2
git commit -m "$(cat <<'EOF'
Lay out the raid page in seven tabs

Route and tempo has no raid meaning and is absent; damage and mechanics are
the two a boss fight adds. The tab machinery itself is generic -- the script
matches a button to a panel by string equality and counts nothing -- so a
seventh tab is two more hand-written halves and no code.

The stylesheet, the script, the macros and the icon pipeline are included
unchanged. A raid page that forked any of them would be a second copy to keep
in step.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: `render_raid`

**Files:**
- Modify: `src/wowperf/adapters/render/html.py`
- Test: `tests/adapters/render/test_raid_html_invariants.py` (Task 10 writes it; this task adds the smallest test that proves the function renders at all)

**Interfaces:**
- Consumes: `RaidReport` (Task 4), `all_raid_ledger_rows` (Task 4).
- Produces: `render_raid(report: RaidReport, icons: CdnIcons | None = None) -> str`. Task 12 calls it.

- [ ] **Step 1: Write the failing test**

```python
def test_a_raid_report_renders_its_seven_panels() -> None:
    html = render_raid(a_minimal_raid_report())

    assert html.count('<section class="panel"') == len(RAID_PANEL_ORDER)
    for panel in RAID_PANEL_ORDER:
        assert html.count(f'data-tab-for="{panel}"') == 1


def test_an_ability_a_damage_row_names_still_draws_its_icon() -> None:
    """The icon resolver walks the model, so a field it does not walk draws nothing.

    Every other icon failure is loud. This one is a missing picture on a page
    that otherwise renders, which is why the walk is asserted from a row in a
    field only the raid model has.
    """
    ability_id = 12345
    report = a_raid_report_with_an_ability_only_in(field="damage_rows", ability_id=ability_id)

    html = render_raid(report, CdnIcons({ability_id: "spell_holy_divineshield.jpg"}))

    assert f".i-{ability_id}" in html
```

- [ ] **Step 2: Run them and watch them fail**

- [ ] **Step 3: Write `render_raid`**

Beside `render`, sharing `_environment()`:

```python
RAID_TEMPLATE_NAME = "raid.html.j2"
```

and a `_raid_icon_addresses(report: RaidReport, icons: CdnIcons) -> dict[int, str]` walking, in fixed order: death cards, `all_raid_ledger_rows(report)`, then each card's `comparison_tables`. Do not walk a player timeline — a raid card has none.

If `_icon_addresses` can be narrowed to take the pieces it walks rather than a whole `Report`, narrow it and share one function. If it cannot without contortion, write the sibling and say so in the docstring. Prefer narrowing; say which you did.

- [ ] **Step 4: Run everything, then the mutation check**

Drop `all_raid_ledger_rows(report)` from the walk. `test_an_ability_a_damage_row_names_still_draws_its_icon` must fail. Restore it.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/adapters/render/html.py tests/adapters/render/test_raid_html_invariants.py
git commit -m "$(cat <<'EOF'
Render a raid report

One more entry point beside the Mythic+ one, sharing the Jinja environment and
the icon resolver's shape. The resolver walks the raid model's own row fields,
because an ability that reaches the page without reaching the resolver draws
nothing and reports nothing -- the quietest failure this page has.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: The raid page under the same invariants as the Mythic+ one

Design section 10: *"`tests/adapters/render/test_html_invariants.py` governs the raid report as it governs the Mythic+ one."* That file's rules are written against `minimal_html()` and `rich_html()`, which build `Report`s. The raid page needs the same rules asserted against a raid page.

**Files:**
- Create: `tests/adapters/render/test_raid_html_invariants.py`
- Modify: `tests/adapters/render/test_html_invariants.py` (only `NUMBERS_THAT_ARE_NOT_TOTALS`, if Tasks 3 to 7 added a bare numeric field)

**Interfaces:**
- Consumes: `render_raid` (Task 9).
- Produces: `RAID_PANEL_ORDER`, and the raid fixtures Task 11 turns into a golden file.

- [ ] **Step 1: Write the panel registry and the fixtures**

```python
RAID_PANEL_ORDER = [
    "tab-summary",
    "tab-damage",
    "tab-mechanics",
    "tab-deaths",
    "tab-interrupts",
    "tab-players",
    "tab-provenance",
]
"""The exact seven top-level panel ids, in the order the page draws them.

Nothing in the templates or the renderer counts tabs -- the script matches a
button to a panel by string equality -- so this list is the only place the
count is stated, and a tab added without a line here is a tab no test sees.
"""
```

- [ ] **Step 2: Write the invariants, one test each**

Port these from `test_html_invariants.py`, asserting them against the rendered raid page. Each keeps the name and the reasoning of the test it mirrors, so a reader can put the two files side by side:

1. `test_the_page_executes_only_its_own_script` — exactly one `<script>`, no `src=` on it, none of `FORBIDDEN_IN_SCRIPT` in its body, no `@import`, no `<link rel=`, no `src="..."` starting `http://`, `https://` or `//`, and `getElementById` present. Import `FORBIDDEN_IN_SCRIPT` from the Mythic+ module rather than retyping it, so one tuple governs both pages.
2. `test_every_href_is_a_fragment_a_report_link_or_an_icon_address` — every href starts with `#`, `https://www.warcraftlogs.com/reports/`, or `ICON_HOST`; and at least one of each of the first two exists, so the test cannot pass on a page with no links.
3. `test_every_image_address_the_page_draws_points_at_the_icon_host` — every `url(...)` starts with `ICON_HOST`, at least one found.
4. `test_a_resolved_icon_reaches_the_page_as_an_address_never_as_embedded_bytes` — no `data:image` anywhere.
5. `test_the_page_hides_nothing_before_the_script_runs` — no bare `hidden` attribute, no inline `display` style, every `display: none` rule scoped under `.js ` or exactly `.tabs`/`.tip`.
6. `test_every_panel_appears_once_in_tab_order` — the seven `RAID_PANEL_ORDER` ids appear in ascending index order, and `html.count('<section class="panel"') == len(RAID_PANEL_ORDER)`.
7. `test_every_panel_has_exactly_one_tab_button` and `test_the_tab_buttons_follow_panel_order`.
8. `test_no_element_id_appears_twice` — collected `id="..."` values are unique, and the list is non-empty.
9. `test_every_finding_reaches_the_page` and `test_no_finding_reaches_the_page_twice`.
10. `test_every_pointer_targets_an_anchor_that_exists` and `test_a_pointer_is_a_link_not_a_second_card`.
11. `test_no_empty_findings_wrappers_render`.
12. `test_every_withheld_section_gives_a_reason` — on a wiped fixture, the Damage panel carries a `class="withheld"` block with text in it. This is the one design section 13 names as a risk by itself.

- [ ] **Step 3: The test that only twenty raiders can fail**

```python
def test_a_full_roster_collides_no_element_ids() -> None:
    """Twenty raiders is where a suffix that failed to distinguish anybody shows.

    Two would pass a suffix that appended a constant. The offline sibling of
    the e2e test that costs quota -- this one is free and runs on every push.
    """
    report = a_raid_report_with(raiders=20, compared=20)

    html = render_raid(report)

    element_ids = re.findall(r'\sid="([^"]+)"', html)
    assert element_ids, "a page with no element ids would pass this vacuously"
    duplicates = {value for value in element_ids if element_ids.count(value) > 1}
    assert duplicates == set()
```

The fixture builds twenty raiders from the sanctioned names plus an index — `Emberkin 1`, `Emberkin 2` and so on — which is also the harder case, because every one of them slugs to `emberkin` before the roster index is appended.

- [ ] **Step 4: Run everything, then the mutation check**

Two mutations, each naming its test:

1. Delete `tab-mechanics` from the nav in `raid.html.j2` → `test_every_panel_has_exactly_one_tab_button` fails.
2. In `slugs_by_actor`, return `player_slug(names[player.actor_id])` without the index → `test_a_full_roster_collides_no_element_ids` fails.

Restore both.

- [ ] **Step 5: Commit**

```bash
git add tests/adapters/render/test_raid_html_invariants.py tests/adapters/render/test_html_invariants.py
git commit -m "$(cat <<'EOF'
Hold the raid page to the rules the report already has

Design section 10 says the invariants govern this page as they govern the
other one, and they are written against a model the raid report does not use.
So the rules are asserted again against a raid page, each test keeping the
name and the reasoning of the one it mirrors, and the two tuples worth having
exactly one copy of -- the forbidden script calls and the icon host -- are
imported rather than retyped.

The twenty-raider case earns its place: two raiders would pass a suffix that
appended a constant, and twenty who all slug to one name would not.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: A golden raid page whose comparison sentences are real

Ruling 4. The Mythic+ golden fixture passes `None` for its speed sample and hand-authors its comparison rows as `Finding` literals, so no `compare.*` family reaches the page it renders and a wording mutation leaves it green. That was found by mutation during plan 3a after the file had been cited as proof in three review briefs. The raid fixture does not repeat it.

**Files:**
- Create: `tests/adapters/render/golden/raid.html`
- Modify: `tests/adapters/render/test_raid_html_invariants.py`

- [ ] **Step 1: Write the fixture that runs the real comparison**

`a_real_raid_comparison()` builds a `LoadedEncounter` with two compared raiders and a `ParseSample` with enough members to clear `MIN_SAMPLE_FOR_AGGREGATE`, and calls **`analyse_encounter`** — the real service, including Task 2's minting — rather than assembling `Finding` literals. Its output feeds `build_raid_report`.

Guard it, or the fixture can rot into the thing it replaced:

```python
def test_the_golden_fixture_actually_carries_a_comparison() -> None:
    """The guard the Mythic+ golden file does not have.

    Its fixture carries no reference sample, so no comparison family reaches
    the page it renders, and a mutation to any comparison sentence leaves it
    green -- discovered by mutation during plan 3a, after the file had been
    cited as proof in three review briefs. A fixture that stops comparing must
    fail here rather than quietly stop testing.
    """
    findings = a_real_raid_comparison()

    families = {f.id.rsplit(".", 1)[0] for f in findings if f.id.startswith("compare.")}
    assert families >= {
        "compare.damage.total", "compare.rank", "compare.talents",
    }, sorted(families)
```

- [ ] **Step 2: Write the golden test**

```python
def test_the_rendered_raid_page_matches_the_golden_file(pytestconfig: pytest.Config) -> None:
    html = golden_raid_html()
    if pytestconfig.getoption("--golden-update"):
        RAID_GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        RAID_GOLDEN.write_text(html, encoding="utf-8")
        pytest.skip("golden file rewritten")
    assert html == RAID_GOLDEN.read_text(encoding="utf-8"), (
        "The rendered raid report changed. Read the diff, then regenerate with "
        "`uv run pytest tests/adapters/render/test_raid_html_invariants.py --golden-update`."
    )
```

- [ ] **Step 3: Generate the golden file and read it**

```bash
uv run pytest tests/adapters/render/test_raid_html_invariants.py --golden-update
```

Then **read the generated file** before committing it. A golden file committed unread is a snapshot of whatever the code did, including whatever it did wrong. Check the seven tabs are there, the comparison sentences read as English, and no real character name appears in it — the fixture uses sanctioned names, and this is the file where a slip would be committed.

- [ ] **Step 4: Mutation check — the one this task exists for**

Change a word in a raid comparison finding's title in `src/wowperf/domain/comparison/throughput.py` — for instance the noun in `compare_damage_total`'s title. `test_the_rendered_raid_page_matches_the_golden_file` **must** fail. If it passes, the fixture is not carrying a comparison and Ruling 4 has not been satisfied: fix the fixture, not the test. Restore the word.

- [ ] **Step 5: Commit**

```bash
git add tests/adapters/render/golden/raid.html tests/adapters/render/test_raid_html_invariants.py
git commit -m "$(cat <<'EOF'
Pin the raid page against a comparison that really ran

The Mythic+ golden fixture has no reference sample behind it, so no comparison
family reaches the page it pins and a wording mutation leaves it green. That
was found by mutation during plan 3a, after the file had been cited as proof
in three separate review briefs.

This fixture calls the real service, and a guard beside it fails if the
families stop arriving -- so the fixture cannot rot into the thing it was
written to replace.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: `raid` writes the page

**Files:**
- Modify: `src/wowperf/cli.py:1579-1588` (the raid command's output half)
- Modify: `src/wowperf/adapters/render/icons.py` — no change expected; confirm the ability data the raid path fetches reaches `CdnIcons` the same way `analyze` gets it
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `build_raid_report` (Task 7), `render_raid` (Task 9).
- Produces: `<code>-<fight>.html` beside `<code>-<fight>.findings.json`, as section 11 specifies.

- [ ] **Step 1: Write the failing test**

```python
def test_raid_writes_a_page_beside_its_findings(tmp_path: Path) -> None:
    """Section 11: the command's output is both files, under `--out`."""
    result = CliRunner().invoke(app, raid_args(tmp_path))

    assert result.exit_code == 0, f"{result.stderr}\n{result.exception!r}"
    [findings] = (tmp_path / "out").glob("*.findings.json")
    [page] = (tmp_path / "out").glob("*.html")
    assert page.stem == findings.stem.removesuffix(".findings")
    assert "<section class=\"panel\"" in page.read_text(encoding="utf-8")


def test_the_command_names_both_files_it_wrote(tmp_path: Path) -> None:
    """A path printed is a path a person can open. Two files, two lines."""
    result = CliRunner().invoke(app, raid_args(tmp_path))

    assert ".findings.json" in result.output
    assert ".html" in result.output
```

Drive this from a cached fixture, not the network — `tests/test_cli.py`'s existing raid tests show the shape.

- [ ] **Step 2: Run them and watch them fail**

- [ ] **Step 3: Wire it**

After the findings file is written, build and render, mirroring `analyze`'s ordering at `cli.py:1361-1396`. Write the HTML with the same `OSError` handling the findings write already has — one failure path, not two shapes of it.

- [ ] **Step 4: Run everything**

Then check by hand that `--out` moves both files and that a second run overwrites rather than duplicating.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/cli.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
Write the raid page the command has been promising

Design section 11 says the raid command's output is the findings file and the
page. It has written one of them since plan 1 and said so on every run.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: The end-to-end test that only a real roster can fail

**Files:**
- Modify: `tests/e2e/test_raid_e2e.py`

The sibling of `tests/e2e/test_report_e2e.py:193`, `test_all_players_compares_everyone_and_collides_no_ids`, which is the Mythic+ version of exactly this claim. Read it before writing this one.

- [ ] **Step 1: Write the test**

```python
@pytest.mark.e2e
def test_a_real_raid_roster_renders_one_page_with_no_collisions(tmp_path: Path) -> None:
    """`--all-players` end to end: the real command, the real API, twenty people.

    Driven as the command rather than reassembled from its parts. Who is
    compared is decided in `raid` and nowhere else -- the flag, the roster it
    sweeps up, the slug stamped on every finding it mints and the cards the
    page then fills -- so a reassembly here would exercise the reassembly.

    This is the run that would have caught what one live run at twenty raiders
    measured before this plan: 266 findings over 79 distinct ids, 206 of them
    sharing one.

    Costs real quota. Against a warm cache it costs almost nothing, which is
    how it should usually be run.
    """
```

Assert, in this order: exit code 0 with stderr and the exception both in the message, because a failure here has already spent quota and must say which it was; one findings file and one page; every finding id minted once, naming the duplicates rather than counting them; every element id on the page unique, likewise; every compared slug has a card on the page; and every compared slug appears as some finding's `player_slug`.

- [ ] **Step 2: Run it against the warm caches plan 3a filled**

The kill, wipe and roster caches from plan 3a's live runs are still on disk in this session's scratchpad. Point `--cache-dir` at the roster one and the run costs the two rate-limit reads and nothing else. Reference entries expire after a day, so if the cache has gone cold, say so and take the cold reading rather than pretending it was warm.

```bash
WOWPERF_E2E_RAID_KILL='...' uv run pytest -m e2e -s \
  tests/e2e/test_raid_e2e.py::test_a_real_raid_roster_renders_one_page_with_no_collisions
```

Credentials live in a gitignored UTF-16 `.env` in the main checkout. Copy it in with `shutil.copy2`, **never read, echo, print or commit the values**, never put them on a command line, and **delete the copy when done**.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_raid_e2e.py
git commit -m "$(cat <<'EOF'
Prove a real raid roster mints one id per finding

The offline sibling of this test builds twenty raiders from one sanctioned
name. This one uses the real roster, the real leaderboards and the real
command, because who gets compared is decided in the command and a
reassembled test would exercise the reassembly.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Run it on a real boss and write down what it said

Plan 3a's offline suite was green for eleven tasks and the first live run still found a user-visible false sentence. Plan 2's did the same. This task is not a formality.

**Files:**
- Modify: `.claude/skills/wcl-api/SKILL.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the tool three ways**

A kill, a wipe, and `--all-players`, each against the warm caches from plan 3a where they are still warm. Use `--out` and `--cache-dir` in the scratchpad, never the repository.

- [ ] **Step 2: Read the three pages as a reader, not as an author**

Specifically look for:

- A sentence that is **false**, not merely awkward. Plan 3a's live run produced a finding whose detail read "the share of fight time" beside a fact reading "46% of boss time". That class of defect survives every offline test because both halves are individually correct.
- A withheld section that does not say why. Design section 13 names this as the risk the wipe page carries.
- A row on a tab a reader would not look for it under. Ruling 3 is a judgement, and this is where it is checked.
- Any real character name in a place that is not a player card or a reference link.

Fix what you find in the layer that produced it, with a test that fails first.

- [ ] **Step 3: Record what it cost**

Add a dated row to `.claude/skills/wcl-api/SKILL.md`'s rate-limit section, labelled as a **measurement** and naming its conditions: warm or cold, which report, how many raiders. Do not restate plan 3a's 877.74 as this plan's figure, and do not restate the design's ~730 projection as a measurement — both are already recorded there, each labelled as what it is.

While in that file, the unreconciled reading plan 3a left stands: the raid `characterRankings` board cost 2.01 points on 2026-09-15 against 0.0 recorded for the identical board on 2026-09-14. Leave it recorded and unresolved unless this plan's runs happen to settle it, in which case say which reading won and how.

- [ ] **Step 4: Update `CLAUDE.md`**

Two places, both currently untrue once this plan lands:

- The repository overview says the report "carries six tabs" and names them. Add the raid page's seven beside it.
- The commands table's `raid` row, and the `analyzing-a-run` skill's "The `raid` command" section, both say it writes findings JSON only and that the comparison is not implemented. Both are now false in two ways — plan 3a implemented the comparison and this plan writes the page.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/wcl-api/SKILL.md CLAUDE.md
git commit -m "$(cat <<'EOF'
Record what the raid page cost and what it says

The skill file gains this plan's reading, labelled a measurement and carrying
its conditions. CLAUDE.md loses two sentences that stopped being true: the
report has a seven tab sibling now, and the raid command no longer writes
findings alone or refuses to compare.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review

**Spec coverage.** Section 10's four claims: one self-contained file under the master design's invariants (Tasks 8, 9, 10); seven named tabs with Route & tempo absent (Tasks 4, 5, 8, 10); the header's four facts (Task 3); a model of its own with the vocabulary beneath it reused whole (Tasks 4, 6, 7). The section registry's "four places" are Tasks 4 (`RaidReport`'s fields and `all_raid_ledger_rows`), 5 (`RAID_PLACEMENTS`) and 8 (the template's nav and includes) — with a fifth this plan adds deliberately, `RAID_PANEL_ORDER` in Task 10, because nothing in the templates counts tabs and a test is the only thing that can. Section 11's output half is Task 12. Section 12's three traps: a withheld finding tested for its reason (Tasks 7, 10); a comparison fixture that really compares (Task 11); no real character name in `tests/` (Global Constraints, and checked by eye in Task 11 step 3).

**The four debts from plan 3a**, each an explicit task rather than a footnote: duplicate ids under `--all-players` is Task 2, measured; `PLACEMENTS` missing `mechanics.` is Task 5, with a test named after it; plan 3a's own unplaced families are Task 5 as well; and the golden file proving nothing is Task 11, with the mutation that proves the fix.

**Two of plan 3a's smaller parked items are folded in rather than dropped.** `throughput._unavailable` carrying no `evidence` tuple where every sibling does becomes visible the moment Task 8's ledger rows render evidence lists — fix it in Task 8 if the page shows the gap, and say so. `compare.uptime.unjudged`'s title and detail being whole-pinned on neither axis is closed by Task 11: the golden file pins the rendered sentence, which is the backstop that was missing. `_boss_share` is deliberately left alone, for the reason in "What this plan does not do".

**Type consistency.** `slugs_by_actor(players)` (Task 1) is called by Task 2's CLI change and Task 6's card builder with the same argument shape. `ParseSubject.slug` (Task 2) is read in Task 2 only. `RaidHeader` (Task 3) is a field of `RaidReport` (Task 4) and is printed by Task 8. `RAID_PLACEMENTS` (Task 5) is passed to `place_rows`'s new `placements` argument (Task 5) by `build_raid_report` (Task 7). `RAID_COMPARISON_PREFIXES` (Task 5) is read by `build_raid_players` (Task 6) and by Task 7's `placed_finding_ids`. `RAID_PANEL_ORDER` (Task 10) is read by Tasks 9 and 10. `render_raid` (Task 9) is called by Task 12.

**One open question this plan does not close, deliberately.** Task 3 step 1 asks whether the API names a difficulty before a table is written for it. The answer is unknown as this plan is written, and inventing either the field name or the table would be the failure `CLAUDE.md` names first. The task branches on the answer and records the negative result if that is what it finds.

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-09-15-raid-report-plan.md`.

**Model selection**, task by task — an omitted model inherits the session's, which is usually the dearest:

| Tier | Tasks | Why |
| --- | --- | --- |
| Cheapest | 1, 3, 12 | Near-transcription: one signature, one table, one wiring, all fully specified above. |
| Standard | 2, 4, 5, 6, 8, 9, 13, 14 | Multi-file work with judgement in it. |
| Most capable | 7, 10, 11 | The builder's control flow, the invariant port, and the golden fixture that must not repeat the Mythic+ one's hole. |

The final whole-branch review takes the most capable model available regardless. On plan 3a it found a Critical that eleven per-task reviews had each missed.

**Two execution options:**

1. **Subagent-Driven (recommended)** — a fresh subagent per task, a scoped review after each, one broad review at the end.
2. **Inline Execution** — tasks in this session with checkpoints.
