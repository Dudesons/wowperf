# The Inference Layer — Design

**Status:** approved and implemented 2026-09-05.

**Authority:** `docs/plans/2026-09-03-mplus-postmortem-design.md` §8, which this document expands
and, in the places noted, amends.

**Scope:** the last piece of slice 1. Three skills under `.claude/skills/`, one guardrail in the
command-line tool, and the workflow that turns a Warcraft Logs URL into a finished report without
you reading a JSON file.

---

## 1. Purpose

Everything shipped so far produces facts. Plans A to E fetch a run, compute findings, rank them,
and render a page. Nothing yet says what the facts *mean*.

That job is Claude's, and this design draws the line it may not cross.

## 2. Two layers, and the line between them

**Python produces facts.** Deterministic, tested, opinion-free. "The gap after pull 7 was 41
seconds." "Nobody cast Ice Block." Every figure on the page comes from here.

**Claude produces meaning.** "Both of your largest losses are travel, not combat, so routing is
the problem, not damage."

The tool emits two artifacts. `<code>-<fight>.html` is for people. `<code>-<fight>.findings.json`
is for Claude, and already carries what a reader needs: the run's metadata, both comparison
references, the ranked findings with their confidence badges and evidence, and an explicit
`findings_are_ranked_not_additive` warning naming every nesting relationship.

**Claude never parses the HTML.** The narrative returns to the report through
`analyze --narrative`, which renders it as the page's second section. Determinism survives,
because the narrative is an input to rendering rather than something the template invents.

## 3. The guardrail

### 3.1 The rule

**The narrative states no numbers.**

Not "no unverified numbers" — none at all. Every figure on the page already sits in a section
that owns it, badged and sourced, a few centimetres below the narrative. A number repeated in the
narrative is at best redundant and at worst a second, unbadged claim competing with the first.

The example §8 itself gives contains no digits:

> "Both of your largest losses are travel, not combat, so routing is the problem, not damage."

It ranks, categorises and concludes. That is the whole job.

### 3.2 Where the check lives

`analyze --narrative` rejects a narrative containing any digit, **before anything is fetched**,
beside the existing rule that an unreadable narrative path fails first. A typo and a bad narrative
both cost zero API quota.

The check is a pure function in `src/wowperf/domain/report/narrative.py`. It returns **every**
offending line with its number, not just the first, so fixing a narrative is not whack-a-mole.
`cli.py` reads the file and formats the error; the domain performs no I/O, as everywhere else.

The error explains itself, because the rule is unusual:

```
notes.md line 3: the narrative states no numbers — the figures live in the
report's own sections, directly below it.
  > Travel cost 3:13, more than every death combined.
```

Three consequences, accepted:

- **The rule applies to narratives you write by hand.** It governs what the interpretation section
  on the page may say, not who authored it.
- **There is no escape hatch.** No `--allow-digits`. A guardrail with a bypass is a guardrail
  nobody trusts, and this is the only claim on the page with no tested Python behind it.
- **`str.isdigit()` catches more than ASCII** — superscripts, Arabic-Indic numerals. Correct
  behaviour, not a bug to work around.

### 3.3 What the check does not catch

**It is a tripwire, not a proof.** A narrative saying "you lost three minutes to travel" has no
digits and passes.

The *instruction*, carried by `analyzing-a-run`, is "state no quantities". The *check* catches
numerals, which is where drift actually happens. Spelled-out quantities remain the skill's
responsibility. Closing the gap would take natural-language parsing and is not worth it.

The gap is also useful in one direction: counting words are often exactly what you want. "The four
biggest ranked losses are all gaps between packs" is a count of findings a reader can verify by
looking down the page, not a measurement competing with the ledger.

## 4. The three skills

| Skill | Who reads it | When it fires |
| --- | --- | --- |
| `wcl-api` | a session **writing code** against the API | about to write a query or read a payload field |
| `mplus-analysis` | a session **interpreting findings** | reading the findings JSON, or answering a domain question |
| `analyzing-a-run` | a session **handed a URL** | the entry point; delegates to the other two |

Three different audiences, three different triggers. They are not three chapters of one document.

### 4.1 `wcl-api`

Design §2's verified API reference moves here wholesale, and §2 becomes a two-line pointer. §2 is
*verified context*, not architecture — `CLAUDE.md` names the design as the authority on
"architecture, analyzers, and comparison rules", none of which §2 is. One copy, no drift.

Its organising principle is one this project learned at cost: **every claim carries how it was
verified and when.** Plan D built a half-feature that ships inert because a §2 line said "verified"
and had never been run. So the enemy-debuff measurement of 2026-09-05 goes in as a first-class
entry — no argument scopes that table to one caster, measured on that date — rather than as a
footnote to a claim that reads as true.

Contents: exact field names and enum values with their verification dates; conventions that remain
unverified, marked as such; the terms-of-service limits, including the §5d prohibition on building
a corpus of other players' logs; and rate-limit etiquette with the measured budget.

**The field names live in one Markdown table, not scattered through prose**, so that §8's drift
test can read them. The table's columns are the field, the type it appears on, and the date it was
verified. Prose around the table is free-form; the table is the machine-readable part, and it is
the only place a field name may be introduced.

### 4.2 `mplus-analysis`

What a reader needs in order to interpret honestly:

- the seconds framing, and why findings are **ranked, never summed**
- why damage goes unranked in Mythic+
- the confounds the comparison declares rather than corrects
- **what each confidence badge licenses you to say** — `measured` earns "was", `derived` earns
  "works out to", `inferred` earns "suggests"

That last item is the bridge between the findings and the narrative, and it is why this is a
separate skill rather than a section of the workflow: it is also what you want when someone asks
"why doesn't this rank damage?" without running anything.

### 4.3 `analyzing-a-run`

The workflow of §5. Short, because most of its weight is delegated.

## 5. The workflow

1. Run `uv run wowperf analyze <url> [--player NAME]`.
2. Read `out/<code>-<fight>.findings.json`.
3. Read `mplus-analysis` before forming any opinion.
4. Write the narrative to `out/<code>-<fight>.narrative.md`, matching the artifact naming already
   in use. `out/` is gitignored.
5. Re-run the same command with `--narrative`. Every response is cached, so this costs no quota and
   about fifteen seconds.
6. Hand over the HTML path.
7. Say the conclusion in chat as well, so nobody has to open a file to learn what the tool found.

**No second command.** Re-running `analyze` was considered against a dedicated `narrate` command
and wins: `build_report` needs the whole `LoadedRun`, the references and the subject, none of which
the findings JSON carries, so `narrate` would have to re-load from cache — which is precisely what
re-running `analyze` does, for free.

The skill names four failure modes, because each has a different answer: missing credentials; a URL
that is not a completed keystone; a reference that could not be fetched, where the report still
renders with withheld sections saying why; and the quota, 3600 points an hour against roughly 28
for a compared run — not a constraint, but a reason not to loop.

## 6. What a good narrative is

Three to six sentences. It leads with what dominated and what *kind* of problem it is, says what to
change, and hedges where the finding is inferred.

It echoes finding **titles**, never ids. A title is prose a reader can scan down the page and find;
an id is a machine identifier that means nothing to them.

It renders as escaped, pre-wrapped plain text — not Markdown. Asterisks arrive as asterisks.

Four anti-patterns the skill forbids by name:

1. **Restating the ledger in words.** The ledger already says it, better and with figures.
2. **Adding figures up.** The JSON says why in its own warning string.
3. **Asserting an `inferred` finding as fact.**
4. **Advice that traces to no finding at all.**

## 7. Command surface

Unchanged, except that `--narrative` now rejects a file containing a digit. No new command, no new
flag.

## 8. Testing

**Unit.** The digit function: clean prose, a single numeral, several offending lines reported
together, non-ASCII digits, a digit inside a word, an empty file.

**Integration.** `analyze --narrative` with a digit-bearing file fails with **zero API calls**,
mirroring the existing missing-file test.

**The skills are prose and have nothing to unit test** — but they get one tripwire each, for the
same reason the narrative does. A test reads `wcl-api`'s field table and asserts each name appears
in `src/wowperf/adapters/wcl/queries.py`; another asserts the flags `analyzing-a-run` tells you to
type exist on the CLI. Neither is airtight. Both catch the drift that makes a reference dangerous —
a skill confidently naming a field the code no longer uses.

This is the part of the design most readily dropped if it proves fussier than it looks.

## 9. What changes

| File | Change |
| --- | --- |
| `.claude/skills/wcl-api/SKILL.md` | *New.* Design §2's content, with verification dates |
| `.claude/skills/mplus-analysis/SKILL.md` | *New.* Interpretation knowledge |
| `.claude/skills/analyzing-a-run/SKILL.md` | *New.* The workflow |
| `src/wowperf/domain/report/narrative.py` | *New.* The digit check, pure |
| `src/wowperf/cli.py` | *Modified.* Calls the check before fetching |
| `tests/domain/report/test_narrative.py` | *New.* Unit tests for the digit check |
| `tests/test_skills.py` | *New.* The two drift tripwires of §8 |
| `tests/test_cli.py` | *Modified.* A digit-bearing narrative fails with zero API calls |
| `docs/plans/2026-09-03-mplus-postmortem-design.md` | *Modified.* §2 becomes a pointer; §8 records what shipped |
| `CLAUDE.md` | *Modified.* Skills table gains three rows, loses the sentence promising them |

## 10. Out of scope

- **Any change to the findings JSON.** It already carries the metadata, the references, the
  non-additivity warning and the badged findings. Adding a Python-computed "narrative brief" was
  considered and rejected: deciding what matters is the job this design gives to Claude, and moving
  it into Python collapses the two-layer split §8 exists to draw.
- **Rendering Markdown in the narrative.** A second dependency and a second escaping story for one
  paragraph of prose.
- **Slices 2 to 4** — raid, wipe and healer analysis.

## 11. Decisions recorded

1. **The narrative states no numbers**, and the check rejects any digit rather than trying to
   distinguish a measurement from a reference. One sentence to state, three lines to check, never
   arguable. It costs "pull 7" and "+16"; the narrative writes "the pack before the second boss"
   and "your key" instead, which reads better anyway.
2. **The check lives in `analyze`, not a separate command.** A check you have to remember to run is
   a check that stops running.
3. **The check is a tripwire, not a proof**, and §3.3 says so rather than letting the design read
   as a guarantee it cannot make.
4. **Design §2 moves rather than being copied.** Two copies of a schema reference drift, and the
   drifted one is read as true.
5. **Three skills, not two.** `mplus-analysis` is wanted without the workflow — when someone asks a
   domain question having run nothing — and a single skill covering both jobs goes blunt.
6. **No `narrate` command.** It would re-load from cache exactly as re-running `analyze` does.
