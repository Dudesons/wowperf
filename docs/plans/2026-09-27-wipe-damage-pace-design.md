# A wipe's damage pace against the kills, with a projection

**Status:** approved design; slice 1 planned in
`docs/plans/2026-09-27-wipe-damage-pace-plan.md` and built. Slice 2 specified in §13 (approved
2026-09-28), planned in `docs/plans/2026-09-28-wipe-pace-per-player-plan.md` and built.
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
   twenty. **Specified in §13 (approved 2026-09-28)**; the roster check it waited on was run
   that day, and §13 amends this paragraph where the two differ.
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
  defensive ceiling's notices do, with its reason: no single boss actor (a council); our boss's own
  damage graph held no series to compare; no reference kill of this raid size; the boss absent from
  every reference; no second of the attempt could be compared against the references at all. The
  Damage tab then shows nothing, not an empty chart.
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

**Golden:** no wipe golden exists. The raid golden is a kill handed a real, behind pace sample --
it pins the kill gate (design section 4's "only on a wipe": nothing from that sample reaches the
page). The render tests pin the pace chart's own elements, the Summary pointer, and the
Provenance line, against fixtures built for those tests rather than against the golden file
(ruled 2026-09-28).

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
occur on any of the nine fights this report offers. The offline suite does exercise each of those
code paths (§10, Unit) -- including, after the 2026-09-28 fix wave, the exactly-one-reference
wording of the fallback and its projection, which `test_the_fallback_names_the_slowest_kill_and_gives_no_range`
alone had left at two references and untested at one -- but until a live run shows on pace, ahead
and the fallback actually occurring, slice 1 is not exercised live in those three states. This is
left open, not resolved either way: RwlRwl is to supply another report to look for them on. No
single run over the nine fights passed the 120-point stop threshold set for this exercise; the
costliest, fight 28, spent 45.63.

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
- Council encounters in slices 1 and 2.
- Slice 3 beyond what §2 records.
- Any change to `wipe.cause`.
- A per-player projection (§13.3).

## 13. Slice 2: each player's pace against the same specialisation

Approved 2026-09-28. Everything in §1-§12 holds for this slice unless this section says otherwise.

### 13.1 The roster check

Run 2026-09-28 against the four references the mechanics comparison drew for fight 30, about 15
points, and recorded in `.claude/skills/wcl-api/SKILL.md` ("A reference kill's roster costs one
point more, read in the same lookup"). `friendlySpecs` names the specialisation only, so the class
comes from the reference report's player actors (`subType`); every roster id resolved; the
boss-only graph's per-player series ids equalled the roster's on three references, and one
reference carried a 21st series with no roster entry.

**The sample is thin, and that shapes the slice.** Fight 30's twenty players hold 19 distinct
class-and-specialisation pairs. Across the four references, 10 of them have three or more players
of the same pair, 5 have two, 1 has one and 3 have none. About half the raid gets a reading on the
canonical wipe.

### 13.2 Data

- **The reference roster** is read in the one reference-fight lookup §4 already makes, with
  `friendlyPlayers`, `friendlySpecs` and `masterData(translate: true) { actors(type: "Player") { id
  subType } }` added: one request per reference as before, priced 2.00 points against 1.00, about
  four points more per wipe. The report's player actors span the whole report (370 actors on one
  reference for a 20-player fight), so they are an id-to-class lookup and never the roster.
- **The damage** is the per-player series of the boss-only graphs §4 already fetches, ours and each
  reference's. No new graph. A series whose id is not in its fight's roster is dropped.
- **Who is compared:** the players the `raid` command analyses (`--player`, `--all-players`), kept
  when `data/roles.toml` reads them as damage or tank. Healers are not compared.
- **Against whom:** every reference player of the same class and specialisation, pooled across the
  reference kills, each over their own kill's length.

### 13.3 The comparison

- **The band** is §5's arithmetic over those players: lowest, median and highest at each second,
  cut where fewer than three are still fighting. States as §5: behind below the lowest, ahead
  above the highest, on pace between. "Behind from T" and the earlier-stretch bar are §5's.
- **Below three same-specialisation players: withheld**, with a notice (ruled 2026-09-28). There is
  no slowest-player fallback: one other player's boss damage mostly reflects what that raid
  assigned them, so a comparison against one player reads as a verdict on a coin flip.
- **The window** runs from the pull to the player's first death that no resurrection answered, or
  to the wipe's end. A death answered by a resurrection or a self-resurrection, as `return_of`
  classifies it for the death recaps, does not end the window: the stretch spent dead stays in and
  is named in the evidence. A release ends the window, since on a wipe a release is the end of the
  attempt for that player. A reference player's window ends at their first death, answered or
  not: a reference kill's resurrections are not read, so an answered death cannot be told from
  one that was not, and ending at the first death only drops that player from the band sooner
  than an unread resurrection would have. Every reference read so far was deathless.
- **The time lag** replaces a projection. Take the player's cumulative boss damage at the end of
  their window; find the first time at which the same-specialisation median reaches it, interpolated
  within the second, searched over every second the band holds; the lag is the window's end minus
  that time, behind when positive and ahead when negative. When the median never reaches the
  player's damage before the band ends, the lag is not a number and the evidence says so. It is read
  off the same curves as the share, so the two cannot disagree, and it assumes nothing about pace
  holding.
- **No per-player projection.** The raid-wide projection answers a real event: the boss dies when
  the raid's total reaches the kills'. No event answers one player reaching one specialisation's
  total, and at a steady pace such a projection is the share restated as a guess.

### 13.4 Findings

- **`compare.pace.player.<slug>`, `derived`**, one per compared player. Titles follow §5's shape,
  naming the pair: "Behind the kills' Frost Mages: 82% of their median boss damage by 3:20";
  "On the kills' Frost Mages' pace: ..."; "Ahead of the kills' Frost Mages: ...".
- **Evidence, in order:**
  - "Against 7 Frost Mages across 4 reference kills of this raid size";
  - "Their range at 3:20: 88% to 112% of their median";
  - the lag: "By 3:20 they had dealt what the kills' Frost Mages had dealt by 2:41: 39 seconds
    behind"; ahead, "... by 3:52: 32 seconds ahead"; past the band, "More than the kills' median
    had dealt by 5:10, where fewer than three were still fighting";
  - where the window ended: "Compared through the wipe at 3:20", "Compared through their death at
    2:05", or "Compared through 4:10, after which fewer than three Frost Mages were still
    fighting";
  - "Dead from 1:10 to 1:40, then resurrected", one line per answered death;
  - "Behind from 2:30 to 3:20", and "Also behind between ..." under §5's bar.
- **The detail** says this is damage to the boss only: a player assigned to adds, or a tank who
  held adds, reads behind for that assignment, not for their play.
- **`compare.pace.player.unavailable.<slug>`, `measured`**, the withheld notice, on the player's
  card: "Only 2 Frost Mages in the reference kills: fewer than three to compare against." A player
  whose specialisation the report does not name reads "This report does not name their
  specialisation."
- **When the raid-wide comparison was withheld** (§7: a council, no reference, no boss series), no
  per-player finding or notice is emitted; the raid-wide notice in Provenance covers them.
- A player with no series in our graph dealt the boss nothing: 0%, and no lag. A player dead before
  the first second has no reading and no line.

### 13.5 On the page

- The finding and the notice sit on the player's card on the Players tab, in the comparison family.
  No new chart, no Summary pointer: twenty charts would bury §7's one, and twenty pointers would
  crowd the verdict.
- Provenance says once: "Damage pace per player compares damage dealers and tanks only."
- No raw damage figure anywhere: shares, clocks and seconds.

### 13.6 Wiring

`load_pace_sample` also returns, per reference, its roster (actor id to class and specialisation)
and its per-player boss series, and our own per-player series, read from the graph already fetched
by a builder beside `build_boss_damage` that keeps the integer-id rows. A pure
`analyse_player_pace` takes the sample, the analysed players with their roles, and our deaths and
resurrections, and reuses `return_of`. The band and lag arithmetic sits in `pace_curve.py` beside
§5's. No I/O in the domain. The only added cost is the point per reference.

### 13.7 Testing

**Unit:** pooling by class and specialisation across references; each window end -- the wipe, an
unanswered death, a resurrected death, a release; the lag behind, ahead and past the band; the
notice below three and for an unnamed specialisation; healers not compared; a player absent from
our graph at 0%. **Integration:** the per-player builder on a hand-written graph payload, the
roster in the reference lookup, the finding and the notice on the card. **Render:** a card carries
the line; a withheld card carries the notice. **End to end:** shape only, on fight 30.
**Live:** `raid --fight N` over fights 28-34 of `cW38jmwdnZfbHVL4`, reading the findings JSON only,
counting by fight and player index -- never by name -- how often each state occurred: behind, on
pace, ahead, lag past the band, withheld below three, withheld for an unnamed specialisation. A
state that never occurs is reported as open, as §10's were.

**Live (2026-09-28, `cW38jmwdnZfbHVL4`, fights 28-34, `raid --fight N --all-players`).** Seven
wipes, twenty players each; four healers per fight carry no line, so 112 per-player lines, 16 per
fight. Player indices count each findings file's distinct player slugs in sorted order, the same
twenty on every fight.

- **69 readings, all `derived`:** behind 30, on pace 26, ahead 13.
- **The lag:** behind 44, ahead 22, past the band 3 (fight 30, players 8, 12 and 14). A lag of
  exactly zero never occurred, and neither did a player with no series in our graph (0%, no lag).
- **The window's end:** a death 60, the band cut 8 (all fight 30), the wipe 1 (fight 29, player
  16). The findings file does not tell an unanswered death from a release, so the release's own
  window end is not counted apart.
- **A resurrection stretch named:** 2 (fight 30, players 10 and 14).
- **43 notices, all `measured`, all withheld below three:** players 0, 1, 3, 6, 7 and 15 on every
  fight, and player 10 on fight 28 only, where they played another specialisation than on fights
  29-34.
- **The e2e** (`test_a_real_wipe_is_compared_against_the_kills_pace`, fight 30, `--all-players`,
  cold cache) spent 83.00 points; the seven distribution runs 15.00 together, against a warm
  cache (9.00 for the first, which re-read the four reference lookups, then 1.00 each).
- **No reference kill's deaths were ever read:** the e2e's one `Deaths` call was our own fight's,
  and no distribution run made one.
- The seven pages carry no template leak: no `>None<`, `>null<`, `>nan<`, `nan%`, `inf%`, `{{`
  or `{%`. Four pages carry `>None ` once each, and each is the deaths finding's own sentence
  opening "None of these".

**Open:** withheld for an unnamed specialisation (0 occurrences), the "no second could be
compared" notice (0), a player at 0% with no lag (0), a lag of exactly zero (0), a window ended
by a release as distinct from an unanswered death (not observable in the findings file), and a
reference player's window ended by their death (no reference kill with a death was drawn).
