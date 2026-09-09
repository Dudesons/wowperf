# Spell icons in the report — design

Written 2026-09-09. Supersedes nothing; it implements the first half of the recommendation in
`docs/plans/2026-09-08-icons-and-tooltips-spike.md` §9.

## 1. What this builds

A spell icon beside every ability the death card names, embedded in the page as bytes, so a
report opened in two years still draws them with no network.

Icons only. **No tooltips.** The spike measured the tooltip half and found its only complete
text source in conflict with three clauses of the ZAM EULA, so that decision is deferred to
its own slice with its own evidence (§14).

## 2. What this rests on

Three decisions already taken, recorded elsewhere, not reopened here:

- **Reports never leave this machine.** Every licensing judgement below depends on it.
- **Icon bytes come from Blizzard's render CDN, not Wowhead's.** Staying local answers the
  *distribution* objection for both, but ZAM's first clause restricts automated *retrieval*,
  which locality does not touch. Blizzard does not prohibit the mechanism, and without an API
  key the Developer API Terms never attach. The memory `report-icon-sourcing-decided` holds
  the full reasoning.
- **Embed, never hotlink.** Blizzard's CDN 403s some assets and lags on the newest ones, so a
  hotlinked report rots. For a local archive, still-opens-in-two-years is the whole value.

## 3. Scope: where an icon appears

| Site | Instances | Distinct | Included |
| --- | --- | --- | --- |
| Death recap event rows | 181 | 45 | yes |
| Availability — defensives | 11 | 9 | yes |
| Availability — teammates' externals | 9 | 3 | yes |
| Death card heading (killing blow) | 4 | 4 | yes |
| Availability — consumables | 8 | 2 | **no** |
| "Came back" sentence | 2 | 2 | **no** |
| Everything built from a `Finding` | 41 | — | **no** |

Counts are from `out/6Kx1P9GbNXrcLdHa-36.html`, a real four-death run.

**Consumables are excluded because they have no single ability id.** `ConsumableCategory` is a
name and a tuple of ids — "health potion" is a cooldown group, not an item. Picking one id from
the tuple would have the page assert an identity the data does not carry.

**The "came back" line is excluded** because it is one pre-formatted sentence; splitting it to
seat an icon buys two icons for a rewrite of the sentence the builder composes.

**Findings are excluded** because `Finding` carries no ability field. Adding one touches the
type every analyser emits, for 41 mentions of which several already appear elsewhere on the
page. That is a larger change than the rest of this design put together, and it can be made
later without redoing any of this.

## 4. Architecture

Four hops, and the layer rule decides where each lives.

```
WCL masterData.abilities   id → icon filename        adapter (I/O)
        ↓
LoadedRun.ability_icons    carried as plain data     domain (no I/O)
        ↓
view model .ability_id     one int per icon site     domain (no I/O)
        ↓
IconSource.data_uri(id)    filename → bytes → CSS    adapter (I/O)
```

**The domain never sees an image.** It carries integers. Everything that touches the network,
the disk or base64 lives in an adapter, behind a port.

### 4.1 The identity the domain must carry

Today ability identity becomes a display string before the view model: `RecapRow.ability` is a
`str`, `model.py` has no id field anywhere, and `Death` resolves `killingAbilityGameID` only to
look the name up and then discards it. Threading the id down is the bulk of this work.

| Type | Field added | Source |
| --- | --- | --- |
| `RecapEvent` (`analysis/recap.py`) | `ability_id: int` | already on `DamageTakenEvent`, `HealingEvent`, `CastEvent` |
| `RecapRow` (`report/model.py`) | `ability_id: int \| None` | copied in `deaths.py` |
| `AbilityState` (`analysis/recap.py`) | `ability_id: int \| None` | `availability_at` already reads `ability.ability_id` |
| `AvailabilityRow` (`report/model.py`) | `ability_id: int \| None` | copied in `deaths.py` |
| `Death` (`domain/events.py`) | `killing_blow_id: int` | `ingest.py` reads it today and throws it away |
| `DeathCard` (`report/model.py`) | `killing_blow_id: int \| None` | copied in `deaths.py` |

`None` means "no icon is possible here", and is what a consumable row carries. **Zero is never
used as a sentinel**: `masterData` maps id 0 to "Unknown Ability" with a real icon file
(`inv_axe_02.jpg`), so a 0 reaching the resolver would draw an axe beside an ability nobody
identified. The resolver rejects 0 explicitly (§6).

### 4.2 The filename map

`masterData.abilities` already gives id → name; it gives id → icon in the same response for no
extra points. `ABILITIES_QUERY` gains one field and the map travels on `LoadedRun`:

```python
# LoadedRun
ability_icons: tuple[tuple[int, str], ...] = ()

@property
def ability_icon_map(self) -> Mapping[int, str]:
    return MappingProxyType(dict(self.ability_icons))
```

Pairs rather than a dict, with a `MappingProxyType` property, following `Run.npc_counts` /
`Run.npc_count_map` exactly — a `LoadedRun` stays immutable and hashable.

A filename is data of the same kind as a name: it comes from the API, it is a string, and
carrying it performs no I/O.

The map reaches the resolver through the CLI, which already holds both: it builds the resolver
from `loaded.ability_icon_map` and hands it to `render`. Nothing else needs to see it.

## 5. The port

In `domain/ports.py`, beside the two that are already there:

```python
class IconSource(Protocol):
    def data_uri(self, ability_id: int) -> str | None: ...
```

One method. `None` means no icon for that ability, for any reason — unknown id, absent from the
CDN, a byte store that failed. The caller never learns which, because the page does the same
thing in every case: draw the name without an icon.

`render` grows one optional keyword:

```python
def render(report: Report, icons: IconSource | None = None) -> str:
```

Defaulting to `None` keeps all sixty-odd existing `render(...)` call sites in the tests
unchanged, and gives the no-icon path a first-class meaning rather than making it a special
case.

## 6. The resolver

`adapters/render/icons.py`, implementing `IconSource`. It owns the whole chain and every rule
below, so the rules are testable without a network.

```
https://render.worldofwarcraft.com/eu/icons/36/<filename>
```

Region `eu`, size 36. Sizes 18, 36 and 56 all serve; 128 does not. Region `cn` does not.

Rules, each measured rather than assumed:

1. **Id 0 resolves to nothing.** It is `masterData`'s "Unknown Ability" row and its icon is a
   generic axe.
2. **An id absent from the filename map resolves to nothing.**
3. **Strip any query string from the filename** before building the URL and before keying the
   cache. Three of 2511 rows in a real report carried a literal `?cachebust` suffix, all three
   the same underlying file, so stripping also deduplicates them.
4. **A response is an icon only if it is 200 *and* its content type begins `image/`.** A miss
   is a **403 carrying `application/xml`**, not a 404 and not an exception. Without the content
   type check the page would embed an XML error document as a JPEG.
5. **A miss is remembered**, so a known-absent icon costs one request ever rather than one per
   analysis.

## 7. Embedding once

181 rows draw 45 distinct icons. A `data:` URI per row would cost roughly 400 KB for one
section, so the bytes are emitted **once per distinct ability** as CSS rules inside the
existing inline `<style>`, and referenced by class:

```css
.i-48792 { background-image: url(data:image/jpeg;base64,...); }
```

```html
<span class="icon i-48792" aria-hidden="true"></span>Icebound Fortitude
```

A helper in the render adapter walks the report's icon-bearing fields, resolves each distinct
id once, and returns the block. Collecting is the adapter's job because only the adapter can
know which ids resolve — that answer requires I/O.

**The span is emitted only when a data URI exists** — never when an id merely exists. That is
what makes the no-`IconSource` path byte-identical to today's page rather than merely similar,
and it collapses "no source", "unknown id" and "absent from the CDN" into one rendered outcome.

**The icon is always decorative.** The name is rendered whether or not an icon appears, and the
span carries `aria-hidden="true"`. Nothing on the page is ever an icon alone, so a miss costs
appearance and never meaning.

One maintenance cost, named rather than designed away: the collecting helper and the template
each know the icon sites, so adding a fourth site means editing both. Three sites do not justify
a registry; a fifth would.

## 8. Caching

`DiskCache` stores JSON keyed on a GraphQL query and its variables. Icons are neither, so they
get a small store of their own: `cache/icons/<filename>` for bytes and `cache/icons/<filename>.miss`
as a zero-byte marker for a known absence.

**The filename comes from an API and becomes a path, so it is validated before it is either.**
Only `[a-z0-9_-]+\.jpg` after the query string is stripped; anything else resolves to no icon
and is never opened, requested or written. Every one of the 2511 observed names matches that
shape, so the rule costs nothing today and stops a crafted `../` from reaching the filesystem. Written atomically, the way `DiskCache` already
writes. **No expiry** — the art does not change, and an expiring cache would re-pull every icon
on a schedule for nothing.

Adding `icon` to `ABILITIES_QUERY` changes the query text, and `cache_key` hashes that text, so
every existing `Abilities` entry is orphaned. That is one 7-point refetch, once.

## 9. Cost

| | |
| --- | --- |
| Report today | 107,250 bytes |
| Distinct icons on that report | ~60 |
| Blizzard `eu/36`, base64 | ~150,000 bytes |
| **Report becomes** | **~258,000 bytes, 2.4x** |

Requests: one per distinct icon, first run only, then never again. Roughly 60 on a cold cache,
about 1.7 KB each. Warcraft Logs points: unchanged — `icon` rides along on a query already
being sent — plus the one 7-point refetch above.

Blizzard's JPEGs are ~45% larger than zamimg's at the same dimensions, and miss roughly 4–5% of
current-season assets. Both are the price of §2's sourcing decision, paid deliberately.

## 10. What changes

| File | Change |
| --- | --- |
| `adapters/wcl/queries.py` | `abilities { gameID name }` → `abilities { gameID name icon }` |
| `adapters/wcl/repository.py` | build the id → icon map beside `ability_names`, put it on `LoadedRun` |
| `adapters/wcl/ingest.py` | keep `killingAbilityGameID` on `Death` |
| `domain/model.py` | `LoadedRun.ability_icons` + `ability_icon_map` |
| `domain/events.py` | `Death.killing_blow_id` |
| `domain/analysis/recap.py` | `RecapEvent.ability_id`, `AbilityState.ability_id` |
| `domain/report/model.py` | `ability_id` on `RecapRow` and `AvailabilityRow`, `killing_blow_id` on `DeathCard` |
| `domain/report/deaths.py` | copy the ids through |
| `domain/ports.py` | `IconSource` |
| `adapters/render/icons.py` | **new** — the resolver, the byte store, the CSS block |
| `adapters/render/html.py` | `render(report, icons=None)` |
| `adapters/render/_deaths.html.j2` | the icon span at three sites |
| `adapters/render/report.css.j2` | `.icon` sizing |
| `cli.py` | build the resolver, pass it to `render` |
| `.claude/skills/wcl-api/SKILL.md` | the `icon` row and the dated findings in §13 |

## 11. Testing

TDD throughout; the rules in §6 are the point of the feature and each gets its own test.

- **Resolver**: id 0 → `None`; unknown id → `None`; a filename failing the shape rule → `None`
  with no request and no file touched; `?cachebust` stripped from URL and key; a
  403 with `application/xml` → `None` and nothing embedded; a 200 with `image/jpeg` → a
  `data:image/jpeg;base64,` URI; a remembered miss issues no second request. All against a
  fake byte source — no network in the suite.
- **Embedding**: a report drawing one ability 40 times emits one CSS rule, not 40.
- **View model**: each of the six new fields carries the id the layer below gave it, and a
  consumable row carries `None`.
- **Rendering**: with no `IconSource` the page is byte-identical to today; with one, the span
  appears beside the name and the name still renders.
- **New invariant**: no `url(http` anywhere in the page. The existing
  `test_the_page_executes_only_its_own_script` checks `src` attributes and would not catch an
  external CSS `url()`.
- The golden file changes. Its diff is the review.

## 12. Invariants this must not break

- `src/wowperf/domain/` imports nothing that does I/O. The domain gains integers and strings.
- The template computes nothing: no `{% set %}`, no `|sum`, no `sum(`.
- The page loads no external resource. §11's new test extends the existing guard to CSS.
- Every numeric view-model field needs a written entry in `NUMBERS_THAT_ARE_NOT_TOTALS`. The
  three new `ability_id` fields are identifiers, not durations.
- No invented API field name. §13 carries the verification.

## 13. Verified 2026-09-09, for the `wcl-api` skill

- **`ReportAbility` has exactly four fields**: `gameID: Float`, `icon: String`, `name: String`,
  `type: String`. Introspected against the live schema. There is no description, no cooldown
  and no tooltip text anywhere on it — the reason §14 exists.
- **`icon` is a bare lowercase filename with a `.jpg` extension**, e.g.
  `spell_holy_magicalsentry.jpg`. All 2511 rows of one report carried one; three carried a
  `?cachebust` suffix.
- **`render.worldofwarcraft.com/eu/icons/36/<filename>` serves those names**, `image/jpeg`,
  1.3–1.8 KB each. Nine of ten sampled resolved; the failure was a **403 with
  `application/xml`**.

Each needs a dated row before or with the implementation, and the `icon` row in the Fields
table must read `yes` and land in the same commit as the query change, or
`test_every_field_the_table_says_we_query_is_in_the_queries` fails.

## 14. Deferred, deliberately

- **Tooltips.** Warcraft Logs has no spell text. Wowhead's is the only complete source and
  conflicts with the ZAM EULA on retrieval, reproduction and display; its endpoint is
  undocumented; and its HTML cannot render without `|safe`, which `html.py` forbids by design.
  Blizzard's Game Data API is the honest alternative and needs an API key and a human to accept
  its terms. `/data/wow/spell/{id}` has **not** been called and nothing here assumes its shape.
- **Reference-data staleness.** `verified` dates in `data/*.toml` are dropped at the loader
  (`adapters/config/toml.py:93`) and reach neither the domain nor the page, so a patch that
  retunes a cooldown would go unnoticed. Two cheap fixes exist — cross-checking our ability
  names against `masterData` on every run for free, and disclosing the dates in Provenance —
  and both are independent of this design. Its own slice, and worth doing before tooltips.
- **Icons on findings.** §3.

## 15. For review

One judgement in §3 is worth a second opinion before implementation: consumable rows get no
icon, because a category holds several ids and no one of them is the item. Eight of the 28
availability rows are consumables, so two of the three groups on a death card will carry icons
and one will not. The alternative is a curated id per category in `consumables.toml` — a hand-
maintained choice, dated like everything else in that file, which the tool would then be
asserting rather than reading. This design takes the gap over the assertion.
