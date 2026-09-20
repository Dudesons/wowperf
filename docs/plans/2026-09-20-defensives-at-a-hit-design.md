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
nothing at all on a warm cache.

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
