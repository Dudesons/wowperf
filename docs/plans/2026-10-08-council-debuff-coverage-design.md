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
- **The row's figure counts council time.** Single-boss figures do not move, for every pull Warcraft
  Logs lists once. *Amended 2026-10-08, final review:* a boss pull listed twice is the exception, and
  section 5 says what it did before and what it does now.
- **The caption** stops saying council pulls are left out. It says a council is measured over the time
  each of its bosses was alive, from the pull's start to that boss's death, or to the pull's end if it
  did not die there.
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
   - *Amended 2026-10-08, live:* the log stamps the last council boss's death 3 to 36 ms after the
     pull's end on all 26 cached council kills, so a death counts for a pull from its start up to the
     next pull's start, and the span is capped at the pull's end.
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

*Amended 2026-10-08, final review:* `dungeonPulls` is sorted by start, but it lists some boss pulls
twice. Over the 969 cached keystone fights, 10 boss pulls in 5 fights appear as exact duplicates, with
the same name, start and end, and all of them are wipes.

- **The rule.** `boss_windows_of` skips a boss pull whose encounter, start and end equal the previous
  boss pull's, so one physical pull is measured once. When it looks for the next pull, it also skips
  any pull, trash or boss, with the same start and end as the current one: a duplicate of this pull is
  not the next pull.
- **What it fixed.** The branch counted a duplicate's boss-alive seconds and its covered seconds twice,
  so a pull's seconds read 120 s instead of 60 s, and a figure summed with other pulls was weighted
  wrongly. A boss pull listed twice, with a debuff on it from 20 s to 50 s of a 60 s pull, read 0.50
  over 120 s and now reads 0.50 over 60 s. The first copy's next-pull horizon was its own start, so no
  death was admitted there.
- **Single-boss figures before the branch.** The earlier code merged the numerator once and summed the
  denominator twice, so on those 5 fights the single-boss figure was itself halved: the same pull read
  0.25. The claim that single-boss figures do not move holds for every pull listed once. On a pull
  listed twice, the figure moved from 0.25 to 0.50, which is the true share.
- **A death in a pull's own span always counts.** A council boss's death is a pull's when it falls from
  the pull's start and either at or before the pull's end, or before the next pull's start, or there
  is no next pull. A next pull that opens before this one closes cannot hide a death inside this one.
  The span stays the last such death, capped at the pull's end.

*Amended 2026-10-08, live:* `analyze` ran on `LyKXYvVZm192TDr6` fight 9 with `--all-players` and on
`nd6Rz47Gj1ZPxFfm` fight 3. Both runs used the death rule of §4 as amended.

- **Council cells:** all 24 were measured, 22 on Kyrakka and Erkhart Stormvein and 2 on Adderis and
  Aspix. None was withheld.
- **Boss-alive seconds:** the council adds 391.4 s on the first key (Kyrakka 212.7 s and Erkhart
  178.7 s) and 365.4 s on the second (Adderis 164.4 s and Aspix 201.0 s).
- **Single bosses:** no single-boss cell moved, in figure, median or withheld state. The row
  figures moved, since council seconds joined the denominator. Ours moved most on Flame Shock, by
  -15.69 points, and on Deathstalker's Mark, by -14.52.
- **Deathless:** 0 on both keys. A survey of the 26 cached keys found the death of every council
  boss of a kill, 52 of 52, and no coverage above 100%. The highest share any player held was 100.00%
  on a single boss and 99.37% on a council.
- **Council coverage, ours against the median,** in four examples:
  - Blood Plague, 92.72% against 98.97%;
  - Mystic Touch, 98.24% against 97.77%;
  - Mortal Wounds, 50.84% against 70.80%;
  - Touch of the Magi on Adderis and Aspix, 13.14% against 14.31%.
- **The untargetable question,** on Kyrakka and Erkhart, was not settled.
  - The council cell medians, the compared players' own references, sat at 97.5 to 99% on three
    debuffs: Mystic Touch 97.77%, Atrophic Poison 97.54% and Blood Plague 98.97%.
  - The survey measured group-union coverage on the council bosses: the union over every player of
    a reference's group, not the compared player's figure. It ranged widely across reference pulls:

    | Debuff | Group-union coverage | Reference pulls |
    | --- | --- | --- |
    | Mystic Touch | 97.3 to 99.2% | 6 |
    | Atrophic Poison | 91.7 to 99.0% | 10 |
    | Blood Plague | 89.4 to 99.2% | 8 |
    | Overwhelmed | 84.9 to 99.0% | 14 |
    | Insidious Chill | 62.2 to 94.9% | 9 |

  - The cost of an untargetable stretch was not isolated, and the lows are not explained. A spec
    absent from a group, or a debuff not kept up, are candidates only; neither was verified.
  - The comparison stays like for like whatever the cause, because both sides are measured over
    the same span rule.
- **Row verdicts:**
  - `level` 20, `unjudged` 3, `below` 1.
  - 2 rows are shared: Mortal Wounds, on an Arms Warrior and on a Windwalker Monk.
- **`below` and the gap finding are still not exercised genuinely.**
  - The one `below` row is the Arms Warrior's Mortal Wounds, 60.48% against 83.90%. It was already
    `below` before council time joined.
  - That row is shared, so no gap finding fires.
  - Its figure checks by hand: 302.75 s on single bosses plus 198.99 s on the council, over
    829.59 s, is 60.48%.
- **"too few references" did not occur.** Its one occurrence before this change was on the Arms
  Warrior's Honed Reflexes row, and that row left the table. The debuff was on neither council boss
  at all, for us or for any of the five references. So the references' shares fell from a range of
  2.81 to 23.12% to a range of 1.50 to 11.90%, and their median from 14.40% to 7.67%. All five references still carried
  the debuff, but the median fell under the 10% floor, the rule as designed.
- **"no reference measured this boss" did not occur,** before this change or after. It stays
  unexercised live.

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

*Amended 2026-10-08, live:* the real cost is that of the first run with the feature. Its references'
death streams were not yet cached, and every other read was.

| Command | Cost |
| --- | --- |
| The one-player `analyze` | 6.58 points: `EnemyDeaths` 5 calls for 5.58, and 1.00 for the two `RateLimit` reads |
| `--all-players` | 25.30 points: `EnemyDeaths` 19 calls for 24.30, and 1.00 for the two `RateLimit` reads |
| The live proof | 31.88 points in all |

- **Per call:** one call per distinct parse reference, averaging 1.12 points on the one-player
  command and 1.28 on `--all-players`. Each figure sits somewhat above its estimate.
- **Our own side** paid nothing. Its read was a cache hit.
- **The rerun** after the deathless fix was warm, and each command spent 1.00, all of it on
  `RateLimit`. It is not the feature's cost.

## 8. Documentation, when it ships

- **The parent design.** A dated amendment to `2026-10-07-enemy-debuff-uptime-design.md` §2, saying
  council pulls are measured by this design.
- **The mplus-analysis skill.** The debuff bullet: a council's cell is coverage across its bosses.
- **The wcl-api skill.** The use of `EnemyDeaths` on references, and its live cost.
- **CLAUDE.md.** Remove "council" from "Trash, raid and council pulls are not measured yet".
