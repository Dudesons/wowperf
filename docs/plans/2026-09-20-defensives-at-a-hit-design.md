# Defensives at the moment of a hit — held, faded, or not said

**Status:** approved 2026-09-20. Implements the part of `2026-09-18-wipe-analysis-design.md`
§7.4 that survives measurement, and **corrects that section's premise** — see §2.3.

---

## 1. What this answers

A death card says `pressed` when the player cast a defensive in the ten seconds before they
died. It cannot say whether the buff was **still up when the blow landed**. Press Barkskin nine
seconds before dying with an eight-second duration and the page credits the player with having
done the right thing.

`DamageTakenEvent.buff_ids` — every aura on the player at the instant of a hit, parsed from the
`buffs` field and measured 2026-09-11 — is the only thing in the log that separates those two
cases. So `pressed` splits:

| State | Means |
| --- | --- |
| `held` | the aura was on the player when the blow landed |
| `faded` | it was not |
| `pressed` | we cannot say |

That is the whole deliverable. **It corrects an overstatement rather than adding an insight**,
and the scope section is honest about how much smaller that is than what §7.4 proposed.

---

## 2. Scope

### 2.1 In scope

The three-state split, wherever an ability's buff id is known; verified `buff_id` entries for the
abilities whose buff differs from their cast; and a marker for abilities that raise no aura at
all, where the question has no answer.

### 2.2 Out of scope

| Deferred | Why |
| --- | --- |
| Non-lethal hits | §7.4's "at the moment of a hit" covers every hit. Deaths are where the page is already organised and where the claim carries weight; widening re-opens the count problem for a narrower payoff. |
| Retiring `defensives.never` | Its 29-of-55 problem is real and it is a *different* problem. It was in this scope while the design was larger; once the core shrank to a three-state split, bundling it became scope creep. Its own piece of work. |
| Deriving buff ids from the logs | Inference wearing measurement's clothes: right most of the time, silently wrong sometimes, with no way to tell which. It also contradicts the data file's own stated methodology, which is that no API exposes this and every id was read from game data one spell at a time. |

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
a defensive active, so every `pressed` outside that set is either genuinely faded or an id that
does not map.

---

## 3. Where the auras come from

`availability_at` states its own input discipline: it takes "who was there, and what they pressed
-- rather than the fight that carries them". It keeps that, and gains one parameter:

```
availability_at(..., auras: tuple[int, ...] = ()) -> AvailabilityAt
```

`auras` is the aura ids on the dying player when the killing blow landed. **The default `()` means
"not supplied", and every state stays `pressed`.**

One pure helper supplies it:

```
auras_at_death(damage_taken, death) -> tuple[int, ...]
```

It finds the lethal hit for that death and returns its `buff_ids`, or `()` where no matching
event exists. A death whose killing blow was never fetched produces silence, not a guess.

---

## 4. The split

Keeping `pressed` as an explicit third state is the design's load-bearing decision. It becomes the
honest *unknown* rather than an implied success, and every path that cannot resolve lands there:
no auras supplied, no killing blow found, no known buff id, or an ability that raises no aura.

`seconds` keeps its meaning across all three — how long before the death the ability was cast — so
nothing downstream changes shape.

`held` and `faded` are **measured**, read straight off the event. Worth stating because the
neighbouring `ready` and `cooldown` states are inferred, and the card now carries both kinds at
once.

---

## 5. The data file

`data/defensives.toml` gains two optional keys per ability:

- **`buff_id`** — absent means the cast id doubles as the buff id, which holds for 32 of the 42
  defensive ids actually cast in the cached logs. Present overrides it.
- **`no_aura = true`** — the ability raises no lasting aura, so held-or-faded has no answer and
  the state stays `pressed`.

Both are read from game data one spell at a time and dated, as the file's header already requires
of every id in it.

**Ten ids need a reading, and the log cannot say which key each one wants.** These are the
defensive cast ids that appear in the cached logs but never appear as a buff id:

| Id | Name |
| --- | --- |
| 198589 | Blur |
| 48743 | Death Pact |
| 109304 | Exhilaration |
| 115203 | Fortifying Brew |
| 110959 | Greater Invisibility |
| 202168 | Impending Victory |
| 6789 | Mortal Coil |
| 2565 | Shield Block |
| 1856 | Vanish |
| 360995 | Verdant Embrace |

A cast id that never appears as a buff means one of two things — the aura carries a different id,
or the ability raises no aura at all — and **the log cannot distinguish them**, because both look
like absence. Each of the ten therefore gets its own reading against game data before a key is
written down, and until then each keeps neither key and stays `pressed`. Do not guess a category
from the ability's name or from what it does in the game; that is the sort of plausible detail
this repository forbids, and one of these (110959, Greater Invisibility, against buff 110960) has
already cost this project a silently dead feature once.

Two invariants, each with a test: no entry carries both keys, and no entry sets `buff_id` equal to
its own `ability_id`, which would be noise pretending to be a decision.

---

## 6. What would make this wrong

- **An unmapped ability reading as `faded`.** A false accusation, which is the thing this analyser
  most has to avoid. Defended by the `pressed` default and by the `buff_id != ability_id` test.
- **A missing killing blow producing a guess** rather than silence.
- **`faded` read as blame.** It is a statement about timing, not effort: pressing a six-second
  buff against a cast that lands nine seconds later is reasonable and unlucky. §5.5 forbids the
  page assigning intent.
- **`held` read as "it worked".** It means the aura was up, not that it was enough. A player can
  die with Barkskin held because the right answer was a larger cooldown. The wording must not
  imply otherwise.
- **The mapping going stale** when a spell changes, defended the way the rest of the file is:
  dated entries, verified one at a time.

---

## 7. Testing

Beyond unit coverage of the helper and the three states:

- **The matched path** — an ability whose buff id equals its cast id: present in `buff_ids` yields
  `held`, absent yields `faded`.
- **The mapped path** — `buff_id` differing from `ability_id`, against a real pair.
- **The no-aura path** — resolves in neither direction, ever.
- **No auras supplied, and a death with no matching damage event** — every state stays `pressed`.
  Both need a test that fails if the default ever becomes a resolution.
- **The data-file invariants** of §5.
- Golden-file update, and a live run against the canonical wipe.

**The live run is the premise check, not a formality.** It answers the one number the cached walk
could not: of the presses the card labels `pressed` today, how many are `held` and how many
`faded`. The cache carries no report code, so pairing casts to deaths across it risks matching a
cast in one report to a death in another; running the real recap over one report is what settles
it.

The falsifier is stated here so it cannot be rationalised later: **if essentially none come back
`faded`, the overstatement this design exists to correct does not occur in practice, and the
design was not worth building.** That result is to be recorded, not explained away.
