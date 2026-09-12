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

- `compare.duration` is the total gap against the median of the sample. It does not contain the
  other figures below: the median prices one quantity — the sample as a whole — while every other
  `seconds_lost` figure is priced against a particular run's own route, so the numbers overlap
  without either containing the other. It carries none — `null` — in two cases: a keystone-level
  gap withheld the comparison, or we finished no slower than the sample.
- `time.gap.*` and `compare.downtime` both nest inside `time.residual`.
- `deaths.single.*`, `deaths.chain.*` and `deaths.repeat.*` nest inside `deaths.total`.
- `compare.route.skipped.*` overlaps the waste `trash.overage` already reports.

Summing a nested pair double-counts the piece they share. Summing `compare.duration` with anything
else is a different mistake: the two figures are priced on different bases and were never meant to
combine into a total at all. The report labels every nested row "Already counted inside …" for
exactly this reason, and a test holds that label set and the warning above in step, so neither can
drift from the other.

## The quantifier is the narrative's only count

The narrative states no numbers at all — `analyze --narrative` refuses a file that contains a
single digit. An aggregate finding carries a `quantifier` for exactly this: one of `every`,
`most`, `about half`, `some`, `none`, or empty, already computed from the sample so the narrative
can echo it rather than calculate one of its own.

Use only the quantifier a finding was given, and only on that finding. Reaching for "most" because
a ratio in the evidence looks high, or carrying one finding's word onto a different finding, is
reading a number off the page and writing it back in words — the exact thing the digit ban exists
to stop.

An empty quantifier means the finding is not an aggregate over a sample at all — one reference's
own figure, say — and there is no "how many agreed" to have an opinion about. Say nothing.

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

## What a death recap can honestly say

Each death card carries a timeline of the last ten seconds, the state of every saving tool, and a
return line. Three of its claims need care.

**The health column is reconstructed**, badged `derived`. The log states a player's health only on
their own casts; between readings each hit is subtracted and each heal added, and the next reading
replaces the running value. Write "was around", never a flat figure, and expect the column to be
empty for a player who never cast in the window.

**A remaining cooldown is an upper bound.** "At most 14 s left" means the base cooldown says so;
a talent or a reset could have made it ready. "Ready, for at least 4 s" is the mirror: a lower
bound. "Not seen this run" is a fact about the log, not about the player — a talent not taken
looks the same. An external marked ready is a fact about a teammate's cooldown; the report draws
no finding from it, and neither should you.

**"Released" is a reading, not an event.** A resurrection is logged; a release is not. The card
says "released" when no resurrection preceded the player's first action against an enemy, and
gives that action as the return time, which is the same anchor the death cost uses. It is badged
`derived` for that reason. "Not seen acting again this run" means exactly that.

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

The references are five other groups on other keys. The comparison states its confounds
instead of adjusting for them, because adjusting would invent a number:

- **Group composition.** Which packs can be held, which mechanics are trivial, and how much damage
  a route can absorb all change with the roster.
- **Item level.** The only gear difference the tool can see. Tier, trinkets and embellishments are
  uncorrected, and equal item level no longer implies a similar stat profile.
- **Keystone level.** Enemy health scales about 10% a level and compounds, so anything shaped like
  a duration means something different on each side of a gap. `compare.duration` is what this
  gates: with fewer than three references at our own keystone level it becomes "Completion times
  are not compared", carries no seconds, and `compare.confound.keystone_level` counts how many sat
  elsewhere. Pull composition, pull order, packs skipped, deaths, missed interrupts and
  between-pull downtime do not depend on how much health a mob had, so they are still compared. A
  reference more than one level away is never offered at all.
- **Pull segmentation.** Warcraft Logs records a chain of packs fought without a break as one
  pull. It also cuts a single engagement in two, leaving a pull of a few milliseconds — usually
  the tail of a boss pull, holding one of that pull's own enemies — and it records pulls with no
  enemies at all. Neither is a pack a route decision could have taken or left. `Pull.is_a_pack`
  is the test and `MIN_PACK_SECONDS` its floor, measured 2026-09-11 against 98 cached pulls where
  six ran under a second, the longest of those 0.525s, and the next shortest ran 6.770s. Neither
  shape is ever named as skipped, drawn as skipped on the timeline, counted in the match rate or
  in the share that decides eligibility, or ranked among the packs that bought fewest enemy
  forces. That last one carries a reading worth having: a `trash.pull.*` row saying a pull bought
  no forces at all is now always a real pack that paid nothing, which is this analyser at its
  strongest rather than an artefact scoring zero because it was never a pack. Some figures
  deliberately do still count every pull
  the log recorded: the two route lengths, and the "in common", "only ours" and "only theirs"
  evidence beneath them, here and on `compare.route.unaligned`. So one summary can read "2 of 2
  trash packs found a counterpart" above "2 only ours" with neither line wrong, and can say our
  route was ten pulls and eight trash packs in the same breath. Alignment matches a pull to every
  separate pull it covers, so "in common" counts pulls of ours that found a counterpart and never
  the pairs. A reference whose route lined up with fewer than half of our packs is dropped from
  the skipped-pack counts outright, and `compare.route.summary` states how many were left to
  price a skip against — which is why route
  rows can carry a smaller denominator than tempo rows on the same page. No
  `compare.route.unaligned` finding marks that exclusion; read the summary's own count, and never
  read a reference's silence as agreement. `compare.route.unaligned` survives only below the
  floor, where one reference is stated pairwise: there it means the two logs cut the route
  differently, and an unmatched pull is not a skipped pack. Say that, not "the reference skipped
  it".
- **The spell rate comparison is scoped to boss pulls**, the one stretch where two runs fought the
  same encounter, so it says nothing about trash. The "never cast it" finding is the exception: it
  checks the whole of our run, boss and trash, before claiming a spell is absent.
- **The parse references are five other characters.** A spell missing from our run is "either a
  talent not taken or a button not pressed; the log cannot tell which" — a prompt to check a
  build, not a verdict on it. The uptime comparison matches by exact ability, so a gap can still
  mean a different item of the same kind. On the aggregate path it no longer means gear one
  player happens to own: an uptime gap is reported only where at least three of the parses
  carried that aura, which a single proc or a single trinket cannot reach. Below that floor, the
  comparison falls back to a single reference stated pairwise, where a gap can still mean gear
  this player does not own. `compare.talents.<slug>` is the one row still drawn from a single
  reference — the top-ranked parse, whose report its evidence links to.

When a comparison was withheld, the report says why in the tool's own words — a
`compare.*.unavailable` finding, or `compare.confound.keystone_level`. Repeat that reason; do not
invent a better-sounding one.

## Reading the file

`out/<code>-<fight>.findings.json` carries the run's metadata (`report_code`, `fight_id`,
`dungeon_name`, `keystone_level`, `keystone_time_seconds`, `in_time`, `player`), a `comparison`
block, the `findings_are_ranked_not_additive` warning, and the findings themselves — each with an
`id`, a `title`, a `detail`, a `confidence`, a `seconds_lost`, an `evidence` list, a `facts` list,
a `pull_index`, an `ability_id`, an `ability_name`, a `quantifier` and a `player_slug`. Every
finding carries the last of those, and it is empty on any finding that is a statement about the
run rather than about one player: a route, a tempo or a confound belongs to nobody.

`facts` holds the same figures the `evidence` states in prose, as a `label`, a `value` and an
optional `confidence` of the line's own — what the page lays out in the hover panel at the
finding's ability name. It says nothing `evidence` does not; read either, and never both as two
measurements.

`comparison.references` lists every candidate the sample considered, loaded or not, each carrying
its `axis` (`speed` or `parse`), the `report_code`, `fight_id` and `keystone_level` that name it,
a `url` to the report, whether it `loaded`, the `reason` it was not used if it was not, whether
everything it needed was already `from_cache`, and the player whose comparison weighed it — twice
over, as a `player_slug` to match on and a `player_name` spelled the way the page spells it. Both
are empty on the speed axis, which is drawn once for the run. `comparison.players` lists the
players compared, subject first, by that same slug. `sample_size.speed` gives how many references
loaded for the run, and `sample_size.parse` how many loaded for each of those players, keyed by
their slug. A player absent from that mapping was never compared. A player present with a zero
was compared and drew nothing, for either of two reasons the count itself does not separate: the
leaderboard for their specialisation returned nothing, or the log records no specialisation for
them at all, so no leaderboard could be asked for one. Their own
`compare.parse.unavailable.<slug>` finding says which. None of these counts is the denominator of
any one finding: eligibility is decided per finding — our own keystone level for a duration, a
route that lined up for a skipped pack, aura data for an uptime — so the "4 of 5" in a title is
the only count that describes what that finding was drawn from.

`comparison.compared` is a statement about the run rather than about the subject: it is `true`
when the speed sample loaded, or when any one compared player's parse sample did. Under
`--all-players` a teammate's sample is enough on its own, so a run whose subject drew nothing
still reports `true`. For the subject's own axis read `sample_size.parse[<subject slug>]`, the
first entry of `comparison.players`. A `false` therefore means neither axis loaded for anybody,
and that arises in two different situations the findings tell apart. Under `--no-compare` the
comparison never ran, so no `compare.*` finding exists at all and `references` is empty.
Otherwise `compare.speed.unavailable`, and a `compare.parse.unavailable.<slug>` for each compared
player, are there to say so, and `references` may still list candidates that were tried and
failed to load. Both differ again from a comparison that ran and was withheld, which leaves its
findings in place with `seconds_lost: null` and the reason in the `detail`. The route, tempo,
duration and confound findings hang off the speed sample; spells, talents and uptime hang off the
parse sample. One axis can be absent while the other is not, and the two are named differently:
every id in the parse family ends `.<slug>`, because each is a statement about one player, while
the speed family — `compare.speed.unavailable` included — carries no suffix at all.

The `title` is prose written for a reader. The `id` is a machine identifier. When you want to
point a reader at a finding, echo its title — they can find it on the page. An id means nothing to
them. An aggregate title carries its denominator, and so carries digits the narrative may not
write; name such a finding by its `quantifier` and its subject instead of echoing the title.

The page groups the findings under six tabs, so when you point a reader at one, you can also say
where to look. Summary holds the three decomposition rows, up to five pointers at the biggest
losses, the aligned timeline and anything no tab claimed. Route & tempo holds the gaps, the
downtime, the skipped and extra packs, the trash rates and the confounds. Deaths holds each death
card and the death costs, defensives and consumables beneath them. Interrupts holds the kicks.
Players holds the cards and, beneath them, the per-player defensive and throughput rates.
Provenance holds the sources, everything withheld, and the badge legend. Without scripting, the
same sections stack in that order.
