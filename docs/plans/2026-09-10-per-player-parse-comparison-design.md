# The Per-Player Parse Comparison (J2) — Design

**Status:** Approved 2026-09-10, not implemented. Phase J of
`2026-09-06-audit-and-improvement-roadmap.md`, second half.

**Authority:** `2026-09-03-mplus-postmortem-design.md` remains the authority on analysers,
badges and refusals; §2.6 (no rotation scoring) and §5.5 (no damage ranking) bind this document
and are not reopened. `2026-09-05-mplus-report-design.md` remains the authority on the view
model's shape. `2026-09-08-sampling-design.md` remains the authority on how a sample is drawn
and when a comparison is withheld; this design draws more samples and changes none of those
rules.

**Companion:** `2026-09-10-per-player-page-design.md` built the sub-tab this fills. Its §13
records what it believed blocked J2; §11 of this document corrects that record where the tree
disagrees with it, and supersedes it.

**Closes roadmap decision 5** — "parse references: for the subject only, as today, or for every
player at the extra quota cost?" The answer is both, chosen at runtime by the reader.

## 1. What this builds

`analyze` gains the ability to run the parse comparison for more than one member of the roster.

Nothing else about the report changes. The per-player page already draws one sub-tab per
player, and each card already carries a slot for comparison rows that only the subject fills
(`src/wowperf/domain/report/players.py`, `spell_and_talent_rows`). J2 fills the slots the reader
asked for, and says plainly why the rest are empty.

The reader chooses the scope and pays for it: themselves, a few teammates, or the whole group.

## 2. What already exists and is not rebuilt

- **The sub-tabs.** One per player, with a slug, a card and a timeline. Built.
- **The comparison itself.** `compare_spells_sample`, `compare_talents` and
  `compare_uptime_sample` already take a player and a sample. Neither what they measure nor how
  they word it changes here.
- **Sampling and withholding.** `SAMPLE_SIZE = 5`, the keystone-gap refusal, the match-rate
  gate, the below-floor fallback to a single reference. Unchanged, applied per player.
- **The card's comparison slot.** `PlayerCard.spell_and_talent_rows` exists and is empty for
  four of five players.
- **The tank and healer question.** Settled by measurement, not by this design:
  `characterRankings(metric: playerscore)` returns rows for tank and healer specialisations,
  measured 2026-09-10 and recorded in `.claude/skills/wcl-api/SKILL.md`. A tank returned 81 rows
  and a healer 75, against 72, 82 and 82 for three damage specialisations — the same range, not
  a degraded one.

## 3. What is not in scope

- **The speed axis.** Route, tempo and confounds are statements about the run. They are fetched
  once and compared once, whoever is being compared.
- **What a comparison says.** J2 changes who it is said about, not the saying.
- **The icon duplication** measured in the per-player design's §12.2 — about 175 KB, 27% of the
  rendered file, a second copy of icons the page already carries as CSS rules. J2 makes the page
  larger and so makes that recovery worth more, because the duplicate layer means every ability
  J2 newly introduces costs its data URI twice. It is still adjacent work: a 662 KB file opens
  instantly from disk and so would a larger one.
- **The deep-link scroll defect** recorded in `2026-09-08-deep-link-scroll-defect.md`.

## 4. The command line

`--player` becomes repeatable. `--all-players` requests the whole roster.

**The default does not change.** With neither flag, `analyze` compares the report owner alone,
costs what it costs today, and produces a report whose four other sub-tabs carry a withheld
comparison. A command whose price rises without being asked is a command that surprises somebody
mid-key, and every existing expectation about a default run stays true.

**The subject is the first `--player` given, or the report owner when none is.** The subject's
card still sorts first, still fills the findings JSON's scalar `"player"`, and is still who the
narrative is about. `--all-players` with no `--player` keeps the report owner as subject, which
means the owner's card opens first even when the reader is someone else; naming a `--player`
fixes it. This is a known wart, accepted in exchange for leaving the subject concept intact.

**The flags combine rather than conflict.** `--player X --all-players` makes X the subject and
compares everyone.

**`--no-compare` still wins.** It skips every reference fetch, and the two flags become inert
rather than an error: a reader who asks for the whole group and then asks for no comparison has
contradicted themselves, and refusing the command teaches them nothing the empty report does not.

**An unknown name still raises the existing roster error**, and with several names given the
message names which one missed rather than the last one checked.

The findings JSON gains a `comparison.players` list — the slugs actually compared — beside the
existing scalar `"player"`. A reader of the JSON can then tell "nobody asked" from "the
leaderboard was empty" without inspecting findings.

## 5. Identity: one slug, two consumers

A finding's identity today is (family, rank). Under J2 it is (family, rank, player), and three
mechanisms key on the id string:

- `COMPARISON_PREFIXES` in `report/players.py` and the nesting rules in `report/ledger.py` are
  `startswith` **prefix** matches. Anything appended to an id survives them; anything prepended
  breaks them.
- `titles_by_id` in `report/build.py` is a plain dict keyed by id. Colliding ids silently
  overwrite, and every "Already counted inside ..." cross-reference then names the wrong player.
- `id="finding-{{ row.finding_id }}"` in `adapters/render/_macros.html.j2`, with the page's own
  `href="#finding-..."` pointers. Colliding ids emit duplicate element ids, which is invalid
  HTML, and a pointer lands on whichever the browser picks.

### 5.1 One slug function

A new pure function in the domain:

```
slugs_by_actor(run) -> dict[int, str]
```

It computes the disambiguated slug for the whole roster once: `player_slug(display_name)` plus
the index that separates `Bríala` from `Briala`. `build_players` stops minting its own and reads
this; the comparison reads the same map.

That agreement is the point. It is what makes `#finding-compare.talents.briala-3` land in the
sub-tab belonging to that same player. Nothing enforces the agreement today because there is
only ever one player to agree about, and the moment the slug becomes load-bearing for finding
ids, two independent computations of it become a defect waiting for a name with an accent in it.

### 5.2 The suffix, and the field

Every parse-family finding carries the slug in two places:

| Today | Under J2 |
| --- | --- |
| `compare.spells.missing.{rank}` | `compare.spells.missing.{rank}.{slug}` |
| `compare.spells.rate.{rank}` | `compare.spells.rate.{rank}.{slug}` |
| `compare.spells.unavailable` | `compare.spells.unavailable.{slug}` |
| `compare.talents` | `compare.talents.{slug}` |
| `compare.uptime.{kind}.{rank}` | `compare.uptime.{kind}.{rank}.{slug}` |
| `compare.uptime.unavailable` | `compare.uptime.unavailable.{slug}` |
| `compare.parse.unavailable` | `compare.parse.unavailable.{slug}` |

`Finding` gains `player_slug: str = ""`, empty on every finding that is not about one player.

The suffix keeps every prefix match working untouched. The field is what the findings JSON and
the card filter read, so neither ever parses a slug back out of a string. The redundancy is
deliberate and has precedent: `ability_name` already duplicates what the title says, for the
stated reason that locating it by parsing would be a guess.

**The speed-axis families are not suffixed.** `compare.route.*`, `compare.tempo.*`,
`compare.downtime`, `compare.deaths`, `compare.interrupts`, `compare.duration`,
`compare.confound.*` and `compare.speed.unavailable` are statements about the run. Giving them a
player would be a lie.

**Ids change on every run, including single-player ones.** `compare.talents` becomes
`compare.talents.<slug>` whether or not anyone asked for a second player. Goldens regenerate, and
a report already on disk has ids the next run will not reproduce. This is the visible cost of
putting the player in the id rather than in a composite key, and it is accepted: the alternative
spellings either leave two id shapes for one family, or turn three string-keyed mechanisms into
two-part keys for no gain a reader can see.

## 6. The split of `compare()`

The seam is already visible in `domain/comparison/service.py`: the `speed` branch is run-level,
the `parse` branch is per-player. J2 makes that explicit rather than adding a loop inside a
function that reads as though it handles one player.

```
class ComparisonSubject(Frozen):
    player: Player
    slug: str
    parse: ParseSample | None
    our_auras: PlayerAuras | None

def compare(
    ours: LoadedRun,
    speed: SpeedSample | None,
    subjects: Sequence[ComparisonSubject],
) -> list[Finding]
```

One entry point, one `rank_findings` over the whole list, and the per-player-ness carried by a
type instead of by an argument convention. The speed branch runs once. The parse branch runs once
per subject, each with its own sample and its own auras. The five comparison modules are
unchanged except that the slug reaches the id they mint.

`PARSE_UNAVAILABLE_ID` in `report/frame.py` stops being an exact-match constant and becomes a
per-player lookup: `section_for` is asked about one player's section at a time.

Parse-family findings all carry `seconds_lost=None`, so ranking leaves them interleaved at the
end of the list in no particular order across players. That is harmless: `build_players` filters
them per card, and each card's rows keep their own relative order.

## 7. Fetching, cost, and partial failure

`_samples` returns one `ParseSample` per requested player, keyed by actor id, and one
`SpeedSample` for the run. `_fetch_parse_auras` runs per subject.

**The cost is not only on the reference side.** `our_auras` is one `AuraTable` for the player
being analysed. Five subjects means five of our own aura fetches, plus each sample member's.

**Self-exclusion applies to every sample.** `our_names` is computed once from our roster and
applied to all of them: a reference that is quietly one of our own characters must be dropped
from a teammate's sample as firmly as from the subject's.

### 7.1 What it costs

- **Measured 2026-09-08:** 83.39 points of 3600 for one player, five speed and five parse
  references, cold cache. Recorded in `.claude/skills/wcl-api/SKILL.md`.
- **Derived:** roughly 165 points more for four further specialisations at `SAMPLE_SIZE = 5`, so
  about 250 of 3600 for `--all-players` — near 7% of an hourly budget this project has never come
  close to exhausting.
- **The derived figure is probably high.** Reference runs cache by report code with no class or
  spec in the key, so a report already loaded for one player's sample costs a second player only
  its aura query. How often that happens is unmeasured.

**The plan must take one real `--all-players` reading** and record in
`.claude/skills/wcl-api/SKILL.md`, with its date, both the total and how many reference loads
were served from another player's sample. The derived 165 stops being the best available figure
the moment that reading exists.

### 7.2 Partial failure

The existing idiom is record and continue, and J2 keeps it. A player whose leaderboard returns
nothing, whose references all fail to load, or who falls below the comparability floor gets a
withheld section carrying the reason the comparison itself gave — exactly as the single-player
path does today. Every candidate weighed is disclosed in Provenance whether or not it loaded.

`BracketMismatch` still stops the command. It means the bracket convention this tool relies on has
changed, which is not a per-player fact and must not be swallowed four times over.

### 7.3 A player nobody asked for

Not the same state as a player whose comparison failed, and it must not read as one.

No finding is emitted for an unrequested player. The reason is a report-written constant, the way
`NO_COMPARISON_RAN` already is in `report/frame.py` — the rule that a withheld section quotes a
finding exists so the report never invents a claim about the API, and "you did not ask for this"
is a statement about the command line, not about a leaderboard.

The consequence matters: **a default run emits exactly the findings it emits today**, and four
cards say so plainly rather than implying an empty leaderboard.

## 8. The page

Each `PlayerCard` carries its own `spell_and_talent` Section instead of sharing one.
`build_players` filters comparison findings by `finding.player_slug == card.slug` rather than by
`is_subject`.

Three states, all already expressible by `Section`:

| State | When | Reason shown |
| --- | --- | --- |
| present | compared, and the comparison found something | — |
| withheld | compared, and the comparison refused | the `compare.parse.unavailable.<slug>` detail |
| withheld | not requested | a report-written constant |

`ReferenceRecord` gains `player_slug: str = ""` so Provenance can group parse candidates by whose
comparison weighed them. The speed candidates keep an empty slug.

Nothing else in the template changes.

## 9. Terms of service

`--all-players` multiplies disclosed reference candidates by up to five — as many as 25 parse
rows in Provenance beside the 5 speed rows.

The posture under RPGLogs §5d is unchanged, and the reason is worth stating rather than assuming.
`ReferenceRecord` carries a link and never a figure, deliberately: a file that tabulates other
players' durations and death counts is the corpus the 24-hour reference cache exists to avoid.
Five samples of five links is still five times nothing tabulated. The reference cache still
expires after a day, and no reference event stream outlives the report that used it.

## 10. What must not break

- **One file, nothing loaded, one inline script.** `tests/adapters/render/test_html_invariants.py`
  enforces every clause and none of them is relaxed here.
- **Every finding carries a badge.**
- **The domain performs no I/O.** `slugs_by_actor` is pure and lives in the domain.
- **No finding reaches the page twice** — and now, no id appears twice either. See §11.1.
- **The narrative contains no digits**, and the LLM computes nothing.
- **No hardcoded season data.**
- **No real character name in `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`,
  `Bríala`, `Кириллица`.

## 11. Corrections to the per-player design's §13

§13 was written before this session and the tree has moved. Two of its three blockers are
resolved and one was mis-diagnosed. This section supersedes it.

### 11.1 The finding-id blocker is real, but the failure is silent

§13 says: "Five players collide, and `test_html_invariants.py:377` fails."

The line is now `:421`. More importantly, that test asserts on the **title**, not the id:

```
assert html.count(f"<h3>{escape(finding.title)}</h3>") == 1, finding.id
```

and `compare.spells.missing.{rank}` titles already carry `our_player.name`. Five players produce
five distinct titles, so the test would pass. It also runs against a fixed fixture; only the
copy at `tests/e2e/test_report_e2e.py` sees real data, and it shares the same title-based blind
spot.

**No test asserts that finding ids are unique.** What colliding ids actually do is overwrite
entries in `titles_by_id`, emit duplicate HTML element ids, and repeat ids in the findings JSON
with no way to tell whose is whose — three silent corruptions, not a red test.

So the blocker stands, but the plan must add the assertion that does not exist, not rely on the
one §13 named.

### 11.2 The tank and healer blocker is cleared

Measured 2026-09-10; see §2.

### 11.3 The rendering question is mostly already answered

§13 treats where a per-player comparison renders as open. `PlayerCard.spell_and_talent_rows`
exists and is filled `if is_subject else ()`. The slot is built; J2 fills it.

## 12. Testing

Ordinary coverage of every new behaviour, plus three tests that exist because of what §11 found:

1. **Finding ids are unique within a report.** One domain test over `compare()` with a
   multi-player roster; one render-level test over the built page. Neither exists today.
2. **The card slug and the finding suffix agree.** This is what makes `#finding-...` land in the
   right sub-tab, and it is the failure mode `slugs_by_actor` exists to prevent — so it needs a
   test that fails if the two are ever computed independently again.
3. **The slug collision case.** A fixture roster holding both `Bríala` and a neighbour reducing
   to the same slug, proving the index still separates them once the slug is load-bearing for
   finding ids.

Beyond those: the flag combinations of §4 including `--no-compare` winning; an unrequested
player's section reading as unrequested rather than as empty; a partial failure leaving other
players' comparisons intact; and one e2e exercising `--all-players` against the real API,
asserting unique ids and that every card either has rows or states a reason. The e2e spends quota
only under `-m e2e`.

Goldens regenerate with
`uv run pytest tests/adapters/render/test_html_invariants.py --golden-update`.

## 13. Open questions

1. **Cross-sample cache hits.** §7.1 derives 165 points and says the true figure is probably
   lower. The plan measures it once; until then no claim about `--all-players` costing under 250
   points may be stated as measured.
2. **Whether five comparisons is more than a reader wants.** Four real runs produced 5, 5, 5 and
   15 parse-family findings for a single player, against whole-report totals of 39 to 52. Four
   more players is +20 typically and +60 at the observed worst, so the report's finding count
   roughly doubles and can more than double. Whether that reads as a richer report or a longer
   one cannot be settled before a real `--all-players` run exists to look at. If it reads badly,
   the lever is `MAX_SPELLS_REPORTED` and `MAX_AURAS_REPORTED` for non-subjects, and that is a
   later change with its own measurement.
