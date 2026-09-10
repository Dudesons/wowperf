# Mythic+ Post-Mortem: The HTML Report — Design

**Status:** Approved and implemented 2026-09-05. Amended since for tabs, the death recap and
spell icons; each amendment is dated in place.

**Authority:** `docs/plans/2026-09-03-mplus-postmortem-design.md` §7 fixes the technology and the
eight sections and remains binding. This document refines §7 into something implementable and
records the four decisions §7 left open. Where the two disagree, this one is newer and wins; a
disagreement worth keeping is amended back into §7.

**Depends on:** Plans A (`62fd0e4`), B (`eae5238`), C (`71b10f7`) and D (`f39976c`), all merged.

**Not in scope:** design §8, the inference layer — the three skills and the narrative's authorship.
This document covers only how a narrative, once written, reaches the page. §8 gets its own design
and its own plan.

---

## 1. What the report is

One self-contained HTML file, written beside the findings JSON every time `analyze` runs. It must
open from disk with no network, survive being posted to Discord, and be readable on a phone
screenshot. No content delivery network, no external font, and one inline `<script>` that only shows and
hides (*amended 2026-09-06*, see §9 and `2026-09-06-report-tabs-design.md` §3).

Its reader is a person deciding what to practise next. The findings JSON serves a different
reader — Claude, writing the narrative — and the two must not be collapsed into one artifact.

## 2. Architecture

Three units, one direction of flow, no cycles.

| Unit | Responsibility |
| --- | --- |
| `src/wowperf/domain/report/model.py` | The `Report` value object and the sub-values it holds. Pure data, already formatted: strings final, numbers rounded, order decided. |
| `src/wowperf/domain/report/build.py` | `build_report(...) -> Report`. Every judgement about what appears where. Pure, no I/O. |
| `src/wowperf/adapters/render/html.py` | `render(report: Report) -> str`. Jinja2 lives here and nowhere else. |

**The template may not reach past the `Report`.** It loops, escapes and interpolates; it decides
nothing. This is the boundary that keeps judgement out of Jinja, where it cannot be unit-tested.

`build_report` is a domain function and therefore performs no I/O, imports no `jinja2`, and reads
no file. The narrative arrives as a string the CLI has already read.

### 2.1 Signature

```python
def build_report(
    loaded: LoadedRun,
    findings: Sequence[Finding],
    speed: SpeedReference | None,
    parse: ParseReference | None,
    narrative: str | None,
) -> Report
```

It calls `align_pulls(loaded.run, speed.loaded.run)` itself when a speed reference is present.
`align_pulls` is already a pure function of two `Run`s, so `compare()` needs no change to expose
its `Alignment`.

## 3. The per-player numbers already exist

An earlier draft of this design called for extracting a `player_facts` function from
`analyse_players`. **That was wrong: the function is already there.**
`summarise_players(run, casts, deaths, interrupts) -> tuple[PlayerSummary, ...]` in
`src/wowperf/domain/analysis/players.py` is public, pure, and returns exactly what the cards need:

```python
class PlayerSummary(Frozen):
    name: str
    actor_id: int
    class_name: str
    spec: str
    casts_in_pulls: int
    active_seconds: float
    activity_percent: float
    interrupts: int
    deaths: int
```

`build_report` calls it directly. No refactor, no second definition, and one fewer task.

### 3.1 There is no "avoidable damage", and the cards must not claim one

Design §7 lists "avoidable damage" among the per-player card's fields. `players.py` refuses that
framing on purpose — its own header reads "Damage taken is stated against the group median, never
as 'avoidable damage'" — because **the log does not record whether a hit could have been dodged**.
Its finding says "took 2.3x the group median from Frigid Roar" and states in the same breath that
this is a difference, not a mistake.

The card follows the analyser, not §7. It shows the player's damage outliers as
`players.damage.*` already words them, with the same caveat. A card headed "avoidable damage" would
be the tool asserting something it cannot know, about a named person, on a page they will read.
§7 is amended to say so when this design is committed.

## 4. The view model

Sketched to fix names and shapes; an implementation plan may add a field it turns out to need, but
not a method. Every type is `Frozen` with tuple fields, like the rest of the domain.

```python
class SectionState(StrEnum):
    PRESENT = "present"      # has data, renders normally
    WITHHELD = "withheld"    # renders its heading and a reason

class Section(Frozen):
    state: SectionState
    reason: str = ""         # non-empty exactly when state is WITHHELD

class Badge(Frozen):
    label: str               # "measured" | "derived" | "inferred"
    tint: str                # a palette token name, never a raw colour

class LedgerRow(Frozen):
    finding_id: str
    title: str
    detail: str
    badge: Badge
    seconds: str | None      # formatted, e.g. "1:42" — None when seconds_lost is None
    nests_inside: str | None # the finding id this one is contained by, or None

class TimelineBlock(Frozen):
    label: str               # pack or boss name, for the SVG <title>
    x: float                 # already scaled to the viewBox
    width: float
    is_boss: bool
    kind: str                # "matched" | "extra" | "skipped"

class TimelineTrack(Frozen):
    caption: str             # "Ours — 31:48"
    blocks: tuple[TimelineBlock, ...] = ()

class Timeline(Frozen):
    section: Section
    ours: TimelineTrack | None = None
    theirs: TimelineTrack | None = None
    ticks: tuple[tuple[float, str], ...] = ()   # (x, "10:00")
    width: float = 0.0
    height: float = 0.0

class DamageRow(Frozen):
    seconds_before: str      # "-6.2s"
    source: str
    ability: str
    amount: str

class DeathCard(Frozen):
    player: str
    class_name: str
    when: str                # "12:04, pull 5"
    killing_blow: str
    last_ten_seconds: tuple[DamageRow, ...] = ()
```

*Amended 2026-09-07:* `DamageRow` and this `DeathCard` are superseded by the recap card of
`2026-09-07-death-recap-design.md` §5: a `RecapRow` timeline with a reconstructed health column,
three `AvailabilityGroup`s (own defensives, consumables, teammates' externals) of four-state
`AvailabilityRow`s, and one return line with its badge. `Provenance` gains `methods`, the
sentences a reader might dispute, stated once — today the health reconstruction.

```python
class PlayerCard(Frozen):
    name: str
    class_name: str          # rendered as text, never colour alone
    spec: str
    colour: str              # palette token for the class
    casts_summary: str       # "182 casts in 31:49 of pulls"
    # *Amended 2026-09-05:* not `active_time` as a percentage. `active_seconds` is
    # `casts_in_pulls` at one modelled second per cast, a deliberately coarse floor, so a fast
    # caster exceeds both the pull time and 100% activity on the reference run. The card states
    # the cast count over the pull time instead, and drops the derived share. See postmortem
    # design §7 item 7.
    deaths: int
    kicks: int
    # Damage outliers as `players.damage.*` words them: a multiple of the group
    # median, never "avoidable". See §3.1.
    damage_rows: tuple[LedgerRow, ...] = ()
    spell_and_talent: Section          # WITHHELD without a parse reference
    spell_and_talent_rows: tuple[LedgerRow, ...] = ()

class Header(Frozen):
    dungeon: str
    keystone_level: int
    affixes: tuple[str, ...]
    result: str              # "Timed by 2:14" | "Depleted by 4:31"
    warnings: tuple[str, ...] = ()
    # No percentile field: see §5.1. Nothing this project fetches can produce one.

class Provenance(Frozen):
    report_code: str
    fight_id: int
    fetched_at: str
    speed_reference_url: str | None
    parse_reference_url: str | None
    withheld: tuple[str, ...] = ()   # one line per section that could not render

class Report(Frozen):
    header: Header
    narrative: str | None
    ledger_decomposition: tuple[LedgerRow, ...]
    ledger_losses: tuple[LedgerRow, ...]
    timeline: Timeline
    deaths: tuple[DeathCard, ...]
    interrupts: tuple[LedgerRow, ...]
    players: tuple[PlayerCard, ...]
    provenance: Provenance
```

*Amended 2026-09-06:* `ledger_losses` is gone. `Report` carries `summary_pointers`, `route`,
`route_rows`, `death_rows` (formerly `death_findings`) and `group_rows` instead, all tuples of
`LedgerRow` except `route`, a `Section`. Every ranked loss lives on the tab that owns its family
and keeps its seconds there; the Summary points at the biggest five. See
`2026-09-06-report-tabs-design.md` §4 and §5.

## 5. The eight sections

Every section always appears. A section with no data renders its heading and one sentence saying
why, taken from the `compare.*.unavailable` finding the tool already emits — so the reason is
reported, never invented by the template.

| # | Section | Fed by | Withheld when |
| --- | --- | --- | --- |
| 1 | Header | `Run` fields | Never — but see §5.1, the percentile line is not built |
| 2 | Narrative | the `--narrative` file | No `--narrative` given: the section is absent, not withheld (nothing was withheld; nothing was asked for) |
| 3 | Seconds ledger | `time.*`, `deaths.*`, `interrupts.*`, `trash.*`, `defensives.*`, `compare.*` | Never — analysis always runs |
| 4 | Aligned timeline | `Alignment` from `align_pulls` | No speed reference. Reason from `compare.speed.unavailable` |
| 5 | Deaths | `loaded.deaths` and `loaded.damage_taken` | Never |
| 6 | Interrupts | `interrupts.ability.*`, `interrupts.summary` | Never |
| 7 | Per-player cards | `summarise_players` and `players.damage.*`; comparison rows from `compare.spells.*`, `compare.talents`, `compare.uptime.*` | The comparison rows only, without a parse reference. Reason from `compare.parse.unavailable` |
| 8 | Provenance | `Run`, both references, and the list of everything withheld | Never |

*Amended 2026-09-05:* a ninth section, "Other findings", renders between 7 and 8. See §5.2.

*Amended 2026-09-06:* the Deaths section also places the `defensives.unused.*`,
`consumables.unused.*` and `consumables.never.*` findings, as rows beneath the cards. On a real
run the catch-all repeated each card's one-line claim as a full card with a three-sentence caveat,
six times over. A finding placed under Deaths is claimed like any other and reaches the page once;
the section count does not change.

Section 2 is the one exception to "always appears", and deliberately: a report generated without
`--narrative` has not withheld anything. So the report renders ~~eight~~ **nine** sections with a
narrative and ~~seven~~ **eight** without, and §10's invariant is worded to match. *Amended
2026-09-05:* a ninth section was added after this design was approved. See §5.2.

*Amended 2026-09-06:* the sections are grouped under six tabs — Summary, Route & tempo, Deaths,
Interrupts, Players, Provenance — and a tenth section, "Route and tempo", holds the route, gap,
downtime, trash and confound findings that the ledger of losses used to rank on one list. The
Summary's "Biggest losses" heading appears only when a timed loss exists. Which section sits
under which tab is fixed in `2026-09-06-report-tabs-design.md` §2; the heading count in §10 is
superseded by that document's §7.1.

*Amended 2026-09-07:* row 5 is fed by `loaded.deaths`, `loaded.damage_taken`, `loaded.healing`,
`loaded.health_samples`, `loaded.resurrections`, and the defensives, consumables and externals
data files. See `2026-09-07-death-recap-design.md`.

### 5.1 The header's percentile is not built, and why

Design §7 lists "parse percentile as triage" in the header. **Nothing this project fetches can
produce it.** `WclRankingRepository.top_parses` returns the leading rows for a specialisation; it
does not return our own player's rank among them, and our subject's own score appears nowhere in
`LoadedRun`. Computing a percentile from the top rows alone would be an invented number.

Getting it would need a new leaderboard query scoped to our own character, and — after Plan D
shipped a whole half-feature on a schema claim that was written down as verified without ever being
run — that query gets a live verification pass and a recorded date before any code depends on it.
That is a plan of its own, not a line item in this one.

So the header carries dungeon, keystone level, affixes, result and warnings, and no percentile. This
is a deliberate omission from an approved design; §7 is amended to say so when this design is
committed.

### 5.2 A ninth section: observations *(amended 2026-09-05)*

On the first real run this branch analysed, four of twenty-six findings — three `trash.pull.*`
and one `defensives.<player>.<ability>` — matched no section's id-prefix whitelist and were
silently dropped (final whole-branch review, Ruling N). A prefix list is not a stable partition:
any analyser family absent from it disappears from the page without a trace, and Plan D's entire
defensives analyser was one such family with nowhere assigned to go.

The fix is structural rather than another whitelist entry: `build_report` computes the set of
finding ids every other section actually placed and routes everything left over into a new
"Other findings" heading, positioned after the per-player cards and before provenance. The report
therefore renders **nine** sections with a narrative and **eight** without — this design's "eight
sections" (§5) and §10's invariant are both superseded by that count.

## 6. The aligned timeline

Two horizontal tracks on one shared elapsed-time axis. Ours above, the reference below. Blocks are
pulls drawn to real duration; **the space between blocks is travel**, which is what makes this
layout worth its cost — every analyser since Plan B has been saying travel is where the time goes,
and no per-pull table shows it.

- The axis is scaled to the longer of the two runs, so both fit and the shorter one visibly ends
  early.
- Boss pulls carry a stroke; trash does not.
- A pack only we pulled is tinted as an addition. A pack only they pulled is drawn as a dashed
  outline on their track.
- ~~Matched boss pulls are joined by a faint tie, so cumulative drift reads as the ties
  fanning.~~ *Amended 2026-09-05:* not built. The implementation plan never asked for it, and its
  absence went unrecorded until this amendment — it stayed unbuilt through every task of this
  branch's execution.
- Pack names do not fit inside thin blocks and are not attempted. Each block carries an SVG
  `<title>` child, so a name appears on hover when the file is opened. **A screenshot loses the
  names, which is accepted:** the section's job is showing where time went, and section 4's detail
  is available in the route findings the ledger already lists.

All geometry is computed in `build_report` and arrives at the template as numbers. The template
emits `<rect>` elements from a loop and does no arithmetic.

## 7. The seconds ledger is not a sum

The findings JSON already carries this warning, and the report must obey it:

> findings are ranked by `seconds_lost`, not additive: `compare.duration` is the total gap against
> the reference and already contains every other `seconds_lost` figure; `time.gap.*` and
> `compare.downtime` both nest inside `time.residual`; `deaths.single`/`chain` nest inside
> `deaths.total`; and `compare.route.skipped.*` overlaps the waste `trash.overage` already reports.

A section called a ledger invites a total row. **There is no total row**, and no arithmetic over
`seconds` anywhere in the template or the view model. The section renders in two parts:

1. **Decomposition** — where the run's time went, at one level only.
2. **Ranked losses** — each loss with its badge and its seconds, and, where it nests inside
   another, a plain line saying so (`LedgerRow.nests_inside`).

Printing a total here would produce a number larger than the run itself. Plan C's final review
caught exactly that arithmetic in the JSON; the report is where a reader would actually believe it.

## 8. Command surface

```
analyze <url> [--player NAME] [--no-compare] [--narrative notes.md]
```

`analyze` writes both artifacts every time: `<code>-<fight>.findings.json` and
`<code>-<fight>.html`. There is no separate `report` command and no opt-in flag — the report is the
deliverable for a human reader, and burying it behind a flag or a second entry point invites the
two to drift apart.

The workflow is two passes. The first writes the JSON; Claude reads it and writes a narrative; the
second pass adds `--narrative notes.md` and re-renders. **The second pass spends no quota** — every
response it needs is already in the disk cache.

A `--narrative` path that does not exist or cannot be read is an error raised **before any
fetching**, so a typo costs nothing and never silently produces a report missing its narrative.

## 9. Rendering rules

- **Dark palette, fixed in the file.** This is a standalone artifact posted into a chat client, not
  a page that can consult a reader's theme. Colours are declared once as CSS custom properties at
  the top of the document.
- **No colour carries meaning alone.** Confidence badges are a text label with a tint, never a tint
  alone. Player cards print the class name beside the class colour. Several class colours are hard
  to tell apart, and reports get screenshotted and recompressed.
- **Charts are server-generated inline SVG.** No charting library. Output is deterministic, which is
  what makes the golden file in §10 possible.
- **Self-containment is a hard rule**: no `src` or `href` to any external origin, no webfont, and
  exactly one `<script>` — inline, with no `src`, and restricted to showing and hiding sections.
  System font stack only. §10 tests this directly rather than trusting it. *Amended 2026-09-06:*
  this bullet said "no `<script>`" until the report grew to sixty-seven cards; see
  `2026-09-06-report-tabs-design.md` §1 and §3 for the script's four duties and its no-script
  fallback.

## 10. Testing

Weight sits on the view model, because that is where the judgement is.

**View model** — exhaustive unit tests of `build_report`: each section's `PRESENT` and `WITHHELD`
state, the reason text sourced from the right finding, timeline geometry for a matched pull, an
extra pack and a skipped one, the ledger's two parts and its `nests_inside` links, a run with no
deaths, a run with no boss pulls.

**HTML by invariant** — parse the rendered string and assert:

- exactly one `<script>` element, inline, and its text free of anything that fetches, writes
  text or reads storage; no `src` or `href` whose value is not a fragment or a Warcraft Logs
  report link (*amended 2026-09-06*, see `2026-09-06-report-tabs-design.md` §7.1);
- the rendered page hides nothing before the script runs, every Summary pointer targets an
  anchor that exists, and every finding family lands on the tab the builder's table says
  (*added 2026-09-06*, ibid. §7.2);
- every section present and in order — ~~eight~~ **nine** when a narrative was supplied, ~~seven~~
  **eight** without it (*amended 2026-09-05:* a ninth section, "Other findings", was added after
  this design was approved; see §5.2);
- every finding id in the input appears in the output;
- every withheld section renders a non-empty reason.

The ledger's no-total rule is enforced where it can be: `Report` exposes no total field, and a test
asserts the ledger template renders no `sum`, `+` or accumulator over `LedgerRow.seconds`. Asserting
on the rendered string that "no number is a total" is not possible, so the rule is enforced by the
absence of anything to total with.

**One golden file** — over a deliberately tiny fixture: two pulls, one player, one finding. Small
enough that a diff is reviewable, which is the whole point. A full-page golden over a realistic run
is rejected: it would churn on every CSS edit and train everyone to approve it unread.

**End to end** — render the reference report and assert the written file opens and contains no
external reference. Marked `e2e`, deselected by default, like the rest.

## 11. Out of scope, deliberately

~~No table of contents, no print stylesheet, no interactivity, no collapsible sections, no theme
toggle, no chart library, no pagination. If the report ever needs navigation, that is evidence it
has grown too long, and the answer is to cut it rather than to add a contents list.~~

*Superseded 2026-09-06.* The first real run rendered sixty-seven cards that different readers
need different parts of, and cutting would remove something one of them came for. The page is
grouped under six tabs by `2026-09-06-report-tabs-design.md`, whose §1 restates the rule this
section was protecting: "the template decides nothing" is about judgement, and navigation is not
judgement. Still out of scope: a print stylesheet, a theme toggle, a chart library, pagination,
collapsible cards, and storing the chosen tab anywhere but the URL fragment.

## 12. Carried forward into this plan

`analysis/timeline.py:88` and `analysis/trash.py:73` still print a raw `map position x=…, y=…` with
no pack name. Plan C fixed the same problem in `comparison/route.py` by leading with the pack name,
and its final review accepted the inconsistency for that branch. These strings are about to be read
on a page rather than in a JSON blob, so this plan aligns all three.

## 13. Decisions this design records

1. **The renderer consumes a purpose-built view model**, not the domain objects and not the findings
   JSON. The JSON cannot render sections 4, 5 or 7 — it carries no `Alignment`, no damage events and
   no per-player numbers — and widening it to serve the template would degrade the artifact Claude
   reads. Passing the domain objects instead would move formatting and filtering into Jinja, where
   they cannot be tested.
2. **`analyze` always writes both artifacts.** One command, one code path, and an HTML file that can
   never be stale relative to its JSON.
3. **A section with no data keeps its heading and states the reason.** Omitting it would make "no
   data" indistinguishable from "found nothing", which is the ambiguity the confidence badges exist
   to prevent. Rendering half of it would need two layouts per degradable section for a gain the
   route findings already deliver in text.
4. **The timeline is two tracks on one clock**, not a per-pull table. It is the only layout that
   shows travel, and travel is what this tool has been measuring since Plan B.
5. **Testing weight sits on the view model**, with the HTML asserted by invariant and one tiny golden
   file. A realistic-run golden file is worse than no test, because nobody reads a 2000-line diff
   twice.

## 14. Known gaps, carried forward

- **Pack names are lost in a screenshot.** They live in SVG `<title>` tooltips, which need the file
  open. Accepted in §6; revisit only if screenshots turn out to be how the report is actually read.
- **The report renders one subject player's comparison**, matching every comparison shipped so far.
  A group-wide view is slice 4.
- **The seconds ledger's nesting is expressed as text**, not as a visual hierarchy. A treemap or a
  nested bar would show containment better and is a candidate for a later plan; the text line is
  what stops the reader summing, which is the part that matters now.
