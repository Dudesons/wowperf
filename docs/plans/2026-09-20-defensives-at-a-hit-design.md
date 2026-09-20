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
twenty-one deaths. Counted over the rendered page's availability rows, `<li class="...">`:

| state | rows |
| --- | --- |
| `cooldown` | 124 |
| `ready` | 73 |
| `unseen` | 48 |
| `faded` | 6 |
| `pressed` | 1 |
| `held` | **0** |

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
