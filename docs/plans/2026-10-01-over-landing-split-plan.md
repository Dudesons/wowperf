# What keeps over-landing, split: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A boss summary names the abilities no reference kill took at all, then those it took more
often than the kills did, each only when it recurs in more than half the compared pulls.

**Architecture:** `progression.lead.overlanding` becomes two boss-level findings in
`src/wowperf/domain/analysis/night_rollups.py`, built by one shared helper over the same compared
pulls. The split reads each per-pull `mechanics.ability.*` finding's own `quantifier`, which is
`"none"` exactly when no reference kill took the ability. The page needs no new section:
`progression.lead.` already places both on `lead_rows`, in the order `analyse_night_rollups`
returns them.

**Tech Stack:** Python 3.12, `uv`, pytest, pydantic `Frozen` models, Typer CLI with httpx
`MockTransport` harnesses.

**Spec:** `docs/plans/2026-10-01-raid-leader-night-design.md`, section 10 (and the §5.2
amendment it carries). Read §10 and §8 before any task.

## Global Constraints

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` touches the network,
  the disk or a template. `domain/analysis` never imports `domain/report`.
- **Every finding carries a confidence badge.** Both findings are `derived`.
- **Findings are never summed.** Each new aggregate sets `Finding.quantifier` with
  `quantifier_for(matching, total)` (`src/wowperf/domain/findings.py`).
- **No hand-written boss knowledge.** No ability or mechanic is named in code.
- **No causal or avoidability claim (spec §8).** Say "no reference kill took it" as what the log
  shows. Never say "avoidable", "should have", or that a mechanic was failed.
- **Every code file starts with two `ABOUTME: ` lines.** Comments are evergreen. Never remove a
  true comment; rewrite one this change makes false.
- **Tests never carry a real character name.** Use `Emberkin`, `Stonewake`, `Bríala`,
  `Кириллица`. Boss and ability names in tests are invented.
- **Commits:**
  - imperative subject, with no `feat:`/`fix:` prefix, and a body that says why;
  - plain ASCII only;
  - end with `Co-Authored-By: <the model that wrote it> <noreply@anthropic.com>`;
  - never `--no-verify`;
  - commit with `/mingw64/bin/git`;
  - never push.
- **Toolchain:** every Bash command that runs `uv` starts with `export PATH="$HOME/.local/bin:$PATH";`.
  Tests: `uv run pytest`. Lint: `uv run ruff check .`. Types: `uv run mypy` (no paths).
- **Goldens:** `tests/adapters/render/golden/{raid,night,progression}.html`.
  - Regenerate one with `uv run pytest <its test file> --golden-update`, then read every hunk.
  - A hunk outside the task's intent is a finding: stop and report it.
  - The night page's `TRIMMED_NIGHT_BUDGET_BYTES` (101,000) is never raised silently.
- **The brief's code is a strong default, not scripture.** If a worked test or snippet fails, first
  diagnose whether the fixture or the implementation is wrong, change one, and report the evidence.
- **Before asserting on a literal, grep the tree for it** with the Grep tool. A Bash grep pattern
  containing a double quote silently reports 0.
- **A test changed on purpose is named, not silently edited.** Any other existing test that fails
  is a finding to report.
- **No network.** Never run `pytest -m e2e` or `wowperf` against the API in Tasks 1 and 2. Never
  open `.env` or `out/`.

## File Structure

| File | Change | Responsibility |
| --- | --- | --- |
| `src/wowperf/domain/analysis/night_rollups.py` | modify | `NEVER_TAKEN_ID`; the two findings from one helper; the fixed order |
| `tests/domain/analysis/test_night_rollups.py` | modify | the split, the majority bar, the mixed and single-reference records, the cap, the order |
| `tests/domain/report/test_progression_ledger.py` | modify | the new id places to `lead_rows` |
| `tests/test_cli_night.py` | modify | the harness's one hostile ability lands on whichever finding its references put it on |
| `tests/e2e/test_night_e2e.py` | modify | the fixed order includes the new id |
| `src/wowperf/domain/report/progression_model.py`, `src/wowperf/domain/analysis/night_service.py` | modify | comments naming the rollups |
| `.claude/skills/mplus-analysis/SKILL.md`, `.claude/skills/analyzing-a-run/SKILL.md`, `README.md` | modify | the two findings and the summary's order |

---

### Task 1: Two findings from one rule

**Files:**
- Modify: `src/wowperf/domain/analysis/night_rollups.py`. Replace `_overlanding`, add the new id and
  details, and change the order in `analyse_night_rollups`.
- Test: `tests/domain/analysis/test_night_rollups.py`, `tests/domain/report/test_progression_ledger.py`,
  `tests/test_cli_night.py`

**Interfaces:**
- Consumes: `capped_line(count) -> str | None` and `MAX_REPEAT_ABILITIES` from
  `wowperf.domain.analysis.progression_repeats`; `fight_ranges`, `quantifier_for` and `quantity`
  from `wowperf.domain.findings`.
- Produces:
  - `NEVER_TAKEN_ID = "progression.lead.never_taken"`;
  - `analyse_night_rollups(attempts, pull_findings, mechanics_compared) -> list[Finding]`, whose
    output order is `progression.lead.kill_speed`, `progression.lead.verdicts`,
    `progression.lead.never_taken`, `progression.lead.overlanding`, each only where it fires.

The rule (spec §10.2):
- **The compared pulls.** These are the attempts whose fight id is in `mechanics_compared`. With
  fewer than two compared pulls, neither finding fires. A rule about what *keeps* landing needs two
  attempts, as `repeat_ability`'s `attempts_with_window < 2` guard does.
- **An ability counts** when the compared pulls reporting it are more than half of them:
  `len(pulls) * 2 > compared`. Each pull counts once, however many of its findings name the ability.
- **Never taken.** Every report of the ability, in every compared pull, has `quantifier == "none"`.
  That value is `quantifier_for(0, total)`, so no reference took it.
- **Taken more often.** Everything else, including a mixed record and an empty `quantifier`, which
  a single-reference reading carries.

- [ ] **Step 1: Read before writing**

Read `night_rollups.py` end to end, `capped_line` in `progression_repeats.py`, and
`mechanics._against_sample` (`src/wowperf/domain/comparison/mechanics.py`). Confirm that the
per-pull finding's `quantifier` is `quantifier_for(carrying, total)`, and find what a single-reference
reading (`_against_one`) sets it to. Read the harness test at `tests/test_cli_night.py` around line
1199, and find which quantifier the harness's references give its one hostile ability.

- [ ] **Step 2: Write the failing tests**

In `tests/domain/analysis/test_night_rollups.py`:

1. Add `NEVER_TAKEN = "progression.lead.never_taken"` beside the other ids.
2. Give the `over_landing` helper a keyword `references_took: str = ""` that sets the finding's
   `quantifier`. Existing calls stay as they are, reading as a single-reference report.

```python
def over_landing(
    rank: int, ability_id: int, name: str, *, references_took: str = ""
) -> Finding:
    """A `mechanics.ability.*` finding in the shape `compare_mechanics` writes it.

    `references_took` is the finding's quantifier, `quantifier_for(carrying,
    total)` over the references that took the ability at all: "none" for one no
    reference took, "" for a single-reference reading.
    """
    return Finding(
        id=f"mechanics.ability.{rank}",
        title=(
            f"This raid took {name} 3.0 times a minute where the references took a "
            "median of 1.0 a minute"
        ),
        detail="3.0 landings a minute against a reference median of 1.0.",
        confidence=Confidence.DERIVED,
        ability_id=ability_id,
        ability_name=name,
        quantifier=references_took,
    )
```

3. Add these tests:

```python
def test_an_ability_no_reference_took_in_most_compared_pulls_is_never_taken() -> None:
    attempts = [a_wipe(3), a_wipe(4), a_wipe(5)]
    pull_findings = {
        3: [over_landing(0, 9001, "Brinecoil Lash", references_took="none")],
        4: [],
        5: [over_landing(1, 9001, "Brinecoil Lash", references_took="none")],
    }

    found = analyse_night_rollups(attempts, pull_findings, frozenset({3, 4, 5}))
    rollup = the_rollup(found, NEVER_TAKEN)

    assert rollup.title == (
        "Brinecoil Lash landed in 2 of 3 compared attempts, where no reference kill took it"
    )
    assert rollup.evidence == (
        "Brinecoil Lash landed in 2 of 3 compared attempts (Fights 3 and 5)",
    )
    assert rollup.quantifier == "most"
    assert rollup.confidence is Confidence.DERIVED
    assert rollup.ability_id == 9001
    assert rollup.ability_name == "Brinecoil Lash"
    assert OVERLANDING not in [finding.id for finding in found]


def test_exactly_half_the_compared_pulls_is_not_most() -> None:
    """Two of four is about half: the bar is more than half, the rule `most` names."""
    attempts = [a_wipe(fight) for fight in (3, 4, 5, 6)]
    pull_findings = {
        3: [over_landing(0, 9001, "Brinecoil Lash", references_took="none")],
        4: [over_landing(0, 9002, "Marrow Squall")],
        5: [over_landing(1, 9001, "Brinecoil Lash", references_took="none")],
        6: [over_landing(1, 9002, "Marrow Squall")],
    }

    found = analyse_night_rollups(attempts, pull_findings, frozenset({3, 4, 5, 6}))

    assert [finding.id for finding in found] == []


def test_one_compared_pull_keeps_nothing() -> None:
    """What keeps landing needs two attempts, as `repeat_ability` requires."""
    attempts = [a_wipe(3)]
    pull_findings = {3: [over_landing(0, 9001, "Brinecoil Lash", references_took="none")]}

    found = analyse_night_rollups(attempts, pull_findings, frozenset({3}))

    assert NEVER_TAKEN not in [finding.id for finding in found]
    assert OVERLANDING not in [finding.id for finding in found]


def test_a_mixed_record_never_earns_the_stronger_claim() -> None:
    """No reference took it on two pulls, most did on the third: it goes to taken more often."""
    attempts = [a_wipe(3), a_wipe(4), a_wipe(5)]
    pull_findings = {
        3: [over_landing(0, 9001, "Brinecoil Lash", references_took="none")],
        4: [over_landing(0, 9001, "Brinecoil Lash", references_took="none")],
        5: [over_landing(0, 9001, "Brinecoil Lash", references_took="most")],
    }

    found = analyse_night_rollups(attempts, pull_findings, frozenset({3, 4, 5}))

    assert NEVER_TAKEN not in [finding.id for finding in found]
    assert the_rollup(found, OVERLANDING).title == (
        "Brinecoil Lash over-landed in 3 of 3 compared attempts"
    )


def test_a_single_reference_reading_goes_to_taken_more_often() -> None:
    """A reading against one reference carries no count of references, so no "none"."""
    attempts = [a_wipe(3), a_wipe(4)]
    pull_findings = {
        3: [over_landing(0, 9001, "Brinecoil Lash")],
        4: [over_landing(0, 9001, "Brinecoil Lash")],
    }

    found = analyse_night_rollups(attempts, pull_findings, frozenset({3, 4}))

    assert NEVER_TAKEN not in [finding.id for finding in found]
    assert the_rollup(found, OVERLANDING).title == (
        "Brinecoil Lash over-landed in 2 of 2 compared attempts"
    )


def test_one_boss_splits_its_abilities_between_the_two_findings() -> None:
    """Each finding counts only its own abilities, and never taken comes first."""
    attempts = [a_wipe(3), a_wipe(4), a_wipe(5)]
    never = "Brinecoil Lash"
    taken = "Marrow Squall"
    pull_findings = {
        fight: [
            over_landing(0, 9001, never, references_took="none"),
            over_landing(1, 9002, taken, references_took="every"),
        ]
        for fight in (3, 4, 5)
    }

    found = analyse_night_rollups(attempts, pull_findings, frozenset({3, 4, 5}))

    assert [finding.id for finding in found] == [NEVER_TAKEN, OVERLANDING]
    assert the_rollup(found, NEVER_TAKEN).ability_name == never
    assert the_rollup(found, OVERLANDING).ability_name == taken
    assert the_rollup(found, NEVER_TAKEN).quantifier == "every"


def test_several_abilities_no_reference_took_are_all_counted_and_capped() -> None:
    names = [f"Ability {letter}" for letter in "ABCDEFG"]
    attempts = [a_wipe(fight) for fight in (3, 4, 5)]
    pull_findings: dict[int, list[Finding]] = {3: [], 4: [], 5: []}
    for index, name in enumerate(names):
        for fight in ((3, 4, 5) if name == "Ability G" else (3, 4)):
            pull_findings[fight].append(
                over_landing(index, 100 + index, name, references_took="none")
            )

    rollup = the_rollup(
        analyse_night_rollups(attempts, pull_findings, frozenset({3, 4, 5})), NEVER_TAKEN
    )

    assert rollup.title == "7 abilities no reference kill took landed in most compared attempts"
    assert rollup.ability_id is None
    assert rollup.evidence == (
        "Ability G landed in 3 of 3 compared attempts (Fights 3–5)",
        "Ability A landed in 2 of 3 compared attempts (Fights 3–4)",
        "Ability B landed in 2 of 3 compared attempts (Fights 3–4)",
        "Ability C landed in 2 of 3 compared attempts (Fights 3–4)",
        "Ability D landed in 2 of 3 compared attempts (Fights 3–4)",
        "The evidence lists the 5 abilities most reported",
    )
```

**Deliberately changed** existing tests. Name each in the report:
- `test_several_abilities_are_all_counted_and_the_most_repeated_listed_first`: the title becomes
  `"7 abilities over-landed in most compared attempts"`.
- `test_abilities_the_cap_does_not_cut_carry_no_line_about_the_cap`: the title becomes
  `"5 abilities over-landed in most compared attempts"`.
- `test_the_rollups_come_in_their_fixed_order`:
  - give one pull's findings an ability with `references_took="none"` in two of its three compared
    pulls, so all four rollups fire;
  - the order becomes `[KILL_SPEED, VERDICTS, NEVER_TAKEN, OVERLANDING]`;
  - keep its `rank_raid_findings` half.
- `tests/domain/report/test_progression_ledger.py`: add `("progression.lead.never_taken", "lead_rows")`
  to the parametrized list.
- `tests/test_cli_night.py` (~1199-1204): the harness's one hostile ability lands on
  `progression.lead.never_taken` or `progression.lead.overlanding`, according to the quantifier its
  references give it (Step 1).
  - Assert the finding it actually lands on, with the exact title, and that the other id is
    absent.
  - Update the comment above it.

The existing tests `test_an_ability_over_landing_in_two_compared_pulls_is_named_once`,
`test_an_ability_reported_in_one_pull_does_not_repeat` and
`test_a_pull_not_compared_is_not_in_the_denominator` must pass unchanged: 2 of 3, 1 of 2 and 2 of
2 sit on the same side of the new bar as the old one.

- [ ] **Step 3: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis/test_night_rollups.py tests/domain/report/test_progression_ledger.py tests/test_cli_night.py -q`
Expected: the new tests fail. `progression.lead.never_taken` is never minted, and the changed titles
still read "more than one compared attempt".

- [ ] **Step 4: Implement**

In `night_rollups.py`, replace `OVERLANDING_DETAIL` and `_overlanding` with the code below. Keep
`MECHANICS_ABILITY_PREFIX` and `OVERLANDING_ID`. Rewrite the module docstring or ABOUTME lines only
if they no longer describe the file.

```python
NEVER_TAKEN_ID = "progression.lead.never_taken"

NO_REFERENCE_TOOK_IT = "none"
"""A per-pull `mechanics.ability.*` quantifier when no reference kill took the ability at all.

`compare_mechanics` sets that finding's quantifier to `quantifier_for(carrying,
total)` over the references that took the ability, so this is the one value
meaning none of them did. A single-reference reading carries no count of
references, so it never reads this.
"""

NEVER_TAKEN_DETAIL = (
    "Each compared pull names the abilities it took far more often than the reference kills "
    "did, and how many of those kills took each one at all. This counts the compared pulls "
    "naming an ability no reference kill took, never its hits, and names one only where more "
    "than half of them reported it. It states a difference, not a mistake: whether any landing "
    "could have been prevented is not something the log records."
)

OVERLANDING_DETAIL = (
    "Each compared pull names the abilities it took far more often than the reference kills "
    "did. This counts the compared pulls naming an ability the reference kills took too, never "
    "its hits, and names one only where more than half of them reported it; one no reference "
    "kill took at all is named under its own finding instead. It states a difference, not a "
    "mistake: whether any landing could have been prevented is not something the log records."
)


def _reported(
    compared: Sequence[Encounter], pull_findings: Mapping[int, Sequence[Finding]]
) -> tuple[dict[int, str], dict[int, list[int]], set[int]]:
    """Per ability, its name, the compared pulls reporting it, and whether any reference took it.

    Each pull counts once, however many of its findings name the ability. The
    returned set holds every ability some report said a reference took, so an
    ability outside it was reported, every time, as one no reference took.
    """
    names: dict[int, str] = {}
    pulls: dict[int, list[int]] = defaultdict(list)
    taken: set[int] = set()
    for one in compared:
        seen: set[int] = set()
        for found in pull_findings.get(one.fight_id, ()):
            if not found.id.startswith(MECHANICS_ABILITY_PREFIX) or found.ability_id is None:
                continue
            names.setdefault(found.ability_id, found.ability_name)
            if found.quantifier != NO_REFERENCE_TOOK_IT:
                taken.add(found.ability_id)
            if found.ability_id not in seen:
                seen.add(found.ability_id)
                pulls[found.ability_id].append(one.fight_id)
    return names, pulls, taken


def _kept_landing(
    finding_id: str,
    detail: str,
    ability_ids: Iterable[int],
    names: Mapping[int, str],
    pulls: Mapping[int, list[int]],
    total: int,
    *,
    head: Callable[[str, int, int], str],
    single: Callable[[str, int, int], str],
    several: Callable[[int], str],
) -> Finding | None:
    """The abilities among `ability_ids` reported in more than half of `total` compared pulls.

    The bar is `progression.repeat.ability`'s, and the one `quantifier_for`'s
    "most" names. The title counts every qualifying ability; only the evidence
    is capped at `MAX_REPEAT_ABILITIES`, and a cut list says so.
    """
    repeated = sorted(
        (one for one in ability_ids if len(pulls[one]) * 2 > total),
        key=lambda one: (-len(pulls[one]), names[one]),
    )
    if not repeated:
        return None
    named = repeated[:MAX_REPEAT_ABILITIES]
    cut_line = capped_line(len(repeated))
    lone = named[0] if len(repeated) == 1 else None
    top = len(pulls[named[0]])
    return Finding(
        id=finding_id,
        title=(
            single(names[lone], top, total) if lone is not None else several(len(repeated))
        ),
        detail=detail,
        confidence=Confidence.DERIVED,
        evidence=tuple(
            f"{head(names[one], len(pulls[one]), total)} ({fight_ranges(pulls[one])})"
            for one in named
        )
        + (() if cut_line is None else (cut_line,)),
        ability_id=lone,
        ability_name=names[lone] if lone is not None else "",
        quantifier=quantifier_for(top, total),
    )


def _over_landing(
    attempts: Sequence[Encounter],
    pull_findings: Mapping[int, Sequence[Finding]],
    mechanics_compared: frozenset[int],
) -> tuple[Finding | None, Finding | None]:
    """What kept landing that no reference kill took, then what landed more often than theirs.

    Both count the compared pulls only: a pull whose sample drew no member
    compared nothing, so it is left out of the denominator rather than counted
    as a pull where nothing over-landed. With fewer than two compared pulls
    nothing can be said to keep landing, so neither fires. An ability whose
    reports disagree goes to the second: a mixed record never earns the
    stronger claim.
    """
    compared = [one for one in attempts if one.fight_id in mechanics_compared]
    if len(compared) < 2:
        return None, None
    names, pulls, taken = _reported(compared, pull_findings)
    total = len(compared)
    never_taken = _kept_landing(
        NEVER_TAKEN_ID,
        NEVER_TAKEN_DETAIL,
        (one for one in pulls if one not in taken),
        names,
        pulls,
        total,
        head=lambda name, n, of: f"{name} landed in {n} of {of} compared attempts",
        single=lambda name, n, of: (
            f"{name} landed in {n} of {of} compared attempts, where no reference kill took it"
        ),
        several=lambda count: (
            f"{quantity(count, 'ability', 'abilities')} no reference kill took landed in "
            "most compared attempts"
        ),
    )
    over_landing = _kept_landing(
        OVERLANDING_ID,
        OVERLANDING_DETAIL,
        (one for one in pulls if one in taken),
        names,
        pulls,
        total,
        head=lambda name, n, of: f"{name} over-landed in {n} of {of} compared attempts",
        single=lambda name, n, of: f"{name} over-landed in {n} of {of} compared attempts",
        several=lambda count: (
            f"{quantity(count, 'ability', 'abilities')} over-landed in most compared attempts"
        ),
    )
    return never_taken, over_landing
```

Add `Callable` to the `collections.abc` import. Then change `analyse_night_rollups`:

```python
    never_taken, over_landing = _over_landing(attempts, pull_findings, mechanics_compared)
    candidates = (
        _kill_speed(attempts, pull_findings),
        _verdicts(attempts, pull_findings),
        never_taken,
        over_landing,
    )
    return [one for one in candidates if one is not None]
```

Rewrite its docstring's first line to "Kill speed, then why wipes ended, then what no reference took,
then what over-landed: each where it fires." Keep the rest of the docstring true.

`quantity(1, 'ability', 'abilities')` never reaches a `several` title, which fires only with two or
more. It stays for consistency with every other count.

- [ ] **Step 5: Run the focused tests, then everything**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis/test_night_rollups.py tests/domain/report/test_progression_ledger.py tests/test_cli_night.py -q`
Expected: PASS.

Then run `uv run pytest -q`, `uv run ruff check .` and `uv run mypy`.
- If the night or progression golden moves, regenerate it and read the hunks. The night golden's
  fixture hands no mechanics findings, so it should not move.
- Report the night page's size if it changes.

Give mutation evidence for each of these, showing the named test fails:
- `len(pulls[one]) * 2 > total` changed to `>=`;
- the `len(compared) < 2` guard removed;
- `taken.add` skipped for `"most"`, so the mixed record goes to never taken;
- the order swapped;
- `named` used in place of `repeated` in the title count.

- [ ] **Step 6: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/analysis/night_rollups.py tests/domain/analysis/test_night_rollups.py tests/domain/report/test_progression_ledger.py tests/test_cli_night.py
/mingw64/bin/git commit -m "Split what keeps over-landing into never taken and taken more often" -m "Two appearances in pulls whose own lists are capped at five named every boss's top five; most of those were abilities no reference kill took at all, a different claim from taking one more often. Each now has its own finding, past more than half the compared pulls." -m "Co-Authored-By: ..."
```

---

### Task 2: The skills, the README and the end-to-end order

**Files:**
- Modify: `.claude/skills/mplus-analysis/SKILL.md`. Replace the `progression.lead.overlanding`
  bullet (~line 77) with two bullets, `progression.lead.never_taken` then
  `progression.lead.overlanding`.
- Modify: `.claude/skills/analyzing-a-run/SKILL.md` (~line 229), the night summary's lead order.
- Modify: `README.md` (~line 109), "which abilities kept landing harder than they did for the
  reference kills".
- Modify: `src/wowperf/domain/report/progression_model.py:126`, the `lead_rows` comment.
- Modify: `src/wowperf/domain/analysis/night_service.py:41`. Rewrite the docstring only if it is now
  false.
- Modify: `tests/e2e/test_night_e2e.py` (~line 463), the fixed-order tuple.
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: `progression.lead.never_taken` and the narrowed `progression.lead.overlanding` from Task 1.

- [ ] **Step 1: Write the prose**

The `mplus-analysis` bullets cover, for each finding:
- what it counts: compared pulls, never hits;
- its bar: more than half the compared pulls, and at least two compared pulls;
- its badge: `derived`;
- its quantifier: the top ability's, so only `most` or `every`;
- that the title counts every qualifying ability and the evidence is capped, with a last line
  saying so.

For `never_taken`, also say:
- it means no reference kill took the ability at all;
- a mixed or single-reference record goes to `overlanding`;
- write "no reference kill took it" and never "avoidable".

`analyzing-a-run` and the README give the lead's order: kill speed, why the wipes ended, what kept
landing that no reference kill took, what kept landing harder than it did for the kills, and then
the repeats. State no number from any real report.

- [ ] **Step 2: The end-to-end order**

In `tests/e2e/test_night_e2e.py`, the fixed-order tuple becomes:

```python
            one for one in (
                "progression.lead.kill_speed",
                "progression.lead.verdicts",
                "progression.lead.never_taken",
                "progression.lead.overlanding",
            ) if one in lead_ids
```

Do not run it: it needs the network. The controller runs it in Task 3.

- [ ] **Step 3: Run the skill test and the suite**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_skills.py -q && uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
/mingw64/bin/git add .claude/skills README.md src/wowperf/domain/report/progression_model.py src/wowperf/domain/analysis/night_service.py tests/e2e/test_night_e2e.py
/mingw64/bin/git commit -m "Say what the two over-landing findings count" -m "The skills and the README described one rollup at a two-pull threshold." -m "Co-Authored-By: ..."
```

---

### Task 3: Live verification

Run by the controller, not a subagent: it spends quota and reads real players' logs.

- [ ] **Step 1: The night end-to-end test**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -m e2e tests/e2e/test_night_e2e.py -q`

- [ ] **Step 2: The live distribution**

Run `wowperf night` on `6jHcTvtB4XAMGZag` and `cW38jmwdnZfbHVL4` (warm cache, `--out out/live`). For
each boss with compared pulls, report how many abilities each finding names and its quantifier,
without printing a player name. The spec predicts:

| Boss | Never taken | Taken more often |
| --- | --- | --- |
| Mythic, seven pulls | 3 | 1 |
| Mythic, thirteen pulls | 3 | none |
| Heroic, seven pulls | 4 | 1 |

A state that never occurs is investigated, not accepted. That includes the single-ability title of
either finding.

- [ ] **Step 3: Commit anything the live run changed**

If the end-to-end test needed a change, commit it with its reason.
