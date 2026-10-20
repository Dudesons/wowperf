# The `character` command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** `wowperf character <character-url>` reads one recent high key per dungeon for one
character, analyses each with the `analyze` pipeline, and writes a page stating what repeats across
the runs.

**Architecture:** `analyze`'s body is lifted, unchanged, into `analyse_run` / `write_findings` /
`write_page` in `cli.py`, guarded by a golden pin. A new adapter lists the character's ranked runs;
pure domain modules under `src/wowperf/domain/character/` choose the runs and count what repeats
(repeated judgements, unanimous directions, a group ledger); a view model and one template draw the
page.

**Tech Stack:** Python 3.12, uv, typer, httpx, pydantic (`Frozen`), Jinja2, pytest, ruff, mypy
(strict, over `src` and `tests`).

**Spec:** `docs/plans/2026-10-14-character-command-design.md` (read it first, including its
dated amendments).

## Global Constraints

- `uv` is not on `PATH` in Bash: run every command as `~/.local/bin/uv run …` from the repo root.
- Every new file starts with two `# ABOUTME: ` lines (`{# ABOUTME: … #}` in a template).
- The domain performs no I/O: nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`,
  `pathlib` I/O or the adapters.
- Never put a real character name in `tests/`. Use `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`.
  The live character is given on the command line in Task 16 and never committed.
- Every finding carries a confidence badge. Nothing is summed across runs.
- Never invent an API field. Task 6 verifies every new field live before code uses it.
- Commit messages: plain ASCII, imperative subject, no `feat:` prefix, body says why, ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never `--no-verify`.
- Lines at most 100 characters (ruff). After every task: `~/.local/bin/uv run ruff check .`,
  `~/.local/bin/uv run mypy`, `~/.local/bin/uv run pytest` all clean.
- Chosen numbers, verbatim from the spec: `REPEAT_MIN_RUNS = 3` (and at least half the loaded
  runs), `MIN_DIRECTION_RUNS = 6`, `DIRECTION_RATE_FLOOR = 0.10`, `DIRECTION_SHARE_FLOOR = 0.05`,
  `LEVELS_BELOW_TOP = 1`.

---

### Task 1: Pin what `analyze` writes

**Files:**
- Create: `tests/test_cli_analyze_pin.py`
- Create (generated): `tests/golden/analyze/abc123-36.findings.json`,
  `tests/golden/analyze/abc123-36.html`

**Interfaces:**
- Consumes: `run_analyze` and the mock transport in `tests/test_cli.py`; the `--golden-update`
  flag from `tests/conftest.py`.
- Produces: a byte-for-byte guard Task 2 must keep green.

- [ ] **Step 1: Write the pin**

```python
# ABOUTME: Pins what `analyze` writes for one compared mock run, byte for byte.
# ABOUTME: Guards the lifting of its pipeline into shared functions: nothing a reader gets may move.

from datetime import datetime, tzinfo
from pathlib import Path
from typing import Self

import pytest

from tests.test_cli import run_analyze

GOLDEN = Path(__file__).parent / "golden" / "analyze"


class _FrozenDatetime(datetime):
    """`datetime` whose clock reads one fixed minute, so the page's fetch line is stable."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        return cls(2026, 10, 14, 9, 30)


@pytest.mark.parametrize("name", ["abc123-36.findings.json", "abc123-36.html"])
def test_analyze_writes_exactly_what_it_wrote_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config, name: str
) -> None:
    monkeypatch.setattr("wowperf.cli.datetime", _FrozenDatetime)

    result = run_analyze(tmp_path, "--player", "Emberkin")

    assert result.exit_code == 0, result.output
    written = (tmp_path / "out" / name).read_text(encoding="utf-8")
    golden = GOLDEN / name
    if pytestconfig.getoption("--golden-update"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(written, encoding="utf-8")
        pytest.skip("golden file rewritten")
    assert written == golden.read_text(encoding="utf-8")
```

- [ ] **Step 2: Generate the golden files from today's `analyze`**

Run: `~/.local/bin/uv run pytest tests/test_cli_analyze_pin.py --golden-update -v`
Expected: 2 skipped ("golden file rewritten"); both files now exist under `tests/golden/analyze/`.

- [ ] **Step 3: Run the pin for real**

Run: `~/.local/bin/uv run pytest tests/test_cli_analyze_pin.py -v`
Expected: 2 passed.

- [ ] **Step 4: Prove the pin bites**

Change `cls(2026, 10, 14, 9, 30)` to `cls(2026, 10, 14, 9, 31)` and run Step 3 again.
Expected: the `.html` case FAILS (its fetch line moved). Then also confirm the comparison path is in
the golden: `grep -c '"compare\.' tests/golden/analyze/abc123-36.findings.json` prints a number
above 0. Restore `9, 30` and re-run Step 3: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli_analyze_pin.py tests/golden/analyze
git commit -m "Pin what analyze writes before its pipeline moves" -m "The character command reuses analyze's pipeline, which means lifting it out of the command body. A byte-for-byte pin on a compared mock run is what proves the move changed nothing a reader gets." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Lift `analyze`'s pipeline into `analyse_run`, `write_findings` and `write_page`

**Files:**
- Modify: `src/wowperf/cli.py` (imports; new `RunAnalysis`, `_read_narrative`, `analyse_run`,
  `run_payload`, `write_findings`, `write_page` placed just above `@app.command() def analyze`;
  `analyze`'s body at lines 1486-1728 rewritten to call them)

**Interfaces:**
- Consumes: everything `analyze` already calls.
- Produces (later tasks rely on these exact names):
  - `class RunAnalysis(NamedTuple)` with fields `loaded: LoadedRun`, `findings: list[Finding]`,
    `subject: Player`, `subjects: list[ComparisonSubject]`, `speed_sample: SpeedSample | None`,
    `compared_slugs: frozenset[str] | None`, `reference_records: tuple[ReferenceRecord, ...]`,
    `tables: dict[str, PlayerMeasures]`, `defensives: Defensives`, `consumables: Consumables`,
    `externals: Externals`, `throughput: ThroughputCooldowns`, `roles: Roles`
  - `def _read_narrative(narrative: Path | None) -> str | None`
  - `def analyse_run(repository: WclRunRepository, cache_dir: Path, code: str, fight_id: int | None, *, players: Sequence[str] = (), all_players: bool = False, no_compare: bool = False, throughput_ceiling: bool = False) -> RunAnalysis`
  - `def run_payload(analysis: RunAnalysis) -> dict[str, Any]`
  - `def write_findings(analysis: RunAnalysis, out: Path) -> Path`
  - `def write_page(analysis: RunAnalysis, out: Path, narrative_text: str | None, fetched_at: str) -> Path`

This is a refactor: behaviour must not change, and Task 1's pin plus the existing `analyze` tests
are the failing-test guard. No new test is written.

- [ ] **Step 1: Run the guard before touching anything**

Run: `~/.local/bin/uv run pytest tests/test_cli_analyze_pin.py tests/test_cli.py -q`
Expected: all pass.

- [ ] **Step 2: Add the imports**

In `src/wowperf/cli.py` change `from typing import NamedTuple` to `from typing import Any, NamedTuple`
and add, in the sorted position among the `wowperf.domain` imports:

```python
from wowperf.domain.season import Consumables, Defensives, Externals, Roles, ThroughputCooldowns
```

- [ ] **Step 3: Add the lifted functions above `analyze`**

Insert immediately before `@app.command()\ndef analyze(`. Every comment is carried over from the
body it came from; do not drop any.

```python
class RunAnalysis(NamedTuple):
    """Everything one Mythic+ run's analysis produced, before anything is written.

    `analyze` writes it as one findings file and one page; `character` writes it
    the same way and reads it again across runs. The data files the page builder
    needs ride along, so the page is built from exactly what the analysers read.
    """

    loaded: LoadedRun
    findings: list[Finding]
    subject: Player
    subjects: list[ComparisonSubject]
    speed_sample: SpeedSample | None
    compared_slugs: frozenset[str] | None
    reference_records: tuple[ReferenceRecord, ...]
    tables: dict[str, PlayerMeasures]
    defensives: Defensives
    consumables: Consumables
    externals: Externals
    throughput: ThroughputCooldowns
    roles: Roles


def _read_narrative(narrative: Path | None) -> str | None:
    """The narrative's text, refused before anything is fetched if it states a number.

    Read before anything is fetched: a typo in the path must cost nothing, and
    must never quietly produce a report with no narrative.
    """
    if narrative is None:
        return None
    try:
        narrative_text = narrative.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        # UnicodeDecodeError's own message never names the file it came
        # from, so a bad-encoding narrative would otherwise print a
        # codec complaint with no way to tell which path caused it.
        raise ValueError(f"{narrative}: {error}") from error

    offending = lines_with_digits(narrative_text)
    if offending:
        raise ValueError(_narrative_digits_message(narrative, offending))
    return narrative_text


def analyse_run(
    repository: WclRunRepository,
    cache_dir: Path,
    code: str,
    fight_id: int | None,
    *,
    players: Sequence[str] = (),
    all_players: bool = False,
    no_compare: bool = False,
    throughput_ceiling: bool = False,
) -> RunAnalysis:
    """Analyse one Mythic+ run and compare it, exactly as `analyze` does, writing nothing.

    Raises what `analyze` reports: `ValueError`, `WclError`, `httpx.HTTPError`
    and `OSError`. The caller decides whether one failed run stops it.
    """
    loaded = repository.load(code, fight_id)
    # Fetched here, once, so the comparison below and the report builder
    # after it both see the same LoadedRun -- a --no-compare report still
    # gets its own roster's cover windows.
    loaded = load_run_with_auras(repository, code, loaded.run.fight_id, loaded)
    # Loaded once and shared: the analysers and the death cards must read
    # the same cooldowns, or the page and the findings disagree.
    defensives = load_defensives()
    consumables = load_consumables()
    consumable_buffs = load_consumable_buffs()
    aura_groups = load_aura_groups()
    throughput = load_throughput_cooldowns()
    roles = load_roles()
    externals = load_externals()
    slot_names = load_slot_names()
    # The comparison's combat-potion family reads this one category rather
    # than all of `consumables`: `for_survival()` excludes it (it shares no
    # cooldown with a health potion), but `categories` still carries it.
    combat_potion_ids = next(
        (category.ability_ids for category in consumables.categories
         if category.name == "combat potion"),
        (),
    )
    findings = analyse(
        loaded,
        load_season_data(),
        defensives,
        consumables,
        throughput,
        roles=roles,
        include_cooldown_ceiling=throughput_ceiling,
        answers=answers_for(loaded.run.players, throughput, externals, roles),
    )

    # The roster's own spelling, disambiguated where two members share a
    # name, computed once and read by everything that names a player: the
    # names `--player` accepts, the roster a refusal lists, and the name
    # stamped onto every comparison subject below. One mapping rather than
    # three calls, so a finding's title, a card heading, a provenance row
    # and the argument that asked for them cannot spell a player
    # differently.
    names = display_names(loaded.run.players)
    subject, to_compare = _resolve_requested(
        loaded.run.players, loaded.run.owner_name, players, all_players, names
    )
    speed_sample: SpeedSample | None = None
    # Everyone the comparison was asked for: the subject, then the order
    # the reader named the rest, then whoever `--all-players` swept up.
    # That is not the order the cards come in -- those are the subject
    # first and the roster's own order behind -- so nothing may read this
    # sequence as a card order. It is the one source for *who* was
    # compared: the slugs stamped onto the findings, the slugs the report
    # matches cards by, the JSON's own list, the per-player sample sizes
    # and the page's icons are all read off it, so none of them can drift
    # from another. Empty means the comparison did not run.
    subjects: list[ComparisonSubject] = []
    compared_slugs: frozenset[str] | None = None
    reference_records: tuple[ReferenceRecord, ...] = ()
    tables: dict[str, PlayerMeasures] = {}
    if not no_compare:
        rankings, references = build_reference_repositories(repository.client, cache_dir)
        # The only place this command mints a slug: the comparison stamps a
        # player's slug onto every finding it emits about them, and the report
        # matches their card by it. The name beside it is `names`' spelling,
        # so a provenance row naming a player names the same one their card
        # does -- and the same one `--player` would have to be given.
        slugs = slugs_by_actor(loaded.run.players)
        requested: tuple[RequestedPlayer, ...] = tuple(
            RequestedPlayer(
                player=one, slug=slugs[one.actor_id], name=names[one.actor_id]
            )
            for one in to_compare
        )
        # Every candidate `_samples` weighed comes back as `reference_records`,
        # carried onto both the report's provenance below and the comparison
        # block of the findings JSON.
        speed_sample, parse_samples, reference_records = _samples(
            rankings, references, loaded.run, requested
        )

        # One enemy-debuff stream covers the whole group, so every subject
        # reads the same one: memoised, it is requested once at most (a
        # failure is not cached on disk, so the memo is what stops a second
        # request), and only once some member's counterpart resolves.
        our_debuff_log = functools.cache(
            lambda: _debuff_log(repository, loaded.run.report_code, loaded.run.fight_id)
        )
        for player_to_compare, slug, name in requested:
            sample, our_auras = _fetch_parse_auras(
                parse_samples[player_to_compare.actor_id],
                repository,
                references,
                loaded.run,
                player_to_compare,
            )
            sample, our_debuffs = _fetch_parse_debuffs(
                sample, references, our_debuff_log, loaded.run, player_to_compare
            )
            subjects.append(
                ComparisonSubject(
                    player=player_to_compare,
                    slug=slug,
                    display_name=name,
                    parse=sample,
                    our_auras=our_auras,
                    our_debuffs=our_debuffs,
                    consumable_buffs=consumable_buffs,
                    aura_groups=aura_groups,
                    potion_ids=combat_potion_ids,
                    slot_names=slot_names,
                )
            )
        compared_slugs = frozenset(one.slug for one in subjects)

        findings += compare(ours=loaded, speed=speed_sample, subjects=subjects)
        tables = comparison_measures(ours=loaded, subjects=subjects)
        findings = rank_findings(findings)
    return RunAnalysis(
        loaded=loaded,
        findings=findings,
        subject=subject,
        subjects=subjects,
        speed_sample=speed_sample,
        compared_slugs=compared_slugs,
        reference_records=reference_records,
        tables=tables,
        defensives=defensives,
        consumables=consumables,
        externals=externals,
        throughput=throughput,
        roles=roles,
    )


def run_payload(analysis: RunAnalysis) -> dict[str, Any]:
    """The findings file's contents for one analysed run."""
    run = analysis.loaded.run
    speed_sample = analysis.speed_sample
    subjects = analysis.subjects
    return {
        "report_code": run.report_code,
        "fight_id": run.fight_id,
        "dungeon_name": run.dungeon_name,
        "keystone_level": run.keystone_level,
        "keystone_time_seconds": run.keystone_time_seconds,
        "in_time": run.keystone_bonus >= 1,
        "player": analysis.subject.name,
        "comparison": {
            "compared": bool(
                (speed_sample and speed_sample.members)
                or any(_parse_sample_size(one) for one in subjects)
            ),
            # Who was compared, subject first. An empty list says nobody was
            # asked for, which a reader can now tell from a leaderboard that
            # had nothing to offer without inspecting the findings.
            "players": [one.slug for one in subjects],
            "sample_size": {
                "speed": len(speed_sample.members) if speed_sample else 0,
                # The parse axis is drawn once per player, so its size is a
                # figure per player: one number could only ever describe one
                # of them, and would under-report the rest.
                "parse": {one.slug: _parse_sample_size(one) for one in subjects},
            },
            "references": [
                {
                    "axis": record.axis,
                    "report_code": record.report_code,
                    "fight_id": record.fight_id,
                    "keystone_level": record.keystone_level,
                    "url": record.url,
                    "loaded": record.loaded,
                    "reason": record.reason,
                    "from_cache": record.from_cache,
                    "player_slug": record.player_slug,
                    "player_name": record.player_name,
                }
                for record in analysis.reference_records
            ],
        },
        "findings_are_ranked_not_additive": FINDINGS_ARE_RANKED_NOT_ADDITIVE,
        "findings": [finding.model_dump(mode="json") for finding in analysis.findings],
        "comparison_tables": {
            slug: measured.model_dump(mode="json") for slug, measured in analysis.tables.items()
        },
    }


def write_findings(analysis: RunAnalysis, out: Path) -> Path:
    """Write the run's findings file under `out`, creating `out`, and return its path."""
    run = analysis.loaded.run
    written = out / f"{run.report_code}-{run.fight_id}.findings.json"
    out.mkdir(parents=True, exist_ok=True)
    # Real rosters contain non-ASCII names; write_text's default encoding is
    # locale-dependent (commonly cp1252 on Windows) and would raise on them.
    written.write_text(
        json.dumps(run_payload(analysis), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return written


def write_page(
    analysis: RunAnalysis, out: Path, narrative_text: str | None, fetched_at: str
) -> Path:
    """Write the run's report page under `out` and return its path."""
    loaded = analysis.loaded
    run = loaded.run
    report_file = out / f"{run.report_code}-{run.fight_id}.html"
    report_file.write_text(
        render(
            build_report(
                loaded,
                analysis.findings,
                analysis.speed_sample,
                analysis.compared_slugs,
                analysis.subject,
                narrative_text,
                fetched_at,
                analysis.defensives,
                analysis.consumables,
                externals=analysis.externals,
                self_resurrections=load_self_resurrections(),
                throughput=analysis.throughput,
                reference_records=analysis.reference_records,
                comparison_measures=analysis.tables,
                roles=analysis.roles,
            ),
            icons=build_icons(
                loaded,
                tuple(one.parse for one in analysis.subjects if one.parse is not None),
                tuple(one.our_auras for one in analysis.subjects),
            ),
        ),
        encoding="utf-8",
    )
    return report_file
```

- [ ] **Step 4: Rewrite `analyze`'s body to call them**

Keep the signature and docstring. Replace everything from the `sys.stdout.reconfigure` block's end
to the end of the function with:

```python
    try:
        narrative_text = _read_narrative(narrative)
        code, fight_from_url = parse_report_url(report)
        repository = build_repository(cache_dir)
        before = repository.rate_limit()
        analysis = analyse_run(
            repository,
            cache_dir,
            code,
            fight if fight is not None else fight_from_url,
            players=player,
            all_players=all_players,
            no_compare=no_compare,
            throughput_ceiling=throughput_ceiling,
        )
        after = repository.rate_limit()
    except (ValueError, WclError, httpx.HTTPError, OSError) as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    # A guard of its own, because this phase fails differently from the one
    # above: nothing here can be degraded or retried, and a failure can arrive
    # after the findings have been written and announced. `OSError` alone --
    # the API errors the first block names cannot reach a filesystem write.
    try:
        written = write_findings(analysis, out)
        typer.echo(f"{len(analysis.findings)} findings written to {written}")
        report_file = write_page(
            analysis, out, narrative_text, datetime.now().strftime("%Y-%m-%d %H:%M")
        )
    except OSError as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    typer.echo(f"report written to {report_file}")
    typer.echo(_quota_sentence(before, after), err=True)
    _echo_cost_breakdown(repository.client.costs)
```

- [ ] **Step 5: Run the guard**

Run: `~/.local/bin/uv run pytest tests/test_cli_analyze_pin.py tests/test_cli.py tests/test_skills.py -q`
Expected: all pass, the pin included. If the pin fails, the move changed behaviour: diff the
written file against the golden and fix the move, never the golden.

- [ ] **Step 6: Lint, type-check, full suite**

Run: `~/.local/bin/uv run ruff check . && ~/.local/bin/uv run mypy && ~/.local/bin/uv run pytest -q`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/wowperf/cli.py
git commit -m "Lift analyze's pipeline into functions the character command can call" -m "The character command analyses several runs exactly as analyze analyses one. The body moves into analyse_run, write_findings and write_page unchanged, comments included; the golden pin proves the bytes did not move." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Typed tempo measures the findings and the ledger both read

**Files:**
- Modify: `src/wowperf/domain/comparison/tempo.py`
- Test: `tests/domain/comparison/test_tempo.py` (append)

**Interfaces:**
- Produces:
  - `class TempoMeasures(Frozen)` with `members: int`, `our_time: float`,
    `their_time: float | None`, `our_deaths: int`, `their_deaths: float`, `our_downtime: float`,
    `their_downtime: float`, `our_kick_share: float | None`, `their_kick_share: float`
  - `def tempo_measures(ours: LoadedRun, sample: SpeedSample) -> TempoMeasures | None`

- [ ] **Step 1: Write the failing tests** (append to `tests/domain/comparison/test_tempo.py`)

```python
# --- tempo_measures ----------------------------------------------------------


def test_tempo_measures_state_ours_beside_each_sample_median() -> None:
    ours = a_loaded(
        level=16, time_s=1300.0, deaths=4, kicked=1, landed=1,
        pulls=(a_pull(0, 0, 60), a_pull(1, 240, 60)),  # 180s of downtime
    )
    sample = SpeedSample(
        members=(
            a_member(time_s=1200.0, deaths=0, kicked=1, landed=1,
                     pulls=(a_pull(0, 0, 60), a_pull(1, 160, 60))),  # 100s
            a_member(time_s=1250.0, deaths=1, kicked=8, landed=2,
                     pulls=(a_pull(0, 0, 60), a_pull(1, 180, 60))),  # 120s
            a_member(time_s=1300.0, deaths=2, kicked=0, landed=2,
                     pulls=(a_pull(0, 0, 60), a_pull(1, 210, 60))),  # 150s
        )
    )

    measures = tempo_measures(ours, sample)

    assert measures == TempoMeasures(
        members=3,
        our_time=1300.0,
        their_time=1250.0,
        our_deaths=4,
        their_deaths=1.0,
        our_downtime=180.0,
        their_downtime=120.0,
        our_kick_share=0.5,
        their_kick_share=0.5,
    )


def test_tempo_measures_withhold_the_time_when_too_few_share_our_level() -> None:
    sample = SpeedSample(
        members=(a_member(level=16), a_member(level=16), a_member(level=17), a_member(level=15))
    )

    measures = tempo_measures(a_loaded(level=16), sample)

    assert measures is not None
    assert measures.their_time is None


def test_tempo_measures_name_no_share_when_none_of_our_casts_resolved() -> None:
    sample = SpeedSample(members=(a_member(), a_member(), a_member()))

    measures = tempo_measures(a_loaded(kicked=0, landed=0), sample)

    assert measures is not None
    assert measures.our_kick_share is None


def test_below_the_floor_there_are_no_sample_measures() -> None:
    assert tempo_measures(a_loaded(), SpeedSample(members=(a_member(), a_member()))) is None
    assert tempo_measures(a_loaded(), SpeedSample()) is None


def test_the_tempo_findings_state_the_figures_the_measures_carry() -> None:
    ours = a_loaded(deaths=4, pulls=(a_pull(0, 0, 60), a_pull(1, 240, 60)))
    sample = SpeedSample(
        members=(
            a_member(deaths=0, pulls=(a_pull(0, 0, 60), a_pull(1, 160, 60))),
            a_member(deaths=1, pulls=(a_pull(0, 0, 60), a_pull(1, 180, 60))),
            a_member(deaths=2, pulls=(a_pull(0, 0, 60), a_pull(1, 210, 60))),
        )
    )

    measures = tempo_measures(ours, sample)
    findings = compare_tempo_sample(ours, sample)

    assert measures is not None
    downtime = one(findings, "compare.downtime")
    assert f"median of 3 fast runs is {measures.their_downtime:.0f}s" in downtime.title
    assert f"died {measures.their_deaths:.0f} times" in one(findings, "compare.deaths").title
```

Change the import line at the top of the file to:

```python
from wowperf.domain.comparison.tempo import (
    TempoMeasures,
    compare_tempo,
    compare_tempo_sample,
    tempo_measures,
)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.local/bin/uv run pytest tests/domain/comparison/test_tempo.py -q`
Expected: collection error, `cannot import name 'TempoMeasures'`.

- [ ] **Step 3: Implement**

In `tempo.py` add `from wowperf.domain.base import Frozen` to the imports, then add after
`_kick_counts`:

```python
def _kick_shares(members: Sequence[SpeedMember]) -> list[float]:
    """Each member's own kicked share; a member that resolved nothing contributes 0.0.

    Dropping such a member would let the denominator drift from the number of
    members the median was drawn from.
    """
    shares: list[float] = []
    for member in members:
        kicked, landed = _kick_counts(member)
        resolved = kicked + landed
        shares.append(kicked / resolved if resolved > 0 else 0.0)
    return shares


class TempoMeasures(Frozen):
    """The four group figures the sample's tempo findings state, as numbers.

    The findings carry them as display strings, which nothing may parse back,
    so anything else that needs the figures -- the character page's group
    ledger -- reads them here, from the computation the findings read too.
    `their_time` is None when fewer than `MIN_SAMPLE_FOR_AGGREGATE` members
    shared our keystone level, where the completion time is withheld.
    `our_kick_share` is None when the log resolved none of our enemy casts.
    """

    members: int
    our_time: float
    their_time: float | None
    our_deaths: int
    their_deaths: float
    our_downtime: float
    their_downtime: float
    our_kick_share: float | None
    their_kick_share: float


def tempo_measures(ours: LoadedRun, sample: SpeedSample) -> TempoMeasures | None:
    """Our figures beside the sample's medians, or None below the aggregate floor.

    Below the floor the tempo findings fall back to one reference, which is a
    pairwise statement and not a median, so there is no sample figure to give.
    """
    members = sample.members
    if not members or not sample.can_aggregate(members):
        return None
    eligible = sample.duration_eligible
    our_kicked, our_landed = _kick_counts(ours)
    our_resolved = our_kicked + our_landed
    return TempoMeasures(
        members=len(members),
        our_time=ours.run.keystone_time_seconds,
        their_time=(
            median([member.run.keystone_time_seconds for member in eligible])
            if sample.can_aggregate(eligible)
            else None
        ),
        our_deaths=len(ours.deaths),
        their_deaths=median([float(len(member.deaths)) for member in members]),
        our_downtime=_downtime_seconds(ours),
        their_downtime=median([_downtime_seconds(member) for member in members]),
        our_kick_share=our_kicked / our_resolved if our_resolved > 0 else None,
        their_kick_share=median(_kick_shares(members)),
    )
```

Then make the four sample findings read the medians from it. In `compare_tempo_sample`, replace
from `if not sample.can_aggregate(sample.members):` to the end of the function with:

```python
    measures = tempo_measures(ours, sample)
    if measures is None:
        first = sample.members[0]
        return too_few(compare_tempo(ours, first, first.comparability), len(sample.members))

    members = sample.members
    return [
        _downtime_finding(ours, members, measures),
        _deaths_finding(ours, members, measures),
        _interrupts_finding(ours, members, measures),
        _duration_finding(ours, sample, measures),
    ]
```

and in each helper add the parameter `measures: TempoMeasures` and read the median from it:

- `_downtime_finding`: `our_downtime = measures.our_downtime`, `their_median = measures.their_downtime`
  (keep `theirs = [...]` for `observed_range`).
- `_deaths_finding`: `our_deaths = measures.our_deaths`, `their_median = measures.their_deaths`
  (keep `theirs` for the range).
- `_interrupts_finding`: `shares = _kick_shares(members)` replaces the loop,
  `their_median = measures.their_kick_share`; keep `our_kicked, our_landed = _kick_counts(ours)`
  for the title's counts. Move the loop's docstring sentence about a member resolving nothing into
  `_kick_shares` (already written above) and leave the rest of `_interrupts_finding`'s docstring.
- `_duration_finding(ours, sample, measures)`: replace `if not sample.can_aggregate(eligible):` with
  `if measures.their_time is None:` and `their_median = median(theirs)` with
  `their_median = measures.their_time` (keep `theirs` for the range). Leave everything else.

- [ ] **Step 4: Run the tests**

Run: `~/.local/bin/uv run pytest tests/domain/comparison/test_tempo.py tests/test_cli_analyze_pin.py -q`
Expected: all pass (the pin proves the findings did not change).

- [ ] **Step 5: Lint, type-check, full suite**

Run: `~/.local/bin/uv run ruff check . && ~/.local/bin/uv run mypy && ~/.local/bin/uv run pytest -q`

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/comparison/tempo.py tests/domain/comparison/test_tempo.py
git commit -m "Expose the tempo comparison's figures as typed measures" -m "The character page's group ledger needs completion time, deaths, downtime and kick share as numbers. The findings carry them only as display strings, which nothing may parse back, so both now read one computation and cannot disagree." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: A public `least_certain`

**Files:**
- Modify: `src/wowperf/domain/findings.py`, `src/wowperf/domain/analysis/night_rollups.py`
- Test: `tests/domain/test_findings.py` (append)

**Interfaces:**
- Produces: `def least_certain(confidences: Iterable[Confidence]) -> Confidence` in
  `wowperf.domain.findings`.

- [ ] **Step 1: Write the failing test** (append; add `least_certain` to the file's
  `from wowperf.domain.findings import …` line)

```python
def test_the_least_certain_badge_wins() -> None:
    assert least_certain([Confidence.MEASURED, Confidence.DERIVED]) is Confidence.DERIVED
    assert least_certain([Confidence.DERIVED, Confidence.INFERRED]) is Confidence.INFERRED
    assert least_certain([Confidence.MEASURED]) is Confidence.MEASURED
```

- [ ] **Step 2: Run to verify it fails**

Run: `~/.local/bin/uv run pytest tests/domain/test_findings.py -q`
Expected: ImportError on `least_certain`.

- [ ] **Step 3: Move it**

In `findings.py`, after `quantity`, add:

```python
_CERTAINTY = (Confidence.INFERRED, Confidence.DERIVED, Confidence.MEASURED)
"""Least certain first, so the lowest index is the weakest claim."""


def least_certain(confidences: Iterable[Confidence]) -> Confidence:
    """The weakest badge among several: a claim built on others is no surer than they are."""
    return min(confidences, key=_CERTAINTY.index)
```

In `night_rollups.py`, delete `_CERTAINTY` and `_least_certain`, add `least_certain` to its
`from wowperf.domain.findings import (…)` block, and replace the one call
`_least_certain(` with `least_certain(`.

- [ ] **Step 4: Run tests, lint, types**

Run: `~/.local/bin/uv run pytest tests/domain -q && ~/.local/bin/uv run ruff check . && ~/.local/bin/uv run mypy`

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/domain/findings.py src/wowperf/domain/analysis/night_rollups.py tests/domain/test_findings.py
git commit -m "Make the least-certain badge rule a shared helper" -m "The night's boss rollups badge a count by the weakest claim it counts, and the character page's repeated judgements must follow the same rule. One function, so the two cannot drift." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Parse a character URL

**Files:**
- Modify: `src/wowperf/urls.py` (and its ABOUTME second line)
- Test: `tests/test_urls.py` (append)

**Interfaces:**
- Produces: `class CharacterRef(NamedTuple)` with `region: str`, `realm: str`, `name: str`,
  `zone_id: int | None`; `def parse_character_url(value: str) -> CharacterRef`.

- [ ] **Step 1: Write the failing tests** (append; extend the import to
  `from wowperf.urls import CharacterRef, parse_character_url, parse_report_url`)

```python
def test_a_character_url_yields_its_region_realm_name_and_zone() -> None:
    assert parse_character_url(
        "https://www.warcraftlogs.com/character/eu/argent-dawn/Emberkin?zone=55"
    ) == CharacterRef(region="eu", realm="argent-dawn", name="Emberkin", zone_id=55)


def test_a_character_url_without_a_zone_has_none() -> None:
    assert parse_character_url(
        "https://www.warcraftlogs.com/character/us/stormrage/Stonewake"
    ).zone_id is None


def test_an_accented_name_is_decoded() -> None:
    ref = parse_character_url("https://www.warcraftlogs.com/character/EU/Archimonde/Br%C3%ADala")
    assert ref == CharacterRef(region="eu", realm="archimonde", name="Bríala", zone_id=None)


def test_a_report_url_is_not_a_character_url() -> None:
    with pytest.raises(ValueError, match="not a Warcraft Logs character URL"):
        parse_character_url("https://www.warcraftlogs.com/reports/aBc123XyZ")


def test_a_zone_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(ValueError, match="is not a zone id"):
        parse_character_url("https://www.warcraftlogs.com/character/eu/argent-dawn/Emberkin?zone=x")
```

- [ ] **Step 2: Run to verify they fail**

Run: `~/.local/bin/uv run pytest tests/test_urls.py -q` — Expected: ImportError.

- [ ] **Step 3: Implement** (append to `urls.py`; change `from urllib.parse import parse_qs, urlsplit`
  to `from urllib.parse import parse_qs, unquote, urlsplit`, add `from typing import NamedTuple`, and
  make the second ABOUTME line read
  `# ABOUTME: Accepts a bare code or a report URL, and a character page URL for the character command.`)

```python
CHARACTER_PATTERN = re.compile(
    r"^https?://[^/]*warcraftlogs\.com/character/"
    r"(?P<region>[A-Za-z]+)/(?P<realm>[^/?#]+)/(?P<name>[^/?#]+)/?(?P<rest>[?#].*)?$"
)


class CharacterRef(NamedTuple):
    """One character's address on Warcraft Logs, in the form the API's `character` field takes.

    `realm` is the server slug the page's address carries (`argent-dawn`), which
    is what `serverSlug` wants. `name` is percent-decoded, so an accented name
    reaches the API as itself.
    """

    region: str
    realm: str
    name: str
    zone_id: int | None


def parse_character_url(value: str) -> CharacterRef:
    match = CHARACTER_PATTERN.match(value.strip())
    if match is None:
        raise ValueError(
            f"{value!r} is not a Warcraft Logs character URL "
            "(https://www.warcraftlogs.com/character/<region>/<realm>/<name>)"
        )
    rest = urlsplit(match.group("rest") or "")
    zones = parse_qs(rest.query).get("zone")
    zone_id = None
    if zones:
        if not zones[-1].isdigit():
            raise ValueError(f"zone={zones[-1]!r} is not a zone id")
        zone_id = int(zones[-1])
    return CharacterRef(
        region=match.group("region").lower(),
        realm=unquote(match.group("realm")).lower(),
        name=unquote(match.group("name")),
        zone_id=zone_id,
    )
```

- [ ] **Step 4: Run tests, lint, types** — as in Task 4 Step 4, over `tests/test_urls.py`.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/urls.py tests/test_urls.py
git commit -m "Parse a Warcraft Logs character URL" -m "The character command starts from a character page, not a report. Region, realm slug, decoded name and the optional zone are what the API's character field and the zone lookup need." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Verify the character fields live, then query and read them

**Files:**
- Create: `src/wowperf/domain/character/__init__.py` (empty), `src/wowperf/domain/character/model.py`
- Modify: `src/wowperf/adapters/wcl/queries.py`
- Create: `src/wowperf/adapters/wcl/character_runs.py`, `src/wowperf/adapters/wcl/character_repository.py`
- Modify: `.claude/skills/wcl-api/SKILL.md`
- Test: `tests/adapters/wcl/test_character_runs.py`, `tests/adapters/wcl/test_character_repository.py`

**Interfaces:**
- Produces:
  - `wowperf.domain.character.model`: `Dungeon(encounter_id: int, name: str)`,
    `Zone(zone_id: int, name: str, difficulty_ids: tuple[int, ...] = (), dungeons: tuple[Dungeon, ...] = ())`,
    `RankedRun(encounter_id: int, keystone_level: int, spec: str, start_time_ms: int, report_code: str | None = None, fight_id: int | None = None)`
  - `queries.ZONE_QUERY`, `queries.character_runs_query(encounter_ids: Sequence[int]) -> str`
  - `character_runs.build_zone(payload: dict[str, Any]) -> Zone`,
    `character_runs.build_ranked_runs(payload: dict[str, Any], dungeons: Sequence[Dungeon]) -> tuple[RankedRun, ...]`
  - `WclCharacterRepository(client: WclClient, cache: DiskCache)` with
    `.zone(zone_id: int) -> Zone` and
    `.ranked_runs(name: str, realm: str, region: str, zone: Zone) -> tuple[RankedRun, ...]`

- [ ] **Step 1: Verify the fields against the live API**

These were read by hand on 2026-10-08 but are in no dated row yet. Write a throwaway probe in the
scratchpad (never in the repo) that sends, through `WclClient` with the `.env` credentials (loaded
with `wowperf.adapters.config.dotenv.apply_dotenv`; never print them):

1. `{ worldData { zone(id: 55) { id name difficulties { id name } encounters { id name } } } }`
2. `{ worldData { zones { id name difficulties { id name } } } }` — pick one raid zone from the
   answer and note its difficulty ids.
3. `characterData { character(name: …, serverSlug: …, serverRegion: …) { id hidden e<ID>: encounterRankings(encounterID: <ID>) } }`
   for RwlRwlRwlRwl's character (ask for it in chat; it is never written to the repo) and one of
   zone 55's encounter ids.
4. The same query for a name that does not exist on that realm.

Record, for the plan's reader: zone 55's difficulties are exactly `[{"id": 10, "name": "Dungeon"}]`;
the raid zone lists other ids; a rank has `report { code fightID startTime }`, `bracketData` equal to
the keystone level, `spec`, `startTime`; a rank with no public log has `report.code == ""` and
`fightID: null`; a missing character answers `character: null`. **If any of these differs, stop and
report it to RwlRwlRwlRwl before writing code** — Task 7's selection depends on each.

- [ ] **Step 2: Record the verified fields in the wcl-api skill**

Append to the `## Fields` table, dated the day Step 1 ran:

```markdown
| `characterData` | `Query` | 2026-10-14 | yes |
| `serverSlug` | `characterData.character` argument | 2026-10-14 | yes |
| `serverRegion` | `characterData.character` argument | 2026-10-14 | yes |
| `hidden` | `Character` | 2026-10-14 | yes |
| `encounterRankings` | `Character` | 2026-10-14 | yes |
| `zoneRankings` | `Character` | 2026-10-14 | no |
| `recentReports` | `Character` | 2026-10-14 | no |
| `difficulties` | `Zone` | 2026-10-14 | yes |
| `encounters` | `Zone` | 2026-10-14 | yes |
```

and add a section `### A character's ranked runs (verified 2026-10-14)` stating what Step 1
recorded, that Warcraft Logs describes `encounterRankings` as "not considered frozen, and it can
change without notice", that `bracketData` on these ranks is the keystone level itself (unlike the
`characterRankings` leaderboard's bracket argument), and that both queries go to the one-day cache
because the list changes with every key played.

- [ ] **Step 3: Write the failing adapter tests**

`tests/adapters/wcl/test_character_runs.py`:

```python
# ABOUTME: Behaviour tests for reading a zone's dungeons and a character's ranked runs.
# ABOUTME: A rank with no public report is kept, marked, so selection can say why it was skipped.

from typing import Any

import pytest

from wowperf.adapters.wcl.character_runs import build_ranked_runs, build_zone
from wowperf.domain.character.model import Dungeon, RankedRun, Zone

DUNGEONS = (Dungeon(encounter_id=101, name="Den of Nalorakk"),
            Dungeon(encounter_id=102, name="Murder Row"))


def a_rank(level: int, code: str, fight: int | None, start: int) -> dict[str, Any]:
    return {
        "report": {"code": code, "fightID": fight, "startTime": start},
        "bracketData": level,
        "spec": "Protection",
        "startTime": start,
        "duration": 1_700_000,
        "medal": "bronze",
    }


def test_a_zone_names_its_dungeons_and_difficulties() -> None:
    payload = {
        "worldData": {
            "zone": {
                "id": 55,
                "name": "Mythic+ Season 2",
                "difficulties": [{"id": 10, "name": "Dungeon"}],
                "encounters": [{"id": 101, "name": "Den of Nalorakk"},
                               {"id": 102, "name": "Murder Row"}],
            }
        }
    }

    assert build_zone(payload) == Zone(
        zone_id=55, name="Mythic+ Season 2", difficulty_ids=(10,), dungeons=DUNGEONS
    )


def test_an_unknown_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="no zone"):
        build_zone({"worldData": {"zone": None}})


def test_each_rank_becomes_a_ranked_run_of_its_dungeon() -> None:
    payload = {
        "characterData": {
            "character": {
                "id": 1,
                "hidden": False,
                "e101": {"ranks": [a_rank(18, "aBc123XyZ", 7, 2000)]},
                "e102": {"ranks": [a_rank(17, "", None, 1000)]},
            }
        }
    }

    assert build_ranked_runs(payload, DUNGEONS) == (
        RankedRun(encounter_id=101, keystone_level=18, spec="Protection", start_time_ms=2000,
                  report_code="aBc123XyZ", fight_id=7),
        RankedRun(encounter_id=102, keystone_level=17, spec="Protection", start_time_ms=1000),
    )


def test_a_dungeon_with_no_ranks_contributes_nothing() -> None:
    payload = {"characterData": {"character": {"id": 1, "hidden": False, "e101": None}}}
    assert build_ranked_runs(payload, DUNGEONS) == ()


def test_a_missing_character_is_refused() -> None:
    with pytest.raises(ValueError, match="no such character"):
        build_ranked_runs({"characterData": {"character": None}}, DUNGEONS)


def test_a_character_with_hidden_rankings_is_refused() -> None:
    with pytest.raises(ValueError, match="hidden"):
        build_ranked_runs({"characterData": {"character": {"id": 1, "hidden": True}}}, DUNGEONS)
```

`tests/adapters/wcl/test_character_repository.py`:

```python
# ABOUTME: Behaviour tests for fetching a zone and a character's ranked runs through the cache.
# ABOUTME: Pins the variables the API receives and that a second read comes from disk.

import json
from pathlib import Path
from typing import Any

import httpx

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.character_repository import WclCharacterRepository
from wowperf.adapters.wcl.client import WclClient
from wowperf.domain.character.model import Dungeon, Zone

TOKEN = {"access_token": "t", "expires_in": 86400}
ZONE = Zone(zone_id=55, name="Mythic+ Season 2", difficulty_ids=(10,),
            dungeons=(Dungeon(encounter_id=101, name="Den of Nalorakk"),))


def repository(tmp_path: Path, bodies: list[dict[str, Any]]) -> WclCharacterRepository:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        bodies.append(body)
        if "zoneId" in body["variables"]:
            return httpx.Response(200, json={"data": {"worldData": {"zone": {
                "id": 55, "name": "Mythic+ Season 2",
                "difficulties": [{"id": 10, "name": "Dungeon"}],
                "encounters": [{"id": 101, "name": "Den of Nalorakk"}]}}}})
        return httpx.Response(200, json={"data": {"characterData": {"character": {
            "id": 1, "hidden": False, "e101": {"ranks": []}}}}})

    http = httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x")
    return WclCharacterRepository(WclClient(TokenProvider("id", "secret", http), http),
                                  DiskCache(tmp_path))


def test_the_zone_is_asked_for_by_id(tmp_path: Path) -> None:
    bodies: list[dict[str, Any]] = []
    assert repository(tmp_path, bodies).zone(55) == ZONE
    assert bodies[0]["variables"] == {"zoneId": 55}


def test_the_character_is_asked_for_by_name_realm_and_region(tmp_path: Path) -> None:
    bodies: list[dict[str, Any]] = []
    runs = repository(tmp_path, bodies).ranked_runs("Emberkin", "argent-dawn", "eu", ZONE)

    assert runs == ()
    assert bodies[0]["variables"] == {
        "name": "Emberkin", "serverSlug": "argent-dawn", "serverRegion": "eu"
    }
    assert "e101: encounterRankings(encounterID: 101)" in bodies[0]["query"]


def test_a_second_read_is_served_from_the_cache(tmp_path: Path) -> None:
    bodies: list[dict[str, Any]] = []
    characters = repository(tmp_path, bodies)
    characters.zone(55)
    characters.zone(55)
    assert len(bodies) == 1
```

Also append to `tests/adapters/wcl/test_queries.py`:

```python
def test_the_character_runs_query_aliases_one_ranking_per_dungeon_in_id_order() -> None:
    query = character_runs_query([102, 101])
    assert query.index("e101: encounterRankings(encounterID: 101)") < query.index(
        "e102: encounterRankings(encounterID: 102)"
    )
    assert operation_name(query) == "CharacterRuns"
```

(importing `character_runs_query` and `operation_name` from `wowperf.adapters.wcl.queries` if the
file does not already).

- [ ] **Step 4: Run to verify they fail**

Run: `~/.local/bin/uv run pytest tests/adapters/wcl/test_character_runs.py tests/adapters/wcl/test_character_repository.py tests/adapters/wcl/test_queries.py -q`
Expected: ImportErrors.

- [ ] **Step 5: Implement**

`src/wowperf/domain/character/model.py` (Task 7 and 8 append to it):

```python
# ABOUTME: The character command's domain types: a zone's dungeons, ranked runs, chosen runs,
# ABOUTME: and what one analysed run hands to the cross-run reading.

from wowperf.domain.base import Frozen


class Dungeon(Frozen):
    encounter_id: int
    name: str


class Zone(Frozen):
    """A Warcraft Logs zone: its dungeons, and the difficulty ids it is ranked at."""

    zone_id: int
    name: str
    difficulty_ids: tuple[int, ...] = ()
    dungeons: tuple[Dungeon, ...] = ()


class RankedRun(Frozen):
    """One of the character's ranked runs, as their rankings list it.

    `report_code` and `fight_id` are None for a run with no public log: the
    rankings keep it, the analysis cannot read it.
    """

    encounter_id: int
    keystone_level: int
    spec: str
    start_time_ms: int
    report_code: str | None = None
    fight_id: int | None = None
```

In `queries.py`, change `talents_query`'s docstring sentence "This is the only generated query
here;" to "One of two generated queries here, with `character_runs_query`;", then append:

```python
# `worldData.zone` names a zone's dungeons and the difficulties it is ranked at.
# A Mythic+ zone lists exactly one, id 10 "Dungeon" (wcl-api skill, "A
# character's ranked runs", 2026-10-14), which is how the character command
# refuses a raid zone before it reads anything else.
ZONE_QUERY = """
query Zone($zoneId: Int!) {
  worldData {
    zone(id: $zoneId) {
      id
      name
      difficulties { id name }
      encounters { id name }
    }
  }
}
"""


def character_runs_query(encounter_ids: Sequence[int]) -> str:
    """One aliased `encounterRankings` per dungeon, for one character.

    `Character.encounterRankings(encounterID:)` takes one encounter, so a zone's
    dungeons need an alias each, as `talents_query` gives each roster member
    one. The ids are coerced to `int` and sorted for the reason
    `talents_query` gives: the cache key is the query text.
    """
    fields = "\n".join(
        f"      e{encounter_id}: encounterRankings(encounterID: {encounter_id})"
        for encounter_id in sorted(int(encounter_id) for encounter_id in encounter_ids)
    )
    return f"""
query CharacterRuns($name: String!, $serverSlug: String!, $serverRegion: String!) {{
  characterData {{
    character(name: $name, serverSlug: $serverSlug, serverRegion: $serverRegion) {{
      id
      hidden
{fields}
    }}
  }}
}}
"""
```

`src/wowperf/adapters/wcl/character_runs.py`:

```python
# ABOUTME: Reads a zone's dungeons and one character's per-dungeon rankings off the API's answer.
# ABOUTME: A rank with no public report is kept with no code, so selection can say why it was skipped.

from collections.abc import Sequence
from typing import Any

from wowperf.domain.character.model import Dungeon, RankedRun, Zone


def build_zone(payload: dict[str, Any]) -> Zone:
    zone = (payload.get("worldData") or {}).get("zone")
    if zone is None:
        raise ValueError("Warcraft Logs has no zone with that id")
    return Zone(
        zone_id=int(zone["id"]),
        name=str(zone["name"]),
        difficulty_ids=tuple(int(one["id"]) for one in zone.get("difficulties") or ()),
        dungeons=tuple(
            Dungeon(encounter_id=int(one["id"]), name=str(one["name"]))
            for one in zone.get("encounters") or ()
        ),
    )


def build_ranked_runs(
    payload: dict[str, Any], dungeons: Sequence[Dungeon]
) -> tuple[RankedRun, ...]:
    """Every rank of every dungeon, in dungeon order then the rankings' own order."""
    character = (payload.get("characterData") or {}).get("character")
    if character is None:
        raise ValueError("Warcraft Logs has no such character on that realm")
    if character.get("hidden"):
        raise ValueError("This character has hidden its rankings on Warcraft Logs")
    runs: list[RankedRun] = []
    for dungeon in dungeons:
        block = character.get(f"e{dungeon.encounter_id}") or {}
        for rank in block.get("ranks") or ():
            report = rank.get("report") or {}
            # A run with no public log arrives with an empty code and no fight.
            code = report.get("code") or None
            fight = report.get("fightID")
            runs.append(
                RankedRun(
                    encounter_id=dungeon.encounter_id,
                    keystone_level=int(rank["bracketData"]),
                    spec=str(rank["spec"]),
                    start_time_ms=int(rank["startTime"]),
                    report_code=code,
                    fight_id=int(fight) if code is not None and fight is not None else None,
                )
            )
    return tuple(runs)
```

`src/wowperf/adapters/wcl/character_repository.py`:

```python
# ABOUTME: Fetches a zone and one character's ranked runs, behind the cache it is handed.
# ABOUTME: The CLI hands it the one-day tier: the list changes with every key the character plays.

from typing import Any

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.character_runs import build_ranked_runs, build_zone
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.queries import ZONE_QUERY, character_runs_query
from wowperf.domain.character.model import RankedRun, Zone


class WclCharacterRepository:
    def __init__(self, client: WclClient, cache: DiskCache) -> None:
        self._client = client
        self._cache = cache

    def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        payload, _ = self._cache.get_or_fetch(
            cache_key(query, variables),
            lambda: self._client.execute(query, variables),
        )
        return payload

    def zone(self, zone_id: int) -> Zone:
        return build_zone(self._query(ZONE_QUERY, {"zoneId": zone_id}))

    def ranked_runs(self, name: str, realm: str, region: str, zone: Zone) -> tuple[RankedRun, ...]:
        query = character_runs_query([dungeon.encounter_id for dungeon in zone.dungeons])
        payload = self._query(
            query, {"name": name, "serverSlug": realm, "serverRegion": region}
        )
        return build_ranked_runs(payload, zone.dungeons)
```

- [ ] **Step 6: Run the tests, then the skill check**

Run: `~/.local/bin/uv run pytest tests/adapters/wcl tests/test_skills.py -q`
Expected: all pass, including `test_every_field_the_table_says_we_query_is_in_the_queries` and
`test_every_field_the_table_says_we_do_not_query_is_absent`.

- [ ] **Step 7: Lint, types, full suite, commit**

```bash
git add src/wowperf/domain/character src/wowperf/adapters/wcl/queries.py src/wowperf/adapters/wcl/character_runs.py src/wowperf/adapters/wcl/character_repository.py .claude/skills/wcl-api/SKILL.md tests/adapters/wcl
git commit -m "Read a zone's dungeons and a character's ranked runs" -m "The character command chooses its runs from the character's own rankings. Every field was verified live and dated in the wcl-api skill first, and both queries go to the one-day cache because the list changes with every key played." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Choose the runs

**Files:**
- Modify: `src/wowperf/domain/character/model.py` (append)
- Create: `src/wowperf/domain/character/selection.py`
- Test: `tests/domain/character/__init__.py` (empty), `tests/domain/character/test_selection.py`

**Interfaces:**
- Consumes: `Dungeon`, `Zone`, `RankedRun` (Task 6).
- Produces:
  - model: `ChosenRun(dungeon: str, encounter_id: int, keystone_level: int, start_time_ms: int, report_code: str, fight_id: int)`,
    `LeftOut(dungeon: str, reason: str)`,
    `Selection(spec: str, chosen: tuple[ChosenRun, ...] = (), left_out: tuple[LeftOut, ...] = ())`
  - selection: `MYTHIC_PLUS_DIFFICULTY = 10`, `LEVELS_BELOW_TOP = 1`, `SELECTION_RULE: str`,
    `require_mythic_plus(zone: Zone) -> None`,
    `choose_spec(runs: Sequence[RankedRun], requested: str | None) -> str`,
    `select_runs(zone: Zone, runs: Sequence[RankedRun], spec: str | None = None) -> Selection`

- [ ] **Step 1: Write the failing tests** (`tests/domain/character/test_selection.py`)

```python
# ABOUTME: Behaviour tests for choosing one recent high key per dungeon for one specialisation.
# ABOUTME: Covers the level window, recency, missing logs, left-out dungeons and the spec rule.

import pytest

from wowperf.domain.character.model import ChosenRun, Dungeon, LeftOut, RankedRun, Zone
from wowperf.domain.character.selection import (
    choose_spec,
    require_mythic_plus,
    select_runs,
)

DEN = Dungeon(encounter_id=101, name="Den of Nalorakk")
ROW = Dungeon(encounter_id=102, name="Murder Row")
ZONE = Zone(zone_id=55, name="Mythic+ Season 2", difficulty_ids=(10,), dungeons=(DEN, ROW))


def a_run(encounter_id: int, level: int, start: int, *, code: str | None = "aBc123XyZ",
          fight: int | None = 1, spec: str = "Blood") -> RankedRun:
    return RankedRun(encounter_id=encounter_id, keystone_level=level, spec=spec,
                     start_time_ms=start, report_code=code,
                     fight_id=fight if code is not None else None)


def test_the_most_recent_run_at_the_top_level_or_one_below_is_chosen() -> None:
    runs = [a_run(101, 18, 100, fight=1), a_run(101, 17, 300, fight=2), a_run(101, 16, 500, fight=3)]

    selection = select_runs(ZONE, runs)

    assert selection.chosen == (
        ChosenRun(dungeon="Den of Nalorakk", encounter_id=101, keystone_level=17,
                  start_time_ms=300, report_code="aBc123XyZ", fight_id=2),
    )


def test_two_below_the_top_is_never_chosen() -> None:
    runs = [a_run(101, 18, 100, code=None), a_run(101, 16, 500)]

    selection = select_runs(ZONE, runs)

    assert selection.chosen == ()
    assert LeftOut(dungeon="Den of Nalorakk",
                   reason="no run at +18 or +17 has a public report") in selection.left_out


def test_a_run_with_no_public_log_is_passed_over_for_one_with_a_log() -> None:
    runs = [a_run(101, 18, 900, code=None), a_run(101, 18, 100, fight=4)]
    assert select_runs(ZONE, runs).chosen[0].fight_id == 4


def test_a_dungeon_never_run_as_the_spec_is_left_out_with_the_reason() -> None:
    selection = select_runs(ZONE, [a_run(101, 18, 100)])
    assert selection.left_out == (LeftOut(dungeon="Murder Row", reason="no ranked run as Blood"),)


def test_the_spec_with_the_most_ranked_runs_is_read() -> None:
    runs = [a_run(101, 18, 1, spec="Blood"), a_run(102, 18, 2, spec="Blood"),
            a_run(101, 18, 3, spec="Frost")]
    assert choose_spec(runs, None) == "Blood"


def test_a_tie_between_specs_goes_to_the_one_played_most_recently() -> None:
    runs = [a_run(101, 18, 1, spec="Blood"), a_run(101, 18, 9, spec="Frost")]
    assert choose_spec(runs, None) == "Frost"


def test_a_requested_spec_is_matched_ignoring_case() -> None:
    assert choose_spec([a_run(101, 18, 1, spec="Blood")], "blood") == "Blood"


def test_a_spec_the_character_never_ran_is_refused_naming_the_ones_it_did() -> None:
    with pytest.raises(ValueError, match="ranked as: Blood"):
        choose_spec([a_run(101, 18, 1, spec="Blood")], "Frost")


def test_no_ranked_run_at_all_is_refused() -> None:
    with pytest.raises(ValueError, match="no ranked Mythic"):
        select_runs(ZONE, [])


def test_a_raid_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="not a Mythic\\+ zone"):
        require_mythic_plus(Zone(zone_id=42, name="Some Raid", difficulty_ids=(3, 4, 5)))
    require_mythic_plus(ZONE)
```

- [ ] **Step 2: Run to verify they fail** — `~/.local/bin/uv run pytest tests/domain/character -q`

- [ ] **Step 3: Implement**

Append to `model.py`:

```python
class ChosenRun(Frozen):
    """A run the selection kept: always one with a public log to read."""

    dungeon: str
    encounter_id: int
    keystone_level: int
    start_time_ms: int
    report_code: str
    fight_id: int


class LeftOut(Frozen):
    dungeon: str
    reason: str


class Selection(Frozen):
    spec: str
    chosen: tuple[ChosenRun, ...] = ()
    left_out: tuple[LeftOut, ...] = ()
```

`selection.py`:

```python
# ABOUTME: Chooses one recent high key per dungeon, for one specialisation, from a character's ranks.
# ABOUTME: A dungeon with nothing to read is left out with the reason, never silently dropped.

from collections import Counter
from collections.abc import Sequence

from wowperf.domain.character.model import ChosenRun, LeftOut, RankedRun, Selection, Zone

MYTHIC_PLUS_DIFFICULTY = 10
"""The one difficulty a Mythic+ zone is ranked at (wcl-api skill, 2026-10-14)."""

LEVELS_BELOW_TOP = 1
"""How far under the character's best key in a dungeon a run may sit and still be read."""

SELECTION_RULE = (
    "One run per dungeon: the most recent ranked run with a public log at the character's "
    f"highest keystone level in that dungeon or up to {LEVELS_BELOW_TOP} below it, timed or "
    "not, for one specialisation."
)


def require_mythic_plus(zone: Zone) -> None:
    if zone.difficulty_ids != (MYTHIC_PLUS_DIFFICULTY,):
        raise ValueError(
            f"Zone {zone.zone_id} ({zone.name}) is not a Mythic+ zone; "
            "the character command reads Mythic+ runs only"
        )


def choose_spec(runs: Sequence[RankedRun], requested: str | None) -> str:
    """The requested spec, or the one with the most ranked runs, then the latest run."""
    counts = Counter(run.spec for run in runs)
    if not counts:
        raise ValueError("This character has no ranked Mythic+ runs in this zone")
    if requested is not None:
        for spec in counts:
            if spec.casefold() == requested.casefold():
                return spec
        raise ValueError(
            f"No ranked runs as {requested!r}; ranked as: {', '.join(sorted(counts))}"
        )
    latest = {spec: max(run.start_time_ms for run in runs if run.spec == spec) for spec in counts}
    return max(counts, key=lambda spec: (counts[spec], latest[spec]))


def select_runs(zone: Zone, runs: Sequence[RankedRun], spec: str | None = None) -> Selection:
    chosen_spec = choose_spec(runs, spec)
    chosen: list[ChosenRun] = []
    left_out: list[LeftOut] = []
    for dungeon in zone.dungeons:
        mine = [
            run for run in runs
            if run.encounter_id == dungeon.encounter_id and run.spec == chosen_spec
        ]
        if not mine:
            left_out.append(LeftOut(dungeon=dungeon.name, reason=f"no ranked run as {chosen_spec}"))
            continue
        top = max(run.keystone_level for run in mine)
        floor = top - LEVELS_BELOW_TOP
        best: ChosenRun | None = None
        for run in mine:
            if run.keystone_level < floor or run.report_code is None or run.fight_id is None:
                continue
            if best is None or run.start_time_ms > best.start_time_ms:
                best = ChosenRun(
                    dungeon=dungeon.name,
                    encounter_id=dungeon.encounter_id,
                    keystone_level=run.keystone_level,
                    start_time_ms=run.start_time_ms,
                    report_code=run.report_code,
                    fight_id=run.fight_id,
                )
        if best is None:
            left_out.append(LeftOut(
                dungeon=dungeon.name,
                reason=f"no run at +{top} or +{floor} has a public report",
            ))
            continue
        chosen.append(best)
    return Selection(spec=chosen_spec, chosen=tuple(chosen), left_out=tuple(left_out))
```

- [ ] **Step 4: Run tests, lint, types; commit**

```bash
git add src/wowperf/domain/character tests/domain/character
git commit -m "Choose one recent high key per dungeon for one specialisation" -m "Patterns only mean something if they hold across dungeons and specs are not mixed. A dungeon with nothing readable is listed with its reason rather than dropped." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: What one run hands on, and repeated judgements

**Files:**
- Modify: `src/wowperf/domain/character/model.py` (append)
- Create: `src/wowperf/domain/character/patterns.py`
- Test: `tests/domain/character/builders.py`, `tests/domain/character/test_repeats.py`

**Interfaces:**
- Consumes: `Finding`, `quantifier_for`, `least_certain` (Task 4), `PlayerMeasures`,
  `TempoMeasures` (Task 3).
- Produces:
  - model: `CharacterRun(report_code: str, fight_id: int, dungeon: str, keystone_level: int, in_time: bool, subject_slug: str, subject_deaths: int = 0, findings: tuple[Finding, ...] = (), measures: PlayerMeasures | None = None, tempo: TempoMeasures | None = None)`,
    `FailedRun(dungeon: str, keystone_level: int, report_code: str, fight_id: int, reason: str)`
  - patterns: `REPEAT_MIN_RUNS`, `REPEAT_RULE: str`, `ANALYSIS_FAMILIES_NOT_COUNTED: str`,
    `COUNTED_NOT_SUMMED: str`, `family_of(finding: Finding, subject_slug: str) -> str | None`,
    `repeated_judgements(runs: Sequence[CharacterRun]) -> list[Finding]`

- [ ] **Step 1: Shared test builders** (`tests/domain/character/builders.py`)

```python
# ABOUTME: Builders for the character tests: runs, findings and the comparison rows they carry.
# ABOUTME: Dungeon names only; every player in these fixtures is one of the sanctioned names.

from wowperf.domain.character.model import CharacterRun
from wowperf.domain.comparison.measures import (
    AbilityRate,
    AuraRow,
    AuraUptime,
    DebuffRow,
    DebuffTable,
    PlayerMeasures,
    StatShare,
    Stretch,
    Verdict,
)
from wowperf.domain.comparison.tempo import TempoMeasures
from wowperf.domain.findings import Confidence, Finding

DUNGEONS = ("Altar of Fangs", "Den of Nalorakk", "Kings' Rest", "Murder Row",
            "Ruby Life Pools", "Temple of Sethraliss", "The Blinding Vale", "Voidscar Arena")


def a_run(index: int, *, findings: tuple[Finding, ...] = (),
          measures: PlayerMeasures | None = None, tempo: TempoMeasures | None = None,
          slug: str = "emberkin-0", subject_deaths: int = 0, level: int = 18,
          in_time: bool = True) -> CharacterRun:
    return CharacterRun(
        report_code=f"code{index:03d}x", fight_id=index + 1,
        dungeon=DUNGEONS[index % len(DUNGEONS)], keystone_level=level, in_time=in_time,
        subject_slug=slug, subject_deaths=subject_deaths, findings=findings,
        measures=measures, tempo=tempo,
    )


def a_finding(finding_id: str, *, slug: str = "emberkin-0", ability_id: int | None = None,
              ability_name: str = "", title: str = "A run's own title",
              confidence: Confidence = Confidence.DERIVED) -> Finding:
    return Finding(id=finding_id, title=title, detail="", confidence=confidence,
                   ability_id=ability_id, ability_name=ability_name, player_slug=slug)


def a_rate(ability_id: int, ours: float, theirs: float, *, stretch: Stretch = Stretch.BOSS,
           verdict: Verdict = Verdict.LEVEL, name: str = "Vampiric Strike") -> AbilityRate:
    return AbilityRate(ability_id=ability_id, name=name, ours=ours, their_median=theirs,
                       their_rates=(theirs,), stretch=stretch, verdict=verdict)


def a_buff(ability_id: int, ours: float, theirs: float, *, verdict: Verdict = Verdict.LEVEL,
           name: str = "Visceral Strength") -> AuraRow:
    return AuraRow(uptime=AuraUptime(ability_id=ability_id, name=name, ours=ours,
                                     their_median=theirs, their_fractions=(theirs,),
                                     verdict=verdict))


def a_debuff(ability_id: int, ours: float, theirs: float, *, verdict: Verdict = Verdict.LEVEL,
             shared_with: tuple[int, ...] = (), name: str = "Blood Plague") -> DebuffRow:
    return DebuffRow(uptime=AuraUptime(ability_id=ability_id, name=name, ours=ours,
                                       their_median=theirs, their_fractions=(theirs,),
                                       verdict=verdict),
                     shared_with=shared_with)


def a_stat(name: str, ours: float, theirs: float, *,
           verdict: Verdict = Verdict.LEVEL) -> StatShare:
    return StatShare(name=name, ours=ours, their_median=theirs, their_shares=(theirs,),
                     our_rating=100, their_median_rating=100.0, their_ratings=(100.0,),
                     verdict=verdict)


def measures_of(*, boss: tuple[AbilityRate, ...] = (), trash: tuple[AbilityRate, ...] = (),
                auras: tuple[AuraRow, ...] = (), debuffs: tuple[DebuffRow, ...] = (),
                stats: tuple[StatShare, ...] = ()) -> PlayerMeasures:
    return PlayerMeasures(boss=boss, trash=trash, auras=auras, stats=stats,
                          debuffs=DebuffTable(rows=debuffs))
```

- [ ] **Step 2: Write the failing tests** (`tests/domain/character/test_repeats.py`)

```python
# ABOUTME: Behaviour tests for the judgements one character's runs made again and again.
# ABOUTME: Families join across runs by id shape and ability, never by a run's own slug or rank.

from tests.domain.character.builders import a_finding, a_run
from wowperf.domain.character.patterns import family_of, repeated_judgements
from wowperf.domain.findings import Confidence, Finding

CARESS = 195292


def caress_gap(rank: int, slug: str = "emberkin-0") -> Finding:
    return a_finding(f"compare.spells.trash.rate.{rank}.{slug}", slug=slug,
                     ability_id=CARESS, ability_name="Death's Caress")


def test_the_same_family_under_two_slugs_and_two_ranks_is_one_family() -> None:
    assert family_of(a_finding("compare.spells.trash.rate.0.emberkin-0"), "emberkin-0") == (
        "compare.spells.trash.rate")
    assert family_of(a_finding("compare.spells.trash.rate.3.emberkin-2", slug="emberkin-2"),
                     "emberkin-2") == "compare.spells.trash.rate"


def test_a_judgement_in_three_of_five_runs_is_reported_with_its_quantifier() -> None:
    runs = [a_run(0, findings=(caress_gap(0),)), a_run(1, findings=(caress_gap(3, "emberkin-2"),),
            slug="emberkin-2"), a_run(2, findings=(caress_gap(1),)), a_run(3), a_run(4)]

    [finding] = repeated_judgements(runs)

    assert finding.id == f"character.repeat.compare.spells.trash.rate.{CARESS}"
    assert finding.title == (
        "Top parses cast Death's Caress more often than you on trash, in 3 of 5 runs")
    assert finding.quantifier == "most"
    assert finding.ability_id == CARESS
    assert finding.ability_name == "Death's Caress"
    assert finding.seconds_lost is None
    assert finding.evidence[0] == "Altar of Fangs +18: A run's own title"


def test_fewer_than_three_runs_is_never_a_pattern_even_at_half() -> None:
    runs = [a_run(0, findings=(caress_gap(0),)), a_run(1, findings=(caress_gap(0),)),
            a_run(2), a_run(3)]
    assert repeated_judgements(runs) == []


def test_under_half_the_runs_is_not_a_pattern() -> None:
    runs = [a_run(i, findings=(caress_gap(0),) if i < 3 else ()) for i in range(8)]
    assert repeated_judgements(runs) == []


def test_exactly_half_is_a_pattern_about_half_the_time() -> None:
    runs = [a_run(i, findings=(caress_gap(0),) if i < 4 else ()) for i in range(8)]
    [finding] = repeated_judgements(runs)
    assert finding.quantifier == "about half"


def test_a_teammates_judgement_is_not_counted() -> None:
    teammate = a_finding("compare.spells.trash.rate.0.stonewake-1", slug="stonewake-1",
                         ability_id=CARESS, ability_name="Death's Caress")
    runs = [a_run(i, findings=(teammate,)) for i in range(4)]
    assert repeated_judgements(runs) == []


def test_statements_that_always_appear_are_never_counted() -> None:
    always = (a_finding("compare.duration", slug=""), a_finding("compare.downtime", slug=""),
              a_finding("compare.spells.level.emberkin-0"),
              a_finding("compare.uptime.unjudged.emberkin-0"),
              a_finding("compare.uptime.debuff.unjudged.emberkin-0"))
    runs = [a_run(i, findings=always) for i in range(4)]
    assert repeated_judgements(runs) == []


def test_two_skipped_packs_in_one_run_count_that_run_once() -> None:
    skipped = (a_finding("compare.route.skipped.0", slug=""),
               a_finding("compare.route.skipped.1", slug=""))
    runs = [a_run(i, findings=skipped) for i in range(3)] + [a_run(3)]

    [finding] = repeated_judgements(runs)

    assert finding.id == "character.repeat.compare.route.skipped"
    assert finding.title == "The group pulled a pack fast runs skipped, in 3 of 4 runs"


def test_a_prefix_family_names_what_its_id_names() -> None:
    haste = a_finding("compare.stats.rating.haste.emberkin-0")
    runs = [a_run(i, findings=(haste,)) for i in range(3)]

    [finding] = repeated_judgements(runs)

    assert finding.id == "character.repeat.compare.stats.rating.haste"
    assert "haste" in finding.title


def test_the_count_wears_the_least_certain_badge_it_counts() -> None:
    runs = [a_run(0, findings=(a_finding("compare.talents.emberkin-0",
                                         confidence=Confidence.MEASURED),)),
            a_run(1, findings=(a_finding("compare.talents.emberkin-0",
                                         confidence=Confidence.DERIVED),)),
            a_run(2, findings=(a_finding("compare.talents.emberkin-0",
                                         confidence=Confidence.MEASURED),))]
    [finding] = repeated_judgements(runs)
    assert finding.confidence is Confidence.DERIVED


def test_the_analysis_families_are_not_counted_in_this_slice() -> None:
    analysis = (a_finding("defensives.ceiling.emberkin.48792", slug=""),
                a_finding("consumables.never.Emberkin", slug=""))
    runs = [a_run(i, findings=analysis) for i in range(4)]
    assert repeated_judgements(runs) == []
```

- [ ] **Step 3: Run to verify they fail** — `~/.local/bin/uv run pytest tests/domain/character -q`

- [ ] **Step 4: Implement**

Append to `model.py` (add the imports at its top):

```python
from wowperf.domain.comparison.measures import PlayerMeasures
from wowperf.domain.comparison.tempo import TempoMeasures
from wowperf.domain.findings import Finding


class CharacterRun(Frozen):
    """What one analysed run hands to the cross-run reading.

    `subject_slug` is the character's slug in that run's own findings, which is
    their roster index there and can differ from run to run. `measures` is None
    when the run drew no parse sample, `tempo` when the speed sample sat under
    the aggregate floor.
    """

    report_code: str
    fight_id: int
    dungeon: str
    keystone_level: int
    in_time: bool
    subject_slug: str
    subject_deaths: int = 0
    findings: tuple[Finding, ...] = ()
    measures: PlayerMeasures | None = None
    tempo: TempoMeasures | None = None


class FailedRun(Frozen):
    dungeon: str
    keystone_level: int
    report_code: str
    fight_id: int
    reason: str
```

`patterns.py`:

```python
# ABOUTME: What repeats across one character's runs: judgements made again and again, and
# ABOUTME: measures on one side of the top parses in every run. Counts, never sums.

import math
from collections import defaultdict
from collections.abc import Sequence
from typing import NamedTuple

from wowperf.domain.character.model import CharacterRun
from wowperf.domain.findings import Finding, least_certain, quantifier_for

REPEAT_MIN_RUNS = 3
"""The fewest runs a repeated judgement may rest on, however few runs loaded."""

REPEAT_RULE = (
    "Judged again and again: a judgement the per-run analysis made in at least half of the "
    f"runs that loaded, and in at least {REPEAT_MIN_RUNS}."
)

ANALYSIS_FAMILIES_NOT_COUNTED = (
    "Defensive, consumable and throughput-cooldown findings are not counted across runs: they "
    "do not name their player in a form the count can read."
)

COUNTED_NOT_SUMMED = (
    "Findings across runs are counted, never summed: seconds lost in different dungeons, at "
    "different keys and on different routes are not one quantity. Each count says how many runs "
    "it rests on, and each run's own figures are its own."
)

SUBJECT_FAMILIES = frozenset({
    "compare.spells.rate",
    "compare.spells.above",
    "compare.spells.missing",
    "compare.spells.trash.rate",
    "compare.spells.trash.above",
    "compare.talents",
    "compare.uptime.self",
    "compare.uptime.debuff",
    "compare.gear.tier",
    "compare.consumables.potion",
})
"""The subject's judgement families: each fires only when something stands out."""

SUBJECT_FAMILY_PREFIXES = (
    "compare.gear.enchant.",
    "compare.stats.rating.",
    "compare.consumables.buff.",
)
"""Judgement families whose id names what they judge after the prefix: a slot, a stat, a
category."""

RUN_FAMILIES = frozenset({"compare.route.skipped", "trash.overage"})
"""The run's own judgement families, which belong to nobody."""

_TITLES = {
    "compare.spells.rate": "Top parses cast {ability} more often than you on bosses",
    "compare.spells.above": "You cast {ability} more often than top parses on bosses",
    "compare.spells.trash.rate": "Top parses cast {ability} more often than you on trash",
    "compare.spells.trash.above": "You cast {ability} more often than top parses on trash",
    "compare.spells.missing": "Top parses cast {ability}; you never did",
    "compare.talents": "Your talent build differed from the top-ranked parse",
    "compare.uptime.self": "Top parses kept {ability} up longer than you",
    "compare.uptime.debuff": "Top parses' {ability} covered more of the enemies' lives than yours",
    "compare.gear.tier": "Your tier piece count differed from top parses'",
    "compare.consumables.potion": "You drank fewer combat potions than top parses",
    "compare.route.skipped": "The group pulled a pack fast runs skipped",
    "trash.overage": "The group killed more trash than the key required",
}

_PREFIX_TITLES = {
    "compare.gear.enchant.": "Top parses enchanted their {suffix}; you did not",
    "compare.stats.rating.": "Your {suffix} share of secondary rating differed from top parses'",
    "compare.consumables.buff.": "Top parses carried {suffix}; you did not",
}

REPEAT_DETAIL = (
    "Counted once for each run in which that run's own analysis made this judgement; a run "
    "that made it twice counts once. It is a count, not a sum: each run's figures are its own "
    "and are listed below."
)


def family_of(finding: Finding, subject_slug: str) -> str | None:
    """The finding's family when it is one this page counts, or None.

    The subject's slug and a trailing rank index are removed: `.emberkin-0` and
    `.emberkin-2` are one character in two runs, and `.0` and `.3` one family
    ranked differently.
    """
    family = finding.id
    if subject_slug and finding.player_slug == subject_slug:
        suffix = f".{subject_slug}"
        if family.endswith(suffix):
            family = family[: -len(suffix)]
        head, _, last = family.rpartition(".")
        if head and last.isdigit():
            family = head
        if family in SUBJECT_FAMILIES or family.startswith(SUBJECT_FAMILY_PREFIXES):
            return family
        return None
    if finding.player_slug == "":
        head, _, last = family.rpartition(".")
        if head and last.isdigit():
            family = head
        if family in RUN_FAMILIES:
            return family
    return None


class _Fired(NamedTuple):
    run: CharacterRun
    finding: Finding


def _title(family: str, ability: str) -> str:
    if family in _TITLES:
        return _TITLES[family].format(ability=ability)
    for prefix, template in _PREFIX_TITLES.items():
        if family.startswith(prefix):
            return template.format(suffix=family[len(prefix):].replace("-", " "))
    raise ValueError(f"no title for {family!r}")


def _repeat(family: str, ability_id: int | None, hits: list[_Fired], total: int) -> Finding:
    ability = hits[-1].finding.ability_name
    count = len(hits)
    return Finding(
        id=f"character.repeat.{family}" + (f".{ability_id}" if ability_id is not None else ""),
        title=f"{_title(family, ability)}, in {count} of {total} runs",
        detail=REPEAT_DETAIL,
        confidence=least_certain(hit.finding.confidence for hit in hits),
        evidence=tuple(
            f"{hit.run.dungeon} +{hit.run.keystone_level}: {hit.finding.title}" for hit in hits
        ),
        ability_id=ability_id if ability else None,
        ability_name=ability,
        quantifier=quantifier_for(count, total),
    )


def repeated_judgements(runs: Sequence[CharacterRun]) -> list[Finding]:
    total = len(runs)
    fired: dict[tuple[str, int | None], list[_Fired]] = defaultdict(list)
    for run in runs:
        seen: set[tuple[str, int | None]] = set()
        for finding in run.findings:
            family = family_of(finding, run.subject_slug)
            if family is None:
                continue
            key = (family, finding.ability_id)
            if key in seen:
                continue
            seen.add(key)
            fired[key].append(_Fired(run, finding))
    needed = max(REPEAT_MIN_RUNS, math.ceil(total / 2))
    found = [
        _repeat(family, ability_id, hits, total)
        for (family, ability_id), hits in fired.items()
        if len(hits) >= needed
    ]
    return sorted(found, key=lambda finding: (-len(finding.evidence), finding.id))
```

- [ ] **Step 5: Run tests, lint, types; commit**

```bash
git add src/wowperf/domain/character tests/domain/character
git commit -m "Count the judgements a character's runs made again and again" -m "A spell flagged in every run is a habit; flagged once it is noise. Families join across runs by id shape and ability, because a run's slug is its roster index and changes from run to run." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Consistent directions

**Files:**
- Modify: `src/wowperf/domain/character/patterns.py` (append)
- Test: `tests/domain/character/test_directions.py`

**Interfaces:**
- Produces: `MIN_DIRECTION_RUNS`, `DIRECTION_RATE_FLOOR`, `DIRECTION_SHARE_FLOOR`,
  `DIRECTION_RULE: str`, `DIRECTIONS_WITHHELD_ID = "character.direction.withheld"`,
  `consistent_directions(runs: Sequence[CharacterRun]) -> list[Finding]`

- [ ] **Step 1: Write the failing tests**

```python
# ABOUTME: Behaviour tests for measures that sat on one side of the top parses in every run.
# ABOUTME: Unanimity over six runs and a gap floor; a run counts only where it judged the row.

from tests.domain.character.builders import (
    a_buff,
    a_debuff,
    a_rate,
    a_run,
    a_stat,
    measures_of,
)
from wowperf.domain.character.patterns import DIRECTIONS_WITHHELD_ID, consistent_directions
from wowperf.domain.comparison.measures import Stretch, Verdict
from wowperf.domain.findings import Confidence

STRIKE = 433895
PLAGUE = 55078


def test_a_rate_below_the_median_in_six_runs_is_a_direction() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0, 9.0),))) for i in range(6)]

    [finding] = consistent_directions(runs)

    assert finding.id == f"character.direction.boss.{STRIKE}"
    assert finding.title == (
        "You cast Vampiric Strike less often than top parses on bosses, in every one of 6 runs")
    assert finding.quantifier == "every"
    assert finding.confidence is Confidence.DERIVED
    assert finding.ability_id == STRIKE
    assert finding.evidence[0] == "Altar of Fangs +18: 7.0 against 9.0 a minute"
    assert finding.evidence[-1] == "median gap 22%"


def test_five_judged_runs_are_not_enough() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0, 9.0),)) if i < 5
                  else measures_of()) for i in range(6)]
    assert consistent_directions(runs) == []


def test_one_dissent_breaks_it() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0 if i else 9.5, 9.0),)))
            for i in range(7)]
    assert consistent_directions(runs) == []


def test_one_tie_breaks_it() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0 if i else 9.0, 9.0),)))
            for i in range(7)]
    assert consistent_directions(runs) == []


def test_a_rate_gap_at_the_floor_counts_and_under_it_does_not() -> None:
    at = [a_run(i, measures=measures_of(trash=(a_rate(STRIKE, 9.0, 10.0,
                                                      stretch=Stretch.TRASH),))) for i in range(6)]
    under = [a_run(i, measures=measures_of(trash=(a_rate(STRIKE, 9.05, 10.0,
                                                         stretch=Stretch.TRASH),)))
             for i in range(6)]
    assert [f.id for f in consistent_directions(at)] == [f"character.direction.trash.{STRIKE}"]
    assert consistent_directions(under) == []


def test_a_share_gap_of_five_points_counts_and_four_does_not() -> None:
    at = [a_run(i, measures=measures_of(auras=(a_buff(461130, 0.50, 0.55),))) for i in range(6)]
    under = [a_run(i, measures=measures_of(auras=(a_buff(461130, 0.51, 0.55),)))
             for i in range(6)]
    [finding] = consistent_directions(at)
    assert finding.title == (
        "Visceral Strength was up less of the key for you than for top parses, "
        "in every one of 6 runs")
    assert finding.evidence[-1] == "median gap 5 points"
    assert consistent_directions(under) == []


def test_debuff_coverage_is_a_direction_of_its_own() -> None:
    runs = [a_run(i, measures=measures_of(debuffs=(a_debuff(PLAGUE, 0.60, 0.80),)))
            for i in range(6)]
    [finding] = consistent_directions(runs)
    assert finding.id == f"character.direction.debuff.{PLAGUE}"
    assert finding.title == (
        "Your Blood Plague covered less of the enemies' lives than top parses', "
        "in every one of 6 runs")


def test_a_stat_share_direction_names_the_stat() -> None:
    runs = [a_run(i, measures=measures_of(stats=(a_stat("haste", 0.38, 0.30),)))
            for i in range(6)]
    [finding] = consistent_directions(runs)
    assert finding.id == "character.direction.stat.haste"
    assert finding.title == (
        "Your haste share of secondary rating sat above top parses', in every one of 6 runs")
    assert finding.ability_id is None


def test_rows_a_run_declined_to_judge_never_count() -> None:
    unjudged = [a_run(i, measures=measures_of(
        auras=(a_buff(461130, 0.0, 0.55, verdict=Verdict.UNJUDGED),),
        debuffs=(a_debuff(PLAGUE, 0.1, 0.8, verdict=Verdict.BOSSES_ONLY),
                 a_debuff(1, 0.1, 0.8, shared_with=(701,), name="Mortal Wounds")),
    )) for i in range(6)]
    assert consistent_directions(unjudged) == []


def test_a_run_with_no_parse_sample_contributes_nothing() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0, 9.0),)) if i < 5 else None)
            for i in range(7)]
    assert consistent_directions(runs) == []


def test_fewer_than_six_loaded_runs_withholds_the_source_and_says_so() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0, 9.0),))) for i in range(5)]

    [finding] = consistent_directions(runs)

    assert finding.id == DIRECTIONS_WITHHELD_ID
    assert finding.confidence is Confidence.MEASURED
    assert finding.title == "Consistent directions are not stated: 5 runs loaded, 6 are needed"
```

- [ ] **Step 2: Run to verify they fail** — `~/.local/bin/uv run pytest tests/domain/character -q`

- [ ] **Step 3: Implement** (append to `patterns.py`; add
  `from wowperf.domain.comparison.measures import Verdict`,
  `from wowperf.domain.comparison.statistics import median`,
  `from wowperf.domain.findings import Confidence` to its imports)

```python
MIN_DIRECTION_RUNS = 6
DIRECTION_RATE_FLOOR = 0.10
DIRECTION_SHARE_FLOOR = 0.05

DIRECTION_RULE = (
    f"Every run, the same side: a measure judged in at least {MIN_DIRECTION_RUNS} runs, every "
    "one of them on the same side of the top parses' median, with a median gap of at least "
    f"{DIRECTION_RATE_FLOOR:.0%} for a cast rate or {DIRECTION_SHARE_FLOOR * 100:.0f} points for "
    "an uptime, a coverage or a stat share. A run counts only where its own comparison judged "
    "the row. These floors are chosen numbers, not measured ones, set well under the single-run "
    "thresholds on purpose: this reading exists to catch gaps no single run could call."
)

DIRECTIONS_WITHHELD_ID = "character.direction.withheld"

DIRECTION_DETAIL = (
    "Counted in each run whose own comparison judged this row; every one of them sat on the same "
    "side of that run's top parses. It states a difference, not a mistake, and a different build "
    "or a different job in the group can account for it."
)

_JUDGED = frozenset({Verdict.BELOW, Verdict.ABOVE, Verdict.LEVEL})
_RATE_KINDS = frozenset({"boss", "trash"})


class _Reading(NamedTuple):
    run: CharacterRun
    ours: float
    theirs: float


_Readings = dict[tuple[str, str], tuple[str, int | None, list[_Reading]]]
"""(kind, what it measures) -> (the name to print, the ability id or None, every judged reading)."""


def _readings(runs: Sequence[CharacterRun]) -> _Readings:
    """Every judged row of every run, keyed by kind and what it measures.

    The name printed is the first run's spelling of it.
    """
    found: _Readings = {}

    def add(kind: str, key: str, name: str, ability_id: int | None, run: CharacterRun,
            ours: float, theirs: float) -> None:
        _, _, readings = found.setdefault((kind, key), (name, ability_id, []))
        readings.append(_Reading(run, ours, theirs))

    for run in runs:
        measures = run.measures
        if measures is None:
            continue
        for kind, rates in (("boss", measures.boss), ("trash", measures.trash)):
            for rate in rates:
                if rate.verdict in _JUDGED:
                    add(kind, str(rate.ability_id), rate.name, rate.ability_id, run,
                        rate.ours, rate.their_median)
        for row in measures.auras:
            if row.uptime.verdict in _JUDGED:
                add("buff", str(row.uptime.ability_id), row.uptime.name, row.uptime.ability_id,
                    run, row.uptime.ours, row.uptime.their_median)
        for debuff in measures.debuffs.rows:
            if debuff.uptime.verdict in _JUDGED and not debuff.shared_with:
                add("debuff", str(debuff.uptime.ability_id), debuff.uptime.name,
                    debuff.uptime.ability_id, run, debuff.uptime.ours,
                    debuff.uptime.their_median)
        for stat in measures.stats:
            if stat.verdict in _JUDGED:
                add("stat", stat.name, stat.name, None, run, stat.ours, stat.their_median)
    return found


def _title_for(kind: str, name: str, below: bool, count: int) -> str:
    tail = f", in every one of {count} runs"
    if kind in _RATE_KINDS:
        where = "on bosses" if kind == "boss" else "on trash"
        return f"You cast {name} {'less' if below else 'more'} often than top parses {where}{tail}"
    if kind == "buff":
        return (f"{name} was up {'less' if below else 'more'} of the key for you than for top "
                f"parses{tail}")
    if kind == "debuff":
        return (f"Your {name} covered {'less' if below else 'more'} of the enemies' lives than "
                f"top parses'{tail}")
    return (f"Your {name} share of secondary rating sat {'below' if below else 'above'} top "
            f"parses'{tail}")


def _direction(kind: str, key: str, name: str, ability_id: int | None,
               readings: list[_Reading]) -> tuple[Finding, float] | None:
    below = all(one.ours < one.theirs for one in readings)
    above = all(one.ours > one.theirs for one in readings)
    if not (below or above):
        return None
    if kind in _RATE_KINDS:
        gaps = [abs(one.ours - one.theirs) / one.theirs if one.theirs > 0 else math.inf
                for one in readings]
        gap = median(gaps)
        if gap < DIRECTION_RATE_FLOOR:
            return None
        lines = [f"{one.run.dungeon} +{one.run.keystone_level}: {one.ours:.1f} against "
                 f"{one.theirs:.1f} a minute" for one in readings]
        lines.append(f"median gap {gap:.0%}")
    else:
        gap = median([abs(one.ours - one.theirs) for one in readings])
        if gap < DIRECTION_SHARE_FLOOR:
            return None
        lines = [f"{one.run.dungeon} +{one.run.keystone_level}: {one.ours:.0%} against "
                 f"{one.theirs:.0%}" for one in readings]
        lines.append(f"median gap {gap * 100:.0f} points")
    finding = Finding(
        id=f"character.direction.{kind}.{key}",
        title=_title_for(kind, name, below, len(readings)),
        detail=DIRECTION_DETAIL,
        confidence=Confidence.DERIVED,
        evidence=tuple(lines),
        ability_id=ability_id,
        ability_name=name if ability_id is not None else "",
        quantifier="every",
    )
    return finding, gap


def consistent_directions(runs: Sequence[CharacterRun]) -> list[Finding]:
    if len(runs) < MIN_DIRECTION_RUNS:
        return [
            Finding(
                id=DIRECTIONS_WITHHELD_ID,
                title=(f"Consistent directions are not stated: {len(runs)} runs loaded, "
                       f"{MIN_DIRECTION_RUNS} are needed"),
                detail=(
                    "Below this many runs, a measure lands on one side of the top parses in every "
                    "run by chance alone too often for the count to mean anything, so the bar is "
                    "kept and the reading withheld."
                ),
                confidence=Confidence.MEASURED,
            )
        ]
    found: list[tuple[Finding, float]] = []
    for (kind, key), (name, ability_id, readings) in _readings(runs).items():
        if len(readings) < MIN_DIRECTION_RUNS:
            continue
        direction = _direction(kind, key, name, ability_id, readings)
        if direction is not None:
            found.append(direction)
    found.sort(key=lambda pair: (-len(pair[0].evidence), -pair[1], pair[0].id))
    return [finding for finding, _ in found]
```

Note the gap check for rates: a direction is reported when the median relative gap is at least the
floor, so `9.0 against 10.0` (exactly 10%) is reported and `9.05 against 10.0` (9.5%) is not.

- [ ] **Step 4: Run tests, lint, types; commit**

```bash
git add src/wowperf/domain/character/patterns.py tests/domain/character/test_directions.py
git commit -m "State the measures that sat on one side of the top parses in every run" -m "Vampiric Strike and Death Strike sat below the sample in every run of a live character yet crossed no single run's threshold. Unanimity over six runs and a gap floor keep chance patterns rare, and a run counts only where its own comparison judged the row." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: The group ledger

**Files:**
- Create: `src/wowperf/domain/character/ledger.py`
- Test: `tests/domain/character/test_ledger.py`

**Interfaces:**
- Produces: `GroupColumn(above: int = 0, below: int = 0, level: int = 0, compared: int = 0)`,
  `GroupLedger(time: GroupColumn, deaths: GroupColumn, downtime: GroupColumn, kick_share: GroupColumn, subject_died_in: int)`,
  `group_ledger(runs: Sequence[CharacterRun]) -> GroupLedger`

- [ ] **Step 1: Write the failing tests**

```python
# ABOUTME: Behaviour tests for the group ledger: four comparisons every run carries, counted.
# ABOUTME: Counts sides of the fast runs' median and states no verdict; a withheld time stays out.

from tests.domain.character.builders import a_run
from wowperf.domain.character.ledger import GroupColumn, group_ledger
from wowperf.domain.comparison.tempo import TempoMeasures


def a_tempo(*, time: float = 1800.0, their_time: float | None = 1700.0, deaths: int = 2,
            downtime: float = 90.0, kick: float | None = 0.3) -> TempoMeasures:
    return TempoMeasures(members=5, our_time=time, their_time=their_time, our_deaths=deaths,
                         their_deaths=1.0, our_downtime=downtime, their_downtime=100.0,
                         our_kick_share=kick, their_kick_share=0.3)


def test_each_column_counts_the_runs_above_below_and_on_the_median() -> None:
    runs = [a_run(0, tempo=a_tempo()), a_run(1, tempo=a_tempo(time=1600.0, deaths=0)),
            a_run(2, tempo=a_tempo(downtime=100.0, kick=0.5))]

    ledger = group_ledger(runs)

    assert ledger.time == GroupColumn(above=2, below=1, level=0, compared=3)
    assert ledger.deaths == GroupColumn(above=2, below=1, level=0, compared=3)
    assert ledger.downtime == GroupColumn(above=0, below=2, level=1, compared=3)
    assert ledger.kick_share == GroupColumn(above=1, below=0, level=2, compared=3)


def test_a_withheld_time_and_a_missing_share_are_left_out_of_their_columns() -> None:
    runs = [a_run(0, tempo=a_tempo(their_time=None, kick=None)), a_run(1, tempo=a_tempo())]

    ledger = group_ledger(runs)

    assert ledger.time.compared == 1
    assert ledger.kick_share.compared == 1


def test_a_run_below_the_speed_floor_is_in_no_column() -> None:
    ledger = group_ledger([a_run(0), a_run(1, tempo=a_tempo())])
    assert ledger.deaths.compared == 1


def test_the_characters_own_deaths_are_counted_by_run() -> None:
    ledger = group_ledger([a_run(0, subject_deaths=2), a_run(1), a_run(2, subject_deaths=1)])
    assert ledger.subject_died_in == 2
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

```python
# ABOUTME: The group ledger: completion time, deaths, downtime and kick share, run by run, counted.
# ABOUTME: These appear in every run whatever happened, so they are counted and never judged.

from collections.abc import Iterable, Sequence

from wowperf.domain.base import Frozen
from wowperf.domain.character.model import CharacterRun


class GroupColumn(Frozen):
    """How many runs sat above, below or on the fast runs' median for one comparison."""

    above: int = 0
    below: int = 0
    level: int = 0
    compared: int = 0


class GroupLedger(Frozen):
    time: GroupColumn
    deaths: GroupColumn
    downtime: GroupColumn
    kick_share: GroupColumn
    subject_died_in: int


def _count(pairs: Iterable[tuple[float, float]]) -> GroupColumn:
    above = below = level = 0
    for ours, theirs in pairs:
        if ours > theirs:
            above += 1
        elif ours < theirs:
            below += 1
        else:
            level += 1
    return GroupColumn(above=above, below=below, level=level, compared=above + below + level)


def group_ledger(runs: Sequence[CharacterRun]) -> GroupLedger:
    tempos = [run.tempo for run in runs if run.tempo is not None]
    return GroupLedger(
        time=_count((t.our_time, t.their_time) for t in tempos if t.their_time is not None),
        deaths=_count((float(t.our_deaths), t.their_deaths) for t in tempos),
        downtime=_count((t.our_downtime, t.their_downtime) for t in tempos),
        kick_share=_count(
            (t.our_kick_share, t.their_kick_share) for t in tempos if t.our_kick_share is not None
        ),
        subject_died_in=sum(1 for run in runs if run.subject_deaths > 0),
    )
```

If mypy does not narrow `t.their_time` / `t.our_kick_share` inside the generator, bind them first:
`((t.our_time, their) for t in tempos if (their := t.their_time) is not None)`.

- [ ] **Step 4: Run tests, lint, types; commit**

```bash
git add src/wowperf/domain/character/ledger.py tests/domain/character/test_ledger.py
git commit -m "Count the group comparisons run by run without judging them" -m "Completion time, deaths, downtime and kick share appear in every run whatever happened, so firing in N runs means nothing. A ledger states where each run sat against its fast runs and how often, and nothing more." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: The character page's view model and builder

**Files:**
- Modify: `src/wowperf/domain/character/model.py` (append `CharacterSubject`)
- Create: `src/wowperf/domain/report/character_model.py`, `src/wowperf/domain/report/character_build.py`
- Test: `tests/domain/report/test_character_build.py`

**Interfaces:**
- Consumes: `ledger_row` (`wowperf.domain.report.ledger`), `LedgerRow`, `quantity`, everything
  from Tasks 7-10.
- Produces:
  - model: `CharacterSubject(name: str, realm: str, region: str, zone_name: str)`
  - `character_model`: `CharacterHeader`, `GroupRow`, `RunRow`, `CharacterProvenance`,
    `CharacterReport`, `all_character_ledger_rows(report: CharacterReport) -> Iterator[LedgerRow]`
  - `character_build.build_character_report(subject: CharacterSubject, selection: Selection, runs: Sequence[CharacterRun], failed: Sequence[FailedRun], findings: Sequence[Finding], ledger: GroupLedger, narrative: str | None, fetched_at: str) -> CharacterReport`
  - `character_build.run_file(report_code: str, fight_id: int) -> str` (`"<code>-<fight>.html"`)

- [ ] **Step 1: Write the failing tests** (`tests/domain/report/test_character_build.py`)

```python
# ABOUTME: Behaviour tests for the character page's builder: which row goes where, and the strings.
# ABOUTME: The template loops; every word and figure on the page is decided here.

from collections.abc import Sequence

from tests.domain.character.builders import a_finding, a_run
from tests.domain.character.test_ledger import a_tempo
from wowperf.domain.character.ledger import group_ledger
from wowperf.domain.character.model import (
    CharacterSubject,
    FailedRun,
    LeftOut,
    Selection,
)
from wowperf.domain.character.patterns import COUNTED_NOT_SUMMED, DIRECTION_RULE, REPEAT_RULE
from wowperf.domain.character.selection import SELECTION_RULE
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.report.character_build import build_character_report, run_file
from wowperf.domain.report.character_model import CharacterReport

SUBJECT = CharacterSubject(name="Emberkin", realm="argent-dawn", region="eu",
                           zone_name="Mythic+ Season 2")
NARRATIVE = "Your losses are route, not rotation."
FINDINGS = (
    a_finding("character.direction.boss.433895", slug="", title="Direction title"),
    a_finding("character.repeat.compare.talents", slug="", title="Repeat title"),
    a_finding("character.direction.withheld", slug="", title="Withheld title",
              confidence=Confidence.MEASURED),
)


def a_report(*, findings: Sequence[Finding] = FINDINGS,
             narrative: str | None = NARRATIVE) -> CharacterReport:
    """Two runs read (one timed with a ledger, one not), one failed, one dungeon left out."""
    runs = [a_run(0, tempo=a_tempo()), a_run(1, in_time=False, subject_deaths=1)]
    return build_character_report(
        SUBJECT,
        Selection(spec="Blood",
                  left_out=(LeftOut(dungeon="Murder Row", reason="no ranked run as Blood"),)),
        runs,
        [FailedRun(dungeon="Kings' Rest", keystone_level=18, report_code="zzz999", fight_id=3,
                   reason="Report zzz999 was not found")],
        findings,
        group_ledger(runs),
        narrative,
        "2026-10-14 09:30",
    )


def test_each_finding_lands_in_its_own_section() -> None:
    report = a_report()
    assert [row.finding_id for row in report.direction_rows] == ["character.direction.boss.433895"]
    assert [row.finding_id for row in report.repeat_rows] == ["character.repeat.compare.talents"]
    assert [row.finding_id for row in report.other_rows] == ["character.direction.withheld"]


def test_the_header_names_the_character_zone_and_spec() -> None:
    header = a_report().header
    assert header.name == "Emberkin"
    assert header.realm_line == "argent-dawn (EU)"
    assert header.spec == "Blood"
    assert header.read_line == "2 runs read, 1 failed to load, 1 dungeon left out"


def test_a_run_row_links_its_own_report_file() -> None:
    [first, second] = a_report().runs
    assert first.report_file == run_file("code000x", 1) == "code000x-1.html"
    assert first.outcome == "timed"
    assert second.outcome == "not timed"


def test_the_group_rows_state_ours_against_the_median() -> None:
    [first, second] = a_report().group_rows
    assert first.time == "1800s against 1700s"
    assert first.deaths == "2 against 1"
    assert first.downtime == "90s against 100s"
    assert first.kick_share == "30% against 30%"
    assert second.time == "too few fast runs"
    assert second.your_deaths == "1"


def test_the_group_counts_state_sides_and_never_a_verdict() -> None:
    counts = a_report().group_counts
    assert counts[0] == "1 above, 0 below the median, of 1 compared"
    assert counts[-1] == "you died in 1 of 2 runs"


def test_failed_runs_and_left_out_dungeons_are_named_with_their_reasons() -> None:
    report = a_report()
    assert report.failed == ("Kings' Rest +18 (report zzz999, fight 3): Report zzz999 was not found",)
    assert report.left_out == ("Murder Row: no ranked run as Blood",)


def test_the_provenance_states_every_rule_and_the_warning() -> None:
    provenance = a_report().provenance
    assert provenance.warning == COUNTED_NOT_SUMMED
    for rule in (SELECTION_RULE, REPEAT_RULE, DIRECTION_RULE):
        assert rule in provenance.methods


def test_the_narrative_is_carried_as_given() -> None:
    assert a_report().narrative == "Your losses are route, not rotation."
    assert a_report(narrative=None).narrative is None
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

Append to `domain/character/model.py`:

```python
class CharacterSubject(Frozen):
    """Who the page is about, as the command was asked."""

    name: str
    realm: str
    region: str
    zone_name: str
```

`src/wowperf/domain/report/character_model.py`:

```python
# ABOUTME: The character report's view model: every judgement its four-tab page makes.
# ABOUTME: Reuses LedgerRow whole; run reports are linked by file name, never fetched.

from collections.abc import Iterator

from wowperf.domain.base import Frozen
from wowperf.domain.report.model import LedgerRow


class CharacterHeader(Frozen):
    name: str
    realm_line: str
    zone: str
    spec: str
    read_line: str


class RunRow(Frozen):
    dungeon: str
    level: str
    outcome: str
    report_file: str


class GroupRow(Frozen):
    label: str
    report_file: str
    time: str
    deaths: str
    downtime: str
    kick_share: str
    your_deaths: str


class CharacterProvenance(Frozen):
    read_line: str
    fetched_at: str
    warning: str
    methods: tuple[str, ...] = ()


class CharacterReport(Frozen):
    header: CharacterHeader
    narrative: str | None
    direction_rows: tuple[LedgerRow, ...] = ()
    repeat_rows: tuple[LedgerRow, ...] = ()
    # Every finding neither list above claimed -- the withheld directions today --
    # so a new family can never vanish from the page.
    other_rows: tuple[LedgerRow, ...] = ()
    group_rows: tuple[GroupRow, ...] = ()
    group_counts: tuple[str, ...] = ()
    runs: tuple[RunRow, ...] = ()
    failed: tuple[str, ...] = ()
    left_out: tuple[str, ...] = ()
    provenance: CharacterProvenance


def all_character_ledger_rows(report: CharacterReport) -> Iterator[LedgerRow]:
    """Every finding row on the character page, in the order the page draws them."""
    yield from report.direction_rows
    yield from report.repeat_rows
    yield from report.other_rows
```

`src/wowperf/domain/report/character_build.py`:

```python
# ABOUTME: Builds the character page's view model: sections, run links, ledger strings, provenance.
# ABOUTME: Pure: the CLI hands it the runs and findings, and it decides every word the page prints.

from collections.abc import Sequence

from wowperf.domain.character.ledger import GroupColumn, GroupLedger
from wowperf.domain.character.model import (
    CharacterRun,
    CharacterSubject,
    FailedRun,
    Selection,
)
from wowperf.domain.character.patterns import (
    ANALYSIS_FAMILIES_NOT_COUNTED,
    COUNTED_NOT_SUMMED,
    DIRECTION_RULE,
    REPEAT_RULE,
)
from wowperf.domain.character.selection import SELECTION_RULE
from wowperf.domain.comparison.tempo import TempoMeasures
from wowperf.domain.findings import Finding, quantity
from wowperf.domain.report.character_model import (
    CharacterHeader,
    CharacterProvenance,
    CharacterReport,
    GroupRow,
    RunRow,
)
from wowperf.domain.report.ledger import ledger_row


def run_file(report_code: str, fight_id: int) -> str:
    """The run report's file name, beside the character page in the same directory."""
    return f"{report_code}-{fight_id}.html"


def _figure(value: float) -> str:
    """A median that may be a half: `1`, `0.5`, never `1.0`."""
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _group_row(run: CharacterRun) -> GroupRow:
    tempo: TempoMeasures | None = run.tempo
    label = f"{run.dungeon} +{run.keystone_level}"
    file = run_file(run.report_code, run.fight_id)
    if tempo is None:
        missing = "too few fast runs"
        return GroupRow(label=label, report_file=file, time=missing, deaths=missing,
                        downtime=missing, kick_share=missing, your_deaths=str(run.subject_deaths))
    time = (
        f"{tempo.our_time:.0f}s; not compared at this level"
        if tempo.their_time is None
        else f"{tempo.our_time:.0f}s against {tempo.their_time:.0f}s"
    )
    kick = (
        f"none resolved, against {tempo.their_kick_share:.0%}"
        if tempo.our_kick_share is None
        else f"{tempo.our_kick_share:.0%} against {tempo.their_kick_share:.0%}"
    )
    return GroupRow(
        label=label,
        report_file=file,
        time=time,
        deaths=f"{tempo.our_deaths} against {_figure(tempo.their_deaths)}",
        downtime=f"{tempo.our_downtime:.0f}s against {tempo.their_downtime:.0f}s",
        kick_share=kick,
        your_deaths=str(run.subject_deaths),
    )


def _count(column: GroupColumn) -> str:
    if column.compared == 0:
        return "not compared"
    return f"{column.above} above, {column.below} below the median, of {column.compared} compared"


def build_character_report(
    subject: CharacterSubject,
    selection: Selection,
    runs: Sequence[CharacterRun],
    failed: Sequence[FailedRun],
    findings: Sequence[Finding],
    ledger: GroupLedger,
    narrative: str | None,
    fetched_at: str,
) -> CharacterReport:
    titles = {finding.id: finding.title for finding in findings}
    rows = [(finding.id, ledger_row(finding, titles)) for finding in findings]
    read_line = (
        f"{quantity(len(runs), 'run', 'runs')} read, {len(failed)} failed to load, "
        f"{quantity(len(selection.left_out), 'dungeon', 'dungeons')} left out"
    )
    return CharacterReport(
        header=CharacterHeader(
            name=subject.name,
            realm_line=f"{subject.realm} ({subject.region.upper()})",
            zone=subject.zone_name,
            spec=selection.spec,
            read_line=read_line,
        ),
        narrative=narrative,
        direction_rows=tuple(
            row for finding_id, row in rows
            if finding_id.startswith("character.direction.")
            and finding_id != "character.direction.withheld"
        ),
        repeat_rows=tuple(
            row for finding_id, row in rows if finding_id.startswith("character.repeat.")
        ),
        other_rows=tuple(
            row for finding_id, row in rows
            if not finding_id.startswith("character.repeat.")
            and (not finding_id.startswith("character.direction.")
                 or finding_id == "character.direction.withheld")
        ),
        group_rows=tuple(_group_row(run) for run in runs),
        group_counts=(
            _count(ledger.time),
            _count(ledger.deaths),
            _count(ledger.downtime),
            _count(ledger.kick_share),
            f"you died in {ledger.subject_died_in} of {quantity(len(runs), 'run', 'runs')}",
        ),
        runs=tuple(
            RunRow(
                dungeon=run.dungeon,
                level=f"+{run.keystone_level}",
                outcome="timed" if run.in_time else "not timed",
                report_file=run_file(run.report_code, run.fight_id),
            )
            for run in runs
        ),
        failed=tuple(
            f"{one.dungeon} +{one.keystone_level} (report {one.report_code}, fight "
            f"{one.fight_id}): {one.reason}"
            for one in failed
        ),
        left_out=tuple(f"{one.dungeon}: {one.reason}" for one in selection.left_out),
        provenance=CharacterProvenance(
            read_line=read_line,
            fetched_at=fetched_at,
            warning=COUNTED_NOT_SUMMED,
            methods=(SELECTION_RULE, REPEAT_RULE, DIRECTION_RULE, ANALYSIS_FAMILIES_NOT_COUNTED),
        ),
    )
```

(`quantity(n, singular, plural)` returns the count and the noun together, e.g. `"2 runs"`.)

- [ ] **Step 4: Run tests, lint, types; commit**

```bash
git add src/wowperf/domain/character/model.py src/wowperf/domain/report/character_model.py src/wowperf/domain/report/character_build.py tests/domain/report/test_character_build.py
git commit -m "Build the character page's view model" -m "Every word and figure the page prints is decided here, so the template only loops. Run reports are linked by file name, and the ledger states sides and counts, never a verdict." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Render the character page

**Files:**
- Create: `src/wowperf/adapters/render/character.html.j2`
- Modify: `src/wowperf/adapters/render/html.py`
- Test: `tests/adapters/render/test_character_html_invariants.py`

**Interfaces:**
- Produces: `CHARACTER_TEMPLATE_NAME = "character.html.j2"`,
  `render_character(report: CharacterReport, icons: CdnIcons | None = None) -> str`

- [ ] **Step 1: Write the failing invariant tests**

```python
# ABOUTME: Whole-page rules for the character report: four panels, one script, scoped links.
# ABOUTME: A run report beside the page is the one new link kind, and nothing else new is admitted.

import re

from tests.adapters.render.test_html_invariants import FORBIDDEN_IN_SCRIPT, ICON_HOST
from tests.domain.character.builders import a_finding
from tests.domain.report.test_character_build import a_report
from wowperf.adapters.render.html import render_character
from wowperf.adapters.render.icons import CdnIcons

CHARACTER_PANEL_ORDER = ["tab-summary", "tab-group", "tab-runs", "tab-provenance"]
PANEL_ID = re.compile(r'<section class="panel"[^>]*\sid="([^"]+)"')
MAIN_NAV = re.compile(r'<nav class="tabs" data-tab-group="main"[^>]*>(.*?)</nav>', re.DOTALL)
TAB_TARGET = re.compile(r'data-tab-for="([^"]+)"')
RUN_FILE = re.compile(r"^[A-Za-z0-9]+-\d+\.html$")
ICON_ABILITY_ID = 433895


def a_page(icons: CdnIcons | None = None) -> str:
    return render_character(a_report(), icons)


def test_every_panel_appears_once_in_tab_order() -> None:
    html = a_page()
    assert PANEL_ID.findall(html) == CHARACTER_PANEL_ORDER
    assert html.count('<section class="panel"') == len(CHARACTER_PANEL_ORDER)


def test_the_tab_buttons_follow_panel_order() -> None:
    nav = MAIN_NAV.search(a_page())
    assert nav is not None
    assert TAB_TARGET.findall(nav.group(1)) == CHARACTER_PANEL_ORDER


def test_the_page_makes_no_request_but_its_icons() -> None:
    html = a_page()
    assert "<link" not in html.lower()
    assert "@import" not in html.lower()
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, flags=re.S | re.I)
    assert len(scripts) == 1
    attributes, body = scripts[0]
    assert "src=" not in attributes.lower()
    for forbidden in FORBIDDEN_IN_SCRIPT:
        assert forbidden not in body, forbidden


def test_every_finding_appears_exactly_once() -> None:
    ids = re.findall(r'id="finding-([^"]+)"', a_page())
    for finding_id in ("character.direction.boss.433895", "character.repeat.compare.talents",
                       "character.direction.withheld"):
        assert ids.count(finding_id) == 1, finding_id


def test_every_href_is_a_fragment_the_icon_host_or_a_run_report_beside_the_page() -> None:
    html = a_page(CdnIcons({ICON_ABILITY_ID: "spell_deathknight_bloodboil.jpg"}))
    hrefs = re.findall(r'href="([^"]*)"', html)
    assert any(RUN_FILE.match(href) for href in hrefs), "no run report was linked"
    for href in hrefs:
        assert href.startswith("#") or href.startswith(ICON_HOST) or RUN_FILE.match(href), href


def test_the_page_links_no_report_on_warcraft_logs() -> None:
    assert "warcraftlogs.com/reports/" not in a_page()


def test_the_narrative_and_the_warning_are_on_the_page() -> None:
    html = a_page()
    assert "Your losses are route, not rotation." in html
    assert "counted, never summed" in html


def test_a_title_containing_markup_is_escaped() -> None:
    report = a_report(findings=[a_finding("character.repeat.compare.talents", slug="",
                                          title="<b>bold</b>")])
    html = render_character(report)
    assert "<b>bold</b>" not in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html
```

- [ ] **Step 2: Run to verify they fail** — ImportError on `render_character`.

- [ ] **Step 3: Write the template** (`src/wowperf/adapters/render/character.html.j2`)

```jinja
{# ABOUTME: Document skeleton for the character report: a header, four tab panels, and one #}
{# ABOUTME: inline script that only shows and hides -- one self-contained file. #}
{% from "_macros.html.j2" import ledger_row with context %}
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ report.header.name }} &middot; {{ report.header.zone }}</title>
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

<h1>{{ report.header.name }}</h1>
<p class="sub">{{ report.header.realm_line }} &middot; {{ report.header.zone }} &middot; {{ report.header.spec }} &middot; {{ report.header.read_line }}</p>

<nav class="tabs" data-tab-group="main" aria-label="Sections">
  <button type="button" class="tab" data-tab-for="tab-summary">Summary</button>
  <button type="button" class="tab" data-tab-for="tab-group">Group</button>
  <button type="button" class="tab" data-tab-for="tab-runs">Runs</button>
  <button type="button" class="tab" data-tab-for="tab-provenance">Provenance</button>
</nav>

<section class="panel" data-tab-panel="main" id="tab-summary">
{% if report.narrative %}
<h2 id="narrative">What these runs say</h2>
<div class="narrative">{{ report.narrative }}</div>
{% endif %}
<h2 id="directions">Every run, the same side</h2>
{% if report.direction_rows %}
<div class="findings">
{% for row in report.direction_rows %}
{{ ledger_row(row) }}
{% endfor %}
</div>
{% else %}
<p class="sub">No measure sat on the same side of the top parses in every run.</p>
{% endif %}
<h2 id="repeats">Judged again and again</h2>
{% if report.repeat_rows %}
<div class="findings">
{% for row in report.repeat_rows %}
{{ ledger_row(row) }}
{% endfor %}
</div>
{% else %}
<p class="sub">No judgement repeated in enough runs to count.</p>
{% endif %}
{% if report.other_rows %}
<h2 id="other">Other findings</h2>
<div class="findings">
{% for row in report.other_rows %}
{{ ledger_row(row) }}
{% endfor %}
</div>
{% endif %}
</section>

<section class="panel" data-tab-panel="main" id="tab-group">
<h2 id="group">The group, run by run</h2>
<p class="sub">Each cell is ours against the median of that run's fast runs. These appear in every run whatever happened, so they are counted and never judged.</p>
<table class="attempts">
<thead>
<tr><th>Run</th><th>Completion time</th><th>Deaths</th><th>Time between packs</th><th>Kick share</th><th>Your deaths</th></tr>
</thead>
<tbody>
{% for row in report.group_rows %}
<tr><td><a href="{{ row.report_file }}">{{ row.label }}</a></td><td>{{ row.time }}</td><td>{{ row.deaths }}</td><td>{{ row.downtime }}</td><td>{{ row.kick_share }}</td><td>{{ row.your_deaths }}</td></tr>
{% endfor %}
</tbody>
<tfoot>
<tr><th>Count</th>{% for cell in report.group_counts %}<td>{{ cell }}</td>{% endfor %}</tr>
</tfoot>
</table>
</section>

<section class="panel" data-tab-panel="main" id="tab-runs">
<h2 id="runs">Runs read</h2>
<table class="attempts">
<thead>
<tr><th>Dungeon</th><th>Key</th><th>Outcome</th><th>Report</th></tr>
</thead>
<tbody>
{% for row in report.runs %}
<tr><td>{{ row.dungeon }}</td><td>{{ row.level }}</td><td>{{ row.outcome }}</td><td><a href="{{ row.report_file }}">{{ row.report_file }}</a></td></tr>
{% endfor %}
</tbody>
</table>
{% if report.failed %}
<h2 id="failed">Runs that did not load</h2>
<ul class="evidence">{% for line in report.failed %}<li>{{ line }}</li>{% endfor %}</ul>
{% endif %}
{% if report.left_out %}
<h2 id="left-out">Dungeons left out</h2>
<ul class="evidence">{% for line in report.left_out %}<li>{{ line }}</li>{% endfor %}</ul>
{% endif %}
</section>

<section class="panel" data-tab-panel="main" id="tab-provenance">
<h2 id="provenance">Provenance</h2>
<p class="sub">{{ report.provenance.read_line }}, fetched {{ report.provenance.fetched_at }}.</p>
<p class="sub">{{ report.provenance.warning }}</p>
{% for line in report.provenance.methods %}
<p class="sub">{{ line }}</p>
{% endfor %}
<p class="legend">
<span class="badge badge-measured">measured</span> read from the log, or arithmetic over logged facts.
<span class="badge badge-derived">derived</span> reconstructed by a documented rule, or a modelling choice that could be wrong.
<span class="badge badge-inferred">inferred</span> requires an assumption the log cannot confirm.
</p>
</section>

</main>
<script>
{% include "report.js.j2" %}
</script>
</body>
</html>
```

- [ ] **Step 4: Add the renderer** (in `html.py`: import `CharacterReport` and
  `all_character_ledger_rows` from `wowperf.domain.report.character_model`, add
  `CHARACTER_TEMPLATE_NAME = "character.html.j2"` beside the other names, and append)

```python
def render_character(report: CharacterReport, icons: CdnIcons | None = None) -> str:
    """The character page: four tabs over cross-run findings, a ledger and run links.

    Only a ledger row can name an ability here, so the icon walk is that single
    loop, as `render_progression` does it.
    """
    addresses: dict[int, str] = {}
    if icons is not None:
        for row in all_character_ledger_rows(report):
            if row.ability_id is None or row.ability_id in addresses:
                continue
            address = icons.url(row.ability_id)
            if address is not None:
                addresses[row.ability_id] = address
    return _environment().get_template(CHARACTER_TEMPLATE_NAME).render(
        report=report, icons_by_id=addresses
    )
```

- [ ] **Step 5: Run the tests, then the whole render suite**

Run: `~/.local/bin/uv run pytest tests/adapters/render -q` — Expected: all pass.

- [ ] **Step 6: Lint, types; commit**

```bash
git add src/wowperf/adapters/render/character.html.j2 src/wowperf/adapters/render/html.py tests/adapters/render/test_character_html_invariants.py
git commit -m "Render the character page" -m "Four tabs over what repeats, the group ledger, the runs and provenance, in one self-contained file. The run reports beside it are the one new link kind, and the invariant test admits nothing else new." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: The `character` command

**Files:**
- Modify: `src/wowperf/cli.py`
- Test: `tests/test_cli_character.py`

**Interfaces:**
- Consumes: Tasks 2-12.
- Produces: `icon_names(loaded, parse_samples, our_auras) -> dict[int, str]` in `cli.py`
  (`build_icons` now wraps it), and
  `wowperf character <url> [--zone ID] [--spec NAME] [--narrative FILE] [--cache-dir DIR] [--out DIR]`
  writing `<out>/<region>-<realm-slug>-<name-slug>/character.json` and `character.html`, plus every
  loaded run's `<code>-<fight>.findings.json` and `.html` in the same directory.

- [ ] **Step 1: Write the failing tests** (`tests/test_cli_character.py`)

```python
# ABOUTME: Command-level tests for `character`, over the analyze mock transport plus two queries.
# ABOUTME: Six runs load, one fails to load, one dungeon is left out, and every file lands together.

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from tests.test_cli import build_analyze_transport, operation_name, plain
from wowperf.adapters.wcl.client import RateLimitExceeded
from wowperf.cli import app
from wowperf.domain.character.patterns import COUNTED_NOT_SUMMED

URL = "https://www.warcraftlogs.com/character/eu/argent-dawn/Emberkin?zone=55"
DIRECTORY = "eu-argent-dawn-emberkin"
DUNGEON_IDS = range(101, 109)


def a_rank(code: str, fight: int | None, level: int = 16, start: int = 1) -> dict[str, Any]:
    return {"report": {"code": code, "fightID": fight, "startTime": start},
            "bracketData": level, "spec": "Protection", "startTime": start,
            "duration": 1_700_000, "medal": "bronze"}


def build_character_transport(*, difficulties: tuple[int, ...] = (10,),
                              hidden: bool = False) -> httpx.MockTransport:
    inner = build_analyze_transport()
    ranks: dict[int, list[dict[str, Any]]] = {
        **{encounter: [a_rank("abc123", 36)] for encounter in range(101, 107)},
        107: [a_rank("zzz999", 1)],
        108: [a_rank("", None)],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/oauth/token":
            name = operation_name(json.loads(request.content)["query"])
            if name == "Zone":
                return httpx.Response(200, json={"data": {"worldData": {"zone": {
                    "id": 55, "name": "Mythic+ Season 2",
                    "difficulties": [{"id": one, "name": "x"} for one in difficulties],
                    "encounters": [{"id": one, "name": f"Dungeon {one}"} for one in DUNGEON_IDS],
                }}}})
            if name == "CharacterRuns":
                character: dict[str, Any] = {"id": 1, "hidden": hidden}
                character.update({f"e{one}": {"ranks": ranks[one]} for one in DUNGEON_IDS})
                return httpx.Response(200, json={"data": {"characterData": {"character": character}}})
        # `handle_request` is the transport's typed entry point; `.handler` is typed as
        # either a sync or an async handler, which strict mypy will not return as a Response.
        return inner.handle_request(request)

    return httpx.MockTransport(handler)


def invoke(tmp_path: Path, *args: str, transport: httpx.MockTransport | None = None) -> Any:
    chosen = transport or build_character_transport()
    real_client = httpx.Client

    def fake_client(*_: Any, **__: Any) -> httpx.Client:
        return real_client(transport=chosen)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "Client", fake_client)
        mp.setenv("WCL_CLIENT_ID", "id")
        mp.setenv("WCL_CLIENT_SECRET", "secret")
        return CliRunner().invoke(app, ["character", *args,
                                        "--cache-dir", str(tmp_path / "cache"),
                                        "--out", str(tmp_path / "out")])


def test_character_writes_its_page_and_every_run_beside_it(tmp_path: Path) -> None:
    result = invoke(tmp_path, URL)

    assert result.exit_code == 0, result.output
    directory = tmp_path / "out" / DIRECTORY
    for name in ("character.json", "character.html", "abc123-36.findings.json", "abc123-36.html"):
        assert (directory / name).is_file(), name
    assert 'href="abc123-36.html"' in (directory / "character.html").read_text(encoding="utf-8")


def test_the_character_file_names_what_loaded_failed_and_was_left_out(tmp_path: Path) -> None:
    invoke(tmp_path, URL)
    payload = json.loads((tmp_path / "out" / DIRECTORY / "character.json").read_text(
        encoding="utf-8"))

    assert payload["character"]["name"] == "Emberkin"
    assert payload["character"]["spec"] == "Protection"
    assert len(payload["runs"]) == 6
    assert [one["dungeon"] for one in payload["failed"]] == ["Dungeon 107"]
    assert [one["dungeon"] for one in payload["left_out"]] == ["Dungeon 108"]
    assert payload["findings_are_counted_not_summed"] == COUNTED_NOT_SUMMED
    ids = [finding["id"] for finding in payload["findings"]]
    assert len(ids) == len(set(ids))
    assert all(finding["confidence"] in {"measured", "derived", "inferred"}
               for finding in payload["findings"])


def test_no_zone_stops_before_any_request(tmp_path: Path) -> None:
    result = invoke(tmp_path, URL.split("?")[0])
    assert result.exit_code == 1
    assert "zone" in plain(result.output + result.stderr).lower()


def test_a_raid_zone_is_refused(tmp_path: Path) -> None:
    result = invoke(tmp_path, URL, transport=build_character_transport(difficulties=(3, 4, 5)))
    assert result.exit_code == 1
    assert "not a Mythic+ zone" in result.stderr


def test_hidden_rankings_are_refused(tmp_path: Path) -> None:
    result = invoke(tmp_path, URL, transport=build_character_transport(hidden=True))
    assert result.exit_code == 1
    assert "hidden" in result.stderr


def test_an_unknown_spec_names_the_ones_the_character_has(tmp_path: Path) -> None:
    result = invoke(tmp_path, URL, "--spec", "Frost")
    assert result.exit_code == 1
    assert "ranked as: Protection" in result.stderr


def test_a_spent_budget_stops_the_command_rather_than_shrinking_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def spent(*_: Any, **__: Any) -> Any:
        raise RateLimitExceeded("The hourly point budget is spent")

    monkeypatch.setattr("wowperf.cli.analyse_run", spent)
    result = invoke(tmp_path, URL)
    assert result.exit_code == 1
    assert "budget is spent" in result.stderr


def test_the_character_flags_are_offered_and_the_run_flags_are_not() -> None:
    options = plain(CliRunner().invoke(app, ["character", "--help"]).output).partition("Options")[2]
    for flag in ("--zone", "--spec", "--narrative", "--cache-dir", "--out"):
        assert flag in options, flag
    for flag in ("--player", "--all-players", "--no-compare", "--fight", "--throughput-ceiling"):
        assert flag not in options, flag
```

- [ ] **Step 2: Run to verify they fail** — `No such command 'character'`.

- [ ] **Step 3: Implement the command**

Imports to add to `cli.py`:

```python
from wowperf.adapters.wcl.character_repository import WclCharacterRepository
from wowperf.adapters.render.html import render_character  # extend the existing import line
from wowperf.domain.character.ledger import group_ledger
from wowperf.domain.character.model import CharacterRun, CharacterSubject, FailedRun
from wowperf.domain.character.patterns import (
    COUNTED_NOT_SUMMED,
    DIRECTION_RATE_FLOOR,
    DIRECTION_SHARE_FLOOR,
    MIN_DIRECTION_RUNS,
    REPEAT_MIN_RUNS,
    consistent_directions,
    repeated_judgements,
)
from wowperf.domain.character.selection import require_mythic_plus, select_runs
from wowperf.domain.comparison.tempo import tempo_measures
from wowperf.domain.report.character_build import build_character_report, run_file
from wowperf.domain.slug import player_slug
from wowperf.urls import parse_character_url  # extend the existing import line
```

Split `build_icons` so the character page can merge every run's icon names (`CdnIcons` keeps its
mapping private, and a character finding names an ability whose art only a run's dictionary
holds). Rename the body to `icon_names` and keep `build_icons` as the one-line wrapper every
existing caller already uses; the pin from Task 1 proves the run pages did not change:

```python
def icon_names(
    loaded: LoadedRun | LoadedEncounter,
    parse_samples: Sequence[ParseSample],
    our_auras: Sequence[PlayerAuras | None] = (),
) -> dict[int, str]:
    """<build_icons' current docstring, unchanged>"""
    names: dict[int, str] = {}
    # ... build_icons' current body, unchanged, up to and excluding its return ...
    return names


def build_icons(
    loaded: LoadedRun | LoadedEncounter,
    parse_samples: Sequence[ParseSample],
    our_auras: Sequence[PlayerAuras | None] = (),
) -> CdnIcons:
    """Icons for one run: `icon_names`, resolved behind one CDN."""
    return CdnIcons(icon_names(loaded, parse_samples, our_auras))
```

Refactor `build_reference_repositories` to share the one-day cache it builds:

```python
def _transient_cache(cache_dir: Path) -> DiskCache:
    """The one-day tier: leaderboards, reference runs, and a character's ranked runs."""
    return DiskCache(cache_dir / REFERENCE_CACHE_SUBDIR, max_age_seconds=REFERENCE_CACHE_SECONDS)


def build_reference_repositories(
    client: WclClient, cache_dir: Path
) -> tuple[WclRankingRepository, WclRunRepository]:
    """The leaderboards and the reference runs, behind the expiring cache."""
    transient = _transient_cache(cache_dir)
    return WclRankingRepository(client, transient), WclRunRepository(client, transient)
```

Then add, after `analyze` (before `raid`):

```python
NO_ZONE_MESSAGE = (
    "No zone given. Add ?zone=<id> to the character URL or pass --zone: the id is the number "
    "after zone= in the character page's address once a Mythic+ season is selected there."
)


def _character_run(analysis: RunAnalysis, dungeon: str) -> CharacterRun:
    """What one analysed run hands to the cross-run reading."""
    loaded = analysis.loaded
    run = loaded.run
    slug = analysis.subjects[0].slug if analysis.subjects else ""
    return CharacterRun(
        report_code=run.report_code,
        fight_id=run.fight_id,
        dungeon=dungeon,
        keystone_level=run.keystone_level,
        in_time=run.keystone_bonus >= 1,
        subject_slug=slug,
        subject_deaths=sum(
            1 for death in loaded.deaths if death.actor_id == analysis.subject.actor_id
        ),
        findings=tuple(analysis.findings),
        measures=analysis.tables.get(slug),
        tempo=(
            tempo_measures(loaded, analysis.speed_sample)
            if analysis.speed_sample is not None
            else None
        ),
    )


@app.command()
def character(
    url: str = typer.Argument(..., help="Warcraft Logs character page URL"),
    zone: int | None = typer.Option(None, help="Zone id; defaults to the URL's ?zone="),
    spec: str | None = typer.Option(
        None, help="Specialisation to read; defaults to the one with the most ranked runs"
    ),
    narrative: Path | None = typer.Option(
        None, help="Plain text notes to render as the page's interpretation section"
    ),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Where to cache API responses"),
    out: Path = typer.Option(Path("out"), help="Where to write the character's directory"),
) -> None:
    """Read one recent high key per dungeon for one character and state what repeats."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        narrative_text = _read_narrative(narrative)
        ref = parse_character_url(url)
        zone_id = zone if zone is not None else ref.zone_id
        if zone_id is None:
            raise ValueError(NO_ZONE_MESSAGE)
        repository = build_repository(cache_dir)
        before = repository.rate_limit()
        characters = WclCharacterRepository(repository.client, _transient_cache(cache_dir))
        found_zone = characters.zone(zone_id)
        require_mythic_plus(found_zone)
        selection = select_runs(
            found_zone,
            characters.ranked_runs(ref.name, ref.realm, ref.region, found_zone),
            spec,
        )
        directory = out / f"{ref.region}-{player_slug(ref.realm)}-{player_slug(ref.name)}"
        directory.mkdir(parents=True, exist_ok=True)

        runs: list[CharacterRun] = []
        failed: list[FailedRun] = []
        # Every loaded run's icon names, merged: a cross-run finding names an
        # ability, and only a run's own dictionary knows its art.
        icons: dict[int, str] = {}
        for chosen in selection.chosen:
            label = f"{chosen.dungeon} +{chosen.keystone_level}"
            try:
                analysis = analyse_run(
                    repository, cache_dir, chosen.report_code, chosen.fight_id, players=[ref.name]
                )
            except RateLimitExceeded:
                # A spent budget is not one bad run: every run after it would
                # fail the same way, so the command stops and says so.
                raise
            except (ValueError, WclError, httpx.HTTPError) as error:
                typer.secho(f"{label}: {error}", err=True, fg="yellow")
                failed.append(FailedRun(
                    dungeon=chosen.dungeon, keystone_level=chosen.keystone_level,
                    report_code=chosen.report_code, fight_id=chosen.fight_id, reason=str(error),
                ))
                continue
            written = write_findings(analysis, directory)
            write_page(analysis, directory, None, fetched_at)
            typer.echo(f"{label}: {len(analysis.findings)} findings written to {written}")
            icons.update(icon_names(
                analysis.loaded,
                tuple(one.parse for one in analysis.subjects if one.parse is not None),
                tuple(one.our_auras for one in analysis.subjects),
            ))
            runs.append(_character_run(analysis, chosen.dungeon))
        after = repository.rate_limit()
    except (ValueError, WclError, httpx.HTTPError, OSError) as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    findings = consistent_directions(runs) + repeated_judgements(runs)
    ledger = group_ledger(runs)
    subject = CharacterSubject(
        name=ref.name, realm=ref.realm, region=ref.region, zone_name=found_zone.name
    )
    payload = {
        "character": {
            "name": ref.name, "realm": ref.realm, "region": ref.region,
            "zone_id": found_zone.zone_id, "zone_name": found_zone.name, "spec": selection.spec,
        },
        "asked_for": {"url": url, "zone": zone, "spec": spec},
        "runs": [
            {
                "dungeon": run.dungeon, "keystone_level": run.keystone_level,
                "in_time": run.in_time, "report_code": run.report_code,
                "fight_id": run.fight_id,
                "findings_file": f"{run.report_code}-{run.fight_id}.findings.json",
                "report_file": run_file(run.report_code, run.fight_id),
                "subject_deaths": run.subject_deaths,
                "tempo": run.tempo.model_dump(mode="json") if run.tempo else None,
            }
            for run in runs
        ],
        "failed": [one.model_dump(mode="json") for one in failed],
        "left_out": [one.model_dump(mode="json") for one in selection.left_out],
        "rules": {
            "repeat_min_runs": REPEAT_MIN_RUNS,
            "min_direction_runs": MIN_DIRECTION_RUNS,
            "direction_rate_floor": DIRECTION_RATE_FLOOR,
            "direction_share_floor": DIRECTION_SHARE_FLOOR,
        },
        "findings_are_counted_not_summed": COUNTED_NOT_SUMMED,
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "group_ledger": ledger.model_dump(mode="json"),
    }
    try:
        written = directory / "character.json"
        written.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        page = directory / "character.html"
        page.write_text(
            render_character(
                build_character_report(
                    subject, selection, runs, failed, findings, ledger, narrative_text, fetched_at
                ),
                icons=CdnIcons(icons),
            ),
            encoding="utf-8",
        )
    except OSError as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    typer.echo(f"{len(findings)} findings written to {written}")
    typer.echo(f"page written to {page}")
    typer.echo(_quota_sentence(before, after), err=True)
    _echo_cost_breakdown(repository.client.costs)
```

- [ ] **Step 4: Run the tests**

Run: `~/.local/bin/uv run pytest tests/test_cli_character.py -q` — Expected: all pass.

- [ ] **Step 5: Full suite, lint, types; commit**

```bash
git add src/wowperf/cli.py tests/test_cli_character.py
git commit -m "Add the character command" -m "It chooses one recent high key per dungeon, analyses each with analyze's own pipeline into one directory, and writes a page and a JSON stating what repeats. A run that fails to load shrinks the page; a spent budget stops the command, since every run after it would fail the same way." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: End to end against the real API

**Files:**
- Create: `tests/e2e/test_character_e2e.py`
- Modify: `.env.example`

- [ ] **Step 1: Add the variable to `.env.example`** (after the raid entries)

```text
# The character the `character` end-to-end test reads: a Warcraft Logs character page URL with
# ?zone=<id>. Left empty here on purpose -- a character URL names a real person, and CLAUDE.md
# keeps real names out of the repository. Prefer a character with fewer than six dungeons ranked
# in that zone: the run stays cheap and reaches the withheld-directions state. A cold run costs
# about 100 points per dungeon read.

WOWPERF_E2E_CHARACTER=
```

- [ ] **Step 2: Write the test**

```python
# ABOUTME: The character command against the live API: one real character, every file it writes.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

"""Asserts shapes and invariants only, never a name: the character is a real person, named only
in the untracked `.env`."""

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wowperf.adapters.config.dotenv import apply_dotenv
from wowperf.cli import app

pytestmark = pytest.mark.e2e


def test_character_writes_a_page_whose_every_finding_is_badged(tmp_path: Path) -> None:
    apply_dotenv(Path.cwd() / ".env", os.environ)
    url = os.environ.get("WOWPERF_E2E_CHARACTER")
    if not url:
        pytest.fail("Set WOWPERF_E2E_CHARACTER in .env to a character URL with ?zone=<id>; "
                    "see .env.example.")

    result = CliRunner().invoke(app, ["character", url, "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    [directory] = [one for one in tmp_path.iterdir() if one.is_dir()]
    payload = json.loads((directory / "character.json").read_text(encoding="utf-8"))
    assert (directory / "character.html").is_file()
    for run in payload["runs"]:
        assert (directory / run["findings_file"]).is_file()
        assert (directory / run["report_file"]).is_file()
    ids = [finding["id"] for finding in payload["findings"]]
    assert len(ids) == len(set(ids))
    for finding in payload["findings"]:
        assert finding["confidence"] in {"measured", "derived", "inferred"}
        if finding["id"].startswith("character.direction.") and \
                finding["id"] != "character.direction.withheld":
            assert finding["quantifier"] == "every"
```

- [ ] **Step 3: Run it** (only once RwlRwlRwlRwl has set the variable; it spends quota)

Run: `~/.local/bin/uv run pytest -m e2e tests/e2e/test_character_e2e.py -v`
Expected: PASS. Record its cost from the printed breakdown.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_character_e2e.py .env.example
git commit -m "Check the character command end to end against the live API" -m "Offline tests cannot tell whether the live rankings, the run selection and the per-run pipeline agree. The character is read from .env, since a character URL names a real person." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Documentation

**Files:**
- Modify: `.claude/skills/analyzing-a-run/SKILL.md`, `tests/test_skills.py`,
  `.claude/skills/mplus-analysis/SKILL.md`, `CLAUDE.md`, `README.md`, `docs/how-it-works.md`,
  `docs/plans/2026-09-03-mplus-postmortem-design.md`

- [ ] **Step 1: Make the skill test expect the new section (failing first)**

In `tests/test_skills.py`: `COMMANDS = ("analyze", "raid", "progression", "night", "character")`;
add `"character": frozenset({"--player", "--all-players", "--no-compare", "--fight", "--throughput-ceiling"})`
to `EXPLICITLY_UNSUPPORTED`; in `_section_text`, make `night` end at the new heading and add the new
branch:

```python
    if command == "night":
        return text.split("## The `night` command")[1].split("## The `character` command")[0]
    if command == "character":
        return text.split("## The `character` command")[1].split("## When it goes wrong")[0]
```

Run: `~/.local/bin/uv run pytest tests/test_skills.py -q` — Expected: FAIL (no such heading).

- [ ] **Step 2: Write the skill section** in `analyzing-a-run/SKILL.md`, between the `night` section
  and `## When it goes wrong`, headed `## The \`character\` command`. It must name `--zone`,
  `--spec`, `--narrative`, `--cache-dir` and `--out`, and say that `--player`, `--all-players`,
  `--no-compare`, `--fight` and `--throughput-ceiling` are not offered and why (the subject is the
  character, the comparison is what the patterns read, the runs are chosen by rule). Cover: the run
  selection rule; that every run's report is written into `<out>/<region>-<realm>-<name>/` beside
  the page; the three kinds of statement; the narrative workflow (read `character.json`, write the
  narrative with no digits, re-run with the same flags plus `--narrative`); cost (about 100 points a
  cold dungeon, about one warm); and that failed runs shrink the page while a spent budget stops it.

Run: `~/.local/bin/uv run pytest tests/test_skills.py -q` — Expected: PASS.

- [ ] **Step 3: `mplus-analysis/SKILL.md`** — add `## Reading a character page`: repeated judgements
  carry the least-certain badge and the quantifier of their count; directions are `derived`, always
  `every`, over at least six judged runs with the two floors, chosen not measured, and state a
  difference, not a mistake; the ledger counts sides and states no verdict; nothing is summed; the
  analysis-side families are not counted (and why); the narrative echoes quantifiers and titles,
  never the "N of M" digits.

- [ ] **Step 4: `CLAUDE.md`** — add the command to the Commands table
  (`uv run wowperf character <character-url> [--zone ID] [--spec NAME] [--narrative FILE] [--cache-dir DIR] [--out DIR]`
  with its role), change "The five that read a report" to also cover the character command, and add
  one sentence to the repository overview naming it. `README.md` and `docs/how-it-works.md`: the
  command, its output directory, and a quota row once Task 16 has measured it.

- [ ] **Step 5: Master design amendment** — in `2026-09-03-mplus-postmortem-design.md`, after the
  "Out of scope, deferred to later slices" line, add:
  `*Amended 2026-10-14:* personal run history is taken up by \`2026-10-14-character-command-design.md\`.`

- [ ] **Step 6: Full suite, lint, types; commit**

```bash
git add .claude/skills tests/test_skills.py CLAUDE.md README.md docs/how-it-works.md docs/plans/2026-09-03-mplus-postmortem-design.md
git commit -m "Document the character command" -m "The skills drive the tool for a reader, and the skill test holds each command's section to its real --help, so the new command needs its own section. The master design deferred personal run history; it now names the design that took it up." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: The live proof

**Files:**
- Modify: `docs/plans/2026-10-14-character-command-design.md` (dated amendment), `.claude/skills/wcl-api/SKILL.md` (cost), `README.md` (quota row)

- [ ] **Step 1: Run against RwlRwlRwlRwl's own character** (URL from the chat, never committed)

Run: `~/.local/bin/uv run wowperf character "<character URL>?zone=55"`
Record: points spent, by operation; runs chosen, loaded, failed; dungeons left out.

- [ ] **Step 2: Report how often each state occurred**, from `character.json` with a short script:
  direction findings (and their kinds: boss, trash, buff, debuff, stat), repeated judgements (and
  their families), whether directions were withheld, ledger columns compared. **A state that never
  occurred is a defect, not a quiet success**: buff, debuff and stat directions, repeated
  judgements, a failed run and a left-out dungeon should each be looked for.

- [ ] **Step 3: Reach the withheld state.** It cannot occur with six or more loaded runs. Pre-check
  cheaply (the selection queries cost about two points; no run is analysed): run the selection alone
  for RwlRwlRwlRwl's character over the other Mythic+ zones the API lists, and find a zone where
  fewer than six dungeons qualify. If one exists, run the command there and confirm
  `character.direction.withheld`. If none exists, stop and ask RwlRwlRwlRwl for a character to use —
  never pick another player's history unasked.

- [ ] **Step 4: Open the page and check it by eye** — serve the output directory with
  `python -m http.server` (the browser pane renders local files as inert snapshots) and confirm the
  four tabs switch, every run link opens its report, and the ledger reads.

- [ ] **Step 5: Record it** — a dated amendment in the design's §8 and §10 with the measured cost
  and the state distribution (no names: "the user's own character"), the selection queries' cost in
  the `wcl-api` skill, and the quota row in the README.

- [ ] **Step 6: Commit**

```bash
git add docs/plans/2026-10-14-character-command-design.md .claude/skills/wcl-api/SKILL.md README.md
git commit -m "Record what the character command cost and which states a live run reached" -m "A new judgement is not done until a live run has exercised it. This records the cost by operation and how often each kind of statement occurred on a real character." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
