# Progression Layer 3 and the Report — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Say what the best attempt of a night did differently, and render the whole night as one self-contained five-tab HTML page.

**Architecture:** Layer 3 is one new analyser module reading the attempts Layer 2 already deepened — no new fetch, no new event stream, no new field on any aggregate. The page is slice 2's shape a third time: a frozen view model, a pure builder under `src/wowperf/domain/report/progression_*.py`, and Jinja templates that loop and decide nothing. The Attempts tab's chart is SVG whose every coordinate is computed in the builder, exactly as the keystone route timeline is.

**Tech Stack:** Python 3.12, pydantic frozen models, Jinja2, typer, `uv` as the only toolchain.

**Spec:** `docs/plans/2026-09-16-progression-analysis-design.md` — §5.3 (Layer 3), §6 (ranking), §8 (the report), §10 (testing). Plan 1 built §4 and §5.1; plan 2 built §5.2 and the per-attempt fetch.

---

## Global Constraints

Copied verbatim from the spec and from CLAUDE.md. Every task's requirements implicitly include this section.

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or anything else that touches the network, the disk, or a template.
- **Every finding carries a confidence badge** — `measured`, `derived`, or `inferred`. A finding without one is a bug.
- **The report loads its icons and nothing else.** One HTML file with no stylesheet link, no `@import`, no remote `src`, and exactly one inline script. That script may show, hide and highlight what is already on the page; it may not fetch, write text, or read storage.
- **Every printed percentage names which one it is** (§2.4). `fightPercentage` is the encounter's progress remaining; `bossPercentage` is the boss's health; they diverge 3 to 8 points. `Progression.uses_boss_health` is the single place the scale is chosen, and every label reads it rather than deciding again.
- **`fightPercentage` counts down.** A kill reads about 0.01 and an instant wipe reads 100. A bar drawn from it without inverting shows the worst attempt as the tallest.
- **Phase colouring and every phase claim are gated on `separates_wipes`** (§8, §2.2).
- **The page never redraws one fight's anatomy.** That is `wowperf raid --fight N`'s work and it already does it. Keeping the two pages from becoming duplicate templates is a CLAUDE.md prohibition, not a preference.
- **The tab mechanism is two hand-written halves matched only by string equality.** `data-tab-for="tab-X"` and `data-tab-panel="main" id="tab-X"`. Nothing loops or counts them; the invariant tests that pin the id set are what make it safe, and the progression page needs its own.
- **No assertion may survive deleting the arithmetic or the string it claims to check.** Every real defect slices 1 to 3 shipped into review was a test that could not have failed.
- **Never put a real character name in `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`, `Bríala` and `Кириллица`.
- **The twenty players on report `cW38jmwdnZfbHVL4` are real people.** Refer to them by class, spec, role or index — in code, in tests, in commit messages and in documents.
- **Never accumulate a corpus of other players' logs.** RPGLogs terms §5d.
- **The LLM never computes a number.** Every metric comes from tested Python.
- Findings are **ranked, not additive** — a progression findings file has no seconds to sum.
- `uv` is the only toolchain. The gate is `uv run pytest`, `uv run ruff check .`, `uv run mypy`. Line length 100, ruff selects `E, F, I, UP, B`, mypy `strict = true` over `src` and `tests`.
- Every file starts with two `# ABOUTME: ` lines.
- **NEVER USE `--no-verify` WHEN COMMITTING.**

---

## What this plan settled before it was written

**The opening measurement is open item 4 — whether a session gap should split a series or merely be declared (§9.6).** Plan 2's lesson was that the measurement decides which tasks exist, so it ran first.

**Measured 2026-09-16 over this project's own response cache.** 295 cached responses; 24 of them carry a `fights` list; 4 distinct reports hold raid fights with both a start and an end time. Grouping those into series by `(encounterID, difficulty)` gives 9 series with two or more timed attempts and **59 within-series gaps**, measured end-of-one-attempt to start-of-the-next:

| | n | min | p50 | p90 | max |
| --- | --- | --- | --- | --- | --- |
| Within a series | 59 | 45s | 143s | 701s | **6281s (1.74h)** |
| Between consecutive raid fights of one report | 71 | 45s | 168s | 800s | **10572s (2.94h)** |

**Nothing in this population is a second session.** Two within-series gaps exceed half an hour (1.74h and 1.39h, both on one encounter of report `xBDdYAjbRFqWKC8n`, whose cached fights carry no `difficulty` at all — so those two may be a difficulty switch inside one evening rather than a break). Not one gap in either column reaches two hours within a series or three hours across a report. An overnight boundary would be eight hours or more.

**Ruling: the session-gap declaration is cut from this plan.** A threshold above 2.94h would never fire on any data this project has seen; one below it would fire on an ordinary evening's break and call it a second night. That is the same shape as plan 2's player-sourced cut: a feature with no positive control is not shipped behind a hedge. Open item 4 stays open with this dated negative reading, and the population's weakness is part of the reading — 4 reports is small, and three of the four are this project's own probe reports. A genuinely multi-session report turning up reopens it.

**A second ruling, from reading the code rather than measuring it: the page must not use `Encounter.outcome`.** That property returns `f"wiped at {self.fight_percentage:.1f}%"` — a printed percentage that does not name its scale, against the constraint above. It has no production consumer today (`RaidHeader.outcome` is built separately in `raid_frame.py`), so it is dead code with a latent defect rather than a live one. This plan does not fix it, because fixing it would change slice 2's meaning for no reason this plan has; it simply does not reach for it. The Attempts tab computes its own depth column through `remaining_percent` and names the scale once in the column header. **This is recorded as a known gap below.**

---

## File Structure

**New, under `src/wowperf/domain/`:**

| File | Responsibility |
| --- | --- |
| `analysis/progression_best.py` | Layer 3: the two findings comparing the deepest attempt against the rest. |
| `report/progression_model.py` | The view model: every judgement the five-tab page makes. |
| `report/progression_frame.py` | The header, and one row per attempt for the Attempts table. |
| `report/progression_chart.py` | The Attempts chart's SVG geometry, in viewBox units. |
| `report/progression_ledger.py` | Which tab each `progression.*` family's rows land in. |
| `report/progression_build.py` | Assembles the view model from a `LoadedProgression` and its findings. |

**New, under `src/wowperf/adapters/render/`:**

| File | Responsibility |
| --- | --- |
| `progression.html.j2` | Document skeleton: header, five tab panels, one inline script. |
| `_progression_summary.html.j2` | Summary panel. |
| `_progression_attempts.html.j2` | Attempts panel: the chart, the table, the rows. |
| `_progression_repeats.html.j2` | Repeats panel. |
| `_progression_best.html.j2` | Best attempt panel. |
| `_progression_provenance.html.j2` | Provenance panel. |

**Modified:**

| File | Change |
| --- | --- |
| `src/wowperf/adapters/render/html.py` | `render_progression`, mirroring `render_raid`. |
| `src/wowperf/adapters/render/report.css.j2` | The Attempts chart's own classes. |
| `src/wowperf/cli.py` | `progression` writes the HTML beside the JSON. |
| `CLAUDE.md` | The command table's `progression` row, and the repository overview's page list. |

**New tests:** `tests/domain/analysis/test_progression_best.py`, `tests/domain/report/test_progression_frame.py`, `tests/domain/report/test_progression_chart.py`, `tests/domain/report/test_progression_ledger.py`, `tests/domain/report/test_progression_build.py`, `tests/adapters/render/test_progression_html_invariants.py`, `tests/adapters/render/golden/progression.html`.

---

## Task 1: Layer 3 — the deepest attempt's death count

**Files:**
- Create: `src/wowperf/domain/analysis/progression_best.py`
- Test: `tests/domain/analysis/test_progression_best.py`

**Interfaces:**
- Consumes: `LoadedProgression` (`attempts_with_events`, `deepest_loaded`), `LoadedEncounter` (`deaths`, `players`, `encounter`), `Finding`, `Confidence`.
- Produces: `roster_deaths(one: LoadedEncounter) -> int`, `best_deaths(series: LoadedProgression) -> Finding | None`, `raid_invocation(one: LoadedEncounter) -> str`, `MIN_OTHER_ATTEMPTS = 2`.

**Context:** §5.3 says Layer 3 names what the deepest attempt did differently, by internal comparison only, and that "where a reader wants the anatomy, the finding carries the `wowperf raid --fight N` invocation that renders it". This task is the first of the two findings that layer emits.

- [ ] **Step 1: Write the failing tests**

```python
# ABOUTME: Layer 3's claims: what the deepest attempt of a night did differently.
# ABOUTME: Internal comparison only -- no reference run, and never a named player.

from wowperf.domain.analysis.progression_best import best_deaths, roster_deaths
from wowperf.domain.findings import Confidence
from wowperf.domain.progression import LoadedProgression

from tests.domain.progression_fixtures import a_loaded_attempt, a_loaded_series, a_series


def test_a_deaths_count_ignores_an_actor_who_is_not_on_the_roster() -> None:
    """A pet or an unidentified actor dying is not a roster player's death.

    The same filter `_first_death_ms` applies, for the same reason: three
    analysers must agree about which deaths count.
    """
    one = a_loaded_attempt(3, deaths_after_ms=(1_000, 2_000, 3_000))

    # `a_loaded_attempt` deals every death to actor id 1 when no roster is
    # given, and `_DEFAULT_PLAYER` is that one actor, so all three count.
    assert roster_deaths(one) == 3

    orphan = a_loaded_attempt(4, deaths_after_ms=(1_000,))
    stripped = orphan.model_copy(
        update={"encounter": orphan.encounter.model_copy(update={"players": ()})}
    )
    assert roster_deaths(stripped) == 0


def test_the_best_attempt_losing_fewer_players_is_stated_with_both_figures() -> None:
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(1_000, 2_000))
    others = [
        a_loaded_attempt(2, remaining=60.0, deaths_after_ms=tuple(range(1_000, 10_000, 1_000))),
        a_loaded_attempt(3, remaining=70.0, deaths_after_ms=tuple(range(1_000, 10_000, 1_000))),
        a_loaded_attempt(4, remaining=80.0, deaths_after_ms=tuple(range(1_000, 12_000, 1_000))),
    ]

    finding = best_deaths(a_loaded_series(deepest, *others))

    assert finding is not None
    assert finding.id == "progression.best.deaths"
    # Two deaths on the deepest attempt, a median of 9 across the other three.
    assert "2" in finding.title
    assert "9" in finding.title
    assert finding.confidence is Confidence.MEASURED
    assert "wowperf raid abc123 --fight 1" in finding.detail


def test_the_best_attempt_losing_more_players_is_said_rather_than_hidden() -> None:
    """The best attempt is not always the cleanest, and that is worth reading.

    A finding that only speaks when the deepest attempt looks good is a finding
    that flatters the night rather than measuring it.
    """
    deepest = a_loaded_attempt(
        1, remaining=10.0, deaths_after_ms=tuple(range(1_000, 9_000, 1_000))
    )
    others = [
        a_loaded_attempt(2, remaining=60.0, deaths_after_ms=(1_000, 2_000)),
        a_loaded_attempt(3, remaining=70.0, deaths_after_ms=(1_000, 2_000)),
    ]

    finding = best_deaths(a_loaded_series(deepest, *others))

    assert finding is not None
    assert "8" in finding.title
    assert "2" in finding.title
    assert "more" in finding.title.lower()


def test_an_equal_count_is_reported_as_no_difference() -> None:
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(1_000, 2_000))
    others = [
        a_loaded_attempt(2, remaining=60.0, deaths_after_ms=(1_000, 2_000)),
        a_loaded_attempt(3, remaining=70.0, deaths_after_ms=(1_000, 2_000)),
    ]

    finding = best_deaths(a_loaded_series(deepest, *others))

    assert finding is not None
    assert "no difference" in finding.title.lower()


def test_one_other_attempt_is_not_a_comparison() -> None:
    """A median of one figure is that figure, and a claim drawn from it reads
    exactly as confident as one drawn from fifty."""
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(1_000,))
    other = a_loaded_attempt(2, remaining=60.0, deaths_after_ms=(1_000, 2_000, 3_000))

    assert best_deaths(a_loaded_series(deepest, other)) is None


def test_nothing_deepened_says_nothing() -> None:
    empty = LoadedProgression(progression=a_series(), loaded=())
    assert best_deaths(empty) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/domain/analysis/test_progression_best.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.domain.analysis.progression_best'`

- [ ] **Step 3: Write the implementation**

```python
# ABOUTME: Layer 3: what the deepest attempt did differently, by internal comparison only.
# ABOUTME: It names differences and explains none -- the anatomy is `wowperf raid --fight N`.

from statistics import median

from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import LoadedProgression

MIN_OTHER_ATTEMPTS = 2
"""Below this the deepest attempt has no cluster to stand against.

A median of one figure is that figure, and "the best attempt lost fewer
players than the one other attempt" is an anecdote wearing a comparison's
words. The keystone comparison falls back below three comparable references
for the same reason.
"""


def raid_invocation(one: LoadedEncounter) -> str:
    """The command that renders this attempt's anatomy, spelled out for a reader.

    Section 5.3: this layer names differences and does not explain them, and
    where a reader wants the anatomy the finding carries the invocation that
    renders it. The progression page never draws one fight's internals itself
    (section 8), so this string is the whole of the hand-off.
    """
    return f"wowperf raid {one.encounter.report_code} --fight {one.encounter.fight_id}"


def roster_deaths(one: LoadedEncounter) -> int:
    """How many roster players died in this attempt.

    Filtered to `one.players` for the reason `_first_death_ms` filters: a pet
    or an unidentified actor dying is not a roster player's death, and letting
    one through would make this figure disagree with the collapse window's
    anchor about what a death is.
    """
    roster_ids = {player.actor_id for player in one.players}
    return sum(1 for death in one.deaths if death.actor_id in roster_ids)


def best_deaths(series: LoadedProgression) -> Finding | None:
    """How many players the deepest attempt lost, against the median of the rest.

    `measured`: both figures are counts of logged deaths, and the median is
    arithmetic over them. The comparison is internal -- the night against
    itself -- so no reference run and no external sample takes any part in it.

    Withheld below `MIN_OTHER_ATTEMPTS` others, and when nothing was deepened.
    Never withheld for being unflattering: an attempt that went deepest while
    losing more players than the rest is a real difference and is stated in
    those words.
    """
    deepest = series.deepest_loaded
    if deepest is None:
        return None

    others = [
        one
        for one in series.attempts_with_events
        if one.encounter.fight_id != deepest.encounter.fight_id
    ]
    if len(others) < MIN_OTHER_ATTEMPTS:
        return None

    mine = roster_deaths(deepest)
    theirs = median(roster_deaths(one) for one in others)
    gap = theirs - mine

    if gap > 0:
        title = f"The best attempt lost {mine} players against a median of {theirs:.0f}"
    elif gap < 0:
        title = (
            f"The best attempt lost {mine} players -- {-gap:.0f} more "
            f"than the median of {theirs:.0f}"
        )
    else:
        title = f"The best attempt lost {mine} players, no difference from the rest"

    return Finding(
        id="progression.best.deaths",
        title=title,
        detail=(
            f"Counted across the {len(others)} other deepened attempts, whose median was "
            f"{theirs:.0f} roster deaths. A median and a range, never an average. This "
            "counts deaths and says nothing about what caused them; to see that attempt's "
            "anatomy -- the health curves, what hit whom, and what each player still had "
            f"-- run `{raid_invocation(deepest)}`."
        ),
        confidence=Confidence.MEASURED,
        evidence=(
            f"{mine} roster deaths on the deepest attempt, fight {deepest.encounter.fight_id}",
            f"median {theirs:.0f} across {len(others)} other attempts",
        ),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/domain/analysis/test_progression_best.py -v`
Expected: PASS

- [ ] **Step 5: Run the gate and commit**

Run `uv run pytest`, then `uv run ruff check .`, then `uv run mypy`, each as its own command. Commit `src/wowperf/domain/analysis/progression_best.py` and its test with the subject "Count the best attempt's deaths against the rest of the night".

---

## Task 2: Layer 3 — a specialisation still alive that usually is not

**Files:**
- Modify: `src/wowperf/domain/analysis/progression_best.py`
- Modify: `src/wowperf/domain/analysis/progression_service.py`
- Test: `tests/domain/analysis/test_progression_best.py` (append), `tests/domain/analysis/test_progression_service.py` (append)

**Interfaces:**
- Consumes: Task 1's module, `Player.spec`, `Player.class_name`, `findings.quantity`.
- Produces: `best_survived(series: LoadedProgression) -> Finding | None`, `MAX_SURVIVORS = 5`.

**Context:** §5.3's third difference: "a role still alive that usually is not". `repeat_first_death` already reports who falls first; this reports who stopped falling on the one attempt that went deepest. It counts specialisations and names no one, exactly as that finding does — the report holds real people.

**Ruling recorded here so no implementer has to guess:** §5.3's second difference, "damage that did not arrive", is **not** built in this plan. `repeat_ability` already uses the deepest attempt as its control (§5.2), so an ability absent from the best attempt's window is precisely what that finding reports. A Layer 3 finding restating it would be the same claim under a second id, and this repository's ledger deduplicates by id, not by meaning.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/analysis/test_progression_best.py`:

```python
from wowperf.domain.analysis.progression_best import best_survived
from wowperf.domain.model import Player

ROSTER = (
    Player(actor_id=1, name="Emberkin", class_name="Paladin", spec="Holy", item_level=600),
    Player(actor_id=2, name="Stonewake", class_name="Warrior", spec="Protection", item_level=600),
    Player(actor_id=3, name="Bríala", class_name="Mage", spec="Frost", item_level=600),
)


def test_a_specialisation_that_stopped_dying_on_the_best_attempt_is_named() -> None:
    """The deepest attempt's roster is the control: who died everywhere else and not there."""
    # `a_loaded_attempt` deals deaths round-robin over `players`, so one death
    # reaches actor 1 (Holy Paladin), two reach actors 1 and 2, and so on.
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(1_000,), players=ROSTER)
    others = [
        a_loaded_attempt(n, remaining=60.0, deaths_after_ms=(1_000, 2_000), players=ROSTER)
        for n in (2, 3, 4)
    ]

    finding = best_survived(a_loaded_series(deepest, *others))

    assert finding is not None
    assert finding.id == "progression.best.survived"
    assert "Protection Warrior" in finding.detail
    # Holy Paladin died on every attempt including the deepest, so it is not named.
    assert "Holy Paladin" not in finding.detail
    # Frost Mage died on none of them, so it never stopped dying.
    assert "Frost Mage" not in finding.detail
    assert finding.confidence is Confidence.DERIVED
    assert "wowperf raid abc123 --fight 1" in finding.detail


def test_no_real_player_name_reaches_the_finding() -> None:
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(1_000,), players=ROSTER)
    others = [
        a_loaded_attempt(n, remaining=60.0, deaths_after_ms=(1_000, 2_000), players=ROSTER)
        for n in (2, 3, 4)
    ]

    finding = best_survived(a_loaded_series(deepest, *others))

    assert finding is not None
    printed = finding.title + finding.detail + " ".join(finding.evidence)
    for player in ROSTER:
        assert player.name not in printed


def test_a_specialisation_absent_from_the_best_attempts_roster_is_not_a_survivor() -> None:
    """A swap out is not a survival, and the log cannot tell the two apart by itself."""
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(), players=ROSTER[:1])
    others = [
        a_loaded_attempt(n, remaining=60.0, deaths_after_ms=(1_000, 2_000), players=ROSTER)
        for n in (2, 3, 4)
    ]

    finding = best_survived(a_loaded_series(deepest, *others))

    # Protection Warrior died in all three others but was not on the deepest
    # attempt's roster at all, so there is nothing to name. Holy Paladin was
    # there and died in all three others, so it is what the finding reports --
    # this asserts the roster guard, not silence.
    assert finding is not None
    assert "Protection Warrior" not in finding.detail
    assert "Holy Paladin" in finding.detail


def test_a_specialisation_dying_in_half_the_others_is_not_enough() -> None:
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(), players=ROSTER)
    others = [
        a_loaded_attempt(2, remaining=60.0, deaths_after_ms=(1_000,), players=ROSTER),
        a_loaded_attempt(3, remaining=70.0, deaths_after_ms=(), players=ROSTER),
    ]

    # Holy Paladin died in 1 of 2 others: exactly half, which is not "usually".
    assert best_survived(a_loaded_series(deepest, *others)) is None


def test_one_other_attempt_is_not_a_comparison_for_survivors_either() -> None:
    deepest = a_loaded_attempt(1, remaining=10.0, deaths_after_ms=(), players=ROSTER)
    other = a_loaded_attempt(2, remaining=60.0, deaths_after_ms=(1_000,), players=ROSTER)

    assert best_survived(a_loaded_series(deepest, other)) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/domain/analysis/test_progression_best.py -v`
Expected: FAIL with `ImportError: cannot import name 'best_survived'`

- [ ] **Step 3: Write the implementation**

Add to `progression_best.py`, extending its imports with `from wowperf.domain.findings import Confidence, Finding, quantity` and `from wowperf.domain.model import Player`:

```python
MAX_SURVIVORS = 5
"""At six the finding stops being a difference and starts being the roster."""


def _spec_label(player: Player) -> str:
    """"Frost DeathKnight", not "Frost Death Knight".

    `class_name` is the API's own `subType` (`ingest.py`), which carries no
    space. A test asserting the spaced spelling asserts a string this code
    cannot produce.
    """
    return f"{player.spec} {player.class_name}"


def _specs_that_died(one: LoadedEncounter) -> set[str]:
    """Which specialisations lost at least one player in this attempt."""
    by_actor = {player.actor_id: player for player in one.players}
    return {
        _spec_label(by_actor[death.actor_id])
        for death in one.deaths
        if death.actor_id in by_actor
    }


def best_survived(series: LoadedProgression) -> Finding | None:
    """Specialisations that usually died and did not, on the attempt that went deepest.

    Counted only over specialisations on the deepest attempt's own roster: a
    specialisation that was not there did not survive anything, and a swap out
    reads identically to a survival in a log that records deaths rather than
    lives.

    `derived` rather than `measured`. Not dying is not the same as surviving
    something: a player who stood further out, a healer who was dead already in
    the other attempts and so could not die again, and a raid that reached a
    phase that ability never fires in all produce this shape, and the log
    distinguishes none of them.

    Withheld below `MIN_OTHER_ATTEMPTS` others, when nothing was deepened, and
    when nothing qualifies -- "usually" means more than half of the others,
    strictly, so a specialisation dying in exactly half is not named.
    """
    deepest = series.deepest_loaded
    if deepest is None:
        return None

    others = [
        one
        for one in series.attempts_with_events
        if one.encounter.fight_id != deepest.encounter.fight_id
    ]
    if len(others) < MIN_OTHER_ATTEMPTS:
        return None

    candidates = {_spec_label(player) for player in deepest.players} - _specs_that_died(deepest)

    counts: dict[str, int] = {}
    for one in others:
        for spec in _specs_that_died(one) & candidates:
            counts[spec] = counts.get(spec, 0) + 1

    qualifying = [(spec, count) for spec, count in counts.items() if count > len(others) / 2]
    if not qualifying:
        return None

    qualifying.sort(key=lambda pair: (-pair[1], pair[0]))
    top = qualifying[:MAX_SURVIVORS]
    lines = tuple(
        f"{spec} died in {count} of the {len(others)} other attempts, and not in the best one"
        for spec, count in top
    )

    return Finding(
        id="progression.best.survived",
        title=(
            f"{quantity(len(top), 'specialisation', 'specialisations')} that usually died "
            "came through the best attempt"
        ),
        detail=(
            "Counted across the deepest attempt's own roster, so a specialisation that was "
            "not in the raid for it is never named: "
            + "; ".join(lines)
            + ". Not dying is not the same as surviving something -- standing further out, "
            "being dead already when the others ended, and reaching a phase an ability never "
            "fires in all look like this, and the log tells them apart from none of the "
            "others. That is why this reads as derived. This counts specialisations and "
            "names no player; to see what the best attempt actually looked like, run "
            f"`{raid_invocation(deepest)}`."
        ),
        confidence=Confidence.DERIVED,
        evidence=lines,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/domain/analysis/test_progression_best.py -v`
Expected: PASS

- [ ] **Step 5: Wire both findings into the service**

In `src/wowperf/domain/analysis/progression_service.py`, add `from wowperf.domain.analysis.progression_best import best_deaths, best_survived` and extend the existing Layer 2 loop:

```python
    for deeper in (
        repeat_phase(progression),
        repeat_first_death(series),
        repeat_ability(series),
        collapse(series),
        best_deaths(series),
        best_survived(series),
    ):
        if deeper is not None:
            findings.append(deeper)
```

Update `analyse_progression`'s docstring: it now appends Layer 2's findings and Layer 3's, in that fixed order, skipping any analyser that found nothing to say. Layer 3 reads only `deepest_loaded` and the other deepened attempts, so a night where nothing was deepened leaves both silent.

- [ ] **Step 6: Test the wiring**

In `tests/domain/analysis/test_progression_service.py`, add a test that builds a series with a deepest attempt and three others, calls `analyse_progression`, and asserts on the **list of finding ids** — that it contains `progression.best.deaths` and `progression.best.survived`, and that both come after the Layer 2 ids. Asserting the list, rather than membership alone, is what fails when a finding is dropped from the loop.

- [ ] **Step 7: Run the gate and commit**

Run the three gate commands, then commit with the subject "Name the specialisations that came through the best attempt".

---

## Task 3: The view model and the ledger placements

**Files:**
- Create: `src/wowperf/domain/report/progression_model.py`
- Create: `src/wowperf/domain/report/progression_ledger.py`
- Test: `tests/domain/report/test_progression_ledger.py`

**Interfaces:**
- Consumes: `LedgerRow`, `Section` from `report/model.py`.
- Produces: `ProgressionReport`, `ProgressionHeader`, `AttemptRow`, `AttemptBar`, `AttemptsChart`, `ProgressionProvenance`, `all_progression_ledger_rows`, `PROGRESSION_PLACEMENTS`, `progression_field_for`.

**Context:** §8 names the five tabs. `Provenance` is **not** reused: it carries a `fight_id` (a night is not one fight) and a `references` tuple for external candidates (this command draws no external sample at all — §7.1). Giving the progression page its own provenance type makes "no corpus of other players' logs" structural rather than a habit: the page has no field a reference could be recorded in.

- [ ] **Step 1: Write `progression_model.py`**

```python
# ABOUTME: The progression report's view model: every judgement its five-tab page makes.
# ABOUTME: A sibling of RaidReport -- it reuses LedgerRow whole and carries no reference at all.

from collections.abc import Iterator

from wowperf.domain.base import Frozen
from wowperf.domain.report.model import LedgerRow, Section


class ProgressionHeader(Frozen):
    """The facts printed above a progression report's tabs.

    `depth_label` names the scale every percentage on this page is on, once,
    where a reader meets it first. Section 2.4: a printed percentage that does
    not say which one it is, is a figure nobody can act on.
    """

    boss: str
    difficulty: str
    size: int
    outcome: str
    attempts_counted: int
    attempts_discarded: int
    depth_label: str


class AttemptRow(Frozen):
    """One attempt in the Attempts table. Every field is already a string to print.

    `depth` and `deaths` are strings rather than numbers because both have an
    honest empty state -- an attempt the report gave no percentage for, and an
    attempt that was never deepened -- and a zero standing in for either would
    read as a measurement.
    """

    index: int
    fight_id: int
    depth: str
    duration: str
    phase: str = ""
    deaths: str
    is_best: bool = False
    is_kill: bool = False


class AttemptBar(Frozen):
    """One attempt's bar, in viewBox units. All arithmetic happened in the builder."""

    x: float
    y: float
    width: float
    height: float
    css_class: str
    hover: str


class AttemptsChart(Frozen):
    """The night's shape as one drawing. Withheld when no attempt carries a reading.

    Every coordinate the SVG needs lives here so the template computes none:
    `tick_x1`/`tick_x2` bound the horizontal gridlines, `tick_label_x` places
    their text, and `baseline_y` is the floor every bar stands on.
    """

    section: Section
    bars: tuple[AttemptBar, ...] = ()
    ticks: tuple[tuple[float, str], ...] = ()
    legend: str = ""
    width: float = 0.0
    height: float = 0.0
    tick_x1: float = 0.0
    tick_x2: float = 0.0
    tick_label_x: float = 0.0
    baseline_y: float = 0.0


class ProgressionProvenance(Frozen):
    """What was read, and what was withheld. No references, by construction.

    `Provenance` is deliberately not reused. It carries a `fight_id`, and a
    night is not one fight; and it carries `references`, the external
    candidates a comparison weighed. This command draws no external sample at
    all (section 7.1), which is what makes it an order of magnitude cheaper
    than a compared raid analysis -- and a type with nowhere to put another
    player's run cannot grow into a corpus by accident.
    """

    report_code: str
    encounter_id: int
    attempts_counted: int
    attempts_deepened: int
    fetched_at: str
    withheld: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()


class ProgressionReport(Frozen):
    header: ProgressionHeader
    chart: AttemptsChart
    attempts: tuple[AttemptRow, ...] = ()
    # Where attempts sat: the cluster, the movement, what was discarded.
    attempt_rows: tuple[LedgerRow, ...] = ()
    # What repeated: the phase, who fell first, what kept landing, the collapse.
    repeat_rows: tuple[LedgerRow, ...] = ()
    # What the deepest attempt did differently, and which attempt it was.
    best_rows: tuple[LedgerRow, ...] = ()
    # Withheld when no attempt was deepened, with the reason a reader needs.
    best: Section
    # Every finding no field above claimed -- a structural catch-all, not a
    # whitelist of its own, so a new family can never vanish from the page.
    observations: tuple[LedgerRow, ...] = ()
    provenance: ProgressionProvenance


def all_progression_ledger_rows(report: ProgressionReport) -> Iterator[LedgerRow]:
    """Every finding row on the progression page.

    One place names the fields, so a caller cannot reach four of the five tabs
    and lose the fifth in silence: a row whose ability reaches the page without
    reaching the icon resolver draws nothing and reports nothing.
    """
    yield from report.attempt_rows
    yield from report.repeat_rows
    yield from report.best_rows
    yield from report.observations
```

- [ ] **Step 2: Write the failing placement tests**

```python
# ABOUTME: Which tab each progression finding family lands on, and that none can fall off.
# ABOUTME: A family with no placement reaches Observations, which is the page's catch-all.

import pytest

from wowperf.domain.report.progression_ledger import (
    PROGRESSION_PLACEMENTS,
    progression_field_for,
)


@pytest.mark.parametrize(
    ("finding_id", "field"),
    [
        ("progression.best", "best_rows"),
        ("progression.best.deaths", "best_rows"),
        ("progression.best.survived", "best_rows"),
        ("progression.cluster", "attempt_rows"),
        ("progression.movement", "attempt_rows"),
        ("progression.attempts.discarded", "attempt_rows"),
        ("progression.repeat.phase", "repeat_rows"),
        ("progression.repeat.first_death", "repeat_rows"),
        ("progression.repeat.ability", "repeat_rows"),
        ("progression.collapse", "repeat_rows"),
    ],
)
def test_every_shipped_progression_finding_has_a_tab(finding_id: str, field: str) -> None:
    assert progression_field_for(finding_id) == field


def test_a_family_nothing_places_falls_through_to_observations() -> None:
    """None, not a default tab. `build_observations` is what catches it, and a
    default here would hide a new family on a tab nobody chose for it."""
    assert progression_field_for("progression.something.new") is None
    assert progression_field_for("deaths.total") is None


def test_the_narrow_prefix_is_written_first() -> None:
    """`progression.best.` precedes `progression.best`, and the first match wins.

    Both name the same field today, so this asserts the order is stated rather
    than that the order changes an answer -- the day a Layer 3 finding wants a
    tab of its own, an unordered table sends it to the wrong one silently.
    """
    prefixes = [prefix for prefix, _ in PROGRESSION_PLACEMENTS]
    assert prefixes.index("progression.best.") < prefixes.index("progression.best")
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/domain/report/test_progression_ledger.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Write `progression_ledger.py`**

```python
# ABOUTME: Where each progression finding family lands, mirroring raid_ledger.py's table.
# ABOUTME: A family absent from the table reaches the Summary's catch-all, never nowhere.

PROGRESSION_PLACEMENTS: tuple[tuple[str, str], ...] = (
    ("progression.best.", "best_rows"),
    ("progression.best", "best_rows"),
    ("progression.repeat.", "repeat_rows"),
    ("progression.collapse", "repeat_rows"),
    ("progression.cluster", "attempt_rows"),
    ("progression.movement", "attempt_rows"),
    ("progression.attempts.", "attempt_rows"),
)
"""Which tab's rows a progression finding family lands in: the first prefix
that matches wins.

Order is the rule and the narrow families come first, exactly as in the two
tables beside this one. `progression.best.` and `progression.best` name the
same field today, so reversing them changes nothing -- they are written in
that order anyway, because the day a Layer 3 finding wants a tab of its own is
the day an unordered table quietly sends it to the wrong one.

`progression.best` -- Layer 1's "which attempt went deepest" -- sits on the
Best attempt tab rather than with the cluster, so that tab always opens on the
attempt it is about.

There is no decomposition table beside this one. A progression finding costs
no seconds, so no figure here contains another and nothing can be nested.
"""


def progression_field_for(finding_id: str) -> str | None:
    """The progression sibling of `ledger._field_for`.

    `None` for an id the table does not cover, which is what sends it to
    `build_observations` and onto the Summary. A default field here would put a
    new family on a tab nobody chose and look deliberate doing it.
    """
    return next(
        (field for prefix, field in PROGRESSION_PLACEMENTS if finding_id.startswith(prefix)),
        None,
    )
```

- [ ] **Step 5: Run the tests, run the gate, commit**

Run the placement tests, then the three gate commands, then commit with the subject "Add the progression report's view model and tab placements".

---

## Task 4: The header and the attempts table

**Files:**
- Create: `src/wowperf/domain/report/progression_frame.py`
- Test: `tests/domain/report/test_progression_frame.py`

**Interfaces:**
- Consumes: `LoadedProgression`, `remaining_percent`, `format_seconds`, `roster_deaths` (Task 1), `raid_frame`'s difficulty-name table.
- Produces: `build_progression_header(series) -> ProgressionHeader`, `build_attempt_rows(series) -> tuple[AttemptRow, ...]`, `depth_label(uses_boss_health: bool) -> str`, `NO_READING`.

- [ ] **Step 1: Write the failing tests**

```python
# ABOUTME: The progression header and one row per attempt, in the words the page prints.
# ABOUTME: Every percentage on the page names its scale, and the header is where it is named.

from wowperf.domain.progression import LoadedProgression, Progression
from wowperf.domain.report.progression_frame import build_attempt_rows, build_progression_header

from tests.domain.progression_fixtures import PHASES, a_loaded_attempt, a_loaded_series, a_series
from tests.domain.test_progression import an_attempt


def test_the_header_names_the_scale_the_page_is_on() -> None:
    """Boss health and encounter progress diverge 3 to 8 points, so the page says which."""
    on_boss_health = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0, boss_percentage=30.0),
        a_loaded_attempt(2, remaining=60.0, boss_percentage=40.0),
    )
    assert build_progression_header(on_boss_health).depth_label == "boss health"

    on_progress = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0),
        a_loaded_attempt(2, remaining=60.0),
    )
    assert build_progression_header(on_progress).depth_label == "encounter progress"


def test_the_header_counts_what_was_excluded() -> None:
    progression = Progression(
        report_code="abc123",
        encounter_id=3492,
        boss_name="Emberkin",
        difficulty=5,
        size=20,
        attempts=(an_attempt(1, 50.0, 200.0),),
        discarded=(an_attempt(2, 100.0, 15.8), an_attempt(3, 100.0, 17.1)),
    )
    header = build_progression_header(LoadedProgression(progression=progression))

    assert header.attempts_counted == 1
    assert header.attempts_discarded == 2
    assert header.difficulty == "Mythic"
    assert header.size == 20


def test_the_header_says_which_attempt_killed_it() -> None:
    killed = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0),
        a_loaded_attempt(2, remaining=0.01, kill=True),
    )
    assert build_progression_header(killed).outcome == "Killed on attempt 2 of 2"

    survived = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0),
        a_loaded_attempt(2, remaining=40.0),
    )
    assert build_progression_header(survived).outcome == "No kill in 2 attempts"


def test_a_row_per_attempt_in_pull_order_marks_the_deepest() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0, seconds=204.0, deaths_after_ms=(1_000, 2_000)),
        a_loaded_attempt(2, remaining=16.5, seconds=480.0, deaths_after_ms=(1_000,)),
        a_loaded_attempt(3, remaining=55.0, seconds=227.0),
    )

    rows = build_attempt_rows(series)

    assert [row.index for row in rows] == [1, 2, 3]
    assert [row.fight_id for row in rows] == [1, 2, 3]
    assert [row.is_best for row in rows] == [False, True, False]
    assert rows[0].depth == "60.0%"
    assert rows[1].duration == "8:00"
    assert rows[0].deaths == "2"


def test_an_attempt_with_no_reading_prints_no_figure() -> None:
    """A dash, never a zero: a zero here would read as a kill."""
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0),
        a_loaded_attempt(2, remaining=50.0, fight_percentage=None),
    )

    rows = build_attempt_rows(series)

    assert rows[0].depth == "60.0%"
    assert rows[1].depth == "—"


def test_an_attempt_nobody_deepened_prints_no_death_count() -> None:
    one = a_loaded_attempt(1, remaining=60.0, deaths_after_ms=(1_000,))
    two = a_loaded_attempt(2, remaining=50.0, deaths_after_ms=(1_000, 2_000))
    series = LoadedProgression(
        progression=a_series(one.encounter, two.encounter), loaded=(one,)
    )

    rows = build_attempt_rows(series)

    assert rows[0].deaths == "1"
    assert rows[1].deaths == "—"


def test_the_phase_column_is_empty_where_the_api_says_phases_do_not_separate_wipes() -> None:
    gated = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0, last_phase=3),
        a_loaded_attempt(2, remaining=50.0, last_phase=1),
        separates_wipes=False,
    )
    assert [row.phase for row in build_attempt_rows(gated)] == ["", ""]

    open_gate = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0, last_phase=3),
        a_loaded_attempt(2, remaining=50.0, last_phase=1),
        separates_wipes=True,
    )
    assert [row.phase for row in build_attempt_rows(open_gate)] == [
        "The Drowning",
        "The Gathering",
    ]
    assert PHASES[2].name == "The Drowning"


def test_a_discarded_attempt_gets_no_row() -> None:
    """It takes no part in any figure the series reports, so a row for it would
    invite a comparison against figures it was excluded from."""
    progression = Progression(
        report_code="abc123",
        encounter_id=3492,
        boss_name="Emberkin",
        difficulty=5,
        size=20,
        attempts=(an_attempt(1, 50.0, 200.0),),
        discarded=(an_attempt(2, 100.0, 15.8),),
    )

    rows = build_attempt_rows(LoadedProgression(progression=progression))

    assert [row.fight_id for row in rows] == [1]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/domain/report/test_progression_frame.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `progression_frame.py`**

```python
# ABOUTME: The progression report's header and its one-row-per-attempt table.
# ABOUTME: Every percentage here is on the scale the header names, and never on the other.

from wowperf.domain.analysis.progression_best import roster_deaths
from wowperf.domain.progression import LoadedProgression, remaining_percent
from wowperf.domain.report.frame import format_seconds
from wowperf.domain.report.progression_model import AttemptRow, ProgressionHeader
from wowperf.domain.report.raid_frame import DIFFICULTY_NAMES

NO_READING = "—"
"""What an attempt with no figure prints. A zero would read as a kill, and an
empty cell reads as a rendering bug."""


def depth_label(uses_boss_health: bool) -> str:
    """Which percentage this page's figures are, in one phrase.

    The same two words `progression_service._depth_label` prints into the
    findings, so the page and the JSON cannot describe one night on two scales.
    """
    return "boss health" if uses_boss_health else "encounter progress"


def build_progression_header(series: LoadedProgression) -> ProgressionHeader:
    progression = series.progression
    attempts = progression.attempts
    killed = next((index for index, a in enumerate(attempts, start=1) if a.kill), None)
    if killed is not None:
        outcome = f"Killed on attempt {killed} of {len(attempts)}"
    else:
        outcome = f"No kill in {len(attempts)} attempt{'' if len(attempts) == 1 else 's'}"
    return ProgressionHeader(
        boss=progression.boss_name,
        difficulty=DIFFICULTY_NAMES.get(
            progression.difficulty, f"Difficulty {progression.difficulty}"
        ),
        size=progression.size,
        outcome=outcome,
        attempts_counted=len(attempts),
        attempts_discarded=len(progression.discarded),
        depth_label=depth_label(progression.uses_boss_health),
    )


def build_attempt_rows(series: LoadedProgression) -> tuple[AttemptRow, ...]:
    """One row per qualifying attempt, in pull order.

    Discarded attempts are not rows: they are excluded from every figure the
    series reports, so a row for one would invite a reader to compare it
    against figures it took no part in. The header states how many there were.

    The deaths column is filled only for an attempt that was deepened. An
    attempt nobody fetched events for has no death count, and printing 0 for it
    would claim nobody died.
    """
    progression = series.progression
    uses_boss_health = progression.uses_boss_health
    deepest = progression.deepest
    phase_names = {phase.id: phase.name for phase in progression.phases}
    deepened = {one.encounter.fight_id: one for one in series.loaded}

    rows: list[AttemptRow] = []
    for index, attempt in enumerate(progression.attempts, start=1):
        left = remaining_percent(attempt, uses_boss_health=uses_boss_health)
        loaded = deepened.get(attempt.fight_id)
        phase = ""
        if progression.separates_wipes and attempt.last_phase is not None:
            phase = phase_names.get(attempt.last_phase, "")
        rows.append(
            AttemptRow(
                index=index,
                fight_id=attempt.fight_id,
                depth=NO_READING if left is None else f"{left:.1f}%",
                duration=format_seconds(attempt.duration_seconds) or NO_READING,
                phase=phase,
                deaths=NO_READING if loaded is None else str(roster_deaths(loaded)),
                is_best=deepest is not None and attempt.fight_id == deepest.fight_id,
                is_kill=attempt.kill,
            )
        )
    return tuple(rows)
```

**Note for the implementer:** the difficulty-name table lives in `raid_frame.py` as `_DIFFICULTY_NAMES`, private. Rename it to `DIFFICULTY_NAMES` and update its one existing user in that same file — do **not** copy the three ids into a second module. A hand-kept mapping with a verified-on date in its docstring must have exactly one home. Keep the docstring where it is.

- [ ] **Step 4: Run the tests, gate, commit**

Run the frame tests, then the three gate commands, then commit with the subject "Build the progression header and its attempts table".

---

## Task 5: The attempts chart

**Files:**
- Create: `src/wowperf/domain/report/progression_chart.py`
- Test: `tests/domain/report/test_progression_chart.py`

**Interfaces:**
- Consumes: `LoadedProgression`, `remaining_percent`, `AttemptBar`, `AttemptsChart`, `Section`, `SectionState`.
- Produces: `build_attempts_chart(series) -> AttemptsChart` and the geometry constants.

**Context:** §8 — "Its geometry is computed by the builder and emitted as SVG. No charting library, no axes drawn in JavaScript. The keystone route timeline already works this way." `src/wowperf/domain/report/timeline.py` is the model to follow: named constants, each with a docstring saying what it is, and every number the template prints already on the model.

**The one arithmetic trap in this whole plan:** depth counts *down*. A bar whose height is proportional to `remaining` draws the **worst** attempt tallest. The height must come from `100 - remaining`, and the first test below fails if that subtraction is deleted.

- [ ] **Step 1: Write the failing tests**

```python
# ABOUTME: The attempts chart's geometry: a taller bar is a deeper attempt, not a worse one.
# ABOUTME: Depth counts down, so every height here is an inversion a test must be able to catch.

from wowperf.domain.report.model import SectionState
from wowperf.domain.report.progression_chart import (
    CHART_HEIGHT,
    CHART_WIDTH,
    build_attempts_chart,
)

from tests.domain.progression_fixtures import a_loaded_attempt, a_loaded_series


def test_a_deeper_attempt_draws_a_taller_bar() -> None:
    """The whole chart in one assertion: depth counts down and height counts up.

    Delete the inversion in `build_attempts_chart` and this fails, because the
    16.5% attempt would then draw the shortest bar on the page instead of the
    tallest.
    """
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=64.8),
        a_loaded_attempt(2, remaining=16.5),
        a_loaded_attempt(3, remaining=85.8),
    )

    chart = build_attempts_chart(series)

    heights = [bar.height for bar in chart.bars]
    assert heights[1] > heights[0] > heights[2]


def test_the_bars_stand_on_the_baseline_and_stay_inside_the_drawing() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=0.01),
        a_loaded_attempt(2, remaining=100.0),
    )

    chart = build_attempts_chart(series)

    assert chart.width == CHART_WIDTH
    assert chart.height == CHART_HEIGHT
    for bar in chart.bars:
        assert bar.y >= 0.0
        assert bar.y + bar.height <= chart.baseline_y + 0.001
        assert bar.x >= 0.0
        assert bar.x + bar.width <= chart.width


def test_the_deepest_attempt_carries_its_own_class() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0),
        a_loaded_attempt(2, remaining=20.0),
        a_loaded_attempt(3, remaining=70.0),
    )

    chart = build_attempts_chart(series)

    assert [("attempt-best" in bar.css_class) for bar in chart.bars] == [False, True, False]


def test_a_kill_carries_its_own_class_too() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0),
        a_loaded_attempt(2, remaining=0.01, kill=True),
    )

    chart = build_attempts_chart(series)

    assert "attempt-kill" in chart.bars[1].css_class
    assert "attempt-kill" not in chart.bars[0].css_class


def test_an_attempt_with_no_reading_leaves_its_slot_empty() -> None:
    """Its slot, not its place in the row: a missing bar must not shift the
    attempts after it, or bar 3 would sit where a reader reads bar 2."""
    with_gap = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0),
        a_loaded_attempt(2, remaining=50.0, fight_percentage=None),
        a_loaded_attempt(3, remaining=40.0),
    )
    without_gap = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0),
        a_loaded_attempt(2, remaining=50.0),
        a_loaded_attempt(3, remaining=40.0),
    )

    gapped = build_attempts_chart(with_gap)
    whole = build_attempts_chart(without_gap)

    assert len(gapped.bars) == 2
    assert len(whole.bars) == 3
    assert gapped.bars[1].x == whole.bars[2].x
    assert "1 attempt carries no depth reading" in gapped.legend


def test_a_night_with_no_reading_at_all_withholds_the_chart() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0, fight_percentage=None),
        a_loaded_attempt(2, remaining=50.0, fight_percentage=None),
    )

    chart = build_attempts_chart(series)

    assert chart.section.state is SectionState.WITHHELD
    assert chart.bars == ()
    assert "no depth reading" in chart.section.reason


def test_every_tick_label_names_a_depth_the_axis_reaches() -> None:
    chart = build_attempts_chart(
        a_loaded_series(a_loaded_attempt(1, remaining=50.0), a_loaded_attempt(2, remaining=40.0))
    )

    assert [label for _, label in chart.ticks] == ["0%", "25%", "50%", "75%", "100%"]
    ys = [y for y, _ in chart.ticks]
    assert ys[0] == chart.baseline_y
    assert ys == sorted(ys, reverse=True)
    assert chart.tick_x1 < chart.tick_x2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/domain/report/test_progression_chart.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `progression_chart.py`**

```python
# ABOUTME: The night's shape as one bar per attempt, in viewBox units the template prints.
# ABOUTME: Depth counts down and the chart counts up, so every height here is an inversion.

from wowperf.domain.progression import LoadedProgression, remaining_percent
from wowperf.domain.report.model import Section, SectionState
from wowperf.domain.report.progression_model import AttemptBar, AttemptsChart

CHART_WIDTH = 680.0
CHART_HEIGHT = 220.0

PLOT_X0 = 46.0
"""Where the bars start: right of the depth axis's labels."""

PLOT_X1 = 664.0
"""Where the bars end."""

PLOT_TOP = 16.0
"""The y of 100% reached -- the top of a bar that killed the boss."""

BASELINE_Y = 186.0
"""The y every bar stands on: 0% reached, the floor of the drawing."""

BAR_GAP = 6.0
"""The gap between one attempt's slot and the next."""

MIN_BAR_HEIGHT = 2.0
"""An attempt that moved the boss almost not at all still draws something.

Zero height renders nothing, and a slot with nothing in it reads as an attempt
the tool failed to measure rather than one that made no progress.
"""

TICK_PERCENTS = (0, 25, 50, 75, 100)
"""One gridline every quarter: enough to place a bar, few enough to stay legible."""

TICK_LABEL_X = 40.0
"""Where a gridline's label sits, right-aligned against the plot's left edge."""

LEGEND = (
    "One bar an attempt, in pull order. A taller bar got further into the encounter. "
    "The outlined bar is the attempt that went deepest."
)

NO_READING_REASON = (
    "No attempt in this series carries a depth reading, so there is no shape to draw. "
    "The attempts table below still lists every one of them."
)


def build_attempts_chart(series: LoadedProgression) -> AttemptsChart:
    """One bar per qualifying attempt, depth reached upward from the baseline.

    Depth counts down -- `fightPercentage` and `bossPercentage` both report
    what was *left* -- and the chart draws what was *reached*, so every height
    is `100 - remaining` scaled to the plot. Drawing `remaining` directly would
    put the worst attempt of the night at the top of the page and look entirely
    plausible doing it.

    Slots are laid out by an attempt's position in pull order, not by its
    position among the attempts that carry a reading: an attempt the report
    gave no percentage for leaves its slot empty rather than closing the gap,
    so the bars stay aligned with the table's row numbers.
    """
    progression = series.progression
    attempts = progression.attempts
    uses_boss_health = progression.uses_boss_health
    deepest = progression.deepest

    blank = AttemptsChart(section=Section(state=SectionState.WITHHELD, reason=NO_READING_REASON))
    if not attempts:
        return blank

    span = BASELINE_Y - PLOT_TOP
    ticks = tuple(
        (BASELINE_Y - (percent / 100.0) * span, f"{percent}%") for percent in TICK_PERCENTS
    )
    slot = (PLOT_X1 - PLOT_X0) / len(attempts)
    width = max(slot - BAR_GAP, 1.0)

    bars: list[AttemptBar] = []
    missing = 0
    for index, attempt in enumerate(attempts):
        left = remaining_percent(attempt, uses_boss_health=uses_boss_health)
        if left is None:
            missing += 1
            continue
        reached = max(0.0, min(100.0, 100.0 - left))
        height = max(MIN_BAR_HEIGHT, (reached / 100.0) * span)
        classes = ["attempt-bar"]
        if deepest is not None and attempt.fight_id == deepest.fight_id:
            classes.append("attempt-best")
        if attempt.kill:
            classes.append("attempt-kill")
        bars.append(
            AttemptBar(
                x=PLOT_X0 + index * slot,
                y=BASELINE_Y - height,
                width=width,
                height=height,
                css_class=" ".join(classes),
                hover=(
                    f"Attempt {index + 1}: {left:.1f}% left, "
                    f"{attempt.duration_seconds:.0f} seconds"
                ),
            )
        )

    if not bars:
        return blank

    legend = LEGEND
    if missing:
        legend = (
            f"{LEGEND} {missing} attempt{'' if missing == 1 else 's'} "
            f"carr{'ies' if missing == 1 else 'y'} no depth reading and draw"
            f"{'s' if missing == 1 else ''} no bar."
        )
    return AttemptsChart(
        section=Section(state=SectionState.PRESENT),
        bars=tuple(bars),
        ticks=ticks,
        legend=legend,
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        tick_x1=PLOT_X0,
        tick_x2=PLOT_X1,
        tick_label_x=TICK_LABEL_X,
        baseline_y=BASELINE_Y,
    )
```

**Note on the legend's wording:** the test asserts the exact substring `"1 attempt carries no depth reading"`. Check the singular branch produces it verbatim before moving on. If the implementer prefers different wording, change the test's expected substring with it — but do not weaken the assertion to `"carries no"` alone, which would pass on a sentence that never states the count.

- [ ] **Step 4: Run the tests, gate, commit**

Run the chart tests, then the three gate commands, then commit with the subject "Draw a night of attempts as one bar per attempt".

---

## Task 6: The builder

**Files:**
- Create: `src/wowperf/domain/report/progression_build.py`
- Test: `tests/domain/report/test_progression_build.py`

**Interfaces:**
- Consumes: Tasks 3, 4 and 5; `place_rows`, `build_observations`, `placed_finding_ids` from `report/ledger.py`; `_check_unique_finding_ids` from `report/build.py`.
- Produces: `build_progression_report(series, findings, fetched_at) -> ProgressionReport`.

**Context:** `raid_build.py` is the model. Note what this builder does **not** take: no `subject` (a night is about a boss, not a raider), no `defensives`/`consumables`/`externals`/`self_resurrections` (those four build death cards, and §8 forbids redrawing one fight's anatomy), no `reference_records` and no `compared_slugs` (no external sample exists). A parameter accepted and ignored is a lie the type system helps tell.

**Read before writing.** `place_rows`, `build_observations` and `placed_finding_ids` were written for the Mythic+ and raid shapes. Open `src/wowperf/domain/report/ledger.py` and check three things: whether `place_rows` derives its output field names from the placement table it is handed or hard-codes them (if it hard-codes them, make it read them from the table rather than adding a third copy of the function); the exact parameter order of `placed_finding_ids`; and whether `build_observations` tolerates an empty tooltips mapping. This page resolves no tooltips — every tooltip panel in this repository is built from a `LoadedEncounter`'s aura tables and a defensives data file, and this page holds neither — so `{}` is the honest argument, not an oversight.

- [ ] **Step 1: Write the failing tests**

```python
# ABOUTME: The progression page's builder: every judgement made here, none in the template.
# ABOUTME: No death cards and no references -- section 8 sends both elsewhere by design.

import pytest

from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import LoadedProgression
from wowperf.domain.report.model import SectionState
from wowperf.domain.report.progression_build import build_progression_report

from tests.domain.progression_fixtures import a_loaded_attempt, a_loaded_series, a_series


def a_finding(finding_id: str, title: str = "t") -> Finding:
    return Finding(id=finding_id, title=title, detail="d", confidence=Confidence.MEASURED)


def test_each_finding_lands_on_exactly_one_tab() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0), a_loaded_attempt(2, remaining=20.0)
    )
    findings = [
        a_finding("progression.best"),
        a_finding("progression.best.deaths"),
        a_finding("progression.cluster"),
        a_finding("progression.repeat.phase"),
        a_finding("progression.collapse"),
    ]

    report = build_progression_report(series, findings, fetched_at="2026-09-16 21:04")

    assert [row.finding_id for row in report.best_rows] == [
        "progression.best",
        "progression.best.deaths",
    ]
    assert [row.finding_id for row in report.attempt_rows] == ["progression.cluster"]
    assert [row.finding_id for row in report.repeat_rows] == [
        "progression.repeat.phase",
        "progression.collapse",
    ]
    assert report.observations == ()


def test_a_finding_no_table_places_reaches_the_summary_rather_than_vanishing() -> None:
    series = a_loaded_series(a_loaded_attempt(1, remaining=60.0))

    report = build_progression_report(
        series, [a_finding("progression.something.new", "New")], fetched_at="x"
    )

    assert [row.finding_id for row in report.observations] == ["progression.something.new"]


def test_the_best_tab_is_withheld_when_nothing_was_deepened() -> None:
    series = LoadedProgression(progression=a_series(), loaded=())

    report = build_progression_report(series, [], fetched_at="x")

    assert report.best.state is SectionState.WITHHELD
    assert report.best.reason
    assert any("Best attempt" in line for line in report.provenance.withheld)


def test_the_best_tab_is_present_when_something_was_deepened() -> None:
    series = a_loaded_series(a_loaded_attempt(1, remaining=60.0))

    report = build_progression_report(series, [], fetched_at="x")

    assert report.best.state is SectionState.PRESENT
    assert report.provenance.withheld == ()


def test_a_duplicate_finding_id_is_refused() -> None:
    series = a_loaded_series(a_loaded_attempt(1, remaining=60.0))

    with pytest.raises(ValueError):
        build_progression_report(
            series,
            [a_finding("progression.cluster"), a_finding("progression.cluster")],
            fetched_at="x",
        )


def test_the_provenance_counts_what_was_read_and_carries_no_reference_field() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0), a_loaded_attempt(2, remaining=20.0)
    )

    report = build_progression_report(series, [], fetched_at="2026-09-16 21:04")

    assert report.provenance.report_code == "abc123"
    assert report.provenance.encounter_id == 3492
    assert report.provenance.attempts_counted == 2
    assert report.provenance.attempts_deepened == 2
    assert report.provenance.fetched_at == "2026-09-16 21:04"
    # The type has nowhere to record another player's run, and that is the point.
    assert not hasattr(report.provenance, "references")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/domain/report/test_progression_build.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `progression_build.py`**

```python
# ABOUTME: Turns a night of attempts and its findings into the value the page renders.
# ABOUTME: A sibling of raid_build.py with no death cards, no subject and no reference.

from collections.abc import Sequence

from wowperf.domain.findings import Finding
from wowperf.domain.progression import LoadedProgression
from wowperf.domain.report.build import _check_unique_finding_ids
from wowperf.domain.report.ledger import build_observations, place_rows, placed_finding_ids
from wowperf.domain.report.model import Section, SectionState
from wowperf.domain.report.progression_chart import build_attempts_chart
from wowperf.domain.report.progression_frame import build_attempt_rows, build_progression_header
from wowperf.domain.report.progression_ledger import PROGRESSION_PLACEMENTS
from wowperf.domain.report.progression_model import ProgressionProvenance, ProgressionReport

NOTHING_DEEPENED = (
    "No attempt was deepened, so there is nothing to compare the best one against."
)

METHOD_DEPTH_SCALE = (
    "Every percentage on this page is the same scale, chosen once for the whole series: "
    "boss health where every qualifying attempt carried one, and the encounter's own "
    "progress otherwise. Both count down -- a kill reads about 0.01 and an instant wipe "
    "reads 100 -- and the header names which scale this night is on."
)

METHOD_NO_ANATOMY = (
    "This page draws the night, never one attempt's internals. The health curves, what hit "
    "whom and what each player still had are `wowperf raid --fight N`'s work, and the "
    "findings that want them carry the invocation."
)


def build_progression_report(
    series: LoadedProgression,
    findings: Sequence[Finding],
    fetched_at: str,
) -> ProgressionReport:
    """Everything the progression page shows, decided here so the template decides nothing.

    `fetched_at` is a parameter rather than a clock read, because the domain
    performs no I/O and the same inputs must render the same page.

    Several of `build_raid_report`'s parameters are deliberately absent, and
    each absence is a fact about a night rather than an omission. There is no
    `subject`: a series is about a boss, not a raider, and no card on this page
    belongs to one. There are no `defensives`, `consumables`, `externals` or
    `self_resurrections`: those four exist to build death cards, and section 8
    forbids this page from redrawing one fight's anatomy. There are no
    `reference_records` and no `compared_slugs`: this command draws no external
    sample at all, which is what makes it an order of magnitude cheaper.
    """
    _check_unique_finding_ids(findings)
    titles_by_id = {finding.id: finding.title for finding in findings}
    placed = place_rows(findings, titles_by_id, set(), {}, placements=PROGRESSION_PLACEMENTS)

    deepened = len(series.loaded)
    best = (
        Section(state=SectionState.PRESENT)
        if deepened
        else Section(state=SectionState.WITHHELD, reason=NOTHING_DEEPENED)
    )
    withheld = (
        (f"Best attempt: {best.reason}",) if best.state is SectionState.WITHHELD else ()
    )

    placed_ids = placed_finding_ids((), placed, ())
    return ProgressionReport(
        header=build_progression_header(series),
        chart=build_attempts_chart(series),
        attempts=build_attempt_rows(series),
        attempt_rows=placed["attempt_rows"],
        repeat_rows=placed["repeat_rows"],
        best_rows=placed["best_rows"],
        best=best,
        observations=build_observations(findings, placed_ids, titles_by_id, {}),
        provenance=ProgressionProvenance(
            report_code=series.progression.report_code,
            encounter_id=series.progression.encounter_id,
            attempts_counted=len(series.progression.attempts),
            attempts_deepened=deepened,
            fetched_at=fetched_at,
            withheld=withheld,
            methods=(METHOD_DEPTH_SCALE, METHOD_NO_ANATOMY),
        ),
    )
```

- [ ] **Step 4: Run the tests, gate, commit**

Run the build tests, then the three gate commands, then commit with the subject "Assemble the progression report from a night and its findings".

---

## Task 7: The templates, the stylesheet and the renderer

**Files:**
- Create: `src/wowperf/adapters/render/progression.html.j2`, `_progression_summary.html.j2`, `_progression_attempts.html.j2`, `_progression_repeats.html.j2`, `_progression_best.html.j2`, `_progression_provenance.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`, `src/wowperf/adapters/render/html.py`

**Interfaces:**
- Consumes: `ProgressionReport`, `all_progression_ledger_rows`, `CdnIcons`.
- Produces: `render_progression(report, icons=None) -> str`, `PROGRESSION_TEMPLATE_NAME`.

**Context:** the five panel ids are `tab-summary`, `tab-attempts`, `tab-repeats`, `tab-best`, `tab-provenance`, in that order, matching §8's Summary, Attempts, Repeats, Best attempt, Provenance.

- [ ] **Step 1: Write `progression.html.j2`**

```jinja
{# ABOUTME: Document skeleton for the progression report: a header, five tab panels, and one #}
{# ABOUTME: inline script that only shows and hides -- one self-contained file. #}
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ report.header.boss }} {{ report.header.difficulty }} progression</title>
<style>
{% include "report.css.j2" %}
{% for ability_id, uri in icons_by_id.items() %}
.i-{{ ability_id }} { background-image: url({{ uri }}); }
{% endfor %}
</style>
</head>
<body>
{% if icons_by_id %}
<svg class="icon-defs" aria-hidden="true">
{% for ability_id, uri in icons_by_id.items() %}
<symbol id="icon-{{ ability_id }}" viewBox="0 0 1 1"><image href="{{ uri }}" width="1" height="1"/></symbol>
{% endfor %}
</svg>
{% endif %}
<main>

<h1>{{ report.header.boss }} {{ report.header.difficulty }}</h1>
<p class="sub">{{ report.header.outcome }} &middot; {{ report.header.attempts_counted }} attempts read{% if report.header.attempts_discarded %}, {{ report.header.attempts_discarded }} excluded as too short{% endif %} &middot; depth is {{ report.header.depth_label }}</p>

<nav class="tabs" data-tab-group="main" aria-label="Sections">
  <button type="button" class="tab" data-tab-for="tab-summary">Summary</button>
  <button type="button" class="tab" data-tab-for="tab-attempts">Attempts</button>
  <button type="button" class="tab" data-tab-for="tab-repeats">Repeats</button>
  <button type="button" class="tab" data-tab-for="tab-best">Best attempt</button>
  <button type="button" class="tab" data-tab-for="tab-provenance">Provenance</button>
</nav>
{# The blank lines below are page output, not source spacing: text outside a tag renders, #}
{# and a comment or an include tag does not. Removing one changes the rendered page. #}



{% include "_progression_summary.html.j2" %}

{% include "_progression_attempts.html.j2" %}

{% include "_progression_repeats.html.j2" %}

{% include "_progression_best.html.j2" %}

{% include "_progression_provenance.html.j2" %}

</main>
<script>
{% include "report.js.j2" %}
</script>
</body>
</html>
```

- [ ] **Step 2: Write `_progression_attempts.html.j2`**

```jinja
{# ABOUTME: The Attempts panel: the night's shape as a drawing, then every attempt as a row. #}
{# ABOUTME: Every coordinate below was computed in progression_chart.py; this loops and prints. #}
{% from "_macros.html.j2" import ledger_row with context %}
<section class="panel" data-tab-panel="main" id="tab-attempts">

<h2 id="attempts">Attempts</h2>
{% if report.chart.section.state.value == "withheld" %}
<p class="withheld">{{ report.chart.section.reason }}</p>
{% else %}
<p class="legend">{{ report.chart.legend }}</p>
<svg width="100%" viewBox="0 0 {{ report.chart.width }} {{ report.chart.height }}">
  {% for y, label in report.chart.ticks %}
  <line class="tick" x1="{{ report.chart.tick_x1 }}" y1="{{ y }}"
        x2="{{ report.chart.tick_x2 }}" y2="{{ y }}"></line>
  <text class="tick-label" x="{{ report.chart.tick_label_x }}" y="{{ y }}"
        text-anchor="end" dominant-baseline="middle">{{ label }}</text>
  {% endfor %}
  {% for bar in report.chart.bars %}
  <rect class="{{ bar.css_class }}" x="{{ bar.x }}" y="{{ bar.y }}"
        width="{{ bar.width }}" height="{{ bar.height }}"><title>{{ bar.hover }}</title></rect>
  {% endfor %}
</svg>
{% endif %}

<table class="attempts">
<thead>
<tr><th>#</th><th>Depth left ({{ report.header.depth_label }})</th><th>Duration</th><th>Ended in</th><th>Deaths</th></tr>
</thead>
<tbody>
{% for row in report.attempts %}
<tr{% if row.is_best %} class="best"{% endif %}>
<td>{{ row.index }}</td><td>{{ row.depth }}</td><td>{{ row.duration }}</td><td>{{ row.phase }}</td><td>{{ row.deaths }}</td></tr>
{% endfor %}
</tbody>
</table>

{% if report.attempt_rows %}
<div class="findings">
{% for row in report.attempt_rows %}
{{ ledger_row(row) }}
{% endfor %}
</div>
{% endif %}

</section>
```

- [ ] **Step 3: Write the four remaining panels**

`_progression_summary.html.j2` mirrors `_raid_summary.html.j2` with its decomposition ledger and its pointer list **removed** — a progression finding costs no seconds, so there is no figure containing another and no "biggest losses" to rank by cost. It renders one `<p class="sub">` naming what the other tabs hold, then `<h2 id="observations">Other findings</h2>` over `report.observations`, with "Nothing else measured." as the empty case.

`_progression_repeats.html.j2` mirrors `_raid_mechanics.html.j2` exactly — a panel with `id="tab-repeats"`, an `<h2 id="repeats">Repeats</h2>`, `report.repeat_rows` or "Nothing to report."

`_progression_best.html.j2` is the same shape with `id="tab-best"` and `report.best_rows`, plus the withheld line above the rows, exactly as `_route.html.j2` writes it:

```jinja
{% if report.best.state.value == "withheld" %}
<p class="withheld">{{ report.best.reason }}</p>
{% endif %}
```

`_progression_provenance.html.j2` mirrors `_raid_provenance.html.j2` with the reference loop **removed** — there is no `references` field to loop over — and its opening lines reading:

```jinja
<p class="sub">Report {{ report.provenance.report_code }}, encounter {{ report.provenance.encounter_id }}, {{ report.provenance.attempts_counted }} attempts read and {{ report.provenance.attempts_deepened }} deepened, fetched {{ report.provenance.fetched_at }}.</p>
<p class="sub">No reference run of any kind was fetched: this page compares a night against itself.</p>
```

Keep the withheld loop, the methods loop and the three-badge legend block verbatim.

- [ ] **Step 4: Add the stylesheet's new classes**

Append to `report.css.j2`, beside the existing `.block` rules:

```css
.attempt-bar { fill: var(--ours); }
.attempt-best { stroke: var(--ink); stroke-width: 2; }
.attempt-kill { fill: var(--badge-measured); }
.attempts { width: 100%; border-collapse: collapse; font-size: 13px; margin: 12px 0 8px; }
.attempts th { text-align: left; color: var(--ink-faint); font-weight: 500;
  padding: 0 8px 4px 0; }
.attempts td { padding: 3px 8px 3px 0; border-top: 1px solid var(--line);
  color: var(--ink-dim); font-variant-numeric: tabular-nums; }
.attempts tr.best td { color: var(--ink); font-weight: 600; }
```

`.timeline` is already the death recap's table class, which is why this one is `.attempts`. Check the `--ours`, `--ink`, `--ink-dim`, `--ink-faint`, `--line` and `--badge-measured` tokens all exist in the palette block at the top of that file before using them.

- [ ] **Step 5: Add `render_progression` to `html.py`**

```python
PROGRESSION_TEMPLATE_NAME = "progression.html.j2"


def render_progression(report: ProgressionReport, icons: CdnIcons | None = None) -> str:
    """`render_raid`'s counterpart for the five-tab progression page.

    `_icon_addresses` is not reused: it walks death cards and player cards, and
    this page has neither. Only a ledger row can name an ability here --
    `progression.repeat.ability` is the one finding that does -- so the walk is
    that single loop rather than a third caller of a function whose other two
    arguments would every time be empty.

    Without an `icons` source the page draws exactly as the other two do
    without one: every ability id on the view model is inert until something
    can address it, and the `ability` macro renders a bare name.
    """
    addresses: dict[int, str] = {}
    if icons is not None:
        for row in all_progression_ledger_rows(report):
            if row.ability_id is None or row.ability_id in addresses:
                continue
            address = icons.url(row.ability_id)
            if address is not None:
                addresses[row.ability_id] = address
    return _environment().get_template(PROGRESSION_TEMPLATE_NAME).render(
        report=report, icons_by_id=addresses
    )
```

- [ ] **Step 6: Check the wheel carries the new templates**

`.github/workflows/gate.yml` builds the wheel to check it carries the report's templates, because none of them is a `.py` file and no test running from the source tree would notice one missing. Confirm the packaging configuration in `pyproject.toml` globs the template directory rather than listing files; if it lists them, add the six new ones.

- [ ] **Step 7: Gate and commit**

Run the three gate commands, then commit with the subject "Render a night of attempts as one five-tab page".

---

## Task 8: The page's invariant tests and the golden file

**Files:**
- Create: `tests/adapters/render/test_progression_html_invariants.py`
- Create: `tests/adapters/render/golden/progression.html` (generated by the test)

**Interfaces:**
- Consumes: `render_progression`, `build_progression_report`, `tests/domain/progression_fixtures.py`.
- Produces: `PROGRESSION_PANEL_ORDER`, `a_progression_page()`.

**Context:** §8 — "The invariant tests that pin the id set are what make this safe, and the progression page needs its own." `tests/adapters/render/test_raid_html_invariants.py` is the model; port the **rules**, do not copy the file wholesale.

- [ ] **Step 1: Build the page fixture**

`a_progression_page()` renders a night that varies, per §10: several attempts with the **deepest in the middle**, at least one discarded, `separates_wipes=True` with a phase table, no kill, and findings covering all four row fields plus one the placement table does not know (so the Observations catch-all renders too). A monotonic fixture never exercises the one behaviour this tool must get right.

- [ ] **Step 2: Port the invariant rules**

```python
PROGRESSION_PANEL_ORDER = [
    "tab-summary", "tab-attempts", "tab-repeats", "tab-best", "tab-provenance",
]
```

1. `test_every_panel_appears_once_in_tab_order` — the ids the page renders, compared as a **list** against `PROGRESSION_PANEL_ORDER`, plus the `<section class="panel"` count. The list says the ids are right; the count says there are no others.
2. `test_every_panel_has_exactly_one_tab_button` — both directions. A panel with no button is unreachable; a button naming a panel that does not exist is a click that does nothing.
3. `test_the_tab_buttons_follow_panel_order` — the script opens the first button's panel, so button order is the default tab.
4. `test_the_root_class_the_script_adds_is_not_in_the_markup`.
5. `test_the_page_makes_no_request_but_its_icons` — no `<link`, no `@import`, no `src=` other than `wow.zamimg.com`, exactly one `<script`.
6. `test_every_finding_appears_exactly_once` — each `id="finding-<id>"` occurs once in the whole document.
7. `test_a_title_containing_markup_is_escaped` — render a finding whose title contains a `<script>` tag and assert the raw tag does not reach the page. Autoescaping is the only thing standing between an API-sourced string and the reader's browser.

Then the two rules this page has that no other does:

```python
def test_the_page_never_draws_one_attempts_anatomy() -> None:
    """Section 8: the anatomy is `wowperf raid --fight N`'s work, and keeping the
    two pages from becoming duplicate templates is a prohibition, not a taste.

    Asserted against the class names the death recap owns, because that is the
    one part of the raid page a progression page would plausibly grow into.
    """
    html = a_progression_page()

    for owned_by_the_raid_page in ('class="recap"', 'class="hp-curve"', 'class="avail"'):
        assert owned_by_the_raid_page not in html


def test_the_page_carries_no_reference_to_another_report() -> None:
    """RPGLogs terms section 5d: never accumulate a corpus of other players' logs.

    The provenance type has no field for one, so this asserts what a reader can
    check: the page links to no report at all.
    """
    assert "warcraftlogs.com/reports/" not in a_progression_page()
```

- [ ] **Step 3: Cover the other gate state**

Add a second, smaller fixture with `separates_wipes=False` and assert the "Ended in" column is empty on every row of it. The golden carries one state; the tests carry both.

- [ ] **Step 4: Write the golden test and generate the file**

Mirror `test_the_rendered_page_matches_the_golden_file` from `test_html_invariants.py`, including its `--golden-update` branch and the failure message naming the command that regenerates it.

Run: `uv run pytest tests/adapters/render/test_progression_html_invariants.py --golden-update`
Then: `uv run pytest tests/adapters/render/test_progression_html_invariants.py -v`
Expected: PASS

**Read the generated file before committing it.** A golden nobody read is a golden that pins a bug. Check four things by eye: the depth column's header names a scale; the deepest attempt's row is marked and its bar is the tallest in the SVG; the discarded count appears in the header line; and no player name appears anywhere.

- [ ] **Step 5: Gate and commit**

Run the three gate commands, then commit with the subject "Pin the progression page's panels, script and golden output".

---

## Task 9: The command writes the page, and the end-to-end test proves it

**Files:**
- Modify: `src/wowperf/cli.py`
- Modify: `CLAUDE.md`
- Modify: `tests/e2e/test_progression_e2e.py`

**Interfaces:**
- Consumes: `build_progression_report`, `render_progression`.
- Produces: `<code>-<encounter>.progression.html` beside the existing JSON.

- [ ] **Step 1: Write the HTML in the `progression` command**

After the JSON write, in its own `try` block — the same reasoning the `raid` command's write phase carries: this fails differently, and it can fail after the findings have already been computed.

```python
    report_file = out / f"{progression.report_code}-{progression.encounter_id}.progression.html"
    try:
        report_file.write_text(
            render_progression(
                build_progression_report(
                    deep, findings, datetime.now().strftime("%Y-%m-%d %H:%M")
                ),
                icons=<see below>,
            ),
            encoding="utf-8",
        )
    except OSError as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    typer.echo(f"report written to {report_file}")
```

**The icons argument is a decision the implementer makes from the code, not from this plan.** Read `build_icons` in `cli.py` and see what it needs. If it requires a `LoadedEncounter` and its aura tables, this path holds a `LoadedProgression` instead, and the two honest options are: build a `CdnIcons` from the deepest loaded attempt's `ability_icons`, or pass `None` and let every ability render as a bare name — which the `ability` macro already supports and which the Mythic+ comparison tables relied on for months. Choose one, say which in the commit body, and **do not invent a new icon source**.

- [ ] **Step 2: Correct the command's docstring**

Its last paragraph currently reads "Writes no HTML. The report for this command belongs to a later plan; a half-rendered page is worse than none." Replace it with one naming what the page carries and what it deliberately does not: five tabs holding the night's shape, and no single attempt's anatomy — that is `wowperf raid --fight N`'s work, and the findings that want it carry the invocation.

- [ ] **Step 3: Update CLAUDE.md**

- The command table's `progression` row: it writes `<code>-<encounter>.progression.json` **and** `<code>-<encounter>.progression.html` under `--out`.
- The repository overview's paragraph listing the pages: the Mythic+ page carries six tabs, the raid page seven, and the progression page five — Summary, Attempts, Repeats, Best attempt, Provenance.

- [ ] **Step 4: Deepen the end-to-end test**

`tests/e2e/test_progression_e2e.py` already runs against the real API. Extend it to assert on the rendered page as well as the JSON:

- The HTML file exists and is not empty.
- Its five panel ids appear, in order.
- The depth column's header names one of the two scales, and the same one the JSON's findings name.
- **No roster name from the fetched report appears anywhere in the page.** Read the roster from the fetched data and assert each name's absence — never hard-code a real name into the test file.
- The page contains no `warcraftlogs.com/reports/` link.

- [ ] **Step 5: Run the command against the real night and read the page**

```bash
uv run wowperf progression cW38jmwdnZfbHVL4 --boss 3492 --difficulty 4 --out out
```

(The real night is difficulty 4, not 5; the command refuses a `--difficulty` the report holds no
fight at. `--difficulty` can also be omitted entirely -- it defaults to the boss's own first fight
in the report, which is difficulty 4 here too.)

**This step is not optional and is not a formality.** Plan 2's live run found three findings that fired with nothing to say, and none of them was reachable from an offline fixture, because a fixture is built to make its finding fire. Open the written HTML and read every tab. Check specifically:

- The chart's tallest bar is the attempt the Best attempt tab names.
- Every percentage on the page is on one scale, and the header names it.
- The Repeats tab reads as sense on a real night. On this night that is **seven findings, not eight**: `repeat.first_death` is withheld because seven specialisations each died first once, and `repeat.phase` names **both** tied phases. A plan-2 output with eight findings is a pre-fix output and is not what this page should show.
- Layer 3's two findings say something a reader could act on, and neither names a player.

Record what the run printed — the finding count, the quota spent, and its composition — in the commit body. If a finding fires with nothing to say, fix it here, before the final review. That is what this step is for.

- [ ] **Step 6: Gate and commit**

Run the three gate commands, then `uv run pytest -m e2e tests/e2e/test_progression_e2e.py`, then commit with the subject "Write the progression page beside its findings".

---

## Self-Review

**1. Spec coverage.**

| Spec section | Task |
| --- | --- |
| §5.3 Layer 3 — deaths that did not happen | Task 1 |
| §5.3 Layer 3 — a role still alive that usually is not | Task 2 |
| §5.3 Layer 3 — damage that did not arrive | **Deliberately not built.** `repeat_ability`'s control already reports it — ruling in Task 2. |
| §5.3 — the finding carries the `raid --fight N` invocation | Tasks 1 and 2, `raid_invocation` |
| §6 — the severity table gains the `progression.*` families | **Already done in plan 2.** `SEVERITY_BY_FAMILY` carries `"progression": 1`, and `family_of` splits on the first dot, so `progression.best.deaths` resolves through that one key. Verified by reading `severity.py`; no task needed. |
| §8 — five tabs, frozen view model, pure builder, templates that decide nothing | Tasks 3, 6, 7 |
| §8 — the Attempts tab is the spine, one row per attempt in pull order | Task 4 |
| §8 — geometry computed by the builder, emitted as SVG, no charting library | Task 5 |
| §8 — phase claims gated on `separates_wipes` | Task 4's phase column; see known gap 2 for the colouring half |
| §8 — the page never redraws one fight's anatomy | Task 8's invariant test |
| §8 — the tab mechanism needs its own invariant tests | Task 8 |
| §10 — the golden page carries a night that varies | Task 8 |
| §10 — both guard states present | Task 4 and Task 8 step 3 |
| §10 — end-to-end against the real API | Task 9 |
| §9.6 / open item 4 — session gaps | **Measured and cut**, above. |

**2. Placeholder scan.** One deliberate trap is planted and labelled: Task 9's `icons=<see below>`, which does not compile and forces the implementer to read `build_icons` before writing. Every other code block is complete and runnable as written. Three tasks carry a "read before writing" note naming the exact function to open — Task 4 (`_DIFFICULTY_NAMES`), Task 6 (`ledger.py`'s three helpers), Task 7 (the CSS palette tokens) — because each is a place where a plausible-looking guess compiles and is wrong.

**3. Type consistency.** `AttemptRow.depth` and `.deaths` are `str` in the model (Task 3), built as `str` in Task 4, printed as `str` in Task 7. `AttemptsChart.ticks` is `tuple[tuple[float, str], ...]` holding a **y** and a label, where `Timeline.ticks` holds an x and a label — this axis is vertical, and Task 7's loop unpacks `y, label` accordingly. `roster_deaths` is defined in Task 1 and consumed in Task 4: the dependency runs from `analysis/` into `report/`, the direction every other builder already imports in. `raid_invocation` is defined in Task 1 and used in Task 2.

---

## Known gaps, recorded rather than hidden

1. **`Encounter.outcome` still prints a percentage without naming its scale.** It is dead production code today and this page does not reach for it (ruling above). It will bite the first consumer that does.
2. **No phase colouring on the chart.** §8 says the colouring is gated on `separates_wipes`; this plan draws no phase colour at all, and a gate on a thing that does not exist is satisfied. The phase reaches the page as the Attempts table's "Ended in" column, correctly gated. Colouring the bars by ending phase is a later change and must carry the same gate.
3. **No Layer 3 phase finding.** §5.3's "deaths that did not happen before the phase that usually ends the night" joins two claims that `progression.best` and `repeat.phase` already make separately. Left out under YAGNI, recorded so the omission is visible rather than accidental.
4. **The golden page carries one `separates_wipes` state.** A golden file is one page; the other state is covered by a test.
5. **The session-gap declaration is cut**, with the measurement above. The design's open item 4 gains this dated negative reading in this plan's first commit.
6. ~~**`progression.best.survived` has no positive control from real data.** Unlike the floor and the debuff composition, this finding's rule was not measured against a real night before being written — the night is available and Task 9 step 5 is where it meets one. If it names a specialisation on the fixture night that a reader would call noise, cut it there rather than shipping it hedged.~~ **Outcome, Task 9: the positive control failed and the finding is cut.** On the real night the deepest attempt's 20 players resolved to 19 distinct specialisation labels, 18 of which died on it, leaving one candidate before any filter ran; every attempt logged 19 to 21 roster deaths, so "usually died" rejected nothing and the single candidate scored 5 of 6. The output was decided entirely by who happened not to die once. A `MAX_SURVIVORS` gate was tried first and measured inert — it guards the opposite end of the funnel — so the finding, its helpers and its tests were removed. The design's §5.3 gains the dated negative reading and names what would reopen it. `progression.best.deaths` is unaffected and ships.
