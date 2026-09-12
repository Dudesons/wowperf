# The Comparison Table — Design

**Status:** Proposed 2026-09-13. Not implemented.

**Authority:** `2026-09-03-mplus-postmortem-design.md` remains the authority on analysers, badges
and refusals; nothing here reopens its §6.5, and its rule against ranking per-player throughput
is restated and kept in §9. `2026-09-10-per-player-parse-comparison-design.md` remains the
authority on how a parse sample is drawn. `2026-09-13-trash-spell-comparison-design.md` supplies
the second stretch this table has to show.

**Origin:** a Blood Death Knight tank read the report after the trash comparison landed and asked
why nothing was said about Death Strike, Heart Strike, Vampiric Strike, Blood Boil or any buff
uptime. The answer was that all of them had been compared and none had crossed a bar. The page
had no way to say so with a number, and neither did he have any way to find out where inside the
bar he sat.

## 1. What this builds

A table under each compared player's card listing **every ability and aura the comparison
measured**, with our figure, the sample's median, the observed range, and which of the three
verdicts it earned — below the sample, above it, or level with it.

It adds no measurement. Every figure in it is one the comparison already computes and currently
discards after deciding whether it was worth a sentence.

## 2. The silence this answers

The report is built to say only what is worth saying. Three families now exist to keep silence
from meaning several things at once — `compare.spells.level`, `compare.spells.trash.level` and
`compare.uptime.unjudged` — and each names the abilities it set aside. That was the right fix for
"was this even looked at". It does not fix the next question.

A level row says a rate sat inside the band. It cannot say **where** inside. On the run that
prompted this, Blood Boil on boss pulls was 7.7 casts a minute against a sample median of 10.6,
with every one of the five parses above us — a real shortfall, correctly not reported, and
invisible. The same row also covered Death Strike at 14.1 against 15.3, which is nothing at all.
One sentence, two facts a reader cannot tell apart.

The bar is 1.5. For a filler button pressed ten times a minute, clearing it would mean being half
asleep, so these rows can essentially never fire on exactly the buttons a player most wants
judged. Widening the bar is the wrong fix: it would flood the ledger with rows too weak to act
on. Showing the figures without making them findings is the right one.

## 3. Where the numbers come from

This is the decision the rest of the design hangs on.

`_rate_sample` in `spells.py` and `_rate_rows` in `trash_spells.py` each compute, per ability,
`(ability_id, name, our_rate, their_median, rates)`. They then choose one of three branches and
throw the tuple away. `compare_uptime_sample` does the same with aura fractions.

**The measurement is separated from the finding.** A new module `comparison/measures.py` holds
two frozen types and nothing else:

```
AbilityRate: ability_id, name, ours, their_median, their_rates, stretch, verdict
AuraUptime:  ability_id, name, ours, their_median, their_fractions, verdict
```

`spells.py`, `trash_spells.py` and `uptime.py` each grow one function that returns a tuple of
these, and their existing finding builders consume that tuple instead of computing inline. The
table is a second consumer of the same tuple.

This is the `casts_in` move from the trash plan, applied one level up. The alternative — a
`tables.py` that recomputes the rates itself — would put two definitions of one figure in the
repository, and the first time a threshold moved, the table and the row above it would disagree
about the same player. A page that contradicts itself is worse than a page that says less.

**`verdict` is computed with the finding, not re-derived.** Which branch an ability took is a
fact about the comparison, and asking the table to work it out again from the same thresholds is
the same duplication in a smaller place.

## 4. How it reaches the report

`compare()` keeps its signature. A new top-level function sits beside it:

```
comparison_tables(ours: LoadedRun, subjects: Sequence[ComparisonSubject]) -> dict[str, ComparisonTable]
```

keyed by player slug. `cli` calls it directly after `compare()` and passes the result to
`build_report`, which passes it to `build_players`, which sets a new `comparison_table` field on
`PlayerCard`. `build_report`'s signature already carries a tail of defaulted keyword arguments
and this joins it.

**This runs the measurement twice** — once inside `compare()` for the findings, once inside
`comparison_tables()` for the table. That is deliberate. The alternative is for `compare()` to
return a tuple, which changes a signature every test and both callers use, to save microseconds
of pure arithmetic over data already in memory. Duplicate execution, single definition, is the
cheaper trade.

## 5. What a row holds

The view model carries formatted strings, as `LedgerRow` and `stats_line` already do: the
template decides nothing, including how a number is spelled.

| Field | Example | Note |
| --- | --- | --- |
| `ability_id` | `50842` | For the icon; the macro already guards on `icons_by_id` |
| `name` | `Blood Boil` | |
| `ours` | `7.7` | |
| `theirs` | `10.6` | The sample's median, never a mean |
| `spread` | `8.9 to 12.9` | The observed range |
| `sample` | `5 top parses` | |
| `verdict` | `below` / `above` / `level` | Which branch it took |

`AbilityRate` also carries `stretch`, which is not a column: it routes a row into the boss table
or the trash one, as §6 splits them.

Sorting is by the absolute difference between `ours` and `theirs`, descending, so the top of each
table is the end worth reading. Sorting happens in the builder, before formatting.

`verdict` spells the three branches `below`, `above` and `level`. `below` is the branch that
writes `compare.spells.rate` and its trash twin — named for the direction rather than the
family,
so the two directions read as a pair in a column.

## 6. Three tables, not one

Boss casts, trash casts, and buff uptime are rendered as three tables, each captioned with its
own denominator — "per minute of 648s of boss pulls", "per minute of 950s of aligned trash across
8 packs", "share of 648s of boss pulls".

One table with a stretch column would put a figure measured over 648 seconds in the same column
as one measured over 950, and a reader comparing two rows would be comparing two denominators
without being told. The units differ too: casts a minute against a percentage.

## 7. Volume, and why it is collapsed

Counted on the run that prompted this, for one player: 15 abilities took a rate verdict on boss
pulls, 19 on aligned trash, and 52 auras cleared both of the uptime comparison's floors. Eighty-six
rows. Under `--all-players` that multiplies by the roster.

Each table renders inside a native `<details>`, collapsed by default. `<details>` needs no script,
which matters: the page is allowed exactly one inline script and that script may only show, hide
and highlight what is already on the page. This adds none.

**Page size is an open cost.** The report is already about 1 MB for one compared player, almost
all of it embedded icon data URIs. The level rows draw no icons today, so a table drawing them for
sixty-odd abilities and auras could add meaningfully. §12 carries this as a question to measure
during implementation rather than guess now.

## 8. The badge, and what a table may claim

Every figure in the table is a division, so every figure is `derived`. The badge is carried once,
in each table's caption, rather than repeated on eighty rows — a finding earns a badge because it
makes a claim, and the table makes one claim per table: *these are the figures the comparison
measured*.

The table is evidence, not a new assertion. It must never state a figure that differs from a
finding's, and because both are projections of one measurement it structurally cannot — which is
the property §11 pins with a test rather than trusting.

## 9. What this does not do

- **It does not rank damage.** The project invariant stands. This is cast rates and aura uptimes,
  which is what the parse axis has always compared. No percentile, no parse number, no throughput.
- **It does not fetch anything.** Same data, already in memory, currently discarded.
- **It is not a finding and is not ranked among them.** It does not enter the ledger, does not
  carry `seconds_lost`, and does not appear in the `findings` array of the JSON. It goes in the
  findings file as a sibling top-level key, `comparison_tables`, so it is inspectable and
  testable without polluting a ranked list.
- **It does not replace the rows.** The gap, reverse and level rows stay exactly as they are. A
  reader who wants the judgement reads the rows; a reader who wants the figures opens the table.
- **It does not cover the speed axis.** Route, tempo and downtime are not per-ability and have no
  row shape here.
- **It does not let the narrative quote figures.** The digit ban is unchanged, and a table full of
  numbers is precisely what the narrative must not restate.

## 10. Approaches rejected

**The table as one finding carrying `FindingFact`s.** Rides the existing machinery with no new
data path, and wrong: it would sit in the ranked ledger as a row whose title is not a sentence,
`FindingFact` carries no ability id so no icons, and a hover panel of eighty rows is unreadable.

**One finding per compared ability.** Eighty-odd findings per player would swamp both the ranked
list and the JSON, and each would be a claim the project does not want to make.

**A `tables.py` that recomputes the figures.** Rejected in §3: two definitions of one rate is the
exact failure `casts_in` was extracted to prevent.

**A curated "important" set per specialisation.** Reads better and needs a hand-maintained data
file covering thirty-nine specialisations, dated and kept current; a specialisation nobody has
filled in would show nothing. Put to the repository's owner, who chose everything-compared.

**Its own tab.** More room, and it separates the table from the findings it is evidence for. Also
put to the owner, who chose the player card.

## 11. Testing

Per CLAUDE.md, all three levels.

- **Unit.** The measurement functions return one row per compared ability with the verdict that
  matches the branch the finding took. The refactor of §3 changes no finding: the existing spell,
  trash and uptime suites are the regression net and must pass untouched.
- **Integration.** The table reaches `PlayerCard` for a compared player and not for an uncompared
  one. Sorting is by absolute difference. **The anti-drift test: for every rate and uptime finding
  on the page, the table holds a row naming the same ability with the same two figures.** That is
  the property §8 rests on, and it is the one test that would catch the two-definitions failure if
  a later change reintroduced it.
- **HTML.** The table renders, adds no script, introduces no duplicate element id, and any icon it
  draws is a data URI. The existing invariants suite covers the last three and must be extended to
  see the table rather than assumed to.
- **End-to-end.** Against a real run: the table's row count equals the number of abilities the
  comparison measured, and no row contradicts a finding.

Every test written first and watched fail. Where one passes on first writing, the guard it covers
is mutated and the test confirmed red before it is trusted. Two tests in the trash work passed on
first writing because their fixtures were rejected by an earlier gate than the one under test —
both prescribed in that plan's own worked code — so a plan's fixtures earn no more trust here than
any others.

## 12. Open questions for implementation

1. **Icon volume and page size.** Measure the rendered page before and after against a real run
   with `--all-players`. If the increase is large, the fallback is to draw icons only for rows that
   already have one on the page and let the rest render as names, which the existing macro already
   does when an id is absent from `icons_by_id`.
2. **Auras under `MIN_UPTIME_FRACTION`.** The uptime comparison ignores them. Current inclination:
   the table follows the comparison exactly, so it is the evidence for what was compared rather
   than a superset with different rules.
3. **Whether `--all-players` renders a table for every player or only the subject.** Inclination:
   every compared player, because that is what the flag is for; revisit if question 1 says the page
   cannot afford it.
4. **Whether a row should say how many of the sample cast the ability at all**, as distinct from
   how many cleared `MIN_CASTS_TO_COMPARE`. The rows above already state the second. Inclination:
   no — one count per row, and the same one the findings use.
