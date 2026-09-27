# A wipe's damage pace against the kills, with a projection

**Status:** approved design; slice 1 planned in
`docs/plans/2026-09-27-wipe-damage-pace-plan.md` and built.
**Area:** the raid page on a wipe. It amends ruling 4.5 of
`docs/plans/2026-09-18-wipe-analysis-design.md` for damage *done* (§3) and opens the depletion
question that design's §8.4 set aside, answered with damage rather than health.

## 1. Goal

On a wipe, compare the raid's cumulative damage **to the boss**, second by second from the pull,
with the reference kills over the same seconds. Say whether the raid was behind, on pace or
ahead when it wiped, and from when it had been behind. Then project when, at its own average
pace, it would have dealt the kills' total boss damage.

Today a wipe's Damage tab is empty: the parse comparison is withheld because Warcraft Logs ranks
kills alone (`compare.parse.unavailable`). The only pace-like reading is `wipe.cause`, which sets
our duration against the kills' median duration.

## 2. Three slices, one design

1. **Raid-wide, on `raid --fight N` for a wipe.** Two findings, one chart, one Summary pointer.
   This document specifies slice 1 in full.
2. **Per player**, against players of the same specialisation in the same reference kills:
   median and range from three or more such players, withheld below that. It reuses slice 1's
   graphs, which already carry one series per player (§4), so it fetches no graph of its own. It
   needs a check that each reference fight's roster -- who played which specialisation -- can be
   read cheaply, and it is built only after slice 1 has run live. Why separate: a specialisation
   is often held by fewer than three players across the reference kills; one player's damage over
   a stretch depends on an assignment reference raids hand out differently; and every plan here
   has found its worst defects on the first live run, which is easier to read on one line than on
   twenty.
3. **The night page:** slice 1's comparison on each wipe pull. Each boss's reference kills are
   fetched once and shared by all its pulls, so a pull costs about one graph.

## 3. Ruling 4.5, amended for damage done

Ruling 4.5 says our damage figure never sits beside a reference's. Its reason is that the
reference side was a mitigated `viewBy: Ability` damage-taken table while ours was unmitigated
events, measured 4.61x apart. That reason does not reach damage **done** read from one query on
both sides. **Amended 2026-09-27:** damage done may be compared across raids when both sides are
the same boss-only `DamageDone` graph (§4). Ruling 4.5 stands unchanged for damage taken.

The page still prints no raw damage figure (§7): shares of the kills' median only.

## 4. Data

**The graph.** `graph(dataType: DamageDone, hostilityType: Friendlies, fightIDs, startTime,
endTime, targetID: <boss actor>)`. `targetID` on `graph` was introspected 2026-09-27 and is
recorded in `.claude/skills/wcl-api/SKILL.md`. Scoped to the boss it returns the unscoped call's
bucket grid with add damage removed (fight 2 of `cW38jmwdnZfbHVL4`: 34% lower, agreeing with the
boss-only `table` to 1.1%). Slice 1 reads its `Total` series, which summed to the per-player
series to 1e-8 on every fight measured. The adapter converts the rate to damage per bucket, as
`build_damage_done` does; the domain never holds a rate.

**Alignment, measured 2026-09-27.** `pointStart` equals the fight's `startTime` on every graph
(offset 0). `pointInterval` is about duration / 240 -- every graph returns about 241 buckets -- so
a 88 s wipe is read at 0.37 s buckets and a 500 s kill at 2.1 s. The grid overhangs the fight's
end by one bucket, occasionally two. The leaderboard's `duration` matches the fight's own to the
millisecond.

**Our fight's boss.** From `masterData.actors(type: "NPC")`: the actor whose `subType` is
`"Boss"` **and** whose `name` equals the fight's `name`. Both halves are needed:

- `subType == "Boss"` alone over-selects. On Ula'tek it also flags Gore Rattle and Venomous
  Heart, adds that carry a boss frame.
- The name alone is ambiguous. Ula'tek has a second actor of that name with `subType: "NPC"`,
  which took no player damage.
- `ReportFightNPC` carries no boss marker (`gameID id instanceCount groupCount petOwner`), and
  `encounterID` is not an NPC game id (3492 against 257758).

Anything other than exactly one match withholds the comparison (§7). On this report that is
both council encounters: Entombed Sentinels and The Coiled Altar each field two `Boss` actors,
neither named after the fight. Councils are out of slice 1.

**Each reference kill's boss.** Our boss's `gameID` looked up in that reference fight's
`enemyNPCs`. Found on all four references measured. A reference where it is not found is dropped
from the sample and Provenance says so.

**References.** The same kills the mechanics comparison selects: `reference_kills`, then
`select_reference_kills` (same raid size, at most five). No new selection rule, so the page's two
comparisons stand on one sample. Same size matters more here than for mechanics: a flexible
difficulty scales boss health with raid size, so a 23-player kill has more to deal.

**Cache.** Our fight's responses permanently; reference responses expire after a day. The
existing two tiers; nothing kept beyond one comparison.

**Cost, measured 2026-09-27.** A boss-only graph averaged 1.37 points over 16 calls; a reference
fight's `enemyNPCs` lookup 1.00. The leaderboard is already fetched for mechanics. So a wipe costs
about 13 points cold with five references and nothing warm, printed as its own operation in the
closing cost breakdown. **On a kill nothing is requested.**

## 5. The comparison: `compare.pace.boss`, `derived`

**The curves.** For our fight and each reference kill, cumulative boss damage at each whole
second from the pull: every complete bucket before it, plus the covered fraction of the one that
straddles it.

**The band.** At each second, from the references still fighting at that second (second <= its
duration): the lowest, the median and the highest cumulative. Our raid is **behind** below the
lowest, **ahead** above the highest, **on pace** otherwise. The observed range, never a mean and
never a percentage we chose: the project's existing rule for every comparison.

**Where the band stops.** When fewer than three references are still fighting, the comparison
stops at the last second that had three, and says "compared through 7:41, after which fewer than
three kills were still fighting". Measured: 18 s cut from the 480 s wipe, which outlasted the two
fastest kills.

**Fewer than three references overall.** The project falls back to a single reference and says
so. Here it falls back to **the slowest kill**, and behind means below it. The slowest kill is the
most lenient comparison, so the claim can only understate. The finding then carries a share and a
state against that one kill, no range, and says it stands on one kill.

**Behind from T.** When the state at the last compared second is behind, T is the start of the
final unbroken stretch below the band, running to that second. An earlier stretch behind is
mentioned ("it had also fallen behind between 0:35 and 1:04") only when it lasted longer than the
widest reference bucket in play. That width is not a chosen number: it is the finest detail the
reference curves hold, and a shorter dip cannot be told from interpolating across one bucket.
Measured, this excludes the spurious flicker of every wipe's first ten seconds, where one 2 s
reference bucket is read against our finer grid, and keeps the real mid-pull recovery on the two
110 s wipes (behind 32-59 s, back in the band, behind again from 64-66 s).

**What it says.** Title: our cumulative as a share of the kills' median at the last compared
second, with the state -- "Behind the kills' pace: 71% of their median boss damage by 3:10".
Evidence: how many references; median and range as shares of the median; the last compared
second and why it is last; T and any earlier stretch; the fallback when it applies. `derived`:
it interpolates within buckets and reads a sample.

## 6. The projection: `compare.pace.projection`, `inferred`

- **Our pace:** our boss damage over the whole wipe divided by its duration.
- **Target:** the median of the references' total boss damage, each kill's cumulative at its own
  end. Measured 620-667M across four kills, min/max 0.93: one health bar.
- **Projected time:** target divided by our pace, printed against the kills' durations as a median
  and range: "At its average pace this raid would have dealt the kills' boss damage by about 7:40;
  the kills took 7:41 to 8:38."
- The sample is §5's, slowest-kill fallback included.
- **Never a rate on the page.** It prints a time, never our damage per second.
- **Withheld** whenever `compare.pace.boss` is withheld, when the wipe is shorter than
  `MIN_ATTEMPT_SECONDS` (44 s, the project's existing line under which a pull is a reset), and when
  our boss damage is zero.
- **Its detail says:** it assumes the raid's average pace would have held, which phases,
  intermissions and a shrinking raid all break, and a wipe is where the raid shrank; it says
  nothing about enrage, for which this tool has no data; and it is damage pace, not a forecast of
  the boss's health -- on this boss early wipes dealt 25-28% of a kill's boss damage while removing
  17-20% of its health.
- **No warning comes from it.** Behind is §5's warning; an inferred line does not raise one.

**Why not boss health.** Proposed first and rejected on measurement. `boss_percentage` and
`fight_percentage` disagree by up to 14 points on Ula'tek and 3.76 against 51.12 on The Coiled
Altar, swinging a health projection from 282 s to 555 s; and damage share does not track health
share early in a pull (above). Damage on both sides is one measured quantity from one query.

## 7. On the page

- **Placement.** A `compare.pace.` prefix in `RAID_PLACEMENTS` puts both findings on the Damage
  tab's rows. Severity: the existing `compare` family; `rank_raid_findings` unchanged.
- **The warning.** The raid Summary's pointers take timed findings only (`seconds_lost`), which a
  pace finding is not. So a new optional view-model field, `pace_warning`, carries one pointer
  beside the `wipe.cause` verdict **only when the state is behind**. The builder fills it; the
  template draws it and decides nothing. `wipe.cause` itself is unchanged.
- **The chart.** `build_pace_chart`, pure and in the domain, emits inline SVG the way
  `progression_chart.py` and the players-alive chart do: the kills' range as a band, their median
  as a thin line, our cumulative as a heavier one, a vertical mark at T, and the band ending where
  fewer than three kills remain. X: time from the pull. Y: share of the kills' median total. No
  raw damage figure appears. The page's one inline script is untouched.
- **Withheld.** `compare.pace.unavailable` goes to Provenance only, as the verdict's and the
  defensive ceiling's notices do, with its reason: no single boss actor (a council); no reference
  kill of this raid size; the boss absent from every reference. The Damage tab then shows nothing,
  not an empty chart.
- **On a kill:** no pace finding, no chart, no notice; the page is unchanged.
- **The findings JSON** carries the findings like any other; no new top-level field.

## 8. Wiring

The raid's loaded model gains a boss-damage series for our fight and one per selected reference,
loaded on a wipe only. A pure `analyse_pace` turns them into the two findings or the notice.
The curve and band arithmetic lives in one pure module that both `analyse_pace` and
`build_pace_chart` read, so the findings and the chart cannot disagree. No I/O in the domain.

## 9. Edge cases

- A kill: nothing fetched, nothing emitted.
- A council, or not exactly one boss actor: the notice.
- No reference of this size, or the boss in no reference: the notice.
- One or two references: the slowest-kill fallback, said so.
- A reference whose boss is not found: dropped, with a Provenance line.
- The band thinning below three: compared through the last second with three, said so.
- A wipe under 44 s: `compare.pace.boss` stands, the projection is withheld.
- Zero boss damage: our share reads 0%; the projection is withheld; no division by zero.
- Ahead at the wipe: said plainly, no warning. The wipe had another cause, which `wipe.cause`
  names.
- An earlier behind stretch no longer than the widest reference bucket: not mentioned.

## 10. Testing

Every test is shown able to fail against the line it guards. Fixtures use invented actors and the
sanctioned names only.

**Unit:** interpolation inside a bucket; the band's lowest, median and highest from references
ending at different times; the three states; T as the start of the *final* stretch, with an
earlier stretch both longer and shorter than the bucket-width bar; the band cut at fewer than
three; the slowest-kill fallback; the projection's arithmetic and each of its withholds; the boss
actor rule -- one match, a same-named non-boss, boss-framed adds, a council; the chart's band,
median, our line, the T mark and the cut; no raw damage figure in the chart's labels.

**Integration:** the adapter parses a recorded target-scoped graph and converts rate to damage;
`compare.pace.` lands on `damage_rows`; the Summary pointer appears only when behind; the notice
lands in Provenance only; a kill makes no pace request.

**Golden:** the raid wipe golden moves by exactly the new rows, chart and pointer. The kill golden
does not move.

**End to end:** `raid --fight 30` on `cW38jmwdnZfbHVL4`, the canonical wipe. Shape only: the state
is one of three, shares fall in a plausible range, T precedes the last compared second, the cost is
bounded.

**Live:** `raid --fight N` over the report's wipes, reading the findings JSON only, reporting per
state -- behind, on pace, ahead, withheld by reason, fallback, band cut -- how often it occurred, by
fight index and never by name.

**End to end, run 2026-09-28:** `test_a_real_wipe_is_compared_against_the_kills_pace` against
fight 30 of `cW38jmwdnZfbHVL4`, cold cache -- 89.01 points of 3600, passed first run.

**A state not yet seen.** Run live 2026-09-28 over all nine listed fights (28-34, 26, 8) of
`cW38jmwdnZfbHVL4`: all seven boss fights (28-34) landed `behind`; the two council fights (26, 8)
withheld with `compare.pace.unavailable`. On pace, ahead and the slowest-kill fallback did not
occur on any of the nine fights this report offers. The offline suite exercises each of those
code paths (§10, Unit), but until a live run shows on pace, ahead and the fallback actually
occurring, slice 1 is not exercised live in those three states. This is left open, not resolved
either way: RwlRwl is to supply another report to look for them on. No single run over the nine
fights passed the 120-point stop threshold set for this exercise; the costliest, fight 28, spent
45.63.

## 11. Measurements taken (2026-09-27, `cW38jmwdnZfbHVL4`, Heroic, about 46 points)

| Fight | Duration (s) | Share of kills' median at the wipe | State | Behind from (s) | Band under three (s) |
| --- | --- | --- | --- | --- | --- |
| 28 | 216 | 0.69 | behind | 25 | 0 |
| 29 | 106 | 0.85 | behind | 66 | 0 |
| 30 | 480 | 0.79 | behind | 24 | 18 |
| 31 | 110 | 0.84 | behind | 64 | 0 |
| 32 | 88 | 0.91 | behind | 85 | 0 |
| 33 | 279 | 0.78 | behind | 29 | 0 |
| 34 | 227 | 0.87 | behind | 27 | 0 |

All on Ula'tek, against four references of size 20 (kills of 461, 461, 504 and 518 s). The
measurement read fight 30's share at the wipe against the two kills still fighting then; under §5
it is compared through 461 s instead, the last second with three. Every reference on all three
boards was deathless.

**Corrected 2026-09-28, from the live command rather than the spike above:** the two council
wipes (26 and 8) do not withhold for want of a size-20 reference. `raid --fight N` run live against
both spent 2.00 points each and produced `compare.pace.unavailable` with detail `NO_SINGLE_BOSS`
("this fight has no single boss to compare"): the pace axis withholds before it ever looks for a
reference, because a council fight's report names no one boss actor after the fight, per the boss
actor rule in the Binding constraints. The sentence this replaces described a size mismatch that
this design never measured for fights 26 and 8; the live run found the actual, earlier cause.
Every figure in the table above matches what `raid --fight N` produced live on 2026-09-28, so
none of it needed correcting.

## 12. Out of scope

- Kills; they have the parse comparison.
- Enrage and berserk timers: no data.
- A boss-health projection (§6).
- Council encounters in slice 1.
- Slices 2 and 3 beyond what §2 records.
- Any change to `wipe.cause`.
