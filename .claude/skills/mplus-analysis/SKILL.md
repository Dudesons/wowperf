---
name: mplus-analysis
description: Use when interpreting a wowperf findings file, or answering a question about what this project's Mythic+ analysis can and cannot honestly say
---

# Interpreting a Mythic+ run

## Everything is seconds

A keystone is a race. The unit that makes findings comparable is time, so every analyser that can
express a loss in seconds does, and `seconds_lost` is what `rank_findings` orders the file by.

A finding with `seconds_lost: null` is not a small finding. It is one where no honest figure
exists — a defensive never pressed, a talent the top parse takes and you do not, a completion time
withheld across a keystone-level gap. Ranking puts them last; that is a sort key, not a verdict.
Never treat `null` as zero, and never sort it as though it were.

A death's cost (`deaths.total` and its nested findings) is measured to the player's first cast at
another actor, because a respawned player casts self-only spells while running back.

## Findings are ranked, never summed

The findings file says this itself, in `findings_are_ranked_not_additive`. It is the single
easiest way to produce a confident wrong number, so it is worth restating:

- `compare.duration` is the total gap against the reference run. When it carries a figure, that
  figure already contains every other `seconds_lost` in the file. It carries none — `null` — in
  two cases: a keystone-level gap withheld the comparison, or we finished no slower than the
  reference.
- `time.gap.*` and `compare.downtime` both nest inside `time.residual`.
- `deaths.single.*`, `deaths.chain.*` and `deaths.repeat.*` nest inside `deaths.total`.
- `compare.route.skipped.*` overlaps the waste `trash.overage` already reports.

Adding any two of those together produces a number larger than the run. The report labels every
nested row "Already counted inside …" for exactly this reason, and a test holds that label set
and the warning above in step, so neither can drift from the other.

## What each confidence badge licenses you to say

Every finding carries one. It is the difference between a report that is trusted and one that is
argued with.

| Badge | What it means | What you may write |
| --- | --- | --- |
| `measured` | read from the log, or plain arithmetic over logged facts and dated constants, needing no assumption that could be wrong | "was", "cost", plain assertion |
| `derived` | reconstructed by a documented rule, or computed with a modelling choice that could be wrong | "works out to", "on this reckoning" |
| `inferred` | requires an assumption the log cannot confirm | "suggests", "looks like", never a flat claim |

Asserting an `inferred` finding as fact is the fastest way to lose a reader who knows the game
better than the tool does. Every defensives finding is `inferred`, in three different ways. The
log emits no cooldown-reset events, so a defensive that was never pressed may genuinely have been
unavailable. `defensives.ceiling.*` infers something else: a use count set against what the
cooldown allowed over the seconds the player spent alive and in combat. That arithmetic is exact,
but a defensive is pressed into incoming damage rather than on cooldown, so the ceiling is a
ceiling and not a target — the finding says so itself, and the interpretation must keep saying it.

`defensives.unused.*` is the third: the player died while an ability was, as far as cast
timestamps and a base cooldown can tell, off cooldown. It is the strongest of the three, because
it is anchored to a moment rather than to a whole run and because it only names abilities the
player cast somewhere in the run — a talent they never took can never appear. It is still a
question rather than a verdict: a defensive held for a worse moment thirty seconds later is
ordinary play. Say "had it available", never "should have pressed it".

Silence from any of the three means one of two things, and they are not the same: the player's
spec is absent from `data/defensives.toml`, which covers every specialisation, or it checked and
found nothing to say. The death cards distinguish them — "Defensives off cooldown: none" is a
check that came back empty, and no line at all is a spec nobody has entered. The findings file
cannot distinguish them, so do not read a missing `defensives.*` finding as a clean run.

## Throughput cooldowns ask about placement, not rate

`throughput.alignment.*` names cooldowns a player owned, had off cooldown when a big pack was
engaged, and did not press. It is deliberately scoped to the run's boss pulls and its three
largest trash packs, because pressing burst on cooldown is not what a keystone rewards — the
route decides how many packs are worth it. Read it as "these were the pulls that mattered and
the button was up", never as "they should press it more".

**Expect it on most runs, for most players.** A spec with five or six listed cooldowns will
almost always have left one of them unpressed on one of the six selected pulls, and several
of them are situational buttons a player casts once and correctly never again. Two to four
players named in a run is ordinary. Treat a single line as noise and a player named on every
big pull as the signal.

It also covers healing cooldowns for healing specs — Tranquility and Divine Hymn are in the
same file — so for a healer read it as "a throughput cooldown was up", not as damage.

The log records presses, not plans. A cooldown held through a big pack because a bigger one was
thirty seconds away is good play and appears here as a gap. Say so when you repeat it.

`throughput.ceiling.*` is the rate claim, and it appears **only when someone passed
`--throughput-ceiling`**. Its absence therefore means nothing at all. When it is present, it carries
the same caveat as the defensive ceiling and one more: a route, not a rotation, sets how many
windows existed.

## The two consumable claims, and which one to lead with

`consumables.never.*` says the player died and drank from a whole category at no point in the run.
Lead with this one. It is a habit rather than a coincidence, a reader can act on it without
knowing what was in anyone's bags, and it is said once however many times they died.

`consumables.unused.*` says a category the player **does** use was off cooldown at a particular
death. It only appears for a category they drank from at least once, so it is no longer the
near-universal line it was — but it is still a coincidence of timing, so treat it as the weaker of
the two.

Neither can see a bag. Both mean "none was used", never "none was carried", and the difference
matters because they want the same fix.

## Reading either of them

Both are about what a player carried rather than what their spec gives them, and both are claims
whose absence of evidence is not evidence. A consumable reaches the log only when it is drunk, so
either finding means **none was used** — never that one was in the bag. Write "no potion was used";
do not write that they had one.

Two silences mean nothing at all rather than something good. A death early enough that the
category's window reaches back before the log begins is not judged, because casts are fetched per
fight and a potion drunk before the pull is invisible. And combat and mana potions are not tracked
at all — they stopped sharing a cooldown with health potions in patch 9.0, so their absence from
the data is deliberate and carries no meaning.

## Why damage goes unranked

Warcraft Logs deliberately exports no per-boss Mythic+ damage metric, because the unit of
optimisation is the whole dungeon. Ranking individual throughput in a key invites the behaviour
this tool exists to coach out, so this project does not rank damage.

What `analysis/players.py` does instead is state damage taken **per ability, against the median
of the players who took at least one hit of that same ability** — with the analyser's own caveat
attached: it is a difference, not a mistake, and whether any single hit was avoidable is not
something the log records. The figure is unmitigated damage, before absorbs, and the finding is
badged `derived`.

Do not turn that into "avoidable damage". The report deliberately refuses the phrase.

A tank taking many multiples of the group median from melee is the job, not a mistake, so tanks
are left out of the damage-against-median comparison altogether: as the only member of their role
in a keystone they have no honest median to be measured against. Which specialisations tank is
read from `data/roles.toml`, which is maintained by hand and carries the date it was checked, and
a specialisation absent from it is treated as damage — so a tank the table does not know would
still appear. The finding's evidence names the class and spec beside the figure, which is what
lets a reader spot that case.

An Augmentation Evoker on either roster raises `compare.confound.augmentation`: while it stands,
treat every per-player damage figure in the report as approximate.

## Activity is cast-based here, and Warcraft Logs' is not

Warcraft Logs computes Activity from damage events, so damage-over-time ticks mask real downtime.
This project counts successful cast events instead — the API's own `Casts` events, as `wcl-api`
records — and only those inside a pull window, so waiting between packs is charged to the route
rather than to a player. The two numbers will not agree, and ours is the one that answers "were
you doing something".

The measure is deliberately coarse: the analyser charges one second per cast and calls that a
floor on time spent acting, not a simulation of a rotation. The percentage it reports is that
floor over pull time on that reckoning, which is why the finding is `derived` rather than
`measured`. A finding only appears below 60% — silence means above the threshold, not perfect
play.

## The confounds the comparison declares rather than corrects

A reference run is a different group on a different key. The comparison states its confounds
instead of adjusting for them, because adjusting would invent a number:

- **Group composition.** Which packs can be held, which mechanics are trivial, and how much damage
  a route can absorb all change with the roster.
- **Item level.** The only gear difference the tool can see. Tier, trinkets and embellishments are
  uncorrected, and equal item level no longer implies a similar stat profile.
- **Keystone level.** Enemy health scales about 10% a level and compounds, so anything shaped like
  a duration means something different on each side of a gap. `compare.duration` is what this
  gates: at a level gap it becomes "Completion times are not compared", carries no seconds, and
  `compare.confound.keystone_level` states the gap beside it. Pull composition, pull order, packs
  skipped, deaths, missed interrupts and between-pull downtime do not depend on how much health a
  mob had, so they are still compared. A reference more than one level away is never offered at
  all.
- **Pull segmentation.** Warcraft Logs records a chain of packs fought without a break as one
  pull. Alignment matches a pull to every separate pull it covers, and the route summary says how
  many of our trash pulls found a counterpart. When fewer than half did, `compare.route.unaligned`
  appears and no `compare.route.skipped.*` or `compare.route.extra.*` finding does: the two logs
  cut the route differently, and an unmatched pull is not a skipped pack. Say that, not "the
  reference skipped it".
- **The spell rate comparison is scoped to boss pulls**, the one stretch where two runs fought the
  same encounter, so it says nothing about trash. The "never cast it" finding is the exception: it
  checks the whole of our run, boss and trash, before claiming a spell is absent.
- **The parse reference is a different character.** A spell missing from our run is "either a
  talent not taken or a button not pressed; the log cannot tell which" — a prompt to check a
  build, not a verdict on it. The uptime comparison matches by exact ability, so a gap can also
  mean a different item of the same kind, or gear this player does not own.

When a comparison was withheld, the report says why in the tool's own words — a
`compare.*.unavailable` finding, or `compare.confound.keystone_level`. Repeat that reason; do not
invent a better-sounding one.

## Reading the file

`out/<code>-<fight>.findings.json` carries the run's metadata (`report_code`, `fight_id`,
`dungeon_name`, `keystone_level`, `keystone_time_seconds`, `in_time`, `player`), a `comparison`
block holding both reference runs when they were fetched, the `findings_are_ranked_not_additive`
warning, and the findings themselves — each with an `id`, a `title`, a `detail`, a `confidence`, a
`seconds_lost`, an `evidence` list and a `pull_index`.

`comparison.compared` is `false` and both references are `null` in two different situations, and
the findings tell them apart. Under `--no-compare` the comparison never ran, so no `compare.*`
finding exists at all. When a leaderboard returned nothing, `compare.speed.unavailable` or
`compare.parse.unavailable` is there to say so. Both differ again from a comparison that ran and
was withheld, which leaves its findings in place with `seconds_lost: null` and the reason in the
`detail`. The route, tempo, duration and confound findings hang off the speed reference; spells,
talents and uptime hang off the parse reference. One can be absent while the other is not.

The `title` is prose written for a reader. The `id` is a machine identifier. When you want to
point a reader at a finding, echo its title — they can find it on the page. An id means nothing to
them.

The page groups the findings under six tabs, so when you point a reader at one, you can also say
where to look. Summary holds the three decomposition rows, up to five pointers at the biggest
losses, the aligned timeline and anything no tab claimed. Route & tempo holds the gaps, the
downtime, the skipped and extra packs, the trash rates and the confounds. Deaths holds each death
card and the death costs, defensives and consumables beneath them. Interrupts holds the kicks.
Players holds the cards and, beneath them, the per-player defensive and throughput rates.
Provenance holds the sources, everything withheld, and the badge legend. Without scripting, the
same sections stack in that order.
