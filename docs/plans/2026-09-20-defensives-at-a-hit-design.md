# Defensives at the moment of a hit — held, faded, or not said

**Status:** approved 2026-09-20. Implements the part of `2026-09-18-wipe-analysis-design.md`
§7.4 that survives measurement, and **corrects that section's premise** — see §2.3.

---

## 1. What this answers

A death card says `pressed` when the player cast a defensive in the ten seconds before they
died. It cannot say whether the buff was **still up when the blow landed**. Press Barkskin nine
seconds before dying with an eight-second duration and the page credits the player with having
done the right thing.

The aura table records every interval each aura was up. That is the only thing in the log that
separates those two cases, so `pressed` splits:

| State | Means |
| --- | --- |
| `held` | the aura was on the player when the blow landed |
| `faded` | it was not |
| `pressed` | we cannot say |

That is the whole deliverable. **It corrects an overstatement rather than adding an insight**,
and §2.3 is honest about how much smaller that is than what §7.4 proposed.

---

## 2. Scope

### 2.1 In scope

The three-state split; a roster-wide aura fetch on the raid path so the split can be made for
every player rather than one; and the quota reading that fetch costs.

### 2.2 Out of scope

| Deferred | Why |
| --- | --- |
| Non-lethal hits | §7.4's "at the moment of a hit" covers every hit. Deaths are where the page is already organised and where the claim carries weight; widening re-opens the count problem for a narrower payoff. |
| Retiring `defensives.never` | Its 29-of-55 problem is real and it is a *different* problem. It was in this scope while the design was larger; once the core shrank to a three-state split, bundling it became scope creep. Its own piece of work. |
| Reading `buff_ids` off the killing blow | The rejected route. See §3.2. |

### 2.3 What §7.4 got wrong, measured

§7.4 proposed that `buff_ids` makes **"a hit landed with nothing mitigating it"** measurable, and
offered that as the prize — the honest neighbour of the claim §5.5 forbids.

Measured 2026-09-20 by walking 387 cached response bodies, 234,879 events carrying a `buffs`
string, and every lethal blow among them:

- **278 lethal blows.**
- **250 (89.9%)** carried some aura.
- **30 (10.8%)** carried a defensive from `data/defensives.toml`.
- **248 (89.2%)** carried none.

A finding that fires on "nothing was mitigating it" would therefore fire on nine deaths in ten.
It would say almost nothing about almost every death, and it would reproduce exactly the
drowning that made `defensives.never` reach 29 of 55 findings on a real report. **The premise is
dropped, and it is recorded here so the next reader does not re-derive it.**

What survives is the narrower claim in §1, which the same data supports: only 30 lethal blows had
a defensive active, so most presses the card credits today did not hold.

---

## 3. Where the answer comes from

### 3.1 The aura table, which already knows

Two functions in `report/cover.py` answer this between them, and both already exist:

- **`resolve_aura(auras, ability_id, ability_name)`** finds the player's own aura for a cast, by
  id first and by name second. The aura table is keyed by the id of the *buff*, while
  `data/defensives.toml` records the id of the spell *cast* to apply it, and for some abilities
  those differ — its docstring names Alter Time (108978 casting, 342246 buffing) and Greater
  Invisibility (110959 against 110960). **The mapping problem is solved here already**, and no
  data-file column is needed for it.
- **`band_holding(aura, start_ms, end_ms, at_ms)`** returns the single band covering a moment, or
  `None`. It deliberately refuses to merge touching bands, because a merged span would let one
  press claim the duration another press earned.

So the rule is: resolve the ability to an aura, ask whether a band holds the death's timestamp.
`held` when one does, `faded` when none does, `pressed` when the aura cannot be resolved or the
player has no aura table at all.

> **Amended by §8.1 (2026-09-20).** "The death's timestamp" is the mis-specification the live run
> falsified: a death strips the bands being read. The moment asked about is the **killing blow's**,
> and a death whose killing blow is not in the fetched stream reads `pressed`. The rest of this
> section stands.

> **Amended again by §8.3 (2026-09-20).** The instant is still the killing blow's, and **a band
> ending at the instant the death stripped that player's auras counts as covering it.** §8.1
> asserted from 21 deaths on one fight that the strip lands exactly on the blow; across 105 deaths
> it lands 1 to 3 ms *before* it on two, and those two printed `faded` over defensives that were up.
>
> **Several of one player's independent auras ending at the same instant is the death stripping
> them, not each expiring.** On the worked example two raid buffs over 218 seconds long and a
> 30.8-second rune end within 2 ms of each other, which no natural expiry explains. §8.3 measured
> the discriminator across the eleven fights: **7 to 21 of the player's other bands co-end when the
> ability was stripped, 0 or 1 when it expired, and nothing in between.** A tolerance constant on
> `band_holding` was refused instead, because no measurement here justifies its width.
>
> **The reading is three-way, and its two numbers are the measured clusters' own edges rather than
> a cut between them.** A single cut would decide cases the data does not decide, which is what §5
> exists to prevent:
>
> | co-ending abilities | reading |
> | --- | --- |
> | at or below `EXPIRED_CO_ENDING_ABILITIES` (1) | not a strip; the blow's own answer stands |
> | at or above `STRIPPED_CO_ENDING_ABILITIES` (7) | a strip; the aura was up when the blow landed |
> | between them (2 to 6) | `pressed`, the honest unknown |
>
> **This table is not the whole rule, and reading it alone would mislead.** It is reached in exactly
> two situations: when no instant at or before the death is a strip outright, and when one is but the
> band ended **after** it. The case it is *not* reached in is the one that would otherwise surprise a
> reader — a band ending **before** the strip. There the aura was already gone when the death took
> the rest, and **position settles it as `faded` with the count never consulted**, so a band with 3
> co-enders reads `faded` there rather than `pressed`. §8.3's "Fixed" subsection carries the
> consequence: it is why the 11 correct `faded` rows never reach the no-man's land.
>
> **A band counts as stripped only when it *ends inside* the instant, never when it merely runs
> through it.** The strip is read only after the blow has already answered `None`, so a band
> spanning the strip instant without covering the blow ended between the two: it outlived the
> removal and then ran out, and crediting it would assert the aura was up when the blow landed while
> its own band says it had ended. Such a band falls to the count instead of being condemned on
> position. This matters most where the reach-back below fires, since the further back the anchor
> reaches the more room a band has to span an instant without ending in it.
>
> **What that costs, stated exactly, because the loose version of it is tempting.** `held` remains
> *reachable* — a band ending after the latest qualifying instant ends in one that does not qualify,
> or it would itself be the latest, so `held` was never on offer for that band. But rows that
> previously read `held` do change, and that is the point of the fix: measured over the cached
> tables, 1430 become `faded` and 77 become `pressed`. Reading the count rather than condemning on
> position changes the answer only for a tail of **three to seven** abilities behind the strip, which
> answers `pressed` instead of `faded`; at one or two it is `faded` either way, and at eight or more
> the tail is itself a strip and answers `held`.
>
> **The residual, which is real and belongs here rather than in a report.** Where a death's removal
> was genuinely logged across a gap wider than a millisecond, the tail *is* the strip and its members
> were up when the blow landed — yet below an eight-ability tail they read `faded` or `pressed`. A
> small split tail is therefore a false `faded`, §6's first failure mode. Nothing measured separates
> it from an ordinary expiry: both are a band ending with little beside it, and the width that would
> join a tail to the run before it is the tolerance this design has refused throughout. **A lone
> trailing band is the commonest such shape** — 14 of the 188 qualifying runs are followed by another
> band end within 60 ms — though none of those is a defensive spanning the strip. Searched for and
> not found: across all 133 cached tables and all 163 qualifying instants, **no defensive band spans
> a qualifying strip and ends after it**, at window widths of 60 ms, 1 s and 5 s. The region is empty
> in real data, which is why the fixed point did not move when this changed.
>
> **One further behaviour change, named rather than implied.** A band ending after the strip was
> `faded` on position before and now reaches the count, so it can answer `pressed` at 2 to 6
> co-enders — a `faded`→`pressed` move that did not exist as a class before. Exposure: **24 of the
> 2760 defensive band ends in the cached tables, 0.87%.**
>
> **Both edges are re-derived in the unit the code counts, which is distinct abilities, not bands.**
> They do not transfer by assumption. Of the 140,366 runs of adjacent band ends in the 133 cached
> aura tables, only 195 carry one ability twice and the largest of those holds 6 bands — so no run
> of seven ends or more counts an ability twice, and over the range that matters the two units
> coincide exactly, putting the stripped edge at 7 in both. The expired edge was measured directly
> in ability units over the rows this section calls genuinely expired, matched by the band lengths
> it records: **0 co-ending abilities 15 times, 1 co-ending ability 20 times, and never more.**
>
> Two further properties keep it from over-correcting, and both are measured rather than chosen.
> The instant read is **the latest one that is a strip**, not the instant holding the player's
> latest band end: an unrelated aura ending between the strip and the death would otherwise be
> anchored on, its instant would hold one ability, and every defensive just stripped would fall back
> to `faded`. That shape is real — of the 188 runs of seven abilities or more in the cached tables,
> **14 are followed by another band end 2 to 60 ms later and 7 of those within 15 ms**, against a
> blow-to-death window of 15 to 55 ms on fight 30. An older pile-up — a keystone party leaving
> combat drops a dozen procs together — is passed over for any strip after it.
>
> **Where no strip is found after it, the search reaches back to that older pile-up. It stops at the
> press.** The refinement only ever runs for a press inside the run-up, and **a band cannot end
> before the press that opened it**, so no instant earlier than the **earliest** of those presses
> can be the strip of a band they opened. It is a bound the log itself gives — a timestamp read off
> the row's own presses — and not a look-back tolerance in milliseconds, which is the constant this
> design has refused throughout.
>
> **The earliest press and not the latest**, because the same conflation lurks on this side too:
> what is read is the aura's latest band end at or before the death, which may belong to an earlier
> press while a later one landed after that band ended — a second press inside the 15-to-55 ms gap
> between the strip and the death is enough. Bounding at the later press throws the death's own
> strip away and answers `pressed` where the band ended inside it. `seconds` still counts from the
> latest press; only the search's floor moves.
>
> **What the bound does and does not claim.** It does *not* exclude nothing that could have been
> right: the band read may belong to a press older than the run-up entirely. What is exact is that a
> death's own strip sits within milliseconds of the death, so no bound inside the run-up can exclude
> one; what is cut off is the older instants the residual describes. And while `since_ms` is
> different in kind from the tolerance refused here — a per-row timestamp read out of the log,
> justified causally rather than calibrated — the honest qualifier is that the worst-case reach is
> now `RUN_UP_SECONDS` = 10.0, which *is* a chosen constant. It is pre-existing and justified
> elsewhere, but it is not nothing.
>
> **The bound was earned, not precautionary.** §8.4 measured the unbounded search on live data: no
> qualifying instant at all on 31 of 105 deaths, and on 5 of those the search reached an older one,
> once by **1777 seconds**. The tempting argument is that this cannot do harm, because an instant
> half an hour early cannot hold a band a run-up press opened. That is true of the band the press
> opened and **false of what the code reads**, which is the aura's latest band end at or before the
> death — and that falls back to a *previous* use when the press left no band of its own. A test
> built on the observed 1777 s answered `held` on a band that stale before the bound went in.
>
> **What remains is bounded, not gone.** An older pile-up *inside the run-up* can still answer for a
> death whose own removal is too small — a keystone party leaving combat drops a dozen procs
> together — and a defensive ending there reads `held` for an instant that was not the death's, §6's
> second failure mode. Separating those two needs the tolerance above, so the residual stays
> recorded rather than patched, now at the size of a run-up rather than of a whole fight. It is
> pinned by a test rather than left to be discovered.
>
> **How close the edge of 7 sits to real data, since the same measurement says so.** Of those 31
> deaths with no qualifying instant, **11 were exactly one ability short of the edge**. Those rows
> fall to the count, which is silence and not error, but the figure belongs beside the edge's
> justification: the separation is clean where it was measured, and real deaths sit against it.
>
> And bands ending on **consecutive milliseconds** are one instant, because one millisecond is the
> finest gap the log can express, so the width is the clock's own resolution rather than a number
> chosen to fit. It is load-bearing even so, and calling it "not a tolerance" would overstate it:
> grouping only exact-equal milliseconds splits the worked example's strip into instants of one,
> four and five abilities, none of them a strip. What bounds the risk the other way is that
> adjacency does not chain — of those 140,366 runs, 138,031 are a single millisecond wide and the
> widest is 4 ms.

`availability_at` keeps its stated input discipline — "who was there, and what they pressed,
rather than the fight that carries them" — and gains one parameter:

```
availability_at(..., auras: PlayerAuras | None = None) -> AvailabilityAt
```

**`None` means no aura table for this player, and every state stays `pressed`.** A resolved aura
with no band over the death is `faded`; that is a reading, not an absence.

### 3.2 Why not `buff_ids`

`DamageTakenEvent.buff_ids` carries every aura on the player at the instant of a hit, and it was
this design's first route. It was rejected on two measurements:

- **The mapping.** Ten defensive cast ids appear in the cached logs and never appear as a buff
  id — 198589 Blur, 48743 Death Pact, 109304 Exhilaration, 115203 Fortifying Brew, 110959 Greater
  Invisibility, 202168 Impending Victory, 6789 Mortal Coil, 2565 Shield Block, 1856 Vanish,
  360995 Verdant Embrace. A cast id absent from the buff ids means either a different aura id or
  no aura at all, and the damage stream cannot tell those apart. `resolve_aura`'s name fallback
  can.
- **The killing blow.** Reading auras off the lethal hit means a death whose killing blow was
  never fetched has no answer. Bands do not care which event killed the player.

The route's one advantage was coverage: `buff_ids` rides on damage events that are already
fetched for everyone, which is why §4 exists.

---

## 4. The roster's auras

Aura tables are fetched **per actor**, one `AuraTable` query each. The Mythic+ path already
fetches every roster player's (`load_run_with_auras`, about 1.06 points per player). The raid
path does not: it fetches auras only for comparable parse subjects.

Measured 2026-09-20 against the cached canonical wipe: **one aura table for a twenty-player
report**. Building §3 on bands without changing this would make the split silent for nineteen
players in twenty, which is not a feature.

So the raid path gains the analogue of `load_run_with_auras`. The domain is already shaped for
it — `LoadedEncounter.auras` exists and is simply never filled — so this is a fetch change, not a
model change.

**It restores more than the split, and that was unremarked until the whole-branch review found
it.** `LoadedEncounter.auras` is read by three other things besides §3: `deaths._press_band`,
`deaths._availability_tooltips`, and `finding_tooltip.tooltips_by_finding_id`. The first of those
matters most, because `build_deaths` **drops a cast row from a death's timeline outright** when
the press resolves to no band — so with one table for twenty players, nineteen raid death cards
in twenty drew no press at all, and no cover rectangle beside the health curve, and their
defensive findings carried no aura tooltip. The live page after the fetch carries **45
`<tr class="cast">` rows and 45 `class="hp-cover"` rectangles**, where before it carried the
subject's alone. This is accepted as an improvement rather than a regression, and it is recorded
because it was a real behaviour change that no test, golden, commit body or design section named
at the time: the goldens cannot catch it, since none of them carries a single availability row and
none is built through the CLI's fetch. `_press_band`'s drop rule is now pinned on the raid path by
`tests/domain/report/test_recap_from_an_encounter.py`, against a roster player who is not the
comparable parse subject — the case the fetch exists for.

**Cost: about 21 points for a twenty-player fight**, against an hourly budget of 3600, and
nothing for a player whose table is already cached. A failed fetch for one player leaves that
player with no bands and their states at `pressed`, exactly as `_auras` already does on the
Mythic+ side: a failed aura fetch must never discard a report that has already been paid for.

The real reading goes in `.claude/skills/wcl-api/SKILL.md` under the rate-limit section, dated,
in the style of the readings already there.

---

## 5. The split

Keeping `pressed` as an explicit third state is the design's load-bearing decision. It becomes the
honest *unknown* rather than an implied success, and every path that cannot resolve lands there:
no aura table for the player, an ability that resolves to no aura, or a fetch that failed.

`seconds` keeps its meaning across all three — how long before the death the ability was cast — so
nothing downstream changes shape.

`held` and `faded` are **measured**, read off the aura table's own bands. Worth stating because
the neighbouring `ready` and `cooldown` states are inferred, and the card now carries both kinds
at once.

**No change to `data/defensives.toml`.** §3.1's name fallback is what makes that true, and it is
worth saying out loud because the first draft of this design specified two new columns and ten
hand-verified readings that turned out to be unnecessary.

---

## 6. What would make this wrong

- **An unresolved ability reading as `faded`.** A false accusation, which is the thing this
  analyser most has to avoid. `resolve_aura` returning `None` must yield `pressed`, never `faded`.
- **A failed or missing aura fetch reading as `faded`** rather than as silence.
- **`faded` read as blame.** It is a statement about timing, not effort: pressing a six-second
  buff against a cast that lands nine seconds later is reasonable and unlucky. §5.5 forbids the
  page assigning intent.
- **`held` read as "it worked".** It means the aura was up, not that it was enough. A player can
  die with Barkskin held because the right answer was a larger cooldown. The wording must not
  imply otherwise.
- **The name fallback matching the wrong aura.** It is a heuristic, scoped to one player's own
  `on_self` list. If it ever matches something unrelated, the page would state a band that is not
  the ability's. The scoping is the defence; a collision is worth a test.

---

## 7. Testing

Beyond unit coverage of the three states:

- **A band over the death** yields `held`; **a resolved aura with no band over it** yields
  `faded`.
- **An ability that resolves to no aura**, and **a player with no aura table**, both yield
  `pressed`. Each needs a test that fails if the default ever becomes a resolution.
- **The name fallback** resolves an ability whose cast id and buff id differ, against a real pair.
- **A failed aura fetch** for one player leaves that player at `pressed` and does not disturb
  the rest of the report.
- Golden-file update, and a live run against the canonical wipe.

**The live run is the premise check, not a formality.** It answers the one number no cached walk
could: of the presses the card labels `pressed` today, how many are `held` and how many `faded`.

The falsifier is stated here so it cannot be rationalised later: **if essentially none come back
`faded`, the overstatement this design exists to correct does not occur in practice, and the
design was not worth building.** That result is to be recorded, not explained away.

---

## 8. What the live run found (2026-09-20)

Measured on the canonical wipe, report `cW38jmwdnZfbHVL4` fight 30, twenty players and
twenty-one deaths. Counted over the rendered page's availability rows, `<li class="...">`, twice:
once against the death event as §3.1 originally specified, and again after §8.1 moved the question
to the killing blow. Both readings are kept, because the first is the evidence for the correction
and the second is what the feature says today. 252 rows either way, the same rows.

| state | at the death event | at the killing blow |
| --- | --- | --- |
| `cooldown` | 124 | 124 |
| `ready` | 73 | 73 |
| `unseen` | 48 | 48 |
| `faded` | 6 | **1** |
| `pressed` | 1 | 1 |
| `held` | **0** | **5** |

The rest of this section reads the first column; §8.2 reads the second.

**The falsifier did not fire, but the result does not vindicate the build either, because five of
the six `faded` rows are false.** Checked press by press against the bands they were judged from:

| ability | cast before death | its band ran | band ended before the death | true state |
| --- | --- | --- | --- | --- |
| Ice Barrier | 2149 ms | 2115 ms | 34 ms | still up |
| Astral Shift | 3321 ms | 3273 ms | 48 ms | still up |
| Fade | 8399 ms | 8344 ms | 55 ms | still up |
| Shield Block | 7030 ms | 7015 ms | 15 ms | still up |
| Shield Wall | 2803 ms | 2788 ms | 15 ms | still up |
| Feint | 9609 ms | 6013 ms | 3596 ms | **genuinely faded** |

**Root cause: an aura band is truncated by the death that ends it.** A buff a player is carrying
when they die is stripped by the death, and Warcraft Logs timestamps that strip 15-55 ms *before*
the death event's own timestamp. §3.1 asks `band_holding` whether a band covers `death_ms`
exactly, so for any defensive that was in fact up at the moment of death the answer is
structurally `None`. The Protection Warrior settles it: Shield Wall and Shield Block, two
independent auras, both end at the identical timestamp `9997398` against a death at `9997413`,
and that Shield Wall band is 2788 ms long against an eight-second ability. It did not expire; it
was cut off.

So `held` is very nearly unreachable for the dying player's own defensives, and the page prints
"over by then" over a Shield Wall the same page's tooltip credits with mitigating 85% of what
arrived while it was up. This is §6's first failure mode — *"An unresolved ability reading as
`faded`. A false accusation, which is the thing this analyser most has to avoid"* — arriving by a
route §6 did not anticipate: not an unresolved ability, but a resolved one whose band the death
itself foreshortened.

**On the premise.** Corrected for the defect, exactly **one** of the six resolvable presses had
genuinely faded when the blow landed. The overstatement this design exists to correct is
therefore real but uncommon — one press in six on this fight, not the routine case §1 implies.
That is a thinner mandate than the design assumed, and a second fight should be measured before
concluding the split earns its cost. The `pressed` row is a consumable, whose `ability_id` is
`None` by construction, so it is the designed unknown behaving correctly.

**Status: not fit to ship as built.** The fix is not a tolerance constant. The design's own title
and §6 speak of *the blow*, and `_press_state` should ask whether the band covered the killing
blow rather than the death event that strips it — an instant that lands inside the band for all
five misjudged presses and outside it for Feint, with no magic number. That changes which instant
§3.1 names, so it is a design decision and is recorded here rather than taken unilaterally.

### 8.1 The instant, corrected

**§3.1's instant was the death event, and it was wrong.** It said "ask whether a band holds the
death's timestamp", and §8 measured what that produces: `held` on **0 of 252** rows, and **five of
six** `faded` rows false accusations about named players. The mechanism is not a tolerance
question. A death strips the auras the player was carrying, and Warcraft Logs timestamps that
strip 15 to 55 ms *before* the death event, so no aura a death removes — which is every active
defensive in `data/defensives.toml` — can have a band covering the death. §3.1 asked a question
whose answer was fixed before the log was read.

**The instant is the killing blow.** §1 already said so — "the aura was on the player when **the
blow landed**" — and §6 speaks of the blow throughout. Only §3.1 named a different moment, and it
is §3.1 that is corrected. For all 21 player deaths on the canonical wipe the killing blow lands
**exactly on** the strip timestamp, so the same bands that answered `None` for every death answer
for every blow. (This paragraph first said 23; the encounter carries 21 deaths and the page 21
cards, re-counted from the domain on 2026-09-20. The figure was wrong, not the claim.) The blow's moment is read from the damage stream by `killing_blow_id` — the hit on
the dying player whose ability is the one the death names, latest at or before the death — and
never as "the last damage event before the death", which is a different claim that a stray tick in
the final milliseconds gets wrong.

**This reintroduces the dependency §3.2 rejected, in a softer form, and that is accepted
knowingly.** §3.2 dismissed the `buff_ids` route partly because "a death whose killing blow was
never fetched has no answer"; judging bands against the blow makes that true again. The softening
is that only the *refinement* depends on the blow, not the row: a death with **no hit of that
ability at all** in the fetched stream reads **`pressed`**, the design's explicit unknown, and the
press is still named and still timed. Falling back to the death's own timestamp would look like an
answer and be the defect above, so there is no fallback. The mapping half of §3.2's rejection is
untouched: `resolve_aura`'s name fallback still does the work `buff_ids` could not.

**The matching rule carries a residual, and it is not the unknown.** The moment is the *latest*
hit of that ability at or before the death, with no staleness bound. So the unknown is reached
only when the stream holds no such hit whatever; where the true lethal hit is missing but an
**earlier** hit of the same ability is present, that earlier hit is taken as the blow, and the
bands are read at an instant with nothing to do with the death. A defensive pressed after that
stale hit then reads `faded` — a false accusation from a *resolved* ability, which is the failure
class this whole section exists to record, arriving by a third route. The same gap opens from the
other side if Warcraft Logs ever timestamps a lethal hit *after* the death event, since the rule
looks only at or before it. Both were left open deliberately: closing them needs a staleness
tolerance of at least 55 ms with nothing to justify the number, and this design has refused
magic numbers throughout. `DamageTakenEvent.overkill`, which the log carries only on a lethal
blow, is a second and independent handle on the same hit and would close both without a constant.
**It is no longer unmeasured — §8.2 prices it, and on this fight it is exact.** Neither residual
occurred here, so the measurement bounds the risk rather than removing it.

**`band_holding`'s closed interval is now load-bearing.** Every correct `held` sits *exactly* on a
band's upper boundary, because the strip and the blow share a millisecond. Narrowing the
comparison to a half-open interval, or a Warcraft Logs change putting the strip 1 ms before the
blow, would flip every `held` row back to `faded` and reproduce §8 in full. The contract is stated
in the function's own docstring and pinned by a test built from the real timestamps.

**The Mythic+ path carried the same defect and was never measured.** `build_deaths` is shared by
`analyze` and `raid`, and `load_run_with_auras` has always filled `auras` for every roster player,
so every keystone death card has been judging presses against the death since this feature
shipped. §4 discusses the raid path's aura coverage and says nothing about this, because nobody
looked. Both paths now read the blow, and both are covered.

### 8.2 Re-measured at the blow, and the premise answered (2026-09-20)

Same command, same report, same fight, with §8.1's instant in place: `wowperf raid` on
`cW38jmwdnZfbHVL4` fight 30. 252 availability rows, counted over `<li class="...">`, which occurs
in exactly one place in the template set. The second column of §8's table is this reading.

**Every row §8 got wrong is now right, and the one it got right is unchanged.** The five presses
§8 proved were still up read `held`; the one press that had genuinely ended reads `faded`; the
consumable, whose `ability_id` is `None` by construction, stays at the designed unknown.

| ability | says now | §8's reading | §8's verdict on that reading |
| --- | --- | --- | --- |
| Ice Barrier | `held`, 2.1 s before death, still up | `faded` | false |
| Astral Shift | `held`, 3.3 s | `faded` | false |
| Fade | `held`, 8.4 s | `faded` | false |
| Shield Block | `held`, 7.0 s | `faded` | false |
| Shield Wall | `held`, 2.8 s | `faded` | false |
| Feint | `faded`, 9.6 s before death, over by then | `faded` | genuine |
| a health potion | `pressed`, 4.6 s | `pressed` | the designed unknown |

The §8 contradiction is gone with it: the Protection Warrior's Shield Wall row now says "still up"
beside its own tooltip crediting that ability with mitigating 85% of what arrived inside its cover.
The two halves of that row agreed on nothing before and agree now.

**The unknown was never reached. 21 of 21 deaths resolved a killing blow; none fell back to
`pressed` for want of one.** Read from the domain, not from the page: the cached encounter loaded
and `killing_blow_ms` called per death. No death named a `killing_blow_id` of zero. The
blow-to-death gap ran 1 to 55 ms across all 21, which widens §8's observed 15-55 ms at the low end
and does not disturb the mechanism. So §8.1's softened dependency on the damage stream cost
nothing at all on this fight — the single rendered `pressed` row is the consumable, not a missing
blow.

**`overkill` agrees with the matching rule exactly, in both directions.** §8.1 left it unmeasured
as the thing that would close the rule's residual without a magic number. Measured here:

- 15,798 damage-taken events in the fight carry **21** non-zero `overkill` values, against **21**
  deaths, and every one pairs to a death by `(actor, ability)`. No overkill hit is left over.
- For each of the 21 deaths, **exactly one** hit of the ability the death names carries
  `overkill`, and it is **exactly the hit `killing_blow_ms` picked** — 21 of 21, no disagreement.
- No overkill hit of a death's named ability lands *after* that death, so the second half of the
  residual — a lethal hit timestamped after the death event — did not occur here.

That last point matters more than the agreement does. The rule takes the *latest* matching hit at
or before the death with no staleness bound, and on this fight it was asked to choose among as many
as **474** candidate hits of the named ability for one death; it still landed on the
overkill-carrying one every time. The stale-hit residual is real in principle and was not exercised
in practice. **This is one fight, and it does not license removing the residual from the record.**
It does say that switching the rule to `overkill` would change nothing observable here, which is an
argument for leaving the code alone rather than for rewriting it.

**On the falsifier.** §7 wrote it down before any of this ran: *if essentially none come back
`faded`, the overstatement this design exists to correct does not occur in practice, and the design
was not worth building.*

One row in 252 comes back `faded`. Read literally, **that is the falsifier firing.**

It is not the whole answer, for one reason that counts and one that does not:

- **It counts that `held` is now reachable, five times.** Every `held` row is a press the page used
  to report as a bare `pressed` and now reports as covered. That is the same overstatement being
  corrected in the other direction, and §1's table always claimed both halves. Six of the seven
  presses in the run-up across twenty players now carry an answer the page could not give before.
- **It does not count that the numbers are flattering.** Six resolvable presses is a denominator
  in single figures. One fight, one composition, one wipe.

**The verdict, stated as weakly as the evidence deserves: the premise is not confirmed, and the
design is not vindicated by this run.** What the design set out to correct — a press credited as
if it held when it had ended — happened **once** in six presses on this fight. What it corrects
in the other direction — a press now shown to have held — happened five times, but that half was
never the case §1 argued from, and five of those five are also the rows §8's defect had libelled,
so they are as much a repair of this branch's own damage as a new insight. **The honest reading is
that the feature is now correct and its value is unproven.** A second fight, and preferably a
Mythic+ run through the same shared `build_deaths`, is the cheapest thing that would move this
either way; the aura fetch it rides on costs about 20 points of 3600 for a twenty-player fight and
nothing at all on a warm cache. **That was done. §8.3 carries the answer, and it moves the verdict:
the premise holds and the correction is not complete.** Read §8.3 rather than this paragraph's
"unproven", which describes a one-fight denominator that no longer stands.

**Nothing here argues for reverting.** The split is cheap, its states are honest, and §8's five
false accusations are gone. But the design asked whether it was worth building, and on one fight
the answer is *not demonstrated*, which is what §7 required to be recorded rather than explained
away.

**The page was read, and all six states occur.** Served over `python -m http.server` and opened in
a fresh tab, Deaths tab selected, plus the rendered HTML read directly. `held` renders
"2.8 s before death, still up" in the measured green, `faded` renders "9.6 s before death, over by
then" in the same amber as `cooldown` — not an alarm colour — and `pressed` renders
"4.6 s before death" with no judgement at all. The wording is timing, not blame, and "still up"
asserts that the aura was up and stops there, as §6 requires. One observation for the record:
`held` shares its green with `pressed` (`--badge-measured`), so a reader scanning colour alone sees
a success tint on a row that belongs to a player who died. The prose does not claim sufficiency;
the colour is one confidence tier away from claiming it.

**Quota: 1.00 point of 3600, fully warm cache** — the two `RateLimit` reads and nothing else. The
reading is in `.claude/skills/wcl-api/SKILL.md`. Reading the blow adds no query: `DamageTaken` is
already fetched for every friendly across the whole fight, so §8.1's correction is free.

### 8.3 Widened to eleven fights, and the premise answered (2026-09-20)

§8.2 asked for a second fight and a Mythic+ run before the split's value could be called either
way. Eleven fights were measured instead: four twenty-player raid fights across two rosters, and
seven Mythic+ runs across five parties. **105 deaths, 1212 availability rows.**

**The instrument, stated before its readings.** Counted over `<li class="...">`, which occurs in
exactly one place in the whole template set (`_deaths.html.j2:112`). The pattern was built from a
row read out of a rendered page first — `          <li class="ready">` — and is written
`<li class=.([a-z]+).>`, with `.` in place of each quote, because a double-quoted grep pattern
returns zero here on files that demonstrably contain the string. It was verified against fight 30
before it was trusted anywhere else: 252 rows, 124/73/48/1/1/5, which is §8.2's recorded reading
exactly. Death cards were counted the same way over `<div class="recap-availability">`, one per
card, and gave 21 on fight 30. Every state count below was then reproduced a second time from the
domain, by re-running `availability_at` over the cached fight, and the two instruments agree row
for row on all eleven fights.

| report | fight | path | deaths | blow resolved | rows | `held` | `faded` | `pressed` | `cooldown` | `ready` | `unseen` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cW38jmwdnZfbHVL4` | 30 | raid | 21 | 21 | 252 | 5 | 1 | 1 | 124 | 73 | 48 |
| `cW38jmwdnZfbHVL4` | 26 | raid | 16 | **6** | 184 | 1 | 1 | 1 | 48 | 48 | 85 |
| `cW38jmwdnZfbHVL4` | 8 | raid | 20 | 20 | 221 | 1 | 3 | 6 | 41 | 4 | 166 |
| `DJfap6RcYKhPGHXZ` | 7 | raid | 23 | 23 | 398 | 2 | 3 | 8 | 169 | 46 | 170 |
| `6Kx1P9GbNXrcLdHa` | 36 | M+ | 4 | 4 | 23 | 0 | 1 | 0 | 5 | 12 | 5 |
| `jZVQmxCaqbdKtRN8` | 2 | M+ | 5 | 5 | 30 | 0 | 0 | 2 | 11 | 8 | 9 |
| `HpYwCAvmPFDtz1Jj` | 1 | M+ | 4 | 4 | 30 | 0 | 0 | 0 | 8 | 13 | 9 |
| `VCGkLQtPwNRA8HhD` | 1 | M+ | 3 | 3 | 20 | 0 | 1 | 0 | 9 | 8 | 2 |
| `G7MBJZfNakrcPvAx` | 3 | M+ | 1 | 1 | 6 | 0 | 0 | 0 | 4 | 2 | 0 |
| `BN91L2DXKAR38mpd` | 1 | M+ | 6 | 6 | 34 | 0 | 2 | 0 | 9 | 18 | 5 |
| `wqd4MaK6JZpztV21` | 12 | M+ | 2 | 2 | 14 | 1 | 1 | 0 | 3 | 9 | 0 |
| **total** | | | **105** | **95** | **1212** | **10** | **13** | **18** | **431** | **241** | **499** |

**Only 25 of those rows were ever refinable, and the denominator is 25, not 1212.**
`availability_at` passes `auras`, `window` and `blow_ms` to the dying player's **own** defensives
and to nothing else. An external's aura sits on the dying player but is keyed to the caster's
ability id, and `resolve_aura` is scoped to one player's own `on_self` list, so externals stay
`pressed` by construction; a consumable's `ability_id` is `None` by construction. Of the 18
rendered `pressed` rows, **12 are externals and 4 are consumables** — outside the question
entirely, not failures to answer it. The refinable denominator is `held` 10 + `faded` 13 + the two
own-defensive rows that fell to the unknown = **25 presses in a death's run-up**.

**The two unknowns are the two the design named, one each.** On `cW38jmwdnZfbHVL4` fight 26 a
Protection Warrior's Shield Block reads `pressed` because that death names no killing ability at
all, so `killing_blow_ms` had nothing to match — §8.1's softened dependency on the damage stream,
reached for the first time. On `DJfap6RcYKhPGHXZ` fight 7 a Devastation Evoker's Verdant Embrace
reads `pressed` because `resolve_aura` returns `None` for it: a heal that raises no self-buff is
an ability with no aura to read, which is §3.1's other explicit unknown. Neither is a guess and
neither is a `faded`.

#### The strip can land *before* the blow, and two `faded` rows are false

§8.1 asserted, from 21 deaths on one fight, that "the killing blow lands **exactly on** the strip
timestamp". Across 105 deaths it does not always. Every `held` and `faded` row was re-checked by
§8's own test — do several independent auras of that player end at the same instant, which is the
death stripping them rather than each one expiring? — and the answer separates cleanly, with 7 to
21 co-ending bands on one side and 0 or 1 on the other. Nothing sat in between.

| report | fight | who | ability | says | co-ending bands | strip vs blow | true state |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `cW38jmwdnZfbHVL4` | 26 | Devastation Evoker | Obsidian Scales | `faded` | 9 | 3 ms **before** | **still up** |
| `DJfap6RcYKhPGHXZ` | 7 | Shadow Priest | Fade | `faded` | 10 | 1 ms **before** | **still up** |

**Both were live on the page when this was written, and both are fixed.** §8.4 re-ran all eleven
fights against the strip rule below and read them off the rendered pages: each now reads `held`,
"still up", and nothing else on the eleven moved. The two rows below are the record of what the
defect was, not of what the tool says today.

Both are false accusations about real players, of exactly the class §6 puts first, arriving by the
same mechanism §8 recorded and surviving §8.1's correction. On both, ten or so of that player's
auras — including raid buffs hundreds of seconds long — end within 6 and 11 ms of the death, and
the killing blow lands 1 to 3 ms *after* that instant rather than on it. `band_holding`'s closed
interval, which §8.1 called load-bearing, is exactly one millisecond wide against a miss of one.

**All 10 `held` rows are correct**: every one sits on a strip instant with the blow inside the
band, 7 to 21 co-ending auras confirming it. **11 of the 13 `faded` rows are correct**: their
bands end 200 ms to 4.4 s before the blow with no co-ending neighbour, and their lengths match the
abilities' own durations or, for the absorbs, a shield eaten early. So the honest reading of the
25 is **`held` 12, `faded` 11, unknown 2** — and the page at the time of this reading printed 10,
13 and 2, with two rows on the wrong side. **The page now prints 12, 11 and 2**, measured live in
§8.4.

**This was recorded, not fixed.** Moving the instant again is a §3.1 decision, as §8 said the first
time, and the same objection applies to the obvious patch: a tolerance constant would need a
number no measurement here justifies. What the residual then had was a size — 2 in 25 presses, on
2 of 105 deaths — rather than an argument.

#### Fixed, by the discriminator this section measured (2026-09-20)

§3.1 now reads a band ending at the death's strip instant as covering the blow, and the
discriminator is the one measured above rather than a tolerance: **several of one player's
independent auras ending at the same instant is the death stripping them.**

**The two numbers it carries are this section's own cluster edges, not a cut between them**, and
both were re-derived in the unit the code counts — distinct abilities, not bands. At or below **1**
co-ending ability the band ended as an expiry ends and the blow's reading stands; at or above **7**
the death stripped it; between them the answer is `pressed`. The stripped edge transfers from the
7-to-21 band figure because no run of seven ends or more in the 133 cached tables counts an ability
twice (195 of 140,366 runs do, and the largest holds 6 bands). The expired edge was measured
directly in ability units over the genuinely expired rows named above: **0 co-enders 15 times, 1 co-
ender 20 times, never more.** §3.1 carries the table.

`auras.strip_instant` anchors on **the latest instant that is a strip**, not on the instant holding
the player's latest band end: a single unrelated aura ending between the strip and the death would
otherwise hide it, and of the 188 runs of seven abilities or more in the cached tables, 14 are
followed by another band end 2 to 60 ms later — 7 within 15 ms, against a blow-to-death window of
15 to 55 ms on fight 30. It groups band ends on **consecutive milliseconds**, the log's own
resolution rather than a width chosen to fit, though not a free choice either: grouping only
exact-equal milliseconds splits the worked example's strip into instants of one, four and five
abilities and loses it.

**The anchor's reach-back is bounded at the press, and what is left of it is the rule's known
residual.** When the death's own removal holds fewer than eight abilities it does not qualify and
the search walks further back, but no earlier than the **earliest** press in the row's run-up: a
band cannot end before the press that opened it. Inside that span an older pile-up can still answer
in the death's place, and a defensive ending there reads `held` for an instant that was not this
death's.
Separating the two needs a look-back tolerance no measurement justifies, so that much is recorded
rather than patched, exactly as §8.1's stale-hit residual was.

**The bound itself was earned by measurement, not caution.** §8.4 saw the unbounded search reach
1777 s on a real death, and the argument that an ancient instant cannot hold a run-up press's band
turned out to be true of the band the press opened and false of the band the code reads. §3.1
carries both halves and two tests pin them.

**What the reach-back does *not* widen, because it was closed here:** a band that merely spans the
instant the anchor reached back to. The rule now asks whether the band **ends inside** the strip,
which is what §3.1 always said and what the code did not do — it asked whether the band *covered*
it, and so credited a defensive that was up when an older pile-up dropped and ran out long before
the blow. That was a false `held` whose width grew with the reach-back. A band ending after the
latest qualifying instant ends in an instant that does not qualify — or it would itself be the
latest — so it falls to the count, where `held` was never on offer. **That is not the same as
costing nothing**, and §3.1 states the price: 1430 rows move from `held` to `faded` and 77 to
`pressed` over the cached tables, which is the fix working, and a genuine split-strip tail below
eight abilities now reads `faded` or `pressed` where it was up, which is the residual §3.1 records.

**The corrected counts are the honest reading this section already stated: `held` 12, `faded` 11,
`pressed` 2 of the 25 refinable presses.** The two rows in the table above become `held` and
nothing else moves. The 10 rows that already read `held` are untouched, because a band covering the
blow is answered before the strip is consulted at all. The two unknowns stay `pressed` — a death
that named no killing ability, and a heal that raises no self buff — and neither is a case this
change reaches.

**The 11 correct `faded` rows keep their reading by either path, which is what makes the
three-way rule safe to add.** Their bands end 200 ms to 4.4 s before the blow, so they cover no
strip instant. Where their player's death produces a strip, their band ended *before* it — the
anchor does not reach back past them, because the death's own removal is what it lands on — so
position settles it and the count is not consulted. Where it produces none, the count is the 0 or 1
that sits inside the expired cluster. Neither road reaches the no-man's land. (Position settles it
only for a band ending *before* the strip; one ending after it does reach the count, which is the
case §3.1 describes and none of these 11 is.) An earlier draft of this fix
argued that a three-way rule would silence those rows; that argument was against an *unbounded*
three-way rule and does not hold against one bounded by the measured edges.

**The ambiguous case answers `pressed`, and there are two different cases here — do not read one
for the other.**

- **The co-ending no-man's land**, between the measured clusters' edges: an ability whose band ends
  with **2 to 6** of the player's others. Too many to be the expiry the 0-or-1 cluster describes,
  too few to be the strip the 7-to-21 cluster describes. **This answers `pressed`, and it is a new
  fifth route to that state**, added by this fix. It is why the reading is three-way rather than a
  single cut: a cut would decide what the measurement does not.
- **The four routes §3.1 already named** — no aura table, no window, an unresolved ability, no
  killing blow in the stream — are untouched and still answer `pressed`.

At or below the expired edge the answer is `faded`, not `pressed`: that is a reading off the aura
table and softening it would silence the 11 correct `faded` rows counted above. An unresolved
ability is never `faded`, and it is never `held`.

Verified against the cached aura tables before the next live run, at no quota: the worked example's
Obsidian Scales reads `held` where the blow alone reads `faded`; fight 30's Feint — one of the 11
genuinely expired rows, on a table that does carry a real strip instant at that player's own blow —
still reads `faded`; and fight 30's Fade, a correct `held`, is unmoved. **Re-running the eleven
fights is the next task and this is not a substitute for it.** That was done: **§8.4 carries the
live reading, and it matches this prediction exactly.**

#### The no-blow case, reached once

Ten deaths in 105 resolved no killing blow, **all ten on one fight** (`cW38jmwdnZfbHVL4` 26), and
all ten because the log itself carries `killingAbilityGameID: null` and `killerID: null` — read
back out of the cached `Deaths` page, not inferred. They are the last ten deaths of a wipe, inside
the final 16 s of the pull, two of them after the last damage event in the fight. The ingest is
right and the tool is right: those deaths have no blow to read, and the one press among them says
`pressed`. Every other fight resolved every death: 95 of 105 overall, 25 of 25 on the keystone
path.

#### `overkill` on the Mythic+ path, and why it is not the fix

§8.1 named `DamageTakenEvent.overkill` as the second handle that would close the matching rule's
residual without a magic number, and §8.2 priced it on one raid fight as exact. Measured on the
keystone path, which §8.2 could not reach:

- **25 of 25 Mythic+ deaths resolved a blow; 24 of the 25 chosen hits carry a non-zero
  `overkill`, and in every one of those 24 it is the only overkill-carrying candidate.**
- **The 25th is a fall death.** The blow is `Falling` (ability id 3), picked 1 ms before the
  death and plainly right; none of the three `Falling` hits in that run carries `overkill` at all.
  An `overkill`-keyed rule would have returned the unknown for a death the present rule resolves
  correctly.
- **One `overkill` value sits on a hit that killed nobody.** On `6Kx1P9GbNXrcLdHa` fight 36 a tick
  carries `overkill` 4974 against a player whose only death was 106 s earlier, and whose health
  readings either side of it are 7% before and 18% after. An `overkill`-keyed rule could take a
  survived hit for a lethal one. The mechanism is not established here and is recorded as an
  observation, not explained.
- **The long reach the keystone path was expected to suffer from did not bite.** Its damage stream
  spans a whole run, and the rule was asked to choose among as many as 94 candidate hits of the
  named ability for one death — yet the worst blow-to-death gap across all 25 was **57 ms**, and
  no pick was stale by more than 200 ms.
- **The stale pick appeared on the raid path instead.** On `cW38jmwdnZfbHVL4` fight 26 one death
  names an ability the player took exactly once in the fight, **2989 ms** before dying and
  survived — 29.4M unmitigated, 19.9M of it absorbed — so the bands for that card were read at an
  instant three seconds adrift. That card happens to carry no press, so nothing visible was
  misstated, but §8.1's stale-hit residual is now observed rather than theoretical. Its chosen hit
  carries no `overkill`, so `overkill` would have caught this one.

**Net: `overkill` would have closed one residual and opened two.** It is a better *cross-check*
than the rule and a worse *rule* than the rule. §8.1's suggestion that switching to it "would
change nothing observable" held on one raid fight and does not hold here; the code should be left
alone, and this is now a measured reason rather than an aesthetic one.

#### The falsifier, answered

§7: *if essentially none come back `faded`, the overstatement this design exists to correct does
not occur in practice, and the design was not worth building.*

**Eleven of 25 presses in a death's run-up had genuinely ended when the blow landed — 44%.** The
falsifier does not fire. It is not close to firing.

- **Rate against count, which §8.2 left unresolved, resolves in favour of the rate.** 13 `faded`
  rows in 1212 is 1.1% and reads as "essentially none"; 13 in 25 presses is 52%. §8.2 could say
  only that the two readings disagreed at 1/252 against 1/7. At 25 presses the press-rate reading
  is no longer a small-sample artefact, and it is the one §7 was asking about: §7's "come back
  `faded`" is a statement about presses, not about rows, because a `cooldown` or `unseen` row was
  never a candidate for either answer. **The count reading is answering a different question.**
- **`held` counts too, and it counts 12 times.** Every `held` row is a press this page used to
  report as a bare `pressed` and now reports as covered. Unlike §8.2's five, these are not mostly
  repairs of this branch's own damage: 5 of the 12 are fight 30's, already counted there, and
  **7 are new**, on three fights and two rosters that §8's defect never touched.
- **Independence is much better than §8.2's, and still not good.** The 25 presses come from **six
  separate groups** — two twenty-player raid rosters and four Mythic+ parties — and from **12
  distinct killing-blow abilities** plus one death with none, against fight 30's single mechanic.
  Up to 18 distinct players are involved. But the clustering is real and should not be smoothed
  over, and one of those 12 abilities is `Melee`, which is a generic rather than a mechanic: **10
  of the 25 presses sit on just two raid-wide hits**, one on fight 30 and one on fight 8, each of
  which killed 14 or 15 people with 10 or 11 of them inside 25 ms. `DJfap6RcYKhPGHXZ` fight 7 is
  better behaved — 23 deaths, no two within 25 ms of each other — and `cW38jmwdnZfbHVL4` fight 26
  better still. The six keystone presses are the most independent
  observations in the set — six distinct abilities, four parties, runs 9 to 30 minutes long — and
  **five of those six had genuinely faded**.
- **The two paths disagree, and the shape of the disagreement is interesting.** Raid deaths in a
  wipe cluster on one mechanic, and the defensive was usually pressed 2 to 7 s earlier and was
  still up: 11 `held` against 6 genuinely `faded` across four fights. Keystone deaths are spread
  across a run, and the press was usually 8 to 9 s earlier against a 5 to 8 s button: 1 `held`
  against 5 `faded`. **The path nobody had looked at is the path where the split earns the most.**

**The verdict: the premise holds.** A press credited as if it held when it had ended is not the
rare case §8.2's one fight suggested — it is a little under half of all presses in a death's
run-up, and on the keystone path it is the usual case. §1's claim is supported and §7's falsifier
is answered in the negative. **Two things temper it and neither reverses it**: the denominator is
25, which is small for a 44% figure, and the feature at the time of this reading still printed two
of those 25 on the wrong side, so the split is worth having *and* was not yet finished. (The second
is closed: §8.4 measured 0 wrong of 23 resolved. The first stands.) §8.2's "the feature is now correct
and its value is unproven" is superseded on both halves: the value is shown, and the correctness
is not complete.

> **The second of those two is now addressed in code** — see "Fixed, by the discriminator this
> section measured" above — and **§8.4 confirms it on a live re-run of all eleven fights**: the
> page prints `held` 12, `faded` 11, `pressed` 2, and every one of the 23 resolved rows is correct.
> The first stands: the denominator is still 25.

**Quota: 219.72 points of 3600 across the hour, for all eleven fights.** Two fresh fights of the
already-fetched raid report at 48.20 and 53.20 with the report warm and each fight's own streams
cold; one cold fight of a new raid report at 61.22; seven keystone runs at 3.01 or 5.01 each,
32.07 in total, because `load_run_with_auras` had already fetched every aura table they read; two
aborted runs at 6.01 each, which spend the roster queries before they check the subject's name;
and 4.01 for a fight-list probe. Re-reading the cache through the domain, which every check in
this section rests on, cost nothing. The readings are in `.claude/skills/wcl-api/SKILL.md`.

### 8.4 The strip rule confirmed against the eleven fights (2026-09-20)

§8.3 fixed the two false `faded` rows in code and verified the fix against the cached aura tables
only, closing with *"re-running the eleven fights is the next task and this is not a substitute for
it"*. This is that run. Same eleven fights, same commands, `--no-compare` throughout, cache fully
warm.

**The instrument, again stated before its readings.** Counted over `<li class=.[a-z]*.>` — `.` in
place of each quote, because a double-quoted grep pattern returns zero here on files that
demonstrably contain the string — built from a row read out of the freshly rendered fight 30 page
first, `          <li class="ready">`, and confirmed against the same file through a second grep
engine that is unaffected by the quoting defect. Both agree. Fight 30 read 252 rows,
124/73/48/1/1/5, which is §8.2's recorded reading to the row, so the instrument was checked against
a known answer before it was trusted on the other ten. Death cards were counted over
`<div class=.recap-availability.>`. **Every count below was then reproduced a second time from the
domain**, by re-running `availability_at` over each cached fight with the same `killing_blow_ms`
the report builder passes, and the two instruments agree row for row on all eleven fights and on
all six states.

| report | fight | path | deaths | blow resolved | rows | `held` | `faded` | `pressed` | `cooldown` | `ready` | `unseen` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cW38jmwdnZfbHVL4` | 30 | raid | 21 | 21 | 252 | 5 | 1 | 1 | 124 | 73 | 48 |
| `cW38jmwdnZfbHVL4` | 26 | raid | 16 | 6 | 184 | **2** | **0** | 1 | 48 | 48 | 85 |
| `cW38jmwdnZfbHVL4` | 8 | raid | 20 | 20 | 221 | 1 | 3 | 6 | 41 | 4 | 166 |
| `DJfap6RcYKhPGHXZ` | 7 | raid | 23 | 23 | 398 | **3** | **2** | 8 | 169 | 46 | 170 |
| `6Kx1P9GbNXrcLdHa` | 36 | M+ | 4 | 4 | 23 | 0 | 1 | 0 | 5 | 12 | 5 |
| `jZVQmxCaqbdKtRN8` | 2 | M+ | 5 | 5 | 30 | 0 | 0 | 2 | 11 | 8 | 9 |
| `HpYwCAvmPFDtz1Jj` | 1 | M+ | 4 | 4 | 30 | 0 | 0 | 0 | 8 | 13 | 9 |
| `VCGkLQtPwNRA8HhD` | 1 | M+ | 3 | 3 | 20 | 0 | 1 | 0 | 9 | 8 | 2 |
| `G7MBJZfNakrcPvAx` | 3 | M+ | 1 | 1 | 6 | 0 | 0 | 0 | 4 | 2 | 0 |
| `BN91L2DXKAR38mpd` | 1 | M+ | 6 | 6 | 34 | 0 | 2 | 0 | 9 | 18 | 5 |
| `wqd4MaK6JZpztV21` | 12 | M+ | 2 | 2 | 14 | 1 | 1 | 0 | 3 | 9 | 0 |
| **total** | | | **105** | **95** | **1212** | **12** | **11** | **18** | **431** | **241** | **499** |

**The predicted fixed point is hit exactly: `held` 12, `faded` 11, `pressed` 2 of the 25 refinable
presses.** Two rows moved and nothing else did. Every other cell in the table — 105 deaths, 95
blows, 1212 rows, and the `pressed`, `cooldown`, `ready` and `unseen` columns entire — is identical
to §8.3's, which is the stronger half of the result: a rule that reaches back through a player's
whole aura table could have moved a great deal and moved two rows.

| report | fight | who | ability | §8.3 said | says now | the page's words |
| --- | --- | --- | --- | --- | --- | --- |
| `cW38jmwdnZfbHVL4` | 26 | Devastation Evoker | Obsidian Scales | `faded`, false | **`held`** | "6.1 s before death, still up" |
| `DJfap6RcYKhPGHXZ` | 7 | Shadow Priest | Fade | `faded`, false | **`held`** | "8.8 s before death, still up" |

Both reach `held` by the new route and not by the old one: their bands end 1 and 2 ms *before* the
blow, inside a strip instant holding 10 and 11 of that player's abilities. `band_holding` still
answers `None` for both, exactly as §8.3 measured. The two false accusations §8.3 left live are
withdrawn.

#### The audit: 23 of 23 resolved rows are right, and 0 are false in either direction

Every `held` and every `faded` row was re-checked by §8.3's own discriminator — do several
*independent* auras of that player end at the same instant, which is the death stripping them, or
does the band end alone at a length that matches the ability's own duration?

**All 12 `held` rows are correct.** Ten are answered by `band_holding`: the blow lands exactly on
the band's upper boundary, so the aura table itself says the aura was up, with no inference at all.
Two are answered by the strip. Co-ending abilities at the band's end, across all twelve: **8, 9, 10,
10, 10, 10, 11, 11, 12, 12, 18, 22** — every one inside the stripped cluster, none near its edge
from below except the 8, which is a keystone death whose blow `band_holding` answered anyway.

**All 11 `faded` rows are correct.** Their bands end **200 ms to 4437 ms** before the blow, and the
co-ending count at each band's end is **0 eight times and 1 three times** — the expired cluster
exactly, with nothing in between, which is §8.3's separation reproduced on a second reading. The
band lengths are the abilities' own: Divine Shield 8005 and 8010, Divine Protection 8009, Spell
Reflection 4995, 4998 and 5014, Dark Pact 3988, Feint 6013, Ice Barrier 2411, Prismatic Barrier
18984, and one Feint band of 11512 ms where two casts touch. Nine of the eleven are settled on
position — their band ended before the death's strip — and two on the count, on deaths that produced
no qualifying strip at all.

**The two `pressed` rows are the same two unknowns §8.3 named**, unchanged and neither a guess: a
Protection Warrior's Shield Block on `cW38jmwdnZfbHVL4` fight 26, where the log carries
`killingAbilityGameID: null` so there is no blow to read; and a Devastation Evoker's Verdant Embrace
on `DJfap6RcYKhPGHXZ` fight 7, a heal that raises no self-buff, so `resolve_aura` returns `None`.

**Genuinely false rows: 0 of 23 resolved, in either direction.** No false `faded`, which is §6's
first failure mode, and no false `held`, which is its second.

#### The four residuals, hunted in the wild

All four were left on record by §8.3 and none had been seen live. Two have now been seen in their
*shape* and neither has produced a wrong row.

- **The unbounded reach-back: its precondition fired five times, and it cost nothing.** On 5 of the
  105 deaths the death's own removal did not qualify and `strip_instant` walked back to an older
  pile-up: 64 s, 77 s, 81 s, 348 s and **1777 s** — nearly half an hour — before the death. This is
  the shape §8.3 searched the cache for and did not find, and it is real. **It misstated nothing,
  because none of those five death cards carries a press in its run-up at all**, so no band was
  read against a reached-back instant. The residual is now *observed* rather than theoretical, and
  its price on these eleven fights is still zero. It should not be read as harmless; it was
  unexercised.
- **A strip split across more than 1 ms with a short tail: the shape occurred 6 times, and no
  defensive was in a tail.** Six deaths show a qualifying run followed within 60 ms by a further
  band end, every one of them a tail of exactly **1** ability (gaps of 2, 3, 7, 11, 11 and 21 ms).
  No `held` or `faded` row's band ends in one of those tails — every faded band ended before its
  death's strip and every held band inside it — so the false `faded` this residual describes did not
  occur. Strip widths themselves: 38 instants 0 ms wide, 32 one, 3 two, 1 four.
- **The `faded`→`pressed` class did not fire.** No rendered row reached the co-ending count with a
  value above the expired edge. The 0.87% measured over the cached tables was not visible on any of
  the 105 death cards.
- **The 2-to-6 no-man's land did not fire either, and came within one row of it.** No row answered
  `pressed` by that route. The near miss is the fight 26 Shield Block above: its band ends 24 ms
  before the death with **6** co-enders, squarely in the no-man's land — but the death names no
  killing ability, so the row answers `pressed` at the first guard for a different reason, and the
  fifth route was not the one that spoke. The route remains fixture-only.

**A fifth thing this run measured, which §8.3 did not, and which matters more than any of the four.**
`strip_instant` found no qualifying instant on **31 of the 105 deaths**, and the latest instant on
those 31 held **1, 2, 5, 6 or 7** abilities — **eleven of them exactly 7**, one short of the
`STRIPPED_CO_ENDING_ABILITIES` edge, and most of them 1 to 30 ms before the death, which is a
death strip's timing exactly. So the edge that §8.3 took from the bottom of its measured cluster
declines to call roughly a third of these deaths' removals a strip. Nothing here says the edge is
wrong — §8.3's expired cluster tops out at 1 co-ender, and a 7-ability instant is not that either,
which is why a defensive ending inside one answers `pressed` rather than `faded`. The two `faded`
rows that sit on such deaths are both correct, their bands having ended a full second earlier with
0 co-enders. But the honest statement is that **the rule is silent on a third of these deaths rather
than right about them**, and the three deaths whose latest instant holds only 2 abilities are the
shape that would read `faded` if a defensive ended there. None did.

**`overkill` and the stale pick are unchanged.** 95 of 105 blows resolved, the ten unresolved all on
`cW38jmwdnZfbHVL4` fight 26 and all `killingAbilityGameID: null`, exactly as §8.3 recorded. The
blow-to-death gap ran **0 to 57 ms on 94 of the 95**, and 2989 ms on the one stale pick §8.3 already
names — a Blood Death Knight on fight 26 whose death names an ability taken once, three seconds
earlier, and survived. That card still carries no press, so §8.1's stale-hit residual still
misstates nothing.

#### What this settles and what it does not

**Settles**: the strip rule is correct on every row it answered across eleven fights, two paths, six
groups and 105 deaths; the two false accusations are withdrawn; and the rule moved exactly the two
rows it was predicted to move and no others.

**Does not settle**: the denominator is still 25 presses, which §8.3's concern already stated and
this run does not improve; the reach-back has now been seen reaching 1777 s and has simply not been
asked a question yet; and the `>= 8` edge is silent on 31 of 105 deaths, eleven of them by one
ability. None of these is a reason to add the tolerance constant this design has refused four times.
They are the size of what is left.

> **The reach-back was settled after this section was written, and not the way it was expected to
> be.** The argument put to the question was that it could never do harm: the refinement runs only
> for a press inside the run-up, and an instant half an hour early cannot hold a band that press
> opened. **That argument is sound about the band the press opened and false about what the code
> reads** — the aura's *latest band end at or before the death*, which falls back to a previous use
> when the press left no band of its own. A test built on the 1777 s reach observed above answered
> `held` on a band that stale. So it was reachable, not merely unexercised, and "it misstated
> nothing on these eleven fights" was the right way to have recorded it.
>
> It is now bounded at **the earliest press in the row's run-up**: a band cannot end before the
> press that opened it, so nothing earlier can be the strip of a band those presses opened. The
> earliest and not the latest, because a second press landing after the band ended would otherwise
> cut off the death's own strip. The bound is the log's own and not the look-back tolerance this
> design has refused — with the qualifier that its worst-case reach is `RUN_UP_SECONDS` = 10.0,
> which is a chosen constant, pre-existing and justified elsewhere. What survives is an older
> pile-up *inside the run-up* answering for a death whose own removal is too small — the same
> residual at the size of a run-up rather than of a fight. §3.1 carries it and three tests pin it.

**Quota: 1.00 point per run as each command priced it, 22.00 of 3600 across the hour for all
eleven, on a fully warm cache.** Every run printed `RateLimit` 2 calls for 1.00 and no other line —
four `raid` commands and seven `analyze` commands, all `--no-compare`. The two figures differ
because the closing quota read is unpriced: the balance fell by exactly 2.00 per run, 3600 to 3578.
Re-reading the eleven cached fights through the domain for the audit and the residual scan, several
times each, cost nothing. The readings are in `.claude/skills/wcl-api/SKILL.md`.
