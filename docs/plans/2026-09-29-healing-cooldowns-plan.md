# Healing cooldowns against the heaviest moments -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rank each raid fight's and each Mythic+ run's heaviest moments of damage taken and say, for the group, whether a healing or group-wide defensive cooldown answered each -- on the raid page's Mechanics tab (and so every `night` pull) and the Mythic+ page's Deaths tab.

**Architecture:** One pure domain analyser, `src/wowperf/domain/analysis/spikes.py`, over data every command already fetches: whole-fight damage-taken events and every actor's casts. The answer set is read from the two existing cooldown files, each ability that answers the whole group marked `group = true` by hand. The two analysis services call it when handed an answer set; the CLI builds that set from the roster; placement is one prefix line per page.

**Tech Stack:** Python 3.12, pydantic frozen models, TOML data files, Jinja2, pytest, typer `CliRunner`, httpx `MockTransport`. `uv` only: in Bash, `/c/Users/damien/.local/bin/uv.exe`.

**Spec:** `docs/plans/2026-09-29-healing-cooldowns-design.md` -- read it whole before Task 1, including its 2026-09-29 amendments (§3 counting, §5 answer set, early-fight "not judged", §7 placement).

## Global Constraints

- No new Warcraft Logs query and no new API field (§3). Every field used is already in `DamageTakenEvent`, `CastEvent`, `Death`, `Resurrection`, `Player`.
- A hit counts `health_damage + absorbed - overkill`, roster players only (§4).
- `SPIKE_WINDOW_SECONDS = 5`, `SECONDS_PER_SPIKE = 180`, `SPIKE_FLOOR = 2.0`, `ANSWER_LEAD_SECONDS = 10` -- named constants, stated on the page (§4, §5).
- The judgement is the group's, never one healer's (§5).
- The page never says a cooldown was "on cooldown", never prints a raw damage figure, and never calls a cooldown ready that `ready_at()` would not (§5).
- Finding ids and badges: `healing.spikes` derived, `healing.spikes.unanswered` inferred, `healing.spikes.unavailable` measured; none carries time lost (§6).
- Only entries marked `group = true` answer a moment; an ability stays in one data file only (§5).
- `src/wowperf/domain/` performs no I/O. The report's one inline script is untouched.
- No real character name in `tests/`: only `Emberkin`, `Stonewake`, `Bríala`, `Кириллица` (plus `Briala`). Players on `cW38jmwdnZfbHVL4` and `6Kx1P9GbNXrcLdHa` are referred to by class, spec, role or index only -- never by name, slug or raw finding id -- in replies, commits, documents and test messages.
- Every new test is shown able to fail: break the line it guards, watch it go red, restore. Read `.claude/skills/testing/test-driven-development/SKILL.md` before the first test.
- Every new code file starts with two `ABOUTME: ` lines. Comments evergreen.
- Commits: imperative subject, no prefix, body says why, plain ASCII, last line a `Co-Authored-By:` naming the model that wrote the commit. Commit with `/mingw64/bin/git`. Never `--no-verify`.
- Gate after every task: `uv run ruff check .`, `uv run mypy` (strict over `tests/` too), `uv run pytest` -- green, output pristine.
- Goldens: the raid golden moves deliberately in Task 3 and in no other task; every other golden stays byte-identical. If one moves anywhere else, stop and report.

---

### Task 1: Mark the answers that cover the whole group

**Files:**
- Modify: `src/wowperf/domain/season.py` (`CooldownAbility`)
- Modify: `src/wowperf/adapters/config/toml.py` (`_load_cooldowns`)
- Modify: `data/throughput_cooldowns.toml`, `data/externals.toml`
- Test: `tests/adapters/config/test_toml.py`

**Interfaces:**
- Produces: `CooldownAbility.group: bool = False` (inherited by `DefensiveAbility` and `ExternalAbility`), read from an optional `group = true` on each TOML entry.

- [ ] **Step 1: Write the failing tests**

Append to `tests/adapters/config/test_toml.py` (it already imports `Path` and `pytest`):

```python
def test_a_group_marker_is_read_and_its_absence_reads_false(tmp_path: Path) -> None:
    from wowperf.adapters.config.toml import load_externals

    path = tmp_path / "externals.toml"
    path.write_text(
        'verified = "2026-09-29"\n\n'
        '["Warrior/Arms"]\n'
        "abilities = [\n"
        '  { ability_id = 97462, name = "Rallying Cry", cooldown_seconds = 180.0, group = true },\n'
        '  { ability_id = 3411, name = "Intervene", cooldown_seconds = 30.0 },\n'
        "]\n",
        encoding="utf-8",
    )
    [rallying, intervene] = load_externals(path).for_spec("Warrior", "Arms")
    assert (rallying.name, rallying.group) == ("Rallying Cry", True)
    assert (intervene.name, intervene.group) == ("Intervene", False)


GROUP_THROUGHPUT = {
    ("Druid/Restoration", "Incarnation: Tree of Life"),
    ("Druid/Restoration", "Convoke the Spirits"),
    ("Druid/Restoration", "Tranquility"),
    ("Evoker/Preservation", "Rewind"),
    ("Evoker/Preservation", "Emerald Communion"),
    ("Monk/Mistweaver", "Invoke Yu'lon, the Jade Serpent"),
    ("Monk/Mistweaver", "Invoke Chi-Ji, the Red Crane"),
    ("Monk/Mistweaver", "Revival"),
    ("Monk/Mistweaver", "Restoral"),
    ("Paladin/Holy", "Avenging Wrath"),
    ("Priest/Discipline", "Evangelism"),
    ("Priest/Holy", "Apotheosis"),
    ("Priest/Holy", "Divine Hymn"),
    ("Shaman/Restoration", "Healing Tide Totem"),
    ("Shaman/Restoration", "Ascendance"),
}
"""The healer cooldowns that answer the whole group's damage. Touch of Death, Power Infusion,
Holy Word: Chastise and the rest of the healer blocks answer nobody's damage, or one target's."""

GROUP_EXTERNALS = {
    ("Priest/Discipline", "Power Word: Barrier"),
    ("Shaman/Restoration", "Spirit Link Totem"),
    ("Warrior/Arms", "Rallying Cry"),
    ("Warrior/Fury", "Rallying Cry"),
    ("Warrior/Protection", "Rallying Cry"),
}


def test_the_committed_group_markers_are_exactly_the_reviewed_set() -> None:
    from wowperf.adapters.config.toml import load_externals, load_throughput_cooldowns

    def marked(
        entries: tuple[tuple[str, tuple[CooldownAbility, ...]], ...],
    ) -> set[tuple[str, str]]:
        return {(spec, one.name) for spec, abilities in entries for one in abilities if one.group}

    assert marked(load_throughput_cooldowns().entries) == GROUP_THROUGHPUT
    assert marked(load_externals().entries) == GROUP_EXTERNALS


def test_every_marked_throughput_cooldown_sits_under_a_healer_spec() -> None:
    from wowperf.adapters.config.toml import load_roles, load_throughput_cooldowns

    healers = set(load_roles().healers)
    for spec, abilities in load_throughput_cooldowns().entries:
        if any(one.group for one in abilities):
            assert spec in healers, f"{spec} is not a healer spec"
```

Add `from wowperf.domain.season import CooldownAbility` to the file's imports. `load_roles` is `wowperf.adapters.config.toml.load_roles` (checked 2026-09-29).

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/adapters/config/test_toml.py -q -k "group_marker or group_markers or marked_throughput"`
Expected: FAIL -- `AttributeError` or a `False`/empty set where `True`/the set is expected (the field does not exist yet).

- [ ] **Step 3: The field and the loader**

In `src/wowperf/domain/season.py`, `CooldownAbility`, after `charges: int = 1`:

```python
    # Whether pressing it answers a heavy moment for the whole group, as a
    # raid-wide heal or damage reduction does. Marked by hand per ability in
    # the data files, because the lists hold abilities that answer no one but
    # their target (Power Infusion, Ironbark) beside ones that answer everyone.
    group: bool = False
```

The model's base (`Frozen`) ignores unknown keywords silently, so the field must exist for a `group=` to mean anything -- do not skip this line.

In `src/wowperf/adapters/config/toml.py`, `_load_cooldowns`, inside the `ability(...)` call after `charges=...`:

```python
                        group=bool(item.get("group", False)),
```

and extend its docstring's "four fields" sentence to name the optional `group` marker.

- [ ] **Step 4: The markers**

In `data/throughput_cooldowns.toml`, add `, group = true` inside the braces of exactly the fifteen entries in `GROUP_THROUGHPUT` (match by spec block and name; `Avenging Wrath` only under `["Paladin/Holy"]`, `Ascendance` only under `["Shaman/Restoration"]`). In `data/externals.toml`, the same on the five entries in `GROUP_EXTERNALS`. In each file's header comment, add one line: `# group = true marks an ability that answers the whole group's damage (healing-cooldowns design, 2026-09-29).` Leave `verified` as it is: no id or cooldown changed.

**Not in this task:** adding Anti-Magic Zone, Darkness, Aura Mastery or any other ability. Adding one to `externals.toml` also lists it on every death card as a teammate's external, and each needs its spell id confirmed from a real log and its cooldown from a primary source (design §5). It is a follow-up.

- [ ] **Step 5: Run, pass, prove**

Run the three tests: green. Prove, restoring after each:
- drop `group=bool(...)` from the loader -> the marker test red;
- drop the `group = true` from one throughput entry -> the reviewed-set test red;
- add `group = true` to `Touch of Death` under `["Monk/Mistweaver"]` -> the reviewed-set test red;
- move a marked entry's marker onto a non-healer spec's entry in `throughput_cooldowns.toml` -> the healer-spec test red.

- [ ] **Step 6: Gate and commit**

Full gate. Every golden unchanged (nothing reads `group` yet). Subject: `Mark the cooldowns that answer the whole group's damage`

---

### Task 2: The heaviest moments and their answers

**Files:**
- Create: `src/wowperf/domain/analysis/spikes.py`
- Test: `tests/domain/analysis/test_spikes.py` (create)

**Interfaces:**
- Consumes: Task 1's `CooldownAbility.group`; `ready_at` (`domain/analysis/throughput.py`); `clock_text` (`domain/comparison/pace.py`); `pair_label` (`domain/comparison/pace_player.py`).
- Produces: `SPIKES_ID`, `UNANSWERED_ID`, `UNAVAILABLE_ID`, the four constants, `Answer(actor_id, holder, ability)`, `answers_for(players, throughput, externals, roles) -> tuple[Answer, ...]`, `heaviest_moments(damage_taken, player_ids, span, combat) -> tuple[Moment, ...]`, `analyse_spikes(*, damage_taken, casts, deaths, resurrections, players, answers, span, combat, setting) -> list[Finding]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/analysis/test_spikes.py`:

```python
# ABOUTME: The group's heaviest moments of damage taken, and whether a group cooldown answered each.
# ABOUTME: Pins the curve, the ranking, the floor, the answer set, each state and every wording.

import re

from wowperf.domain.analysis.spikes import (
    ANSWER_LEAD_SECONDS,
    NOT_JUDGED_TITLE,
    SPIKES_ID,
    UNANSWERED_ID,
    UNAVAILABLE_ID,
    Answer,
    analyse_spikes,
    answers_for,
    heaviest_moments,
)
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, Resurrection
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.season import (
    CooldownAbility,
    ExternalAbility,
    Externals,
    Roles,
    ThroughputCooldowns,
)

DRUID = Player(actor_id=1, name="Emberkin", class_name="Druid", spec="Restoration", item_level=690)
WARRIOR = Player(actor_id=2, name="Stonewake", class_name="Warrior", spec="Arms", item_level=690)
MAGE = Player(actor_id=3, name="Bríala", class_name="Mage", spec="Frost", item_level=690)
ROSTER = (DRUID, WARRIOR, MAGE)
PET = 99

TRANQUILITY = CooldownAbility(
    ability_id=740, name="Tranquility", cooldown_seconds=180.0, group=True
)
SWIFTNESS = CooldownAbility(ability_id=132158, name="Nature's Swiftness", cooldown_seconds=60.0)
RALLYING = ExternalAbility(
    ability_id=97462, name="Rallying Cry", cooldown_seconds=180.0, group=True
)
IRONBARK = ExternalAbility(ability_id=102342, name="Ironbark", cooldown_seconds=90.0)

THROUGHPUT = ThroughputCooldowns(
    entries=(("Druid/Restoration", (TRANQUILITY, SWIFTNESS)), ("Mage/Frost", (TRANQUILITY,)))
)
EXTERNALS = Externals(entries=(("Druid/Restoration", (IRONBARK,)), ("Warrior/Arms", (RALLYING,))))
ROLES = Roles(healers=("Druid/Restoration",))
ANSWERS = answers_for(ROSTER, THROUGHPUT, EXTERNALS, ROLES)

FIVE_MINUTES = (0, 300_000)


def hit(actor_id: int, second: float, health: int, *, absorbed: int = 0, overkill: int = 0
        ) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id, ability_id=1, ability_name="Venom Bolt", amount=health + absorbed,
        timestamp_ms=int(second * 1000), health_damage=health, absorbed=absorbed,
        overkill=overkill,
    )


def steady(seconds: int, per_second: int = 100) -> list[DamageTakenEvent]:
    """The mage taking the same damage every second: the median every burst is weighed by."""
    return [hit(MAGE.actor_id, second, per_second) for second in range(seconds)]


def burst(first: int, *, per_second: int = 1000, length: int = 5) -> list[DamageTakenEvent]:
    return [hit(MAGE.actor_id, first + one, per_second) for one in range(length)]


def cast(player: Player, ability: CooldownAbility, second: float) -> CastEvent:
    return CastEvent(
        actor_id=player.actor_id, ability_id=ability.ability_id, ability_name=ability.name,
        timestamp_ms=int(second * 1000),
    )


FILLER = cast(MAGE, SWIFTNESS, 1)
"""One unrelated cast, so a fight with no answer pressed still reads as a fight with casts."""


def spikes(
    damage: list[DamageTakenEvent],
    casts: list[CastEvent],
    *,
    span: tuple[int, int] = FIVE_MINUTES,
    combat: tuple[tuple[int, int], ...] | None = None,
    deaths: tuple[Death, ...] = (),
    resurrections: tuple[Resurrection, ...] = (),
    answers: tuple[Answer, ...] = ANSWERS,
    setting: str = "fight",
) -> list[Finding]:
    return analyse_spikes(
        damage_taken=damage, casts=casts, deaths=deaths, resurrections=resurrections,
        players=ROSTER, answers=answers, span=span,
        combat=combat if combat is not None else (span,), setting=setting,
    )


def the(findings: list[Finding], finding_id: str) -> Finding:
    [one] = [finding for finding in findings if finding.id == finding_id]
    return one


def test_the_answer_set_is_a_healers_marked_cooldowns_and_anyones_marked_externals() -> None:
    names = [(one.holder, one.ability.name) for one in ANSWERS]
    assert names == [
        ("Restoration Druid, Emberkin", "Tranquility"),
        ("Arms Warrior, Stonewake", "Rallying Cry"),
    ]


def test_a_hit_counts_what_reached_health_and_what_a_shield_took_less_overkill() -> None:
    moments = heaviest_moments(
        [*steady(300), hit(MAGE.actor_id, 100, 700, absorbed=500, overkill=200)],
        frozenset({MAGE.actor_id}), FIVE_MINUTES, (FIVE_MINUTES,),
    )
    [heaviest] = [one for one in moments if one.rank == 1]
    assert heaviest.weight == (500 + 700 + 500 - 200) / 500


def test_a_pet_or_an_npc_taking_damage_is_not_counted() -> None:
    damage = [*steady(300), *(hit(PET, 100 + one, 50_000) for one in range(5))]
    findings = spikes(damage, [FILLER])
    assert the(findings, UNAVAILABLE_ID).title == "No moment of this fight was heavy enough to rank"


def test_a_burst_straddling_a_second_boundary_is_one_whole_window() -> None:
    moments = heaviest_moments(
        [*steady(300), *burst(42)], frozenset({MAGE.actor_id}), FIVE_MINUTES, (FIVE_MINUTES,)
    )
    assert [(one.start_ms, one.end_ms) for one in moments if one.rank == 1] == [(42_000, 47_000)]


def test_one_moment_per_started_three_minutes_heaviest_first_never_overlapping() -> None:
    nine_minutes = (0, 540_000)
    damage = [*steady(540), *burst(100, per_second=3000), *burst(102, per_second=2500),
              *burst(300, per_second=2000), *burst(450, per_second=1500)]
    moments = heaviest_moments(
        damage, frozenset({MAGE.actor_id}), nine_minutes, (nine_minutes,)
    )
    assert [(one.start_ms // 1000, one.rank) for one in moments] == [(100, 1), (300, 2), (450, 3)]


def test_a_window_below_twice_the_median_never_ranks() -> None:
    findings = spikes([*steady(300), *burst(100, per_second=90)], [FILLER])
    assert [one.id for one in findings] == [UNAVAILABLE_ID]


def test_a_window_straddling_two_pulls_neither_ranks_nor_weighs() -> None:
    run = (0, 400_000)
    pulls = ((0, 100_000), (200_000, 300_000))
    damage = [*(hit(MAGE.actor_id, s, 100) for s in (*range(100), *range(200, 300))),
              *burst(98, per_second=5000, length=4)]
    moments = heaviest_moments(damage, frozenset({MAGE.actor_id}), run, pulls)
    assert all(
        any(low <= one.start_ms and one.end_ms <= high for low, high in pulls) for one in moments
    )
    assert [one.weight for one in moments if one.rank == 1] == [(100 * 5 + 5000 * 2) / 500]


def test_a_press_up_to_the_lead_before_the_window_answers_it() -> None:
    before = 200 - ANSWER_LEAD_SECONDS
    findings = spikes([*steady(300), *burst(200)], [FILLER, cast(DRUID, TRANQUILITY, before)])
    assert the(findings, SPIKES_ID).evidence == (
        "3:20 to 3:25, the heaviest (11.0 times the median): answered by Tranquility "
        "(Restoration Druid, Emberkin)",
    )


def test_a_press_one_second_earlier_than_the_lead_is_not_an_answer() -> None:
    before = 200 - ANSWER_LEAD_SECONDS - 1
    findings = spikes([*steady(300), *burst(200)], [FILLER, cast(DRUID, TRANQUILITY, before)])
    assert the(findings, SPIKES_ID).evidence == (
        "3:20 to 3:25, the heaviest (11.0 times the median): nothing pressed, and no answer was "
        "shown ready; Tranquility (Restoration Druid, Emberkin): pressed at 3:09, within its "
        "base cooldown of 3:00",
    )


def test_a_cooldown_ready_and_unpressed_is_held_against_the_group() -> None:
    casts = [FILLER, cast(DRUID, TRANQUILITY, 5), cast(WARRIOR, RALLYING, 100)]
    findings = spikes([*steady(300), *burst(200)], casts)
    assert the(findings, SPIKES_ID).title == (
        "1 heaviest moment: 1 unanswered while cooldowns were ready"
    )
    unanswered = the(findings, UNANSWERED_ID)
    assert unanswered.confidence is Confidence.INFERRED
    assert unanswered.title == (
        "1 of 1 heaviest moment went unanswered while group cooldowns were ready"
    )
    assert unanswered.evidence == (
        "3:20 to 3:25, the heaviest (11.0 times the median): nothing pressed; ready: Tranquility "
        "(Restoration Druid, Emberkin)",
    )


def test_a_cooldown_whose_window_reaches_before_the_fight_is_not_judged() -> None:
    findings = spikes([*steady(300), *burst(42)], [FILLER, cast(DRUID, TRANQUILITY, 250)])
    assert UNANSWERED_ID not in [one.id for one in findings]
    assert the(findings, SPIKES_ID).evidence == (
        "0:42 to 0:47, the heaviest (11.0 times the median): nothing pressed, and no answer was "
        "shown ready; Tranquility (Restoration Druid, Emberkin): not judged, its base cooldown "
        "reaches before the fight's first second",
    )


def test_a_cooldown_never_pressed_all_fight_is_not_seen_at_all() -> None:
    findings = spikes([*steady(300), *burst(200)], [FILLER])
    assert the(findings, SPIKES_ID).evidence == (
        "3:20 to 3:25, the heaviest (11.0 times the median): nothing pressed, and no answer was "
        "shown ready",
    )


def test_a_holder_dead_when_the_window_opens_is_not_counted_ready() -> None:
    died = Death(player_name=DRUID.name, actor_id=DRUID.actor_id, timestamp_ms=190_000,
                 killing_blow="Venom Bolt")
    casts = [FILLER, cast(DRUID, TRANQUILITY, 5)]
    findings = spikes([*steady(300), *burst(200)], casts, deaths=(died,))
    assert UNANSWERED_ID not in [one.id for one in findings]
    assert the(findings, SPIKES_ID).evidence[0].endswith(
        "Tranquility (Restoration Druid, Emberkin): its holder was dead"
    )


def test_a_holder_brought_back_before_the_window_is_alive_again() -> None:
    died = Death(player_name=DRUID.name, actor_id=DRUID.actor_id, timestamp_ms=150_000,
                 killing_blow="Venom Bolt")
    back = Resurrection(actor_id=DRUID.actor_id, caster_id=WARRIOR.actor_id, ability_id=20484,
                        ability_name="Rebirth", timestamp_ms=170_000)
    casts = [FILLER, cast(DRUID, TRANQUILITY, 5)]
    findings = spikes([*steady(300), *burst(200)], casts, deaths=(died,), resurrections=(back,))
    assert UNANSWERED_ID in [one.id for one in findings]


def test_a_cast_after_a_death_is_as_good_a_sign_of_life_as_a_resurrection() -> None:
    died = Death(player_name=DRUID.name, actor_id=DRUID.actor_id, timestamp_ms=150_000,
                 killing_blow="Venom Bolt")
    casts = [FILLER, cast(DRUID, TRANQUILITY, 5), cast(DRUID, SWIFTNESS, 180)]
    findings = spikes([*steady(300), *burst(200)], casts, deaths=(died,))
    assert UNANSWERED_ID in [one.id for one in findings]


def test_the_title_counts_every_state_that_occurred_in_a_fixed_order() -> None:
    nine_minutes = (0, 540_000)
    damage = [*steady(540), *burst(100, per_second=3000), *burst(300, per_second=2000),
              *burst(450, per_second=1500)]
    casts = [FILLER, cast(DRUID, TRANQUILITY, 98), cast(WARRIOR, RALLYING, 60)]
    findings = spikes(damage, casts, span=nine_minutes)
    assert the(findings, SPIKES_ID).title == (
        "3 heaviest moments: 1 answered, 2 unanswered while cooldowns were ready"
    )
    assert the(findings, SPIKES_ID).confidence is Confidence.DERIVED
    assert [line.split(",")[0] for line in the(findings, SPIKES_ID).evidence] == [
        "1:40 to 1:45", "5:00 to 5:05", "7:30 to 7:35",
    ]
    assert "the second heaviest" in the(findings, SPIKES_ID).evidence[1]


def test_a_run_read_without_casts_says_so() -> None:
    findings = spikes([*steady(300), *burst(200)], [], setting="run")
    assert [(one.id, one.title, one.detail) for one in findings] == [(
        UNAVAILABLE_ID, NOT_JUDGED_TITLE,
        "This run was read without its casts, so no press of any cooldown can be seen.",
    )]
    assert findings[0].confidence is Confidence.MEASURED


def test_a_group_holding_no_answer_says_so() -> None:
    findings = spikes([*steady(300), *burst(200)], [FILLER], answers=())
    assert [(one.id, one.title) for one in findings] == [(UNAVAILABLE_ID, NOT_JUDGED_TITLE)]
    assert "whole group's damage" in findings[0].detail


def test_a_median_of_nothing_names_no_multiple() -> None:
    findings = spikes(burst(200), [FILLER, cast(DRUID, TRANQUILITY, 200)])
    assert the(findings, SPIKES_ID).evidence == (
        "3:20 to 3:25, the heaviest (most of this fight's 5-second windows took no damage): "
        "answered by Tranquility (Restoration Druid, Emberkin)",
    )


def test_no_title_detail_or_evidence_carries_a_raw_damage_figure() -> None:
    nine_minutes = (0, 540_000)
    damage = [*steady(540, per_second=40_000), *burst(100, per_second=900_000),
              *burst(300, per_second=500_000)]
    casts = [FILLER, cast(DRUID, TRANQUILITY, 98), cast(WARRIOR, RALLYING, 60)]
    for finding in spikes(damage, casts, span=nine_minutes):
        for text in (finding.title, finding.detail, *finding.evidence):
            assert not re.search(r"\d{4,}", text), text
```

The expected strings were run against this task's code before the plan was committed (2026-09-29, 20 of 20 green, ruff and mypy clean). If one disagrees now, the code was transcribed differently: diff against the plan before changing a test.

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/analysis/test_spikes.py -q`
Expected: FAIL at import -- `No module named 'wowperf.domain.analysis.spikes'`.

- [ ] **Step 3: Write the module**

Create `src/wowperf/domain/analysis/spikes.py`:

```python
# ABOUTME: The group's heaviest moments of damage taken, and whether a cooldown answered each.
# ABOUTME: Judged for the group, never per healer: the log records presses, not rotation plans.

from collections.abc import Sequence
from enum import StrEnum
from math import ceil
from statistics import median

from wowperf.domain.analysis.throughput import ready_at
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace import clock_text
from wowperf.domain.comparison.pace_player import pair_label
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, Resurrection
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.season import CooldownAbility, Externals, Roles, ThroughputCooldowns

SPIKES_ID = "healing.spikes"
UNANSWERED_ID = "healing.spikes.unanswered"
UNAVAILABLE_ID = "healing.spikes.unavailable"

SPIKE_WINDOW_SECONDS = 5
"""A heavy moment is a rolling window this long, so a burst straddling a boundary is not halved."""

SECONDS_PER_SPIKE = 180
"""One moment is ranked per started stretch this long: the cooldown of almost every answer."""

SPIKE_FLOOR = 2.0
"""A window ranks only at this multiple of the median window or above. Chosen, not measured."""

ANSWER_LEAD_SECONDS = 10
"""A press this long before a window opens still answers it: casting ahead is correct play."""

NOT_JUDGED_TITLE = "Healing cooldowns at the heaviest moments were not judged"


class Answer(Frozen):
    """One cooldown one player holds that answers a heavy moment for the whole group."""

    actor_id: int
    holder: str
    ability: CooldownAbility


class Moment(Frozen):
    """One ranked window. `rank` 1 is the heaviest; `weight` is None when the median window
    took no damage, so there is nothing to weigh it against."""

    start_ms: int
    end_ms: int
    rank: int
    weight: float | None


class State(StrEnum):
    ANSWERED = "answered"
    READY = "unanswered, cooldowns ready"
    NONE_READY = "unanswered, no answer shown ready"


class Verdict(Frozen):
    moment: Moment
    state: State
    pressed: tuple[str, ...] = ()
    ready: tuple[str, ...] = ()
    unready: tuple[str, ...] = ()


def answers_for(
    players: Sequence[Player],
    throughput: ThroughputCooldowns,
    externals: Externals,
    roles: Roles,
) -> tuple[Answer, ...]:
    """Every group answer each player holds: a healer's marked cooldowns, anyone's marked externals.

    Only entries marked `group` count. Both files also hold abilities that
    answer nobody but their target -- Power Infusion, Ironbark -- and a
    heavy moment is the whole group's.
    """
    found: list[Answer] = []
    for player in players:
        abilities: list[CooldownAbility] = [
            one for one in externals.for_spec(player.class_name, player.spec) if one.group
        ]
        if roles.role_of(player.class_name, player.spec) == "healer":
            abilities = [
                one for one in throughput.for_spec(player.class_name, player.spec) if one.group
            ] + abilities
        holder = f"{pair_label(player.class_name, player.spec, plural=False)}, {player.name}"
        found.extend(
            Answer(actor_id=player.actor_id, holder=holder, ability=one) for one in abilities
        )
    return tuple(found)


def heaviest_moments(
    damage_taken: Sequence[DamageTakenEvent],
    player_ids: frozenset[int],
    span: tuple[int, int],
    combat: Sequence[tuple[int, int]],
) -> tuple[Moment, ...]:
    """The heaviest non-overlapping windows of the group's damage taken, in clock order.

    Each hit counts what reached health plus what a shield absorbed, less any
    damage past death: what healers had to answer. Only roster players count.
    A window must sit wholly inside one `combat` stretch -- the fight, or one
    pull of a key -- so the quiet between pulls neither ranks nor drags the
    median down.
    """
    start, end = span
    seconds = max(0, ceil((end - start) / 1000))
    buckets = [0] * seconds
    for hit in damage_taken:
        if hit.actor_id not in player_ids:
            continue
        index = (hit.timestamp_ms - start) // 1000
        if 0 <= index < seconds:
            buckets[index] += max(0, hit.health_damage + hit.absorbed - hit.overkill)

    width = SPIKE_WINDOW_SECONDS
    windows: list[tuple[int, int]] = []
    for first in range(seconds - width + 1):
        opens = start + first * 1000
        closes = opens + width * 1000
        if any(low <= opens and closes <= high for low, high in combat):
            windows.append((sum(buckets[first : first + width]), first))
    if not windows:
        return ()

    wanted = ceil(seconds / SECONDS_PER_SPIKE)
    typical = median(total for total, _ in windows)
    picked: list[tuple[int, int]] = []
    for total, first in sorted(windows, key=lambda one: (-one[0], one[1])):
        if len(picked) >= wanted or total <= 0 or total < SPIKE_FLOOR * typical:
            break
        if any(abs(first - other) < width for _, other in picked):
            continue
        picked.append((total, first))

    moments = [
        Moment(
            start_ms=start + first * 1000,
            end_ms=start + (first + width) * 1000,
            rank=rank,
            weight=total / typical if typical > 0 else None,
        )
        for rank, (total, first) in enumerate(picked, start=1)
    ]
    return tuple(sorted(moments, key=lambda one: one.start_ms))


def _dead_at(
    actor_id: int,
    at_ms: int,
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
) -> bool:
    """Dead when the moment opened: died before it, with no resurrection and no cast since.

    A cast is a sign of life as good as a resurrection record, and the only
    one a player who released and ran back leaves: the log records no return.
    """
    before = [death.timestamp_ms for death in deaths if death.actor_id == actor_id]
    before = [when for when in before if when < at_ms]
    if not before:
        return False
    died = max(before)
    revived = any(
        one.actor_id == actor_id and died < one.timestamp_ms <= at_ms for one in resurrections
    )
    acted = any(one.actor_id == actor_id and died < one.timestamp_ms <= at_ms for one in casts)
    return not (revived or acted)


def judge(
    moment: Moment,
    answers: Sequence[Answer],
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
    visible_from_ms: int,
    setting: str,
) -> Verdict:
    """Which answers were pressed for one moment, which sat ready, and why the rest did not.

    A cooldown never pressed anywhere in the fight is left out altogether:
    whether it was talented cannot be told. Nothing here says a cooldown was
    "on cooldown" -- talents shorten some, so the page states the press it saw.
    """
    lead_ms = ANSWER_LEAD_SECONDS * 1000
    pressed: list[str] = []
    ready: list[str] = []
    unready: list[str] = []
    for answer in answers:
        name = f"{answer.ability.name} ({answer.holder})"
        own = [
            cast.timestamp_ms
            for cast in casts
            if cast.actor_id == answer.actor_id and cast.ability_id == answer.ability.ability_id
        ]
        if not own:
            continue
        if any(moment.start_ms - lead_ms <= when <= moment.end_ms for when in own):
            pressed.append(name)
            continue
        if _dead_at(answer.actor_id, moment.start_ms, casts, deaths, resurrections):
            unready.append(f"{name}: its holder was dead")
            continue
        if ready_at(
            tuple(casts), (answer.ability,), answer.actor_id, moment.start_ms, visible_from_ms
        ):
            ready.append(name)
            continue
        cooldown_ms = answer.ability.cooldown_seconds * 1000
        recent = [when for when in own if moment.start_ms - cooldown_ms <= when <= moment.start_ms]
        if recent:
            unready.append(
                f"{name}: pressed at {clock_text((max(recent) - visible_from_ms) / 1000)}, within "
                f"its base cooldown of {clock_text(answer.ability.cooldown_seconds)}"
            )
        else:
            unready.append(
                f"{name}: not judged, its base cooldown reaches before the {setting}'s first second"
            )

    if pressed:
        state = State.ANSWERED
    elif ready:
        state = State.READY
    else:
        state = State.NONE_READY
    return Verdict(
        moment=moment,
        state=state,
        pressed=tuple(pressed),
        ready=tuple(ready),
        unready=tuple(unready),
    )


def analyse_spikes(
    *,
    damage_taken: Sequence[DamageTakenEvent],
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
    players: Sequence[Player],
    answers: Sequence[Answer],
    span: tuple[int, int],
    combat: Sequence[tuple[int, int]],
    setting: str,
) -> list[Finding]:
    """`healing.spikes`, and `healing.spikes.unanswered` when it applies, or one notice.

    `span` is the fight's, or the whole run's on a key; `combat` the stretches
    a window may sit in; `setting` names the span on the page ("fight", "run").
    """
    if not casts:
        return [_notice(NOT_JUDGED_TITLE, NO_CASTS_DETAIL.format(setting=setting))]
    if not answers:
        return [_notice(NOT_JUDGED_TITLE, NO_ANSWER_DETAIL)]
    moments = heaviest_moments(
        damage_taken, frozenset(player.actor_id for player in players), span, combat
    )
    if not moments:
        return [
            _notice(
                f"No moment of this {setting} was heavy enough to rank",
                NO_MOMENT_DETAIL.format(setting=setting),
            )
        ]

    verdicts = [
        judge(moment, answers, casts, deaths, resurrections, span[0], setting)
        for moment in moments
    ]
    count = len(verdicts)
    plural = "s" if count != 1 else ""
    tally = {state: sum(one.state is state for one in verdicts) for state in State}
    parts = [
        f"{tally[state]} {label}"
        for state, label in (
            (State.ANSWERED, "answered"),
            (State.READY, "unanswered while cooldowns were ready"),
            (State.NONE_READY, "unanswered with no answer shown ready"),
        )
        if tally[state]
    ]
    findings = [
        Finding(
            id=SPIKES_ID,
            title=f"{count} heaviest moment{plural}: {', '.join(parts)}",
            detail=SPIKES_DETAIL.format(setting=setting),
            confidence=Confidence.DERIVED,
            evidence=tuple(_line(one, span[0], setting) for one in verdicts),
        )
    ]
    unanswered = [one for one in verdicts if one.state is State.READY]
    if unanswered:
        findings.append(
            Finding(
                id=UNANSWERED_ID,
                title=(
                    f"{len(unanswered)} of {count} heaviest moment{plural} went unanswered "
                    "while group cooldowns were ready"
                ),
                detail=UNANSWERED_DETAIL.format(setting=setting),
                confidence=Confidence.INFERRED,
                evidence=tuple(_line(one, span[0], setting) for one in unanswered),
            )
        )
    return findings


ORDINALS = ("", "second ", "third ", "fourth ", "fifth ", "sixth ", "seventh ", "eighth ",
            "ninth ", "tenth ")


def _line(verdict: Verdict, origin_ms: int, setting: str) -> str:
    moment = verdict.moment
    opens = clock_text((moment.start_ms - origin_ms) / 1000)
    closes = clock_text((moment.end_ms - origin_ms) / 1000)
    rank = ORDINALS[moment.rank - 1] if moment.rank <= len(ORDINALS) else f"{moment.rank}th "
    weight = (
        f"{moment.weight:.1f} times the median"
        if moment.weight is not None
        else f"most of this {setting}'s {SPIKE_WINDOW_SECONDS}-second windows took no damage"
    )
    if verdict.state is State.ANSWERED:
        body = f"answered by {_joined(verdict.pressed)}"
    elif verdict.state is State.READY:
        body = f"nothing pressed; ready: {_joined(verdict.ready)}"
    else:
        body = "nothing pressed, and no answer was shown ready"
        if verdict.unready:
            body += "; " + "; ".join(verdict.unready)
    return f"{opens} to {closes}, the {rank}heaviest ({weight}): {body}"


def _joined(names: Sequence[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _notice(title: str, detail: str) -> Finding:
    return Finding(
        id=UNAVAILABLE_ID, title=title, detail=detail, confidence=Confidence.MEASURED
    )


SPIKES_DETAIL = (
    "The damage the group's players took, each hit counted as what reached health plus what a "
    f"shield absorbed, less any damage past death, summed over rolling {SPIKE_WINDOW_SECONDS}-"
    f"second windows. One moment is ranked per started {SECONDS_PER_SPIKE // 60} minutes of the "
    "{setting}, heaviest first and never overlapping, and a window counts only at "
    f"{SPIKE_FLOOR:g} times the {{setting}}'s median {SPIKE_WINDOW_SECONDS}-second window or "
    "above. "
    "A healing or group-wide defensive cooldown answers a moment when it was pressed from "
    f"{ANSWER_LEAD_SECONDS} seconds before the window opened to its close."
)
UNANSWERED_DETAIL = (
    "Judged for the group, never for one healer: the group may have planned this moment for a "
    "cooldown that came later. A cooldown reads as ready when its holder pressed it somewhere "
    "in this {setting}, had not pressed it within its base cooldown before the window opened, "
    "and was alive. Talents that shorten a cooldown are not modelled, a second charge reads as "
    "not ready, and a cooldown never pressed in the {setting} is not seen at all, so ready is "
    f"understated, never invented. The {ANSWER_LEAD_SECONDS}-second lead and the floor of "
    f"{SPIKE_FLOOR:g} times the median are chosen numbers, not measured ones."
)
NO_CASTS_DETAIL = (
    "This {setting} was read without its casts, so no press of any cooldown can be seen."
)
NO_ANSWER_DETAIL = (
    "Nobody in this group plays a specialisation holding a healing or group-wide defensive "
    "cooldown that this tool lists as answering the whole group's damage."
)
NO_MOMENT_DETAIL = (
    f"No {SPIKE_WINDOW_SECONDS}-second window of this {{setting}} reached {SPIKE_FLOOR:g} times "
    "its median window, so none is presented as a heavy moment."
)
```

- [ ] **Step 4: Run, pass, prove**

Run the file: 20 pass. Prove, restoring after each:
- count `hit.amount` instead of `health_damage + absorbed - overkill` -> the overkill test red;
- drop the `hit.actor_id not in player_ids` filter -> the pet test red;
- drop the `combat` containment check -> the two-pulls test red;
- make the non-overlap check `< 1` instead of `< width` -> the one-per-three-minutes test red;
- drop `or total < SPIKE_FLOOR * typical` -> the below-twice-the-median test red;
- change `moment.start_ms - lead_ms` to `moment.start_ms` -> the lead test red;
- drop the `_dead_at` branch -> the dead-holder test red;
- make `_dead_at` ignore casts (`acted = False`) -> the sign-of-life test red;
- drop the `if not own: continue` -> the never-pressed test red;
- swap the `not judged` and `pressed at` branches' conditions -> the not-judged test red.

- [ ] **Step 5: Gate and commit**

Full gate. Every golden unchanged (nothing calls the analyser yet). Subject: `Rank the group's heaviest moments and read who answered them`

---

### Task 3: On both pages, from every command

**Files:**
- Modify: `src/wowperf/domain/analysis/service.py` (`analyse`, Mythic+)
- Modify: `src/wowperf/domain/analysis/encounter_service.py` (`analyse_encounter`, raid)
- Modify: `src/wowperf/domain/report/ledger.py` (`PLACEMENTS`), `src/wowperf/domain/report/raid_ledger.py` (`RAID_PLACEMENTS`)
- Modify: `src/wowperf/cli.py` (`analyze`, `raid`, `night`)
- Test: `tests/domain/analysis/test_service.py` (or the file testing `analyse` -- `grep -rln "from wowperf.domain.analysis.service import analyse" tests/`), `tests/domain/analysis/test_encounter_service.py`, `tests/domain/report/test_build.py` and `tests/domain/report/test_raid_build.py` (placement), `tests/adapters/render/test_raid_html_invariants.py` and `tests/adapters/render/test_html_invariants.py` (render), `tests/test_cli.py`, `tests/test_cli_night.py`
- Golden: `tests/adapters/render/golden/raid.html` (moves, deliberately)

**Interfaces:**
- Consumes: Task 2's `Answer`, `answers_for`, `analyse_spikes`, the three ids.
- Produces: `analyse(..., answers: Sequence[Answer] | None = None)` and `analyse_encounter(..., answers: Sequence[Answer] | None = None)` (keywords, last). `None` runs no spike analysis at all -- the convention `pace=None` already follows -- so every existing caller and fixture is untouched.

Read `analyse`, `analyse_encounter`, both placement tables and their docstrings, and the three CLI call sites (`grep -n "= analyse(\|analyse_encounter(" src/wowperf/cli.py`) whole before editing.

- [ ] **Step 1: The two services, test first**

In `analyse` (Mythic+), when `answers is not None`, append:

```python
        findings += analyse_spikes(
            damage_taken=loaded.damage_taken,
            casts=loaded.casts,
            deaths=loaded.deaths,
            resurrections=loaded.resurrections,
            players=loaded.run.players,
            answers=answers,
            span=loaded.run.window_ms,
            combat=tuple((pull.start_ms, pull.end_ms) for pull in loaded.run.pulls),
            setting="run",
        )
```

In `analyse_encounter` (raid), when `answers is not None`:

```python
        span = (loaded.encounter.start_ms, loaded.encounter.end_ms)
        findings += analyse_spikes(
            damage_taken=loaded.damage_taken,
            casts=loaded.casts,
            deaths=loaded.deaths,
            resurrections=loaded.resurrections,
            players=loaded.encounter.players,
            answers=answers,
            span=span,
            combat=(span,),
            setting="fight",
        )
```

Place each call where its docstring's list of analysers reads naturally, and add one sentence to each docstring: the spike analysis runs only when handed an answer set, because the answer set is built from the data files by the caller. Tests, with each file's own fixtures plus `answers_for` over that fixture's players and a hand-built `ThroughputCooldowns`/`Externals` carrying one `group=True` ability the fixture casts: `answers=None` gives no `healing.` finding; an answer set gives exactly one of `healing.spikes` or `healing.spikes.unavailable`, with the Mythic+ one reading "run" and the raid one "fight" in its text. Prove red by not appending, and by passing `setting="fight"` on the Mythic+ side.

- [ ] **Step 2: Placement, test first**

`PLACEMENTS` gains `("healing.", "death_rows")` after `("compare.deaths", "death_rows")`; `RAID_PLACEMENTS` gains `("healing.", "mechanics_rows")` after `("players.damage.", "mechanics_rows")`. Extend each table's docstring by one sentence: heavy moments sit with the deaths they cause on a keystone, and with what hit the raid on a boss. Builder tests: a `healing.spikes` finding and a `healing.spikes.unanswered` finding built by `analyse_spikes` (never hand-typed) land in `report.death_rows` on the Mythic+ report and in `report.mechanics_rows` on the raid report, each exactly once, and on no other field. Prove red by removing each prefix line.

- [ ] **Step 3: Render tests**

On a Mythic+ page and a raid page built with those findings: the Deaths panel (Mythic+) and the Mechanics panel (raid) carry the `healing.spikes` title and each of its evidence lines, taken from the finding object; no other panel carries them; no `>None<`. Assert the rendered text, not that an element exists.

- [ ] **Step 4: The CLI, test first**

In `analyze`, `raid` and `night`, build the answer set from the roster and the two data files and pass it:
- `analyze`: `answers=answers_for(loaded.run.players, throughput, load_externals(), roles)`, reusing the `throughput` the command already loads and lifting `load_roles()` into a local `roles` if it is only inline today.
- `raid`: load `load_throughput_cooldowns()` beside the command's other data loads (it does not load it today), and pass `answers=answers_for(loaded.encounter.players, throughput, externals, roles)`, loading `load_externals()` once and reusing it where the report builder already takes it.
- `night`: one `answers_for(attempt.encounter.players, ...)` per drawn attempt inside the `findings_by_fight` comprehension, the data files loaded once for the night.

Tests: each command's findings file carries exactly one of `healing.spikes` or `healing.spikes.unavailable` per analysed fight or run (the night: per pull); the night golden and every Mythic+ golden unchanged. Prove red by not passing `answers` in one command at a time.

- [ ] **Step 5: The raid golden, deliberately**

`golden_raid_html()` in `tests/adapters/render/test_raid_html_invariants.py` calls `analyse_encounter`; pass it `answers=answers_for(...)` over the golden fixture's players with the repository's real data files (`load_throughput_cooldowns()`, `load_externals()`, `load_roles()`), so the golden pins the block a real run draws. Run `/c/Users/damien/.local/bin/uv.exe run pytest tests/adapters/render/test_raid_html_invariants.py --golden-update`, then `git diff tests/adapters/render/golden/raid.html` and read it whole: the only change is the new ledger rows (or the one notice) inside the Mechanics panel. Anything else moving is a defect: stop and report. Record in the report what the golden now shows (spikes and their states, or which notice).

- [ ] **Step 6: Gate and commit**

Full gate. Only `raid.html` among the goldens changed. Subject: `Show the group's heaviest moments on both pages`

---

### Task 4: Exercise it on real reports

**Files:**
- Modify: `docs/plans/2026-09-29-healing-cooldowns-design.md` (status, §8 Live paragraph)
- Modify: `README.md` (roadmap row for slice 4), `.claude/skills/mplus-analysis/SKILL.md` (what `healing.spikes` can and cannot say)

**This task is not optional.** A new judgement is not done until a live run has exercised it, and a state that never occurs is a defect.

- [ ] **Step 1: The live runs, once each**

Read `.claude/skills/wcl-api/SKILL.md`'s rate-limit sections. Warm caches keep these near a point each; note what each prints:
- `/c/Users/damien/.local/bin/uv.exe run wowperf night cW38jmwdnZfbHVL4 --no-deaths`
- `/c/Users/damien/.local/bin/uv.exe run wowperf raid cW38jmwdnZfbHVL4 --fight 2` and `--fight 30`
- `/c/Users/damien/.local/bin/uv.exe run wowperf analyze 6Kx1P9GbNXrcLdHa` (the fight id the analyze e2e uses; read `tests/e2e/test_analyze_e2e.py` for it)

If any run spends more than 30 points, stop and report before the next.

- [ ] **Step 2: The distribution**

With a scratch script in the session scratchpad that prints no name, no slug and no reference code, read each findings JSON (never the HTML, except a leak scan reduced to counts) and report per fight or run: how many moments were wanted (one per started three minutes), how many ranked, how many the floor cut; per moment its state (answered / unanswered with cooldowns ready / no answer shown ready) and, for the last, how many answers read "its holder was dead", "pressed at ..., within its base cooldown", and "not judged"; which notice fired where. Totals across all runs: each state, each reason, each notice. Scan each HTML for `>None<`, `>null<`, `>nan<`, `{{`, `{%` as counts. A state or reason that never occurs is reported as open, not settled; do not go looking for another report -- RwlRwl supplies one.

- [ ] **Step 3: The docs**

- Design: status line gains "built"; under §8 a "Live" paragraph with the counts (numbers, fight ids and boss indices only), the points spent, and every state or reason that did not occur, marked open. If "not judged" dominates the raid moments, say so plainly: it is what the reset check predicted, and the cross-pull follow-up (design §5) is how it would shrink.
- README: the slice 4 roadmap row moves from Planned to started, naming this sub-slice.
- `.claude/skills/mplus-analysis/SKILL.md`: a short entry for `healing.spikes` and `healing.spikes.unanswered` -- what they measure, that the judgement is the group's, that "ready" is understated and never invented, that "not judged" is not a fault, and that the lead and the floor are chosen numbers. Run `tests/test_skills.py`.

- [ ] **Step 4: Gate and commit**

Offline gate. Subject: `Exercise the heaviest-moment judgement on real reports`. Body: the points spent and the per-state counts, no names.

---

## What this plan deliberately does not build

- Any per-healer judgement.
- New group defensives (Anti-Magic Zone, Darkness, Aura Mastery): each needs a verified id and cooldown, and each would also appear on every death card.
- Judging a `night` pull's early moments from the previous pull's casts.
- The healer's side of each death (sub-slice 2), healing throughput, mana.
- A per-boss line across a night's pulls.
