# wowperf

Two halves. A command-line tool that reads a Mythic+ run, a raid boss fight, or a whole night of
attempts at one boss from Warcraft Logs and computes what happened, and a set of Claude skills
that read those numbers back and tell you what they mean.

The line between them is the whole design: **Python produces facts, Claude produces meaning.**
Every figure comes from tested code. The model never does arithmetic — the interpretation it
writes is refused outright if it contains so much as a digit. The result is a coach that cannot
invent a number at you.

It all runs on your machine. Point it at a key, and it works out where the time went, what each
death cost, which interrupts were missed, which defensives sat off cooldown at a death and which
were pressed far below what their cooldown allowed, and compares all of it against fast
completions of the same dungeon. Point it at a boss fight, and it says what ended the attempt, who
took far more of something than the rest of the raid, and how the pull reads against kills of the
same boss. Either way, out comes one HTML file you open from disk.

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

## Analysing a raid

```bash
uv run wowperf raid https://www.warcraftlogs.com/reports/YOURCODE --fight 12
```

A sibling of `analyze`, not a mode of it: one boss fight, kill or wipe, written as the same two
files. It takes `--fight`, `--player`, `--all-players`, `--no-compare` and `--out`, and nothing
else — a boss has no route and no pulls, so the flags that read those are not offered.

A kill is compared against kills of the same boss. A wipe is told what ended it and where the
raid's damage went, and every comparison that needs a completed kill is withheld and says so:
Warcraft Logs ranks kills alone.

```bash
uv run wowperf progression https://www.warcraftlogs.com/reports/YOURCODE --boss 3492
```

reads every attempt at one boss in one report and writes the night rather than the pull — how
deep each attempt got, what kept ending them, and what the best one did differently. `--boss` is
required once a report holds more than one boss. It draws no outside reference at all, a night's
attempts being judged against each other, which is why it is the cheapest of the three by an
order of magnitude.

## Asking Claude to coach you

The tool gives you a report. The skills give you someone to read it with.

`.claude/skills/` ships with the repo, so a clone already has them. Open Claude Code in the
folder and paste a log URL — *"have a look at this run"* is enough.

- **`analyzing-a-run`** takes it from there: fetches the fight, reads the findings, writes the
  interpretation in plain language, and hands you a finished report. On a key it feeds that
  interpretation back through `--narrative`, so the reasoning lands inside the page; a raid page
  carries no narrative, and the reading comes back in the conversation instead.
- **`mplus-analysis`** governs what may be said about those findings — which comparisons are
  sound, which must be withheld, what each confidence badge does and does not licence. It is the
  half that stops coaching from turning into confident invention. It covers the Mythic+ families;
  the raid ones have no counterpart yet.

You can also just ask: *why did we lose the key? Was the third death avoidable? What should I
press earlier next week?* It answers from the findings file — never from the HTML, and never from
what it happens to believe about your specialisation.

Without Claude Code, everything above still works. You read the report yourself.

## What the report holds

A key gets six tabs — Summary, Route & tempo, Deaths, Interrupts, Players, Provenance. A boss
fight gets seven: Route & tempo gives way to Damage and Mechanics, the two axes a boss has in its
place. A night of attempts gets five — Summary, Attempts, Repeats, Best attempt, Provenance — the
night's shape rather than any one pull's anatomy, which stays `raid --fight N`'s work.

Each death gets a recap: a health curve, a timeline of what hit you, how you came back, and every
defensive, consumable and teammate external placed in one of six states at the moment you died —
pressed, ready, on cooldown, or never seen all run, and one of your own defensives you pressed
refined to held or faded by whether its aura was still up when the killing blow landed.

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

Warcraft Logs gives each client 3600 points an hour, and every response is cached under `cache/`,
so a second look at a fight you have already read costs a single point. What a first look costs
depends on the command and on how wide you cast it. Measured, against a cold cache:

| Command | Points |
| --- | --- |
| `progression`, a whole night | 3 to 26 |
| `raid --all-players`, a wipe | 65 |
| `raid`, one player, a kill | 63 |
| `analyze`, one player | 83 to 95 |
| `analyze --all-players` | 190 |
| `raid --all-players`, a kill | 878 |

Each is one reading of one report on one day rather than a budget; the dates and the conditions
behind them are recorded in `.claude/skills/wcl-api/SKILL.md`, which is where a new measurement
goes.

**Whether the boss died is what moves the raid figures, not how many players you name.**
Warcraft Logs ranks kills alone, so an attempt that wiped carries no rankings row, and the
per-player reference sample that dominates the last line is never drawn — `--all-players` on a
wipe costs about what one player costs. Only that last line is worth a thought before you run
it: naming every raider on a kill draws a sample for each of the twenty, and four such runs
would spend the hour. Every command closes by printing what it spent, dearest operation first.

## Roadmap

Mythic+ is the first of four slices. Each later one reuses the API client, cache, domain model,
findings format, report renderer and skills layer, and adds analysers on top.

| Slice | Status | What it covers |
| --- | --- | --- |
| 1. Mythic+ post-mortem | **Shipped** | `analyze` — everything described above |
| 2. Single-player raid analysis | **Shipped** | `raid` — your own fight, read against kills of the same boss |
| 3. Raid wipe analysis | **Mostly shipped** | `raid` on a wipe, and `progression` across a night of them |
| 4. Healer analysis | Planned | Healing asks different questions and fails in different ways |

Slice 3 still owes the one claim it is deliberately slow about: that one raider's action caused
another's death. Today the tool measures what happened alongside what, badges it `inferred`, and
uses no causal verb. Nothing is designed yet that would earn one.

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
not. Ability icons are Blizzard's artwork, addressed on their CDN and fetched by your browser when
you open a report, so the page carries no image bytes of its own — and names every ability in text
when you open it without a connection.
