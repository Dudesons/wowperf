# One report, every pull: the `night` command

**Status:** approved design, not yet planned or built.
**Slice:** the first of two. This document is spec A — the container. Spec B, the cross-pull
analysers, is deliberately out of scope here and is named in §12.

## 1. Goal

`wowperf night <url>` takes a Warcraft Logs report link and writes **one HTML file covering
every boss and every pull in it**, navigable by two dropdowns, without fetching anything after
the page is opened.

## 2. Why this exists, and what already exists

Half of the request is already built and was not obvious. `progression` **is** analysis across
all pulls at one boss: it reports the median and range of boss health, the movement between the
two halves of the night, who died first most often, how fast attempts collapse, and the best
attempt's death count. It even names the deepest attempt's fight id and tells the reader to run
`wowperf raid --fight N`.

What is missing is not the analysis. It is that

- the pointer to a pull's anatomy is **prose telling you to type a command**, not something you
  click;
- `--boss` is required, so a report holding three bosses produces three unrelated pages; and
- nothing reads across pulls (spec B).

This spec closes the first two.

## 3. Constraint: the report invariant holds unchanged

One HTML file, no stylesheet link, no `@import`, no remote `src` but the icon host, exactly one
inline script, and **that script may show, hide and highlight what is already on the page — it
may not fetch**. `tests/adapters/render/test_html_invariants.py` enforces both halves.

The dropdowns are therefore `<select>` elements driving CSS visibility over content that is
already present. Nothing loads on demand. This is why §6 and §7 exist: if everything must be
pre-rendered, size becomes a first-class design constraint rather than an accident.

## 4. The command

```
wowperf night <url> [--deep FIGHT]... [--difficulty N] [--cache-dir DIR] [--out DIR]
```

A fourth sibling of `analyze`, `raid` and `progression`, not a mode of any of them.

- **no `--fight`** — it covers every fight in the report; that is the point.
- **`--deep FIGHT`**, repeatable — promote these pulls to full death anatomies (§7).
- **`--difficulty N`** — as `progression` takes it, defaulting per boss to that boss's own first
  fight in the report.
- **`--cache-dir` / `--out`** — as the other three take them.

Not offered, each for a stated reason:

- **`--player` / `--all-players`** — layer 1 draws no parse axis at all (§5), so there is no
  per-player reference sample for them to widen. Adding them would offer a knob that changes
  nothing.
- **`--no-compare`** — the only comparison drawn is the mechanics axis, which is per-encounter
  and cheap; there is no expensive half to switch off.
- **`--narrative`** — as `raid` and `progression` do not take it, and for the same reason.

Outputs `<code>.night.json` and `<code>.night.html` under `--out`.

`raid`'s existing refusal — `This report holds several boss fights ({ids}); pass --fight` —
gains a sentence pointing at `wowperf night`, so pasting a bare report URL still teaches the
right command at the cost of the refusal, which is a few points.

## 5. Layer 1 draws no parse axis

The per-player leaderboard sample is the expensive half of `raid`: it is what separates the
877.74-point kill reading from the 65.19-point wipe reading, both recorded in
`.claude/skills/wcl-api/SKILL.md`. Drawn once per player **per boss**, across a whole report, it
would dominate everything else by an order of magnitude.

So the night page draws **no parse axis**. The mechanics axis stays: it is per-encounter, drawn
once for the whole boss, and cost about 15 points on fight 26.

Consequence for the page: every parse-fed family — damage against the board, damage by target,
casts a minute, talents, buff uptime, the percentile — is absent from a night page, and must be
**disclosed rather than silently missing**. The existing `compare.parse.unavailable.<slug>`
finding says "This attempt did not kill the boss", which is the wrong reason here and must not
be reused with a false explanation. A new disclosure finding is needed, stating that this
command does not draw the axis and naming `wowperf raid --fight N` as what does.

**Open item for the plan:** the id and wording of that finding. Do not invent it here.

## 6. Cost, measured

Every figure below is extrapolated across twenty pulls from one measured breakdown — report
`Kw1fCtq4VJ7W8rQA` fight 26, 2026-09-23, recorded in `.claude/skills/wcl-api/SKILL.md`. It is
arithmetic over one reading, not twenty readings, and the plan should re-measure once the
command exists.

That breakdown showed `Healing` at 22 calls, one per death, and `AuraTable` at 20 calls, one per
roster player — together 42 of the run's 65.19 points. Those two queries exist **only** to build
death recaps, and they split along the tiers in §7:

| per pull | points/pull | 20 pulls |
| --- | --- | --- |
| no death cards | ~2 | ~40 |
| trimmed cards — needs `AuraTable` | ~22 | ~440 |
| full cards — needs `AuraTable` and `Healing` | ~44 | ~880 |

A deepened `progression` pass already fetches `Fights`, `Actors`, `Deaths`, `DamageTaken`,
`PlayerDetails` and `Abilities` for every attempt, at roughly 2 points an attempt. The night
command does that work anyway, so those streams are not a marginal cost here.

**Decision: trimmed cards are on by default.** About 440 points, an eighth of the hourly budget,
for the tab most readers open first. `--deep` buys the rest per pull.

## 7. Death cards, and the one element that does not scale

Measured on fight 26's page, a death card is **77 KB**. Stripped:

| card | size |
| --- | --- |
| full | 77 KB |
| minus hover tooltips | 70 KB |
| minus tooltips and the health-curve SVG | 58 KB |
| **minus the timeline table as well** | **5.8 KB** |

The per-death **timeline table** — 93 rows of the last ten seconds, one per event, each with its
own hover panel — is ~52 KB of every card and 94% of that page's 2,234 KB. Twenty pulls of full
cards is roughly 23 MB. Twenty pulls of trimmed cards is roughly 1.7 MB.

A **trimmed card** keeps the killing blow, the time, the class, the six availability states, the
consumable lines and the return line. It drops `timeline` and `health_curve`. Both are already
guarded in `_deaths.html.j2` by `{% if death.timeline %}` and `{% if death.health_curve %}`, and
`timeline_note` exists for the absent case — so a trimmed card should be a **builder decision,
not new markup**. The plan must confirm that the absent-timeline path renders a sensible note
rather than an empty block, and say what that note is.

A **deep card** is what `raid` renders today, unchanged, for pulls named by `--deep`.

Trimmed cards still need `AuraTable`: `held` and `faded` are refined by whether the ability's
aura was still up when the killing blow landed, and without that refinement every press collapses
to `pressed`, the explicit unknown. Dropping the aura fetch would quietly destroy the six-state
distinction that `docs/plans/2026-09-22-raid-defensive-ceiling-design.md` exists to protect.

**Page budget:** roughly 74 KB a pull for everything that is not deaths, plus ~6 KB a death, plus
35 KB of CSS once. A twenty-pull night lands near 3 MB — about what one raid page costs today.

## 8. Architecture

Four new files, following the quartet `raid_*` and `progression_*` each already have:

- `src/wowperf/domain/report/night_model.py` — the frozen view model
- `src/wowperf/domain/report/night_frame.py` — the frame
- `src/wowperf/domain/report/night_build.py` — the pure builder
- `src/wowperf/adapters/render/night.html.j2` — one template, deciding nothing

plus `render_night` in `src/wowperf/adapters/render/html.py` and a `night` command in
`src/wowperf/cli.py`.

**The reuse is structural, not incidental.** `LoadedProgression.loaded` is a
`tuple[LoadedEncounter, ...]`, and `LoadedEncounter` is exactly `build_raid_report`'s first
argument. The night command is therefore:

1. read the report's fights once, and its bosses;
2. for each boss, run the existing progression path — deepening every attempt;
3. for each loaded attempt, run the existing raid builder, with the parse axis off and death
   cards trimmed unless `--deep` names it;
4. assemble the per-boss and per-pull view models into one night view model;
5. render once.

No analyser is duplicated. If a step needs a new analyser, that is a signal it belongs in spec B.

## 9. The findings JSON

`<code>.night.json` carries the report metadata, a list of bosses with their progression
findings, and a list of pulls each carrying that pull's findings — the same finding shape the
other three commands write, so anything that reads a findings file keeps working. Every finding
keeps its `confidence` badge; a finding without one is a bug, here as everywhere.

The digit ban and the narrative rules do not apply — this command writes no narrative.

## 10. Errors

- A report with no boss fights at all fails with a message saying so, as `progression` does.
- `--deep` naming a fight id not in the report fails naming the ids that are, matching the shape
  of `raid`'s existing refusal.
- A single pull failing to deepen shrinks the night rather than failing it, and the Provenance
  section names it with the reason — the same rule the comparison already follows for a reference
  that would not load.

## 11. Testing

- **Builder tests**, pure, one per decision: which pulls trim, which deepen, what the absent-axis
  disclosure says, how a failed pull is represented.
- **`test_html_invariants.py` extended** to the night page: one script, one icon host, no
  stylesheet link, no `@import`.
- **A size-budget regression test.** Size is a design constraint now, so it gets a test: a
  fixture night renders under a stated byte budget. Without one, a future card gains a field and
  nobody notices until a 20 MB file lands.
- **e2e.** `cW38jmwdnZfbHVL4` fights 2 and 30 are pinned as `WOWPERF_E2E_RAID_KILL` and
  `WOWPERF_E2E_RAID_WIPE` and are depended on by unrelated tests; a whole-report run touches
  every fight in that log. The plan must decide whether the night e2e uses that report or another,
  and must not repoint those two variables.
- **A live run before this is called done.** A new judgement is not done until a live run has
  exercised it: report how often each state and each tier actually occurred, on a real report.

## 12. Out of scope

- **The three cross-pull analyser families — spec B.** What keeps killing us across a boss's
  pulls; who keeps dying and with what available; whether the raid is improving. They need this
  container to display them, and they are new domain work rather than reuse.
- Any parse-axis comparison (§5).
- Any narrative.
- Any claim that one raider's action caused another's death, which remains unbuilt and undesigned
  across the whole project.

## 13. Naming, and one reword it costs

`night` completes the scope ladder the other commands imply: `raid` is one pull, `progression` is
one boss's pulls, `night` is the whole report.

`report` was rejected: the domain package is `domain/report/`, the builders are `build_report`
and `build_raid_report`, the view models are `Report` and `RaidReport`, and Warcraft Logs calls
the input a report code. `overview` was rejected as naming the artifact rather than the subject,
which breaks the convention the other three follow.

The cost is that `progression` is currently described as covering "a whole night of attempts at
one boss" in `CLAUDE.md`, `README.md` and `.claude/skills/analyzing-a-run/SKILL.md`. Those
sentences must say **every attempt at one boss**, which is both more precise and free of the
collision. Note that `.claude/skills/` prose is CI-tested by `tests/test_skills.py`, which reads
each section's flags against that command's real `--help`; a new command means a new section and
a new entry in that test's expectations.

## 14. Open questions for the plan

1. The id and wording of the absent-parse-axis disclosure finding (§5).
2. What the absent-timeline note on a trimmed card says (§7).
3. Which report the e2e runs against (§11).
4. Whether the boss and pull dropdowns are two independent `<select>`s or one nested control —
   a page-shape question better answered against a rendered fixture than in prose.

## 15. What this rests on

Measured 2026-09-23 against report `Kw1fCtq4VJ7W8rQA`, a Mythic 20-player night of three bosses
across twenty fights, and recorded with its conditions in `.claude/skills/wcl-api/SKILL.md`:

- `raid --all-players` on fight 26, a wipe, cost **65.19 points**, of which `Healing` was 22.00
  and `AuraTable` 20.00.
- Deepened `progression` cost **26.30, 8.59 and 13.85 points** for 12, 2 and 5 attempts.
- That page is **2,234 KB**, of which the Deaths tab is 2,099 KB — 94%.
- A death card is 77 KB, and 5.8 KB without its timeline table, health curve and tooltips.
