# Night Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `wowperf night <url>` writes one HTML file covering every boss and every pull in a report, navigable by two dropdowns, fetching nothing after the page is opened.

**Architecture:** A new repository pair reads a report's bosses and deepens every attempt with the streams a full pull page needs. A new view-model quartet (`night_model` / `night_frame` / `night_build` / `night.html.j2`) assembles one `RaidReport` per pull with the existing `build_raid_report` and groups them by boss. No analyser is duplicated: if a step needs a new analyser, it belongs in spec B.

**Tech Stack:** Python 3.12, uv, typer, pydantic (`Frozen`), Jinja2, pytest, ruff, mypy (strict).

**Spec:** `docs/plans/2026-09-23-night-report-design.md`

## Global Constraints

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or anything touching network, disk or template. Adapters do that, behind the ports in `src/wowperf/domain/ports.py`.
- **Every finding carries a `confidence` badge** — `measured`, `derived` or `inferred`. A finding without one is a bug.
- **Never invent an API field name.** `.claude/skills/wcl-api/SKILL.md` is the verified reference and every claim in it carries the date it was checked. If a field is not there, verify against the live schema first, then add a dated row.
- **The report loads its icons and nothing else.** One HTML file, no stylesheet link, no `@import`, no remote `src`, exactly one inline script that may only show, hide and highlight. The single exception is icon art at `wow.zamimg.com`. `tests/adapters/render/test_html_invariants.py` enforces both halves.
- **Never delete a test because it is failing.** Raise it with RwlRwlRwlRwl instead.
- **Never put a real character name in `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`. The twenty players on `cW38jmwdnZfbHVL4` are real people: refer to them by class, spec, role or index in code, tests, commit messages and documents.
- **`cW38jmwdnZfbHVL4` fights 2 and 30** are pinned as `WOWPERF_E2E_RAID_KILL` and `WOWPERF_E2E_RAID_WIPE` in `.env.example`. Read them; never repoint them.
- **A new judgement is not done until a live run has exercised it.** Task 11 is not optional.
- **All code files start with two `# ABOUTME: ` lines** (`{# ABOUTME: ... #}` for templates).
- **`uv` is the only toolchain.** In Bash it is off PATH: use `/c/Users/damien/.local/bin/uv.exe`. Bare `git` can be refused by a shell hook: use `/mingw64/bin/git`. `uv run mypy` takes no path arguments.
- **Commit messages:** imperative mood, no `feat:` / `fix:` prefix, plain ASCII, body says why not what, ending `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Never `--no-verify`.

---

## Amendments to the spec

Five things were found while mapping the code this plan has to touch. Each changes what the spec said; the spec is the authority on intent, and these are the corrections of fact.

**1. §8's reuse is true by type and thin by data.** `LoadedProgression.loaded` really is `tuple[LoadedEncounter, ...]` (`src/wowperf/domain/progression.py:177`) and that really is `build_raid_report`'s first argument (`src/wowperf/domain/report/raid_build.py:79`). But `load_progression_attempts` (`src/wowperf/adapters/wcl/repository.py:516`) fetches **two streams an attempt — `Deaths` and `DamageTaken` — and nothing else**, and discards the ability dictionary's icon half on purpose (`repository.py:546`). Handing one of those encounters to `build_raid_report` yields a page with no aura refinement on its death cards, no icons, and an empty Interrupts tab. §8 step 2 therefore cannot be "run the existing progression path"; a new deepening method is required. Task 2 writes it.

**2. A pull's section is a full raid page.** RwlRwlRwlRwl decided 2026-09-23 that each pull renders the real seven-tab page rather than the reduced set the two priced streams would support. The measured cost of a full `raid --all-players` page on a wipe is 65.19 points, and every night pull is wipe-shaped because §5 draws no parse axis, so the arithmetic is roughly 65 a pull rather than the 878 a kill would cost.

**3. Death cards stay trimmed by default, and that is a size decision, not a cost one.** §7 measured a full card at 77 KB and the Deaths tab at 94% of a 2,234 KB page. Nineteen pulls of full cards is near 40 MB in one file, which no browser opens comfortably. So the tier ladder in §6 survives amendment 2 unchanged: trimmed by default (~45 a pull once the other tabs' streams are added), `--deep FIGHT` for a full card, `--no-deaths` for none. Making full cards the default would make `--deep` redundant and the file unusable.

**4. `raid`'s multi-boss refusal is not in `cli.py`.** It is raised in `select_raid_fight` at `src/wowperf/adapters/wcl/ingest.py:104-105`. §4's sentence pointing a reader at `wowperf night` is edited there.

**5. `tests/test_skills.py` needs a structural edit, not just an addition.** `_section_text` (`tests/test_skills.py:51-68`) splits `analyzing-a-run/SKILL.md` on literal headings, and the `progression` branch ends at `"## When it goes wrong"` because it is currently the last command section. Inserting a `night` section after it breaks that split silently — the progression branch would swallow the night prose and the flag comparison would pass for the wrong reason. Task 10 moves the split point.

---

### Task 1: Read a whole report's bosses instead of refusing on them

**Files:**
- Create: `src/wowperf/domain/night.py`
- Modify: `src/wowperf/adapters/wcl/repository.py` (add `load_night` beside `load_progression` at :481)
- Test: `tests/domain/test_night.py`, `tests/adapters/wcl/test_repository_night.py`

**Interfaces:**
- Consumes: `Progression` (`src/wowperf/domain/progression.py:105`), and `load_progression`'s existing machinery — one `FIGHTS_QUERY` call through `self._report`, then `_pick_boss` (`repository.py:135`) and `build_progression`.
- Produces: `Night(Frozen)` with `report_code: str` and `bosses: tuple[Progression, ...]`, and `WclRunRepository.load_night(report_code: str, difficulty: int | None) -> Night`.

**Why this task exists.** `load_progression` refuses when a report holds several bosses (`repository.py:135`: `"This report holds several bosses ({named}); pass --boss"`). That refusal is right for `progression`, whose subject is one boss. `night`'s subject is the report, so it needs the same fight list read the other way: every boss, each as its own `Progression`.

- [ ] **Step 1: Write the failing test for the container**

Create `tests/domain/test_night.py`:

```python
# ABOUTME: Behaviour tests for the Night container: a report's bosses, each as a Progression.
# ABOUTME: The empty report is the case a naive implementation gets wrong, so it is pinned.

from wowperf.domain.night import Night
from wowperf.domain.progression import Progression


def a_boss(encounter_id: int, name: str) -> Progression:
    return Progression(
        report_code="TESTCODE00000000",
        encounter_id=encounter_id,
        boss_name=name,
        difficulty=5,
        size=20,
        phases=(),
        separates_wipes=True,
        attempts=(),
        discarded=(),
    )


def test_a_night_carries_its_bosses_in_the_order_given() -> None:
    night = Night(
        report_code="TESTCODE00000000",
        bosses=(a_boss(3492, "Ula'tek"), a_boss(3420, "Nek'zali")),
    )
    assert tuple(boss.encounter_id for boss in night.bosses) == (3492, 3420)


def test_a_report_with_no_boss_fights_is_an_empty_night_not_an_error() -> None:
    # The command refuses an empty report itself, with a message naming the report.
    # The container stays a container: a type that cannot represent nothing is a
    # type that forces the refusal into the wrong layer.
    night = Night(report_code="TESTCODE00000000", bosses=())
    assert night.bosses == ()
```

Read `src/wowperf/domain/progression.py:105-125` first for `Progression`'s exact field list; if a required field is missing from `a_boss` above, add it with a value that reads as test data, and say so in your report.

- [ ] **Step 2: Run it and watch it fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/test_night.py -v`
Expected: FAIL on the import — `wowperf.domain.night` does not exist.

- [ ] **Step 3: Write the container**

Create `src/wowperf/domain/night.py`:

```python
# ABOUTME: One report read whole: every boss it holds, each as its own Progression.
# ABOUTME: A sibling of Progression -- that one is a boss's attempts, this one a report's bosses.

from wowperf.domain.frozen import Frozen
from wowperf.domain.progression import Progression


class Night(Frozen):
    """Every boss a report holds, in the order its fight list gave them.

    `progression` refuses a report with several bosses because its subject is
    one boss and picking one would analyse a fight nobody asked for. This type
    is the same fight list read the other way: the report is the subject, so
    several bosses is the ordinary case rather than the ambiguous one.

    An empty `bosses` is representable on purpose. A report with no boss fights
    at all is a real thing to be handed, and the refusal belongs in the command,
    where it can name the report, rather than in a constructor that can only
    raise.
    """

    report_code: str
    bosses: tuple[Progression, ...] = ()
```

Confirm `Frozen`'s import path by reading the top of `src/wowperf/domain/progression.py` — use whatever that file imports, not this guess.

- [ ] **Step 4: Run it and watch it pass**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/test_night.py -v`
Expected: both tests pass.

- [ ] **Step 5: Write the failing repository test**

Read `repository.py:481-515` (`load_progression`) and the existing repository tests for the fixture shape they use — do not invent a fake transport. Then add a test asserting that a report whose fight list holds three bosses produces a `Night` with three `Progression`s, in fight-list order, each carrying that boss's own attempts, and that **no exception is raised** where `load_progression` would have refused.

Anchor it on a presence, not an absence: assert the three encounter ids and each one's attempt count, so the test fails if the grouping collapses.

- [ ] **Step 6: Run it and watch it fail, then write `load_night`**

Add to `WclRunRepository`, beside `load_progression`:

```python
    def load_night(self, report_code: str, difficulty: int | None) -> Night:
        """Every boss in one report, each as a Progression, from one fight list.

        `load_progression` reads this same list and then narrows it to one boss,
        refusing when nothing picks one out. This reads it and keeps all of
        them: the report is the subject here, so several bosses is what the
        command is for rather than an ambiguity to refuse.

        One `Fights` query answers the whole report, exactly as it does for
        `load_progression` -- the cost of reading a night's shape does not scale
        with how many bosses it holds. What scales is the deepening, which is
        `load_night_attempts`' business and priced there.
        """
```

Implement it by reading `load_progression`'s body and reusing its fight-list read and its `build_progression` call per boss, rather than by writing a second fight parser. Where `load_progression` calls `_pick_boss`, iterate instead. If `difficulty` is `None`, take each boss's own first fight's difficulty, as `load_progression` does for an explicit `--boss`.

- [ ] **Step 7: Run both test files, then the full gate**

```
/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/test_night.py tests/adapters/wcl/ -v
/c/Users/damien/.local/bin/uv.exe run pytest
/c/Users/damien/.local/bin/uv.exe run ruff check .
/c/Users/damien/.local/bin/uv.exe run mypy
```

- [ ] **Step 8: Commit**

Subject: `Read a report's bosses as a night instead of refusing on them`

---

### Task 2: Deepen every attempt with the streams a pull page needs

**Files:**
- Modify: `src/wowperf/domain/night.py` (add `LoadedNight`)
- Modify: `src/wowperf/adapters/wcl/repository.py` (add `load_night_attempts` beside `load_progression_attempts` at :516)
- Test: `tests/adapters/wcl/test_repository_night.py`

**Interfaces:**
- Consumes: `Night` from Task 1; the existing stream helpers `fetch_all_events`, `DEATHS_QUERY`, `DAMAGE_TAKEN_QUERY` and whatever `load_encounter` uses for enemy casts, interrupts, auras, health samples, healing and casts. **Read `load_encounter` and list its fetches before writing anything.**
- Produces: `LoadedNight(Frozen)` with `night: Night` and `loaded: tuple[LoadedProgression, ...]`, and
  `WclRunRepository.load_night_attempts(night: Night, *, deep_fights: frozenset[int], death_cards: bool) -> LoadedNight`.

**Why this task exists.** Amendment 1. `load_progression_attempts` fetches two streams and is right to: a progression page draws no death card at all. A night pull renders the full raid page, so it needs what `load_encounter` fetches, minus the parse axis, minus the streams a trimmed card does not use.

**The tier ladder, which this method implements:**

| tier | reached by | streams beyond the two | measured basis |
| --- | --- | --- | --- |
| no cards | `death_cards=False` | enemy casts, interrupts | §6 row 1 plus amendment 2 |
| trimmed | the default | the above, plus `AuraTable` | `AuraTable` was 20.00 of the 65.19-point wipe, one call a roster player |
| full | `deep_fights` names the fight | the above, plus `Healing`, health samples, casts | `Healing` was 22.00 of the same 65.19, one call a death |

`AuraTable` is what refines a press into `held` or `faded`. Dropping it collapses all six availability states back to `pressed`, the explicit unknown, and quietly undoes what `docs/plans/2026-09-22-raid-defensive-ceiling-design.md` exists to protect. It is in the trimmed tier for that reason and must not be moved out of it.

- [ ] **Step 1: Read `load_encounter` and write down its fetches**

Before any code: open `src/wowperf/adapters/wcl/repository.py`, find `load_encounter`, and list every query it sends and what field of `LoadedEncounter` each one fills. Put that list in your report. The rest of this task is wrong if that list is wrong, and the tier table above is a design intent that your list either confirms or contradicts — if it contradicts, stop and report rather than reconciling it yourself.

- [ ] **Step 2: Write the failing tier test**

Write a test per tier asserting **which streams were requested**, not only what came back. Count the queries the fake transport saw, by name. A test asserting only that `auras` is non-empty passes against a method that fetches auras in every tier, which is the regression that costs real points.

Three tests:
1. `death_cards=False` sends no `AuraTable`, no `Healing`.
2. the default sends `AuraTable` and no `Healing`.
3. a fight named in `deep_fights` sends `Healing` **for that fight only**, and the others in the same night still send none.

The third is the one that catches a `--deep` that leaks across pulls, which is a whole night at the dearest tier.

- [ ] **Step 3: Run them and watch them fail**

Expected: FAIL on the missing method. If any passes before the method exists, the test is asserting nothing — fix it before continuing.

- [ ] **Step 4: Write `load_night_attempts`**

Model it on `load_progression_attempts` (`repository.py:516`), which is the closest existing shape: one ability-dictionary read for the whole report, then a loop over attempts. Two differences, both deliberate:

- **Keep the icon half.** `load_progression_attempts` writes `ability_names, _icons = self._ability_dictionary(...)` because its page draws no icons. A night pull's death cards and ledger rows do, so keep both halves and put the icons on each `LoadedEncounter`.
- **Fetch by tier**, per the table above, with `deep_fights` consulted per attempt rather than per night.

- [ ] **Step 5: Make one failing pull shrink the night rather than fail it**

Spec §10: *"A single pull failing to deepen shrinks the night rather than failing it, and the
Provenance section names it with the reason"* — the same rule the comparison already follows
for a reference that would not load.

Write the failing test first: a night of three attempts where the second one's stream raises,
and assert that the result carries the other two **and** a record of the failure naming the
fight id and the reason. Assert both halves in the same test. A test that only checks two
attempts survived passes against a method that swallows the failure silently, which is how a
night quietly gets smaller than the report it claims to cover.

Then implement it: catch per attempt, not per night, and collect `FailedPull(fight_id=...,
reason=...)` records on `LoadedNight` for Task 6 to render into Provenance.

Do not catch bare `Exception`. Catch what the existing load paths catch — read the `except`
clause on the `progression` command (`cli.py:1727-1730`) for the exact tuple this project
treats as a load failure.

- [ ] **Step 6: Run the tier tests and the failure test, then the full gate**

- [ ] **Step 7: Commit**

Subject: `Deepen a night's attempts by tier rather than two streams flat`

---

### Task 3: The night view model

**Files:**
- Create: `src/wowperf/domain/report/night_model.py`
- Test: `tests/domain/report/test_night_model.py`

**Interfaces:**
- Consumes: `RaidReport` (`src/wowperf/domain/report/raid_model.py`), `LedgerRow` and the shared card/provenance types it already reuses.
- Produces: `NightReport`, `NightHeader`, `BossSection`, `PullSection`, `FailedPull`, and
  `all_night_ledger_rows(report: NightReport) -> tuple[LedgerRow, ...]`.

`all_night_ledger_rows` is the night's counterpart to `all_raid_ledger_rows`, which
`render_raid` already uses to walk every row for icon addresses (`html.py:154-178`). It walks
every pull's rows plus the page-level rows, and Tasks 6 and 7 both depend on it existing.

**Why a new model rather than a list of `RaidReport`s.** The page needs what no single `RaidReport` carries: which boss a pull belongs to, the order of both dropdowns, which tier each pull was rendered at, and the one page-level disclosure from Task 5. Read `progression_model.py` (125 lines) for how small a sibling model is allowed to be; this one is the same kind of thing.

- [ ] **Step 1: Write the failing model test**

Assert, with a fixture holding two bosses of two pulls each:
- `report.bosses` preserves fight-list order, and each `BossSection.pulls` preserves pull order;
- every `PullSection` carries a `RaidReport` and a `tier` of `"none" | "trimmed" | "deep"`;
- `report.total_pulls` equals the sum over bosses — a figure the page prints, so it gets a test that fails if the grouping loses one.

Separate the two counts in the fixture: give the bosses **different** pull counts (two and three, not two and two), so a builder that reports one boss's count for the whole night cannot pass. A fixture where two quantities happen to be equal cannot tell them apart.

- [ ] **Step 2: Run, fail, write the model, run, pass**

Follow `raid_model.py`'s style: `Frozen` subclasses, docstrings stating what each field is for.

- [ ] **Step 3: Full gate and commit**

Subject: `Add the night page's view model`

---

### Task 4: Disclose the absent parse axis, once for the page

**Files:**
- Create: `src/wowperf/domain/comparison/night_axis.py`
- Test: `tests/domain/comparison/test_night_axis.py`

**Interfaces:**
- Produces: `NOT_DRAWN_ID = "compare.parse.not_drawn"`, `NOT_DRAWN_DETAIL`, and `parse_axis_not_drawn() -> Finding`.

**The settled design (spec §5).** `measured`, drawn **once for the whole page**. It must not reuse `UNAVAILABLE_ID` or `WITHHELD_DETAIL` from `src/wowperf/domain/comparison/parse_axis.py:25,37`: that detail opens *"This attempt did not kill the boss"*, which is true of a wipe and false here — a night page omits the axis on kills too, for an entirely different reason. Putting a wrong cause in front of a reader is the failure §5 exists to prevent.

It must say three things: that `wowperf night` does not draw the parse axis at all; which families are therefore absent, named in one place rather than left as six silences — damage against the board, damage by target, casts a minute, talents, buff uptime, the percentile; and that `wowperf raid --fight N` is what draws them for one pull.

- [ ] **Step 1: Write the failing test**

```python
def test_the_disclosure_gives_the_right_reason_and_not_the_wipe_one() -> None:
    finding = parse_axis_not_drawn()
    assert finding.id == "compare.parse.not_drawn"
    assert finding.confidence is Confidence.MEASURED
    assert finding.seconds_lost is None
    # The reason must be this command's, never the wipe's: a night page omits the
    # axis on kills too, so borrowing that sentence would state a false cause.
    assert "did not kill the boss" not in finding.detail
    assert finding.detail != WITHHELD_DETAIL
    # Every family it stands in for, named where the reader meets the absence.
    for family in ("damage", "casts a minute", "talents", "uptime", "percentile"):
        assert family in finding.detail
    assert "wowperf raid --fight" in finding.detail
```

Import `WITHHELD_DETAIL` from `parse_axis` in the test so the inequality is checked against the real constant rather than a copy that could drift.

- [ ] **Step 2: Run, fail, write it, run, pass**

Write the prose yourself against the three requirements above. Match the register of `WITHHELD_DETAIL`, which is the nearest sibling: plain sentences, no hedging, the reason first.

- [ ] **Step 3: Full gate and commit**

Subject: `Say that a night page draws no parse axis, and why`

---

### Task 5: A trimmed death card, and a note that says which absence this is

**Files:**
- Modify: `src/wowperf/domain/report/deaths.py` (constant beside `NO_TIMELINE_EVENT` at :107; `build_deaths` at :316)
- Modify: `src/wowperf/domain/report/raid_build.py` (`build_raid_report` at :79)
- Test: `tests/domain/report/test_deaths.py`, `tests/domain/report/test_raid_build.py`

**Interfaces:**
- Produces: `TRIMMED_CARD_NOTE` in `deaths.py`; a keyword-only `trimmed: bool = False` on `build_deaths` and on `build_raid_report`, threaded to it.

**Why a parameter and not empty streams.** It was checked: starving the streams does not work. `recap_timeline` draws a timeline from `damage_taken` alone, so a card built from a two-stream encounter still renders rows. Trimming has to be something the builder decides, which is what §7 means by "a builder decision, not new markup".

**Why a second note.** `NO_TIMELINE_EVENT` at `deaths.py:107` reads `"No event in the last seconds."` — a claim about the log: nothing happened. A trimmed card's timeline is absent because this command chose not to build it: a claim about the run. The two look identical on the page and mean opposite things, and a reader who takes one for the other concludes the pull was quiet when it may have been carnage. This is the same mistake as reusing `WITHHELD_DETAIL` in Task 4, in a second place.

- [ ] **Step 1: Write the failing tests**

Two, and the second is the one that matters:

```python
def test_a_trimmed_card_drops_the_timeline_and_the_curve() -> None:
    cards = build_deaths(a_loaded_fight_with_events(), NO_DEFENSIVES, NO_CONSUMABLES,
                         trimmed=True)
    assert cards[0].timeline == ()
    assert cards[0].health_curve is None


def test_a_trimmed_card_says_which_absence_this_is() -> None:
    # The fixture has events, so an untrimmed card would render rows. The note
    # must not claim the log was quiet -- it was not.
    cards = build_deaths(a_loaded_fight_with_events(), NO_DEFENSIVES, NO_CONSUMABLES,
                         trimmed=True)
    assert cards[0].timeline_note == TRIMMED_CARD_NOTE
    assert cards[0].timeline_note != NO_TIMELINE_EVENT
    assert "--deep" in cards[0].timeline_note
```

The fixture must carry real events. A trimmed-card test on an empty fixture cannot distinguish the two notes, because both would be reachable — the exact shape of defect this repository keeps finding.

And the third, guarding the default:

```python
def test_an_untrimmed_card_is_unchanged() -> None:
    cards = build_deaths(a_loaded_fight_with_events(), NO_DEFENSIVES, NO_CONSUMABLES)
    assert cards[0].timeline != ()
    assert cards[0].timeline_note == ""
```

- [ ] **Step 2: Run, watch all three fail for the right reason**

- [ ] **Step 3: Implement**

Add the constant beside `NO_TIMELINE_EVENT`:

```python
TRIMMED_CARD_NOTE = (
    "This card is trimmed: the timeline and health curve were not built for this pull. "
    "Re-run with --deep <fight> to render them."
)
"""Why a card has no timeline, when the reason is us rather than the log.

`NO_TIMELINE_EVENT` says the log recorded nothing in the window. This says the
run declined to build it. They look the same on the page and mean opposite
things, and a reader who takes this one for that concludes the pull was quiet.
"""
```

Then thread `trimmed` through `build_deaths` (`deaths.py:316`) so that when it is set, `timeline` is `()`, `health_curve` is `None`, and `timeline_note` is `TRIMMED_CARD_NOTE`. Do not compute the timeline and discard it — the point of the tier is not doing the work.

Thread the same keyword through `build_raid_report` (`raid_build.py:79`) to its `build_deaths` call.

- [ ] **Step 4: Run, pass**

- [ ] **Step 5: Prove the new behaviour is not vacuous**

In a throwaway process — never editing the repository — make `trimmed` always `False` and confirm the two trimmed tests fail; then make it always `True` and confirm the untrimmed test fails. Report both. A tier flag that no test can distinguish is a tier that will silently stop working.

- [ ] **Step 6: Check the raid golden**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/adapters/render/ -q`
Expected: **unchanged**. `trimmed` defaults to `False`, so no existing page moves. If the golden moves, stop and report — it means the default changed.

- [ ] **Step 7: Full gate and commit**

Subject: `Let a death card be trimmed, and say which absence that is`

---

### Task 6: The frame and the builder

**Files:**
- Create: `src/wowperf/domain/report/night_frame.py`
- Create: `src/wowperf/domain/report/night_build.py`
- Test: `tests/domain/report/test_night_build.py`

**Interfaces:**
- Consumes: `LoadedNight` (Task 2), `NightReport` and friends (Task 3), `parse_axis_not_drawn` (Task 4), the `trimmed` keyword (Task 5), and `build_raid_report` (`raid_build.py:79`).
- Produces: `build_night_header(loaded: LoadedNight) -> NightHeader` and
  `build_night_report(loaded: LoadedNight, findings_by_fight: Mapping[int, Sequence[Finding]], fetched_at: str, defensives: Defensives, consumables: Consumables, roles: Roles, deep_fights: frozenset[int], death_cards: bool, externals: Externals = Externals(), self_resurrections: SelfResurrections = SelfResurrections()) -> NightReport`.

**The shape, from spec §8.** For each boss, for each loaded attempt, call `build_raid_report` with the parse axis off and the card tier chosen per pull. No analyser is duplicated; if a step here needs a new analyser, it belongs in spec B and you should stop and report rather than writing one.

**Two things `build_raid_report` needs that a night page has no obvious source for.** Read its signature at `raid_build.py:79` before starting:

- **`subject: Player`.** A night page names no player. Use the report owner: `Encounter.owner_name` (`src/wowperf/domain/encounter.py:35-62`) matched against that pull's roster, falling back to the first player in roster order when the owner is not on it. Whatever you choose, it is a decision a test must pin, because "whose card opens the Players tab" is visible on every pull.
- **`compared_slugs: frozenset[str] | None`.** Pass `None`. That is what "no comparison was drawn" already means to the raid builder; an empty frozenset means "a comparison ran and matched nobody", which is a different and false claim.

- [ ] **Step 1: Write the failing builder tests**

Four, each pinning one decision:

```python
def test_every_pull_is_built_and_grouped_under_its_own_boss() -> None:
    # Two bosses with different pull counts, so a builder that reports one
    # boss's count for the night cannot pass by coincidence.
    report = build_night_report(a_night(bosses=(2, 3)), NO_FINDINGS, FETCHED,
                                NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
                                deep_fights=frozenset(), death_cards=True)
    assert tuple(len(boss.pulls) for boss in report.bosses) == (2, 3)
    assert report.total_pulls == 5


def test_a_pull_named_by_deep_is_the_only_one_built_deep() -> None:
    night = a_night(bosses=(3,))
    named = night.night.bosses[0].attempts[1].fight_id
    report = build_night_report(night, NO_FINDINGS, FETCHED, NO_DEFENSIVES,
                                NO_CONSUMABLES, NO_ROLES,
                                deep_fights=frozenset({named}), death_cards=True)
    tiers = tuple(pull.tier for pull in report.bosses[0].pulls)
    assert tiers == ("trimmed", "deep", "trimmed")


def test_no_death_cards_leaves_every_pull_without_one() -> None:
    report = build_night_report(a_night(bosses=(2,)), NO_FINDINGS, FETCHED,
                                NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
                                deep_fights=frozenset(), death_cards=False)
    assert all(pull.report.deaths == () for pull in report.bosses[0].pulls)
    assert all(pull.tier == "none" for pull in report.bosses[0].pulls)


def test_the_page_carries_the_absent_axis_disclosure_exactly_once() -> None:
    report = build_night_report(a_night(bosses=(2, 3)), NO_FINDINGS, FETCHED,
                                NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
                                deep_fights=frozenset(), death_cards=True)
    ids = [row.id for row in all_night_ledger_rows(report)]
    assert ids.count("compare.parse.not_drawn") == 1
```

The second test asserts the tier of *every* pull, not just the named one. Asserting only that the named pull is deep passes against a builder that deepens all of them, which is the whole night at the dearest tier and the most expensive regression this feature can have.

- [ ] **Step 2: Run, watch all four fail**

- [ ] **Step 3: Write the frame, then the builder**

`night_frame.py` first — the header, modelled on `progression_frame.py:24` (`build_progression_header`). It carries the report code, how many bosses and pulls, the tier the run used and the fetch time.

Then `night_build.py`, modelled on `progression_build.py:34`. Keep it near that file's size: the work is grouping and delegation, and anything long here is probably an analyser that belongs in spec B.

- [ ] **Step 4: Run, pass**

- [ ] **Step 5: Name every pull that failed to deepen, in Provenance**

Task 2 collected `FailedPull` records rather than failing the night. They are useless unless
the page shows them: a night that is quietly smaller than the report it names is worse than
one that refused outright, because nothing on the page says a pull is missing.

Failing test first: a `LoadedNight` carrying one `FailedPull` produces a report whose
provenance names that fight id and its reason, and whose `total_pulls` counts the pulls that
loaded rather than the attempts that existed. Assert both numbers in the same test — the
count and the note — so a builder that hides the failure by counting optimistically cannot
pass.

- [ ] **Step 6: Full gate and commit**

Subject: `Assemble a night page from the existing raid builder`

---

### Task 7: The page, and two dropdowns that only show and hide

**Files:**
- Create: `src/wowperf/adapters/render/night.html.j2`
- Modify: `src/wowperf/adapters/render/html.py` (add `render_night` beside `render_progression` at :181)
- Test: `tests/adapters/render/test_night_html_invariants.py`

**Interfaces:**
- Consumes: `NightReport`; the existing partials the raid page composes — `_raid_summary.html.j2`, `_raid_mechanics.html.j2`, `_deaths.html.j2`, `_interrupts.html.j2`, `_players.html.j2`, `_raid_provenance.html.j2`.
- Produces: `def render_night(report: NightReport, icons: CdnIcons | None = None) -> str:` and `NIGHT_TEMPLATE_NAME = "night.html.j2"`.

**The controls, settled in spec §3.** One boss `<select>`, and **one pull `<select>` per boss**. Choosing a boss shows that boss's own pull control and hides the others. The alternative — one pull control holding every pull, with options hidden or disabled as the boss changes — asks the script to manipulate `<option>` elements, which browsers handle inconsistently and which sits closer to the line the invariant draws. Per-boss controls keep the script to showing, hiding and highlighting, which is all it is allowed to do.

`raid.html.j2` is 62 lines because it composes partials. `night.html.j2` should be the same kind of file: a skeleton, the two controls, and a loop that includes the raid partials once per pull. If it grows past roughly a hundred lines, something that belongs in the builder has leaked into the template — stop and report.

- [ ] **Step 1: Write the failing invariant tests**

Model the file on `tests/adapters/render/test_raid_html_invariants.py`. Assert:
- exactly one `<script>`, with none of `FORBIDDEN_IN_SCRIPT` in its body — reuse that constant from the existing invariant test rather than retyping the list;
- no `<link rel=`, no `@import`, no `src="http...`;
- every `url(...)` address starts with `ICON_HOST`;
- one `<select>` for bosses, and exactly one pull `<select>` per boss;
- the script contains no `createElement`, no `innerHTML`, and no `disabled` — the three ways an option-manipulating implementation would give itself away.

That last assertion is the one that pins spec §3's decision rather than leaving it as prose.

- [ ] **Step 2: Run, fail, write the template and `render_night`**

`render_night` follows `render_raid` (`html.py:154-178`) for its icon walk. A night page carries deaths, ledger rows, players and grid columns across many pulls, so the address map has to be gathered over every pull rather than one — read `_icon_addresses`' docstring before deciding how.

- [ ] **Step 3: Run, pass**

- [ ] **Step 4: Full gate and commit**

Subject: `Render a night as one page behind two dropdowns`

---

### Task 8: A golden page, and a byte budget that can fail

**Files:**
- Modify: `tests/adapters/render/test_night_html_invariants.py`
- Create: `tests/adapters/render/golden/night.html`

**Why a byte budget.** Size is a design constraint here rather than an accident: §7's whole tier ladder exists because a death card is 77 KB and the Deaths tab is 94% of a raid page. Without a test, a future card gains a field and nobody notices until a 40 MB file lands on someone's disk.

- [ ] **Step 1: Write the golden test**

Copy the shape from `test_raid_html_invariants.py:1581-1590` exactly, including the message telling the reader to read the diff before regenerating:

```python
NIGHT_GOLDEN = Path(__file__).parent / "golden" / "night.html"


def test_the_rendered_night_page_matches_the_golden_file(pytestconfig: pytest.Config) -> None:
    html = golden_night_html()
    if pytestconfig.getoption("--golden-update"):
        NIGHT_GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        NIGHT_GOLDEN.write_text(html, encoding="utf-8")
        pytest.skip("golden file rewritten")
    assert html == NIGHT_GOLDEN.read_text(encoding="utf-8"), (
        "The rendered night report changed. Read the diff, then regenerate with "
        "`uv run pytest tests/adapters/render/test_night_html_invariants.py --golden-update`."
    )
```

- [ ] **Step 2: Write the byte-budget test**

```python
def test_a_trimmed_night_stays_inside_its_byte_budget() -> None:
    # Two bosses, three pulls each, one death apiece. The budget is deliberately
    # close to the real figure: a budget with room to spare is a test that cannot
    # fail until the damage is done.
    html = golden_night_html()
    assert len(html.encode("utf-8")) < TRIMMED_NIGHT_BUDGET_BYTES


def test_the_budget_would_catch_a_full_card_regression() -> None:
    # The same fixture at the deep tier must exceed the trimmed budget. Without
    # this, a builder that quietly ignores the tier passes the budget test by
    # rendering a small page for the wrong reason.
    html = golden_night_html(deep_every_pull=True)
    assert len(html.encode("utf-8")) > TRIMMED_NIGHT_BUDGET_BYTES
```

Set `TRIMMED_NIGHT_BUDGET_BYTES` from the figure the fixture actually produces, rounded up by a small margin, and put the measured number and the date in a comment beside it. Do not guess it: render the fixture, read the size, then write the constant.

- [ ] **Step 3: Regenerate the golden after reading the diff**

Run the suite first and read what the golden test prints. Then:
`/c/Users/damien/.local/bin/uv.exe run pytest tests/adapters/render/test_night_html_invariants.py --golden-update`

- [ ] **Step 4: Full gate and commit**

Subject: `Pin the night page with a golden and a byte budget`

---

### Task 9: The command

**Files:**
- Modify: `src/wowperf/cli.py` (a `night` command after `progression` at :1686-1794)
- Modify: `src/wowperf/adapters/wcl/ingest.py` (the refusal at :104-105)
- Test: `tests/test_cli_night.py`

**Note on the file.** `cli.py` is 1798 lines. Follow the `progression` command's shape closely and add nothing to the module beyond the command itself and any constant it needs. If you find yourself wanting to refactor the file, don't — mention it in your report instead.

**The command, from spec §4:**

```
wowperf night <url> [--deep FIGHT]... [--no-deaths] [--difficulty N] [--cache-dir DIR] [--out DIR]
```

Writes `<code>.night.json` and `<code>.night.html` under `--out`.

- [ ] **Step 1: Write the failing CLI tests**

Use `CliRunner` as `tests/test_skills.py:71-83` does. Assert:
- `--deep` and `--no-deaths` together exits non-zero and the message names **both** flags (spec §10);
- `--deep` naming a fight id not in the report exits non-zero naming the ids that are;
- a report with no boss fights exits non-zero with a message naming the report;
- a successful run writes both files at the documented names.

- [ ] **Step 2: Run, fail, write the command**

Copy the `progression` command's structure verbatim as the skeleton — the stdout reconfigure, the try/except around the load, the separate try/except around each write, the `_quota_sentence` and `_echo_cost_breakdown` at the end — and change only what differs. Those guards exist for reasons its comments record; do not collapse them.

The JSON payload carries the report metadata, a list of bosses with their findings, and a list of pulls each carrying that pull's findings, in the same finding shape the other three commands write, so anything reading a findings file keeps working.

- [ ] **Step 3: Point the raid refusal at the new command**

`src/wowperf/adapters/wcl/ingest.py:104-105` currently reads:

```python
        raise IngestError(f"This report holds several boss fights ({ids}); pass --fight")
```

Extend the message to name `wowperf night` as what reads the whole report. Keep `pass --fight` first: a reader who wanted one fight should not have to read past an alternative to find the answer. Update whichever test pins that string — find it before you change it.

- [ ] **Step 4: Run, pass, full gate**

- [ ] **Step 5: Commit**

Subject: `Add the night command`

---

### Task 10: The documents, and the test that reads them

**Files:**
- Modify: `.claude/skills/analyzing-a-run/SKILL.md` (a `## The `night` command` section after :165)
- Modify: `tests/test_skills.py` (`COMMANDS` at :35, `_section_text` at :51-68)
- Modify: `CLAUDE.md`, `README.md` (the command table and the §13 reword)

**Amendment 5, which is the trap in this task.** `_section_text`'s `progression` branch ends at `"## When it goes wrong"` because `progression` is currently the last command section. Inserting a `night` section after it means the progression branch swallows the night prose, and the flag comparison then passes for the wrong reason. Move the progression split point to `"## The `night` command"` in the same edit.

- [ ] **Step 1: Write the failing test first**

Add `"night"` to `COMMANDS` (`tests/test_skills.py:35`) and run the suite. It fails: there is no night section for `_section_text` to find. That failure is the test doing its job, and it is the RED step for this task.

- [ ] **Step 2: Move the progression split point and add the night branch**

```python
    if command == "progression":
        return text.split("## The `progression` command")[1].split("## The `night` command")[0]
    if command == "night":
        return text.split("## The `night` command")[1].split("## When it goes wrong")[0]
```

- [ ] **Step 3: Write the skill section**

Match the `progression` section's paragraph shape (SKILL.md:150-165): what it is a sibling of and why; what each flag does and how they relate; which sibling flags are **not** offered and why; the exact output filenames; the page's shape and what it deliberately leaves to another command.

Name every real flag: `--deep`, `--no-deaths`, `--difficulty`, `--cache-dir`, `--out`. The test compares both directions, so a flag named in prose that the command does not offer fails just as loudly as one offered and undocumented.

Say plainly that it draws no parse axis, and that `wowperf raid --fight N` is what does.

- [ ] **Step 4: Reword "a whole night" where it now collides**

Spec §13: `progression` is described as covering "a whole night of attempts at one boss" in `CLAUDE.md`, `README.md` and `.claude/skills/analyzing-a-run/SKILL.md`. Those must say **every attempt at one boss**, which is both more precise and free of the collision with the new command's name. Find every occurrence before editing; there may be more than the three the spec names.

Add `night` to the command table in `CLAUDE.md` and `README.md`, and to README's quota table once Task 11 has measured it — not before, because that table carries measured figures and nothing else.

- [ ] **Step 5: Run the skill tests, then the full gate**

`/c/Users/damien/.local/bin/uv.exe run pytest tests/test_skills.py -v`

- [ ] **Step 6: Commit**

Subject: `Document the night command where the tests can read it`

---

### Task 11: Exercise it on a real report

**Files:**
- Create: `tests/e2e/test_night_e2e.py`
- Modify: `README.md` (the quota table, with today's measured figure)

**This task is not optional.** A new judgement is not done until a live run has exercised it, and a state that never occurs is a defect rather than a quiet success. Every prior slice in this repository found its worst defect here, with the whole offline suite green.

**The report, settled in spec §11.** `cW38jmwdnZfbHVL4`, the whole thing: eight bosses, nineteen boss fights, recorded from a verified live read in `tests/e2e/test_progression_e2e.py`'s header. It runs with `--no-deaths`. At the trimmed default, nineteen fights cost roughly 420 points — an eighth of the hourly budget for one test run, which is the kind of price that gets a suite quietly stopped from running. `WOWPERF_E2E_RAID_KILL` and `WOWPERF_E2E_RAID_WIPE` are read along with the rest and never repointed.

The twenty players on that report are real people. Assert on counts, shapes and uniqueness only, never on a name.

- [ ] **Step 1: Write the e2e**

Model it on `tests/e2e/test_progression_e2e.py`, including its header comment recording what was verified live and when. Assert the boss count, the pull count per boss, that every pull carries a `RaidReport`, that `compare.parse.not_drawn` appears exactly once, and that every pull's tier is `"none"` under `--no-deaths`.

- [ ] **Step 2: Run the whole command live, at the default tier, once**

```
/c/Users/damien/.local/bin/uv.exe run wowperf night cW38jmwdnZfbHVL4
```

Record from its own output: the points spent, the full breakdown dearest-operation-first, the byte size of the written HTML, and the number of bosses and pulls. These are measurements, not projections — §6's table is arithmetic over one reading and this is the first real one.

- [ ] **Step 3: Report the distribution of every state the page can reach**

Read the findings JSON, never the HTML — that is a project invariant. Report how often each card tier occurred, how many pulls carried death cards, and how many availability states appeared across the whole night. **A state that never occurs is a defect, not a quiet success.** If `held` or `faded` render zero times across nineteen fights, say so and stop: that is the failure `docs/plans/2026-09-22-raid-defensive-ceiling-design.md` exists to catch, and it has happened before with a green suite.

- [ ] **Step 4: Open the page and check the controls work**

Serve `out/` over `python -m http.server` and open the page — a local file loads as a snapshot with inert fragments, so the dropdowns will not work from `file://`. Confirm that choosing a boss changes the visible pull control, and that choosing a pull changes the visible section.

- [ ] **Step 5: Put the measured figures in the documents**

Add the night row to README's quota table with the figure Step 2 measured, and a dated reading to `.claude/skills/wcl-api/SKILL.md` with its full breakdown and its conditions — one reading of one report on one day, as every row in that file is.

If the measured cost differs materially from §6's projection, amend §6 in the design with the real number and say which way it moved. The projection was arithmetic over one wipe; this is the first measurement of the command itself.

- [ ] **Step 6: Commit**

Subject: `Exercise the night command on a real report and record what it cost`

---

## What this plan deliberately does not build

- **The three cross-pull analyser families — spec B.** What keeps killing us across a boss's pulls; who keeps dying and with what available; whether the raid is improving. They need this container to display them and are new domain work rather than reuse. If a task here seems to need a new analyser, that is the signal it belongs in B: stop and report.
- **Any parse-axis comparison.** Spec §5.
- **Any narrative.** This command writes none, so the digit ban and the narrative rules do not apply to it.
- **Any claim that one raider's action caused another's death**, which remains unbuilt and undesigned across the whole project.
