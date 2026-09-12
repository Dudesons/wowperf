# Report density and interaction — design

Status: approved 2026-09-11. Supersedes nothing; extends the report sections of
`docs/plans/2026-09-03-mplus-postmortem-design.md` (§12) and the death-recap work that
followed it.

Interactive mockup, built against the report's own palette and class names:
<https://claude.ai/code/artifact/26da5f41-c3c7-4e3c-9360-5e516f31686f>

## 1. Why

The first reading of a real report by someone other than its author produced six points. Five
are presentation and are the subject of this design. The sixth — ordered tips for improvement —
is analysis, gets its own design, and is deliberately excluded so it cannot hold the rest up.

The points, as given:

1. Every view is very compact; the page could use the screen it has.
2. The death timeline should react to where the reader is looking, and the dots on the health
   curve are not clear.
3. The player timeline is good but cramped, and a cooldown that grants a buff should show how
   long that buff covered.
4. Hovering an icon should open a tooltip with detail about the ability.
5. An ability name beside its icon should read as one thing.

## 2. Scope

**In:** the five points above.

**Out, with reasons:**

- **Ordered improvement tips.** Analysis, not presentation. Needs its own tests and its own
  honesty argument, because the difference between ranking measured findings and inventing
  coaching is the whole design.
- **Damage dealt per ability.** The project fetches Casts, DamageTaken, Healing, Deaths,
  Interrupts, Resurrects and the buff table. There is no `DamageDone` query. Adding one means a
  new stream, a new page-through, and real points on every run. Nothing else in this design
  depends on it. Deferred as its own decision rather than smuggled in as a tooltip field.

## 3. The two rules this design turns on

### 3.1 The script may grow; the ban list does not

`CLAUDE.md` says the page carries "exactly one inline script — the tab toggle, which may not
fetch, write text, or read storage." The first half of that sentence is a description of what
the script happens to do today; the second half is the rule.
`tests/adapters/render/test_html_invariants.py::test_the_page_executes_only_its_own_script`
enforces: one `<script>`, no `src`, and none of `fetch`, `XMLHttpRequest`, `import(`,
`document.write`, `innerHTML`, `textContent`, `localStorage`, `sessionStorage`, `eval`,
`WebSocket`.

Hover behaviour needs `classList` and `addEventListener`, both of which the current script
already uses and neither of which is forbidden. So the interaction in this design is legal
under the test as it stands, and only the prose is in the way.

**Amend the prose to state the rule.** Replace the invariant's script clause with:

> One HTML file, opened from disk, with no stylesheet link, no `@import`, no remote `src`, and
> exactly one inline script. That script may show, hide and highlight what is already on the
> page; it may not fetch, write text, or read storage, and
> `tests/adapters/render/test_html_invariants.py` enforces the list.

The property being protected — the page loads nothing, stores nothing, writes no text, and
reads the same in two years as it does today — is untouched. What changes is that the rule now
says what it is rather than naming the one feature that happened to need it.

### 3.2 Every coordinate is computed in Python

No geometry is calculated in the browser. Marker positions, cover windows, pull column bounds
and bar heights are computed by the view model builder, rendered into the page hidden, and
revealed by a class toggle.

Three consequences, and they are the reason the amendment above is cheap rather than a slippery
slope:

- The arithmetic is covered by `pytest`, not by untestable browser behaviour.
- The script stays roughly its current size. It gains a hover handler, not a rendering engine.
- The "the LLM never computes a number" discipline extends naturally: **nothing outside tested
  Python computes a number**, script included.

Any future proposal that needs the script to calculate a position should be read as a proposal
to move work out of the tested layer, and refused on that basis.

## 4. The changes

### 4.1 Responsive width

`report.css.j2` line 18 is `main { max-width: 760px }`. Removing the cap alone would stretch
running prose to an unreadable measure, so the width is split by content type:

- **Prose keeps a measure.** Narrative, detail text, notes: `max-width: 68ch`.
- **Dense content takes the width.** Finding cards, event tables, timelines, provenance tables.
- **Findings flow into columns**: `repeat(auto-fit, minmax(330px, 1fr))`.

CSS only. No view model change.

Care needed on two things the mockup does not settle: a column count that never leaves one card
alone on the final row, and the Provenance tables staying readable rather than merely wide.

### 4.2 The death recap answers where the reader is looking

Hovering or focusing a row in the event table drops a marker onto the health curve at that
event's moment. A row that is a defensive press also reveals the window that defensive covered,
so "the shield expired before the killing blow" becomes something seen rather than worked out.

The curve and the table already live in the same card (`_deaths.html.j2`), and every row already
carries its `seconds_before`. The view model gains:

- an `x` on each timeline row, in the curve's coordinate space;
- a `(start_x, end_x)` cover window on each press row, from the aura bands.

**The readings also change.** Today the line is solid and the dots are `r=2.5` in the measured
tint. The complaint that the dots are unclear is fair: they read as kinks. Instead —

- the line between readings becomes **dashed**, because it is arithmetic;
- the readings become **ringed against the page colour**, so they read as marks.

The shapes then carry the measured/derived distinction that the legend currently has to explain
in words.

### 4.3 Death event tooltips

Every event name in the recap table becomes a tooltip. A damage event is the richest thing on
the page for this, because `unmitigatedAmount`, `mitigated`, `absorbed` and `amount` are four
fields on one event: the tooltip reports a single hit and apportions nothing.

Contents by event kind:

| Kind | Carries |
| --- | --- |
| Damage taken | struck for, mitigated, absorbed, reached health, source, hit type, area |
| Killing blow | the above, plus overkill |
| Heal received | healed for, resulting health, caster |
| Absorb | the shield, and the hit it soaked (`extraAbilityGameID`) |
| Defensive press | cover from this press, when it ran out, what arrived while it was up |

The heal tooltip states no overheal, because the healing stream returns no such field — recorded
2026-09-06 in the wcl-api skill. Saying so is better than omitting the row silently.

### 4.4 The run timeline

Four changes, three of them answering questions the first mockup provoked.

**Pull columns.** The grey boxes were pulls and nothing said so. They become columns running the
full height of the chart, so a press visibly lands *inside* a pull rather than floating above
one.

**Pulls are named.** `Pull.name`, `Pull.is_boss` and `Pull.enemies` are all already on the
domain model and unused by the timeline. Boss pulls take their name; trash pulls take their
index.

**A cooldown shows when it comes back.** Today a press mark is followed by a lighter stretch for
the cooldown, and "available again" has no mark at all — it is read as an absence. It gains a
tick at the end of the cooldown stretch, and the track behind it is dark so the transition is
visible.

**Cover windows are drawn to scale, and the scale is brutal.** 570px spans 1980 seconds, so a
five-second shield is 1.4px. This is not a drafting problem to be fixed by drawing it bigger;
drawing it bigger is a lie about duration. Two conclusions:

- On the run timeline the sliver stays, because at true scale it says something worth saying:
  Anti-Magic Shell covers 5 seconds of every 60, and the green head on a grey bar is how much of
  each cycle the ability was doing anything.
- **Duration as a readable quantity belongs on the death card**, where the axis is ten seconds
  wide, and in the tooltip as a number.

The damage row also gains an axis (`0` to the run's tallest bucket) and a caption saying a bar
is a five-second bucket. Previously the only scale cue sat below the chart.

### 4.5 Ability tooltips, and the three tiers

An ability tooltip carries, in this order:

1. **Static** — name, class and role, and the description. Fetched at build time (§5) and
   embedded. Only as fresh as its source, and marked as such.
2. **Measured** — figures from fields on events already fetched.
3. **Derived** — figures computed from those, badged accordingly.

Worked example, Icebound Fortitude, and the reason this section exists:

| Line | Tier |
| --- | --- |
| "Reduces damage taken by 30% for 8 sec" | static, from the description |
| Base cooldown 120s; 4 presses; 32s of cover | measured |
| 2,904,118 arrived while it was up | measured |
| 1,043,880 of it reached health | measured |
| 64% mitigated inside its windows, 41% outside | derived |

Nothing in the measured or derived tiers is computed from the static one. That separation is
what keeps a tuning change from silently corrupting a figure the page presents as measured.

### 4.5.1 Which surfaces carry one, settled 2026-09-12

> **Amended 2026-09-12 by `docs/plans/2026-09-12-report-second-reading-design.md` §6.**
> The ruling below on **ledger card headings** is overturned: they carry a tooltip after all.
> A second reading of a real report found a reader looking for the panel with the evidence list
> already on screen, and the cost was overstated — the five families that name an ability need
> three new builders, not five, because `ability_tooltip` fits both defensives families. The
> ruling on **the death card heading** stands, on the ground given here.

Four surfaces on the page name an ability. Two carry the panel above — the death recap's event
rows and its availability rows. Two do not, and will not.

**The ledger card headings and the death card heading carry no tooltip.** Not for want of
plumbing: `ability()` already takes an optional tooltip and the headings simply call it without
one. The reason is that there is nothing worth putting in the panel.

- **Every ability-carrying ledger card already prints its measured facts**, as the evidence list
  three lines under the heading. `defensives.ceiling.*` gives its cast count against the seconds
  the player was alive; `compare.uptime.*` gives both sides' boss-pull seconds; `interrupts.*`
  gives what landed against what was kicked. The two surfaces that did earn a panel earned it
  because a recap row is one line of a dense table with nowhere to print evidence.
- **There is no one panel to build.** `ability_tooltip` is shaped for a defensive at a death:
  base cooldown, presses, cover, mitigated inside and outside. Those fields say nothing about an
  uptime gap or an unkicked cast. Doing this honestly means one tooltip builder per finding
  family, a dispatcher over them, and `LoadedRun` and the per-player aura tables threaded through
  all five `ledger_row` call sites into a function whose whole job is formatting — to print a
  second copy of what is already on the screen.
- The death card heading names the killing blow, and the recap row below it already carries that
  hit's own figures, with `hit_tooltip` on them.

**The player timeline's rows do carry their facts.** The promise was that its SVG rows would keep
"their native `<title>` enriched with the same measured facts". They had no `<title>` to enrich:
only the pull bands carried one, and it held the pull's name alone. A cooldown row is the one
surface whose facts are genuinely absent — presses, cover, ready marks and unavailable stretches
drawn as bare rectangles against a single name — so each row now carries a `<g>` title giving its
press count and its cover, and each pull band says how long its pull ran.

Those titles are measured only. They omit the time an ability spent unavailable, which is a base
cooldown from `data/` laid over the presses rather than anything the log stated, and a native SVG
title carries no badge to grade such a figure with. They do distinguish an ability the aura
tables say nothing about from one whose buff was never up, because the drawing cannot: it shows
no rectangle either way.

### 4.6 Icon and name as one object

The icon and the name already sit adjacent in the markup; they are simply not bound into one
element. They become a single hoverable, focusable unit, with the name in the page's ink weight.
CSS and one template macro.

## 5. What we refuse to state

**Damage prevented by a named ability is not derivable, and must not be printed.**

`DamageTaken` reports one `mitigated` figure per hit and never says what caused it. Armour,
Versatility, spec passives, a second defensive running concurrently, and a teammate's external
all land in that one number, stacking multiplicatively.

The tempting implementation is `unmitigatedAmount * 0.30`. It produces a confident figure, it
looks measured, and it is fabricated: it assumes the reduction applies uniformly across damage
types, ignores stacking order, and hardcodes a tuning value that changes between patches. **Do
not implement it.** The tooltip says instead that the log does not attribute mitigation, and
offers the inside/outside rate gap as suggestive rather than attributable.

This is the same failure the debuff half was retired for on 2026-09-11: shipping a number whose
meaning the API cannot support.

## 6. What the data supports

| Claim | Source | Already fetched | Badge |
| --- | --- | --- | --- |
| Health at a stated moment | cast/resource events | yes | measured |
| Health between readings | arithmetic over hits and heals | yes | derived |
| One hit's struck/mitigated/absorbed/landed | `DamageTaken` event fields | yes | measured |
| Overkill on the killing blow | `DamageTaken` | yes | measured |
| Buff cover windows | aura `bands` on the buff table | yes | measured |
| Which buffs were up on a given hit | `buffs` on the damage event | **fetched, discarded** | measured |
| Damage taken while a buff was up | the row above | yes | measured |
| Mitigation rate inside vs outside a window | derived from the above | yes | derived |
| Cooldown stretches | `data/*.toml` base lengths | n/a | inferred |
| Pull names and boss status | `Pull.name`, `Pull.is_boss` | yes | measured |
| Spell description | external, see §7 | **no** | static |
| Damage dealt by an ability | `DamageDone` | **no** | out of scope |
| Damage prevented by a named ability | nothing | — | **refused, §5** |

One row there is a finding rather than a restatement: **every damage-taken event carries a
`buffs` field** (verified 2026-09-04, in the wcl-api skill's stream table), and `ingest.py` does
not read it. That makes "what arrived while this was up" exact per hit rather than approximated
by intersecting band timestamps against event timestamps. Its wire format is not verified here;
check it before relying on it, and add a dated row.

## 7. Prerequisite: where descriptions come from

Descriptions are wanted first in the tooltip, and no source is confirmed.

**The page never fetches.** The invariant holds without amendment on this point: descriptions
are fetched by `wowperf analyze` at build time, cached on disk permanently, and embedded as
static text — exactly the rail `adapters/render/icons.py` already runs for ability icons against
Blizzard's render CDN. A description captured at build time also describes the patch the run
happened on, which a hand-maintained file cannot promise.

What is not known: which source serves usable description text, at what cost, under what terms.
Blizzard's Game Data API is the obvious candidate and needs its own client credentials, which
this project does not hold — it has Warcraft Logs OAuth only. This is a spike, and its outcome
does not block the rest.

**The tooltip is built so descriptions are optional.** It renders with the measured and derived
tiers alone, and the static tier appears only where a description resolved. Every tooltip in
this design is useful without one.

## 8. Tests this design owes

- The script still passes `test_the_page_executes_only_its_own_script` unchanged. That test is
  the amendment's enforcement and must not be relaxed.
- Marker, cover-window, pull-column and bar geometry: unit tests on the view model builder, in
  the tested Python layer, per §3.2.
- A cover window is never widened below its true scale — the guard against redrawing 1.4px as
  something legible.
- No tooltip renders a figure attributed to a single mitigation source (§5).
- Every tooltip renders correctly with no description present.
- The existing invariants — one script, no remote `src`, no `@import`, unique element ids, every
  finding on the page exactly once — all continue to hold.

## 9. Open, and not blocking

- The description-source spike (§7).
- Whether damage dealt justifies a `DamageDone` query (§2).
- Tooltips near a card's bottom edge need to flip upward; a mockup detail, not a design one.
