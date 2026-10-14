# Key Uptime Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure Mythic+ uptime over the whole key. Buffs are judged over the key clock, from the fight's start to its end. Debuffs are judged as coverage over every enemy's life, summed, with reach described beside it. Each family keeps a Bosses figure and gains a non-boss one. The Bosses figure does not move, except on the buff side of a fight where Warcraft Logs lists a boss pull twice: that pull is now measured once there, as the debuff side already measures it (spec §3.3, amended).

**Architecture:**

- **Task 1** re-measures, offline, the rule that opens a trash life, and records it in the design.
- **Task 2** carries each enemy death with its actor and copy, and the report's players, in the debuff log.
- **Task 3** cuts every enemy that is not a measured boss into lives, in a new module `comparison/enemy_lives.py`.
- **Task 4** measures coverage and reach per stretch, in a new module `comparison/key_debuffs.py`, and reads the shared rule per life. The boss figure is built by the same helpers as before, and every existing boss test now reads it through the new path.
- **Task 5** judges debuffs on Overall coverage, renames their finding ids to `compare.uptime.debuff.*`, and fills the table's stretch and reach cells.
- **Task 6** gives our run and every parse reference its fight's own start and end, read from the report the cache already holds.
- **Task 7** judges buffs over the key clock and describes them without bosses and on bosses. A boss pull listed twice is one buff window, by the rule the debuff figure already reads, now held in one helper both call.
- **Task 8** draws the page: the buff columns, "Debuff coverage", "Debuff reach", each with the Range and Sample of its Overall figure, the note and the warning.
- **Task 9** updates the docs.
- **Task 10** is the live proof.

**Tech Stack:** Python 3.12, pydantic `Frozen` models, httpx `MockTransport` for offline tests, Jinja2, `uv`.

**Spec:** `docs/plans/2026-10-13-key-uptime-coverage-design.md`. Read it first. It builds on `docs/plans/2026-10-07-enemy-debuff-uptime-design.md` and `docs/plans/2026-10-08-council-debuff-coverage-design.md`, which you should also read. The previous plan in this area, `docs/plans/2026-10-08-council-debuff-coverage-plan.md`, shows how the boss figure was built.

**Choices the spec leaves open, decided here.** Task 9 records choices 3 to 7, 10 and 12 in the design as dated amendments. Choices 11 and 13 are not among them. RwlRwlRwlRwl decided those two on 2026-10-13, after reading this plan, and the design's §4 and §3.3 already carry them as dated amendments.

1. **Where the lives live.** In `comparison/enemy_lives.py`, taking the measured bosses' game ids rather than the windows. A module that reads only a log and a route has no reason to import the boss rule.
2. **How the key is represented.** A new `KeyDebuffs` composes the unchanged `BossDebuffs` with a `StretchCover` for trash and one for adds. Extending `BossDebuffs` would have put trash under a type named for bosses. Replacing it would have rewritten forty boss tests that are the best evidence the boss figure does not move.
3. **`boss_debuffs()` moves to `key_debuffs.py`** and returns `key_debuffs(...).bosses`. Every existing boss test then pins the path the comparison really runs. Left in `boss_debuffs.py`, it would have pinned a path production no longer takes.
4. **A measured boss's game id is never cut into lives.** Otherwise every wiped boss would read as an enemy with no death, and every boss would be counted twice, once as a target and once as a life (spec §3.2 item 2).
5. **The enemies of a pull with no boss found count as adds**, including the unfound boss. They died in a boss pull and are no boss target (spec §3.2 item 3).
6. **A death belongs to the last pull starting at or before it**, so a death stamped just after a pull closes stays with that pull (council design §4, amended 2026-10-08). A death before every pull belongs to the first.
7. **A death row the log writes twice is one death**, so it never makes a zero-length life of its own.
8. **The fight's clock rides on `Run.fight_ms` and `ParseMember.fight_ms`.** It is filled by `build_run`, which already holds the fight dict that `repository._load` reads from the cached report. No new query is made.
9. **The key clock reaches the shared uptime code in two keyword arguments**, `our_fight_ms` and `over`. Their defaults leave the raid path exactly as it is.
10. **The warning states each clause only when its count is above zero.** A clause stating zero would warn about nothing.
11. **The three uptime tables keep a Range and a Sample column, for the judged Overall figure.** Debuff coverage reads `Ability | Verdict | Overall | Range | Sample | Trash | Bosses | one column per boss`. Buff uptime reads `Ability | Verdict | Overall | Range | Sample | Without bosses | Bosses`. Debuff reach reads `Ability | Overall | Range | Sample | Trash | Bosses`.
    - **Why.** The verdict rests on Overall, so the spread and the count of the references behind Overall's median are what let a reader weigh it. This plan first drew neither, and RwlRwlRwlRwl reversed that on 2026-10-13 ("keep range and sample"). Reach keeps the two columns too, stating its Overall figure's references, so the three tables share one shape. The cells for each stretch and each boss stay "ours against the median".
    - **How.** The builder writes Overall, Range and Sample as each row's first three cells, under headings of the same names, so the template still only loops. The Ours, Median, Range and Sample columns that the cast tables draw before the Verdict are not drawn on these tables. Their rows leave those four strings empty rather than carry a second copy of what the cells draw.
    - **Reach's references.** A `StretchCell` holds no references, so `DebuffReach.overall_fractions` keeps the references' Overall reaches behind `overall`'s median (Task 5).
12. **The findings file's `comparison_tables.<slug>.boss_debuffs` becomes `.debuffs`**, for the reason spec §4 gives for renaming the ids: the old name would describe the wrong figure. Each `auras` entry now nests its judged figure under `uptime`, beside `without_bosses` and `bosses`. Each debuff row's `reach` carries `overall_fractions` beside its three cells.
13. **A boss pull Warcraft Logs lists twice is one buff window**, by the rule `boss_windows_of` already applies to the debuff figure.
    - **The rule lives in one helper.** It is `boss_debuffs.boss_pulls_listed_once`, which both `boss_windows_of` and `uptime.boss_windows` call (Task 7).
    - **What it corrects.** `boss_windows` listed such a pull's span twice. `auras.uptime_seconds_in` clips bands to every window and merges the result, so the buff's seconds inside the pull counted once, while the boss seconds counted it twice. Today that is the judged figure, with `spells.boss_seconds` as its denominator; after Task 7 it is the Bosses cell, with `tables._share_in` summing the windows. A buff up through every boss pull therefore read below 100%, and exactly 50% when the duplicated pull is the fight's only boss pull.
    - **What it leaves alone.** The cast path reads `spells.boss_pulls` and `spells.boss_seconds`, never `boss_windows`, so cast rates are untouched. Spec §10 leaves them to a separate task. The raid path reads no boss window, so it is untouched too.

## Global Constraints

- **Toolchain:** `uv` is not on PATH in the Bash tool. Begin every shell command that runs it with `export PATH="$HOME/.local/bin:$PATH";`. Run every command from the worktree root, `C:\Users\damien\claude_perso\wow_perf\.claude\worktrees\suspicious-heisenberg-5a6da7`.
- **Git:** use `/mingw64/bin/git` for every git command, one git command per Bash call.
- **Hooks:** never use `--no-verify` or any other hook bypass.
- **Commit messages:**
  - write them with the Write tool into the session scratchpad and commit with `/mingw64/bin/git commit -F <file>`;
  - plain ASCII only;
  - imperative subject, no `feat:` prefix;
  - the body says why;
  - end with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Scratchpad:** `C:\Users\damien\AppData\Local\Temp\claude\C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7\d8ccc848-7597-4c52-b0ac-84b521f1c3b0\scratchpad`. In Bash, that is `/c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad`. Scripts and commit messages go there, are written with the Write tool and never with a heredoc, and are never committed. In this plan, `<scratchpad>` names that directory and nothing else; every command spells the path out.
- **File headers:** every new code file starts with two `# ABOUTME: ` lines.
- **Fixture names:** tests use only the sanctioned character names `Emberkin`, `Stonewake`, `Bríala` and `Кириллица`. NPC and boss names are invented, such as `Fixture Whelp` and `The Test Colossus`. No real report code appears in `tests/`.
- **Players are never named.** Not in a test, a commit message, a design note, a script's output or a report. Refer to a player by class and spec, or by index.
- **Layering:** the domain performs no I/O.
- **Badges:** buff and debuff gaps and unjudged findings are `derived`, and unavailable is `measured`. Nothing here changes a badge.
- **Thresholds:** they are reused, never redefined. These are `MIN_UPTIME_FRACTION`, `UPTIME_GAP_FRACTION`, `MIN_SAMPLE_FOR_AGGREGATE`, `MAX_AURAS_REPORTED` and `SHARED_OVERLAP_TOLERANCE_S`. Reach has no threshold.
- **Comments:** never remove a comment unless it is actively false. Where this plan rewrites a docstring, it is because a sentence in it became false.
- **Line length:** ruff's limit is 100. Wrap long lines; never `noqa` in committed code.
- **Gate before every commit:** `uv run ruff check .`, `uv run mypy` and `uv run pytest -q`, each as its own command. All three must pass, with pristine output.
- **Network:** no task except Task 10 makes a network call. Never read `.env`; Task 10 loads it inline and never prints it.

---

## File Structure

| File | Change |
| --- | --- |
| `docs/plans/2026-10-13-key-uptime-coverage-design.md` | The measured life start (Task 1); the status line and the planning decisions (Task 9); the live amendment (Task 10). The §3.3 and §4 amendments for choices 13 and 11 are already in it. |
| `src/wowperf/domain/debuffs.py` | `EnemyDeathRow`, `DebuffLog.death_rows`, `DebuffLog.player_ids` (Task 2). |
| `src/wowperf/adapters/wcl/ingest.py` | `build_debuff_log` fills the two new fields (Task 2); `build_run` fills `Run.fight_ms` (Task 6). |
| `src/wowperf/domain/comparison/enemy_lives.py` | **New.** `LifeStretch`, `EnemyLife`, `EnemyLives`, `enemy_lives` (Task 3). |
| `src/wowperf/domain/comparison/boss_debuffs.py` | `Target`, `Held`, `held_on_bosses`, `bosses_held_by`, `BossDebuffs.reached` and `.targets`, a per-target `find_shared`, public `merged_spans` and `length_ms`, and `boss_debuffs` moved out (Task 4); `Withheld.NO_TRASH` (Task 5); `boss_pulls_listed_once`, which `boss_windows_of` now reads (Task 7). |
| `src/wowperf/domain/comparison/key_debuffs.py` | **New.** `StretchCover`, `combined`, `KeyDebuffs`, `held_on_lives`, `key_debuffs`, `boss_debuffs` (Task 4). |
| `src/wowperf/domain/comparison/measures.py` | `StretchCell`, `DebuffReach` with `overall_fractions`, `DebuffRow`, `DebuffTable` and `PlayerMeasures.debuffs` (Task 5); `AuraRow`, `PlayerMeasures.auras` and `.key_seconds` (Task 7). |
| `src/wowperf/domain/comparison/uptime.py` | `measured_or`, `carried_shares` and `stretch_cell` (Task 5); the two-argument `UptimeRule`, `key_clock_uptime`, `fight_seconds`, `without_boss_pulls`, `boss_seconds_of`, `fight_seconds_of`, `our_fight_ms` and `over`, the removal of `boss_pull_uptime`, and `boss_windows` reading `boss_pulls_listed_once` (Task 7). |
| `src/wowperf/domain/comparison/debuff_uptime.py` | Judged on Overall coverage, `compare.uptime.debuff.*`, `debuff_table` with stretch and reach cells, and reach's Overall references (Task 5). |
| `src/wowperf/domain/comparison/sample.py` | `ParseMember.debuffs` (Task 5), `ParseMember.fight_ms` (Task 6). |
| `src/wowperf/domain/comparison/service.py` | `ComparisonSubject.our_debuffs` (Task 5); buffs over the key clock (Task 7). |
| `src/wowperf/domain/comparison/tables.py` | `debuff_table` (Task 5); `_auras` builds `AuraRow`s over the key clock (Task 7). |
| `src/wowperf/domain/comparison/wording.py` | `KEY` (Task 7). |
| `src/wowperf/domain/model.py` | `Run.fight_ms` (Task 6). |
| `src/wowperf/cli.py` | `_fetch_parse_debuffs` reads `key_debuffs` (Task 5); a parse member's `fight_ms` (Task 6). |
| `src/wowperf/domain/report/model.py` | `ComparisonTable.figures`, `.judged`, `.note`, `.warning`; `ComparisonRow` figure strings default to empty (Task 8). |
| `src/wowperf/domain/report/players.py` | Field renames (Tasks 5, 7); the three uptime tables, the note and the warning (Task 8). |
| `src/wowperf/adapters/render/_players.html.j2` | The optional figure and verdict columns, the note and the warning (Task 8). |
| Tests | `tests/adapters/wcl/test_ingest_debuffs.py`, `test_ingest.py`; `tests/domain/comparison/test_enemy_lives.py` (new), `test_key_debuffs.py` (new), `test_boss_debuffs.py`, `test_debuff_uptime.py`, `test_sample.py`, `test_sample_invariants.py`, `test_uptime.py`, `test_service.py`, `test_tables.py`; `tests/domain/report/test_build_players.py`; `tests/adapters/render/test_html_invariants.py`; `tests/test_cli.py`; `tests/e2e/test_boss_debuffs_e2e.py`, `test_uptime_e2e.py`, `test_compare_e2e.py`. |
| Docs (Task 9) | The parent and council designs, the mplus-analysis skill, CLAUDE.md, README and `docs/how-it-works.md`. |
| Docs (Task 10) | This design's live amendment, and the wcl-api skill if a cost reading moved. |

---

### Task 1: Measure where a trash life opens, on the cache

The design opens a trash life at the first debuff *application* on that copy after its previous death (§3.2 item 1). The spike measured something else: the first *row* of any kind (§3.1), meaning an application, a removal, a row the enemy sourced, or a friendly cast at it. This task checks offline that the two agree. If they do not, it stops.

**Files:**
- Create, scratch only and never committed: `<scratchpad>\life_start_check.py` and its output `life_start_check.out`.
- Modify: `docs/plans/2026-10-13-key-uptime-coverage-design.md`, §3.1.

**Interfaces:** consumes the spike's `trash_common.py`, already in the scratchpad: `STREAMS`, `actors_of`, `matching_actors`, `scanned_actor_lists`, `scanned_reports` and `stream`. They join a stream's pages by recomputing the repository's own `cache_key(query, variables)` and following `nextPageTimestamp`, because a cache is pages, not runs. They never construct `DiskCache`, whose reference tier purges expired files when it is built. Produces nothing for later tasks except the go-ahead.

- [ ] **Step 1: Write the script**

Write `C:\Users\damien\AppData\Local\Temp\claude\C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7\d8ccc848-7597-4c52-b0ac-84b521f1c3b0\scratchpad\life_start_check.py` with the Write tool:

```python
"""Task 1 of the key uptime plan: the first-application life start against the spike's first row.

Offline only. Cached pages are read through trash_common, which never constructs DiskCache and
never fetches. Prints counts and seconds only: no player's name, no NPC's name.

An enemy is (game id, instance), cut into lives at its deaths. A life is kept when its death
falls in a trash pull, the last pull starting at or before the death.
- First row, the spike's rule (b): the life's first EnemyDebuffs row of any kind on it, any
  EnemyDebuffs row it sourced, or any friendly cast at it. A removal within 3 s after the
  previous death belongs to the previous life and is skipped.
- First application, the design's rule: the life's first `applydebuff` row on it.
Either start is the death itself when the life holds no such row.
"""

import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from trash_common import (  # noqa: E402
    STREAMS,
    actors_of,
    matching_actors,
    scanned_actor_lists,
    scanned_reports,
    stream,
)

REMOVAL_GRACE_MS = 3000
# The spike's own figures under rule (b), keyed by game id (trash-span-spike.md, Q4).
SPIKE_ALIVE_S = {"ours": 10_310, "references": 114_119}
SPIKE_LIVES = {"ours": 269, "references": 3_156}


def pct(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(share * (len(ordered) - 1))))]


def describe(values_ms):
    seconds = [value / 1000 for value in values_ms]
    return (
        f"n={len(seconds)} median={statistics.median(seconds):.1f}s "
        f"p90={pct(seconds, 0.9):.1f}s max={max(seconds):.1f}s"
    )


actor_lists = scanned_actor_lists()
moved = defaultdict(list)
alive = defaultdict(lambda: [0, 0])
tally = Counter()

for code, (report, _tier) in sorted(scanned_reports().items()):
    for fight in report["fights"]:
        if fight.get("keystoneLevel") is None or not fight.get("dungeonPulls"):
            continue
        debuffs = stream(STREAMS["EnemyDebuffs"], code, fight)
        deaths = stream(STREAMS["EnemyDeaths"], code, fight)
        if debuffs is None or deaths is None:
            continue
        casts = stream(STREAMS["Casts"], code, fight) or []
        side = "ours" if stream(STREAMS["DamageTaken"], code, fight) is not None else "references"
        tally[f"{side}: fights"] += 1
        pulls = sorted(fight["dungeonPulls"], key=lambda pull: pull["startTime"])
        pairs = {(npc["id"], npc["gameID"]) for npc in fight.get("enemyNPCs") or []}
        for pull in pulls:
            pairs |= {(npc["id"], npc["gameID"]) for npc in pull.get("enemyNPCs") or []}
        actors = actors_of(code)
        if actors is None:
            hits = matching_actors(pairs, actor_lists)
            actors = hits[0] if hits else []
        game_of = {a["id"]: a["gameID"] for a in actors if a.get("gameID") is not None}
        for actor_id, game_id in pairs:
            game_of.setdefault(actor_id, game_id)
        owner = {a["id"]: a.get("petOwner") for a in actors}
        players = set(fight.get("friendlyPlayers") or []) | {
            a["id"] for a in actors if a.get("type") == "Player"
        }

        def enemy(actor_id, players=players, owner=owner, game_of=game_of):
            """The game id an actor is keyed by; None for a player, a player's pet, or no id."""
            if actor_id in players or owner.get(actor_id) in players:
                return None
            return game_of.get(actor_id)

        rows = defaultdict(list)
        for row in debuffs:
            game_id = enemy(row["targetID"])
            if game_id is not None:
                kind_of = row.get("type", "")
                tag = (
                    "apply" if kind_of == "applydebuff"
                    else "remove" if kind_of.startswith("remove")
                    else "other"
                )
                rows[(game_id, row.get("targetInstance") or 0)].append((row["timestamp"], tag))
            source = enemy(row["sourceID"])
            if source is not None:
                rows[(source, row.get("sourceInstance") or 0)].append((row["timestamp"], "npc"))
        for row in casts:
            if row.get("type") == "cast" and row.get("targetID") is not None:
                game_id = enemy(row["targetID"])
                if game_id is not None:
                    key = (game_id, row.get("targetInstance") or 0)
                    rows[key].append((row["timestamp"], "cast"))
        died = defaultdict(set)
        for row in deaths:
            if row.get("type") == "death":
                game_id = enemy(row["targetID"])
                if game_id is not None:
                    died[(game_id, row.get("targetInstance") or 0)].add(row["timestamp"])

        def in_trash(at, pulls=pulls):
            holders = [pull for pull in pulls if pull["startTime"] <= at]
            holder = holders[-1] if holders else pulls[0]
            return holder["encounterID"] == 0

        for key, death_times in died.items():
            events = sorted(rows.get(key, []))
            previous = None
            for death_ms in sorted(death_times):
                life = [
                    (at, tag)
                    for at, tag in events
                    if (previous is None or at > previous)
                    and at <= death_ms
                    and not (
                        tag == "remove"
                        and previous is not None
                        and at - previous <= REMOVAL_GRACE_MS
                    )
                ]
                previous = death_ms
                if not in_trash(death_ms):
                    continue
                first_row = min((at for at, _ in life), default=death_ms)
                first_application = min(
                    (at for at, tag in life if tag == "apply"), default=death_ms
                )
                moved[side].append(first_application - first_row)
                alive[side][0] += death_ms - first_row
                alive[side][1] += death_ms - first_application
                tally[f"{side}: died trash lives"] += 1
                tally[f"{side}: zero-length under first row"] += first_row == death_ms
                tally[f"{side}: zero-length under first application"] += (
                    first_application == death_ms
                )

for side in ("ours", "references"):
    print(f"== {side}")
    for name, count in sorted(tally.items()):
        if name.startswith(f"{side}:"):
            print(f"  {name[len(side) + 2:]}: {count}")
    values = moved[side]
    if not values:
        print("  no died trash life")
        continue
    first_row_s, first_application_s = (total / 1000 for total in alive[side])
    spike_drift = (first_row_s - SPIKE_ALIVE_S[side]) / SPIKE_ALIVE_S[side]
    change = (first_application_s - first_row_s) / first_row_s
    over_10s = sum(1 for value in values if value > 10_000)
    print(f"  the spike counted {SPIKE_LIVES[side]} died trash lives")
    print(f"  first application less first row: {describe(values)}")
    print(f"  lives moved by more than 1 s: {sum(1 for value in values if value > 1_000)}")
    print(f"  lives moved by more than 10 s: {over_10s}")
    print(
        f"  summed alive seconds: first row {first_row_s:.0f}s "
        f"(the spike's {SPIKE_ALIVE_S[side]}s, {spike_drift:+.1%}), "
        f"first application {first_application_s:.0f}s ({change:+.1%})"
    )
    reproduced = abs(spike_drift) <= 0.01
    material = abs(change) > 0.02 or over_10s > 0.01 * len(values)
    print(
        f"  spike reproduced: {'yes' if reproduced else 'NO'}; "
        f"material: {'YES' if material else 'no'}"
    )
```

- [ ] **Step 2: Run it**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run python /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/life_start_check.py > /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/life_start_check.out
```

Then read `life_start_check.out` with the Read tool.

Expected: an `ours` block over 2 fights and a `references` block over 24. Each block prints a `spike reproduced` line and a `material` line.

- [ ] **Step 3: Judge, and stop if it fails**

1. **The baseline must reproduce the spike.** On each side, the first-row sum must sit within 1% of the spike's, and the life count must be close to it. If either side prints `spike reproduced: NO`, the script has not reproduced the spike's method. Compare it against the scratchpad's `trash_spans2.py --by-game` and its output `trash_spans2_bygame.out`, fix the script, and re-run. Judge nothing on a baseline that was not reproduced.
2. **The two rules must agree.** Material means either of these, on either side:
   - summed alive seconds moved by more than 2%;
   - more than 1% of the died lives moved by more than 10 s.

   The spike's two rules, (b) and (c), differed by about 1% of alive time, and the design accepted that as noise. A difference twice that is no longer noise.
3. **If either side prints `material: YES`, stop.** Report to the controller:
   - both blocks of the output;
   - the ten lives that moved furthest, by game id. Add a print to the script for them, naming no player.

   Do not continue to Task 2.

- [ ] **Step 4: Record it in the design**

In `docs/plans/2026-10-13-key-uptime-coverage-design.md`, insert a paragraph directly after the line "The spike's full record is not committed; this section is its measured content." It reads as below, with every figure copied from `life_start_check.out`:

```markdown
*Amended 2026-10-13, while planning:* the life start was re-measured on the cache as §3.2 states
it: the first `applydebuff` row on a copy after its previous death, against the spike's first row
of any kind. On our two full fights, over [ours: died trash lives] died trash lives, the first
application came a median [median] s, p90 [p90] s and at most [max] s after the first row, and
summed alive time moved by [change]. On the references, over [references: died trash lives]
lives, the same figures were [median] s, [p90] s and [max] s, and alive time moved by [change].
[N] lives on ours and [M] on the references moved by more than 10 s. Lives of zero length went
from [first row] to [first application] on ours, and from [first row] to [first application] on
the references. Both sides stay within the 2% of alive time this plan set as material, so the
rule stands.
```

Each bracket is replaced by the figure the output prints on that side's line of the same name. No bracket survives into the commit.

- [ ] **Step 5: Gate and commit**

Run the gate. Nothing under `src/` or `tests/` changed, so it must pass as it did on the branch.

Write `<scratchpad>\task1-msg.txt`:

```text
Measure where the design opens a trash life

The design opens a trash life at the first debuff application on a copy
after its previous death; the spike measured the first row of any kind.
Re-measured on the cache, the two agree within the noise the design
already accepted, so the rule is kept.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
/mingw64/bin/git add docs/plans/2026-10-13-key-uptime-coverage-design.md
```

```bash
/mingw64/bin/git commit -F /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/task1-msg.txt
```

---

### Task 2: Carry each enemy death with its actor and copy, and the report's players

`DebuffLog.deaths` is (game id, timestamp). It has no copy number, so it cannot cut lives, and no actor id, so a player's own hostile pet cannot be filtered out. This task adds both pieces of data beside it and leaves the council rule's input untouched.

**Files:**
- Modify: `src/wowperf/domain/debuffs.py`
- Modify: `src/wowperf/adapters/wcl/ingest.py` (`build_debuff_log`)
- Test: `tests/adapters/wcl/test_ingest_debuffs.py`

**Interfaces:**
- Produces:
  - `EnemyDeathRow(target_id: int, target_instance: int = 0, timestamp_ms: int)` in `wowperf.domain.debuffs`.
  - `DebuffLog.death_rows: tuple[EnemyDeathRow, ...] = ()`, which holds every `death` row, whatever the actor.
  - `DebuffLog.player_ids: tuple[int, ...] = ()`, which holds the actor ids of type `Player`.
- Unchanged: `build_debuff_log(events, actors, ability_names, end_ms, death_events=())` and `DebuffLog.deaths`.

- [ ] **Step 1: Write the failing tests**

In `tests/adapters/wcl/test_ingest_debuffs.py`, change the domain import to `from wowperf.domain.debuffs import EnemyDeathRow` (add the line under the `NpcActor` import), and append:

```python
def test_each_enemy_death_keeps_its_actor_and_its_copy() -> None:
    log = build_debuff_log(
        EVENTS,
        ACTORS,
        {55078: "Blood Plague"},
        9000,
        death_events=[
            {"type": "death", "targetID": 261, "targetInstance": 3, "timestamp": 7000},
            {"type": "death", "targetID": 279, "timestamp": 8000},
            {"type": "death", "targetID": 12345, "timestamp": 8100},
            {"type": "resurrect", "targetID": 279, "timestamp": 8200},
        ],
    )

    # Every death row, even one on an actor with no game id: the domain decides
    # what an enemy is, and an absent copy number is the actor's only copy.
    assert log.death_rows == (
        EnemyDeathRow(target_id=261, target_instance=3, timestamp_ms=7000),
        EnemyDeathRow(target_id=279, target_instance=0, timestamp_ms=8000),
        EnemyDeathRow(target_id=12345, target_instance=0, timestamp_ms=8100),
    )
    # The council rule's own reading is unchanged beside it.
    assert log.deaths == ((189893, 7000), (999, 8000))


def test_the_reports_players_ride_along() -> None:
    assert a_log().player_ids == (171,)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl/test_ingest_debuffs.py -q`
Expected: an ImportError on `EnemyDeathRow`.

- [ ] **Step 3: Implement**

In `src/wowperf/domain/debuffs.py`, add this class after `DebuffEvent`:

```python
class EnemyDeathRow(Frozen):
    """One `death` row of the enemy-deaths stream: which copy of which actor died, and when.

    An absent instance is the actor's only copy, read as 0: measured 2026-10-13,
    no actor of 1,374 carried an absent and a present instance both
    (`docs/plans/2026-10-13-key-uptime-coverage-design.md` §3.1).
    """

    target_id: int
    target_instance: int = 0
    timestamp_ms: int
```

In `DebuffLog`, add these two fields after `deaths`:

```python
    death_rows: tuple[EnemyDeathRow, ...] = ()
    """Every enemy death of the fight by actor and copy, for cutting each enemy into lives."""
    player_ids: tuple[int, ...] = ()
    """The report's players, so that a pet a player owns is never read as an enemy."""
```

In `src/wowperf/adapters/wcl/ingest.py`, import `EnemyDeathRow` beside `DebuffEvent` and `DebuffLog` from `wowperf.domain.debuffs`. Then add these two arguments to the `DebuffLog(...)` that `build_debuff_log` returns, after `deaths=...`:

```python
        death_rows=tuple(
            EnemyDeathRow(
                target_id=event["targetID"],
                target_instance=event.get("targetInstance") or 0,
                timestamp_ms=event["timestamp"],
            )
            for event in death_events
            if event.get("type") == "death"
        ),
        player_ids=tuple(actor["id"] for actor in actors if actor.get("type") == "Player"),
```

Add this sentence to the docstring of `build_debuff_log`: "`death_rows` keeps every death by actor and copy, game id or not: which of them is an enemy is the domain's to decide."

- [ ] **Step 4: Run the tests to see them pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl/test_ingest_debuffs.py -q`
Expected: all pass.

- [ ] **Step 5: Gate and commit**

Run the gate. Write `<scratchpad>\task2-msg.txt`:

```text
Carry each enemy death with its actor and copy in the debuff log

A trash enemy is cut into lives at its deaths, keyed by game id and
copy number, and the council rule's deaths carry neither the copy nor
the actor. The report's players ride along so that a pet a player owns,
which the log lists as hostile, is never read as an enemy.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
/mingw64/bin/git add src/wowperf/domain/debuffs.py src/wowperf/adapters/wcl/ingest.py tests/adapters/wcl/test_ingest_debuffs.py
```

```bash
/mingw64/bin/git commit -F /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/task2-msg.txt
```

---

### Task 3: Cut every enemy of the key into lives

**Files:**
- Create: `src/wowperf/domain/comparison/enemy_lives.py`
- Create: `tests/domain/comparison/test_enemy_lives.py`

**Interfaces:**
- Consumes: Task 2's `EnemyDeathRow`, `DebuffLog.death_rows` and `DebuffLog.player_ids`.
- Produces, in `wowperf.domain.comparison.enemy_lives`:
  - `LifeStretch(StrEnum)`: `TRASH = "trash"`, `ADDS = "adds"`.
  - `EnemyLife(game_id: int, instance: int, start_ms: int, end_ms: int, stretch: LifeStretch)`, with property `key -> tuple[int, int, int]`, which is `(game_id, instance, end_ms)`.
  - `EnemyLives(lives: tuple[EnemyLife, ...] = (), unmeasured_no_death: int = 0, undebuffed_deaths: int = 0)`.
  - `enemy_lives(log: DebuffLog, pulls: Sequence[Pull], bosses: frozenset[int]) -> EnemyLives`, where `bosses` holds the game ids the boss rule measures.
- Test fixtures exported for Task 4: `PLAYER`, `PET`, `OTHER`, `WHELP`, `LASHER`, `BOSS_ACTOR`, `BOSS_GAME`, `LASHER_GAME`, `WHELP_GAME`, `DOT`, `PULLS`, `a_log`, `applied`, `removed` and `died`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/comparison/test_enemy_lives.py`:

```python
# ABOUTME: Every enemy of a key cut into lives, from the first debuff anyone applied to its death.
# ABOUTME: Pins the cuts, a reused instance, one creature under two actor ids, and what is left out.

from wowperf.domain.comparison.enemy_lives import EnemyLife, EnemyLives, LifeStretch, enemy_lives
from wowperf.domain.comparison.pace_boss import NpcActor
from wowperf.domain.debuffs import DebuffEvent, DebuffLog, EnemyDeathRow
from wowperf.domain.model import EnemyNpc, Pull

PLAYER, PET, OTHER = 7, 8, 9
WHELP, WHELP_TWIN, LASHER, TOMB, BOSS_ACTOR, NAMELESS = 30, 31, 32, 33, 50, 77
WHELP_GAME, LASHER_GAME, TOMB_GAME, BOSS_GAME, PET_GAME = 3000, 3200, 3300, 5000, 900
BOSS_NAME = "The Test Colossus"
DOT = 55078
GAME_IDS = {
    # Players carry game id 0 in a real report's actors, so a player is only
    # kept out by being named a player, never by a missing game id.
    PLAYER: 0,
    OTHER: 0,
    PET: PET_GAME,
    WHELP: WHELP_GAME,
    WHELP_TWIN: WHELP_GAME,
    LASHER: LASHER_GAME,
    TOMB: TOMB_GAME,
    BOSS_ACTOR: BOSS_GAME,
}


def a_pull(
    index: int,
    start_ms: int,
    end_ms: int,
    *,
    encounter_id: int = 0,
    name: str = "Pack",
    enemies: tuple[int, ...] = (),
) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name=name,
        encounter_id=encounter_id,
        start_ms=start_ms,
        end_ms=end_ms,
        killed=True,
        x=0,
        y=0,
        enemies=tuple(EnemyNpc(actor_id=actor, game_id=GAME_IDS[actor]) for actor in enemies),
    )


TRASH = a_pull(0, 0, 60_000, enemies=(WHELP, LASHER))
BOSS = a_pull(1, 100_000, 160_000, encounter_id=2001, name=BOSS_NAME, enemies=(BOSS_ACTOR,))
PULLS = (TRASH, BOSS)
NPC_ACTORS = (
    NpcActor(actor_id=BOSS_ACTOR, game_id=BOSS_GAME, name=BOSS_NAME, sub_type="Boss"),
    NpcActor(actor_id=WHELP, game_id=WHELP_GAME, name="Fixture Whelp", sub_type="NPC"),
    NpcActor(actor_id=WHELP_TWIN, game_id=WHELP_GAME, name="Fixture Whelp", sub_type="NPC"),
    NpcActor(actor_id=LASHER, game_id=LASHER_GAME, name="Fixture Lasher", sub_type="NPC"),
)


def applied(
    at: int, *, target: int = WHELP, instance: int = 1, source: int = PLAYER
) -> DebuffEvent:
    return DebuffEvent(
        applied=True,
        timestamp_ms=at,
        source_id=source,
        target_id=target,
        target_instance=instance,
        ability_id=DOT,
    )


def removed(
    at: int, *, target: int = WHELP, instance: int = 1, source: int = PLAYER
) -> DebuffEvent:
    return DebuffEvent(
        applied=False,
        timestamp_ms=at,
        source_id=source,
        target_id=target,
        target_instance=instance,
        ability_id=DOT,
    )


def died(at: int, *, target: int = WHELP, instance: int = 1) -> EnemyDeathRow:
    return EnemyDeathRow(target_id=target, target_instance=instance, timestamp_ms=at)


def a_log(*events: DebuffEvent, deaths: tuple[EnemyDeathRow, ...] = ()) -> DebuffLog:
    return DebuffLog(
        events=events,
        pet_owners=((PET, PLAYER), (TOMB, PLAYER)),
        game_ids=tuple(GAME_IDS.items()),
        npc_actors=NPC_ACTORS,
        ability_names=((DOT, "Blood Plague"),),
        death_rows=deaths,
        player_ids=(PLAYER, OTHER),
        end_ms=200_000,
    )


def lives_of(log: DebuffLog, bosses: frozenset[int] = frozenset({BOSS_GAME})) -> EnemyLives:
    return enemy_lives(log, PULLS, bosses)


def a_life(
    start_ms: int,
    end_ms: int,
    *,
    game_id: int = WHELP_GAME,
    instance: int = 1,
    stretch: LifeStretch = LifeStretch.TRASH,
) -> EnemyLife:
    return EnemyLife(
        game_id=game_id, instance=instance, start_ms=start_ms, end_ms=end_ms, stretch=stretch
    )


def test_a_life_runs_from_the_first_application_by_anyone_to_the_death() -> None:
    found = lives_of(
        a_log(applied(10_000, source=OTHER), applied(20_000), deaths=(died(40_000),))
    )

    assert found == EnemyLives(lives=(a_life(10_000, 40_000),))


def test_an_enemy_is_cut_into_a_life_at_each_of_its_deaths() -> None:
    # The log reuses copy numbers inside one pull: one copy number, two mobs.
    found = lives_of(
        a_log(applied(5_000), applied(30_000), deaths=(died(20_000), died(50_000)))
    )

    assert found.lives == (a_life(5_000, 20_000), a_life(30_000, 50_000))


def test_a_removal_logged_just_after_a_death_opens_no_life() -> None:
    found = lives_of(a_log(applied(5_000), removed(20_050), deaths=(died(20_000),)))

    assert found == EnemyLives(lives=(a_life(5_000, 20_000),))


def test_one_creature_under_two_actor_ids_is_one_enemy() -> None:
    found = lives_of(
        a_log(applied(5_000, target=WHELP), deaths=(died(20_000, target=WHELP_TWIN),))
    )

    assert found.lives == (a_life(5_000, 20_000),)


def test_a_life_with_no_death_is_left_out_and_counted() -> None:
    found = lives_of(a_log(applied(5_000), applied(30_000), deaths=(died(20_000),)))

    assert found == EnemyLives(lives=(a_life(5_000, 20_000),), unmeasured_no_death=1)


def test_an_enemy_debuffed_and_never_killed_is_counted_once() -> None:
    found = lives_of(a_log(applied(5_000), applied(10_000, source=OTHER)))

    assert found == EnemyLives(unmeasured_no_death=1)


def test_a_death_nobody_debuffed_is_a_life_of_no_length_and_counted() -> None:
    found = lives_of(a_log(deaths=(died(20_000, target=LASHER, instance=0),)))

    assert found == EnemyLives(
        lives=(a_life(20_000, 20_000, game_id=LASHER_GAME, instance=0),),
        undebuffed_deaths=1,
    )


def test_a_death_the_log_writes_twice_is_one_death() -> None:
    found = lives_of(a_log(applied(5_000), deaths=(died(20_000), died(20_000))))

    assert found == EnemyLives(lives=(a_life(5_000, 20_000),))


def test_a_player_and_a_pet_a_player_owns_are_never_enemies() -> None:
    # Glacial Tomb and A Knot of Snakes are logged as hostile pets of a player.
    found = lives_of(
        a_log(
            applied(5_000, target=TOMB, instance=0),
            applied(5_000, target=PET, instance=0),
            applied(5_000, target=OTHER, instance=0),
            deaths=(
                died(20_000, target=TOMB, instance=0),
                died(20_000, target=PET, instance=0),
                died(20_000, target=OTHER, instance=0),
            ),
        )
    )

    assert found == EnemyLives()


def test_a_life_belongs_to_the_pull_holding_its_death() -> None:
    # The first lasher dies after the trash pull closed and before the boss pull
    # opened, so the trash pull still holds it. The second dies inside the boss
    # pull: an add.
    found = lives_of(
        a_log(
            applied(50_000, target=LASHER, instance=1),
            applied(120_000, target=LASHER, instance=2),
            deaths=(
                died(61_000, target=LASHER, instance=1),
                died(150_000, target=LASHER, instance=2),
            ),
        )
    )

    assert found.lives == (
        a_life(50_000, 61_000, game_id=LASHER_GAME, instance=1),
        a_life(120_000, 150_000, game_id=LASHER_GAME, instance=2, stretch=LifeStretch.ADDS),
    )


def test_a_measured_boss_is_left_to_the_boss_rule() -> None:
    # A wipe: the boss carried a debuff and never died. As a life it would read
    # as an enemy with no death; the boss rule measures it instead.
    found = lives_of(a_log(applied(110_000, target=BOSS_ACTOR, instance=0)))

    assert found == EnemyLives()


def test_a_boss_no_window_measured_is_an_add() -> None:
    found = lives_of(
        a_log(
            applied(110_000, target=BOSS_ACTOR, instance=0),
            deaths=(died(150_000, target=BOSS_ACTOR, instance=0),),
        ),
        bosses=frozenset(),
    )

    assert found.lives == (
        a_life(110_000, 150_000, game_id=BOSS_GAME, instance=0, stretch=LifeStretch.ADDS),
    )


def test_an_actor_with_no_game_id_is_no_enemy() -> None:
    found = lives_of(
        a_log(applied(5_000, target=NAMELESS), deaths=(died(20_000, target=NAMELESS),))
    )

    assert found == EnemyLives()


def test_a_fight_with_no_pulls_holds_no_life() -> None:
    log = a_log(applied(5_000), deaths=(died(20_000),))

    assert enemy_lives(log, (), frozenset()) == EnemyLives()


def test_a_life_is_keyed_by_its_enemy_and_its_death() -> None:
    assert a_life(5_000, 20_000).key == (WHELP_GAME, 1, 20_000)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_enemy_lives.py -q`
Expected: `ModuleNotFoundError: No module named 'wowperf.domain.comparison.enemy_lives'`.

- [ ] **Step 3: Implement**

Create `src/wowperf/domain/comparison/enemy_lives.py`:

```python
# ABOUTME: Every enemy of a key cut into lives, from the first debuff anyone applied to its death.
# ABOUTME: A life belongs to the pull holding its death; a measured boss is left to the boss rule.

from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum

from wowperf.domain.base import Frozen
from wowperf.domain.debuffs import DebuffLog
from wowperf.domain.model import Pull


class LifeStretch(StrEnum):
    """Which stretch of the key holds a life: the pull holding its death decides."""

    TRASH = "trash"
    ADDS = "adds"


class EnemyLife(Frozen):
    """One life of one copy of one kind of enemy, from its first debuff to its death."""

    game_id: int
    instance: int
    start_ms: int
    end_ms: int
    stretch: LifeStretch

    @property
    def key(self) -> tuple[int, int, int]:
        """This life and no other: what two players' copies are compared on when shared."""
        return (self.game_id, self.instance, self.end_ms)


class EnemyLives(Frozen):
    """Every measured enemy life of a key, and what could not be measured, counted."""

    lives: tuple[EnemyLife, ...] = ()
    unmeasured_no_death: int = 0
    """Copies debuffed after their last death with no death to close them: left out."""
    undebuffed_deaths: int = 0
    """Deaths with no application since that copy's previous death: lives of no length."""


def enemy_lives(log: DebuffLog, pulls: Sequence[Pull], bosses: frozenset[int]) -> EnemyLives:
    """Every enemy life of the key outside the measured bosses, and what could not be measured.

    An enemy is (game id, instance), as the pairing keys a target: one creature
    can be logged under two actor ids, and the log reuses copy numbers, so each
    copy is cut into lives at its deaths. A life opens at the first application
    by anyone on that copy after its previous death, so a removal logged just
    after a death never opens one, and it closes at its death. Measured
    2026-10-13 (`docs/plans/2026-10-13-key-uptime-coverage-design.md` §3.1):
    the pull's start would triple a trash mob's alive time, since pulls chain
    packs, and the first debuff sits within about a second of the richest
    stream's first sight of the mob.

    A copy that died with no application since its previous death is a life of
    no length, counted in `undebuffed_deaths`: it adds no alive time and still
    counts for reach. Applications after a copy's last death with no death to
    close them are one life left out, counted in `unmeasured_no_death`. A death
    the log writes twice at one millisecond is one death.

    Left out entirely: a player, and a pet a player owns, which the log lists
    as hostile (Glacial Tomb, A Knot of Snakes); an actor with no game id, which
    nothing keys; and every game id in `bosses`, which the boss rule measures.

    A life belongs to the pull holding its death, the last pull starting at or
    before it: the log stamps a kill's last death a few milliseconds after its
    pull closed (measured 2026-10-08 on council kills), so a death between two
    pulls is the earlier pull's, and a death before every pull is the first
    pull's. A boss pull makes a life an add, a trash pull trash. A fight with no
    pulls has no stretch to put a life in, and holds none.
    """
    if not pulls:
        return EnemyLives()
    game_ids = dict(log.game_ids)
    owners = dict(log.pet_owners)
    players = frozenset(log.player_ids)

    def enemy(actor_id: int) -> int | None:
        """The game id this actor is measured under, or None when it is no enemy here."""
        if actor_id in players or owners.get(actor_id) in players:
            return None
        game_id = game_ids.get(actor_id)
        if game_id is None or game_id in bosses:
            return None
        return game_id

    applied: dict[tuple[int, int], list[int]] = defaultdict(list)
    for event in log.events:
        if not event.applied:
            continue
        game_id = enemy(event.target_id)
        if game_id is not None:
            applied[(game_id, event.target_instance)].append(event.timestamp_ms)
    died: dict[tuple[int, int], set[int]] = defaultdict(set)
    for row in log.death_rows:
        game_id = enemy(row.target_id)
        if game_id is not None:
            died[(game_id, row.target_instance)].add(row.timestamp_ms)

    lives: list[EnemyLife] = []
    unmeasured = 0
    undebuffed = 0
    for key in sorted(applied.keys() | died.keys()):
        game_id, instance = key
        applications = sorted(applied.get(key, ()))
        previous: int | None = None
        for death_ms in sorted(died.get(key, ())):
            opened = next(
                (
                    at
                    for at in applications
                    if (previous is None or at > previous) and at <= death_ms
                ),
                None,
            )
            if opened is None:
                undebuffed += 1
                opened = death_ms
            lives.append(
                EnemyLife(
                    game_id=game_id,
                    instance=instance,
                    start_ms=opened,
                    end_ms=death_ms,
                    stretch=_stretch_at(pulls, death_ms),
                )
            )
            previous = death_ms
        if any(previous is None or at > previous for at in applications):
            unmeasured += 1
    return EnemyLives(
        lives=tuple(lives), unmeasured_no_death=unmeasured, undebuffed_deaths=undebuffed
    )


def _stretch_at(pulls: Sequence[Pull], at_ms: int) -> LifeStretch:
    """The stretch of the pull holding a death: the last pull starting at or before it."""
    started = [pull for pull in pulls if pull.start_ms <= at_ms]
    holder = (
        max(started, key=lambda pull: pull.start_ms)
        if started
        else min(pulls, key=lambda pull: pull.start_ms)
    )
    return LifeStretch.ADDS if holder.is_boss else LifeStretch.TRASH
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_enemy_lives.py -q`
Expected: 15 passed.

- [ ] **Step 5: Gate and commit**

Run the gate. Write `<scratchpad>\task3-msg.txt`:

```text
Cut every enemy of a key into lives

Trash coverage needs each enemy's alive time, and the log records a
death but never an appearance. A life opens at the first debuff anyone
applied to that copy since its previous death and closes at its death,
the rule the design measured; a measured boss is left to the boss rule,
and a player's own hostile pet is no enemy.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/enemy_lives.py tests/domain/comparison/test_enemy_lives.py
```

```bash
/mingw64/bin/git commit -F /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/task3-msg.txt
```

---

### Task 4: Measure coverage and reach per stretch, and read the shared rule per life

**Files:**
- Modify: `src/wowperf/domain/comparison/boss_debuffs.py`
- Create: `src/wowperf/domain/comparison/key_debuffs.py`
- Create: `tests/domain/comparison/test_key_debuffs.py`
- Modify tests:
  - `tests/domain/comparison/test_boss_debuffs.py`, its import line only;
  - `tests/domain/comparison/test_debuff_uptime.py`, its import lines only;
  - `tests/e2e/test_boss_debuffs_e2e.py`.

**Interfaces:**
- Consumes: Task 3's `EnemyLife`, `LifeStretch` and `enemy_lives`.
- Produces, in `wowperf.domain.comparison.boss_debuffs`:
  - `Target = tuple[int, ...]`. A boss is `(window index, game id)` and a life is `EnemyLife.key`.
  - `Held = dict[tuple[int, int], dict[Target, list[Span]]]`.
  - `held_on_bosses(windows: Sequence[BossWindow], intervals: Sequence[DebuffInterval], owners: frozenset[int]) -> Held`.
  - `bosses_held_by(windows: tuple[BossWindow, ...], held: Held, owner_id: int, ability_names: tuple[tuple[int, str], ...], tally: PairingTally, shared_with: tuple[tuple[int, tuple[int, ...]], ...]) -> BossDebuffs`.
  - `find_shared(held: Mapping[tuple[int, int], Mapping[Target, Sequence[Span]]], owner_id: int)`.
  - `merged_spans(spans: Iterable[Span]) -> list[Span]` and `length_ms(spans: Iterable[Span]) -> int`, renamed from `_merged` and `_length_ms`.
  - `BossDebuffs.reached: tuple[tuple[int, int], ...] = ()`, as (ability id, boss targets it covered at all).
  - `BossDebuffs.targets`, a property counting the boss targets of the measured windows.
  - `boss_debuffs` leaves this module.
- Produces, in `wowperf.domain.comparison.key_debuffs`:
  - `StretchCover(lives: int = 0, alive_ms: int = 0, covered: tuple[tuple[int, int], ...] = (), reached: tuple[tuple[int, int], ...] = ())`. Its property `seconds -> float`, and its methods `coverage(ability_id) -> float | None` and `reach(ability_id) -> float | None`.
  - `combined(*covers: StretchCover) -> StretchCover`.
  - `KeyDebuffs(bosses: BossDebuffs = BossDebuffs(), trash: StretchCover = StretchCover(), adds: StretchCover = StretchCover(), life_names: tuple[tuple[int, str], ...] = (), unmeasured_no_death: int = 0, undebuffed_deaths: int = 0)`. Its properties are `on_bosses -> StretchCover`, `overall -> StretchCover`, `names -> tuple[tuple[int, str], ...]` and `shared_with`.
  - `held_on_lives(lives: Sequence[EnemyLife], intervals: Sequence[DebuffInterval], owners: frozenset[int]) -> Held`.
  - `key_debuffs(log: DebuffLog, pulls: Sequence[Pull], owner_id: int, players: frozenset[int]) -> KeyDebuffs`.
  - `boss_debuffs(log, pulls, owner_id, players) -> BossDebuffs`, which is `key_debuffs(...).bosses`.

- [ ] **Step 1: Point the existing tests at the moved function (they fail to import until Step 3)**

- In `tests/domain/comparison/test_boss_debuffs.py`, remove `boss_debuffs,` from the `wowperf.domain.comparison.boss_debuffs` import, and add `from wowperf.domain.comparison.key_debuffs import boss_debuffs` below it. Change nothing else in that file: each of its tests now pins the boss figure through the path the comparison runs.
- In `tests/domain/comparison/test_debuff_uptime.py`, likewise remove `boss_debuffs,` from the `boss_debuffs` import and add `from wowperf.domain.comparison.key_debuffs import boss_debuffs`.
- In `tests/e2e/test_boss_debuffs_e2e.py`, replace the import line `from wowperf.domain.comparison.boss_debuffs import boss_debuffs, boss_windows_of` with:

```python
from wowperf.domain.comparison.boss_debuffs import boss_windows_of
from wowperf.domain.comparison.key_debuffs import boss_debuffs, key_debuffs
```

  Then append this block at the end of its test function, after the `left_open` assertion:

```python
    # Every stretch's share stays within the alive time and the lives it was
    # measured over, for every player of the key.
    for player in run.players:
        key = key_debuffs(log, run.pulls, player.actor_id, players)
        for stretch in (key.overall, key.on_bosses, key.trash, key.adds):
            for ability_id, ms in stretch.covered:
                assert ms <= stretch.alive_ms, (ability_id, ms, stretch.alive_ms)
            for ability_id, count in stretch.reached:
                assert count <= stretch.lives, (ability_id, count, stretch.lives)
```

- [ ] **Step 2: Write the failing tests**

Create `tests/domain/comparison/test_key_debuffs.py`:

```python
# ABOUTME: One player's debuffs over every enemy of a key: coverage and reach on each stretch.
# ABOUTME: Pins the summing over lives, adds in Overall only, the boss figure unmoved, sharing.

from tests.domain.comparison.test_enemy_lives import (
    BOSS_ACTOR,
    DOT,
    LASHER,
    OTHER,
    PET,
    PLAYER,
    PULLS,
    WHELP,
    a_log,
    applied,
    died,
    removed,
)
from wowperf.domain.comparison.key_debuffs import (
    KeyDebuffs,
    StretchCover,
    boss_debuffs,
    combined,
    key_debuffs,
)
from wowperf.domain.debuffs import DebuffEvent, DebuffLog

RUN_PLAYERS = frozenset({PLAYER, OTHER})


def held_on(
    target: int, instance: int, start_ms: int, end_ms: int, *, source: int = PLAYER
) -> tuple[DebuffEvent, DebuffEvent]:
    """One application and its removal, by `source`, on one copy of one enemy."""
    return (
        applied(start_ms, target=target, instance=instance, source=source),
        removed(end_ms, target=target, instance=instance, source=source),
    )


def mine(log: DebuffLog, owner_id: int = PLAYER) -> KeyDebuffs:
    return key_debuffs(log, PULLS, owner_id, RUN_PLAYERS)


def test_trash_coverage_sums_debuff_time_over_summed_alive_time() -> None:
    # The first whelp lives 10-50s, opened by a teammate's application, and
    # carried ours 20-40s. The second lives 10-20s and carried ours 10-15s. The
    # lasher died undebuffed at 30s. That is 25s of 50s alive, on 2 lives of 3.
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 50_000, source=OTHER),
            *held_on(WHELP, 1, 20_000, 40_000),
            *held_on(WHELP, 2, 10_000, 15_000),
            deaths=(
                died(50_000),
                died(20_000, instance=2),
                died(30_000, target=LASHER, instance=0),
            ),
        )
    )

    assert found.trash == StretchCover(
        lives=3, alive_ms=50_000, covered=((DOT, 25_000),), reached=((DOT, 2),)
    )
    assert found.trash.coverage(DOT) == 0.5
    assert found.trash.reach(DOT) == 2 / 3
    assert found.undebuffed_deaths == 1


def test_a_debuff_reaching_past_a_death_is_clipped_to_the_life() -> None:
    # Ours went on at 10s and its removal was logged at 60s, but the whelp died at
    # 40s: the life, and the debuff counted on it, end there.
    found = mine(a_log(*held_on(WHELP, 1, 10_000, 60_000), deaths=(died(40_000),)))

    assert found.trash == StretchCover(
        lives=1, alive_ms=30_000, covered=((DOT, 30_000),), reached=((DOT, 1),)
    )
    assert found.unmeasured_no_death == 0


def test_a_debuff_outliving_its_copys_death_counts_on_the_next_life_it_overlaps() -> None:
    # Ours went on whelp 1 at 10s and its removal was logged at 40s, though that
    # copy died at 20s. A teammate's application at 25s opens the copy's next
    # life, which dies at 50s. Ours is clipped to each life it overlaps: 10s on
    # the first and 15s on the second, nothing in the 5s between them. Measured
    # 2026-10-13 over 26 cached fights: 1,801 of 156,175 paired intervals outlived
    # a death of their copy, and the time past it was 0.38% of all interval time,
    # so this is pinned, not changed.
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 40_000),
            *held_on(WHELP, 1, 25_000, 30_000, source=OTHER),
            deaths=(died(20_000), died(50_000)),
        )
    )

    assert found.trash == StretchCover(
        lives=2, alive_ms=35_000, covered=((DOT, 25_000),), reached=((DOT, 2),)
    )


def test_a_players_and_their_pets_copies_on_one_life_count_once() -> None:
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 30_000),
            *held_on(WHELP, 1, 20_000, 40_000, source=PET),
            deaths=(died(50_000),),
        )
    )

    assert found.trash.covered == ((DOT, 30_000),)
    assert found.trash.alive_ms == 40_000


def test_an_add_counts_in_overall_and_not_in_trash() -> None:
    # Trash: a whelp alive 10-50s carried ours 10-30s. Boss: ours 100-130s of
    # its 60s pull. Add: a lasher alive 120-150s inside the boss pull carried
    # ours all of it. Overall is 80s of 130s.
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 30_000),
            *held_on(BOSS_ACTOR, 0, 100_000, 130_000),
            *held_on(LASHER, 3, 120_000, 150_000),
            deaths=(died(50_000), died(150_000, target=LASHER, instance=3)),
        )
    )

    assert found.trash == StretchCover(
        lives=1, alive_ms=40_000, covered=((DOT, 20_000),), reached=((DOT, 1),)
    )
    assert found.adds == StretchCover(
        lives=1, alive_ms=30_000, covered=((DOT, 30_000),), reached=((DOT, 1),)
    )
    assert found.on_bosses == StretchCover(
        lives=1, alive_ms=60_000, covered=((DOT, 30_000),), reached=((DOT, 1),)
    )
    assert found.overall.coverage(DOT) == 80_000 / 130_000
    assert found.overall.reach(DOT) == 1.0


def test_the_boss_figure_is_the_boss_rule_whatever_died_beside_it() -> None:
    alone = mine(a_log(*held_on(BOSS_ACTOR, 0, 100_000, 130_000)))
    beside = mine(
        a_log(
            *held_on(BOSS_ACTOR, 0, 100_000, 130_000),
            *held_on(WHELP, 1, 10_000, 30_000),
            *held_on(LASHER, 3, 120_000, 150_000),
            deaths=(died(50_000), died(150_000, target=LASHER, instance=3)),
        )
    )

    assert beside.bosses == alone.bosses
    assert beside.bosses.covered == ((2001, DOT, 30_000),)
    assert beside.bosses.seconds == 60.0


def test_boss_debuffs_is_the_boss_half_of_the_key() -> None:
    log = a_log(
        *held_on(BOSS_ACTOR, 0, 100_000, 130_000),
        *held_on(WHELP, 1, 10_000, 30_000),
        deaths=(died(50_000),),
    )

    assert boss_debuffs(log, PULLS, PLAYER, RUN_PLAYERS) == mine(log).bosses


def test_a_boss_is_reached_once_however_often_it_carried_the_debuff() -> None:
    found = mine(
        a_log(
            *held_on(BOSS_ACTOR, 0, 100_000, 110_000),
            *held_on(BOSS_ACTOR, 0, 120_000, 130_000),
        )
    )

    assert found.bosses.reached == ((DOT, 1),)
    assert found.bosses.targets == 1


def test_two_players_who_swap_a_debuff_on_one_trash_life_share_it() -> None:
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 30_000),
            *held_on(WHELP, 1, 30_000, 50_000, source=OTHER),
            deaths=(died(50_000),),
        )
    )

    assert found.shared_with == ((DOT, (OTHER,)),)


def test_copies_that_coexist_on_one_trash_life_are_each_casters_own() -> None:
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 40_000),
            *held_on(WHELP, 1, 20_000, 50_000, source=OTHER),
            deaths=(died(50_000),),
        )
    )

    assert found.shared_with == ()


def test_two_players_on_different_lives_are_never_compared() -> None:
    # Ours only ever on one whelp, theirs only on the other: the copies never met.
    # Ours on whelp 1 from 10s to 30s and theirs on whelp 2 from 30s to 50s, so
    # the two never overlap in time either. Keyed by copy there is no common
    # target to compare them on. Keyed by game id alone, theirs would land on
    # whelp 1's 10-50s life beside ours, overlap it for 0s, and read as shared.
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 30_000),
            *held_on(WHELP, 2, 30_000, 50_000, source=OTHER),
            deaths=(died(50_000), died(50_000, instance=2)),
        )
    )

    assert found.shared_with == ()


def test_a_debuff_seen_only_on_trash_is_named() -> None:
    found = mine(a_log(*held_on(WHELP, 1, 10_000, 30_000), deaths=(died(50_000),)))

    assert found.names == ((DOT, "Blood Plague"),)
    assert found.bosses.names == ()


def test_what_could_not_be_measured_rides_along() -> None:
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 30_000),
            deaths=(died(40_000, target=LASHER, instance=0),),
        )
    )

    assert (found.unmeasured_no_death, found.undebuffed_deaths) == (1, 1)


def test_a_stretch_with_nothing_measured_has_no_share() -> None:
    assert StretchCover().coverage(DOT) is None
    assert StretchCover().reach(DOT) is None
    assert StretchCover(lives=1).coverage(DOT) is None
    assert StretchCover(lives=1).reach(DOT) == 0.0


def test_stretches_combine_by_summing() -> None:
    first = StretchCover(lives=2, alive_ms=10_000, covered=((DOT, 4_000),), reached=((DOT, 1),))
    second = StretchCover(
        lives=1,
        alive_ms=5_000,
        covered=((DOT, 5_000), (DOT + 1, 1_000)),
        reached=((DOT, 1), (DOT + 1, 1)),
    )

    assert combined(first, second) == StretchCover(
        lives=3,
        alive_ms=15_000,
        covered=((DOT, 9_000), (DOT + 1, 1_000)),
        reached=((DOT, 2), (DOT + 1, 1)),
    )
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison -q`
Expected: collection errors, `ModuleNotFoundError: No module named 'wowperf.domain.comparison.key_debuffs'`, in `test_key_debuffs.py`, `test_boss_debuffs.py` and `test_debuff_uptime.py`.

- [ ] **Step 4: Split `boss_debuffs.py`'s figure into reusable halves**

In `src/wowperf/domain/comparison/boss_debuffs.py`:

1. Replace `from wowperf.domain.debuffs import DebuffLog, PairingTally, pair_debuffs` with `from wowperf.domain.debuffs import DebuffInterval, PairingTally`. The function that read the log moves out.
2. After the `Span` alias and its docstring, add:

```python
Target = tuple[int, ...]
"""What two owners' copies of a debuff are compared on: one target within one pull.

A boss is (window index, boss game id). An enemy's life is (game id, instance,
death ms), which names one life and so one pull. The two shapes differ in
length, so they never collide.
"""

Held = dict[tuple[int, int], dict[Target, list[Span]]]
"""Clipped spans keyed by (owner, ability id), then by the target they sat on."""
```

3. In `BossDebuffs`, add this field after `names`:

```python
    reached: tuple[tuple[int, int], ...] = ()
    """(ability id, measured boss targets it covered for any time at all), for reach."""
```

   Replace the docstring of `shared_with` with `"""(ability id, the other players' actor ids), for each debuff `find_shared` finds shared over every target of the key, bosses and enemy lives alike."""`, wrapped to the line limit. Then add this property after `deathless`:

```python
    @property
    def targets(self) -> int:
        """Boss targets of the measured pulls: the Bosses stretch's lives, for reach."""
        return sum(len(window.targets) for window in self.windows if window.withheld is None)
```

4. Replace the whole of `def boss_debuffs(...)` with:

```python
def held_on_bosses(
    windows: Sequence[BossWindow], intervals: Sequence[DebuffInterval], owners: frozenset[int]
) -> Held:
    """Every owner's spans on each measured boss, each clipped to that boss's span.

    The boss is matched by game id, for the same reason the pairing keys on it.
    """
    held: Held = {}
    for index, window in enumerate(windows):
        for target in window.targets:
            for one in intervals:
                if one.owner_id not in owners or one.target_game_id != target.game_id:
                    continue
                start_ms = max(one.start_ms, target.start_ms)
                end_ms = min(one.end_ms, target.end_ms)
                if end_ms > start_ms:
                    by_target = held.setdefault((one.owner_id, one.ability_id), {})
                    by_target.setdefault((index, target.game_id), []).append((start_ms, end_ms))
    return held


def bosses_held_by(
    windows: tuple[BossWindow, ...],
    held: Held,
    owner_id: int,
    ability_names: tuple[tuple[int, str], ...],
    tally: PairingTally,
    shared_with: tuple[tuple[int, tuple[int, ...]], ...],
) -> BossDebuffs:
    """One owner's figure on the measured bosses, from every owner's spans on them.

    A player's and their pets' copies on one boss are merged before they are
    counted, and a boss target reached for any time at all counts once.
    """
    covered: dict[tuple[int, int], int] = defaultdict(int)
    reached: dict[int, int] = defaultdict(int)
    for (owner, ability_id), by_target in held.items():
        if owner != owner_id:
            continue
        for (index, _), spans in by_target.items():
            covered[(windows[index].encounter_id, ability_id)] += length_ms(merged_spans(spans))
            reached[ability_id] += 1
    names = dict(ability_names)
    return BossDebuffs(
        windows=windows,
        covered=tuple(
            (encounter_id, ability_id, ms)
            for (encounter_id, ability_id), ms in sorted(covered.items())
        ),
        names=tuple(
            (ability_id, names.get(ability_id, f"Unknown ability {ability_id}"))
            for ability_id in sorted({ability_id for _, ability_id in covered})
        ),
        reached=tuple(sorted(reached.items())),
        tally=tally,
        shared_with=shared_with,
    )
```

5. Replace `find_shared`, `_overlap_ms`, `_merged` and `_length_ms` with the following. Only the target type, the helper names and the sentences naming a boss change. The second paragraph of `find_shared`'s docstring is kept word for word.

```python
def find_shared(
    held: Mapping[tuple[int, int], Mapping[Target, Sequence[Span]]], owner_id: int
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Each debuff this owner shares one slot of with other players, and who those are.

    `held` is every player's clipped spans on the measured targets, keyed by
    (owner, ability id) and then by target: a boss as (window index, boss game
    id), an enemy's life as (game id, instance, death ms). A debuff is
    exclusive when at least two owners held it and no two of them overlapped by
    more than `SHARED_OVERLAP_TOLERANCE_S` in total, the overlaps measured
    target by target and summed: a teammate's application replaced the one
    before it. Only owners who held it on a common target are compared: two
    copies that each kept to a different boss of a council, or to a different
    mob, never met, which shows nothing either way. Several owners holding it
    is not enough on its own, since copies of a per-caster debuff coexist.

    It is shared with this owner when it is exclusive and someone else held it.
    That includes a debuff this owner never held, once two others took it over
    from each other. Beside a single other owner, the overlap that would show
    exclusivity has no second owner to be measured against, so the debuff is
    not shared and its zero stays unjudged.
    """
    holders: dict[int, dict[int, dict[Target, list[Span]]]] = defaultdict(dict)
    for (owner, ability_id), by_target in held.items():
        holders[ability_id][owner] = {
            target: merged_spans(spans) for target, spans in by_target.items()
        }

    shared: list[tuple[int, tuple[int, ...]]] = []
    for ability_id in sorted(holders):
        owners = holders[ability_id]
        others = tuple(sorted(owner for owner in owners if owner != owner_id))
        pairs = [
            (first, second)
            for first, second in combinations(owners.values(), 2)
            if first.keys() & second.keys()
        ]
        exclusive = bool(pairs) and all(
            _overlap_ms(first, second) <= SHARED_OVERLAP_TOLERANCE_S * 1000
            for first, second in pairs
        )
        if exclusive and others:
            shared.append((ability_id, others))
    return tuple(shared)


def _overlap_ms(
    first: Mapping[Target, Sequence[Span]],
    second: Mapping[Target, Sequence[Span]],
) -> int:
    """The milliseconds two owners' copies of one debuff sat on the same target at once.

    Target by target, each alone less the two together is exactly the time
    counted twice; those are summed. Every edge is a whole millisecond, so it is
    exact.
    """
    return sum(
        length_ms(first[target])
        + length_ms(second[target])
        - length_ms(merged_spans([*first[target], *second[target]]))
        for target in first.keys() & second.keys()
    )


def merged_spans(spans: Iterable[Span]) -> list[Span]:
    """The spans, overlaps joined, in order."""
    merged: list[Span] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def length_ms(spans: Iterable[Span]) -> int:
    """The milliseconds the spans cover, summed as given."""
    return sum(end - start for start, end in spans)
```

`encounter_share` and `boss_windows_of` are unchanged.

- [ ] **Step 5: Create `key_debuffs.py`**

```python
# ABOUTME: One player's debuffs over every enemy of a key: coverage and reach on each stretch.
# ABOUTME: Bosses keep the boss rule; trash and adds are read life by life, first debuff to death.

from collections import defaultdict
from collections.abc import Sequence

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.boss_debuffs import (
    BossDebuffs,
    Held,
    boss_windows_of,
    bosses_held_by,
    find_shared,
    held_on_bosses,
    length_ms,
    merged_spans,
)
from wowperf.domain.comparison.enemy_lives import EnemyLife, LifeStretch, enemy_lives
from wowperf.domain.debuffs import DebuffInterval, DebuffLog, pair_debuffs
from wowperf.domain.model import Pull


class StretchCover(Frozen):
    """One stretch of a key: its measured lives, and what one player's debuffs did on them.

    `covered` sums, life by life, the time a debuff sat on each life, the
    player's and their pets' copies merged per life first. `reached` counts the
    lives it sat on at all. A life of no length adds a life and no time.
    """

    lives: int = 0
    alive_ms: int = 0
    covered: tuple[tuple[int, int], ...] = ()
    """(ability id, milliseconds it covered these lives, summed over them)."""
    reached: tuple[tuple[int, int], ...] = ()
    """(ability id, lives it covered for any time at all)."""

    @property
    def seconds(self) -> float:
        """The stretch's summed alive time: the denominator of its coverage."""
        return self.alive_ms / 1000

    def coverage(self, ability_id: int) -> float | None:
        """The share of the alive time this debuff covered, or None with none to share."""
        if self.alive_ms <= 0:
            return None
        return dict(self.covered).get(ability_id, 0) / self.alive_ms

    def reach(self, ability_id: int) -> float | None:
        """The share of the lives this debuff sat on at all, or None with no life measured."""
        if self.lives <= 0:
            return None
        return dict(self.reached).get(ability_id, 0) / self.lives


def combined(*covers: StretchCover) -> StretchCover:
    """Several stretches read as one: lives, alive time, covered time and reach summed."""
    covered: dict[int, int] = defaultdict(int)
    reached: dict[int, int] = defaultdict(int)
    for cover in covers:
        for ability_id, ms in cover.covered:
            covered[ability_id] += ms
        for ability_id, count in cover.reached:
            reached[ability_id] += count
    return StretchCover(
        lives=sum(cover.lives for cover in covers),
        alive_ms=sum(cover.alive_ms for cover in covers),
        covered=tuple(sorted(covered.items())),
        reached=tuple(sorted(reached.items())),
    )


class KeyDebuffs(Frozen):
    """One player's debuffs over every enemy of one key, stretch by stretch.

    `bosses` is the boss figure, built by the boss rule and unmoved by anything
    that died beside a boss. `trash` holds every life whose death fell in a
    trash pull, and `adds` every other life whose death fell in a boss pull.
    Overall is the three summed, and it is the stretch the verdict reads.
    """

    bosses: BossDebuffs = BossDebuffs()
    trash: StretchCover = StretchCover()
    adds: StretchCover = StretchCover()
    life_names: tuple[tuple[int, str], ...] = ()
    """(ability id, name), for every debuff in `trash` or `adds`."""
    unmeasured_no_death: int = 0
    """Enemies debuffed after their last death with no death to close them: left out."""
    undebuffed_deaths: int = 0
    """Deaths with no application since that copy's previous death: lives of no length."""

    @property
    def on_bosses(self) -> StretchCover:
        """The Bosses stretch: each boss target of a measured pull is one life."""
        targets = [
            target
            for window in self.bosses.windows
            if window.withheld is None
            for target in window.targets
        ]
        covered: dict[int, int] = defaultdict(int)
        for _, ability_id, ms in self.bosses.covered:
            covered[ability_id] += ms
        return StretchCover(
            lives=len(targets),
            alive_ms=sum(target.end_ms - target.start_ms for target in targets),
            covered=tuple(sorted(covered.items())),
            reached=self.bosses.reached,
        )

    @property
    def overall(self) -> StretchCover:
        """Bosses, trash and adds together: the stretch the verdict reads."""
        return combined(self.on_bosses, self.trash, self.adds)

    @property
    def names(self) -> tuple[tuple[int, str], ...]:
        """(ability id, name) of every debuff covering any measured target, by id."""
        return tuple(sorted((dict(self.bosses.names) | dict(self.life_names)).items()))

    @property
    def shared_with(self) -> tuple[tuple[int, tuple[int, ...]], ...]:
        """(ability id, the other players' actor ids) for each debuff found shared."""
        return self.bosses.shared_with


def held_on_lives(
    lives: Sequence[EnemyLife], intervals: Sequence[DebuffInterval], owners: frozenset[int]
) -> Held:
    """Every owner's spans on each enemy life, each clipped to that life.

    A life is matched by game id and copy number, as the pairing keys a target,
    so a debuff on one copy of a mob never counts on another copy beside it.
    """
    by_enemy: dict[tuple[int, int], list[EnemyLife]] = defaultdict(list)
    for life in lives:
        by_enemy[(life.game_id, life.instance)].append(life)
    held: Held = {}
    for one in intervals:
        if one.owner_id not in owners:
            continue
        for life in by_enemy.get((one.target_game_id, one.target_instance), ()):
            start_ms = max(one.start_ms, life.start_ms)
            end_ms = min(one.end_ms, life.end_ms)
            if end_ms > start_ms:
                by_life = held.setdefault((one.owner_id, one.ability_id), {})
                by_life.setdefault(life.key, []).append((start_ms, end_ms))
    return held


def key_debuffs(
    log: DebuffLog, pulls: Sequence[Pull], owner_id: int, players: frozenset[int]
) -> KeyDebuffs:
    """What this player, and their pets, kept on every enemy of this key.

    The boss is matched by game id, for the same reason the pairing keys on it,
    and each interval is clipped to the span of the boss it sat on. Every other
    enemy is cut into lives by `enemy_lives` and matched by game id and copy
    number; each interval is clipped to the life it sat on.

    `players` is the actor ids of the run's players, the only owners whose
    debuffs `find_shared` reads: a pet is already folded into its owner by the
    pairing, and an enemy is never a player. A reference is read with none, so
    nothing on its side is ever shared. The shared rule reads every target of
    the key at once, bosses and lives, and the boss figure carries its answer.
    """
    windows = boss_windows_of(pulls, log.npc_actors, log.deaths)
    intervals, tally = pair_debuffs(log)
    owners = players | {owner_id}
    boss_ids = frozenset(target.game_id for window in windows for target in window.targets)
    found = enemy_lives(log, pulls, boss_ids)
    on_bosses = held_on_bosses(windows, intervals, owners)
    on_lives = held_on_lives(found.lives, intervals, owners)
    everywhere: Held = {key: dict(by_target) for key, by_target in on_bosses.items()}
    for key, by_life in on_lives.items():
        everywhere.setdefault(key, {}).update(by_life)
    trash = _cover(found.lives, on_lives, owner_id, LifeStretch.TRASH)
    adds = _cover(found.lives, on_lives, owner_id, LifeStretch.ADDS)
    names = dict(log.ability_names)
    on_lives_abilities = {ability_id for ability_id, _ in (*trash.covered, *adds.covered)}
    return KeyDebuffs(
        bosses=bosses_held_by(
            windows,
            on_bosses,
            owner_id,
            log.ability_names,
            tally,
            find_shared(everywhere, owner_id),
        ),
        trash=trash,
        adds=adds,
        life_names=tuple(
            (ability_id, names.get(ability_id, f"Unknown ability {ability_id}"))
            for ability_id in sorted(on_lives_abilities)
        ),
        unmeasured_no_death=found.unmeasured_no_death,
        undebuffed_deaths=found.undebuffed_deaths,
    )


def boss_debuffs(
    log: DebuffLog, pulls: Sequence[Pull], owner_id: int, players: frozenset[int]
) -> BossDebuffs:
    """The boss half of `key_debuffs`: what this player kept on each measured boss.

    Kept as its own reading because every boss test, and the boss end-to-end
    test, read the boss figure through it: they pin the very path the
    comparison runs, so nothing that died beside a boss can move its figure
    unnoticed.
    """
    return key_debuffs(log, pulls, owner_id, players).bosses


def _cover(
    lives: Sequence[EnemyLife], held: Held, owner_id: int, stretch: LifeStretch
) -> StretchCover:
    """One stretch's lives, and this owner's merged time on them and lives reached."""
    mine = [life for life in lives if life.stretch is stretch]
    keys = {life.key for life in mine}
    covered: dict[int, int] = defaultdict(int)
    reached: dict[int, int] = defaultdict(int)
    for (owner, ability_id), by_life in held.items():
        if owner != owner_id:
            continue
        for key, spans in by_life.items():
            if key in keys:
                covered[ability_id] += length_ms(merged_spans(spans))
                reached[ability_id] += 1
    return StretchCover(
        lives=len(mine),
        alive_ms=sum(life.end_ms - life.start_ms for life in mine),
        covered=tuple(sorted(covered.items())),
        reached=tuple(sorted(reached.items())),
    )
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison -q`
Expected: all pass. Every test of `test_boss_debuffs.py` passes unchanged, which pins the boss figure, the windows, the tally and the shared rule through `key_debuffs`.

- [ ] **Step 7: Point the CLI at the moved function, then gate**

`src/wowperf/cli.py` imports `BossDebuffs, boss_debuffs` from `wowperf.domain.comparison.boss_debuffs`, and the function is no longer there. Make that line `from wowperf.domain.comparison.boss_debuffs import BossDebuffs`, and add `from wowperf.domain.comparison.key_debuffs import boss_debuffs` below it. Task 5 replaces that use.

Run the gate. Then run `grep -rn "_merged(\|_length_ms(" src/wowperf/domain/comparison tests/domain/comparison`. No hit may name the removed helpers. The search is scoped to `comparison/` because `report/player_timeline.py` has an unrelated `_merged` of its own. Then run `grep -rn "import boss_debuffs" src tests`: every import of the function `boss_debuffs` must come from `key_debuffs`.

- [ ] **Step 8: Commit**

Write `<scratchpad>\task4-msg.txt`:

```text
Measure debuff coverage and reach over every enemy of a key

The boss figure read boss pulls only, and a key is mostly trash. Each
trash and add life is now measured beside the bosses, and the shared
rule compares two players on a common life as it did on a common boss.
The boss figure is built by the same helpers and every boss test now
reads it through the new path, so it cannot move unnoticed.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/boss_debuffs.py src/wowperf/domain/comparison/key_debuffs.py src/wowperf/cli.py tests/domain/comparison/test_key_debuffs.py tests/domain/comparison/test_boss_debuffs.py tests/domain/comparison/test_debuff_uptime.py tests/e2e/test_boss_debuffs_e2e.py
```

```bash
/mingw64/bin/git commit -F /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/task4-msg.txt
```

---

### Task 5: Judge debuffs on Overall coverage, under `compare.uptime.debuff.*`

The verdict moves from the bosses to Overall, and the findings change name with it: spec §4 says `compare.uptime.boss.*` would describe the wrong figure. The table gains a Trash and a Bosses cell and a reach for each row, and it carries the two counts. The page's wording follows in Task 8. Until then the caption still says boss-alive time, which is false for one commit, as the council plan's Task 2 was before its Task 4.

**Every consumer of the old ids**, found with `grep -rn "compare.uptime.boss" src tests .claude docs/how-it-works.md README.md CLAUDE.md`:
- `src/wowperf/domain/comparison/debuff_uptime.py`, where `ID_PREFIX` mints them;
- `src/wowperf/domain/comparison/sample.py`, in a comment;
- `src/wowperf/cli.py`, in the docstring of `_debuff_log`;
- `tests/domain/comparison/test_debuff_uptime.py`, rewritten whole below;
- `tests/domain/comparison/test_sample_invariants.py`, in `MEDIAN_ID_PREFIXES` and two comments;
- `tests/test_cli.py`, at six assertions;
- `.claude/skills/mplus-analysis/SKILL.md`, which Task 9 rewrites.

`report/players.py` routes every `compare.uptime.` id to the card by prefix, so it needs no change.

**Files:**
- Modify:
  - `src/wowperf/domain/comparison/boss_debuffs.py` (`Withheld.NO_TRASH`)
  - `src/wowperf/domain/comparison/measures.py`
  - `src/wowperf/domain/comparison/uptime.py` (`measured_or`, `stretch_cell`)
  - `src/wowperf/domain/comparison/debuff_uptime.py` (rewritten)
  - `src/wowperf/domain/comparison/sample.py`
  - `src/wowperf/domain/comparison/service.py`
  - `src/wowperf/domain/comparison/tables.py`
  - `src/wowperf/domain/report/players.py`
  - `src/wowperf/cli.py`
- Modify tests:
  - `tests/domain/comparison/test_debuff_uptime.py` (rewritten)
  - `tests/domain/comparison/test_sample.py`
  - `tests/domain/comparison/test_sample_invariants.py`
  - `tests/domain/report/test_build_players.py`
  - `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 4's `KeyDebuffs`, `StretchCover` and `key_debuffs`.
- Produces:
  - `Withheld.NO_TRASH = "no trash measured"`.
  - In `measures`:
    - `StretchCell(ours: float | None = None, their_median: float | None = None, withheld: Withheld | None = None)`;
    - `DebuffReach(overall: StretchCell = StretchCell(), trash: StretchCell = StretchCell(), bosses: StretchCell = StretchCell(), overall_fractions: tuple[float, ...] = ())`, where `overall_fractions` holds the references' Overall reaches behind `overall`'s median, which the reach table's Range and Sample state (Task 8);
    - `DebuffRow(uptime: AuraUptime, trash: StretchCell = StretchCell(), bosses: StretchCell = StretchCell(), cells: tuple[BossCell, ...] = (), reach: DebuffReach = DebuffReach(), shared_with: tuple[int, ...] = ())`, which replaces `BossDebuffRow`;
    - `DebuffTable(rows, seconds, bosses, tally, deathless, unmeasured_no_death: int = 0, undebuffed_deaths: int = 0)`, which replaces `BossDebuffTable`;
    - `PlayerMeasures.debuffs: DebuffTable`, which replaces `boss_debuffs`.
  - In `uptime`:
    - `measured_or(value: float | None, reason: Withheld) -> float | Withheld`;
    - `carried_shares(theirs: Sequence[float | None]) -> tuple[float, ...]`, the references that carried a figure over one stretch, which both `stretch_cell` and `debuff_uptime._reach` read;
    - `stretch_cell(ours: float | Withheld, theirs: Sequence[float | None]) -> StretchCell`.
  - In `debuff_uptime`:
    - `ID_PREFIX = "compare.uptime.debuff"`;
    - `coverage_fractions(cover: StretchCover, names: Sequence[tuple[int, str]])`;
    - `debuff_fractions(debuffs: KeyDebuffs)`;
    - `per_member_fractions(members)`;
    - `compare_debuffs_sample(our: KeyDebuffs | None, our_name: str, sample: ParseSample) -> list[Finding]`;
    - `debuff_table(our: KeyDebuffs | None, sample: ParseSample) -> DebuffTable`.
  - `ParseMember.debuffs: KeyDebuffs | None`, which replaces `boss_debuffs`.
  - `ComparisonSubject.our_debuffs: KeyDebuffs | None`, which replaces `our_boss_debuffs`.
  - `cli._fetch_parse_debuffs(...) -> tuple[ParseSample, KeyDebuffs | None]`, which replaces `_fetch_parse_boss_debuffs`.

- [ ] **Step 1: Rewrite `tests/domain/comparison/test_debuff_uptime.py` whole**

```python
# ABOUTME: Debuff coverage against the parse sample: the buff family's thresholds, on Overall.
# ABOUTME: Pins the gap, level, unjudged, the pairwise fallback, the stretch cells and reach.

import pytest

from tests.domain.comparison.test_boss_debuffs import (
    BOSS_PULL,
    OTHER,
    PLAYER,
    RUN_PLAYERS,
    a_log,
    held,
)
from tests.domain.comparison.test_uptime import BOSS, a_player, a_run
from wowperf.domain.comparison.boss_debuffs import BossDebuffs, BossTarget, BossWindow, Withheld
from wowperf.domain.comparison.debuff_uptime import compare_debuffs_sample, debuff_table
from wowperf.domain.comparison.key_debuffs import KeyDebuffs, StretchCover, key_debuffs
from wowperf.domain.comparison.measures import BossCell, DebuffReach, StretchCell, Verdict
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.comparison.service import ComparisonSubject, compare
from wowperf.domain.comparison.tables import comparison_measures
from wowperf.domain.debuffs import PairingTally
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun

OUR_NAME = "Stonewake (actor 7)"
DOT, DOT_NAME = 55078, "Blood Plague"
REFERENCE_NAMES = ("Bríala", "Кириллица", "Emberkin")


def on_the_boss(*shares: tuple[int, str, float], seconds: float = 100.0) -> KeyDebuffs:
    """One measured boss pull of `seconds` and no other enemy, each debuff on it for its share."""
    end_ms = int(seconds * 1000)
    window = BossWindow(
        encounter_id=2001,
        name="The Test Colossus",
        start_ms=0,
        end_ms=end_ms,
        targets=(BossTarget(game_id=5000, start_ms=0, end_ms=end_ms),),
    )
    carried = [(ability_id, name, share) for ability_id, name, share in shares if share > 0]
    return KeyDebuffs(
        bosses=BossDebuffs(
            windows=(window,),
            covered=tuple(
                (2001, ability_id, int(end_ms * share)) for ability_id, _, share in carried
            ),
            names=tuple((ability_id, name) for ability_id, name, _ in carried),
            reached=tuple((ability_id, 1) for ability_id, _, _ in carried),
        )
    )


def with_trash(
    debuffs: KeyDebuffs,
    share: float,
    *,
    lives: int = 4,
    reached: int = 4,
    seconds: float = 100.0,
) -> KeyDebuffs:
    """The same key with trash beside its bosses: `lives` mobs alive `seconds` in all,
    the debuff on them for `share` of that time and on `reached` of them."""
    alive_ms = int(seconds * 1000)
    carried = share > 0
    return debuffs.model_copy(
        update={
            "trash": StretchCover(
                lives=lives,
                alive_ms=alive_ms,
                covered=((DOT, int(alive_ms * share)),) if carried else (),
                reached=((DOT, reached),) if carried else (),
            ),
            "life_names": ((DOT, DOT_NAME),) if carried else (),
        }
    )


def on_its_bosses(debuffs: KeyDebuffs, **fields: object) -> KeyDebuffs:
    """The same key with these fields of its boss figure replaced."""
    return debuffs.model_copy(update={"bosses": debuffs.bosses.model_copy(update=fields)})


def a_member(name: str, debuffs: KeyDebuffs | None) -> ParseMember:
    return ParseMember(
        character_name=name, report_code="ref", fight_id=1, boss_seconds=100.0, debuffs=debuffs
    )


def a_sample(*shares: float) -> ParseSample:
    return ParseSample(
        members=tuple(
            a_member(name, on_the_boss((DOT, DOT_NAME, share)))
            for name, share in zip(REFERENCE_NAMES, shares, strict=False)
        )
    )


def a_sample_of(*members: KeyDebuffs) -> ParseSample:
    return ParseSample(
        members=tuple(
            a_member(name, debuffs)
            for name, debuffs in zip(REFERENCE_NAMES, members, strict=True)
        )
    )


def by_id(findings: list[Finding]) -> dict[str, Finding]:
    return {finding.id: finding for finding in findings}


def test_a_debuff_kept_up_well_below_the_sample_is_a_gap() -> None:
    findings = by_id(
        compare_debuffs_sample(
            on_the_boss((DOT, DOT_NAME, 0.5)), OUR_NAME, a_sample(0.9, 0.9, 0.9)
        )
    )

    gap = findings["compare.uptime.debuff.0"]
    assert gap.confidence is Confidence.DERIVED
    assert gap.title == (
        "Blood Plague covered a median 90% of enemy-alive time across 3 top parses; "
        "50% for Stonewake (actor 7)"
    )
    assert "range 90% to 90% across 3 top parses" in gap.evidence
    assert "ours over 100s of measured enemy-alive time" in gap.evidence
    assert "a trash mob from the first debuff anyone put on it to its death" in gap.detail
    assert (
        "a council's bosses each from the pull's start to their own death, or to the pull's "
        "end if they did not die there."
    ) in gap.detail
    assert "0 of 3 references had no debuff data" in gap.evidence
    assert (gap.ability_id, gap.ability_name) == (DOT, DOT_NAME)


def test_a_narrow_difference_is_level_and_reports_nothing() -> None:
    findings = compare_debuffs_sample(
        on_the_boss((DOT, DOT_NAME, 0.85)), OUR_NAME, a_sample(0.9, 0.9, 0.9)
    )

    assert findings == []


def test_a_debuff_the_sample_kept_and_we_never_applied_is_named_not_judged() -> None:
    findings = by_id(compare_debuffs_sample(on_the_boss(), OUR_NAME, a_sample(0.9, 0.9, 0.9)))

    assert set(findings) == {"compare.uptime.debuff.unjudged"}
    unjudged = findings["compare.uptime.debuff.unjudged"]
    assert unjudged.title == (
        "1 debuff the sample kept on enemies is absent for Stonewake (actor 7)"
    )
    assert unjudged.evidence[0] == DOT_NAME


def test_below_the_floor_one_reference_is_stated_pairwise() -> None:
    findings = by_id(
        compare_debuffs_sample(on_the_boss((DOT, DOT_NAME, 0.5)), OUR_NAME, a_sample(0.9, 0.9))
    )

    gap = findings["compare.uptime.debuff.0"]
    assert gap.title == (
        "Blood Plague covered 90% of Bríala's enemy-alive time, 50% of Stonewake (actor 7)'s"
    )
    assert gap.evidence[-1].startswith("a single reference, not an aggregate")


def test_below_the_floor_a_narrow_difference_is_not_a_gap() -> None:
    findings = compare_debuffs_sample(
        on_the_boss((DOT, DOT_NAME, 0.85)), OUR_NAME, a_sample(0.9, 0.9)
    )

    assert findings == []


def test_below_the_floor_a_debuff_we_never_applied_is_passed_over() -> None:
    findings = compare_debuffs_sample(on_the_boss(), OUR_NAME, a_sample(0.9, 0.9))

    assert findings == []


def test_an_empty_sample_says_nothing_here() -> None:
    assert compare_debuffs_sample(on_the_boss(), OUR_NAME, ParseSample()) == []


def test_no_reference_with_debuff_data_is_unavailable() -> None:
    sample = ParseSample(members=(a_member("Bríala", None), a_member("Кириллица", None)))

    [finding] = compare_debuffs_sample(on_the_boss(), OUR_NAME, sample)

    assert finding.id == "compare.uptime.debuff.unavailable"
    assert finding.title == "Debuff coverage could not be compared for Stonewake (actor 7)"
    assert finding.confidence is Confidence.MEASURED
    assert "0 of 2 references returned debuff data" in finding.evidence


def test_our_own_missing_stream_is_unavailable() -> None:
    [finding] = compare_debuffs_sample(None, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert finding.id == "compare.uptime.debuff.unavailable"
    assert "our debuff data absent" in finding.evidence


def test_a_key_with_no_enemy_measured_is_unavailable() -> None:
    unfound = KeyDebuffs(
        bosses=BossDebuffs(
            windows=(
                BossWindow(
                    encounter_id=2001,
                    name="The Fixture Hall",
                    start_ms=0,
                    end_ms=60_000,
                    withheld=Withheld.NO_BOSS,
                ),
            )
        )
    )

    [finding] = compare_debuffs_sample(unfound, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert finding.id == "compare.uptime.debuff.unavailable"
    assert "our measured enemy-alive time 0s" in finding.evidence


def test_at_most_five_gaps_are_reported() -> None:
    six = tuple((DOT + offset, f"Debuff {offset}", 0.9) for offset in range(6))
    ours = tuple((ability_id, name, 0.3) for ability_id, name, _ in six)
    sample = ParseSample(
        members=tuple(a_member(name, on_the_boss(*six)) for name in REFERENCE_NAMES)
    )

    findings = compare_debuffs_sample(on_the_boss(*ours), OUR_NAME, sample)

    assert sorted(finding.id for finding in findings) == [
        f"compare.uptime.debuff.{rank}" for rank in range(5)
    ]


def test_the_service_files_the_gap_under_the_players_own_slug() -> None:
    subject = ComparisonSubject(
        player=a_player(),
        slug="stonewake-0",
        display_name=OUR_NAME,
        parse=a_sample(0.9, 0.9, 0.9),
        our_debuffs=on_the_boss((DOT, DOT_NAME, 0.5)),
    )

    ids = [finding.id for finding in compare(LoadedRun(run=a_run(BOSS)), None, [subject])]

    assert "compare.uptime.debuff.0.stonewake-0" in ids


def test_the_verdict_reads_trash_and_bosses_summed() -> None:
    # Ours: 90% of the boss and 10% of the trash, so 50% of the key. The sample:
    # 90% of both. On the bosses alone ours would read level.
    ours = with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.1)
    sample = a_sample_of(
        *(with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9) for _ in range(3))
    )

    findings = by_id(compare_debuffs_sample(ours, OUR_NAME, sample))

    gap = findings["compare.uptime.debuff.0"]
    assert gap.title == (
        "Blood Plague covered a median 90% of enemy-alive time across 3 top parses; "
        "50% for Stonewake (actor 7)"
    )
    assert "ours over 200s of measured enemy-alive time" in gap.evidence


def test_a_row_describes_its_trash_and_bosses_beside_the_verdict() -> None:
    ours = with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.1)
    sample = a_sample_of(
        *(with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9) for _ in range(3))
    )

    [row] = debuff_table(ours, sample).rows

    assert row.uptime.verdict is Verdict.BELOW
    assert row.uptime.ours == pytest.approx(0.5)
    assert row.trash == StretchCell(ours=0.1, their_median=0.9)
    assert row.bosses == StretchCell(ours=0.9, their_median=0.9)


def test_a_key_with_no_trash_measured_says_so_in_its_trash_cells() -> None:
    sample = a_sample_of(
        *(with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9) for _ in range(3))
    )

    [row] = debuff_table(on_the_boss((DOT, DOT_NAME, 0.5)), sample).rows

    assert row.trash == StretchCell(withheld=Withheld.NO_TRASH)
    assert row.reach.trash == StretchCell(withheld=Withheld.NO_TRASH)


def test_a_trash_cell_no_reference_measured_shows_ours_and_says_so() -> None:
    ours = with_trash(on_the_boss((DOT, DOT_NAME, 0.5)), 0.1)
    sample = a_sample(0.9, 0.9, 0.9)

    [row] = debuff_table(ours, sample).rows

    assert row.trash == StretchCell(ours=0.1, withheld=Withheld.NOT_REACHED)


def test_reach_is_described_for_every_stretch() -> None:
    # Ours sat on the boss and on 1 of 4 mobs: 2 of 5 enemies. Each reference
    # sat on the boss and on all 4, so each of the three gives an Overall reach
    # of 1.0, and those three are what the reach table's Range and Sample state.
    ours = with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.1, reached=1)
    sample = a_sample_of(
        *(with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9) for _ in range(3))
    )

    [row] = debuff_table(ours, sample).rows

    assert row.reach == DebuffReach(
        overall=StretchCell(ours=0.4, their_median=1.0),
        trash=StretchCell(ours=0.25, their_median=1.0),
        bosses=StretchCell(ours=1.0, their_median=1.0),
        overall_fractions=(1.0, 1.0, 1.0),
    )


def test_reach_keeps_the_references_overall_reach_not_their_coverage() -> None:
    # Each reference covered 90% of the boss and of its trash, and reached the
    # boss and 2 of its 4 mobs: 3 of 5 enemies. Their coverage, 0.9, is not
    # their reach, 0.6, and only the reach belongs under the reach table's Range.
    ours = with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.1, reached=1)
    sample = a_sample_of(
        *(with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9, reached=2) for _ in range(3))
    )

    [row] = debuff_table(ours, sample).rows

    assert row.reach.overall_fractions == (0.6, 0.6, 0.6)
    assert row.uptime.their_fractions == (0.9, 0.9, 0.9)


def test_a_debuff_seen_only_on_trash_still_earns_a_row() -> None:
    # No one put it on the boss. The sample kept it on 90% of their trash, which
    # is 45% of the key; ours 10%, which is 5%.
    ours = with_trash(on_the_boss(), 0.1)
    sample = a_sample_of(*(with_trash(on_the_boss(), 0.9) for _ in range(3)))

    [row] = debuff_table(ours, sample).rows

    assert (row.uptime.name, row.uptime.verdict) == (DOT_NAME, Verdict.BELOW)
    assert row.uptime.ours == pytest.approx(0.05)
    assert row.uptime.their_median == pytest.approx(0.45)
    assert row.bosses == StretchCell(ours=0.0, withheld=Withheld.TOO_FEW)


def test_the_table_carries_what_could_not_be_measured() -> None:
    ours = on_the_boss((DOT, DOT_NAME, 0.5)).model_copy(
        update={"unmeasured_no_death": 3, "undebuffed_deaths": 2}
    )

    full = debuff_table(ours, a_sample(0.9, 0.9, 0.9))
    thin = debuff_table(ours, a_sample(0.9, 0.9))

    assert (full.unmeasured_no_death, full.undebuffed_deaths) == (3, 2)
    assert full.rows
    assert (thin.unmeasured_no_death, thin.undebuffed_deaths) == (3, 2)
    assert thin.rows == ()


FIRST = BossWindow(
    encounter_id=2001,
    name="First Boss",
    start_ms=0,
    end_ms=100_000,
    targets=(BossTarget(game_id=5000, start_ms=0, end_ms=100_000),),
)
SECOND = BossWindow(
    encounter_id=2002,
    name="Second Boss",
    start_ms=200_000,
    end_ms=300_000,
    targets=(BossTarget(game_id=6000, start_ms=200_000, end_ms=300_000),),
)
SECOND_UNFOUND = SECOND.model_copy(update={"targets": (), "withheld": Withheld.NO_BOSS})


def on_two_bosses(
    first: float,
    second: float,
    *,
    windows: tuple[BossWindow, ...] = (FIRST, SECOND),
    second_encounter: int = 2002,
) -> KeyDebuffs:
    covered = []
    if first > 0:
        covered.append((2001, DOT, int(100_000 * first)))
    if second > 0:
        covered.append((second_encounter, DOT, int(100_000 * second)))
    return KeyDebuffs(
        bosses=BossDebuffs(
            windows=windows,
            covered=tuple(covered),
            names=((DOT, DOT_NAME),) if covered else (),
            reached=((DOT, len(covered)),) if covered else (),
        )
    )


def test_a_row_carries_the_overall_verdict_and_one_cell_per_boss() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = debuff_table(on_two_bosses(0.5, 0.9), sample)

    [row] = table.rows
    assert row.uptime.verdict is Verdict.BELOW
    assert row.cells == (
        BossCell(encounter_id=2001, boss="First Boss", ours=0.5, their_median=0.9),
        BossCell(encounter_id=2002, boss="Second Boss", ours=0.9, their_median=0.9),
    )
    assert (table.bosses, table.seconds) == (("First Boss", "Second Boss"), 200.0)


def test_a_boss_fought_twice_is_one_column_and_one_cell_summed_over_both_pulls() -> None:
    # A wipe, then the kill: two windows sharing one encounter id. 50s of the
    # first pull's 100s and 90s of the second's make 140s of 200s.
    kill = FIRST.model_copy(
        update={
            "start_ms": 200_000,
            "end_ms": 300_000,
            "targets": (BossTarget(game_id=5000, start_ms=200_000, end_ms=300_000),),
        }
    )
    sample = a_sample_of(
        *(
            on_two_bosses(0.9, 0.9, windows=(FIRST, kill), second_encounter=2001)
            for _ in range(3)
        )
    )

    table = debuff_table(
        on_two_bosses(0.5, 0.9, windows=(FIRST, kill), second_encounter=2001), sample
    )

    assert table.bosses == ("First Boss",)
    assert table.seconds == 200.0
    [row] = table.rows
    [cell] = row.cells
    assert cell.encounter_id == 2001
    assert cell.ours == pytest.approx(0.7)
    assert cell.their_median == pytest.approx(0.9)


def test_our_unfound_boss_cell_is_withheld_with_its_reason() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = debuff_table(on_two_bosses(0.5, 0.0, windows=(FIRST, SECOND_UNFOUND)), sample)

    assert table.rows[0].cells[1] == BossCell(
        encounter_id=2002, boss="Second Boss", withheld=Withheld.NO_BOSS
    )


def test_a_boss_no_reference_reached_shows_ours_and_says_so() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.0, windows=(FIRST,)) for _ in range(3)))

    table = debuff_table(on_two_bosses(0.5, 0.9), sample)

    assert table.rows[0].cells[1] == BossCell(
        encounter_id=2002, boss="Second Boss", ours=0.9, withheld=Withheld.NOT_REACHED
    )


def test_a_boss_too_few_references_applied_it_on_shows_ours_and_says_so() -> None:
    sample = a_sample_of(
        on_two_bosses(0.9, 0.9), on_two_bosses(0.9, 0.9), on_two_bosses(0.9, 0.0)
    )

    table = debuff_table(on_two_bosses(0.5, 0.9), sample)

    assert table.rows[0].cells[1] == BossCell(
        encounter_id=2002, boss="Second Boss", ours=0.9, withheld=Withheld.TOO_FEW
    )


def test_no_table_below_the_floor_or_without_our_own_figure() -> None:
    two = ParseSample(
        members=(
            a_member("Bríala", on_two_bosses(0.9, 0.9)),
            a_member("Кириллица", on_two_bosses(0.9, 0.9)),
        )
    )
    three = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    assert debuff_table(on_two_bosses(0.5, 0.9), two).rows == ()
    assert debuff_table(None, three).rows == ()


def test_the_table_carries_our_count_of_deathless_council_bosses() -> None:
    window = FIRST.model_copy(update={"deathless": 1})
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = debuff_table(on_two_bosses(0.5, 0.9, windows=(window, SECOND)), sample)

    assert table.deathless == 1


def test_below_the_floor_the_empty_table_still_carries_our_deathless_count() -> None:
    window = FIRST.model_copy(update={"deathless": 2})
    two = ParseSample(
        members=(
            a_member("Bríala", on_two_bosses(0.9, 0.9)),
            a_member("Кириллица", on_two_bosses(0.9, 0.9)),
        )
    )

    table = debuff_table(on_two_bosses(0.5, 0.9, windows=(window, SECOND)), two)

    assert table.rows == ()
    assert table.deathless == 2


def a_tallied_run() -> KeyDebuffs:
    return on_its_bosses(
        on_two_bosses(0.5, 0.9), tally=PairingTally(orphan_removes=2, closed_at_end=1)
    )


def test_our_own_pairing_tally_rides_on_the_table() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    assert debuff_table(a_tallied_run(), sample).tally == PairingTally(
        orphan_removes=2, closed_at_end=1
    )


def test_below_the_floor_the_empty_table_still_carries_our_own_tally_and_seconds() -> None:
    two = ParseSample(
        members=(
            a_member("Bríala", on_two_bosses(0.9, 0.9)),
            a_member("Кириллица", on_two_bosses(0.9, 0.9)),
        )
    )

    table = debuff_table(a_tallied_run(), two)

    assert table.rows == ()
    assert table.seconds == 200.0
    assert table.tally == PairingTally(orphan_removes=2, closed_at_end=1)


def test_with_no_measured_enemy_the_empty_table_still_carries_our_own_tally() -> None:
    unfound = KeyDebuffs(
        bosses=BossDebuffs(
            windows=(
                BossWindow(
                    encounter_id=2001,
                    name="The Fixture Hall",
                    start_ms=0,
                    end_ms=60_000,
                    withheld=Withheld.NO_BOSS,
                ),
            ),
            tally=PairingTally(orphan_removes=3),
        )
    )
    three = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = debuff_table(unfound, three)

    assert table.rows == ()
    assert table.seconds == 0.0
    assert table.tally == PairingTally(orphan_removes=3)


def test_a_clean_log_records_a_zero_tally_not_an_absent_one() -> None:
    two = ParseSample(members=(a_member("Bríala", on_two_bosses(0.9, 0.9)),))

    table = debuff_table(on_two_bosses(0.5, 0.9), two)

    assert table.tally == PairingTally()
    assert table.tally is not None


def test_when_our_stream_could_not_be_read_the_table_records_no_tally() -> None:
    three = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = debuff_table(None, three)

    assert table.tally is None
    assert table.seconds == 0.0


TEAMMATE, SECOND_TEAMMATE = 702, 703


def marked_shared(debuffs: KeyDebuffs, ability_id: int, *owners: int) -> KeyDebuffs:
    return on_its_bosses(debuffs, shared_with=((ability_id, owners),))


def test_a_shared_debuff_far_below_the_sample_is_not_a_gap() -> None:
    ours = marked_shared(on_the_boss((DOT, DOT_NAME, 0.3)), DOT, TEAMMATE)

    assert compare_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9)) == []


def test_below_the_floor_a_shared_debuff_is_not_a_gap_either() -> None:
    ours = marked_shared(on_the_boss((DOT, DOT_NAME, 0.3)), DOT, TEAMMATE)

    assert compare_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9)) == []


def test_a_shared_debuff_we_never_applied_is_not_named_unjudged() -> None:
    ours = marked_shared(on_the_boss(), DOT, TEAMMATE, SECOND_TEAMMATE)

    assert compare_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9)) == []


OTHER_DOT, OTHER_DOT_NAME = 55095, "Frost Fever"


def test_only_the_shared_debuff_is_set_aside() -> None:
    both = ((DOT, DOT_NAME, 0.9), (OTHER_DOT, OTHER_DOT_NAME, 0.9))
    sample = ParseSample(
        members=tuple(a_member(name, on_the_boss(*both)) for name in REFERENCE_NAMES)
    )
    ours = marked_shared(
        on_the_boss((DOT, DOT_NAME, 0.3), (OTHER_DOT, OTHER_DOT_NAME, 0.3)), DOT, TEAMMATE
    )

    findings = compare_debuffs_sample(ours, OUR_NAME, sample)

    assert [(finding.id, finding.ability_id) for finding in findings] == [
        ("compare.uptime.debuff.0", OTHER_DOT)
    ]


def test_a_teammate_taking_the_debuff_over_from_us_leaves_no_gap() -> None:
    # Read off a log: ours 10s of the 60s pull, the teammate's the other 50s,
    # never at once. The sample's 90% against our 17% would be a gap.
    ours = key_debuffs(
        a_log(*held(PLAYER, 10_000, 20_000), *held(OTHER, 20_000, 70_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert compare_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9)) == []


def test_a_teammates_copy_beside_ours_leaves_the_gap_standing() -> None:
    # The same figures, but the teammate's copy sat on the boss beside ours, so
    # theirs took nothing away from ours: the gap is ours.
    ours = key_debuffs(
        a_log(*held(PLAYER, 10_000, 20_000), *held(OTHER, 10_000, 70_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    findings = compare_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert [finding.id for finding in findings] == ["compare.uptime.debuff.0"]


def test_a_shared_row_keeps_its_figures_and_names_who_it_was_shared_with() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))
    ours = marked_shared(on_two_bosses(0.5, 0.9), DOT, TEAMMATE, SECOND_TEAMMATE)

    [row] = debuff_table(ours, sample).rows

    assert row.shared_with == (TEAMMATE, SECOND_TEAMMATE)
    assert row.uptime.ours == pytest.approx(0.7)
    assert row.uptime.verdict is Verdict.BELOW


def test_a_row_whose_debuff_is_not_the_shared_one_names_nobody() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))
    ours = marked_shared(on_two_bosses(0.5, 0.9), OTHER_DOT, TEAMMATE)

    [row] = debuff_table(ours, sample).rows

    assert row.shared_with == ()


def test_the_players_measures_carry_the_debuff_table() -> None:
    subject = ComparisonSubject(
        player=a_player(),
        slug="stonewake-0",
        display_name=OUR_NAME,
        parse=a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3))),
        our_debuffs=on_two_bosses(0.5, 0.9),
    )

    measures = comparison_measures(LoadedRun(run=a_run(BOSS)), [subject])

    assert [row.uptime.name for row in measures["stonewake-0"].debuffs.rows] == [DOT_NAME]
```

Rewrite these other tests, which break on the renames:

- **`tests/domain/comparison/test_sample.py`**, in `test_a_parse_member_carries_no_run`:
  - replace `"boss_debuffs",` with `"debuffs",` in the expected set;
  - in its docstring, replace "`boss_debuffs` is here because the boss debuff comparison reads a reference's own debuffs on its own bosses" with "`debuffs` is here because the debuff comparison reads a reference's own debuffs on every enemy of its own key".
- **`tests/domain/comparison/test_sample_invariants.py`:**
  - Add `from wowperf.domain.comparison.key_debuffs import KeyDebuffs` beside the `boss_debuffs` import.
  - In `MEDIAN_ID_PREFIXES`, replace `"compare.uptime.boss.",` with `"compare.uptime.debuff.",`. In the comment above it, replace both `uptime.boss` with `uptime.debuff`.
  - Make `_boss_debuffs` return `KeyDebuffs`, its return annotation included. Its docstring becomes `"""One measured boss pull and no other enemy, the debuff up for `share` of it."""`, and its body returns `KeyDebuffs(bosses=BossDebuffs(...))`. The `BossDebuffs(...)` keeps its three arguments and gains `reached=((UPTIME_BOSS_ABILITY_ID, 1),),`.
  - In `_parse_member`, replace `boss_debuffs=_boss_debuffs(0, 120.0, 0.80),` with `debuffs=_boss_debuffs(0, 120.0, 0.80),`.
  - In `SUBJECT_WITH_AURAS`, replace `our_boss_debuffs=OUR_BOSS_DEBUFFS,` with `our_debuffs=OUR_BOSS_DEBUFFS,`.
  - In the comment above `PARSE_SAMPLE`, replace `(compare.uptime.boss: the same)` with `(compare.uptime.debuff: the same)`.
- **`tests/test_cli.py`:** replace `compare.uptime.boss.` with `compare.uptime.debuff.` in all six places:
  - `test_a_compared_run_reads_both_sides_debuffs_on_the_boss` (`"compare.uptime.debuff.0.emberkin-0" in ids`);
  - `test_a_teammate_taking_our_debuff_over_leaves_no_gap` (`one.startswith("compare.uptime.debuff.")`);
  - `test_our_own_failed_debuff_stream_still_writes_the_report_and_says_so` (`.unavailable.emberkin-0` and `.0.emberkin-0`);
  - `test_a_reference_whose_debuff_stream_failed_is_counted_as_having_none` (the same two).

  The fixture's EnemyDeaths stream is empty, so Overall is the boss there and every figure those tests rely on is unchanged.

  Then append to `test_a_compared_run_reads_both_sides_debuffs_on_the_boss`, which pins the two counts in the written findings file (spec §7). The boss is a measured boss and never cut into lives, and nothing else was debuffed or died, so both counts are zero. One reference sits below the floor, so the table has no rows, and the counts still ride along because our stream was read.

```python
    debuffs = written_findings(tmp_path)["comparison_tables"]["emberkin-0"]["debuffs"]
    assert (debuffs["unmeasured_no_death"], debuffs["undebuffed_deaths"]) == (0, 0)
```
- **`tests/domain/report/test_build_players.py`:**
  - In the `measures` import, replace `BossDebuffRow,` and `BossDebuffTable,` with `DebuffRow,` and `DebuffTable,`.
  - Replace every `BossDebuffTable(` with `DebuffTable(`, every `BossDebuffRow(` with `DebuffRow(`, and every `boss_debuffs=` keyword of `PlayerMeasures` with `debuffs=`. They occur in these tests and helpers:
    - `test_a_debuff_table_with_no_rows_and_no_stream_is_not_drawn`;
    - `test_the_debuff_table_follows_the_buff_table_with_a_column_per_boss`;
    - `a_shared_debuff_table`;
    - `test_a_boss_no_reference_measured_is_labelled_for_what_the_cell_can_know`.

- [ ] **Step 2: Run the tests to see them fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain tests/test_cli.py -q`
Expected: collection errors on `compare_debuffs_sample`, `debuff_table`, `DebuffReach`, `StretchCell`, `DebuffRow` and `DebuffTable`, which do not exist yet.

- [ ] **Step 3: `Withheld.NO_TRASH`**

In `src/wowperf/domain/comparison/boss_debuffs.py`, replace `Withheld` with:

```python
class Withheld(StrEnum):
    """Why a boss, one boss's cell, or one stretch's cell carries no figure.

    The first two are read off our own route: a boss pull may hold no enemy
    `bosses_of` can name, and a key may hold no trash life to measure. The last
    two are about the sample beside a figure of ours.
    """

    NO_BOSS = "no boss found"
    NO_TRASH = "no trash measured"
    NOT_REACHED = "no reference measured this boss"
    TOO_FEW = "too few references"
```

- [ ] **Step 4: The table's models**

In `src/wowperf/domain/comparison/measures.py`:

1. Add, after `BossCell`:

```python
class StretchCell(Frozen):
    """One stretch's figure in a row: ours against the sample's median, never a verdict.

    `ours` is None only when our own side measured nothing over that stretch,
    and `their_median` is None whenever `withheld` names a reason, so a cell
    always says why it is missing a figure.
    """

    ours: float | None = None
    their_median: float | None = None
    withheld: Withheld | None = None


class DebuffReach(Frozen):
    """One debuff's reach over each stretch: the share of enemies it sat on at all.

    Described, never judged: a reach threshold would be invented, not measured.
    `overall_fractions` are the references' Overall reaches above zero, which
    give `overall`'s median; the reach table states their range and count.
    """

    overall: StretchCell = StretchCell()
    trash: StretchCell = StretchCell()
    bosses: StretchCell = StretchCell()
    overall_fractions: tuple[float, ...] = ()
```

2. Replace `BossDebuffRow` and `BossDebuffTable` with:

```python
class DebuffRow(Frozen):
    """One debuff: the judged figure over every enemy of the key, then what describes it.

    `uptime` is Overall coverage and carries the verdict. `trash` and `bosses`
    describe the two stretches, `cells` each boss, and `reach` the share of
    enemies the debuff sat on at all; none of them carries a verdict.

    `shared_with` names, by actor id, the other players whose copies of this
    debuff replaced this player's rather than sat beside it. When it names
    anyone the row is not judged, whatever `uptime.verdict` says: the figure is
    this player's share of one slot, not their coverage.
    """

    uptime: AuraUptime
    trash: StretchCell = StretchCell()
    bosses: StretchCell = StretchCell()
    cells: tuple[BossCell, ...] = ()
    reach: DebuffReach = DebuffReach()
    shared_with: tuple[int, ...] = ()


class DebuffTable(Frozen):
    """Everything the debuff tables state, with the denominator and the log's own counts.

    `tally` is None only when no stream was read for our side, whether it was
    never requested or could not be read, so that a findings file tells "no
    stream read" apart from "read, and clean". Whenever the stream was read it
    is our own tally, even with no rows to show.
    """

    rows: tuple[DebuffRow, ...] = ()
    seconds: float = 0.0
    """Our summed enemy-alive seconds over every measured enemy: Overall's denominator."""
    bosses: tuple[str, ...] = ()
    tally: PairingTally | None = None
    deathless: int = 0
    """Our council bosses of a kill pull with no death in the log, measured to the pull's end."""
    unmeasured_no_death: int = 0
    """Our enemies debuffed with no death after it in the log: left out of coverage and reach."""
    undebuffed_deaths: int = 0
    """Our enemies that died with no debuff from anyone since their previous death."""
```

3. In `PlayerMeasures`, replace `boss_debuffs: BossDebuffTable = BossDebuffTable()` with `debuffs: DebuffTable = DebuffTable()`.

- [ ] **Step 5: The cell rule, shared with buffs**

In `src/wowperf/domain/comparison/uptime.py`, import `Withheld` (`from wowperf.domain.comparison.boss_debuffs import Withheld`), and add `StretchCell` to the `measures` import. Then add after `uptime_measures`:

```python
def measured_or(value: float | None, reason: Withheld) -> float | Withheld:
    """Our own figure over a stretch, or why our side measured nothing over it."""
    return reason if value is None else value


def carried_shares(theirs: Sequence[float | None]) -> tuple[float, ...]:
    """The references' shares over one stretch that carried it there: measured, above zero.

    These give a stretch cell's median, and the reach table states their range
    and count beside Overall reach.
    """
    return tuple(share for share in theirs if share is not None and share > 0.0)


def stretch_cell(ours: float | Withheld, theirs: Sequence[float | None]) -> StretchCell:
    """One stretch's cell: ours against the median of the references that carried it there.

    Descriptive only: the verdict is the row's. `ours` is a reason when our own
    side measured nothing over the stretch. A reference that measured nothing
    there (None) is not counted for it, and a reference at zero there did not
    carry it; the rest give the median, at the floor the row's own median keeps.
    """
    if isinstance(ours, Withheld):
        return StretchCell(withheld=ours)
    if all(share is None for share in theirs):
        return StretchCell(ours=ours, withheld=Withheld.NOT_REACHED)
    carried = carried_shares(theirs)
    if len(carried) < MIN_SAMPLE_FOR_AGGREGATE:
        return StretchCell(ours=ours, withheld=Withheld.TOO_FEW)
    return StretchCell(ours=ours, their_median=median(carried))
```

- [ ] **Step 6: Rewrite `debuff_uptime.py`**

Replace the whole of `src/wowperf/domain/comparison/debuff_uptime.py` with:

```python
# ABOUTME: Compares one player's debuff coverage over every enemy against their spec's parses.
# ABOUTME: Judged on Overall coverage by the buff family's thresholds; stretches and reach describe.

from collections.abc import Collection, Sequence

from wowperf.domain.comparison.boss_debuffs import BossDebuffs, Withheld, encounter_share
from wowperf.domain.comparison.key_debuffs import KeyDebuffs, StretchCover
from wowperf.domain.comparison.measures import (
    BossCell,
    DebuffReach,
    DebuffRow,
    DebuffTable,
    Verdict,
)
from wowperf.domain.comparison.sample import (
    MIN_SAMPLE_FOR_AGGREGATE,
    ParseMember,
    ParseSample,
    too_few,
)
from wowperf.domain.comparison.statistics import count_phrase, observed_range
from wowperf.domain.comparison.uptime import (
    MAX_AURAS_REPORTED,
    carried_fractions,
    carried_shares,
    measured_or,
    pairwise_gaps,
    stretch_cell,
    uptime_measures,
)
from wowperf.domain.comparison.wording import DUNGEON
from wowperf.domain.findings import Confidence, Finding, FindingFact, quantity

ID_PREFIX = "compare.uptime.debuff"

STRETCH = "enemy-alive time"

GAP_DETAIL = (
    "Both figures are the share of enemy-alive time, summed over every enemy of the key, that "
    "carried this debuff from the player or their pets: a trash mob from the first debuff anyone "
    "put on it to its death, an add of a boss fight the same way, a single boss over its whole "
    "pull, and a council's bosses each from the pull's start to their own death, or to the "
    "pull's end if they did not die there. That is comparable even though the keys ran for "
    "different lengths. A boss pull with no boss found counts every enemy in it as an add, on "
    f"both sides. {DUNGEON.uptime_hedge} The intervals are rebuilt from the log's own "
    "applications and removals rather than read from a table."
)


def coverage_fractions(
    cover: StretchCover, names: Sequence[tuple[int, str]]
) -> dict[int, tuple[str, float]]:
    """Ability id to (name, share of this stretch's alive time it covered)."""
    if cover.alive_ms <= 0:
        return {}
    covered = dict(cover.covered)
    return {
        ability_id: (name, covered.get(ability_id, 0) / cover.alive_ms)
        for ability_id, name in names
    }


def debuff_fractions(debuffs: KeyDebuffs) -> dict[int, tuple[str, float]]:
    """Ability id to (name, share of the key's summed enemy-alive time it covered): Overall."""
    return coverage_fractions(debuffs.overall, debuffs.names)


def per_member_fractions(
    members: Sequence[ParseMember],
) -> tuple[dict[int, str], list[dict[int, float]]]:
    """Each member's Overall shares above zero, and every name seen, for `uptime_measures`.

    A share of zero reads the same as never having applied the debuff at all,
    the reading the buff family gives a band that never meets its stretch.
    """
    names: dict[int, str] = {}
    per_member: list[dict[int, float]] = []
    for member in members:
        assert member.debuffs is not None  # debuff_eligible guarantees it
        per_member.append(carried_fractions(debuff_fractions(member.debuffs), names))
    return names, per_member


def _unavailable(our_name: str, detail: str, evidence: tuple[str, ...]) -> Finding:
    return Finding(
        id=f"{ID_PREFIX}.unavailable",
        title=f"Debuff coverage could not be compared for {our_name}",
        detail=(
            "A debuff comparison needs the enemy-debuff stream, and at least one enemy "
            f"measured, on our side and on a reference's. {detail} No figures are reported "
            "rather than figures from one side."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=evidence,
    )


def compare_debuffs_sample(
    our: KeyDebuffs | None, our_name: str, sample: ParseSample
) -> list[Finding]:
    """Where the sample's debuffs covered markedly more of their enemies' time than ours did.

    The order of the checks follows `uptime.compare_uptime_sample`. An empty
    sample says nothing here: `compare.parse.unavailable` already says it once.
    """
    if not sample.members:
        return []

    eligible = sample.debuff_eligible
    if not eligible:
        return [
            _unavailable(
                our_name,
                "No reference in the sample returned any debuff data.",
                (f"{count_phrase(0, len(sample.members))} references returned debuff data",),
            )
        ]

    if our is None or our.overall.alive_ms <= 0:
        return [
            _unavailable(
                our_name,
                "Our own side has no figure: its stream could not be read, or no enemy of the "
                "key could be measured.",
                (
                    f"our debuff data {'absent' if our is None else 'present'}",
                    "our measured enemy-alive time "
                    f"{0.0 if our is None else our.overall.seconds:.0f}s",
                ),
            )
        ]

    our_seconds = our.overall.seconds
    our_fractions = debuff_fractions(our)
    # A shared debuff is one slot a teammate's application took over, so our
    # share of it is no coverage of ours: it is neither a gap nor an unjudged zero.
    shared = dict(our.shared_with)
    if not sample.can_aggregate(eligible):
        return too_few(
            _pairwise(our_fractions, our_seconds, our_name, eligible[0], shared),
            len(eligible),
        )

    names, per_member = per_member_fractions(eligible)
    measures = [
        m
        for m in uptime_measures(our_fractions, per_member, names)
        if m.ability_id not in shared
    ]
    total = len(sample.members)
    missing = total - len(eligible)
    gaps = sorted(
        (m for m in measures if m.verdict is Verdict.BELOW),
        key=lambda m: m.their_median - m.ours,
        reverse=True,
    )

    findings: list[Finding] = []
    for rank, m in enumerate(gaps[:MAX_AURAS_REPORTED]):
        low, high = observed_range(m.their_fractions)
        findings.append(
            Finding(
                id=f"{ID_PREFIX}.{rank}",
                title=(
                    f"{m.name} covered a median {m.their_median:.0%} of {STRETCH} "
                    f"across {len(m.their_fractions)} top parses; {m.ours:.0%} for {our_name}"
                ),
                detail=GAP_DETAIL,
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {m.ability_id}",
                    f"ours over {our_seconds:.0f}s of measured {STRETCH}",
                    f"range {low:.0%} to {high:.0%} across {len(m.their_fractions)} top parses",
                    f"{count_phrase(missing, total)} references had no debuff data",
                ),
                facts=(
                    FindingFact(label="Ours", value=f"{m.ours:.0%} of {STRETCH}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Reference median",
                                value=f"{m.their_median:.0%} of {STRETCH}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Observed range", value=f"{low:.0%} to {high:.0%}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Sample", value=f"{len(m.their_fractions)} top parses"),
                ),
                ability_id=m.ability_id,
                ability_name=m.name,
            )
        )

    unjudged = sorted({m.name for m in measures if m.verdict is Verdict.UNJUDGED})
    if unjudged:
        findings.append(_unjudged(our_name, unjudged))
    return findings


def _pairwise(
    our_fractions: dict[int, tuple[str, float]],
    our_seconds: float,
    our_name: str,
    theirs: ParseMember,
    shared: Collection[int],
) -> list[Finding]:
    """One reference, named, by the buff family's pairwise rule.

    A zero on our side is passed over here as it is on the buff side: below the
    floor there is no sample to say the debuff is one this build applies. A
    debuff in `shared` is passed over too, as it is in the sample's rule.
    """
    assert theirs.debuffs is not None  # chosen from debuff_eligible
    their_seconds = theirs.debuffs.overall.seconds
    gaps = [
        gap
        for gap in pairwise_gaps(our_fractions, debuff_fractions(theirs.debuffs))
        if gap[1] not in shared
    ]

    return [
        Finding(
            id=f"{ID_PREFIX}.{rank}",
            title=(
                f"{name} covered {their_share:.0%} of {theirs.character_name}'s "
                f"{STRETCH}, {our_share:.0%} of {our_name}'s"
            ),
            detail=GAP_DETAIL,
            confidence=Confidence.DERIVED,
            seconds_lost=None,
            evidence=(
                f"ability {ability_id}",
                f"ours over {our_seconds:.0f}s of measured {STRETCH}",
                f"theirs over {their_seconds:.0f}s of measured {STRETCH}",
            ),
            facts=(
                FindingFact(label="Ours", value=f"{our_share:.0%} of {STRETCH}",
                            confidence=Confidence.DERIVED),
                FindingFact(label="Reference", value=f"{their_share:.0%} of {STRETCH}",
                            confidence=Confidence.DERIVED),
                FindingFact(label="Sample", value=f"1 reference {DUNGEON.reference_noun}"),
            ),
            ability_id=ability_id,
            ability_name=name,
        )
        for rank, (_, ability_id, name, our_share, their_share) in enumerate(
            gaps[:MAX_AURAS_REPORTED]
        )
    ]


def _unjudged(our_name: str, names: Sequence[str]) -> Finding:
    """Debuffs the sample kept on its enemies that ours never carried.

    A debuff names who applied it, so unlike a buff's zero this one is the
    player's own. What the log cannot say is whether their build has the
    ability at all, which is why it is named rather than judged. A debuff two
    teammates took over from each other is shared and never listed here. One
    a single teammate held still is: one holder cannot show that copies never
    coexist, so whether that teammate's copy left ours no room is unknown too.
    """
    count = len(names)
    return Finding(
        id=f"{ID_PREFIX}.unjudged",
        title=(
            f"{quantity(count, 'debuff', 'debuffs')} the sample kept on enemies "
            f"{'is' if count == 1 else 'are'} absent for {our_name}"
        ),
        detail=(
            "Each of these covered enough of the sample's enemy-alive time to compare, and never "
            "sat on an enemy of ours. A debuff names who applied it, so this zero is the "
            "player's own; what the log cannot say is whether their build has the ability at "
            "all, or whether a teammate's copy of a debuff that sits once on a target left no "
            "room for theirs. Check the talents before reading it as a missed button."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            ", ".join(names),
            f"applied by at least {MIN_SAMPLE_FOR_AGGREGATE} top parses each",
            "absent from every enemy we measured",
        ),
    )


def debuff_table(our: KeyDebuffs | None, sample: ParseSample) -> DebuffTable:
    """The debuff tables: each qualifying debuff judged on Overall, described per stretch.

    Gated exactly as `tables._auras` gates the buff table: no table below the
    floor, where the comparison states one reference rather than a median.

    Where there is no table, our own seconds, tally and counts still ride along
    when our stream was read: a zero left there by default would read in the
    findings file as a measurement. Without our stream the tally is None.
    """
    if our is None:
        return DebuffTable()
    overall = our.overall
    counted = DebuffTable(
        seconds=overall.seconds,
        tally=our.bosses.tally,
        deathless=our.bosses.deathless,
        unmeasured_no_death=our.unmeasured_no_death,
        undebuffed_deaths=our.undebuffed_deaths,
    )
    eligible = sample.debuff_eligible
    if overall.alive_ms <= 0 or not eligible or not sample.can_aggregate(eligible):
        return counted

    names, per_member = per_member_fractions(eligible)
    theirs: list[KeyDebuffs] = []
    for member in eligible:
        assert member.debuffs is not None  # debuff_eligible guarantees it
        theirs.append(member.debuffs)
    shared = dict(our.shared_with)
    bosses: dict[int, str] = {}
    for window in our.bosses.windows:
        bosses.setdefault(window.encounter_id, window.name)

    rows = tuple(
        DebuffRow(
            uptime=m,
            trash=stretch_cell(
                measured_or(our.trash.coverage(m.ability_id), Withheld.NO_TRASH),
                [one.trash.coverage(m.ability_id) for one in theirs],
            ),
            bosses=stretch_cell(
                measured_or(our.on_bosses.coverage(m.ability_id), Withheld.NO_BOSS),
                [one.on_bosses.coverage(m.ability_id) for one in theirs],
            ),
            cells=tuple(
                _cell(our.bosses, eligible, m.ability_id, encounter_id, name)
                for encounter_id, name in bosses.items()
            ),
            reach=_reach(our, theirs, m.ability_id),
            shared_with=shared.get(m.ability_id, ()),
        )
        for m in uptime_measures(debuff_fractions(our), per_member, names)
    )
    return counted.model_copy(update={"rows": rows, "bosses": tuple(bosses.values())})


def _reach(our: KeyDebuffs, theirs: Sequence[KeyDebuffs], ability_id: int) -> DebuffReach:
    """One debuff's reach over each stretch, ours against the sample's: described, never judged.

    The references' Overall reaches behind the median ride along, for the reach
    table's Range and Sample.
    """
    overall = our.overall.reach(ability_id)
    assert overall is not None  # the table's gate leaves alive time, so at least one life
    their_overall = [one.overall.reach(ability_id) for one in theirs]
    return DebuffReach(
        overall=stretch_cell(overall, their_overall),
        overall_fractions=carried_shares(their_overall),
        trash=stretch_cell(
            measured_or(our.trash.reach(ability_id), Withheld.NO_TRASH),
            [one.trash.reach(ability_id) for one in theirs],
        ),
        bosses=stretch_cell(
            measured_or(our.on_bosses.reach(ability_id), Withheld.NO_BOSS),
            [one.on_bosses.reach(ability_id) for one in theirs],
        ),
    )


def _cell(
    our: BossDebuffs,
    members: Sequence[ParseMember],
    ability_id: int,
    encounter_id: int,
    name: str,
) -> BossCell:
    """One boss's cell. Descriptive only: the verdict is the row's, never a cell's.

    A member that never reached this boss, or whose pull of it was withheld,
    is not counted for it. Those that did and applied the debuff there give the
    median, at the same floor the row's own median keeps. That rule is
    `uptime.stretch_cell`'s, so this reads it rather than keeping a copy: a
    share that is not a figure is passed as None, and our own as its reason.
    """
    ours = encounter_share(our, ability_id, encounter_id)
    our_figure = ours if isinstance(ours, float) else (ours or Withheld.NO_BOSS)
    theirs: list[float | None] = []
    for member in members:
        assert member.debuffs is not None  # debuff_eligible guarantees it
        share = encounter_share(member.debuffs.bosses, ability_id, encounter_id)
        theirs.append(share if isinstance(share, float) else None)
    cell = stretch_cell(our_figure, theirs)
    return BossCell(
        encounter_id=encounter_id,
        boss=name,
        ours=cell.ours,
        their_median=cell.their_median,
        withheld=cell.withheld,
    )
```

- [ ] **Step 7: The plumbing**

1. **`sample.py`.**
   - Replace the import `from wowperf.domain.comparison.boss_debuffs import BossDebuffs` with `from wowperf.domain.comparison.key_debuffs import KeyDebuffs`.
   - Replace the `boss_debuffs` field and its comment with:

```python
    # This reference's own debuffs over every enemy of its own key, rebuilt from
    # its enemy-debuff stream. None when the stream could not be had, which
    # `compare.uptime.debuff.unavailable` states rather than reading as "applied
    # nothing".
    debuffs: KeyDebuffs | None = None
```

   - `debuff_eligible` becomes `return tuple(member for member in self.members if member.debuffs is not None)`.
2. **`service.py`.**
   - Replace the `BossDebuffs` import with `from wowperf.domain.comparison.key_debuffs import KeyDebuffs`.
   - Replace `compare_boss_debuffs_sample` in the `debuff_uptime` import with `compare_debuffs_sample`.
   - In `ComparisonSubject`, the field and its comment become:

```python
    # Our player's own debuffs over every enemy of our key. One stream serves the
    # whole group, so `cli.py` fetches it once and builds this per subject from it.
    our_debuffs: KeyDebuffs | None = None
```

   - In `_compare_player`, the call becomes `*compare_debuffs_sample(subject.our_debuffs, subject.display_name, parse),`.
3. **`tables.py`.**
   - Replace the `BossDebuffs` import with `from wowperf.domain.comparison.key_debuffs import KeyDebuffs`, and `boss_debuff_table` with `debuff_table`.
   - In `comparison_measures`, pass `subject.our_debuffs`.
   - `_for_one`'s parameter becomes `our_debuffs: KeyDebuffs | None`, and its `PlayerMeasures(...)` gets `debuffs=debuff_table(our_debuffs, parse)` in place of `boss_debuffs=...`.
   - In `_auras`' docstring, replace "sits beside these in `boss_debuffs` (see `comparison/boss_debuffs.py` and" with "sits beside these in `debuffs` (see `comparison/key_debuffs.py` and".
4. **`report/players.py`.**
   - In the `measures` import, replace `BossDebuffRow` with `DebuffRow`.
   - In `_tables`, replace `debuffs = measures.boss_debuffs` with `debuffs = measures.debuffs`.
   - `_debuff_rows`' parameter becomes `rows: Sequence[DebuffRow]`.
   - Nothing else changes in this task.
5. **`cli.py`.**
   - Replace the imports `from wowperf.domain.comparison.boss_debuffs import BossDebuffs` and `from wowperf.domain.comparison.key_debuffs import boss_debuffs` (from Task 4) with `from wowperf.domain.comparison.key_debuffs import KeyDebuffs, key_debuffs`.
   - In `_debuff_log`'s docstring, replace `compare.uptime.boss.unavailable` with `compare.uptime.debuff.unavailable`.
   - Replace `_fetch_parse_boss_debuffs` with the following. It is renamed, reads `key_debuffs`, and sets `debuffs`; its docstring's first line changes and the rest is kept.

```python
def _fetch_parse_debuffs(
    sample: ParseSample,
    references: WclRunRepository,
    our_log: Callable[[], DebuffLog | None],
    our_run: Run,
    subject: Player,
) -> tuple[ParseSample, KeyDebuffs | None]:
    """Every parse member's own debuffs over every enemy of its key, and our subject's.

    The rule is `_fetch_parse_auras`'s. A member whose counterpart cannot be
    found in its own roster is left without debuff data, unfetched. Our own
    side is built only once some member's counterpart resolves. `our_log` is
    shared across every subject of one run, because the stream covers the
    whole group: the caller memoises it, so our stream is requested once at
    most. A reference's stream is paid for once, and a later subject drawing
    the same reference reads it back from the disk cache.

    Our side is read with the run's players, so a debuff a teammate's
    application replaces is found shared. A reference is read with none:
    sharing can only lower a reference's share, which moves the median down
    and so never makes ours read wrongly below.
    """
    ours: KeyDebuffs | None = None
    ours_built = False
    members: list[ParseMember] = []
    for member in sample.members:
        their_player = find_player(member.players, member.character_name)
        if their_player is None:
            members.append(member)
            continue
        if not ours_built:
            log = our_log()
            players = frozenset(player.actor_id for player in our_run.players)
            ours = (
                None
                if log is None
                else key_debuffs(log, our_run.pulls, subject.actor_id, players)
            )
            ours_built = True
        their_log = _debuff_log(references, member.report_code, member.fight_id)
        members.append(
            member.model_copy(
                update={
                    "debuffs": None
                    if their_log is None
                    else key_debuffs(
                        their_log, member.pulls, their_player.actor_id, frozenset()
                    )
                }
            )
        )
    return sample.model_copy(update={"members": tuple(members)}), ours
```

   - In `analyze`, the call becomes `sample, our_debuffs = _fetch_parse_debuffs(...)` with the same arguments, and the subject is built with `our_debuffs=our_debuffs,`.

- [ ] **Step 8: Run the tests to see them pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain tests/test_cli.py -q`
Expected: all pass.

- [ ] **Step 9: Gate and commit**

Run the gate. Then run `grep -rn "compare.uptime.boss\|boss_debuff_table\|BossDebuffRow\|BossDebuffTable\|our_boss_debuffs\|_fetch_parse_boss_debuffs\|compare_boss_debuffs_sample" src tests`. It must find nothing.

Write `<scratchpad>\task5-msg.txt`:

```text
Judge debuff coverage over every enemy of the key

The verdict read the bosses alone, so a player could keep a debuff on
every boss and drop it on half the key unnoticed. It now reads Overall
coverage, and the ids become compare.uptime.debuff.* because the old
name would describe the wrong figure. Each row describes its trash, its
bosses and its reach beside the verdict, and the table carries the two
counts of what could not be measured.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/boss_debuffs.py src/wowperf/domain/comparison/measures.py src/wowperf/domain/comparison/uptime.py src/wowperf/domain/comparison/debuff_uptime.py src/wowperf/domain/comparison/sample.py src/wowperf/domain/comparison/service.py src/wowperf/domain/comparison/tables.py src/wowperf/domain/report/players.py src/wowperf/cli.py tests/domain/comparison/test_debuff_uptime.py tests/domain/comparison/test_sample.py tests/domain/comparison/test_sample_invariants.py tests/domain/report/test_build_players.py tests/test_cli.py
```

```bash
/mingw64/bin/git commit -F /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/task5-msg.txt
```

---

### Task 6: Give our run and every parse reference its fight's own clock

The key clock is the fight's start to its end. `Run.window_ms` is something else: it runs from the first pull's start to the last pull's end, and it leaves out the walk to the first pack. The fight dict is already in hand wherever a run is built. `WclRunRepository._load` reads the cached report (`self._report(report_code, hits)`), picks the fight (`select_keystone_fight`), and passes that fight to `build_run(report, fight, ...)`. That is true for our own `load` and for `load_parse_reference` alike, so the reference's clock costs 0 points.

**Files:**
- Modify:
  - `src/wowperf/domain/model.py` (`Run.fight_ms`)
  - `src/wowperf/adapters/wcl/ingest.py` (`build_run`, `_fight_clock`)
  - `src/wowperf/domain/comparison/sample.py` (`ParseMember.fight_ms`)
  - `src/wowperf/cli.py` (`_samples`)
- Test:
  - `tests/adapters/wcl/test_ingest.py`
  - `tests/domain/comparison/test_sample.py`
  - `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `Run.fight_ms: tuple[int, int] | None = None`;
  - `ParseMember.fight_ms: tuple[int, int] | None = None`, which is None for a raid reference.
- Unchanged: `build_run(report, fight, talents=None, loadouts=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/adapters/wcl/test_ingest.py`:

```python
def test_the_fights_own_clock_is_carried_into_the_run() -> None:
    # The fight's start and end, not the first pull's start and the last pull's end.
    run = build_run(report(), select_keystone_fight(report()["fights"], None))

    assert run.fight_ms == (10_000, 1_810_000)


def test_a_fight_with_no_clock_carries_none() -> None:
    report = {"code": "abc123", "masterData": {"actors": []}}

    assert build_run(report, a_minimal_fight()).fight_ms is None
```

In `tests/domain/comparison/test_sample.py`, in `test_a_parse_member_carries_no_run`, add `"fight_ms",` to the expected set of `ParseMember.model_fields`. Add this sentence to that test's docstring: "`fight_ms` is here because buffs are judged over a reference's own key clock, which no route can supply."

Append to `tests/test_cli.py`:

```python
def test_both_sides_of_a_parse_comparison_carry_their_fights_own_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Buffs are judged over each side's key clock. A reference's clock is read
    from the report the cache already holds, so no query is added for it, and
    the shared fixture's fight runs 0 to 1,920,000ms on both sides."""
    captured: dict[str, Any] = {}

    def fake_compare(**kwargs: Any) -> list[Any]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr("wowperf.cli.compare", fake_compare)

    result = run_analyze(tmp_path, "--player", "Emberkin")

    assert result.exit_code == 0, result.output
    assert captured["ours"].run.fight_ms == (0, 1_920_000)
    [subject] = captured["subjects"]
    assert subject.parse is not None
    assert subject.parse.members
    assert {member.fight_ms for member in subject.parse.members} == {(0, 1_920_000)}
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl/test_ingest.py tests/domain/comparison/test_sample.py tests/test_cli.py -q -k "clock or carries_no_run"`
Expected:
- `AttributeError: 'Run' object has no attribute 'fight_ms'`;
- the field-set assertion fails on the missing `fight_ms`.

- [ ] **Step 3: Implement**

1. In `src/wowperf/domain/model.py`, add this field to `Run` after `pulls`:

```python
    # The fight's own start and end: the key clock, from the timer's start to the
    # key's end with the walking between pulls included. Not `window_ms`, which
    # runs from the first pull to the last. None when the fight carried no clock,
    # which only a hand-built fixture does.
    fight_ms: tuple[int, int] | None = None
```

2. In `src/wowperf/adapters/wcl/ingest.py`, add `fight_ms=_fight_clock(fight),` after `pulls=_build_pulls(fight),` in `build_run`. Then add this function after `build_run`:

```python
def _fight_clock(fight: dict[str, Any]) -> tuple[int, int] | None:
    """The fight's own start and end, or None when the fight dict carries neither."""
    start, end = fight.get("startTime"), fight.get("endTime")
    if start is None or end is None:
        return None
    return (int(start), int(end))
```

3. In `src/wowperf/domain/comparison/sample.py`, add this field to `ParseMember` after `pulls`:

```python
    # This reference's fight from its start to its end: the key clock its buffs
    # are judged over. Read from the report the cache already holds, so it costs
    # nothing. None for a raid reference, whose buffs another rule reads.
    fight_ms: tuple[int, int] | None = None
```

4. In `src/wowperf/cli.py`, in `_samples`, add `fight_ms=theirs.run.fight_ms,` after `pulls=theirs.run.pulls,` in the `ParseMember(...)` it builds.

- [ ] **Step 4: Run the tests to see them pass**

Run the Step 2 command. Expected: all pass. Then run `uv run pytest -q`. Every other test still passes, because nothing reads the clock yet.

- [ ] **Step 5: Gate and commit**

Run the gate. Write `<scratchpad>\task6-msg.txt`:

```text
Carry each fight's own clock on the run and on a parse reference

Buffs are about to be judged over the whole key clock, from the fight's
start to its end, on both sides. The run's window starts at the first
pull, so it misses the walk to the first pack. The fight's own start and
end are already in the cached report on both sides, so this costs no
query.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
/mingw64/bin/git add src/wowperf/domain/model.py src/wowperf/adapters/wcl/ingest.py src/wowperf/domain/comparison/sample.py src/wowperf/cli.py tests/adapters/wcl/test_ingest.py tests/domain/comparison/test_sample.py tests/test_cli.py
```

```bash
/mingw64/bin/git commit -F /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/task6-msg.txt
```

---

### Task 7: Judge buffs over the key clock

This task also measures a boss pull Warcraft Logs lists twice once in the buff windows (choice 13). The duplicate test that `boss_windows_of` runs moves into `boss_debuffs.boss_pulls_listed_once`, and `uptime.boss_windows` calls it too.

What a duplicate does today, read from the code:
- `uptime.boss_windows` returns one span per boss pull, so it returns a duplicated pull's span twice.
- `auras.uptime_seconds_in` clips every band to every window and merges the clipped intervals before summing, so the buff's seconds inside that pull count once.
- The denominators sum every boss pull: `spells.boss_seconds` today, and Task 7's `_share_in` for the Bosses cell. So the pull's seconds count twice.

On a fight whose only boss pull is listed twice, a buff up throughout reads 50%. Beside one other boss pull of the same length, it reads 67%.

The Overall figure and the Without bosses cell never count the duplicate twice. `key_clock_uptime` reads the fight's one span. `without_boss_pulls` walks the sorted boss windows with a cursor, and a repeated window starts behind it.

This task leaves the cast path alone. A cast rate reads `spells.boss_pulls` and `spells.boss_seconds`, never `boss_windows`: `grep -rn "boss_windows(" src` finds it only in `uptime.py` and `tables.py`. The raid's buff rule, `whole_fight_uptime`, reads no window at all, and the raid's denominator is `ParseMember.boss_seconds` through the default `over`. So neither path moves.

**Files:**
- Modify:
  - `src/wowperf/domain/comparison/boss_debuffs.py` (`boss_pulls_listed_once`, read by `boss_windows_of`; `Withheld.NOTHING_OUTSIDE_BOSSES`)
  - `src/wowperf/domain/comparison/uptime.py`
  - `src/wowperf/domain/comparison/sample.py` (`ParseMember`'s docstring)
  - `src/wowperf/domain/comparison/wording.py`
  - `src/wowperf/domain/comparison/service.py`
  - `src/wowperf/domain/comparison/measures.py`
  - `src/wowperf/domain/comparison/tables.py`
  - `src/wowperf/domain/report/players.py`
- Modify tests:
  - `tests/domain/comparison/test_boss_debuffs.py`
  - `tests/domain/comparison/test_uptime.py`
  - `tests/domain/comparison/test_service.py`
  - `tests/domain/comparison/test_tables.py`
  - `tests/domain/comparison/test_sample_invariants.py`
  - `tests/domain/report/test_build_players.py`
  - `tests/test_cli.py`
  - `tests/e2e/test_compare_e2e.py`
  - `tests/e2e/test_uptime_e2e.py`

**Interfaces:**
- Consumes: Task 6's `Run.fight_ms` and `ParseMember.fight_ms`, and Task 5's `stretch_cell`, `measured_or` and `StretchCell`.
- Produces:
  - In `boss_debuffs`: `boss_pulls_listed_once(pulls: Sequence[Pull]) -> tuple[tuple[int, Pull], ...]`, each boss pull with its position in `pulls`, a pull that repeats the previous boss pull's encounter, start and end dropped. `boss_windows_of` reads it, and its signature and behaviour are unchanged.
  - `Withheld.NOTHING_OUTSIDE_BOSSES = "nothing outside boss pulls"`, the reason an empty buff Without bosses cell gives. That stretch is the key clock less its boss pulls, walking included, so the debuff's "no trash measured" would be false there. Task 8 gives it its label.
  - In `uptime`:
    - `boss_windows(pulls)` keeps its signature and lists a boss pull Warcraft Logs lists twice once. It no longer imports `spells.boss_pulls`, which stays as it is for the cast path;
    - `UptimeRule = Callable[[Sequence[Pull], Span | None], Callable[[Aura], float]]`;
    - `fight_seconds(fight_ms: Span | None) -> float`;
    - `key_clock_uptime(pulls, fight_ms) -> Callable[[Aura], float]`;
    - `without_boss_pulls(fight_ms: Span, pulls: Sequence[Pull]) -> tuple[Span, ...]`;
    - `boss_seconds_of(member: ParseMember) -> float` and `fight_seconds_of(member: ParseMember) -> float`;
    - new keyword arguments on `compare_uptime` and `compare_uptime_sample`: `our_fight_ms: Span | None = None` and `over: Callable[[ParseMember], float] = boss_seconds_of`;
    - `whole_fight_uptime(pulls, fight_ms)`;
    - `boss_pull_uptime` is removed, because this task leaves nothing in `src/` using it.
  - `wording.KEY`.
  - In `measures`:
    - `AuraRow(uptime: AuraUptime, without_bosses: StretchCell = StretchCell(), bosses: StretchCell = StretchCell())`;
    - `PlayerMeasures.auras: tuple[AuraRow, ...]`;
    - `PlayerMeasures.key_seconds: float = 0.0`.

- [ ] **Step 1: Write the failing tests, and rewrite the ones the change breaks**

The helper's own test in `test_boss_debuffs.py` is written at Step 7. Written here, its import error would stop `test_boss_debuffs.py`, `test_debuff_uptime.py` and `test_tables.py` from collecting, since the last two import helpers from it. The two duplicate tests below could then never show their wrong figure at Step 6.

**`tests/domain/comparison/test_uptime.py`:**
- Its first ABOUTME line becomes `# ABOUTME: Behaviour tests for buff uptime against a top parse or sample, by each caller's rule.`, since the module now pins the key clock rule beside the boss-pull one.
- Replace its imports through the `wording` line with:

```python
from collections.abc import Callable, Sequence

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.measures import Verdict
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, ParseMember, ParseSample
from wowperf.domain.comparison.spells import boss_seconds
from wowperf.domain.comparison.uptime import (
    UPTIME_GAP_FRACTION,
    boss_windows,
    compare_uptime,
    compare_uptime_sample,
    fight_seconds,
    fight_seconds_of,
    key_clock_uptime,
    seconds_up_in,
    seconds_up_over_the_fight,
    uptime_measures,
    whole_fight_uptime,
    without_boss_pulls,
)
from wowperf.domain.comparison.wording import DUNGEON, KEY
```

- Add this rule after `a_reference`:

```python
def on_boss_pulls(
    pulls: Sequence[Pull], fight_ms: tuple[int, int] | None
) -> Callable[[Aura], float]:
    """This module's rule: uptime inside a route's boss pulls, the fight's clock ignored.

    The comparison's own branches -- the floor, the gap bar, the fallbacks -- do
    not depend on which stretch a rule reads, so this module drives them over
    boss pulls, where its fixtures put their bands. The rule a real key binds
    is `key_clock_uptime`, pinned below.
    """
    return seconds_up_in(boss_windows(pulls))
```

- In `pairwise_uptime` and `sample_uptime`, replace `measured=boss_pull_uptime` with `measured=on_boss_pulls`. In `pairwise_uptime`'s docstring, replace "so every one of them binds `boss_pull_uptime` and our own side is the two values that route produces" with "read here over its boss pulls by `on_boss_pulls`, and our own side is the two values that route produces".
- In `test_overlapping_bands_over_a_whole_fight_are_counted_once`, the last line becomes `assert whole_fight_uptime((), None) is seconds_up_over_the_fight`.
- Append:

```python
def test_the_key_clock_rule_reads_the_fight_from_its_start_to_its_end() -> None:
    aura = an_aura(1, "Fixture Ward", (0, 50_000), (150_000, 250_000))

    assert key_clock_uptime((BOSS, TRASH), (0, 200_000))(aura) == 100.0
    assert key_clock_uptime((BOSS, TRASH), None)(aura) == 0.0


def test_without_boss_pulls_is_the_clock_less_every_boss_pull() -> None:
    first = a_pull(0, 100_000, 160_000, encounter_id=2001)
    trash = a_pull(1, 200_000, 260_000, encounter_id=0)
    second = a_pull(2, 300_000, 360_000, encounter_id=2002)

    assert without_boss_pulls((0, 400_000), (first, trash, second)) == (
        (0, 100_000),
        (160_000, 300_000),
        (360_000, 400_000),
    )
    assert without_boss_pulls((0, 100_000), (a_pull(0, 0, 100_000, encounter_id=2001),)) == ()


def test_a_fights_seconds_are_its_clock_and_no_clock_reads_zero() -> None:
    assert fight_seconds((10_000, 1_810_000)) == 1800.0
    assert fight_seconds(None) == 0.0


def test_a_boss_pull_warcraft_logs_lists_twice_is_one_window() -> None:
    # One encounter, start and end listed twice, as `dungeonPulls` lists some
    # wipes. Two windows would count its seconds twice in a sum over them while
    # `uptime_seconds_in` merges the aura's seconds in it once. The same boss
    # pulled again later is a window of its own.
    relisted = BOSS.model_copy(update={"index": 2, "pull_id": 2})
    again = a_pull(3, 300_000, 400_000, encounter_id=12825)

    assert boss_windows((BOSS, relisted, TRASH, again)) == (
        (0, 100_000),
        (300_000, 400_000),
    )


def test_a_reference_is_read_over_its_own_clock_when_the_rule_reads_one() -> None:
    # The reference's key runs 300s and carried the buff for 150s of it; its boss
    # pull, the default denominator, is 100s. Ours ran the same 300s and carried
    # it 30s. Over the two clocks that is 50% against 10%. Divided by boss
    # seconds, the reference would read 150%.
    theirs = a_reference(
        a_run(BOSS, TRASH),
        PlayerAuras(actor_id=11, on_self=(an_aura(1, "Fixture Ward", (0, 150_000)),)),
    ).model_copy(update={"fight_ms": (0, 300_000)})
    ours = PlayerAuras(actor_id=7, on_self=(an_aura(1, "Fixture Ward", (0, 30_000)),))

    findings = compare_uptime(
        (BOSS, TRASH), 300.0, ours, OUR_NAME, theirs,
        measured=key_clock_uptime, words=KEY, our_fight_ms=(0, 300_000), over=fight_seconds_of,
    )

    [gap] = [finding for finding in findings if finding.id == "compare.uptime.self.0"]
    assert gap.title == (
        "Fixture Ward was up for 50% of Bríala's key time, 10% of Stonewake (actor 7)'s"
    )
```

**`tests/domain/comparison/test_service.py`:**
- In `a_loaded`, add this argument to its `Run(...)`, after `owner_name="emberkin",`:

```python
            fight_ms=(
                (min(pull.start_ms for pull in pulls), max(pull.end_ms for pull in pulls))
                if pulls
                else None
            ),
```

- In `a_parse_member`, add `fight_ms=theirs.run.fight_ms,` after `pulls=theirs.run.pulls,`.
- Replace the comment above `OUR_AURAS` with:

```python
# Buffs are judged over each side's key clock: ours runs 0-460_000ms and the
# parse reference's 0-60_000ms. 3s of Arcane Power against 57s of it is a gap of
# over 90 points, which clears UPTIME_GAP_FRACTION.
```

**`tests/domain/comparison/test_tables.py`:**
- Add `from wowperf.domain.comparison.boss_debuffs import Withheld` to the imports, and add `StretchCell` to the `measures` import.
- Add `from tests.domain.comparison.test_boss_debuffs import a_listed_twice` above the `tests.domain.comparison.test_service` import.
- In `a_parse_member`, add `fight_ms=theirs.run.fight_ms,` after `pulls=theirs.run.pulls,`.
- Correct two docstrings that say boss time, because each of these references' key clock is its one boss pull:
  - `an_aura_parse_member`'s becomes:

```python
    """A reference carrying Arcane Power for `band_ms` of a pull `seconds` long.

    That pull is its whole key clock and, unless `fought_a_boss` is False, a
    boss pull. It always starts at zero, so a `band_start_ms` past its end is an
    aura the reference carried outside every boss pull and outside its key clock.
    """
```

  - `a_sample_carrying_an_aura_unevenly`'s becomes:

```python
    """Three references carrying an aura across their key clock, and one that did not.

    Each key clock here is one boss pull. The three sit at 0.75, 0.6 and 0.95
    of theirs, each a division by a different denominator, so no fraction is
    the band length that produced it. Their median is 0.75 against our own 0.25.

    The fourth is the awkward one, and what makes a change to which members the
    aura table counts visible rather than only a change to how it divides. It
    carried the aura, but never inside its own key clock, which reads the same
    as never having carried it at all. Counted as a zero it would drag the
    median to 0.675.
    """
```
- Replace `test_an_aura_row_is_a_share_of_boss_time_on_both_sides` with:

```python
def test_an_aura_row_is_judged_over_the_key_clock_on_both_sides() -> None:
    """Thirty seconds of a two-minute key is a quarter of it, and the sample's four
    references with the aura inside their clock carried it over 0.75, 0.6, 0.95
    and 0.75 of theirs. Every one of those is a division by a different
    denominator, so none of them is the band length that produced it. Each run
    here is one pull long, so its clock is that pull."""
    sample = ParseSample(
        members=(
            an_aura_parse_member("REF1", 60.0, 45_000),
            an_aura_parse_member("REF2", 90.0, 54_000),
            an_aura_parse_member("REF3", 60.0, 57_000),
            # No boss pull: its key clock still counts, so it carried the aura
            # over the key though it has no Bosses figure to give.
            an_aura_parse_member("REF4", 60.0, 45_000, fought_a_boss=False),
            # No aura data at all, so not an eligible member of the sample.
            a_parse_member_without_auras("REF5"),
            # The aura was up, but never inside this reference's own clock, which
            # reads the same as never having carried it. Counted as a zero, it
            # would pull the median down.
            an_aura_parse_member("REF6", 60.0, 30_000, band_start_ms=100_000),
        )
    )

    measures = comparison_measures(
        a_run_with_a_two_minute_boss(), only_ours(sample, our_auras=OUR_UPTIME)
    )[OUR_SLUG]

    [row] = measures.auras
    assert row.uptime.name == "Arcane Power"
    assert row.uptime.ours == 0.25
    assert row.uptime.their_median == 0.75
    assert row.uptime.their_fractions == (0.75, 0.6, 0.95, 0.75)
    assert row.uptime.verdict is Verdict.BELOW
    # Bosses describes: four references fought one, and REF6 sat at zero there,
    # so the other three give the median.
    assert row.bosses == StretchCell(ours=0.25, their_median=0.75)
    # This key was all boss pull: nothing of ours lay outside one.
    assert row.without_bosses == StretchCell(withheld=Withheld.NOTHING_OUTSIDE_BOSSES)
    assert measures.key_seconds == 120.0
```

- Append:

```python
def a_two_pull_aura_member(code: str, *, boss_listed_twice: bool = False) -> ParseMember:
    """A reference with a minute of trash, then a minute of boss 140s later, its
    aura up from the key's start to its end. `boss_listed_twice` lists that boss
    pull twice, as Warcraft Logs lists some wipes."""
    trash, boss = a_pull_of(0, (1,), 60.0), a_pull_of(1, (9,), 60.0, boss=True)
    pulls = (trash, *a_listed_twice(boss)) if boss_listed_twice else (trash, boss)
    theirs = a_loaded((THEIRS,), pulls)
    return a_parse_member(
        code,
        theirs,
        auras=PlayerAuras(actor_id=THEIRS.actor_id, on_self=(an_aura(260_000),)),
    )


def test_an_aura_is_described_without_bosses_and_on_bosses_beside_its_verdict() -> None:
    """Ours ran 250s: 100s of trash, 100s of walking, then a 50s boss pull. The
    aura was up for the first 100s: 40% of the key, half of the 200s outside the
    boss pull, and none of the boss. Every reference held it the whole key."""
    ours = a_loaded(
        (OURS,), (a_pull_of(0, (1,), 100.0), a_pull_of(1, (9,), 50.0, boss=True))
    )
    sample = ParseSample(
        members=tuple(a_two_pull_aura_member(code) for code in ("REF1", "REF2", "REF3"))
    )
    our_auras = PlayerAuras(actor_id=OURS.actor_id, on_self=(an_aura(100_000),))

    measures = comparison_measures(ours, only_ours(sample, our_auras=our_auras))[OUR_SLUG]

    [row] = measures.auras
    assert (row.uptime.ours, row.uptime.their_median) == (0.4, 1.0)
    assert row.without_bosses == StretchCell(ours=0.5, their_median=1.0)
    assert row.bosses == StretchCell(ours=0.0, their_median=1.0)
    assert measures.key_seconds == 250.0


def test_a_boss_pull_listed_twice_counts_once_in_the_bosses_cell() -> None:
    """Warcraft Logs lists some boss pulls twice, with one encounter, start and
    end. Ours: 100s of trash, then a 50s boss pull listed twice, the aura up over
    that pull alone. Each reference lists its 60s boss pull twice too, the aura
    up throughout. Counted twice, a pull's seconds double while the aura's
    seconds in it merge once, and both sides would read 50% on bosses."""
    trash, boss = a_pull_of(0, (1,), 100.0), a_pull_of(1, (9,), 50.0, boss=True)
    ours = a_loaded((OURS,), (trash, *a_listed_twice(boss)))
    sample = ParseSample(
        members=tuple(
            a_two_pull_aura_member(code, boss_listed_twice=True)
            for code in ("REF1", "REF2", "REF3")
        )
    )
    our_auras = PlayerAuras(
        actor_id=OURS.actor_id, on_self=(an_aura(50_000, start_ms=200_000),)
    )

    measures = comparison_measures(ours, only_ours(sample, our_auras=our_auras))[OUR_SLUG]

    [row] = measures.auras
    assert row.bosses == StretchCell(ours=1.0, their_median=1.0)
    # The key clock and the key less its boss pulls never counted it twice:
    # 50s of a 250s key, and none of the 200s outside the boss pull.
    assert row.uptime.ours == 0.2
    assert row.without_bosses == StretchCell(ours=0.0, their_median=1.0)
```

- In `test_every_uptime_finding_has_a_table_row_stating_the_same_figures`, replace its last block, from `by_aura = ...` to the end, with:

```python
    by_aura = {row.uptime.ability_id: row.uptime for row in measures.auras}
    gaps = [f for f in findings if f.id.startswith("compare.uptime.self.")]
    assert gaps, "no uptime finding to check against"

    for finding in gaps:
        assert finding.ability_id is not None
        measured = by_aura[finding.ability_id]
        assert finding.ability_name == measured.name
        assert fact_value(finding, "Ours") == f"{measured.ours:.0%} of key time"
        assert fact_value(finding, "Reference median") == (
            f"{measured.their_median:.0%} of key time"
        )
        assert f"{measured.ours:.0%}" in finding.title
        assert f"{measured.their_median:.0%}" in finding.title
```

**`tests/domain/comparison/test_sample_invariants.py`:**
- In `OUR_RUN`, add `fight_ms=(0, 1_320_000),` after `owner_name="emberkin",`. Replace the comment above `OUR_AURAS` with:

```python
# Buffs are judged over the key clock, 0 to 1_320_000ms here, so 6s of the aura
# kept up is under 1% of it -- low enough for every top parse below (80%) to clear
# UPTIME_GAP_FRACTION against it, and still above zero so the "we never had it at
# all" carve-out does not swallow the gap.
```

- In `_parse_member`, add `fight_ms=(0, 120_000),` after `pulls=theirs.pulls,`. Replace the comment `# This run's boss pull spans 0ms to 120_000ms; 96s of the aura is 80% of it.` with `# This run's key and its one boss pull both span 0ms to 120_000ms; 96s of the aura is 80% of either.`, wrapped to the line limit.

**`tests/test_cli.py`:** replace `test_a_compared_run_fetches_both_players_auras_and_reports_uptime` with:

```python
def test_a_compared_run_fetches_both_players_auras_and_reports_uptime(tmp_path: Path) -> None:
    """The defining feature of this task: two `AuraTable` queries, one per player,
    feeding a real, populated uptime finding -- not the `unavailable` fallback a
    missing counterpart (or a fixture with no key clock at all) would silently
    produce instead, satisfying `any(id.startswith("compare.uptime."))` either
    way and hiding the bug.

    Both fights run 1,920s by the shared fixture's own clock, and buffs are
    judged over it. `aura_rows_by_code` gives both sides the same ability, ours
    for half the key and theirs for all of it, so the gap clears the reporting
    thresholds in `wowperf.domain.comparison.uptime` -- and our own side must
    carry the ability at all, or `_gap_findings` drops it as attributed to
    someone else's kit rather than this player's.
    """
    calls: list[str] = []
    result = run_analyze(
        tmp_path,
        calls=calls,
        aura_rows_by_code={
            "abc123": {
                "onSelf": [
                    {
                        "guid": 999,
                        "name": "Power Infusion",
                        "totalUptime": 960000,
                        "totalUses": 1,
                        "bands": [{"startTime": 0, "endTime": 960000}],
                    }
                ],
            },
            PARSE_REFERENCE_CODE: {
                "onSelf": [
                    {
                        "guid": 999,
                        "name": "Power Infusion",
                        "totalUptime": 1920000,
                        "totalUses": 1,
                        "bands": [{"startTime": 0, "endTime": 1920000}],
                    }
                ],
            },
        },
    )

    payload = written_findings(tmp_path)
    ids = [f["id"] for f in payload["findings"]]

    assert result.exit_code == 0, result.output
    assert calls.count("AuraTable") == 2
    assert "compare.uptime.self.0.emberkin-0" in ids
```

- In `build_analyze_transport`'s docstring, replace the sentences from "`boss_pull_reports` turns a named report's only dungeon pull" through "a genuine, populated uptime finding instead." with the lines below. The `aura_rows_by_code` sentences that follow them are unchanged.

```python
    `boss_pull_reports` turns a named report's only dungeon pull from trash
    (encounter id 0) into a boss pull. A comparison that reads boss pulls, such
    as the boss cast rates, needs one: with the fixture's default all-trash pull
    every run reports zero boss seconds. Buff uptime is judged over the fight's
    own key clock, so it reads a populated figure without one.
```

**`tests/domain/report/test_build_players.py`:**
- Add `AuraRow,` to the `measures` import.
- Wrap every `AuraUptime(...)` passed inside an `auras=(...)` tuple as `AuraRow(uptime=AuraUptime(...))`, with the `AuraUptime` arguments unchanged. For example, `AuraUptime(ability_id=3, name="Bone Shield", ours=0.984, their_median=1.0, their_fractions=(1.0,), verdict=Verdict.LEVEL)` becomes `AuraRow(uptime=AuraUptime(ability_id=3, name="Bone Shield", ours=0.984, their_median=1.0, their_fractions=(1.0,), verdict=Verdict.LEVEL))`. The places are:
  - `test_an_uptime_table_is_sorted_by_our_own_uptime_not_by_the_gap` (two);
  - `test_an_uptime_row_is_spelled_as_a_percentage`;
  - `a_card_with_all_three_tables`;
  - `test_an_aura_the_comparison_refused_to_judge_keeps_that_verdict`;
  - `test_each_verdict_reaches_a_row_as_its_own_word`;
  - `test_the_debuff_table_follows_the_buff_table_with_a_column_per_boss`.

  The `uptime=` of a `DebuffRow` is not wrapped.

**`tests/e2e/test_compare_e2e.py`:** replace the block from `gaps = [f for f in findings if f.id.startswith("compare.uptime.self.")]` to the end of that test with:

```python
    gaps = [f for f in findings if f.id.startswith("compare.uptime.self.")]
    below = [row for row in measures.auras if row.uptime.verdict is Verdict.BELOW]
    assert len(gaps) == min(len(below), MAX_AURAS_REPORTED)

    by_aura = {row.uptime.ability_id: row.uptime for row in measures.auras}
    for finding in gaps:
        assert finding.ability_id is not None
        aura = by_aura[finding.ability_id]
        assert finding.ability_name == aura.name
        assert fact_value(finding, "Ours") == f"{aura.ours:.0%} of key time"
        assert fact_value(finding, "Reference median") == (
            f"{aura.their_median:.0%} of key time"
        )
```

**`tests/e2e/test_uptime_e2e.py`:** append to its test function:

```python
    # Buffs are judged over the fight's own clock, so every band must sit inside it.
    assert loaded.run.fight_ms is not None
    start, end = loaded.run.fight_ms
    for aura in auras.on_self:
        for band in aura.bands:
            assert start <= band.start_ms and band.end_ms <= end, aura.name
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain tests/test_cli.py -q`
Expected:
- ImportErrors on `KEY`, `key_clock_uptime`, `fight_seconds`, `fight_seconds_of`, `without_boss_pulls` and `AuraRow`;
- once those names exist, and until `service.py` binds the key clock, two tests fail because the verdict still reads boss pulls:
  - `test_a_compared_run_fetches_both_players_auras_and_reports_uptime` in `tests/test_cli.py`. The shared fixture's fight holds no boss pull, so the boss rule reports `compare.uptime.unavailable` and no `compare.uptime.self.0`.
  - `test_every_uptime_finding_has_a_table_row_stating_the_same_figures` in `tests/domain/comparison/test_tables.py`. Its facts read "of boss time" where it expects "of key time".

`test_uptime_findings_appear_when_both_sides_carry_auras` in `test_service.py` passes under both rules (5% against 95%), so it does not pin the switch.

The two duplicate tests show their wrong figure at Step 6, once everything but the duplicate rule is in place.

- [ ] **Step 3: `uptime.py`**

1. Replace the ABOUTME's second line with `# ABOUTME: Fractions of the stretch a rule names, never seconds: two runs last different lengths.`
2. In the module comment under it, replace "It is rebuilt from the event stream instead, for bosses, in `debuff_uptime.py` and `boss_debuffs.py`" with "It is rebuilt from the event stream instead, for every enemy of a key, in `debuff_uptime.py` and `key_debuffs.py`".
3. Add `Span` to the `boss_debuffs` import Task 5 added: `from wowperf.domain.comparison.boss_debuffs import Span, Withheld`.
4. Replace `UptimeRule` and its docstring with:

```python
UptimeRule = Callable[[Sequence[Pull], Span | None], Callable[[Aura], float]]
"""How long a side's auras count as up, given that side's own route and its fight's clock.

The counterpart of `spells.CastRule`, and one rule for both sides for the same
reason: a fraction is only comparable when the two numerators were measured the
same way. The clock is the fight's own start and end, None where a side has none
to give; a rule that does not read it ignores it.
"""
```

5. Delete `boss_pull_uptime`. Add the following after `seconds_up_in`:

```python
def fight_seconds(fight_ms: Span | None) -> float:
    """Seconds of a fight's own clock, zero for a side that carries none."""
    return 0.0 if fight_ms is None else (fight_ms[1] - fight_ms[0]) / 1000


def key_clock_uptime(pulls: Sequence[Pull], fight_ms: Span | None) -> Callable[[Aura], float]:
    """The Mythic+ rule: uptime over the whole key clock, from the fight's start to its end.

    The walking between pulls is inside it, so a buff only up in combat reads
    lower the more of the key was spent between pulls, on either side. `pulls`
    is accepted and ignored. A side with no clock measures nothing, and its
    seconds read zero, which the comparison states as unavailable.
    """
    return seconds_up_in(() if fight_ms is None else (fight_ms,))


def without_boss_pulls(fight_ms: Span, pulls: Sequence[Pull]) -> tuple[Span, ...]:
    """The key clock less its boss pulls: the trash pulls and the walking between them."""
    windows: list[Span] = []
    cursor = fight_ms[0]
    for start, end in sorted(boss_windows(pulls)):
        if start > cursor:
            windows.append((cursor, min(start, fight_ms[1])))
        cursor = max(cursor, end)
    if cursor < fight_ms[1]:
        windows.append((cursor, fight_ms[1]))
    return tuple((start, end) for start, end in windows if end > start)
```

6. Change `whole_fight_uptime`'s signature to `def whole_fight_uptime(pulls: Sequence[Pull], fight_ms: Span | None) -> Callable[[Aura], float]:`. In its docstring, replace "`pulls` is accepted and ignored" with "`pulls` and `fight_ms` are accepted and ignored".
7. Add the following after `whole_fight_uptime`:

```python
def boss_seconds_of(member: ParseMember) -> float:
    """A reference's boss seconds: its denominator under every rule but the key clock."""
    return member.boss_seconds


def fight_seconds_of(member: ParseMember) -> float:
    """A reference's key clock in seconds: its denominator under the key clock rule."""
    return fight_seconds(member.fight_ms)
```

8. In `compare_uptime`:
   - Add two keyword parameters after `words: Wording,`: `our_fight_ms: Span | None = None,` and `over: Callable[[ParseMember], float] = boss_seconds_of,`.
   - Replace `their_seconds = theirs.boss_seconds` with `their_seconds = over(theirs)`.
   - Replace the two `fractions_of(...)` arguments of `_gap_findings(...)` with:

```python
        fractions_of(our_auras.on_self, measured(our_pulls, our_fight_ms), our_seconds),
        fractions_of(their_auras.on_self, measured(theirs.pulls, theirs.fight_ms), their_seconds),
```

   - Append this paragraph to its docstring: "`our_fight_ms` is our fight's own clock and `over` reads a reference's denominator, for a rule that reads the clock. Their defaults read boss seconds, as the raid and every rule before the key clock did."
9. In `compare_uptime_sample`:
   - Add the same two keyword parameters after `words: Wording,`.
   - Pass `our_fight_ms=our_fight_ms, over=over,` to the fallback `compare_uptime(...)` call.
   - Replace `our_fractions = fractions_of(our_auras.on_self, measured(our_pulls), our_seconds)` with `our_fractions = fractions_of(our_auras.on_self, measured(our_pulls, our_fight_ms), our_seconds)`.
   - Pass `over=over` to `_gap_findings_sample(...)` beside `measured=measured, words=words`.
10. In `_gap_findings_sample`:
    - Add the keyword parameter `over: Callable[[ParseMember], float],` after `words: Wording,`.
    - Replace `their_seconds = member.boss_seconds` with `their_seconds = over(member)`.
    - Replace `measured(member.pulls)` with `measured(member.pulls, member.fight_ms)`.
11. Correct the text in this module that named boss time, which is false once a caller can bind the key clock:
    - `UPTIME_GAP_FRACTION`'s docstring becomes `"""How much more of the measured stretch they must have it up before it is worth reporting."""`.
    - In `compare_uptime`'s docstring, the first line becomes `"""Where an aura was up markedly more of the reference's measured stretch than of ours.`.
    - In `compare_uptime_sample`'s docstring, the first line becomes `"""Where an aura was up over markedly more of the sample's measured stretches than of ours.`.
    - In `_gap_findings_sample`'s docstring, the first line becomes `"""Auras up over markedly more of the sample's measured stretches than of ours, by median.`, and "a band that never overlaps a boss pull reads the same" becomes "a band that never overlaps the stretch its rule measures reads the same".
    - In `_gap_findings`, the comment above `title=` becomes:

```python
                # Presence, never agency. A proc is not something a player
                # keeps up, and this family cannot tell a proc from a button:
                # the aura table reports that a buff was present, not who or
                # what put it there. So the aura is the subject and the two
                # players are only whose stretch it is measured over -- the
                # key clock in a dungeon, the fight itself in a raid, which is
                # what `words.stretch_time` spells out below.
```

12. In `src/wowperf/domain/comparison/sample.py`, the second paragraph of `ParseMember`'s docstring becomes:

```python
    There is deliberately no `comparability`: nothing on the parse axis is
    shaped like a duration. Casts are compared as rates per minute of boss time,
    auras as fractions of the key clock and debuffs as fractions of enemy-alive
    time, and all three mean the same thing at any keystone level, so the rule
    that gates `compare.duration` has nothing to gate here.
```

- [ ] **Step 4: `wording.py`, `measures.py`, `service.py`**

1. Append to `src/wowperf/domain/comparison/wording.py`:

```python
KEY = DUNGEON.model_copy(
    update={
        "both_sides": "a key clock",
        "over": "the key",
        "absent_from": "our own key",
        "rate_basis": "the key's clock",
        "stretch_time": "key time",
        "uptime_hedge": (
            "Key time runs from the key's start to its end with the walking between pulls "
            "included, so a buff only up in combat reads lower the more of the key was spent "
            "between pulls, and a reference that walked less reads higher whatever either "
            "player did. A different keystone level still changes what fits, so read a narrow "
            "gap as noise."
        ),
    }
)
"""A Mythic+ run's buffs, judged over the whole key clock rather than its boss pulls.

Only the uptime family reads it, so only the slots `uptime.py` fills are changed.
The others keep `DUNGEON`'s words, which no uptime sentence says.
"""
```

2. In `src/wowperf/domain/comparison/measures.py`:
   - Replace `AuraUptime`'s docstring first line, "One aura's share of our boss time against the sample's median share.", with "One aura's share of the stretch its family judges, against the sample's median share."
   - Add after `StretchCell`:

```python
class AuraRow(Frozen):
    """One buff: the figure judged over the whole key clock, and two cells that describe.

    `uptime` is the key clock's figure and carries the verdict. `without_bosses`
    is the key less its boss pulls and `bosses` the boss pulls; neither carries
    a verdict.
    """

    uptime: AuraUptime
    without_bosses: StretchCell = StretchCell()
    bosses: StretchCell = StretchCell()
```

   - In `PlayerMeasures`, `auras` becomes `auras: tuple[AuraRow, ...] = ()`, and add after `pack_count`:

```python
    key_seconds: float = 0.0
    """Our key clock in seconds, from the fight's start to its end: the buff table's
    denominator."""
```

3. In `src/wowperf/domain/comparison/service.py`:
   - Replace the `uptime` import with `from wowperf.domain.comparison.uptime import compare_uptime_sample, fight_seconds, fight_seconds_of, key_clock_uptime`, wrapped in parentheses.
   - Replace the `wording` import with `from wowperf.domain.comparison.wording import DUNGEON, KEY`.
   - In `_compare_player`, replace the comment and the two lines above `return [` with:

```python
    # Our own side of the two parse comparisons, as the values they read rather
    # than as a run: this axis is a dungeon, so its route decides which casts
    # count, on our side and on every reference's alike, and its fight's own
    # clock decides which milliseconds a buff is measured over.
    our_pulls = ours.run.pulls
    our_boss_seconds = boss_seconds(our_pulls)
    our_fight_ms = ours.run.fight_ms
```

   - Replace the `compare_uptime_sample(...)` entry with:

```python
        *compare_uptime_sample(
            our_pulls, fight_seconds(our_fight_ms), subject.our_auras, subject.display_name,
            parse, measured=key_clock_uptime, words=KEY, our_fight_ms=our_fight_ms,
            over=fight_seconds_of,
        ),
```

- [ ] **Step 5: `tables.py` and `players.py`**

First, in `src/wowperf/domain/comparison/boss_debuffs.py`, replace `Withheld` (as Task 5 left it) with:

```python
class Withheld(StrEnum):
    """Why a boss, one boss's cell, or one stretch's cell carries no figure.

    The first three are read off our own route: a boss pull may hold no enemy
    `bosses_of` can name, a key may hold no trash life to measure, and a key
    clock may hold no time outside its boss pulls. The last two are about the
    sample beside a figure of ours.
    """

    NO_BOSS = "no boss found"
    NO_TRASH = "no trash measured"
    NOTHING_OUTSIDE_BOSSES = "nothing outside boss pulls"
    NOT_REACHED = "no reference measured this boss"
    TOO_FEW = "too few references"
```

In `src/wowperf/domain/comparison/tables.py`:

1. Imports:
   - `from wowperf.domain.auras import PlayerAuras, uptime_seconds_in`;
   - `from wowperf.domain.comparison.boss_debuffs import Span, Withheld`;
   - in the `measures` import, replace `AuraUptime` with `AuraRow`;
   - the `uptime` import becomes `aura_fractions, boss_windows, fight_seconds, measured_or, stretch_cell, uptime_measures, without_boss_pulls`;
   - `from wowperf.domain.model import LoadedRun, Player, Pull`.
2. In `_for_one`, compute `auras, key_seconds = _auras(ours, our_auras, parse)` before the `return`. Pass `auras=auras,` and `key_seconds=key_seconds,` to `PlayerMeasures(...)`.
3. Replace `_auras` with the following, and add the two helpers after it:

```python
def _auras(
    ours: LoadedRun, our_auras: PlayerAuras | None, parse: ParseSample
) -> tuple[tuple[AuraRow, ...], float]:
    """Buff uptime against the sample's median: judged over the key clock, described beside it.

    Buffs only, from this table: no query argument narrows the enemy-debuff
    table to one caster, so what a player kept up on enemies cannot come from
    it. That figure is rebuilt from the event stream instead, and sits beside
    these in `debuffs` (see `comparison/key_debuffs.py` and
    `.claude/skills/wcl-api/SKILL.md`, "The debuff event stream does name the
    caster").

    The verdict reads each side's whole key clock, from its fight's start to its
    end, as `compare_uptime_sample` does for the findings. Without bosses and
    Bosses describe and never judge. The seconds returned are our own key
    clock's, and zero beside no rows.
    """
    eligible = parse.aura_eligible
    if not eligible:
        # Not one reference returned aura data, which settles it on the
        # reference side alone: there is nothing for ours to be compared against.
        return (), 0.0

    our_fight = ours.run.fight_ms
    our_seconds = fight_seconds(our_fight)
    if (
        our_auras is None
        or our_fight is None
        or our_seconds <= 0
        or not parse.can_aggregate(eligible)
    ):
        # Below the floor, or our own side has nothing to compute a fraction
        # from either way. The comparison states a single reference here rather
        # than a statistic, and one reference has no median for a table to hold.
        return (), 0.0

    names: dict[int, str] = {}
    per_member: list[dict[int, float]] = []
    for member in eligible:
        assert member.auras is not None  # aura_eligible guarantees a PlayerAuras
        fight = member.fight_ms
        their_seconds = fight_seconds(fight)
        fractions = (
            aura_fractions(member.auras.on_self, (fight,), their_seconds)
            if fight is not None and their_seconds > 0
            else {}
        )
        qualifying: dict[int, float] = {}
        for ability_id, (name, fraction) in fractions.items():
            # A band that never overlaps the key clock reads the same as never
            # having carried the aura at all, the reading `aura_fractions` already
            # gives the pairwise comparison.
            if fraction <= 0.0:
                continue
            names.setdefault(ability_id, name)
            qualifying[ability_id] = fraction
        per_member.append(qualifying)

    our_fractions = aura_fractions(our_auras.on_self, (our_fight,), our_seconds)
    our_away, our_bosses = _beside(our_fight, ours.run.pulls)
    rows: list[AuraRow] = []
    for m in uptime_measures(our_fractions, per_member, names):
        away: list[float | None] = []
        on_bosses: list[float | None] = []
        for member in eligible:
            assert member.auras is not None  # aura_eligible guarantees a PlayerAuras
            their_away, their_bosses = _beside(member.fight_ms, member.pulls)
            away.append(_share_in(member.auras, m.ability_id, their_away))
            on_bosses.append(_share_in(member.auras, m.ability_id, their_bosses))
        our_away_share = _share_in(our_auras, m.ability_id, our_away)
        our_boss_share = _share_in(our_auras, m.ability_id, our_bosses)
        rows.append(
            AuraRow(
                uptime=m,
                without_bosses=stretch_cell(
                    measured_or(our_away_share, Withheld.NOTHING_OUTSIDE_BOSSES), away
                ),
                bosses=stretch_cell(measured_or(our_boss_share, Withheld.NO_BOSS), on_bosses),
            )
        )
    return tuple(rows), our_seconds


def _beside(
    fight_ms: Span | None, pulls: Sequence[Pull]
) -> tuple[tuple[Span, ...], tuple[Span, ...]]:
    """A side's two described stretches: the key clock less its boss pulls, and its boss pulls."""
    away = without_boss_pulls(fight_ms, pulls) if fight_ms is not None else ()
    return away, boss_windows(pulls)


def _share_in(auras: PlayerAuras, ability_id: int, windows: tuple[Span, ...]) -> float | None:
    """This aura's share of these windows, or None when they hold no time at all.

    The denominator sums the windows as given. Neither caller's windows overlap:
    `without_boss_pulls` walks past every boss pull, and `boss_windows` lists a
    boss pull Warcraft Logs lists twice once, so no second is counted twice.
    """
    seconds = sum(end - start for start, end in windows) / 1000
    if seconds <= 0:
        return None
    aura = next((one for one in auras.on_self if one.ability_id == ability_id), None)
    return 0.0 if aura is None else uptime_seconds_in(aura, windows) / seconds
```

In `src/wowperf/domain/report/players.py`:
- In the `measures` import, replace `AuraUptime` with `AuraRow`.
- Replace `_aura_rows` with the version below. Its docstring keeps its paragraph and drops only "as shares of boss time not seconds", which is now false.

```python
def _aura_rows(rows: Sequence[AuraRow]) -> tuple[ComparisonRow, ...]:
    """Aura uptimes, our own highest first, as shares not seconds.

    The two cast tables lead with the widest gap. This one does not, because it
    is read differently: dozens of rows long, it answers "how much of the fight
    did I hold each of these for", and that is a list a reader scans from the
    top. Sorting by the gap scattered the figures a reader came for and led
    with whatever the player held *least*.
    """
    ordered = sorted(rows, key=lambda row: row.uptime.ours, reverse=True)
    built = []
    for row in ordered:
        m = row.uptime
        low, high = observed_range(m.their_fractions)
        built.append(
            ComparisonRow(
                ability_id=m.ability_id,
                name=m.name,
                ours=f"{m.ours:.0%}",
                theirs=f"{m.their_median:.0%}",
                spread=f"{low:.0%} to {high:.0%}",
                sample=f"{len(m.their_fractions)} top parses",
                verdict=m.verdict.value,
                verdict_label=VERDICT_LABELS[m.verdict],
            )
        )
    return tuple(built)
```

The buff table's heading and caption change in Task 8.

- [ ] **Step 6: Run the tests to see the duplicate tests fail on their figure**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain tests/test_cli.py -q`
Expected: every test passes except these two, which fail on what a boss pull listed twice does today:
- `test_a_boss_pull_warcraft_logs_lists_twice_is_one_window` reads `((0, 100000), (0, 100000), (300000, 400000))`: the duplicate's span twice;
- `test_a_boss_pull_listed_twice_counts_once_in_the_bosses_cell` reads `StretchCell(ours=0.5, their_median=0.5, withheld=None)` on bosses: the pull's seconds counted twice, the aura's once.

- [ ] **Step 7: One rule for a boss pull listed twice**

1. In `tests/domain/comparison/test_boss_debuffs.py`, add `boss_pulls_listed_once,` to the `wowperf.domain.comparison.boss_debuffs` import, between `Withheld,` and `boss_windows_of,`. Then append, after `test_a_duplicate_of_a_pull_is_not_the_next_pull_for_a_trash_pull_either`:

```python
def test_a_boss_pull_listed_twice_is_kept_once_at_its_own_position() -> None:
    # The position is the pull's place in the route, which `boss_windows_of`
    # reads on from to find the next pull. The same boss pulled again later is
    # a second pull, not a duplicate.
    first, twin = a_listed_twice(BOSS_PULL)
    again = a_pull(3, 100_000, 160_000, encounter_id=2001, name=BOSS_NAME)

    assert boss_pulls_listed_once((TRASH_PULL, first, twin, again)) == (
        (1, first),
        (3, again),
    )
```

   Every other test in that file stays as it is. Among them, `test_a_boss_pull_listed_twice_is_measured_once`, `test_a_council_kill_listed_twice_is_one_window_ending_at_its_deaths` and `test_a_duplicate_of_a_pull_is_not_the_next_pull_for_a_trash_pull_either` pin `boss_windows_of`'s rule once it reads the helper.

   Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_boss_debuffs.py -q`
   Expected: a collection error, `ImportError: cannot import name 'boss_pulls_listed_once'`.

2. In `src/wowperf/domain/comparison/boss_debuffs.py`, add this function after `bosses_of`, before `boss_windows_of`:

```python
def boss_pulls_listed_once(pulls: Sequence[Pull]) -> tuple[tuple[int, Pull], ...]:
    """Every boss pull of a route with its position in it, a pull listed twice kept once.

    Warcraft Logs sometimes lists one physical boss pull twice, with the same
    encounter, start and end (measured 2026-10-08: 10 duplicated boss pulls in 5
    of 969 cached fights, all wipes). A boss pull that repeats the boss pull
    before it is dropped, so its seconds and what was up during them are
    counted once wherever they are summed. The same boss pulled again at
    another time is another pull. The position is the pull's index in `pulls`,
    for a caller that reads on from it.
    """
    kept: list[tuple[int, Pull]] = []
    previous: tuple[int, int, int] | None = None
    for position, pull in enumerate(pulls):
        if not pull.is_boss:
            continue
        listed = (pull.encounter_id, pull.start_ms, pull.end_ms)
        if listed == previous:
            continue
        previous = listed
        kept.append((position, pull))
    return tuple(kept)
```

3. In `boss_windows_of`, replace these lines:

```python
    windows: list[BossWindow] = []
    previous: tuple[int, int, int] | None = None
    for position, pull in enumerate(pulls):
        if not pull.is_boss:
            continue
        listed = (pull.encounter_id, pull.start_ms, pull.end_ms)
        if listed == previous:
            continue
        previous = listed
        horizon = next(
```

with:

```python
    windows: list[BossWindow] = []
    for position, pull in boss_pulls_listed_once(pulls):
        horizon = next(
```

   The rest of the function is unchanged. In its docstring, after "It is measured once, so its seconds and covered time are not counted twice.", add the sentence "`boss_pulls_listed_once` holds that rule, and the buff windows read it too."

4. In `src/wowperf/domain/comparison/uptime.py`, extend the `boss_debuffs` import of Step 3 to `from wowperf.domain.comparison.boss_debuffs import Span, Withheld, boss_pulls_listed_once`. Remove `from wowperf.domain.comparison.spells import boss_pulls`: `boss_windows` was its only reader in this module, and `spells.boss_pulls` itself stays as it is for the cast path.
5. Replace `boss_windows` with:

```python
def boss_windows(pulls: Sequence[Pull]) -> tuple[tuple[int, int], ...]:
    """The millisecond spans of the boss pulls, for intersecting aura bands against.

    Takes the route rather than a `Run`, so that a parse reference — which
    carries its pulls and no run — reaches the same rule our own side does.

    A boss pull Warcraft Logs lists twice is one span, by the rule the debuff
    figure's `boss_windows_of` reads, so a sum over these spans counts its
    seconds once, as the merge in `auras.uptime_seconds_in` counts the aura's.
    """
    return tuple((pull.start_ms, pull.end_ms) for _, pull in boss_pulls_listed_once(pulls))
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain tests/test_cli.py tests/adapters -q`
Expected: all pass, the three duplicate tests included. Every `boss_windows_of` test in `test_boss_debuffs.py` passes unchanged. `tests/domain/comparison/test_parse_axis.py`, the raid's uptime, passes unchanged, and so does `tests/domain/comparison/test_spells.py`, the cast rates'.

- [ ] **Step 9: Gate and commit**

Run the gate. Then run `grep -rn "boss_pull_uptime" src tests`. It must find nothing. Then run `grep -rn "boss_windows(" src`. It must list only `src/wowperf/domain/comparison/uptime.py` and `src/wowperf/domain/comparison/tables.py`, which shows the rule reached no cast or raid path.

Write `<scratchpad>\task7-msg.txt`:

```text
Judge buff uptime over the whole key clock

Buff uptime read boss pulls only, so a buff dropped across the trash
went unseen. It is now judged over each side's key clock, from the
fight's start to its end, and described without bosses and on bosses
beside the verdict. The finding ids keep their names. The raid path
keeps its own rule through the defaults of the two new arguments.

A boss pull Warcraft Logs lists twice put its span in the buff windows
twice, so its seconds counted twice while the buff's seconds in it
merged once: a buff up through every boss pull read below 100%. The
debuff figure already measured such a pull once. The rule now lives in
one helper both read. Cast rates do not read these windows and are
left to a separate change.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/boss_debuffs.py tests/domain/comparison/test_boss_debuffs.py src/wowperf/domain/comparison/uptime.py src/wowperf/domain/comparison/sample.py src/wowperf/domain/comparison/wording.py src/wowperf/domain/comparison/service.py src/wowperf/domain/comparison/measures.py src/wowperf/domain/comparison/tables.py src/wowperf/domain/report/players.py tests/domain/comparison/test_uptime.py tests/domain/comparison/test_service.py tests/domain/comparison/test_tables.py tests/domain/comparison/test_sample_invariants.py tests/domain/report/test_build_players.py tests/test_cli.py tests/e2e/test_compare_e2e.py tests/e2e/test_uptime_e2e.py
```

```bash
/mingw64/bin/git commit -F /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/task7-msg.txt
```

---

### Task 8: Draw the buff columns, "Debuff coverage", "Debuff reach", the note and the warning

The builder decides everything here, and the template only loops.

- **Two booleans** on `ComparisonTable` say whether the figure columns and the Verdict column are drawn.
- **The uptime tables' layout.** The three uptime tables draw no figure columns. Their judged Overall figure, its Range and its Sample are each row's first three cells, under headings of the same names, in the layout choice 11 gives. Their rows leave `ours`, `theirs`, `spread` and `sample` empty, so each string is drawn from one place.
- **A table with both defaults** renders byte for byte as before. `trim_blocks` and `lstrip_blocks` remove a block tag that stands on its own line, and the one inline tag that opens an indented line is written `{%+ ... %}`, which keeps that line's indentation.
- **What holds that claim.** `test_a_comparison_row_without_cells_ends_as_it_always_has` holds it, with the rich fixture's column tests (`test_every_compared_cell_lands_under_the_heading_it_claims` and `test_a_right_aligned_column_is_headed_by_a_right_aligned_heading`), whose tables are all cast rates. The golden pages do not hold it. None of the four (`minimal.html`, `raid.html`, `night.html`, `progression.html`) draws a comparison table: none contains `<table class="compared-rows">`.
- **The goldens still change, in one comment.** Every golden inlines the stylesheet, so each of the four changes where Step 4 corrects the verdict-tint comment in `report.css.j2`, and nowhere else. Step 6 regenerates them and checks that diff.
- **The verdict tint stays on the second cell.** On the uptime tables that cell is the Verdict word, not our figure. The word states the same branch the tint does, so the tint stays. Moving it onto Overall would need a table-level class, which the invariants' exact `<table class="compared-rows">` pattern would no longer match. The stylesheet's comment, which said the second cell is always our figure, is corrected instead.
- **Sample is right-aligned on these tables.** It is drawn through the cells loop, which marks every cell `num`, while the cast tables' Sample column is left-aligned. That is accepted: the heading and its cells agree, which `test_a_right_aligned_column_is_headed_by_a_right_aligned_heading` pins, and the template only loops.

**Files:**
- Modify:
  - `src/wowperf/domain/report/model.py`
  - `src/wowperf/domain/report/players.py`
  - `src/wowperf/adapters/render/_players.html.j2`
  - `src/wowperf/adapters/render/report.css.j2` (the verdict-tint comment)
- Modify tests:
  - `tests/domain/report/test_build_players.py`
  - `tests/adapters/render/test_html_invariants.py`
  - `tests/adapters/render/golden/minimal.html`, `raid.html`, `night.html` and `progression.html`, regenerated

**Interfaces:**
- Consumes: Task 5's `DebuffTable`, `DebuffRow`, `DebuffReach` and `StretchCell`; Task 7's `AuraRow` and `PlayerMeasures.key_seconds`.
- Produces:
  - `ComparisonTable.figures: bool = True`, `.judged: bool = True`, `.note: str = ""` and `.warning: str = ""`;
  - `ComparisonRow.ours`, `.theirs`, `.spread`, `.sample` and `.verdict_label`, each defaulting to `""`;
  - in `players`: `DESCRIBED = "described"`, `DEBUFF_NOTE`, `WITHHELD_LABELS[Withheld.NO_TRASH] == "no trash measured"`, `WITHHELD_LABELS[Withheld.NOTHING_OUTSIDE_BOSSES] == "nothing outside boss pulls"`, and the private helpers `_overall`, `_spread_and_sample`, `_reach_rows` and `_unmeasured`.
- Consumes from Task 5 as well: `DebuffReach.overall_fractions`, which the reach table's Range and Sample state.

- [ ] **Step 1: Write the failing tests, and rewrite the ones the change breaks**

In `tests/domain/report/test_build_players.py`:
- Add `DebuffReach,` and `StretchCell,` to the `measures` import.
- In `a_card_with_all_three_tables`, add `key_seconds=1834.0,` to its `PlayerMeasures(...)` after `pack_count=8,`.
- In `test_the_three_tables_come_under_their_own_headings_in_one_order`, the third heading becomes `"Buff uptime"`.
- In `test_the_table_captions_are_not_interchangeable`, the `auras.caption` assertion becomes:

```python
    assert auras.caption == (
        "Share of 1834s of key time, from the key's start to its end with the walking "
        "between pulls included, against the median of the parses that carried each. The "
        "verdict reads Overall, and Range and Sample are Overall's. Without bosses is the key "
        "less its boss pulls and Bosses the boss pulls; each reads ours against the median "
        "and carries no verdict. A buff only up in combat reads lower over the whole key the "
        "more of it was spent between pulls, so a reference that walked less reads higher "
        "whatever either player did. Derived."
    )
```

- In `test_an_uptime_row_is_spelled_as_a_percentage`, the table draws its figure in its Overall cell now, and an uptime is a share of the key's time. Replace "uptimes are a share of boss time" in its docstring with "uptimes are a share of the key's time", and its last two assertions with:

```python
    assert auras.rows[0].cells[0] == "98% against 100%"
```

- In `test_an_aura_the_comparison_refused_to_judge_keeps_that_verdict`, the Range and Sample are cells now. Replace its last two assertions, on `row.spread` and `row.sample`, with:

```python
    assert row.cells[1:3] == ("94% to 99%", "3 top parses")
```

- Replace `test_the_debuff_table_follows_the_buff_table_with_a_column_per_boss` with:

```python
def test_the_debuff_tables_follow_the_buff_table_with_a_column_per_stretch_and_boss() -> None:
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraRow(
                    uptime=AuraUptime(
                        ability_id=195181, name="Bone Shield", ours=0.62,
                        their_median=0.98, their_fractions=(0.95, 0.98, 0.99),
                        verdict=Verdict.BELOW,
                    )
                ),
            ),
            boss_seconds=648.0,
            key_seconds=1834.0,
            debuffs=DebuffTable(
                rows=(
                    DebuffRow(
                        uptime=AuraUptime(
                            ability_id=55078, name="Blood Plague", ours=0.7,
                            their_median=0.9, their_fractions=(0.85, 0.9, 0.95),
                            verdict=Verdict.BELOW,
                        ),
                        trash=StretchCell(ours=0.4, their_median=0.8),
                        bosses=StretchCell(ours=0.6, their_median=0.9),
                        cells=(
                            BossCell(
                                encounter_id=2001, boss="First Boss", ours=0.5,
                                their_median=0.9,
                            ),
                            BossCell(
                                encounter_id=2002, boss="Second Boss",
                                withheld=Withheld.NO_BOSS,
                            ),
                            BossCell(
                                encounter_id=2003, boss="Third Boss", ours=0.8,
                                withheld=Withheld.TOO_FEW,
                            ),
                        ),
                    ),
                ),
                seconds=200.0,
                bosses=("First Boss", "Second Boss", "Third Boss"),
                tally=PairingTally(orphan_removes=1, closed_at_end=2),
            ),
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    assert [t.heading for t in card.comparison_tables] == [
        "Buff uptime",
        "Debuff coverage",
        "Debuff reach",
    ]
    table = card.comparison_tables[1]
    assert (table.figures, table.judged) == (False, True)
    assert table.cell_headings == (
        "Overall",
        "Range",
        "Sample",
        "Trash",
        "Bosses",
        "First Boss",
        "Second Boss",
        "Third Boss",
    )
    [row] = table.rows
    assert row.verdict_label == "Below"
    # Drawn once, in the cells: the row's own figure strings stay empty on a
    # table that draws no figure columns.
    assert (row.ours, row.theirs, row.spread, row.sample) == ("", "", "", "")
    # Range and Sample are Overall's: the references' 85%, 90% and 95%. Neither
    # stretch nor any boss cell carries a range of its own.
    assert row.cells == (
        "70% against 90%",
        "85% to 95%",
        "3 top parses",
        "40% against 80%",
        "60% against 90%",
        "50% against 90%",
        "no boss found",
        "80%; too few references",
    )
    assert table.caption == (
        "Share of 200s of enemy-alive time, summed over every enemy measured, that carried "
        "each debuff from this player or their pets, against the median of the parses that "
        "applied each. The verdict reads Overall, and Range and Sample are Overall's. Trash "
        "is the mobs of trash pulls; Bosses is the bosses themselves, a council's each from "
        "the pull's start to their own death, or to the pull's end if they did not die "
        "there; adds that spawn during a boss fight, and the enemies of a pull with no boss "
        "found, count in Overall only. Those columns and each boss's read ours against the "
        "median and carry no verdict. A debuff a teammate's application replaces is marked "
        "shared, not judged. The group's log for the whole fight held 1 removal with no "
        "application, dropped (a pet copy's second removal counts here); 2 applications "
        "still open at the fight's end, closed there; and 0 rows on an enemy with no game "
        "id, skipped. Derived."
    )
    # This row sets no reach, so every reach cell is empty, Range and Sample too.
    [unreached] = card.comparison_tables[2].rows
    assert unreached.cells == ("", "", "", "", "")
```

- In `a_shared_debuff_table`:
  - give its `DebuffRow(...)` `trash=StretchCell(withheld=Withheld.NO_TRASH),` and `bosses=StretchCell(ours=0.7, their_median=0.9),` after `uptime=...`;
  - replace its last two lines, `[table] = card.comparison_tables` and `return table`, with `coverage, _reach = card.comparison_tables` and `return coverage`.
- In `test_a_shared_debuff_is_labelled_with_who_it_was_shared_with_and_not_judged`, the last assertion becomes:

```python
    assert row.cells == (
        "70% against 90%",
        "85% to 95%",
        "3 top parses",
        "no trash measured",
        "70% against 90%",
        "70% against 90%",
    )
```

- In `test_a_boss_no_reference_measured_is_labelled_for_what_the_cell_can_know`, replace `assert row.cells == ("90%; no reference measured it",)` with the assertion below. The row sets neither stretch, and an empty `StretchCell` draws an empty cell.

```python
    assert row.cells == (
        "70% against 90%", "85% to 95%", "3 top parses", "", "", "90%; no reference measured it"
    )
```
- Append:

```python
def test_the_buff_table_reads_overall_its_range_and_sample_then_each_stretch() -> None:
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraRow(
                    uptime=AuraUptime(
                        ability_id=195181, name="Bone Shield", ours=0.62,
                        their_median=0.98, their_fractions=(0.95, 0.98, 0.99),
                        verdict=Verdict.BELOW,
                    ),
                    without_bosses=StretchCell(ours=0.55, their_median=0.97),
                    bosses=StretchCell(ours=0.9, withheld=Withheld.TOO_FEW),
                ),
            ),
            key_seconds=1834.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    [table] = card.comparison_tables
    assert table.heading == "Buff uptime"
    assert (table.figures, table.judged) == (False, True)
    assert table.cell_headings == ("Overall", "Range", "Sample", "Without bosses", "Bosses")
    [row] = table.rows
    assert row.verdict_label == "Below"
    # Range and Sample are the references behind Overall's median, 95% to 99%
    # over three; neither stretch carries a range of its own.
    assert row.cells == (
        "62% against 98%",
        "95% to 99%",
        "3 top parses",
        "55% against 97%",
        "90%; too few references",
    )


def test_a_key_with_no_time_outside_its_boss_pulls_says_so_in_without_bosses() -> None:
    # The buff stretch is the key less its boss pulls, walking included, so an
    # empty cell there must not borrow the debuff's "no trash measured".
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraRow(
                    uptime=AuraUptime(
                        ability_id=195181, name="Bone Shield", ours=0.62,
                        their_median=0.98, their_fractions=(0.95, 0.98, 0.99),
                        verdict=Verdict.BELOW,
                    ),
                    without_bosses=StretchCell(withheld=Withheld.NOTHING_OUTSIDE_BOSSES),
                    bosses=StretchCell(ours=0.62, their_median=0.98),
                ),
            ),
            key_seconds=1834.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    [table] = card.comparison_tables
    [row] = table.rows
    assert row.cells == (
        "62% against 98%",
        "95% to 99%",
        "3 top parses",
        "nothing outside boss pulls",
        "62% against 98%",
    )


def debuff_tables(
    *, unmeasured_no_death: int = 0, undebuffed_deaths: int = 0
) -> tuple[ComparisonTable, ComparisonTable]:
    """The coverage and reach tables of a card with one debuff, on one boss and on trash."""
    measures = {
        "stonewake-0": PlayerMeasures(
            debuffs=DebuffTable(
                rows=(
                    DebuffRow(
                        uptime=AuraUptime(
                            ability_id=55078, name="Blood Plague", ours=0.6,
                            their_median=0.9, their_fractions=(0.85, 0.9, 0.95),
                            verdict=Verdict.BELOW,
                        ),
                        trash=StretchCell(ours=0.4, their_median=0.85),
                        bosses=StretchCell(ours=0.95, their_median=0.97),
                        cells=(
                            BossCell(
                                encounter_id=2001, boss="First Boss", ours=0.95,
                                their_median=0.97,
                            ),
                        ),
                        reach=DebuffReach(
                            overall=StretchCell(ours=0.5, their_median=0.92),
                            trash=StretchCell(ours=0.45, their_median=0.9),
                            bosses=StretchCell(ours=1.0, their_median=1.0),
                            # Four, where the coverage row has three, and another
                            # range, so a reach Range or Sample read off the
                            # coverage figure would show.
                            overall_fractions=(0.88, 0.9, 0.94, 0.95),
                        ),
                    ),
                ),
                seconds=300.0,
                bosses=("First Boss",),
                tally=PairingTally(),
                unmeasured_no_death=unmeasured_no_death,
                undebuffed_deaths=undebuffed_deaths,
            ),
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]
    coverage, reach = card.comparison_tables
    return coverage, reach


def test_the_reach_table_follows_the_coverage_table_and_judges_nothing() -> None:
    coverage, reach = debuff_tables()

    assert (coverage.heading, reach.heading) == ("Debuff coverage", "Debuff reach")
    [covered] = coverage.rows
    assert covered.cells == (
        "60% against 90%",
        "85% to 95%",
        "3 top parses",
        "40% against 85%",
        "95% against 97%",
        "95% against 97%",
    )
    assert (reach.figures, reach.judged) == (False, False)
    assert reach.cell_headings == ("Overall", "Range", "Sample", "Trash", "Bosses")
    [row] = reach.rows
    assert (row.name, row.verdict, row.verdict_label) == ("Blood Plague", "described", "")
    # Range and Sample are the references' Overall reach, not their coverage.
    assert row.cells == (
        "50% against 92%",
        "88% to 95%",
        "4 top parses",
        "45% against 90%",
        "100% against 100%",
    )
    assert reach.caption == (
        "Share of the enemies measured that carried each debuff from this player or their "
        "pets at least once, against the median of the parses that applied each. Range and "
        "Sample are Overall's. A boss counts as one enemy. Reach describes and is never "
        "judged. Derived."
    )


def test_the_note_under_the_debuff_tables_explains_coverage_and_reach() -> None:
    coverage, reach = debuff_tables()

    assert coverage.note == ""
    assert reach.note == (
        "Coverage: the share of the enemies' alive time this player's debuff was on them, "
        "summed over every enemy, so a long-lived mob weighs more than one that dies in "
        "seconds. Reached: the share of the enemies that carried it at least once. Low "
        "coverage with high reach means it was spread but not kept up; low coverage with low "
        "reach means it stayed on too few mobs. A trash mob's life runs from the first debuff "
        "anyone put on it to its death; adds that spawn during a boss fight count in Overall "
        "only."
    )


@pytest.mark.parametrize(
    ("unmeasured", "undebuffed", "warning"),
    [
        (0, 0, ""),
        (3, 0, "3 enemies had no death in the log and were not measured."),
        (0, 1, "1 enemy died without anyone debuffing it and counts only toward reached."),
        (
            1,
            2,
            "1 enemy had no death in the log and was not measured; 2 died without anyone "
            "debuffing them and count only toward reached.",
        ),
    ],
)
def test_the_warning_states_each_count_only_when_above_zero(
    unmeasured: int, undebuffed: int, warning: str
) -> None:
    coverage, reach = debuff_tables(
        unmeasured_no_death=unmeasured, undebuffed_deaths=undebuffed
    )

    assert coverage.warning == ""
    assert reach.warning == warning
```

In `tests/adapters/render/test_html_invariants.py`:
- In `test_a_boss_column_lands_under_its_own_heading`, rename the fixture's heading from `"Debuff uptime on bosses"` to `"Debuff coverage"`.
- Append:

```python
def test_a_table_with_no_figure_columns_and_no_verdict_draws_only_its_cells() -> None:
    """The reach table judges nothing and states Overall, its Range and Sample, and
    each stretch in a cell, so its headings are Ability and the cells' own, in
    that order, and its note and warning follow it."""
    report = rich_report()
    table = ComparisonTable(
        heading="Debuff reach",
        caption="Derived.",
        figures=False,
        judged=False,
        cell_headings=("Overall", "Range", "Sample", "Trash", "Bosses"),
        rows=(
            ComparisonRow(
                ability_id=55078, name="Blood Plague", verdict="described",
                cells=(
                    "40% against 100%", "88% to 100%", "3 top parses", "25% against 100%",
                    "100% against 100%",
                ),
            ),
        ),
        note="Coverage: the share of alive time. Reached: the share of enemies.",
        warning="3 enemies had no death in the log and were not measured.",
    )
    first = report.players[0].model_copy(update={"comparison_tables": (table,)})
    report = report.model_copy(update={"players": (first, *report.players[1:])})

    html = render(report)

    [(headings, rows)] = [
        rendered for rendered in compared_tables(html) if "Trash" in rendered[0]
    ]
    assert headings == ["Ability", "Overall", "Range", "Sample", "Trash", "Bosses"]
    [(row_class, cells)] = rows
    assert row_class == "v-described"
    assert [MARKUP.sub("", cell) for cell in cells[1:]] == [
        "40% against 100%", "88% to 100%", "3 top parses", "25% against 100%",
        "100% against 100%",
    ]
    [body] = [body for body in COMPARED_TABLE.findall(html) if ">Trash<" in body]
    headed = _numeric_columns(COMPARED_HEADING_TAG.findall(body))
    for _, drawn in COMPARED_ROW.findall(body):
        assert _numeric_columns(COMPARED_CELL_TAG.findall(drawn)) == headed
    assert f'<p class="sub">{escape(table.note)}</p>' in html
    assert f'<p class="withheld">{escape(table.warning)}</p>' in html


def test_a_judged_table_with_no_figure_columns_keeps_its_verdict() -> None:
    report = rich_report()
    table = ComparisonTable(
        heading="Buff uptime",
        caption="Derived.",
        figures=False,
        cell_headings=("Overall", "Range", "Sample", "Without bosses", "Bosses"),
        rows=(
            ComparisonRow(
                ability_id=195181, name="Bone Shield", verdict="below", verdict_label="Below",
                cells=(
                    "62% against 98%", "95% to 99%", "3 top parses", "55% against 97%",
                    "90%; too few references",
                ),
            ),
        ),
    )
    first = report.players[0].model_copy(update={"comparison_tables": (table,)})
    report = report.model_copy(update={"players": (first, *report.players[1:])})

    [(headings, rows)] = [
        rendered
        for rendered in compared_tables(render(report))
        if "Without bosses" in rendered[0]
    ]

    assert headings == [
        "Ability", "Verdict", "Overall", "Range", "Sample", "Without bosses", "Bosses"
    ]
    [(_, cells)] = rows
    assert [MARKUP.sub("", cell) for cell in cells[1:]] == [
        "Below", "62% against 98%", "95% to 99%", "3 top parses", "55% against 97%",
        "90%; too few references",
    ]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_players.py tests/adapters/render/test_html_invariants.py -q`
Expected:
- failures on the headings, the captions, the cells, `table.figures`, `reach.note` and `reach.warning`;
- in the invariants tests, a `ValidationError` for the `ComparisonRow` that names no `ours`, and headings that still include the Ours, Median, Range and Sample figure columns before the Verdict.

- [ ] **Step 3: The view model**

In `src/wowperf/domain/report/model.py`, in `ComparisonRow`:
- Give `ours`, `theirs`, `spread`, `sample` and `verdict_label` the default `""`, keeping their order.
- Add this paragraph to its docstring: "A row of a table that draws no figure columns, or no verdict, leaves those strings empty. The uptime tables state their judged figure, its range and its sample in cells, and the reach table judges nothing."

In `ComparisonTable`, replace the two-line comment on `cell_headings` and add the four fields, so the body reads:

```python
    heading: str
    caption: str
    # Whether the row's own Ours, Median, Range and Sample columns are drawn. The
    # uptime tables draw their judged figure, its range and its sample as their
    # first three cells instead, then a cell per stretch.
    figures: bool = True
    # Whether the Verdict column is drawn. The reach table judges nothing.
    judged: bool = True
    # Extra column headings after Verdict: on the uptime tables, Overall, Range
    # and Sample, then a stretch or a boss each. Empty for every other table,
    # which then renders exactly as it always has.
    cell_headings: tuple[str, ...] = ()
    rows: tuple[ComparisonRow, ...] = ()
    # Drawn under the table: what its figures mean.
    note: str = ""
    # Drawn under the note: what its figures could not include. Empty when nothing
    # was left out.
    warning: str = ""
```

- [ ] **Step 4: The template**

In `src/wowperf/adapters/render/_players.html.j2`, replace the block from `<table class="compared-rows">` to `</details>` with:

```jinja
  <table class="compared-rows">
    <thead><tr><th scope="col">Ability</th>{% if table.figures %}<th scope="col" class="num">Ours</th><th scope="col" class="num">Median</th><th scope="col" class="num">Range</th><th scope="col">Sample</th>{% endif %}{% if table.judged %}<th scope="col">Verdict</th>{% endif %}{% for heading in table.cell_headings %}<th scope="col" class="num">{{ heading }}</th>{% endfor %}</tr></thead>
    <tbody>
    {% for row in table.rows %}
    <tr class="v-{{ row.verdict }}">
      <td>{{ ability(row.ability_id, row.name) }}</td>
      {% if table.figures %}
      <td class="num">{{ row.ours }}</td>
      <td class="num">{{ row.theirs }}</td>
      <td class="num">{{ row.spread }}</td>
      <td>{{ row.sample }}</td>
      {% endif %}
      {%+ if table.judged %}<td>{{ row.verdict_label }}</td>{% endif %}{% for cell in row.cells %}<td class="num">{{ cell }}</td>{% endfor +%}
    </tr>
    {% endfor %}
    </tbody>
  </table>
  {% if table.note %}
  <p class="sub">{{ table.note }}</p>
  {% endif %}
  {% if table.warning %}
  <p class="withheld">{{ table.warning }}</p>
  {% endif %}
  </details>
```

In `src/wowperf/adapters/render/report.css.j2`, the comment above `.compared-rows tr.v-below td:nth-child(2)` says the tint always lands on our own figure. That is false for the uptime tables, so it becomes:

```css
/* The verdict is a word in its own column and a tint here, never a colour alone:
   a reader who cannot separate the tints, or who printed the page, still has
   the column. Three of the four land on the second cell. On the cast and stat
   tables that is our own figure, the one the verdict is about. On the uptime
   tables, which draw no figure columns and state Overall in a cell after the
   verdict, it is the Verdict word itself, which says the same branch. Either
   way they say two different things. Hue says
   which side our figure landed on: --theirs mutes it where we sit under the
   sample's median, --ours picks it out where we sit over it, --ink-dim settles
   it where the two are level. Weight says whether the comparison found a
   difference at all, so below and above carry it and level does not. Without
   both readings the row a reader can act on is the quietest in the table, and
   a level row left to inherit would keep the body's ink, the brightest on the
   page. An unjudged row is greyed whole, because none of its figures was read
   as a shortfall. */
```

The three rules under it are unchanged.

- [ ] **Step 5: The builder**

In `src/wowperf/domain/report/players.py`:

1. In the `measures` import, add `AuraUptime`, `DebuffTable` and `StretchCell` beside `AuraRow` and `DebuffRow`.
2. Add `Withheld.NO_TRASH: "no trash measured",` and `Withheld.NOTHING_OUTSIDE_BOSSES: "nothing outside boss pulls",` to `WITHHELD_LABELS`, in that order, after `Withheld.NO_BOSS`. Its docstring becomes `"""How a boss or stretch cell with no figure says why, in the reader's words."""`.
3. Add after `VERDICT_LABELS` and its docstring:

```python
DESCRIBED = "described"
"""The row class of a table that judges nothing.

No stylesheet rule tints it, so its figures read in the page's own ink: reach is
a description, and a verdict's tint on it would claim a judgement nobody made.
"""

DEBUFF_NOTE = (
    "Coverage: the share of the enemies' alive time this player's debuff was on them, summed "
    "over every enemy, so a long-lived mob weighs more than one that dies in seconds. "
    "Reached: the share of the enemies that carried it at least once. Low coverage with high "
    "reach means it was spread but not kept up; low coverage with low reach means it stayed "
    "on too few mobs. A trash mob's life runs from the first debuff anyone put on it to its "
    "death; adds that spawn during a boss fight count in Overall only."
)
"""What the two debuff tables measure, drawn once under the pair."""
```

4. In `_tables`, replace the `if measures.auras:` block with:

```python
    if measures.auras:
        built.append(
            ComparisonTable(
                heading="Buff uptime",
                caption=(
                    f"Share of {measures.key_seconds:.0f}s of key time, from the key's start to "
                    "its end with the walking between pulls included, against the median of "
                    "the parses that carried each. The verdict reads Overall, and Range and "
                    "Sample are Overall's. Without bosses is the key less its boss pulls and "
                    "Bosses the boss pulls; each reads ours against the median and carries no "
                    "verdict. A buff only up in combat reads lower over the whole key the more "
                    "of it was spent between pulls, so a reference that walked less reads "
                    "higher whatever either player did. Derived."
                ),
                figures=False,
                cell_headings=("Overall", "Range", "Sample", "Without bosses", "Bosses"),
                rows=_aura_rows(measures.auras),
            )
        )
```

   Then replace the `built.append(ComparisonTable(heading="Debuff uptime on bosses", ...))` inside `if debuffs.rows:` with the following. The `tally` and `deathless` lines above it stay as they are.

```python
        built.append(
            ComparisonTable(
                heading="Debuff coverage",
                caption=(
                    f"Share of {debuffs.seconds:.0f}s of enemy-alive time, summed over every "
                    "enemy measured, that carried each debuff from this player or their pets, "
                    "against the median of the parses that applied each. The verdict reads "
                    "Overall, and Range and Sample are Overall's. Trash is the mobs of trash "
                    "pulls; Bosses is the bosses themselves, a council's each from the pull's "
                    "start to their own death, or to the pull's end if they did not die there; "
                    "adds that spawn during a boss fight, and the enemies of a pull with no "
                    "boss found, count in Overall only. Those columns and each boss's read ours "
                    "against the median and carry no verdict. A debuff a teammate's "
                    "application replaces is marked shared, not judged. The group's log for "
                    "the whole fight held "
                    f"{quantity(tally.orphan_removes, 'removal', 'removals')} with no "
                    "application, dropped (a pet copy's second removal counts here); "
                    f"{quantity(tally.closed_at_end, 'application', 'applications')} still "
                    "open at the fight's end, closed there; and "
                    f"{quantity(tally.unresolved_targets, 'row', 'rows')} on an enemy with no "
                    f"game id, skipped. {deathless}Derived."
                ),
                figures=False,
                cell_headings=(
                    "Overall", "Range", "Sample", "Trash", "Bosses", *debuffs.bosses
                ),
                rows=_debuff_rows(debuffs.rows, specs),
            )
        )
        built.append(
            ComparisonTable(
                heading="Debuff reach",
                caption=(
                    "Share of the enemies measured that carried each debuff from this player "
                    "or their pets at least once, against the median of the parses that "
                    "applied each. Range and Sample are Overall's. A boss counts as one "
                    "enemy. Reach describes and is never judged. Derived."
                ),
                figures=False,
                judged=False,
                cell_headings=("Overall", "Range", "Sample", "Trash", "Bosses"),
                rows=_reach_rows(debuffs.rows),
                note=DEBUFF_NOTE,
                warning=_unmeasured(debuffs),
            )
        )
```

5. Replace `_aura_rows` with the following. Its docstring keeps both of Task 7's paragraphs and gains a third. The row's `ours`, `theirs`, `spread` and `sample` are no longer set: the table draws no figure columns, and the cells carry those figures once.

```python
def _aura_rows(rows: Sequence[AuraRow]) -> tuple[ComparisonRow, ...]:
    """Aura uptimes, our own highest first, as shares not seconds.

    The two cast tables lead with the widest gap. This one does not, because it
    is read differently: dozens of rows long, it answers "how much of the fight
    did I hold each of these for", and that is a list a reader scans from the
    top. Sorting by the gap scattered the figures a reader came for and led
    with whatever the player held *least*.

    Its cells read Overall, Overall's range and sample, then Without bosses and
    Bosses.
    """
    ordered = sorted(rows, key=lambda row: row.uptime.ours, reverse=True)
    return tuple(
        ComparisonRow(
            ability_id=row.uptime.ability_id,
            name=row.uptime.name,
            verdict=row.uptime.verdict.value,
            verdict_label=VERDICT_LABELS[row.uptime.verdict],
            cells=(
                _overall(row.uptime),
                *_spread_and_sample(row.uptime.their_fractions),
                _cell(row.without_bosses),
                _cell(row.bosses),
            ),
        )
        for row in ordered
    )
```

6. Replace `_debuff_rows` with the following. Its docstring keeps both of its paragraphs and gains a third. As in `_aura_rows`, the row's four figure strings are no longer set, and the `low, high = observed_range(...)` line goes with them.

```python
def _debuff_rows(
    rows: Sequence[DebuffRow], specs: Mapping[int, tuple[str, str]]
) -> tuple[ComparisonRow, ...]:
    """Debuff uptimes, our own highest first, for the reason `_aura_rows` gives.

    A shared row keeps its figures and names who it was shared with in place
    of a verdict. It takes the `unjudged` tint, because like that row it says
    nothing about this player's play.

    Its cells read Overall, Overall's range and sample, Trash and Bosses, then
    each boss.
    """
    ordered = sorted(rows, key=lambda row: row.uptime.ours, reverse=True)
    built = []
    for row in ordered:
        m = row.uptime
        verdict, label = m.verdict, VERDICT_LABELS[m.verdict]
        if row.shared_with:
            verdict = Verdict.UNJUDGED
            label = _shared_label(row.shared_with, specs)
        built.append(
            ComparisonRow(
                ability_id=m.ability_id,
                name=m.name,
                verdict=verdict.value,
                verdict_label=label,
                cells=(
                    _overall(m),
                    *_spread_and_sample(m.their_fractions),
                    _cell(row.trash),
                    _cell(row.bosses),
                    *(_cell(cell) for cell in row.cells),
                ),
            )
        )
    return tuple(built)
```

7. Replace `_cell` with the following, and add the four functions after it:

```python
def _cell(cell: BossCell | StretchCell) -> str:
    """One boss's or one stretch's cell: ours against the median, or ours and why not."""
    reason = WITHHELD_LABELS[cell.withheld] if cell.withheld is not None else ""
    if cell.ours is None:
        return reason
    if cell.their_median is None:
        return f"{cell.ours:.0%}; {reason}" if reason else f"{cell.ours:.0%}"
    return f"{cell.ours:.0%} against {cell.their_median:.0%}"


def _overall(m: AuraUptime) -> str:
    """The judged figure as a cell: ours against the median, the verdict beside it."""
    return f"{m.ours:.0%} against {m.their_median:.0%}"


def _spread_and_sample(fractions: Sequence[float]) -> tuple[str, str]:
    """The Range and Sample cells of the references behind an Overall median.

    Two empty cells when there are none, as on a reach no reference measured.
    """
    if not fractions:
        return "", ""
    low, high = observed_range(fractions)
    return f"{low:.0%} to {high:.0%}", f"{len(fractions)} top parses"


def _reach_rows(rows: Sequence[DebuffRow]) -> tuple[ComparisonRow, ...]:
    """Each debuff's reach, in the coverage table's order so a reader can look across.

    Its cells read Overall, Overall's range and sample, then Trash and Bosses.
    """
    ordered = sorted(rows, key=lambda row: row.uptime.ours, reverse=True)
    return tuple(
        ComparisonRow(
            ability_id=row.uptime.ability_id,
            name=row.uptime.name,
            verdict=DESCRIBED,
            cells=(
                _cell(row.reach.overall),
                *_spread_and_sample(row.reach.overall_fractions),
                _cell(row.reach.trash),
                _cell(row.reach.bosses),
            ),
        )
        for row in ordered
    )


def _unmeasured(debuffs: DebuffTable) -> str:
    """The warning under the debuff tables, a clause per count above zero, or nothing.

    A clause stating zero would warn about nothing, so each is drawn only when
    its own count is above zero.
    """
    unmeasured, undebuffed = debuffs.unmeasured_no_death, debuffs.undebuffed_deaths
    clauses: list[str] = []
    if unmeasured:
        clauses.append(
            f"{quantity(unmeasured, 'enemy', 'enemies')} had no death in the log and "
            f"{'was' if unmeasured == 1 else 'were'} not measured"
        )
    if undebuffed:
        who = str(undebuffed) if clauses else quantity(undebuffed, "enemy", "enemies")
        clauses.append(
            f"{who} died without anyone debuffing {'it' if undebuffed == 1 else 'them'} and "
            f"{'counts' if undebuffed == 1 else 'count'} only toward reached"
        )
    return "; ".join(clauses) + "." if clauses else ""
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report tests/adapters/render -q`
Expected: everything passes except the four golden-file tests, which fail on the stylesheet comment Step 4 corrected:
- `test_the_rendered_page_matches_the_golden_file` in `test_html_invariants.py`;
- `test_the_rendered_raid_page_matches_the_golden_file`;
- `test_the_rendered_night_page_matches_the_golden_file`;
- `test_the_rendered_page_matches_the_golden_file` in `test_progression_html_invariants.py`.

The others include `test_a_comparison_row_without_cells_ends_as_it_always_has` and the rich fixture's column tests, which pin that a table with both defaults renders as it did.

Regenerate the four goldens, one command each:

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py --golden-update -q
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_raid_html_invariants.py --golden-update -q
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_night_html_invariants.py --golden-update -q
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_progression_html_invariants.py --golden-update -q
```

Then run `/mingw64/bin/git diff --stat tests/adapters/render/golden`. It must list the four files and nothing else. Run `/mingw64/bin/git diff tests/adapters/render/golden`: every changed line must lie inside the verdict-tint comment. Any other changed line means the page itself moved, and is a defect to chase before going on.

Run the Step 6 command again. Expected: all pass.

- [ ] **Step 7: Gate and commit**

Run the gate. Write `<scratchpad>\task8-msg.txt`:

```text
Draw buff uptime, debuff coverage and debuff reach over the whole key

The page now shows what the comparison judges. Each uptime table reads
the verdict, then Overall with the range and sample of the references
behind its median, then each stretch, and the debuff pair gets a reach
table that judges nothing. Range and Sample stay because the verdict
rests on Overall, and a reader weighs a median by its spread and count.
A note explains coverage against reach, and a warning names what could
not be measured. The template only loops: the builder decides which
columns a table draws. The stylesheet's comment said the verdict tint
always lands on our own figure; on these tables it lands on the verdict
word, so the comment says so, and the four golden pages carry it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
/mingw64/bin/git add src/wowperf/domain/report/model.py src/wowperf/domain/report/players.py src/wowperf/adapters/render/_players.html.j2 src/wowperf/adapters/render/report.css.j2 tests/domain/report/test_build_players.py tests/adapters/render/test_html_invariants.py tests/adapters/render/golden/minimal.html tests/adapters/render/golden/raid.html tests/adapters/render/golden/night.html tests/adapters/render/golden/progression.html
```

```bash
/mingw64/bin/git commit -F /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/task8-msg.txt
```

---

### Task 9: Say it in the docs

Spec §9 lists these. The wcl-api skill waits for Task 10, which is where a cost reading would move.

**Files:**
- `docs/plans/2026-10-13-key-uptime-coverage-design.md`
- `docs/plans/2026-10-07-enemy-debuff-uptime-design.md`
- `docs/plans/2026-10-08-council-debuff-coverage-design.md`
- `.claude/skills/mplus-analysis/SKILL.md`
- `CLAUDE.md`
- `README.md`
- `docs/how-it-works.md`

**Interfaces:** none. `tests/test_skills.py` reads the skills, so the gate covers the skill edit.

- [ ] **Step 1: This design**

1. Replace the status line with `**Status:** approved design, 2026-10-13; planned in `docs/plans/2026-10-13-key-uptime-coverage-plan.md`.`
2. At the end of §3.2, after item 7, add:

```markdown
*Amended 2026-10-13, while planning:* five points the section left open were decided in the plan.
- A measured boss's game id is never cut into lives. Otherwise every wiped boss would read as an
  enemy with no death, and every boss would count twice.
- The enemies of a boss pull with no boss found count as adds, the unfound boss among them.
- A death belongs to the last pull starting at or before it, as the council's death rule reads it.
- A death row the log writes twice at one millisecond is one death.
- The lives are built in `comparison/enemy_lives.py`, and coverage and reach in
  `comparison/key_debuffs.py`. The boss figure is built by the same helpers as before, and every
  boss test reads it through `key_debuffs`.
```

3. At the end of §4, after the **Findings** list, add the block below. The tables' columns are not in it: §4's own amendment of 2026-10-13, after planning, already states them.

```markdown
*Amended 2026-10-13, while planning:*
- The warning states each clause only when its own count is above zero.
- In the findings file, `comparison_tables.<slug>.boss_debuffs` becomes `.debuffs`, and each
  `auras` entry nests its judged figure under `uptime`, beside `without_bosses` and `bosses`.
  Each debuff row's `reach` carries `overall_fractions`, the references' Overall reaches behind
  its median.
- The page heads the first column of every comparison table "Ability", these three included, so
  the example tables above head it so too. The template draws one shared heading and only loops.
- An empty buff Without bosses cell reads "nothing outside boss pulls", not "no trash measured":
  that stretch is the key less its boss pulls, walking included, so it is not trash alone.
```

4. In §4's three example tables, replace the first column's heading with `Ability`. The three header rows become:

```markdown
| Ability | Verdict | Overall | Range | Sample | Without bosses | Bosses |
```

```markdown
| Ability | Verdict | Overall | Range | Sample | Trash | Bosses | per-boss cells as today |
```

```markdown
| Ability | Overall | Range | Sample | Trash | Bosses |
```

   Each replaces the row that heads the same columns with `Buff` or `Debuff` in their place. The separator rows under them are unchanged.

- [ ] **Step 2: The parent and council designs**

1. In `docs/plans/2026-10-07-enemy-debuff-uptime-design.md`, §2, add this indented line under the **Trash** bullet, after "It is not designed here.":

```markdown
  *Amended 2026-10-13:* trash is measured, as coverage over every enemy's life and reach across
  them, by `docs/plans/2026-10-13-key-uptime-coverage-design.md`. That design supersedes this one
  wherever a section here says trash is out or the figure is boss-only.
```

   In §3, under the bullet that ends "`report/players.py`'s `COMPARISON_PREFIXES`.", add:

```markdown
  *Amended 2026-10-13:* the ids are now `compare.uptime.debuff.{rank}`,
  `compare.uptime.debuff.unjudged` and `compare.uptime.debuff.unavailable`, judging Overall
  coverage. The table is "Debuff coverage", beside "Debuff reach"
  (`docs/plans/2026-10-13-key-uptime-coverage-design.md` §4).
```

2. In `docs/plans/2026-10-08-council-debuff-coverage-design.md`, add this paragraph at the end of §3, before `## 4. Components and data flow`:

```markdown
*Amended 2026-10-13:* the council's figure is unchanged, and it is now one boss column of "Debuff
coverage" and part of its Bosses column. The row's verdict reads Overall coverage over every enemy
of the key, by `docs/plans/2026-10-13-key-uptime-coverage-design.md`. The shared rule compares two
players on a common target, which is now a boss within one pull or one enemy's life.
```

- [ ] **Step 3: The mplus-analysis skill**

In `.claude/skills/mplus-analysis/SKILL.md`, replace the whole bullet that begins `- **Debuff uptime on bosses is rebuilt, not read.**` and ends `of a kill pull had no death in the log and were measured to the pull's end. Zero is none.` with these two bullets:

```markdown
- **Buff uptime is judged over the whole key clock**, from the fight's start to its end with the
  walking between pulls included, on our side and on every reference's. A buff only up in combat
  reads lower the more of the key was spent between pulls, so a reference that walked less reads
  higher whatever either player did: say so before reading a narrow gap as play. The card's
  Without bosses and Bosses columns describe and never judge; its Range and Sample are Overall's.
  A boss pull Warcraft Logs lists twice counts once in Bosses, as it does for debuffs.
  `comparison_tables.<slug>.auras` carries each row's `uptime`, the judged figure, beside
  `without_bosses` and `bosses`.
- **Debuff coverage is rebuilt, not read.** `compare.uptime.debuff.<rank>.<slug>` is the share
  of the enemies' alive time, summed over every enemy of the key, that carried a debuff from the
  player or their pets, against the median of the parses that applied it, by the buff family's
  thresholds. It is derived: the intervals come from the log's own applications and removals. A
  trash mob's life runs from the first debuff anyone applied to it to its death. A boss keeps the
  boss rule: a single boss over its pull, and a council's bosses each from the pull's start to
  their own death, or to the pull's end if they did not die there. Overall carries the verdict.
  Trash (the mobs of trash pulls) and Bosses describe, and adds that spawn during a boss fight
  count in Overall only. Coverage is not reach. Each row's `reach` is the share of the enemies
  that carried the debuff at least once, described and never judged; its `overall_fractions` are
  the references' Overall reaches behind its median. Low coverage with high reach
  is a debuff spread but not kept up; low coverage with low reach is one kept on too few mobs.
  Unlike a buff, a debuff names who applied it, so `compare.uptime.debuff.unjudged` is the
  player's own zero; what it cannot say is whether their build has the ability. A debuff only one
  copy of which sits on a target is another matter. When at least two of the run's players held
  it, at least one pair of them on a common target (a boss within one pull, or one enemy's life),
  and every such pair's copies overlapped by at most a second in total, a teammate's application
  replaced theirs. Two players who held it only on different targets were never compared. Such a
  debuff is shown as shared, its row's `shared_with` naming those teammates' actor ids, and is
  never judged: no gap finding, and not in `unjudged`. In the findings JSON a shared row still
  carries the `uptime.verdict` its figures reach, "below" for instance, beside the non-empty
  `shared_with`; read that row as not judged, whatever its verdict says. A zero beside a single
  teammate who held it stays `unjudged`, because one holder cannot show the copies never coexist.
  `comparison_tables.<slug>.debuffs.tally` counts what the pairing met in our own log, and is
  provenance, not a finding. It is recorded whenever our stream was read, even beside no rows,
  and is null when it was not: null is "no stream read", while a zero tally is a log that paired
  cleanly. `comparison_tables.<slug>.debuffs.deathless` is provenance too: how many council
  bosses of a kill pull had no death in the log and were measured to the pull's end. So are
  `unmeasured_no_death` and `undebuffed_deaths`. The first counts the enemies debuffed with no
  death after it in the log, left out of coverage and reach. The second counts the enemies that
  died with no debuff from anyone since their previous death, which count toward reach only.
  Neither is judged, and zero is none.
```

- [ ] **Step 4: CLAUDE.md, README and how-it-works**

1. In `CLAUDE.md`, replace:

```markdown
buff uptime, and the confounds that would make any of the others misleading. Uptime covers
buffs everywhere and debuffs on Mythic+ bosses. The enemy-debuff *table* cannot be
scoped to one caster (measured 2026-09-05), but the `Debuffs` event stream names each
application's caster (measured 2026-10-07), and the boss figure is rebuilt from it. Both are
recorded in `.claude/skills/wcl-api/SKILL.md`. Trash and raid pulls are not measured
yet; `docs/plans/2026-10-07-enemy-debuff-uptime-design.md` §2 says why.
```

   with:

```markdown
buff uptime, and the confounds that would make any of the others misleading. Uptime covers
buffs over the whole key clock and debuffs on every enemy of a Mythic+ key, as coverage of
their alive time and reach across them. The enemy-debuff *table* cannot be
scoped to one caster (measured 2026-09-05), but the `Debuffs` event stream names each
application's caster (measured 2026-10-07), and the figure is rebuilt from it. Both are
recorded in `.claude/skills/wcl-api/SKILL.md`. Raid pulls are not measured
yet; `docs/plans/2026-10-07-enemy-debuff-uptime-design.md` §2 says why.
```

2. In `README.md`, replace:

```markdown
- **Uptime covers buffs everywhere and debuffs on Mythic+ bosses.** Warcraft Logs offers no way to
  scope the enemy-debuff table to a single caster, but its event stream names each application's
  caster, so "what you kept up on the boss" is rebuilt from that stream. Trash and raid
  pulls are not measured yet.
```

   with:

```markdown
- **Uptime covers buffs over the whole key and debuffs on every enemy of a Mythic+ key.** Warcraft
  Logs offers no way to scope the enemy-debuff table to a single caster, but its event stream
  names each application's caster, so "what you kept up on enemies" is rebuilt from that stream,
  as coverage of their alive time and reach across them. Raid pulls are not measured yet.
```

3. In `docs/how-it-works.md`:
   - In the axis table, replace `debuff uptime on bosses` with `debuff coverage and reach`.
   - Replace:

```markdown
Uptime covers buffs everywhere and debuffs on Mythic+ bosses. Warcraft Logs offers no way to
scope the enemy-debuff table to one caster (measured 2026-09-05), but its `Debuffs` event stream
names each application's caster (measured 2026-10-07), so what a player kept up *on enemies* is
rebuilt from that stream for bosses. Both are recorded in `wcl-api`. Trash and raid
pulls, and any pull with no boss found, are not measured yet.
```

   with:

```markdown
Uptime covers buffs over the whole key clock and debuffs on every enemy of a Mythic+ key. Warcraft
Logs offers no way to scope the enemy-debuff table to one caster (measured 2026-09-05), but its
`Debuffs` event stream names each application's caster (measured 2026-10-07), so what a player
kept up *on enemies* is rebuilt from that stream, as coverage of their alive time and reach
across them. Both are recorded in `wcl-api`. Raid pulls are not measured yet.
```

- [ ] **Step 5: Gate and commit**

Run the gate, `tests/test_skills.py` included. Then run `grep -rn "compare.uptime.boss\|Debuff uptime on bosses\|Trash and raid" CLAUDE.md README.md docs/how-it-works.md .claude/skills`. It must find nothing.

Write `<scratchpad>\task9-msg.txt`:

```text
Say in the docs that uptime covers the whole key

CLAUDE.md, the README, how-it-works and the interpretation skill said
trash was not measured and named the old boss-only ids, which is now
false. The parent and council designs gain dated amendments, and this
design records the choices its plan made.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
/mingw64/bin/git add docs/plans/2026-10-13-key-uptime-coverage-design.md docs/plans/2026-10-07-enemy-debuff-uptime-design.md docs/plans/2026-10-08-council-debuff-coverage-design.md .claude/skills/mplus-analysis/SKILL.md CLAUDE.md README.md docs/how-it-works.md
```

```bash
/mingw64/bin/git commit -F /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/task9-msg.txt
```

---

### Task 10: Prove it live

This task carries the CLAUDE.md invariant: a new judgement is not done until a live run shows how often each state it can reach occurred. The feature adds no query, but the reference cache tier expires after a day, so the references are paid for again. Budget about 450 of the 3,600-point hour for both keys cold. That is the parent design's 400 for this pair, plus the e2e runs.

**Files:**
- Modify:
  - `docs/plans/2026-10-13-key-uptime-coverage-design.md`, the live amendment;
  - `.claude/skills/wcl-api/SKILL.md`, only if Step 6 finds a cost reading that moved.
- Scratch, not committed: `run_key1.py` (already in the scratchpad), `run_key2.py`, `live_states.py`, `survey_key.py` and their outputs.

**Interfaces:** consumes every earlier task, through `wowperf analyze`, the findings file's `comparison_tables.<slug>.auras` and `.debuffs`, `key_debuffs`, `boss_pulls_listed_once`, `boss_windows_of`, `uptime.boss_windows` and `pair_debuffs`. It produces no code.

- [ ] **Step 1: Write the second key's runner**

`run_key1.py` regenerates the first key with `--all-players`, naming the first roster player without printing them. `--all-players` needs `--player` naming the roster's first player, because the report owner's name differs from the roster's. Write `<scratchpad>\run_key2.py` with the Write tool, so that the second key's output is filtered the same way:

```python
"""Regenerate the second key's report, echoing only lines that cannot carry a player name."""
import subprocess
import sys

cache, out = sys.argv[1], sys.argv[2]
result = subprocess.run(
    ["wowperf", "analyze", "nd6Rz47Gj1ZPxFfm", "--fight", "3",
     "--cache-dir", cache, "--out", out],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
)
for line in (result.stdout + result.stderr).splitlines():
    if line.startswith(("Rate limit", "  ", "Wrote", "wrote")) or "points" in line or out in line:
        print(line)
print("exit", result.returncode)
```

- [ ] **Step 2: Re-run the two keys**

From the worktree, load the credentials inline: they are UTF-16, and they are never printed.

```bash
set -a && . <(iconv -f UTF-16 -t UTF-8 ../../../.env | tr -d '\r') 2>/dev/null && set +a; export PATH="$HOME/.local/bin:$PATH"; uv run python /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/run_key2.py ../../../cache ../../../out/uptime
```

```bash
set -a && . <(iconv -f UTF-16 -t UTF-8 ../../../.env | tr -d '\r') 2>/dev/null && set +a; export PATH="$HOME/.local/bin:$PATH"; uv run python /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/run_key1.py ../../../cache ../../../out/uptime
```

Both must end `exit 0`. Keep each command's cost breakdown, operation by operation, and the remaining quota it prints.

- [ ] **Step 3: Measure the distribution**

Write `<scratchpad>\live_states.py`:

```python
"""Task 10 of the key uptime plan: every state the two live findings files reached.

Reads the findings files only. Prints counts, ability names and percentages; a player is
"player <index>" in the comparison's own order, never a name or a slug.
"""

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

OUT = Path(sys.argv[1])
FILES = ("LyKXYvVZm192TDr6-9.findings.json", "nd6Rz47Gj1ZPxFfm-3.findings.json")


def family(finding_id):
    parts = finding_id.split(".")
    if parts[:2] != ["compare", "uptime"]:
        return None
    if parts[2] == "debuff":
        return "debuff " + ("gap" if parts[3].isdigit() else parts[3])
    if parts[2] == "self":
        return "buff gap"
    if parts[2] in ("unjudged", "unavailable"):
        return "buff " + parts[2]
    return "UNEXPECTED " + parts[2]


def state(cell):
    if cell["withheld"] is not None:
        return cell["withheld"] if cell["ours"] is None else f"ours; {cell['withheld']}"
    return "measured" if cell["ours"] is not None else "empty"


def pct(value):
    return "-" if value is None else f"{value:.2%}"


defects = 0
for name in FILES:
    payload = json.loads((OUT / name).read_text(encoding="utf-8"))
    print(f"===== {name[:4]}")
    families = Counter()
    for finding in payload["findings"]:
        kind = family(finding["id"])
        if kind is not None:
            families[f"{kind} ({finding['confidence']})"] += 1
    print("findings:", dict(sorted(families.items())))
    counts = Counter()
    medians = {"coverage": [], "reach": []}
    for index, slug in enumerate(payload["comparison"]["players"]):
        tables = payload["comparison_tables"].get(slug)
        if tables is None:
            print(f"player {index}: no tables")
            continue
        for row in tables["auras"]:
            counts[f"buff verdict {row['uptime']['verdict']}"] += 1
            counts[f"buff without bosses: {state(row['without_bosses'])}"] += 1
            counts[f"buff bosses: {state(row['bosses'])}"] += 1
        debuffs = tables["debuffs"]
        print(
            f"player {index}: enemy-alive seconds {debuffs['seconds']:.1f}, "
            f"no death {debuffs['unmeasured_no_death']}, "
            f"undebuffed {debuffs['undebuffed_deaths']}, "
            f"deathless {debuffs['deathless']}, tally {debuffs['tally']}"
        )
        for row in debuffs["rows"]:
            uptime = row["uptime"]
            verdict = "shared" if row["shared_with"] else uptime["verdict"]
            counts[f"debuff verdict {verdict}"] += 1
            counts[f"coverage trash: {state(row['trash'])}"] += 1
            counts[f"coverage bosses: {state(row['bosses'])}"] += 1
            for cell in row["cells"]:
                counts[f"coverage per boss: {state(cell)}"] += 1
            for stretch in ("overall", "trash", "bosses"):
                counts[f"reach {stretch}: {state(row['reach'][stretch])}"] += 1
            medians["coverage"].append(uptime["their_median"])
            if row["reach"]["overall"]["their_median"] is not None:
                medians["reach"].append(row["reach"]["overall"]["their_median"])
            figures = [uptime["ours"], uptime["their_median"], *uptime["their_fractions"]]
            for cell in (row["trash"], row["bosses"], *row["cells"]):
                figures += [cell["ours"], cell["their_median"]]
            if any(value is not None and value > 1.0 + 1e-9 for value in figures):
                defects += 1
                print(f"  DEFECT: a coverage above 100% on {uptime['name']}")
            # A reference that covered any time on an enemy reached it, and one that
            # reached an enemy covered time on it, so the two lists name the same
            # references. Unequal lengths would put the reach Range over other parses.
            if len(row["reach"]["overall_fractions"]) != len(uptime["their_fractions"]):
                defects += 1
                print(f"  DEFECT: reach and coverage name different references on {uptime['name']}")
            print(
                f"  player {index} {uptime['name']} [{verdict}]: coverage "
                f"overall {pct(uptime['ours'])} vs {pct(uptime['their_median'])}, "
                f"trash {pct(row['trash']['ours'])} vs {pct(row['trash']['their_median'])}, "
                f"bosses {pct(row['bosses']['ours'])} vs {pct(row['bosses']['their_median'])}; "
                f"reach overall {pct(row['reach']['overall']['ours'])} vs "
                f"{pct(row['reach']['overall']['their_median'])}, "
                f"trash {pct(row['reach']['trash']['ours'])} vs "
                f"{pct(row['reach']['trash']['their_median'])}"
            )
    for label, count in sorted(counts.items()):
        print(f"  {label}: {count}")
    for label, values in medians.items():
        if values:
            print(
                f"  reference {label} medians, Overall: min {min(values):.2%}, "
                f"median {statistics.median(values):.2%}, max {max(values):.2%}, "
                f"{sum(1 for value in values if value >= 0.99)} of {len(values)} at 99% or more"
            )
print("defects:", defects)
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run python /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/live_states.py ../../../out/uptime > /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/live_states.out
```

- [ ] **Step 4: Survey the cache offline**

Write `<scratchpad>\survey_key.py`:

```python
"""Task 10 of the key uptime plan: the blind spot and the coverage bound over every cached key.

Offline only: cached pages are read through trash_common, which never constructs DiskCache and
never fetches. Every cached keystone fight's route is checked for the boss pulls Warcraft Logs
lists twice: the buff windows must keep the spans the debuff windows keep. Every player of each
fight with both debuff streams is read through the domain's own key_debuffs, and the paired
intervals that outlive a death of their own enemy copy are counted. Prints a report code's
first four characters, counts and ability ids; never a player's name.
"""

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from trash_common import STREAMS, actors_of, scanned_reports, stream  # noqa: E402

from wowperf.adapters.wcl.ingest import build_debuff_log, build_run  # noqa: E402
from wowperf.domain.comparison.boss_debuffs import (  # noqa: E402
    boss_pulls_listed_once,
    boss_windows_of,
)
from wowperf.domain.comparison.key_debuffs import key_debuffs  # noqa: E402
from wowperf.domain.comparison.uptime import boss_windows  # noqa: E402
from wowperf.domain.debuffs import pair_debuffs  # noqa: E402

totals = Counter()
defects = 0
for code, (report, tier) in sorted(scanned_reports().items()):
    actors = actors_of(code)
    if actors is None:
        continue
    for fight in report["fights"]:
        if fight.get("keystoneLevel") is None or not fight.get("dungeonPulls"):
            continue
        try:
            run = build_run(report, fight)
        except Exception as error:  # a payload cached under an older query text
            print(f"{code[:4]} f{fight['id']}: no run ({type(error).__name__})")
            continue
        events = stream(STREAMS["EnemyDebuffs"], code, fight)
        deaths = stream(STREAMS["EnemyDeaths"], code, fight)
        end_ms = int(fight["endTime"])

        # The route check reads no stream: a window's span is its pull's, whatever
        # died in it, so a fight without the debuff streams is checked too.
        routed = build_debuff_log([], actors, {}, end_ms, death_events=[])
        listed = sum(1 for pull in run.pulls if pull.is_boss)
        dropped = listed - len(boss_pulls_listed_once(run.pulls))
        totals["keystone fights routed"] += 1
        totals["boss pulls listed twice, dropped"] += dropped
        totals["fights with a boss pull listed twice"] += dropped > 0
        debuff_spans = tuple(
            (window.start_ms, window.end_ms)
            for window in boss_windows_of(run.pulls, routed.npc_actors, routed.deaths)
        )
        if boss_windows(run.pulls) != debuff_spans:
            defects += 1
            print(f"  DEFECT {code[:4]} f{fight['id']}: buff and debuff boss windows differ")

        if events is None or deaths is None:
            continue
        log = build_debuff_log(events, actors, {}, end_ms, death_events=deaths)

        game_of = dict(log.game_ids)
        died: dict[tuple[int, int], list[int]] = defaultdict(list)
        for row in log.death_rows:
            if row.target_id in game_of:
                died[(game_of[row.target_id], row.target_instance)].append(row.timestamp_ms)
        intervals, _ = pair_debuffs(log)
        for one in intervals:
            totals["paired intervals"] += 1
            times = sorted(died.get((one.target_game_id, one.target_instance), ()))
            inside = [at for at in times if one.start_ms < at < one.end_ms]
            if inside:
                totals["intervals outliving a death of their copy"] += 1
                totals["of those, reaching a later death of it"] += any(
                    at > inside[0] for at in times if at <= one.end_ms
                )

        players = frozenset(player.actor_id for player in run.players)
        if not players:
            continue
        first = key_debuffs(log, run.pulls, min(players), players)
        totals["fights"] += 1
        totals["trash lives"] += first.trash.lives
        totals["add lives"] += first.adds.lives
        totals["undebuffed deaths"] += first.undebuffed_deaths
        totals["no death, left out"] += first.unmeasured_no_death
        print(
            f"{code[:4]} f{fight['id']} ({tier}): trash {first.trash.lives}, "
            f"adds {first.adds.lives}, undebuffed {first.undebuffed_deaths}, "
            f"no death {first.unmeasured_no_death}"
        )
        for actor_id in sorted(players):
            mine = key_debuffs(log, run.pulls, actor_id, players)
            for label, cover in (
                ("overall", mine.overall),
                ("bosses", mine.on_bosses),
                ("trash", mine.trash),
                ("adds", mine.adds),
            ):
                for ability_id, ms in cover.covered:
                    if ms > cover.alive_ms:
                        defects += 1
                        print(f"  DEFECT {label} coverage above 100%: ability {ability_id}")
                for ability_id, count in cover.reached:
                    if count > cover.lives:
                        defects += 1
                        print(f"  DEFECT {label} reach above 100%: ability {ability_id}")
measured = totals["trash lives"] + totals["add lives"]
print(dict(totals))
if measured:
    share = totals["undebuffed deaths"] / measured
    print(f"undebuffed share of trash and add lives: {share:.1%}")
print("defects:", defects)
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run python /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/survey_key.py > /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/survey_key.out
```

- [ ] **Step 5: Run the end-to-end tests the feature touched**

```bash
set -a && . <(iconv -f UTF-16 -t UTF-8 ../../../.env | tr -d '\r') 2>/dev/null && set +a; export PATH="$HOME/.local/bin:$PATH"; WOWPERF_E2E_REPORT="https://www.warcraftlogs.com/reports/LyKXYvVZm192TDr6?fight=9" uv run pytest -m e2e tests/e2e/test_boss_debuffs_e2e.py tests/e2e/test_uptime_e2e.py -q
```

Both must pass.

Then run `tests/e2e/test_compare_e2e.py` the same way, if it fits this task's budget. Task 7 rewrote part of it, so it should not ship without a run. It loads every reference cold, so run it only if Step 2's second command reported more than 1,500 points remaining. Its own cost has not been measured, so record what it spent.

If it is not run, the live amendment of Step 7 records it as a known gap: Task 7's edit to that test shipped without a live run, with the remaining quota as the reason. Say so in the report too.

- [ ] **Step 6: Judge**

Stop and report, without committing, if any of these holds:
- `live_states.out` or `survey_key.out` prints `defects:` above 0. That means a coverage or reach above 100%, a reach row whose references differ in number from its coverage row's, or a fight whose buff boss windows differ from its debuff boss windows;
- any `UNEXPECTED` finding family appears;
- any id `compare.uptime.boss` appears in either findings file.

Each of these must have occurred, on the two keys together:
- **Buffs:** the verdict `level`; the Without bosses and Bosses cells `measured`.
- **Debuffs:** the verdicts `level` and `unjudged`, and the shared state; the Trash, Bosses and per-boss cells `measured`.
- **Reach:** every one of its three stretches `measured`.
- **Counts:** `unmeasured_no_death` and `undebuffed_deaths` reported for every player. On the spike's evidence they should be near 29 and 10 on our two keys together, so a zero on both keys is a defect to chase.

Every other reachable state must be accounted for, whether it occurred or not:
- the buff verdicts `below` and `unjudged`;
- the debuff verdict `below`;
- the gap findings of each family;
- each `unavailable` finding;
- the cell states `no trash measured`, `no boss found`, `no reference measured it` and `too few references`.

For each one that never occurred, find in the data why not, as the parent design's live amendment did for its three. A state that never occurs is a defect to chase, not a quiet success.

From `live_states.out`, read how far the references' Overall coverage and reach medians sit below 100%. From `survey_key.out`, read the blind spot: the undebuffed share of trash and add lives, against the 2.7 to 3.7% that §3.1 measured.

Read the cost breakdowns from Step 2. The feature adds no query, so every operation should be one the 2026-10-08 live runs already listed: `EnemyDebuffs`, `EnemyDeaths`, `Actors`, and the reference loads. A new operation name is a finding to report.

- [ ] **Step 7: Record and commit**

1. Append to this design, after §8, a dated amendment `*Amended <the date the runs were made>, live:*`. It records:
   - the state counts from `live_states.out`, both keys;
   - for every state that never occurred, why;
   - coverage and reach on both sides, with the four debuffs whose Overall gap is widest, ours against the median;
   - how far the references' Overall medians sit below 100%;
   - the survey's totals: fights, trash and add lives, undebuffed deaths and their share, enemies with no death, and defects;
   - the route check:
     - keystone fights routed;
     - fights with a boss pull listed twice, and the pulls dropped (the 2026-10-08 reading was 10 in 5 of 969 fights);
     - that the buff and debuff boss windows agreed on every fight.

     The buff Bosses figure itself was not read on a fight with a duplicated pull: no cached `AuraTable` response covers one. State that it stays unproven live, and raise it with RwlRwlRwlRwl when reporting this task;
   - the paired intervals that outlive a death of their own copy, and how many of those reach a later death of it (2026-10-13: 1,801 and 11 of 156,175);
   - whether `tests/e2e/test_compare_e2e.py` ran and what it spent, or, if it did not, that it is a known gap (Step 5);
   - each command's cost, operation by operation, and whether any operation was new.

   It names players by class and spec only, never by name.
2. If an operation was new, or a per-call cost of `EnemyDebuffs`, `EnemyDeaths` or `Actors` sat outside the range the wcl-api skill records, add a dated paragraph to the skill's section "The debuff event stream does name the caster" with the reading. Otherwise leave the skill alone, and say so in the design's amendment.

Write `<scratchpad>\task10-msg.txt`:

```text
Record uptime over the whole key on two live keys

The design priced the feature at no new query and named the states it
can reach; this is the feature's own reading of both, and of the cached
keys' blind spot and coverage bound.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
/mingw64/bin/git add docs/plans/2026-10-13-key-uptime-coverage-design.md
```

If the wcl-api skill changed, add it as well:

```bash
/mingw64/bin/git add .claude/skills/wcl-api/SKILL.md
```

```bash
/mingw64/bin/git commit -F /c/Users/damien/AppData/Local/Temp/claude/C--Users-damien-claude-perso-wow-perf--claude-worktrees-suspicious-heisenberg-5a6da7/d8ccc848-7597-4c52-b0ac-84b521f1c3b0/scratchpad/task10-msg.txt
```

---

## Spec coverage

| Spec | Task |
| --- | --- |
| §1, §2 decisions 1-2: both families, buffs over the key clock | 7, 8 |
| §2 decision 3, §3.2 items 4 and 6: coverage over every enemy's life, the shared rule per life | 4 |
| §2 decisions 4-5: reach beside coverage; Overall carries the verdict | 4, 5, 8 |
| §2 decision 6, §3.1: a trash life opens at the first debuff | 1 (re-measured), 3 |
| §2 decision 7: no death left out and counted; undebuffed deaths counted | 3, 5, 8 |
| §2 decision 8, §3.2 item 3: adds in Overall only | 3, 4 |
| §2 decision 9, §4: the reach table, the note, the warning | 8 |
| §3.2 item 1: lives, instances, two actor ids, removals, player pets | 2, 3 |
| §3.2 item 2: boss figures unmoved | 4 (all of `test_boss_debuffs.py` through `key_debuffs`, and `test_the_boss_figure_is_the_boss_rule_whatever_died_beside_it`) |
| §3.2 item 7: thresholds reused | 5, 7 (`uptime_measures`, `stretch_cell`) |
| §3.3: buff windows on both sides; the reference's clock at 0 points | 6, 7 |
| §3.3 amendment: a boss pull listed twice is one buff window, by the debuff rule, in one shared helper; cast rates and the raid path untouched | 7 (`boss_pulls_listed_once`; `test_a_boss_pull_warcraft_logs_lists_twice_is_one_window`, `test_a_boss_pull_listed_twice_counts_once_in_the_bosses_cell`, `test_a_boss_pull_listed_twice_is_kept_once_at_its_own_position`; every `boss_windows_of` test unchanged; Step 9's `grep -rn "boss_windows(" src`) |
| §4 amendment: Range and Sample of the Overall figure on all three tables, reach included | 5 (`DebuffReach.overall_fractions`, `carried_shares`, `test_reach_keeps_the_references_overall_reach_not_their_coverage`), 8 (the column order, and Range and Sample read off Overall in `test_the_debuff_tables_follow_the_buff_table_with_a_column_per_stretch_and_boss`, `test_the_buff_table_reads_overall_its_range_and_sample_then_each_stretch` and `test_the_reach_table_follows_the_coverage_table_and_judges_nothing`) |
| §4 findings: buff ids kept, debuff ids renamed, badges unchanged, the two counts in the file | 5 (the counts read back from a written findings file in `test_a_compared_run_reads_both_sides_debuffs_on_the_boss`), 7 |
| §5 components | 3, 4, 5, 6, 7, 8 |
| §6 edge cases: no trash; two actor ids; a debuff across a death; a boss pull listed twice | 5; 3; 4 (`test_a_debuff_reaching_past_a_death_is_clipped_to_the_life`, `test_a_debuff_outliving_its_copys_death_counts_on_the_next_life_it_overlaps`); 4 (`boss_windows_of` unchanged) and 7 (the buff windows, by the same rule) |
| §7 tests | 2-8 |
| §7 the plan's first step | 1 |
| §7 live proof, §8 cost | 10 (with the route check of boss pulls listed twice, the count of intervals outliving their copy's death, the reach and coverage reference check, and `test_compare_e2e` run or recorded as a known gap) |
| §9 documentation | 9, 10 |
| §10 out of scope | untouched: the raid path keeps its rule through `whole_fight_uptime` and the defaults of `our_fight_ms` and `over`; cast rates keep `spells.boss_seconds`, which still sums a boss pull listed twice twice, for the separate task §10 names |
