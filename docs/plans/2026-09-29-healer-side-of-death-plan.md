# The healer's side of each death -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every death card a "Healers" group: for each other healer, alive or dead, where their casts in the last ten seconds were aimed, the last cast at the dying player, and where each of their group healing cooldowns stood -- read by the same rule the heavy-moment finding reads them.

**Architecture:** The per-cooldown rule inside `spikes.py` `judge` is extracted to `domain/analysis/cooldown_reading.py` and both surfaces call it. A pure analyser, `domain/analysis/healer_side.py`, reads one death's other healers off the roster, the roles and the cast stream. The deaths builder turns that into a `HealerGroup` on `DeathCard`; the template loops. `build_deaths` draws the group only when handed `roles`, so every existing caller and golden is untouched until the wiring task passes it.

**Tech Stack:** Python 3.12, pydantic frozen models, Jinja2, pytest, typer `CliRunner`. `uv` only: in Bash, `/c/Users/damien/.local/bin/uv.exe`.

**Spec:** `docs/plans/2026-09-29-healer-side-of-death-design.md` -- read it whole before Task 1. Sub-slice 1's design, `docs/plans/2026-09-29-healing-cooldowns-design.md` §5, holds the cooldown rule this plan extracts.

## Global Constraints

- No new Warcraft Logs query and no new API field (§2). Every field used is already on `CastEvent`, `Death`, `Resurrection`, `Player`.
- Descriptive only: no finding, no verdict on any healer, never "on cooldown", never "should" (§1, §4).
- The window is the card's run-up, `RUN_UP_SECONDS` (10) from `domain/analysis/defensives.py` (§3).
- A cooldown reads as ready only where `ready_at()` does; the rule is one function shared with `spikes.py`, whose output stays byte-identical (§4).
- Figures are counts and seconds only; no healing amount anywhere (§3).
- Badges: the lines `measured`, the cooldown states `derived` (§3).
- Only `group = true` entries of `data/throughput_cooldowns.toml`; externals stay in "Teammates' externals" (§4).
- `src/wowperf/domain/` performs no I/O. The report's one inline script is untouched. The stylesheet is untouched (every page inlines it, so an edit would move every golden).
- No real character name in `tests/`: only `Emberkin`, `Stonewake`, `Bríala`, `Кириллица` (plus `Briala`). Players on `cW38jmwdnZfbHVL4` and `6Kx1P9GbNXrcLdHa` are referred to by class, spec, role or index only -- never by name, slug or raw finding id -- in replies, commits, documents and test messages.
- Every new test is shown able to fail: break the line it guards, watch it go red, restore. Read `.claude/skills/testing/test-driven-development/SKILL.md` before the first test. Fixture clocks sit on a non-zero origin (`.claude/lessons.md`, 2026-09-29).
- Every new code file starts with two `ABOUTME: ` lines. Comments evergreen.
- Commits: imperative subject, no prefix, body says why, plain ASCII, last line a `Co-Authored-By:` naming the model that wrote the commit. Commit with `/mingw64/bin/git`. Never `--no-verify`.
- Gate after every task: `uv run ruff check .`, `uv run mypy` (strict over `tests/` too), `uv run pytest` -- green, output pristine.
- Goldens: no golden moves in Tasks 1-3. In Task 4 the goldens move deliberately, each diff read whole: the Healers group and nothing else. If a golden moves anywhere else, stop and report.

The code in Tasks 1-3 was run on 2026-09-29 before this plan was committed: 2719 passed, ruff and mypy clean, no golden moved. If a test disagrees now, the code was transcribed differently: diff against the plan before changing a test.

---

### Task 1: One rule for where a cooldown stood

**Files:**
- Create: `src/wowperf/domain/analysis/cooldown_reading.py`
- Modify: `src/wowperf/domain/analysis/spikes.py` (`judge`, the imports; `_dead_at` moves out)
- Test: `tests/domain/analysis/test_cooldown_reading.py` (create); `tests/domain/analysis/test_spikes.py` unchanged

**Interfaces:**
- Produces: `Reading` (StrEnum: `UNSEEN`, `PRESSED`, `DEAD`, `READY`, `WITHIN`, `NOT_JUDGED`, values `"unseen"`, `"pressed"`, `"dead"`, `"ready"`, `"within"`, `"unjudged"`); `CooldownReading(reading, press_ms: int | None = None)`; `dead_at(actor_id, at_ms, casts, deaths, resurrections) -> bool`; `read_cooldown(ability, actor_id, casts, deaths, resurrections, *, pressed_from_ms, judged_at_ms, pressed_until_ms, visible_from_ms) -> CooldownReading`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/analysis/test_cooldown_reading.py`:

```python
# ABOUTME: Where one holder's cooldown stood at a moment, read the one way every surface reads it.
# ABOUTME: Pins each reading on a clock whose origin is not zero, so an origin slip cannot pass.

from wowperf.domain.analysis.cooldown_reading import (
    CooldownReading,
    Reading,
    dead_at,
    read_cooldown,
)
from wowperf.domain.events import CastEvent, Death, Resurrection
from wowperf.domain.season import CooldownAbility

ORIGIN = 3_000_000
"""The log's first second, far from zero: real timestamps are report-relative."""

TRANQUILITY = CooldownAbility(
    ability_id=740, name="Tranquility", cooldown_seconds=180.0, group=True
)
DRUID = 1


def at(second: float) -> int:
    return ORIGIN + int(second * 1000)


def press(second: float, actor_id: int = DRUID, ability_id: int = 740) -> CastEvent:
    return CastEvent(
        actor_id=actor_id, ability_id=ability_id, ability_name="Tranquility",
        timestamp_ms=at(second),
    )


def reading_at(
    second: float,
    casts: list[CastEvent],
    *,
    deaths: tuple[Death, ...] = (),
    resurrections: tuple[Resurrection, ...] = (),
    visible_from_ms: int = ORIGIN,
) -> CooldownReading:
    """Judged at `second`, pressed-window the ten seconds before it -- a death card's run-up."""
    return read_cooldown(
        TRANQUILITY, DRUID, casts, deaths, resurrections,
        pressed_from_ms=at(second - 10), judged_at_ms=at(second - 10),
        pressed_until_ms=at(second), visible_from_ms=visible_from_ms,
    )


def test_a_cooldown_never_pressed_in_the_log_is_unseen() -> None:
    other = press(50, ability_id=132158)
    assert reading_at(300, [other]) == CooldownReading(reading=Reading.UNSEEN)


def test_a_press_inside_the_window_is_pressed_and_carries_the_latest_press() -> None:
    assert reading_at(300, [press(293), press(296)]) == CooldownReading(
        reading=Reading.PRESSED, press_ms=at(296)
    )


def test_a_press_one_millisecond_before_the_window_is_not_pressed() -> None:
    before = CastEvent(
        actor_id=DRUID, ability_id=740, ability_name="Tranquility", timestamp_ms=at(290) - 1
    )
    assert reading_at(300, [before]).reading is Reading.WITHIN


def test_ready_only_where_ready_at_says_so() -> None:
    assert reading_at(300, [press(20)]) == CooldownReading(reading=Reading.READY)


def test_a_press_inside_the_base_cooldown_is_within_and_carries_that_press() -> None:
    assert reading_at(300, [press(20), press(200)]) == CooldownReading(
        reading=Reading.WITHIN, press_ms=at(200)
    )


def test_a_press_before_the_visible_origin_is_within_and_keeps_its_timestamp() -> None:
    pre_pull = press(-15)
    reading = reading_at(100, [pre_pull])
    assert reading == CooldownReading(reading=Reading.WITHIN, press_ms=at(-15))


def test_a_base_cooldown_reaching_before_the_log_is_not_judged() -> None:
    assert reading_at(100, [press(250)]) == CooldownReading(reading=Reading.NOT_JUDGED)


def test_the_visible_origin_is_what_decides_not_judged() -> None:
    later_origin = at(60)
    assert reading_at(200, [press(250)], visible_from_ms=later_origin).reading is (
        Reading.NOT_JUDGED
    )
    assert reading_at(200, [press(250)]).reading is Reading.READY


def test_a_holder_dead_at_the_judged_moment_reads_dead() -> None:
    died = Death(player_name="Emberkin", actor_id=DRUID, timestamp_ms=at(250),
                 killing_blow="Venom Bolt")
    assert reading_at(300, [press(20)], deaths=(died,)) == CooldownReading(reading=Reading.DEAD)


def test_a_press_in_the_window_outranks_a_death() -> None:
    died = Death(player_name="Emberkin", actor_id=DRUID, timestamp_ms=at(250),
                 killing_blow="Venom Bolt")
    assert reading_at(300, [press(20), press(295)], deaths=(died,)).reading is Reading.PRESSED


def test_dead_until_a_resurrection_or_a_cast_says_otherwise() -> None:
    died = Death(player_name="Emberkin", actor_id=DRUID, timestamp_ms=at(100),
                 killing_blow="Venom Bolt")
    back = Resurrection(actor_id=DRUID, caster_id=2, ability_id=20484, ability_name="Rebirth",
                        timestamp_ms=at(120))
    acted = press(130, ability_id=774)
    assert dead_at(DRUID, at(150), [], [died], []) is True
    assert dead_at(DRUID, at(150), [], [died], [back]) is False
    assert dead_at(DRUID, at(150), [acted], [died], []) is False
    assert dead_at(DRUID, at(90), [], [died], []) is False
```

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/analysis/test_cooldown_reading.py -q`
Expected: FAIL at import -- `No module named 'wowperf.domain.analysis.cooldown_reading'`.

- [ ] **Step 3: Write the module**

Create `src/wowperf/domain/analysis/cooldown_reading.py`:

```python
# ABOUTME: Where one holder's cooldown stood at a moment: pressed, ready, out of reach, not judged.
# ABOUTME: One rule for every surface that asks, so two parts of a page cannot disagree on a press.

from collections.abc import Sequence
from enum import StrEnum

from wowperf.domain.analysis.throughput import ready_at
from wowperf.domain.base import Frozen
from wowperf.domain.events import CastEvent, Death, Resurrection
from wowperf.domain.season import CooldownAbility


class Reading(StrEnum):
    """What the log shows of one cooldown at one moment. Never "on cooldown": talents shorten
    some cooldowns, so a press within the base cooldown is stated as the press it was."""

    UNSEEN = "unseen"
    PRESSED = "pressed"
    DEAD = "dead"
    READY = "ready"
    WITHIN = "within"
    NOT_JUDGED = "unjudged"


class CooldownReading(Frozen):
    """One reading, and the press it rests on: the latest press in the window for PRESSED,
    the latest press inside the base cooldown for WITHIN, None otherwise."""

    reading: Reading
    press_ms: int | None = None


def dead_at(
    actor_id: int,
    at_ms: int,
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
) -> bool:
    """Dead at `at_ms`: died before it, with no resurrection and no cast since.

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


def read_cooldown(
    ability: CooldownAbility,
    actor_id: int,
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
    *,
    pressed_from_ms: int,
    judged_at_ms: int,
    pressed_until_ms: int,
    visible_from_ms: int,
) -> CooldownReading:
    """Where `ability`, held by `actor_id`, stood at `judged_at_ms`.

    UNSEEN when it was never pressed in the log read: whether it was talented
    cannot be told. PRESSED when a press falls in `[pressed_from_ms,
    pressed_until_ms]`, whatever its target. DEAD when its holder was dead at
    `judged_at_ms`. READY only where `ready_at()` says so. WITHIN when a press
    falls inside the base cooldown before `judged_at_ms`; NOT_JUDGED when none
    does but the base cooldown reaches back before `visible_from_ms`, where a
    press would be invisible.
    """
    own = [
        cast.timestamp_ms
        for cast in casts
        if cast.actor_id == actor_id and cast.ability_id == ability.ability_id
    ]
    if not own:
        return CooldownReading(reading=Reading.UNSEEN)
    pressed = [when for when in own if pressed_from_ms <= when <= pressed_until_ms]
    if pressed:
        return CooldownReading(reading=Reading.PRESSED, press_ms=max(pressed))
    if dead_at(actor_id, judged_at_ms, casts, deaths, resurrections):
        return CooldownReading(reading=Reading.DEAD)
    if ready_at(tuple(casts), (ability,), actor_id, judged_at_ms, visible_from_ms):
        return CooldownReading(reading=Reading.READY)
    cooldown_ms = ability.cooldown_seconds * 1000
    recent = [when for when in own if judged_at_ms - cooldown_ms <= when <= judged_at_ms]
    if recent:
        return CooldownReading(reading=Reading.WITHIN, press_ms=max(recent))
    return CooldownReading(reading=Reading.NOT_JUDGED)
```

- [ ] **Step 4: Put `judge` on it**

In `src/wowperf/domain/analysis/spikes.py`:
- Replace `from wowperf.domain.analysis.throughput import ready_at` with `from wowperf.domain.analysis.cooldown_reading import Reading, read_cooldown` (nothing else in the file uses `ready_at`).
- Delete `_dead_at` whole (it now lives in `cooldown_reading.py` as `dead_at`; grep: nothing else imports `_dead_at`).
- In `judge`, replace the body of `for answer in answers:` -- from `name = ...` through the final `unready.append(... not judged ...)` -- with:

```python
        name = f"{answer.ability.name} ({answer.holder})"
        reading = read_cooldown(
            answer.ability, answer.actor_id, casts, deaths, resurrections,
            pressed_from_ms=moment.start_ms - lead_ms,
            judged_at_ms=moment.start_ms,
            pressed_until_ms=moment.end_ms,
            visible_from_ms=visible_from_ms,
        )
        if reading.reading is Reading.UNSEEN:
            continue
        if reading.reading is Reading.PRESSED:
            pressed.append(name)
        elif reading.reading is Reading.DEAD:
            unready.append(f"{name}: its holder was dead")
        elif reading.reading is Reading.READY:
            ready.append(name)
        elif reading.reading is Reading.WITHIN:
            assert reading.press_ms is not None  # WITHIN always carries its press
            # A key's casts are read from the fight's start, but its clock starts at
            # the first pull: a press between the two has no clock to print.
            if reading.press_ms < visible_from_ms:
                unready.append(
                    f"{name}: pressed before the {setting}'s first second, within its base "
                    f"cooldown of {clock_text(answer.ability.cooldown_seconds)}"
                )
            else:
                unready.append(
                    f"{name}: pressed at "
                    f"{clock_text((reading.press_ms - visible_from_ms) / 1000)}, within "
                    f"its base cooldown of {clock_text(answer.ability.cooldown_seconds)}"
                )
        else:
            unready.append(
                f"{name}: not judged, its base cooldown reaches before the {setting}'s first second"
            )
```

`lead_ms`, `pressed`, `ready`, `unready` and everything after the loop stay as they are.

- [ ] **Step 5: Run, pass, prove**

Run `tests/domain/analysis/test_cooldown_reading.py` (11 pass) and `tests/domain/analysis/test_spikes.py` plus `tests/adapters/render/test_raid_html_invariants.py` (unchanged, green -- the refactor must not move a byte). Prove, restoring after each:
- drop `if not own: return ... UNSEEN` -> the never-pressed test red;
- make the pressed window open at `pressed_from_ms - 1` -> the one-millisecond test red;
- drop the `dead_at` branch -> the dead-holder test red;
- pass `0` instead of `visible_from_ms` to `ready_at` -> the visible-origin test red;
- swap the WITHIN and NOT_JUDGED returns -> the within and not-judged tests red;
- make `dead_at` ignore resurrections, then casts -> the dead-until test red each time;
- in `judge`, route WITHIN always to the "pressed at" wording -> `test_spikes.py`'s pre-pull test red.

- [ ] **Step 6: Gate and commit**

Full gate. Every golden unchanged. Subject: `Read a cooldown's standing by one rule the whole page shares`

---

### Task 2: The other healers' side of one death

**Files:**
- Create: `src/wowperf/domain/analysis/healer_side.py`
- Test: `tests/domain/analysis/test_healer_side.py` (create)

**Interfaces:**
- Consumes: Task 1's `Reading`, `CooldownReading`, `dead_at`, `read_cooldown`; `RUN_UP_SECONDS` (`domain/analysis/defensives.py`); `CooldownAbility.group`.
- Produces: `TargetCounts(at_player, at_self, at_other_players, at_non_players, untargeted)` with `.total`; `HealerCooldown(ability, reading)`; `HealerSide(healer, dead, casts, last_at_player_ms, cooldowns=(), listed=0)`; `healer_side(death, players, casts, deaths, resurrections, roles, throughput, visible_from_ms) -> tuple[HealerSide, ...]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/analysis/test_healer_side.py`:

```python
# ABOUTME: The other healers' side of one death: who counts, where casts went, their cooldowns.
# ABOUTME: Every fixture sits on a clock whose origin is not zero, as report timestamps do.

from wowperf.domain.analysis.cooldown_reading import CooldownReading, Reading
from wowperf.domain.analysis.healer_side import TargetCounts, healer_side
from wowperf.domain.events import CastEvent, Death, Resurrection
from wowperf.domain.model import Player
from wowperf.domain.season import CooldownAbility, Roles, ThroughputCooldowns

ORIGIN = 3_000_000

DRUID = Player(actor_id=1, name="Emberkin", class_name="Druid", spec="Restoration", item_level=690)
PRIEST = Player(actor_id=2, name="Bríala", class_name="Priest", spec="Holy", item_level=690)
WARRIOR = Player(actor_id=3, name="Stonewake", class_name="Warrior", spec="Arms", item_level=690)
ROSTER = (DRUID, PRIEST, WARRIOR)
ENEMY = 900

TRANQUILITY = CooldownAbility(
    ability_id=740, name="Tranquility", cooldown_seconds=180.0, group=True
)
SWIFTNESS = CooldownAbility(ability_id=132158, name="Nature's Swiftness", cooldown_seconds=60.0)
HYMN = CooldownAbility(ability_id=64843, name="Divine Hymn", cooldown_seconds=180.0, group=True)
THROUGHPUT = ThroughputCooldowns(
    entries=(("Druid/Restoration", (TRANQUILITY, SWIFTNESS)), ("Priest/Holy", (HYMN,)))
)
ROLES = Roles(healers=("Druid/Restoration", "Priest/Holy"))

REJUVENATION = 774


def at(second: float) -> int:
    return ORIGIN + int(second * 1000)


def cast(player: Player, second: float, target: int | None, ability_id: int = REJUVENATION
         ) -> CastEvent:
    return CastEvent(
        actor_id=player.actor_id, ability_id=ability_id, ability_name="Rejuvenation",
        timestamp_ms=at(second), target_id=target,
    )


def death_of(player: Player, second: float) -> Death:
    return Death(player_name=player.name, actor_id=player.actor_id, timestamp_ms=at(second),
                 killing_blow="Venom Bolt")


def test_every_other_healer_counts_and_the_dying_healer_does_not() -> None:
    sides = healer_side(
        death_of(DRUID, 300), ROSTER, [], (), (), ROLES, THROUGHPUT, ORIGIN
    )
    assert [side.healer.name for side in sides] == ["Bríala"]


def test_a_group_with_no_other_healer_yields_no_side() -> None:
    only_druid = Roles(healers=("Druid/Restoration",))
    assert healer_side(
        death_of(DRUID, 300), ROSTER, [], (), (), only_druid, THROUGHPUT, ORIGIN
    ) == ()


def test_casts_in_the_run_up_are_counted_by_where_they_were_aimed() -> None:
    casts = [
        cast(DRUID, 291, WARRIOR.actor_id),
        cast(DRUID, 292, WARRIOR.actor_id),
        cast(DRUID, 293, DRUID.actor_id),
        cast(DRUID, 294, PRIEST.actor_id),
        cast(DRUID, 295, ENEMY),
        cast(DRUID, 296, None),
        cast(DRUID, 289, WARRIOR.actor_id),
    ]
    side = healer_side(death_of(WARRIOR, 300), ROSTER, casts, (), (), ROLES, THROUGHPUT, ORIGIN)[0]
    assert side.healer is DRUID
    assert side.casts == TargetCounts(
        at_player=2, at_self=1, at_other_players=1, at_non_players=1, untargeted=1
    )
    assert side.casts.total == 6


def test_the_last_cast_at_the_dying_player_is_the_latest_one_in_the_run_up() -> None:
    casts = [cast(DRUID, 292, WARRIOR.actor_id), cast(DRUID, 297, WARRIOR.actor_id),
             cast(DRUID, 299, PRIEST.actor_id)]
    side = healer_side(death_of(WARRIOR, 300), ROSTER, casts, (), (), ROLES, THROUGHPUT, ORIGIN)[0]
    assert side.last_at_player_ms == at(297)


def test_no_cast_at_the_dying_player_leaves_no_last_cast() -> None:
    casts = [cast(DRUID, 285, WARRIOR.actor_id), cast(DRUID, 295, PRIEST.actor_id)]
    side = healer_side(death_of(WARRIOR, 300), ROSTER, casts, (), (), ROLES, THROUGHPUT, ORIGIN)[0]
    assert side.last_at_player_ms is None
    assert side.casts == TargetCounts(at_other_players=1)


def test_only_marked_cooldowns_are_read_and_a_never_pressed_one_is_left_out() -> None:
    casts = [cast(DRUID, 20, None, ability_id=740), cast(DRUID, 250, None, ability_id=132158)]
    side = healer_side(death_of(WARRIOR, 300), ROSTER, casts, (), (), ROLES, THROUGHPUT, ORIGIN)
    druid, priest = side
    assert [(one.ability.name, one.reading) for one in druid.cooldowns] == [
        ("Tranquility", CooldownReading(reading=Reading.READY))
    ]
    assert (druid.listed, priest.listed, priest.cooldowns) == (1, 1, ())


def test_a_cooldown_pressed_in_the_run_up_reads_pressed_whatever_its_target() -> None:
    casts = [cast(DRUID, 296, None, ability_id=740)]
    druid = healer_side(
        death_of(WARRIOR, 300), ROSTER, casts, (), (), ROLES, THROUGHPUT, ORIGIN
    )[0]
    assert druid.cooldowns[0].reading == CooldownReading(reading=Reading.PRESSED, press_ms=at(296))


def test_a_cooldown_is_judged_as_the_run_up_opens() -> None:
    pressed_just_inside_its_cooldown = cast(DRUID, 111, None, ability_id=740)
    druid = healer_side(
        death_of(WARRIOR, 300), ROSTER, [pressed_just_inside_its_cooldown], (), (), ROLES,
        THROUGHPUT, ORIGIN,
    )[0]
    assert druid.cooldowns[0].reading == CooldownReading(reading=Reading.WITHIN, press_ms=at(111))


def test_a_dead_healer_is_dead_and_lists_no_cooldown() -> None:
    casts = [cast(DRUID, 20, None, ability_id=740), cast(DRUID, 292, WARRIOR.actor_id)]
    sides = healer_side(
        death_of(WARRIOR, 300), ROSTER, casts, (death_of(DRUID, 295),), (), ROLES, THROUGHPUT,
        ORIGIN,
    )
    druid = sides[0]
    assert (druid.dead, druid.cooldowns, druid.listed) == (True, (), 1)
    assert druid.casts == TargetCounts(at_player=1)


def test_a_healer_brought_back_before_the_death_is_alive() -> None:
    back = Resurrection(actor_id=DRUID.actor_id, caster_id=PRIEST.actor_id, ability_id=20484,
                        ability_name="Rebirth", timestamp_ms=at(295))
    sides = healer_side(
        death_of(WARRIOR, 300), ROSTER, [cast(DRUID, 20, None, ability_id=740)],
        (death_of(DRUID, 200),), (back,), ROLES, THROUGHPUT, ORIGIN,
    )
    assert sides[0].dead is False
```

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/analysis/test_healer_side.py -q`
Expected: FAIL at import -- `No module named 'wowperf.domain.analysis.healer_side'`.

- [ ] **Step 3: Write the module**

Create `src/wowperf/domain/analysis/healer_side.py`:

```python
# ABOUTME: What the other healers were doing in a dying player's last seconds, read off the casts.
# ABOUTME: Where their casts were aimed and where their group cooldowns stood: facts, no verdict.

from collections.abc import Sequence

from wowperf.domain.analysis.cooldown_reading import (
    CooldownReading,
    Reading,
    dead_at,
    read_cooldown,
)
from wowperf.domain.analysis.defensives import RUN_UP_SECONDS
from wowperf.domain.base import Frozen
from wowperf.domain.events import CastEvent, Death, Resurrection
from wowperf.domain.model import Player
from wowperf.domain.season import CooldownAbility, Roles, ThroughputCooldowns


class TargetCounts(Frozen):
    """A healer's casts in the run-up, by where each was aimed.

    A target is a player when its id is on the roster; anything else -- an
    enemy, a pet -- is a non-player. `None` is an untargeted cast.
    """

    at_player: int = 0
    at_self: int = 0
    at_other_players: int = 0
    at_non_players: int = 0
    untargeted: int = 0

    @property
    def total(self) -> int:
        return (
            self.at_player + self.at_self + self.at_other_players + self.at_non_players
            + self.untargeted
        )


class HealerCooldown(Frozen):
    """One group healing cooldown a healer holds, and where it stood as the run-up opened."""

    ability: CooldownAbility
    reading: CooldownReading


class HealerSide(Frozen):
    """One other healer at one death.

    `cooldowns` leaves out every cooldown never pressed in the log read, and
    is empty for a dead healer: a dead player presses nothing. `listed` is how
    many group healing cooldowns the healer's specialisation lists at all, so
    a caller can tell "none listed" from "none pressed".
    """

    healer: Player
    dead: bool
    casts: TargetCounts
    last_at_player_ms: int | None
    cooldowns: tuple[HealerCooldown, ...] = ()
    listed: int = 0


def healer_side(
    death: Death,
    players: Sequence[Player],
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
    roles: Roles,
    throughput: ThroughputCooldowns,
    visible_from_ms: int,
) -> tuple[HealerSide, ...]:
    """Every other healer's side of one death, in roster order.

    The window is the card's run-up, `RUN_UP_SECONDS` before the death. Each
    group healing cooldown -- an entry marked `group` under the healer's
    specialisation -- is read as the run-up opens, the card's rule that
    availability is judged from when the damage began, by the same rule the
    heavy-moment finding reads it (`read_cooldown`).
    """
    death_ms = death.timestamp_ms
    opens_ms = int(death_ms - RUN_UP_SECONDS * 1000)
    roster = {player.actor_id for player in players}
    sides: list[HealerSide] = []
    for healer in players:
        if healer.actor_id == death.actor_id:
            continue
        if roles.role_of(healer.class_name, healer.spec) != "healer":
            continue
        own = [
            cast
            for cast in casts
            if cast.actor_id == healer.actor_id and opens_ms <= cast.timestamp_ms <= death_ms
        ]
        counts = TargetCounts(
            at_player=sum(cast.target_id == death.actor_id for cast in own),
            at_self=sum(cast.target_id == healer.actor_id for cast in own),
            at_other_players=sum(
                cast.target_id is not None
                and cast.target_id in roster
                and cast.target_id not in (death.actor_id, healer.actor_id)
                for cast in own
            ),
            at_non_players=sum(
                cast.target_id is not None and cast.target_id not in roster for cast in own
            ),
            untargeted=sum(cast.target_id is None for cast in own),
        )
        at_player = [cast.timestamp_ms for cast in own if cast.target_id == death.actor_id]
        dead = dead_at(healer.actor_id, death_ms, casts, deaths, resurrections)
        marked = [
            one for one in throughput.for_spec(healer.class_name, healer.spec) if one.group
        ]
        readings = (
            ()
            if dead
            else tuple(
                HealerCooldown(ability=ability, reading=reading)
                for ability in marked
                if (reading := read_cooldown(
                    ability, healer.actor_id, casts, deaths, resurrections,
                    pressed_from_ms=opens_ms,
                    judged_at_ms=opens_ms,
                    pressed_until_ms=death_ms,
                    visible_from_ms=visible_from_ms,
                )).reading is not Reading.UNSEEN
            )
        )
        sides.append(
            HealerSide(
                healer=healer,
                dead=dead,
                casts=counts,
                last_at_player_ms=max(at_player) if at_player else None,
                cooldowns=readings,
                listed=len(marked),
            )
        )
    return tuple(sides)
```

- [ ] **Step 4: Run, pass, prove**

Run the file: 10 pass. Prove, restoring after each:
- drop the `healer.actor_id == death.actor_id` skip -> the dying-healer test red;
- drop the `at_self` term from `at_other_players`' exclusion (count self as another player) -> the aim test red;
- open the window at `death_ms - 11_000` -> the aim test red (the 289 cast joins);
- judge at `death_ms` instead of `opens_ms` (`judged_at_ms=death_ms`) -> the judged-as-the-run-up-opens test red;
- read cooldowns for a dead healer too -> the dead-healer test red;
- drop the `if one.group` filter -> the marked-only test red;
- make `dead_at` ignore resurrections (in Task 1's module, temporarily) -> the brought-back test red.

- [ ] **Step 5: Gate and commit**

Full gate. Every golden unchanged. Subject: `Read what the other healers were doing when a player died`

---

### Task 3: The Healers group on the death card

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`HealerLine`, `HealerGroup` after `AvailabilityGroup`; `DeathCard.healers`)
- Modify: `src/wowperf/domain/report/deaths.py` (constants, three helpers, `build_deaths`)
- Modify: `src/wowperf/adapters/render/_deaths.html.j2` (the group, after the availability loop)
- Test: `tests/domain/report/test_build_deaths_healers.py` (create), `tests/adapters/render/test_deaths_healers_html.py` (create)

**Interfaces:**
- Consumes: Task 2's `HealerSide`, `HealerCooldown`, `healer_side`; Task 1's `Reading`.
- Produces: `build_deaths(..., *, trimmed=False, roles: Roles | None = None, throughput: ThroughputCooldowns = ThroughputCooldowns())` -- `roles=None` draws no group; `DeathCard.healers: HealerGroup | None`; constants `NO_OTHER_HEALER`, `HEALER_AIM`, `HEALER_LANDED`, `HEALER_COOLDOWNS`.

- [ ] **Step 1: Write the failing builder tests**

Create `tests/domain/report/test_build_deaths_healers.py`:

```python
# ABOUTME: The Healers group on a death card: one line per other healer, every sentence pinned.
# ABOUTME: Fixtures sit on a non-zero clock origin, as report timestamps do.

import re

from tests.domain.report.test_build_frame import NO_CONSUMABLES, NO_DEFENSIVES, a_pull, a_run
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.deaths import (
    HEALER_AIM,
    HEALER_LANDED,
    NO_OTHER_HEALER,
    build_deaths,
)
from wowperf.domain.report.model import DeathCard, HealerGroup
from wowperf.domain.season import CooldownAbility, Roles, ThroughputCooldowns

ORIGIN = 3_000_000

DRUID = Player(actor_id=1, name="Emberkin", class_name="Druid", spec="Restoration", item_level=690)
PRIEST = Player(actor_id=2, name="Bríala", class_name="Priest", spec="Holy", item_level=690)
WARRIOR = Player(actor_id=3, name="Stonewake", class_name="Warrior", spec="Arms", item_level=690)

TRANQUILITY = CooldownAbility(
    ability_id=740, name="Tranquility", cooldown_seconds=180.0, group=True
)
THROUGHPUT = ThroughputCooldowns(entries=(("Druid/Restoration", (TRANQUILITY,)),))
ROLES = Roles(healers=("Druid/Restoration", "Priest/Holy"))
ENEMY = 900


def at(second: float) -> int:
    return ORIGIN + int(second * 1000)


def cast(player: Player, second: float, target: int | None, ability_id: int = 774) -> CastEvent:
    return CastEvent(
        actor_id=player.actor_id, ability_id=ability_id, ability_name="Rejuvenation",
        timestamp_ms=at(second), target_id=target,
    )


def death_of(player: Player, second: float) -> Death:
    return Death(player_name=player.name, actor_id=player.actor_id, timestamp_ms=at(second),
                 killing_blow="Venom Bolt", pull_index=0)


def card_for(
    casts: list[CastEvent],
    *,
    roster: tuple[Player, ...] = (DRUID, WARRIOR),
    deaths: tuple[Death, ...] = (),
    dying: Player = WARRIOR,
    second: float = 300,
    roles: Roles | None = ROLES,
    trimmed: bool = False,
) -> DeathCard:
    death = death_of(dying, second)
    loaded = LoadedRun(
        run=a_run(players=roster, pulls=(a_pull(0, ORIGIN, at(600)),)),
        deaths=(*deaths, death),
        casts=tuple(casts),
    )
    cards = build_deaths(
        loaded, NO_DEFENSIVES, NO_CONSUMABLES, roles=roles, throughput=THROUGHPUT,
        trimmed=trimmed,
    )
    [card] = [one for one in cards if one.player == dying.name]
    return card


def healers_of(card: DeathCard) -> HealerGroup:
    assert card.healers is not None
    return card.healers


def test_a_card_built_without_roles_draws_no_healers_group() -> None:
    assert card_for([], roles=None).healers is None


def test_a_healers_line_names_the_holder_and_counts_casts_by_aim() -> None:
    casts = [
        cast(DRUID, 291, WARRIOR.actor_id), cast(DRUID, 292, WARRIOR.actor_id),
        cast(DRUID, 293, DRUID.actor_id), cast(DRUID, 295, ENEMY), cast(DRUID, 296, None),
        cast(DRUID, 20, None, ability_id=740),
    ]
    [line] = healers_of(card_for(casts)).lines
    assert line.holder == "Restoration Druid, Emberkin"
    assert line.summary == (
        "alive when this player died; 5 casts in the last 10 seconds: 2 at this player, "
        "1 at themselves, 1 at a non-player, 1 untargeted; the last at this player 8.0 s "
        "before death"
    )


def test_casts_at_other_players_are_counted_in_the_plural() -> None:
    casts = [cast(DRUID, 293, PRIEST.actor_id), cast(DRUID, 294, PRIEST.actor_id)]
    group = healers_of(card_for(casts, roster=(DRUID, PRIEST, WARRIOR)))
    assert [line.summary for line in group.lines][0] == (
        "alive when this player died; 2 casts in the last 10 seconds: 2 at other players; "
        "none at this player"
    )


def test_a_healer_casting_nothing_in_the_run_up_says_so() -> None:
    [line] = healers_of(card_for([cast(DRUID, 20, None, ability_id=740)])).lines
    assert line.summary == "alive when this player died; no cast in the last 10 seconds"


def test_each_cooldown_reading_is_worded_back_from_the_death() -> None:
    ready = healers_of(card_for([cast(DRUID, 20, None, ability_id=740)])).lines[0]
    pressed = healers_of(card_for([cast(DRUID, 297, None, ability_id=740)])).lines[0]
    within = healers_of(card_for([cast(DRUID, 190, None, ability_id=740)])).lines[0]
    unjudged = healers_of(card_for([cast(DRUID, 250, None, ability_id=740)], second=100)).lines[0]
    assert [(row.ability, row.state, row.detail) for row in ready.cooldowns] == [
        ("Tranquility", "ready", "ready")
    ]
    assert [row.detail for row in pressed.cooldowns] == ["pressed 3.0 s before death"]
    assert [row.detail for row in within.cooldowns] == [
        "pressed 1:50 before death, within its base cooldown of 3:00"
    ]
    assert [(row.state, row.detail) for row in unjudged.cooldowns] == [
        ("unjudged", "not judged, its base cooldown reaches before the run's first second")
    ]


def test_a_press_before_the_first_pull_is_timed_back_from_the_death() -> None:
    pre_pull = cast(DRUID, -15, None, ability_id=740)
    [line] = healers_of(card_for([pre_pull], second=100)).lines
    assert [row.detail for row in line.cooldowns] == [
        "pressed 1:55 before death, within its base cooldown of 3:00"
    ]


def test_a_dead_healer_reads_dead_and_lists_no_cooldown() -> None:
    casts = [cast(DRUID, 20, None, ability_id=740)]
    [line] = healers_of(card_for(casts, deaths=(death_of(DRUID, 250),))).lines
    assert line.summary == "dead when this player died; no cast in the last 10 seconds"
    assert (line.cooldowns, line.note) == ((), "")


def test_a_healer_whose_cooldowns_were_never_pressed_says_so_in_one_clause() -> None:
    [line] = healers_of(card_for([cast(DRUID, 295, None)])).lines
    assert line.cooldowns == ()
    assert line.note == (
        "None of their group healing cooldowns was pressed in the log read for this run."
    )


def test_a_healer_whose_spec_lists_no_group_cooldown_says_so() -> None:
    group = healers_of(card_for([], roster=(PRIEST, WARRIOR)))
    assert group.lines[0].note == "No group healing cooldown is listed for Holy Priest."


def test_with_no_other_healer_the_group_holds_one_sentence() -> None:
    group = healers_of(card_for([], dying=DRUID))
    assert (group.lines, group.note, group.badge) == ((), NO_OTHER_HEALER, None)


def test_the_group_is_badged_and_its_note_states_the_limits() -> None:
    group = healers_of(card_for([cast(DRUID, 20, None, ability_id=740)]))
    assert group.badge is not None and group.badge.label == "measured"
    assert group.cooldown_badge is not None and group.cooldown_badge.label == "derived"
    assert group.note == (
        "Casts are counted where they were aimed, not by whom they healed: a smart heal or a "
        "heal over time can reach this player with no cast aimed at them, and a cast at an "
        "enemy can still heal, as Discipline's Atonement does. The heals that landed on this "
        "player are in the timeline above, named by caster. A group healing cooldown reads as "
        "ready only when it was pressed somewhere in the log read for this run, not within its "
        "base cooldown before the damage began, and that base cooldown reaches back no further "
        "than the run's first second. Talents that shorten a cooldown are not modelled, a "
        "second charge reads as not ready, and a cooldown never pressed is not listed, so "
        "ready is understated, never invented."
    )


def test_a_group_listing_no_cooldown_carries_no_derived_badge() -> None:
    group = healers_of(card_for([cast(DRUID, 295, None)]))
    assert group.cooldown_badge is None


def test_a_trimmed_card_does_not_point_at_a_timeline_it_does_not_draw() -> None:
    group = healers_of(card_for([], trimmed=True))
    assert HEALER_AIM in group.note
    assert HEALER_LANDED not in group.note


def test_no_sentence_says_on_cooldown_should_or_carries_a_healing_amount() -> None:
    casts = [cast(DRUID, 190, None, ability_id=740), cast(DRUID, 295, WARRIOR.actor_id)]
    group = healers_of(card_for(casts))
    texts = [group.note, *(line.summary for line in group.lines),
             *(line.note for line in group.lines),
             *(row.detail for line in group.lines for row in line.cooldowns)]
    for text in texts:
        assert "on cooldown" not in text, text
        assert "should" not in text, text
        assert not re.search(r"\d{1,3}(,\d{3})+|\d{4,}", text), text
```

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/report/test_build_deaths_healers.py -q`
Expected: FAIL at import -- `cannot import name 'HEALER_AIM'`.

- [ ] **Step 3: The view model**

In `src/wowperf/domain/report/model.py`, after `AvailabilityGroup`:

```python
class HealerLine(Frozen):
    """One other healer at one death: who, what they were doing, where their cooldowns stood.

    `summary` is the sentence after the holder: alive or dead, the run-up's
    casts by where they were aimed, and the last cast at the dying player.
    `cooldowns` reuses the availability row with states of its own --
    "pressed", "ready", "within", "unjudged" or "dead" -- and never "cooldown":
    talents shorten some, so a press within the base cooldown is stated as the
    press it was. `note` says why the list is empty when it is.
    """

    holder: str
    summary: str
    cooldowns: tuple[AvailabilityRow, ...] = ()
    note: str = ""


class HealerGroup(Frozen):
    """The Healers group on a death card.

    `badge` is measured: the lines are counted straight off the cast stream.
    `cooldown_badge` is derived, and None when no line lists a cooldown. `note`
    states the limits of both, or, with no line, that no other healer was there.
    """

    title: str = "Healers"
    lines: tuple[HealerLine, ...] = ()
    badge: Badge | None = None
    cooldown_badge: Badge | None = None
    note: str = ""
```

In `DeathCard`, after `availability: tuple[AvailabilityGroup, ...] = ()`:

```python
    healers: HealerGroup | None = None
    """The other healers' side of this death, or None where the card was built without the
    roles that say who heals."""
```

- [ ] **Step 4: The builder**

In `src/wowperf/domain/report/deaths.py`:

Imports -- add these, then run `ruff check --fix` on the file to sort them:

```python
from wowperf.domain.analysis.cooldown_reading import Reading
from wowperf.domain.analysis.defensives import RUN_UP_SECONDS
from wowperf.domain.analysis.healer_side import HealerCooldown, HealerSide, healer_side
from wowperf.domain.comparison.pace import clock_text
from wowperf.domain.comparison.pace_player import pair_label
```

add `HealerGroup` and `HealerLine` to the `wowperf.domain.report.model` import, and replace the `wowperf.domain.season` import with:

```python
from wowperf.domain.season import (
    Consumables,
    Defensives,
    Externals,
    Roles,
    SelfResurrections,
    ThroughputCooldowns,
)
```

After `NO_TEAMMATE_EXTERNALS = ...`:

```python
NO_OTHER_HEALER = "No other healer was in the group."

HEALER_AIM = (
    "Casts are counted where they were aimed, not by whom they healed: a smart heal or a heal "
    "over time can reach this player with no cast aimed at them, and a cast at an enemy can "
    "still heal, as Discipline's Atonement does."
)
HEALER_LANDED = "The heals that landed on this player are in the timeline above, named by caster."
"""Left out of a trimmed card's note: that card draws no timeline to point at."""

HEALER_COOLDOWNS = (
    "A group healing cooldown reads as ready only when it was pressed somewhere in the log read "
    "for this {setting}, not within its base cooldown before the damage began, and that base "
    "cooldown reaches back no further than the {setting}'s first second. Talents that shorten "
    "a cooldown are not modelled, a second charge reads as not ready, and a cooldown never "
    "pressed is not listed, so ready is understated, never invented."
)

_AIMS = (
    ("at this player", "at this player"),
    ("at themselves", "at themselves"),
    ("at another player", "at other players"),
    ("at a non-player", "at non-players"),
    ("untargeted", "untargeted"),
)
```

After `_came_back`:

```python
def _healer_summary(side: HealerSide, death: Death) -> str:
    """Alive or dead, the run-up's casts by where they were aimed, and the last at this player."""
    parts = ["dead when this player died" if side.dead else "alive when this player died"]
    counts = side.casts
    window = f"in the last {RUN_UP_SECONDS:g} seconds"
    if not counts.total:
        parts.append(f"no cast {window}")
        return "; ".join(parts)
    aimed = [
        f"{count} {one if count == 1 else many}"
        for count, (one, many) in zip(
            (counts.at_player, counts.at_self, counts.at_other_players, counts.at_non_players,
             counts.untargeted),
            _AIMS,
            strict=True,
        )
        if count
    ]
    parts.append(f"{counts.total} {plural(counts.total, 'cast')} {window}: {', '.join(aimed)}")
    if side.last_at_player_ms is None:
        parts.append("none at this player")
    else:
        seconds = (death.timestamp_ms - side.last_at_player_ms) / 1000
        parts.append(f"the last at this player {seconds:.1f} s before death")
    return "; ".join(parts)


def _healer_cooldown_row(cooldown: HealerCooldown, death: Death, setting: str) -> AvailabilityRow:
    """One group healing cooldown, timed back from the death like the rest of the card."""
    reading = cooldown.reading
    ability = cooldown.ability
    if reading.reading is Reading.PRESSED:
        assert reading.press_ms is not None  # PRESSED always carries its press
        detail = f"pressed {(death.timestamp_ms - reading.press_ms) / 1000:.1f} s before death"
    elif reading.reading is Reading.READY:
        detail = "ready"
    elif reading.reading is Reading.WITHIN:
        assert reading.press_ms is not None  # WITHIN always carries its press
        detail = (
            f"pressed {clock_text((death.timestamp_ms - reading.press_ms) / 1000)} before death, "
            f"within its base cooldown of {clock_text(ability.cooldown_seconds)}"
        )
    elif reading.reading is Reading.DEAD:
        detail = "its holder was dead when the damage began"
    else:
        detail = f"not judged, its base cooldown reaches before the {setting}'s first second"
    return AvailabilityRow(
        ability=ability.name,
        state=str(reading.reading),
        detail=detail,
        ability_id=ability.ability_id,
    )


def _healers(
    sides: tuple[HealerSide, ...], death: Death, names: dict[int, str], setting: str,
    trimmed: bool,
) -> HealerGroup:
    """The Healers group: one line per other healer, or the one line saying there was none."""
    if not sides:
        return HealerGroup(note=NO_OTHER_HEALER)
    lines = []
    for side in sides:
        healer = side.healer
        label = pair_label(healer.class_name, healer.spec, plural=False)
        if side.dead:
            note = ""
        elif not side.listed:
            note = f"No group healing cooldown is listed for {label}."
        elif not side.cooldowns:
            note = (
                "None of their group healing cooldowns was pressed in the log read for this "
                f"{setting}."
            )
        else:
            note = ""
        lines.append(
            HealerLine(
                holder=f"{label}, {names.get(healer.actor_id, healer.name)}",
                summary=_healer_summary(side, death),
                cooldowns=tuple(
                    _healer_cooldown_row(one, death, setting) for one in side.cooldowns
                ),
                note=note,
            )
        )
    note = " ".join(
        [HEALER_AIM, *([] if trimmed else [HEALER_LANDED]),
         HEALER_COOLDOWNS.format(setting=setting)]
    )
    return HealerGroup(
        lines=tuple(lines),
        badge=badge_for(Confidence.MEASURED),
        cooldown_badge=(
            badge_for(Confidence.DERIVED) if any(line.cooldowns for line in lines) else None
        ),
        note=note,
    )
```

In `build_deaths`:
- the signature's keyword block becomes `*, trimmed: bool = False, roles: Roles | None = None, throughput: ThroughputCooldowns = ThroughputCooldowns(),`;
- append to its docstring:

```
    `roles` draws the Healers group: without it nothing says who heals, so no
    card carries the group. `throughput` names each healer's group healing
    cooldowns, read by the same rule the heavy-moment finding reads them.
```

- after `start_ms = loaded.window_ms[0]`: `setting = "run" if loaded.has_pulls else "fight"`;
- in the `DeathCard(...)` call, after `availability=(...),`:

```python
                healers=(
                    None
                    if roles is None
                    else _healers(
                        healer_side(
                            death, loaded.players, loaded.casts, loaded.deaths,
                            loaded.resurrections, roles, throughput, start_ms,
                        ),
                        death, names, setting, trimmed,
                    )
                ),
```

- [ ] **Step 5: Run the builder tests, pass, prove**

Run the file: 14 pass. Prove, restoring after each:
- draw the group when `roles is None` too (use `Roles()`) -> the no-roles test red;
- always include `HEALER_LANDED` -> the trimmed test red;
- swap `_AIMS`' singular and plural for "another player" -> the plural test red;
- word WITHIN by clock from the run's origin (`reading.press_ms - start`) instead of back from the death -> the pre-pull test red (pass `start_ms` through temporarily);
- set `cooldown_badge` unconditionally -> the no-derived-badge test red;
- drop the `elif not side.listed` branch -> the no-group-cooldown test red.

- [ ] **Step 6: The template, test first**

Create `tests/adapters/render/test_deaths_healers_html.py`:

```python
# ABOUTME: The Healers group reaches both pages' Deaths panel as its builder wrote it, alone.
# ABOUTME: Every string asserted is read off the built card, never typed a second time.

from markupsafe import escape

from tests.adapters.render.test_html_invariants import (
    COMPARED,
    SUBJECT,
    minimal_findings,
    minimal_loaded,
)
from tests.adapters.render.test_raid_html_invariants import _panel, a_built_raid_report
from tests.domain.report.test_build_deaths_healers import DRUID, card_for, cast
from tests.domain.report.test_build_frame import FETCHED, NO_CONSUMABLES, NO_DEFENSIVES
from wowperf.adapters.render.html import render, render_raid
from wowperf.domain.report.build import build_report
from wowperf.domain.report.model import DeathCard


def a_card() -> DeathCard:
    return card_for([
        cast(DRUID, 20, None, ability_id=740), cast(DRUID, 293, 3), cast(DRUID, 296, None),
    ])


def drawn_strings(card: DeathCard) -> list[str]:
    assert card.healers is not None
    group = card.healers
    strings = [group.title, group.note]
    for line in group.lines:
        strings += [line.holder, line.summary, *(row.detail for row in line.cooldowns)]
    return [str(escape(one)) for one in strings if one]


def mplus_html(card: DeathCard) -> str:
    report = build_report(
        minimal_loaded(), minimal_findings(), None, COMPARED, SUBJECT, None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
    )
    return render(report.model_copy(update={"deaths": (card,)}))


def test_the_healers_group_is_drawn_in_the_mythic_plus_deaths_panel_alone() -> None:
    card = a_card()
    html = mplus_html(card)
    deaths = _panel(html, "tab-deaths")
    for text in drawn_strings(card):
        assert text in deaths, text
    summary = str(escape(card.healers.lines[0].summary)) if card.healers else ""
    assert html.count(summary) == 1
    assert ">None<" not in deaths


def test_the_healers_group_is_drawn_in_the_raid_deaths_panel_alone() -> None:
    card = a_card()
    html = render_raid(a_built_raid_report().model_copy(update={"deaths": (card,)}))
    deaths = _panel(html, "tab-deaths")
    for text in drawn_strings(card):
        assert text in deaths, text
    summary = str(escape(card.healers.lines[0].summary)) if card.healers else ""
    assert html.count(summary) == 1
    assert ">None<" not in deaths


def test_both_badges_render_beside_what_they_qualify() -> None:
    card = a_card()
    deaths = _panel(mplus_html(card), "tab-deaths")
    healers = deaths[deaths.index('class="avail healers"'):]
    assert 'class="badge badge-measured"' in healers
    assert 'class="badge badge-derived"' in healers


def test_a_card_with_no_other_healer_draws_its_one_sentence() -> None:
    card = card_for([], dying=DRUID)
    deaths = _panel(mplus_html(card), "tab-deaths")
    assert card.healers is not None
    assert str(escape(card.healers.note)) in deaths
    assert 'class="healer-line"' not in deaths
```

Run it: red (the template does not draw the group). Then in `src/wowperf/adapters/render/_deaths.html.j2`, inside `<div class="recap-availability">`, after `{% endfor %}` closing the `death.availability` loop and before the closing `</div>`:

```jinja
      {% if death.healers %}
      <div class="avail healers">
        <p class="avail-title">{{ death.healers.title }}
          {%- if death.healers.badge %} <a class="badge {{ death.healers.badge.tint }}"
             href="#{{ scope }}provenance">{{ death.healers.badge.label }}</a>{% endif %}</p>
        {% for line in death.healers.lines %}
        <p class="healer-line"><span class="owner">{{ line.holder }}</span>: {{ line.summary }}</p>
        {% if line.cooldowns %}
        <ul>
          {% for row in line.cooldowns %}
          <li class="{{ row.state }}">
            <span class="avail-name">{{ ability(row.ability_id, row.ability, row.tooltip) }}</span>
            <span class="avail-detail">{{ row.detail }}</span>
          </li>
          {% endfor %}
        </ul>
        {% endif %}
        {% if line.note %}
        <p class="nests">{{ line.note }}</p>
        {% endif %}
        {% endfor %}
        {% if death.healers.note %}
        <p class="nests">
          {%- if death.healers.cooldown_badge %}<a class="badge {{ death.healers.cooldown_badge.tint }}"
             href="#{{ scope }}provenance">{{ death.healers.cooldown_badge.label }}</a> {% endif -%}
          {{ death.healers.note }}</p>
        {% endif %}
      </div>
      {% endif %}
```

Do not touch `report.css.j2`: every page inlines it, so a rule there moves every golden. The new row states render unstyled, as "ready" already does.

Run: 4 pass. Prove red by deleting the `{% if death.healers %}` block, and by dropping the cooldown-badge link.

- [ ] **Step 7: Gate and commit**

Full gate. Every golden unchanged: no caller passes `roles` yet. Subject: `Draw the other healers' side on each death card`

---

### Task 4: From every command, and the goldens deliberately

**Files:**
- Modify: `src/wowperf/domain/report/build.py` (`build_report`), `src/wowperf/domain/report/raid_build.py` (`build_raid_report`), `src/wowperf/domain/report/night_build.py` (`build_night_report`)
- Modify: `src/wowperf/cli.py` (`analyze`, `raid`, `night`)
- Test: `tests/test_cli.py`, `tests/test_cli_night.py`, the builder tests beside each builder (`tests/domain/report/test_build*.py`, `tests/domain/report/test_raid_build.py`, `tests/domain/report/test_night_build.py` -- grep for each builder's name)
- Golden: `tests/adapters/render/golden/minimal.html`, `raid.html`, `night.html` -- each may move, deliberately

**Interfaces:**
- Consumes: Task 3's `build_deaths(..., roles=, throughput=)`.
- Produces: `build_report(..., roles: Roles | None = None)` (keyword, passed with the `throughput` it already takes); `build_raid_report(..., throughput: ThroughputCooldowns | None = None)` and `build_night_report(..., throughput: ThroughputCooldowns | None = None)`. `None` draws no Healers group -- without the cooldown list the group would say "no group healing cooldown is listed" of specs the data file does list, a false sentence -- so every existing caller stays byte-identical.

Read `build_report`, `build_raid_report`, `build_night_report` and their docstrings, and the three CLI call sites (`grep -n "build_report(\|build_raid_report(\|build_night_report(" src/wowperf/cli.py`), whole before editing.

- [ ] **Step 1: The builders, test first**

- `build_report`: add `roles: Roles | None = None` after `throughput`; pass `roles=roles, throughput=throughput` to its `build_deaths` call.
- `build_raid_report`: add `throughput: ThroughputCooldowns | None = None` beside `pace`; pass `roles=roles if throughput is not None else None, throughput=throughput or ThroughputCooldowns()` to its `build_deaths` call.
- `build_night_report`: add `throughput: ThroughputCooldowns | None = None`; pass it to each pull's `build_raid_report`.
- Each docstring gains one sentence: the Healers group is drawn only when handed what says who heals and which cooldowns they hold.

Tests, one per builder, on each file's own fixtures with a roster holding a healer other than a dying player: without the new argument no card carries `healers`; with it every card does, and the group's first line names that healer. Prove red by not passing the argument through, one builder at a time.

- [ ] **Step 2: The CLI, test first**

- `analyze`: pass `roles=roles` to `build_report` (the command already holds `roles` and `throughput`).
- `raid`: pass `throughput=throughput` to `build_raid_report` (already loaded for `answers_for`).
- `night`: pass `throughput=throughput` to `build_night_report` (already loaded).

Tests: for each command, on a fixture whose transport returns a death and a healer other than the dying player, the written HTML carries `class="avail healers"` inside its Deaths panel, and the command's findings file is byte-identical to what it was before (the group is page-only). If a command's fixture has no such death, extend its transport minimally and say so. Prove red by not passing the argument in one command at a time.

- [ ] **Step 3: The goldens, deliberately**

Each golden builder passes the new argument with the repository's real data files (`load_roles()`, `load_throughput_cooldowns()` from `wowperf.adapters.config.toml`), so a golden pins what a real run draws:
- `minimal_html()` in `tests/adapters/render/test_html_invariants.py`: `roles=load_roles(), throughput=load_throughput_cooldowns()`;
- `golden_raid_html()` in `tests/adapters/render/test_raid_html_invariants.py`: `throughput=load_throughput_cooldowns()`;
- `golden_night_html()` in `tests/adapters/render/test_night_html_invariants.py`: `throughput=load_throughput_cooldowns()`.

Run each golden test with `--golden-update`, then `git diff tests/adapters/render/golden/` and read every changed file whole: the only change is a Healers group on death cards (or its "No other healer was in the group." sentence). Anything else moving is a defect: stop and report. If the night golden's byte-size test (`test_night_html_invariants.py`, the measured-size docstring near line 1067) now fails, update its measured figure and date only if the diff is exactly the group. Record in the report what each golden now shows: how many cards gained the group, how many lines, which sentence where there is no other healer.

- [ ] **Step 4: Gate and commit**

Full gate. Only the three goldens above may have changed. Subject: `Show the other healers' side from every command`

---

### Task 5: Exercise it on real reports

**Files:**
- Modify: `docs/plans/2026-09-29-healer-side-of-death-design.md` (status, §6 Live paragraph)
- Modify: `README.md` (the slice 4 roadmap row), `.claude/skills/mplus-analysis/SKILL.md` (what the Healers group can and cannot say)

**This task is not optional.** A new judgement is not done until a live run has exercised it, and a state that never occurs is a defect.

- [ ] **Step 1: The live runs, once each**

Read `.claude/skills/wcl-api/SKILL.md`'s rate-limit sections. With `--no-compare` (the comparison's references are the costly part and this group does not read them), warm caches keep each near a point; note what each prints, and stop if any spends more than 30:
- `/c/Users/damien/.local/bin/uv.exe run wowperf raid cW38jmwdnZfbHVL4 --fight 2 --no-compare --out <scratchpad dir>`
- the same with `--fight 30`
- `/c/Users/damien/.local/bin/uv.exe run wowperf analyze 6Kx1P9GbNXrcLdHa --fight 36 --no-compare --out <scratchpad dir>`

- [ ] **Step 2: The distribution**

The group is page-only, and the HTML is not read. Write a scratch script in the session scratchpad that loads the same fights through the repository with the default cache dir (warm: no new query beyond the quota read), builds the cards with `build_deaths(..., roles=load_roles(), throughput=load_throughput_cooldowns())`, and prints counts only -- no name, no slug, no reference code: per fight, deaths; cards with "No other healer"; lines alive and dead; each target category summed; lines with "none at this player" and with no cast at all; each cooldown state (`pressed`, `ready`, `within`, `unjudged`, `dead`); lines noting "none pressed" and "none listed". Totals across all three. Scan each written HTML for `>None<`, `>null<`, `>nan<`, `{{`, `{%` as counts. A state that never occurs is reported as open, not settled; do not go looking for another report -- RwlRwl supplies one.

- [ ] **Step 3: The docs**

- Design: status line gains "built"; under §6 a "Live" paragraph with the counts (numbers, fight ids only), the points spent, and every state that did not occur, marked open.
- README: the slice 4 roadmap row names this second sub-slice as built.
- `.claude/skills/mplus-analysis/SKILL.md`: a short entry for the Healers group -- what each line counts, that a cast's target is where it was aimed and not everyone it healed, that it is descriptive and never a verdict on a healer, that its cooldown states follow the heavy-moment rule ("ready" understated, "not judged" is not a fault), and that it is on the page only, not in the findings file. Run `tests/test_skills.py`.

- [ ] **Step 4: Gate and commit**

Offline gate. Subject: `Exercise the healers' side of each death on real reports`. Body: the points spent and the per-state counts, no names.

---

## What this plan deliberately does not build

- Any verdict on a healer, and any finding.
- The early-fight overclaim on the card's existing externals (design §7): a follow-up of its own.
- The triage reading, and naming the other targets of a healer's casts.
- Healing throughput, overhealing, mana.
- A stylesheet rule for the new states.
