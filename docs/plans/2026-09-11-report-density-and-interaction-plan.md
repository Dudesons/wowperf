# Report density and interaction — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the report use the screen it has, react to where the reader is looking, and say
what an ability actually did — without the page fetching anything or the browser computing a
coordinate.

**Architecture:** Every geometry change is a new field on the frozen view model under
`src/wowperf/domain/report/`, computed by a builder and covered by `pytest`; the Jinja templates
under `src/wowperf/adapters/render/` print those fields and decide nothing. Tooltips are
pre-rendered markup revealed by CSS `:hover`/`:focus-within`, so they need no script at all. The
one script grows by a single hover handler that toggles a class on an element already on the page.

**Tech Stack:** Python 3.12, pydantic v2 (`Frozen`), Jinja2, pytest, ruff, mypy, `uv`.

**Spec:** `docs/plans/2026-09-11-report-density-and-interaction-design.md`

## Global Constraints

Copied from the spec and from `CLAUDE.md`. Every task's requirements implicitly include these.

- **The report loads nothing.** One HTML file, opened from disk, with no stylesheet link, no
  `@import`, no remote `src`, and exactly one inline script. That script may show, hide and
  highlight what is already on the page; it may not fetch, write text, or read storage.
  `tests/adapters/render/test_html_invariants.py` enforces the list, and
  `test_the_page_executes_only_its_own_script` must keep passing **unchanged**: no token may be
  removed from `FORBIDDEN_IN_SCRIPT` (`fetch`, `XMLHttpRequest`, `import(`, `document.write`,
  `innerHTML`, `textContent`, `localStorage`, `sessionStorage`, `eval`, `WebSocket`).
- **Every coordinate is computed in Python** (spec §3.2). Marker positions, cover windows, pull
  column bounds and bar heights are computed by the view model builder, rendered into the page
  hidden, and revealed by a class toggle. A change that needs the script to calculate a position
  is out of scope by construction.
- **Damage prevented by a named ability is not derivable and must not be printed** (spec §5).
  Never write `unmitigatedAmount * 0.30` or any variant. `mitigated` is one figure per hit that
  the log never attributes; armour, Versatility, spec passives, a concurrent defensive and a
  teammate's external all land in it.
- **`src/wowperf/domain/` performs no I/O.** No `httpx`, no `jinja2`, no filesystem, no clock.
- **The LLM never computes a number**, and neither does the template: no `{% set %}`, no `sum(`,
  no `|sum` in any `.j2` file — `test_the_report_carries_no_total_row` reads every template.
- **Every new numeric field on a view model must be added to `NUMBERS_THAT_ARE_NOT_TOTALS`** in
  `tests/adapters/render/test_html_invariants.py`, with a comment saying why it cannot hold a
  total. The test fails otherwise, and that failure is the point.
- **Never invent an API field name.** Verified names live in `.claude/skills/wcl-api/SKILL.md`
  with the date checked. `tests/test_skills.py` holds that table against `queries.py` by substring
  match in both directions.
- **Every finding carries a `measured` / `derived` / `inferred` badge.**
- **No real character name in `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`, `Bríala`,
  `Кириллица`.
- **TDD, every task.** Write the failing test, watch it fail, write the minimal code, watch it
  pass, commit.
- **The gate**, run before every commit:
  `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
- **Ruff line length is 100.**
- **Git:** invoke as `/mingw64/bin/git`. Never `--no-verify`, `--no-hooks`,
  `--no-pre-commit-hook`. Stage by name; never `git add -A`; never stage anything under `out/` or
  `cache/`. Commit messages are plain ASCII written to a scratch file and committed with
  `-F <path>`: imperative mood, no `feat:`/`fix:` prefix, a subject saying what the repository now
  does, a body saying why, and a final line exactly
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **The golden file** `tests/adapters/render/golden/minimal.html` changes whenever markup does.
  Regenerate with
  `uv run pytest tests/adapters/render/test_html_invariants.py --golden-update`, then read the
  diff before committing it.
- **Two `# ABOUTME: ` lines** at the top of every new file. Comments are evergreen: they describe
  the code as it is, never how it changed.

## Rulings made while writing this plan

These resolve gaps between the spec and what the code and the API actually offer. Each is a
decision, not a discovery to re-litigate; each says what it costs if wrong.

1. **Aura bands are not "already fetched".** The spec's §6 table marks buff cover windows as
   already available. They are not: `PlayerAuras` is fetched in `cli.py::_auras` only inside the
   parse-comparison path, flows into the comparison inputs, and never reaches `LoadedRun` or the
   report builder. Task 2 plumbs it. Cost: one `AuraTable` query per roster player, measured at
   **about 1.06 points** (`.claude/skills/wcl-api/SKILL.md`, measured 2026-09-11 over thirty
   calls), and nothing at all for a player whose
   auras a parse comparison already fetched — our own run's responses are cached forever, so the
   second read is free. If wrong, cover windows are missing, not fabricated: the builder draws
   nothing where it has no band.
2. **Hit type is dropped from the tooltip.** The spec's §4.3 table lists it. `hitType` is an
   integer on the wire (values 1, 2 and 4 observed) and **no source in this repository documents
   what those integers mean**. Printing "hit type 1" is noise; printing "critical" is a guess.
   The tooltip carries `tick` instead, which is self-describing and renders as "periodic".
   If wrong, one honest line is missing from a tooltip.
3. **Overkill is on the damage stream, and it is verified.** Measured offline on 2026-09-11
   against the cached `DamageTaken` responses for report `6Kx1P9GbNXrcLdHa` fight 36: 11,368
   damage events, of which 18 carry `overkill`. Only lethal blows carry it, which is exactly what
   the killing-blow row needs. Task 1 records the dated row.
4. **The `buffs` wire format is a dot-terminated id list.** Same measurement: `buffs` appears on
   10,138 of those 11,368 events as a string like `"391395.391398.391571."` — ability game ids
   separated *and* terminated by a period. Task 1 records the dated row and parses it.
5. **The static description tier is not built.** The spec's §7 calls the description source an
   open spike. It is less open than that: `docs/plans/2026-09-08-icons-and-tooltips-spike.md`
   already probed `nether.wowhead.com/tooltip/spell/<id>`, found it works, found a three-clause
   ZAM Network EULA conflict, and **recommended shipping the icons and deferring the tooltips**
   pending three questions only RwlRwlRwlRwl can answer. Nothing in this plan builds the static
   tier. Every tooltip here renders from the measured and derived tiers alone, which is what the
   spec's own §7 says it must be able to do. If wrong, the tooltips are shorter than intended and
   a later task adds one line to a macro. *Closed 2026-09-12:* the three questions no longer
   block it. That spike's §9 now carries the answer and records this as a decision not to build
   the tier rather than a deferral waiting on anyone.
6. **Rich tooltips attach to HTML, not to SVG.** An HTML hover panel positioned over an SVG needs
   a script-computed position, which §3.2 forbids. So the recap table, the availability rows and
   the ledger card headings get the CSS hover panel; the player timeline's SVG rows keep their
   native `<title>`, enriched with the same measured facts. If wrong, the timeline's facts are one
   hover-delay slower to read than the card's. *Amended 2026-09-12:* half of this was wrong in
   both directions. The ledger card headings carry no panel and will not: their measured facts
   are already printed as the evidence list below them. The player timeline's cooldown rows had
   no `<title>` to enrich, only the pull bands did, and those rows now carry one. The design's
   §4.5.1 records both, and why.

---

## File Structure

**Domain — the layer that computes:**

- `src/wowperf/domain/events.py` — `DamageTakenEvent` gains the fields the log already returns.
- `src/wowperf/domain/model.py` — `LoadedRun` gains `auras`.
- `src/wowperf/domain/analysis/recap.py` — `RecapEvent` carries those fields to the report.
- `src/wowperf/domain/report/model.py` — every new view-model field, and the tooltip value.
- `src/wowperf/domain/report/tooltip.py` *(new)* — one responsibility: turning measured event
  fields into tooltip lines. Kept out of `deaths.py`, which is already 235 lines of card
  assembly.
- `src/wowperf/domain/report/cover.py` *(new)* — one responsibility: clipping aura bands to an
  axis and returning drawable spans. Read by both the death card and the player timeline, which
  is why it is neither one's file.
- `src/wowperf/domain/report/health_curve.py` — the marker x for a recap row.
- `src/wowperf/domain/report/deaths.py` — wiring: marker ids, cover spans, tooltips onto rows.
- `src/wowperf/domain/report/player_timeline.py` — pull columns, names, ready ticks, damage axis.
- `src/wowperf/domain/report/build.py` — passes auras down.

**Adapters — the layer that fetches and prints:**

- `src/wowperf/adapters/wcl/ingest.py` — reads the new event fields.
- `src/wowperf/cli.py` — fetches the roster's auras once and puts them on `LoadedRun`.
- `src/wowperf/adapters/render/report.css.j2` — width, tooltips, curve shapes, icon pairing.
- `src/wowperf/adapters/render/report.js.j2` — one hover handler.
- `src/wowperf/adapters/render/_macros.html.j2` — the `ability` macro every icon+name pair uses.
- `src/wowperf/adapters/render/_deaths.html.j2` — markers, cover windows, row tooltips.
- `src/wowperf/adapters/render/_player_timeline.html.j2` — columns, names, ticks, axis.

**Documentation:**

- `CLAUDE.md` — the script clause, amended in Task 6.
- `.claude/skills/wcl-api/SKILL.md` — dated rows for `overkill`, `mitigated`, `isAoE`, `tick` and
  `buffs`, added in Task 1.

---

### Task 1: Carry the damage fields the log already returns

The `DamageTaken` stream returns every field of each event as raw JSON — the query selects
`data`, not a field list — so `mitigated`, `overkill`, `isAoE`, `tick`, `sourceID` and `buffs`
are already on disk in every cached response and are discarded by `ingest.py`. This task stops
discarding them. Nothing on the page changes yet.

**Files:**
- Modify: `src/wowperf/domain/events.py:91-112` (`DamageTakenEvent`)
- Modify: `src/wowperf/adapters/wcl/ingest.py:332-358` (`build_damage_taken`)
- Modify: `.claude/skills/wcl-api/SKILL.md` (the event-stream prose, not the `## Fields` table)
- Test: `tests/adapters/wcl/test_ingest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `DamageTakenEvent` gains `mitigated: int = 0`, `overkill: int = 0`,
  `source_id: int | None = None`, `is_area: bool = False`, `is_tick: bool = False`,
  `buff_ids: tuple[int, ...] = ()`. Every one defaults, so no existing construction breaks.
- Produces: `wowperf.adapters.wcl.ingest.parse_buff_ids(raw: str | None) -> tuple[int, ...]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/adapters/wcl/test_ingest.py`, using whichever run fixture that file already uses in
its damage-taken tests:

```python
def test_a_damage_event_carries_what_was_mitigated_and_whether_it_was_periodic() -> None:
    events = [
        {
            "type": "damage",
            "targetID": 1,
            "sourceID": 735,
            "abilityGameID": 100,
            "timestamp": 1000,
            "amount": 67343,
            "unmitigatedAmount": 145434,
            "mitigated": 15609,
            "isAoE": True,
            "tick": True,
            "buffs": "391395.391398.",
        }
    ]
    taken = build_damage_taken(events, a_run(), {100: "Frigid Roar"})
    assert taken[0].mitigated == 15609
    assert taken[0].source_id == 735
    assert taken[0].is_area is True
    assert taken[0].is_tick is True
    assert taken[0].buff_ids == (391395, 391398)


def test_a_lethal_blow_carries_its_overkill_and_an_ordinary_hit_carries_none() -> None:
    # Measured 2026-09-11 against the cached DamageTaken stream of report
    # 6Kx1P9GbNXrcLdHa fight 36: 18 of 11,368 damage events carry `overkill`,
    # and they are the lethal ones. An absent key must read as zero rather than
    # as a hit that overkilled by an unknown amount.
    lethal = {"type": "damage", "targetID": 1, "abilityGameID": 100, "timestamp": 1000,
              "amount": 67343, "unmitigatedAmount": 145434, "overkill": 62482}
    ordinary = {"type": "damage", "targetID": 1, "abilityGameID": 100, "timestamp": 2000,
                "amount": 100, "unmitigatedAmount": 100}
    taken = build_damage_taken([lethal, ordinary], a_run(), {100: "Frigid Roar"})
    assert taken[0].overkill == 62482
    assert taken[1].overkill == 0


def test_a_hit_with_no_buffs_field_carries_no_buff_ids() -> None:
    # 1,230 of that run's 11,368 damage events carry no `buffs` key at all.
    # An empty tuple says "the log listed none"; it must not become `(0,)`.
    events = [{"type": "damage", "targetID": 1, "abilityGameID": 100, "timestamp": 1000,
               "amount": 100, "unmitigatedAmount": 100}]
    assert build_damage_taken(events, a_run(), {100: "Frigid Roar"})[0].buff_ids == ()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/adapters/wcl/test_ingest.py -k "mitigated or overkill or buff_ids" -v`
Expected: FAIL with `AttributeError: 'DamageTakenEvent' object has no attribute 'mitigated'`

- [ ] **Step 3: Extend the event**

In `src/wowperf/domain/events.py`, add to `DamageTakenEvent` after `absorbed`:

```python
    # What the game reduced before the hit landed, as one figure the log never
    # attributes: armour, Versatility, spec passives, a concurrent defensive and
    # a teammate's external all land here together. Reportable as a figure for
    # this hit, and never divisible between its causes.
    mitigated: int = 0
    # Damage past zero health, present only on a lethal blow.
    overkill: int = 0
    # The enemy that dealt it, joined against the report's actor list for a name.
    source_id: int | None = None
    is_area: bool = False
    # A damage-over-time tick rather than a discrete hit.
    is_tick: bool = False
    # Every aura on the player when the hit landed, as ability game ids.
    buff_ids: tuple[int, ...] = ()
```

- [ ] **Step 4: Read them in the ingest**

In `src/wowperf/adapters/wcl/ingest.py`, above `build_damage_taken`:

```python
def parse_buff_ids(raw: str | None) -> tuple[int, ...]:
    """The `buffs` field's dot-terminated id list, as game ids.

    Measured 2026-09-11 against the cached DamageTaken stream of report
    6Kx1P9GbNXrcLdHa fight 36: the field is a string of ability game ids
    separated and terminated by a period, e.g. "391395.391398.". The trailing
    separator yields an empty final part, which is why the parts are filtered
    rather than trusted.
    """
    if not raw:
        return ()
    return tuple(int(part) for part in raw.split(".") if part)
```

and inside the `DamageTakenEvent(...)` construction:

```python
                mitigated=int(event.get("mitigated") or 0),
                overkill=int(event.get("overkill") or 0),
                source_id=event.get("sourceID"),
                is_area=bool(event.get("isAoE")),
                is_tick=bool(event.get("tick")),
                buff_ids=parse_buff_ids(event.get("buffs")),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/adapters/wcl/test_ingest.py -v`
Expected: PASS

- [ ] **Step 6: Record the dated measurement in the API skill**

In `.claude/skills/wcl-api/SKILL.md`, in the bullet list under the event-stream table, add:

```markdown
- **On a damage event, `overkill` appears only on a lethal blow, and `buffs` is a
  dot-terminated list of ability game ids.** Measured 2026-09-11 against the cached
  `DamageTaken` responses for report `6Kx1P9GbNXrcLdHa` fight 36 — 11,368 damage events. Key
  frequencies: `timestamp`, `type`, `sourceID`, `targetID`, `abilityGameID`, `fight`,
  `hitType`, `amount`, `unmitigatedAmount` and `isAoE` on all 11,368; `mitigated` on 10,177;
  `buffs` on 10,138; `sourceInstance` on 5,930; `absorbed` on 5,785; `tick` on 3,766;
  `sourceMarker` on 1,335; `overkill` on 18; `blocked` on 2. An absent key means the log said
  nothing, so each reads as zero or false. `buffs` looks like `"391395.391398.391571."` — ids
  separated *and* terminated by a period. **`hitType` is an integer (1, 2 and 4 observed) and
  nothing here documents what those integers mean**, so no code may translate one.
```

Do not add a row to the `## Fields` table: these are keys of a raw `data` JSON blob, not selected
GraphQL fields, and `tests/test_skills.py` matches that table against `queries.py` by substring.

- [ ] **Step 7: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/domain/events.py src/wowperf/adapters/wcl/ingest.py .claude/skills/wcl-api/SKILL.md tests/adapters/wcl/test_ingest.py
```

Commit subject: `Keep the damage fields the log already sends`

---

### Task 2: Our own roster's aura bands reach the report

`PlayerAuras` already exists, `repository.auras()` already fetches it and `build_player_auras`
already parses it — but only the parse comparison calls that path, and its result never reaches
the report builder. This task carries it to `LoadedRun`. Nothing on the page changes yet.

**Files:**
- Modify: `src/wowperf/domain/model.py:120-145` (`LoadedRun`)
- Modify: `src/wowperf/cli.py` (beside `_auras`, and in the `analyze` command)
- Test: `tests/domain/test_model.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `LoadedRun.auras: tuple[PlayerAuras, ...] = ()` and the read-only property
  `LoadedRun.auras_by_actor -> Mapping[int, PlayerAuras]`, mirroring `ability_icon_map`.
- Produces: `wowperf.cli.load_run_with_auras(runs, code, fight_id, loaded) -> LoadedRun`.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/test_model.py`:

```python
def test_a_loaded_run_exposes_its_auras_by_actor() -> None:
    loaded = LoadedRun(
        run=a_run(),
        auras=(
            PlayerAuras(actor_id=7, on_self=(Aura(
                ability_id=48792, name="Icebound Fortitude", total_uptime_ms=8000, uses=1,
                bands=(AuraBand(start_ms=1000, end_ms=9000),),
            ),)),
        ),
    )
    assert loaded.auras_by_actor[7].on_self[0].name == "Icebound Fortitude"
    assert 99 not in loaded.auras_by_actor


def test_a_loaded_run_with_no_auras_has_an_empty_mapping() -> None:
    # A report built with --no-compare and no aura fetch must read as "no bands
    # known", never as a KeyError at draw time.
    assert dict(LoadedRun(run=a_run()).auras_by_actor) == {}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/domain/test_model.py -k auras -v`
Expected: FAIL with a pydantic `ValidationError` on the unknown field `auras`

- [ ] **Step 3: Add the field and the mapping**

In `src/wowperf/domain/model.py`, add `from wowperf.domain.auras import PlayerAuras` to the
imports and this to `LoadedRun`, after `ability_icons`:

```python
    # Every roster player's own buff bands, as the aura table reports them. A
    # tuple rather than a dict for the same reason `ability_icons` is one: a
    # LoadedRun stays immutable and hashable. Empty when no aura table was
    # fetched, which is a report that draws no cover window rather than one
    # that draws a wrong window.
    auras: tuple[PlayerAuras, ...] = ()

    @property
    def auras_by_actor(self) -> Mapping[int, PlayerAuras]:
        """Buff bands by actor id, as a read-only mapping."""
        return MappingProxyType({one.actor_id: one for one in self.auras})
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/domain/test_model.py -k auras -v`
Expected: PASS

- [ ] **Step 5: Write the failing CLI test**

Add to `tests/test_cli.py`, following the fake-repository pattern that file already uses for
`analyze`. Extend that fake with an `aura_calls` counter and an optional set of actor ids whose
aura fetch raises `IngestError`:

```python
def test_analyze_fetches_the_aura_table_once_for_every_roster_player() -> None:
    # Cover windows on a death card and on a player timeline are drawn from
    # these bands. Fetching them per report rather than per comparison is what
    # lets a --no-compare report draw them at all.
    runs = FakeRunRepository()
    loaded = load_run_with_auras(runs, "6Kx1P9GbNXrcLdHa", 36, a_loaded_run())
    assert {one.actor_id for one in loaded.auras} == {
        player.actor_id for player in loaded.run.players
    }
    assert runs.aura_calls == len(loaded.run.players)


def test_a_failed_aura_fetch_costs_that_player_their_bands_and_nothing_else() -> None:
    # `_auras` already swallows IngestError, WclError and httpx.HTTPError for
    # the comparison path, for the reason its docstring gives: everything else
    # has been fetched and paid for. The same rule holds here.
    runs = FakeRunRepository(failing_actor_ids={2})
    loaded = load_run_with_auras(runs, "6Kx1P9GbNXrcLdHa", 36, a_loaded_run())
    assert 2 not in loaded.auras_by_actor
    assert len(loaded.auras) == len(loaded.run.players) - 1
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/test_cli.py -k aura -v`
Expected: FAIL with `ImportError: cannot import name 'load_run_with_auras'`

- [ ] **Step 7: Add the loader and call it**

In `src/wowperf/cli.py`, beside `_auras`:

```python
def load_run_with_auras(
    runs: WclRunRepository, code: str, fight_id: int, loaded: LoadedRun
) -> LoadedRun:
    """The run, with every roster player's buff bands attached.

    One `AuraTable` query per player, measured at about 1.06 points
    (`.claude/skills/wcl-api/SKILL.md`). A player whose parse comparison
    already fetched theirs costs nothing the second time: our own run's cached
    responses never expire. A player whose fetch fails simply has no bands, and
    the drawings that read them draw nothing rather than guessing a window.
    """
    fetched = tuple(
        one
        for one in (
            _auras(runs, code, fight_id, player.actor_id) for player in loaded.run.players
        )
        if one is not None
    )
    return loaded.model_copy(update={"auras": fetched})
```

Call it in `analyze` immediately after the run is loaded and before the comparison runs, so the
comparison and the report see the same `LoadedRun`.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli.py tests/domain/test_model.py -v`
Expected: PASS

- [ ] **Step 9: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/domain/model.py src/wowperf/cli.py tests/domain/test_model.py tests/test_cli.py
```

Commit subject: `Fetch every roster player's buff bands with the run`

---

### Task 3: The page uses the screen it has

Spec §4.1. CSS only: no template and no view model change.

**Files:**
- Modify: `src/wowperf/adapters/render/report.css.j2:18` and the rules beneath it
- Test: `tests/adapters/render/test_html_invariants.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing test**

Add to `tests/adapters/render/test_html_invariants.py`:

```python
def test_running_prose_keeps_a_reading_measure_while_dense_content_takes_the_width() -> None:
    # Removing the 760px cap alone would stretch a narrative paragraph to the
    # width of a monitor, which is the one thing worse than a cramped one. The
    # cap moves off the page and onto the text.
    html = rich_html()
    assert "main { max-width: 760px" not in html
    assert "max-width: 68ch" in html
    assert "repeat(auto-fit, minmax(330px, 1fr))" in html
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/adapters/render/test_html_invariants.py -k reading_measure -v`
Expected: FAIL on `assert "max-width: 68ch" in html`

- [ ] **Step 3: Split the width by content type**

In `src/wowperf/adapters/render/report.css.j2`, replace line 18 with:

```css
/* The page takes the screen; running prose does not. A paragraph read at the
   width of a monitor is harder to follow than one read in a narrow column, so
   the measure moves off the page and onto the text, and the dense content --
   cards, tables, drawings -- keeps the whole width. */
main { max-width: 1400px; margin: 0 auto; }
.detail, .sub, .legend, .nests, .group-note, .narrative, .withheld { max-width: 68ch; }
.findings { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
  gap: 10px; align-items: start; }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/adapters/render/test_html_invariants.py -k reading_measure -v`
Expected: PASS

- [ ] **Step 5: Wrap each run of finding cards in the grid**

In `_route.html.j2`, `_deaths.html.j2`, `_interrupts.html.j2`, `_players.html.j2` and
`_summary.html.j2`, wrap each `{% for row in ... %}{{ ledger_row(row) }}{% endfor %}` loop in
`<div class="findings"> ... </div>`. Leave the per-player cards, the death cards and the pointers
alone: a death card holds a drawing and a table and does not belong in a 330px column.

- [ ] **Step 6: Check the columns never leave one card alone on the last row**

Open the rendered report and confirm at a wide viewport. `auto-fit` collapses empty tracks, so a
final row with one card only happens when the count demands it; if a section routinely ends that
way, raise its `minmax` floor rather than fixing the count.

```bash
uv run wowperf analyze 6Kx1P9GbNXrcLdHa --fight 36 --no-compare --out out
```

- [ ] **Step 7: Regenerate the golden file and read the diff**

```bash
uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

Then `/mingw64/bin/git diff tests/adapters/render/golden/minimal.html` and check the change is
the stylesheet and the new wrappers, nothing else.

- [ ] **Step 8: Run the gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/adapters/render/ tests/adapters/render/test_html_invariants.py tests/adapters/render/golden/minimal.html
```

Commit subject: `Give the report the width of the screen and prose a measure`

---

### Task 4: An icon and its ability name read as one object

Spec §4.6. The icon and the name already sit adjacent in four places; they are not bound into one
element. One macro replaces all four, so Tasks 8 and 12 have one place to attach a tooltip.

**Files:**
- Modify: `src/wowperf/adapters/render/_macros.html.j2`
- Modify: `src/wowperf/adapters/render/_deaths.html.j2:43,61,97`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the Jinja macro `ability(ability_id, name)` in `_macros.html.j2`, rendering
  `<span class="ability"><span class="icon i-ID"></span><span class="ability-name">NAME</span></span>`
  when the id resolved and the same without the icon span when it did not. Tasks 8 and 12 extend
  this macro with a third argument.

- [ ] **Step 1: Write the failing tests**

Add to `tests/adapters/render/test_html_sections.py`:

```python
def test_an_icon_and_its_ability_name_render_as_one_element() -> None:
    # Two adjacent spans read as two things. A reader scanning a recap table
    # for "which ability was that" should meet one object with one hover
    # target, which is also what a tooltip later attaches to.
    card = DeathCard(player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar", killing_blow_id=7)
    html = render(a_report(deaths=(card,)), icons=FakeIcons({7: "data:image/jpeg;base64,AAA"}))
    assert '<span class="ability">' in html
    assert '<span class="ability-name">Frigid Roar</span>' in html


def test_an_unresolved_icon_still_renders_the_ability_as_one_element() -> None:
    card = DeathCard(player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar", killing_blow_id=7)
    html = render(a_report(deaths=(card,)), icons=FakeIcons({}))
    assert '<span class="ability">' in html
    assert '<span class="ability-name">Frigid Roar</span>' in html
    assert 'class="icon i-7"' not in html
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/adapters/render/test_html_sections.py -k one_element -v`
Expected: FAIL on `assert '<span class="ability">' in html`

- [ ] **Step 3: Add the macro**

Append to `src/wowperf/adapters/render/_macros.html.j2`:

```jinja
{# One hoverable object per ability: the art and the word are the same thing to a
   reader, so they are the same element to the page. #}
{% macro ability(ability_id, name) %}
<span class="ability">{% if ability_id in icons_by_id %}<span class="icon i-{{ ability_id }}" aria-hidden="true"></span>{% endif %}<span class="ability-name">{{ name }}</span></span>
{%- endmacro %}
```

- [ ] **Step 4: Use it everywhere an icon sits beside a name**

In `_deaths.html.j2`, import it
(`{% from "_macros.html.j2" import ability, ledger_row with context %}`) and replace:

- line 43's heading pair with
  `{{ ability(death.killing_blow_id, death.killing_blow) }} — {{ death.player }}`
- line 61's event cell with `{{ ability(row.ability_id, row.ability) }}`
- line 97's `avail-name` pair with `{{ ability(row.ability_id, row.ability) }}`

In `_macros.html.j2`'s own `ledger_row`, replace the `<h3>` body with
`{{ row.title_before }}{% if row.title_ability %}{{ ability(row.ability_id, row.title_ability) }}{% endif %}{{ row.title_after }}`.

- [ ] **Step 5: Style the pair**

In `report.css.j2`, beside the `.icon` rule:

```css
/* The pair is one object: it wraps as one, and the name carries the page's
   full ink weight so the eye lands on the word rather than only on the art. */
.ability { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
.ability .icon { margin-right: 0; vertical-align: baseline; }
.ability-name { color: var(--ink); font-weight: 500; }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/adapters/render/ -v`
Expected: PASS. Assertions elsewhere that look for `<span class="icon i-7"` still hold — the
macro emits that span unchanged, one level deeper.

- [ ] **Step 7: Regenerate the golden file, run the gate, commit**

```bash
uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/adapters/render/ tests/adapters/render/test_html_sections.py tests/adapters/render/golden/minimal.html
```

Commit subject: `Bind an ability icon and its name into one object`

---

### Task 5: The health curve's line is dashed and its readings are ringed

Spec §4.2, second half. The dots read as kinks in the line because they share its weight and sit
on it. Shape now carries the measured/derived distinction the legend has to explain in words.
CSS and one attribute; no view model change.

**Files:**
- Modify: `src/wowperf/adapters/render/report.css.j2:88-92`
- Modify: `src/wowperf/adapters/render/_deaths.html.j2:20` (the reading's radius)
- Test: `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing test**

Add to `tests/adapters/render/test_html_sections.py`:

```python
def test_the_curve_draws_arithmetic_dashed_and_a_stated_reading_as_a_ring() -> None:
    # The line is derived and the dots are measured, and the badges beneath say
    # so. Saying it in shape as well as in words means a reader who never reads
    # the legend still sees two different claims.
    curve = HealthCurve(
        width=680.0, height=148.0, plot_x0=40.0, plot_x1=648.0, label_x=34.0,
        tick_label_y=136.0,
        points=(CurvePoint(x=40.0, y=14.0), CurvePoint(x=648.0, y=116.0)),
        readings=(CurveReading(x=40.0, y=14.0, percent=100),),
    )
    card = DeathCard(player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar", health_curve=curve)
    html = render(a_report(deaths=(card,)))
    assert "stroke-dasharray" in html
    assert 'class="hp-reading"' in html
    assert 'r="3.5"' in html
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/adapters/render/test_html_sections.py -k dashed -v`
Expected: FAIL on `assert "stroke-dasharray" in html`

- [ ] **Step 3: Change the two rules and the radius**

In `report.css.j2`, replace the `.hp-line` and `.hp-reading` rules:

```css
/* The line takes the derived tint and a dashed stroke, because it is
   arithmetic between readings rather than anything the log stated. The
   readings take the measured tint and a ring against the page colour, so a
   stated figure reads as a mark on the drawing rather than as a kink in the
   line it happens to sit on. */
.hp-line { fill: none; stroke: var(--badge-derived); stroke-width: 1.5;
  stroke-linejoin: round; stroke-dasharray: 5 3; }
.hp-reading { fill: var(--badge-measured); stroke: var(--page); stroke-width: 1.5; }
```

In `_deaths.html.j2` line 20, change `r="2.5"` to `r="3.5"`: a ring drawn at the old radius is
mostly stroke.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/adapters/render/test_html_sections.py -k dashed -v`
Expected: PASS

- [ ] **Step 5: Regenerate the golden file, run the gate, commit**

```bash
uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/adapters/render/report.css.j2 src/wowperf/adapters/render/_deaths.html.j2 tests/adapters/render/test_html_sections.py tests/adapters/render/golden/minimal.html
```

Commit subject: `Draw the health line as arithmetic and its readings as marks`

---

### Task 6: Hovering a recap row marks the curve

Spec §4.2, first half, and the §3.1 prose amendment — the first task that grows the script, so
the amendment travels with it.

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`RecapRow`, `DeathCard`)
- Modify: `src/wowperf/domain/report/health_curve.py` (export the x mapping)
- Modify: `src/wowperf/domain/report/deaths.py` (`build_deaths`)
- Modify: `src/wowperf/adapters/render/_deaths.html.j2`
- Modify: `src/wowperf/adapters/render/report.js.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Modify: `CLAUDE.md` (the invariant's script clause)
- Test: `tests/domain/report/test_build_deaths.py`,
  `tests/adapters/render/test_html_invariants.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-5.
- Produces: `RecapRow.marker_id: str = ""` and `RecapRow.marker_x: float | None = None`;
  `DeathCard.slug: str = ""`. A row whose event falls outside the curve's axis, or on a card with
  no curve, carries `marker_x=None` and renders no marker.
- Produces: `wowperf.domain.report.health_curve.curve_x(timestamp_ms, death) -> float` — the same
  arithmetic the curve's own points use, exported so a row and a marker cannot drift apart.

- [ ] **Step 1: Write the failing builder test**

Add to `tests/domain/report/test_build_deaths.py`:

```python
def test_every_recap_row_carries_the_x_of_its_own_moment_on_the_curve() -> None:
    # The marker is drawn where the curve puts that instant, not where the
    # browser guesses: both come from `curve_x`, so a row and its mark cannot
    # drift apart.
    loaded = a_loaded_run_with_one_death()
    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.health_curve is not None
    row = next(row for row in card.timeline if row.kind == "hit")
    assert row.marker_x is not None
    assert card.health_curve.plot_x0 <= row.marker_x <= card.health_curve.plot_x1


def test_a_recap_row_on_a_card_with_no_curve_carries_no_marker() -> None:
    # A marker with nothing to sit on is a mark floating over a table.
    loaded = a_loaded_run_with_a_death_the_log_reported_no_health_for()
    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]
    assert card.health_curve is None
    assert all(row.marker_x is None for row in card.timeline)


def test_every_marker_id_on_the_page_is_unique_across_cards() -> None:
    # Two deaths in one run each produce a row zero. The script looks a marker
    # up by id, so a collision would light the wrong card's curve.
    cards = build_deaths(a_loaded_run_with_two_deaths(), NO_DEFENSIVES, NO_CONSUMABLES)
    ids = [row.marker_id for card in cards for row in card.timeline]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/domain/report/test_build_deaths.py -k marker -v`
Expected: FAIL with `AttributeError: 'RecapRow' object has no attribute 'marker_x'`

- [ ] **Step 3: Add the fields and export the x arithmetic**

In `src/wowperf/domain/report/model.py`, add to `RecapRow`:

```python
    marker_id: str = ""
    """This row's own element id, shared with the marker it lights on the curve.

    Unique across the page: two deaths in one run each have a row zero, and the
    script resolves a marker by id.
    """
    marker_x: float | None = None
    """Where this row's moment falls on the curve, or None when there is no curve
    to place it on. In the curve's own coordinate space, from `curve_x`."""
```

and to `DeathCard`:

```python
    slug: str = ""
    """This card's fragment id, unique within the report. Every marker id on the
    card is built from it."""
```

In `health_curve.py`, rename the private `_x` usage into a public helper the card can share:

```python
def curve_x(timestamp_ms: int, death: Death) -> float:
    """Where an instant of the run-up falls on the curve's axis.

    Exported so a recap row's marker and the curve's own points are placed by
    one piece of arithmetic. A row computing its own x would drift the first
    time the plot's margins changed.
    """
    start_ms = window_start(death)
    span_ms = death.timestamp_ms - start_ms
    return _x(timestamp_ms, start_ms, span_ms)
```

- [ ] **Step 4: Fill them in the builder**

In `deaths.py`, give `_recap_row` the extra arguments and set the fields:

```python
def _recap_row(
    event: RecapEvent, death: Death, names: dict[int, str], marker_id: str, has_curve: bool
) -> RecapRow:
```

with, in the returned `RecapRow`:

```python
        marker_id=marker_id,
        marker_x=curve_x(event.timestamp_ms, death) if has_curve else None,
```

and in `build_deaths`, build the curve before the rows so `has_curve` is known, and number both:

```python
    for index, death in enumerate(sorted(loaded.deaths, key=lambda d: d.timestamp_ms)):
        ...
        curve = build_health_curve(events, readings_in_window(loaded, death), death)
        slug = f"death-{index}"
        timeline = tuple(
            _recap_row(event, death, names, f"{slug}-e{position}", curve is not None)
            for position, event in enumerate(events)
        )
```

passing `slug=slug` and `health_curve=curve` to the `DeathCard`.

- [ ] **Step 5: Run the builder tests to verify they pass**

Run: `uv run pytest tests/domain/report/test_build_deaths.py -v`
Expected: PASS

- [ ] **Step 6: Add the marker to the markup and the allowlist entry**

In `_deaths.html.j2`, inside the `health_curve` macro, after the readings loop, take the card's
rows as a macro argument and draw one hidden marker each:

```jinja
  {% for row in rows %}
  {% if row.marker_x is not none %}
  <line class="hp-marker" id="{{ row.marker_id }}-mark"
        x1="{{ row.marker_x }}" y1="{{ curve.plot_y0 }}"
        x2="{{ row.marker_x }}" y2="{{ curve.plot_y1 }}"></line>
  {% endif %}
  {% endfor %}
```

`plot_y0` and `plot_y1` are new `HealthCurve` fields carrying `PLOT_TOP` and `PLOT_BOTTOM`.
They are named for the axis they bound, as `plot_x0` and `plot_x1` already are,
which the builder already knows and the template must not. Add both to
`NUMBERS_THAT_ARE_NOT_TOTALS` in `test_html_invariants.py`:

```python
    (HealthCurve, "plot_y0"),       # a viewBox coordinate, not a quantity
    (HealthCurve, "plot_y1"),       # a viewBox coordinate, not a quantity
    (RecapRow, "marker_x"),         # a viewBox coordinate, not a quantity
```

Give each table row its id and a focus target:

```jinja
        <tr class="{{ row.kind }}" id="{{ row.marker_id }}" tabindex="0">
```

- [ ] **Step 7: Write the failing script test**

Add to `tests/adapters/render/test_html_invariants.py`:

```python
def test_the_script_lights_a_curve_marker_by_id_and_computes_no_position() -> None:
    # Spec 3.2: every coordinate is computed in Python. The script may toggle a
    # class on a marker already placed; the moment it multiplies or divides to
    # find an x, the arithmetic has left the tested layer.
    html = rich_html()
    body = re.findall(r"<script\b[^>]*>(.*?)</script>", html, flags=re.S | re.I)[0]
    assert "hp-marker" in html
    assert "classList" in body
    assert "getBoundingClientRect" not in body
    assert "getAttribute" in body
```

- [ ] **Step 8: Grow the script by one handler**

Append inside the IIFE in `report.js.j2`, before the closing `})();`:

```javascript
  // Lighting a marker the builder already placed. No geometry here: the x of
  // every marker was computed in Python and is already in the document, so
  // this only decides which of them is visible.
  var rows = document.querySelectorAll("tr[id]");
  for (var r = 0; r < rows.length; r++) {
    rows[r].addEventListener("mouseenter", light);
    rows[r].addEventListener("mouseleave", darken);
    rows[r].addEventListener("focus", light);
    rows[r].addEventListener("blur", darken);
  }

  function markerOf(row) {
    return document.getElementById(row.getAttribute("id") + "-mark");
  }

  function light(event) {
    var mark = markerOf(event.currentTarget);
    if (mark) { mark.classList.add("lit"); }
  }

  function darken(event) {
    var mark = markerOf(event.currentTarget);
    if (mark) { mark.classList.remove("lit"); }
  }
```

and the CSS:

```css
/* Placed by the builder, hidden until the row it belongs to is hovered or
   focused. Hidden by opacity rather than by display so the browser has no
   layout to recompute when it appears. */
.hp-marker { stroke: var(--extra); stroke-width: 1.5; opacity: 0; }
.hp-marker.lit { opacity: 1; }
tr[id]:hover td { background: var(--line); }
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `uv run pytest tests/adapters/render/ -v`
Expected: PASS, `test_the_page_executes_only_its_own_script` included and unmodified.

- [ ] **Step 10: Amend the prose in CLAUDE.md**

Replace the invariant's script clause under "Invariants not to break" with, verbatim:

```markdown
- **The report loads nothing.** One HTML file, opened from disk, with no stylesheet link, no
  `@import`, no remote `src`, and exactly one inline script. That script may show, hide and
  highlight what is already on the page; it may not fetch, write text, or read storage, and
  `tests/adapters/render/test_html_invariants.py` enforces the list. Icons are embedded as
  data URIs for this reason.
```

- [ ] **Step 11: Regenerate the golden file, run the gate, commit**

```bash
uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add CLAUDE.md src/wowperf/domain/report/ src/wowperf/adapters/render/ tests/domain/report/test_build_deaths.py tests/adapters/render/test_html_invariants.py tests/adapters/render/golden/minimal.html
```

Commit subject: `Mark the health curve where the reader is looking`

---

### Task 7: A defensive press shows the window it covered

Spec §4.2, third part. Needs Task 2's bands. "The shield expired before the killing blow" becomes
something seen rather than worked out.

**Files:**
- Create: `src/wowperf/domain/report/cover.py`
- Modify: `src/wowperf/domain/report/model.py` (`RecapRow`)
- Modify: `src/wowperf/domain/report/deaths.py`
- Modify: `src/wowperf/adapters/render/_deaths.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/domain/report/test_cover.py` *(new)*, `tests/domain/report/test_build_deaths.py`

**Interfaces:**
- Consumes: `LoadedRun.auras_by_actor` from Task 2; `RecapRow.marker_id` from Task 6.
- Produces: `wowperf.domain.report.cover.clipped_bands(aura, start_ms, end_ms) -> tuple[tuple[int, int], ...]`
  — every band of one aura clipped to a window, in milliseconds, merged so overlap counts once.
  Task 11 reads the same function.
- Produces: `RecapRow.cover_x: float | None = None` and `RecapRow.cover_width: float | None = None`.

- [ ] **Step 1: Write the failing cover test**

Create `tests/domain/report/test_cover.py`:

```python
def test_a_band_is_clipped_to_the_window_rather_than_counted_whole() -> None:
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=8000, uses=1,
                bands=(AuraBand(start_ms=0, end_ms=10_000),))
    assert clipped_bands(aura, 4_000, 8_000) == ((4_000, 8_000),)


def test_overlapping_bands_are_merged_so_cover_never_exceeds_the_window() -> None:
    # Nothing in the aura table's response promises the bands it hands back are
    # disjoint, and two overlapping bands drawn as two rectangles would paint
    # the same second twice.
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=8000, uses=2,
                bands=(AuraBand(start_ms=0, end_ms=6_000), AuraBand(start_ms=4_000, end_ms=9_000)))
    assert clipped_bands(aura, 0, 10_000) == ((0, 9_000),)


def test_a_band_wholly_outside_the_window_yields_nothing() -> None:
    aura = Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=1000, uses=1,
                bands=(AuraBand(start_ms=0, end_ms=1_000),))
    assert clipped_bands(aura, 5_000, 9_000) == ()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/domain/report/test_cover.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.domain.report.cover'`

- [ ] **Step 3: Write the module**

Create `src/wowperf/domain/report/cover.py`:

```python
# ABOUTME: Aura bands clipped to a drawing's window, merged, as milliseconds.
# ABOUTME: One piece of arithmetic behind every cover window the report draws.

from wowperf.domain.auras import Aura


def clipped_bands(aura: Aura, start_ms: int, end_ms: int) -> tuple[tuple[int, int], ...]:
    """Every stretch this aura was up inside the window, merged, oldest first.

    Clipped rather than counted whole, so a band that began before the window
    contributes only the part the drawing covers. Merged for the reason
    `auras.uptime_seconds_in` merges: nothing in the aura table's own response
    promises the bands it hands back are disjoint, and two overlapping bands
    drawn as two rectangles paint the same second twice.
    """
    clipped = sorted(
        (max(band.start_ms, start_ms), min(band.end_ms, end_ms))
        for band in aura.bands
        if min(band.end_ms, end_ms) > max(band.start_ms, start_ms)
    )
    if not clipped:
        return ()
    merged = [clipped[0]]
    for low, high in clipped[1:]:
        last_low, last_high = merged[-1]
        if low <= last_high:
            merged[-1] = (last_low, max(last_high, high))
        else:
            merged.append((low, high))
    return tuple(merged)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/domain/report/test_cover.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing card test**

Add to `tests/domain/report/test_build_deaths.py`:

```python
def test_a_pressed_defensive_row_carries_the_window_that_press_covered() -> None:
    # The band is measured: the aura table states when the buff was up. Only
    # the width the reader sees is arithmetic, and it is arithmetic done here.
    loaded = a_loaded_run_with_a_pressed_defensive_and_its_band()
    card = build_deaths(loaded, ARCANE, NO_CONSUMABLES)[0]
    row = next(row for row in card.timeline if row.kind == "cast")
    assert row.cover_x is not None
    assert row.cover_width is not None
    assert row.cover_width > 0


def test_a_press_with_no_band_in_the_log_draws_no_cover_window() -> None:
    # A report fetched without an aura table, or a press whose buff the table
    # never recorded, must draw nothing rather than a window the width of a
    # guess.
    loaded = a_loaded_run_with_a_pressed_defensive_and_no_auras()
    card = build_deaths(loaded, ARCANE, NO_CONSUMABLES)[0]
    assert all(row.cover_width is None for row in card.timeline)
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/domain/report/test_build_deaths.py -k cover -v`
Expected: FAIL with `AttributeError: 'RecapRow' object has no attribute 'cover_x'`

- [ ] **Step 7: Add the fields and fill them**

In `model.py`, add to `RecapRow`:

```python
    cover_x: float | None = None
    """The left edge of the window this press covered, in the curve's coordinate
    space, or None on a row that is not a press or whose buff the aura table
    never recorded. Drawn only where the log stated a band."""
    cover_width: float | None = None
```

In `deaths.py`, add the helper and call it once per row:

```python
def _cover_of(
    event: RecapEvent, death: Death, auras: PlayerAuras | None
) -> tuple[float | None, float | None]:
    """Where this press's buff was up, in the curve's coordinate space.

    The window containing the press, not the ability's whole history: the row
    describes one cast, and an earlier band of the same buff belongs to an
    earlier one. Both values are None where no aura table was fetched, where
    the table recorded no band for this ability, or where the press's own band
    does not reach into the run-up the card draws.
    """
    if auras is None or event.kind != CAST:
        return (None, None)
    aura = next((one for one in auras.on_self if one.ability_id == event.ability_id), None)
    if aura is None:
        return (None, None)
    windows = clipped_bands(aura, window_start(death), death.timestamp_ms)
    holding = next(
        (
            (start, end)
            for start, end in windows
            if start <= event.timestamp_ms <= end
        ),
        None,
    )
    if holding is None:
        return (None, None)
    start_x = curve_x(holding[0], death)
    return (start_x, round(curve_x(holding[1], death) - start_x, PRECISION))
```

with `PRECISION = 1` imported from `health_curve`, and in `build_deaths`, resolve the player's
auras once per card before the row loop:

```python
        auras = loaded.auras_by_actor.get(death.actor_id)
```

passing it into `_recap_row`, which sets `cover_x, cover_width = _cover_of(event, death, auras)`.

Add both fields to `NUMBERS_THAT_ARE_NOT_TOTALS` with the comment
`# a viewBox coordinate, not a quantity`.

- [ ] **Step 8: Draw it**

In the `health_curve` macro in `_deaths.html.j2`, beside the marker:

```jinja
  {% if row.cover_width is not none %}
  <rect class="hp-cover" id="{{ row.marker_id }}-cover"
        x="{{ row.cover_x }}" y="{{ curve.plot_y0 }}"
        width="{{ row.cover_width }}" height="{{ curve.plot_height }}"></rect>
  {% endif %}
```

`plot_height` is a new `HealthCurve` field, `PLOT_BOTTOM - PLOT_TOP`, computed in the builder.
Add it to the allowlist. Extend the script's `light`/`darken` to toggle the cover element too, by
the same id-plus-suffix rule, and style it:

```css
/* Behind the line, not over it: the window is context for the curve, and a
   filled band drawn on top would hide the shape a reader came for. */
.hp-cover { fill: var(--ours); opacity: 0; }
.hp-cover.lit { opacity: 0.18; }
```

- [ ] **Step 9: Run the tests, regenerate the golden file, run the gate, commit**

```bash
uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/domain/report/ src/wowperf/adapters/render/ tests/domain/report/ tests/adapters/render/
```

Commit subject: `Show how long a defensive covered the seconds before a death`

---

### Task 8: A death's events say what the log recorded about them

Spec §4.3. Needs Task 1's fields and Task 4's macro. A damage event is the richest thing on the
page for this: `unmitigatedAmount`, `mitigated`, `absorbed` and `amount` are four fields of one
event, so the tooltip reports a single hit and apportions nothing.

**Files:**
- Create: `src/wowperf/domain/report/tooltip.py`
- Modify: `src/wowperf/domain/analysis/recap.py` (`RecapEvent`)
- Modify: `src/wowperf/domain/report/model.py` (`Tooltip`, `RecapRow.tooltip`)
- Modify: `src/wowperf/domain/report/deaths.py`
- Modify: `src/wowperf/adapters/render/_macros.html.j2`, `_deaths.html.j2`, `report.css.j2`
- Test: `tests/domain/report/test_tooltip.py` *(new)*,
  `tests/adapters/render/test_html_invariants.py`

**Interfaces:**
- Consumes: `DamageTakenEvent.mitigated`, `.overkill`, `.source_id`, `.is_area`, `.is_tick` from
  Task 1; the `ability` macro from Task 4.
- Produces: `Tooltip(lines: tuple[TooltipLine, ...] = (), note: str = "")` and
  `TooltipLine(label: str, value: str)` on `report/model.py`; `RecapRow.tooltip: Tooltip | None`.
- Produces: `wowperf.domain.report.tooltip.hit_tooltip(event) -> Tooltip`,
  `heal_tooltip(event, names) -> Tooltip`, `absorb_tooltip(event, names) -> Tooltip`.
- Produces: the macro `ability(ability_id, name, tooltip=None)` — the third argument is optional,
  so Task 4's call sites keep working untouched.

- [ ] **Step 1: Write the failing tooltip tests**

Create `tests/domain/report/test_tooltip.py`:

```python
def test_a_hit_reports_its_four_figures_and_attributes_none_of_them() -> None:
    event = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar", ability_id=7,
                       amount=67343, absorbed=0, mitigated=15609, unmitigated=145434)
    labels = {line.label: line.value for line in hit_tooltip(event).lines}
    assert labels["Struck for"] == "145,434"
    assert labels["Mitigated"] == "15,609"
    assert labels["Reached health"] == "67,343"


def test_a_hit_tooltip_never_says_what_did_the_mitigating() -> None:
    # Spec 5. `mitigated` is one figure the log never attributes, and a tooltip
    # that named a cause would be the debuff half's failure again.
    event = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar", ability_id=7,
                       amount=1, mitigated=99, unmitigated=100)
    note = hit_tooltip(event).note
    assert "does not attribute" in note
    for line in hit_tooltip(event).lines:
        assert "%" not in line.value


def test_only_a_lethal_blow_reports_overkill() -> None:
    lethal = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar", ability_id=7,
                        amount=67343, unmitigated=145434, overkill=62482)
    ordinary = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar", ability_id=7,
                          amount=100, unmitigated=100)
    assert any(line.label == "Overkill" for line in hit_tooltip(lethal).lines)
    assert not any(line.label == "Overkill" for line in hit_tooltip(ordinary).lines)


def test_a_heal_tooltip_says_the_log_reports_no_overheal() -> None:
    # Recorded 2026-09-06 in the wcl-api skill: the healing stream returns no
    # such field. Saying so beats omitting the row in silence.
    event = RecapEvent(kind=HEAL, timestamp_ms=1000, ability_name="Holy Word: Serenity",
                       ability_id=9, amount=42_000, source_id=3)
    assert "no overheal" in heal_tooltip(event, {3: "Bríala"}).note
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/domain/report/test_tooltip.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.domain.report.tooltip'`

- [ ] **Step 3: Carry the fields to the recap event**

In `src/wowperf/domain/analysis/recap.py`, add to `RecapEvent`:

```python
    # What the hit was worth before mitigation and absorption, and what the game
    # reduced. `mitigated` is one figure the log never attributes to a cause.
    unmitigated: int = 0
    mitigated: int = 0
    overkill: int = 0
    is_area: bool = False
    is_tick: bool = False
```

and set them in `recap_timeline`'s `HIT` branch from the damage event.

- [ ] **Step 4: Write the module**

Create `src/wowperf/domain/report/tooltip.py`:

```python
# ABOUTME: What one event of a death is worth saying, as labelled lines the page prints.
# ABOUTME: Reports the fields of a single event and apportions none of them between causes.

from wowperf.domain.analysis.recap import RecapEvent
from wowperf.domain.report.model import Tooltip, TooltipLine

MITIGATION_IS_NOT_ATTRIBUTED = (
    "The log does not attribute what reduced this hit: armour, Versatility, spec passives, a "
    "defensive and a teammate's external all land in one figure."
)
"""Said wherever `mitigated` is printed.

The figure is real and the causes are not separable, so the tooltip states the
one and refuses the other. Printing the figure without this sentence invites
exactly the reading the design's section 5 forbids.
"""

NO_OVERHEAL_FIELD = (
    "The healing stream reports no overheal, so this is what landed, not what was wasted."
)
"""Recorded 2026-09-06 in the wcl-api skill. Saying so beats omitting the row in silence."""


def hit_tooltip(event: RecapEvent) -> Tooltip:
    """One hit, in the four figures the log gives for it.

    `unmitigated` is how hard it swung, `mitigated` what the game took off,
    `absorbed` what a shield soaked and `amount` what reached health. Overkill
    appears only where the log recorded it, which is only on a lethal blow.
    """
    lines = [
        TooltipLine(label="Struck for", value=f"{event.unmitigated:,}"),
        TooltipLine(label="Mitigated", value=f"{event.mitigated:,}"),
    ]
    if event.absorbed:
        lines.append(TooltipLine(label="Absorbed", value=f"{event.absorbed:,}"))
    lines.append(TooltipLine(label="Reached health", value=f"{event.amount:,}"))
    if event.overkill:
        lines.append(TooltipLine(label="Overkill", value=f"{event.overkill:,}"))
    if event.is_area:
        lines.append(TooltipLine(label="Area", value="yes"))
    if event.is_tick:
        lines.append(TooltipLine(label="Periodic", value="yes"))
    return Tooltip(lines=tuple(lines), note=MITIGATION_IS_NOT_ATTRIBUTED)


def heal_tooltip(event: RecapEvent, names: dict[int, str]) -> Tooltip:
    """One heal that landed, and who cast it."""
    source = event.source_id
    caster = "an unknown source" if source is None else names.get(source, "an unknown source")
    return Tooltip(
        lines=(
            TooltipLine(label="Healed for", value=f"{event.amount:,}"),
            TooltipLine(label="From", value=caster),
        ),
        note=NO_OVERHEAL_FIELD,
    )


def absorb_tooltip(event: RecapEvent, names: dict[int, str]) -> Tooltip:
    """One shield, and the hit it soaked."""
    source = event.source_id
    caster = "an unknown source" if source is None else names.get(source, "an unknown source")
    return Tooltip(
        lines=(
            TooltipLine(label="Soaked", value=f"{event.amount:,}"),
            TooltipLine(label="Shield from", value=caster),
        )
    )
```

Add the two values it returns to `src/wowperf/domain/report/model.py`:

```python
class TooltipLine(Frozen):
    """One labelled figure of a tooltip. Formatted here; the template prints it."""

    label: str
    value: str


class Tooltip(Frozen):
    """What hovering an ability says: measured lines, and the caveat they need.

    A tooltip with no lines is never built: the panel exists to carry figures,
    and an empty one is a hover target that rewards nothing.
    """

    lines: tuple[TooltipLine, ...] = ()
    note: str = ""
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/domain/report/test_tooltip.py -v`
Expected: PASS

- [ ] **Step 6: Attach it, render it, and prove it is inert**

Add `tooltip: Tooltip | None = None` to `RecapRow`, fill it in `_recap_row` by `event.kind`,
extend the `ability` macro with the optional third argument:

```jinja
{% macro ability(ability_id, name, tooltip=None) %}
<span class="ability">{% if ability_id in icons_by_id %}<span class="icon i-{{ ability_id }}" aria-hidden="true"></span>{% endif %}<span class="ability-name">{{ name }}</span>
{%- if tooltip %}<span class="tip" role="note">
{%- for line in tooltip.lines %}<span class="tip-line"><span class="tip-label">{{ line.label }}</span><span class="tip-value">{{ line.value }}</span></span>{% endfor %}
{%- if tooltip.note %}<span class="tip-note">{{ tooltip.note }}</span>{% endif %}</span>{% endif %}</span>
{%- endmacro %}
```

and style it as a CSS-only panel:

```css
/* Revealed by hover and by keyboard focus, and rendered into the page whether
   or not it is shown: the panel is markup the builder wrote, never text the
   script fetches or writes. */
.ability { position: relative; }
.tip { position: absolute; left: 0; bottom: calc(100% + 6px); z-index: 5; display: none;
  min-width: 220px; max-width: 320px; white-space: normal; padding: 8px 10px;
  background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  font-size: 12px; line-height: 1.5; box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45); }
.ability:hover .tip, .ability:focus-within .tip { display: block; }
.tip-line { display: flex; justify-content: space-between; gap: 12px; }
.tip-label { color: var(--ink-dim); }
.tip-value { font-variant-numeric: tabular-nums; }
.tip-note { display: block; margin-top: 6px; color: var(--ink-faint); }
```

Add to `tests/adapters/render/test_html_invariants.py`:

```python
def test_a_tooltip_is_markup_the_builder_wrote_and_never_names_a_mitigation_source() -> None:
    # Spec 5: no tooltip renders a figure attributed to a single mitigation
    # source. This reads the whole page rather than one tooltip, so a second
    # tooltip added later is covered the day it exists.
    html = rich_html()
    assert 'class="tip"' in html
    body = re.findall(r"<script\b[^>]*>(.*?)</script>", html, flags=re.S | re.I)[0]
    assert "tip" not in body
    assert "prevented" not in html.lower()
    assert "damage reduction" not in html.lower()
```

- [ ] **Step 7: Run the tests, regenerate the golden file, run the gate, commit**

```bash
uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/domain/ src/wowperf/adapters/render/ tests/domain/report/test_tooltip.py tests/adapters/render/
```

Commit subject: `Say what the log recorded about each event of a death`

---

### Task 9: The run timeline names its pulls and draws them as columns

Spec §4.4, first two changes. The grey boxes were pulls and nothing said so.

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`PlayerTimeline`)
- Modify: `src/wowperf/domain/report/player_timeline.py:175-187` (`_pull_bands`)
- Modify: `src/wowperf/adapters/render/_player_timeline.html.j2:13-15`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `PlayerTimeline.column_height: float` and `PlayerTimeline.pull_label_y: float`;
  `TimelineBlock.label` on a player timeline now reads the boss's name or `Pull 7`.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/report/test_build_player_timeline.py`:

```python
def test_a_boss_pull_takes_its_name_and_a_trash_pull_takes_its_index() -> None:
    # `Pull.name`, `Pull.is_boss` and `Pull.index` are already on the domain
    # model and the timeline used none of them. A reader looking at a press
    # should be able to say which pull it landed in.
    loaded = a_loaded_run(pulls=(a_pull(index=1, name="Loa Speaker Nanea", encounter_id=0),
                                 a_pull(index=2, name="Nalorakk", encounter_id=2571)))
    timeline = build_player_timeline(loaded, 1, "Mage", "Arcane", NO_DEFENSIVES, NO_THROUGHPUT)
    assert [block.label for block in timeline.pulls] == ["Pull 1", "Nalorakk"]


def test_a_pull_is_drawn_as_a_column_the_height_of_the_chart() -> None:
    # A band above the tracks floats over them. A column runs behind them, so a
    # press visibly lands inside a pull.
    loaded = a_loaded_run(pulls=(a_pull(index=1, name="Nalorakk", encounter_id=2571),))
    timeline = build_player_timeline(loaded, 1, "Mage", "Arcane", NO_DEFENSIVES, NO_THROUGHPUT)
    assert timeline.column_height > timeline.band_height
    assert timeline.band_y + timeline.column_height <= timeline.height
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/domain/report/test_build_player_timeline.py -k pull -v`
Expected: FAIL on the label list — the first entry is the raw pull name

- [ ] **Step 3: Name the pulls and size the column**

In `player_timeline.py`, in `_pull_bands`, replace `label=pull.name` with:

```python
            # A boss's name is worth the space; a trash pack's generated name is
            # the first mob the log happened to see, which names nothing a reader
            # can find again. The index is what the rest of the report calls it.
            label=pull.name if pull.is_boss else f"Pull {pull.index}",
```

and in `build_player_timeline`, pass `column_height=height - BAND_Y - BOTTOM_MARGIN` and
`pull_label_y=BAND_Y - PULL_LABEL_GAP` with a new module constant
`PULL_LABEL_GAP = 3.0`. Add both fields to `NUMBERS_THAT_ARE_NOT_TOTALS`.

- [ ] **Step 4: Draw the column and the name**

Replace the band loop in `_player_timeline.html.j2`:

```jinja
  {% for band in timeline.pulls %}
  <rect class="{{ band.css_class }}" x="{{ band.x }}" y="{{ timeline.band_y }}"
        width="{{ band.width }}" height="{{ timeline.column_height }}"><title>{{ band.label }}</title></rect>
  {% if band.is_boss %}
  <text class="pull-name" x="{{ band.x }}" y="{{ timeline.pull_label_y }}">{{ band.label }}</text>
  {% endif %}
  {% endfor %}
```

Only boss pulls are labelled on the chart: at this scale a run's forty trash names overlap into a
smear, and every pull's name is still one hover away in its `<title>`.

```css
/* Behind every track, so a press reads as landing inside a pull. Faint enough
   that forty of them do not become the drawing. */
.pull-band { fill: var(--line); opacity: 0.55; }
.pull-name { fill: var(--ink-dim); font-size: 8px; }
```

- [ ] **Step 5: Run the tests, regenerate the golden file, run the gate, commit**

```bash
uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/domain/report/ src/wowperf/adapters/render/ tests/domain/report/test_build_player_timeline.py tests/adapters/render/
```

Commit subject: `Draw a pull as a column and name the bosses`

---

### Task 10: A cooldown shows when it comes back, and the damage row gets a scale

Spec §4.4, third and fourth changes. "Available again" has no mark today and is read as an
absence.

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`CooldownRow`, `DamageTrack`)
- Modify: `src/wowperf/domain/report/player_timeline.py`
- Modify: `src/wowperf/adapters/render/_player_timeline.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Consumes: Task 9's `column_height`.
- Produces: `CooldownRow.ready_ticks: tuple[float, ...] = ()`; `DamageTrack.axis_top_y: float`,
  `DamageTrack.axis_top_label: str`, `DamageTrack.bucket_caption: str`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_cooldown_that_finishes_inside_the_run_is_marked_ready_again() -> None:
    # The stretch after a press is the cooldown; its end is the moment the
    # ability came back, and an unmarked end reads as an absence rather than as
    # an event.
    loaded = a_loaded_run_with_one_press_early_in_a_long_run()
    timeline = build_player_timeline(loaded, 1, "Mage", "Arcane", ARCANE, NO_THROUGHPUT)
    row = timeline.cooldowns[0]
    assert len(row.ready_ticks) == 1
    assert row.ready_ticks[0] > row.presses[0].x


def test_a_cooldown_still_running_when_the_run_ends_is_not_marked_ready() -> None:
    # Marking a tick at the axis end would claim the ability came back at the
    # moment the run finished, which the log never says.
    loaded = a_loaded_run_with_one_press_seconds_before_the_end()
    timeline = build_player_timeline(loaded, 1, "Mage", "Arcane", ARCANE, NO_THROUGHPUT)
    assert timeline.cooldowns[0].ready_ticks == ()


def test_the_damage_row_states_its_own_scale_and_bucket_width() -> None:
    loaded = a_loaded_run_with_damage_taken()
    timeline = build_player_timeline(loaded, 1, "Mage", "Arcane", NO_DEFENSIVES, NO_THROUGHPUT)
    assert timeline.damage is not None
    assert timeline.damage.axis_top_label != ""
    assert "5 seconds" in timeline.damage.bucket_caption
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/domain/report/test_build_player_timeline.py -k "ready or scale" -v`
Expected: FAIL with `AttributeError: 'CooldownRow' object has no attribute 'ready_ticks'`

- [ ] **Step 3: Compute the ticks and the axis**

In `_cooldown_rows`, alongside each `unavailable` span, emit the tick where that span ends — only
when the cooldown finished before the axis did:

```python
                ready_ticks=tuple(
                    round(TRACK_ORIGIN_X + end * scale, PRECISION)
                    for end in (
                        (at - origin_ms) / 1000 + ability.cooldown_seconds for at in presses
                    )
                    if end < span_seconds
                ),
```

In `_damage_track`, add:

```python
        axis_top_y=round(DAMAGE_BASELINE_Y - DAMAGE_HEIGHT, PRECISION),
        axis_top_label=f"{peak:,}",
        bucket_caption=(
            f"One bar is {int(BUCKET_SECONDS)} seconds of unmitigated damage taken. The axis "
            f"runs from nothing to this player's own tallest bucket, never the group's."
        ),
```

and keep `peak_label` as it is: it names the same figure in a sentence, and the axis label is the
figure itself.

- [ ] **Step 4: Draw them**

In `_player_timeline.html.j2`, after each row's presses:

```jinja
  {% for tick in row.ready_ticks %}
  <rect class="ready-again" x="{{ tick }}" y="{{ row.baseline_y }}"
        width="{{ timeline.press_width }}" height="{{ timeline.row_height }}"/>
  {% endfor %}
```

and above the damage bars:

```jinja
  <line class="damage-axis" x1="{{ timeline.label_x }}" y1="{{ timeline.damage.axis_top_y }}"
        x2="{{ timeline.width }}" y2="{{ timeline.damage.axis_top_y }}"/>
  <text class="tick-label row-label" x="{{ timeline.label_x }}"
        y="{{ timeline.damage.axis_top_y }}">{{ timeline.damage.axis_top_label }}</text>
```

with the caption rendered beside `peak_label` beneath the drawing. Style:

```css
/* An open tick, not a filled mark: a press is something the player did and a
   comeback is something that merely became true, and the two must not read as
   the same event. */
.ready-again { fill: none; stroke: var(--ours); stroke-width: 1; }
.damage-axis { stroke: var(--line); stroke-width: 1; }
```

Extend `LEGEND` in `player_timeline.py` with one sentence: `"An open tick is the moment the
cooldown finished and the ability was available again."`

Add `ready_ticks` (a tuple, so no allowlist entry) and the two new `DamageTrack` numeric fields to
`NUMBERS_THAT_ARE_NOT_TOTALS`.

- [ ] **Step 5: Run the tests, regenerate the golden file, run the gate, commit**

```bash
uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/domain/report/ src/wowperf/adapters/render/ tests/domain/report/test_build_player_timeline.py tests/adapters/render/
```

Commit subject: `Mark when a cooldown came back and scale the damage row`

---

### Task 11: Cover windows on the run timeline, at true scale

Spec §4.4, fourth change. 570 px spans 1980 seconds, so a five-second shield is 1.4 px. The
sliver stays: at true scale it says something worth saying, and drawing it bigger is a lie about
duration.

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`CooldownRow.cover`)
- Modify: `src/wowperf/domain/report/player_timeline.py`
- Modify: `src/wowperf/adapters/render/_player_timeline.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Consumes: `clipped_bands` from Task 7; `LoadedRun.auras_by_actor` from Task 2.
- Produces: `CooldownRow.cover: tuple[Span, ...] = ()`, reusing the existing `Span`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_cooldown_row_carries_the_windows_its_buff_actually_covered() -> None:
    loaded = a_loaded_run_with_a_press_and_its_band()
    timeline = build_player_timeline(loaded, 1, "Mage", "Arcane", ARCANE, NO_THROUGHPUT)
    assert timeline.cooldowns[0].cover != ()


def test_a_cover_window_is_never_widened_to_make_it_visible() -> None:
    # The guard the spec asks for. MIN_BLOCK_WIDTH floors a pull so it does not
    # vanish; a cover window has no such floor, because its width IS the claim.
    # A five-second buff on a thirty-three-minute axis is 1.4 units, and 1.4 is
    # what must be drawn.
    loaded = a_loaded_run_with_a_five_second_band_on_a_long_run()
    timeline = build_player_timeline(loaded, 1, "Mage", "Arcane", ARCANE, NO_THROUGHPUT)
    span = timeline.cooldowns[0].cover[0]
    assert span.width < MIN_BLOCK_WIDTH


def test_a_player_with_no_aura_table_gets_no_cover_windows() -> None:
    loaded = a_loaded_run_with_a_press_and_no_auras()
    timeline = build_player_timeline(loaded, 1, "Mage", "Arcane", ARCANE, NO_THROUGHPUT)
    assert timeline.cooldowns[0].cover == ()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/domain/report/test_build_player_timeline.py -k cover -v`
Expected: FAIL with `AttributeError: 'CooldownRow' object has no attribute 'cover'`

- [ ] **Step 3: Add the field and compute the spans**

Add to `CooldownRow`:

```python
    cover: tuple[Span, ...] = ()
    """Every stretch this ability's buff was actually up, from the aura table's
    own bands, clipped to the axis.

    Drawn at true scale and never floored: a five-second buff on a
    thirty-three-minute axis is about one and a half units wide, and widening it
    to make it visible would be a claim about duration the log did not make.
    Empty where no aura table was fetched for this player, or where the table
    recorded no band for the ability.
    """
```

In `player_timeline.py`, give `_cooldown_rows` an `auras: PlayerAuras | None` argument, add this
helper beside it, and set `cover=_cover_spans(ability.ability_id, auras, scale, origin_ms, span_seconds)`
on each row:

```python
def _cover_spans(
    ability_id: int,
    auras: PlayerAuras | None,
    scale: float,
    origin_ms: int,
    span_seconds: float,
) -> tuple[Span, ...]:
    """Every stretch this ability's buff was up, drawn at the axis's own scale.

    `MIN_BLOCK_WIDTH` is deliberately not applied. A pull is floored to that
    width because a pull that vanishes tells the reader nothing; a cover
    window's width *is* the claim, and widening a five-second buff on a
    thirty-three-minute axis from 1.4 units to 2 would overstate its duration by
    nearly half.
    """
    if auras is None:
        return ()
    aura = next((one for one in auras.on_self if one.ability_id == ability_id), None)
    if aura is None:
        return ()
    end_ms = origin_ms + int(span_seconds * 1000)
    return tuple(
        Span(
            x=round(TRACK_ORIGIN_X + (start - origin_ms) / 1000 * scale, PRECISION),
            width=round((end - start) / 1000 * scale, PRECISION),
        )
        for start, end in clipped_bands(aura, origin_ms, end_ms)
    )
```

`build_player_timeline` gains the same argument and reads
`loaded.auras_by_actor.get(actor_id)` to fill it.

- [ ] **Step 4: Draw it and grade it**

In the template, before the presses so a press mark sits on top:

```jinja
  {% for span in row.cover %}
  <rect class="cover" x="{{ span.x }}" y="{{ row.baseline_y }}"
        width="{{ span.width }}" height="{{ timeline.row_height }}"/>
  {% endfor %}
```

```css
/* The share of each cycle the ability was doing anything, at true scale. A
   green head on a grey bar. */
.cover { fill: var(--badge-measured); }
```

The cover windows are measured, so extend `BADGE_MEASURED_CAPTION` to
`"the damage bars, the press marks and the cover windows."` — the dimming stays inferred.

- [ ] **Step 5: Run the tests, regenerate the golden file, run the gate, commit**

```bash
uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/domain/report/ src/wowperf/adapters/render/ tests/domain/report/test_build_player_timeline.py tests/adapters/render/
```

Commit subject: `Draw how much of each cooldown cycle a buff actually covered`

---

### Task 12: An ability's tooltip says what it measured

Spec §4.5, the measured and derived tiers. The static tier is out by ruling 5. This is the task
where the spec's Icebound Fortitude example becomes a real tooltip on a death card's availability
row.

**Files:**
- Modify: `src/wowperf/domain/report/tooltip.py`
- Modify: `src/wowperf/domain/report/model.py` (`AvailabilityRow.tooltip`)
- Modify: `src/wowperf/domain/report/deaths.py`
- Modify: `src/wowperf/adapters/render/_deaths.html.j2`
- Test: `tests/domain/report/test_tooltip.py`

**Interfaces:**
- Consumes: `hit_tooltip` and the `Tooltip` value from Task 8; `clipped_bands` from Task 7;
  `DamageTakenEvent.buff_ids` from Task 1; `LoadedRun.auras_by_actor` from Task 2.
- Produces: `wowperf.domain.report.tooltip.ability_tooltip(...) -> Tooltip` and
  `AvailabilityRow.tooltip: Tooltip | None = None`.

- [ ] **Step 1: Write the failing tests**

```python
def a_hit(timestamp_ms: int, swung: int, landed: int, buffs: tuple[int, ...]) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=1, ability_id=100, ability_name="Frigid Roar", amount=swung,
        timestamp_ms=timestamp_ms, health_damage=landed, buff_ids=buffs,
    )


def test_an_ability_tooltip_reports_presses_cover_and_what_arrived_inside_it() -> None:
    # Every figure here is a field on an event the log emitted, or a sum of
    # such fields over a window the aura table stated. Nothing is apportioned.
    tip = ability_tooltip(
        cooldown_seconds=120.0, cover=((1_000, 9_000),),
        hits=(a_hit(2_000, 1_000, 400, (48792,)), a_hit(20_000, 1_000, 800, ())),
        buff_id=48792, presses=1,
    )
    labels = {line.label: line.value for line in tip.lines}
    assert labels["Base cooldown"] == "120 s"
    assert labels["Presses"] == "1"
    assert labels["Cover"] == "8.0 s"
    assert labels["Arrived while it was up"] == "1,000"
    assert labels["Reached health"] == "400"
    assert labels["Mitigated inside / outside"] == "60% / 20%"


def test_an_ability_tooltip_states_the_rate_gap_as_suggestive_not_attributable() -> None:
    # Spec 5: the inside/outside gap is offered as suggestive and never as
    # damage this ability prevented.
    tip = ability_tooltip(
        cooldown_seconds=120.0, cover=((1_000, 9_000),),
        hits=(a_hit(2_000, 1_000, 400, (48792,)),), buff_id=48792, presses=1,
    )
    assert "does not attribute" in tip.note
    assert "suggestive, not attributable" in tip.note
    assert not any("prevented" in line.label.lower() for line in tip.lines)


def test_a_side_with_no_hits_reads_as_a_dash_rather_than_as_perfect_mitigation() -> None:
    # No hits outside the window is not the claim "nothing got through outside
    # the window", and a zero there would read as exactly that.
    tip = ability_tooltip(
        cooldown_seconds=120.0, cover=((1_000, 9_000),),
        hits=(a_hit(2_000, 1_000, 400, (48792,)),), buff_id=48792, presses=1,
    )
    assert tip.lines[-1].value == "60% / --"


def test_an_ability_with_no_band_reports_its_presses_and_no_cover() -> None:
    tip = ability_tooltip(cooldown_seconds=120.0, cover=(), hits=(), buff_id=48792, presses=2)
    assert not any(line.label == "Cover" for line in tip.lines)
    assert {line.label for line in tip.lines} == {"Base cooldown", "Presses"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/domain/report/test_tooltip.py -k ability_tooltip -v`
Expected: FAIL with `ImportError: cannot import name 'ability_tooltip'`

- [ ] **Step 3: Write it**

Append to `src/wowperf/domain/report/tooltip.py`:

```python
RATE_GAP_IS_SUGGESTIVE = (
    "The gap between the two rates is suggestive, not attributable: this ability is one of "
    "several things reducing every hit, and the log separates none of them."
)


def _inside(hit: DamageTakenEvent, buff_id: int, cover: tuple[tuple[int, int], ...]) -> bool:
    """Whether this hit landed while the buff was up.

    The event's own `buffs` list is exact per hit and is the answer wherever the
    log wrote one. Only where it wrote none does this fall back to the aura
    table's bands, which place the hit by timestamp rather than by what the game
    said was on the player.
    """
    if hit.buff_ids:
        return buff_id in hit.buff_ids
    return any(start <= hit.timestamp_ms <= end for start, end in cover)


def _rate(hits: tuple[DamageTakenEvent, ...]) -> str:
    """What share of what swung never reached health, as a whole percent.

    An empty side reads as a dash rather than as zero: no hits is not the same
    claim as hits that were never reduced.
    """
    swung = sum(hit.amount for hit in hits)
    if swung == 0:
        return "--"
    landed = sum(hit.health_damage for hit in hits)
    return f"{round(100 * (swung - landed) / swung)}%"


def ability_tooltip(
    cooldown_seconds: float,
    cover: tuple[tuple[int, int], ...],
    hits: tuple[DamageTakenEvent, ...],
    buff_id: int,
    presses: int,
) -> Tooltip:
    """What the run measured about one ability, and what it refuses to conclude.

    Every figure is a field the log emitted, or a sum of such fields over a
    window the aura table stated. The inside/outside rates are derived from
    those sums and are offered as a comparison, never as damage this ability
    prevented -- see the design's section 5.
    """
    lines = [
        TooltipLine(label="Base cooldown", value=f"{cooldown_seconds:.0f} s"),
        TooltipLine(label="Presses", value=str(presses)),
    ]
    if cover:
        seconds = sum(end - start for start, end in cover) / 1000
        lines.append(TooltipLine(label="Cover", value=f"{seconds:.1f} s"))
        within = tuple(hit for hit in hits if _inside(hit, buff_id, cover))
        without = tuple(hit for hit in hits if not _inside(hit, buff_id, cover))
        lines.append(
            TooltipLine(
                label="Arrived while it was up",
                value=f"{sum(hit.amount for hit in within):,}",
            )
        )
        lines.append(
            TooltipLine(
                label="Reached health",
                value=f"{sum(hit.health_damage for hit in within):,}",
            )
        )
        lines.append(
            TooltipLine(
                label="Mitigated inside / outside",
                value=f"{_rate(within)} / {_rate(without)}",
            )
        )
    return Tooltip(
        lines=tuple(lines),
        note=f"{MITIGATION_IS_NOT_ATTRIBUTED} {RATE_GAP_IS_SUGGESTIVE}",
    )
```

The name is not printed inside the panel: the macro that carries it already renders the ability's
name and icon as the thing being hovered.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/domain/report/test_tooltip.py -v`
Expected: PASS

- [ ] **Step 5: Attach it to the availability rows**

Add `tooltip: Tooltip | None = None` to `AvailabilityRow`, fill it in `_availability_row` for a
row whose `ability_id` resolves in the dying player's auras, and pass it through the `ability`
macro at `_deaths.html.j2`'s availability list.

- [ ] **Step 6: Run the tests, regenerate the golden file, run the gate, commit**

```bash
uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/domain/report/ src/wowperf/adapters/render/ tests/domain/report/test_tooltip.py tests/adapters/render/
```

Commit subject: `Say what a defensive measured, and refuse to say what it prevented`

---

## After the last task

Run the whole thing against the real report and read the page, because
`.claude/lessons.md` and this repository's history both say the offline suite has never caught
the defects a real run finds:

```bash
uv run wowperf analyze 6Kx1P9GbNXrcLdHa --fight 36 --out out
```

Check, in this order: the columns never leave one card alone on a final row; the Provenance tables
are readable rather than merely wide; a tooltip near a card's bottom edge is not clipped (spec §9
flags this as a mockup detail — if it is, fix it with `bottom: auto; top: calc(100% + 6px)` on a
`.tip` inside the last row, not with script); and a five-second cover window is still a sliver.

## Spec coverage

| Spec section | Task |
| --- | --- |
| §3.1 script clause amended | 6 |
| §3.2 every coordinate in Python | every task, enforced by the Task 6 script test |
| §4.1 responsive width | 3 |
| §4.2 hover marker, cover window, dashed line, ringed readings | 5, 6, 7 |
| §4.3 death event tooltips | 1, 8 |
| §4.4 pull columns, names, ready ticks, damage axis, true-scale cover | 9, 10, 11 |
| §4.5 ability tooltips, measured and derived tiers | 12 |
| §4.5.1 which surfaces carry one | settled 2026-09-12 in the design; the two card headings decline one, the player timeline's rows gained theirs |
| §4.5 static tier | **not built** — ruling 5, closed 2026-09-12 in `2026-09-08-icons-and-tooltips-spike.md` §9 |
| §4.6 icon and name as one object | 4 |
| §5 what we refuse to state | 8, 12, both with their own test |
| §6 `buffs` on every damage event | 1, used in 12 |
| §7 description source | **not built** — ruling 5, closed 2026-09-12 in `2026-09-08-icons-and-tooltips-spike.md` §9 |
| §8 tests owed | each in the task that owes it |
