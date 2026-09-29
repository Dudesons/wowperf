# Not judged before the log

**Status:** approved design, 2026-09-29.
**Area:** the death card's availability rows (the dying player's own defensives, teammates'
externals) and the "defensives off cooldown at a death" finding, per pull and pooled across a
night. It closes the follow-up `docs/plans/2026-09-29-healer-side-of-death-design.md` §7
recorded, widened to every surface with the same defect.

## 1. The defect

A press before the log began is invisible. Three surfaces nonetheless call an ability ready, or
up, at a moment whose base cooldown reaches back before the log's first second:

1. **Teammates' externals on the death card.** `domain/analysis/recap.py` `state_of` answers
   READY whenever no press falls within the base cooldown before the death, however early in
   the fight the death is.
2. **The dying player's own defensives on the card.** The same `state_of` call.
3. **The finding** `defensives.unused.*` ("died with a defensive available") and its pooled
   night version (`repeat_defensives_up`). `domain/analysis/defensives.py` `defensives_up_at`
   counts an ability up when it was cast somewhere in the fight and at no point in
   `[death - (base cooldown + run-up), death]`. Its docstring says a press before the timer
   started "understates what was up". It overstates: an unseen press can have spent it.

On a raid the overstatement is real, not theoretical: a reset check on `cW38jmwdnZfbHVL4`'s
fifteen repeated boss pulls (sub-slice 1, `docs/plans/2026-09-29-healing-cooldowns-design.md`
§5) found cooldowns carried over between pulls rather than resetting. So the finding can say a
named player died with a defensive available when their last pull spent it -- a false claim
about a person, the class of error this project ranks first.

The heavy-moment finding and the Healers group already refuse this: they read through
`ready_at` (`domain/analysis/throughput.py`), which declines a window reaching before the
visible origin, and say "not judged".

## 2. The rule

**One predicate:** a base cooldown is judged only when it lies wholly inside the log --
`moment - base cooldown >= visible origin`, the condition `ready_at` already applies. The
visible origin is what the card already passes as `visible_from_ms`: a keystone's first pull
start, a boss fight's own start (`window_ms[0]`).

**The card, `state_of`,** reads in this order:

1. never pressed in the log read: `unseen` (unchanged);
2. pressed in the run-up: `pressed`, refined to `held` or `faded` (unchanged, including the
   external's rule that only a press on the dying player or an untargeted one counts);
3. enough presses within the base cooldown to spend every charge: `cooldown`, with its bound
   (unchanged: the presses it rests on are in the log, so it stays true);
4. **new:** the base cooldown before the death reaches before the origin: `unjudged`;
5. otherwise `ready`.

Charges keep working: a two-charge ability with one visible press early in a fight reads
`unjudged`, since an unseen press could have spent the second charge.

Consumables do not change: `availability_at` already drops a category whose window reaches
before `visible_from_ms`.

**The finding, `defensives_up_at`,** counts an ability up only when its window, base cooldown
plus run-up before the death, starts at or after the origin. Otherwise it says nothing about
that ability, as it already does for anything it cannot prove. Both callers hold the origin: the
keystone service (first pull start) and the raid service (fight start). The pooled night
finding judges each pull against that pull's own start and sums, so it follows unchanged.

**Chosen over rewriting onto `read_cooldown`:** that rule models no charges, no per-target press
rule and no held/faded refinement; adopting it would lose all three. Both approaches draw the
line with the same predicate, so they cannot disagree about where "not judged" begins.

## 3. On the page

- **The row:** state `unjudged`, detail "not judged, its base cooldown reaches before the
  {setting}'s first second", `setting` "run" on a keystone and "fight" on a boss -- the sentence
  the Healers group and the heavy-moment finding already print. The row keeps its ability icon,
  tooltip and owner. The stylesheet is untouched (every page inlines it); the state renders
  unstyled, as the Healers group's do.
- **Listed, not dropped.** An ability the card cannot judge stays on it: dropping it would make
  "not judged" look like "this specialisation does not have it", the silence the `unseen` state
  exists to prevent.
- **Badges:** the Defensives and Teammates' externals groups keep theirs. This withholds a
  claim; it adds none.
- **The finding** names fewer abilities, or is not emitted where none remains. Its detail gains
  one clause: an ability whose base cooldown reaches before the {fight's / run's} first second
  is not counted as available. The pooled finding's detail gains the same clause.
- **Goldens move, deliberately:** every fixture death within a base cooldown of its fight's
  start turns `ready` rows to `unjudged`, and a defensives finding resting only on an early
  ability goes. Each golden is regenerated on purpose and its diff read whole: the new rows and
  the withdrawn findings, nothing else.
- **Docs:** `CLAUDE.md`'s death-card paragraph ("six states" becomes seven); an inline
  amendment note in each earlier design that lists the card's states; the healer design's §7
  marked closed; `.claude/skills/mplus-analysis/SKILL.md`'s defensives section -- `unjudged` is a
  withheld judgement, never a fault.

## 4. Testing

- **Unit, test first, on a clock with a non-zero origin** (`.claude/lessons.md`, 2026-09-29):
  - `state_of`: a window starting exactly at the origin is `ready`, one millisecond earlier
    `unjudged`; `pressed` and `cooldown` outrank `unjudged`; the two-charge case; `unseen`
    unchanged; the external's target rule and the held/faded refinement unchanged; consumables
    untouched.
  - `defensives_up_at`: the same boundary on its window, with a keystone origin (first pull) and
    a raid origin (fight start); the pooled finding judged against each pull's own start.
  - Every new test shown able to fail by breaking the line it guards.
- **Builder and render:** the row's text asserted from the view model in both settings, never
  hand-typed; no `>None<`; the finding's added clause present.
- **Neighbours:** the heavy-moment finding and the Healers group read `read_cooldown`, not
  `state_of`, and their tests pass unchanged.
- **Live, not optional** (warm caches, `--no-compare`): `raid` on `cW38jmwdnZfbHVL4` fights 2,
  30, 32, 8, 29 and 31; `analyze` on `6Kx1P9GbNXrcLdHa` fight 36 and `4vFcVAW1PB2CrD9z` fight 72.
  A script that prints no name counts, before and after: own-defensive rows and external rows
  by state, from the cards; `defensives.unused.*` findings and the abilities they name, from the
  findings files. The design records how many `ready` claims the guard withdrew -- the size of
  the overclaim -- and any state that never occurs, as open.

## 5. Out of scope

- The `unseen` row reads "not seen this run" on a boss fight too, where there is no run. It
  predates this and is recorded, not fixed here.
- Modelling talents that shorten a cooldown, charges refreshed early, or cooldown resets.
- The Healers group's parked items (the measured badge over alive/dead; a dead healer's run-up
  press).
