# Spike: spell icons and hover tooltips in the report

Run 2026-09-08 against the live Warcraft Logs API, the live Wowhead tooltip endpoint, the
zamimg CDN and Blizzard's render CDN. Real report throughout:
`6Kx1P9GbNXrcLdHa` fight 36, the same one every other measurement in this repository uses.

This is a spike. It produced no production code and changed nothing under `src/` or `tests/`.
Every number below was measured, not recalled. Where I could not determine something, the
document says so rather than guessing.

---

## 1. The answer, up front

**Technically: yes, comfortably.** Icons and hover tooltips both fit inside one
self-contained HTML file that needs no network at view time. I built the page and confirmed
it — icons as `data:image/jpeg;base64` URIs, tooltips as a CSS `:hover` panel, no JavaScript,
no external reference of any kind. A realistic report grows from **94,847 bytes to about
224,000** — roughly 2.4x, still a fifth of a megabyte.

**Structurally: two days of plumbing, not an afternoon.** The report view model carries
**zero numeric spell ids**. Every ability reaches the page as a bare name string. The ids
exist upstream — nearly every event type has one — but they are dropped before the view
model. Icons key on ids, so that plumbing is the real work, and §7 lists it slot by slot.

**Legally: this is the blocker, and it is a real one.** The obvious source — Wowhead's
tooltip endpoint and the zamimg CDN — conflicts with the ZAM Network EULA on three separate
clauses, independently of any copyright question. Blizzard's own render CDN is better
provenance and covers 96% of what we need, but its terms were written for "Data" and never
mention images. **My recommendation is to ship the icons and defer the tooltips**, and §9
explains why that split is the one the evidence supports. A human has to make the call in §9
before any of this is planned.

---

## 2. Question 1 — Warcraft Logs does expose an icon per ability

**Yes.** `ReportAbility.icon` exists. Live introspection of the type behind
`reportData.report.masterData.abilities`, 2026-09-08:

```
### ReportMasterData (OBJECT)
   abilities                ReportAbility    A list of every ability that occurs in the report.

### ReportAbility (OBJECT)
   gameID                   Float            The game ID of the ability.
   icon                     String           An icon to use for the ability.
   name                     String           The name of the actor.
   type                     String           The type of the ability. This represents the type of damage…
```

(`name`'s description reading "the name of the actor" is Warcraft Logs' own copy-paste, not a
transcription error on my part.)

Two neighbours, introspected the same day:

- **`GameAbility { id, icon, name }`** — reachable as `gameData.ability(id: Int)` and
  `gameData.abilities(limit:, page:)`. A per-id lookup that does not need a report.
- **`ReportActor.icon`** — already recorded in the skill; on a player it is the
  class-spec token (`"Shaman-Elemental"`), not a spell icon.

### What it actually returns

The project's `ABILITIES_QUERY` currently asks `abilities { gameID name }`
(`src/wowperf/adapters/wcl/queries.py:120`). I ran it with `icon` added, against the real
report:

| Measure | Value |
| --- | --- |
| Abilities in `masterData` for the whole report | 2511 |
| Carrying a non-null `icon` | **2511 — every one** |
| Distinct icon filenames behind them | 1321 |
| Point cost, `gameID name` | 1.00 |
| Point cost, `gameID name icon` | **1.00 — the field is free** |

Both costs are net of the 1.00-point `rateLimitData` read used to measure them. Adding
`icon` to an existing query costs no extra points and no extra round trip.

Rows verbatim, exactly as returned:

```json
{"gameID": 0,       "name": "Unknown Ability",  "icon": "inv_axe_02.jpg",                 "type": "0"}
{"gameID": 279910,  "name": "Wild Imp",         "icon": "ability_warlock_impoweredimp.jpg","type": "32"}
{"gameID": 1459,    "name": "Arcane Intellect", "icon": "spell_holy_magicalsentry.jpg",    "type": "64"}
```

**One wart.** Three of the 2511 rows carry a query string glued to the filename:
`"ability_monk_chiexplosion.jpg?cachebust"`. Anything that builds a URL or a filename from
this field has to split on `?` first. The CDN ignores the suffix and serves the image anyway,
so it fails quietly rather than loudly — which is worse.

### The table endpoints already return icons too, for free

`table(...)` returns a JSON scalar with no subfield selection, so its icons arrive without
any query change and without ever appearing in `queries.py`. Both are already in the cache:

- **Deaths table** — each damage/healing ability row carries `icon`, e.g.
  `{"guid": 1297749, "name": "Frozen Tempest", …, "icon": "spell_frost_ring-of-frost.jpg"}`.
  The entry itself carries the actor's `icon` (`"Shaman-Elemental"`).
- **Aura table** — each aura carries `abilityIcon` (already recorded in the skill,
  2026-09-05).

### The decisive finding: the icon string *is* the CDN filename

I sampled 42 distinct icon names from the real report — including all three `?cachebust`
oddities — and requested each from the zamimg CDN:

```
hits 42 / 42, misses 0
medium icon bytes: min 847  median 1116  mean 1120  max 1380  (all 36x36)
```

And I cross-checked 12 abilities that exist in both sources: **Warcraft Logs and Wowhead
return byte-identical icon names**, modulo Wowhead omitting the `.jpg`.

| id | WCL `icon` | Wowhead `icon` + `.jpg` | |
| --- | --- | --- | --- |
| 642 | `spell_holy_divineshield.jpg` | `spell_holy_divineshield.jpg` | same |
| 235450 | `spell_magearmor.jpg` | `spell_magearmor.jpg` | same |
| 1297749 | `spell_frost_ring-of-frost.jpg` | `spell_frost_ring-of-frost.jpg` | same |
| 1307578 | `inv_121_trinket_raid_ulatek_ritualvessel.jpg` | `inv_121_trinket_raid_ulatek_ritualvessel.jpg` | same |

**12 agree, 0 differ.** So for the icon half, Wowhead is not needed at all. One word added to
a query the project already makes yields the icon name for every ability that occurs in the
log.

### Where that is not enough

`masterData` lists what *occurred*. The report also names abilities that never happened —
that is the entire point of "defensives never pressed". Of the 14 availability rows the real
report renders, **three have no `masterData` row**: `Ice Block`, `health potion`,
`healthstone`. Across all five `data/*.toml` files, 72 of 175 curated ids (41%) are absent
from this report's `masterData`.

Splitting the 74 abilities this page names:

| Source | Count | Icon available from |
| --- | --- | --- |
| Occurred in the log | 59 | `masterData.icon` — free |
| Curated in `data/*.toml`, some never cast | 15 | needs an id→icon table, or a lookup |

A committed static table alone would cover only 15 of 74, so it is not a substitute. But the
inverse holds nicely: `masterData` covers everything that happened, and a small dated
`id → icon` table covers the curated set that might not have. The curated set is 175 rows,
changes only when someone edits a TOML, and would sit naturally beside the existing
`verified = "…"` stamps.

**Consumables have no honest icon.** `ConsumableCategory.name` is a cooldown *category*, not
a spell. `"health potion"` covers three ids resolving to two different icons; `"healthstone"`
covers three ids resolving to three. There is no single correct image for those rows, and
picking one would be the page asserting something it does not know.

---

## 3. Question 2 — what the Wowhead tooltip endpoint returns

`GET https://nether.wowhead.com/tooltip/spell/<id>` returns **nine keys**, identical across
all eight spells I fetched (ids drawn from `data/defensives.toml`, `data/externals.toml`, and
the report itself). Full shape, key by key:

| Key | Type | What it holds |
| --- | --- | --- |
| `name` | string | The spell name. `"Divine Shield"`. |
| `icon` | string | **Icon base name, lowercase, no extension and no path.** `"spell_holy_divineshield"`. |
| `tooltip` | string | The full tooltip as an HTML `<table>`. Median 643 bytes. |
| `tooltip2` | string | Empty on all eight. Purpose undetermined. |
| `buff` | string | The buff/aura tooltip as HTML, or empty. Empty for `Power Word: Barrier`. |
| `quality` | int | `-1` on all eight spells. Presumably meaningful for items. |
| `spells` | object | `id → [[a, b, c]]`. Talent-conditional text fragments — the deltas a talent applies to the tooltip. Empty for simple spells (`Icebound Fortitude`). |
| `buffspells` | object | Same shape, for the buff text. Usually empty. |
| `completion_category` | int | `7` or `-2` across the sample. Undetermined; looks unrelated to spells. |

One response verbatim, trimmed only where marked:

```json
{"name":"Divine Shield","icon":"spell_holy_divineshield",
 "tooltip":"<table><tr><td><a class=\"whtt-name\" href=\"/spell=642/divine-shield\">…
   <th><!--cooldownText-->5 min cooldown<!--cooldownText--></th>…
   <div class=\"q\">Grants immunity to all damage, harmful effects, knockbacks and forced
   movement effects for 8 sec.…</div></td></tr></table>",
 "tooltip2":"",
 "buff":"<table>…<b class=\"q\">Divine Shield</b>…Immune to all attacks and harmful effects.
   <span class=\"q\">8 seconds remaining</span>…</table>",
 "quality":-1,
 "spells":{"114154":[["","",""]],"204077":[["","Taunts all targets within 15 yd.",""]],
           "378425":[["","",""]]},
 "buffspells":{},
 "completion_category":7}
```

**Does it name an icon?** Yes — `icon`, as a bare base name. Append `.jpg` and it matches
Warcraft Logs exactly (§2).

**Does it carry tooltip HTML we could bake in?** Yes, and this is its real value: it is the
only source here for the *text* of a spell. Warcraft Logs has no equivalent. But see the two
problems below.

**Anything else useful?** `spells` and `buffspells` are the talent-variant deltas, which is
how the tooltip knows Blessing of Protection reads differently for Holy, Retribution and
Protection. Useful in principle, fiddly in practice, and not needed for a first pass.

### Behaviour at the edges, measured

| Probe | Result |
| --- | --- |
| Boss ability (`1297749`, Frozen Tempest) | 200, resolves correctly |
| Trinket proc (`1307578`, Soulcoil Barrier) | 200, resolves correctly |
| Nonexistent id (`999999999`) | **404**, 30-byte body |
| `0` — the `"Unknown Ability"` row `masterData` always carries | **404** |
| All 74 abilities this report names | **74 resolved, 0 misses** |
| Latency | ~94 ms each, 6.9 s for 74 sequential |
| `cache-control` | `max-age=0, s-maxage=43200` (12 h shared) |
| `access-control-allow-origin` | `*` |
| Rate-limit headers | **none** — no `x-ratelimit-*`, no `retry-after` |

### Two problems with baking the HTML

**It phones home.** 13 of the 74 tooltips embed absolute image URLs inside their HTML:

```
//wow.zamimg.com/images/wow/icons/small/spell_holy_holybolt.jpg
```

Paste that HTML into the report and the "self-contained, no network" guarantee is gone for
18% of tooltips — silently, and only at view time. Every tooltip also carries a site-relative
`href="/spell=642/divine-shield"` that resolves to nothing from a local file.

**It cannot be rendered without `|safe`.** `src/wowperf/adapters/render/html.py` mandates
autoescaping, and its docstring says why:

> Player names, pack names and killing blows all come from an external API and all land in
> HTML. A `|safe` anywhere in this template would let a character name execute markup in
> whoever opens the file.

Injecting third-party HTML from an undocumented endpoint into an autoescape-mandatory
template is exactly the thing that comment forbids. **Plain text is the honest route**, and
it is also five times smaller: 18,719 bytes against 53,108 for the same 74 tooltips.

I wrote the HTML-to-text conversion and it works, with visible seams — table cells run
together, so `Instant` + `5 min cooldown` renders as `Instant5 min cooldown`. Handling
`<td>`/`<th>` boundaries fixes it; I did not, because that is implementation, not spike.

---

## 4. The icon files themselves

`https://wow.zamimg.com/images/wow/icons/<size>/<name>.jpg`, measured 2026-09-08 on
`spell_holy_divineshield.jpg`:

| Size | HTTP | Bytes | Dimensions |
| --- | --- | --- | --- |
| `tiny` | 404 | — | — |
| `small` | 200 | 685 | **18 x 18** |
| `medium` | 200 | 1,213 | **36 x 36** |
| `large` | 200 | 2,118 | **56 x 56** |

JPEG only. `.webp` and `.png` both 404, and an `Accept: image/webp` header still returns
`image/jpeg`. 73 sequential fetches on one keep-alive connection took **0.4 s**.

**Use `medium` art at 18 CSS pixels.** 36x36 is exactly 2x for an 18px slot, so it stays
crisp on the HiDPI display most people read on, while `small` would be visibly soft.

---

## 5. Cost in file size, for a real report

Counted, not estimated: I intersected the 2511 `masterData` ability names against the text of
the rendered report.

| | |
| --- | --- |
| Report HTML today | **94,847 bytes** |
| Distinct ability names the page shows | **74** |
| Distinct icons behind them (names sharing art collapse) | **73** |

All 74 sit inside the four death-recap sections — the death recap is where this report names
abilities, and the ledger prose adds none beyond it. So "death-recap scope" and "whole page"
are the same 74 today.

### Icons

| Source and size | Raw | Base64 | Page becomes | |
| --- | --- | --- | --- | --- |
| zamimg `small` (18px) | 47,096 | 62,794 | 157,641 | 1.66x |
| **zamimg `medium` (36px)** | **82,658** | **110,210** | **205,057** | **2.16x** |
| zamimg `large` (56px) | 138,062 | 184,082 | 278,929 | 2.94x |
| Blizzard render `36` | 112,909 | 150,545 | 245,392 | 2.59x |

Blizzard's own JPEGs are about 45% larger than zamimg's at the same pixel dimensions —
zamimg re-compresses harder.

### Tooltips

| | Bytes | Page becomes | |
| --- | --- | --- | --- |
| Raw tooltip HTML, 74 spells | 53,108 | 147,955 | 1.56x |
| Same tooltips as plain text | **18,719** | 113,566 | 1.20x |

### Combinations

| | Total | |
| --- | --- | --- |
| Today | 94,847 | 1.00x |
| Icons only (`medium`) | 205,057 | 2.16x |
| **Icons (`medium`) + plain-text tooltips** | **223,776** | **2.36x** |
| Icons (`medium`) + raw tooltip HTML | 258,165 | 2.72x |

**Do not bake every icon `masterData` names.** All 1321 distinct icons at `medium` would add
**2,013,204 bytes** of base64 — a 22x page. Only bake what the page actually renders.

Deflating the 73 JPEGs together saves little (82,658 → 63,829): JPEG is already
entropy-coded, so a sprite sheet or an archive buys almost nothing over 73 separate data
URIs. Not worth the complexity.

---

## 6. Cost in requests, and whether they cache

Per analysis, on a cold cache, for this report:

| | Requests | Wall clock | Warcraft Logs points |
| --- | --- | --- | --- |
| Icon names | 0 — one word on an existing query | 0 | **0** |
| Icon images from a CDN | 73 | 0.4 s | 0 |
| Tooltips from Wowhead | 74 | 6.9 s | 0 |

Neither CDN nor Wowhead touches the Warcraft Logs quota. Against the 44.29-point cost of a
full compared analysis with the recap, the icon feature is free.

**Cacheable — but not by the existing cache as it stands.** `DiskCache` stores JSON, one file
per key, keyed on `sha256(query + canonical variables)`. Icons are binary, and neither icons
nor tooltips are keyed by a GraphQL query. Two honest options: teach `DiskCache` a bytes
variant, or add a small sibling asset cache. Either is small.

The important asymmetry is that **this content is global, not per-report**. A Warcraft Logs
response is about one fight and caches for one report; `spell_holy_divineshield.jpg` is the
same for every run forever. So a persistent asset cache approaches a 100% hit rate after a
handful of analyses, and the steady-state cost of the feature is zero requests.

That also settles the terms question the project already answers for Warcraft Logs. RPGLogs
§5d forbids accumulating a corpus of other players' logs; a cache of Blizzard icon art is not
a corpus of anyone's logs, so §5d does not bite here. **The Wowhead and Blizzard terms are a
separate matter and do bite — see §9.**

---

## 7. What the codebase would have to change

The report view model carries **no numeric spell id anywhere**. Every ability reaches the
page as a name string. Three tiers of work, in increasing order:

**Free — the id is already in scope, just not copied.**

- `AvailabilityRow.ability` (`domain/report/model.py:114`). `availability_at` in
  `domain/analysis/recap.py` already matches on `ability.ability_id` and then passes only
  `ability.name`. Widening `AbilityState` and `AvailabilityRow` adds no new data.
- `RecapRow.ability` (`model.py:105`) — the highest-volume slot on the page. `RecapEvent` is
  built from `DamageTakenEvent`, `HealingEvent` and `CastEvent`, all of which carry
  `ability_id`. Same widening.

**Cheap, but a real change.**

- `DeathCard.killing_blow` (`model.py:150`). The id is *destroyed at ingest*:
  `adapters/wcl/ingest.py:229-231` reads `killingAbilityGameID`, resolves it to a string and
  never stores it. `Death` (`domain/events.py:7-13`) has `killing_blow: str` and no id field.
  This feeds the most prominent ability name on the page — the death-card headline.

**Needs a design decision.**

- Every `LedgerRow` ability name. The name is interpolated mid-sentence into `Finding.title`
  and `.detail`, so there is no slot to hang an icon on. Most analysers already have
  `ability_id` in scope and merely format it into an evidence string
  (`f"ability {ability_id}"`, in `analysis/defensives.py:251`, `analysis/throughput.py:272`,
  `comparison/spells.py:110`, `comparison/uptime.py:111`). Giving `Finding` a structured
  ability field is the clean fix — and it is not needed for a first pass, since all 74
  abilities on today's page are already reachable through the recap slots above.

**One template, one constraint.** `adapters/render/report.html.j2` is the whole page. Ability
names print as bare escaped text with no wrapper — except `<span class="avail-name">`, the
one existing hook. Because autoescaping is mandatory and `|safe` is forbidden, an `<img>`
cannot be smuggled in as a string from the builder; it has to be real template markup driven
by a new structured field. That is the right constraint, and it is worth stating in the plan
so nobody tries to route around it.

---

## 8. Alternatives I rejected

**Hotlinking a CDN at view time** — `<img src="https://wow.zamimg.com/…">`. Cheapest by far:
zero bytes, zero fetches at analysis time. Rejected because it breaks the product's defining
property. `render()`'s contract is "one self-contained HTML document: … no network, no
external font", and the report is a file you keep, mail to a friend, or open on a plane six
months later. A page whose icons are blank rectangles offline is worse than a page with no
icons. It also turns every reader into a tracked request against a third party's CDN, which
is a privacy decision the reader never agreed to.

**Wowhead's sanctioned `tooltips.js` embed** — the officially documented route, used by
Warcraft Logs and Raider.IO. Rejected on the same ground, only harder: the script works by
scanning links at load and fetching icons *and* text at runtime. It is inherently online.
There is no offline mode. The sanctioned route and the offline requirement are mutually
exclusive, which is uncomfortable and worth saying plainly.

**A committed static icon table for `data/*.toml`** — rejected as a *substitute*, since it
covers only 15 of the 74 abilities this page names. Kept as a *supplement*: it is the right
answer for the curated-but-never-cast set (§2), it is 175 stable rows, and it fits the
existing dated-TOML pattern.

**A sprite sheet or a zip** — rejected on measurement. Deflating the 73 JPEGs saves 19 KB on
a 224 KB page, and costs a build step, an image dependency the project does not have (only
`httpx`, `jinja2`, `pydantic`, `typer`), and CSS offset arithmetic.

**Re-encoding to WebP** — rejected because it needs an image library, and because the CDN
does not serve WebP anyway (404 on `.webp`; `Accept: image/webp` still returns JPEG).

**Extracting icons from the user's own game install** (CASC/BLP) — the cleanest position by
far, since the user owns the game and the file never leaves their machine. Rejected for now:
it needs a BLP decoder, a WoW installation the tool cannot assume, and a code path no test in
CI could exercise. Worth revisiting if §9 goes badly.

---

## 9. The licensing question — for a human, before anything is planned

**I am summarising documents, not giving legal advice.** Everything here was read
2026-09-08 and the URLs are given so a human can check them.

### Wowhead / ZAM — the clearest problem

`https://www.wowhead.com/tos` is a stub pointing at the **ZAM Network, LLC EULA and Terms of
Service** (`https://corp.fanbyte.com/legal/terms`, last updated 2025-05-14), whose defined
"Service" expressly includes ZAM's websites **and APIs**. Three clauses cut against this
proposal, and none of them depends on the copyright question:

1. **Automated retrieval is prohibited.** The prohibited-conduct list bars downloading
   content with anything other than a generally available web browser, naming *"spiders,
   robots, crawlers, data mining tools or the like"*. A script pulling 73 JPEGs is the
   described behaviour.
2. **Reproduction and distribution are prohibited** by the License Limitations paragraph.
3. **Display outside the Service requires express written consent.**

The license grant is in any case personal, non-commercial and internal-use only.

Two further facts I verified directly. **The `nether.wowhead.com/tooltip/spell/<id>` endpoint
is documented nowhere** — it is the internal endpoint `tooltips.js` calls for logged-out
users. It returns 200, but working is not the same as sanctioned. And `wowhead.com/robots.txt`
carries `Disallow: /` for a long list of automated agents including `ClaudeBot`,
`anthropic-ai`, `GPTBot`, `CCBot` and `Scrapy`. That list targets training crawlers rather
than this use case, but it is a clear statement of posture. `wow.zamimg.com/robots.txt` is a
404, and I found **no ZAM statement about image hotlinking either way**.

### Blizzard — better provenance, unclear terms

The art is Blizzard's regardless of who serves it. I verified that **Blizzard serves these
same icons itself, from `https://render.worldofwarcraft.com/<region>/icons/<size>/<name>.jpg`,
with no API key**:

| Probe | Result |
| --- | --- |
| Regions `us`, `eu`, `kr`, `tw` | 200 |
| Region `cn` | 403 |
| Sizes 18, 36, 56 | 200, and the dimensions match the numbers |
| Size 128 | 403 |
| Broad sample of 200 report icons at `eu/36` | **192 hit (96.0%), 8 miss** |
| The 73 icons this report needs | **69 hit, 4 miss** |

The misses are informative: `inv_121_trinket_raid_ulatek_ritualvessel.jpg`,
`inv_121_trinket_dungeon_ulatek_vile.jpg`, `inv_121_trinket_raid_ulatek_heart.jpg` and
`spell_frost_ring-of-frost.jpg`. **Blizzard's render CDN lags on the newest assets** — the
`inv_121_*` current-season trinkets are exactly what a current-season Mythic+ report leans
on. A fallback would be needed for roughly 4–5% of icons.

Three Blizzard documents, which do not fully agree with each other:

- **Blizzard Legal FAQ** — grants a personal, non-exclusive licence to display material
  *"for home, noncommercial and personal use only"*, provided copyright notices stay intact.
  The closest thing to a fan-content grant that still exists. Two caveats: it is scoped to
  material downloaded *from Blizzard's site*, and it is visibly stale (it still references
  Heroes of the Storm and Diablo III).
- **Blizzard's website Terms of Use** — stricter, and in tension with the FAQ: excludes
  downloading other than page caching, excludes distribution and public display.
- **Blizzard Developer API Terms of Use** (last updated 2019-10-01) — the Game Data API's
  `/data/wow/media/spell/{id}` does expose icon URLs, and the terms permit distributing Data
  to end users via your Application. Conditions: registered application, Blizzard-issued API
  key, Blizzard identified as the source, no monetisation, refresh at least every 30 days.
  The terms **never use the words "image", "icon", "art" or "media"** — every restriction
  attaches to "Data" — so whether the 30-day refresh rule was meant to reach a static JPEG is
  genuinely unclear from the text.

**There is no longer a Blizzard "Fan Content Policy" or "fan site policy" document.** The
Trademark Usage Guidelines still reference one; that reference dangles.

**Nothing re-licenses the art.** Warcraft Wiki's CC BY-SA covers its text, not the underlying
game assets. The `wowdev` listfile is filenames only. GitHub icon packs are redistributions
that cannot bind Blizzard's rights. Nobody but Blizzard can license Blizzard's art.

### The three questions a human should actually answer

1. **Is the report distributed?** This is the decisive factual question under both sets of
   terms. A file that never leaves your machine reads very differently from one posted to a
   Discord. Base64-embedding is what turns the HTML into a self-contained redistributable
   copy — that is the step that moves this from "personal use" toward "distribution".
2. **Is bulk fetching different from what we already do?** The project already reads
   Wowhead's tooltip endpoint by hand to verify spell names — `data/defensives.toml` carries
   `verified = "2026-09-05"` for exactly that. A handful of dated manual lookups and an
   automated 73-image pull per analysis are materially different activities under the same
   terms, even though both are "using the endpoint".
3. **Is Blizzard's render CDN worth the 4% gap?** It is first-party, needs no key, and is a
   far better provenance story. It costs 45% more bytes, misses the newest trinkets, and its
   terms were written for JSON.

### What I recommend

**Ship the icons; defer the tooltips.** The evidence separates cleanly:

- **Icons** carry real value per byte, need no third-party *text*, and — this is the point —
  the icon *name* comes from Warcraft Logs, an API this project is already licensed to use,
  at no extra point cost. Only the image bytes need a third party, and Blizzard's own CDN can
  serve 96% of them. Start there, with a small dated fallback table for the rest, and prefer
  Blizzard over zamimg on provenance even though it costs bytes.
- **Tooltips** are where the cost concentrates and the licence is weakest: 74 requests to an
  undocumented endpoint, HTML that cannot be rendered without breaking the autoescape
  invariant, and plain text that is lossy. They add 18,719 bytes of genuine value and a
  three-clause EULA conflict. Not worth it in this phase.

If the answer to question 1 above is "yes, these get shared", I would not ship either half
without a human reading the ZAM EULA directly.

---

## 10. What I could not determine

- **Whether ZAM tolerates icon hotlinking in practice.** No published statement either way.
- **`tooltip2`, `quality` and `completion_category`.** Present on every response; I have no
  evidence for what they mean. `quality` was `-1` on all eight spells and is presumably for
  items; `completion_category` was `7` or `-2` with no pattern I could see.
- **Whether Blizzard's 30-day refresh rule is intended to reach image assets.** The Developer
  API terms never mention images.
- **The official Blizzard media-documents guide.** `develop.battle.net` redirects to a
  JavaScript-rendered SPA that returns no fetchable documentation text. The render CDN
  pattern was confirmed by live probing instead, which establishes that it *works*, not that
  it is *supported*.
- **wago.tools' terms.** Returned 403.
- **Why 4% of icon names are missing from Blizzard's CDN but present on zamimg.** The pattern
  suggests newest-content lag plus some Wowhead-side renaming (two of eight misses had
  hyphens, e.g. `spell_priest_void-blast.jpg`), but I did not establish the cause.
- **Whether `masterData.abilities` paginates on a very large report.** 2511 rows came back in
  one response with no pagination field; I did not test a bigger report.

---

## 11. Rows proposed for the wcl-api skill

Do not paste these without reading the note below. `tests/test_skills.py` holds this table
against `queries.py` by **substring match**, in both directions: a row marked `yes` must have
its field name appear somewhere in `queries.py`, and a row marked `no` must have it appear
nowhere.

**One row for the table**, to be added to `## Fields`:

```
| `icon` | `ReportAbility` | 2026-09-08 | no |
```

I verified this passes the gate today: `icon` appears **zero** times in
`src/wowperf/adapters/wcl/queries.py`. **When the icon work lands and `icon` enters
`ABILITIES_QUERY`, this row must flip to `yes` in the same commit**, or
`test_every_field_the_table_says_we_do_not_query_is_absent` will fail.

**Deliberately not proposed as rows.** `ReportAbility.type` and `GameAbility.id` are both
real and both verified 2026-09-08, but `type` and `id` already appear throughout
`queries.py` (`dataType:`, `hostilityType:`, `actors(type: "Player")`), so a `no` row for
either would fail the substring gate immediately. They belong in prose. This is a general
hazard of short field names in that table and is worth knowing before adding any future row.

**Prose to add**, suggested for a new section after "Aura tables":

> ## Icons come with the ability, at no extra cost
>
> Verified 2026-09-08 by live introspection and against report `6Kx1P9GbNXrcLdHa`.
>
> `ReportAbility` carries `gameID`, `icon`, `name` and `type`. `icon` is described as "An
> icon to use for the ability" and is a bare JPEG filename — `spell_holy_divineshield.jpg`.
> All 2511 abilities in the report carried a non-null icon. Three carried a query string
> glued to the filename (`ability_monk_chiexplosion.jpg?cachebust`), so split on `?` before
> using the value as a filename or a URL.
>
> Adding `icon` to `ABILITIES_QUERY` costs **no extra points**: `abilities { gameID name }`
> and `abilities { gameID name icon }` both measured 1.00 point against the same report,
> each net of the 1.00-point `rateLimitData` read.
>
> `GameAbility { id, icon, name }` offers the same per-id, without a report, via
> `gameData.ability(id: Int)` and `gameData.abilities(limit:, page:)`.
>
> The table endpoints already return icons inside their JSON scalar, so they need no query
> change and their field names never appear in `queries.py`: the Deaths table gives `icon` on
> each damage and healing ability row, and the aura table gives `abilityIcon`.
>
> The value is directly a CDN filename. 42 of 42 sampled icon names resolved at
> `https://wow.zamimg.com/images/wow/icons/{small|medium|large}/<name>.jpg` (18x18, 36x36 and
> 56x56; `tiny` 404s, and no WebP or PNG variant exists). Warcraft Logs and Wowhead return
> identical icon names for the same spell, checked on 12 abilities — so the icon half of a
> report needs no Wowhead lookup. `masterData` only lists abilities that *occurred*, though:
> of 14 availability rows on the real report, three named an ability with no `masterData`
> row.
>
> **Terms.** Reading the icon *name* from Warcraft Logs is ordinary use of this API. Fetching
> the image *bytes* is a separate third party's business: Wowhead's zamimg CDN is governed by
> the ZAM Network EULA, which prohibits scripted retrieval, reproduction and display outside
> the Service, and `nether.wowhead.com/tooltip/spell/<id>` is undocumented. Blizzard's own
> `render.worldofwarcraft.com/<region>/icons/<size>/<name>.jpg` serves the same art with no
> API key at 18, 36 and 56 pixels (`us`/`eu`/`kr`/`tw`; `cn` and size 128 return 403) and
> covered 96% of a 200-icon sample. See
> `docs/plans/2026-09-08-icons-and-tooltips-spike.md` §9.
