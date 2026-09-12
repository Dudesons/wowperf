# The damage done track

A second bar track on the player timeline, drawn from Warcraft Logs' own pre-aggregated series, so
a reader can see whether a cooldown press produced anything.

Extends the player timeline of `2026-09-12-report-second-reading-design.md` §5. Bound by
`2026-09-03-mplus-postmortem-design.md` §5.5, which is **not** amended here: nothing in this design
ranks damage, and §4 and §5 say how that is kept true.

## 1. Why

The chart draws **throughput cooldown rows** underneath a **damage taken** track. So it shows when
a player pressed a damage cooldown, and what was hitting them, and nothing at all about what came
out. "Did I press my burst where it mattered" is the question the drawing most invites and the one
it cannot answer.

`throughput.alignment.*` makes that claim in words already — it names cooldowns that were off
cooldown when a big pack was engaged and were not pressed. What words cannot do is show the reader
the moment. A press mark above a flat stretch and a press mark above a peak are the same row today.

## 2. What we fetch

One query per run, issued with the other fight-scoped fetches in `WclRunRepository.load`:

```graphql
graph(dataType: DamageDone, hostilityType: Friendlies,
      fightIDs: [$fightId], startTime: $startTime, endTime: $endTime)
```

Measured 2026-09-12 against report `G7MBJZfNakrcPvAx` fight 3, and recorded with its date in
`.claude/skills/wcl-api/SKILL.md`: **one call, no pagination**, returning `data.series` — one entry
per player plus a `Total` — each carrying the actor `id`, `guid`, class `type`, `pointStart`,
`pointInterval`, `total`, and a list of numbers. Cached in the permanent tier with the rest of the
analysed run, so every re-render is free.

**The event stream was the obvious plan and is the wrong one.** `events(dataType: DamageDone)`
returns at most 10000 rows a page — measured offline from the cache, where one page came back at
exactly 10000 carrying a `nextPageTimestamp` and thirty others came back short with none — and this
fight alone logs 8804 damage-taken events and 8423 friendly casts, so the damage *done* stream is
some multiple of that and pages accordingly. The graph replaces an unknown number of pages with one
call.

### 2.1 The points are a rate

**The series' numbers are damage per second, not damage in the bucket.** Verified on all five
players independently: `sum(points) * pointInterval/1000` reproduces the series' own `total` to
within 0.3% to 0.7%. Reading the points as amounts understates by a factor of `pointInterval` in
seconds — 6.4 on this run.

`ingest.py` converts once, at the boundary:

```
amount = point * (pointInterval / 1000)
```

Nothing above the adapter ever sees a rate. This is the single line most able to fail quietly —
every bar a sixth of its true height, and the chart still entirely plausible — so §6 gives it the
most unambiguous test in the set.

### 2.2 Pets are already folded in

**The API attributes a pet's damage to its owner**, so this design does no pet handling at all.
Measured 2026-09-12: the Death Knight's graph series total is 213,303,506, which equals that
player's `table(dataType: DamageDone)` entry total **with** its three pets, and not the 173,621,604
without them.

It matters more than it sounds. **39,681,902 of that player's damage — 18.6% — comes from things
they summoned**, and Dancing Rune Weapon is one of the throughput cooldowns this chart already
draws a row for. Had the figures excluded pets, pressing it would have drawn a press mark above a
flat track: the exact opposite of what the reader is being invited to conclude. Four of the five
players on this run own pets.

### 2.3 What ingest drops

**The `Total` series.** It is the sum of the other five — verified, largest gap at any bucket 0.2 —
and nothing here has a use for it. Refusing it at the door is cheaper than repeatedly explaining
why a run-wide damage total sits unused in the model, one import away from a page that ranks.

`LoadedRun` gains one field, `damage_done`, holding per actor the id, `point_start`, `interval_ms`
and the per-bucket amounts, as frozen tuples — the shape `ability_icons` and the aura bands already
travel in.

**One call serves every player.** The response carries a series for each of them, and each player's
own timeline draws its own. So the cost does not scale with `--all-players`, and a single-player
run pays for series it does not draw — one point, once, cached forever.

## 3. How it is drawn

The track sits **between the damage taken bars and the first cooldown row**. That placement follows
from the purpose rather than from taste: the reader's eye goes from a press mark to the output it
produced, so the two must be adjacent, and anything between them is in the way.

| | Now | After |
| --- | --- | --- |
| Damage taken bars | 44 to 76 | unchanged |
| Damage done bars | — | 84 to 116 |
| First cooldown row | 96 | 136 |
| Chart height, 19 rows | 428 | **468** |

Same upward growth from its own baseline, its own peak label, its own CSS class in a colour
distinct from the damage bars above and the four cooldown states below. Each bar's hover answers
like its neighbour above — the amount, the time, and which pull it fell in, through `_bucket_pulls`.

**The scale is the player's own tallest bucket.** The existing track's caption already says this,
and is reused verbatim rather than re-derived: *"Each bar is a 5-second bucket, and the axis runs
from nothing to this player's own tallest, never the group's."* That clause is what keeps §5.5 true
on a chart that now draws output, and rewriting it would risk weakening it.

### 3.1 Two bucket widths, and why they stay

The graph hands back about 6.41 s buckets — 241 points across a 1538.8 s window, with no argument
to set the interval — while the damage taken track buckets its own events at 5 s.

Re-bucketing damage taken to match was the obvious fix, and the measurement refuses it. The track
is 506 units wide for 1538.8 s, so a 5 s bar is **1.64 units** and a 6.41 s bar is **2.11** — at a
1400 px window, **3.4 px against 4.3 px**. Under a pixel of difference is not worth re-cutting a
track that works, has tests, and sits in the golden file.

Each caption states its own width. The option stays open: we hold the raw damage taken events, so
re-bucketing them at whatever interval the graph reports remains available if the difference ever
becomes visible.

**`BUCKET_SECONDS` is formatted with `int()` in three places today.** 6.41 is not an integer, so the
damage done captions take one decimal — otherwise the page claims 6-second buckets for 6.4-second
bars.

## 4. What it may claim

**The bars carry `derived`.** Damage taken is summed from individual logged events and is
`measured`. Damage done is reconstructed from a rate, and that reconstruction does not close
exactly: it lands within 0.3% to 0.7% of the API's own `total`, and the residual is explained — 241
buckets of 6.4117 s span 1545.2 s of a 1538.8 s window, so the last bucket overhangs the fight by
0.4%. A figure that near the truth by a documented rule is what `derived` means here.

The chart's legend therefore gains a third badge line; it carries `measured` and `inferred` today.

**Rescaling the buckets to hit `total` exactly is refused.** It would move damage away from the
moment the API placed it so that a sum looks tidy — trading a stated 0.4% for a silent
misplacement, on a chart whose whole subject is when things happened.

## 5. What this design refuses

- **No rate reaches the page.** The response gives DPS natively and printing it would cost one
  line. It is the number §5.5 refuses to produce: *"Ranking individual throughput in Mythic+ invites
  exactly the behaviour this tool exists to coach out."* A hover says damage in this bucket, never
  damage per second. The rate dies in `ingest.py`.
- **No finding comes out of this.** Nothing analyses the track: no entry in the findings JSON, no
  `seconds_lost`, no rank. A finding saying "you pressed Avatar and got X out of it" would be
  scoring throughput, and scoring it wrongly — a cooldown held through one pack for a bigger one
  thirty seconds later is good play, and reads here as a gap.
- **The alignment reading stays the reader's.** The chart puts the press and the output on one
  axis. It concludes nothing, and no text on the page claims it did. This is the line
  `throughput.alignment.*` already walks in words.
- **No cross-player comparison**, guaranteed structurally by the own-peak scaling rather than by a
  caveat a reader has to find.
- **A player with no series draws no track, and says so** — the abstention `NO_AURA_DATA` already
  makes for cover, rather than a flat line that reads as "you did nothing".

## 6. Tests

1. **The rate becomes an amount.** Interval 6000 ms, point 100, expect 600. Dropping the multiply
   gives 100; inverting it gives 0.0167. Both die loudly.
2. **Each track scales to its own player.** Two players an order of magnitude apart; the smaller
   one's tallest bar is still full height. This is the anti-ranking invariant expressed as a test,
   and it fails the moment someone normalises across the roster — the "helpful" change most
   available to a reader who has not read §5.5.
3. **The `Total` series never survives ingest.** A fixture carrying one with a distinctive value;
   assert that value appears in no series.
4. **No rate reaches the page.** Rendered hovers contain no "per second" and no "DPS", paired with a
   positive assertion that a hover states its bucket's amount and its duration — so a changed hover
   fails the positive half first and says why, rather than leaving the negative half vacuous.
5. **A player with no series draws no track and says so.**
6. **Every new numeric view-model field joins `NUMBERS_THAT_ARE_NOT_TOTALS`** in
   `test_html_invariants.py`, with a reason it cannot hold a total. The previous plan missed this
   and the existing invariant test caught it, so it is a step here rather than a thing to remember.

**The golden file is a weak net here.** Its fixture is small on purpose and has no cooldown rows.
The real coverage is a builder-to-page seam test, the shape commit `0990494` established.

**One regression to verify on a real page.** The row hover strips are positioned as
`baseline_y / height * 100`. This change moves `FIRST_ROW_Y` from 96 to 136 and the chart height
from 428 to 468, so **every strip percentage shifts**. The `hit_top` tests should catch a mistake,
but a strip that hovers the wrong row is invisible to the offline suite and obvious to a reader, so
the implementation confirms it against a rendered report before finishing.
