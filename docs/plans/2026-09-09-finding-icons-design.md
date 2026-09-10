# Spell Icons on Findings — Design

Approved and implemented 2026-09-09. Extends the shipped death-card icon feature to the
sections rendered from `Finding`.

Companion documents, both current:

- `docs/plans/2026-09-09-report-icons-design.md` — the shipped icon spec. Its port, resolver,
  store and CSS mechanism are reused here unchanged; this document does not restate them.
- `docs/plans/2026-09-08-icons-and-tooltips-spike.md` — the measured evidence underneath both.

## 1. What this builds

An icon beside every spell a finding names, drawn inline at the ability's own words rather than
at the start of the row.

Today icons appear on death cards and nowhere else. A live run of `6Kx1P9GbNXrcLdHa` fight 36
draws 189 of them, all inside the Deaths section; every other section renders from `Finding` and
carries none.

## 2. What already exists and is not rebuilt

The whole resolution and drawing machinery shipped with the previous slice and is reused as-is:

- `IconSource` in `src/wowperf/domain/ports.py` — `data_uri(ability_id: int) -> str | None`.
- `BlizzardIcons`, `IconStore` and `icon_filename` in `src/wowperf/adapters/render/icons.py`.
- `render(report, icons=None)` and `_icon_uris` in `src/wowperf/adapters/render/html.py`.
- One CSS rule per distinct icon in `report.html.j2`, `.icon` sizing in `report.css.j2`.
- `build_icons` in `src/wowperf/cli.py`, the only network surface.

No new Warcraft Logs query is added. Every ability named by a finding is already in an ability
dictionary the tool fetches.

## 3. Scope — the twelve sites

Every `Finding` whose title names one ability, verified by parsing the domain's syntax tree:

| Site | Title shape | Where the id comes from |
| --- | --- | --- |
| `analysis/interrupts.py:173` | `{name} landed {n} times` | `ability_id`, the loop variable |
| `analysis/defensives.py:234` | `{player} used {ability} {n} of a possible {m} times` | `ability.ability_id` |
| `analysis/defensives.py:259` | `{player} never cast {ability}` | `ability.ability_id` |
| `analysis/throughput.py:255` | `{player} used {ability} {n} of a possible {m} times` | `ability.ability_id` |
| `analysis/deaths.py:151` | `{player} died to {killing_blow}` | `Death.killing_blow_id` |
| `analysis/players.py:220` | `{player} took {x}x the group median from {ability}` | the damage outlier's id |
| `comparison/spells.py:108` | `{them} cast {name} {n} times on bosses; {us} never cast it` | `ability_id`, unpacked |
| `comparison/spells.py:144` | `{them} cast {name} {r} times a minute…` | `ability_id`, unpacked |
| `comparison/spells.py:249` | `{q} top parses cast {name} on bosses…` | `ability_id`, unpacked |
| `comparison/spells.py:304` | `{n} top parses cast {name} a median {r}…` | `ability_id`, unpacked |
| `comparison/uptime.py:119` | `{them} kept {name} up for {p} of boss time…` | `ability_id`, unpacked |
| `comparison/uptime.py:312` | `{n} top parses kept {name} up a median {p}…` | `ability_id`, unpacked |

No site needs a new lookup: every one of them already holds the ability's id in a local.

`analysis/players.py:220` is the one to check while implementing — its title interpolates a bare
name, and whether the id travels beside it must be confirmed in `_damage_outliers` rather than
assumed.

## 4. Excluded, and why

- **`analysis/consumables.py:202`** joins several category names — `"used no health potion or
  healthstone"`. A `ConsumableCategory` is a cooldown group holding several ability ids and none
  of them is the item, so there is no honest icon. This matches the previous slice's exclusion of
  consumable rows on death cards.
- **The detail paragraph and the evidence bullets.** Both repeat the ability's name. One icon per
  card is the claim; a second is noise.
- **`analysis/deaths.py:98` and `comparison/service.py:28`** construct a `Finding` from a `title`
  variable rather than a literal. Both were read: the first is a death-count sentence, the second
  the generic "could not be compared" helper. Neither names an ability.
- **Speed references.** Every title in `comparison/route.py` and `comparison/tempo.py` names
  packs, seconds, deaths or kicks. None names an ability, so the speed sample carries no icons.

## 5. The domain change

`Finding` gains two optional fields:

```python
ability_id: int | None = None
ability_name: str = ""
```

Both stay unset on the findings that name no ability, so the ~38 other construction sites are
untouched.

`ability_name` is redundant with the title in principle and exists so that locating the spell is
never a guess about which words are the spell. The identity always comes from `ability_id`; the
name is only ever used to find a substring already known to be there.

`Finding.title` stays a single string. That is the property that keeps this affordable: the
findings JSON, the digit-free narrative guardrail and `titles_by_id` are all unaffected.

## 6. The split rule

Performed in `ledger_row()` at `src/wowperf/domain/report/ledger.py:77` — the one function every
finding passes through on its way to the page.

> When `ability_id` is set and `ability_name` occurs **exactly once** in `title`, split the title
> there. Otherwise emit the title whole and draw no icon.

Zero occurrences means the analyser and its own title disagree. Two means the reader cannot be
told which is meant. Both fall back to today's rendering, which is correct and merely plainer —
the same silent, meaning-preserving failure every other icon miss already uses.

This is not identity recovered from prose. The id is known outright; the name locates a substring
for presentation, and refuses when it cannot do so unambiguously.

## 7. The view model

`LedgerRow` keeps `title` and gains four fields:

```python
title_before: str = ""
title_ability: str = ""
title_after: str = ""
ability_id: int | None = None
```

With no icon, `title_before` carries the whole title and the other two are empty, so the template
renders one shape rather than branching on two.

`title` is kept rather than replaced because it has two renderers, not one. The full card at
`_macros.html.j2:9` draws the split form with its icon; the compact summary pointer at
`_macros.html.j2:27` draws `title` whole and carries no icon, which is correct — a one-line
cross-reference should not sprout art.

Two representations of one sentence is a seam that goes stale, so it is closed by an invariant
rather than by discipline: **`title_before + title_ability + title_after == title` for every row**,
asserted over every `LedgerRow` a real report produces. Concatenation, not reconstruction — the
split never rewrites the sentence, it only cuts it.

`LedgerRow.ability_id` is a new numeric view-model field and needs its entry in
`NUMBERS_THAT_ARE_NOT_TOTALS` in `tests/adapters/render/test_html_invariants.py`, with a written
reason. `Finding.ability_id` needs none: that allowlist walks view-model types, and `Finding` is
domain.

## 8. The template

In the `ledger_row` macro in `src/wowperf/adapters/render/_macros.html.j2`:

```jinja
<h3>{{ row.title_before }}{% if row.ability_id in icons_by_id %}<span
  class="icon i-{{ row.ability_id }}" aria-hidden="true"></span>{% endif %}{{ row.title_ability }}{{ row.title_after }}</h3>
```

The same membership test, span, class and `aria-hidden` as the death cards. Nothing new enters the
rendering layer, and no `|safe` is needed anywhere.

The summary-pointer macro at `_macros.html.j2:27` is left exactly as it is, still rendering
`{{ row.title }}`. Pointers are compact cross-references into other sections; the icon belongs at
the finding itself.

Placing the icon inside the sentence avoids the ragged left edge that an icon leading a column
produces. A finding without an icon reads as an ordinary sentence, so the open question on the
Defensives list does not recur here.

## 9. The two icon maps

**Ours** is `LoadedRun.ability_icon_map`, already built from our report's `masterData.abilities`.

**The parse references** need a thread pulled through three points, each one line:

1. `adapters/wcl/repository.py:331` — the `parse`-profile `LoadedRun` is built as
   `LoadedRun(run=run, casts=...)`. The `ability_icons` tuple is already computed at line 308,
   before the profile branch. Pass it.
2. `domain/comparison/sample.py:46` — `ParseMember` gains
   `ability_icons: tuple[tuple[int, str], ...] = ()`.
3. `cli.py:401` — the `ParseMember(...)` construction passes `ability_icons=theirs.ability_icons`.

The CLI merges before constructing the resolver: reference pairs as the base, ours overlaid, so
ours wins a collision. A collision is the same ability id naming the same file, so the rule
matters only for determinism.

This is what makes the comparison findings work at all. They name abilities our player never cast,
which are therefore absent from our report's dictionary.

## 10. Reaching every row

`_icon_uris` walks `report.deaths` today. Findings live in nine places:

- seven on `Report` — `ledger_decomposition`, `summary_pointers`, `route_rows`, `death_rows`,
  `interrupts`, `group_rows`, `observations`
- two nested inside `PlayerCard` — `damage_rows` and `spell_and_talent_rows`
  (`domain/report/model.py:275,277`)

The nested pair is not a corner case: `spell_and_talent_rows` is where the `spells.py` and
`uptime.py` findings land, so half the new icons are there.

An id that reaches the view model without reaching `_icon_uris` produces no CSS rule, which means
no icon and no error — a silent hole. So a single helper in the domain yields every `LedgerRow` in
a `Report`, nested ones included, and `_icon_uris` consumes it instead of naming nine fields. The
helper iterates frozen models and performs no I/O.

## 11. Testing

- **The split rule**, three cases: the name once (split, icon drawn), zero times (whole title, no
  icon), twice (whole title, no icon). Asserted on rendered HTML, not only the view model, so the
  template's shape is pinned with the rule.
- **The enumeration guard.** Introspect `Report` and `PlayerCard` for every field annotated
  `tuple[LedgerRow, ...]` and assert the helper reaches all of them. A tenth section added without
  wiring fails this test rather than losing its icons quietly.
- **One test per icon site family** — an own-run finding and a comparison finding — using distinct
  ability ids, so a cross-site copy-paste fails rather than passes.
- **The merged map**: a comparison finding whose ability appears only in the reference dictionary
  still resolves.
- **The concatenation invariant** of §7, over every `LedgerRow` a real report produces — this is
  what keeps `title` and its three parts from drifting.
- **The summary pointer keeps its plain title** and emits no icon span.
- **Every new test proves it bites by mutation**: break the line it covers, run it, watch it fail,
  restore, record the output. Five of the previous slice's eight tasks failed their first review
  for tests that could not fail. This is written into the plan's steps, not left to judgement.

## 12. Invariants that stay binding

Already enforced by the suite; no task may weaken them.

- `tests/adapters/render/golden/minimal.html` stays byte-identical.
- A page rendered with no `IconSource` is byte-identical to a page rendered before this work.
- The page loads no external resource: no `url(http`, no `url(//`.
- `src/wowperf/domain/` performs no I/O.
- Autoescape stays on; no `{% set %}`, `|sum` or `sum(` in any template.
- Every finding keeps its `measured` / `derived` / `inferred` badge.
- The narrative contains no digits.

## 13. Measurements to take, not assert

After implementation, render the real report and report the numbers rather than asserting them,
as the previous slice did. A size assertion would fail on every unrelated change to the page.

- icons per section, before and after
- distinct icons embedded, and total spans
- external references, which must be zero
- CDN requests on a second run, which must be zero

Baseline from the live run on 2026-09-09: 234,571 bytes, 53 distinct icons, 189 spans, 0 external
references, 50 image files and 3 recorded misses on disk.

## 14. Deferred, with reasons

- **Sequential icon fetching.** A cold cache makes one `httpx.get` per icon, each building and
  discarding its own client, 30s timeout apiece, with no progress output, after "findings written"
  has printed. Typically seconds; a slow-but-accepting CDN gives roughly 26 minutes of apparent
  hang. This work adds a few dozen reference icons and so makes it worse. One shared client and a
  shorter timeout are two lines. Explicitly out of scope for this design, by decision.
- **The Defensives ragged edge.** Rows whose ability the report's dictionary never named sit 21px
  left of their iconed siblings on a death card. Unresolved, and untouched by this work, which
  does not reproduce it.
- **`IconStore.__init__`'s `mkdir`** runs outside the CLI's guarded region. Tracked separately.
- **Tooltips** and **reference-data staleness**, both from the previous slice's §14.

## 15. Open questions

None. Scope, placement, the split mechanism, the title-only rule and the merged reference map were
all settled before this document was written.
