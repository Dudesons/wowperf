# The defensive ceiling on raid

**Status:** approved design, not yet planned or implemented.

**Amends** `2026-09-13-raid-analysis-design.md` section 6.12, which assumed the ceiling worked
on raid once its denominator stopped being zero. It does not. Supersedes nothing.

## 1. What this changes

Two defects in `analyse_defensive_ceiling` as it reaches a raid boss fight, found by measuring
the analyser against cached runs rather than by reading it:

- **D1.** A player whose death was never followed by an outward action is dropped from the
  analysis entirely, although the log says exactly how long they were alive.
- **D2.** A fight too short for any defensive to have a reachable ceiling produces silence,
  which a reader cannot tell apart from having pressed everything enough.

The first is repaired. The second is disclosed rather than repaired, because it is not a
defect in the code — it is a true fact about short fights that the report currently keeps to
itself.

## 2. The evidence

Measured 2026-09-22 against the fifteen reports in `out/` and the cache behind them; thirteen
were still cached and readable offline. Two reports (`43HaCNQwPrKqtYgn-2`,
`CmzA8dnZyaD4Wkw1-1`) have aged out of the cache and were not read. Every figure below comes
from running the shipped analyser, or the proposed rule, over real cached data through a
repository whose client raises rather than reaching the network.

Across all thirteen runs, **259 of 425 (player, ability) pairs never reach the threshold at
all** — they exit earlier, at `alive is None`. The split is almost entirely by fight type:

| shape | pairs judged | pairs dropped |
| --- | --- | --- |
| nine keystones | 149 | 2 |
| four raid wipes | 17 | 257 |

On the four cached wipes, 6 per cent of pairs are judged. Three of the four judge two pairs or
fewer out of roughly seventy.

### 2.1 The kill is the control

All four raid fights in `out/` are wipes, so `cW38jmwdnZfbHVL4` fight 2 — the canonical kill
named in `.env.example` as `WOWPERF_E2E_RAID_KILL` — was fetched for this design (33.2 points
of an hourly 3600; the raid path makes one `AuraTable` call per player, so it costs about five
times a keystone).

| fight | kill | seconds | judged today | fires today | judged proposed | fires proposed |
| --- | --- | --- | --- | --- | --- | --- |
| `cW38jmwdnZfbHVL4-2` | yes | 316 | 68 | 7 | 68 | 7 |
| `cW38jmwdnZfbHVL4-8` | no | 106 | 0 | 0 | 68 | 0 |
| `cW38jmwdnZfbHVL4-26` | no | 271 | 15 | 0 | 68 | 4 |
| `cW38jmwdnZfbHVL4-30` | no | 480 | 2 | 0 | 68 | 8 |
| `DJfap6RcYKhPGHXZ-7` | no | 542 | 0 | 0 | 70 | 5 |

**On the kill, the current rule and the proposed rule agree exactly.** D1 is a wipe defect and
nothing else. This is the most important line in the document: it bounds the change to fights
that ended with players dead, and it means no kill or keystone report can move except through
the small residue described in section 9.

## 3. Defect D1: the denominator discards a number it has

`alive_combat_seconds` (`src/wowperf/domain/analysis/defensives.py`) returns `None` when any of
a player's deaths carries `seconds_until_next_action is None`, and both ceiling analysers then
skip that player. Its docstring gives the reason:

> There is no honest dead-time figure to subtract, so there is no honest alive-time figure
> either.

That reasoning holds for a keystone and fails for a wipe. `seconds_until_next_action` is
computed in `src/wowperf/adapters/wcl/ingest.py` as the time until the player's next cast aimed
at another actor, and is `None` when no such cast follows. It therefore means **"we never saw
them act on another actor again"**, not "we cannot measure them". When the fight ended at that
death, they demonstrably never came back, and their alive time is the interval from the pull to
their death — exact, not estimated.

The discarded information is large, because players die late. On `cW38jmwdnZfbHVL4-26` the
median player was alive for 269 seconds of a 271-second fight.

The defect reaches Mythic+ too, but barely: two pairs across nine keystones.

## 4. Defect D2: silence reads as a clean bill of health

A ceiling finding requires `uses >= 1` and `uses < ceiling * CEILING_USE_FRACTION`, which
together force `ceiling > 1 / 0.2 = 5`. (The separate `MIN_CEILING_USES` floor that used to sit
beside this was retired in #21 after it was shown never to change an outcome.)

An ability therefore cannot produce a finding at any press count unless combat ran longer than
five of its cooldowns. Against the 65 distinct defensives in `data/`:

| combat seconds | reachable | out of reach | what it is |
| --- | --- | --- | --- |
| 106 | 3 | 62 | shortest cached wipe |
| 271 | 18 | 47 | cached wipe |
| 542 | 36 | 29 | longest cached wipe |
| 1380 to 1660 | 60 to 62 | 5 to 3 | the cached keystones |

Divine Shield needs a fight longer than 1500 seconds to be judgeable at all.

This is not confined to wipes. On the 316-second kill, **11 of the 25 pressed pairs cannot fire
at any press count**. The report says nothing about them, and nothing about why.

The repo already holds the principle this violates. From `CLAUDE.md`:

> A state that never occurs is a defect, not a quiet success.

And from the README's account of comparisons, which are withheld rather than guessed and say so
on the finding. The ceiling currently withholds without saying so.

## 5. The repair

**Rule.** A death that was never followed by an outward action counts as dead from that death
until combat ended.

- On a wipe this is **exact**: the fight ended, so the player provably did not return.
- For a resurrected player who then only ever casts on themselves, it **understates** their
  alive time, which lowers their ceiling and weakens the claim. That is the direction
  `defensives.py` already commits to for every other approximation it makes: "Each understates
  what was up, and understating cannot produce a false accusation."

**Signature.**

```python
def alive_combat_seconds(
    combat_seconds: float,
    deaths: tuple[Death, ...],
    actor_id: int,
    combat_end_ms: int,
) -> float:
```

It no longer returns `None`. The `if alive is None: continue` branch leaves both
`analyse_defensive_ceiling` and `analyse_cooldown_ceiling`: the change is a deletion, not an
added special case.

**Callers.** `encounter_service.py` passes `encounter.end_ms`. `service.py` passes the end of
the last pull; `src/wowperf/domain/model.py` already computes `max(pull.end_ms for pull in
self.pulls)` for its own frame origin, so that expression should be reused rather than
repeated. A `Run` with no pulls must not reach `max()` of an empty sequence; its
`total_pull_seconds` is already zero, so the ceiling is zero and nothing can fire, and the
guard belongs at the caller.

**What does not change.** `Death.seconds_until_next_action` keeps returning `None` exactly
where it does today. It remains the honest answer to what a death *cost*, which
`analysis/deaths.py` and `analysis/recap.py` both depend on. Only the alive-time question stops
treating that `None` as unanswerable.

## 6. Disclosing D2

One finding per report, `defensives.ceiling.withheld`, following the route `WITHHELD_ID`
(`wipe.cause.withheld`, `analysis/attempt_shape.py`) already established: minted as a real
`Finding` carrying its reason, lifted out in `report/raid_build.py`, and disclosed on the
Provenance tab rather than ranked among the findings.

**Minted only when a pressed ability was actually suppressed** — that is, when someone pressed
an ability and `cooldown_ceiling(combat_seconds, ability) <= 5`. It is not minted from the
cooldown table alone. This keeps it off a 1660-second keystone whose three unreachable abilities
nobody pressed, and puts it on every fight where a reader would otherwise mistake silence for
approval.

**The condition is judged against the fight, not against each player's alive time.** A player
who died early has abilities suppressed by their own short life rather than by a short fight,
and an evidence line saying the fight was too short would then be false. That per-player case
is a different statement and is deliberately not made here. The counts in section 9 were
measured per player and are therefore an **upper bound** on what this condition will produce.

**Badge: `measured`.** On the same reasoning `attempt_shape._withheld` gives for
`WITHHELD_ID` — "the absence itself is a fact about the report rather than a reading of it".
What is asserted is that the analyser declined to judge, and why: the press count, the fight
length and the cooldown are all checked. The ceiling claim being declined is `inferred`; this
is not that claim.

**Routing work this implies.** `report/raid_ledger.py` routes the bare `defensives.` prefix to
`group_rows`, which renders on the Players tab, so a new id under `defensives.ceiling.` would
land there by default. It needs the same lifting `WITHHELD_ID` gets in `raid_build.py`, and the
Mythic+ report needs its equivalent. This is real work in the report layer, not a one-line
addition to the analyser.

## 7. Non-goals

- `CEILING_USE_FRACTION` stays at 0.2. It was measured against the same cached corpus on
  2026-09-22 and holds: across 108 pressed Mythic+ pairs the ratio distribution runs p10 0.16,
  median 0.56, p75 0.91, and 0.2 fires on 13 of them (12 per cent). At 0.5 it would fire on 43
  per cent, corroborating the original measurement recorded in its docstring.
- No revival of the `defensives.never` family, retired in #19.
- No change to the death card's six availability states.
- No change to what `seconds_until_next_action` means or how it is computed.

## 8. Testing

The gap this design must close first: **no test anywhere exercises the raid path with an
unmeasured death.** The ceiling test in `tests/domain/analysis/test_encounter_service.py`
passes no deaths at all, and the `tests/domain/report/test_raid_ledger.py` fixture is a kill
whose five deaths all carry measured costs. The `None` rule is covered only against a Mythic+
`Run` fixture. The behaviour that silences 94 per cent of pairs on a real wipe is, in test
terms, invisible.

Required:

1. A wipe fixture in which every death is unmeasured, driven through the encounter path, that
   fails today and passes after the repair.
2. `alive_combat_seconds` against a death with no following action and an explicit
   `combat_end_ms`, asserting the exact alive figure rather than merely that it is not `None`.
3. A resurrected player whose only later casts are self-targeted, asserting the understating
   direction deliberately.
4. Boundary tests for the withheld finding: minted when a pressed ability had a ceiling of 5 or
   less, not minted when that same ability was never pressed.
5. A `Run` with no pulls, asserting no exception.
6. Every new guard shown to die alone under mutation. This repo's plans have twice failed on
   tests that could not fail; a test added here is not finished until it has been watched to
   fail.

And the standing invariant from `CLAUDE.md`: a new judgement is not done until a live run has
exercised it. The repaired analyser must be run across every cached run and the
before-and-after distribution reported, not assumed. The table in section 2.1 is the baseline
to compare against.

## 9. Risks

- **Mythic+ output can move.** Two pairs across nine keystones currently exit at `alive is
  None` and will begin to be judged. Whether either produces a finding must be measured on
  every cached run before and after, not reasoned about.
- **The withheld finding's fire rate.** Raised as a risk and then measured, since a claim that
  always fires carries no information. Under the minting condition in section 6 it would fire
  on **all five raid fights** (11, 14, 18, 15 and 15 suppressed pairs respectively) and on
  **three of the nine keystones**, each of those on exactly one suppressed ability:
  `G7MBJZfNakrcPvAx-3`, `wqd4MaK6JZpztV21-12` and `xBDdYAjbRFqWKC8n-59`. It therefore
  discriminates rather than decorating every report, and the condition stands as written.

  These counts were taken with a per-player ceiling. Section 6 settles the condition on the
  fight's own length instead, which is a subset, so the real rate is the same or lower. It must
  be re-measured after implementation, and a notice that fires on every report or on none is a
  defect either way.
- **`max()` on an empty pull tuple** raises where today the code returned zero quietly.
- **The kill case rests on one fight.** Section 2.1 is strong evidence that D1 is wipe-only,
  not proof.

## 10. Considered and rejected

**Passing the `Run` or `Encounter` aggregate to the analyser.** This is what
`2026-09-13-raid-analysis-design.md` section 5.3 rejected, and the docstring on
`alive_combat_seconds` records the consequence: "taking a `Run` meant a raid fight silently
supplied zero." Taking a scalar denominator is what lets a keystone and a boss ask the same
question, and adding `combat_end_ms` as a second scalar keeps that property.

**Having each service compute alive time per player and pass a mapping.** A clean boundary —
each aggregate owns its own shape — but it puts the rule in two services or in a shared helper,
which is where it already lives, and churns two analyser signatures and their tests for no
measured gain.

**Repairing D1 only, leaving D2 silent.** Rejected: it leaves a reader unable to distinguish
"nothing to say" from "could not say anything", on a kill where that is 11 of 25 pressed
abilities.

## 11. Open items

- The four stale reports in `out/` predate current behaviour and should be regenerated once
  this lands. `CmzA8dnZyaD4Wkw1-1` predates the current finding-id scheme and carries real
  character names inside its finding ids, so anything classifying findings by id prefix must
  not be pointed at it.
- `.claude/worktrees/` still holds `infallible-fermi-f7d3e4` and `jovial-golick-a5b700` from
  merged branches.

## 12. Task 4: what the repaired analyser actually does (2026-09-22)

Measured through an offline harness against the same thirteen cached reports section 2 used
(nine keystones, four raid wipes), plus a direct fetch of `cW38jmwdnZfbHVL4` fight 2 -- the kill,
not in `out/` -- exactly as section 2.1's control was fetched. `43HaCNQwPrKqtYgn-2` and
`CmzA8dnZyaD4Wkw1-1` are still aged out of cache and were not read; both are keystones, matching
section 2's own gap. The harness is described at the end of this section.

### 12.1 Did anything move that should not have?

Comparing the repaired analyser's `defensives.ceiling.*` finding ids (excluding
`defensives.ceiling.withheld`, which this plan introduces and which therefore appears in no
shipped file) against the shipped `out/*.findings.json` id sets:

- All nine keystones: **identical**, id for id.
- The kill (`cW38jmwdnZfbHVL4-2`): 7 findings both before and after the repair, run directly with
  the actual pre-repair code (below) -- confirming section 2.1's claim that the current and
  proposed rule agree exactly on this fight.
- The three raid wipes long enough to judge anything (`cW38jmwdnZfbHVL4-26`,
  `cW38jmwdnZfbHVL4-30`, `DJfap6RcYKhPGHXZ-7`): every difference is an **addition** (+4, +8, +5;
  nothing removed), the only direction the repair can move a result -- it can only turn an
  unmeasurable alive time into a real one, never the reverse.
- `cW38jmwdnZfbHVL4-8` (106s wipe): unchanged, 0 findings before and after -- every pressed
  ability on this fight is still too short to fire regardless of alive time, so D1 has nothing to
  move here.

Section 3's "two pairs across nine keystones" was re-checked directly, running the actual
pre-repair `alive_combat_seconds` (`git show f271648^:src/wowperf/domain/analysis/defensives.py`,
the commit before this plan's first) against the same nine keystones. Only **one** pressed pair
was ever affected by D1 there -- one Retribution Paladin's one pressed defensive, in
`HpYwCAvmPFDtz1Jj-1` -- not two. It did not cross the firing threshold before or after, so this
does not change the "identical" result above; section 3's count is corrected here to what
actually reproduces.

### 12.2 What did the repair buy on raid?

Actual `judged` and `fires` from the repaired analyser, against section 2.1's predictions:

| fight | kill | seconds | judged (actual) | fires (actual) | judged proposed | fires proposed |
| --- | --- | --- | --- | --- | --- | --- |
| `cW38jmwdnZfbHVL4-2` | yes | 316 | 25 | 7 | 68 | 7 |
| `cW38jmwdnZfbHVL4-8` | no | 106 | 16 | 0 | 68 | 0 |
| `cW38jmwdnZfbHVL4-26` | no | 271 | 26 | 4 | 68 | 4 |
| `cW38jmwdnZfbHVL4-30` | no | 480 | 41 | 8 | 68 | 8 |
| `DJfap6RcYKhPGHXZ-7` | no | 542 | 39 | 5 | 70 | 5 |

**`fires` matches the prediction exactly on every row.** That is the number that reaches a
reader, and the implementation produces exactly what the design predicted, no more.

**`judged` does not, on any row, and the table is the error.** `68` and `70` are each report's
full roster kit size -- every `(player, ability)` pair the roster's specs carry, pressed or not
(`sum(len(defensives.for_spec(p.class_name, p.spec)) for p in players)`, verified to equal these
figures exactly, per report). The repair does not change which pairs are judged; it changes what
happens to a pair that was already pressed (`uses >= 1`) once its player's alive time is asked
for. A pair nobody pressed still exits at the `if not uses: continue` gate before
`alive_combat_seconds` is ever called, repaired or not. `judged` (actual) counts pressed pairs,
and it tracks how much a roster actually cast that fight -- naturally different fight to fight,
never the constant the kit size implies.

The same conflation explains section 2's headline evidence. `151` and `274` (keystones' and
raid's `judged + dropped` totals there) are the two shapes' summed kit sizes, not summed
pressed-pair counts -- verified the same way. The true figures, measured with the actual
pre-repair code run directly against the same cached data, are:

| shape | pressed pairs | truly dropped (alive was `None`) | truly judged (old code) |
| --- | --- | --- | --- |
| nine keystones | 109 | 1 | 108 |
| four raid wipes | 122 | 113 | 9 |

Section 3's "two pairs" and section 2's "257 dropped" both used the kit-size denominator instead
of the pressed-pair one; the corrected figures are 1 and 113. Section 2's qualitative story
stands regardless -- wipes still drop the large majority of what they judge (113 of 122 pressed
pairs, 93 per cent, against section 2's 257 of 274, 94 per cent) -- but its raw counts, and
section 2.1's `judged proposed` column, should be read as roster kit sizes rather than as the
pressed-pair figures their column headers say they are.

One further, smaller discrepancy: section 2.1 gives `cW38jmwdnZfbHVL4-26`'s `judged today` as
`15`. Run directly, the actual pre-repair code returns `7` on this fight (`26` pressed pairs, `7`
resolved). `15` fits neither the pressed-pair count nor the kit size, so it is not explained by
the pattern above. It is recorded here rather than guessed at -- inventing a reason would be
exactly what `CLAUDE.md` warns against -- and it changes no conclusion: `fires today` for this
fight (`0`) is independently confirmed against the shipped
`out/cW38jmwdnZfbHVL4-26.findings.json`, which carries no `defensives.ceiling.*` id, exactly as
section 2.1 says.

### 12.3 Does the new notice discriminate?

`defensives.ceiling.withheld` fires on:

- **3 of 9** keystones -- the identical three fights section 9 named from its per-player
  measurement -- each naming exactly one suppressed ability.
- **4 of 4** loadable raid wipes, and the kill fetched alongside them fires it too (suppressed
  counts of 12, 17, 13 and 10 on the wipes, 10 on the kill) -- matching section 9's prediction
  that it would fire on all five raid fights, now confirmed under the fight-level condition this
  plan shipped rather than the per-player one section 9 measured.
- **7 of 13** overall: neither always nor never, so it discriminates as required.

Count distribution where it fires: `1, 1, 1` on the keystones and `10, 12, 13, 17` on the raid
wipes, `10` again on the kill. The count is not pinned to `1`: section 9's predicted range for
raid (11 to 18 suppressed abilities, measured per-player) and the actual fight-level range (10 to
17) overlap closely; the keystones' `1` is a real fact about those three fights -- each has
exactly one pressed ability whose ceiling never clears five -- not a placeholder that happened to
land on the same value three times.

### 12.4 What this leaves unmeasured

- `43HaCNQwPrKqtYgn-2` and `CmzA8dnZyaD4Wkw1-1` are still aged out of cache and were not read.
  Both are keystones; neither's shipped `out/` file has been regenerated, so both remain the
  stale reports section 11 already names.
- The four stale `out/` reports section 11 names predate behaviour unrelated to this plan and
  were compared as shipped; nothing measured here depends on their being current.
- The `cW38jmwdnZfbHVL4-26` "judged today" discrepancy in section 12.2 is recorded, not resolved
  -- the script that produced section 2.1's numbers no longer exists to re-run.
- `CEILING_USE_FRACTION` was not touched or re-measured; section 7's 2026-09-22 measurement
  stands as the last word on it.

**Harness.** An offline script, not part of the repository, built a `WclRunRepository` over
`DiskCache(Path("cache"))` with a client whose `execute` raises rather than reaching the network,
read each `out/*.findings.json`'s `(report_code, fight_id)` pair, loaded it through `repo.load`
or `repo.load_encounter` by the presence of `dungeon_name` versus `boss_name`, and ran
`analyse_defensive_ceiling` directly with the same arguments `service.py` and
`encounter_service.py` pass it. `Player.name` and any finding id carrying a player slug were
loaded like every other field but never printed or written down; every count above is keyed by
report code, fight id, and -- for the one keystone exception in 12.1 -- class and spec alone.
