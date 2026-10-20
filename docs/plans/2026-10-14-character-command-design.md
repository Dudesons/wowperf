# One character, every dungeon: the `character` command

**Status:** approved design, brainstormed 2026-10-08 and revised 2026-10-14 against main after
#56 and #57. Built 2026-10-14 on the `character-command` branch, to the plan
`2026-10-14-character-command-plan.md`; the dated amendments below record where the build departed
from this design.
**Slice:** personal run history, the slice `2026-09-03-mplus-postmortem-design.md` deferred. One
character's recent Mythic+ runs are analysed one by one and read together for what repeats.

## 1. Goal

`wowperf character <character-url>` takes a Warcraft Logs character page and writes **one HTML
page stating what repeats across that character's recent runs**: the judgements the per-run
analysis made again and again, the measures that sat on the same side of the top parses in every
run, and a run-by-run ledger of the group comparisons. Every run it reads also gets the report
`wowperf analyze` would have written, and the character page links to each.

## 2. Why

One run is noise. On 2026-10-08 ten runs of one Blood Death Knight were analysed by hand and read
together with a scratch script. What mattered was what no single run said:

- Death's Caress was flagged below the top parses in every run. Each report said it once; only
  the count said it was a habit.
- Vampiric Strike and Death Strike were never flagged in any run, because no gap reached
  `RATE_GAP_MULTIPLE`, yet both sat below the parse sample's median in every run. The chain they
  form was the most useful finding of the session, and only the comparison tables, read across
  runs, showed it.

The scratch script computed those counts outside tested Python, which the project forbids for
anything a reader is shown. This command puts the counting where the rules are.

## 3. Decisions

1. **Which runs.** For each dungeon of the zone: the character's highest keystone level there,
   then the most recent ranked run at that level or one below that has a report attached, timed or
   not. At most one run per dungeon. A dungeon with no such run is left out and listed with the
   reason. Patterns only count if they hold across dungeons, and depleted keys are kept because
   they are where the lessons usually are.
2. **One specialisation.** Runs are taken from one spec only: the spec with the most ranked runs in
   the zone, or the one `--spec` names. A direction counted across two specs compares a tank's
   rotation with a damage dealer's. The page states the spec. *(Decided while writing; confirmed
   at spec review.)*
3. **What it writes.** A character JSON and page, and each run's own findings file and report. The
   runs are analysed anyway, and a pattern a reader cannot trace to its runs is a claim.
4. **Where it writes.** Everything goes under `<out>/<region>-<realm>-<name>/`, using the
   project's slug, so the character page and its run reports sit in one directory and link to each
   other by file name. A run report another `analyze --narrative` already wrote under `<out>` is
   never overwritten. *(Decided while writing; confirmed at spec review.)*
   *Amended 2026-10-14, while building:* the directory is not built from the project's slug. That
   slug serves HTML ids, so it reduces every wholly non-Latin name to one fallback (`player`) and
   strips accents, and two characters on one realm (`Кириллица` and another Cyrillic name, or
   `Bríala` and `Briala`) would share a directory, the second overwriting the first. The directory
   is `<region>-<realm>-<name>`: the region, the realm slug as `parse_character_url` returns it
   (lower-cased and percent-decoded from the URL; it is already a Warcraft Logs slug), and the
   character name casefolded in its own script. A file
   name does not need the HTML-id alphabet, and a character name is letters only; a realm or name
   whose percent-decoding holds a path separator is refused before anything is fetched.
5. **Three kinds of statement** (§5): repeated judgements, consistent directions, and a ledger
   that carries no verdict.
6. **Nothing is summed.** Seconds lost in different dungeons, at different keys and on different
   routes are not one quantity. The page and the JSON carry the same ranked-not-additive warning the
   other commands carry.
   *Amended 2026-10-14, while building:* the same warning in kind, not in words. The JSON key is
   the other commands' own, `findings_are_ranked_not_additive`, but its text is the character
   page's, `CHARACTER_FINDINGS_ARE_RANKED_NOT_ADDITIVE` in `domain/character/patterns.py`. Each
   command's warning names its own findings' families and the order they are ranked in, which a
   cross-run finding shares with none of them, and the domain cannot import the other commands'
   warnings, which live in `cli.py`.
7. **No class knowledge in this slice.** Relations such as "Infliction of Sorrow fires only on
   targets carrying Blood Plague" belong in a hand-maintained, dated, sourced file under `data/`,
   designed in the next slice (§12). The pattern sources here are built so such a relation can be
   added as one more source feeding the same counting.

## 4. Command

```
wowperf character <character-url> [--zone ID] [--spec NAME] [--narrative FILE] [--cache-dir DIR] [--out DIR]
```

- **The URL** is `https://www.warcraftlogs.com/character/<region>/<realm>/<name>`, optionally with
  `?zone=<id>`. `urls.parse_character_url` returns region, realm slug, name and the zone if present.
- **The zone** comes from the URL or `--zone`; with neither, the command stops and says where to
  find the zone id. It never guesses the current season (no hardcoded season data).
- **`--narrative`** works as on `analyze`: the file is refused before anything is fetched if it
  holds a digit, and the text sits at the top of the Summary.
- **`--spec`** picks the specialisation (§3.2). A name the character has no ranked runs for stops
  the command and lists the specs it does have.
- Not offered: `--player`, `--all-players`, `--no-compare`, `--fight`, `--throughput-ceiling`. The
  subject is the character, the comparison is what the patterns read, and the runs are chosen by
  the rule in §3.1.

### 4.1 Run selection

1. `worldData.zone(id)` gives the zone's name and its dungeons (`encounters { id name }`).
2. `characterData.character(name, serverSlug, serverRegion)` gives `hidden`, and one aliased
   `encounterRankings(encounterID: …)` per dungeon gives the character's ranked runs.
3. Each rank carries `report { code fightID startTime }`, `bracketData` (the keystone level),
   `startTime`, `duration`, `medal` and `spec`. A rank whose `report` is missing has no public log
   and is not a candidate.
4. `domain/character/selection.py` applies §3.1 and §3.2 and returns the chosen runs and the
   dungeons left out, each with its reason.

These fields were read live by hand on 2026-10-08 (one character, zone 55). None is in the
`wcl-api` skill yet. The build verifies each against the live schema and records it as a dated row
before any code uses it. Warcraft Logs labels `encounterRankings` "not considered frozen, and it can
change without notice"; the skill records that too.

### 4.2 Errors

The command stops, naming the cause, when the character is not found, when `hidden` is true, when
no zone is given, or when the zone is not a Mythic+ zone. Zone 55 reports one difficulty, id 10
"Dungeon"; the build checks a raid zone live to confirm `difficulties` tells the two apart before
relying on it. If it does not, the per-run keystone check (`select_keystone_fight`) is the test,
and every run failing it is reported as such.

A run that fails to load, for any reason the analysis raises, does not stop the command. It is
listed under Runs with its reason, and the page counts only what loaded.

*Amended 2026-10-14, while building:* "any reason" is narrowed to the failures that belong to one
run. A `ValueError` (the ingest's own refusals among them), a `WclError` or an `httpx.HTTPError`
from one run's analysis lists that run as failed and the command goes on. Two failures stop it
instead, naming the cause and writing no character page: `RateLimitExceeded`, because a spent
budget is not one bad run and every run after it would fail the same way, so a page shrunk by it
would describe the budget rather than the character; and `OSError`, because that is the disk or
the cache, not the run, and it would fail the next write as well. Everything fetched before the
stop stays cached, so a second run resumes at almost no cost. A stop deletes nothing: a
`character.json` and `character.html` an earlier invocation wrote stay in place, untouched and
now older than the run reports this invocation already wrote beside them.

## 5. What counts as a pattern

All three kinds are pure functions in `domain/character/`, over what each run's analysis returned.
Runs are joined on the character, never on a finding id's slug: `emberkin-0` in one run can be
`emberkin-2` in the next, because the suffix is the roster index.

*Amended 2026-10-14, after the live run:* a known limitation. One ability name can own several
game ids, and nothing in the log says whether two ids are one press or two abilities
(`_one_row_per_sentence` in `comparison/spells.py` records the measurement). Repeated judgements
and directions are keyed by ability id, so one habit can split across ids and be counted, or given
a direction, once per id. It was seen live: two "Boiling Point" aura ids each gave a direction, one
up more of the key than the top parses and one up less. Merging by name would be wrong wherever two
ids are two abilities, so the page states each id as read, and `mplus-analysis` tells a reader not
to add or net them.

### 5.1 Repeated judgements

- A finding's **family** is its id with the subject's slug suffix and any trailing rank index
  removed, together with its `ability_id` when it has one. `compare.spells.trash.rate.0.<slug>` for
  Death's Caress and `compare.spells.trash.rate.3.<slug>` for Death's Caress in another run are one
  family.
- Only **judgement** families count: ones that fire only when something stands out. They are named
  in an explicit allowlist, so a family added later is not counted by accident:
  - The subject's own: spell rate gaps on bosses and trash in both directions, a spell never cast,
    talents, buff uptime gaps, debuff coverage gaps (`compare.uptime.debuff.*`), gear, stat shares,
    the consumable comparisons, `defensives.unused`, `defensives.ceiling`, `consumables.never`,
    `consumables.unused` and `throughput.alignment`.
  - The run's: `compare.route.skipped` and `trash.overage`.
  - Never counted: statements that always appear (`compare.duration`, `compare.deaths`,
    `compare.downtime`, `compare.interrupts`, `compare.route.summary`), level, unjudged,
    unavailable and withheld statements, and confounds.
- *Amended 2026-10-14, while planning:* the analysis-side families above — `defensives.unused`,
  `defensives.ceiling`, `consumables.never`, `consumables.unused` and `throughput.alignment` —
  are left out of this slice. They carry no `player_slug`: each analyser writes its owner into the
  id in its own way (`defensive_base_ids` mints `<slug>.<ability>`, the consumable analysers the raw
  name, or `name.actor_id` on a clash), and `defensive_base_ids`' own docstring forbids parsing the
  fragment back. Counting them needs those findings to carry the comparison's `player_slug`,
  which is a change to five analysers and its own small slice. The comparison families, which do
  carry it, are all counted.
- *Amended 2026-10-14, while building:* talents are not counted either. `compare.talents` is not
  a judgement family: `comparison/spells.py` mints it under the one id for every compared player
  whatever the outcome — the build could not be compared, it matched, or it differed — so it
  would "fire" in every run and the count would say nothing. Telling the outcomes apart needs
  analyze to mint them under different ids, which moves analyze's own output and is out of this
  slice. Each run's page still states its talent comparison.
- A family is reported when it fired in **at least half of the loaded runs, and in at least 3**.
- Wording uses the existing `quantifier_for` (every, most, about half). The badge is the least
  certain among the findings counted, the rule the night's boss rollups follow.

### 5.2 Consistent directions

A sign count over the comparison tables of every loaded run.

- **The measures:** cast rates on bosses and on trash, buff uptime over the key clock
  (`AuraRow.uptime`), debuff coverage over every enemy (`DebuffRow.uptime`), and stat shares.
- **A run counts for a measure only where that run judged it:** its verdict is `below`, `above` or
  `level`. `unjudged`, `bosses_only`, and any debuff row whose `shared_with` names someone are left
  out, as are every descriptive cell (reach, the trash and boss stretches, per-boss cells). The
  character page never judges what a run declined to.
- **The direction** of a run is ours against `their_median`. An exact tie counts for neither side.
- **A pattern needs:**
  1. at least `MIN_DIRECTION_RUNS` = **6** runs where the measure was judged;
  2. every one of them on the same side;
  3. a median gap across those runs of at least `DIRECTION_RATE_FLOOR` = **10%** relative, for a
     cast rate, or `DIRECTION_SHARE_FLOOR` = **5 points**, for an uptime, a coverage or a stat share.
- **Badge:** `derived`.
- **Why unanimity over six.** A page reads about ninety measures. By chance alone a measure lands
  on one side in every run with probability 2/2ⁿ:

  | Runs | All on one side, by chance | Expected chance patterns over 90 measures |
  | --- | --- | --- |
  | 5 | 6.2% | about 6 |
  | 6 | 3.1% | about 3 |
  | 7 | 1.6% | about 1.4 |
  | 8 | 0.8% | about 0.7 |
  | 7 of 8 | 7.0% | about 6 |

  Unanimity over six keeps the chance patterns near three before the gap floors, which remove the
  tiny consistent differences that make up most of them. "Seven of eight" is not strong enough and
  is not offered. The measures are not independent of each other, so these figures are a guide to
  the rule's strictness, not a significance level the page reports.
- **The floors are chosen numbers, not measured ones**, and the page says so, as the heavy-moment
  finding does for its own. They sit well under the single-run thresholds (`RATE_GAP_MULTIPLE` 1.5
  and `UPTIME_GAP_FRACTION` 15 points) on purpose: this source exists to catch gaps no single run
  could call.
- **Fewer than six loaded runs** withholds the whole source with a `measured` finding saying how
  many loaded, rather than lowering the bar.

### 5.3 The group ledger

The four comparisons every run carries whatever happened — completion time, deaths, time between
packs and kick share — mean nothing as "fired in N runs". They go in a table, one row per run, ours
against the fast runs' median, with a count under each column such as "above the median in 7 of
10". The character's own deaths in each run are a fifth column. The badge is `measured`, and the
ledger makes no claim beyond its counts.
*Amended 2026-10-14, while building:* the ledger ships without the `measured` badge named here. It
is a table of counts of logged figures, not a finding, so nothing in `GroupLedger`, the view model,
the template or `character.json` carries a badge; it still states no verdict.

The four figures are computed today inside `comparison/tempo.py`, and the findings carry them only
as display strings, which nothing may parse back. The build exposes them as a typed measure that
the tempo findings and the ledger both read, so the two can never disagree. A completion time the
level gap withheld stays withheld in the ledger, with the same reason.

### 5.4 Order

Directions first, then repeated judgements, each ordered by how many runs support it and then by
the size of its median gap. Nothing is ranked by seconds, since no seconds are summed.

## 6. Architecture

```
character URL
  └─ urls.parse_character_url ─────────────► CharacterRef(region, realm, name, zone)
adapters/wcl (new queries, dated in wcl-api)
  ├─ ZONE_ENCOUNTERS   worldData.zone → dungeon ids and names, difficulties
  └─ CHARACTER_RUNS    characterData.character → hidden, encounterRankings per dungeon (aliased)
        └─ character_runs.py: JSON → RankedRun(encounter_id, dungeon, level, spec, report_code,
                                              fight_id, start_time_ms, medal)
domain/character/selection.py  (pure) → Selection(chosen, left_out)
for each chosen run:
  └─ analyse_run(...)  lifted out of `analyze`, behaviour unchanged
        writes <code>-<fight>.findings.json and .html, returns RunAnalysis(findings,
        player measures, tempo measures, subject deaths)
domain/character/patterns.py, ledger.py  (pure) → cross-run findings and ledger rows
domain/report/character_model.py, character_build.py (pure) → frozen view model
adapters/render/character.html.j2 + render_character → the page
cli.py `character` → character.json and character.html
```

- **The domain does no I/O.** Selection, patterns and the ledger are pure functions over domain
  objects, tested without the network.
- **The run list is cached for a day, in the reference tier.** It is the character's own data, but
  it changes with every key played, and the permanent tier would freeze it. Each run's own data
  stays in the permanent tier, as `analyze` keeps it.
- **`analyse_run` is extracted first, as its own step.** A test pins `analyze`'s findings file and
  page on a recorded run before the move, and passes unchanged after it. `analyze` then calls the
  extracted function. The extraction targets `analyze` as it stands on main after #57, debuff
  stream included. *Amended 2026-10-14, while planning:* `analyse_run` and `write_run` stay in
  `cli.py`, beside `_samples`, `_fetch_parse_auras` and `_fetch_parse_debuffs`, which `raid` and
  `night` share; moving those is a restructure this slice does not need.
- **The page's tabs:** Summary (narrative, then the patterns), Group (the ledger), Runs (every run
  linked to its report, then the dungeons left out and the runs that failed), Provenance (the
  queries, the chosen numbers, what was withheld, the not-additive warning).
- **One invariant gains a link kind, deliberately.** `test_html_invariants.py` admits fragments,
  Warcraft Logs report links and the icon host. The Runs tab links to `<code>-<fight>.html` beside
  the page. A link is not a load, so "the report loads its icons and nothing else" holds; the
  character page's own invariant test admits same-directory `.html` links and nothing else new.

## 7. The JSON

`character.json` holds the character (region, realm, name, zone id and name, spec), what was asked
for, the chosen runs (dungeon, encounter id, level, timed, report code, fight id, the run's two file
names), the dungeons left out and the runs that failed with their reasons, the chosen numbers of §5,
the ranked-not-additive warning, the findings, and the ledger rows. Every finding carries its badge.

## 8. Cost

- **Selection:** two small queries. Their cost is unmeasured and is recorded in `wcl-api` on the
  first live run.
- **Each run:** what `analyze` costs. A cold one-player run read 107.53 points on 2026-10-08, and
  98.15 on 2026-10-13. A warm one reads about one point.
- **A cold page of eight runs:** about 800 to 900 of the hourly 3600. The command closes with the
  usual breakdown by operation. If the budget runs out, the client already waits for the reset and
  says why.

> **Amended 2026-10-14, after the live run.** The estimates above were low. A cold page of eight
> dungeons on the user's own character cost **1090.57 points**, about **136 a dungeon**, not 800 to
> 900 and not the 98 to 108 a single `analyze` had read. The two selection queries cost **9.01
> points** in all, measured: the zone query 1.00 point, and the one character-runs query 8.01
> points, for eight aliased `encounterRankings`. Two zones were measured, both with eight dungeons,
> and each read 1.00 plus 8.01; whether the selection's cost scales with a zone's dungeon count is
> unconfirmed. The other 1081.56 points are the eight per-run analyses. The dearest operations were
> `EnemyDebuffs` (161 calls, 179.02 points), `Fights` (65 calls, 138.65), `Talents` (48 calls,
> 107.41), `PlayerDetails` (48 calls, 97.00) and `AuraTable` (79 calls, 79.00). A reader planning an
> hour's budget should count about a thousand points for a cold page, nearly a third of the hourly
> 3600, which leaves room for about two more cold pages in the same hour. A page whose runs all fail
> to load is cheap: 38.27 points, the selection queries plus the first query of each failed load.
> The behaviour on a spent budget is untested live: this run never came near it.

## 9. Terms of service

Only the named character's runs are listed and analysed. Each run's references are fetched for that
run's comparison into the one-day tier, exactly as `analyze` fetches them, and the run list expires
after a day too. Nothing accumulates beyond what `analyze` already keeps, and no other character's
history is read. This answers the corpus question `2026-09-08-sampling-decision-brief.md` raises:
the sample per run is unchanged, and the runs added are the user's own.

## 10. Testing and proof

Test-driven throughout.

- **The extraction guard:** `analyze`'s findings file and page pinned on a recorded run, green
  before and after `analyse_run` is lifted out.
- **Unit:**
  - `parse_character_url`: regions, realms with hyphens, names with accents, a zone present or not,
    and a report URL refused;
  - the rankings parser: a rank with no report, a rank with one;
  - selection: the top level, one below, two below refused, the most recent chosen, a dungeon left
    out, the spec rule and `--spec`;
  - patterns at their edges: five runs against six, unanimous against one dissent, a tie, a 9.9%
    gap against 10%, 4.9 points against 5, an `unjudged`, `bosses_only` or shared row excluded, the
    same family under two slugs and two rank indices, the quantifier, the least-certain badge;
  - the ledger: a withheld completion time, the counts under each column;
  - the view-model builder.
- **Page invariants:** a new `test_character_html_invariants.py`, including the same-directory link
  rule and that nothing else new is admitted.
- **Command level:** a `CliRunner` test over an `httpx.MockTransport`.
- **End to end:** `tests/e2e/test_character_e2e.py`, reading the character URL from a new
  `WOWPERF_E2E_CHARACTER` entry in `.env.example`, since no real character name may sit under
  `tests/`. A character with fewer than six qualifying dungeons keeps it cheap and exercises the
  withheld state.
- **The live proof.** Run against the character the session started from and report how often each
  state occurred: patterns of each kind fired, directions withheld, dungeons left out, runs failed.
  Withheld directions cannot occur on a character with eight qualifying dungeons, so a pre-check
  finds a real one with fewer before the work is called done. A state that never occurs is a
  defect.

> **Amended 2026-10-14, after the live run.** Two runs of the command, both on the user's own
> character, one on each of two Mythic+ seasons.
>
> **Run A, the current season, cold cache.** Eight dungeons chosen, eight loaded, none failed, none
> left out; the specialisation was the one with the most ranked runs. It produced 22 findings:
>
> - **Directions, 15** (all derived, all with the quantifier "every"): trash 6, boss 3, buff 5,
>   debuff 1, stat 0.
> - **Repeated judgements, 7**: `compare.spells.trash.rate` 2, `compare.spells.rate` 3,
>   `compare.route.skipped` 1 (measured), `compare.spells.trash.above` 1. The quantifiers seen were
>   "every" (8 of 8), "most" and "about half".
> - **Directions withheld:** no, since eight runs loaded.
> - **Group ledger:** all four columns were compared in 8 of 8 runs. Time was above the median
>   in 8; deaths above in 6 and on the median in 2; downtime above in 7 and below in 1; kick share
>   above in 5 and below in 3. The subject died in none of the eight runs.
>
> **The stat direction never occurred, and that is not a defect of the rule.** The closest case was
> versatility, which sat below the top parses in all eight runs, unanimous, but with a median gap of
> 4.97 points against a floor of 5. The other stats split sides. A gap that reads one side in every
> run and misses the floor by 0.03 is the floor doing its work: it is a chosen number, not a
> measured one (§5.2), and the near miss is no reason to move it to a value that would have let this
> one through. The near miss shows that the stat readings are collected and judged against the
> floor; it does not show a stat direction firing. That firing is covered by the unit test
> `test_a_stat_share_direction_names_the_stat` in `tests/domain/character/test_directions.py`, and
> by nothing live.
>
> **Run B, the previous season, found by a selection-only pre-check.** The pre-check ran the two
> selection queries alone over every zone listing difficulty 10 and found seven zones where fewer
> than six dungeons qualified; what it cost a zone was not itemised. The command was run on one of
> them, an eight-dungeon zone whose selection read 1.00 plus 8.01 points as Run A's did. It chose
> five dungeons and left out three: two for having "no run at +N or +N-1 has a public report" and
> one for having "no ranked run as" the chosen specialisation. All five chosen runs then failed to
> load, each with the API's "This report has been archived" error, a `WclError`: they were listed
> as failed and the command carried on. Zero runs loaded, so **`character.direction.withheld` was
> reached**, reading "0 runs loaded, 6 are needed".
>
> **Reached live across the two runs:** directions of the trash, boss, buff and debuff kinds;
> repeated judgements; the withheld state; a failed run; a left-out dungeon under two reasons; and
> the ledger's above, below and level counts. **Not reached live:** a stat direction (the near miss
> above), and a run failing in mid-command because the budget was spent. The withheld state was
> reached by every run failing rather than by a character with few qualifying dungeons, so the
> path "five loaded, directions withheld, the rest of the page standing" is covered by the unit
> and command-level tests only.
>
> The page of Run A was served over `http.server` and checked: the four tabs switch, all 16 run
> links answer 200, and the ledger reads.

## 11. Documentation, when it ships

- `analyzing-a-run`: a `## The \`character\` command` section; `tests/test_skills.py` adds the
  command to `COMMANDS`.
- `mplus-analysis`: reading a character page — what each kind of statement licenses, the floors,
  and that the ledger states counts and no verdict.
- `wcl-api`: dated rows for every new field, the selection queries' measured cost, and the
  "not frozen" note.
- `CLAUDE.md`: the command table and the overview. `README.md` and `docs/how-it-works.md`.
- `2026-09-03-mplus-postmortem-design.md`: an inline amendment where it defers personal run
  history, naming this design.

## 12. Out of scope

- **Spec knowledge**, the next slice: a dated, sourced file under `data/` relating abilities
  (Infliction of Sorrow per Vampiric Strike, Blood Plague coverage behind it), counted by the same
  rules as §5.2.
- **Resource and proc timing:** runic power over the cap, a proc held before it is spent,
  Vampiric Strikes inside Dancing Rune Weapon. These need aura windows and resource readings this
  command does not fetch.
- **The same-level damage percentile** on each report.
- **Raid zones**, and trends over time.
