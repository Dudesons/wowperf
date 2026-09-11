# Mythic+ Post-Mortem: The Death Recap — Design

**Status:** Approved in conversation 2026-09-07, implemented 2026-09-08. Phase I of
`2026-09-06-audit-and-improvement-roadmap.md`.

**Authority:** `2026-09-03-mplus-postmortem-design.md` remains the authority on analysers, badges
and comparison rules, and `2026-09-05-mplus-report-design.md` on the report, wherever this document
is silent. This document replaces the death card of the report design's §4 and amends its §5 row 5;
it extends the postmortem design's §5.8 and §5.9 and closes the question its §5.2 amendment left to
"a later phase". Where the documents disagree, this one is newer and wins; each disagreement is
amended back into the older document, dated, by the plan that implements this design.

**Depends on:** Phase H, merged into `master` at `03c58ed`.

**Not in scope:** the multi-reference sample for comparisons, the per-player page (Phase J), any
new finding. See §9.

---

## 1. What a recap is for

A death card today names the killing blow, lists the hits of the last ten seconds, and says which
defensives and consumables were off cooldown. It answers "what hit me" and "was anything up" as
two separate lists, and leaves the reader to join them.

The recap joins them. Its first question is **what actually killed this player**: the last ten
seconds as one timeline of hits, absorbs, heals and the player's own casts, with the player's
health after each event. Its second question, answered in the same glance, is **could they have
survived it**: every saving tool the group had for this player — the player's own defensives, the
healing consumables, and the externals their teammates could have cast on them — each with its
state at the moment of death and, when it was on cooldown, an upper bound on how long it had left.
A third line, under the timeline, says how the player came back.

The order is deliberate. Availability without the timeline invites the wrong lesson: "press it
earlier" when the killing hit was unmitigable, or "nothing was up" when a heal three seconds
earlier would have carried them. The timeline without availability is a curiosity. Together they
let the reader judge burst against attrition against silence from the healer, and see what was in
hand for each.

Every rule the two older designs impose still holds: the domain performs no I/O; the LLM computes
no number; every claim carries a badge; no field name is used that the wcl-api skill has not
verified; nothing about other players' logs is kept beyond the cache tier the postmortem design
§3.3 already defines.

## 2. What is fetched

Three changes in the Warcraft Logs adapter. Nothing in the domain learns a field name.

**The casts query gains `includeResources: true`.** With it, each cast event carries `hitPoints`
and `maxHitPoints` for the event's source actor — the caster. These are the only health readings
the log offers for a player, because the hits a player takes carry no hit points for the target
(wcl-api skill, "The event stream, probed for a death recap", 2026-09-06). Same query, same
pagination, larger rows.

**The damage-taken ingest stops discarding fields.** Today it keeps `unmitigatedAmount` alone.
It will also keep `amount`, which is what reached the target's health after mitigation and
absorption, and `absorbed`, which is what a shield soaked. Both are in the payload already.

**Two small queries per death, issued once the deaths are known.** Both are event queries scoped
to the dying player with `targetID`, so each returns a handful of rows:

- `dataType: Healing` over `[death − run-up, death]`, giving `heal` events with their `amount`,
  and `absorbed` events with `extraAbilityGameID` naming the absorbing aura.
- `dataType: All` over `[death, return]`, where `return` is the player's first cast aimed at
  another actor after the death, or the fight's end if there is none. A `resurrect` event in that
  window carries the resurrecting spell as `abilityGameID`, the caster as `sourceID` and the
  player as `targetID`. The window ends at the return because a resurrection that revived the
  player necessarily precedes their first action; anything later belongs to a later death.

*Amended 2026-09-07:* the first bullet's field roles are reversed. On an `absorbed` row,
`abilityGameID` names the shield and `extraAbilityGameID` names the hit it soaked — measured
across 43 rows over four deaths on 2026-09-07 and recorded in `.claude/skills/wcl-api/SKILL.md`.

*Amended 2026-09-07:* the second bullet's query does not work as specified. `targetID` is ignored
on `dataType: All`: a sixty-second window asked for one player returned 7087 rows, of which 428
targeted them. What ships instead is one query per fight with
`filterExpression: "type = 'resurrect'"`, which returns every resurrection in a 31-minute fight
for one point and no pagination.

Every query is cached and its `rateLimitData` recorded like every other. The plan's first task
measures, on the real run, what casts with resources and the two scoped queries cost, and records
the figures with dates in the wcl-api skill before any later task depends on them.

## 3. The domain model

### 3.1 Three event records

The loaded run gains three tuples — `health_samples`, `healing` and `resurrections` — each
defaulting to empty so every existing fixture still constructs:

```python
class HealthSample(Frozen):
    actor_id: int
    timestamp_ms: int
    hit_points: int
    max_hit_points: int

class HealingEvent(Frozen):
    actor_id: int            # the player healed or shielded
    source_id: int
    ability_id: int
    ability_name: str        # the heal, or the absorbing shield
    amount: int
    timestamp_ms: int
    absorbed: bool           # True for an `absorbed` event, False for a `heal`

class Resurrection(Frozen):
    actor_id: int            # the player brought back
    caster_id: int
    ability_id: int
    ability_name: str
    timestamp_ms: int
```

A health sample is built from every cast that carried resources. Casts that carried none produce
no sample. The ingest module remains the only place that knows the field names.

### 3.2 The damage record

`DamageTakenEvent` keeps `amount` as the unmitigated figure, because the per-ability comparison
and every existing test read it that way, and gains two fields beside it:

```python
    health_damage: int = 0   # the log's `amount`: what reached health
    absorbed: int = 0        # the log's `absorbed`: what a shield soaked
```

The defaults keep existing fixtures valid. A fully absorbed hit therefore reads as unmitigated
damage above zero, health damage zero, and absorbed equal to the shield's share — three facts the
old record collapsed into one.

### 3.3 Externals

`data/externals.toml` lists, per specialisation, the cooldowns a player casts on someone else to
keep them alive: Pain Suppression, Ironbark, Blessing of Sacrifice, Life Cocoon and the like. The
file has the shape of `data/defensives.toml` — a `verified` date, then one table per `"Class/Spec"`
holding `ability_id`, `name`, `cooldown_seconds` and an optional `charges` — and the same rules:
base cooldowns without talent reductions, every id ~~verified against the API's ability lookup on
the dated day~~ **verified from the game's own spell data on the dated day, the way
`data/defensives.toml` was** *(corrected 2026-09-07 — no such API lookup exists; an id that has
to match what the log itself emits, as `data/resurrections.toml`'s does, is verified against the
log instead, see §3.4)*, and a spec absent from the file produces no claim.

In the domain, `ExternalAbility(CooldownAbility)` and `Externals` mirror `DefensiveAbility` and
`Defensives`, with the same `for_spec`. The loader gains `load_externals`. The existing test that
forbids one ability in both the defensive and the throughput file for one spec is extended to
three files: an ability lives in at most one of them.

*Amended 2026-09-07:* this changed existing behaviour, not only added a rule. Ironbark and Lay on
Hands were personal defensives in `data/defensives.toml` and are now externals: Druid/Restoration,
Paladin/Holy, Paladin/Protection and Paladin/Retribution no longer produce a "defensive never
pressed" finding for them, and a death card judges each as a teammate's tool rather than the
player's own.

### 3.4 Telling a self-resurrection from a release

A player who comes back without a `resurrect` event either released and ran back, or brought
themselves back with Reincarnation or a Soulstone. The two carry different lessons, and the recap
tells them apart. The probe recorded a Reincarnation only as an ordinary `cast` and did not look
for a paired `resurrect` event, so the plan's spike settles the mechanism:

- **If the log emits a `resurrect` event for a self-resurrection**, with the player as both
  source and target, the query of §2 already catches it and nothing more is needed.
- **Otherwise** `data/resurrections.toml` lists the self-resurrection spells — a handful of ids,
  verified and dated like every other data file — and the rule is: a cast of a listed spell by the
  dead player, after the death and before any other cast of theirs, is a self-resurrection.

Either way the domain sees a `Resurrection` whose caster is the player themselves.

*Amended 2026-09-07:* the log does not emit a `resurrect` event for a self-resurrection, so the
first branch above never fires and the second is what ships. A player on the measured fight died
and came back 1.5 seconds later with Reincarnation, and the log carries no `resurrect` row for
it — only a `cast` of the spell and the cooldown debuff around it. A self-resurrection is
therefore recognised from the cast of a listed spell, and `data/resurrections.toml` holds that
list. The id in the file is the one the log emits, `21169`, not the one the spell database offers
for the Shaman ability, because an id matched against log events has to come from the log. The
Soulstone's self-resurrection is deliberately absent: no id could be verified as one the bearer
casts, so a Soulstone save reads as a release.

## 4. The computation

One pure module, `src/wowperf/domain/analysis/recap.py`, no I/O, three functions. Each takes the
loaded run, the data tables it needs, and one death. The report builder calls them and formats
the result; the template loops over what the builder made.

### 4.1 The timeline

Every event in `[death − run-up, death]` where the player is the target or the actor: hits, with
health damage and absorbed amount; absorbs, naming the shield; heals, with amount and source;
and the player's own casts. `run-up` is `RUN_UP_SECONDS`, the same constant the availability rule
uses, so the timeline and the "available at death" judgement speak about the same seconds and a
change to one is a change to both. Rows are sorted by time and labelled by seconds before death.
The last row is the killing blow, which the death record already names.

Overkill is not shown. It lives in the `Deaths` table, which this design does not fetch (§10).

### 4.2 The health column

Health is known exactly only where the player cast something, so the column is **reconstructed**
and badged `derived`:

- The anchor is the most recent health sample at or before the window opens, or failing that the
  first sample inside the window. Rows before any anchor carry no value.
- Walking forward, a hit subtracts its health damage; a heal adds its amount, capped at the last
  sampled maximum; an absorb changes nothing, because the shield took it; a sample replaces the
  running value outright.
- Each value is shown as a percentage of the last sampled maximum.
- When a sample disagrees with the running value, the sample wins and nothing is said on the
  card. The provenance tab states the method and that it re-anchors at every reading.
- A player with no health sample anywhere before the death has an empty column, and the card
  says so in one line rather than leaving a blank the reader would read as "no data on this row".

The arithmetic is sound because the log's `amount` on a hit is what reached health and the
healing stream reports absorbs as their own events. It drifts when an event is missing or the
player's maximum changed between readings; the re-anchor bounds the drift to one interval.

### 4.3 Availability

The set for one death is the player's own defensives (`Defensives.for_spec`), the two consumable
categories, and every external in `Externals.for_spec` for each teammate's specialisation, labelled
with its owner's display name. Each ability lands in exactly one of four states:

| State | Rule | Shown as |
| --- | --- | --- |
| pressed in the window | its owner cast it in `[death − run-up, death]`; for an external, only a cast whose `target_id` is the dying player counts | "pressed, 4 s before" |
| ready | fewer presses than `charges` fall in `[death − cooldown, death]` | "ready" |
| on cooldown | otherwise; the bound is `last press + cooldown − death`, rounded up to a whole second | "at most 14 s left" |
| not seen this run | its owner never cast it in the fight | "not seen this run" |

*Amended 2026-09-07:* a **ready** row whose readiness arrived inside the run-up says for how long,
as a lower bound — "ready, for at least 4 s" — because base cooldowns are longer than talented
ones, so the true moment was no later. Without this, an ability that came off cooldown mid-burst
would read exactly like one ready all along.

*Amended 2026-09-07:* a group with no rows says why it is empty, and that line is not the caveat
that qualifies rows that are present — the two purposes share one field. For consumables the
group can be empty two ways: nothing is listed for the run, or every category's cooldown window
reaches back before the run began. The line names both without claiming which.

"Not seen this run" is listed and never judged, for the reason the postmortem design §5.8 gives:
a talent not taken looks exactly like a button never pressed. "Ready" for an external means the
teammate could have cast it; it does not say they should have, and the card's copy must not.

The consumable categories keep the visibility rule of `consumables_up_at`: a category is judged
only when its whole cooldown window lies inside the fight, since a potion drunk before the timer
started is invisible, and the caveat that the log never proves a potion was carried stays on the
card in the same words. A category never takes the "not seen this run" state — no talent gates a
potion — so a category drunk nowhere in the fight is "ready" when visible and absent otherwise.

The bound is an upper bound and the badge is `inferred`, with the reason unchanged: the log emits
no cooldown reset, no charge refresh and no talent reduction, so the true remaining time is at
most the figure shown. Understating what was up cannot produce a false accusation; the bound
errs the same way.

A specialisation absent from a data file produces no rows from that file and one quiet line
saying the tool has no data for it — the report design's distinction between "checked, none" and
"not checked" survives per group.

### 4.4 The return

Exactly one of four lines:

1. A `Resurrection` targeting the player whose caster is someone else, after the death and before
   the player's first cast aimed at another actor: "Resurrected by *caster* with *spell*, N s after
   death."
2. A `Resurrection` whose caster is the player: "Self-resurrected with *spell*, N s after death."
3. Otherwise, when the player has a cast aimed at another actor before the run ends: "Released;
   first action against an enemy N s after death." The anchor is the one the death cost already
   uses (postmortem design §5.2, amended 2026-09-06), so the two figures agree by construction.
4. Otherwise: "Not seen acting again this run."

Lines 1, 2 and 4 are `measured`; the log states the event, or states its absence. Line 3 is
`derived`; the release itself leaves no event, and "released" is the only reading left once a
resurrection is excluded.

## 5. The view model

`DeathCard` keeps `player`, `class_name`, `when` and `killing_blow`, and replaces its run-up rows
and availability lists with typed rows the template loops over without deciding anything:

```python
class RecapRow(Frozen):
    seconds_before: str      # "6.2 s"
    kind: str                # "hit" | "absorb" | "heal" | "cast" — a row class, never a judgement
    ability: str
    detail: str              # "12,480 to health, 3,200 absorbed" / "+9,100 from Thrall" / ""
    health: str              # "62%" or "" before the first anchor
    health_percent: int | None   # width of the inline bar; None renders no bar

class AvailabilityRow(Frozen):
    ability: str
    owner: str               # "" for the player's own; a teammate's display name for an external
    state: str               # "pressed" | "ready" | "cooldown" | "unseen" — a row class
    detail: str              # "4 s before" / "" / "at most 14 s left" / "not seen this run"

class AvailabilityGroup(Frozen):
    title: str               # "Defensives" | "Consumables" | "Teammates' externals"
    rows: tuple[AvailabilityRow, ...] = ()
    badge: Badge | None = None     # inferred; None when the group has no data for the spec
    note: str = ""           # the no-data line, or the consumable caveat

class DeathCard(Frozen):
    player: str
    class_name: str
    when: str
    killing_blow: str
    timeline: tuple[RecapRow, ...] = ()
    health_badge: Badge | None = None    # derived; None when the column is empty
    health_note: str = ""                # why the column is empty, or ""
    came_back: str = ""
    came_back_badge: Badge | None = None
    availability: tuple[AvailabilityGroup, ...] = ()
```

Every string is formatted by the builder. `kind` and `state` are closed vocabularies the template
maps to CSS classes and to nothing else.

*Amended 2026-09-07:* `AvailabilityRow.detail` carries the word "ready" — "ready" alone, or
"ready, for at least 4 s" — rather than leaving it empty, so the state a defensive card exists to
show never rests on colour alone. §4.3's table of states governs here: this section's comment
originally showed an empty detail for a ready row with no lower bound, which contradicted it.

## 6. Template and CSS

Inside `<section id="tab-deaths">`, each card keeps its head — player, killing blow, when — and
below it a two-column body that stacks under a narrow viewport:

- **Left, the timeline** as a table: seconds before, ability, detail, health. Each row carries
  `class="{{ row.kind }}"` so hits, absorbs, heals and casts read in colour at a glance; the
  health cell holds the percentage and a thin inline bar whose width is `health_percent`. The
  killing blow is the last row. Under the table, the return line with its badge, and the health
  note when the column is empty.
- **Right, availability** as three small groups in the order own defensives, consumables,
  teammates' externals. Each row is the ability, the owner where there is one, and the detail;
  `class="{{ row.state }}"` lets ready rows sit quiet, pressed rows read as used, cooldown rows
  show the bound and unseen rows dim. One badge per group, linking to `#provenance`, and the
  group's note beneath it.

The stylesheet stays in the one file, no resource is fetched, and the inline script of the tabs
design is untouched: the recap adds no behaviour. The death findings beneath the cards stay where
Phase H placed them, with their not-additive caption.

## 7. Testing

TDD at each layer, in the order the plan builds them.

- **Domain, `analysis/recap.py`.** The timeline includes exactly the four kinds inside the window
  and nothing outside it. The health column: anchor before the window, anchor inside it, no anchor,
  a heal capped at the maximum, an absorb leaving health unchanged, a sample overriding a drifted
  value. Availability: each of the four states for an own defensive, the charges rule with two
  charges, an external pressed on this player versus on someone else, a consumable outside its
  visibility window, a spec absent from a file. The return: each of the four lines, a resurrect
  event after the first action ignored, a self-resurrection recognised by whichever mechanism the
  spike chose.
- **Ingest.** Fixture payloads for a cast with and without resources, a hit with `amount`,
  `absorbed` and `unmitigatedAmount`, a `heal` and an `absorbed` event, a `resurrect` event; the
  two scoped queries carry the right `targetID`, `startTime` and `endTime`.
- **Repository.** The per-death queries are issued once per death and pass through the cache.
- **Builder.** One card per death with the rows formatted as §5 says; the badges present; the
  no-data note where a spec is absent.
- **Render.** The four row kinds and four states reach the page as classes; the badges link to
  provenance; the golden `minimal.html` is regenerated and its diff read in full; the one-inline-
  script invariant is unchanged.
- **End to end.** On the real run, the new queries are cached, the spend is printed, and every
  death renders a timeline and three availability groups.
- **The spike**, first task of the plan, measured and recorded in the wcl-api skill: the point cost
  of casts with resources, of the two scoped queries, and whether a self-resurrection emits a
  `resurrect` event.

## 8. Amendments to other documents, made in the same plan

- `2026-09-05-mplus-report-design.md` §4: the death card of §5 above replaces `DamageRow` and
  `DeathCard`. §5 row 5: fed by `loaded.deaths`, `loaded.damage_taken`, `loaded.healing`,
  `loaded.health_samples`, `loaded.resurrections`, and three data files.
- `2026-09-03-mplus-postmortem-design.md` §5.8 and §5.9: the two-state answer becomes the four
  states of §4.3, and the externals join it; §5.2's closing sentence points here.
- `2026-09-06-audit-and-improvement-roadmap.md`: the D3 heading reads "confirmed, cause open"
  although the §5.2 amendment and the ingest already anchor on the first cast aimed at another
  actor; it is corrected to "amended 2026-09-06, return recorded by Phase I".
- `.claude/skills/wcl-api/SKILL.md`: the measured costs and the self-resurrection answer, dated.
- `.claude/skills/mplus-analysis/SKILL.md`: what the recap can honestly say — a health value is
  reconstructed, a remaining cooldown is an upper bound, "released" is a reading not an event.

## 9. Out of scope, deliberately

- **A sample of references** for the comparisons. Separate brainstorm, separate design.
- **New findings.** The recap is a card. `defensives.unused.*` and `consumables.*` keep their
  place and wording; whether the four states should feed them is a later question.
- **Overkill and the Deaths table.** See §10.
- **Judging a teammate.** An external shown "ready" is a fact about a cooldown. No finding, no
  ranking and no narrative sentence is derived from it here.
- **The per-player page** (Phase J).

## 10. Decisions this design records

1. **Timeline first, availability beside it.** The card leads with what killed the player; the
   saving tools sit next to it, not above it.
2. **Externals from teammates are in**, with their own data file and their owner named on every
   row, at the cost of a hand-maintained table and a fourth dated data file.
3. **A fixed ten-second window**, shared with the availability rule, rather than the API's
   per-death `deathWindow`, whose rule is undocumented and would give two cards on one page
   different spans for reasons the page cannot state.
4. **Health is reconstructed between readings**, re-anchored at each, badged derived, method on
   the provenance tab. Known points alone would leave the burst that killed a silent player blank.
5. **The return is on the card**, in one of four lines, and a self-resurrection is told from a
   release by the mechanism the spike settles.
6. **Data comes from extended streams and two tiny scoped queries per death**, not from one `All`
   stream for the whole fight, whose cost was never measured, and not from the `Deaths` table,
   which has no health and a three-event snippet. Overkill goes with the table.
7. **A remaining cooldown is printed as an upper bound**, never as a value. The log cannot say
   more.

## 11. Known gaps, carried forward

- The health curve is blind between a player's casts. A player who stops casting for the last
  seconds shows a straight arithmetic line through the burst, and a missed event shows as drift
  until the next reading. The badge and the provenance note carry this.
- "Released" is inferred from the absence of a resurrection, and the return time is the first
  action against an enemy, which can trail the actual respawn by the run back.
- The externals file, like the defensives file, is maintained by hand and dates. A spec missing
  from it silently produces no external rows for that teammate.
- The Deaths tab grows with each death. A run with many deaths becomes a long tab; Phase J's
  nested groups are the designed answer if it needs one.
