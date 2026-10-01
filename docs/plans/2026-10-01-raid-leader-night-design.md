# The night page, rebuilt for the raid leader

**Status:** approved design, not yet planned.
**Area:** `wowperf night`, and through the builders it shares, `wowperf raid --fight N` and
`wowperf progression`. It amends `docs/plans/2026-09-23-night-report-design.md` (§5, restoring
what the shipped code dropped), `docs/plans/2026-09-27-wipe-damage-pace-design.md` (§4, §7, §11,
§12: the boss lookup, councils and kills), and the raid page's wipe summary.

## 1. Why

A live night — report `6jHcTvtB4XAMGZag`, three Mythic bosses, 21 pulls — produced 732 findings
and compared nothing against anyone. Every comparison finding in its file was one of 19
`compare.pace.unavailable` notices. The page reads accordingly:

- The two kills open on "Nothing else measured". The night command draws neither the parse axis
  nor the mechanics axis, so a kill there has no comparison at all.
- Every wipe says "No verdict on why this attempt ended", because `wipe.cause` needs the
  mechanics sample and the night command does not draw it.
- Every Vashnik wipe says its fight "has no single boss", which is wrong. The fight is named
  "Vashnik the Malignant"; its boss-flagged actor is named "Vashnik". `find_boss_actor`
  (`src/wowperf/domain/comparison/pace_boss.py`) requires the two names to be equal.
- Entombed Sentinels is a real council, and pace gives up on it.
- A wipe's Summary tab leads with "18 deaths cost 25s of play" and ranks its losses in seconds.
  That is the Mythic+ frame, where time is the currency. A wipe is not a race; its question is
  how it came apart.
- The Damage tab on a wipe is one paragraph about what is absent, repeated on all twenty player
  cards, and Provenance repeats one sentence nineteen times.
- The boss summary — the one part of the page that tells a story — opens on a tab that says
  "Nothing else measured". Its substance sits in Repeats.

The night design wanted the mechanics axis kept (§4, §5, "about 15 points on fight 26"). Commit
`fe2da70` records that the shipped code dropped it: "The design's section 5 wanted the mechanics
axis kept; the shipped code does not draw it." No design argues it should stay out.

## 2. Who the page is for

The raid leader, the morning after. Their questions, in order:

1. On a boss in progression: why do our attempts end, how close are we getting, and what keeps
   repeating?
2. On a boss we killed: was the kill clean and repeatable (cleanup for farm), and how fast was it
   against other kills (kill speed)?

Each raider's own performance against top parses stays on `wowperf raid --fight N
--all-players`, an opt-in per kill. The night page does not draw it (§8).

## 3. Shape of the work

Two sub-slices, one plan each, in this order:

1. **Comparison coverage** (§4). Every boss gets a comparison against reference kills.
2. **The page** (§5). The page is rebuilt around what sub-slice 1 produces.

Data first, so the page is designed around verdicts that occur on real logs rather than
placeholders.

## 4. Sub-slice 1: every boss gets a comparison

### 4.1 The mechanics axis on the night, every pull

The night command draws the mechanics axis for every pull, kills included, exactly as
`raid --fight N` does (`cli.py`, the `raid` path around `_mechanics_sample` and `_ability_taken`).
This brings back, per pull:

- `mechanics.ability.*` — hostile abilities landing at least twice the reference kills' median
  rate per minute, or that the references never took.
- `mechanics.lethal.*` — abilities killing our players more often than they killed the
  references'.
- `wipe.cause` — execution, throughput, both, or withheld. `classify_attempt`
  (`analysis/attempt_shape.py`) reads only the sample members' durations and deaths, so it works
  unchanged once the sample exists. The `no_sample_on_the_night` notice is removed.

The reference sample is drawn once per boss and raid size and shared across that boss's pulls
through the one-day reference cache. Our own damage-taken table is one query per pull.

The pace comparison takes its reference kills from the mechanics sample's members first, as
`raid` does, followed by the rest of the board. Without a failure that is exactly the mechanics
sample; a member whose pace graph fails is refilled from the rows behind it, as the night
refills today, rather than shrinking the pace sample.

### 4.2 Finding the boss by the fight's enemies, not by name

The boss is the boss-flagged actor (`subType` "Boss", from `NPC_ACTORS_QUERY`) whose id appears
in **this fight's own** `enemyNPCs`. That field is already verified and read for reference fights
by `REFERENCE_FIGHT_QUERY`; our own fight is read through the same query. The name no longer has
to match the fight's.

`subType` "Boss" alone over-selects across a report (the `wcl-api` skill row of 2026-09-27: some
adds carry a boss frame), which is why the restriction is to the fight's own enemies. Two things
are unverified and are the plan's first task, a cheap probe on `6jHcTvtB4XAMGZag` before any
code:

- that each Vashnik fight lists exactly one boss-flagged actor among its enemies;
- where the boss-flagged "Drowned Echo" belongs, so an add with a boss frame inside a boss fight
  is found if it exists.

If the probe shows an add with a boss frame inside a single-boss fight, the tie-break is the
current rule: among the fight's boss-flagged enemies, the one named after the fight, else the one
whose name the fight's name begins with. The probe decides whether that tie-break is needed at
all; it is not built speculatively.

**Probe result, 2026-10-01.** It is needed. Each Vashnik fight lists one boss-flagged enemy,
"Vashnik". The Entombed Sentinels fights list two, Blood and Breath of Ula'tek, neither named
after the fight. But Nek'zali's fight lists three: the boss and two boss-framed adds ("Drowned
Echo", "Echo of Jawae"). The rule is therefore: the boss-flagged enemies of this fight; if
exactly one is named after the fight (equal, or its name followed by a space opens the fight's
name), that one alone; if several are, none; otherwise all of them, one being a boss under
another name and several a council. The council's two graphs came back on one grid on both
fights read.

### 4.3 Councils: the bosses' damage summed

A fight whose enemies include more than one boss-flagged actor is a council. Its pace is the sum
of the damage dealt to every one of them, on our side and on each reference's. The boss damage
graph takes one `targetId`, so a council costs one graph per boss on each side.

A reference is matched by every one of our bosses' `gameID`s appearing exactly once in its
`enemyNPCs`. A reference missing any of them is dropped with its reason, as a reference missing
the boss is dropped today.

On `cW38jmwdnZfbHVL4`'s Entombed Sentinels fights the boss-flagged enemies are Blood of Ula'tek
and Breath of Ula'tek; the add Venom Coagulation is flagged `NPC`. That report is the council's
end-to-end fixture.

> **Amended 2026-10-01.** The council's end-to-end test reads `6jHcTvtB4XAMGZag` fight 8, a
> Mythic wipe at the same council, not `cW38jmwdnZfbHVL4`'s Entombed Sentinels: on 2026-10-01
> `cW38`'s Heroic board offered no reference kill at our size of 20, so its pace withheld before
> any graph was summed.

`NO_SINGLE_BOSS` survives only for a fight whose enemies include no boss-flagged actor.

### 4.4 Kill speed

Two findings, on kills only:

- **Kill time** (`measured`). Our kill's duration against the reference kills' median and
  observed range, a median and a range and never a mean. The durations are already in the
  leaderboard rows the mechanics sample fetches (`ReferenceKillRow.duration_ms`); no new query.
- **Where the gap opened** (`derived`). The existing pace curve (`read_pace` in
  `comparison/pace_curve.py`) run on a kill: from when our cumulative boss damage sat behind the
  reference band. `read_pace` does not care whether the fight was a kill; what blocks it today is
  the kill gates in `pace.py`, `adapters/wcl/pace.py`'s callers in `cli.py`, `pace_player.py` and
  `pace_night.py`, and wording written for wipes. The projection is a wipe's question and is not
  drawn on a kill. The band's existing cut — compared only while at least three reference kills
  are still fighting — is kept and stated.

The references are top kills from the execution leaderboard, so being slower is the expected
result. Both findings say so in their detail: what they offer is where the gap opened, not that it
exists.

No design accepted or declined kill duration as a raid finding. The Mythic+ design's refusal to
compare boss kill times (`2026-09-03-mplus-postmortem-design.md` §6.4) rests on keystone levels
scaling enemy health, which a fixed raid difficulty does not do. `2026-09-27-wipe-damage-pace-
design.md` §12 left kills out because "they have the parse comparison"; on the night page they do
not, and this design amends that section.

Per-player pace on a kill is not drawn (§8).

## 5. Sub-slice 2: the page

### 5.1 Every boss opens on its summary

A boss pulled once has a summary too. With kill speed and the mechanics axis, a first-pull kill
has a story; its attempt table has one row. Progression findings that need two or more attempts
stay silent, as today, and say so as today.

### 5.2 The boss summary leads with the headline

The Summary tab opens on the outcome — killed on attempt N, or the best depth reached — then the
strongest findings in a fixed order:

1. **Kill speed**, when the boss died (§4.4).
2. **Why attempts ended** — a new boss-level rollup of the per-pull `wipe.cause` verdicts:
   how many attempts each verdict covered, with a quantifier (`every`, `most`, `about half`,
   `some`) so a narrative can echo it without a number. Withheld verdicts are counted and named as
   withheld, not dropped.
3. **What keeps over-landing** — a new boss-level rollup of `mechanics.ability.*`: an ability
   reported in more than one compared pull, with the count of pulls it appeared in and a
   quantifier. The threshold mirrors the existing `progression.repeat.*` findings.
4. **The existing repeats** — `progression.repeat.killing_blow`, `progression.repeat.first_death`,
   `progression.repeat.ability`.

Neither rollup computes anything new from the log; each counts findings its pulls already carry,
so each takes the confidence of the findings it counts. "Nothing else measured" no longer opens
the tab.

### 5.3 The attempt table

The Attempts tab keeps `build_attempt_rows`' columns (`progression_frame.py`: depth, duration,
phase, deaths) and adds:

- the wipe verdict;
- the pace state at the end of the attempt;
- the first death: player, specialisation, killing ability;
- how long the raid held after the first death (`collapse_seconds`, `progression_repeats.py`).

Everything is already in memory (`LoadedEncounter.deaths`, `_first_death_ms`, the pull's
findings); no new query. Selecting a row shows that pull's panel. The page's one inline script may
show, hide and highlight, so this stays inside the invariant `test_html_invariants.py` enforces.

### 5.4 A wipe's Summary says how it started

On a wipe, the Summary tab no longer leads with `deaths.total` or ranks losses in seconds. It
shows the first death, the chain it set off (`deaths.chain`), how long the raid held, the
`wipe.cause` verdict and the pace state. `deaths.total` and the death costs stay on the Deaths
tab. The pull builder is shared, so `raid --fight N` on a wipe changes the same way.

On a kill, the kill-speed findings open the pull's Summary.

### 5.5 Each notice once

- The parse axis's absence is stated once on the night page (`compare.parse.not_drawn`), not on
  every pull's Damage tab (`raid_build._damage_section`) or every player card
  (`players._comparison_section`). On a `raid --fight N` wipe it stays, once, on the Damage tab
  and not on each player card.
- Provenance groups identical reasons ("Fights 8–13: …"), and a reason printed in a pull's
  Provenance is not printed again at night level (today the pace notice is in both:
  `raid_build.py` and `night_build.py`).

## 6. Failures

The existing rules hold:

- A reference that fails to load is dropped and listed in Provenance with its reason.
- A comparison with no usable reference is withheld, and the reason is stated once (§5.5).
- A council whose reference fight lacks one of our bosses drops that reference.
- Nothing is silently empty: every absence names why.

## 7. Cost

Estimated at about 100 points above the 575.80 this report cost on 2026-10-01: the reference
kills per boss, one damage-taken table per pull, a second graph per council pull on each side,
and the kill-pace graphs. It is an estimate. The live run measures it, and the figure goes into
`.claude/skills/wcl-api/SKILL.md` with its date.

## 8. Out of scope

- The parse axis on the night page. It stays `raid --fight N --all-players`, per kill.
- Per-player pace on the night page, and per-player pace on kills.
- A boss-ability timeline, a phase table, or any hand-written mechanic knowledge
  (`2026-09-18-wipe-analysis-design.md` §4.2).
- Any claim that one raider caused another's death (`2026-09-16-progression-analysis-design.md`
  §2.5, §9.1), or that damage was avoidable.
- A boss-health curve; no API series exists (`2026-09-18-wipe-analysis-design.md` §8.4).

## 9. Testing and done

Test-first throughout. Unit tests cover:

- the boss lookup: a single boss, a boss whose actor name differs from the fight's, a council,
  and an add carrying a boss frame;
- both kill-speed findings, including the band cut;
- both rollups and their quantifiers, including withheld verdicts;
- the attempt table's new columns;
- each notice rendered once.

End-to-end tests stay on `cW38jmwdnZfbHVL4`: fight 2 the canonical kill, fight 30 the canonical
wipe. Its Entombed Sentinels fights are the council fixture.

> **Amended 2026-10-01.** The council's end-to-end test reads `6jHcTvtB4XAMGZag` fight 8
> (Mythic) instead, because `cW38jmwdnZfbHVL4`'s Heroic board offered no reference kill at size
> 20 on 2026-10-01; section 4.3 carries the same note.

Done means a live run of `wowperf night 6jHcTvtB4XAMGZag` reports how often each state
occurred across its 21 pulls: each `wipe.cause` verdict, pace behind / on pace / ahead, each
kill-speed reading, and the boss lookup's outcome per boss. A state that never occurs is
investigated, not accepted.
