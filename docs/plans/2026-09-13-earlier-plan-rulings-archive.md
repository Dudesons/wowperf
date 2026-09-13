# Rulings from five earlier plans — archive

**Status:** Archived 2026-09-13. A record, not guidance.

Five plans between 2026-09-03 and 2026-09-10 were executed under
`superpowers:subagent-driven-development`, each out of a gitignored scratch workspace under
`.superpowers/sdd/`. Those workspaces held the only copy of the controller's rulings, and
nothing in git held them. They have been deleted; the rulings are copied here verbatim
first.

**Read this for what it is.** Unlike
[`2026-09-13-comparison-table-rulings.md`](2026-09-13-comparison-table-rulings.md), which
records live obligations — a deliberate duplication whose collateral is one named test, a
missing zero-guard that is load-bearing — almost every ruling below is a transient
plan-correction. The plan's snippet named a function that does not exist; use the real name.
The import would trip ruff; move it. Their own cost-if-wrong clauses say so: *"a red gate,
caught immediately"*, *"caught on the first run"*, *"none"*. They are kept because they were
the only copy and deleting them would have been a choice nobody made deliberately, not
because a reader needs them.

If you are looking for what constrains the comparison code today, the other document is the
one you want.

**What was dropped.** Each workspace also held per-task briefs and reports, review diffs,
and fix reports. The diffs are `git diff A..B` between commits that are still in history, so
they reconstruct exactly. The briefs and reports record how the work was done, which the
commits carry. The fix reports describe code that has since changed.

**What survives elsewhere.** Two durable facts from these ledgers are already recorded where
they are actually needed: the `uv python install` failure on this machine and the
interpreter's relocation, and the Warcraft Logs quota measurements.

The passages below are copied from each ledger without editing, each bounded to the ruling
and the lines around it. Some carry a little of the surrounding task log; that is the cost of
copying rather than paraphrasing, and the cheaper mistake.

---

## The Mythic+ foundation — `2026-09-03-mplus-foundation-plan`


3 ruling passages, copied verbatim from the ledger.


- Ruling: `ports.py` may import `pathlib.Path` — the constraint bans I/O, and a type
  annotation performs none. The plan text mandates the signature and the spec §4 declares
  the port. Cost if wrong: a cosmetic import to move behind `TYPE_CHECKING` later.
- Ruling: keep `RankingRepository` and `ReportRenderer` in Task 4 despite having no caller
  in Plan A. The spec declares all three ports as one seam and Plans C and D consume them;
  splitting the seam across plans would churn `ports.py` twice. Cost if wrong: ~15 lines of
  unused Protocol until Plan C.
- Ruling: implementers use `export PATH="$HOME/.local/bin:$PATH"` rather than installing uv
  or adding it to the user's system PATH. Modifying the user's PATH is a side effect outside
  this worktree. Cost if wrong: none; the export is local to each command.
- Ruling: work happens on branch `plan-a-foundation`, not `master`. The skill forbids
  implementing on master without consent and no consent was given for master specifically.
  Cost if wrong: one merge at the end.


Task 1: complete (commits d90527c..849e73d, review clean)
Task 1: minor (deferred): the `.gitignore` anchoring fix (`cache/` -> `/cache/`) was folded
  into the scaffolding commit rather than committed separately; the brief's `git add` list
  did not include `.gitignore`. Reviewer and controller both agree the fix was a precondition
  for staging `src/wowperf/adapters/cache/__init__.py` at all.
Task 1: Ruling: the implementer pinned the project interpreter under
  `AppData\Local\Temp\uv-python-installs` via `UV_PYTHON_INSTALL_DIR` to dodge a real uv bug
  (reproduced: `uv python install 3.12` fails with "Missing expected target directory for
  Python minor version link at ...AppData\Roaming\uv\python"). Temp is purged by Windows, so
  I moved the interpreter to `C:\Users\damien\.uv-python` and repointed `.venv` at it. The
  gate now passes with no environment variable set at all — later tasks need only the PATH
  export. Cost if wrong: none committed; `.venv/` and the interpreter are both untracked.
  Carry forward: a fresh `uv sync` on a machine with no 3.12 will hit the uv bug again; that
  belongs in CLAUDE.md or a README, not in Plan A's scope.
Task 2: complete (commits 849e73d..d73c85b, review clean)
Task 2: minor (deferred): `Pull.signature` is a sorted multiset, duplicates preserved
  (model.py:64-66, asserted at test_model.py:159-160). Intentional and correct for Plan C's
  difflib pull alignment, but any later code assuming uniqueness will be wrong.
Task 2: minor (deferred): no test covers `total_pull_seconds` / `boss_pulls` / `trash_pulls`
  over an empty `pulls` tuple. Behaviour is safe (sum of empty is 0.0, tuple of empty is ()),
  and the brief did not ask for it. Task 4 calls `a_run(())`, so the empty case is exercised
  indirectly there.
Task 3: review found 2 Important, both plan-mandated. Commit body verified against the
  brief by the controller (the reviewer's one ⚠️): exact match, resolved, not a gap.
Task 3: Ruling: the `Frozen` duplication is real and compounds, so fix it rather than let
  Plan B's domain modules inherit a third and fourth copy. Extract `Frozen` into a new
  `src/wowperf/domain/base.py` and have `model.py`, `events.py` and `findings.py` import it.
  Chose a new module over `from wowperf.domain.model import Frozen` because `findings.py`
  has no semantic dependency on the run structure and a later reviewer would rightly flag
  that import. Cost if wrong: one 4-line file more than the plan's File Structure table
  lists, and a touch to Task 2's committed `model.py`.
Task 3: Ruling: the weak stability test is a real gap, not a style quibble — it asserts
  stable ordering with a single untimed finding, so nothing is stable among anything. Widen
  it to two untimed findings so a non-stable sort would actually fail. Cost if wrong: three
  extra lines of test.
Task 3: fix round 1/5 (2 addressed, 0 open; commits e28c3a6..29d70be)
Task 3: complete (commits d73c85b..29d70be, review clean)
Task 3: minor (deferred): `rank_findings` has no test for an empty iterable, a generator
  input, or ties among untimed findings. Implementation handles all three correctly.
Task 3: environment note: an earlier subagent left two zero-byte artifacts at the repo root
  with a mangled literal Windows path,
  `C:Usersdamienclaude_persowow_perftestsdomain__init__.py` and its directory. Untracked,
  empty, harmless. Removal was denied by the permission layer; flag to RwlRwlRwlRwl at the end.
Task 4: review found 1 Important (plan-mandated). Commit body verified by the controller
  against the brief (the reviewer's one ⚠️): exact match, resolved.
Task 4: Ruling: the port-conformance test is genuinely inert — `[tool.mypy] files = ["src"]`
  means the `repository: RunRepository = InMemoryRunRepository(...)` annotation is never
  type-checked, and the Protocol is not `@runtime_checkable`, so neither pytest nor mypy
  catches a port/fake divergence. Fix by widening the gate: `files = ["src", "tests"]` in
  pyproject and `uv run mypy` (no argument) as the command, rather than `@runtime_checkable`
  + isinstance, which only compares method names and would miss a signature change.
  Verified before ruling: `mypy --strict src tests` already passes but for one unused
  `type: ignore` at tests/domain/test_model.py:74, so the cost today is one line.
  Consequence carried forward: every later task's test files are now type-checked under
  strict, which every remaining dispatch must say. Cost if wrong: extra annotations in the
  Task 9/10 fixture-heavy tests.
Task 4: fix round 1/5 (1 addressed, 0 open; commits fd876c7..32b5a26)
Task 4: complete (commits 29d70be..32b5a26, review clean)
Task 4: minor (deferred): no test constructs a `RunRef` directly to confirm it is actually
  frozen. Cheap to add later; `Frozen` inheritance is verified for the other models.
Task 4: gate change in force from here: `[tool.mypy] files = ["src", "tests"]`, command is
  `uv run mypy` with no argument. Test files are now type-checked under strict. CLAUDE.md's
  Commands table row was corrected from the nonexistent `uv run mypy wowperf`.
Task 5: review found 1 Important (plan-mandated), verdict otherwise Approved. Commit body
  verified by the controller against the brief (reviewer ⚠️ #1): exact match, resolved.
  Reviewer ⚠️ #2 (does any domain module import this adapter?) resolved by the controller:
  the diff adds no domain file and `uv run mypy` over src+tests passes, so no such import
  exists; the invariant is checked properly at the final whole-branch review.
Task 5: Ruling: fix the non-atomic cache write. `TokenProvider._fetch` assigns `self._token`
  before parsing `expires_in`, so a 200 response carrying `access_token` but no `expires_in`
  overwrites a still-valid cached token and leaves `_expires_at` stale. Narrow — it
  self-corrects on the next call — but this is the auth path, the fix is two lines, and the
  brief's own code is what is wrong. Also add the two boundary tests the reviewer named as
  Minor (non-200, and 200-missing-`expires_in`), because without them nothing pins the
  atomicity we are about to claim. Cost if wrong: ~10 lines of test and a two-line reshuffle
  that cannot change the happy path.
Task 5: fix round 1/5 (1 addressed, 0 open; commits b1b709a..43a71a4)
Task 5: complete (commits 32b5a26..43a71a4, review clean)
Task 5: minor (deferred): the refresh-margin test never pins the exact boundary
  (`now == expires_at - REFRESH_MARGIN_SECONDS`, which `<` should treat as stale). It covers
  3000 (fresh) and 3550 (stale) around a 3540 boundary.
Task 5: minor (deferred): empty `tests/**/__init__.py` marker files carry no ABOUTME header.
  Consistent with `tests/domain/__init__.py` from Task 2 and with the plan's own steps; the
  global rule's wording just does not carve out zero-content marker files.
Task 6: complete (commits 43a71a4..d34bca9, review clean)
Task 6: minor (deferred): a 200 response with neither `data` nor `errors` falls through to
  `payload["data"]` and raises a bare `KeyError` rather than a `WclError`. Loud, not silent,
  but callers cannot catch it via `WclError`. Inherited from the brief's own code.
Task 6: minor (deferred): no test covers a 200 carrying both partial `data` and `errors`.
  The code is correct by inspection (checks `errors` first, raises), just unverified.
Task 7: complete (commits d34bca9..41a27b7, review clean)
Task 7: commit body verified by the controller against the brief (reviewer ⚠️ #1): exact
  match. Reviewer ⚠️ #2 is a brief-internal inconsistency, not a code defect: the brief's
  Interfaces block types `cache_key`'s `variables` as `dict[str, object]` while its Step 3
  code says `dict[str, Any]`. The implementer followed the code. Ruling: leave it — Task 8's
  `fetch_all_events` and Task 11's repository both pass `dict[str, Any]`, so `Any` is the
  consistent choice. Cost if wrong: a one-word annotation change.
Task 7: minor (deferred): writes are non-atomic (`write_text`, no temp-file-plus-rename). A
  process killed mid-write leaves a truncated file; the next read then raises
  `json.JSONDecodeError` — loud, not silent. The brief deliberately named no lock or index.
Task 7: minor (deferred): a cache file that is valid JSON but the wrong shape (an array, say)
  passes `cast(dict[str, Any], ...)` unchecked and reaches the caller as the wrong type.
Task 7: minor (deferred): `get_or_fetch` does not validate that `key` is a safe hex digest.
  The only producer today is `cache_key`, whose SHA-256 hexdigest cannot escape the directory.
Task 8: complete (commits 41a27b7..a2ee7d7, review clean)
Task 8: commit body verified by the controller against the brief (reviewer ⚠️): exact match.
Task 8: minor (deferred): `payload["reportData"]["report"]["events"]` and `page["data"]` use
  direct indexing, so a malformed page raises a bare `KeyError` with no context. Loud, not a
  silent truncation. Same shape as the Task 6 minor.
Task 8: minor (deferred): no test covers `nextPageTimestamp` absent from the payload
  entirely (only explicit null). `.get()` makes the two identical; the `is None` check also
  correctly keeps paging on a timestamp of `0`, which is the hazard that mattered.
Task 8: the two "verbatim deviations" the reviewer flagged (a `list[dict[str, Any]]`
  annotation in the test and a three-line signature wrap) are forced by the gate I widened
  in Task 4 and by ruff's line length. Not findings.
Task 9: review found 2 Important, both plan-mandated.
Task 9: Ruling: enforce `kill == true` in `select_keystone_fight`. Design line 72 is explicit
  ("A complete Mythic+ run is one `ReportFight` with `keystoneLevel != null` and
  `kill == true`") and the design is the binding authority over the plan's code. Verified
  before ruling that `kill` is already requested by FIGHTS_QUERY (queries.py:28) and already
  present in the fixture, so this costs a filter and tests, not a schema change. Without it
  an abandoned key is analysed as a completed run and every "seconds lost" number is
  measured against a run that never finished. Give the two new rejections their own wording
  rather than reusing "contains no Mythic+ run", so a user who pastes an abandoned key is
  told why. Cost if wrong: a user wanting to analyse an abandoned key gets a clear error
  instead of a report, and we add an opt-in flag in a later plan.
Task 9: Ruling: add the missing test for the several-keystone-runs branch, and build its
  fight list inline rather than adding a second completed keystone fight to the shared
  fixture, which would break the single-fight happy paths. Same for the abandoned-key cases.
  Cost if wrong: a few lines of inline test data instead of fixture data.
Task 9: fix round 1/5 (2 addressed, 0 open; commits ae56be3..9e76bd1)
Task 9: complete (commits a2ee7d7..9e76bd1, review clean)
Task 9: minor (deferred): a `friendlyPlayers` id with no matching actor in `masterData.actors`
  is silently skipped rather than raising, understating the roster with no signal. Requires
  the API to return inconsistent data; Task 11's e2e run is where that would first show.
Task 9: minor (deferred): the `or []` / `or {}` fallbacks for a missing `npcCountMap`, empty
  `dungeonPulls` or empty `friendlyPlayers` are never exercised by a test.
Task 10: complete (commits 9e76bd1..5fefe81, review clean)
Task 10: minor (deferred): `pull_index_at` boundary cases are untested — a timestamp exactly
  equal to a pull's `start_ms` or `end_ms` (both inclusive), before the first pull, and after
  the last. Behaviour is correct by inspection; only the gap and the tie case below are
  unpinned.
Task 10: minor (deferred): a cast at exactly the death timestamp is excluded by the strict
  `>` filter, so a death whose only later cast is simultaneous reports `None` rather than
  `0.0`. Deliberate, untested.
Task 11: review found 2 Important, both plan-mandated.
Task 11: Ruling: fix the Typer single-command collapse. `wowperf fetch <url>` does not work
  (confirmed by running `uv run wowperf --help`: usage is `wowperf [OPTIONS] {report}`), yet
  both the plan's Interfaces block and the design's CLI contract promise a named subcommand,
  and the design's §3.6 surface adds more commands later. Add a no-op `@app.callback()`,
  which is Typer's documented way to keep subcommand mode with one command. Cost if wrong:
  one trivial function; `wowperf <url>` stops working, which nothing documents anyway.
Task 11: Ruling: add offline CLI-dispatch tests. The whole suite bypasses argument parsing,
  which is exactly the layer the defect lived in — a suite that never invokes the CLI as a
  user does cannot catch this class of bug, and Plan D adds more commands to the same
  surface. Verified `fetch` parses the URL and checks credentials before constructing any
  `httpx.Client`, so `CliRunner` tests are safe offline and spend no quota. Cost if wrong:
  three small tests.
Task 11: fix round 1/5 (2 addressed, 0 open; commits df10c80..ad54f57)
Task 11: complete (commits 5fefe81..ad54f57, review clean)
Task 11: the implementer correctly corrected my premise: `["fetch", "--help"]` does NOT
  discriminate, because `--help` is an eager Click flag that short-circuits before positional
  validation. They verified by reverting, kept that test as a regression check, and added
  three that genuinely go red pre-fix. The re-reviewer traced all four independently and
  confirmed. Good catch — my ruling named the wrong test.
Task 11: OUTSTANDING — brief steps 11 (real-API e2e) and 12 (measure the hourly point budget
  and write it into design §11) are NOT done. They need a public Mythic+ report URL, which
  the controller does not have. Everything else in Task 11 shipped. `tests/e2e/test_fetch_e2e.py`
  is written and deselected by default; it fails with a clear message if `WOWPERF_E2E_REPORT`
  is unset. Design §11's first open item therefore stays open.
Task 11: minor (deferred): `parse_report_url` silently ignores a `?fight=7` query string
  (only `#fight=N` fragments are read). Real Warcraft Logs URLs use fragments, so this is
  untested rather than wrong.


Final: Ruling: the Critical (are `friendlySpecs` and `friendlyItemLevels` real `ReportFight`
  fields, or invented?) is resolved by the controller, not by a fix. I ran a live
  introspection query against the Warcraft Logs schema — the one thing no offline subagent
  could do — and both are PRESENT among ReportFight's 43 fields, alongside every other field
  the plan uses. No code change needed; the design's verified list gets them recorded so the
  question cannot recur. Cost if wrong: none, the query is authoritative.
Final: MEASURED, closing design §11's first open item: `limitPerHour` is **3600**, so the
  archived figure research could not confirm was in fact correct. `pointsSpentThisHour` read
  1 immediately after the token exchange plus one introspection query, so schema-shaped
  queries cost about 1 point. What a full `fetch` of a real report costs is still unmeasured
  and still needs a report URL.
Final: environment finding — `.env` is UTF-16 encoded (PowerShell `Out-File` default), so
  any naive UTF-8 reader sees mojibake. It does not affect the tool, which reads credentials
  from `os.environ` and never parses `.env`, but it will bite anyone who adds a dotenv loader.
Final: fix wave (12 fixes, commits ad54f57..ae90aea). Scoped re-review: all 12 ADDRESSED,
  no vacuous tests, domain purity and auth atomicity both survive, no regression.
  Verdict: ready to merge, 4 non-blocking Minors open.
Final: Ruling: take the 4 residuals rather than park them, because two of the four were
  breakage the fix wave itself introduced (`rate_limit()`'s bare `KeyError`, now on the CLI
  hot path where it escapes as a traceback; and a quota line whose "points spent" figure was
  entirely its own measurement on a cached fetch). The skill's "no second fix wave" exists to
  stop loops, not to ship self-inflicted defects, and new breakage in a fix diff joins the
  open findings by the process's own rule. Folded in two one-line doc/dead-code corrections
  while there. Commit 2cf45ba. Controller-verified rather than re-reviewed: 78 passed, ruff
  and mypy clean, `wowperf --help` lists `fetch`, a bad URL prints one line to stderr and
  exits 1. Cost if wrong: one small commit to revert.
Final: parked — a cached `fetch` now spends ~2 points on its own quota reads, where before
  it spent none. Ruling: accept. Design §3.3 requires instrumenting every phase, the budget
  is 3600/hour, and the line now says plainly that the figure includes those two reads.
  Revisit if Plan D's report loop makes repeat fetches frequent.
Final: parked — `MappingProxyType` in `Run.npc_count_map` is rebuilt on every property
  access, and Plan B's trash-efficiency analyser will index it inside a per-kill loop.
  Ruling: leave it; correctness first, and Plan B's brief should mention it.
Final: parked — `CLAUDE.md`'s `wcl-api` skill reference now points at design §2 instead, but
  the skill itself is still unwritten (Plan D).
Final: NOT DONE, needs RwlRwlRwlRwl — Task 11 steps 11 and 12's remaining half: run the e2e
  test against a real report, and measure what a full fetch costs. Needs a public Mythic+
  report URL. `limitPerHour: 3600` is measured and recorded; per-fetch cost is not.


## The analysers — `2026-09-04-mplus-analysers-plan`


7 ruling passages, copied verbatim from the ledger.


| T1 → T5 | `SeasonData.death_penalty(level)` | `decompose_time(run, deaths, season)` | agree |
| T1 → T11/T12 | `load_season_data`, `DEFAULT_SEASON_PATH` | `load_season_data()` no-arg in T12 | see Ruling 1 |
| T1 ↔ T10 | `season.py`, `toml.py`, `tests/adapters/config/test_toml.py` — T1 creates, T10 appends | `DefensiveAbility`/`Defensives`/`load_defensives` added beside T1's types | agree; T10 appends, never rewrites |
| T1 → T5 (dir) | T1 step 2 `mkdir -p src/wowperf/domain/analysis` | T5 creates `analysis/__init__.py` | harmless: an empty dir is untracked, T5 recreates it. See Ruling 2 |


| --- | --- | --- |
| T1 | test imports `DEFAULT_SEASON_PATH, load_season_data`; code defines both | agree once Ruling 1 applies |


| T7 | asserts `DERIVED`; code emits `DERIVED` (1751, 1782) | agree |
| T8 | header says `measured`; body emits `DERIVED` for the overage and `MEASURED` for per-pull | see Ruling 3 |


Ruling 1: `load_season_data` takes `path: Path = DEFAULT_SEASON_PATH`, as the Task 1 code block (line 260) and every call site say — the Interfaces summary line 96 omits the default. Why: three call sites already invoke it with no argument, and `load_defensives` is symmetric. Cost if wrong: a one-word signature edit.


Ruling 2: Task 1 may skip the `src/wowperf/domain/analysis` part of its `mkdir`; Task 5 owns that directory. Why: an empty directory is untracked, so creating it in Task 1 buys nothing. Cost if wrong: nothing — the mkdir is idempotent either way.


Ruling 3: Task 8 emits two findings with two badges — `DERIVED` for the seconds estimate of the forces overage, `MEASURED` for the per-pull forces-per-second figures. Why: the task body is explicit that the percentage is read off the fight while the seconds conversion is an estimate, and the header's single word is a section label, not a specification. Cost if wrong: one badge value, caught by the task's own asserts.


Task 1: minor (deferred): data/season.toml has a two-line comment header but not in `# ABOUTME:` form; reviewer notes the rule's wording does not carve out data files.
Task 1: complete (commits fb6628d..490883a, review clean)
Task 2: first implementer omitted `EnemyCastRow` (5 classes specified, 4 delivered); controller caught it pre-review and dispatched a second implementer, commit 39e1e4c.
Task 2: minor (deferred): the three `EnemyCastRow` tests only assert Pydantic stores what it was given; mirrors the pre-existing `Death`/`CastEvent` test style.
Task 2: minor (deferred): `InterruptEvent`, `EnemyDeath`, `DamageTakenEvent` have no tests — the brief asked for none. Gap is in the plan, not the execution.
Task 2: note for Task 7: nothing guarantees `completed_ms` and `interrupted_by` are mutually exclusive on an `EnemyCast`; the reconstruction must not produce both.
Task 2: complete (commits 490883a..39e1e4c, review clean)
Task 3: minor (deferred): no test drives an event timestamp between pulls through the four new builders (expected `pull_index=None`).
Task 3: minor (deferred): no test drives an ability id absent from `ABILITY_NAMES` through `build_enemy_cast_rows`/`build_damage_taken`.
Task 3: Ruling: `build_enemy_deaths` must raise `IngestError` naming the actor id when `actor_id not in npc_game_ids`, and keep `npc_count_map.get(game_id, 0)` as the documented zero for an NPC that awards no forces. Why: the brief's code block conflates "this NPC awards no forces" with "we could not resolve this actor", and the second is exactly Plan A's killing-blow shape — a plausible wrong value instead of a loud failure. `NPC_ACTORS_QUERY` returns every NPC actor in the report, so an unresolved id means our own fetch is wrong, not that the data is odd. Cost if wrong: a run containing an exotic actor id fails to analyse instead of silently attributing zero forces to a pull; the message names the id, and reverting is a one-line change.
Task 3: fix round 1/5 (1 addressed, 0 open — unresolved-actor conflation; commits f86fb64..a598bf7)
Task 3: complete (commits 39e1e4c..a598bf7, review clean)
Task 4: minor (deferred): `tests/adapters/wcl/test_repository.py` inlines a "Den of Nalorakk" fights payload under report code `abc123` while `report_fights.json` describes a different run under the same code; nothing enforces they stay consistent with `test_ingest_streams.py`'s `a_run()`.
Task 4: Ruling: the brief's `calls == ["Fights"]` assertion after a load-then-get on one repository is wrong, and the `_RecordingRepository` per-call rebuild that made it pass must go. Why: `FIGHTS_QUERY` is correctly keyed on the report code alone — it fetches every fight and selection is client-side — so a real `get` after a `load` costs zero queries, and rebuilding the repository per call engineered a cold cache to preserve a wrong literal. The honest invariant is stronger: after `load`, a `get` on the same cache issues nothing. Cost if wrong: the test asserts a truer property than the brief did; if fights caching ever gains a fight id in its key, the test fails loudly, which is the wanted behaviour.
Task 4: Ruling: `recording_repository` must give the event streams distinguishable non-empty payloads so `test_a_loaded_run_carries_every_stream` proves wiring, not tuple-ness. Why: every stream returning the same empty payload means the test passes identically if `enemy_cast_rows` and `interrupts` are swapped — the same class of blind spot as Plan A's fixture that encoded the code's own wrong belief. Cost if wrong: a slightly larger test fixture.
Task 4: fix round 1/5 (3 addressed, 0 open — artificial load-then-get test, tuple-only stream assertion, accessor bypass; commits ca27336..7500588)
Task 4: complete (commits a598bf7..7500588, review clean)
Task 5: Ruling: keep §5.1's findings `measured` and tighten the `Confidence` docstring in `src/wowperf/domain/findings.py` instead. Why: the badge is about whether a claim needed an assumption that could be wrong, not about whether a minus sign appeared — subtracting two logged timestamps needs none, while reconstructing a cast's outcome does. Relabelling arithmetic as `derived` would make every finding derived and collapse the distinction the taxonomy exists for. Cost if wrong: a docstring; no finding's badge changes.
Task 5: Ruling: a negative residual sets `seconds_lost=None` and says so in the detail, rather than reporting a negative number of seconds lost. Why: the plan's own constraint is that a finding with no honest seconds figure sets `None` rather than inventing one, and a negative "time lost" is not honest — it means pull windows and the death penalty together over-account for the timer. Cost if wrong: one branch and one test; the ranking treats it as untimed, which is where an unexplainable figure belongs.
Task 5: minor (deferred): pull chronological order is assumed by `gaps_between_pulls`, inherited from ingest and not validated here.
Task 5: fix round 1/5 (3 addressed, 0 open — taxonomy docstring, negative residual, untested cap; commits fec6253..15bd76e)
Task 5: minor (deferred): commit 15bd76e's subject is "Fix review findings on time decomposition (task 5)", which describes the process rather than what the commit does to the repository.
Task 5: complete (commits 7500588..15bd76e, review clean)
Task 6: Ruling: a chain, single or repeat finding whose contributing deaths are all unmeasured sets `seconds_lost=None` and says so; a partly-measured group keeps its sum but its evidence must name how many deaths were unmeasured, so the figure reads as a floor. Why: the brief's own reference code reused one `_cost()` helper whose `or 0.0` turned "the player never acted again" into a reported "Cost 0s of play" with no disclosure — the confident lie the whole confidence taxonomy exists to prevent, and the reviewer reproduced it by execution. `deaths.total` already discloses; the other three families must too. Cost if wrong: those findings rank last as untimed instead of showing a fabricated zero, which is where an unmeasurable claim belongs.
Task 6: minor (deferred): `analyse_deaths` recomputes `_cost(group)` twice in a couple of places — pure and cheap, but avoidable.
Task 6: fix round 1/5 (3 addressed, 0 open — fabricated zero cost, missing edge tests, singular grammar; commits ca514d2..2067708)
Task 6: complete (commits 15bd76e..2067708, review clean)
Task 7: fix round 1/5 (2 addressed, 0 open — untested mutual-exclusivity invariant, untested tie-break; commits 8783a46..d7dbfb9)
Task 7: complete (commits 2067708..d7dbfb9, review clean). Reviewer executed the reconstruction against every adversarial case in the brief and could not break it.
Task 8: Ruling: the `trash.pull.*` per-pull ranking only fires when the forces overage clears `OVERKILL_FLOOR_PERCENT`. Why: those findings exist to say where the overkill went, so on a run that killed exactly what it needed — or fell short — they scold the group for nothing, and the narrative layer reads findings at face value. Every sibling analyser gates its per-item findings the same way. Cost if wrong: a clean run reports no pack-efficiency detail, which is the right answer when there is nothing to fix.
Task 8: minor (deferred): `analyse_trash` is one flat 57-line function where the sibling analysers factor comparable logic into small named helpers.
Task 8: fix round 1/5 (2 addressed, 0 open — ungated per-pull ranking, untested guards; commits 8bc171b..20ecbaf)
Task 8: complete (commits d7dbfb9..20ecbaf, review clean)
Task 9: minor (deferred): the implementer's own name-collision fallback for `players.activity.*` ids has no committed test — the reviewer verified it only by ad hoc execution. Worth a test in the final fix wave.
Task 9: minor (deferred): `players.py`'s `if baseline <= 0: continue` is unreachable, since `took` is pre-filtered to positive amounts.
Task 9: complete (commits 20ecbaf..9d76f00, review clean)
Task 10: complete (commits 9d76f00..3878559, review clean). Implementer fixed a finding-id collision the brief's literal sample would have shipped, reusing `players.py`'s actor-id disambiguation.
Task 11: complete (commits 3878559..2f3add1, review clean). Reviewer reproduced every claim by execution: 9 findings on the committed fixture, all ids unique, ranking correct, empty run safe.
Task 11: Ruling: fix `analyse_deaths`'s `deaths.repeat.<name>` now rather than deferring it. Why: the reviewer reproduced it — with two players sharing a display name, one finding reported three deaths as one person's and mixed both players' deaths into its evidence, a factually wrong claim about a named human. `players.py` and `defensives.py` already disambiguate on `actor_id`; deaths is the odd one out. It is out of Task 11's scope, so it ships as its own commit against Task 6's file. Cost if wrong: two more findings on a roster with duplicate names, which is the correct answer.
Task 6 follow-up: repeat-death findings now group by player rather than display name (commit af7e652), per the Task 11 ruling.
Task 12: minor (deferred): `analyze`'s error path uses `typer.secho(..., fg="red")` where the neighbouring `fetch` uses plain `typer.echo`.
Task 12: complete (commits af7e652..5de134f, review clean). Reviewer executed the command against a mock transport: JSON contract matches key for key, UTF-8 write proven on raw bytes, `?fight=N` query form picked up.
Task 13: FIRST CONTACT — the e2e run raised `IngestError: Enemy death targets actor 730, which is absent from the report's NPC actors`. Investigated against the live API: report 6Kx1P9GbNXrcLdHa has 931 actors (194 NPC, 441 Player, 296 Pet); 5 of the fight's 31 distinct enemy-death targets are Pets named "Glacial Tomb" (gameID 246591), each owned by one of the five *players* — a dungeon mechanic that encases a player and is modelled as a hostile pet, so it appears under `hostilityType: Enemies`. `NPC_ACTORS_QUERY` filters `actors(type: "NPC")` and therefore cannot resolve them.
Task 13: Ruling: fetch every actor rather than only `type: "NPC"`, so no death target is ever unresolved, and let `npc_count_map` decide the forces — a Glacial Tomb resolves to game id 246591, which is absent from `npcCountMap`, so it awards 0. Keep the `IngestError`: it did its job, and an unresolved actor still means our own fetch is wrong. Why not drop non-NPC deaths instead: silently discarding rows is the judgement an adapter should not make, and 0 forces is already the honest answer. Cost if wrong: five mechanic deaths appear in `enemy_deaths` awarding nothing, which affects no current analyser.
Task 13: fix round 1/5 (2 addressed, 0 open — no offline guard on the actors query, stale rename comment; commits 3a9771e..80103bf)
Task 13: complete (commits 5de134f..80103bf, review clean). Both e2e tests pass against the live API; `wowperf analyze` writes 26 findings for the real run; quota spent this session ~20 of 3600.
Task 13: OPEN QUESTION FOR RwlRwlRwlRwl (not a defect, a design gap real data revealed): the loudest per-player finding on the real run is "Dudesons took 210.2x the group median from Melee" — Dudesons is the Death Knight, i.e. the tank. Melee damage on a tank is not a mistake, it is the job. Suppressing it needs role knowledge, and the spec list that would provide it is season data this plan deliberately defers. Left unfixed rather than guessed at, because any heuristic invented now could silently hide real findings.
Final review (opus, whole branch fb6628d..80103bf): "Fix before merge". 1 Critical, 4 Important, 8 Minor. Deferred list triaged: only the `players.activity.*` collision test must be fixed; the rest accepted.
Final: Ruling: `PlayerSummary`'s docstring is corrected rather than its behaviour. Why: `interrupts` and `deaths` counting every occurrence rather than only in-pull ones is the more useful number — a death outside a pull still killed the player — and no shipped finding reads either counter today. Correcting the sentence removes the trap without under-reporting deaths to Plan C. Cost if wrong: a docstring, and a later plan filters them itself.
Final: Ruling: mitigate the tank-melee false positive by naming the taker's class and spec in the damage finding's evidence, not by inventing a role heuristic. Why: a reader and the narrative layer can both discount "Blood Death Knight took 210x the median from Melee" on sight, and the honest fix — a `data/roles.toml` keyed Class/Spec — belongs with Plan C, which needs role data anyway. Cost if wrong: three extra words of evidence.
Final: accepted without fixing — `data/*.toml` lacking `# ABOUTME:` headers (the plan mandated that exact content), the three untested event types, the flat `analyse_trash`, two process-describing commit subjects, `secho` vs `echo`, the `pull_by_index` idiom split, `_cost` computed twice.
Final: OPEN FOR RwlRwlRwlRwl: `DATA_DIR` resolves to `<repo>/data`, but `pyproject.toml` packages only `src/wowperf`, so an installed wheel would not find the TOML files. Works today because the tool runs from the repo through `uv run`. Packaging decision, not a Plan B defect.


## The inference layer — `2026-09-05-mplus-inference-layer-plan`


4 ruling passages, copied verbatim from the ledger.


Ruling: Task 5's two new imports go at the top of `tests/test_skills.py`, sorted with the existing ones, not inline where the plan's snippet shows them — ruff lint selects `I`, so an inline import fails the gate the plan itself mandates. Cost if wrong: none; the plan's snippet is illustrative placement, and the gate would have caught it in a fix round anyway.


Ruling: the plan's `In queries.py` column is adopted as written — I verified all 27 rows against `src/wowperf/adapters/wcl/queries.py` before Task 1. Cost if wrong: a drift test that passes vacuously; mitigated by the >= 20 row guard.


Task 1: complete (commits 33c5966..b8b36bd, review clean). 514 passed, gate green.
Task 1: minor (deferred): `str.splitlines()` splits on the full Unicode line-boundary set, so a narrative containing \v, \f or U+2028 could report a line number an editor disagrees with. Theoretical for prose.
Task 2: complete (commits b8b36bd..8168c9d, review clean). 516 passed, gate green.
Task 2: note: the pre-existing `test_a_narrative_with_markup_is_escaped_in_the_report` used narrative text `alert(1)`; the new no-digits rule rejects it, so the implementer changed the payload to `alert('x')`. The test still proves what it was written to prove (HTML escaping of tags), and the change is a direct consequence of the no-carve-out rule. Reviewer confirmed.
Task 2: minor (deferred): the digit check has no inline comment of its own; it leans on the pre-existing "read this before anything is fetched" comment above the block.
Task 3: review found 1 Important (`## Mythic+ in the schema` left undated when §2's blanket sourcing sentence was deleted) + 1 confirmed gap I resolved myself (below) + 3 minors.
Task 3: Ruling: the "roughly 28 points" figure has no recorded measurement anywhere in the repository — I grepped, and it appears only in the plan, the inference-layer design and the new skill, all written this session from my own recollection of Plan D/E live runs. The implementer additionally stamped it "(2026-09-05)", a date the brief never gave. In a document whose premise is that every claim carries how it was verified, a recollected figure wearing a verification date is the exact defect the skill exists to prevent. Decided: keep the figure, drop the fabricated date, and state its provenance honestly as an observed approximation from this project's own compared runs — unlike the 12.02 figure beside it, which has a stated composition. Cost if wrong: a reader treats 28 as softer than it is and re-measures; the alternative cost, a fabricated date, is that they treat it as harder than it is and never do.
Task 3: minor (deferred): the FIELD_ROW regex captures `verified` and never uses it, so a row with a malformed date column drops out silently and the >= 20 floor still passes. Tightening it would mean asserting every row under `## Fields` parses.
Task 3: minor (deferred): the `In queries.py` check is a plain substring match over the file text, so a field named only in a comment counts as queried and a short name could collide with an ordinary word. Loud failure, not silent. Plan decision 3 accepted this.
Task 3: minor (deferred): the debuff entry's "does not work the way the paragraph above once claimed" points at `## Aura tables`, which no longer makes that claim. Inherited verbatim from design §2.2, where the antecedent was equally stale.
Task 3: Ruling: the three dangling `§2.2` cross-references the implementer flagged (`src/wowperf/adapters/wcl/queries.py`, five `(§2.2)` mentions inside the design document, `CLAUDE.md`) are folded into Task 6, which already owns making the repository describe itself correctly. Cost if wrong: Task 6 grows slightly; the alternative is three stale pointers surviving to merge.
Task 3: fix round 1/5 (2 addressed, 0 open; commit amended acfa680 -> c82e316).
Task 3: complete (commits 8168c9d..c82e316, review clean). 519 passed, gate green.
Task 3: for Task 6 — dangling `§2.2` cross-references to fold in: `src/wowperf/adapters/wcl/queries.py:246`, `docs/plans/2026-09-03-mplus-postmortem-design.md` lines 255/262/269/308/445, `CLAUDE.md:342`.
Task 4: complete (commits c82e316..45a1926, review clean — Approved, 0 Critical, 0 Important). Step 2 checked 26 claims: 6 corrected, 1 cut, 6 added, all verified true by the reviewer against the code.
Task 4: the six corrections, all defects in the plan text I wrote: (1) `SPELL_CAST_SUCCESS` appears nowhere in `src/` — the code asks `dataType: Casts` and keeps `type == "cast"`; (2) only the spell comparison's *rate* branch is boss-scoped, the never-cast branch checks the whole run, so the plan would have told a reader to discount a correct finding; (3) `players.py:206` says melee damage on a tank is "not a mistake", not "not a finding", and the finding is emitted deliberately; (4) the tool itself reports the cast count as a share of pull time, contradicting "do not present it as a share of anything"; (5) the findings JSON key list was missing `pull_index`; (6) the badge glosses now quote the `Confidence` docstring.
Task 4: Ruling: three documentation minors are folded into Task 6 rather than a fix round — minors do not extend the loop, and Task 6 already owns making the repository describe itself correctly. They are: `wcl-api` still telling a reader we compute uptime "from `SPELL_CAST_SUCCESS` ourselves" (carried verbatim from design §2.5, and the constant is not in `src/`); `mplus-analysis` stating flatly that `compare.duration` contains every other `seconds_lost` when it is itself None at a level gap and when we finished faster; and its `inferred` gloss covering only the never-pressed defensive, not `defensives.ceiling.*`. Cost if wrong: Task 6 grows by three small edits; leaving them costs a reader who states something the code does not support, which is what this skill exists to prevent.
Task 4: out of scope, real code inconsistency: `cli.py:314`'s non-additivity warning names `deaths.repeat.*`, but `build.py:41-47`'s NESTS_INSIDE lists only `deaths.single.` and `deaths.chain.`, so the report never prints "Already counted inside" for a repeat-deaths row. Confirmed by the reviewer. Not this plan's work.
Task 5: review found 1 Important (step 5 dropped step 1's flags, making "spends no API quota" false — `--player` changes the cache keys, and omitting `--no-compare` fetches both references, the ~28-point path) + 3 minors. Verification account: 14 claims checked, 9 confirmed, 4 corrected, 1 cut; reviewer verified all against the code.
Task 5: the four corrections, all defects in the plan text I wrote: "every fact in the HTML came from the findings file" is false (`build_deaths`'s own docstring says the section exists because no finding carries the damage run-up); the keystone failure is four distinct messages, one of which asks for `--fight`, a flag the plan never mentioned; the quota figure needed `wcl-api`'s hedge; and the draft's own worked example broke the skill's own no-quantities rule. Cut: "takes about fifteen seconds", unverifiable without a live run.
Task 5: fix round 1/5 (4 addressed, 0 open; commit amended 5e2fdde -> ad8c78e).
Task 5: complete (commits 45a1926..ad8c78e, review clean). 520 passed, gate green.
Task 5: minor (deferred): the flag drift test's `flag not in help_text` is a substring match, so a skill naming `--cache` would pass against the real `--cache-dir`. No current flag is a prefix of another. Same accepted coarseness as the field table's check, per plan decision 3.
Task 6: review found 2 Important (a `design §2.2` citation surviving in `tests/domain/comparison/test_uptime.py:91`, and a false completeness claim in the report) + 1 minor.
Task 6: Ruling: `docs/plans/2026-09-05-mplus-uptime-and-cooldowns-plan.md:49` and `docs/plans/2026-09-03-mplus-foundation-plan.md:20` keep their `§2.x` citations. A dated implementation plan records what was true when it was written; repointing its citations rewrites that record, and the citation was correct on its date. The design document is different — live guidance — which is why its citations moved. The exemption is now written into the design's §2 redirect so the next sweep does not rediscover it. Cost if wrong: a reader of an old plan follows a citation to a two-line redirect and needs one extra hop.
Task 6: the implementer's own judgement calls, all upheld by the reviewer: it struck through the design's "four aura tables cost about four points" with a dated amendment rather than repoint it at a section that does not contain that number or invent a per-table share; and it rewrote the `SPELL_CAST_SUCCESS` line to state what the code does (`dataType: Casts`, `type == "cast"`, checked 2026-09-05) while labelling the constant's correspondence as the community reading, unverified here.
Task 6: fix round 1/5 (3 addressed, 0 open; commits 48b53db..154d82f).
Task 6: complete (commits ad8c78e..154d82f, review clean).


Verdict: fix before merge — 3 Important, 4 Minor, all documentation, no code change. One fix wave: commit 78692ad.
Re-review: all seven addressed, one residual — the fix wave's new "surveyed, not verified" list named `talents`, which is not a field (`queries.py:266` is the Python function `talents_query`, `:281` the GraphQL operation `Talents`, `:277` the real field `talentImportCode`).
Ruling: dispatched one further single-word correction (f96c3cc) rather than parking that residual, against the process's "no second fix wave". A reference whose headline rule is "never invent a field name" cannot ship naming one that does not exist, and the fix was a one-word deletion verified by my own grep first. Cost if wrong: one extra cheap dispatch.
Final state: 9 commits, 33c5966..f96c3cc. 520 passed / 5 deselected, ruff clean, mypy clean on 115 files.


## Report icons — `2026-09-09-report-icons-plan`


16 ruling passages, copied verbatim from the ledger.


Ruling: work on branch `report-icons` in the main working copy rather than a git worktree —
the gitignored UTF-16 `.env` and the warm Warcraft Logs disk cache live at the repo root and
a worktree would carry neither, which Task 8's real render needs. Cost if wrong: the branch
shares a working directory with master, so an interrupted session leaves the tree on a
feature branch instead of an isolated path.


R1 — Task 1 Step 5. The plan writes `recording_repository(tmp_path=tmp_path, abilities_rows=[...])`
and `loaded, _ = repository.load("CODE", 36)`. Both are wrong against the real code:
`recording_repository`'s first parameter is `calls: list[str]`, required and positional
(`test_repository.py:105`), and `load` returns a bare `LoadedRun`, not a tuple
(`repository.py:238`). Ruling: the tests read `recording_repository([], tmp_path, abilities_rows=[...])`
and `loaded = repository.load("CODE", 36)`, matching the idiom at `test_repository.py:220`.
Everything else in the step — the `abilities_rows` keyword, its default, the line-127 edit —
stands. Cost if wrong: none; the implementer meets the TypeError on the first run either way.


R2 — Task 3 Step 1. The snippet names `a_loaded_run()`, `DEFENSIVES`, `NO_CONSUMABLES`,
`NO_EXTERNALS`; the file actually defines `loaded()`, `a_death()`, and calls
`Defensives()`/`Consumables()`/`Externals()` inline, with `ICEBOUND` carrying ability id 48792
(`test_recap_availability.py:26`). The plan already says to match the file's own names.
Ruling: adapt the names, keep 48792 as the asserted id, keep both assertions.
Cost if wrong: a test that does not compile, caught on the first run.


R3 — Task 5 Step 3. The module header imports `base64`, `os` and `tempfile` before any code
uses them; `base64` stays unused until Task 6. Ruff F401 would fail Task 5's own gate.
Ruling: Step 3 imports only `re` and `Path`; Step 7 adds `os` and `tempfile` with the store;
Task 6 adds `base64` with the resolver. Cost if wrong: a red gate, caught immediately.


R4 — Task 6 Step 2. The snippet opens with a second top-level
`from wowperf.adapters.render.icons import ...` line partway down a file that already has one,
which is F811 plus E402. Ruling: extend the existing import at the top of the file to name
`BlizzardIcons`, and add `import base64` there too, rather than adding a second import block.
Cost if wrong: a red gate, caught immediately.


R5 — Task 8 Step 1. The test body carries only assertions; the plan says to build the arrange
section on whatever fixture `tests/test_cli.py` already uses to run `analyze` offline. Ruling:
that is an instruction, not an omission — the implementer writes the arrange section against
the real fixture, extends its abilities payload with an `icon` per row, and injects a fake
icon fetcher rather than reaching the network. If no such offline `analyze` fixture exists,
that is a BLOCKED report, not an invented one. Cost if wrong: a test that mocks its own
subject; the task review is the net.


R6 — Task 4. The brief names `tests/adapters/wcl/test_ingest.py` in both its Files block and
Step 1. No such file exists. The death-building tests live in
`tests/adapters/wcl/test_ingest_events.py`, which already imports `build_deaths` (line 6) and
already exercises `killingAbilityGameID` (lines 56-145) through the idiom
`build_deaths(events, a_run(), (), ABILITY_NAMES)`. Ruling: write the test there, mirroring
that idiom and reusing the file's `ABILITY_NAMES` constant. Cost if wrong: a test in a file
nobody else touches, or a ModuleNotFound on the first run.


R7 — Task 5, plan-conflicting finding. The reviewer calls the untested `_write_atomically`
exception-cleanup branch Important; the brief's Step 5 lists only three store tests, and the
implementer declined to exceed it. Ruling: fix it. The brief's step list is a floor, not a
ceiling, and CLAUDE.md's testing policy ("tests MUST comprehensively cover ALL functionality",
"reducing test coverage is worse than failing tests") binds over a step count. The branch guards
the one failure mode this design says never self-heals — a partial file in a store that never
expires would be embedded in every future report as a broken image. Cost if wrong: one extra
test in a file the implementer is already editing.


R9 — Task 6, plan-conflicting finding. The reviewer found the `status != 200` half of the
two-part CDN check pinned by no test: none of the brief's eight fixtures pairs a non-200 status
with an `image/*` content type, so deleting the status check passes the whole suite. Labeled
plan-mandated because the brief's test list is what omits it. Ruling: fix it, on the same
grounds as R7 — the brief's step list is a floor, not a ceiling, and the brief names this as a
two-part check precisely because either half failing must reject. Cost if wrong: one extra
fixture.
Also noted: the controller's own mutation instruction for this task was imprecise — it named the
403/XML test as the one that should fail when the content-type check is dropped, but 403 is
already rejected by the status half. The implementer reported the discrepancy instead of forcing
a match, which is the correct behaviour and not a defect.
Task 6: fix round 1/5 (1 addressed, 0 open — status half of the two-part CDN check unpinned;
commits 705ee81..a3b4c2f)
Task 6: complete (commits b94f1f0..a3b4c2f, review clean). R9 discharged with a
`(500, "image/jpeg")` fixture, mutation-verified against deleting `status != 200 or`.


R10 — Task 7, internal plan contradiction, surfaced by the Step 9 golden trap exactly as
intended. Step 6 gives the `.icon` sizing rule in `report.css.j2` unconditionally; Step 9
requires the golden diff for a page rendered with no `IconSource` to be empty. Both cannot hold:
an unconditional rule ships dead `.icon` CSS on every no-icon page and moves the golden file.
Ruling: Step 9 wins, and the implementer's `{% if icons_by_id %}` guard around the rule stands.
The design's own words are that a page rendered without a source is the page as it was; Step 6
is an argument for that, Step 9 is the requirement itself, and the spec is the binding authority.
Cost if wrong: a page that carries icons is unaffected; a page without them omits three lines of
CSS that would style nothing.


R11 — Task 7, plan-conflicting finding. The Step 8 invariant `test_the_page_loads_no_image_over_
the_network` renders with `icons=None`, so the CSS loop iterates an empty dict and no `url(` of
any kind can appear: the test cannot fail whatever an `IconSource` returns. The brief's Step 8
text is what mandates the vacuous form. Ruling: the test must render a page that would contain
`url(` if the rule were broken — i.e. with a fake source resolving at least one icon — while
keeping the no-icon assertion. A guard that cannot fail is not a guard, and this one exists to
catch a hotlinked icon reaching the page. Cost if wrong: one slightly larger test.


R12 — Task 7. `_icon_uris`'s docstring claims each ability is "resolved once each", but the
dedup guard only records ids that resolved: an id whose `data_uri` returns None is asked again
on every later row. The claim is false, and `FakeIcons.asked` was built to check it and is
asserted nowhere. Ruling: make the claim true rather than soften it — remember every id asked
about, resolved or not, and assert it through `asked`. The design's intent is one resolution per
distinct id, and on a 181-row card an unresolved repeat re-stats the disk each time. Cost if
wrong: one small set's worth of memory per report, and a behaviour closer to the docstring than
the docstring was to the code.


R13 — Task 8, plan-conflicting finding. `build_icons`'s `fetch` closure calls `httpx.get` with no
exception handling, and the `render(...)` call sits outside the `try/except (ValueError, WclError,
httpx.HTTPError, OSError)` that closes at cli.py:553. So one transient CDN failure among the ~53
sequential icon fetches aborts the whole `analyze` command with a raw traceback — after the
findings JSON is written, with no HTML and no cost breakdown — for a feature the design calls
purely decorative. The brief's Step 3 snippet is what mandates the unguarded call. Ruling: fix it.
The design's own contract is that a miss costs appearance and never meaning, and this same file
already catches `httpx.HTTPError` for the main API calls.


R14 — Task 8, the second edge of R13, which the naive fix would walk into. Returning a plain
miss-shaped tuple on a transport error would have `_download` write a `.miss` marker, and the
store never expires anything — so a single timeout would blacklist that icon permanently, on
every future report, with no way back short of deleting the file. Ruling: a request that never
got an answer must be distinguishable from a server that answered and said no. The fetcher
reports status 0 for "no HTTP response at all", and `BlizzardIcons._download` records a miss only
when the server actually answered. Cost if wrong: an icon that is genuinely unreachable is
re-requested once per run instead of never again — the cheap direction to be wrong in.
Task 8: fix round 1/5 (1 addressed, 0 open — a transient CDN failure aborted the whole analyze
run, and the naive guard would have blacklisted an icon permanently; commits bfa8360..63989dc)
Task 8: complete (commits 30e73c4..63989dc, review clean). R13 and R14 both discharged: `fetch`
catches `httpx.HTTPError` and reports status 0, and `_download` returns before any store write on
status 0, so an unanswered request is asked again next run.


Rulings 1-4 (R10, R12, R13/R14, and tests beyond the step list) were all reviewed and agreed with,
ruling 3 "strongly".


R15 — residual from the final fix wave, parked with a ruling. `IconStore.__init__`'s `mkdir` runs
inside `build_icons`, which is evaluated as an argument to the unguarded `render(...)` call, so an
unwritable icons subdirectory would still crash the run one call earlier than F1's fix reaches.
The implementer scoped it out and spawned a follow-up rather than dropping it silently; the
re-reviewer verified the gap is real and the scoping defensible. Ruling: park it. `DiskCache` is
built from the same `cache_dir` at cli.py:518, inside the guarded region, so a bad root path is
already caught before render runs; what remains is a file colliding with the `icons` subdirectory
name, or a disk filling mid-run. Cost if wrong: the same traceback-after-findings-written symptom
F1 fixed, in a narrower window. It is tracked as a follow-up task, not lost.


## The per-player page — `2026-09-10-per-player-page-plan`


7 ruling passages, copied verbatim from the ledger.


| 1 | 3 | `report/model.py` | 1 adds `PlayerCard.slug`; 3 adds `PlayerTimeline` & friends after `Timeline` | Clean. `Timeline` is at model.py:93, `PlayerCard` at model.py:268 — the new types land above `PlayerCard`, so Task 6's `PlayerCard.timeline: PlayerTimeline \| None` needs no forward reference. The plan's contingency ("if it is not, move it") is unnecessary but harmless. |
| 3 | 4 | `report/player_timeline.py` | 3 creates the module with `damage=None`; 4 adds `_damage_track` | **DEFECT — see Ruling 3.** |


| 1 | 6 | `_players.html.j2` | 1 writes the sub-tab nav + panel; 6 inserts the macro import and one call | Clean, 6 quotes the insertion point (`after the <p class="stats"> line`) which 1's template contains. |
| 6 | 7 | `_player_timeline.html.j2` | 6 creates it; 7 rewrites the press `<rect>` | Clean, but **see Ruling 7** — 7's own fallback path breaks an invariant. |


| --- | --- | --- |
| 1 | tests vs code vs files | **DEFECT — Ruling 1.** Step 5's test calls `build_report(...)` with nine positional args plus `LoadedRun`, `FETCHED`, `NO_DEFENSIVES`, `NO_CONSUMABLES`. `tests/domain/report/test_build_players.py` imports none of those and never calls `build_report` — it calls `build_players` only. The test as written raises `NameError`. Step 9's Step-10 expectation names `assert buttons`; the test's variable is `navs` (cosmetic — Ruling 6). Everything else verified: `rich_loaded()` has exactly 2 players, so `len(targets) == 2` is right; the existing panel-hiding rule is `.js .panel:not(.active)` keyed on class `.panel`, so the plan's new `[data-tab-panel]` rule is genuinely needed; `data-tab-group` / `data-tab-for` / `data-tab-panel` are the script's real attribute names and `show()` scopes by group, so nested tabs need no script change. |
| 2 | tests vs code vs files | **DEFECT — Ruling 2.** Same `build_report` NameError as Task 1. Also: the step-6 rationale says `load_throughput_cooldowns()` "is loaded twice" — it is called exactly once today (cli.py:561), inline into `analyse`. The hoist is still correct; only the wording overstates the present. Ruff exemption verified necessary: `extend-immutable-calls` lists `Externals`, `Roles`, `SelfResurrections` and not `ThroughputCooldowns`. |
| 3 | tests vs code vs files | **DEFECT — Ruling 3.** The module's import block imports `DamageTrack`, which nothing in Task 3 uses (`damage=None`). Ruff F401 fails Step 10's gate. Otherwise verified: `_ticks` (timeline.py:103) is referenced only at timeline.py:194 and by no test, so the rename is safe; `run_seconds` returns 0.0 for an empty-pull run (frame.py:85) so the withheld path is reachable; `a_pull(index, start, end, encounter_id=…)` matches; `Pull.is_boss` and `Pull.duration_seconds` are properties, which `_pull_bands` reads correctly. |


| 5 | tests vs code vs files | Clean. The concatenation `throughput.for_spec(...) + defensives.for_spec(...)` typechecks: `DefensiveAbility` is an empty subclass of `CooldownAbility` (season.py:36), so the result is assignable to `tuple[CooldownAbility, ...]`. `CastEvent` needs only the four kwargs the helper passes. Step 5's mutation proof is real and its target test is real. |
| 6 | tests vs code vs files | **DEFECT — Ruling 4** (Step 8's mutation is inert at this task). Otherwise verified: `a_report(**overrides)` accepts `players=`; `PlayerCard`, `Badge`, `Section`, `SectionState`, `TimelineBlock` are already imported by the test file, so only `CooldownRow`, `DamageBar`, `DamageTrack`, `PlayerTimeline`, `Press`, `Span` are actually new; the golden file will change as the plan says (`minimal_loaded()` has one player). Neither the plan nor the spec says how to regenerate the golden — **Ruling 5**. |
| 7 | tests vs code vs files | **DEFECT — Ruling 7.** The fallback the plan authorises (`<image href="data:…">`) violates `test_every_href_is_a_fragment_or_a_report_link_the_reader_asked_for` (test_html_invariants.py:334), which requires every `href="…"` on the page to start with `#` or `https://www.warcraftlogs.com/reports/`. Otherwise verified: `background-image` appears nowhere in `report.css.j2` — only in the generated per-icon rule at `report.html.j2:12` — so `assert "background-image" not in html` under `FakeIcons({})` holds; `_icon_uris` (html.py:33) has the shape the step describes; `test_html_sections.py:640` is the once-only test as cited. |
| 8 | tests vs code vs files | Clean as written, but needs an input the plan does not carry: a report URL. **Ruling 8.** |


- **Ruling 1 (Task 1, Step 5):** rewrite the uniqueness test against `build_players`, using the
  helpers `tests/domain/report/test_build_players.py` already defines (`a_loaded(players=…)`,
  `a_player(actor_id=…, name=…)`) and the call shape it already uses
  (`build_players(loaded, (), None, a_player(), {})`). — Why: the plan's `build_report` call
  cannot resolve in that file, and `build_players` is the unit the task changes; the file's own
  idiom needs no new imports. The assertion is unchanged: every slug truthy, no two equal. —
  Cost if wrong: the test exercises one layer lower than intended; Task 6's render tests cover
  the `build_report` path anyway.
- **Ruling 2 (Task 2, Step 1):** the `build_report(..., throughput=…)` test moves to
  `tests/domain/report/test_build_frame.py`, which defines `FETCHED`, `NO_DEFENSIVES`,
  `NO_CONSUMABLES` and already calls `build_report` with exactly that nine-positional shape.
  A second, smaller test stays in `test_build_players.py` asserting `build_players` accepts the
  two new parameters. — Why: same NameError as Ruling 1; splitting keeps each test in the file
  that owns its unit. — Cost if wrong: one test lives a directory-neighbour away from where a
  reader would look first.
- **Ruling 3 (Task 3, Step 8):** `DamageTrack` is dropped from Task 3's import block; Task 4
  adds it when `_damage_track` first returns one. — Why: ruff F401 would fail Task 3's own
  gate. — Cost if wrong: none; Task 4's step already says to extend the model import.
- **Ruling 4 (Task 6, Step 8):** run the ` with context` mutation and record the honest result.
  At Task 6 the partial reads no context variable, so **nothing failing is the correct
  outcome** — do not invent a test to manufacture a failure. The obligation transfers to
  Task 7, whose `icons_by_id` membership test is the first real dependency on context, and
  whose two icon tests must be shown to fail with ` with context` removed. — Why: the plan's
  "add one that does" would force a test asserting a property the code does not yet have. —
  Cost if wrong: the proof lands one task later than the plan intended; Task 7 is where the
  silent-failure risk actually exists.
- **Ruling 5 (Tasks 1, 6):** the golden file is regenerated with
  `uv run pytest tests/adapters/render/test_html_invariants.py --golden-update`
  (test_html_invariants.py:495), after reading the diff. — Why: the plan says to regenerate but
  never says how, and hand-editing a golden file is how a wrong one gets blessed. — Cost if
  wrong: none, this is the mechanism the suite ships.
- **Ruling 6 (Task 1, Step 10):** the expected failure is on `assert navs`, not `assert
  buttons`. Cosmetic slip in the plan's prose. — Cost if wrong: none.
- **Ruling 7 (Task 7, Step 6):** a CSS `background-image` cannot paint an SVG `<rect>`, so the
  fallback is near-certain. It is pre-authorised, together with the invariant change it forces:
  `test_every_href_is_a_fragment_or_a_report_link_the_reader_asked_for` gains `data:image/` as
  a third allowed prefix, and its name or docstring must say why. — Why: the invariant exists
  so the page fetches nothing; a data URI fetches nothing, so admitting it is faithful to the
  clause's purpose rather than a weakening of it. The `@import`, `<link rel=`, and remote-`src`
  clauses are untouched. The implementer must still verify empirically which branch is needed,
  and must delete `Press.icon_class` and its Task 7 Step 1 test if the `<image>` branch wins,
  rather than leave a field nothing reads. — Cost if wrong: one invariant reads looser than
  before; the remote-fetch clauses that carry the real weight are unchanged.
- **Ruling 8 (Task 8):** deferred to the task. Task 8 needs a live report URL and spends
  roughly 83 points of a 3600/hour budget. Before asking RwlRwlRwlRwl for one, check whether a
  cached run already sits under the default cache dir — a cached run costs nothing and answers
  every one of the four measurements. — Cost if wrong: quota spent that need not have been.


Task 1: reviewer's one ⚠️ (commit body not visible in the diff package) resolved by the controller — `git log -1 53aa958` shows both required rationale paragraphs and the exact `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` trailer.
Task 1: complete (commits 14411c2..53aa958, review clean)
Task 2: implementer a94f1b8047ac02074 (sonnet), reviewer a119bc6387071e78a (sonnet).
Task 2: judgement call endorsed — the brief gives `build_players`'s two new parameters no default, which broke 21 pre-existing call sites in `test_build_players.py`. The implementer updated all 21 rather than adding defaults. Reviewer verified completeness by grep (only `players.py`, `build.py`, `test_build_players.py` call it) and noted `extend-immutable-calls` omits `Defensives`, which is evidence the brief meant it to stay required. Reviewer also verified that inserting `throughput` positionally between `self_resurrections` and `reference_records` cannot shift an argument at any existing `build_report` call site, because every such site passes `reference_records` by keyword.
Task 2: minor (deferred): `build.py:52-71` — `build_report`'s docstring explains why `externals`/`self_resurrections` default to empty but never mentions the new `throughput`.
Task 2: minor (deferred): `players.py:79-96` — `build_players`'s docstring says nothing about the two new required parameters.
Task 2: minor (deferred): `pyproject.toml:22-24` — the comment above `extend-immutable-calls` names Roles, Externals and SelfResurrections; `ThroughputCooldowns` was added to the list without being added to the comment.
Task 2: complete (commits 53aa958..50b3290, review clean)
Task 3: implementer a8d1c4a055b637d65 (sonnet), reviewer ae901ac075bd172bd (opus), fixer afbeeb94d8e25ea36 (sonnet), re-reviewer a6c12c5c4d8fe30ed (sonnet).
Task 3: unplanned file touched and accepted — `tests/adapters/render/test_html_invariants.py`. The six new view-model types' numeric fields tripped `test_the_report_carries_no_total_row`. The opus reviewer read that test in full, enumerated the 19 numeric fields against the 19 allowlist entries added, and found the extension pair-keyed, exactly narrow, complete, opening no new hole, and the intended maintenance path for that invariant — the alternatives (narrowing the traversal, renaming coordinates) would each weaken or work around the guard.
Task 3: Ruling: `badges: tuple[Badge, ...]` (plan) vs `badge_measured` / `badge_inferred` (spec §7) — the spec wins. The plan's positional pair would leave Task 6's template reading `badges[0]`/`badges[1]` to decide which badge means what, and §6 makes the split load-bearing (measured grades the bars and marks, inferred grades the dimming). Fixed in round 1 with a swap-detecting test. — Cost if wrong: two fields where one tuple would do; the template gains two named slots instead of a loop.
Task 3: Ruling: `damage: DamageTrack | None` stays nullable, against spec §7's non-optional shorthand. §4 says a player who took nothing gets no track at all, and Task 4's own test asserts `damage is None` for another player's hits. §7's field list is a shape sketch, not a nullability declaration. — Cost if wrong: the template carries one `{% if %}` the spec did not anticipate.
Task 3: Ruling: design §4 contradicts itself — the intro says a pull sits at a *different* x on the two drawings, layer 1 says the *same* x. The intro governs, and the code follows it. **Task 8 must correct §4's layer-1 sentence** when it rewrites §12. — Cost if wrong: a legend or caption written from layer 1 would tell the reader the two drawings align when they do not.
Task 3: Ruling carried to Task 5: `NOTHING_TO_DRAW` names two conditions but only `span <= 0` is gated, and design §10 requires a player with no tracked casts to get a withheld section with a reason. A run with pulls and no casts currently returns PRESENT with zero rows. **Task 5 must close this** — either the guard becomes `span <= 0 or not rows`, or the message shrinks to what it checks. — Cost if wrong: a player who cast nothing gets an axis with no rows instead of a sentence saying why.
Task 3: Ruling: the Minor `**kwargs: object` finding on the `a_timeline` test helper was folded into fix round 1 rather than deferred, because Tasks 4, 5 and 7 all extend that helper's callers and its three `# type: ignore`s suppressed exactly the checking those tasks need. — Cost if wrong: one extra item in a round that was happening anyway.
Task 3: minor (deferred): `player_timeline.py:77-78` duplicates the x/width expressions at `timeline.py:92-93`. Extracting a shared `block_geometry(pull, scale, origin_ms)` would finish what `axis_scale` started. Two call sites is not yet a pattern; the final review should decide.
Task 3: minor (deferred): `DAMAGE_BASELINE_Y` and `DAMAGE_HEIGHT` are defined and unread until Task 4. Deliberate carry.
Task 3: fix round 1/5 (3 addressed, 0 open — split badge, pull-band arithmetic pinned with three recorded mutations, test helper's type: ignores removed; commits 8b14840..1a412d7)
Task 3: complete (commits 50b3290..1a412d7, review clean)
Task 4: implementer a3cdfddefe06bb0c8 (sonnet), reviewer a4ad08f95b1af117d (sonnet), fixers a3a7aedc57cce7bcc + a05ebfcec1ed9c829 (sonnet), re-reviewers ae273c4c977e0e1b7 + afd7a665256b2af11 (sonnet).
Task 4: the implementer found and closed a real gap the brief created — the brief's fixture amounts (1000 and 500) made peak coincide with the suggested mutation divisor (1000), so "scale to a fixed constant" was invisible. Changed to 2000/1000, same ratio, every other assertion still meaningful. Reviewer recomputed all three mutation outputs by hand and found each exact.
Task 4: Ruling: `_damage_track` divided by an unguarded `peak`, which real ingest data can drive to zero — `ingest.py:343-345` builds `amount` from `unmititigatedAmount` falling back to `amount or 0`, so a miss/dodge/parry is `amount=0`, and a player whose every recorded hit was avoided passed the `if not ours` guard and then raised ZeroDivisionError. This is the brief's Step 3 code verbatim, so a plan defect. Ruled: return `None`, because a run of fully-avoided hits is "took nothing" in the terms the track draws — the same reasoning the docstring already gives for the empty case. Forbade clamping `peak` to 1: a fabricated denominator would draw bars for damage nobody took. — Cost if wrong: a fully-avoided run shows no damage track where a flat baseline might have been preferred.
Task 4: Ruling: the Minor `peak_label` finding was folded into round 1, came back NOT ADDRESSED, and I ran a second round for it rather than parking it. The gap was that no test gave the own player a hit while a different actor took more, so an implementation bucketing from `ours` but reading `peak` from unfiltered `events` would have passed everything. "Never the group's" is a Global Constraint from postmortem design section 5.5, not a coverage nicety, so an unprovable guard on it was worth one more round. Closed with a mutation that exactly one test caught. — Cost if wrong: one extra round spent on a Minor label.
Task 4: minor (deferred): the commit body of `9bf19c5` renders "section 5.5" as "SS5.5" — non-ASCII punctuation is mangled somewhere between a subagent's message and git. Not amended: cosmetic, and amending would rewrite a reviewed SHA. **Every dispatch from Task 5 on tells the implementer to write commit messages in plain ASCII**, and no later commit has recurred.
Task 4: minor (deferred): `a824d39`'s body ends with "Task 4 fix review round 2, finding 1 (Important) and finding 2 (Minor)" — an internal process reference in a permanent commit body. Noise for a future reader; not worth rewriting history over.
Task 4: minor (deferred): a bucket containing only zero-amount avoided hits still gets a dict entry and draws a zero-height bar, inconsistent with `test_a_bucket_with_no_damage_draws_no_bar`'s premise that untouched buckets draw nothing. Invisible and harmless today.
Task 4: minor (deferred): events falling outside the run's span produce an out-of-range bucket index and an x outside the track. Nothing clamps or tests it. Unlikely with real fetch windows.
Task 4: minor (deferred): `_pull_bands` writes `round(max(...), PRECISION)` while `_damage_track` writes `max(round(...), MIN_BLOCK_WIDTH)`. Provably equivalent; two near-identical computations in one module reading differently.
Task 4: fix round 1/5 (1 addressed, 1 open — peak_label could not distinguish own from group; commits 9bf19c5..a824d39)
Task 4: fix round 2/5 (1 addressed, 0 open — own-peak scaling pinned, mutation caught by exactly the new test; commits a824d39..d000458)
Task 4: complete (commits 1a412d7..d000458, review clean)
Task 5: implementer abb4e7e0e9468b516 (sonnet), reviewer a0d17bd59973b3717 (opus), fixer a5e813dee3c01115d (sonnet), re-reviewer aa896ebda3ce014bd (sonnet).
Task 5: Ruling (carried from Task 3): the withheld gate now closes design section 10's requirement that a player with no tracked casts gets a withheld section rather than an empty SVG. Specified the shape myself — compute span; if not positive, withhold; else compute scale, origin and rows; then withhold only if there are no rows AND no damage track, because a player with damage but no tracked casts still has something worth drawing. — Cost if wrong: a player with damage and no cooldowns sees a drawing with empty rows rather than a sentence.
Task 5: Ruling: the press span's width was clamped against the run's whole length instead of the time remaining after the press. The brief dictated that line verbatim, so a plan defect. On a 1800-second run every press in the last 180 seconds overran the axis end and every press in the last ~100 seconds overran the viewBox, painting over the margin that holds the last tick's label. Ruled: per-press width from time remaining; `not_judged` keeps the run-length clamp, because it starts at the origin and means something different. The implementer's defence that the excess "is simply not drawn" was wrong twice — the SVG clips at the viewBox edge (680), not the axis end (656), and leaning on the clip at all inverts the rule that the domain computes every coordinate. — Cost if wrong: a dimmed span stops at the axis rather than running visually off it.
Task 5: Ruling: a press at or beyond the run's end draws a zero-width span rather than none, keeping `presses` and `unavailable` one-to-one. Implementer's choice, reasoned and recorded. — Cost if wrong: one inert `<rect width="0">` per such press in the SVG.
Task 5: Ruling: `NO_PULLS_RECORDED` could be false. `run_seconds` returns 0.0 both for a run with no pulls and for a run whose pulls span no time — `axis_scale`'s own docstring contemplates the instantaneous pull — so a run with a pull was being told it recorded none. Split into `NO_PULLS_RECORDED` behind `if not run.pulls` and a new `RUN_SPANS_NO_TIME` behind `if span <= 0`. — Cost if wrong: three withheld messages where two would do.
Task 5: Ruling: design section 10's clause "a second press inside that span still draws its mark" is carried by NO task in the plan — the reviewer grepped every brief and found it only in the design. Assigned it here, because this is the task that builds dimming and it is three lines. The behaviour was already correct; only the test was missing. — Cost if wrong: none; a test was added to already-correct code.
Task 5: minor (deferred): mutation 4 (weakening the withheld guard's `and` to `or`) has a 15-test blast radius, so most of its catch is incidental. The guard's other direction is proved by the RED step rather than by a mutation. Acceptable as recorded; the two directions together bound it.
Task 5: fix round 1/5 (5 addressed, 0 open — per-press clamp with a boundary test landing exactly on TRACK_X1 and a reverting mutation, the withheld message split, all three reason constants asserted by name, and the two folded-in coordinate tests; commits 9593d84..75c4d0d)
Task 5: complete (commits d000458..75c4d0d, review clean)
Task 6: implementer ae5c2e392501761fd (sonnet), reviewer a5de20da1a9a486f9 (opus), fixer a78b2ffec91af4320 (sonnet), re-reviewer af977171187348a00 (sonnet).
Task 6: Ruling 4 applied — the brief's Step 8 said to delete ` with context` and, if nothing failed, "add one that does". I overrode it: at Task 6 the partial reads no context variable, so the import is genuinely inert and nothing failing is the honest outcome. Forbade manufacturing a failure; transferred the proof obligation to Task 7, where `icons_by_id` is the first real dependency. — Cost if wrong: the silent-failure risk goes unproven one task longer.
Task 6: Ruling — the plan's five-layer guard test `assert layer in html` could not fail for any of its five layers, because all five substrings sit in the unconditional `<style>` block. The golden file proved it: `minimal.html` has no cooldown rows yet carries `.on-cooldown`, `.not-judged` and `.press` rules with no matching elements. `press` was doubly incidental, also matching `.avail li.pressed` and the caption prose. Deleting the press loop from the partial left the whole suite green and nothing anywhere asserted a press mark is drawn. Ruled: prefix each with `class="`, and prove all five with a deletion mutation apiece. — Cost if wrong: none; the test now asserts what its name says.
Task 6: Ruling — the brief's `PlayerCard.timeline` docstring said "`None` when the run had no span to draw on", which the builder contradicts: `build_player_timeline` returns a *withheld* timeline in that case and never returns `None`. A false sentence in the model file, dictated verbatim by the plan. Corrected. — Cost if wrong: none.
Task 6: Ruling — folded in the Minor that the badge captions were authored as template literals while `PlayerTimeline.legend` and `HealthCurve.reading_legend`/`line_legend` are domain fields. A caption saying what a badge grades is a claim, and in this project a claim lives with the badge that grades it, where a test can reach it. Moved both onto `PlayerTimeline` with a swap-detecting test; the rendered bytes are identical, so the golden did not change. — Cost if wrong: two more fields on a view model that already has many.
Task 6: minor (deferred): the paint-order test uses `html.index`, which finds the first occurrence. Sound with today's one-row fixture; if that fixture gains a second row the assertion compares indices across rows and stops meaning what its name says.
Task 6: fix round 1/5 (3 addressed, 0 open — five-layer guard made discriminating with five deletion mutations, model docstring corrected, badge captions moved into the domain with a swap test; commits 14db291..5ad95e7)
Task 6: complete (commits 75c4d0d..5ad95e7, review clean)
Task 7: implementer a1839c9a82e3107b5 (sonnet), reviewer af09a8fb007625e18 (opus), fixers ab138c2287eda9c82 + ac60bb0ae6b2b3c4c (sonnet), re-reviewers adad36c1bfd6cb316 (opus) + a4d66c78151286f9d (sonnet).
Task 7: Ruling 7 exercised as pre-authorised. The implementer verified empirically (getComputedStyle plus a visual render) that an SVG `<rect>` computes `background-image` but paints only its `fill`, so it took the `<image href="data:...">` branch, deleted `Press.icon_class` and its test, and widened `test_every_href_is_a_fragment_or_a_report_link_the_reader_asked_for` to admit a third prefix, `data:image/`. The invariant exists so the page fetches nothing opened from disk, and a data URI fetches nothing; the `@import`, `<link rel=` and remote-`src` clauses are untouched. — Cost if wrong: one href clause reads looser than before.
Task 7: the ` with context` proof obligation transferred from Task 6 was discharged here — deleting it from the macro import makes a test fail, recorded with output.
Task 7: Ruling — the widened invariant was inert in its own fixture. `rich_html()` renders with no `IconSource`, so `icons_by_id` is empty, the `<image>` branch can never be taken, and no `data:` href could appear in the page that test scans. A future edit emitting `<image href="https://...">` would have been caught by nothing: the script test scans only `src="..."` and the network-image test only `url(`. Ruled: a sibling fixture rendering with a resolving `IconSource`, and `test_the_richer_fixture_actually_exercises_what_it_claims_to` taught the new shape. — Cost if wrong: one more fixture to keep alive.
Task 7: Ruling — every press embedded its own full copy of the data URI. Five players, several rows each, a 25-second-cooldown defensive pressed thirty times is over a hundred copies of a 4-7 KB icon, and **Task 8 measures page size against a recorded 257,988 bytes**, so shipping it would have made that measurement a record of the defect. Ruled: at most one payload per SVG. Accepted as bounded, and explicitly did not chase, the one dead `.i-<id>` CSS rule per timeline-only icon. — Cost if wrong: none; the page got smaller.
Task 7: Ruling — the icon marked the wrong instant and hid its neighbours. Drawn at `x = press.x` with `width = row_height` (16 against the fallback's 4), the icon sat entirely right of the moment it marked — up to ~40 seconds late on a 25-minute run — and two presses under ~38 seconds apart overlapped almost completely, so a reader counted fewer icons than presses. The brief's own Step 6 geometry, so a plan defect. Ruled the shape of the fix myself: always draw the narrow mark for every press, and centre the icon on it, with the centring coordinate computed in the domain because the template may not compute. Explicitly did NOT change the icon's size — design section 12.3 sends Task 8 to measure it. — Cost if wrong: a 4-unit mark drawn on every press whether or not it is needed.
Task 7: Ruling — the duplicate-id question the implementer raised. Per-SVG `<defs><image id="icon-N">` gave two players the same element id, and `<use href="#id">` resolves document-wide taking the first match, so one player's presses already rendered another player's definition. Benign only while the payload and the `<image>`'s width/height are globally identical — and Task 8 is about to change the icon's size, at which point four of five players would silently draw the first player's geometry with no test failing. Ruled: a document-level `<symbol>` sprite beside `report.html.j2`'s existing per-id CSS loop. That is strictly better than the per-SVG fix asked for — one payload per **document** — removes the duplicate ids, and puts the geometry in one place before Task 8 touches it. Required empirical verification with a stated fallback to per-player ids; the implementer verified in a browser and needed no fallback. — Cost if wrong: a sprite container on every page that has icons.
Task 7: Ruling — the press mark was drawn but wholly invisible, painted before an opaque JPEG icon whose box strictly contains it. The markup assertion passed while the visual property its own comment named was false: the second time on this branch a test asserted markup for a property that did not hold. Ruled: reorder, and pin the paint order with an index assertion so a future reorder cannot silently undo it. — Cost if wrong: none.
Task 7: fix round 1/5 (4 addressed, 1 new Important — the press mark occluded by its own icon; commits f5a143a..ff4e0a5)
Task 7: fix round 2/5 (4 addressed, 0 open — paint order reversed and pinned, `icon_x` pinned in the render assertion, the None-ability-id test made discriminating, document-level sprite with a two-player one-payload test; commits ff4e0a5..2c27531)
Task 7: complete (commits 5ad95e7..2c27531, review clean)
Task 8: implementer a8dda2b03ebffc3c1 (sonnet), reviewer a74f19c43fd62181f (opus), fixer a82bdda13bdd12123 (sonnet), re-reviewer a1987a6d0f801c341 (sonnet).
Task 8: Ruling 8 resolved — used report 6Kx1P9GbNXrcLdHa fight 36 rather than asking for a URL. `out/6Kx1P9GbNXrcLdHa-36.html` already existed at 260,645 bytes rendered 2026-09-09 from this codebase before the branch, making it a like-for-like *before*; the run's data sits in the permanent cache tier; and RPGLogs section 5d forbids accumulating other players' logs, so re-analysing an already-fetched run adds nothing to the corpus where a fresh one would. Spend: 62.35 points of 3600. — Cost if wrong: the measurement describes one keystone rather than a fresh one.
Task 8: measurements taken 2026-09-10 — rows 6/5/4/4/5 (ceiling of 20 never approached); page 260,645 -> 659,499 bytes, of which 51.3% is icon payload; bucket rects 3,266/2,062/1,609 at 2/5/10 seconds; pre-layout 13,323 -> 15,175 px whole document, Players panel 2,798 -> 4,671 px. `BUCKET_SECONDS` stays 5.0.
Task 8: the opus reviewer corroborated the measurements at zero quota — marginal bytes-per-rect agreeing to 0.2% across two independent deltas (73.97 and 73.83) and bytes-per-icon three ways (2,308/2,301/2,308) — and concluded "I would have caught an invention".
Task 8: Ruling — the docstring defended `BUCKET_SECONDS = 5.0` with a clause the value breaks. It said "wide enough that a run does not emit thousands of rectangles" and then reported 2,062. Rect count could not be the tiebreak either: a 2.03x spread on rects and 1.20x on bytes, with every option openable. The argument that settles it is geometric and was in the code all along — at 610 units over 1,908.976 seconds the scale is 0.3195 u/s, so a 2-second bucket is 0.64 units and is clamped up to `MIN_BLOCK_WIDTH` = 2.0, a 3.1x overdraw in which every bar paints over its two neighbours and a spike draws as three overlapping bars. That is the design's *first* clause failing geometrically, where the concentration table does not discriminate. Also recorded that the concentration metric is biased toward narrow buckets, because a four-bucket neighbourhood is 8/20/40 seconds at the three widths. — Cost if wrong: the value is right either way; only its justification moved.
Task 8: Ruling — overrode the implementer's scope call on design section 11. It left "about three times taller" (measured 7.71x) and "roughly five times taller" (measured 1.67x) standing, with a four-line paragraph in section 12 explaining why it was not correcting them. Correcting a contradiction in section 4 was in scope; this is the same act on the same document in the same commit, and a footnote pointing at a wrong number is worse than a right number. Both corrected, the paragraph deleted, and the deep-link decision section 11 records left untouched. — Cost if wrong: none.
Task 8: Ruling — section 14.1 was closed as settled on the tank's track being densest (307 non-empty buckets against 274). Density is not legibility and arguably cuts the other way; section 10 declares this class of claim unmeasurable by the suite, and section 14.2 was honestly left open on thinner grounds. Required the density figures recorded as facts and the legibility question either settled by looking at the rendered page and saying what was seen, or left open. The implementer looked, and caught itself about to write an unverified detail — it had assumed from a screenshot that the tank's tallest bar sat by a Dancing Rune Weapon press, checked the SVG coordinates, found Vampiric Blood, and corrected it before it landed. — Cost if wrong: a design note claims a drawing reads well on the evidence of one run.
Task 8: minor (deferred, FOR THE FINAL REVIEW'S FIX WAVE): `src/wowperf/domain/report/player_timeline.py:75` states the 10-second bucket's spacing as "3.19 units". 10 * (610 / 1908.976) = 3.19543, which rounds to **3.20**. No conclusion changes, but this is a docstring whose whole purpose is exact re-derivable numbers, in the task whose deliverable is the honesty of the record.
Task 8: minor (deferred): the "about 175 KB, 27%" saving quoted for unifying the icon layers equates the hypothetical removed CSS layer to the sprite's own size rather than to an independently measured CSS-layer byte count. An analogy presented as a measurement.
Task 8: minor (deferred): design section 4 line 106 states "narrow enough that one lethal spike draws as one bar" as settled, where at 5 seconds a mild single-neighbour overdraw remains. Disclosed honestly downstream; the top-level phrasing is generous.
Task 8: fix round 1/5 (4 addressed plus five folded-in record corrections, 0 Important open; commits 3ff6a0d..b3fd572)
Task 8: complete (commits 2c27531..b3fd572, review clean, 1 minor deferred to the final fix wave)


Reviewer ac0eac0afb1d315f4 (opus). Verdict: fix first. Two Important gaps no task-scoped review could see.
Final: Ruling — the subject's sub-tab did not open first. Spec section 3 says outright that `subject` "now decides two" things; it still decided one, and `report.js.j2:50` activates the first button in each group, so four readers in five landed on the wrong player's drawing. Spec section 10's matching test did not exist. No task in the plan was ever assigned it. Ruled: order the subject's card first in `build_players`, which keeps nav and panel order in step, plus the section 10 test. — Cost if wrong: the roster's first player opens instead of the analysed one.
Final: Ruling — the row labels were drawn across the drawing they label. `LABEL_X`'s docstring claimed a right-alignment nothing performed; labels 25-118 units wide ran rightward over a track starting at 46, and because a label's baseline was the row's *top*, glyphs sat over the row above while striking through their own row's not-judged rect. That rect is the abstention section 6 grades with neither badge — obscured, an abstention reads as *ready*, the one direction section 4 says this project never guesses in. Ruled the approach myself: give the drawing its own left origin; extend `axis_scale`/`axis_ticks` with an origin parameter defaulting to `TRACK_X0` rather than forking them; size the gutter against the longest name in the two data files with the figure in its docstring; keep it under about 130 units, with a smaller font if needed; centre the label on its own row with the coordinate computed in the domain. The implementer measured "Incarnation: Avatar of Ashamane" at 121.6-123.6 units across three faces at 8.5px and chose a 130-unit gutter, giving up 13.8% of the track. — Cost if wrong: the track is a seventh narrower and the row labels are small.
Final: Ruling — raising `.on-cooldown` from 1.12:1 to 3.33:1 costs the press mark its contrast against that band (5.43:1 down to 1.81:1), and the two cannot both clear 3:1 because the card and the mark are only 6.02:1 apart. The implementer chose the band and disclosed the trade. The re-reviewer found the stated justification wrong — "the mark always overhangs the leading edge" is false for 40% of marks — but found a better one that holds: 402 of 416 marks are painted over their own icon, so mark-versus-band contrast governs only the 3% whose icon did not resolve. Accepted on that reasoning. — Cost if wrong: on a render where no icon resolves, every press mark sits at 1.81:1.
Final: fix wave adc9546cc2c99e644 (opus), 5 commits b3fd572..287183b, 14 items, 13 tests added and none weakened. Re-review a1a6db4ad1f46b3b9 (opus): **Merge.** It re-derived the geometry, the golden's rescaling, the contrast ratios, the overlap counts and the Chromium label widths, and every figure reproduced.
Final: the fix wave self-corrected two figures from my brief that did not reproduce — 415 adjacent press pairs is 392 per row, and the shipped overlap is 166/392 rather than 139 because the gutter brings presses 13.8% closer. The re-reviewer verified both independently. A correction that makes the recorded number worse is the kind worth naming.
Final: minor (deferred): `LABEL_GAP`'s docstring calls the gutter "clear space", but the icon layer is placed at `instant - ROW_HEIGHT/2` and so overhangs the track's left edge by 8 units. Two of 416 presses on the real run intrude at most 2.1 units into the label's tail.
Final: minor (deferred): a third option for the contrast trade was not tried — a 1-unit `var(--page)` stroke on the press mark would give it 3.67:1 against the new band with one declaration.
Final: minor (deferred): `.row-label`'s 8.5px beats `.track-label`'s 12px by source order alone, equal specificity. Correct today, silently reversible by a reorder.
Final: minor (deferred): three `axis_scale`/`axis_ticks` default-origin tests live in the player-timeline module; they now guard that the default was preserved when the parameter was added, but they belong beside `timeline.py`'s own tests.
Closing: verification a015e3cb941935f17 (sonnet), commit d3ee126. Re-rendered the real five-player run and looked at the page over HTTP. Subject's sub-tab opens first; labels legible in their gutter; not-judged visible; dimmed spans distinct from pull bands with marks findable on top; badges captioned and linking to Provenance. Design status line corrected from "Not yet implemented", and section 12's sentence no longer points at a path whose contents contradict it. One subtlety reported rather than fixed: a cooldown pressed very early has its dashed not-judged outline partly covered by the press icon and the on-cooldown fill — but the covering reads as *unavailable*, the safe direction, so it never misreads as ready.
Branch complete: 14411c2..d3ee126, 22 commits, gate green.
