# One report, every pull: the `night` command

**Status:** approved design, every open question settled, not yet planned or built. The next
step is `superpowers:writing-plans`.
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

**Settled 2026-09-23: one boss `<select>`, and one pull `<select>` per boss.** Choosing a boss
shows that boss's own pull control and hides the others. The alternative — a single pull
control holding every pull, with options hidden or disabled as the boss changes — asks the
script to manipulate `<option>` elements, which browsers handle inconsistently and which sits
closer to the line the invariant draws than showing and hiding a whole element does. Per-boss
controls keep the script to exactly what it is allowed to do: show, hide, highlight. Their
arrangement on the page is still the plan's to decide against a rendered fixture; the mechanism
is not.

## 4. The command

```
wowperf night <url> [--deep FIGHT]... [--no-deaths] [--difficulty N] [--cache-dir DIR] [--out DIR]
```

A fourth sibling of `analyze`, `raid` and `progression`, not a mode of any of them.

- **no `--fight`** — it covers every fight in the report; that is the point.
- **`--deep FIGHT`**, repeatable — promote these pulls to full death anatomies (§7).
- **`--no-deaths`** — drop death cards entirely, reaching §6's cheapest tier. Named for
  `--no-compare`, which it matches in shape: both switch off a whole family of work rather
  than tuning it. Without it §6's first row is priced but unreachable, and every night run
  pays for `AuraTable` whether or not the reader wants anatomy. `--deep` and `--no-deaths`
  together is a contradiction and must be refused, naming both.
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

**Settled 2026-09-23.** The finding is `compare.parse.not_drawn`, `measured`, drawn **once for
the whole page** rather than per player.

Measured, because the absence is a fact about what this command fetched, not a reading of
anything — the same reasoning `attempt_shape.py` records for modelling itself on
`compare.parse.unavailable`.

Once, because `compare.parse.unavailable` is per player: on report `cW38jmwdnZfbHVL4`, twenty
players across nineteen fights would draw it several hundred times to say one thing. A reader
learns that the axis is absent once and needs it to stay learned.

It must not reuse `UNAVAILABLE_ID` or `WITHHELD_DETAIL` from
`src/wowperf/domain/comparison/parse_axis.py`. That detail opens "This attempt did not kill the
boss", which is a true sentence about a wipe and a false explanation here — a night page omits
the axis on kills too, and for an entirely different reason. Borrowing it would put a wrong
cause in front of a reader, which is the failure this whole section exists to prevent.

What it must say: that `wowperf night` does not draw the parse axis at all; which families are
therefore absent — damage against the board, damage by target, casts a minute, talents, buff
uptime, the percentile — named in one place rather than left as six silences, exactly as
`WITHHELD_DETAIL` names them; and that `wowperf raid --fight N` is the command that draws them
for a single pull. The exact prose is the plan's to write against that list.

## 6. Cost, measured

Every figure below is extrapolated across twenty pulls from one measured breakdown — report
`Kw1fCtq4VJ7W8rQA` fight 26, 2026-09-23, recorded in `.claude/skills/wcl-api/SKILL.md`. It is
arithmetic over one reading, not twenty readings, and the plan should re-measure once the
command exists.

That breakdown showed `Healing` at 22 calls, one per death, and `AuraTable` at 20 calls, one per
roster player — together 42 of the run's 65.19 points. Those two queries exist **only** to build
death recaps, and they split along the tiers in §7:

| per pull | reached by | points/pull | 20 pulls |
| --- | --- | --- | --- |
| no death cards | `--no-deaths` | ~2 | ~40 |
| trimmed cards — needs `AuraTable` | the default | ~22 | ~440 |
| full cards — needs `AuraTable` and `Healing` | `--deep FIGHT` | ~44 | ~880 |

Every tier is reachable from the command line. A tier priced in a design and unreachable from
the CLI is a measurement nobody can act on.

A deepened `progression` pass already fetches `Fights`, `Actors`, `Deaths`, `DamageTaken`,
`PlayerDetails` and `Abilities` for every attempt, at roughly 2 points an attempt. The night
command does that work anyway, so those streams are not a marginal cost here.

**Decision: trimmed cards are on by default.** About 440 points, an eighth of the hourly budget,
for the tab most readers open first. `--deep` buys the rest per pull.

### 6.1 Amendment: measured on the command itself, 2026-09-24

The table above is arithmetic over one `raid` reading; this is the first reading of `wowperf
night`. Both figures moved **up**, and the no-death-card row moved a long way. Report
`cW38jmwdnZfbHVL4`, 8 bosses, 16 drawn pulls, 20 raiders; full breakdowns in
`.claude/skills/wcl-api/SKILL.md`.

| per pull | projected above | measured 2026-09-24 |
| --- | --- | --- |
| no death cards | ~2 | **6.6 to 7.4** (106.01 and 118.17 over 16 pulls, cold, two runs) |
| trimmed cards | ~22 | **18.8 or more** (300.34 over 16 pulls, on a partly warm cache) |

**The ~2 was the marginal cost, not the price.** It came from the paragraph below the table --
a deepened `progression` pass fetches its streams anyway, so they are not a marginal cost here.
They are not marginal to a reader with an empty cache, though, and `load_night_attempts` fetches
six streams a pull at every tier: deaths, damage taken, enemy casts, interrupts, resurrections
and the damage graph. Three of those six a `progression` pass never fetches at all. So the
cheapest tier is nearly four times what this table projected, and a twenty-pull night with no
cards is nearer 150 points than 40.

**The trimmed row is a floor rather than a reading.** 300.34 was measured against a cache that
earlier `raid` and `progression` runs on the same report had partly filled -- 239 aura tables
fetched of the 320 the tier needs, no `Fights` or `DamageTaken` call at all. A cold run costs
more, by an amount nobody has measured. What the reading does settle is the shape the table got
right: `AuraTable` is the whole difference between the two tiers, at one call per raider per
pull, and it is 239 of the 300.

The **decision** above stands. The default tier is dearer than projected, and still the tier
worth defaulting to: what the aura tables buy is `held` and `faded` against a bare `pressed`,
and the first live run drew 21 and 14 of them across 186 death cards.

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
not new markup**.

**Settled 2026-09-23: the trimmed card needs its own note, and must not reuse the existing
one.** `NO_TIMELINE_EVENT` in `src/wowperf/domain/report/deaths.py:107` reads "No event in the
last seconds." That is a claim about the log: nothing happened. A trimmed card's timeline is
absent because this command chose not to build it, which is a claim about the run. The two
look identical on the page and mean opposite things, and a reader who takes the trimmed note
for the existing one concludes the pull was quiet when it may have been carnage.

So: a second constant beside it, naming `--deep <fight>` as what renders the timeline. Same
`timeline_note` field, same `{% elif death.timeline_note %}` branch in `_deaths.html.j2:91` —
no new markup, as above. The exact prose is the plan's.

This is the same mistake as reusing `WITHHELD_DETAIL` in §5, in a second place, and both were
found by asking the same question: what does the absence actually mean here, and does the
sentence already on the shelf say that?

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
   cards trimmed unless `--deep` names that pull, or absent entirely under `--no-deaths`;
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
- `--deep` and `--no-deaths` together fails naming both, rather than letting one silently win.
  They are a contradiction: one asks for a fuller death card on a named pull, the other for no
  death cards at all.
- A single pull failing to deepen shrinks the night rather than failing it, and the Provenance
  section names it with the reason — the same rule the comparison already follows for a reference
  that would not load.

## 11. Testing

- **Builder tests**, pure, one per decision: which pulls trim, which deepen, which drop their
  cards under `--no-deaths`, what the absent-axis disclosure says, how a failed pull is
  represented. Each of the three tiers gets a test that fails if a pull lands in the wrong one —
  a tier is a cost decision, and a page that quietly renders the dearest one is a page that
  quietly spends eight hundred points.
- **`test_html_invariants.py` extended** to the night page: one script, one icon host, no
  stylesheet link, no `@import`.
- **A size-budget regression test.** Size is a design constraint now, so it gets a test: a
  fixture night renders under a stated byte budget. Without one, a future card gains a field and
  nobody notices until a 20 MB file lands.
- **e2e. Settled 2026-09-23: `cW38jmwdnZfbHVL4`, the whole report.** It is the raid and
  progression suites' report already, and `tests/e2e/test_progression_e2e.py`'s header records
  from a verified live read what it holds — eight bosses, nineteen boss fights, and which of
  them is the eight-attempt no-kill night. A second report would mean a second roster of real
  people to document under the test-data rule, and a cold cache on every run.
  `WOWPERF_E2E_RAID_KILL` and `WOWPERF_E2E_RAID_WIPE` stay exactly as they are: a night run
  reads fights 2 and 30 along with the rest, which is not the same as repointing them, and the
  plan must not repoint them.
  **It runs with `--no-deaths`.** At the trimmed default, nineteen fights cost roughly 420
  points — an eighth of the hourly budget for one test run, which is the kind of price that
  gets a suite quietly stopped from running. The cheap tier exercises the container, the
  dropdowns, the per-boss grouping and the absent-axis disclosure, which is what this e2e is
  for; death-card tiers are already covered by `raid`'s own e2e.
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

## 14. The questions this design left open, and how they were settled

All four were settled with RwlRwlRwlRwl on 2026-09-23, against the code rather than from
memory. Each is written into the section that owns it; they are listed here so a reader can see
what was decided and what was deliberately left to the plan.

1. **The absent-parse-axis disclosure (§5).** `compare.parse.not_drawn`, `measured`, once for
   the page. Must not reuse `WITHHELD_DETAIL`, whose stated cause is false here. Prose is the
   plan's.
2. **The absent-timeline note on a trimmed card (§7).** A second constant beside
   `NO_TIMELINE_EVENT`, naming `--deep`. Must not reuse `NO_TIMELINE_EVENT`, for the same
   reason as (1). Prose is the plan's.
3. **The e2e report (§11).** `cW38jmwdnZfbHVL4`, the whole report, run with `--no-deaths`.
   The two pinned env vars are read, never repointed.
4. **The dropdown mechanism (§3).** One boss `<select>`, one pull `<select>` per boss, shown
   and hidden. Their arrangement on the page stays a question for a rendered fixture.

A fifth question surfaced while settling these and is recorded in §4 and §6: the design priced
a "no death cards" tier that no flag could reach. `--no-deaths` now reaches it, and the e2e is
its first caller.

**Still deliberately open, for the plan rather than for this design:** the exact prose of the
two findings above, and the page arrangement in (4). Settling wording here would be writing the
plan; settling layout here would be describing a page nobody has rendered.

## 15. What this rests on

Measured 2026-09-23 against report `Kw1fCtq4VJ7W8rQA`, a Mythic 20-player night of three bosses
across twenty fights, and recorded with its conditions in `.claude/skills/wcl-api/SKILL.md`:

- `raid --all-players` on fight 26, a wipe, cost **65.19 points**, of which `Healing` was 22.00
  and `AuraTable` 20.00.
- Deepened `progression` cost **26.30, 8.59 and 13.85 points** for 12, 2 and 5 attempts.
- That page is **2,234 KB**, of which the Deaths tab is 2,099 KB — 94%.
- A death card is 77 KB, and 5.8 KB without its timeline table, health curve and tooltips.
