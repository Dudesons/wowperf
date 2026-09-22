# wowperf

Two halves. A command-line tool that reads a Mythic+ run from Warcraft Logs and computes what
happened, and a set of Claude skills that read those numbers back and tell you what they mean.

The line between them is the whole design: **Python produces facts, Claude produces meaning.**
Every figure comes from tested code. The model never does arithmetic — the interpretation it
writes is refused outright if it contains so much as a digit. The result is a coach that cannot
invent a number at you.

It all runs on your machine. Point it at a log, and it fetches the run, works out where the time
went, what each death cost, which interrupts were missed, which defensives sat off cooldown at a
death and which were pressed far below what their cooldown allowed, compares all of it against
fast completions of the same dungeon, and writes one self-contained HTML file you open from disk.

Every finding is labelled `measured`, `derived` or `inferred`, so you can always tell what the
tool saw from what it worked out.

## What you need

- **uv**, which brings its own Python. Install it from
  [the uv documentation](https://docs.astral.sh/uv/getting-started/installation/).
- **A Warcraft Logs API client.** Free, takes a minute, and yours alone — see below.
- **A log that is public or unlisted.** A report set to *private* needs a Warcraft Logs login,
  which this tool does not implement. Unlisted is fine and keeps the run out of the rankings.
- **Claude Code**, for the coaching half only. The tool works without it.

## Setup

```bash
uv sync
```

Then get yourself credentials:

1. Go to <https://www.warcraftlogs.com/api/clients/> and create a client. Any name, any redirect
   URL — the flow this tool uses needs neither.
2. Copy `.env.example` to `.env`.
3. Paste the client ID and secret into it.

`.env` is gitignored and stays on your machine. If you would rather export the two variables in
your shell, do that instead — the environment wins over the file.

## Analysing a run

```bash
uv run wowperf analyze https://www.warcraftlogs.com/reports/YOURCODE
```

That writes two files into `out/`: the findings as JSON, and the report as one HTML file. Open
the HTML in a browser.

The flags worth knowing:

| Flag | What it does |
| --- | --- |
| `--fight N` | Pick a run when the report holds several keys |
| `--player NAME` | Analyse this player rather than the report owner; repeatable |
| `--all-players` | Give every player in the group their own page |
| `--no-compare` | Skip reference runs and judge the run on its own |
| `--out DIR` | Where the two files go (default `out`) |

`uv run wowperf fetch <url>` prints the raw run as JSON without analysing it, which is
occasionally useful when something looks wrong.

## Asking Claude to coach you

The tool gives you a report. The skills give you someone to read it with.

`.claude/skills/` ships with the repo, so a clone already has them. Open Claude Code in the
folder and paste a log URL — *"have a look at this run"* is enough.

- **`analyzing-a-run`** takes it from there: fetches the run, reads the findings, writes the
  interpretation in plain language, feeds it back through `--narrative`, and hands you a finished
  report with the reasoning already in it.
- **`mplus-analysis`** governs what may be said about those findings — which comparisons are
  sound, which must be withheld, what each confidence badge does and does not licence. It is the
  half that stops coaching from turning into confident invention.

You can also just ask: *why did we lose the key? Was the third death avoidable? What should I
press earlier next week?* It answers from the findings file — never from the HTML, and never from
what it happens to believe about your specialisation.

Without Claude Code, everything above still works. You read the report yourself.

## What the report holds

Six tabs — Summary, Route & tempo, Deaths, Interrupts, Players, Provenance. Each death gets a
recap: a health curve, a timeline of what hit you, how you came back, and every defensive,
consumable and teammate external placed in one of six states at the moment you died — pressed,
ready, on cooldown, or never seen all run, and one of your own defensives you pressed refined to
held or faded by whether its aura was still up when the killing blow landed.

The Provenance tab is the one to read when a number looks wrong. It says where each figure came
from.

## What it will not tell you

Being clear about this matters more than the features:

- **Comparisons are withheld rather than guessed.** If the reference run sits more than one
  keystone level away, or fewer than half the pulls match, the tool says nothing instead of
  something misleading.
- **It reports a median and an observed range, never an average.** Below three comparable
  reference runs it falls back to a single reference and says so on the finding.
- **Uptime covers buffs only.** Warcraft Logs offers no way to scope the enemy-debuff table to a
  single caster, so "what you kept up on the boss" does not exist as a number.
- **Nothing here is a DPS ranking.** It is about decisions, not throughput.

## Quota

Warcraft Logs gives each client 3600 points an hour. A full run costs roughly six, so you will
not run out. Every response is cached under `cache/`, and both commands close by printing what
the run spent, dearest operation first.

## Roadmap

Mythic+ is the first of four slices. Each later one reuses the API client, cache, domain model,
findings format, report renderer and skills layer, and adds analysers on top.

| Slice | Status | What it covers |
| --- | --- | --- |
| 1. Mythic+ post-mortem | **Shipped** | Everything described above |
| 2. Single-player raid analysis | Planned | Your own performance on a raid encounter |
| 3. Raid wipe analysis | Planned | What went wrong for the group rather than the individual |
| 4. Healer analysis | Planned | Healing asks different questions and fails in different ways |

Deliberately out of scope: personal run history across weeks, and raw combat-log ingestion.
Everything arrives through the Warcraft Logs API.

## Feedback

Open an issue. The template asks for the report code and fight number, which is enough for
anyone to reproduce what you saw.

**Please do not attach the findings JSON or the HTML report.** Both carry the real character
names of everyone in your group, and an issue is public. The report code and a description of
what looked wrong are all that is needed.

## Licence

MIT — see [LICENSE](LICENSE).

That covers this code and nothing else. The combat log data belongs to Warcraft Logs, and your
use of it is governed by the RPGLogs API Terms of Service — §2c forbids holding several API
clients to multiply your hourly budget, and §5d forbids building a standing collection of other
people's logs. Fetching a run on demand and caching it locally is ordinary use; warehousing is
not. Ability icons are Blizzard's artwork, fetched from their CDN and embedded so that a report
stays readable offline.
