# Defensives up at a player's deaths, pooled across a boss's pulls

**Status:** approved design, planned in docs/plans/2026-09-26-night-defensives-pooled-plan.md.
**Slice:** the third piece of spec B, the family `docs/plans/2026-09-26-night-boss-summary-design.md`
§2 left as "deaths per player across pulls; availability pooled across pulls". It lands in the
night page's boss summary that design built, beside the first-death killing blow
(`docs/plans/2026-09-26-first-death-killing-blow-design.md`).

## 1. Goal

One new finding per named player, `progression.repeat.ready.<slug>`: which of the player's own
defensives were up, unpressed, at their deaths across a boss's pulls. "Icebound Fortitude up at 4
of 9 deaths." The claim is availability; the player's deaths are its denominator.

## 2. Why availability, and why not a death count

Two readings were weighed and set aside.

- **Deaths per player across pulls** ("died in 5 of 7 pulls"). Measured 2026-09-26 on
  `cW38jmwdnZfbHVL4` (warm cache, 1 point): every wipe held 16 to 21 roster deaths for a roster of
  20, almost all in the pull's final 30 seconds. On a wipe everyone dies, so the tally names the
  whole roster and says nothing.
- **Availability pooled raid-wide, naming nobody.** Safe, and tells no one what to change.

Named per player, availability is the sentence a player can act on next week. The lead chose it,
naming players, as the per-pull death cards already do.

**Every death counts, late wipe deaths included.** The fear was that deaths after a wipe is
called would inflate "up at N of M": nobody presses a defensive on a called wipe. The same
measurement does not bear it out. The share of own-defensive rows reading `ready` on the death
cards, bucketed by the fraction of the roster already dead:

| Already dead | Deaths | Ready share of own rows | Deaths with one ready |
| --- | --- | --- | --- |
| under 10% | 24 | 0.12 | 7 of 24 |
| 10% to 25% | 30 | 0.06 | 3 of 30 |
| 25% to 50% | 45 | 0.12 | 12 of 45 |
| 50% and over | 87 | 0.11 | 26 of 87 |

No gradient, so a roster-fraction cut has no measurement behind it. By time before the pull's
end the share falls rather than rises: 0.20 more than 60 seconds out (15 deaths, mostly on kills,
too few to set a threshold on), 0.10 in the final 30 seconds (166 deaths). Pile-up deaths are not
flush with unpressed defensives. The measurement read the death cards' `ready` state; this finding
uses the stricter `defensives_up_at` rule (§4), so its counts sit at or below it.

## 3. Constraint: default tier only, nothing new fetched

- The rule reads each pull's `casts`, which the night fetches at the default and `--deep` tiers
  and not at `--no-deaths` (`repository.py`, `load_night_attempts`). No aura table is needed.
- No new query, stream, JSON field, view model or template. The finding joins each boss's
  summary findings.
- The standalone `wowperf progression` command never runs it: that page stays player-free.

## 4. The finding

**The rule it pools.** `analyse_defensives_at_death` (`defensives.py:103`) already emits
`defensives.unused.<slug>` on every raid pull, from `defensives_up_at` (`defensives.py:56`): an
ability counts at a death only if the player cast it somewhere in that pull -- so a talent they
never took is never held against them -- and did not cast it anywhere in the last base cooldown
plus the run-up. Every uncertainty (charges, resets, talented cooldowns) resolves toward saying
nothing.

**Judged pull by pull.** Each pull is judged on its own casts, and the summary adds the
judgements up. It is therefore exactly the sum of the pull rows beneath it and never contradicts
one, and it stays right when a raider swaps talents between pulls. Judging ownership across the
whole night -- cast on any pull, owned on every pull -- was set aside: a talent dropped after pull
2 would read as available and unpressed on pull 5, the false accusation the per-pull rule exists
to prevent.

**What it reads.** Every drawn pull of a boss with a summary (two or more drawn pulls,
`MIN_PULLS_FOR_SUMMARY`), in `attempts_with_events` order; every roster death on it, kills
included; the dying player's own defensives from `defensives.for_spec`. Players are matched
across pulls by `actor_id`, stable within one report. A death matching no roster player (a pet)
is skipped. A spec absent from the data file produces nothing -- not the same claim as a spec
that had nothing up.

**What it counts, per player and ability.**
- *Count:* the player's deaths at which `defensives_up_at` lists the ability.
- *Denominator:* the player's deaths on pulls where they cast that ability at least once. On any
  other pull the rule cannot say whether they owned it, so those deaths are unknown, not "not
  up". Each ability carries its own denominator.

*Amended 2026-09-29:* a death whose window reaches back before its own pull's first second is
left out of both the count and the denominator: a cooldown carries over between pulls, so that
death is unknown, not "not up". See `2026-09-29-not-judged-before-the-log-design.md`.

**When a player is named.** At least one ability up at two or more of their deaths, on at least
two different pulls. Two deaths inside one pull (after a battle resurrection) are a claim that
pull's own `defensives.unused` row already makes; this finding exists to say it kept happening.
Within a player, abilities are ordered by count, most first, then by name. Every qualifying
player is named: there is no cap, because stopping at some number would hide the next player for
no reason the page could state.

**Shape.**
- Id `progression.repeat.ready.<base>`, where `<base>` is the player's slug, or `slug.actor_id`
  when two roster players share a slug -- the disambiguation `defensives.unused` uses, lifted into
  one helper both call so the two cannot drift.
- One ability qualifying: title `"<player>: <ability> up at <n> of <m> deaths"`, with
  `ability_id` and `ability_name` set so the row draws the icon.
- Several: title `"<player>: <k> defensives up at more than one death"`, each ability's line in
  `evidence`, no `ability_id`.
- Evidence also carries the player's class and spec, as `defensives.unused` does.
- Confidence `inferred`: availability is rebuilt from cast timestamps against a base cooldown
  from a hand-maintained data file, and the log records no cooldown state to check it against.
- Detail says: judged pull by pull from the player's own casts against base cooldowns; late wipe
  deaths are included, and the measured ready share does not rise in the pile-up; a defensive is
  pressed into damage rather than on cooldown, so this is a question to ask, not a mistake to fix.
- `player_slug` is left empty: the summary carries no player cards to link to, and each pull's
  cards sit under their own `f{fight_id}-` scope.

## 5. Where it lives and how it is wired

- `repeat_defensives_up(series: LoadedProgression, defensives: Defensives) -> list[Finding]` in
  `src/wowperf/domain/analysis/defensives.py`, beside the finding it pools. Pure; no I/O.
- `cli.py:1912` builds each boss's summary findings as
  `rank_raid_findings(analyse_progression(boss))`, with `defensives` loaded at :1901. The new call
  joins that list only when `death_cards` is on: at `--no-deaths` there is no casts stream, and
  calling it would imply a check that never ran. The plan confirms the night's existing
  `--no-deaths` disclosure reaches the reader of a summary, and adds one line where it does not.
  `METHOD_NO_ANATOMY` is unchanged.
- Placement: the existing `progression.repeat.` prefix in `PROGRESSION_PLACEMENTS` sends it to the
  Repeats tab. Severity: the `progression` family `SEVERITY_BY_FAMILY` already covers.
- `analyse_progression` is unchanged.

## 6. Edge cases

- A player absent from some pulls (benched, swapped in): only pulls with them on the roster count.
- Two players reducing to one slug (`Bríala`, `Briala`): two distinct ids by `slug.actor_id`.
- A death off the roster: skipped, no spec, no abilities.
- A spec missing from the data file: nothing emitted.
- A kill's deaths count; a `--deep` pull counts like a trimmed one -- both hold casts.
- A player who died on one pull only: never named.
- A talent cast on pull 1 and not on pull 2: counts on pull 1 only, and pull 2's deaths leave that
  ability's denominator.

## 7. Testing

Every test must be shown able to fail against the line it guards.

**Unit** (`tests/domain/analysis/test_defensives_at_death.py`, where `defensives_up_at`'s own
tests live; sanctioned names only):
- one ability up at two deaths on two pulls fires, with title, `ability_id` and counts;
- two such deaths inside one pull are withheld;
- the denominator leaves out pulls where the ability was never cast;
- several qualifying abilities give the several-abilities title and no `ability_id`;
- ordering by count then name, with fixtures whose insertion order cannot satisfy it;
- a player absent from a pull; the slug collision gives two ids; a spec missing from the data
  file emits nothing;
- a talent cast on pull 1 but not pull 2 does not count on pull 2 (the pull-by-pull ruling);
- confidence `inferred`; `player_slug` empty.

**Integration:** the ledger places `progression.repeat.ready.` on `repeat_rows`; every fired
finding's family is in `SEVERITY_BY_FAMILY`; the night builder carries it into
`BossSection.summary`; the CLI adds it with death cards on and not at `--no-deaths`.

**Golden:** the night golden's fixtures carry no casts, so it is expected not to move; the plan
checks that rather than assuming it, and pins the rendered row with one hand-built finding if no
fixture fires it.

**End to end** (`tests/e2e/test_night_e2e.py`): shape only -- each count at least 2 and at most
its denominator, each denominator at most the boss's roster deaths, confidence `inferred`. No
assertion message prints a player name. The whole-night test in that file runs `--no-deaths`,
where this finding is never computed, so a check there could only pass vacuously. A separate
test, `test_defensives_up_are_pooled_across_one_bosss_pulls`, loads the one summary boss the
live read below measured firing -- night index 7, the 7-pull boss -- at the default tier, and
asserts the shape there. One cold run cost 195.44 points of 3600 (2026-09-26), about 28 a pull.

**Live:** `wowperf night cW38jmwdnZfbHVL4` over the warm cache. Read the JSON, never the HTML,
and report per summary boss, by index and never by name: how many players were named, the
count and denominator spread, and whether the one-ability and several-ability titles each
occurred. The one-ability, icon-drawing state went unseen live in the killing-blow slice; this is
where to look for it.

Measured 2026-09-26, over the warm cache for 1.00 point (the two `RateLimit` reads):

| Night index | Pulls | Named | One-ability | Several-ability | Counts | Denominators | `defensives.unused.` rows across its pulls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2 | 0 | 0 | 0 | -- | -- | 1 |
| 6 | 2 | 0 | 0 | 0 | -- | -- | 6 |
| 7 | 7 | 8 | 4 | 4 | 2 to 4 | 3 to 8 | 32 |

Both title states occurred, the one-ability state four times. Each several-ability finding named
two abilities, twelve evidence lines in all. On index 7 exactly eight players hold a pull row on
two or more pulls, and they are the eight named, so the pooled finding fires nowhere a pull row
does not stand beneath it twice. The two 2-pull bosses name nobody because no ability was up at
a death on both of their pulls: on index 1 one player died on both pulls and one ability was up
at one death; on index 6 four players died on both, and nine abilities were up at a death, each
on one pull only.

## 8. Out of scope

- Teammates' externals and consumables at a death.
- Deaths-per-player tallies (§2).
- Ranking or blaming players; any claim that a death was survivable.
- The standalone progression page.
