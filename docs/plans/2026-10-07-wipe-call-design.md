# The wipe call: a pull is lost at its fourth death

**Status:** approved design, not yet planned.
**Slice:** raid analysis (slice 2), with what the night page inherits from it. It touches the
raid page, the night page's pulls and rollups, and the progression and night attempt rows.

## 1. Goal

A raid leader calls a pull at four deaths. This design states that call: when a pull reaches its
fourth roster death, a wipe is **lost** from that death, and a kill is **dirty**.

On a lost wipe, two things stop reading the collapse, which no one was going to recover anyway:

- the heaviest moments of damage, and whether a group cooldown answered each;
- the death cards, which run to 14 to 21 per full wipe and bury the deaths that started it.

A dirty kill is a label and nothing else.

## 2. What already exists, and what this does not undo

- Nothing in the raid analysis cut a pull short before this design: every analyser read
  `start_ms` to `end_ms`.
- `wipeCalledTime` was null on all 19 fights measured (`2026-09-16-progression-analysis-design.md`
  §7.2), so the API cannot supply the call. It is never queried, and this design does not change
  that.
- `2026-09-26-night-defensives-pooled-design.md` §2 measured a called-wipe cut for the defensives
  finding and rejected it: the share of own defensives reading `ready` at a death showed no
  gradient by the fraction of the roster already dead. **That decision stands.** The defensives
  findings, per pull and pooled, keep every death, and §3's measurement reproduces it.
- The progression layer's first-death reading (`first_roster_death`, `collapse_seconds`, the
  first-death killing blow) is unchanged. The wipe call is a second, later anchor, not a
  replacement.

## 3. Measurement behind the rule

Measured 2026-10-07 offline on the cache, 0 points: 37 pulls of 20 players, 9 kills and 28 wipes,
from `cW38jmwdnZfbHVL4` (Heroic, 16 pulls) and `6jHcTvtB4XAMGZag` (Mythic, 21 pulls).
`6rZmAhbqxQdtTc4w` was left out, being `6jHc` logged twice. Every analyser ran as the raid
command runs it.

**Kills.** Death events per kill: 0 (4 kills), 1 (2), 2 (1), 3 (1), 5 (1). The only kill that
reaches four is `cW38` fight 27, at 442 s of 454; no other kill passes three.

**Wipes.** 26 of 28 reach a fourth death. From it to the pull's end: median 15 s, with four
slow wipes at 57, 62, 142 and 147 s. 77% of all wipe death events come after the fourth.

**Heavy moments on wipes**, by death events before the moment:

| Deaths before | Moments | Answered | Unanswered, cooldowns ready | Unanswered, none ready |
| --- | --- | --- | --- | --- |
| 0 | 18 | 18 | 0 | 0 |
| 1 to 3 | 18 | 15 | 1 | 2 |
| 4 to 7 | 4 | 1 | 2 | 1 |

Before the fourth death, 3 of 36 moments go unanswered; after it, 3 of 4. Two of the three times
`healing.spikes.unanswered` fired on a wipe came after the fourth death. The sample after the cut
is small, and that is stated, not hidden.

**Death cards on wipes.** 456 cards. Cutting at the fourth death keeps 106. Cards before and
after the cut carry about the same share of own defensives reading `ready` (0.07 against 0.11),
which agrees with the defensives precedent: the late cards add volume, not a different failure.

## 4. The rule

A new domain module, `src/wowperf/domain/analysis/wipe_call.py`:

- `WIPE_CALL_DEATHS = 4`, a fixed count at every raid size. Its docstring records §3, including
  that it was measured on 20-player pulls only. At 10 players, 4 deaths is 40% of the roster; no
  pull of another size has been measured either way.
- The count is of **roster deaths**, filtered to the pull's players as `roster_deaths` filters
  them (`progression_best.py`), so a pet or an unidentified actor dying never counts. The deaths
  are ordered by timestamp, then actor id, as `first_roster_death` orders them. A player who is
  battle-rezzed and dies again counts twice.
- `lost_at(loaded) -> Death | None`: the fourth roster death on a wipe, and `None` on a kill or on
  a wipe with fewer than four.
- `is_dirty(loaded) -> bool`: a kill with four roster deaths or more.

Slow wipes follow the rule. A pull that fights on for two minutes after its fourth death is lost
from that death. A second threshold, such as deaths inside a window, would rest on four wipes,
and the cost is stated instead: a failure after the call is not judged.

## 5. Findings

Both are emitted by `analyse_encounter` (`encounter_service.py`), on every raid pull the rule
applies to, and so on every night pull too.

- **`raid.lost`**, badge `derived`: "The pull was lost at the 4th death, 2:41 into 4:03". Its
  detail names the rule and says that heavy moments are read up to that death and death cards
  stop there. The death and its time are read from the log, but "lost" is a rule we chose, and
  the rule can be wrong: one kill in nine crossed it and won.
- **`raid.dirty_kill`**, badge `measured`: "Killed with 5 deaths". "Dirty" is defined, not
  inferred: a kill with four deaths or more.

**Heavy moments on a lost wipe.** `analyse_spikes` is handed `span = (start_ms, lost_at)` and
`combat = (span,)` in place of the whole fight. The spike module does not change: span is
already its input. Ranking, the median every window is weighed against, and the number of
moments are then all read before the call, so collapse damage neither takes a ranked slot nor
moves the median.

A consequence: a moment before the cut that ranked nowhere before may now rank, because the
median falls. That is a new verdict, and the live run must show it, not assume it. Moments after
the cut are never picked, so the page states the window it read rather than a count of moments
it left out.

**Unchanged in the findings file:** the deaths findings, the defensives findings (per pull and
pooled), consumables, interrupts, mechanics, phase cost, the attempt verdict (`wipe.cause`), pace
and kill time all read the whole pull. On a kill, nothing is cut.

## 6. The page

- **Death cards** (`build_deaths`, reached from `build_raid_report`): on a lost wipe, cards stop
  at the fourth death, and one line stands for the rest: "14 more deaths after the 4th — not
  carded". Kills keep every card. Death cards are page-only today and stay so.
- **Raid header** (`build_raid_header`): a dirty kill reads "Killed — dirty, 5 deaths". The
  header then needs the pull's deaths, not only its `Encounter`.
- **Attempt rows** (`progression_frame.py`, shared by the progression page and the night
  summary): the verdict reads "dirty kill" in place of "kill" where the pull's deaths were
  fetched. Where they were not, the row cannot tell, and keeps "kill".
- **Night page:** its pulls are built by `build_raid_report` and its rollups count the pulls' own
  findings, so it inherits the cut and the labels. Its pull labels quote the header's outcome.
- **Unchanged:** the alive-over-time chart (the whole pull, including after the call), the wipe
  opening, kill speed, and reference-kill selection. A dirty kill is still the kill its time
  measures.

## 7. Testing

**Unit tests** (`wipe_call`):

- 3 roster deaths: not lost.
- 4: lost at the fourth, in time order, with ties broken by actor id.
- A pet's death is not counted.
- A rez followed by a second death counts twice.
- A kill with 4 deaths is dirty and never lost; a kill with 3 is neither.

**Unit tests** (elsewhere):

- `analyse_encounter` hands `analyse_spikes` a span ending at the cut on a lost wipe, and the
  whole fight otherwise.
- The card fold stops at the fourth death, and its count line is right.
- The header and attempt-row labels.

**Integration:** `build_raid_report` on a lost wipe and on a dirty kill.

**End-to-end:**

- The canonical wipe (`cW38`, fight 30) carries `raid.lost`.
- The canonical kill (`cW38`, fight 2, no deaths) carries neither finding.

**Live run (the invariant).** Every state must be seen on a real log, and its frequency reported:
lost, wipe under four deaths, dirty kill, clean kill. The cache predicts 26, 2, 1 and 8 over
the 37 pulls in §3. The dirty kill occurs only on `cW38` fight 27, so the live run must include
it. The live run must also report whether any pre-cut moment newly ranks under the shortened
span.

## 8. Open naming point

Today's wipe finding is `wipe.cause` (`raid_build.py`), and the agreed ids are `raid.lost` and
`raid.dirty_kill`. `wipe.lost` would sit in the existing family. No `kill.` family exists:
`compare.kill.time` is the nearest. To settle at spec review.
