# What dealt the first death, counted across a boss's pulls

**Status:** approved design, planned in docs/plans/2026-09-26-first-death-killing-blow-plan.md.
**Slice:** the second piece of spec B, the family `docs/plans/2026-09-26-night-boss-summary-design.md`
§2 left as "killing blows counted across pulls". It lands in the summary that design built, and on
the standalone progression page, through the analyser both already run.

## 1. Goal

One new progression finding, `progression.repeat.killing_blow`: for each ability, how many of a
boss's attempts had their **first death** dealt by it. "Soul Lash dealt the first death in 4 of 7
attempts."

## 2. Why the first death, and only the first

On a wipe, most deaths come after the raid has already come apart. Counting every killing blow
mostly measures what finishes a lost pull -- an enrage, a raid-wide pulse on the survivors -- and
on a seven-pull boss those abilities would head the list every time. The first death is the one
death per pull the collapse cannot swamp, and it is where a pull starts going wrong.

Two wider readings were weighed and set aside:

- **Every roster death, counted once per pull an ability killed in.** The collapse still dominates,
  more quietly.
- **The first few deaths of each pull.** Sees more, but "a few" is a number no measurement
  supports.

If this proves too narrow once it is live, widening it is a later design with a real distribution
in hand.

## 3. Constraint: nothing new is fetched

- Every input is already on a `LoadedEncounter` both `progression` and `night` load at every tier:
  `deaths` (each `Death` carries `killing_blow_id` and `killing_blow`, `events.py:7-14`),
  `damage_taken`, and `players`.
- No new query, stream or JSON field. The finding joins the list `analyse_progression`
  (`progression_service.py:36`) already returns.
- No page, template or command changes.

## 4. The finding

Added to `src/wowperf/domain/analysis/progression_repeats.py` as `repeat_killing_blow(series:
LoadedProgression) -> Finding | None`, and called from `analyse_progression` beside
`repeat_first_death` and `repeat_ability` (`progression_service.py:141-142`).

**The death it reads.** Each drawn attempt's first death, picked by `_earliest_death`
(`progression_repeats.py:156`) -- the same function `repeat_first_death` uses, ties broken by the
lowest actor id. Both findings therefore speak of the same death on every pull and can never
disagree about which one was first.

**An attempt drops out when:**

1. it has no death;
2. its first death matches no roster player by `actor_id` (a pet, say) -- `repeat_first_death`'s
   own rule;
3. the death names no ability: `killing_blow_id == 0`, the log naming nothing;
4. the lethal hit was dealt by a roster player. The hit is the latest one on the dying player at
   or before the death carrying the death's `killing_blow_id` -- the match `killing_blow_ms`
   (`recap.py:249`) already makes -- and it drops out when that hit's `source_id` is a roster
   player's. This is the rule `repeat.ability` applies to every hit (`progression_repeats.py`,
   `_abilities_in_window`), measured there: friendly hits say nothing about what the encounter
   did.

When no lethal hit matches at all, the attempt **stays**: the log still named the ability, and a
missing hit is not evidence of a teammate. A hit with `source_id` of None stays likewise.

**What it counts.** Per `killing_blow_id`, the qualifying attempts whose first death it dealt. An
ability is named when its count is at least 2. Named abilities are ordered by count, most first,
then by name, and capped at five (`MAX_REPEAT_ABILITIES`, `progression_repeats.py:217`, reused).
The ability's name comes from the death's own `killing_blow`.

**Withheld** -- the function returns None -- when fewer than two attempts qualify, or no ability
reaches two. A mode of one is not a pattern, the same ruling `repeat_first_death` makes.

**No control subtraction.** `repeat.ability` drops any ability that also landed on the deepest
attempt, because there it asks what *kept landing*. Here the question is what *started* pulls
going wrong, and a best attempt that also opened with that death is more reason to name it, not
less.

**Wording and badge.**
- Confidence `measured`: the log names both the first death and its killing blow; the counting is
  arithmetic.
- One ability named: title `"<ability> dealt the first death in <n> of <m> attempts"`, and the
  finding carries `ability_id` and `ability_name`, so its row draws the ability's icon.
- Several: title `"<k> abilities dealt the first death in more than one attempt"`, with each
  ability's count in `detail` and `evidence` and no `ability_id`.
- `m` is the number of qualifying attempts, and the detail says what was excluded and why.
- It names no player and no specialisation. Who died first is `repeat_first_death`'s claim; this
  one is about the ability.

## 5. Where it appears

- **Placement:** the existing `progression.repeat.` prefix in `PROGRESSION_PLACEMENTS`
  (`progression_ledger.py`) sends it to the Repeats tab. No table change.
- **Pages:** the Repeats tab of the standalone `wowperf progression` page, and of every night
  summary.
- **JSON:** each boss's `findings` in the night JSON, and the progression JSON, in the shape its
  siblings have.
- **Goldens:** the standalone progression golden is rendered from hand-built findings, not from
  the analyser, so it carries one hand-built `progression.repeat.killing_blow` finding, which pins
  placement and rendering; the analyser itself is pinned by its unit tests. The night golden's
  fixtures name no killing blow, so it does not move.

## 6. Testing

Every test must be shown able to fail against the code it guards.

**Unit** (`tests/domain/analysis/test_progression_repeats.py`, beside `repeat_first_death`'s own):

- one ability dealing two first deaths fires, with `ability_id` set and the counts in the title;
- two abilities tied at two are both named, with no `ability_id`;
- one repeat among singletons names only the repeat;
- fewer than two qualifying attempts is withheld, and so is no ability reaching two;
- a `killing_blow_id` of 0 drops its attempt from the denominator;
- a lethal hit whose `source_id` is a roster player drops its attempt;
- no matching lethal hit keeps its attempt, and so does a hit with no `source_id`;
- a first death matching no roster player drops its attempt;
- on two deaths at one timestamp, this finding and `repeat_first_death` read the same death;
- the cap at five;
- no roster name appears in title, detail or evidence.

**Integration:** `analyse_progression` returns it (`tests/domain/analysis/test_progression_service.py`);
`build_progression_report` places it in `repeat_rows`.

**End to end:** `tests/e2e/test_progression_e2e.py` and `tests/e2e/test_night_e2e.py` assert
shape and counts only, never a player's name or slug. Where a summary boss carries the finding,
the night suite asserts shape rather than an independent count: between one and five abilities,
each named at two or more attempts and never more than the boss was pulled, at `measured`
confidence. An independent count written into the test would re-implement the analyser's own
rule and share any mistake it makes; the unit tests pin the rule instead, and the live
distribution in the next section is the measurement.

**Live:** run `wowperf night cW38jmwdnZfbHVL4` and report, for each of the three summary bosses,
whether it fired, how many abilities it named and over how many attempts. Every first death there
fell to a different specialisation (measured 2026-09-26), which says nothing about whether they
fell to different abilities. If it fires on none of the three, read the raw first-death killing
blows before calling that the data.

`tests/e2e/test_progression_e2e.py` is unchanged and covers the new finding only through its
existing check that no roster name appears in any finding text. `tests/e2e/test_night_e2e.py`
additionally asserts that `progression.repeat.killing_blow` fires on at least one summary boss,
so a regression that silently stopped it from firing at all cannot pass while every per-boss
shape check stays vacuously true.

## 7. Out of scope

- Deaths after the first, in any form (§2).
- Family 2 of spec B: deaths per player across pulls, and what each had available. It needs casts
  and aura tables, which only the night page's default tier fetches, and it is its own design.
- Any claim that the ability *caused* the wipe, or that the dying player could have avoided it.
  This counts; it does not attribute.
- Any narrative, trend line or parse axis.
