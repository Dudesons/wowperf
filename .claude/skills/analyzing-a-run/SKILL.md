---
name: analyzing-a-run
description: Use when given a Warcraft Logs URL to analyse — a Mythic+ key, a raid boss fight, or every attempt at one boss — runs the tool, interprets the findings, and hands back a finished report
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
[--no-deaths] [--difficulty N] [--cache-dir DIR] [--out DIR]`, the fourth sibling of `analyze`,
`raid` and `progression`, not a mode of any of them, and the widest of the four: `raid` reads one
pull, `progression` one boss's pulls, this one every boss and every pull the report holds. There
is no `--fight`, because covering every fight is the point.

It draws no comparison at all — neither axis `raid` draws for a single pull. The parse axis is
per player per boss, and across a whole report it would cost an order of magnitude more than
everything else here put together, so `--player`, `--all-players` and `--no-compare` do not apply
and are not offered; there is no per-player reference for them to widen or skip. The mechanics
axis is absent too, for a different reason: this command fetches no reference kill of any kind,
so every pull's Damage tab and every player's spell-and-talent section read "No reference run was
fetched for this analysis, so there is nothing to compare against" — the same line `raid
--no-compare` prints, since neither command fetched one. The page also states the parse absence
once, on its own, naming the families it leaves out — damage against the board, damage by target,
casts a minute, talents, buff uptime, the percentile — rather than leaving them silently missing.
`wowperf raid --fight N` is what draws both axes, for one pull. `--narrative` is not offered
either, for the reason `raid` and `progression` do not take it: this command writes no
narrative-bearing page.

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
Provenance — behind two dropdowns, a boss and then a pull within it. A boss pulled two or more
times opens on a summary before any pull: the page `wowperf progression` draws for that boss —
its attempts, what kept repeating across them and what the best one did differently — built from
the same findings the night's JSON writes under that boss. A boss pulled once has no summary,
since one attempt leaves nothing to compare, and opens on its pull.

A pull drawn at less than the
deep tier still has its full death anatomy on hand elsewhere: `--deep` buys it back here for a
named pull, or `wowperf raid --fight N` draws it for that one pull on its own.

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
