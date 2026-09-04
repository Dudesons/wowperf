# Mythic+ Post-Mortem, Plan A: Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch a Mythic+ run from Warcraft Logs and turn it into a validated, I/O-free domain model that later plans analyse.

**Architecture:** Hexagonal. `wowperf/domain/` holds Pydantic entities and Protocol ports and imports nothing that touches the network or disk. `wowperf/adapters/wcl/` speaks GraphQL and translates responses into the domain model. `wowperf/adapters/cache/` wraps fetches in a disk cache. A `typer` command wires them together.

**Tech Stack:** Python 3.12+, `uv`, `httpx`, `pydantic` v2, `typer`, `pytest`, `ruff`, `mypy`.

**Spec:** `docs/plans/2026-09-03-mplus-postmortem-design.md`

## Global Constraints

- **Python `>=3.12`.** `uv` is the only toolchain: no pip, no poetry, no hand-managed virtualenv.
- **`wowperf/domain/` imports no I/O.** No `httpx`, no `jinja2`, no `pathlib` writes. Adapters do that.
- **Every `Finding` carries a `Confidence`** of `measured`, `derived`, or `inferred`.
- **No hardcoded zone, encounter, or affix IDs.** They resolve from the API at runtime.
- **Cache every Warcraft Logs response.** Point cost per query is undocumented and the hourly budget is small.
- **Never invent a Warcraft Logs field name.** Every field used in this plan is verified in spec §2. If you need one that is not here, verify it against the live schema first.
- **Fight and pull timestamps are milliseconds relative to report start.** `Report.startTime` is absolute epoch milliseconds.
- **English** in code, comments, error strings, and commit messages.
- **Never `--no-verify`.**
- Every file starts with two `# ABOUTME: ` comment lines.

## File Structure

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Dependencies, tool config, console script |
| `src/wowperf/domain/model.py` | `Run`, `Pull`, `Player` — the run as a structure |
| `src/wowperf/domain/events.py` | `Death`, `CastEvent` — the run as a sequence |
| `src/wowperf/domain/findings.py` | `Confidence`, `Finding`, `rank_findings` |
| `src/wowperf/domain/ports.py` | `RunRepository`, `RankingRepository`, `ReportRenderer` Protocols |
| `src/wowperf/adapters/wcl/auth.py` | OAuth client-credentials token, cached until expiry |
| `src/wowperf/adapters/wcl/client.py` | GraphQL transport, errors, rate-limit reads |
| `src/wowperf/adapters/wcl/queries.py` | GraphQL query text, one constant per query |
| `src/wowperf/adapters/wcl/pagination.py` | `nextPageTimestamp` loop for `events` |
| `src/wowperf/adapters/wcl/ingest.py` | Warcraft Logs JSON to domain model |
| `src/wowperf/adapters/wcl/repository.py` | `WclRunRepository`, implements the port |
| `src/wowperf/adapters/cache/disk.py` | Content-addressed JSON cache on disk |
| `src/wowperf/urls.py` | Parse a report URL into code and fight ID |
| `src/wowperf/cli.py` | `typer` application |
| `tests/fakes.py` | `InMemoryRunRepository` for later plans |

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `.python-version`, `src/wowperf/__init__.py`, `src/wowperf/py.typed`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an installed `wowperf` package importable by every later task, and the commands `uv run pytest`, `uv run ruff check .`, `uv run mypy src`.

- [ ] **Step 1: Confirm the toolchain exists**

Run: `uv --version`

If this fails, stop and install `uv` before continuing. Do not substitute pip.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "wowperf"
version = "0.1.0"
description = "Analyse World of Warcraft logs and report what to improve"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.7",
    "typer>=0.12",
]

[project.scripts]
wowperf = "wowperf.cli:app"

[dependency-groups]
dev = [
    "pytest>=8.2",
    "ruff>=0.5",
    "mypy>=1.10",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/wowperf"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not e2e' --strict-markers"
markers = [
    "e2e: hits the real Warcraft Logs API; needs credentials and spends quota",
]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src"]
```

- [ ] **Step 3: Create the package**

```bash
mkdir -p src/wowperf/domain src/wowperf/adapters/wcl src/wowperf/adapters/cache tests
printf '3.12\n' > .python-version
touch src/wowperf/py.typed
```

Write `src/wowperf/__init__.py`:

```python
# ABOUTME: Package root for wowperf, a local analyser for World of Warcraft combat logs.
# ABOUTME: Holds the version constant only; behaviour lives in domain, adapters and cli.

__version__ = "0.1.0"
```

Create empty `__init__.py` files so the subpackages import:

```bash
touch src/wowperf/domain/__init__.py src/wowperf/adapters/__init__.py \
      src/wowperf/adapters/wcl/__init__.py src/wowperf/adapters/cache/__init__.py \
      tests/__init__.py
```

- [ ] **Step 4: Write the failing test**

`tests/test_packaging.py`:

```python
# ABOUTME: Proves the package is installed and importable before any real code depends on it.
# ABOUTME: A failure here means the uv environment is wrong, not that a feature is broken.

import wowperf


def test_package_exposes_a_version() -> None:
    assert wowperf.__version__ == "0.1.0"
```

- [ ] **Step 5: Sync and run the test**

Run: `uv sync && uv run pytest tests/test_packaging.py -v`
Expected: PASS. If the import fails, the `[tool.hatch.build.targets.wheel]` packages path is wrong.

- [ ] **Step 6: Confirm lint and type checking run clean**

Run: `uv run ruff check . && uv run mypy src`
Expected: both report no issues.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .python-version src tests
git commit -m "Create the wowperf package and its uv toolchain

Establish the src layout, the pytest e2e marker that keeps the default
suite offline, and strict mypy, so every later task inherits the same
gate rather than negotiating one."
```

---

### Task 2: The run as a structure

**Files:**
- Create: `src/wowperf/domain/model.py`
- Test: `tests/domain/test_model.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class Player(BaseModel)`: `actor_id: int`, `name: str`, `class_name: str`, `spec: str`, `item_level: int`
  - `class EnemyNpc(BaseModel)`: `actor_id: int`, `game_id: int`
  - `class Pull(BaseModel)`: `index: int`, `pull_id: int`, `name: str`, `encounter_id: int`, `start_ms: int`, `end_ms: int`, `killed: bool`, `x: int`, `y: int`, `enemies: tuple[EnemyNpc, ...]`; properties `is_boss: bool`, `duration_seconds: float`, `signature: tuple[int, ...]`
  - `class Run(BaseModel)`: `report_code: str`, `fight_id: int`, `dungeon_name: str`, `keystone_level: int`, `affix_ids: tuple[int, ...]`, `keystone_time_ms: int`, `keystone_bonus: int`, `count_reached: int`, `count_required: int`, `npc_count_map: dict[int, int]`, `players: tuple[Player, ...]`, `pulls: tuple[Pull, ...]`; properties `total_pull_seconds: float`, `keystone_time_seconds: float`, `boss_pulls`, `trash_pulls`

- [ ] **Step 1: Write the failing tests**

```bash
mkdir -p tests/domain && touch tests/domain/__init__.py
```

`tests/domain/test_model.py`:

```python
# ABOUTME: Behaviour tests for the run structure: pull classification, durations and signatures.
# ABOUTME: These models are pure data, so the tests cover only the derived properties.

from wowperf.domain.model import EnemyNpc, Player, Pull, Run


def a_pull(index: int, start_ms: int, end_ms: int, encounter_id: int = 0,
           game_ids: tuple[int, ...] = (100,)) -> Pull:
    return Pull(
        index=index,
        pull_id=index,
        name="Pull",
        encounter_id=encounter_id,
        start_ms=start_ms,
        end_ms=end_ms,
        killed=True,
        x=0,
        y=0,
        enemies=tuple(EnemyNpc(actor_id=i, game_id=g) for i, g in enumerate(game_ids)),
    )


def a_run(pulls: tuple[Pull, ...]) -> Run:
    return Run(
        report_code="abc123",
        fight_id=1,
        dungeon_name="Murder Row",
        keystone_level=12,
        affix_ids=(9, 10),
        keystone_time_ms=1_800_000,
        keystone_bonus=1,
        count_reached=820,
        count_required=800,
        npc_count_map={100: 5},
        players=(Player(actor_id=1, name="Someone", class_name="Mage",
                        spec="Frost", item_level=300),),
        pulls=pulls,
    )


def test_a_pull_with_a_non_zero_encounter_id_is_a_boss() -> None:
    assert a_pull(0, 0, 1000, encounter_id=3470).is_boss is True


def test_a_pull_with_encounter_id_zero_is_trash() -> None:
    assert a_pull(0, 0, 1000).is_boss is False


def test_pull_duration_converts_milliseconds_to_seconds() -> None:
    assert a_pull(0, 10_000, 41_500).duration_seconds == 31.5


def test_a_pull_signature_is_its_sorted_enemy_game_ids() -> None:
    assert a_pull(0, 0, 1, game_ids=(300, 100, 200, 100)).signature == (100, 100, 200, 300)


def test_total_pull_seconds_sums_every_pull() -> None:
    run = a_run((a_pull(0, 0, 30_000), a_pull(1, 60_000, 90_000)))
    assert run.total_pull_seconds == 60.0


def test_boss_and_trash_pulls_partition_the_run() -> None:
    run = a_run((a_pull(0, 0, 1000), a_pull(1, 2000, 3000, encounter_id=3470)))
    assert [p.index for p in run.trash_pulls] == [0]
    assert [p.index for p in run.boss_pulls] == [1]


def test_the_model_is_frozen() -> None:
    import pytest
    from pydantic import ValidationError

    pull = a_pull(0, 0, 1000)
    with pytest.raises(ValidationError):
        pull.index = 5  # type: ignore[misc]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/domain/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.domain.model'`

- [ ] **Step 3: Write the implementation**

`src/wowperf/domain/model.py`:

```python
# ABOUTME: The run as a structure: who was there, which packs were pulled, and when.
# ABOUTME: Pure data with derived properties; imports nothing that performs I/O.

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Player(Frozen):
    actor_id: int
    name: str
    class_name: str
    spec: str
    item_level: int


class EnemyNpc(Frozen):
    actor_id: int
    game_id: int


class Pull(Frozen):
    index: int
    pull_id: int
    name: str
    encounter_id: int
    start_ms: int
    end_ms: int
    killed: bool
    x: int
    y: int
    enemies: tuple[EnemyNpc, ...]

    @property
    def is_boss(self) -> bool:
        """Warcraft Logs uses encounter ID 0 to mean a trash pull."""
        return self.encounter_id != 0

    @property
    def duration_seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000

    @property
    def signature(self) -> tuple[int, ...]:
        """Canonical identity of a pull, used to align two runs of the same dungeon."""
        return tuple(sorted(enemy.game_id for enemy in self.enemies))


class Run(Frozen):
    report_code: str
    fight_id: int
    dungeon_name: str
    keystone_level: int
    affix_ids: tuple[int, ...]
    keystone_time_ms: int
    keystone_bonus: int
    count_reached: int
    count_required: int
    npc_count_map: dict[int, int]
    players: tuple[Player, ...]
    pulls: tuple[Pull, ...]

    @property
    def keystone_time_seconds(self) -> float:
        return self.keystone_time_ms / 1000

    @property
    def total_pull_seconds(self) -> float:
        return sum(pull.duration_seconds for pull in self.pulls)

    @property
    def boss_pulls(self) -> tuple[Pull, ...]:
        return tuple(pull for pull in self.pulls if pull.is_boss)

    @property
    def trash_pulls(self) -> tuple[Pull, ...]:
        return tuple(pull for pull in self.pulls if not pull.is_boss)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/domain/test_model.py -v && uv run mypy src`
Expected: 7 passed, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/domain/model.py tests/domain
git commit -m "Model a Mythic+ run as pulls, players and keystone facts

Give the analysis layer a vocabulary that owes nothing to Warcraft Logs,
so a later raw combat-log adapter can produce the same objects without
the analysers noticing."
```

---

### Task 3: The run as a sequence, and findings

**Files:**
- Create: `src/wowperf/domain/events.py`, `src/wowperf/domain/findings.py`
- Test: `tests/domain/test_events.py`, `tests/domain/test_findings.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class Death(BaseModel)`: `player_name: str`, `actor_id: int`, `timestamp_ms: int`, `pull_index: int | None`, `killing_blow: str`, `overkill: int`, `seconds_until_next_action: float | None`
  - `class CastEvent(BaseModel)`: `actor_id: int`, `ability_id: int`, `ability_name: str`, `timestamp_ms: int`, `pull_index: int | None`
  - `class Confidence(StrEnum)`: `MEASURED`, `DERIVED`, `INFERRED`
  - `class Finding(BaseModel)`: `id: str`, `title: str`, `detail: str`, `confidence: Confidence`, `seconds_lost: float | None`, `evidence: tuple[str, ...]`, `pull_index: int | None`
  - `def rank_findings(findings: Iterable[Finding]) -> list[Finding]`

- [ ] **Step 1: Write the failing tests**

`tests/domain/test_events.py`:

```python
# ABOUTME: Behaviour tests for the event entities that analysers consume.
# ABOUTME: Covers only defaulting; the interesting logic lives in the analysers.

from wowperf.domain.events import CastEvent, Death


def test_a_death_outside_any_pull_has_no_pull_index() -> None:
    death = Death(
        player_name="Someone",
        actor_id=1,
        timestamp_ms=5000,
        killing_blow="Void Bolt",
        overkill=120,
    )
    assert death.pull_index is None
    assert death.seconds_until_next_action is None


def test_a_cast_records_the_ability_by_id_and_name() -> None:
    cast = CastEvent(actor_id=1, ability_id=42, ability_name="Frostbolt", timestamp_ms=100)
    assert (cast.ability_id, cast.ability_name) == (42, "Frostbolt")
```

`tests/domain/test_findings.py`:

```python
# ABOUTME: Behaviour tests for the finding type and its ranking.
# ABOUTME: The confidence badge is mandatory, so its absence must be an error.

import pytest
from pydantic import ValidationError

from wowperf.domain.findings import Confidence, Finding, rank_findings


def a_finding(finding_id: str, seconds_lost: float | None) -> Finding:
    return Finding(
        id=finding_id,
        title="Title",
        detail="Detail",
        confidence=Confidence.MEASURED,
        seconds_lost=seconds_lost,
    )


def test_a_finding_without_a_confidence_badge_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Finding(id="x", title="Title", detail="Detail")  # type: ignore[call-arg]


def test_findings_rank_by_seconds_lost_descending() -> None:
    ranked = rank_findings([a_finding("small", 3.0), a_finding("big", 40.0)])
    assert [finding.id for finding in ranked] == ["big", "small"]


def test_findings_without_a_time_cost_rank_last_in_stable_order() -> None:
    ranked = rank_findings([a_finding("untimed", None), a_finding("timed", 1.0)])
    assert [finding.id for finding in ranked] == ["timed", "untimed"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/domain -v`
Expected: FAIL with `ModuleNotFoundError` for `wowperf.domain.events`.

- [ ] **Step 3: Write the implementations**

`src/wowperf/domain/events.py`:

```python
# ABOUTME: The run as a sequence: deaths and casts, each located in time and in a pull.
# ABOUTME: Pure data; analysers derive meaning from these, adapters produce them.

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Death(Frozen):
    player_name: str
    actor_id: int
    timestamp_ms: int
    killing_blow: str
    overkill: int
    pull_index: int | None = None
    seconds_until_next_action: float | None = None


class CastEvent(Frozen):
    actor_id: int
    ability_id: int
    ability_name: str
    timestamp_ms: int
    pull_index: int | None = None
```

`src/wowperf/domain/findings.py`:

```python
# ABOUTME: The output type of every analyser, and the ranking that orders a report.
# ABOUTME: Confidence is mandatory so a reader always knows how much to trust a claim.

from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Confidence(StrEnum):
    """How much the log actually supports a claim.

    MEASURED  read straight from the log
    DERIVED   computed by a documented formula over logged facts
    INFERRED  requires an assumption the log cannot confirm
    """

    MEASURED = "measured"
    DERIVED = "derived"
    INFERRED = "inferred"


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    detail: str
    confidence: Confidence
    seconds_lost: float | None = None
    evidence: tuple[str, ...] = ()
    pull_index: int | None = None


def rank_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Order findings by time cost, descending. Findings with no time cost come last."""
    return sorted(
        findings,
        key=lambda finding: (finding.seconds_lost is None, -(finding.seconds_lost or 0.0)),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/domain -v && uv run mypy src`
Expected: 12 passed, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/domain/events.py src/wowperf/domain/findings.py tests/domain
git commit -m "Add the event entities and the mandatory-confidence finding

Make the confidence badge a required field rather than a convention, so a
finding that cannot say how well the log supports it fails validation
instead of reaching a reader."
```

---

### Task 4: Ports and an in-memory repository

**Files:**
- Create: `src/wowperf/domain/ports.py`, `tests/fakes.py`
- Test: `tests/test_ports.py`

**Interfaces:**
- Consumes: `Run` from Task 2.
- Produces:
  - `class RunRepository(Protocol)`: `def get(self, report_code: str, fight_id: int | None) -> Run`
  - `class RankingRepository(Protocol)`: `def fastest_runs(self, encounter_id: int, keystone_level: int, limit: int) -> list[RunRef]`
  - `class RunRef(BaseModel)`: `report_code: str`, `fight_id: int`, `keystone_level: int`, `duration_ms: int`
  - `class ReportRenderer(Protocol)`: `def render(self, html_path: Path, context: dict[str, object]) -> None`
  - `tests/fakes.py`: `InMemoryRunRepository(runs: dict[tuple[str, int | None], Run])`

- [ ] **Step 1: Write the failing test**

`tests/test_ports.py`:

```python
# ABOUTME: Proves the fake repository satisfies the port that adapters must also satisfy.
# ABOUTME: Keeps later plans honest: if the port changes, the fake breaks here first.

import pytest

from tests.fakes import InMemoryRunRepository
from tests.domain.test_model import a_run
from wowperf.domain.ports import RunRepository


def test_the_in_memory_repository_satisfies_the_run_repository_port() -> None:
    run = a_run(())
    repository: RunRepository = InMemoryRunRepository({("abc123", 1): run})
    assert repository.get("abc123", 1) is run


def test_an_unknown_report_raises_a_key_error_naming_the_code() -> None:
    repository = InMemoryRunRepository({})
    with pytest.raises(KeyError, match="missing"):
        repository.get("missing", 1)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_ports.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.domain.ports'`

- [ ] **Step 3: Write the implementations**

`src/wowperf/domain/ports.py`:

```python
# ABOUTME: The boundaries of the domain: how it obtains runs and rankings, and emits reports.
# ABOUTME: Protocols only, so the domain never imports an adapter or anything doing I/O.

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from wowperf.domain.model import Run


class RunRef(BaseModel):
    """Enough to fetch a run later, without holding the run itself."""

    model_config = ConfigDict(frozen=True)

    report_code: str
    fight_id: int
    keystone_level: int
    duration_ms: int


class RunRepository(Protocol):
    def get(self, report_code: str, fight_id: int | None) -> Run: ...


class RankingRepository(Protocol):
    def fastest_runs(
        self, encounter_id: int, keystone_level: int, limit: int
    ) -> list[RunRef]: ...


class ReportRenderer(Protocol):
    def render(self, html_path: Path, context: dict[str, object]) -> None: ...
```

`tests/fakes.py`:

```python
# ABOUTME: Test doubles that satisfy the domain ports without touching the network.
# ABOUTME: Lets analyser and service tests run offline against real domain objects.

from wowperf.domain.model import Run


class InMemoryRunRepository:
    """Serves pre-built runs. Satisfies RunRepository."""

    def __init__(self, runs: dict[tuple[str, int | None], Run]) -> None:
        self._runs = runs

    def get(self, report_code: str, fight_id: int | None) -> Run:
        try:
            return self._runs[(report_code, fight_id)]
        except KeyError:
            raise KeyError(f"No run stored for report {report_code} fight {fight_id}") from None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_ports.py -v && uv run mypy src`
Expected: 2 passed, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/domain/ports.py tests/fakes.py tests/test_ports.py
git commit -m "Define the domain ports and an in-memory run repository

Fix the seam where a raw combat-log adapter will later enter, and give
every offline test a real Run to work against instead of a mock."
```

---

### Task 5: OAuth client-credentials token

**Files:**
- Create: `src/wowperf/adapters/wcl/auth.py`
- Test: `tests/adapters/wcl/test_auth.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `class TokenProvider(client_id: str, client_secret: str, http: httpx.Client, now: Callable[[], float] = time.time)` with `def token(self) -> str`.

**Note on test design:** these tests use `httpx.MockTransport` to inspect the request *we construct* and to count how often we call out. That is testing our own behaviour at a boundary, not asserting that a mock returns what it was told to return.

- [ ] **Step 1: Write the failing tests**

```bash
mkdir -p tests/adapters/wcl
touch tests/adapters/__init__.py tests/adapters/wcl/__init__.py
```

`tests/adapters/wcl/test_auth.py`:

```python
# ABOUTME: Behaviour tests for the OAuth client-credentials token provider.
# ABOUTME: Asserts the request we build and that a valid token is reused, not refetched.

import base64

import httpx

from wowperf.adapters.wcl.auth import TokenProvider


def test_the_token_request_uses_basic_auth_and_the_client_credentials_grant() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["authorization"]
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TokenProvider("id", "secret", http)

    assert provider.token() == "abc"
    assert seen["url"] == "https://www.warcraftlogs.com/oauth/token"
    assert seen["authorization"] == "Basic " + base64.b64encode(b"id:secret").decode()
    assert "grant_type=client_credentials" in seen["body"]


def test_a_valid_token_is_reused_and_refetched_only_near_expiry() -> None:
    issued: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        issued.append(f"t{len(issued) + 1}")
        return httpx.Response(200, json={"access_token": issued[-1], "expires_in": 3600})

    clock = {"now": 0.0}
    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TokenProvider("id", "secret", http, now=lambda: clock["now"])

    assert provider.token() == "t1"

    clock["now"] = 3000.0
    assert provider.token() == "t1"

    clock["now"] = 3550.0  # inside the 60-second refresh margin
    assert provider.token() == "t2"
    assert len(issued) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/adapters/wcl/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.adapters.wcl.auth'`

- [ ] **Step 3: Write the implementation**

`src/wowperf/adapters/wcl/auth.py`:

```python
# ABOUTME: Obtains and caches a Warcraft Logs OAuth token using the client-credentials flow.
# ABOUTME: This flow reads public reports only; private reports need the authorization-code flow.

import time
from collections.abc import Callable

import httpx

TOKEN_URI = "https://www.warcraftlogs.com/oauth/token"
REFRESH_MARGIN_SECONDS = 60


class TokenProvider:
    """Holds one token and renews it shortly before it expires."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http: httpx.Client,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http
        self._now = now
        self._token: str | None = None
        self._expires_at = 0.0

    def token(self) -> str:
        if self._token is not None and self._now() < self._expires_at - REFRESH_MARGIN_SECONDS:
            return self._token

        response = self._http.post(
            TOKEN_URI,
            data={"grant_type": "client_credentials"},
            auth=httpx.BasicAuth(self._client_id, self._client_secret),
        )
        response.raise_for_status()
        payload = response.json()

        self._token = str(payload["access_token"])
        self._expires_at = self._now() + float(payload["expires_in"])
        return self._token
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/adapters/wcl/test_auth.py -v && uv run mypy src`
Expected: 2 passed, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/adapters/wcl/auth.py tests/adapters
git commit -m "Fetch and cache the Warcraft Logs OAuth token

Renew a minute before expiry rather than on rejection, so a long analysis
never fails midway on a token that lapsed between calls."
```

---

### Task 6: GraphQL client and rate-limit reads

**Files:**
- Create: `src/wowperf/adapters/wcl/client.py`, `src/wowperf/adapters/wcl/queries.py`
- Test: `tests/adapters/wcl/test_client.py`

**Interfaces:**
- Consumes: `TokenProvider` from Task 5.
- Produces:
  - `class WclError(RuntimeError)`, `class RateLimitExceeded(WclError)`
  - `class RateLimit(BaseModel)`: `limit_per_hour: int`, `points_spent_this_hour: float`, `points_reset_in: int`
  - `class WclClient(tokens: TokenProvider, http: httpx.Client, endpoint: str = CLIENT_ENDPOINT)` with `def execute(self, query: str, variables: dict[str, object] | None = None) -> dict[str, object]` and `def rate_limit(self) -> RateLimit`
  - `queries.RATE_LIMIT_QUERY`

- [ ] **Step 1: Write the failing tests**

`tests/adapters/wcl/test_client.py`:

```python
# ABOUTME: Behaviour tests for the GraphQL transport: auth header, error surfacing, quota reads.
# ABOUTME: Routes on request path so the real TokenProvider participates rather than a stub.

import httpx
import pytest

from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import RateLimitExceeded, WclClient, WclError


def build_client(graphql: httpx.Response) -> WclClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        return graphql

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return WclClient(TokenProvider("id", "secret", http), http)


def test_a_query_carries_the_bearer_token_and_returns_the_data_block() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        seen["authorization"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": {"hello": "world"}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)

    assert client.execute("query { hello }") == {"hello": "world"}
    assert seen["authorization"] == "Bearer abc"
    assert seen["url"] == "https://www.warcraftlogs.com/api/v2/client"


def test_graphql_errors_are_raised_with_their_messages() -> None:
    client = build_client(
        httpx.Response(200, json={"errors": [{"message": "Cannot query field dungeonPulls"}]})
    )
    with pytest.raises(WclError, match="Cannot query field dungeonPulls"):
        client.execute("query { bad }")


def test_an_exhausted_point_budget_raises_a_named_error() -> None:
    client = build_client(httpx.Response(429, text="Too Many Requests"))
    with pytest.raises(RateLimitExceeded):
        client.execute("query { hello }")


def test_the_rate_limit_is_read_from_the_api_not_assumed() -> None:
    client = build_client(
        httpx.Response(
            200,
            json={
                "data": {
                    "rateLimitData": {
                        "limitPerHour": 3600,
                        "pointsSpentThisHour": 12.5,
                        "pointsResetIn": 900,
                    }
                }
            },
        )
    )
    limit = client.rate_limit()
    assert (limit.limit_per_hour, limit.points_spent_this_hour, limit.points_reset_in) == (
        3600,
        12.5,
        900,
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/adapters/wcl/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.adapters.wcl.client'`

- [ ] **Step 3: Write the implementations**

`src/wowperf/adapters/wcl/queries.py`:

```python
# ABOUTME: GraphQL query text for the Warcraft Logs v2 client API, one constant per query.
# ABOUTME: Every field here is verified against the published schema; do not add unverified ones.

RATE_LIMIT_QUERY = """
query RateLimit {
  rateLimitData {
    limitPerHour
    pointsSpentThisHour
    pointsResetIn
  }
}
"""
```

`src/wowperf/adapters/wcl/client.py`:

```python
# ABOUTME: POSTs GraphQL to the Warcraft Logs client API and surfaces its errors as exceptions.
# ABOUTME: Point cost per query is undocumented, so quota is read from the API, never assumed.

from typing import Any, cast

import httpx
from pydantic import BaseModel, ConfigDict

from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.queries import RATE_LIMIT_QUERY

CLIENT_ENDPOINT = "https://www.warcraftlogs.com/api/v2/client"


class WclError(RuntimeError):
    """The API answered, but not with data we can use."""


class RateLimitExceeded(WclError):
    """The hourly point budget is spent. Points reset on a fixed one-hour cycle."""


class RateLimit(BaseModel):
    model_config = ConfigDict(frozen=True)

    limit_per_hour: int
    points_spent_this_hour: float
    points_reset_in: int


class WclClient:
    def __init__(
        self,
        tokens: TokenProvider,
        http: httpx.Client,
        endpoint: str = CLIENT_ENDPOINT,
    ) -> None:
        self._tokens = tokens
        self._http = http
        self._endpoint = endpoint

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._http.post(
            self._endpoint,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": f"Bearer {self._tokens.token()}"},
        )
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise RateLimitExceeded(
                "Warcraft Logs hourly point budget is spent. Wait for the reset."
            )
        response.raise_for_status()

        payload = response.json()
        if "errors" in payload:
            messages = "; ".join(
                str(error.get("message", "unknown error")) for error in payload["errors"]
            )
            raise WclError(messages)
        return cast(dict[str, Any], payload["data"])

    def rate_limit(self) -> RateLimit:
        data = self.execute(RATE_LIMIT_QUERY)["rateLimitData"]
        return RateLimit(
            limit_per_hour=data["limitPerHour"],
            points_spent_this_hour=data["pointsSpentThisHour"],
            points_reset_in=data["pointsResetIn"],
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/adapters -v && uv run mypy src`
Expected: 6 passed, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/adapters/wcl/client.py src/wowperf/adapters/wcl/queries.py tests/adapters
git commit -m "Send GraphQL to Warcraft Logs and read the quota from the API

GraphQL answers errors with HTTP 200, so surface them as exceptions
rather than letting a caller treat an error body as data. Read the point
budget rather than hardcoding a documented figure that is already stale."
```

---

### Task 7: Disk cache

**Files:**
- Create: `src/wowperf/adapters/cache/disk.py`
- Test: `tests/adapters/cache/test_disk.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `def cache_key(query: str, variables: dict[str, object]) -> str` — SHA-256 hex of the query plus canonical JSON of the variables
  - `class DiskCache(directory: Path)` with `def get_or_fetch(self, key: str, fetch: Callable[[], dict[str, Any]]) -> dict[str, Any]`

- [ ] **Step 1: Write the failing tests**

```bash
mkdir -p tests/adapters/cache && touch tests/adapters/cache/__init__.py
```

`tests/adapters/cache/test_disk.py`:

```python
# ABOUTME: Behaviour tests for the content-addressed response cache.
# ABOUTME: The cache is load-bearing: point cost is unknown, so a second fetch must not happen.

from pathlib import Path

from wowperf.adapters.cache.disk import DiskCache, cache_key


def test_the_same_query_and_variables_produce_the_same_key() -> None:
    assert cache_key("query {}", {"b": 2, "a": 1}) == cache_key("query {}", {"a": 1, "b": 2})


def test_different_variables_produce_different_keys() -> None:
    assert cache_key("query {}", {"a": 1}) != cache_key("query {}", {"a": 2})


def test_a_second_call_is_served_from_disk_without_fetching(tmp_path: Path) -> None:
    calls: list[int] = []

    def fetch() -> dict[str, object]:
        calls.append(1)
        return {"value": 42}

    cache = DiskCache(tmp_path)
    assert cache.get_or_fetch("k", fetch) == {"value": 42}
    assert cache.get_or_fetch("k", fetch) == {"value": 42}
    assert len(calls) == 1


def test_a_fresh_cache_over_the_same_directory_still_hits(tmp_path: Path) -> None:
    DiskCache(tmp_path).get_or_fetch("k", lambda: {"value": 42})

    def fail() -> dict[str, object]:
        raise AssertionError("should have been served from disk")

    assert DiskCache(tmp_path).get_or_fetch("k", fail) == {"value": 42}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/adapters/cache -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.adapters.cache.disk'`

- [ ] **Step 3: Write the implementation**

`src/wowperf/adapters/cache/disk.py`:

```python
# ABOUTME: Content-addressed JSON cache for Warcraft Logs responses, stored one file per key.
# ABOUTME: Report data for a finished fight never changes, so entries are kept indefinitely.

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast


def cache_key(query: str, variables: dict[str, Any]) -> str:
    canonical = json.dumps(variables, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{query}\n{canonical}".encode()).hexdigest()


class DiskCache:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def get_or_fetch(self, key: str, fetch: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        path = self._directory / f"{key}.json"
        if path.exists():
            return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

        value = fetch()
        path.write_text(json.dumps(value), encoding="utf-8")
        return value
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/adapters -v && uv run mypy src`
Expected: 10 passed, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/adapters/cache tests/adapters/cache
git commit -m "Cache Warcraft Logs responses on disk, keyed by query and variables

Point cost per query is undocumented and the hourly budget is small, so
iterating on analysis code without a cache would exhaust it blind."
```

---

### Task 8: Event pagination

**Files:**
- Create: `src/wowperf/adapters/wcl/pagination.py`
- Test: `tests/adapters/wcl/test_pagination.py`

**Interfaces:**
- Consumes: `WclClient.execute` from Task 6.
- Produces: `def fetch_all_events(execute: Callable[[str, dict[str, Any]], dict[str, Any]], query: str, variables: dict[str, Any]) -> list[dict[str, Any]]`

The `events` field returns `{ data, nextPageTimestamp }`. Feed `nextPageTimestamp` back as the next call's `startTime` until it comes back null.

- [ ] **Step 1: Write the failing tests**

`tests/adapters/wcl/test_pagination.py`:

```python
# ABOUTME: Behaviour tests for the events cursor loop.
# ABOUTME: A dropped page silently truncates a run, so paging must be covered directly.

from typing import Any

from wowperf.adapters.wcl.pagination import fetch_all_events


def test_pages_are_followed_until_the_cursor_is_null() -> None:
    pages = [
        {"reportData": {"report": {"events": {"data": [{"t": 1}], "nextPageTimestamp": 500}}}},
        {"reportData": {"report": {"events": {"data": [{"t": 2}], "nextPageTimestamp": None}}}},
    ]
    seen_start_times: list[Any] = []

    def execute(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        seen_start_times.append(variables["startTime"])
        return pages[len(seen_start_times) - 1]

    events = fetch_all_events(execute, "query", {"startTime": 0})

    assert events == [{"t": 1}, {"t": 2}]
    assert seen_start_times == [0, 500]


def test_a_single_page_makes_one_call() -> None:
    calls: list[int] = []

    def execute(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        calls.append(1)
        return {"reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}}

    assert fetch_all_events(execute, "query", {"startTime": 0}) == []
    assert len(calls) == 1


def test_the_callers_variables_are_not_mutated() -> None:
    variables = {"startTime": 0, "code": "abc"}

    def execute(query: str, passed: dict[str, Any]) -> dict[str, Any]:
        return {"reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}}

    fetch_all_events(execute, "query", variables)
    assert variables == {"startTime": 0, "code": "abc"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/adapters/wcl/test_pagination.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.adapters.wcl.pagination'`

- [ ] **Step 3: Write the implementation**

`src/wowperf/adapters/wcl/pagination.py`:

```python
# ABOUTME: Follows the events cursor until exhausted, collecting every page into one list.
# ABOUTME: Warcraft Logs pages events by feeding nextPageTimestamp back as the next startTime.

from collections.abc import Callable
from typing import Any

Execute = Callable[[str, dict[str, Any]], dict[str, Any]]


def fetch_all_events(execute: Execute, query: str, variables: dict[str, Any]) -> list[dict[str, Any]]:
    page_variables = dict(variables)
    events: list[dict[str, Any]] = []

    while True:
        payload = execute(query, page_variables)
        page = payload["reportData"]["report"]["events"]
        events.extend(page["data"])

        cursor = page.get("nextPageTimestamp")
        if cursor is None:
            return events
        page_variables["startTime"] = cursor
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/adapters -v && uv run mypy src`
Expected: 13 passed, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/adapters/wcl/pagination.py tests/adapters/wcl/test_pagination.py
git commit -m "Follow the events cursor to the end of a fight

A truncated event stream produces a plausible but wrong analysis, which
is worse than an error, so paging gets its own tested function."
```

---

### Task 9: Ingest the report into a Run

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py`
- Create: `src/wowperf/adapters/wcl/ingest.py`, `tests/adapters/wcl/fixtures/report_fights.json`
- Test: `tests/adapters/wcl/test_ingest.py`

**Interfaces:**
- Consumes: `Run`, `Pull`, `Player`, `EnemyNpc` from Task 2.
- Produces:
  - `queries.FIGHTS_QUERY`
  - `def select_keystone_fight(fights: list[dict[str, Any]], fight_id: int | None) -> dict[str, Any]`
  - `def build_run(report: dict[str, Any], fight: dict[str, Any]) -> Run`
  - `class IngestError(ValueError)`

**Fixture policy:** this fixture is hand-written to mirror the documented schema shape. Recorded real responses arrive with the end-to-end test in Task 11 and must have player and guild names anonymised.

- [ ] **Step 1: Write the fixture**

```bash
mkdir -p tests/adapters/wcl/fixtures
```

`tests/adapters/wcl/fixtures/report_fights.json`:

```json
{
  "reportData": {
    "report": {
      "code": "abc123",
      "title": "Keys",
      "startTime": 1700000000000,
      "endTime": 1700000600000,
      "fights": [
        {
          "id": 1,
          "name": "Trash",
          "encounterID": 0,
          "startTime": 0,
          "endTime": 5000,
          "kill": null,
          "keystoneLevel": null,
          "keystoneAffixes": null,
          "keystoneTime": null,
          "keystoneBonus": null,
          "countReached": null,
          "countRequired": null,
          "npcCountMap": null,
          "friendlyPlayers": [],
          "friendlySpecs": [],
          "friendlyItemLevels": [],
          "dungeonPulls": []
        },
        {
          "id": 2,
          "name": "Murder Row",
          "encounterID": 12813,
          "startTime": 10000,
          "endTime": 1810000,
          "kill": true,
          "keystoneLevel": 12,
          "keystoneAffixes": [9, 10],
          "keystoneTime": 1800000,
          "keystoneBonus": 1,
          "countReached": 820,
          "countRequired": 800,
          "npcCountMap": {"5001": 4, "5002": 12},
          "friendlyPlayers": [11, 12],
          "friendlySpecs": ["Frost", "Holy"],
          "friendlyItemLevels": [301, 299],
          "dungeonPulls": [
            {
              "id": 1,
              "name": "Row Thug",
              "encounterID": 0,
              "startTime": 20000,
              "endTime": 50000,
              "kill": true,
              "x": 1200,
              "y": 3400,
              "enemyNPCs": [
                {"id": 201, "gameID": 5001},
                {"id": 202, "gameID": 5002}
              ]
            },
            {
              "id": 2,
              "name": "Boss One",
              "encounterID": 99001,
              "startTime": 120000,
              "endTime": 240000,
              "kill": true,
              "x": 1500,
              "y": 3600,
              "enemyNPCs": [{"id": 210, "gameID": 6001}]
            }
          ]
        }
      ],
      "masterData": {
        "actors": [
          {"id": 11, "name": "Frostie", "subType": "Mage", "server": "Hyjal"},
          {"id": 12, "name": "Healbot", "subType": "Priest", "server": "Hyjal"}
        ]
      }
    }
  }
}
```

- [ ] **Step 2: Write the failing tests**

`tests/adapters/wcl/test_ingest.py`:

```python
# ABOUTME: Integration tests for translating a Warcraft Logs report into the domain model.
# ABOUTME: Runs against a committed payload shaped like the real one; no network involved.

import json
from pathlib import Path
from typing import Any

import pytest

from wowperf.adapters.wcl.ingest import IngestError, build_run, select_keystone_fight

FIXTURE = Path(__file__).parent / "fixtures" / "report_fights.json"


def report() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return payload["reportData"]["report"]


def test_the_keystone_fight_is_the_one_with_a_keystone_level() -> None:
    fight = select_keystone_fight(report()["fights"], None)
    assert fight["id"] == 2


def test_an_explicit_fight_id_selects_that_fight() -> None:
    fight = select_keystone_fight(report()["fights"], 2)
    assert fight["id"] == 2


def test_a_fight_id_that_is_not_a_keystone_run_is_rejected() -> None:
    with pytest.raises(IngestError, match="not a Mythic\\+ run"):
        select_keystone_fight(report()["fights"], 1)


def test_a_report_with_no_keystone_fight_is_rejected() -> None:
    with pytest.raises(IngestError, match="no Mythic\\+ run"):
        select_keystone_fight([{"id": 1, "keystoneLevel": None}], None)


def test_keystone_facts_are_carried_into_the_run() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert run.report_code == "abc123"
    assert run.fight_id == 2
    assert run.dungeon_name == "Murder Row"
    assert run.keystone_level == 12
    assert run.affix_ids == (9, 10)
    assert run.keystone_time_ms == 1_800_000
    assert run.keystone_bonus == 1
    assert (run.count_reached, run.count_required) == (820, 800)


def test_the_npc_count_map_keys_become_integers() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert run.npc_count_map == {5001: 4, 5002: 12}


def test_players_join_master_data_with_the_index_aligned_fight_arrays() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert [(p.name, p.class_name, p.spec, p.item_level) for p in run.players] == [
        ("Frostie", "Mage", "Frost", 301),
        ("Healbot", "Priest", "Holy", 299),
    ]


def test_pulls_keep_their_order_and_classify_bosses() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert [(p.index, p.is_boss) for p in run.pulls] == [(0, False), (1, True)]


def test_pull_enemies_carry_their_game_ids() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert run.pulls[0].signature == (5001, 5002)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/adapters/wcl/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.adapters.wcl.ingest'`

- [ ] **Step 4: Add the query**

Append to `src/wowperf/adapters/wcl/queries.py`:

```python
FIGHTS_QUERY = """
query Fights($code: String!) {
  reportData {
    report(code: $code) {
      code
      title
      startTime
      endTime
      fights(translate: true) {
        id
        name
        encounterID
        startTime
        endTime
        kill
        keystoneLevel
        keystoneAffixes
        keystoneTime
        keystoneBonus
        countReached
        countRequired
        npcCountMap
        friendlyPlayers
        friendlySpecs
        friendlyItemLevels
        dungeonPulls {
          id
          name
          encounterID
          startTime
          endTime
          kill
          x
          y
          enemyNPCs { id gameID }
        }
      }
      masterData(translate: true) {
        actors(type: "Player") { id name subType server }
      }
    }
  }
}
"""
```

- [ ] **Step 5: Write the implementation**

`src/wowperf/adapters/wcl/ingest.py`:

```python
# ABOUTME: Translates Warcraft Logs report JSON into the domain model.
# ABOUTME: The only module that knows Warcraft Logs field names; everything downstream is clean.

from typing import Any

from wowperf.domain.model import EnemyNpc, Player, Pull, Run


class IngestError(ValueError):
    """The report does not contain what this tool needs."""


def select_keystone_fight(fights: list[dict[str, Any]], fight_id: int | None) -> dict[str, Any]:
    """Find the fight holding the Mythic+ run.

    A complete run is one fight carrying a keystoneLevel; its trash and bosses
    hang off it as dungeonPulls rather than appearing as sibling fights.
    """
    keystone_fights = [fight for fight in fights if fight.get("keystoneLevel") is not None]

    if fight_id is not None:
        for fight in keystone_fights:
            if fight["id"] == fight_id:
                return fight
        raise IngestError(f"Fight {fight_id} is not a Mythic+ run in this report")

    if not keystone_fights:
        raise IngestError("This report contains no Mythic+ run")
    if len(keystone_fights) > 1:
        ids = ", ".join(str(fight["id"]) for fight in keystone_fights)
        raise IngestError(f"This report holds several Mythic+ runs ({ids}); pass --fight")
    return keystone_fights[0]


def _build_players(fight: dict[str, Any], actors: list[dict[str, Any]]) -> tuple[Player, ...]:
    by_id = {actor["id"]: actor for actor in actors}
    ids = fight.get("friendlyPlayers") or []
    specs = fight.get("friendlySpecs") or []
    item_levels = fight.get("friendlyItemLevels") or []

    players = []
    for position, actor_id in enumerate(ids):
        actor = by_id.get(actor_id)
        if actor is None:
            continue
        players.append(
            Player(
                actor_id=actor_id,
                name=actor["name"],
                class_name=actor["subType"],
                spec=specs[position] if position < len(specs) else "",
                item_level=item_levels[position] if position < len(item_levels) else 0,
            )
        )
    return tuple(players)


def _build_pulls(fight: dict[str, Any]) -> tuple[Pull, ...]:
    pulls = []
    for index, raw in enumerate(fight.get("dungeonPulls") or []):
        pulls.append(
            Pull(
                index=index,
                pull_id=raw["id"],
                name=raw["name"],
                encounter_id=raw["encounterID"],
                start_ms=raw["startTime"],
                end_ms=raw["endTime"],
                killed=bool(raw.get("kill")),
                x=raw.get("x") or 0,
                y=raw.get("y") or 0,
                enemies=tuple(
                    EnemyNpc(actor_id=npc["id"], game_id=npc["gameID"])
                    for npc in (raw.get("enemyNPCs") or [])
                ),
            )
        )
    return tuple(pulls)


def build_run(report: dict[str, Any], fight: dict[str, Any]) -> Run:
    actors = report.get("masterData", {}).get("actors") or []
    raw_counts = fight.get("npcCountMap") or {}

    return Run(
        report_code=report["code"],
        fight_id=fight["id"],
        dungeon_name=fight["name"],
        keystone_level=fight["keystoneLevel"],
        affix_ids=tuple(fight.get("keystoneAffixes") or ()),
        keystone_time_ms=fight.get("keystoneTime") or 0,
        keystone_bonus=fight.get("keystoneBonus") or 0,
        count_reached=fight.get("countReached") or 0,
        count_required=fight.get("countRequired") or 0,
        # npcCountMap arrives as a JSON object, so its keys are strings.
        npc_count_map={int(game_id): count for game_id, count in raw_counts.items()},
        players=_build_players(fight, actors),
        pulls=_build_pulls(fight),
    )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests -v && uv run mypy src`
Expected: 22 passed, mypy clean.

- [ ] **Step 7: Commit**

```bash
git add src/wowperf/adapters/wcl/ingest.py src/wowperf/adapters/wcl/queries.py \
        tests/adapters/wcl/test_ingest.py tests/adapters/wcl/fixtures
git commit -m "Translate a Warcraft Logs report into the run model

Confine every Warcraft Logs field name to one module, so the untyped JSON
these endpoints return is validated at the boundary instead of leaking
its shape into the analysers."
```

---

### Task 10: Ingest deaths and casts

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py`, `src/wowperf/adapters/wcl/ingest.py`
- Test: `tests/adapters/wcl/test_ingest_events.py`

**Interfaces:**
- Consumes: `Run` and `Pull` from Task 2, `Death` and `CastEvent` from Task 3.
- Produces:
  - `queries.DEATHS_QUERY`, `queries.CASTS_QUERY`
  - `def pull_index_at(run: Run, timestamp_ms: int) -> int | None`
  - `def build_casts(events: list[dict[str, Any]], run: Run, ability_names: dict[int, str]) -> tuple[CastEvent, ...]`
  - `def build_deaths(events: list[dict[str, Any]], run: Run, casts: tuple[CastEvent, ...], ability_names: dict[int, str]) -> tuple[Death, ...]`

- [ ] **Step 1: Write the failing tests**

`tests/adapters/wcl/test_ingest_events.py`:

```python
# ABOUTME: Integration tests for turning event payloads into deaths and casts.
# ABOUTME: Covers pull attribution and the measured cost of a death in seconds not played.

from typing import Any

from wowperf.adapters.wcl.ingest import build_casts, build_deaths, pull_index_at
from wowperf.domain.model import EnemyNpc, Player, Pull, Run

ABILITY_NAMES = {700: "Frostbolt", 900: "Void Bolt"}


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=1000, end_ms=5000,
             killed=True, x=0, y=0, enemies=(EnemyNpc(actor_id=1, game_id=5001),)),
        Pull(index=1, pull_id=2, name="Boss", encounter_id=99001, start_ms=9000, end_ms=20000,
             killed=True, x=0, y=0, enemies=(EnemyNpc(actor_id=2, game_id=6001),)),
    )
    return Run(
        report_code="abc123", fight_id=2, dungeon_name="Murder Row", keystone_level=12,
        affix_ids=(), keystone_time_ms=1_800_000, keystone_bonus=1,
        count_reached=800, count_required=800, npc_count_map={},
        players=(Player(actor_id=11, name="Frostie", class_name="Mage", spec="Frost",
                        item_level=300),),
        pulls=pulls,
    )


def test_a_timestamp_inside_a_pull_resolves_to_its_index() -> None:
    assert pull_index_at(a_run(), 3000) == 0
    assert pull_index_at(a_run(), 12000) == 1


def test_a_timestamp_between_pulls_belongs_to_no_pull() -> None:
    assert pull_index_at(a_run(), 7000) is None


def test_casts_are_named_and_attributed_to_a_pull() -> None:
    events: list[dict[str, Any]] = [
        {"type": "cast", "sourceID": 11, "abilityGameID": 700, "timestamp": 3000}
    ]
    casts = build_casts(events, a_run(), ABILITY_NAMES)
    assert (casts[0].ability_name, casts[0].pull_index) == ("Frostbolt", 0)


def test_an_unknown_ability_id_falls_back_to_its_number() -> None:
    events: list[dict[str, Any]] = [
        {"type": "cast", "sourceID": 11, "abilityGameID": 12345, "timestamp": 3000}
    ]
    assert build_casts(events, a_run(), ABILITY_NAMES)[0].ability_name == "Unknown ability 12345"


def test_a_death_records_its_killing_blow_and_pull() -> None:
    events: list[dict[str, Any]] = [
        {"type": "death", "targetID": 11, "timestamp": 12000, "killingBlow": {"abilityGameID": 900},
         "overkill": 4200}
    ]
    death = build_deaths(events, a_run(), (), ABILITY_NAMES)[0]
    assert (death.player_name, death.killing_blow, death.overkill, death.pull_index) == (
        "Frostie",
        "Void Bolt",
        4200,
        1,
    )


def test_the_cost_of_a_death_is_measured_to_the_players_next_cast() -> None:
    casts = build_casts(
        [
            {"type": "cast", "sourceID": 11, "abilityGameID": 700, "timestamp": 11000},
            {"type": "cast", "sourceID": 11, "abilityGameID": 700, "timestamp": 45000},
        ],
        a_run(),
        ABILITY_NAMES,
    )
    events: list[dict[str, Any]] = [
        {"type": "death", "targetID": 11, "timestamp": 12000, "killingBlow": {"abilityGameID": 900},
         "overkill": 0}
    ]
    death = build_deaths(events, a_run(), casts, ABILITY_NAMES)[0]
    assert death.seconds_until_next_action == 33.0


def test_a_death_with_no_later_cast_has_no_measured_cost() -> None:
    events: list[dict[str, Any]] = [
        {"type": "death", "targetID": 11, "timestamp": 12000, "killingBlow": {"abilityGameID": 900},
         "overkill": 0}
    ]
    assert build_deaths(events, a_run(), (), ABILITY_NAMES)[0].seconds_until_next_action is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/adapters/wcl/test_ingest_events.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_casts'`

- [ ] **Step 3: Add the queries**

Append to `src/wowperf/adapters/wcl/queries.py`:

```python
DEATHS_QUERY = """
query Deaths($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code) {
      events(
        dataType: Deaths
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

CASTS_QUERY = """
query Casts($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code) {
      events(
        dataType: Casts
        hostilityType: Friendlies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

ABILITIES_QUERY = """
query Abilities($code: String!) {
  reportData {
    report(code: $code) {
      masterData(translate: true) {
        abilities { gameID name }
      }
    }
  }
}
"""
```

- [ ] **Step 4: Write the implementation**

Append to `src/wowperf/adapters/wcl/ingest.py`, and add
`from wowperf.domain.events import CastEvent, Death` to its imports:

```python
def pull_index_at(run: Run, timestamp_ms: int) -> int | None:
    """Which pull was underway at this moment, or None if the group was between pulls."""
    for pull in run.pulls:
        if pull.start_ms <= timestamp_ms <= pull.end_ms:
            return pull.index
    return None


def _ability_name(ability_names: dict[int, str], ability_id: int) -> str:
    return ability_names.get(ability_id, f"Unknown ability {ability_id}")


def build_casts(
    events: list[dict[str, Any]], run: Run, ability_names: dict[int, str]
) -> tuple[CastEvent, ...]:
    return tuple(
        CastEvent(
            actor_id=event["sourceID"],
            ability_id=event["abilityGameID"],
            ability_name=_ability_name(ability_names, event["abilityGameID"]),
            timestamp_ms=event["timestamp"],
            pull_index=pull_index_at(run, event["timestamp"]),
        )
        for event in events
        if event.get("type") == "cast" and "sourceID" in event
    )


def build_deaths(
    events: list[dict[str, Any]],
    run: Run,
    casts: tuple[CastEvent, ...],
    ability_names: dict[int, str],
) -> tuple[Death, ...]:
    """Build deaths, measuring the real cost as time until the player acted again.

    The timer penalty understates a death. The seconds a player spent unable to
    contribute is observable, so we measure that instead of estimating a run-back.
    """
    names = {player.actor_id: player.name for player in run.players}
    casts_by_actor: dict[int, list[int]] = {}
    for cast in casts:
        casts_by_actor.setdefault(cast.actor_id, []).append(cast.timestamp_ms)

    deaths = []
    for event in events:
        if event.get("type") != "death":
            continue

        actor_id = event["targetID"]
        timestamp = event["timestamp"]
        later = [stamp for stamp in casts_by_actor.get(actor_id, []) if stamp > timestamp]
        killing_blow = event.get("killingBlow") or {}

        deaths.append(
            Death(
                player_name=names.get(actor_id, f"Actor {actor_id}"),
                actor_id=actor_id,
                timestamp_ms=timestamp,
                killing_blow=_ability_name(
                    ability_names, killing_blow.get("abilityGameID", 0)
                ),
                overkill=event.get("overkill") or 0,
                pull_index=pull_index_at(run, timestamp),
                seconds_until_next_action=(min(later) - timestamp) / 1000 if later else None,
            )
        )
    return tuple(deaths)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests -v && uv run mypy src`
Expected: 29 passed, mypy clean.

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/adapters/wcl/ingest.py src/wowperf/adapters/wcl/queries.py \
        tests/adapters/wcl/test_ingest_events.py
git commit -m "Ingest deaths and casts, and measure what a death actually cost

The five-second timer penalty understates a death badly. Time from the
death to that player's next cast is observable, so measure it rather than
estimating a run-back."
```

---

### Task 11: Repository, URL parsing, and the fetch command

**Files:**
- Create: `src/wowperf/urls.py`, `src/wowperf/adapters/wcl/repository.py`, `src/wowperf/cli.py`
- Test: `tests/test_urls.py`, `tests/adapters/wcl/test_repository.py`, `tests/e2e/test_fetch_e2e.py`

**Interfaces:**
- Consumes: everything from Tasks 2 through 10.
- Produces:
  - `def parse_report_url(value: str) -> tuple[str, int | None]`
  - `class WclRunRepository(client: WclClient, cache: DiskCache)` satisfying `RunRepository`
  - `wowperf fetch <url>` writing the run as JSON to stdout

- [ ] **Step 1: Write the failing URL tests**

`tests/test_urls.py`:

```python
# ABOUTME: Behaviour tests for turning what a user pastes into a report code and fight ID.
# ABOUTME: People paste full URLs with fragments, so bare codes and fragments both parse.

import pytest

from wowperf.urls import parse_report_url


def test_a_bare_report_code_parses_with_no_fight() -> None:
    assert parse_report_url("aBc123XyZ") == ("aBc123XyZ", None)


def test_a_report_url_yields_its_code() -> None:
    assert parse_report_url("https://www.warcraftlogs.com/reports/aBc123XyZ") == (
        "aBc123XyZ",
        None,
    )


def test_a_fight_fragment_is_read() -> None:
    assert parse_report_url("https://www.warcraftlogs.com/reports/aBc123XyZ#fight=7") == (
        "aBc123XyZ",
        7,
    )


def test_a_last_fight_fragment_means_no_explicit_fight() -> None:
    assert parse_report_url("https://www.warcraftlogs.com/reports/aBc123XyZ#fight=last") == (
        "aBc123XyZ",
        None,
    )


def test_something_that_is_not_a_report_is_rejected() -> None:
    with pytest.raises(ValueError, match="not a Warcraft Logs report"):
        parse_report_url("https://example.com/nope")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_urls.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.urls'`

- [ ] **Step 3: Write the URL parser**

`src/wowperf/urls.py`:

```python
# ABOUTME: Turns whatever a user pastes into a report code and an optional fight ID.
# ABOUTME: Accepts a bare code or a full report URL, with or without a #fight fragment.

import re

REPORT_PATTERN = re.compile(
    r"^(?:https?://[^/]*warcraftlogs\.com/reports/)?(?P<code>[A-Za-z0-9]{6,})"
    r"(?:[/?][^#]*)?(?:#.*?fight=(?P<fight>\d+|last).*)?$"
)


def parse_report_url(value: str) -> tuple[str, int | None]:
    match = REPORT_PATTERN.match(value.strip())
    if match is None:
        raise ValueError(f"{value!r} is not a Warcraft Logs report code or URL")

    fight = match.group("fight")
    return match.group("code"), int(fight) if fight and fight != "last" else None
```

- [ ] **Step 4: Run the URL tests**

Run: `uv run pytest tests/test_urls.py -v`
Expected: 5 passed.

- [ ] **Step 5: Write the failing repository test**

`tests/adapters/wcl/test_repository.py`:

```python
# ABOUTME: Integration test wiring client, cache and ingest into a RunRepository.
# ABOUTME: Confirms a second get is served from the cache rather than the network.

import json
from pathlib import Path
from typing import Any

import httpx

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.domain.ports import RunRepository

FIXTURE = Path(__file__).parent / "fixtures" / "report_fights.json"


def build_repository(tmp_path: Path, calls: list[str]) -> WclRunRepository:
    fights = json.loads(FIXTURE.read_text(encoding="utf-8"))
    empty_events: dict[str, Any] = {
        "reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}
    }
    abilities = {"reportData": {"report": {"masterData": {"abilities": []}}}}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        query = json.loads(request.content)["query"]
        name = query.split("query ")[1].split("(")[0].strip()
        calls.append(name)
        if name == "Fights":
            return httpx.Response(200, json={"data": fights})
        if name == "Abilities":
            return httpx.Response(200, json={"data": abilities})
        return httpx.Response(200, json={"data": empty_events})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRunRepository(client, DiskCache(tmp_path))


def test_the_repository_builds_a_run_from_the_api(tmp_path: Path) -> None:
    repository: RunRepository = build_repository(tmp_path, [])
    run = repository.get("abc123", None)
    assert (run.dungeon_name, run.keystone_level, len(run.pulls)) == ("Murder Row", 12, 2)


def test_a_second_get_makes_no_further_calls(tmp_path: Path) -> None:
    calls: list[str] = []
    repository = build_repository(tmp_path, calls)
    repository.get("abc123", None)
    first_call_count = len(calls)
    repository.get("abc123", None)
    assert len(calls) == first_call_count
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/adapters/wcl/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.adapters.wcl.repository'`

- [ ] **Step 7: Write the repository**

`src/wowperf/adapters/wcl/repository.py`:

```python
# ABOUTME: Assembles a Run from Warcraft Logs, caching every response it fetches.
# ABOUTME: Satisfies the RunRepository port so services never learn where a run came from.

from typing import Any

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.ingest import build_casts, build_deaths, build_run, select_keystone_fight
from wowperf.adapters.wcl.pagination import fetch_all_events
from wowperf.adapters.wcl.queries import (
    ABILITIES_QUERY,
    CASTS_QUERY,
    DEATHS_QUERY,
    FIGHTS_QUERY,
)
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.model import Run


class LoadedRun:
    """A run together with the event streams the analysers need."""

    def __init__(self, run: Run, casts: tuple[CastEvent, ...], deaths: tuple[Death, ...]) -> None:
        self.run = run
        self.casts = casts
        self.deaths = deaths


class WclRunRepository:
    def __init__(self, client: WclClient, cache: DiskCache) -> None:
        self._client = client
        self._cache = cache

    def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        return self._cache.get_or_fetch(
            cache_key(query, variables),
            lambda: self._client.execute(query, variables),
        )

    def get(self, report_code: str, fight_id: int | None) -> Run:
        return self.load(report_code, fight_id).run

    def load(self, report_code: str, fight_id: int | None) -> LoadedRun:
        report = self._query(FIGHTS_QUERY, {"code": report_code})["reportData"]["report"]
        fight = select_keystone_fight(report["fights"], fight_id)
        run = build_run(report, fight)

        abilities = self._query(ABILITIES_QUERY, {"code": report_code})
        ability_names = {
            ability["gameID"]: ability["name"]
            for ability in abilities["reportData"]["report"]["masterData"]["abilities"]
        }

        event_variables = {
            "code": report_code,
            "fightId": run.fight_id,
            "startTime": float(fight["startTime"]),
            "endTime": float(fight["endTime"]),
        }
        cast_events = fetch_all_events(self._query, CASTS_QUERY, event_variables)
        death_events = fetch_all_events(self._query, DEATHS_QUERY, event_variables)

        casts = build_casts(cast_events, run, ability_names)
        deaths = build_deaths(death_events, run, casts, ability_names)
        return LoadedRun(run, casts, deaths)
```

- [ ] **Step 8: Run the repository test**

Run: `uv run pytest tests/adapters/wcl/test_repository.py -v`
Expected: 2 passed.

- [ ] **Step 9: Write the CLI**

`src/wowperf/cli.py`:

```python
# ABOUTME: Command-line entry point; the driving adapter that wires ports to implementations.
# ABOUTME: Holds no analysis logic, only construction, argument handling and output.

import os
from pathlib import Path

import httpx
import typer

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.urls import parse_report_url

app = typer.Typer(help="Analyse World of Warcraft logs and report what to improve.")

DEFAULT_CACHE_DIR = Path("cache")


def build_repository(cache_dir: Path) -> WclRunRepository:
    client_id = os.environ.get("WCL_CLIENT_ID")
    client_secret = os.environ.get("WCL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise typer.BadParameter(
            "Set WCL_CLIENT_ID and WCL_CLIENT_SECRET. "
            "Create a client at https://www.warcraftlogs.com/api/clients/"
        )

    http = httpx.Client(timeout=60.0)
    return WclRunRepository(
        WclClient(TokenProvider(client_id, client_secret, http), http),
        DiskCache(cache_dir),
    )


@app.command()
def fetch(
    report: str = typer.Argument(..., help="Report URL or code"),
    fight: int | None = typer.Option(None, help="Fight ID; defaults to the only keystone run"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Where to cache API responses"),
) -> None:
    """Fetch a Mythic+ run and print it as JSON."""
    code, fight_from_url = parse_report_url(report)
    run = build_repository(cache_dir).get(code, fight if fight is not None else fight_from_url)
    typer.echo(run.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
```

- [ ] **Step 10: Write the end-to-end test**

`tests/e2e/test_fetch_e2e.py`:

```python
# ABOUTME: End-to-end test against the real Warcraft Logs API; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.cli import build_repository
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_report_becomes_a_run(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this test"
        )

    code, fight = parse_report_url(REPORT)
    run = build_repository(tmp_path).get(code, fight)

    assert run.keystone_level > 0
    assert run.pulls, "a Mythic+ run should have dungeon pulls"
    assert len(run.players) == 5
    assert run.count_required > 0
```

```bash
mkdir -p tests/e2e && touch tests/e2e/__init__.py
```

- [ ] **Step 11: Run the offline suite, then the end-to-end test**

Run: `uv run pytest -v && uv run ruff check . && uv run mypy src`
Expected: 36 passed, e2e deselected, lint and types clean.

Then, with real credentials and a public Mythic+ report:

```bash
WCL_CLIENT_ID=... WCL_CLIENT_SECRET=... \
WOWPERF_E2E_REPORT='https://www.warcraftlogs.com/reports/<code>' \
uv run pytest -m e2e -v
```

Expected: PASS. If it fails, read the error before changing code: a `WclError` naming a field means the query is wrong; an `IngestError` means the report holds no Mythic+ run.

- [ ] **Step 12: Record the measured point cost**

Run the fetch once against a real report with an empty cache, and read the quota before and after:

```bash
WCL_CLIENT_ID=... WCL_CLIENT_SECRET=... uv run wowperf fetch '<url>' --cache-dir /tmp/wowperf-measure
```

Add the observed `limitPerHour` and the points a single fetch consumed to §11 of the design
document, replacing the note that the figures are unconfirmed. This closes the first open item
in the spec.

- [ ] **Step 13: Commit**

```bash
git add src/wowperf/urls.py src/wowperf/adapters/wcl/repository.py src/wowperf/cli.py \
        tests/test_urls.py tests/adapters/wcl/test_repository.py tests/e2e \
        docs/plans/2026-09-03-mplus-postmortem-design.md
git commit -m "Fetch a real Mythic+ run end to end

Wire the client, cache and ingest behind the RunRepository port and expose
it as a command, so the analysis plan starts from a working fetch rather
than from an interface nobody has exercised.

Record the measured hourly point budget in the design, replacing the
archived figure research could not confirm."
```

---

## Plan Self-Review

**Spec coverage.** This plan implements spec §3.1 steps 1 to 6 (fetch and ingest), §3.2 (hand-written queries, Pydantic at the boundary), §3.3 (cache and quota instrumentation), §3.4 (`uv`), §4 (domain model), §9 (test layers), and the first item of §11 (measure the real point budget).

Deliberately deferred, each to a named plan: §5 analyzers to Plan B, §6 comparison to Plan C, §7 report and §8 skills to Plan D. Spec §3.5 (season data resolved from the API) and §3.6 (the full CLI surface) arrive with the commands that need them; this plan ships only `fetch`.

**Known gap, carried forward.** `data/season.toml` from spec §3.5 has no task here because nothing in this plan reads a death penalty. Plan B's time-decomposition task creates it.
