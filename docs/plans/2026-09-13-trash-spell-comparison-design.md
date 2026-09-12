# The Trash Spell Comparison — Design

**Status:** Proposed 2026-09-13. Not implemented.

**Authority:** `2026-09-03-mplus-postmortem-design.md` remains the authority on analysers,
badges and refusals. This design amends its §6.5, which restricts the spell comparison to boss
pulls, and §6.5's reasoning is quoted and answered in §2 below rather than set aside.
`2026-09-10-per-player-parse-comparison-design.md` remains the authority on how a parse sample
is drawn and how its findings are named per player; nothing here reopens it.

**Origin:** a Blood Death Knight tank asked what the report could tell him about his damage and
found the answer thin. The parse axis measures 648 seconds of a 1761-second key, because boss
pulls are all it looks at. Everything below is about the other two thirds.

## 1. What this builds

A new finding family, `compare.spells.trash.*`, that compares one player's cast rates on the
trash packs that **aligned** with a reference's route — the packs both groups demonstrably
fought — and says so with the number of packs it drew from in the title.

It does not replace the boss-pull comparison. The two sit side by side, measure different
stretches of the dungeon, and are never merged or averaged.

## 2. Why this is not a reversal of §6.5

§6.5 restricts the comparison to boss pulls, and gives its reason:

> Across trash, ability ratios are dominated by pull size and route. Comparing an
> area-of-effect pull against a single-target pull says nothing about play. Boss pulls are a
> fixed, comparable encounter. Restricting to them costs coverage and buys validity.

The objection is exactly right, and it names a confound rather than an impossibility. At the
time §6.5 was written the project had no way to tell which of our packs corresponded to which
of theirs, so every trash comparison really was an area-of-effect pull against a single-target
pull.

`src/wowperf/domain/comparison/alignment.py` now supplies that control. `align_pulls(ours,
theirs)` pairs two routes by set containment over enemy game ids, so a stretch Warcraft Logs
recorded as one pull matches each separate pull it covers. Restricting the comparison to
matched packs is the control §6.5 lacked, not a decision to tolerate the confound it named.

What alignment does **not** remove is stated in §8 and carried on the findings themselves.
Containment means their enemy types are a subset of ours or ours of theirs; an aligned pair is
a comparable pair, never an identical one.

## 3. What it costs to fetch

Nothing. This is worth stating plainly because the opposite was assumed for some time.

- A parse reference is built as `ParseMember(row=..., run=theirs.run, casts=theirs.casts, ...)`
  in `cli.py`, from the same ingest that populates every pull. `ingest.py` fills `Pull.enemies`
  from `dungeonPulls.enemyNPCs` for every pull it reads, boss or trash, so a parse reference's
  run already carries the enemy composition alignment needs.
- `CASTS_QUERY` takes the fight's own start and end and pages over the whole window. It is not
  scoped to boss pulls; `boss_casts` filters an already-fetched stream by pull index.

So both halves — pack composition and trash casts, on both sides — are already fetched, already
cached, and already discarded unused. No new query, no new point cost, no new cache entry.

## 4. The unit, and the two units rejected

**Chosen: casts per minute of aligned trash time.** Our denominator is the summed duration of
our matched packs; theirs is the summed duration of the counterpart pulls those packs matched.
This mirrors `compare.spells.rate` exactly, so the page gains no new mental model, and the
thresholds, wording and confidence badge all transfer unchanged.

**Rejected: casts per aligned pack.** More intuitive for trash, and ill-defined here.
Alignment matches by containment, so one chain-pulled stretch of ours legitimately matches
three pulls of theirs. "Per pack" has no denominator both sides agree on under that matching.
Per-minute does, because time sums cleanly however the pulls were cut.

**Rejected for now: casts per hundred enemy forces.** The most robust of the three against
pack-size differences, and `EnemyDeath.forces` already exists to compute it. Left out because
forces are not an enemy count, and because it introduces a unit no other row on the page uses.
Worth revisiting if the chosen unit proves noisy in practice.

## 5. How the denominator is drawn

For each compared player and each member of their parse sample:

1. `alignment = align_pulls(ours.run, member.run)`.
2. Take `alignment.matched`, and keep only matches whose `ours_index` is in
   `alignment.our_packs`. That property is already restricted to trash pulls a route decision
   could have taken or left, so `Pull.is_a_pack` has already excluded pulls with no recorded
   enemies and the sub-`MIN_PACK_SECONDS` fragments Warcraft Logs leaves when it cuts one
   engagement in two.
3. Our seconds: the summed `duration_seconds` of the distinct pulls of ours in that set.
4. Their seconds: the summed `duration_seconds` of the distinct pulls of **theirs** those
   matches name. **De-duplicate by `theirs_index` before summing.** Several of our pulls can
   match one of theirs, and counting that pull once per match would inflate their denominator
   and depress their rate — which would flatter our own side, the worst direction for an error
   in a report a player reads about themselves.
5. Count each side's casts inside exactly those pull indices.

A member whose alignment yields less than `MIN_ALIGNED_TRASH_SECONDS` on either side
contributes nothing and is counted as not carrying the ability, exactly as a member with no
boss time already is.

## 6. Thresholds

Reused unchanged from `spells.py`, so a reader who has understood the boss rows has understood
these:

| Constant | Value | Role here |
| --- | --- | --- |
| `MIN_CASTS_TO_COMPARE` | 3 | Below this a member's own count is too small to argue from |
| `MIN_MEMBERS_WITH_ABILITY` | 3 | An ability seen in fewer members is one player's build |
| `RATE_GAP_MULTIPLE` | 1.5 | How much higher the sample's median must be before a row is written |
| `MAX_SPELLS_REPORTED` | 5 | Cap per family |

One new constant:

`MIN_ALIGNED_TRASH_SECONDS` — a floor on aligned trash time per side, below which a member is
not compared. A twenty-second denominator turns two casts into a wild rate, and the rate rows
have no other guard against a tiny denominator. The value is to be set from real runs during
implementation and recorded with the date it was measured; it is not guessed here.

Deliberately **not** reused: `MIN_ALIGNED_SHARE`. The route family drops a reference whose
route lined up with fewer than half our packs, because a skipped-pack claim is a claim about
the whole route. A cast rate is not: it is a claim about the packs it was measured over, and
those packs aligned whatever the rest of the route did. Applying the route floor here would
withhold a sound figure for an unrelated reason.

## 7. What the findings say

Three ids, all suffixed with the player slug by `service._for_player`, all landing in the
Players tab through the existing `COMPARISON_PREFIXES` match on `compare.spells.`.

**`compare.spells.trash.rate`** — the gap row.

> 3 top parses cast Blood Boil a median 9.1 times a minute across 4 aligned packs; Dudesons
> casts it 6.0

The pack count sits **in the title**, not in the evidence. This is the whole mitigation for the
permissive stance §9 takes: a row drawn from two packs and a row drawn from eight must not read
alike, and a figure quoted out of the report must carry its denominator with it. Evidence
carries the ability id, both denominators in seconds, and the observed range.

**`compare.spells.trash.level`** — the abilities compared on aligned packs that produced no gap
row, named the way `compare.spells.level` names the boss ones. Without this the feature
recreates the ambiguity it was built to remove: silence would once again mean both "not
compared" and "compared and fine".

**`compare.spells.trash.unavailable`** — emitted when no member cleared
`MIN_ALIGNED_TRASH_SECONDS`, saying so rather than leaving the section absent. A withheld
comparison and a comparison that found nothing must not look alike.

All three are `derived`: a rate is a division, and the alignment beneath it is a reconstruction
by a documented rule. None carries `seconds_lost` — nothing here is priced in time, and a cast
rate never should be.

## 8. Confounds, declared and not corrected

Carried on the findings in the tool's own idiom, alongside the confounds the comparison already
declares:

- **An aligned pair is not an identical pair.** Containment means one side's enemy types are a
  subset of the other's. Pack size therefore still varies within a matched pair, and this is
  the residual of §6.5's objection that alignment does not remove.
- **Trash casts are route-shaped even when packs match.** Pull order, what the group held, and
  which packs were chained all move a rate without any difference in play.
- **The parse references are five other characters**, as on the boss rows. A gap is a prompt to
  check a build, never a verdict on one.
- **Group composition**, already declared by `compare.confound.composition`, bites harder on
  trash than on bosses: which packs can be held is a function of the roster.

## 9. The permissive stance, and who chose it

Three postures were put to the repository's owner:

1. Strict — withhold unless most packs align, reusing the route family's floor.
2. **Permissive — compare what aligned, state the denominator.** *Chosen.*
3. Strict rows, permissive listing.

Permissive was chosen deliberately, for coverage: a route that diverges from the leaderboard's
would otherwise produce the same silence this whole line of work exists to end. The cost is
that thin rows will appear. The title-borne pack count in §7 is the mitigation and is not
optional; without it this posture is indefensible.

## 10. What this does not do

- **It does not rank damage.** The project invariant stands: no per-player throughput ranking,
  no percentile, no parse number. This compares which buttons were pressed and how often, which
  is what the parse axis has always done.
- **It does not merge with the boss rows.** Two stretches, two denominators, two families. A
  combined figure would be a third number no analyser produced.
- **It does not touch the speed axis.** Route, tempo, downtime and the duration comparison are
  untouched.
- **It does not extend to uptime.** Aura bands could in principle be intersected with aligned
  pack windows, but the attribution problem recorded in `uptime.py` — `onSelf` carries no source
  — is unchanged by alignment and would only be multiplied by a smaller denominator.

## 11. Testing

Per CLAUDE.md, all three levels, no exceptions.

- **Unit.** Alignment to denominator, including the de-duplication which is the defect
  most likely to ship silently and in the direction that flatters us (§5, step 4). The
  `MIN_ALIGNED_TRASH_SECONDS` floor. Each threshold's boundary. The level and unavailable rows,
  including that an ability below `MIN_MEMBERS_WITH_ABILITY` is never called level.
- **Integration.** The three families through `compare_spells_sample` and out to the findings
  file, with ids, slugs and tab routing checked.
- **End-to-end.** Against a real cached run under `-m e2e`, asserting the rows appear and the
  pack count in a title matches the alignment that produced it.

Every test written first and watched fail. Where a test passes on first writing, the guard it
covers is to be mutated and the test confirmed red before it is trusted — the repository's
recorded failure mode is a test that could never have failed, not a wrong implementation.

## 12. Open questions for implementation

1. `MIN_ALIGNED_TRASH_SECONDS` has no value yet. Measure it against real runs, set it, and
   record the date and the runs it was measured on.
2. Whether a player with no aligned packs at all should produce `compare.spells.trash.unavailable`
   or nothing. Current inclination: the finding, for the same reason every other withheld
   comparison says so out loud.
3. Whether the level row should list abilities compared on trash only, or state which were
   compared on both stretches. Current inclination: trash only, because a row that spans both
   invites the merge §10 forbids.
