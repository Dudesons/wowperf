# Wipe analysis, Layer 2 — the grid, the chart, and the verdict on top

**Status:** approved 2026-09-19. Supersedes nothing. Implements sections 7.1–7.3, 8.4 and 11 of
`2026-09-18-wipe-analysis-design.md`, which remains the authority on everything else.

---

## 1. What this answers

Layer 1 says *why* an attempt ended. Layer 2 says *who needs to change* and *what the end looked
like*, and puts the verdict where a reader lands.

Three deliverables:

| | From | Lands on |
| --- | --- | --- |
| A per-player grid of damage taken | §7.1–7.3 | Mechanics |
| A players-alive chart | §8.4 | Summary, under the verdict |
| `wipe.cause` promoted to the Summary headline | §11 | Summary |

---

## 2. Scope

### 2.1 In scope

The three deliverables above, and the one extraction each needs.

### 2.2 Out of scope, and why

| Deferred | Why it is separate |
| --- | --- |
| The phase strip (§11) | Needs machine-readable phase identity, which `mechanics.phase.*` does not carry: the phase name lives inside a title string. Its own cycle. |
| Defensives at the moment of a hit (§7.4) | A different analyser answering a different question. It rewrites `defensives.never`, a family that once produced 29 of 55 findings on a real report, and that rewrite deserves its own design. |
| Extracting the doubled phase walk | **Not a prerequisite of this cycle.** The handoff into this work recorded that "Layer 2's per-player grid wants a third" phase walk. It does not: the grid is keyed by player and ability, and the chart by time. Nothing here reads a phase. The extraction remains worth doing, with the strip that needs it. |
| Splitting `MAX_MECHANICS_REPORTED` | Sidestepped rather than done. The grid takes a constant of its own (§4.1) instead of becoming that constant's fourth consumer. |
| A boss health curve | §8.4 settled this: `graph(dataType: Resources, hostilityType: Enemies)` returns zero series, measured 2026-09-18. |

---

## 3. The data layer

Two extractions. Both are pure, both live under `src/wowperf/domain/`, and neither adds a
traversal: each lifts a computation an existing function already performs and throws away.

### 3.1 `damage_matrix`

`damage_outliers` builds `by_ability[ability_id][actor_id]` and a per-ability median, reports
whatever clears `MEDIAN_MULTIPLE`, and discards the rest. The grid needs precisely what is
discarded.

```
damage_matrix(players, damage_taken, roles) -> DamageMatrix
```

`DamageMatrix` carries, per ability: its name, the per-actor totals, the median over the players
who took it, and `took_count`. `damage_outliers` becomes a filter over this object, so the
findings and the grid read one computation.

**One behavioural change, additive.** Tanks are excluded from the median exactly as today — a
tank taking ten times the median is the job, not a finding — but their totals are now retained so
the grid can show them. No median moves, so no existing finding changes. §12 requires this to be
asserted rather than assumed.

**The amount is `hit.amount`, the unmitigated figure.** `DamageTakenEvent` carries three numbers
and they answer different questions: `amount` is how hard the hit landed before mitigation and
absorption, `health_damage` is what reached the player's health, and `absorbed` is what a shield
soaked. `damage_outliers` reads `amount`, which is the honest answer to "how hard did this hit",
and the grid inherits that measure unchanged.

Named here because a grid invites the reading that a cell is what the player *suffered*. It is
not: a fully absorbed hit still shows its full size, which is correct for a table about what the
encounter threw at people and wrong for one about what it cost them. Nothing here converts between
the three.

### 3.2 `alive_over_time`

`_alive_at_the_end` in `attempt_shape.py` already decides who is standing, resurrections and all.
Generalise it:

```
alive_over_time(size, deaths, resurrections) -> tuple[AlivePoint, ...]
```

`_alive_at_the_end` becomes this function's last point.

**This is the point of the extraction, not a tidy-up.** The verdict's first evidence line reads
"N of 20 alive at the end". A chart computing its own step function would sooner or later end on a
different number, and the page would contradict itself in two places a reader sees at once. One
computation makes that impossible; §6 pins it with a test.

The rule carries over whole, including the case where a resurrection shares a death's timestamp:
the player stays down, because a rez cannot land on somebody who has not died yet.

**It is a floor on the living, not a reading of them.** A player who releases and runs back leaves
no record at all, so the series is badged `derived` wherever it appears, exactly as the verdict's
own fact is.

---

## 4. The view models

Both are view models and neither is findings. Twenty players by five abilities is a hundred cells;
as findings that is the cap problem five times over, and §7.1 already rules it out.

### 4.1 `RaidGrid`

A new frozen model. **Not `ComparisonRow`**, despite §7.1's "reusing that pattern": that model
holds one measure per row in fixed `ours`/`theirs`/`spread` fields and cannot express a table with
a column per ability. The `<details>` block and the visual idiom are reused; the model is not.

- One `GridRow` per player, including tanks.
- One `GridCell` per column, carrying the amount already formatted, the multiple where one
  exists, and `tinted`.
- Columns are the abilities `mechanics.ability.*` reports, plus every ability
  `mechanics.lethal.*` names, capped at a new `MAX_GRID_COLUMNS`.

**`MAX_GRID_COLUMNS` is 5.** Its own constant, not `MAX_MECHANICS_REPORTED`, which already governs
three families: a fourth consumer whose constraint is table width rather than list length would
force one number to serve two unrelated questions. It starts at the same value only because five
columns is what fits; the two are free to move apart.

The two sources can together name more than five abilities. Where they do, the ranked list's
order decides, and the lethal abilities that did not fit are still named on the same tab by
`mechanics.lethal.*`.

**Two cells carry no multiple.** A tank's, because tanks are outside the median by design, and any
cell for a player who took none of that ability, because there is no ratio to state. Both print
their amount — `0` for the second, which is a reading and not a gap.

**A cell is tinted only where `damage_outliers` minted a finding for that exact
`(actor_id, ability_id)`.** Not a recomputed threshold — the finding's own existence. So the grid
can state nothing the page does not already say outright, every tint has a card behind it, and the
two cannot drift. Tank cells are therefore never tinted, without needing a rule of their own.

Note what this means for a column: an ability earns its column from the ranked list or from having
killed somebody, neither of which is the outlier measure. A column where nobody was an outlier is
therefore normal, and shows five untinted numbers. That is a column doing its job — it says the
ability hit the raid evenly.

Untinted cells still show their number: the grid stays a full table, not a highlight reel.

**§7.3 holds, and the page carries it.** A tint means "took far more of this than their raid did".
It does not mean a mistake, and the table says so where a reader sees it rather than only here.
Taking a tankbuster is correct, and soaking is doing the job.

### 4.2 `AliveChart`

The step series from §3.2, with boss health at the end point from `Encounter.boss_percentage`,
already ingested and free.

Drawn as **inline SVG**, beside the macros the death health-curves already use. No new rendering
machinery, no stylesheet, no remote asset: the report invariant is one HTML file whose only
outbound addresses are ability icons on `wow.zamimg.com`.

One series, not two. §8.4 settled that there is no boss health curve to draw beside it.

### 4.3 The verdict headline

`RaidReport` grows `verdict: LedgerRow | None`.

**`None` on a kill and on a withheld wipe**, and the template renders the slot only when it is
present. A kill produces no verdict at all, and a withheld wipe now states its reason in
Provenance rather than on the Summary — a landing tab whose first line announces that nothing was
concluded is the complaint §11 exists to fix, not a fix for it.

Those pages keep today's Summary unchanged.

---

## 5. Placement

Tab count stays at seven. No `data-tab-*` changes and no JavaScript changes.

- **Summary:** the verdict, then the chart under it, then today's contents.
- **Mechanics:** the ranked list, the lethal abilities, then the grid.

---

## 6. Testing

Beyond unit coverage of both extractions and both view models:

- **`damage_outliers` is unchanged.** Its existing tests pass untouched, and a test asserts no
  median moved when tank totals began to be retained.
- **The chart ends where the verdict says.** `alive_over_time(...)[-1]` equals the figure the
  verdict's evidence line prints, over a fixture with a resurrection and a second death.
- **A tinted cell always has a finding behind it.** Over a fixture producing both tinted and
  untinted cells, every tinted `(actor_id, ability_id)` appears in `damage_outliers`' output and
  every untinted one does not.
- **A tank row is never tinted**, and is present.
- **The headline is absent on a kill and on a withheld wipe**, and present on a wipe with a
  verdict.
- Golden-file update, and a live run against the canonical wipe — report `cW38jmwdnZfbHVL4`
  fight 30. A step function over twenty real players and a real battle resurrection is where this
  breaks if it breaks.

---

## 7. What would make this wrong

- **If a grid reads as a scoreboard.** The tint rule and §7.3's sentence are the defences. If a
  reader still reads red as blame, the answer is fewer tinted cells, never a softer word.
- **If the chart's floor is read as a count.** It is badged `derived` for a measured reason.
- **If `damage_matrix` grows a consumer that wants phases.** It does not have them, deliberately.
  That consumer wants the extraction §2.2 defers.
