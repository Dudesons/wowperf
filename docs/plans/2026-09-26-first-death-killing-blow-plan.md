# First-death killing blow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new progression finding, `progression.repeat.killing_blow`, counting per ability how many of a boss's attempts had their first death dealt by it -- on the standalone progression page and in every night summary.

**Architecture:** A shared `lethal_hit` helper in `recap.py` returns the hit a death names (so `killing_blow_ms` and the new finding make one match, not two). `repeat_killing_blow` in `progression_repeats.py` reads each attempt's first death through the same `_earliest_death` that `repeat_first_death` uses, and `analyse_progression` calls it. The existing `progression.repeat.` placement puts it on the Repeats tab; no page, template, command or JSON shape changes.

**Tech Stack:** Python 3.12, pydantic frozen models, Jinja2, pytest. `uv` only: in Bash, `/c/Users/damien/.local/bin/uv.exe`.

**Spec:** `docs/plans/2026-09-26-first-death-killing-blow-design.md`. Read it before Task 1.

## Global Constraints

- The death read is each drawn attempt's `_earliest_death` (`progression_repeats.py:156`), the same function `repeat_first_death` uses (spec §4).
- An attempt drops out when: it has no death; its first death matches no roster `actor_id`; `killing_blow_id == 0`; or its lethal hit's `source_id` is a roster player's. No matching lethal hit, or a hit with `source_id` None, keeps the attempt (spec §4).
- An ability is named at a count of at least 2; ordered by count descending, then name; capped at `MAX_REPEAT_ABILITIES` (5). Withheld when fewer than two attempts qualify or no ability reaches two (spec §4).
- No control subtraction against the deepest attempt (spec §4).
- Confidence `measured`. Exactly one ability named: title `"<ability> dealt the first death in <n> of <m> attempts"`, with `ability_id` and `ability_name` set. Several: title `"<k> abilities dealt the first death in more than one attempt"`, no `ability_id`. `m` is the qualifying-attempt count (spec §4).
- The finding names no player and no specialisation (spec §4).
- No new query, stream or JSON field; no template or command change (spec §3).
- `src/wowperf/domain/` performs no I/O (CLAUDE.md).
- No real character name in `tests/`: only `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`. Players on report `cW38jmwdnZfbHVL4` are referred to by class, spec, role or index.
- Every new test is shown able to fail: break the line it guards, watch it go red, restore. Read `.claude/skills/testing/test-driven-development/SKILL.md` before writing the first test.
- Commits: imperative subject, no prefix, body says why, plain ASCII, last line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Commit with `/mingw64/bin/git`. Never `--no-verify`.
- Gate after every task: `uv run ruff check .`, `uv run mypy`, `uv run pytest` -- green, output pristine.

---

### Task 1: One match for the hit a death names

**Files:**
- Modify: `src/wowperf/domain/analysis/recap.py` (`killing_blow_ms` at :249-274)
- Test: `tests/domain/analysis/test_recap_availability.py` (beside the `killing_blow_ms` tests at :59-118)

**Why this task exists.** The new finding needs the lethal hit's `source_id`; `killing_blow_ms` already makes exactly that match but returns only its timestamp. Copying its six-line match into `progression_repeats.py` would leave two definitions of "the hit that killed this player" free to drift. This task extracts the match and changes nothing `killing_blow_ms` returns.

**Interfaces:**
- Produces: `lethal_hit(damage_taken: tuple[DamageTakenEvent, ...], death: Death) -> DamageTakenEvent | None` in `wowperf.domain.analysis.recap`. `killing_blow_ms(damage_taken, death)` keeps its signature and every result.

- [ ] **Step 1: Write the failing tests**

Add after `test_a_death_naming_no_ability_at_all_has_no_moment`, and add `lethal_hit` to the file's import from `wowperf.domain.analysis.recap`:

```python
# --- the blow itself ------------------------------------------------------------
#
# `killing_blow_ms` answers when; `lethal_hit` answers which row, so a caller can
# read who dealt it. The two must agree on every death, or one page would name a
# moment another reader traces to a different hit.


def a_hit_from(at_ms: int, ability_id: int, source_id: int | None) -> DamageTakenEvent:
    return DamageTakenEvent(actor_id=1, ability_id=ability_id, ability_name="x",
                            amount=1, health_damage=1, timestamp_ms=at_ms,
                            source_id=source_id)


def test_the_lethal_hit_is_the_row_the_moment_is_read_from() -> None:
    """The same stream `killing_blow_ms` is tested against, returning the row itself."""
    blow = a_hit_from(BLOW_MS, BLOW_ID, source_id=4242)
    stream = (a_hit_from(9_989_000, BLOW_ID, 1111), blow, a_hit_from(9_997_405, OTHER_ID, 2222))

    assert lethal_hit(stream, a_death_by(BLOW_ID)) == blow
    assert lethal_hit(stream, a_death_by(BLOW_ID)).source_id == 4242  # type: ignore[union-attr]


def test_a_hit_after_the_death_is_never_its_lethal_hit() -> None:
    stream = (a_hit_from(BLOW_MS, BLOW_ID, 1), a_hit_from(9_999_000, BLOW_ID, 2))

    hit = lethal_hit(stream, a_death_by(BLOW_ID))
    assert hit is not None
    assert hit.timestamp_ms == BLOW_MS


def test_no_lethal_hit_where_the_stream_lacks_it_or_the_log_named_nothing() -> None:
    assert lethal_hit((a_hit(BLOW_MS, OTHER_ID),), a_death_by(BLOW_ID)) is None
    assert lethal_hit((a_hit(BLOW_MS, 0),), a_death_by(0)) is None
```

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/analysis/test_recap_availability.py -v`
Expected: FAIL at import -- `cannot import name 'lethal_hit'`.

- [ ] **Step 3: Extract the match**

Replace `killing_blow_ms` in `recap.py` with the pair below. Keep `killing_blow_ms`'s docstring whole, and add the one sentence marked.

```python
def lethal_hit(
    damage_taken: tuple[DamageTakenEvent, ...], death: Death
) -> DamageTakenEvent | None:
    """The hit this death names as its killing blow, or None where the stream does not carry it.

    The one definition of "the hit that killed this player": the latest hit on
    the dying player carrying the death's own `killing_blow_id`, at or before
    the death. `killing_blow_ms` reads its moment and a progression finding
    reads its source, so both answer from the same row. A `killing_blow_id` of
    zero is the log naming no ability, and matches nothing.
    """
    if not death.killing_blow_id:
        return None
    hits = [
        hit
        for hit in damage_taken
        if hit.actor_id == death.actor_id
        and hit.ability_id == death.killing_blow_id
        and hit.timestamp_ms <= death.timestamp_ms
    ]
    return max(hits, key=lambda hit: hit.timestamp_ms) if hits else None


def killing_blow_ms(damage_taken: tuple[DamageTakenEvent, ...], death: Death) -> int | None:
    """...the existing docstring, unchanged...

    The match itself is `lethal_hit`'s; this reads only its moment.
    """
    hit = lethal_hit(damage_taken, death)
    return hit.timestamp_ms if hit is not None else None
```

`max(..., key=...)` returns the first of two hits sharing the latest timestamp; `killing_blow_ms` returned that timestamp before and still does.

- [ ] **Step 4: Run, pass, prove**

Run the file, then the full gate. The five existing `killing_blow_ms` tests must pass unchanged -- they are this refactor's guard. Prove the new tests can fail: change `<=` to `<` and watch the first new test go red; drop the `actor_id` condition and watch `test_the_same_ability_hitting_a_teammate_is_not_this_players_blow` go red. Restore.

- [ ] **Step 5: Commit**

Subject: `Name the hit a death was dealt by in one place`

---

### Task 2: Count what dealt each attempt's first death

**Files:**
- Modify: `src/wowperf/domain/analysis/progression_repeats.py` (new function after `repeat_first_death`, :168-214; ABOUTME line 1)
- Modify: `src/wowperf/domain/analysis/progression_service.py` (the loop at :139-146)
- Modify: `src/wowperf/adapters/render/html.py` (`render_progression`'s docstring at :264-269)
- Test: `tests/domain/analysis/test_progression_repeats.py`, `tests/domain/analysis/test_progression_service.py`, `tests/domain/report/test_progression_ledger.py` (:21-22), `tests/domain/analysis/test_severity.py` (:110-113)

**Interfaces:**
- Consumes: `lethal_hit` (Task 1); `_earliest_death(one: LoadedEncounter) -> Death | None` and `MAX_REPEAT_ABILITIES` (existing, this module); `_join_or` is **not** used -- abilities are listed, not offered as alternatives.
- Produces: `repeat_killing_blow(series: LoadedProgression) -> Finding | None`, id `progression.repeat.killing_blow`, called by `analyse_progression` immediately after `repeat_first_death`.

- [ ] **Step 1: Write the failing unit tests**

Add to `tests/domain/analysis/test_progression_repeats.py`, after the `repeat_first_death` tests, reusing that section's `ROSTER` and `series_of`. Import `repeat_killing_blow` beside the others and `DamageTakenEvent` from `wowperf.domain.events`.

```python
# --- progression.repeat.killing_blow ---

SOUL_LASH = 440_001
VOID_BOLT = 440_002
ENEMY = 90_001
"""An enemy's actor id: never a roster member's."""


def first_death_by(
    fight_id: int,
    ability_id: int,
    ability_name: str,
    *,
    source_id: int | None = ENEMY,
    lethal_hit: bool = True,
    dying: int = 0,
) -> LoadedEncounter:
    """One attempt whose first death -- `ROSTER[dying]`'s -- was dealt by `ability_id`.

    A later death by another ability follows, so a counter that read every
    death rather than the first would count `VOID_BOLT` on every attempt.
    `lethal_hit=False` leaves the stream without the killing hit, the honest
    unknown pagination can produce; `source_id` says who dealt it when it is
    there.
    """
    encounter = an_attempt(fight_id, 50.0, 200.0, players=ROSTER)
    start = encounter.start_ms
    victim = ROSTER[dying]
    other = ROSTER[1 - dying]
    deaths = (
        Death(player_name=victim.name, actor_id=victim.actor_id,
              timestamp_ms=start + 1_000, killing_blow=ability_name,
              killing_blow_id=ability_id),
        Death(player_name=other.name, actor_id=other.actor_id,
              timestamp_ms=start + 9_000, killing_blow="Void Bolt",
              killing_blow_id=VOID_BOLT),
    )
    hits = (
        DamageTakenEvent(actor_id=victim.actor_id, ability_id=ability_id,
                         ability_name=ability_name, amount=1, timestamp_ms=start + 990,
                         source_id=source_id),
    ) if lethal_hit else ()
    return LoadedEncounter(encounter=encounter, deaths=deaths, damage_taken=hits)


def test_names_the_ability_that_dealt_the_first_death_in_more_than_one_attempt() -> None:
    finding = repeat_killing_blow(series_of(
        first_death_by(1, SOUL_LASH, "Soul Lash"),
        first_death_by(2, SOUL_LASH, "Soul Lash"),
        first_death_by(3, 440_003, "Grasp"),
    ))
    assert finding is not None
    assert finding.id == "progression.repeat.killing_blow"
    assert finding.title == "Soul Lash dealt the first death in 2 of 3 attempts"
    assert finding.ability_id == SOUL_LASH
    assert finding.ability_name == "Soul Lash"
    assert finding.confidence is Confidence.MEASURED


def test_reads_only_the_first_death_of_each_attempt() -> None:
    """Every attempt's second death is a Void Bolt; it must never be counted."""
    finding = repeat_killing_blow(series_of(
        first_death_by(1, SOUL_LASH, "Soul Lash"),
        first_death_by(2, 440_003, "Grasp"),
    ))
    assert finding is None


def test_names_every_ability_reaching_two_most_first_with_no_icon() -> None:
    finding = repeat_killing_blow(series_of(
        first_death_by(1, SOUL_LASH, "Soul Lash"),
        first_death_by(2, SOUL_LASH, "Soul Lash"),
        first_death_by(3, SOUL_LASH, "Soul Lash"),
        first_death_by(4, 440_003, "Grasp"),
        first_death_by(5, 440_003, "Grasp"),
        first_death_by(6, 440_004, "Rend"),
    ))
    assert finding is not None
    assert finding.title == "2 abilities dealt the first death in more than one attempt"
    assert finding.ability_id is None
    assert finding.evidence == (
        "Soul Lash dealt the first death in 3 of 6 attempts",
        "Grasp dealt the first death in 2 of 6 attempts",
    )


def test_breaks_a_tie_in_count_by_name() -> None:
    finding = repeat_killing_blow(series_of(
        first_death_by(1, 440_003, "Grasp"),
        first_death_by(2, SOUL_LASH, "Soul Lash"),
        first_death_by(3, 440_003, "Grasp"),
        first_death_by(4, SOUL_LASH, "Soul Lash"),
    ))
    assert finding is not None
    assert [line.split(" dealt")[0] for line in finding.evidence] == ["Grasp", "Soul Lash"]


def test_caps_the_named_abilities_at_five() -> None:
    attempts = [
        first_death_by(10 * n + k + 1, 441_000 + n, f"Rite {n}")
        for n in range(6)
        for k in range(2)
    ]
    finding = repeat_killing_blow(series_of(*attempts))
    assert finding is not None
    assert len(finding.evidence) == 5


def test_is_silent_below_two_qualifying_attempts() -> None:
    assert repeat_killing_blow(series_of(first_death_by(1, SOUL_LASH, "Soul Lash"))) is None


def test_a_death_naming_no_ability_drops_its_attempt_from_the_count() -> None:
    finding = repeat_killing_blow(series_of(
        first_death_by(1, SOUL_LASH, "Soul Lash"),
        first_death_by(2, SOUL_LASH, "Soul Lash"),
        first_death_by(3, 0, "", lethal_hit=False),
    ))
    assert finding is not None
    assert finding.title == "Soul Lash dealt the first death in 2 of 2 attempts"


def test_a_first_death_a_raider_dealt_drops_its_attempt() -> None:
    """Friendly hits say nothing about what the encounter did (repeat.ability's rule)."""
    finding = repeat_killing_blow(series_of(
        first_death_by(1, SOUL_LASH, "Soul Lash"),
        first_death_by(2, SOUL_LASH, "Soul Lash"),
        first_death_by(3, SOUL_LASH, "Soul Lash", source_id=ROSTER[1].actor_id),
    ))
    assert finding is not None
    assert finding.title == "Soul Lash dealt the first death in 2 of 2 attempts"


def test_a_missing_lethal_hit_or_an_unnamed_source_keeps_its_attempt() -> None:
    finding = repeat_killing_blow(series_of(
        first_death_by(1, SOUL_LASH, "Soul Lash", lethal_hit=False),
        first_death_by(2, SOUL_LASH, "Soul Lash", source_id=None),
    ))
    assert finding is not None
    assert finding.title == "Soul Lash dealt the first death in 2 of 2 attempts"


def test_a_first_death_off_the_roster_drops_its_attempt() -> None:
    """A pet dies first, to the repeating ability: its attempt must not count.

    Built by hand rather than with `loaded_attempt_with_roster(..., None)`, whose
    pet death names no ability -- that attempt would be dropped by the
    zero-id rule and never reach the roster rule this test is about.
    """
    encounter = an_attempt(3, 50.0, 200.0, players=ROSTER)
    pet_first = LoadedEncounter(
        encounter=encounter,
        deaths=(
            Death(player_name="Unidentified", actor_id=999,
                  timestamp_ms=encounter.start_ms + 1_000, killing_blow="Soul Lash",
                  killing_blow_id=SOUL_LASH),
        ),
    )
    finding = repeat_killing_blow(series_of(
        first_death_by(1, SOUL_LASH, "Soul Lash"),
        first_death_by(2, SOUL_LASH, "Soul Lash"),
        pet_first,
    ))
    assert finding is not None
    assert finding.title == "Soul Lash dealt the first death in 2 of 2 attempts"


def test_reads_the_same_death_repeat_first_death_reads_on_a_tie() -> None:
    """Two deaths at one instant: the lower actor id is first, for both findings.

    The higher-id death is listed first and carries the repeating ability, so a
    function that took the stream's first-listed death would name it.
    """
    def tied(fight_id: int) -> LoadedEncounter:
        encounter = an_attempt(fight_id, 50.0, 200.0, players=ROSTER)
        start = encounter.start_ms
        high = Death(player_name=ROSTER[1].name, actor_id=ROSTER[1].actor_id,
                     timestamp_ms=start + 1_000, killing_blow="Void Bolt",
                     killing_blow_id=VOID_BOLT)
        low = Death(player_name=ROSTER[0].name, actor_id=ROSTER[0].actor_id,
                    timestamp_ms=start + 1_000, killing_blow="Soul Lash",
                    killing_blow_id=SOUL_LASH)
        return LoadedEncounter(encounter=encounter, deaths=(high, low))

    series = series_of(tied(1), tied(2))
    killing = repeat_killing_blow(series)
    first = repeat_first_death(series)
    assert killing is not None and first is not None
    assert killing.ability_name == "Soul Lash"
    assert ROSTER[0].spec in first.title


def test_never_names_a_player_or_a_specialisation() -> None:
    finding = repeat_killing_blow(series_of(
        first_death_by(1, SOUL_LASH, "Soul Lash"),
        first_death_by(2, SOUL_LASH, "Soul Lash"),
    ))
    assert finding is not None
    text = f"{finding.title} {finding.detail} {' '.join(finding.evidence)}"
    for word in ("Emberkin", "Stonewake", "Bríala", "Кириллица",
                 *(p.spec for p in ROSTER), *(p.class_name for p in ROSTER)):
        assert word not in text
```

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/analysis/test_progression_repeats.py -v`
Expected: FAIL at import -- `cannot import name 'repeat_killing_blow'`.

- [ ] **Step 3: Write the analyser**

In `progression_repeats.py`, import `lethal_hit` from `wowperf.domain.analysis.recap`, change ABOUTME line 1 to `# ABOUTME: What repeated across a night's attempts: the phase, the collapse, who fell first and to what.`, and add after `repeat_first_death`:

```python
def repeat_killing_blow(series: LoadedProgression) -> Finding | None:
    """Which abilities dealt each attempt's first death, counted across the night.

    Reads the death `_earliest_death` picks -- the one `repeat_first_death`
    reads -- so the two findings always speak of the same death on every pull.
    Only the first: on a wipe most deaths come after the raid has come apart,
    and counting them would measure what finishes a lost pull rather than what
    started it going wrong.

    An attempt drops out when its first death matches no roster player, names
    no ability (`killing_blow_id` zero), or was dealt by a roster player -- the
    rule `repeat.ability` applies to every hit, since a teammate's hit says
    nothing about the encounter. Where the stream holds no lethal hit, or the
    hit names no source, the attempt stays: the log still named the ability.

    Withheld below two qualifying attempts, or when no ability reaches two: a
    mode of one is not a pattern. No control subtraction against the deepest
    attempt, unlike `repeat_ability` -- a best attempt that also opened with
    this death is more reason to name it, not less. Measured: the log names the
    death and its blow, and the rest is counting. Names no player and no
    specialisation; who died first is `repeat_first_death`'s claim.
    """
    names: dict[int, str] = {}
    counts: Counter[int] = Counter()
    qualifying = 0
    for one in series.attempts_with_events:
        death = _earliest_death(one)
        if death is None or not death.killing_blow_id:
            continue
        roster = {player.actor_id for player in one.players}
        if death.actor_id not in roster:
            continue
        hit = lethal_hit(one.damage_taken, death)
        if hit is not None and hit.source_id is not None and hit.source_id in roster:
            continue
        qualifying += 1
        names.setdefault(death.killing_blow_id, death.killing_blow)
        counts[death.killing_blow_id] += 1

    if qualifying < 2:
        return None
    named = sorted(
        (ability_id for ability_id, count in counts.items() if count >= 2),
        key=lambda ability_id: (-counts[ability_id], names[ability_id]),
    )[:MAX_REPEAT_ABILITIES]
    if not named:
        return None

    lines = tuple(
        f"{names[ability_id]} dealt the first death in {counts[ability_id]} of "
        f"{qualifying} attempts"
        for ability_id in named
    )
    single = named[0] if len(named) == 1 else None
    return Finding(
        id="progression.repeat.killing_blow",
        title=(
            lines[0]
            if single is not None
            else f"{len(named)} abilities dealt the first death in more than one attempt"
        ),
        detail=(
            f"Across the {qualifying} attempts whose first death was a roster player "
            "killed by an ability the log named: "
            + "; ".join(lines)
            + ". Only each attempt's first death is read -- the one the rest of a wipe "
            "cannot swamp -- and an attempt whose first death a raider dealt is left out. "
            "This counts what the log names; it does not say the death could have been "
            "avoided."
        ),
        confidence=Confidence.MEASURED,
        evidence=lines,
        ability_id=single,
        ability_name=names[single] if single is not None else "",
    )
```

Check `Finding`'s field names and defaults in `src/wowperf/domain/findings.py` before relying on `ability_id`/`ability_name` -- the ledger's `_split_title` needs the ability's name to appear exactly once in the title for the icon, which the single-ability title satisfies.

- [ ] **Step 4: Run, pass, prove the unit tests**

Run the file. Then, one at a time, prove each guard: read every death instead of the first (`test_reads_only_the_first_death_of_each_attempt` red); drop the roster-source check (`..._a_raider_dealt_...` red); drop the `hit is not None` guard so a missing hit drops the attempt (`..._missing_lethal_hit_...` red); change `>= 2` to `>= 1`; remove the `[:MAX_REPEAT_ABILITIES]` slice; sort by name before count. Restore after each.

- [ ] **Step 5: Wire it into the service, test first**

Add to `tests/domain/analysis/test_progression_service.py`:

```python
def test_the_killing_blow_finding_follows_the_first_death_it_reads() -> None:
    """Emitted by the service, right after `repeat_first_death` -- they read one death."""
    from tests.domain.analysis.test_progression_repeats import SOUL_LASH, first_death_by

    found = ids(analyse_progression(a_loaded_series(
        first_death_by(1, SOUL_LASH, "Soul Lash"),
        first_death_by(2, SOUL_LASH, "Soul Lash"),
    )))

    assert "progression.repeat.killing_blow" in found
    assert found.index("progression.repeat.killing_blow") == (
        found.index("progression.repeat.first_death") + 1
    )
```

Check that `ids` and `a_loaded_series` are already in scope in that file; import `a_loaded_series` from `tests.domain.progression_fixtures` if not. Run it (FAIL: not in list), then in `progression_service.py` import `repeat_killing_blow` and insert `repeat_killing_blow(series),` directly after `repeat_first_death(series),` in the loop at :139-146. Run again: PASS. `test_the_layer_three_finding_is_appended_after_layer_two` must still pass unchanged: its fixture's deaths name no ability, so the new finding stays silent there.

- [ ] **Step 6: The two id lists, and one docstring**

- `tests/domain/report/test_progression_ledger.py:21-22`: add `("progression.repeat.killing_blow", "repeat_rows"),` after the first-death row.
- `tests/domain/analysis/test_severity.py:110-113`: this loop requires each listed id to fire from `a_deepened_trio`, which names no killing blow. Do **not** add the id there. Instead add a second assertion below the loop that `SEVERITY_BY_FAMILY` covers `"progression"` for `analyse_progression(a_loaded_series(first_death_by(1, SOUL_LASH, "Soul Lash"), first_death_by(2, SOUL_LASH, "Soul Lash")))` -- every finding's family, the same check the existing loop's tail makes -- so the new finding is ranked on a known severity.
- `src/wowperf/adapters/render/html.py:264-269`: `render_progression`'s docstring says `progression.repeat.ability` "is the one finding that does" name an ability. Now two do. Rewrite the sentence to name both, keeping the rest of the paragraph.

- [ ] **Step 7: Gate and commit**

Full gate. Subject: `Count what dealt each attempt's first death`

---

### Task 3: Pin the row on the progression page

**Files:**
- Modify: `tests/adapters/render/test_progression_html_invariants.py` (`a_progression_findings` at :132-165)
- Modify: `tests/adapters/render/golden/progression.html` (regenerated)
- Modify: `docs/plans/2026-09-26-first-death-killing-blow-design.md` (§5 "Goldens")

**Why a hand-built finding.** The standalone progression golden is rendered from `a_progression_findings()` -- hand-built findings, one per tab -- not by running the analyser. So the design's §5 wording ("the fixture is changed so its first deaths repeat a killing blow") would pin nothing. The golden's job is placement and rendering; the analyser is pinned by Task 2's unit tests. This task adds one hand-built `progression.repeat.killing_blow` finding and amends §5 to say so.

**Interfaces:**
- Consumes: `progression.repeat.killing_blow`'s id and the single-ability title shape (Task 2).

- [ ] **Step 1: Write the failing test**

Add a finding to `a_progression_findings()`, after the `progression.repeat.phase` one:

```python
        Finding(
            id="progression.repeat.killing_blow",
            title="Frigid Roar dealt the first death in 3 of 7 attempts",
            detail="Across the 7 attempts whose first death was a roster player: Frigid Roar dealt 3.",
            confidence=Confidence.MEASURED,
            evidence=("Frigid Roar dealt the first death in 3 of 7 attempts",),
            ability_id=1_309_919,
            ability_name="Frigid Roar",
        ),
```

Its title differs from every other title in the tuple, as the docstring requires. Then add:

```python
def test_the_first_death_killing_blow_is_drawn_on_the_repeats_tab() -> None:
    html = a_progression_page()
    repeats = html.split('id="tab-repeats"', 1)[1].split("</section>", 1)[0]
    assert "finding-progression.repeat.killing_blow" in repeats
```

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/adapters/render/test_progression_html_invariants.py -v`
Expected: the new test PASSES (placement already exists) and the golden test FAILS -- the page now carries a row the golden lacks. Prove the new test can fail: temporarily change the finding's id to `progression.cluster.killing_blow` (which places on Attempts) and watch it go red; restore.

- [ ] **Step 2: Regenerate and read the golden**

Run with `--golden-update`, then without. Read the diff of `golden/progression.html` by eye: exactly one new card on the Repeats tab, carrying the Frigid Roar name, and nothing else moved. Only `golden/progression.html` may change -- if the night, raid or minimal goldens move, stop and report.

- [ ] **Step 3: Confirm the night golden did not move**

`tests/adapters/render/test_night_html_invariants.py` renders real `analyse_progression` findings over fixtures whose deaths carry `killing_blow_id` 0, so the new finding cannot fire there and `golden/night.html` must pass unregenerated. If it fails, stop and report: the analyser fired on a death naming no ability.

- [ ] **Step 4: Amend the design**

In the design's §5 "Goldens" bullet, replace the sentence about changing the fixture's first deaths with: the standalone progression golden is rendered from hand-built findings, so it carries one hand-built `progression.repeat.killing_blow` finding, which pins placement and rendering; the analyser itself is pinned by its unit tests; the night golden's fixtures name no killing blow, so it does not move.

- [ ] **Step 5: Gate and commit**

Subject: `Pin the first-death killing blow on the progression page`

---

### Task 4: Exercise it on the real report

**Files:**
- Modify: `tests/e2e/test_night_e2e.py`
- Modify: `docs/plans/2026-09-26-first-death-killing-blow-design.md` (§6 "End to end", and the status line)

**This task is not optional.** A new judgement is not done until a live run has exercised it, and a state that never occurs is a defect.

**A departure from the design, recorded in Step 4.** Spec §6 asks the night e2e to compare the finding's presence against "an independent count over its loaded first deaths". Written in the test, that count is the analyser's own rule re-implemented -- it would share any mistake the analyser makes. The e2e asserts shape instead, the unit tests pin the rule, and the live distribution in Step 3 is the measurement.

- [ ] **Step 1: Extend the night e2e**

In `test_a_whole_report_reads_as_one_night`, after the existing per-boss summary checks, for every boss with a summary:

```python
        blow = next(
            (f for f in payload["bosses"][index]["findings"]
             if f["id"] == "progression.repeat.killing_blow"),
            None,
        )
        if blow is not None:
            # Shape only: between one and five abilities, each at two or more
            # attempts and never more than the boss was pulled.
            counts = [
                int(m.group(1)) for m in
                (re.search(r"dealt the first death in (\d+) of \d+ attempts", line)
                 for line in blow["evidence"])
                if m
            ]
            assert 1 <= len(counts) == len(blow["evidence"]) <= 5
            assert all(2 <= count <= PULLS_PER_BOSS[index] for count in counts)
            assert blow["confidence"] == "measured"
```

Read the file first and use its existing names for the payload and the boss index. No assertion may print an ability or player name in its failure message beyond what pytest's own introspection shows for these integers.

- [ ] **Step 2: Run both e2e suites once, live**

Read `.claude/skills/wcl-api/SKILL.md`'s rate-limit sections first.

Run: `/c/Users/damien/.local/bin/uv.exe run pytest -m e2e tests/e2e/test_night_e2e.py tests/e2e/test_progression_e2e.py -v -s`
Expected: both PASS, spending about 111 and under 40 points. The progression suite's existing no-roster-name check now covers the new finding's text. Run once; on failure, diagnose from the output before any second run.

- [ ] **Step 3: Report the distribution**

Run `/c/Users/damien/.local/bin/uv.exe run wowperf night cW38jmwdnZfbHVL4` over the warm default cache and read `out/cW38jmwdnZfbHVL4.night.json` (never the HTML). For each of the three summary bosses (indices 1, 6, 7; 2, 2 and 7 pulls): whether `progression.repeat.killing_blow` fired, how many abilities it named, and the counts. If it fires on none of the three, read the raw first-death killing blows from the cache -- `repository.load_night` and `load_night_attempts` over `DEFAULT_CACHE_DIR`, the first roster death per drawn attempt by `(timestamp_ms, actor_id)`, and its `killing_blow_id` and `killing_blow` -- and report whether every first death fell to a different ability (the data) or the analyser missed a repeat (a defect). Report abilities by name only if the finding itself names them; never a player.

- [ ] **Step 4: Amend the design**

§6 "End to end": replace the "independent count" sentence with what Step 1 asserts and why. Status line: `approved design, planned in docs/plans/2026-09-26-first-death-killing-blow-plan.md.`

- [ ] **Step 5: Commit**

Subject: `Exercise the first-death killing blow on a real report`. Body records the points spent and the distribution headline.

---

## What this plan deliberately does not build

- Deaths after the first, in any form (spec §2, §7).
- Family 2 of spec B: deaths per player across pulls and what each had available.
- Any claim that an ability caused a wipe or that a death was avoidable.
- Any change to `METHOD_NO_ANATOMY` or to the night or progression templates.
