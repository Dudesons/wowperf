# Healing cooldowns against the group's heaviest moments

**Status:** approved design, 2026-09-29; planned in `docs/plans/2026-09-29-healing-cooldowns-plan.md`;
built 2026-09-29, and exercised live (§8, "Live").
**Area:** slice 4 (healer analysis), its first sub-slice. It adds one analyser and two findings
to the Mythic+ page (`analyze`) and the raid page (`raid`, and therefore every `night` pull).

## 1. Goal

When the group took its heaviest damage, say whether it answered with a healing or group-wide
defensive cooldown, who pressed what, and what sat ready unpressed.

The repository's only statement of slice 4's intent is the README roadmap's "Healing asks
different questions and fails in different ways". Everything healing-related today serves the
dying player's recap -- healing received, teammates' externals, resurrections, healing
consumables -- and nothing reads what a healer did. `docs/plans/2026-09-13-raid-analysis-design.md`
already rules that printing `hps` ranks "is not healer analysis". This sub-slice judges a **decision**, not an
output, which is the README's own rule: "It is about decisions, not throughput."

## 2. Slice 4, cut into sub-slices

1. **Healing cooldowns against the heaviest moments.** This document.
2. **The healer's side of each death**: what the healers were casting in a player's last seconds,
   on whom, and which of their answers were ready. Not designed.
3. Healing throughput against the same specialisation, and mana, are named and deliberately
   left undesigned: healing done depends on how much damage the group took, and overhealing and
   absorbs muddy it further (§9).

## 3. Data

**No new query.** Every command that loads events already fetches, for the whole run or fight:

- **Damage taken**, as raw `events(dataType: DamageTaken, hostilityType: Friendlies)`
  (`DAMAGE_TAKEN_QUERY`, `repository.py` `_load` and `load_encounter`), held as
  `DamageTakenEvent`. Fields verified in `.claude/skills/wcl-api/SKILL.md` (2026-09-04) include
  `amount`, `absorbed`, `targetID` and `timestamp`, and `overkill` is verified there too, present
  only on a lethal blow. In the domain model `health_damage` is the log's `amount` (what reached
  health), `absorbed` what a shield took, and `overkill` the damage past death (amended
  2026-09-29).
- **Casts**, for every actor (`CASTS_QUERY`, unfiltered by source), in `analyze`'s `parse` and
  `full` profiles and in `raid`'s `load_encounter`. `analyze`'s `speed` profile fetches no casts;
  the judgement is then withheld with a notice (§6).

A `graph(dataType: DamageTaken)` would give the curve directly but is not verified, costs points
on every fight, and saves only a few lines of summing over events already held.

## 4. The heaviest moments

- **Counted:** every damage-taken event whose target is a roster player,
  `health_damage + absorbed - overkill` -- what healers had to answer: what reached health, what a
  shield took, less what no heal could have saved. Pets and NPCs are excluded.
- **The curve:** 1-second buckets from the start of the fight, or of the run on a keystone.
- **A moment** is a rolling 5-second window over those buckets (`SPIKE_WINDOW_SECONDS = 5`), so a
  burst straddling a fixed boundary is not halved.
- **How many:** one per started 3 minutes of fight or run time (`SECONDS_PER_SPIKE = 180`): a
  5-minute boss fight ranks 2, a 9-minute one 3, a 30-minute key 10. 180 seconds is the cooldown
  of almost every answer in §5 -- Tranquility, Healing Tide Totem, Revival, Power Word: Barrier,
  Spirit Link Totem, Rallying Cry -- so a group can meet about one heavy moment per cycle.
- **Picked greedily:** the heaviest window, then the heaviest window not overlapping one already
  picked, until the count is reached or no window clears the floor.
- **The floor:** a window ranks only if it is at least twice the fight's median 5-second window
  (`SPIKE_FLOOR = 2.0`), so a gentle fight's heaviest moment is not presented as a crisis. The 2
  is a chosen number, not a measured one: one named constant, stated on the page, and the live
  run (§8) reports how often it cut a window.
- **Scope:** each raid boss fight on its own -- a `raid` fight, each `night` pull. A keystone
  across its whole run, since healers carry cooldowns from pull to pull; the quiet stretches
  between pulls never rank.

## 5. The answers, and each moment's state

**The answer set** (amended 2026-09-29: the healer blocks of `throughput_cooldowns.toml` also
hold abilities that answer nobody's damage -- Touch of Death, Power Infusion, Holy Word:
Chastise -- so "every cooldown under a healer spec" would count them):
- Every entry of `data/throughput_cooldowns.toml`, under a specialisation that `data/roles.toml`
  calls a healer, that carries a new `group = true` marker.
- Every entry of `data/externals.toml` that carries the same marker: Power Word: Barrier, Spirit
  Link Totem and Rallying Cry are already in that file. Anti-Magic Zone, Darkness, Aura Mastery
  and any other group-wide defensive are added only with their spell id confirmed from a real
  log and their cooldown from a primary source, and the file's verified date updated -- never
  guessed. An ability stays listed in one file only, the house rule both files already state.
- Each marker is set by hand, per ability; the plan lists the proposed set for review.
- A player holds an answer when their class and specialisation list it.

**Pressed in answer:** a cast of the answer falling between 10 seconds before the window opens
and the window's close (`ANSWER_LEAD_SECONDS = 10`). Casting ahead of a known heavy moment is
correct play, and the effects in this set last roughly 8 to 10 seconds. A named constant, stated
on the page.

**Ready:** `ready_at()` (`domain/analysis/throughput.py`) says the answer was owned and off
cooldown when the window opened. Three consequences, all in the safe direction:
- `ready_at()` counts an ability as owned only if it was cast somewhere in the fight or run, so
  a cooldown never pressed all fight is invisible -- whether it was talented cannot be told.
- Charges are ignored, so a second charge reads as not ready.
- Cooldowns are base values; no talent reduction is modelled, as everywhere in this repository.

A holder **dead** when the window opens is excluded: a dead player presses nothing, and counting
their cooldown against the group would be false. Dead means a death before the window with no
resurrection and no cast of theirs since: a cast is the only sign of life a player who released
and ran back leaves.

**Early in a fight nothing can be shown ready** (amended 2026-09-29). `ready_at()` does not
judge a cooldown whose base cooldown reaches back before the fight's first second, since a press
before the log began is invisible; for a three-minute answer that is the fight's first three
minutes. A check on `cW38jmwdnZfbHVL4`'s fifteen repeated boss pulls found no sign of cooldowns
resetting between pulls: the earliest re-press of the same answer in a later pull came at 0.85
of its base cooldown, and within one pull presses came as early as 0.50 (talent reductions), so
the gaps are cooldown reductions carried over, not resets. The rule stands, and the page says
"not judged" rather than inventing a state.

**Each moment is one of three states.**
- **Answered:** at least one answer pressed; every press is listed with its holder.
- **Unanswered, cooldowns ready:** nothing pressed while at least one answer sat ready. The only
  state held against the group.
- **Unanswered, no answer shown ready:** stated as a fact, not a fault, with the reason for each
  answer the group held: its holder was dead; it was pressed at a given clock, within its base
  cooldown; or it was not judged because its base cooldown reaches before the first second. The
  page never says a cooldown was "on cooldown": talents shorten some, so it states the press it
  saw and leaves the talent to the reader.

**The judgement is the group's.** Healers plan cooldown rotations together, so one holding while
another spends is usually correct; a per-healer judgement would call planned rotations mistakes
the tool cannot see. The page still names every holder at each moment.

**Figures:** no raw damage number anywhere. A moment is placed by its clock and rank ("the
heaviest 5 seconds of the fight, 0:42 to 0:47") and weighed as a multiple of the fight's median
5-second window ("3.4 times the median"), the measure the floor already uses, which reads the
same on a Normal fight as on a Mythic one.

## 6. Findings

**`healing.spikes`, `derived`** -- one per fight or run whenever at least one window cleared the
floor.
- Title: a count of the three states, e.g. "3 heaviest moments: 2 answered, 1 unanswered while
  cooldowns were ready".
- Evidence: one line per moment in clock order, e.g. "0:42 to 0:47, the heaviest (3.4 times the
  median): answered by Tranquility (Restoration Druid, *name*) and Rallying Cry (Arms Warrior,
  *name*)".

**`healing.spikes.unanswered`, `inferred`** -- only when at least one moment was unanswered while
an answer sat ready.
- Title: e.g. "1 of 3 heaviest moments went unanswered while group cooldowns were ready".
- Evidence: one line per such moment, each ready answer and its holder.
- Detail states the limits: the group may have planned that moment for someone else's cooldown;
  cooldowns are base values; a second charge reads as not ready; a cooldown never pressed all
  fight is invisible; the 10-second lead and the floor of 2 are chosen numbers.
- No time lost: it never becomes a Summary pointer. Pricing a held cooldown in seconds would be
  dishonest.
- `inferred`, as `throughput.alignment` is: "should have pressed" is a judgement.

**Notices** (`healing.spikes.unavailable`, `measured`), in place of silence:
- No window cleared the floor: "No moment of this fight was heavy enough to rank."
- Nobody in the group holds any answer.
- Casts were not fetched (`analyze`'s speed profile), so no answer can be read.

## 7. On the page

- **Raid:** the **Mechanics** tab, which already shows what hit the raid. Every `night` pull's
  page is the raid page, so it gains this unchanged.
- **Mythic+:** the **Deaths** tab, among its findings below the death cards (amended 2026-09-29:
  findings are placed by id prefix into `death_rows`, which render there; a block above the
  cards would need a field and a template block of its own for two findings). A keystone page
  has no Mechanics tab, and heavy moments are what deaths come from.
- A per-boss line across a night's pulls, as the pace boss line does, is left out.
- A dedicated Healing tab on both pages is the alternative, held until healer analysis has more
  than two findings to show.

## 8. Testing

- **Unit, test first, plain fixtures, no network:** the 1-second curve and the rolling window;
  roster players only; `health_damage + absorbed - overkill`; greedy non-overlap; the count rule; the floor and its
  median; the answer set from both data files; the 10-second lead (an 11th second does not
  count); a holder dead at the window's open excluded; a cooldown never pressed never ready;
  each state and each notice's wording pinned; no raw damage figure in any title or evidence
  line. Every test shown able to fail by breaking the line it guards.
- **Builder and render:** the findings on the raid page's Mechanics tab and on the Mythic+
  page's Deaths tab, asserted by the rendered text taken from the findings; the notices render;
  no `>None<`.
- **Goldens move, deliberately.** This adds a block to both pages, so the raid and Mythic+
  goldens change wherever their fixtures produce a moment. They are regenerated on purpose and
  the diff read line by line: the new block and nothing else.
- **Data:** every `group = true` marker and every added group-wide defensive has its spell id
  confirmed from a real log's own ability names; the file's verified date updated.
- **Live, not optional** (about 1 to 5 points on warm caches): `night` on `cW38jmwdnZfbHVL4`,
  `raid` on its fights 2 and 30, `analyze` on `6Kx1P9GbNXrcLdHa`. A script that prints no name
  counts each state -- answered, unanswered with cooldowns ready, unanswered with nothing ready,
  windows cut by the floor, each notice. A state that never occurs is recorded as open.

**Live** (2026-09-29, four commands, 59.47 points of 3600 as the commands printed them):

| Command | Points | Moments wanted / ranked / cut by the floor | States and notices |
| --- | --- | --- | --- |
| `night cW38jmwdnZfbHVL4 --no-deaths` | 6.49 | -- | 16 of 16 pulls read the no-casts notice |
| `raid cW38jmwdnZfbHVL4 --fight 2` | 50.98 | 2 / 2 / 0 | 2 answered |
| `raid cW38jmwdnZfbHVL4 --fight 30 --no-compare` | 1.00 | 3 / 3 / 0 | 3 answered |
| `analyze 6Kx1P9GbNXrcLdHa --fight 36 --no-compare` | 1.00 | 11 / 11 / 0 | 8 unanswered with cooldowns ready, 3 unanswered with no answer shown ready |

- **Fight 2's 50.98 points were all comparison references**, none of them this judgement's: the
  one-day reference tier had expired for that fight's sample, so the parse axis re-drew five
  reference kills (`Talents` 5 calls for 11.40, `Fights` 5 for 10.04, `Abilities`, `Casts`,
  `DamageDoneTargets` 5 each for 5.00, `AuraTable` 4 for 4.00, `RaidCharacterRankings` 2 for
  2.02) and the mechanics axis its execution board and tables (`AbilityTakenTable` 5 for 6.51,
  `EncounterKillRankings` 1 for 1.01). The fight's own streams were warm. The two later runs took
  `--no-compare` for that reason; the analysed fight or run is loaded in full either way, casts
  included, so the judgement reads the same data.
- **The night pulls were read at the `--no-deaths` tier, which fetches no casts**, so every pull
  drew the no-casts notice, a true sentence. What the judgement says on a night pull at the
  death-card tier, which does fetch casts, is **open**.
- **Totals across the three judged runs:** 16 moments wanted, 16 ranked, 0 cut by the floor;
  5 answered, 8 unanswered with cooldowns ready, 3 unanswered with no answer shown ready. Of the
  reasons on those 3: 2 "pressed at ..., within its base cooldown", 1 "not judged", 0 "its holder
  was dead". One `healing.spikes.unanswered` fired, on the keystone, carrying the 8.
- **Every raid moment was answered** (5 of 5, both fights), so "not judged" did not dominate the
  raid moments here: an answered moment lists its presses and no reasons, and no raid moment
  reached the reasons at all. The reset check's prediction -- that early raid moments would read
  "not judged" -- was therefore neither confirmed nor refuted by these two fights.
- **The keystone's eight "ready" moments rest on one answer.** The group's only healer was a Holy
  Paladin, and nobody else held a marked answer, so Avenging Wrath (base 120 seconds, pressed 4
  times across a 1832-second run window) was the whole answer set. With a two-minute base
  cooldown pressed four times in half an hour, it sat ready at most heavy moments; the finding is
  `inferred` and its detail says the group may have planned otherwise. The run's earliest ranked
  moment's only nearby press landed within a second after that window closed, which the 10-second lead, reaching
  backwards only, does not count: that moment read "not judged".
- **Open, never seen live:** the "its holder was dead" reason; the no-answer, below-the-floor
  and zero-damage notices; a window cut by the floor (0 of 16 wanted); a moment weighed against a
  median window of zero; and every state on a `night` pull at the death-card tier.
- The four HTML pages carried no `>None<`, `>null<`, `>nan<`, `{{` or `{%`.

## 9. Out of scope

- Any per-healer judgement.
- The healer's side of each death (sub-slice 2).
- Healing throughput, overhealing, and mana.
- A per-boss line across a night's pulls.
- Reading real effect durations from auras.
- Talent cooldown reductions, and dispels.
