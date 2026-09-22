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
