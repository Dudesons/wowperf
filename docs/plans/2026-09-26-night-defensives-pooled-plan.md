# Defensives pooled across pulls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One finding per named player on the night page's boss summary, `progression.repeat.ready.<base>`, counting which of the player's own defensives were up at their deaths across the boss's pulls.

**Architecture:** `repeat_defensives_up` in `defensives.py` runs the existing per-pull rule `defensives_up_at` over every drawn pull of one boss and adds the judgements up. A new `analyse_night_boss` in `night_service.py` is the one place a night boss's summary findings are assembled: the unchanged `analyse_progression`, plus the pooled finding when death cards are on. `cli.py`'s night command calls it; the standalone `progression` command never does. The existing `progression.repeat.` placement draws it on the summary's Repeats tab; no template, view model, query or JSON shape changes.

**Tech Stack:** Python 3.12, pydantic frozen models, Jinja2, pytest. `uv` only: in Bash, `/c/Users/damien/.local/bin/uv.exe`.

**Spec:** `docs/plans/2026-09-26-night-defensives-pooled-design.md`. Read it before Task 1.

## Global Constraints

- Each pull is judged on its own casts by `defensives_up_at` (`defensives.py:56`); the summary adds the judgements up. Ownership is never judged across the whole night (spec §4).
- Count: the player's deaths at which the ability was up. Denominator: the player's deaths on pulls where they cast that ability at least once (spec §4).
- Named when at least one ability was up at two or more of their deaths **on at least two different pulls**. Abilities ordered by count, most first, then by name. Every qualifying player is named; no cap (spec §4).
- Id `progression.repeat.ready.<base>`, `<base>` the player's slug, or `slug.actor_id` when two roster players share a slug (spec §4).
- One ability: title `"<player>: <ability> up at <n> of <m> deaths"`, `ability_id` and `ability_name` set. Several: title `"<player>: <k> defensives up at more than one death"`, no `ability_id`. Evidence: `"<class> <spec>"` first, then one `"<ability> up at <n> of <m> deaths"` line per named ability (spec §4).
- Confidence `inferred`. `player_slug` left empty (spec §4).
- Computed only when death cards are on; never at `--no-deaths`; never by the standalone `progression` command. `analyse_progression` and `METHOD_NO_ANATOMY` unchanged (spec §3, §5).
- No new query, stream, JSON field, view model or template (spec §3).
- `src/wowperf/domain/` performs no I/O (CLAUDE.md).
- No real character name in `tests/`: only `Emberkin`, `Stonewake`, `Bríala`, `Кириллица` (plus `Briala` as the accent-stripped twin). Players on report `cW38jmwdnZfbHVL4` are referred to by class, spec, role or index -- never by name or slug, anywhere.
- Every new test is shown able to fail: break the line it guards, watch it go red, restore. Read `.claude/skills/testing/test-driven-development/SKILL.md` before writing the first test.
- Commits: imperative subject, no prefix, body says why, plain ASCII, last line a `Co-Authored-By:` naming the model that wrote the commit. Commit with `/mingw64/bin/git`. Never `--no-verify`.
- Gate after every task: `uv run ruff check .`, `uv run mypy`, `uv run pytest` -- green, output pristine.

---

### Task 1: Pool the per-pull rule across a boss's pulls

**Files:**
- Modify: `src/wowperf/domain/analysis/defensives.py` (ABOUTME lines; `analyse_defensives_at_death` at :103-188; new helper and function after it)
- Test: `tests/domain/analysis/test_defensives_at_death.py` (beside `defensives_up_at`'s own tests)

**Interfaces:**
- Produces: `repeat_defensives_up(series: LoadedProgression, defensives: Defensives) -> list[Finding]` in `wowperf.domain.analysis.defensives`; `REPEAT_READY_PREFIX = "progression.repeat.ready."`.
- Produces (module-private): `_base_ids(players: Iterable[Player]) -> dict[int, str]`, used by both `analyse_defensives_at_death` and `repeat_defensives_up`.

- [ ] **Step 1: Lift the slug disambiguation into one helper (refactor, existing tests guard it)**

In `defensives.py`, add after `defensives_up_at`:

```python
def _base_ids(players: Iterable[Player]) -> dict[int, str]:
    """Each player's id stem: the slug, or `slug.actor_id` when two players share it.

    Counted on the slug rather than the name, because the slug is what the id
    carries: `Bríala` and `Briala` are two players and one slug, and only the
    actor id then tells their findings apart. One helper, so the per-pull
    finding and the one pooling it across pulls can never mint two different
    ids for the same player.
    """
    unique = {player.actor_id: player for player in players}
    slugs = {actor_id: player_slug(player.name) for actor_id, player in unique.items()}
    counts = Counter(slugs.values())
    return {
        actor_id: slug if counts[slug] == 1 else f"{slug}.{actor_id}"
        for actor_id, slug in slugs.items()
    }
```

Import `Counter` from `collections` and `Iterable` from `collections.abc`. In `analyse_defensives_at_death`, replace the `slug_counts` block (the comment above it moves into the helper's docstring, which carries it verbatim) with `base_ids = _base_ids(players)`, and replace the two lines computing `slug` and `base_id` with `base_id = base_ids[player.actor_id]`. Remove `defaultdict` from the import only if nothing else in the module uses it (`analyse_defensive_ceiling`'s `_ceiling_ids` still does).

Run `tests/domain/analysis/test_defensives_at_death.py` and `tests/domain/analysis/test_defensives.py`: every existing test must pass unchanged. Prove the id tests guard the helper: change `counts[slug] == 1` to `True` and watch the same-slug id test in `test_defensives_at_death.py` go red; restore. If no test there goes red, add one (two players `Bríala`/`Briala`, both dying with a defensive up, two distinct ids ending `.<actor_id>`) and prove it red.

- [ ] **Step 2: Write the failing unit tests**

Add to `tests/domain/analysis/test_defensives_at_death.py`. Import `repeat_defensives_up` beside the others, `an_attempt` from `tests.domain.test_progression`, `a_loaded_series` from `tests.domain.progression_fixtures`, and `LoadedEncounter` from `wowperf.domain.encounter`.

```python
# --- progression.repeat.ready: the rule above, pooled across a boss's pulls ---
#
# Each pull is judged on its own casts, and the pulls are added up. Every pull
# below runs 600 seconds from `an_attempt`'s `fight_id * 1_000_000`, so pull
# windows never overlap.

IBF = DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0)
AMS = DefensiveAbility(ability_id=48707, name="Anti-Magic Shell", cooldown_seconds=60.0)
BLOOD = Defensives(entries=(("DeathKnight/Blood", (IBF, AMS)),))
"""Icebound Fortitude listed first: an insertion-ordered sort puts it first,
and a name-ordered one puts Anti-Magic Shell first."""

EMBERKIN = Player(actor_id=1, name="Emberkin", class_name="DeathKnight", spec="Blood",
                  item_level=600)
STONEWAKE = Player(actor_id=2, name="Stonewake", class_name="Mage", spec="Arcane",
                   item_level=600)


def a_pull(
    fight_id: int,
    *,
    deaths: tuple[tuple[Player, float], ...] = (),
    casts: tuple[tuple[Player, DefensiveAbility, float], ...] = (),
    players: tuple[Player, ...] = (EMBERKIN,),
) -> LoadedEncounter:
    """One pull, its deaths and casts given as seconds after the pull's start."""
    encounter = an_attempt(fight_id, 50.0, 600.0, players=players)
    start = encounter.start_ms
    return LoadedEncounter(
        encounter=encounter,
        deaths=tuple(
            Death(player_name=who.name, actor_id=who.actor_id,
                  timestamp_ms=start + int(at * 1000), killing_blow="Void Bolt")
            for who, at in deaths
        ),
        casts=tuple(
            CastEvent(actor_id=who.actor_id, ability_id=ability.ability_id,
                      ability_name=ability.name, timestamp_ms=start + int(at * 1000))
            for who, ability, at in casts
        ),
    )


def owned_and_died(fight_id: int, *abilities: DefensiveAbility) -> LoadedEncounter:
    """Emberkin casts each ability at 1s -- proof of owning it -- and dies at 400s.

    400s is past every window here (Icebound Fortitude's is 180 + 10), so each
    ability cast is up at the death.
    """
    return a_pull(
        fight_id,
        deaths=((EMBERKIN, 400.0),),
        casts=tuple((EMBERKIN, ability, 1.0) for ability in abilities),
    )


def test_an_ability_up_at_deaths_on_two_pulls_names_the_player() -> None:
    findings = repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF), owned_and_died(2, IBF)), BLOOD
    )
    assert [f.id for f in findings] == ["progression.repeat.ready.emberkin"]
    (finding,) = findings
    assert finding.title == "Emberkin: Icebound Fortitude up at 2 of 2 deaths"
    assert finding.ability_id == IBF.ability_id
    assert finding.ability_name == "Icebound Fortitude"
    assert finding.evidence == (
        "DeathKnight Blood", "Icebound Fortitude up at 2 of 2 deaths",
    )
    assert finding.confidence is Confidence.INFERRED
    assert finding.player_slug == ""


def test_two_deaths_inside_one_pull_are_that_pulls_claim_not_this_one() -> None:
    """A battle resurrection, then a second death: both up, both on pull 1."""
    twice = a_pull(
        1,
        deaths=((EMBERKIN, 300.0), (EMBERKIN, 500.0)),
        casts=((EMBERKIN, IBF, 1.0),),
    )
    quiet = a_pull(2, casts=((EMBERKIN, IBF, 1.0),))
    assert repeat_defensives_up(a_loaded_series(twice, quiet), BLOOD) == []


def test_a_death_on_a_pull_without_the_ability_cast_is_left_out_of_its_denominator() -> None:
    """Pull 3 holds a death and no Icebound Fortitude cast: unknown, not "not up"."""
    unowned = a_pull(3, deaths=((EMBERKIN, 400.0),))
    findings = repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF), owned_and_died(2, IBF), unowned), BLOOD
    )
    assert findings[0].title == "Emberkin: Icebound Fortitude up at 2 of 2 deaths"


def test_a_pressed_ability_stays_in_the_denominator_and_out_of_the_count() -> None:
    """Pull 3: owned, pressed at 380s inside its window, so judged and not up."""
    pressed = a_pull(
        3,
        deaths=((EMBERKIN, 400.0),),
        casts=((EMBERKIN, IBF, 1.0), (EMBERKIN, IBF, 380.0)),
    )
    findings = repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF), owned_and_died(2, IBF), pressed), BLOOD
    )
    assert findings[0].title == "Emberkin: Icebound Fortitude up at 2 of 3 deaths"


def test_a_talent_cast_on_one_pull_is_not_owned_on_the_next() -> None:
    """The pull-by-pull ruling: pull 2 never casts it, so pull 2's death says nothing.

    Judged across the night instead, pull 1's cast would make it "up" on pull
    2 as well, and the player would be named at 2 of 2.
    """
    swapped_out = a_pull(2, deaths=((EMBERKIN, 400.0),))
    assert repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF), swapped_out), BLOOD
    ) == []


def test_several_abilities_are_named_in_one_finding_tied_counts_by_name() -> None:
    findings = repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF, AMS), owned_and_died(2, IBF, AMS)), BLOOD
    )
    (finding,) = findings
    assert finding.title == "Emberkin: 2 defensives up at more than one death"
    assert finding.ability_id is None
    assert finding.evidence == (
        "DeathKnight Blood",
        "Anti-Magic Shell up at 2 of 2 deaths",
        "Icebound Fortitude up at 2 of 2 deaths",
    )


def test_abilities_are_ordered_by_count_before_name() -> None:
    """Icebound Fortitude up 3 times, Anti-Magic Shell 2: count wins over the alphabet.

    Listed Anti-Magic Shell first, so neither insertion order nor name order
    can produce the expected order by accident.
    """
    ams_first = Defensives(entries=(("DeathKnight/Blood", (AMS, IBF)),))
    pressed_ams = a_pull(
        3,
        deaths=((EMBERKIN, 400.0),),
        casts=((EMBERKIN, IBF, 1.0), (EMBERKIN, AMS, 1.0), (EMBERKIN, AMS, 380.0)),
    )
    (finding,) = repeat_defensives_up(
        a_loaded_series(
            owned_and_died(1, IBF, AMS), owned_and_died(2, IBF, AMS), pressed_ams
        ),
        ams_first,
    )
    assert finding.evidence[1:] == (
        "Icebound Fortitude up at 3 of 3 deaths",
        "Anti-Magic Shell up at 2 of 3 deaths",
    )


def test_a_player_absent_from_a_pull_is_judged_on_the_pulls_they_played() -> None:
    """Emberkin sits out pull 1: a roster read from the first pull alone would miss him."""
    benched = a_pull(1, players=(STONEWAKE,), deaths=((STONEWAKE, 400.0),))
    findings = repeat_defensives_up(
        a_loaded_series(benched, owned_and_died(2, IBF), owned_and_died(3, IBF)), BLOOD
    )
    assert [f.title for f in findings] == ["Emberkin: Icebound Fortitude up at 2 of 2 deaths"]


def test_two_players_sharing_a_slug_get_two_ids() -> None:
    accented = Player(actor_id=1, name="Bríala", class_name="DeathKnight", spec="Blood",
                      item_level=600)
    plain = Player(actor_id=3, name="Briala", class_name="DeathKnight", spec="Blood",
                   item_level=600)

    def both_die(fight_id: int) -> LoadedEncounter:
        return a_pull(
            fight_id,
            players=(accented, plain),
            deaths=((accented, 400.0), (plain, 410.0)),
            casts=((accented, IBF, 1.0), (plain, IBF, 1.0)),
        )

    findings = repeat_defensives_up(a_loaded_series(both_die(1), both_die(2)), BLOOD)
    assert sorted(f.id for f in findings) == [
        "progression.repeat.ready.briala.1",
        "progression.repeat.ready.briala.3",
    ]


def test_a_spec_absent_from_the_data_file_names_nobody() -> None:
    def mage_dies(fight_id: int) -> LoadedEncounter:
        return a_pull(
            fight_id, players=(STONEWAKE,), deaths=((STONEWAKE, 400.0),),
            casts=((STONEWAKE, IBF, 1.0),),
        )

    assert repeat_defensives_up(a_loaded_series(mage_dies(1), mage_dies(2)), BLOOD) == []


def test_the_detail_says_it_is_a_question_and_how_it_was_judged() -> None:
    (finding,) = repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF), owned_and_died(2, IBF)), BLOOD
    )
    assert "pull by pull" in finding.detail
    assert "a question to ask, not a mistake to fix" in finding.detail
```

Check before running: `a_loaded_series` wraps `LoadedEncounter`s into a `LoadedProgression` whose `attempts_with_events` sorts by start time (read `tests/domain/progression_fixtures.py`); `an_attempt(fight_id, remaining, seconds, players=...)` is in `tests/domain/test_progression.py`.

- [ ] **Step 3: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/analysis/test_defensives_at_death.py -v`
Expected: FAIL at import -- `cannot import name 'repeat_defensives_up'`.

- [ ] **Step 4: Write the analyser**

Change the ABOUTME lines of `defensives.py` to:

```python
# ABOUTME: Defensive claims a combat log can support: cast far below the cooldown ceiling,
# ABOUTME: or off cooldown at a death, one pull at a time or pooled across a boss. All inferred.
```

Import `LoadedProgression` from `wowperf.domain.progression`. Add after `analyse_defensives_at_death`:

```python
REPEAT_READY_PREFIX = "progression.repeat.ready."
"""Pooled across a boss's pulls, so it sits on the summary's Repeats tab.

The `progression.repeat.` placement puts it there with no table change; the
player's id stem follows, exactly as it does on the per-pull finding.
"""


def repeat_defensives_up(series: LoadedProgression, defensives: Defensives) -> list[Finding]:
    """Players whose own defensives were up at their deaths on more than one pull.

    `analyse_defensives_at_death`'s rule, pooled: each pull is judged by
    `defensives_up_at` on that pull's own casts, and the judgements are added
    up, so the pooled count is exactly the sum of the pull rows beneath it and
    stays right when a raider swaps a talent between pulls. Ownership is never
    judged across the night -- a talent dropped after one pull would otherwise
    read as available and unpressed on the next.

    Per player and ability, the count is the deaths at which it was up, and the
    denominator is the deaths on pulls where the player cast it at least once:
    on any other pull the rule cannot say whether they owned it, so those
    deaths are unknown rather than "not up". A player is named when some
    ability was up at two or more deaths on two or more pulls -- two deaths
    inside one pull are a claim that pull's own row already makes.

    Every death counts, late wipe deaths included: measured on a real night,
    the share of defensives still ready at death does not rise in the pile-up
    (`docs/plans/2026-09-26-night-defensives-pooled-design.md` section 2).

    `inferred`, like every claim in this module. Players are matched across
    pulls by actor id, stable within one report, and each pull reads the spec
    that pull's roster gives. A spec absent from the data file names nobody.
    """
    roster: dict[int, Player] = {}
    for one in series.attempts_with_events:
        for player in one.players:
            roster.setdefault(player.actor_id, player)
    base_ids = _base_ids(roster.values())

    names: dict[tuple[int, int], str] = {}
    up: Counter[tuple[int, int]] = Counter()
    judged: Counter[tuple[int, int]] = Counter()
    pulls_up: dict[tuple[int, int], set[int]] = defaultdict(set)
    for one in series.attempts_with_events:
        for player in one.players:
            abilities = defensives.for_spec(player.class_name, player.spec)
            cast_ids = {
                cast.ability_id for cast in one.casts if cast.actor_id == player.actor_id
            }
            for death in one.deaths:
                if death.actor_id != player.actor_id:
                    continue
                up_now = defensives_up_at(
                    one.casts, abilities, player.actor_id, death.timestamp_ms
                )
                for ability in abilities:
                    if ability.ability_id not in cast_ids:
                        continue
                    key = (player.actor_id, ability.ability_id)
                    names.setdefault(key, ability.name)
                    judged[key] += 1
                    if ability.name in up_now:
                        up[key] += 1
                        pulls_up[key].add(one.encounter.fight_id)

    findings = []
    for actor_id, player in roster.items():
        # Two pulls is the whole rule: each pull in `pulls_up` holds at least
        # one death at which the ability was up, so two pulls imply two deaths.
        named = sorted(
            (key for key in up if key[0] == actor_id and len(pulls_up[key]) >= 2),
            key=lambda key: (-up[key], names[key]),
        )
        if not named:
            continue
        lines = tuple(
            f"{names[key]} up at {up[key]} of {judged[key]} deaths" for key in named
        )
        single = named[0] if len(named) == 1 else None
        findings.append(
            Finding(
                id=f"{REPEAT_READY_PREFIX}{base_ids[actor_id]}",
                title=(
                    f"{player.name}: {lines[0]}"
                    if single is not None
                    else f"{player.name}: {len(named)} defensives up at more than one death"
                ),
                detail=(
                    "Judged pull by pull from this player's own casts against each "
                    "ability's base cooldown, counting only abilities they cast somewhere "
                    "in that pull, then added up across the boss's pulls. Every death "
                    "counts, late wipe deaths included: the share of defensives still up "
                    "at death was measured not to rise once a wipe comes apart. A "
                    "defensive is pressed into damage rather than on cooldown, so this is "
                    "a question to ask, not a mistake to fix."
                ),
                confidence=Confidence.INFERRED,
                evidence=(f"{player.class_name} {player.spec}", *lines),
                ability_id=single[1] if single is not None else None,
                ability_name=names[single] if single is not None else "",
            )
        )
    return findings
```

- [ ] **Step 5: Run, pass, prove**

Run the file: all pass. Then prove each guard, one at a time, restoring after each:
- change `len(pulls_up[key]) >= 2` to `up[key] >= 2` -> `..._two_deaths_inside_one_pull_...` red;
- build `roster` from the first pull's players only -> `..._absent_from_a_pull_...` red;
- drop the `ability.ability_id not in cast_ids` check -> `..._without_the_ability_cast_...` red;
- build `cast_ids` from every pull's casts instead of `one.casts` -> `..._talent_cast_on_one_pull_...` red;
- count `judged` only when up -> `..._pressed_ability_stays_in_the_denominator_...` red;
- sort by `names[key]` only -> `..._ordered_by_count_before_name` red; sort by `-up[key]` only -> `..._tied_counts_by_name` red;
If any mutation stays green, report it and add the smallest test that closes the gap.

- [ ] **Step 6: Gate and commit**

Full gate. Subject: `Pool defensives up at a player's deaths across a boss's pulls`

---

### Task 2: Wire it into the night's boss summaries

**Files:**
- Create: `src/wowperf/domain/analysis/night_service.py`
- Modify: `src/wowperf/cli.py` (the night command's `boss_findings` at :1911-1914; imports)
- Modify: `src/wowperf/domain/report/night_build.py` (`CARD_TIER_NONE` at :47-50)
- Test: `tests/domain/analysis/test_night_service.py` (create), `tests/test_cli_night.py`, `tests/domain/report/test_progression_ledger.py` (the placement list at :15-24), `tests/adapters/render/test_night_html_invariants.py`

**Interfaces:**
- Consumes: `repeat_defensives_up`, `REPEAT_READY_PREFIX` (Task 1).
- Produces: `analyse_night_boss(series: LoadedProgression, defensives: Defensives, *, death_cards: bool) -> list[Finding]` in `wowperf.domain.analysis.night_service`.

- [ ] **Step 1: Write the failing service tests**

Create `tests/domain/analysis/test_night_service.py`:

```python
# ABOUTME: The findings one boss earns on the night summary: progression's, plus the night's own.
# ABOUTME: Pins that the pooled defensives finding runs with death cards and never without.

from tests.domain.analysis.test_defensives_at_death import BLOOD, IBF, owned_and_died
from tests.domain.progression_fixtures import a_loaded_series
from wowperf.domain.analysis.defensives import REPEAT_READY_PREFIX
from wowperf.domain.analysis.night_service import analyse_night_boss
from wowperf.domain.analysis.progression_service import analyse_progression
from wowperf.domain.analysis.severity import SEVERITY_BY_FAMILY
from wowperf.domain.progression import LoadedProgression


def a_firing_boss() -> LoadedProgression:
    """Emberkin dies on two pulls with Icebound Fortitude up: the pooled finding fires."""
    return a_loaded_series(owned_and_died(1, IBF), owned_and_died(2, IBF))


def test_with_death_cards_the_pooled_finding_follows_the_progression_findings() -> None:
    series = a_firing_boss()
    found = analyse_night_boss(series, BLOOD, death_cards=True)
    progression = analyse_progression(series)

    assert found[: len(progression)] == progression
    pooled = found[len(progression):]
    assert [f.id for f in pooled] == [f"{REPEAT_READY_PREFIX}emberkin"]
    for finding in found:
        assert finding.id.split(".")[0] in SEVERITY_BY_FAMILY


def test_without_death_cards_it_is_never_asked() -> None:
    """At --no-deaths there is no casts stream; asking would imply a check that never ran."""
    series = a_firing_boss()
    assert analyse_night_boss(series, BLOOD, death_cards=False) == analyse_progression(series)
```

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/analysis/test_night_service.py -v`
Expected: FAIL at import -- `No module named 'wowperf.domain.analysis.night_service'`.

- [ ] **Step 2: Write the service**

Create `src/wowperf/domain/analysis/night_service.py`:

```python
# ABOUTME: The findings one boss earns on the night page's summary, read from its pulls together.
# ABOUTME: Progression's own findings, plus what only a night holding every pull's casts can add.

from wowperf.domain.analysis.defensives import repeat_defensives_up
from wowperf.domain.analysis.progression_service import analyse_progression
from wowperf.domain.findings import Finding
from wowperf.domain.progression import LoadedProgression
from wowperf.domain.season import Defensives


def analyse_night_boss(
    series: LoadedProgression, defensives: Defensives, *, death_cards: bool
) -> list[Finding]:
    """Every finding one boss's summary carries, in the order they are appended.

    `analyse_progression` first and unchanged: the standalone progression page
    and a night summary draw the same progression findings. The pooled
    defensives finding follows only with `death_cards` on -- the tier that
    fetches every pull's casts. Without it there is nothing to judge, and
    asking anyway would put a silence on the page that reads like a check that
    ran and found nothing.
    """
    findings = analyse_progression(series)
    if death_cards:
        findings += repeat_defensives_up(series, defensives)
    return findings
```

Run the test file: PASS. Prove: drop the `if death_cards:` guard (always call) -> `test_without_death_cards_it_is_never_asked` red; restore.

- [ ] **Step 3: Call it from the night command, test first**

In `tests/test_cli_night.py`, add a test recording what the command asks for. Read the file's existing `run_night` helper and the test at :530-575 that records `load_night_attempts`' arguments with `monkeypatch`, and follow its pattern:

```python
@pytest.mark.parametrize(
    ("flags", "expected"),
    [((), True), (("--no-deaths",), False)],
)
def test_each_boss_summary_asks_for_the_pooled_finding_only_with_death_cards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: tuple[str, ...], expected: bool
) -> None:
    """One call per boss, each carrying the tier the command was run at."""
    import wowperf.cli as cli
    from wowperf.domain.analysis.night_service import analyse_night_boss

    seen: list[bool] = []

    def recording(series: Any, defensives: Any, *, death_cards: bool) -> Any:
        seen.append(death_cards)
        return analyse_night_boss(series, defensives, death_cards=death_cards)

    monkeypatch.setattr(cli, "analyse_night_boss", recording)
    result = run_night(tmp_path, *flags)

    assert result.exit_code == 0, result.output
    assert seen == [expected, expected]
```

Adjust `run_night`'s call to its real signature (it may take `calls=`); two bosses in `A_NIGHT` means two calls. Run: FAIL (`cli` has no attribute `analyse_night_boss`).

Then in `cli.py`: import `analyse_night_boss` from `wowperf.domain.analysis.night_service` (module-level `from ... import`, so the monkeypatch above reaches it), and replace the `boss_findings` comprehension's body:

```python
        boss_findings = {
            boss.progression.encounter_id: rank_raid_findings(
                analyse_night_boss(boss, defensives, death_cards=death_cards)
            )
            for boss in loaded.loaded
        }
```

Keep the two-lists comment above it, and extend it with one sentence: `A boss's list also pools each player's defensives across that boss's pulls, which only the death-card tier has the casts for.` Remove the `analyse_progression` import from `cli.py` only if nothing else there still uses it (the `progression` command at :1728 does). Run: PASS. Prove: pass `death_cards=True` unconditionally and watch the `--no-deaths` case go red; restore.

- [ ] **Step 4: Say it at `--no-deaths`**

`CARD_TIER_NONE` (`night_build.py:47-50`) is the night's own method line when death cards are off, and it speaks only of the Deaths tab. Append one sentence to it:

```python
CARD_TIER_NONE = (
    "No death card was drawn on any pull: this night was read with death cards off, so the "
    "Deaths tab is empty because none was asked for rather than for want of a reading. No "
    "boss summary says which defensives were up at a player's deaths either, for the same "
    "reason."
)
```

Run the night builder and render tests. Any test pinning the old wording must be updated to the constant, not to a copied string. If a golden moves, only a no-cards page may; if `golden/night.html` (death cards on) moves, stop and report.

- [ ] **Step 5: Placement and the page**

- `tests/domain/report/test_progression_ledger.py`: add `("progression.repeat.ready.emberkin", "repeat_rows"),` to the placement list after `progression.repeat.ability`.
- `tests/adapters/render/test_night_html_invariants.py`: add a test that a pooled finding handed to a summary boss is drawn on that boss's summary Repeats tab. Read `summary_blocks`, `a_loaded_night`, `a_nights_findings` and `a_night_report` first, and use their real names and id shapes:

```python
def test_a_pooled_defensives_finding_is_drawn_on_its_summary_repeats_tab() -> None:
    night = a_loaded_night()
    index, boss = next(
        (i, b) for i, b in enumerate(night.loaded) if len(b.attempts_with_events) >= 2
    )
    pooled = Finding(
        id="progression.repeat.ready.emberkin",
        title="Emberkin: Icebound Fortitude up at 2 of 3 deaths",
        detail="Judged pull by pull.",
        confidence=Confidence.INFERRED,
        evidence=("DeathKnight Blood", "Icebound Fortitude up at 2 of 3 deaths"),
        ability_id=48792,
        ability_name="Icebound Fortitude",
    )
    html = render_night(build_night_report(
        night, a_nights_findings(night), FETCHED, A_DEFENSIVE, NO_CONSUMABLES, NO_ROLES,
        deep_fights=frozenset(), death_cards=True,
        findings_by_boss={
            one.progression.encounter_id: tuple(analyse_progression(one))
            + ((pooled,) if one is boss else ())
            for one in night.loaded
        },
    ))
    block = summary_blocks(html)[...]  # this boss's summary block, keyed as the helper keys it
    repeats = block.split('tab-repeats"', 1)[1].split("</section>", 1)[0]
    assert "finding-progression.repeat.ready.emberkin" in repeats
```

Replace `summary_blocks(html)[...]` with the helper's real key for boss `index`. Prove it red by giving `pooled` the id `progression.cluster.ready` (placed on Attempts); restore.

- [ ] **Step 6: Gate and commit**

Full gate. The night golden (`golden/night.html`) must pass unregenerated: its builder hands `findings_by_boss` from `analyse_progression` alone and never calls the CLI. Subject: `Pool defensives on each night boss summary, with death cards only`

---

### Task 3: Exercise it on the real report

**Files:**
- Modify: `tests/e2e/test_night_e2e.py` (a new test)
- Modify: `docs/plans/2026-09-26-night-defensives-pooled-design.md` (§7, and the status line)

**This task is not optional.** A new judgement is not done until a live run has exercised it, and a state that never occurs is a defect.

**A departure from the design, recorded in Step 4.** Spec §7 puts the e2e shape check in the night suite's existing test. That test runs the cheap `--no-deaths` tier, where the finding is never computed, so a check there could only ever pass vacuously. The e2e instead loads **one** summary boss at the default tier.

- [ ] **Step 1: Measure first, over the warm cache**

Read `.claude/skills/wcl-api/SKILL.md`'s rate-limit sections. Run `/c/Users/damien/.local/bin/uv.exe run wowperf night cW38jmwdnZfbHVL4` (default tier, warm cache, about 1 point) and read `out/cW38jmwdnZfbHVL4.night.json`, never the HTML. With a scratch script that prints **no name, no slug and no raw id** (count ids by prefix only), report for each of the three summary bosses (night indices 1, 6, 7; 2, 2 and 7 pulls): how many `progression.repeat.ready.` findings, how many carry `ability_id` (one-ability titles) and how many do not (several-ability), and the spread of `n` and `m` parsed from the evidence. Also report the number of `defensives.unused.` findings across the same bosses' pulls, as a cross-check that the pooled finding is not firing where no pull row exists.

If no summary boss fires, stop and report: either the data or a defect, and the pull-level counts say which.

- [ ] **Step 2: Write the e2e test**

Pick the summary boss **with the fewest pulls** that Step 1 shows firing (cheapest to load). Add to `tests/e2e/test_night_e2e.py`, using the file's existing `REPORT_CODE`, `build_repository`, `load_defensives` and `re`, and importing `repeat_defensives_up` from `wowperf.domain.analysis.defensives` and `Confidence` from `wowperf.domain.findings` if the file lacks them:

```python
FIRING_BOSS = ...  # the night index Step 1 measured firing, with the date in a comment


def test_defensives_up_are_pooled_across_one_bosss_pulls(tmp_path: Path) -> None:
    """One summary boss at the default tier: the only tier with the casts this reads.

    The whole-night test above runs `--no-deaths`, where this finding is never
    computed, so it is exercised here on one boss rather than paying the
    default tier for all sixteen pulls.
    """
    repository = build_repository(tmp_path / "cache")
    before = repository.rate_limit().points_spent_this_hour
    night = repository.load_night(REPORT_CODE, None)
    one_boss = night.model_copy(update={"bosses": (night.bosses[FIRING_BOSS],)})
    loaded = repository.load_night_attempts(
        one_boss, deep_fights=frozenset(), death_cards=True
    )
    spent = repository.rate_limit().points_spent_this_hour - before
    print(f"one boss, default tier, cold cache: {spent:.2f} points")

    (series,) = loaded.loaded
    findings = repeat_defensives_up(series, load_defensives())
    assert findings, "no player was named on the boss this report fires it on"

    most_deaths = max(
        sum(1 for one in series.attempts_with_events for d in one.deaths
            if d.actor_id == actor_id)
        for actor_id in {p.actor_id for one in series.attempts_with_events
                         for p in one.players}
    )
    line = re.compile(r"^.+ up at (\d+) of (\d+) deaths$")
    for finding in findings:
        assert finding.id.startswith("progression.repeat.ready.")
        assert finding.confidence is Confidence.INFERRED
        assert finding.player_slug == ""
        pairs = [line.match(text) for text in finding.evidence[1:]]
        assert pairs and all(pairs), "an evidence line lost its shape"
        for match in pairs:
            assert match is not None
            n, m = int(match.group(1)), int(match.group(2))
            assert 2 <= n <= m <= most_deaths
```

Check that `load_night_attempts` accepts a `Night` carrying one boss (read its signature and `Night`'s fields); if `model_copy` is not how `Night` is narrowed elsewhere, use what the code does. Add a `spent` bound once measured (Step 3), in the file's style: the measured figure and date in a comment, a bound comfortably above it. No assertion message may carry a player or ability name.

- [ ] **Step 3: Run the e2e once, live**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest -m e2e tests/e2e/test_night_e2e.py::test_defensives_up_are_pooled_across_one_bosss_pulls -v -s`
Expected: PASS, spending roughly 19 points per pull of that boss (the default tier's measured rate). Run once; on failure, diagnose from the output before any second run. Then set the `spent` bound from the printed figure.

- [ ] **Step 4: Amend the design**

§7 "End to end": replace the sentence placing the check in `test_night_e2e.py`'s existing test with: the whole-night test runs `--no-deaths`, where the finding is never computed, so a separate e2e loads the one summary boss Step 1 measured firing at the default tier and asserts shape there; name the boss by night index and the points it cost. Also correct §7's unit-test file to `tests/domain/analysis/test_defensives_at_death.py`, where `defensives_up_at`'s own tests live. Under "Live", record Step 1's per-boss counts (numbers only). Status line: `approved design, planned in docs/plans/2026-09-26-night-defensives-pooled-plan.md.`

- [ ] **Step 5: Gate and commit**

Offline gate. Subject: `Exercise pooled defensives on a real report`. Body: the points spent and the distribution headline, no names.

---

## What this plan deliberately does not build

- Teammates' externals and consumables at a death (spec §8).
- Deaths-per-player tallies (spec §2).
- Any change to the standalone progression command, `analyse_progression`, `METHOD_NO_ANATOMY`, or any template.
- Linking the finding to a player card (`player_slug` stays empty, spec §4).
