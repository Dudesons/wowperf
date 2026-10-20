---
name: analyzing-a-run
description: Use when given a Warcraft Logs URL to analyse — a Mythic+ key, a raid boss fight, every attempt at one boss, or a character's recent keys — runs the tool, interprets the findings, and hands back a finished report
---

# Analysing a run

You are given a Warcraft Logs URL. You hand back one HTML file and say what it found.

## Before the first run

Only on a clone that has never been run. Both checks are cheap and both stay passed, so skip
them once you have seen the tool work in this directory.

- **Dependencies.** Run `uv sync` if `.venv/` is absent. `uv` is the only toolchain here; there
  is no pip and no hand-managed virtualenv.
- **Credentials.** The tool reads `WCL_CLIENT_ID` and `WCL_CLIENT_SECRET` from the environment,
  or from a `.env` in the directory the command runs from. If that file is absent, copy
  `.env.example` to `.env` and ask the person to paste in the two values; they create a client of
  their own at <https://www.warcraftlogs.com/api/clients/>. It takes a minute and is free.

**Never read, echo, print or commit those two values**, and never put them in a command line.
Confirm the file has them by whether the tool works, not by opening it.

If the tool reports missing credentials, this is the reason, and the message names the file to
copy. Walk the person through it rather than working around it — there is no way to analyse a run
without an API client of their own.

A run is analysable only if the report is public or unlisted. A report the owner set to private
needs a Warcraft Logs login this project does not implement; say so plainly rather than retrying.

## The workflow

1. **Run the tool.**

   ```bash
   uv run wowperf analyze <url>
   ```

   Add `--player NAME` when the person named someone other than the report's owner; if the name is
   not in the roster the tool prints the roster it does have. It is repeatable, and the first name
   given is the subject: whose card opens the Players tab, and who the narrative is about. Add
   `--all-players` when they asked about the group rather than one player — every player then gets
   their own parse comparison, and the one named by `--player` is still the subject. Each compared
   player draws a parse sample of their own, so a whole roster multiplies the parse half of the
   fetch; players sharing a specialisation share the leaderboard query, and any reference already
   fetched is served from the cache. Add `--no-compare` only if they asked
   for the run in isolation; the comparison is the most useful half of the report.
   Add `--throughput-ceiling` only when the person asks how often a burst cooldown was pressed
   against what its cooldown allowed; it is off by default because a route, not a rotation,
   decides how many windows there were (`mplus-analysis`, "Throughput cooldowns ask about
   placement, not rate"). `--fight N` picks one keystone out of a report holding several,
   `--out DIR` moves the two output files, and `--cache-dir DIR` moves the response cache;
   none of the three changes what the report says.

2. **Read `out/<code>-<fight>.findings.json`.** The command prints the path, and the path of the
   HTML beside it. Read the JSON, never the HTML. That is a project invariant, not a preference:
   the findings file is what you interpret, and the page is not yours to parse. The page also
   carries detail the JSON does not — the timeline, the death run-ups, the per-player roster — so
   anything you say has to trace to the JSON alone.

3. **Read the `mplus-analysis` skill before forming an opinion.** It carries what the badges
   license you to say, why findings are never summed, and the confounds the comparison declares.

4. **Write the narrative** to `out/<code>-<fight>.narrative.md`. See below for what it must and
   must not contain.

5. **Re-run with the narrative.** Repeat step 1's command *exactly* — same URL, every `--player`
   in the same order, same `--all-players`, same `--no-compare`, same `--fight` if you used one —
   and add only `--narrative`.

   ```bash
   uv run wowperf analyze <url> --narrative out/<code>-<fight>.narrative.md
   ```

   Only then is every response served from the cache written in step 1, and reference entries
   live a day, so a second run the same day spends no quota beyond the two rate-limit reads. Drop
   a flag and you change the
   subject: without step 1's `--player` the comparison is fetched for a different specialisation
   and a different actor, which are different cache keys and so live queries; without its
   `--no-compare` both references are fetched outright, the roughly-28-point path. The reader
   would also get a page about someone else, or sections the narrative was never written about.

6. **Hand over the HTML path.**

7. **Say the conclusion in chat too.** Nobody should have to open a file to learn what the tool
   found.

## The narrative

**It states no numbers.** Not one digit. The command reads the file and refuses it before it
fetches anything, naming every offending line.

That is not a formatting rule. Every figure on the page already sits in a section that owns it,
badged and sourced, directly below the narrative. A number repeated up there is a second, unbadged
claim competing with the first.

The rule is "state no quantities", and the check only catches numerals. "You lost three minutes to
travel" would pass and is still wrong — write the meaning, and let the ledger carry the figure.
What is banned is a quantity the report measures: seconds, counts of pulls or deaths, percentages,
item levels. Ordinary English that counts nothing measured — "both", "each", "either" — is prose,
not a figure.

**Shape.** Three to six sentences. Lead with what dominated and what *kind* of problem it is. Say
what to change. Hedge where the finding is inferred.

**Echo finding titles, never ids.** A title is prose a reader can scan down the page and find;
`compare.route.skipped.2` means nothing to them. One exception: an aggregate title states its
denominator — "4 of 5 fast runs skipped the pack at pull 7" — and the digit ban forbids echoing
that. Name such a finding by the `quantifier` the findings file gave it and its subject: "most of
the fast runs skipped a pack you spent time on".

**It renders as plain text.** Escaped and pre-wrapped, not Markdown. Asterisks arrive as asterisks.

### Four things it must never do

1. **Restate the ledger in words.** The ledger already says it, with figures, better.
2. **Add figures up.** The findings file explains why in `findings_are_ranked_not_additive`.
3. **Assert an `inferred` finding as fact.**
4. **Give advice that traces to no finding at all.**

### What good looks like

> Your losses are route, not execution. The largest figure on this page is time spent outside
> pulls, and every one of the biggest ranked losses beneath it is a gap between packs — the group
> was travelling or waiting, not fighting. Underneath that, you pulled packs most of the fast runs
> skipped, which is why the trash overage and the skipped-pack findings both appear: the same
> detour, reported from either side.
>
> Deaths barely register beside it, and nothing in the damage findings suggests a mechanical
> problem worth fixing before the route is.
>
> Treat the missing-talent finding as a prompt rather than a verdict — the spell comparison runs on
> boss pulls only, and the parses it counts belong to other characters on other keys.

## The `raid` command

A raid boss fight is `wowperf raid <url>`, a sibling of `analyze` and not a mode of it. It takes
`--fight`, `--player`, `--all-players`, `--no-compare`, `--cache-dir` and `--out` — the same shapes
`analyze` offers, minus `--throughput-ceiling` and `--narrative`, which a boss fight has no pulls
or ceiling to support. `--player` and `--all-players` choose the report's subject and who else is
named in `comparison.players`, exactly as they do for `analyze`; the mechanics comparison itself
is drawn once for the whole encounter, never per player, so naming more players widens who the
parse axis compares, not what the mechanics axis measures. `--no-compare` skips both axes and
analyses the fight in isolation. A wipe withholds every finding that reads a completed-kill
leaderboard — Warcraft Logs ranks kills alone — and both the findings file and the page say so
rather than going quiet. It writes `<code>-<fight>.findings.json` and `<code>-<fight>.html`,
exactly as `analyze` does.

## The `progression` command

Every attempt at one boss is `wowperf progression <url> [--boss ID] [--difficulty N]`,
a sibling of `analyze` and `raid`, not a mode of either. It reads every fight in the report in one
query and reports where a night's attempts sat against each other — never against another report,
since a night's attempts are compared only to one another and no external reference is drawn.
`--boss` is required whenever the report holds more than one boss, since nothing else picks one
out; an explicit `--boss` with no `--difficulty` takes the difficulty of that boss's own first
fight in the report. `--cache-dir` and `--out` move the response cache and the findings file, the
same shapes `analyze` and `raid` offer. `--player`, `--all-players`, `--no-compare` and
`--narrative` do not apply here and are not offered, because this command draws no comparison
sample and writes no narrative-bearing page. It writes `<code>-<encounter>.progression.json` and
`<code>-<encounter>.progression.html`, a five-tab page — Summary, Attempts, Repeats, Best attempt,
Provenance — carrying the night's shape and deliberately not any one attempt's anatomy. A finding
that wants one names the `wowperf raid --fight N` that renders it.

## The `night` command

Every boss and every pull one report holds is `wowperf night <url> [--deep FIGHT]...
[--no-deaths] [--no-compare] [--difficulty N] [--cache-dir DIR] [--out DIR]`, the fourth sibling of
`analyze`, `raid` and `progression`, not a mode of any of them, and the widest of the four: `raid`
reads one pull, `progression` one boss's pulls, this one every boss and every pull the report
holds. There is no `--fight`, because covering every fight is the point.

It draws no parse axis — the per-player comparison `raid` draws for a single kill. The parse axis
is per player per boss, and across a whole report it would cost an order of magnitude more than
everything else here put together, so `--player` and `--all-players` do not apply and are not
offered; there is no per-player reference for them to widen. The page states that absence once,
under Findings about the night, as a `compare.parse.not_drawn` row naming the families it leaves
out — damage against the board, damage by target, casts a minute, talents, buff uptime, the
percentile — rather than leaving them silently missing or repeating it on every pull and every
player card. That row is on the page only: `<code>.night.json` does not carry it, so a reading of
the findings file finds no such finding.
`wowperf raid --fight N` is what draws the parse axis, for one kill; on a wipe `raid` withholds it
too.
`--narrative` is not offered either, for the reason `raid` and `progression` do not take it: this
command writes no narrative-bearing page.

Everything else `raid --fight N` compares for a pull, this draws for every pull, kills included, on
by default: the mechanics axis — what hit and killed the raid against the execution leaderboard's
reference kills — and the damage pace against those kills on every pull, and the kill time on each
kill. A wipe's verdict on why it ended (`wipe.cause`) is read against the same reference kills, as
on `raid`. One reference sample per boss and raid size serves every pull at that boss, shared
through the one-day reference cache; our own damage-taken table is one query per pull. Two or more
compared wipes at one boss also add one line to that boss's Attempts tab, counting how many ended
behind the kills' pace. `--no-compare` skips every comparison and analyses every pull in isolation.

Every pull's spell-and-talent section and every player card is therefore empty, and the page says
why once, in that `compare.parse.not_drawn` row, rather than on each of them. Its wording follows the night:
read with `--no-compare` it says nothing was compared against other kills, and each wipe's verdict
notice says no reference kills were drawn; read compared, it says no parse comparison is drawn and
names what the night does compare instead — what hit and killed the raid, each attempt's damage
pace, each kill's time. A pull's Damage tab with no row of its own points to that finding, and to
the pull's Provenance where its pace was withheld, instead of restating either. `raid --fight N`
states it itself, once: on a wipe, as the Damage tab's withheld reason or, where other rows open
that tab, as a note on it — never on each card. `raid --no-compare` is the same, kill or wipe: the
Damage tab says no reference was fetched, the Provenance says it once for the spell and talent
comparison, and no player card repeats it.

What a pull costs is chosen per pull, on three rungs: `--no-deaths` draws no death card at all,
the cheapest tier a pull can be read at; left unset, the default trims every card to what each
player had at the moment of death; and `--deep FIGHT`, repeatable, buys back a named pull's whole
death anatomy — its run-up timeline and its health curve — priced per pull rather than per night.
`--deep` and `--no-deaths` contradict each other and are refused together, naming both.
`--difficulty` takes a difficulty id and skips any boss the report holds only at another one,
defaulting per boss to that boss's own first fight in the report. `--cache-dir` and `--out` move
the response cache and the output files, the same shapes the other three offer.

It writes `<code>.night.json` and `<code>.night.html` — no fight or encounter id in either name,
because the whole report is what `--out` writes for. The page draws every pull with the same
seven panels `raid` draws for one — Summary, Damage, Mechanics, Deaths, Interrupts, Players,
Provenance — behind two dropdowns, a boss and then a pull within it.

Every boss with at least one drawn pull opens on a summary before any pull: the page `wowperf
progression` draws for that boss, built from the same findings the night's JSON writes under it.
It opens on a headline, the outcome — killed on attempt N, or no kill and how far the deepest
attempt got, as a percentage of boss health or of encounter progress. Then come the lead rows, in
this order and each only where it fires: kill speed (`progression.lead.kill_speed`, a kill's time
and pace, on a boss that died), why the wipes ended (`progression.lead.verdicts`), what kept
landing that no reference kill took (`progression.lead.never_taken`), and what kept landing harder
than it did for the reference kills (`progression.lead.overlanding`), both counted across the
compared pulls. Under them, "What kept repeating" points at the Repeats tab's killing-blow,
first-death and ability cards, and any finding no tab claimed closes the panel. A boss drawn once
has the same summary; its cluster finding is the median of one attempt, and its movement finding
says the night is not compared.

The Attempts tab's table has one row per attempt: the number, how deep it got, how long it ran,
where it ended, and its deaths; then, on a compared night only, the wipe's verdict and its last
pace reading, which names the clock the comparison stopped at where the reference kills' band ran
out before the attempt did; then the first death (who, as what, to which ability) and how long the raid held after
it. On the night page a row's number opens that pull. The standalone `wowperf progression` page
has the first death and the hold but no verdict or pace column, and its rows open nothing.

A wipe's pull Summary opens on its verdict, then on how it started: the first death, how long the
raid held, and a pointer to that death's card. The pace line follows — ended behind, on or ahead of
the reference kills' pace, or the same stated at the clock where the comparison stopped when the
band ran out before the wipe did — and then the alive chart. It does not lead with the death count
or rank losses in seconds; those stay on the Deaths tab, and `raid --fight N` on a wipe reads the
same. A kill's pull Summary opens on kill speed, pointers to the kill time and the damage pace,
wherever either was compared; read with `--no-compare`, or where neither comparison drew a
reference kill, it has no kill speed to open on and starts at the alive chart.

A wipe that reached its fourth roster death carries `wipe.lost` (derived): the pull is read as
lost from that death, its death cards stop there with one line counting the rest, and its heaviest
moments are read only up to it. A kill with four roster deaths or more carries `raid.dirty_kill`
(measured) and reads "dirty" in its header; nothing on a kill is cut. The attempt rows read
"dirty kill" only where the pull's deaths were fetched, and keep "kill" otherwise.

The night's Provenance groups the pulls that failed to load by reason, one line per reason naming
every fight it kept out, and does not repeat a pull's withheld pace notice, which stays in that
pull's own Provenance.

A pull drawn at less than the
deep tier still has its full death anatomy on hand elsewhere: `--deep` buys it back here for a
named pull, or `wowperf raid --fight N` draws it for that one pull on its own.

## The `character` command

One character's recent Mythic+ runs, read together, is `wowperf character <character-url> [--zone ID]
[--spec NAME] [--narrative FILE] [--cache-dir DIR] [--out DIR]`, the fifth sibling of `analyze`,
`raid`, `progression` and `night`. The URL is a Warcraft Logs character page,
`https://www.warcraftlogs.com/character/<region>/<realm>/<name>`, not a report. It writes one page
stating what repeats across the character's runs, and every run it read also gets the findings file
and page `analyze` would have written.

**The zone.** It comes from the URL's `?zone=<id>`, or from `--zone`, which wins. With neither the
command stops before any request and says where the id is: the number after `zone=` in the
character page's address once a Mythic+ season is selected there. It never guesses the season. A
raid zone is refused, since its rankings are not keys, and a character Warcraft Logs does not know,
or one who has hidden their rankings, stops it the same way, naming the cause.

**Which runs.** One per dungeon of the zone, for one specialisation: the most recent ranked run
with a public log at the character's highest keystone level in that dungeon or one below it, timed
or not. A dungeon with no such run is left out and listed with the reason on the page and in
`character.json`. The specialisation is the one with the most ranked runs; `--spec NAME` names
another, and a name the character has no runs for stops the command and lists the ones it has.
`--spec` swaps the specialisation; it never adds one, since a direction counted across two
specialisations would compare one rotation with another. A second run with another `--spec` replaces
`character.json` and `character.html` in the same directory, while the run pages survive, being named
by report code.

**Not offered.** `--player`, `--all-players`, `--no-compare`, `--fight` and `--throughput-ceiling`
do not exist here. The subject is the character, so there is no one else to name. The comparison is
what the patterns read, so it cannot be skipped. The runs are chosen by the rule above, so no fight
is picked. The throughput ceiling is a per-run question the character page does not ask.

**What it writes.** Everything goes under `<out>/<region>-<realm>-<name>/`, the region and
realm lower-cased and percent-decoded from the URL, the name case-folded: `character.json` and `character.html`, and beside them each
run's `<code>-<fight>.findings.json` and `<code>-<fight>.html`, which the page's Runs tab links to.
Read `character.json`, never the HTML, as with every other command. It holds the character, what
was asked for, the chosen runs, the dungeons left out, the runs that failed with their reasons, the
chosen numbers the patterns use, the findings and the group ledger.

**Three kinds of statement.** The page opens, after any narrative, on the consistent directions: a
measure that sat on the same side of the top parses in every run that judged it. Then the repeated
judgements: a judgement the per-run analysis made in at least half the loaded runs, and in at least
three. Then, on its own Group tab, a ledger of the four group comparisons every run carries,
counted and given no verdict. `mplus-analysis`, "Reading a character page", says what each one
licenses. Fewer than six loaded runs withholds the directions, and the file says so in a finding
rather than lowering the bar.

**The narrative.** The same two steps as `analyze`, with a different file:

1. Run the command once without `--narrative`, then read `<out>/<region>-<realm>-<name>/character.json`
   and `mplus-analysis`.
2. Write the narrative with no digits to `<out>/<region>-<realm>-<name>/character.narrative.md`, then
   repeat the same command with the same `--zone` and `--spec` if you used them, and add only
   `--narrative`. A narrative containing a digit is refused before anything is fetched. Name an
   aggregate finding by its `quantifier` and its subject, never by the "N of M" in its title.

The second run is served from the cache: each run's own data is kept for good and the run list and
reference runs live a day.

**Cost.** Measured 2026-10-14: 1090.57 points for eight dungeons read cold, about 136 for each
dungeon, of which the two selection queries are 9.01 in all. A warm run is served from the cache.
That is nearly a third of the hourly 3600, so say so before reading a second character in the same
hour. The command closes with the usual breakdown by operation.

**When runs fail.** A run that fails to load for a reason of its own is listed on the Runs tab with
its reason, printed as a warning, and the page counts only what loaded; fewer runs shrink the page
and can withhold the directions. A spent budget is not a run's failure: it stops the command with
the cause and writes no character page, because every later run would fail the same way and a page
shrunk by it would describe the budget, not the character. A disk or cache error stops it likewise.
Nothing is deleted by a stop, so what was fetched stays cached and a second run resumes almost
free.

## When it goes wrong

- **No credentials.** The tool needs `WCL_CLIENT_ID` and `WCL_CLIENT_SECRET` in the environment,
  and says so by name when they are missing. Ask the person to set them; never read them from a
  file and never print them.
- **Not a completed keystone.** The URL must point at a Mythic+ run that finished. A report with
  no keystone fight, a depleted or abandoned key, or a fight id that is not one, each fails with a
  message saying which. A report holding several keys fails asking for `--fight`, since neither
  `--fight` nor a fight number in the URL picked one out.
- **A reference could not be fetched.** One candidate failing shrinks a denominator rather than
  withholding anything; the provenance lists it with the reason. A whole axis coming back empty is
  the case that withholds sections, and the two axes fail independently: the route and tempo half
  can be missing while the spell and talent half is not. Say which, rather than pretending the
  comparison ran.
- **Quota.** The budget is 3600 points an hour and a full sampled compared analysis cost 83.39
  on the one cold run anyone has measured, against a projection of about 111. `wcl-api` holds
  that row and its conditions. It is the reason not to loop. Fetching other people's reports in
  bulk is separately forbidden: reference runs are fetched for one comparison and cached, never
  warehoused.
