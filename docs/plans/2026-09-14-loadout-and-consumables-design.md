# Loadout and Consumables — Design

- **Date:** 2026-09-14
- **Status:** Proposed
- **Scope:** A shared comparison layer serving both the Mythic+ slice and the raid slice

**Authority.** `2026-09-03-mplus-postmortem-design.md` remains the authority on architecture,
badges and refusals. `2026-09-08-sampling-design.md` remains the authority on how a sample is
drawn and when a comparison is withheld; this design draws no new sample and changes none of
those rules. `2026-09-13-raid-analysis-design.md` describes the slice that inherits this work;
nothing here reopens it. This document amends one detail of the master design in §9.

---

## 1. Purpose

Three problems, one missing data source.

**The tool can currently give advice a player cannot follow.** A real narrative, written from
`VCGkLQtPwNRA8HhD` fight 1, told the analysed player that every top parse cast an ability they
never cast, and offered two explanations: a talent not taken, or a button not pressed. The
ability was a trinket's on-use effect. The player did not own the trinket. The finding carried a
`measured` badge while stating a false dichotomy, which is exactly the failure the badge exists
to prevent.

**The tool cannot see gear.** One averaged integer per player, `friendlyItemLevels`, is the
entire gear signal in the codebase. `comparison/confounds.py:110` disclaims trinkets and
embellishments as uncorrected because there was no way to correct for them.

**The tool cannot see secondary stats, or any consumable a player did not die next to.**
`analysis/consumables.py` covers health potions and healthstones, gated on a death. Flasks, food
and augment runes — the three things a player most often simply forgets — are invisible.

All three are answered by one payload that this project has never requested.

---

## 2. Verified context

Measured against the live API on 2026-09-14, against report `VCGkLQtPwNRA8HhD` fight 1 (five
players, Mythic+) and report `6Kx1P9GbNXrcLdHa` fight 36 (five players; **these five are real
people and are named nowhere**). Every claim below was run, not read. The whole probe — one
introspection and about a dozen queries — cost roughly **15 points of the 3600-point hour**.

### 2.1 `playerDetails` carries a stat block, behind an argument that defaults off

`Report.playerDetails` accepts `difficulty`, `encounterID`, `endTime`, `fightIDs`, `killType`,
`startTime`, `translate` and **`includeCombatantInfo`**, and returns a `JSON` scalar.

Without the flag, every player's `combatantInfo` is `[]` — an empty list, not an object. This is
why the field looks useless on a first read. With `includeCombatantInfo: true` it becomes an
object carrying `artifact`, `factionID`, `gear`, `heartOfAzeroth`, `specIDs`, `stats`,
`talentTree` and `talents`.

`stats` holds ten entries, each `{min, max}`:

```
Crit · Haste · Mastery · Versatility · Leech · Avoidance · Speed
Strength · Stamina · Item Level
```

**These are ratings, not percentages.** One player read `Crit 904`, `Haste 865`, `Mastery 1196`,
`Versatility 0`. Converting a rating to a percentage needs a per-level coefficient that has no
API source, so this design never converts one. Ratings are directly comparable between players
at the same level, which is the only comparison it makes.

`min` and `max` were equal for every stat of every player observed. The design reads `min` and
records that the two agreed; if they ever diverge, the reader is seeing a stat that changed
during the fight and the comparison should be withheld rather than guessed at.

**Cost: 2.00 points** per report, measured from the query's own `rateLimitData`.

### 2.2 `combatantInfo.talents` is empty, and so is the table's

Both `combatantInfo.talents` and the `talents` field on a `DamageDone` table entry came back
`[]` for every player in both reports. **Talents do not come from either endpoint.** The existing
`talentImportCode` route (`queries.py:382`, stored as `Player.talent_import_string`) stays exactly
as it is, and this design adds nothing to the talent comparison.

### 2.3 Gear is free from the table, and included with the stat block

`table(dataType: DamageDone, hostilityType: Friendlies, fightIDs: [N])` costs **0.00 points** and
returns entries carrying `abilities`, `activeTime`, `activeTimeReduced`, `damageAbilities`,
`gear`, `guid`, `icon`, `id`, `itemLevel`, `name`, `talents`, `targets`, `total` and `type`.

(`.claude/skills/wcl-api/SKILL.md` records `pets` on this entry too, measured 2026-09-12. It did
not appear on 2026-09-14 for either report. Nothing here depends on it and the discrepancy is
left unresolved rather than explained away.)

Each `gear` element carries `id`, `slot`, `quality`, `icon`, `name`, `itemLevel`,
`permanentEnchant`, `permanentEnchantName`, `bonusIDs` and `setID`, plus `gems` where the item
has any. All eighteen slots, 0 to 17, are present for every player.

The same `gear` array appears inside `combatantInfo`. **Since the stat block is wanted anyway,
`playerDetails` alone supplies both and the table query is redundant.** The free route is
recorded here because it is the cheaper option should a later slice want gear without stats;
nothing in this design uses it.

The table query requires a window: called without `fightIDs`, it fails with *"You must either
provide fightIDs, or provide startTime and endTime."*

### 2.4 Slot indices, read off the icons

Slot numbering was established from icon filenames rather than assumed:

| Slot | Read from | Slot | Read from |
| --- | --- | --- | --- |
| 0 | `inv_helm_…` head | 9 | `inv_glove_…` hands |
| 1 | `…neck…` neck | 10 | `inv_ring_…` ring |
| 2 | `inv_shoulder_…` shoulder | 11 | `…ring…` ring |
| 4 | `inv_chest_…` chest | 12 | `inv_121_trinket_…` **trinket** |
| 5 | `inv_belt_…` waist | 13 | trinket |
| 6 | `inv_pant_…` legs | 14 | `inv_cape_…` back |
| 7 | `inv_boot_…` feet | 15 | `inv_knife_…` main hand |
| 8 | `inv_bracer_…` wrist | 16 | off hand |

Slots 3 and 17 were not identified and this design does not depend on them.

### 2.5 An item-sourced cast can be joined to its item by name

Warcraft Logs names an on-use trinket's spell after the item. Joining the ability dictionary
this project has already cached — 4274 ids under 2834 distinct names — against the 81 items
equipped by the five players of `VCGkLQtPwNRA8HhD`:

```
equipped items: 81 (10 trinkets)
names also known as an ability: 5 (4 trinkets)
```

Four of the ten equipped trinkets have a name that is also an ability name. The other six are
passive: they fire no named spell, so they can never produce a "you never pressed it" finding and
correctly produce no match. One non-trinket also matched, an item whose equip effect fires a
named spell.

**This is evidence, not proof, and the design treats it as such.** The measurement shows that a
name match reliably indicates an item source. It does **not** show that every item-sourced
ability matches by name — an on-use effect named differently from its item would not be caught.
So a non-match means *unknown*, never *this is a class spell*, and §5 is built on that asymmetry.

### 2.6 Tier sets need a slot rule, not just `setID`

`setID` is present on tier pieces and absent elsewhere, but counting equal `setID`s naively
over-counts. Across ten players in two reports:

- The **tier** set is class-specific and occupies slots `{0, 2, 4, 6, 9}` — head, shoulder,
  chest, legs, hands. Observed: 2055 Death Knight, 2060 Mage, 2062 Paladin, 2063 Priest,
  2064 Rogue, 2065 Shaman, 2067 Warrior. Counts ran 4 or 5 pieces.
- **Set 2070 spans classes**, appearing for a Rogue, a Paladin, a Death Knight and a Warrior, in
  slots 12 and 15 — a trinket and a main hand. It is not tier.

So the tier count is *the number of pieces carrying the `setID` that occupies the tier slots*,
and the design derives it that way. Because that rule is an inference from seven observed sets
rather than something the API states, the finding it feeds is badged `derived`, not `measured`.

### 2.7 Enchantable slots do not need to be hardcoded

Across the same ten players:

| Slot | Enchanted | Slot | Enchanted |
| --- | --- | --- | --- |
| 0, 2, 4, 6, 7, 10, 11, 15 | 10 / 10 | 1, 3, 5, 8, 9, 12, 13, 14, 17 | 0 / 10 |
| 16 (off hand) | 1 / 10 | | |

The eight fully-enchanted slots are unanimous, and the never-enchanted slots are equally
unanimous. **The sample therefore defines the rule.** A slot counts as enchantable when every
comparable member of the sample enchanted it; a slot the sample left bare is not a finding, and
the off-hand case — enchantable for some specialisations and not others — falls out correctly
without a special case.

This keeps the project's no-hardcoded-season-data invariant intact, and it survives an
expansion changing which slots take an enchant, without an edit.

---

## 3. Scope

### 3.1 In scope

1. A `Loadout` on every player: equipped items and the secondary stat block.
2. `compare.spells.missing` stops stating a false dichotomy, in all three of its branches.
3. A gear comparison: an item the sample ran and the player did not; a missing enchant; a tier
   piece count.
4. A stat comparison: each secondary's rating against the sample's median and range, with the
   share-of-budget reading alongside it.
5. A consumable comparison: flask, food, augment rune and damage potions.

### 3.2 Out of scope

- **Gems.** `gems` is in the payload and is not read. Gem choice is a stat decision already
  covered, less directly, by §6.3.
- **`bonusIDs`.** Unverified in meaning; nothing is built on it.
- **Weapon oils and stones.** Considered and dropped — one consumable family is enough surface.
- **Talents.** §2.2: the data is not there, and the existing route already works.
- **Converting ratings to percentages.** §2.1: no API source for the coefficient.
- **Healthstones and health potions.** `analysis/consumables.py` keeps them, keeps its death
  gate, and is not touched.

---

## 4. What is fetched, and for whom

One query is added: `playerDetails(fightIDs: [N], includeCombatantInfo: true)`, at 2.00 points.

It runs for the analysed run and for each member of the **parse sample** — the top parses of the
analysed player's specialisation — because that is the axis on which a stat block and a gear list
mean something for one player. At five references that is **+12.00 points** on an analysis that
costs about 6.00 today, against an hourly budget of 3600.

It does **not** run for the speed sample. Fast completions of a dungeon are a group-level
reference frame; comparing one player's crit rating against the median of five arbitrary players
in five different specialisations would be a number with no meaning. §5's third branch is what
keeps the speed axis honest without it.

`Player` gains `loadout: Loadout | None`. It is optional, and every consumer must handle `None`:
the speed axis will not have one, and neither will any run already in the cache.

---

## 5. The refusal that was missing

`_missing_sample` (`comparison/spells.py:322`) emits `compare.spells.missing` with the detail
*"That is either a talent not taken or a button not pressed; the log cannot tell which."*

A new pure helper resolves the question the detail cannot:

```
item_sourced(ability_name, loadouts) -> EquippedItem | None
```

It returns the item whose name equals the ability's name in any of the given loadouts, and
`None` otherwise. Three branches follow, and each one produces a true sentence:

**The ability resolves to an item the player does not have.** The finding leaves the spell family
entirely and becomes `compare.gear.missing_item`, badged `measured`: every top parse equipped
this item; the player did not, and here is what they ran in that slot instead. Nothing is
suppressed — the observation was always true, and it was only ever filed under the wrong heading.

**The ability resolves to an item the player does have.** The finding stays in the spell family
and gets stronger, not weaker: the player had the item equipped and never used it. The false
dichotomy is replaced by a fact, and the `measured` badge is now earned.

**The ability does not resolve, or the player's loadout is unknown.** The finding stays as it is,
with one word of the detail changed: *"a talent not taken, a button not pressed, or an item not
owned — the log cannot tell which."* Three branches instead of two, which is what the log
actually supports.

That third branch is the important one. It is what §2.5's asymmetry demands — a non-match means
unknown — and it is also what fixes the lie on the speed axis and on every run already cached,
where no loadout exists to consult. **The correctness fix does not depend on the new fetch.**

---

## 6. Analysers

All five live under `src/wowperf/domain/comparison/`, following the one-family-per-module
convention already set by `route.py`, `tempo.py`, `spells.py` and `uptime.py`. Every one obeys
the existing sampling rules: withheld below three comparable members, falling back to a single
named reference, and saying so when it does.

### 6.1 `compare.gear.missing_item` — `measured`

From §5. An item every member of the sample equipped that the analysed player did not, reached
only through a cast the sample made and the player did not. It is not a general gear audit: the
tool has no opinion on what the player *should* wear, only on the specific case where a piece of
advice would otherwise have been unfollowable.

### 6.2 `compare.gear.enchant` — `measured`

A slot every comparable member enchanted and the analysed player left bare (§2.7). The slot is
named. The enchant is not recommended by name — the sample may disagree among themselves, and
the tool does not rank enchants.

### 6.3 `compare.gear.tier` — `derived`

Pieces of the tier `setID` occupying slots `{0, 2, 4, 6, 9}`, against the sample's count (§2.6).
Badged `derived` because the tier-slot rule is inferred from observation, not stated by the API.

This finding also does work for the rest of the report: a player two tier pieces short of the
sample has a throughput explanation that the cast comparison currently attributes to the player.

### 6.4 `compare.stats.rating` — `derived`

One row per secondary — crit, haste, mastery, versatility, and leech, avoidance and speed where
non-zero — carrying the player's rating, the sample's median, and the observed range. The same
shape as every other comparison in this tool: a median and a range, never a mean.

A second sentence carries the reading that item level cannot explain: each stat as a share of the
player's total secondary rating, against the sample's share. A top parse out-gears the analysed
player, so it holds more of every stat, and the raw gap on its own would restate the item-level
confound that `confounds.py` already reports. The share is the part that reflects a decision —
gems, enchants, which piece was chosen — rather than a gear level.

Both sentences are shown. The rating is the fact; the share is what makes the fact worth reading.

### 6.5 `compare.consumables.*` — `measured`

Two shapes of data, one family.

**Flask, food and augment rune are auras.** Reference members already carry `auras`
(`comparison/sample.py:46`), and the buff-table machinery already exists (`AURA_TABLE_QUERY`,
`queries.py:371`), so this comparison rides data the project already fetches. It needs one new
hand-maintained file, `data/consumable_buffs.toml`, carrying the buff ability ids under three
categories with a `verified` date — the same shape as `data/defensives.toml` and the other
curated lists, and the escape hatch the no-hardcoded-season-data invariant provides for constants
with no API source.

**Damage potions are casts.** They need a new category in `data/consumables.toml`. That file's
header currently excludes the combat potion group deliberately, on the grounds that it interacts
with the health-potion cooldown. That exclusion is amended, not silently reversed: the header
gains a note saying the group is now read for comparison and still excluded from the
death-gated survival analysis, which is what the original reasoning was about.

The finding states presence and count against the sample. It does not price a missing flask in
damage, because the tool has no way to compute that and the LLM is forbidden from computing
anything.

---

## 7. Domain model

Three frozen types in `src/wowperf/domain/model.py`, beside `Player`:

```
EquippedItem   item_id, slot, name, item_level, enchant_id, enchant_name, set_id
StatBlock      crit, haste, mastery, versatility, leech, avoidance, speed
Loadout        items: tuple[EquippedItem, ...], stats: StatBlock
```

`Player` gains `loadout: Loadout | None`.

`StatBlock` holds ratings as integers and offers no percentage anywhere, so no caller can
accidentally present one. The domain layer performs no I/O, as ever: the new query lives in
`adapters/wcl/queries.py`, the ingest in `adapters/wcl/ingest.py`, behind the existing port.

---

## 8. The report

The four new families surface in the **Players** tab, in the per-player card, through the
existing `COMPARISON_PREFIXES` mechanism at `report/players.py:54`. Gear and stats read as one
block — what the player brought — and consumables as another.

No new tab. No new script behaviour. `tests/adapters/render/test_html_invariants.py` continues to
hold the report to one inline script that shows, hides and highlights, and nothing else.

---

## 9. Amendment to the master design

**§6.5's treatment of gear as a confound only.** `confounds.py:110` disclaims trinkets and
embellishments as uncorrected, which was accurate when item level was the only gear signal
available. With `Loadout` in the model, a specific item the sample ran and the player did not is
a finding in its own right (§6.1), and the disclaimer narrows accordingly: it continues to cover
the aggregate effect of gear the tool does not compare, and stops implying that no gear
difference can be identified at all.

Nothing else in the master design is reopened.

---

## 10. Testing

Test-driven throughout, per `.claude/skills/testing/test-driven-development`.

- **Unit** — `item_sourced` across all three branches, including the unknown-loadout path; the
  tier-slot rule against a fixture carrying both a tier set and a cross-class set like 2070; the
  enchant rule against a sample that disagrees; the share-of-budget arithmetic; every sampling
  refusal below three members.
- **Integration** — the comparison service assembling the new families, and the ingest turning a
  recorded `playerDetails` payload into a `Loadout`, including the `combatantInfo: []` case that
  a missing `includeCombatantInfo` produces.
- **End-to-end** — marked `e2e`, against the real API, no mocks.

Test fixtures use `Emberkin`, `Stonewake`, `Bríala` and `Кириллица`. No real character name
enters `tests/`, and no item name from a real player's gear is committed to this repository.

The known trap in this codebase is a test that cannot fail. Each analyser's test must be seen to
fail against the unmodified code before the code is written.
