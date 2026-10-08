# Debuff coverage on council bosses

**Status:** approved design, 2026-10-08; planned in `docs/plans/2026-10-08-council-debuff-coverage-plan.md`.
**Area:** the boss debuff figure of `docs/plans/2026-10-07-enemy-debuff-uptime-design.md` (PR #57).
This design lifts that design's §2 exclusion of council pulls. It builds on that branch, and it
supersedes it wherever the two overlap.

## 1. Why

The boss debuff figure withholds every council pull. Its design left them out because a council's
bosses can die at different times, so the pull's length is not each boss's time. On the cached
keys this withholds:

- **Kyrakka and Erkhart Stormvein:** on every Ruby Life Pools key (20 of 20);
- **Adderis and Aspix:** on every Temple of Sethraliss key (6 of 6).

That is one boss in three or four, on every key of both dungeons measured. Each council boss's death
is in the log, in the `EnemyDeaths` stream our own full load already reads, so its time can be
bounded without guessing at an end.

## 2. Decisions

RwlRwlRwlRwl decided each of these on 2026-10-08.

1. **A council is measured as coverage across its bosses.** Its figure is the debuff-seconds on all of
   its bosses, divided by the seconds each boss was alive, summed. Take Blood Plague on Adderis for
   140 s of his 150 s, and on Aspix for 150 s of her 200 s: that is 290 / 350 = 83%. For a single boss
   this is exactly the existing figure, so the whole row keeps one definition: **the share of
   boss-alive seconds that carried the debuff.** It is also the "enemy coverage" measure the parent
   design planned for trash.
   - Rejected: "on any council boss" over the pull, which inflates and matches nothing else; and one
     judged cell per council boss, which multiplies cells and misreads an ability aimed at one boss.
2. **The references read `EnemyDeaths` too.** It is the same stream and query our side uses, so both
   sides' boss times come from one measured rule. It costs about 1 point per parse reference, paid
   only when its counterpart resolves.
   - Rejected: inferring a death from the last debuff removal on the boss. That is free, but it is
     blind when nothing was on the boss at its death, and it would measure the two sides differently.
3. **Covered seconds are counted per target, then summed.** The existing internals keep a player's
   debuffs as time bands on one timeline, and merge them. That is right for one boss and wrong for a
   council, where both bosses are alive at once and a second covered on both must count twice.
   - Rejected: shifting council bosses onto separate stretches of a fake timeline, which makes
     timestamps lie; and one window per council boss, which the merge then collapses and undercounts.

## 3. What the reader sees

- **A council cell is a figure.** It shows the council's coverage against the reference median, e.g.
  "83% against 88%" under "Kyrakka and Erkhart Stormvein", and carries no verdict, like every boss
  column.
- **The row's figure counts council time.** Single-boss figures do not move.
- **The caption** stops saying council pulls are left out. It says a council is measured over the time
  each of its bosses was alive, from the pull's start to that boss's death.
- **"No boss found" stays withheld.** For example Avatar of Sethraliss, whose pull lists no Avatar among
  its enemies.
- **The "council" withheld reason is removed.** Nothing produces it any more, so it is not kept unused.
- **Shared debuffs** (a teammate's application replaces yours) work on councils: two players' copies
  are compared boss by boss, and the overlaps are summed. The tolerance of one second in total and the
  rule of at least two holders are unchanged.
- **Confidence stays `derived`.** One part is inferred: a council boss's time starts at the pull's
  start, because the log records a death but never an appearance. This is stated, not hidden.

## 4. Components and data flow

1. **Death times (adapter).** `WclRunRepository.debuff_log` also reads `EnemyDeaths` for the same
   fight. The query and variables are those of our full load, so on our side this is a cache hit and
   free. `DebuffLog` gains the fight's enemy deaths, each as a game id and a timestamp.
2. **Boss targets (domain, `comparison/boss_debuffs.py`).** Each measured boss pull lists its targets,
   each a boss game id with a time span:
   - **Single boss:** the boss, over the whole pull. This is unchanged.
   - **Council:** each matched boss, from the pull's start to its **last** death inside the pull, or
     to the pull's end if it never died there (a wipe). The last death covers a boss revived mid-fight.
   - **Partial council:** when the pull is named "A and B" but only A is among its enemies, A alone is
     measured.
   - Deaths match a boss by **game id**, for the reason the pairing keys on it: one enemy can be logged
     under two actor ids.
   - The naming rule that picks the boss or the council is the one amended on 2026-10-08: name first,
     flag second. An ambiguous part still reads no boss found.
3. **Covered seconds (domain).** For each player and debuff, the seconds the debuff was on each target,
   clipped to that target's span, are summed over targets. Each target's own player and pet copies are
   merged first, so a second is never counted twice on one target. The figure is covered seconds over
   the targets' total seconds, overall and per encounter.
   - This replaces the band-and-merge path inside `boss_debuffs.py`.
   - `debuff_fractions`, `per_member_fractions` and `encounter_share` read the new totals. The
     thresholds, the median rule, the table, the page and the finding ids are untouched.
4. **Shared rule.** The overlap between two owners is computed per target, then summed.
   *Amended 2026-10-08, while planning:* only owners who held the debuff on a common boss within one
   pull are compared. Copies that each kept to a different council boss never met, so they show
   nothing either way. The same holds for two owners who held it on one boss in different pulls only,
   one in a wipe and the other in the kill, since a boss is keyed by its pull and its game id. For a
   single boss in one pull this is the existing rule.
5. **CLI.** No wiring change. The deaths arrive inside the `DebuffLog` that `analyze` already fetches
   once per run.

## 5. Edge cases

- **A council boss with no death in a kill pull.** It is measured to the pull's end. The run's pairing
  tally counts it as a council boss with no death: recorded, never judged, and a log oddity to examine.
- **A council boss untargetable for part of the fight.** Coverage then cannot reach 100%, on either
  side, so the comparison stays like for like. The live run records how far the references sit below
  100%, and this design is amended with it.
- **An ambiguous name.** No boss found, as now.

## 6. Testing and proof

Tests come first and use invented names only. They cover:

- council coverage summed over two bosses that died at different times;
- a wiped council, where neither boss dies;
- a boss that dies twice, measured to its last death;
- one boss logged under two actor ids;
- a partial council;
- a shared debuff on a council, with the overlaps summed per boss;
- **a single boss whose figure is identical to today's**, the regression guard;
- the council cell and the caption on the page;
- `debuff_log` reading `EnemyDeaths`, with our side paying no extra call;
- the CLI: a reference's `EnemyDeaths` read once, and only when its counterpart resolves.

**Live proof,** per CLAUDE.md's invariant:

- Rerun `analyze` on `LyKXYvVZm192TDr6` fight 9 (`--all-players`) and `nd6Rz47Gj1ZPxFfm` fight 3.
- Report how often each state occurred, the council cells included, and the council coverages on our
  side and the references'.
- Survey the 26 cached keys for council bosses with no death in a kill pull.

## 7. Cost

These are estimates, not measurements:

| Item | Estimate |
| --- | --- |
| A one-player `analyze` | about 5 points more |
| `--all-players` | about 20 points more |
| The live proof | about 25 points |

The first live run records the real figures in the wcl-api skill.

## 8. Documentation, when it ships

- **The parent design.** A dated amendment to `2026-10-07-enemy-debuff-uptime-design.md` §2, saying
  council pulls are measured by this design.
- **The mplus-analysis skill.** The debuff bullet: a council's cell is coverage across its bosses.
- **The wcl-api skill.** The use of `EnemyDeaths` on references, and its live cost.
- **CLAUDE.md.** Remove "council" from "Trash, raid and council pulls are not measured yet".
