# Mythic+ Post-Mortem: The Report in Tabs — Design

**Status:** Approved in conversation 2026-09-06. Not yet implemented. Phase H of
`2026-09-06-audit-and-improvement-roadmap.md`.

**Authority:** `2026-09-05-mplus-report-design.md` remains the report's design and stays binding
wherever this document is silent. This document supersedes its §11 (no navigation), amends its §4,
§5, §9 and §10, and records the decisions the roadmap's §4 "Phase H" left open. Where the two
disagree, this one is newer and wins; each disagreement is amended back into the older document,
dated, by the plan that implements this design.

**Depends on:** Phase G, merged into `master` at `144aa8f`.

**Not in scope:** per-player sub-tabs and their content (Phase J), the death recap (Phase I). See
§9.

---

## 1. Why the report needs navigation after all

The report design's §11 ruled out navigation on the argument that a report needing it has grown
too long and should be cut. The first real run settled the argument the other way: a clean +16
renders sixty-seven cards, the reader needs all of them, and different readers want different
parts — the route for the group's caller, a death for the player who died, provenance for whoever
doubts a number. Cutting would remove something one of them came for.

So the page gains tabs, and one rule is restated rather than relaxed. "The template decides
nothing" has always been about judgement: what a finding means, where it belongs, what its badge
says. Navigation is not judgement. A tab shows and hides sections that are all on the page, in the
order the builder fixed, with the words the builder wrote. Nothing about what is true changes with
the tab that is open.

Everything the report design guarantees survives: one self-contained file; nothing fetched;
every finding on the page exactly once; no total row; a withheld section keeps its heading and
states its reason.

## 2. The page

The header stays above every tab — dungeon, keystone level, result, affixes — because it is what
every reader wants first and what a screenshot must carry. Beneath it, a tab bar of six buttons,
then six panels. Each panel holds `<h2>` sections; every heading and its `id` from today's page
survives unchanged, so every fragment link the page already emits keeps working.

| Tab | Question it answers | Sections inside, in order |
| --- | --- | --- |
| Summary | Did we time it, and where did the time go? | Narrative (when supplied); Where the time went — the three decomposition rows only; Biggest losses — up to five pointers (§5.2); Aligned timeline; Other findings |
| Route & tempo | What did the route cost us against the reference? | Route findings: gaps, downtime, skipped and extra packs, route summary, order and unaligned notice, trash overage and pull rates, confounds |
| Deaths | Why did each death happen, and what was available? | Death cards; then the death rows: single, chained and repeated death costs, defensives and consumables at death, the deaths comparison |
| Interrupts | What got through? | As today, plus the interrupts comparison |
| Players | What can each player look at? | Player cards as today; then a "Group" list of the per-player rate rows — defensive rate and ceiling, throughput alignment and ceiling — until Phase J moves each onto its player |
| Provenance | Where did this come from, and what was withheld? | As today: source, reference links, everything withheld, the badge legend |

Summary opens first. The "Other findings" catch-all sits at the bottom of Summary, the tab that
must lose nothing: an analyser family nobody has homed yet surfaces where every reader looks
first, and on a healthy run it reads "Nothing else measured" in one line.

## 3. The script

One inline `<script>` element at the end of `<body>`, about forty lines of plain JavaScript, with
no `src`. It has four duties and no others:

1. **On load**, add one class to the root `<html>` element. Every rule that hides a panel or shows
   the tab bar is scoped under that class (§6), so the page hides nothing until the script has
   run.
2. **On a tab button click**, mark that button and its panel active within their group, and write
   the panel's id to the URL fragment.
3. **On load and on every fragment change**, resolve the fragment. A panel id opens that panel. Any
   other id — `provenance`, a card's anchor — opens the panel containing that element, then leaves
   the browser to scroll to it. This is what makes a badge's existing `href="#provenance"` open the
   Provenance tab, and a Summary pointer open the tab holding its card.
4. **Nothing else.** It creates no element, sets no text, reads no storage, fetches nothing.
   Remembering the last tab comes from the fragment for free, so there is no storage to read.

**Without the script**, the root class is absent, the tab bar is hidden, and every panel is
visible, stacked in tab order: today's page with its sections regrouped. A reader who saves the
page as text, a search over the file, or a test that parses it sees everything.

**Groups, not a bar.** The script acts on any element carrying the tab-group marker attribute,
not on one bar it knows by id. Phase J adds a per-player bar inside the Players panel by writing
template, not script. This document builds no sub-tab.

## 4. The view model

`ledger_losses` leaves `Report`. Four fields arrive — three tuples of the existing `LedgerRow`
and one `Section` — so no new type and no new numeric field. `death_findings` is renamed
`death_rows` and widened. `interrupts` widens by one family. Everything else in `model.py` keeps
its shape.

```python
class Report(Frozen):
    header: Header
    narrative: str | None
    ledger_decomposition: tuple[LedgerRow, ...]
    # The biggest timed losses, in the order the findings arrived (§5.2). Each is the same
    # LedgerRow object as its card on another tab; the Summary renders it compactly and
    # links to the card, never as a second card.
    summary_pointers: tuple[LedgerRow, ...]
    timeline: Timeline
    # Withheld without a speed reference, with the reason from the same finding the
    # timeline reads. The rows below it that need no reference still render.
    route: Section
    route_rows: tuple[LedgerRow, ...]
    deaths: tuple[DeathCard, ...]
    death_rows: tuple[LedgerRow, ...]          # today's death_findings, widened (§5.1)
    interrupts: tuple[LedgerRow, ...]
    players: tuple[PlayerCard, ...]
    group_rows: tuple[LedgerRow, ...]
    observations: tuple[LedgerRow, ...]
    provenance: Provenance
```

`LedgerRow` is unchanged. A row's anchor on the page is `finding-<finding_id>`, produced by the
row macro from the `finding_id` the row already carries; it is formatting, so the builder emits
nothing for it. HTML permits dots in an `id`, and the script resolves anchors with
`getElementById`, which needs no selector escaping.

## 5. The builder

### 5.1 Placement is one ordered table

Decomposition ids are matched exactly first, as today. Every other finding is then placed by the
first prefix that matches in this table; the player-card families (`players.damage.`,
`compare.spells.`, `compare.talents`, `compare.uptime.`) keep going through `build_players`
unchanged; and whatever no field claimed falls to the catch-all by the existing mechanism — read
back off the fields themselves, never recomputed from a prefix list.

| Prefix | Field | Note |
| --- | --- | --- |
| `defensives.unused.` | `death_rows` | Must precede the bare `defensives.` row |
| `consumables.` | `death_rows` | `consumables.unused.` and `consumables.never.` |
| `deaths.` | `death_rows` | `deaths.single.`, `deaths.chain.`, `deaths.repeat.`; `deaths.total` was already taken as decomposition |
| `compare.deaths` | `death_rows` | |
| `time.gap.` | `route_rows` | |
| `compare.downtime` | `route_rows` | |
| `compare.route.` | `route_rows` | skipped, extra, summary, order, unaligned |
| `compare.speed.unavailable` | `route_rows` | The reason line's own finding, placed on the tab it explains |
| `trash.` | `route_rows` | `trash.overage`, `trash.pull.` |
| `compare.confound.` | `route_rows` | |
| `interrupts.` | `interrupts` | |
| `compare.interrupts` | `interrupts` | |
| `compare.parse.unavailable` | `group_rows` | The comparison rows it explains sit on the subject's card, on this tab |
| `defensives.` | `group_rows` | Rate and `defensives.ceiling.` — after the death families above |
| `throughput.` | `group_rows` | Alignment and ceiling |

The table is documented the way `NESTS_INSIDE` is, with the one difference stated: its entries
deliberately overlap, so **order is the rule** and the narrow death families come first. A test
places one finding from every family the analysers emit and asserts the field each lands in
(§7.2).

A timed row keeps its `seconds` wherever it lands. There is no longer a page-wide ranked list;
the ranking is visible in the Summary's pointers and, within a tab, in the order the rows arrive.

### 5.2 Pointers keep the ranking that already exists

The CLI ranks the merged analysis and comparison findings once, with `rank_findings`, before the
builder sees them: timed findings by seconds descending, untimed last. The builder takes the
first five timed findings that are not decomposition rows, in that order, and does not re-sort.
One ranking authority. Fewer than five when fewer exist; none when none exist, and the Summary
then omits the "Biggest losses" heading rather than rendering an empty list.

A pointer is the same `LedgerRow` object as its card, so its title, seconds and badge cannot drift
from what the card says.

### 5.3 The Route section

`route` is built with the same `_section_for` call and the same speed-unavailable finding as the
timeline. When a speed reference is absent, the Route & tempo panel opens with the reason in the
`withheld` style, and the gap and trash rows that need no reference follow beneath it. Provenance's
"withheld" list gains the matching line, as it does for the timeline.

## 6. Template and CSS

- The tab bar is a `<nav>` of `<button type="button">` elements, each carrying the id of the panel
  it controls in a data attribute. Each panel is a `<section>` carrying the tab-group marker and
  its own id. Buttons, not links, so that the no-script page carries no dead controls: the bar is
  hidden without the script, and a link would still have been a link.
- Three CSS rules do the visibility work, all scoped under the root class the script adds: hide
  an inactive panel; show the tab bar; style the active button. No `hidden` attribute and no
  inline `display` anywhere in the rendered HTML.
- The active tab is marked by an underline and a bold weight as well as a colour, keeping the rule
  that no colour carries meaning alone.
- The "Not additive — never sum" sentence renders as static text at the head of every panel that
  holds timed rows: Summary, Route & tempo, Deaths. It is the same sentence in three places
  because the rows it guards are now in three places.
- The pointer macro renders a title, a seconds figure and a badge on one line, the whole line a
  fragment link to the card's anchor, and uses no `<h3>`. The once-only invariant is anchored on
  `<h3>` and must not see a second heading.
- `nests_inside` text is unchanged and may name a title that lives on another tab. It is a
  cross-reference in words, and the parent's card is one click away.
- Palette tokens, fonts, card styling: unchanged.

## 7. Testing

Weight stays on the view model, as the report design fixed. The HTML invariants are rewritten
deliberately where the design changed, and left alone where it did not.

### 7.1 Invariants rewritten

- **The page executes only its own script**, replacing "no `<script>`": exactly one `<script>`
  element; it has no `src`; its text contains none of `fetch`, `XMLHttpRequest`, `import(`,
  `document.write`, `innerHTML`, `textContent`, `localStorage`, `sessionStorage`, `eval`,
  `WebSocket`. The existing `@import`, `<link rel=` and external-`src` checks stay.
- **The section-order test** keeps its heading list and gains the panel ids in tab order; both
  sequences must be monotonic in the rendered string.
- **The section-count tests** count panels and headings against the new structure: six panels
  always; the heading count with and without a narrative stated as two numbers the test names.
- **The golden file** is regenerated with `--golden-update` and its diff read in full during the
  plan, since the skeleton changes. It stays tiny.

### 7.2 Invariants added

- **The page hides nothing before the script runs**: no `hidden` attribute, no inline
  `display:none`, and the panel-hiding rule appears only inside a selector that begins with the
  root class.
- **Every pointer targets an anchor that exists** on the page, and no pointer targets a
  decomposition row.
- **The pointer macro emits no `<h3>`**, so the once-only test keeps its meaning.
- **Every family lands where the table says**: one finding per family the analysers emit today,
  asserting the field for each, plus one unknown family asserted to reach the catch-all. The test
  cannot know about a family a later analyser adds; what protects that case is §2 — the catch-all
  sits on Summary, where an unhomed family is seen, not dropped.

### 7.3 Unchanged

Every finding reaches the page once; every href is a fragment or a report link; every withheld
section gives a reason; no total row and no numeric field off the allowlist. The death-card tests
and the player-card tests keep passing as written.

### 7.4 View-model tests

`summary_pointers` takes the first five timed non-decomposition rows in the given order, fewer
when fewer exist, none when none; each new field's membership from §5.1; `route` withheld with the
speed-unavailable reason and present otherwise; the catch-all still receives an unknown family.

### 7.5 The browser check

The script's behaviour has no automated test — decided 2026-09-06 (§10). It is verified by hand in
the plan's final real-run task, in the browser pane, with these steps and their outcomes recorded
in the plan's ledger:

1. Open the regenerated real report. Summary is open; the other panels are hidden.
2. Click each tab in turn; exactly one panel is visible after each click, and the fragment names
   it.
3. From a card on Route & tempo, click a badge; the Provenance tab opens at the legend.
4. From Summary, click a pointer; the tab holding its card opens and the card is in view.
5. Reload with `#deaths` in the URL; the Deaths tab is open on load.
6. Disable scripting for the page (the browser pane's or a browser's setting) and reload; the tab
   bar is absent and every panel is visible, stacked in tab order.

A step that fails is recorded as a failure, not smoothed over.

## 8. Amendments to other documents, made in the same plan

- Report design **§11** is superseded, with §1's argument; **§9**'s "no `<script>`" bullet becomes
  the executes-only-its-own-script rule; **§4** and **§5** gain the fields of §4 above and the tab
  table of §2; **§10** gains §7's invariants. Each amendment dated 2026-09-06 and pointing here.
- The postmortem design's **§7** (report) gains one dated sentence saying the page is tabbed and
  where the rule lives.
- `.claude/skills/mplus-analysis/SKILL.md` gains one paragraph saying which tab renders which
  family, so the narrative's author knows where a reader will find each claim.
- `.claude/skills/analyzing-a-run/SKILL.md`: no flag changes, so no amendment.

## 9. Out of scope, deliberately

- Per-player sub-tabs and their content: Phase J. §3 keeps the door open; nothing is built behind
  it.
- The death recap: Phase I. The Deaths tab holds today's cards.
- Storing the chosen tab anywhere but the URL fragment.
- A print stylesheet, a theme toggle, a table of contents, collapsible cards. The tab bar is the
  navigation; nothing else is added.
- The rate-limit reading on the Provenance tab, which the roadmap's tab table suggested. `analyze`
  prints the points it spent, but no domain object carries that number and the builder performs
  no I/O; adding it is a small design question of its own.
- The Holy Armaments charge-pool question raised by the standby session's brief. It is throughput
  data, not report structure, and needs a schema decision of its own.
- The main checkout's `out/` still holds the pre-Phase-G page. The plan's real-run task overwrites
  it.

## 10. Decisions this design records

1. **Tabs via a small inline script with a no-script fallback**, not CSS-only `:target` tricks.
   Roadmap §5 item 1, taken 2026-09-06. The CSS route cannot nest and cannot open a tab from a
   badge link without losing the fragment; the script route can, and its whole surface is show
   and hide.
2. **The Summary points at losses and never repeats a card.** A finding's card lives on its home
   tab only. Pointers are compact lines that link to it. Every-finding-once stays anchored on
   card headings.
3. **The Players tab holds today's cards** and the script is generic. Nothing is built that Phase J
   might reshape.
4. **The catch-all sits at the bottom of Summary.** The tab that must lose nothing is where an
   unhomed family surfaces.
5. **Typed fields per tab, not a generic `Tab` container.** The sections are different shapes; a
   generic container would push shape-dispatch into Jinja and invalidate every builder test for
   no reader-visible gain.
6. **Behavioural coverage of the script is by invariant plus a recorded browser check**, not by a
   second toolchain. Forty lines of show-and-hide do not justify Node or a browser download in a
   uv-only repository. Revisit if the script ever grows past that.

## 11. Known gaps, carried forward

- The script's click behaviour is verified by hand, not by a test that runs in `pytest`. §7.5
  says how, and §10 item 6 says when to change that.
- `nests_inside` may name a parent on another tab in words alone. A visual hierarchy across tabs
  is not attempted; the report design's §14 already carries the nesting-as-text gap.
- A reader who lands on the page with a fragment naming an element that no longer exists sees
  Summary, silently. The script does not report a stale anchor; there is nothing on the page it
  could honestly say.
