# The report's user interface — decision brief and parity inventory

**This document is input to a brainstorm; it decides nothing, approves nothing, and designs no new
UI.** It exists so the brainstorm starts from an honest account of what the report already is,
rather than from memory.

**Status:** written 2026-09-08 by an agent asked to survey, not to build. No code was written and
nothing under `src/` or `tests/` was touched.

**The proposal it responds to.** RwlRwlRwlRwl wants the report easier to read and better looking: a
real timeline widget, spell and talent icons, hover for detail. He is willing to accept a
standalone React + Vite app to reach better libraries. The starting sketch — which the brainstorm
should argue with rather than accept — is that `analyze` writes the view model as
`<code>-<fight>.report.json`, and a prebuilt single-file React bundle takes that JSON inlined at
analysis time, leaving the domain layer untouched.

**A note on icons.** A separate agent is running a live spike on whether spell icons and tooltip
text can be baked into a self-contained file, and at what size cost. Nothing here investigates
that. Where it bears on a decision the text says *pending the icon spike* and says how the
recommendation moves in each direction.

**Sources.** `src/wowperf/domain/report/model.py`, `src/wowperf/domain/report/build.py`,
`src/wowperf/adapters/render/report.html.j2`, `src/wowperf/adapters/render/html.py`, the three test
modules and the golden file under `tests/adapters/render/`, the report sections of
`docs/plans/2026-09-03-mplus-postmortem-design.md`, `2026-09-05-mplus-report-design.md`,
`2026-09-06-report-tabs-design.md`, `2026-09-06-audit-and-improvement-roadmap.md`, and the real
report at `out/6Kx1P9GbNXrcLdHa-36.html`. Every count below was read off disk, not remembered.

---

## Part One — the parity inventory

### 1.0 The shape of the thing, in numbers

| Measured | Value |
| --- | --- |
| `report.html.j2` | 437 lines, 18,158 bytes |
| Branch points in the template | 33 (29 `{% if %}`, 2 `{% elif %}`, 2 `{% else %}`) |
| Loops in the template | 20 |
| Macros in the template | 2 (`ledger_row`, `pointer`) |
| CSS rule blocks in the inline stylesheet | 62, over 88 lines |
| CSS custom properties | 27 (13 class colours + unknown, 3 badge tints, 4 chart tints, ink/page/card/line) |
| Inline script | 57 lines, 4 functions, 3 event wirings |
| `model.py` | 230 lines, 14 frozen models + 1 enum, 88 declared fields |
| `build.py` | 812 lines — every judgement the page makes |
| `html.py` | 35 lines — the only module importing Jinja2 |
| Render tests | 67 (`test_html.py` 14, `test_html_invariants.py` 27, `test_html_sections.py` 26) |
| View-model / builder tests | 142 under `tests/domain/report/` |
| CLI tests that read the written HTML | 8 in `tests/test_cli.py` |
| End-to-end report test | 1 (`tests/e2e/test_report_e2e.py`, marked `e2e`) |
| Whole suite | 769 tests |
| Golden file | `tests/adapters/render/golden/minimal.html`, 325 lines, 13.8 KB |
| A real report | `out/6Kx1P9GbNXrcLdHa-36.html`, 97,212 bytes, 2,241 lines |

What that real report contains: 6 panels, 58 cards, 58 `<h3>` headings, 76 badges, 5 summary
pointers, 1 inline SVG, 4 death recaps holding 181 recap rows and 12 availability groups, 5 player
cards, 49 evidence lists, 20 nesting lines.

### 1.1 Everything the page renders

Derived from the view model and the template together. "Branch" names the conditional in
`report.html.j2` that decides whether the element appears.

#### Document chrome — outside every panel

| # | Element | Kind | Branch / empty state |
| --- | --- | --- | --- |
| 1 | `<title>` — dungeon + keystone level | text | always |
| 2 | `<h1>` — dungeon + keystone level | heading | always |
| 3 | Sub-line — result, then affixes | text | `if header.affixes` appends ` · Affixes a, b, c`; the join happens in the template |
| 4 | Tab bar — 6 `<button>`s | widget | always in markup; hidden by the bare `.tabs { display: none }` and shown only by `.js .tabs` |
| 5 | Inline `<script>` | behaviour | `show`, `reveal`, `resolve`, plus click, `hashchange` and `load` wiring |
| 6 | `:root` palette | styling | 27 tokens; class colour resolved in `build.py`, never in CSS |

#### Two shared macros

| # | Element | Kind | Branch / empty state |
| --- | --- | --- | --- |
| 7 | `ledger_row` — the card every finding renders as | card | anchor `id="finding-<id>"`, `<h3>` title, `if row.seconds` cost span, badge link to `#provenance`, detail paragraph, `if row.nests_inside` → "Already counted inside X.", `if row.evidence` → `<ul>` |
| 8 | `pointer` — a loss as a link, never a second card | link row | title, cost, badge; deliberately no `<h3>` |

#### Panel 1 — Summary (`tab-summary`)

| # | Element | Kind | Branch / empty state |
| --- | --- | --- | --- |
| 9 | "What this run says" + narrative + legend | block | whole block absent when `narrative` is `None`; `white-space: pre-wrap`, left rule |
| 10 | "Where the time went" (`#ledger`) | heading + caption | heading always; caption is the not-additive warning |
| 11 | Decomposition rows | N × `ledger_row` | silently empty when there are none — no empty-state sentence |
| 12 | "Biggest losses" (`#losses`) + caption | heading | whole block absent when `summary_pointers` is empty |
| 13 | Pointers | up to 5 × `pointer` | `POINTER_COUNT = 5` in `build.py` |
| 14 | "Aligned timeline" (`#timeline`) | heading | always |
| 15 | Withheld reason | italic paragraph | `if timeline withheld` — and then **no SVG at all**, by rule |
| 16 | Two captions | text | present branch only: "Blocks are pulls…" and the three-mark legend |
| 17 | Inline SVG | widget | `viewBox` from the model; chart `<title>` as first child; no `role="img"` |
| 18 | Axis ticks | N × line + label | one every 10 minutes (`TICK_SECONDS = 600`) |
| 19 | Track captions | up to 2 × `<text>` | `if track` — "Ours — m:ss from first pull to last", "Reference — …" |
| 20 | Pull blocks | N × `<rect>` with `<title>` | 5 visual variants: `block`, `block block-theirs`, `+ block-boss`, `block-extra`, `block-skipped` |
| 21 | "Other findings" (`#observations`) | heading | always |
| 22 | Observation rows *or* "Nothing else measured." | rows / sentence | two-way branch |

#### Panel 2 — Route & tempo (`tab-route`)

| # | Element | Kind | Branch / empty state |
| --- | --- | --- | --- |
| 23 | "Route and tempo" (`#route`) | heading | always |
| 24 | Withheld reason | italic paragraph | `if route withheld` — renders *in addition to* any rows, not instead of them |
| 25 | Rows, or "Nothing to report." | rows / sentence | three-way: rows → caption + rows; no rows and present → sentence; no rows and withheld → reason only |

#### Panel 3 — Deaths (`tab-deaths`)

| # | Element | Kind | Branch / empty state |
| --- | --- | --- | --- |
| 26 | "Deaths" (`#deaths`) | heading | always |
| 27 | "No deaths." | sentence | `if not report.deaths` |
| 28 | Death card head | card | `<h3>` "player — killing blow" + when |
| 29 | Class-name line | text | always on a card |
| 30 | `.recap` grid | layout | 3fr / 2fr, collapsing to one column at `max-width: 640px` |
| 31 | Recap table | widget | `if death.timeline` — 4 columns: Before / Event / Detail / Health |
| 32 | Recap rows | N × `<tr class="…">` | 4 kinds: `hit`, `absorb`, `heal`, `cast`, each a colour and nothing else |
| 33 | Health cell + bar | cell + bar | `if row.health_percent is not none` → absolutely positioned `.hp-bar` at `width: N%` |
| 34 | Timeline note | sentence | `elif death.timeline_note` — printed verbatim from the builder |
| 35 | "Health after each event" + badge | badge line | `if death.health_badge` |
| 36 | Health note | sentence | `if death.health_note` |
| 37 | Return line + badge | text + badge | `if death.came_back`; four builder-written variants — resurrected, self-resurrected, released, not seen again |
| 38 | Availability groups | 3 × group | always three: Defensives, Consumables, Teammates' externals |
| 39 | Group title + badge | heading | `if group.badge` — inferred, linked to `#provenance` |
| 40 | Availability rows | N × `<li class="…">` | 4 states: `pressed`, `ready`, `cooldown`, `unseen` |
| 41 | Owner span | text | `if row.owner` — teammates' externals only |
| 42 | Group note | sentence | `if group.note` — the same field carries both "why this group is empty" and the consumable caveat qualifying rows that *are* there |
| 43 | Death rows | N × `ledger_row` | `if report.death_rows`, under the not-additive caption |

#### Panel 4 — Interrupts (`tab-interrupts`)

| # | Element | Kind | Branch / empty state |
| --- | --- | --- | --- |
| 44 | "Interrupts" (`#interrupts`) | heading | always |
| 45 | "Nothing to report." | sentence | `if not report.interrupts` |
| 46 | Interrupt rows | N × `ledger_row` | — |

#### Panel 5 — Players (`tab-players`)

| # | Element | Kind | Branch / empty state |
| --- | --- | --- | --- |
| 47 | "Players" (`#players`) | heading | always |
| 48 | "No players." | sentence | `if not report.players` |
| 49 | Player card head | card | colour swatch `var(--<colour>)`, name, class + spec as text beside it |
| 50 | Stats line | text | casts over pull time, deaths, interrupts — pluralised in Python |
| 51 | Damage rows | N × `ledger_row` | against the group median, never "avoidable" |
| 52 | Withheld comparison | italic paragraph | `if player.spell_and_talent withheld` — on every card |
| 53 | Spell / talent / uptime rows | N × `ledger_row` | subject's card only, matched by `actor_id` |
| 54 | Group rows | N × `ledger_row` | `if report.group_rows`, under "Group. Per-player rates, until each finds its player." |

#### Panel 6 — Provenance (`tab-provenance`)

| # | Element | Kind | Branch / empty state |
| --- | --- | --- | --- |
| 55 | "Provenance" (`#provenance`) | heading | always |
| 56 | Report code, fight id, fetched-at | text | always |
| 57 | Speed reference link | link | `if speed_reference_url` |
| 58 | Parse reference link | link | `if parse_reference_url` |
| 59 | Withheld lines | N × italic | one per withheld section, written in `build_report` |
| 60 | Method lines | N × text | today only the health-reconstruction method, and only when a card uses it |
| 61 | Confidence legend | legend | 3 badges + 3 explanations; the one place a badge is not a link |

**Badges.** Three kinds — `measured`, `derived`, `inferred` — rendered in six places: a ledger row's
head, a pointer, a death card's health line, a death card's return line, an availability group's
title, and the legend. Every badge but the legend's is an anchor to `#provenance`. The word is
always shown; colour never carries the meaning alone.

**Judgements the template already makes.** The invariant says the renderer decides nothing. Five
small things already sit on the wrong side of that line, and a rewrite should either carry them or
push them into `build.py` deliberately: the affix join `affixes|join(", ")`; the sentence assembly
"Already counted inside {{ nests_inside }}."; and the three empty-state sentences "No deaths.",
"Nothing to report." and "Nothing else measured." They are small. They are also precisely the kind
of thing that multiplies once the renderer is a programming language.

### 1.2 What the render tests enforce

The safety net a rewrite must rebuild in another language or lose. 67 tests, grouped by what they
actually protect.

| Group | Tests | What is enforced | Where |
| --- | --- | --- | --- |
| **Self-containment** | 2 (+2 CLI, +1 e2e) | Exactly one `<script>`, with no `src`; its body free of all 10 of `fetch`, `XMLHttpRequest`, `import(`, `document.write`, `innerHTML`, `textContent`, `localStorage`, `sessionStorage`, `eval`, `WebSocket`; no `@import`; no `<link rel=`; no `src="http(s)://"` or `//`; every `href` either a `#fragment` or a `warcraftlogs.com/reports/` link; `getElementById` used because finding ids contain dots | `test_html_invariants.py`, `test_cli.py`, `test_report_e2e.py` |
| **Fixture honesty** | 1 | The "rich" fixture is asserted to genuinely contain an SVG, two player cards, a nesting line, a withheld section, and both href kinds — so the self-containment tests cannot pass vacuously | `test_html_invariants.py` |
| **Works with scripting off** | 2 | No `hidden` attribute anywhere; no inline `style="…display…"`; every `display:none` rule in the stylesheet is scoped under `.js ` except the bare `.tabs`; the root element carries no `class="js"` in the markup | `test_html_invariants.py` |
| **Tabs and navigation** | 6 | Six panels, `<section class="panel">`, in a fixed order; exactly one tab button per panel; button order equals panel order; the nine section anchors appear in the order the design fixes; every pointer href targets an id that exists; a pointer is a link and emits no `<h3>` | `test_html_invariants.py` |
| **Escaping** | 3 (+2 CLI) | A narrative, an API-supplied title and an SVG `<title>` label are each proven unable to smuggle markup; every content assertion in the suite compares against `markupsafe.escape(...)`, which is what pins autoescape on | `test_html.py`, `test_html_sections.py`, `test_cli.py` |
| **Every finding once, and in the right place** | 8 | Every finding's escaped title reaches the page; `<h3>{title}</h3>` appears exactly once per finding (also asserted e2e over a real run's whole finding set); death, route, group and narrative content asserted *positionally*, between the anchors of the sections that must contain them; heading count equals section count, plus one with a narrative | `test_html_invariants.py`, `test_html_sections.py` |
| **Withholding** | 5 | Every withheld section states a reason; a withheld route still shows the gaps that need no reference; a withheld timeline emits no SVG at all — the "no empty chart frame" rule | `test_html_invariants.py`, `test_html_sections.py` |
| **The renderer computes nothing** | 1 | `Report` has no field beginning with `total`; **every** numeric field on **every** view-model type must appear on a 14-entry allowlist with a written justification; the template contains no `\|sum`, no `sum(`, and no `{% set %}` | `test_html_invariants.py` |
| **Timeline geometry** | 10 | `viewBox` comes from the model; each block carries its pack name as `<title>`; the chart's own `<title>` is a distinct, earlier element and there is no `role="img"`; boss, extra and skipped marks are distinguishable and never wrongly combined; both captions and the tick labels render; the legend names all three marks; **changing `TIMELINE_HEIGHT` in `build.py` moves the rendered tick line, its label and the block height together** — proof no coordinate is a template literal | `test_html_sections.py` |
| **Death recap** | 11 | All 4 recap kinds and all 4 availability states reach the page as classes; the builder's own note is printed rather than a template sentence; the health bar's width comes from `health_percent`; defensive and consumable states are asserted through real cooldown arithmetic, scoped to the deaths section; the consumable caveat is present; an unchecked spec produces *no rows at all* and says why; the group badge links to `#provenance`; a full card carries at least four provenance links | `test_html_invariants.py`, `test_html_sections.py` |
| **Content presence** | 17 | Header, affix labelling, narrative present and absent, reference links present and absent, the three-part confidence legend anchored to its own spans, provenance methods, "No deaths.", "No players.", interrupt rows, player class-as-text beside colour | `test_html.py`, `test_html_sections.py` |
| **Golden file** | 1 | Byte-exact comparison against 325 lines of rendered HTML; regenerated with `--golden-update`. Deliberately tiny: "a 2000-line diff is a test nobody reads" | `test_html_invariants.py` |

The unparenthesised counts sum to exactly the 67 tests in `tests/adapters/render/`; the
parenthesised ones are the 8 CLI and 1 e2e tests that assert the same properties over the file
`analyze` actually writes, and are additional.

**What the tests do not enforce, and should be said out loud:**

- **The script's behaviour is never executed.** The Python suite reads the script as text. Clicking
  a tab, resolving a fragment, and the scripting-off fallback are verified by hand, against a
  six-step browser checklist recorded in `2026-09-06-report-tabs-design.md` §7.5. §10 item 6 of the
  same document records *why*: "Forty lines of show-and-hide do not justify Node or a browser
  download in a uv-only repository. Revisit if the script ever grows past that."
- **Responsive behaviour is untested.** The single `@media (max-width: 640px)` rule that collapses
  the recap grid is pinned only by the golden file's bytes. Nothing renders the page at a viewport.
- **No visual regression, no contrast check, no accessibility assertions** beyond the absence of
  `role="img"` and whatever the golden bytes happen to freeze (the tab bar's `aria-label`, the
  script's `aria-selected`).
- **There is no CI, no pre-commit hook and no git hook in this repository.** The gate is four
  commands a developer chooses to type.

### 1.3 The close

**This is what a React rewrite has to reproduce before it earns its first new feature:** sixty-one
distinct rendered elements across six panels, thirty-three conditional branches, five block
variants, four recap kinds, four availability states, three badge kinds in six positions, sixty-two
CSS rules and twenty-seven palette tokens — under sixty-seven render tests, one byte-exact golden
file, and a documented offline guarantee asserted at three levels of the suite.

---

## The decision under the decisions

Before the six below, one question decides most of their answers, and the sketch does not name it.

**Does React render on the reader's machine, or at analysis time?**

If the prebuilt bundle renders **in the browser** from an inlined JSON blob, then the written HTML
file contains a `<div id="root">`, a JSON literal and a bundle. There is no markup in it. Every one
of the sixty-seven render tests that asserts about page content dies at once, the golden file
becomes meaningless, and the scripting-off fallback that
`test_the_page_hides_nothing_before_the_script_runs` protects becomes a blank page — a documented,
tested property traded away.

If React renders **at analysis time** (server-side, into markup), the string tests survive, the
golden file survives, the no-script page survives, and the file is still one file. The price is
that `analyze` — a Python CLI — must invoke Node on every run, which ends "uv is the only Python
toolchain used here" as a statement about how the tool runs, not only about how it is built.

Islands are a third answer that dodges the question for the first stage: keep the Jinja page,
mount React only inside a slot, and leave the existing server-rendered SVG in that slot as the
no-script fallback. See decisions 2 and 6.

---

## Part Two — the decisions

### Decision 1 — Does the report stay one self-contained HTML file that works offline, with no CDN?

**What the property is worth today.** Two design documents make it a hard promise:
`2026-09-03-mplus-postmortem-design.md` §7 ("No content delivery network, no network access at
load. It must open from disk, survive being posted to Discord, and work offline") and
`2026-09-05-mplus-report-design.md` §1, which adds "readable on a phone screenshot". Three layers
of the suite assert it: unit, CLI integration, and the real-run e2e test. The `analyzing-a-run`
skill's step 6 is literally "Hand over the HTML path" — the artifact *is* the deliverable, and it
travels as a file.

Beyond the stated reasons, three that are not written down anywhere and should be weighed:

- **Privacy.** A file that fetches nothing tells nobody who read which run, and when. A page that
  pulls icons from a CDN tells that CDN, every time anyone in the group opens it. This project
  already refuses to warehouse other players' logs on ToS grounds; a page that phones home about
  who is reading them is the same concern wearing different clothes.
- **Longevity.** A file that fetches nothing renders in five years. A CDN reference is a broken
  page the day the host reorganises.
- **Determinism.** The golden file exists because the output is deterministic. Anything fetched at
  load time is outside the snapshot.

**What it constrains about icons and tooltips.** Icons must be inlined — `data:` URIs or an inline
SVG sprite — at roughly 1.33× their raw bytes for base64. Tooltip *text* must be baked into the
page; the ordinary way to get WoW tooltips is Wowhead's external script, which this rule forbids
outright. Whether the total is tolerable is pending the icon spike. One relevant fact from the
existing code: every ability the report names already arrives with a `gameID`
(`masterData(translate: true) { abilities { gameID name } }` in `queries.py`), so the *key* for
any icon lookup is already in hand; nothing about icons needs a new identifier.

**Options.**

| Option | For | Against |
| --- | --- | --- |
| **A. Keep the rule absolutely** | Preserves everything above; costs nothing until the spike says icons don't fit | If icons are large, the report either grows or goes without |
| **B. One file plus a sibling assets folder** | Unlimited icon budget; still offline | Kills the drag-a-file-into-Discord workflow, which is how the report is actually shared; two things to move instead of one |
| **C. Allow a CDN for icons only** | Smallest file, easiest to build | Breaks the offline promise, breaks determinism, adds a privacy leak, and invalidates three layers of tests |
| **D. Two outputs — a lean shareable file and a rich local one** | Both audiences served | Two renderers of the same content, which is what decision 2 exists to avoid, doubled |

**Recommendation: A.** Hold the rule, and let the icon spike tell you the price of icons under it.
The current report is 97 KB; there is a great deal of headroom before "one file" stops being
practical, and the sharing channel's own attachment limit — worth checking rather than assuming —
is the real ceiling.

**How the spike moves this.** If icons bake in for, say, a few hundred kilobytes, A costs nothing
and the question closes. If they cost several megabytes, the choice is between dropping icons and
option B — and B should then be argued on its merits, not slipped in as a consequence.

**Cost of being wrong.** Holding the rule when icons would have fit: the report looks plainer for
one cycle. Relaxing it when it was not necessary: a property defended by two designs and three test
layers is gone, and it is very hard to reclaim once a page depends on network assets — every later
feature quietly assumes the network is there.

---

### Decision 2 — Does React replace the Jinja renderer, or sit beside it?

**Options.**

| Option | For | Against |
| --- | --- | --- |
| **A. Replace, in one migration** | One renderer to maintain; no drift | Nothing shippable for a long stretch. §1.3 says how long: 61 elements, 33 branches, 67 tests. A half-migrated page cannot be shipped |
| **B. Beside, permanently** | Each renderer used where it is best | Guaranteed drift, and CLAUDE.md arguably forbids it outright: "ALWAYS use one shared template instead of maintaining duplicates" |
| **C. Beside, temporarily, panel by panel** | Ships at every step | Two renderers of the *same document* for the whole migration; the golden file has to straddle both |
| **D. Islands — Jinja renders the document, React mounts only into named widget slots** | The shell, the escaping, the golden file and the no-script fallback all stay as they are; React is introduced only where it earns its keep | Not "a standalone React app"; the reader's page is still Jinja's, and the bundle sits inside it |

Option D deserves more weight than the sketch gives it. Two of RwlRwlRwlRwl's three wants — icons
and hover detail — need no framework at all. Only "a real timeline widget" plausibly does, and it
is one element of sixty-one. Under D, the timeline becomes a `<div>` with a JSON prop and the
existing server-rendered SVG beneath it as the fallback; the other sixty elements are not touched,
not retested, and not at risk.

The honest cost of D: the bundle's bytes end up inside the golden file, so the golden comparison
must either elide the `<script>` body or compare the bundle separately by hash. That is a small,
solvable problem, and worth naming now rather than discovering later.

**Recommendation: D, escalating to C only on evidence.** Start with one island. If a second and a
third island show that the Jinja shell — not the widgets — is the constraint, then migrate panel by
panel under C, deleting each panel's Jinja in the same commit that lands its React equivalent.
Never B.

**Cost of being wrong.** Choosing A and being wrong is the failure RwlRwlRwlRwl named explicitly: a
multi-session rewrite that shows nothing until the end, in a project with no CI to catch what the
rewrite breaks. Choosing D and being wrong costs one island's work, and the island is deletable —
remove the mount point and the page still renders.

---

### Decision 3 — What enforces "the renderer decides nothing" in a React world?

**What enforces it today, precisely.**

1. `Report` is a frozen pydantic value with 88 fields, every string already final. `model.py`'s own
   header says why there are no methods: "a method here would be judgement the template could
   reach."
2. `test_the_report_carries_no_total_row` walks every view-model type and fails any numeric field
   not on a 14-entry allowlist, each entry carrying a written reason (an id, a difficulty tier, an
   SVG coordinate, a health share). Every duration reaches the page as a pre-formatted string.
3. The same test greps the template for `|sum`, `sum(` and `{% set %}` — no accumulators, no local
   variables.
4. **Jinja's weakness does most of the work.** It has no function definitions, no imports, and
   arithmetic nobody would attempt. The language is the guardrail.
5. Positional tests assert *where* content lands, so a change cannot quietly relocate a judgement.

**What breaks.** JSX is JavaScript. `{row.seconds}` and `{fmt(row.seconds)}` are indistinguishable
in review, and point 4 evaporates entirely. The enforcement has to become explicit for the first
time.

**Replacements, strongest first.**

1. **Keep the pydantic model and its allowlist test unchanged.** They are the strongest control and
   they cost nothing — the view model is still Python, still frozen, still walked by a test that
   fails on a bare number. Whatever renders it, the contract holds that only 14 named numbers ever
   cross the wire as numbers.
2. **A contract test: every text node the page renders comes from the JSON, or from a named
   allowlist of chrome strings.** This is the mechanical statement of "the renderer invents
   nothing," and it is buildable: walk the rendered DOM, subtract the strings present in the view
   model, and assert the remainder is a subset of a checked-in list. That list then *is* the set of
   judgements the renderer is permitted — the thing that today is scattered implicitly through the
   template (see §1.1's note on the five judgements Jinja already makes). Recommend building this
   first; it is worth more than every lint rule combined.
3. **Branded display types.** Generate TypeScript from the pydantic models and brand each display
   field — `type Display = string & { readonly __display: unique symbol }`. A component handed a
   `Display` has nothing to format. This is the closest JS analogue to the frozen model.
4. **An ESLint `no-restricted-syntax` rule** banning `.toFixed`, `Math.round`, `Intl.NumberFormat`,
   `new Date` and arithmetic operators inside the components directory. Useful; heuristic; easy to
   route around. Not a proof, and should not be sold as one.
5. **A redrawn line, stated in the design.** A charting library computes coordinates — that is
   arithmetic in the renderer, and today `build.py` does it precisely so the template cannot. The
   honest redraw is: *no domain arithmetic in the renderer; layout arithmetic is permitted inside a
   widget that receives already-final labels.* If the brainstorm wants a real timeline widget, it is
   accepting this, and it should accept it explicitly rather than by omission.

**What replaces the Python tests in `tests/adapters/render/`.** This depends entirely on the
question above about where React renders.

- **The good news:** roughly ten of the sixty-seven — self-containment, href scoping, script count,
  the no-total/no-`{% set %}` checks, and the golden comparison — are tests over an output *string*.
  They do not care who produced it. If the build still emits one HTML file, they port for free by
  pointing at the built artifact. The eight CLI tests and the one e2e test are already exactly this
  shape.
- **The bad news:** the other ~57 call `render(a_report(...))` from Python and assert on the result.
  Under a client-rendered bundle they are unwritable — there is no markup for Python to read. Under
  a server-rendered bundle they are writable but require `uv run pytest` to invoke Node. Under
  islands they simply keep passing, because Jinja still renders everything they assert about.

**Recommendation.** Keep 1 and 2 as the load-bearing controls, add 3 and 4 as cheap reinforcement,
and write 5 into the design before any widget is built. Prefer the island model precisely because
it keeps 57 existing tests alive while the new controls are proven on a small surface.

**Cost of being wrong.** The invariant is what keeps this tool from confidently lying. If a
component starts formatting a duration, the number on the page stops being the number the tested
Python computed, and no badge on it means anything any more. That is not a UI regression; it is the
project's central claim failing quietly.

---

### Decision 4 — A concrete JS test stack, and exactly how it runs in one gate

**The stack.**

| Layer | Tool | Covers |
| --- | --- | --- |
| Runner | **Vitest** | Native to Vite, TypeScript out of the box, watch mode for red-green |
| Component / DOM | **@testing-library/react** on **jsdom** | Unit: a component given a fixture prop renders the expected text and classes |
| Integration | Vitest over the **built** page from a real fixture JSON | The whole document assembles: panels, order, escaping, empty states |
| End-to-end | **Playwright** against the file `analyze` actually wrote, over `file://` | Clicks each tab, follows a badge to Provenance, follows a pointer to its card, reloads with `#deaths`, and **disables JavaScript to check the no-script fallback** |
| Lint | **ESLint** (plus the restricted-syntax rule from decision 3) | The `ruff` analogue |
| Types | **`tsc --noEmit`** | The `mypy` analogue |

Playwright is the layer that pays for itself independently of React: it automates the six-step
manual browser check recorded in `2026-09-06-report-tabs-design.md` §7.5, which is the largest
untested surface the report has today.

**How it runs as one gate.** There is no CI, no Makefile and no task runner in this repository
today; the gate is four commands typed by hand. So the gate has to be created, not extended.

Add a console script to `pyproject.toml` under `[project.scripts]` — for example
`wowperf-check = "wowperf.check:main"` — that runs, in order, stopping at the first non-zero exit:

```
uv run ruff check .
uv run mypy
uv run pytest
npm --prefix web ci          # only when node_modules is missing or package-lock.json changed
npm --prefix web run lint    # eslint
npm --prefix web run types   # tsc --noEmit
npm --prefix web test        # vitest run
```

**The command a developer types: `uv run wowperf-check`.**

Belt and braces, if the gate must literally be `uv run pytest`: add
`tests/test_js_suite.py::test_the_javascript_suite_passes`, which shells out to
`npm --prefix web test` and asserts the exit code. Then a red Vitest run is a red pytest run. The
cost is one opaque failure hiding many assertions, and a pytest run that is no longer fast and
offline. Recommend the console script as the primary gate and this test as the safety net, marked
so it can be skipped when iterating on Python alone.

**Prerequisites and honest costs.**

- Node **v24.19.0** and npm **11.17.0** are already installed on this machine — measured, not
  assumed. Nothing about the toolchain needs installing to start.
- `web/package.json` with pinned versions, `npm ci` for reproducibility, `web/node_modules/` in
  `.gitignore`.
- `npx playwright install` downloads browser binaries — a real, sizeable one-time download. Flag it
  before agreeing to Playwright, not after.
- `uv run pytest` stops being the whole story. CLAUDE.md's command table gains rows, and the claim
  "`uv` is the only Python toolchain used here" needs a companion sentence about Node.
- **This directly overturns a recorded decision.** `2026-09-06-report-tabs-design.md` §10 item 6
  chose invariants-plus-a-manual-check over "a second toolchain", and named the revisit condition:
  "if the script ever grows past" forty lines of show-and-hide. The proposal *is* that condition.
  The brainstorm should overturn it explicitly and date the amendment, the way this project
  overturns everything else.

**Recommendation.** Adopt the stack, and adopt the single-command gate in the same change that adds
the first JavaScript file — never after. Separately, and regardless of what the brainstorm decides
about React: **add CI.** A gate that exists only as discipline is the weakest part of this
repository today, and doubling the number of toolchains it must remember to run makes that weakness
worse. A GitHub Actions workflow running the same command is the cheapest insurance available, and
it helps even if the React proposal is rejected outright.

**Cost of being wrong.** Two commands instead of one means that eventually a React change ships
with the JS suite red, and nothing catches it. With 769 Python tests currently green and no CI, the
project's quality rests entirely on the gate being cheap to run. Make the new gate cheaper than the
old one or it will not be run.

---

### Decision 5 — Do talent icons belong in this scope?

**What exists today.** `queries.py` has `talents_query`, one aliased `talentImportCode(actorID:)`
per player; `ingest.py` stores the result on `Player.talent_import_string`;
`comparison/spells.py::compare_talents` uses it for exactly two things — string equality, and
printing the reference player's string so ours can be imported. Nothing decodes it. Real values are
in the cache: base64 strings around 100–110 characters, for example
`CgQAAAAAAAAAAAAAAAAAAAAAAAAAAgBAAAAzMzsstMmZmZMzYMjhFYDmxiGbDgZgNmZGMbzMGNbLzMbmxsxixMjhlZZAAwAYmBzMAMGMA`.

**What decoding would actually take.**

1. **Decode the string.** Blizzard's loadout export is a bit stream — a serialization version, the
   specialisation id, a tree hash, then a per-node sequence of selected / rank / choice bits.
   Community implementations of this format exist. This part is bounded, offline-testable against
   the strings already in `cache/`, and is *not* the hard part.
2. **Turn nodes into spells.** The bit stream is **positional**. It says "node 47 is selected,
   choice entry 2"; it does not say which spell that is. Resolving it needs the talent tree
   definition for that specialisation at that game build — node ordering, node ids, entry ids, and
   the spell each entry grants. **Warcraft Logs does not publish this.** Under the project's own
   invariant, constants with no API source live in `data/*.toml` with a verified-on date, so this
   becomes a data file per specialisation — thirteen classes, roughly forty specs, a few hundred
   nodes each — refreshed every patch.
3. **Source that data at all.** It would come from a third-party export of game client data. I have
   not verified any such source, its licence, or its update cadence, and I will not name one as
   usable on the strength of recollection. Establishing that is a research task in its own right,
   and it must precede any estimate.

**The project has already refused this exact shape of dependency.** Design §6.5 item 4 dropped
"cooldown uses against theoretical maximum" because it "needed cooldown seconds and charge counts
for every rotational ability of every specialization, none of which the API publishes, all of which
go stale each patch." Talent trees are the same objection with a larger table and a shorter half-life.

**The asymmetry worth noticing.** *Spell* icons are cheap by comparison. Every ability the report
already names arrives with its `gameID`, and every damage, heal, cast and defensive row keys off an
id the project already holds. Talents are the one family where the identifier is not in hand.
Bundling "spell and talent icons" as one feature hides a large cost inside a small one.

**Recommendation: out of scope, and say so in the design.** Take spell icons now, pending the icon
spike. Leave talent decoding to a later cycle with its own research task. If talents need to look
better sooner, the cheap version needs no decoding at all: the comparison already knows whether the
builds match and already holds the reference's import string — a copy-to-clipboard control gets
most of the reader value for none of the maintenance.

**Cost of being wrong.** Taking it in: a per-patch maintenance obligation nobody will meet, and a
page that eventually shows a stale build with confident icons beside it — the precise failure the
confidence-badge system exists to prevent. Leaving it out and being wrong: a nice-to-have arrives
one cycle later, having been costed properly first.

---

### Decision 6 — Staging: what ships at each step

RwlRwlRwlRwl has said he does not want a multi-session rewrite that shows nothing until the end. §1.3
is the evidence that "rewrite the report in React" has no shippable intermediate: a half-migrated
page of sixty-one elements is a page you cannot open. So the sequence below is built backwards from
the constraint — **every stage ends with a report file on disk that is better than the last one.**

| Stage | What is built | What RwlRwlRwlRwl can look at | New toolchain |
| --- | --- | --- | --- |
| **0. The JSON contract** | `analyze` also writes `<code>-<fight>.report.json` — `Report.model_dump_json()` on the existing frozen model. No renderer change | The view model, inspectable and diffable between runs | none |
| **1. Icons in the page that exists** *(pending the icon spike)* | An icon beside each ability-named row, inlined | A visibly better report | none |
| **2. Hover detail in the page that exists** | Native `<details>`, richer `<title>`s, a small extension to the inline script | The third of the three wants | none — but see below |
| **3. One island: the timeline** | `web/` with Vite + React + a timeline library, rendering one widget from the JSON; mounted into the existing `#timeline` slot with the current SVG beneath it as the no-script fallback | A real timeline widget on an otherwise unchanged report | the full stack from decision 4 |
| **4. Decide, on evidence** | Nothing. Measure the bundle, review the test stack, look at the widget | — | — |
| **5. Replace, only if stage 4 says so** | Panel by panel, each panel's Jinja deleted in the commit that lands its React equivalent | An unchanged-looking report after each panel | — |

**Why this order.**

- Stage 0 is the one piece of the original sketch that is unambiguously right, costs almost nothing,
  and is needed by everything after it. Do it first and independently. The model is already frozen
  pydantic with a `StrEnum`; serialisation needs no new machinery.
- Stages 1 and 2 deliver two of the three stated wants **without React at all**. If the project
  stalls after stage 2 — and projects do — it stalls having improved the report rather than having
  half-rewritten it.
- Stage 2 carries one honest catch: extending the inline script past show-and-hide trips
  `2026-09-06-report-tabs-design.md` §10 item 6's revisit condition, which means the JS test stack
  of decision 4 is needed at stage 2 whether or not React is ever adopted. That is an argument for
  adopting the stack early, not for skipping stage 2.
- Stage 3 is the first thing that genuinely could not be done in Jinja, and it is *reversible*:
  delete the mount point and the page still works. It proves or disproves the whole proposal against
  one small surface — bundle size, test stack, gate command, golden-file treatment — rather than
  against sixty-one elements.
- Stage 4 exists so the expensive, irreversible decision is made with measurements instead of
  arguments.
- If the island model holds, Phase J of `2026-09-06-audit-and-improvement-roadmap.md` — per-player
  cast-activity bars, a cooldown-usage timeline, damage-taken against defensives pressed — is four
  more islands. That is where a component model and real charting libraries genuinely earn their
  keep, and it argues for building the island machinery well rather than for rewriting what exists.

**The thing to be honest about.** If the real goal is "I want to build this in React because I want
to build in React" — a perfectly legitimate goal, and not one this brief can weigh — then stages 1
and 2 are a detour and the sequence should start at stage 3. That should be a decision made out
loud, not one arrived at by treating icons as though they required a framework. They do not.

**Cost of being wrong.** Getting the order wrong is the most expensive mistake available here,
because it is the one that cannot be undone by a later commit: a stalled rewrite leaves the project
with two half-renderers, a golden file that matches neither, and a report worse than the one it
started with.

---

## What this brief did not do

- It did not investigate whether icons and tooltip text can be baked into a self-contained file, or
  at what size. That is the icon spike's question, and every place it bears is marked.
- It did not verify any source of talent tree data, or any library that decodes a loadout string.
  Decision 5 names that as a research task rather than estimating it.
- It did not measure a React bundle's size. Stage 4 exists to measure it rather than guess it.
- It did not check the current attachment limit of whichever channel the report is shared through.
  Decision 1 needs that figure and does not have it.
- It did not run the test suite, and it wrote no code.
