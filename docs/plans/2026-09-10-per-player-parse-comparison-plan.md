# The Per-Player Parse Comparison (J2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `analyze` run the top-parse comparison for any member of the roster the reader
names, or for the whole group, instead of only for the subject.

**Architecture:** A finding's identity becomes (family, rank, player). One pure function mints
every player's slug once; the slug is appended to each parse-family finding id and carried as a
field on `Finding`. `compare()` splits into a run half run once and a per-player half run per
subject, with the per-player-ness carried by a `ComparisonSubject` type rather than by an
argument convention. The report already has an empty slot per card; this fills the ones the
reader asked for and states plainly why the rest are empty.

**Tech Stack:** Python 3.12, `uv`, pydantic v2 (`Frozen`), typer, Jinja2, pytest, ruff, mypy
strict.

**Spec:** `docs/plans/2026-09-10-per-player-parse-comparison-design.md`

## Global Constraints

Copied from the spec and from `CLAUDE.md`. Every task's requirements implicitly include these.

- **The domain performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`,
  or anything touching the network, the disk or a template.
- **Every finding carries a confidence badge** — `measured`, `derived`, or `inferred`.
- **The report loads nothing.** One HTML file, no stylesheet link, no `@import`, no remote
  `src`, exactly one inline script. `tests/adapters/render/test_html_invariants.py` enforces
  every clause and none of them is relaxed by this work.
- **Never invent an API field name.** Verified names live in `.claude/skills/wcl-api/SKILL.md`
  with the date checked. This plan adds no new query.
- **The LLM never computes a number**; the narrative contains no digits.
- **Never delete or weaken a test because it fails.** Raise it with RwlRwlRwlRwl.
- **Never put a real character name into `tests/`.** The sanctioned set is `Emberkin`,
  `Stonewake`, `Bríala`, `Кириллица`. Invented reference-side names such as `Fastclear` are
  fine; the run's own five players are real people.
- **Never accumulate a corpus of other players' logs** (RPGLogs §5d). `ReferenceRecord` carries
  a link and never a figure. Do not add one.
- **Speed-axis finding ids are never suffixed with a player.** `compare.route.*`,
  `compare.tempo.*`, `compare.downtime`, `compare.deaths`, `compare.interrupts`,
  `compare.duration`, `compare.confound.*` and `compare.speed.unavailable` are statements about
  the run.
- **Two `# ABOUTME: ` lines** at the top of any new file. Comments are evergreen — never refer
  to a refactor or to "the new" anything.
- **Ruff line length is 100.**
- **Invoke git as `/mingw64/bin/git`.** A user-level hook rewrites bare `git`.
- **Commit messages are plain ASCII**, imperative mood, no `feat:` / `fix:` prefix. The subject
  says what the repository now does; the body says why. Write "section 5", never a section sign.
  Final line exactly `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Stage by name.** Never `git add -A`, never anything under `out/` or `cache/`.
- **Forbidden git flags:** `--no-verify`, `--no-hooks`, `--no-pre-commit-hook`.
- **The gate**, run before every commit:
  `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
  (`mypy` takes its paths from `pyproject.toml` — pass none).

---

## File Structure

| File | Responsibility after this work |
| --- | --- |
| `src/wowperf/domain/findings.py` | `Finding` gains `player_slug`, empty on anything not about one player |
| `src/wowperf/domain/report/players.py` | `player_slug` unchanged; new `slugs_by_actor`; `build_players` filters comparison rows by slug and builds one Section per card |
| `src/wowperf/domain/report/frame.py` | `parse_unavailable_id(slug)`; the `NOT_REQUESTED` reason |
| `src/wowperf/domain/report/model.py` | `ReferenceRecord` gains `player_slug` |
| `src/wowperf/domain/report/build.py` | Threads the compared slugs; assembles the withheld list from the cards |
| `src/wowperf/domain/comparison/service.py` | `ComparisonSubject`; the split `compare()`; the one place a slug reaches an id |
| `src/wowperf/cli.py` | Repeatable `--player`, `--all-players`, one parse sample per subject, the JSON's `comparison.players` |

The five comparison modules (`spells.py`, `uptime.py`, `route.py`, `tempo.py`, `confounds.py`)
are **not modified**. They keep minting plain ids; `service.py` re-mints the per-player ones. This
is why the plan is seven tasks and not fifteen.

---

## Task 1: One slug per player, independent of card order

**Files:**
- Modify: `src/wowperf/domain/report/players.py`
- Test: `tests/domain/report/test_build_players.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `slugs_by_actor(run: Run) -> dict[int, str]`, exported from
  `wowperf.domain.report.players`. Every later task that needs a player's fragment id calls this
  and never recomputes one.

**Why this is first.** `build_players` currently mints the card slug from its own `enumerate`
index *after* sorting the subject first, so a player's fragment id changes when a different
`--player` reorders the cards. Once the slug is load-bearing for finding ids, two independent
computations of it become a defect waiting for a name with an accent in it. Keying on the roster's
own order also gives a better property for free: a deep link into a report survives re-running
with a different subject.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/report/test_build_players.py`. `a_player`, `a_run`, `a_loaded` and
`a_pull` already exist in that file and in `tests/domain/report/test_build_frame.py`.

```python
def test_two_names_that_reduce_to_one_slug_stay_apart() -> None:
    # Bríala and Briala both reduce to "briala"; the roster index separates them.
    run = a_run(
        players=(a_player(actor_id=1, name="Bríala"), a_player(actor_id=2, name="Briala")),
        pulls=(a_pull(0, 0, 120_000),),
    )
    slugs = slugs_by_actor(run)
    assert slugs[1] != slugs[2]
    assert slugs[1].startswith("briala")
    assert slugs[2].startswith("briala")


def test_a_slug_does_not_change_when_a_different_player_is_the_subject() -> None:
    first = a_player(actor_id=1, name="Emberkin")
    second = a_player(actor_id=2, name="Stonewake")
    loaded = a_loaded(players=(first, second))
    findings: tuple[Finding, ...] = ()

    subject_first = build_players(
        loaded, findings, a_parse(), first, {}, Defensives(), ThroughputCooldowns()
    )
    subject_second = build_players(
        loaded, findings, a_parse(), second, {}, Defensives(), ThroughputCooldowns()
    )

    by_name_first = {card.name: card.slug for card in subject_first}
    by_name_second = {card.name: card.slug for card in subject_second}
    assert by_name_first == by_name_second
```

Add `slugs_by_actor` to the existing import from `wowperf.domain.report.players`, and `Finding`
is already imported.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_players.py -q
```

Expected: `ImportError: cannot import name 'slugs_by_actor'`.

- [ ] **Step 3: Add `slugs_by_actor`**

In `src/wowperf/domain/report/players.py`, directly below `player_slug`:

```python
def slugs_by_actor(run: Run) -> dict[int, str]:
    """Every player's fragment id, keyed by actor id.

    Computed from the roster's own order, not from the order the cards are
    drawn in, so a player's fragment id does not move when a different subject
    reorders the cards -- a deep link into a report stays valid across a
    re-run that named someone else. Two display names can reduce to the same
    slug, so the roster index is appended to keep them apart.

    This is the only place a slug is minted. The comparison's finding ids and
    the card they belong to both read from here, and that agreement is what
    makes a `#finding-...` link land in the right sub-tab.
    """
    names = display_names(run)
    return {
        player.actor_id: f"{player_slug(names[player.actor_id])}-{index}"
        for index, player in enumerate(run.players)
    }
```

`Run` needs adding to the existing `from wowperf.domain.model import ...` line.

- [ ] **Step 4: Point `build_players` at it**

In `build_players`, add below the existing `names_by_actor = display_names(loaded.run)`:

```python
    slugs = slugs_by_actor(loaded.run)
```

and replace the card's `slug=f"{player_slug(display_name)}-{index}"` with:

```python
                slug=slugs[summary.actor_id],
```

`index` remains in use by nothing else in the loop; if `enumerate` is now unused, drop it and
iterate `summaries` directly. Update the `PlayerCard.slug` docstring in
`src/wowperf/domain/report/model.py`, which says "suffixed with the card's index": it is now the
roster index.

- [ ] **Step 5: Run the full gate**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

Expected: PASS. Card slugs change wherever the subject was not the first roster member, so the
render goldens may move.

- [ ] **Step 6: Regenerate the goldens if the gate reported a mismatch**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

Then re-run the gate and read the golden diff before committing: only `id=` and `href=`
fragments should have moved.

- [ ] **Step 7: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/players.py src/wowperf/domain/report/model.py tests/domain/report/test_build_players.py
```

Add any regenerated golden by name, then commit with a message in the house style — subject:
`Mint every player's fragment id in one place`.

---

## Task 2: A finding can name the player it is about

**Files:**
- Modify: `src/wowperf/domain/findings.py`
- Modify: `src/wowperf/domain/comparison/service.py`
- Modify: `src/wowperf/cli.py` (call site only)
- Test: `tests/domain/comparison/test_service.py`

**Interfaces:**
- Consumes: `slugs_by_actor` from Task 1.
- Produces:
  - `Finding.player_slug: str = ""`
  - `ComparisonSubject(player: Player, slug: str, parse: ParseSample | None, our_auras: PlayerAuras | None = None)` from `wowperf.domain.comparison.service`
  - `compare(ours: LoadedRun, speed: SpeedSample | None, subjects: Sequence[ComparisonSubject]) -> list[Finding]`

**The rule this task establishes.** The five comparison modules keep minting plain ids —
`compare.talents`, `compare.spells.missing.0`. `service.py` re-mints them as one player's own.
That is the only place a slug reaches an id, so there is exactly one thing to get right and
`tests/domain/comparison/test_spells.py` and `test_uptime.py` do not change.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/comparison/test_service.py`. The file already builds `OURS`, `THEIRS`, `a_pull`
and full samples; reuse whatever the existing `compare` tests use to build a `ParseSample`.

```python
def test_a_parse_finding_carries_the_player_it_is_about() -> None:
    findings = compare(
        ours=a_loaded_run(),
        speed=None,
        subjects=(ComparisonSubject(player=OURS, slug="emberkin-0", parse=a_parse_sample()),),
    )
    talents = next(f for f in findings if f.id.startswith("compare.talents"))
    assert talents.id == "compare.talents.emberkin-0"
    assert talents.player_slug == "emberkin-0"


def test_a_speed_finding_names_no_player() -> None:
    findings = compare(
        ours=a_loaded_run(),
        speed=None,
        subjects=(ComparisonSubject(player=OURS, slug="emberkin-0", parse=a_parse_sample()),),
    )
    speed = next(f for f in findings if f.id == "compare.speed.unavailable")
    assert speed.player_slug == ""


def test_two_players_produce_no_duplicate_finding_id() -> None:
    # The assertion that did not exist before this work. Colliding ids overwrite
    # entries in the report's title lookup and emit duplicate HTML element ids,
    # neither of which any existing test can see.
    findings = compare(
        ours=a_loaded_run(),
        speed=None,
        subjects=(
            ComparisonSubject(player=OURS, slug="emberkin-0", parse=a_parse_sample()),
            ComparisonSubject(player=SECOND, slug="stonewake-1", parse=a_parse_sample()),
        ),
    )
    ids = [finding.id for finding in findings]
    assert len(ids) == len(set(ids))


def test_a_player_with_no_parse_sample_says_so_in_their_own_name() -> None:
    findings = compare(
        ours=a_loaded_run(),
        speed=None,
        subjects=(ComparisonSubject(player=OURS, slug="emberkin-0", parse=None),),
    )
    unavailable = next(
        f for f in findings if f.id == "compare.parse.unavailable.emberkin-0"
    )
    assert OURS.name in unavailable.title
```

`SECOND` is a new module-level `Player` beside `OURS`, using a sanctioned name:

```python
SECOND = Player(
    actor_id=694,
    name="Stonewake",
    class_name="DeathKnight",
    spec="Blood",
    item_level=320,
    talent_import_string="C4DAAAAB",
)
```

Every existing test in the file that calls `compare(...)` must move to the new signature: the
`our_player=` and `our_auras=` arguments fold into a `ComparisonSubject`, and `parse=` becomes
that subject's `parse`. Do not delete any of them.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_service.py -q
```

Expected: `ImportError: cannot import name 'ComparisonSubject'`.

- [ ] **Step 3: Add the field to `Finding`**

In `src/wowperf/domain/findings.py`, below `quantifier`:

```python
    # The fragment id of the player this finding is about, from `slugs_by_actor`.
    # Empty on any finding that is a statement about the run rather than about
    # one player: a route, a tempo or a confound belongs to nobody.
    player_slug: str = ""
```

- [ ] **Step 4: Split `compare()`**

Replace `compare` in `src/wowperf/domain/comparison/service.py` with the following, keeping
`find_player` and `_unavailable` as they are. Add `from collections.abc import Sequence` and
`from wowperf.domain.base import Frozen` to the imports.

```python
class ComparisonSubject(Frozen):
    """One player to compare, with everything that comparison needs.

    `slug` comes from `slugs_by_actor` and is what makes this player's
    findings addressable: the report's card for the same player carries the
    identical string, so a pointer into a finding lands in the right sub-tab.
    """

    player: Player
    slug: str
    parse: ParseSample | None
    our_auras: PlayerAuras | None = None


def _for_player(findings: list[Finding], slug: str) -> list[Finding]:
    """Re-mint plain comparison ids as one player's own.

    The comparison modules know nothing about who else is in the run, so they
    mint `compare.talents` and this appends the player. Doing it in one place
    is what keeps five modules from each having to be told about the roster,
    and it is why the id is a suffix: every consumer of these ids matches by
    prefix, and a prefix survives anything appended to it.
    """
    return [
        finding.model_copy(update={"id": f"{finding.id}.{slug}", "player_slug": slug})
        for finding in findings
    ]


def _compare_player(ours: LoadedRun, subject: ComparisonSubject) -> list[Finding]:
    """Everything measured about one player against their own parse sample."""
    parse = subject.parse
    if parse is None or not parse.members:
        return [
            _unavailable(
                "compare.parse.unavailable",
                f"No ranked parse was available for {subject.player.name} "
                f"({subject.player.class_name} {subject.player.spec})",
                "The score leaderboard returned nothing for this specialisation within one "
                "keystone level of this run, so spells, talents and uptime are not compared.",
            )
        ]
    top = parse.top
    assert top is not None  # parse.members is non-empty here, so a top member exists
    return [
        *compare_spells_sample(ours, subject.player, parse),
        *compare_talents(
            subject.player, find_player(top.run, top.row.character_name), top.row
        ),
        *compare_uptime_sample(ours.run, subject.our_auras, subject.player, parse),
    ]


def compare(
    ours: LoadedRun,
    speed: SpeedSample | None,
    subjects: Sequence[ComparisonSubject],
) -> list[Finding]:
    """Every comparison, one ranked list.

    The speed axis is a statement about the run and is compared once whoever
    is being looked at. The parse axis is a statement about a player and is
    compared once per subject, each against their own specialisation's sample.

    An empty sample and no sample at all mean the same thing to a reader: the
    leaderboard offered nothing to compare against.
    """
    findings: list[Finding] = []

    if speed is None or not speed.members:
        findings.append(
            _unavailable(
                "compare.speed.unavailable",
                "No faster run was available to compare the route against",
                "The speed leaderboard returned nothing for this dungeon within one keystone "
                "level of this run, so route, downtime, deaths and interrupts are not compared.",
            )
        )
    else:
        findings += compare_route_sample(ours.run, speed, forces_by_pull(ours.enemy_deaths))
        findings += compare_tempo_sample(ours, speed)
        findings += declare_confounds_sample(ours, speed)

    for subject in subjects:
        findings += _for_player(_compare_player(ours, subject), subject.slug)

    return rank_findings(findings)
```

- [ ] **Step 5: Adapt the one call site**

In `src/wowperf/cli.py`, replace the `compare(...)` call with a single-subject one. Import
`ComparisonSubject` from `wowperf.domain.comparison.service` and `slugs_by_actor` from
`wowperf.domain.report.players`:

```python
            findings += compare(
                ours=loaded,
                speed=speed_sample,
                subjects=(
                    ComparisonSubject(
                        player=subject,
                        slug=slugs_by_actor(loaded.run)[subject.actor_id],
                        parse=parse_sample,
                        our_auras=our_auras,
                    ),
                ),
            )
```

Behaviour is unchanged end to end except that parse-family ids now carry the subject's slug.

- [ ] **Step 6: Run the full gate, then regenerate goldens**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

Expect failures in `tests/domain/report/` and `tests/adapters/render/` wherever a test names
`compare.talents` or `compare.parse.unavailable` literally. **Fix each by adding the slug the
test's own fixture implies — never by deleting the assertion.** Then:

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

and re-run the gate.

- [ ] **Step 7: Commit**

Stage `src/wowperf/domain/findings.py`, `src/wowperf/domain/comparison/service.py`,
`src/wowperf/cli.py`, the touched tests and any regenerated golden, by name. Subject:
`Give every parse comparison finding the player it is about`.

---

## Task 3: Each card carries its own comparison section

**Files:**
- Modify: `src/wowperf/domain/report/frame.py`
- Modify: `src/wowperf/domain/report/players.py`
- Modify: `src/wowperf/domain/report/build.py`
- Test: `tests/domain/report/test_build_players.py`, `tests/domain/report/test_build_frame.py`

**Interfaces:**
- Consumes: `Finding.player_slug` and the suffixed ids from Task 2; `slugs_by_actor` from Task 1.
- Produces:
  - `parse_unavailable_id(slug: str) -> str` and `NOT_REQUESTED` from `wowperf.domain.report.frame`
  - `build_players(loaded, findings, compared_slugs, subject, titles_by_id, defensives, throughput)`
    — the `parse: ParseSample | None` parameter is **replaced** by
    `compared_slugs: frozenset[str] | None`
  - `build_report(..., compared_slugs: frozenset[str] | None = None, ...)` replacing its
    `parse: ParseSample | None` parameter

**The three states.** A card's comparison section is now one of: present; withheld because the
comparison refused, quoting that player's own `compare.parse.unavailable.<slug>` detail; or
withheld because nobody asked. `compared_slugs is None` means no comparison ran at all
(`--no-compare`) and every card gets the existing `NO_COMPARISON_RAN` reason — "you did not ask
for this player" would be a lie when the reader asked for nothing.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/report/test_build_players.py`:

```python
def test_a_player_nobody_asked_for_says_so_rather_than_implying_an_empty_leaderboard() -> None:
    first = a_player(actor_id=1, name="Emberkin")
    second = a_player(actor_id=2, name="Stonewake")
    loaded = a_loaded(players=(first, second))
    cards = build_players(
        loaded, (), frozenset({"emberkin-0"}), first, {}, Defensives(), ThroughputCooldowns()
    )
    theirs = next(card for card in cards if card.name == "Stonewake")
    assert theirs.spell_and_talent.state is SectionState.WITHHELD
    assert theirs.spell_and_talent.reason == NOT_REQUESTED


def test_no_comparison_at_all_reads_differently_from_a_player_nobody_asked_for() -> None:
    loaded = a_loaded(players=(a_player(actor_id=1, name="Emberkin"),))
    cards = build_players(
        loaded, (), None, a_player(actor_id=1, name="Emberkin"), {},
        Defensives(), ThroughputCooldowns(),
    )
    assert cards[0].spell_and_talent.reason != NOT_REQUESTED


def test_each_player_gets_only_their_own_comparison_rows() -> None:
    first = a_player(actor_id=1, name="Emberkin")
    second = a_player(actor_id=2, name="Stonewake")
    loaded = a_loaded(players=(first, second))
    mine = Finding(
        id="compare.talents.emberkin-0", title="mine", detail="d",
        confidence=Confidence.MEASURED, player_slug="emberkin-0",
    )
    theirs = Finding(
        id="compare.talents.stonewake-1", title="theirs", detail="d",
        confidence=Confidence.MEASURED, player_slug="stonewake-1",
    )
    cards = build_players(
        loaded, (mine, theirs), frozenset({"emberkin-0", "stonewake-1"}), first,
        titles((mine, theirs)), Defensives(), ThroughputCooldowns(),
    )
    by_name = {card.name: ids(card.spell_and_talent_rows) for card in cards}
    assert by_name["Emberkin"] == ["compare.talents.emberkin-0"]
    assert by_name["Stonewake"] == ["compare.talents.stonewake-1"]


def test_one_player_is_withheld_while_another_is_present() -> None:
    first = a_player(actor_id=1, name="Emberkin")
    second = a_player(actor_id=2, name="Stonewake")
    loaded = a_loaded(players=(first, second))
    mine = Finding(
        id="compare.talents.emberkin-0", title="mine", detail="d",
        confidence=Confidence.MEASURED, player_slug="emberkin-0",
    )
    refused = Finding(
        id="compare.parse.unavailable.stonewake-1", title="none",
        detail="The score leaderboard returned nothing.",
        confidence=Confidence.MEASURED, player_slug="stonewake-1",
    )
    cards = build_players(
        loaded, (mine, refused), frozenset({"emberkin-0", "stonewake-1"}), first,
        titles((mine, refused)), Defensives(), ThroughputCooldowns(),
    )
    by_name = {card.name: card.spell_and_talent for card in cards}
    assert by_name["Emberkin"].state is SectionState.PRESENT
    assert by_name["Stonewake"].state is SectionState.WITHHELD
    assert by_name["Stonewake"].reason == "The score leaderboard returned nothing."
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_players.py -q
```

Expected: `ImportError: cannot import name 'NOT_REQUESTED'`.

- [ ] **Step 3: Add the frame helpers**

In `src/wowperf/domain/report/frame.py`, below `NO_COMPARISON_RAN`:

```python
# Said when the comparison ran but this player was not among the ones asked for.
# Distinct from NO_COMPARISON_RAN, which says nothing was compared at all, and
# from a withheld section, which says the leaderboard had nothing to offer.
NOT_REQUESTED = (
    "No parse comparison was requested for this player. Name them with --player, "
    "or pass --all-players, to compare them against top parses of their specialisation."
)


def parse_unavailable_id(slug: str) -> str:
    """This player's own `compare.parse.unavailable`."""
    return f"{PARSE_UNAVAILABLE_ID}.{slug}"
```

- [ ] **Step 4: Build one Section per card**

In `src/wowperf/domain/report/players.py`, replace the `parse` parameter with
`compared_slugs: frozenset[str] | None`, delete the single
`comparison_section = section_for(...)` line, and add this helper above `build_players`:

```python
def _comparison_section(
    findings: Sequence[Finding], slug: str, compared_slugs: frozenset[str] | None
) -> Section:
    """One player's comparison section, in whichever of three states it is in.

    A player nobody asked for is not the same as a player the leaderboard had
    nothing for, and neither is the same as a run that fetched no reference at
    all. Saying so is the whole job: a reader who cannot tell "not asked" from
    "not available" will read the second as the first and stop asking.
    """
    if compared_slugs is None:
        return Section(state=SectionState.WITHHELD, reason=NO_COMPARISON_RAN)
    if slug not in compared_slugs:
        return Section(state=SectionState.WITHHELD, reason=NOT_REQUESTED)
    return section_for(
        findings,
        parse_unavailable_id(slug),
        present=_finding_by_id(findings, parse_unavailable_id(slug)) is None,
    )
```

`section_for`'s third parameter is positional today; pass it positionally if it is not keyword-
able. Import `NOT_REQUESTED`, `NO_COMPARISON_RAN`, `parse_unavailable_id` and `_finding_by_id`
from `wowperf.domain.report.frame`, and `Section`, `SectionState` from
`wowperf.domain.report.model`. If `_finding_by_id` being private across modules reads wrong,
promote it to `finding_by_id` in `frame.py` and update its two callers there.

Inside the card loop, replace the two comparison fields:

```python
                spell_and_talent=_comparison_section(findings, slugs[summary.actor_id], compared_slugs),
                spell_and_talent_rows=collapse_repeated_details(
                    [
                        ledger_row(finding, titles_by_id)
                        for finding in comparison
                        if finding.player_slug == slugs[summary.actor_id]
                    ]
                ),
```

`is_subject` is now unused inside the loop; remove it if nothing else reads it. Update the
`build_players` docstring: the subject still decides card order, but no longer decides who
carries comparison rows.

- [ ] **Step 5: Thread it through `build_report`**

In `src/wowperf/domain/report/build.py`, replace the `parse: ParseSample | None` parameter with
`compared_slugs: frozenset[str] | None = None`, delete the
`comparison_section = section_for(findings, PARSE_UNAVAILABLE_ID, sampled(parse))` block, move
the `players = build_players(...)` call above the `withheld` list, and build the withheld lines
from the cards:

```python
    players = build_players(
        loaded, findings, compared_slugs, subject, titles_by_id, defensives, throughput
    )

    for card in players:
        if card.spell_and_talent.state is SectionState.WITHHELD and (
            compared_slugs is None or card.slug in compared_slugs
        ):
            withheld.append(
                f"Spell and talent comparison for {card.name}: {card.spell_and_talent.reason}"
            )
```

A player nobody asked for is deliberately absent from that list: an unrequested comparison was
not withheld, it was not requested, and four such lines on every default run would bury the ones
that mean something. `titles_by_id` must be computed before this block; move its line up if
needed. Drop the now-unused `sampled` and `PARSE_UNAVAILABLE_ID` imports if nothing else uses
them.

- [ ] **Step 6: Update every `build_report` and `build_players` caller**

`src/wowperf/cli.py` passes `compared_slugs=frozenset({slugs_by_actor(loaded.run)[subject.actor_id]})`
when comparing and `None` under `--no-compare`. Fix every test caller the gate names.

- [ ] **Step 7: Run the full gate and regenerate goldens**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

Then `--golden-update`, then re-run. Read the golden diff: four cards should have gained a
withheld comparison section with the `NOT_REQUESTED` reason.

- [ ] **Step 8: Commit**

Subject: `Give each player card its own comparison section`.

---

## Task 4: A parse sample per player

**Files:**
- Modify: `src/wowperf/domain/report/model.py`
- Modify: `src/wowperf/cli.py`
- Test: `tests/test_cli.py` (or wherever `_samples` is currently exercised — find it with
  `grep -rn "_samples\|_fetch_parse_auras" tests/`)

**Interfaces:**
- Consumes: `ComparisonSubject` from Task 2.
- Produces:
  - `ReferenceRecord.player_slug: str = ""`
  - `_samples(rankings, runs, run, subjects: Sequence[tuple[Player, str]]) -> tuple[SpeedSample, dict[int, ParseSample], tuple[ReferenceRecord, ...]]`
    — the parse result is keyed by actor id
  - `_fetch_parse_auras(sample, ours, references, our_run, player) -> tuple[ParseSample, PlayerAuras | None]`
    — unchanged signature, called once per player

**What must not drift.** `our_names` is computed once from our own roster and applied to every
sample: a reference that is quietly one of our own characters must be dropped from a teammate's
sample as firmly as from the subject's. `BracketMismatch` from any leaderboard query still
propagates and stops the command — it means the bracket convention this tool relies on has
changed, which is not a per-player fact and must not be swallowed four times over.

- [ ] **Step 1: Write the failing tests**

Whatever fake repository the existing CLI tests use, extend it to return different leaderboard
rows per specialisation, then assert:

```python
def test_each_player_gets_their_own_specialisations_sample() -> None:
    speed, parses, _ = _samples(
        rankings, runs, run, subjects=((mage, "emberkin-0"), (tank, "stonewake-1")),
    )
    assert set(parses) == {mage.actor_id, tank.actor_id}
    assert parses[mage.actor_id] is not parses[tank.actor_id]


def test_a_reference_naming_one_of_our_own_is_dropped_from_every_players_sample() -> None:
    _, parses, records = _samples(
        rankings_returning_our_own_report, runs, run,
        subjects=((mage, "emberkin-0"), (tank, "stonewake-1")),
    )
    for sample in parses.values():
        assert all(
            member.row.report_code != OUR_OWN_OTHER_REPORT for member in sample.members
        )
    assert any("one of our own characters" in record.reason for record in records)


def test_a_parse_candidate_records_whose_comparison_weighed_it() -> None:
    _, _, records = _samples(
        rankings, runs, run, subjects=((mage, "emberkin-0"), (tank, "stonewake-1")),
    )
    parse_records = [record for record in records if record.axis == "parse"]
    assert {record.player_slug for record in parse_records} == {"emberkin-0", "stonewake-1"}
    assert all(record.player_slug == "" for record in records if record.axis == "speed")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_cli.py -q
```

Expected: a `TypeError` about the `subject` argument.

- [ ] **Step 3: Add the field to `ReferenceRecord`**

In `src/wowperf/domain/report/model.py`, inside `ReferenceRecord`:

```python
    # Whose comparison weighed this candidate, from `slugs_by_actor`. Empty on a
    # speed candidate: the route is compared once for the run, not per player.
    player_slug: str = ""
```

- [ ] **Step 4: Take the slug through `_record`**

In `src/wowperf/cli.py`, give `_record` a keyword-only `player_slug: str = ""` and pass it
through to the `ReferenceRecord` it builds.

- [ ] **Step 5: Loop the parse half of `_samples`**

Change the signature to take `subjects: Sequence[tuple[Player, str]]` and return
`dict[int, ParseSample]` for the parse axis. Lift the existing parse block into a loop over
`subjects`, passing `player_slug=slug` into every `_record(...)` call it makes, and collecting
each player's members into their own list. The speed block and `our_names` stay exactly where
they are, computed once. Update the docstring to say the speed axis is drawn once and the parse
axis once per subject.

- [ ] **Step 6: Call `_fetch_parse_auras` per player**

Its signature does not change. In the analyze body, loop:

```python
            subjects: list[ComparisonSubject] = []
            for player_to_compare, slug in requested:
                sample, our_auras = _fetch_parse_auras(
                    parse_samples[player_to_compare.actor_id],
                    repository,
                    references,
                    loaded.run,
                    player_to_compare,
                )
                subjects.append(
                    ComparisonSubject(
                        player=player_to_compare,
                        slug=slug,
                        parse=sample,
                        our_auras=our_auras,
                    )
                )
            findings += compare(ours=loaded, speed=speed_sample, subjects=tuple(subjects))
```

`requested` is a single-element sequence until Task 5 makes it plural.

- [ ] **Step 7: Run the full gate, regenerate goldens, commit**

Subject: `Draw a parse sample for each player being compared`.

---

## Task 5: The command line

**Files:**
- Modify: `src/wowperf/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: `--player` repeatable, `--all-players`, and a
  `comparison.players` list in the findings JSON.

**The contract, from the spec's section 4.** The default does not change: with neither flag,
`analyze` compares the report owner alone. The subject is the first `--player` given, or the
report owner when none is; the subject's card still sorts first and still fills the JSON's scalar
`"player"`. The flags combine rather than conflict. `--no-compare` wins over both, and makes them
inert rather than an error.

- [ ] **Step 1: Write the failing tests**

```python
def test_by_default_only_the_report_owner_is_compared() -> None:
    result = run_analyze([REPORT])
    assert payload(result)["comparison"]["players"] == ["emberkin-0"]


def test_naming_two_players_compares_both_and_makes_the_first_the_subject() -> None:
    result = run_analyze([REPORT, "--player", "Stonewake", "--player", "Emberkin"])
    assert payload(result)["player"] == "Stonewake"
    assert set(payload(result)["comparison"]["players"]) == {"stonewake-1", "emberkin-0"}


def test_all_players_compares_the_whole_roster() -> None:
    result = run_analyze([REPORT, "--all-players"])
    assert len(payload(result)["comparison"]["players"]) == len(ROSTER)


def test_all_players_with_a_named_player_keeps_that_player_as_the_subject() -> None:
    result = run_analyze([REPORT, "--all-players", "--player", "Stonewake"])
    assert payload(result)["player"] == "Stonewake"
    assert len(payload(result)["comparison"]["players"]) == len(ROSTER)


def test_no_compare_makes_both_flags_inert_rather_than_an_error() -> None:
    result = run_analyze([REPORT, "--all-players", "--no-compare"])
    assert result.exit_code == 0
    assert payload(result)["comparison"]["players"] == []


def test_an_unknown_name_says_which_one_missed() -> None:
    result = run_analyze([REPORT, "--player", "Emberkin", "--player", "Nobodyhere"])
    assert result.exit_code == 1
    assert "Nobodyhere" in result.output
    assert "Emberkin" not in result.output.split("is not in this run's roster")[0]
```

Match the existing CLI tests' invocation helper rather than inventing `run_analyze` and
`payload` — find it at the top of `tests/test_cli.py`.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_cli.py -q
```

Expected: failures on the unknown `--all-players` option and the missing `players` key.

- [ ] **Step 3: Change the options**

```python
    player: list[str] = typer.Option(
        [],
        "--player",
        help="Compare this player against top parses of their specialisation. "
        "Repeatable; the first one given is the report's subject. "
        "Defaults to the report owner.",
    ),
    all_players: bool = typer.Option(
        False,
        "--all-players",
        help="Compare every player in the run, not only the subject",
    ),
```

- [ ] **Step 4: Resolve the subject and the requested set**

Add beside `_resolve_player`, keeping that function for the subject:

```python
def _resolve_requested(
    run: Run, requested: Sequence[str], everyone: bool
) -> tuple[Player, tuple[Player, ...]]:
    """The subject, and every player to compare.

    The subject is the first name given, or the report owner when none is: it
    decides whose card opens the Players tab and whose name the findings file
    carries, and a report with no subject at all would leave both undecided.
    `--all-players` widens who is compared without touching who the subject is,
    so the two flags combine rather than conflict.
    """
    subject = _resolve_player(run, requested[0] if requested else None)
    named = [subject] + [_resolve_player(run, name) for name in requested[1:]]
    if everyone:
        by_actor = {player.actor_id: player for player in named}
        for player in run.players:
            by_actor.setdefault(player.actor_id, player)
        return subject, tuple(by_actor.values())
    return subject, tuple(named)
```

`_resolve_player` already raises a `ValueError` naming the missing name and listing the roster,
which satisfies the "says which one missed" test without change.

- [ ] **Step 5: Wire it into the analyze body**

Replace `subject = _resolve_player(loaded.run, player)` with:

```python
        subject, to_compare = _resolve_requested(loaded.run, player, all_players)
        slugs = slugs_by_actor(loaded.run)
        requested = tuple((one, slugs[one.actor_id]) for one in to_compare)
```

Pass `requested` into `_samples` and the aura loop from Task 4. Under `--no-compare`, leave
`requested` unused and pass `compared_slugs=None` to `build_report`; otherwise pass
`frozenset(slug for _, slug in requested)`.

- [ ] **Step 6: Add the JSON key**

In the payload's `"comparison"` block, beside `"compared"`:

```python
            "players": [slug for _, slug in requested] if not no_compare else [],
```

`"player": subject.name` stays exactly as it is. A reader of the JSON can now tell "nobody
asked" from "the leaderboard was empty" without inspecting findings.

- [ ] **Step 7: Update `--sample-size`-style docs**

Update the `analyze` row of the commands table in `CLAUDE.md` to show `[--player NAME]...` and
`[--all-players]`.

- [ ] **Step 8: Run the full gate, regenerate goldens, commit**

Subject: `Let a reader ask for a teammate's parse comparison, or the group's`.

---

## Task 6: The invariants that were missing

**Files:**
- Test: `tests/adapters/render/test_html_invariants.py`
- Test: `tests/domain/report/test_build_players.py`

**Interfaces:**
- Consumes: everything from Tasks 1-5. Adds no production code.

**Why this is its own task.** The spec's section 11.1 found that the three copies of
`test_no_finding_reaches_the_page_twice` assert on **titles**, and the titles already carry the
player's name — so none of them can see a colliding id. Nothing in the suite asserts that finding
ids are unique. These tests are the reason the whole change is safe, and a reviewer should be
able to accept or reject them on their own.

- [ ] **Step 1: Write the render-level uniqueness test**

In `tests/adapters/render/test_html_invariants.py`, beside the existing title-based test:

```python
def test_no_element_id_appears_twice() -> None:
    # The companion to test_no_finding_reaches_the_page_twice, which compares
    # titles and so cannot see two findings that share an id. A duplicate
    # element id is invalid HTML and sends the page's own pointer to whichever
    # of the two the browser happens to pick.
    html = minimal_html()
    element_ids = re.findall(r'\sid="([^"]+)"', html)
    duplicates = {value for value in element_ids if element_ids.count(value) > 1}
    assert duplicates == set()
```

- [ ] **Step 2: Write the slug-agreement test**

In `tests/domain/report/test_build_players.py`:

```python
def test_a_findings_slug_addresses_the_card_that_carries_it() -> None:
    # `slugs_by_actor` exists so the comparison and the card cannot compute a
    # slug independently and drift. This is the test that fails if they ever do.
    first = a_player(actor_id=1, name="Bríala")
    second = a_player(actor_id=2, name="Briala")
    loaded = a_loaded(players=(first, second))
    slugs = slugs_by_actor(loaded.run)
    hers = Finding(
        id=f"compare.talents.{slugs[2]}", title="theirs", detail="d",
        confidence=Confidence.MEASURED, player_slug=slugs[2],
    )
    cards = build_players(
        loaded, (hers,), frozenset(slugs.values()), first, titles((hers,)),
        Defensives(), ThroughputCooldowns(),
    )
    carrying = [card for card in cards if card.spell_and_talent_rows]
    assert len(carrying) == 1
    assert carrying[0].slug == slugs[2]
    assert carrying[0].name != "Bríala"
```

- [ ] **Step 3: Run both and verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py::test_no_element_id_appears_twice tests/domain/report/test_build_players.py -q
```

Expected: PASS. **If `test_no_element_id_appears_twice` fails, do not weaken it** — a duplicate
id on the page is the defect this whole change exists to prevent. Find which ids collide and fix
the production code.

- [ ] **Step 4: Extend the render fixture to two compared players**

`minimal_findings()` currently carries one player's comparison findings. Add a second player's —
same families, a different slug — so the uniqueness test is exercised against the case it exists
for rather than against a fixture that could never collide. Keep the names inside the sanctioned
set.

- [ ] **Step 5: Run the full gate, regenerate goldens, commit**

Subject: `Assert that no two findings share an id or an element`.

---

## Task 7: The measured reading

**Files:**
- Test: `tests/e2e/test_report_e2e.py`
- Modify: `.claude/skills/wcl-api/SKILL.md`

**Interfaces:**
- Consumes: the finished feature.

**This task spends API quota — roughly 250 points of 3600 — and needs credentials.** Do not run
it without RwlRwlRwlRwl's go-ahead. The spec's section 7.1 requires the reading: the 165-point
figure it carries is *derived*, and stops being the best available number the moment a real
`--all-players` run exists.

- [ ] **Step 1: Write the e2e test**

In `tests/e2e/test_report_e2e.py`, following the file's existing marker and fixtures:

```python
@pytest.mark.e2e
def test_all_players_compares_everyone_and_collides_no_ids() -> None:
    findings, html = analyze_e2e(REPORT_CODE, FIGHT_ID, all_players=True)
    ids = [finding["id"] for finding in findings["findings"]]
    assert len(ids) == len(set(ids))
    element_ids = re.findall(r'\sid="([^"]+)"', html)
    assert len(element_ids) == len(set(element_ids))
    for slug in findings["comparison"]["players"]:
        assert any(finding.get("player_slug") == slug for finding in findings["findings"])
```

Match the file's own helper for invoking the command; do not add a mock — e2e tests here use
real data and the real API.

- [ ] **Step 2: Run it once, with a cold cache, and read the cost line**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -m e2e -q
```

The command prints where the run's points went, dearest operation first. Record the total, and
count how many parse references were served from another player's sample — a `ReferenceRecord`
with `from_cache: True` whose report code also appears under a different `player_slug`.

- [ ] **Step 3: Record both numbers in the skill file**

Add a dated paragraph to `.claude/skills/wcl-api/SKILL.md` under the rate-limit section, in the
same shape as the existing measurements: the date, the report and fight, the total points, the
number of parse candidates and how many were cross-sample cache hits. **State only what was
measured** — if the cache-hit count could not be determined from one run, say so rather than
estimating.

- [ ] **Step 4: Correct the design's derived figure**

Update section 7.1 of `docs/plans/2026-09-10-per-player-parse-comparison-design.md` to carry the
measured total beside the derived 165, and strike the open question in section 13 that the
reading answers. Leave section 13's second question — whether five comparisons is more than a
reader wants — open; it needs a real report looked at, not a number.

- [ ] **Step 5: Commit**

Subject: `Record what comparing every player actually costs`.

---

## Self-Review

**Spec coverage.** Section 1 → Tasks 2-5. Section 2 → nothing to build. Section 3 → nothing, by
design. Section 4 (the command line) → Task 5. Section 5.1 (`slugs_by_actor`) → Task 1. Section
5.2 (the suffix and the field) → Task 2. Section 6 (the split) → Task 2. Section 7.1 (cost) →
Task 7. Section 7.2 (partial failure) → Task 4's `our_names` and `BracketMismatch` notes.
Section 7.3 (not requested) → Task 3. Section 8 (the page) → Task 3, plus Task 4 for
`ReferenceRecord.player_slug`. Section 9 (terms of service) → no code; the constraint is in
Global Constraints and in Task 4. Section 10 → Global Constraints. Section 11 → Tasks 2 and 6.
Section 12 (testing) → the three named tests are Task 2 step 1, Task 6 step 2 and Task 6 step 2's
collision fixture. No gaps.

**Placeholder scan.** Two steps deliberately point at the tree instead of quoting it: Task 4's
test file location and Task 5's invocation helper, both because the existing helper's name must
be matched rather than invented, and each says how to find it. Every other step carries the code.

**Type consistency.** `slugs_by_actor(run) -> dict[int, str]` is minted in Task 1 and consumed by
name in Tasks 2, 3, 4, 5 and 6. `ComparisonSubject` fields (`player`, `slug`, `parse`,
`our_auras`) are identical in Tasks 2 and 4. `compared_slugs: frozenset[str] | None` has the same
type in Tasks 3, 4 and 5. `Finding.player_slug` and `ReferenceRecord.player_slug` are both
`str = ""`.

**One ordering risk worth naming.** Task 2 changes finding ids and Task 3 changes how the report
reads them. Between them the tree is green but the report shows every card's comparison as
withheld, because `build_report` still looks for the unsuffixed `compare.parse.unavailable`. That
is a real intermediate state and Task 3 fixes it; an executor who stops after Task 2 must not
ship.
