---
name: analyzing-a-run
description: Use when given a Warcraft Logs Mythic+ URL to analyse — runs the tool, interprets the findings, writes the narrative, and hands back a finished report
---

# Analysing a run

You are given a Warcraft Logs URL. You hand back one HTML file and say what it found.

## The workflow

1. **Run the tool.**

   ```bash
   uv run wowperf analyze <url>
   ```

   Add `--player NAME` when the person named someone other than the report's owner; if the name is
   not in the roster the tool prints the roster it does have. Add `--no-compare` only if they asked
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

5. **Re-run with the narrative.** Repeat step 1's command *exactly* — same URL, same `--player`,
   same `--no-compare`, same `--fight` if you used one — and add only `--narrative`.

   ```bash
   uv run wowperf analyze <url> --narrative out/<code>-<fight>.narrative.md
   ```

   Only then is every response served from the cache written in step 1, and reference entries
   live a day, so a second run the same day spends no API quota. Drop a flag and you change the
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
`compare.route.skipped.2` means nothing to them.

**It renders as plain text.** Escaped and pre-wrapped, not Markdown. Asterisks arrive as asterisks.

### Four things it must never do

1. **Restate the ledger in words.** The ledger already says it, with figures, better.
2. **Add figures up.** The findings file explains why in `findings_are_ranked_not_additive`.
3. **Assert an `inferred` finding as fact.**
4. **Give advice that traces to no finding at all.**

### What good looks like

> Your losses are route, not execution. The largest figure on this page is time spent outside
> pulls, and every one of the biggest ranked losses beneath it is a gap between packs — the group
> was travelling or waiting, not fighting. Underneath that, you pulled packs the faster reference
> run skipped, which is why the trash overage and the skipped-pack findings both appear: the same
> detour, reported from either side.
>
> Deaths barely register beside it, and nothing in the damage findings suggests a mechanical
> problem worth fixing before the route is.
>
> Treat the missing-talent finding as a prompt rather than a verdict — the spell comparison runs on
> boss pulls only, and the reference is a different character on a different key.

## When it goes wrong

- **No credentials.** The tool needs `WCL_CLIENT_ID` and `WCL_CLIENT_SECRET` in the environment,
  and says so by name when they are missing. Ask the person to set them; never read them from a
  file and never print them.
- **Not a completed keystone.** The URL must point at a Mythic+ run that finished. A report with
  no keystone fight, a depleted or abandoned key, or a fight id that is not one, each fails with a
  message saying which. A report holding several keys fails asking for `--fight`, since neither
  `--fight` nor a fight number in the URL picked one out.
- **A reference could not be fetched.** The report still renders, with the affected sections
  withheld and stating the tool's own reason. The speed reference and the parse reference fail
  independently: one can be missing while the other is not. Say so rather than pretending the
  comparison ran.
- **Quota.** The budget is 3600 points an hour and a full compared analysis costs roughly 28 —
  an order of magnitude observed across this project's runs, not a measurement, and the reason not
  to loop rather than a number to budget against. `wcl-api` holds what is actually known. Fetching
  other people's reports in bulk is separately forbidden: reference runs are fetched for one
  comparison and cached, never warehoused.
