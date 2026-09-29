# The healer's side of each death

**Status:** approved design, 2026-09-29; built 2026-09-29, and exercised live (§6, "Live").
**Area:** slice 4 (healer analysis), its second sub-slice. It adds a "Healers" group to every
death card: the Mythic+ page (`analyze`), the raid page (`raid`), and every `night` pull drawn
at the death-card tier or above. It adds no finding and no query.

## 1. Goal

For each death, show what the group's other healers were doing in the dying player's last ten
seconds -- where their casts were aimed, when one last reached this player -- and which of their
group healing cooldowns the log shows ready, pressed, or out of reach.

It describes; it does not judge. `docs/plans/2026-09-29-healing-cooldowns-design.md` §5 ruled
that the judgement of a heavy moment is the group's, never one healer's, because healers plan
rotations the log cannot see. A card showing that a healer spent the run-up on the tank is
useful on its own, and it claims nothing about the plan.

Sub-slice 1 is `docs/plans/2026-09-29-healing-cooldowns-design.md`; its §2 names this one.

## 2. What exists, and what does not

- The death card (`domain/report/deaths.py` `build_deaths`, view model `DeathCard` in
  `domain/report/model.py`) already carries: the killing blow; a timeline of the run-up's hits,
  heals, absorbs and the player's own casts, heals named by caster; a health curve; how the
  player came back; and three availability groups -- "Defensives", "Consumables", "Teammates'
  externals" -- each ability in one of six states (`domain/analysis/recap.py` `availability_at`,
  `state_of`).
- Nothing on the card tells a healer from any other teammate (`recap.py` and `deaths.py` never
  read `Roles`), and nothing reads what a healer was casting.
- **No new query.** Every friendly actor's casts are fetched for the whole fight wherever a
  death card is drawn (`CASTS_QUERY`, unfiltered by source: `load` at the `full` profile,
  `load_encounter`, and `load_night_attempts` at the death-card and deep rungs). Each
  `CastEvent` carries `target_id`, `None` for an untargeted cast: the API writes `-1` and
  `ingest.py` `_target_of` maps it (verified in `.claude/skills/wcl-api/SKILL.md`, 2026-09-06).
- The healing query is scoped to the dying player (`HEALING_QUERY`, `targetID`), so what landed
  on anyone else is not fetched. Casts say where a healer aimed, not what healed whom.

## 3. The healer lines

- **Who:** every roster player whose specialisation `data/roles.toml` calls a healer, except the
  dying player -- a dying healer's own buttons are under "Defensives", and this group is about
  the others. With no other healer present (a keystone's only healer dying), the group holds one
  line: "No other healer was in the group."
- **A roster player the log names no specialisation for** reads as damage, not as unknown, so a
  healer among them would otherwise drop out of the group silently; the note counts them instead,
  either as the whole note (no other healer found) or appended after the other sentences (at
  least one found), and the dying player's own empty specialisation is never counted.
- **The window:** the card's own run-up, `RUN_UP_SECONDS` (10) before the death
  (`domain/analysis/defensives.py`).
- **Each line:**
  - **Alive, or dead when this player died.** Dead means a death before this one with no
    resurrection and no cast since -- sub-slice 1's rule (`spikes.py` `_dead_at`), since a cast
    is the only sign of life a player who released and ran back leaves.
  - **Casts in the run-up, counted by target:** at this player; at another player; at an enemy
    or another non-player; untargeted. A target is a player when its id is a roster actor id.
  - **The last cast at this player:** "N s before this death", or "none in the last 10
    seconds".
  - **The healer's group healing cooldowns** (§4).
- **Figures:** counts and seconds only. No healing amount appears.
- **The group's detail states the limits:** a cast's target is where it was aimed, not
  everyone it healed -- a smart heal or a heal over time can reach this player with no cast
  aimed at them; a cast at an enemy can still heal (Discipline's Atonement); the heals that
  landed on this player are in the card's timeline, named by caster.
- **Badges:** the cast counts and the last cast are `measured`, counted straight off the cast
  stream; the cooldown states are `derived`.

## 4. The cooldown states

- **Which:** the healer's `group = true` entries in `data/throughput_cooldowns.toml` -- the
  fifteen reviewed for sub-slice 1 (Tranquility, Healing Tide Totem, Revival, Divine Hymn,
  Rewind, Avenging Wrath and the rest). Externals stay in "Teammates' externals"; nothing is
  listed twice.
- **When:** judged as the run-up opens, the card's rule: availability is judged from when the
  damage began.
- **Each is one of:**
  - **pressed in the run-up:** "pressed 3 s before this death", whatever its target -- a group
    cooldown covers everyone;
  - **ready:** only what `ready_at()` (`domain/analysis/throughput.py`) calls ready -- pressed
    somewhere in the log read, not within its base cooldown before the run-up opened, and its
    base cooldown window wholly inside the log;
  - **pressed earlier, within its base cooldown:** "pressed 1:12 before this death, within its
    base cooldown of 3:00" -- timed back from the death like the rest of the card, so a
    keystone's pre-pull press needs no wording of its own;
  - **not judged:** its base cooldown reaches before the fight's first second, or the run's;
  - **never pressed in the log read:** not listed, as in sub-slice 1. When none of a healer's
    cooldowns was ever pressed, the line says so in one clause rather than going silent.
- **A dead healer's line** reads "dead when this player died" and lists no cooldown state: a
  dead player presses nothing.
- **Never** "on cooldown", "should", or a verdict on one healer. The detail says why: talents
  shorten cooldowns and are not modelled, a second charge reads as not ready, the tool cannot
  see the plan, and ready is understated, never invented.
- **One rule, two surfaces.** `spikes.py` `judge` holds the per-answer rule inline. It is
  extracted into one function returning the state and the press it rests on; the Mechanics
  tab words it by clock, the card by time before the death. Sub-slice 1's output stays
  byte-identical. A heavy moment and a death at the same instant then cannot disagree on
  whether Tranquility was ready -- the card's own `state_of` would, since it calls an ability
  ready in a fight's first minutes where `ready_at` declines (§7).

## 5. On the page

- A "Healers" group below "Teammates' externals" on every death card.
- The builder makes each line's text and badge; the template loops and decides nothing.
- Holders are named as sub-slice 1 names them: "Restoration Druid, Emberkin".
- A night pull at `--no-deaths` draws no death card, so nothing is missing there.
- **Goldens move, deliberately:** each golden whose fixture holds a death and a healer other
  than the dying player gains the group. Each is regenerated on purpose and its diff read line
  by line: the new group and nothing else.

## 6. Testing

- **Unit, test first, plain fixtures, no network:** who is a healer; the dying healer excluded;
  the "no other healer" line; each target category, with `None`, an enemy id and a roster id;
  the last cast at this player, and "none"; dead by sub-slice 1's rule, and back by a
  resurrection or by a cast; each cooldown state; a keystone press before the first pull timed
  back from the death; no "on cooldown", no "should", no healing amount. The fixture clock sits
  on a non-zero origin by default (`.claude/lessons.md`, 2026-09-29). Every test shown able to
  fail by breaking the line it guards.
- **The extraction:** sub-slice 1's tests pass unchanged, and the raid golden does not move
  from it.
- **Builder and render:** the group's text asserted from the view model, never hand-typed; no
  `>None<`; the badge renders.
- **Live, not optional** (warm caches, `--no-compare`): `raid` on `cW38jmwdnZfbHVL4` fights 2
  and 30, `analyze` on `6Kx1P9GbNXrcLdHa`. A script that prints no name counts, across every
  death: lines alive and dead; each target category; "none in the last 10 seconds"; each
  cooldown state; the "no other healer" line. A state that never occurs is recorded as open.

**Live** (2026-09-29, three commands, 3.00 points of 3600 as the commands printed them):

| Command | Points | Deaths |
| --- | --- | --- |
| `raid cW38jmwdnZfbHVL4 --fight 2 --no-compare` | 1.00 | 0 |
| `raid cW38jmwdnZfbHVL4 --fight 30 --no-compare` | 1.00 | 21 |
| `analyze 6Kx1P9GbNXrcLdHa --fight 36 --no-compare` | 1.00 | 4 |

- **Fight 2, the canonical kill, drew no death card at all**: a clean kill has no death to build
  a Healers group under, so every count below rests on the other two fights.
- **Totals across the three runs, 25 deaths, 84 other-healer lines:** 1 card read "No other
  healer was in the group." Of the 84 lines, 39 read alive and 45 read dead. Casts in the run-up,
  by where they were aimed: 11 at this player, 74 at self, 229 at other players, 9 at
  non-players, 155 untargeted. 40 lines cast something in the window but never at this player; 34
  cast nothing in the window at all. Of the cooldown rows a line carried: 6 read pressed, 4 read
  ready, 56 read within their base cooldown, 0 read unjudged, 0 read dead.
- **Early wipes, to reach the states the three runs missed** (2026-09-29, fights 32, 8, 29 and 31
  of `cW38jmwdnZfbHVL4`, 88 to 110 seconds each, counted from the cards `build_deaths` draws with
  the repository's data files; warm cache, no query fetched): 79 deaths, 79 cards, 300
  other-healer lines, none reading "No other healer". Cooldown rows: 23 pressed, 226 within their
  base cooldown, 1 unjudged (fight 8), 0 dead, 0 ready. No line carried either note: every other
  healer pressed at least one of their group healing cooldowns in every one of these fights.
- **Seen live since:** the "unjudged" cooldown state, once, on fight 8.
- **Open, never seen live:** the "dead" cooldown state (an ability's holder dead as the run-up
  opened, though alive again by the death itself); and the line noting that none of a healer's
  group healing cooldowns was pressed -- on a raid the healers press one before a wipe ends, so it
  wants a report where a healer never does.
- **Unreachable with today's data files:** the line noting that none is listed for a healer's
  specialisation at all. Every healer specialisation `data/roles.toml` names -- Druid/Restoration,
  Evoker/Preservation, Monk/Mistweaver, Paladin/Holy, Priest/Discipline, Priest/Holy,
  Shaman/Restoration -- lists at least one `group = true` entry in `data/throughput_cooldowns.toml`
  (checked 2026-09-29), so no healer's specialisation can reach this note today. It is still
  reachable if a spec's `group` entries changed to none, or a new healer specialisation were
  added with none.
- The three HTML pages carried no `>None<`, `>null<`, `>nan<`, `{{` or `{%`.

## 7. Out of scope, and follow-ups

- **The card's externals overclaim ready early in a fight.** `state_of` reads a teammate's
  external as ready whenever it was not pressed within its base cooldown before the death, in
  a fight's first minutes too, though a press before the log began is invisible. A reset check
  on `cW38jmwdnZfbHVL4`'s fifteen repeated boss pulls (2026-09-29, recorded in sub-slice 1 §5)
  found cooldowns carried over between pulls rather than resetting, so an early "ready" can be
  false. Bringing the externals under the not-judged rule changes every existing card and its
  goldens, and is a follow-up of its own.
- **The triage reading** -- whether the healers were busy elsewhere -- reconsidered once a live
  run shows how often cast targets mislead.
- **Naming the other targets** of a healer's casts.
- Healing throughput, overhealing, mana, and any per-healer verdict.
