# Wipe damage pace, slice 2 (per player) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On `raid --fight N` for a wipe, compare each analysed damage dealer's and tank's cumulative boss damage against the reference kills' players of the same class and specialisation, state a time lag in seconds, and put the reading -- or why it was withheld -- on that player's card on the Players tab.

**Architecture:** The band arithmetic is slice 1's `read_pace`, fed reference *players* instead of reference kills; a new `lag_against` in `pace_curve.py` reads the same median curve for the lag. A new pure `pace_player.py` turns one player's reading into a finding or a notice. The adapter reads each reference kill's roster in the reference-fight lookup slice 1 already makes, splits every boss-only graph slice 1 already fetches by player, and reads a reference kill's deaths only when its leaderboard row says someone died. `analyse_encounter` gains the analyser; the raid card gains `pace_rows`.

**Tech Stack:** Python 3.12, pydantic frozen models, Jinja2, httpx `MockTransport` in adapter tests, typer `CliRunner`, pytest. `uv` only: in Bash, `/c/Users/damien/.local/bin/uv.exe`.

**Spec:** `docs/plans/2026-09-27-wipe-damage-pace-design.md`, **§13** (slice 2). §1-§12 hold where §13 is silent. Read §13 whole before Task 1. Slice 3 (the night page) is not in this plan.

## Global Constraints

- Only on a wipe, only with the comparison on, only when the raid-wide comparison ran: on a kill, with `--no-compare`, or when `compare.pace.unavailable` was emitted, no per-player finding or notice is emitted (§13.4).
- Who is compared: the players the `raid` command analyses (`parse_subjects`), kept when `data/roles.toml` reads them as damage or tank. Healers are not compared (§13.2).
- Against whom: every reference player of the same class **and** specialisation, pooled across the reference kills, each over their own part of their kill (§13.2, §13.3).
- Below `MIN_SAMPLE_FOR_AGGREGATE` (3) same-pair reference players: withheld with a notice, **no fallback** (§13.3).
- The window: from the pull to the first death no resurrection answered, as `return_of` classifies it; a release ends it; an answered death does not, and its dead stretch is named (§13.3).
- The time lag replaces a projection; **no per-player projection** (§13.3).
- Ids and badges: `compare.pace.player.<slug>` `derived`; `compare.pace.player.unavailable.<slug>` `measured`; both carry `player_slug` (§13.4).
- Both go on the player's card on the Players tab and **never** on the Damage tab's rows; no chart, no Summary pointer; Provenance says once "Damage pace per player compares damage dealers and tanks only." (§13.5).
- No raw damage figure on the page or in a finding: shares, clocks and seconds (§3, §13.5).
- The reference roster is read in the existing `REFERENCE_FIGHT_QUERY`, extended with `friendlyPlayers`, `friendlySpecs` and `masterData(translate: true) { actors(type: "Player") { id subType } }`: one request per reference, 2.00 points (§13.2; `.claude/skills/wcl-api/SKILL.md`, "A reference kill's roster costs one point more, read in the same lookup", 2026-09-28). The report's player actors are an id-to-class lookup, never the roster.
- A reference kill's deaths are read only when its `ReferenceKillRow.deaths > 0`, with the existing `DEATHS_QUERY`, into the reference cache (§13.3).
- Nothing persisted names or tabulates a reference: `ReferenceRecord` carries a link and never a figure; `PlayerSeries` carries an actor id and never a name, and lives in memory only.
- `src/wowperf/domain/` performs no I/O. The report's one inline script is untouched.
- Never invent an API field. Every field used is in `.claude/skills/wcl-api/SKILL.md` or already in `queries.py`; death events are read by exactly the keys `build_deaths` reads (`type`, `targetID`, `timestamp`).
- No real character name in `tests/`: only `Emberkin`, `Stonewake`, `Bríala`, `Кириллица` (plus `Briala`). NPC names invented. Players on `cW38jmwdnZfbHVL4` and `6Kx1P9GbNXrcLdHa` are referred to by class, spec, role or index only -- never by name, slug or raw finding id, anywhere.
- Every new test is shown able to fail: break the line it guards, watch it go red, restore. Read `.claude/skills/testing/test-driven-development/SKILL.md` before the first test.
- Every new code file starts with two `ABOUTME: ` lines. Comments evergreen.
- Commits: imperative subject, no prefix, body says why, plain ASCII, last line a `Co-Authored-By:` naming the model that wrote the commit. Commit with `/mingw64/bin/git`. Never `--no-verify`.
- Gate after every task: `uv run ruff check .`, `uv run mypy` (strict over `tests/` too), `uv run pytest` -- green, output pristine.

---

### Task 1: The per-player series and the time lag

**Files:**
- Modify: `src/wowperf/domain/comparison/pace_curve.py`
- Test: `tests/domain/comparison/test_pace_curve.py`

**Interfaces:**
- Produces: `PlayerSeries(actor_id: int, class_name: str, spec: str, damage: BossDamage, until_seconds: float | None = None)`; `PaceReference.players: tuple[PlayerSeries, ...] = ()`; `PaceLag(reached_at: float | None, band_end: int)`; `lag_against(amount: float, references: tuple[PaceReference, ...]) -> PaceLag`.

- [ ] **Step 1: Write the failing tests**

Add `lag_against` to the file's `from wowperf.domain.comparison.pace_curve import (...)` block (alphabetical, after `final_behind_start`), and append:

```python
def one_second_kills(*seconds: int) -> tuple[PaceReference, ...]:
    """Kills dealing 100 a second in 1 s buckets, one per length given."""
    return tuple(a_kill(100, length, interval_ms=1000.0) for length in seconds)


def test_the_lag_is_the_second_the_median_reached_our_total() -> None:
    lag = lag_against(8000.0, one_second_kills(400, 400, 400))
    assert lag.reached_at == pytest.approx(80.0)
    assert lag.band_end == 400


def test_the_lag_is_interpolated_within_the_second() -> None:
    """The median holds 7900 at 79 s and 8000 at 80 s: 7950 is reached half way."""
    lag = lag_against(7950.0, one_second_kills(400, 400, 400))
    assert lag.reached_at == pytest.approx(79.5)


def test_the_lag_reads_the_median_not_the_mean() -> None:
    """At 100, 100 and 400 a second the median is 100 a second; the mean would be 200."""
    kills = (
        a_kill(100, 400, interval_ms=1000.0),
        a_kill(100, 400, interval_ms=1000.0),
        a_kill(400, 400, interval_ms=1000.0),
    )
    assert lag_against(8000.0, kills).reached_at == pytest.approx(80.0)


def test_a_total_the_median_never_reached_has_no_lag() -> None:
    lag = lag_against(50_000.0, one_second_kills(400, 400, 400))
    assert lag.reached_at is None
    assert lag.band_end == 400


def test_the_band_ends_where_fewer_than_three_are_still_fighting() -> None:
    """Four kills of 100, 200, 300 and 400 s: three fight through 200 s, two after."""
    lag = lag_against(50_000.0, one_second_kills(100, 200, 300, 400))
    assert lag.reached_at is None
    assert lag.band_end == 200


def test_the_lag_is_searched_past_where_our_window_ended() -> None:
    """Nothing about our own window bounds the search: 30000 is reached at 300 s."""
    lag = lag_against(30_000.0, one_second_kills(400, 400, 400))
    assert lag.reached_at == pytest.approx(300.0)


def test_nothing_dealt_is_reached_at_the_pull() -> None:
    assert lag_against(0.0, one_second_kills(400, 400, 400)).reached_at == 0.0


def test_fewer_than_three_references_hold_no_band() -> None:
    lag = lag_against(100.0, one_second_kills(400, 400))
    assert lag.reached_at is None
    assert lag.band_end == 0
```

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/comparison/test_pace_curve.py -v`
Expected: FAIL at import -- `cannot import name 'lag_against'`.

- [ ] **Step 3: Write the code**

In `pace_curve.py`, replace the `PaceReference` class with these two classes (`PlayerSeries` first):

```python
class PlayerSeries(Frozen):
    """One player's damage to the boss in one fight, and which class and spec they played.

    `until_seconds` is where a reference player's own death ended their part
    in the kill, counted from the pull; None when they lived to the end.
    Carries an actor id and no name.
    """

    actor_id: int
    class_name: str
    spec: str
    damage: BossDamage
    until_seconds: float | None = None


class PaceReference(Frozen):
    """One reference kill: how long it ran and what it dealt the boss.

    `players` splits `damage` by player, for the per-player comparison; it is
    empty when the kill's roster could not be read. Carries no report code and
    no name. It lives for one comparison in memory and is never written
    anywhere.
    """

    duration_seconds: float
    damage: BossDamage
    players: tuple[PlayerSeries, ...] = ()
```

and append at the end of the file:

```python
class PaceLag(Frozen):
    """When the references' median had dealt a given amount of boss damage.

    `reached_at` is in seconds from the pull, interpolated within the second;
    None when the median never reached the amount before fewer than three
    references were still fighting. `band_end` is the last second that still
    held three.
    """

    reached_at: float | None
    band_end: int


def lag_against(amount: float, references: tuple[PaceReference, ...]) -> PaceLag:
    """The first time the references' median reached `amount`, over every second the band holds.

    The median is taken over the references still fighting at each second, as
    `read_pace` takes it, so the time lag and the share read one curve. An
    amount of zero or less is reached at the pull.
    """
    reached_at: float | None = 0.0 if amount <= 0 else None
    previous = 0.0
    band_end = 0
    second = 1
    while True:
        fighting = [one for one in references if second <= one.duration_seconds]
        if len(fighting) < MIN_SAMPLE_FOR_AGGREGATE:
            break
        current = median(cumulative_at(one.damage, second) for one in fighting)
        if reached_at is None and current >= amount:
            reached_at = second - 1 + (amount - previous) / (current - previous)
        previous = current
        band_end = second
        second += 1
    return PaceLag(reached_at=reached_at, band_end=band_end)
```

- [ ] **Step 4: Run, pass, prove**

Run the file: all pass (these tests were run against this code before the plan was committed, 2026-09-28). Prove, restoring after each:
- use `mean` instead of `median` for `current` -> the median-not-mean test red;
- drop the interpolation (`reached_at = float(second)`) -> the interpolation test red;
- change the band test to `< 1` instead of `< MIN_SAMPLE_FOR_AGGREGATE` -> the band-end and fewer-than-three tests red.

- [ ] **Step 5: Gate and commit**

Full gate. Subject: `Split a pace reference by player and read a time lag off the median`

---

### Task 2: The per-player findings

**Files:**
- Modify: `src/wowperf/domain/comparison/pace.py` (`PaceSample.our_players`; `_clock` and `_share` become the shared `clock_text` and `share_of`)
- Create: `src/wowperf/domain/comparison/pace_player.py`
- Test: `tests/domain/comparison/test_pace_player.py` (create)

**Interfaces:**
- Consumes: Task 1's `PlayerSeries`, `PaceReference.players`, `lag_against`; slice 1's `read_pace`, `cumulative_at`, `final_behind_start`, `earlier_behind`, `PaceState`; `return_of`, `RESURRECTED`, `SELF_RESURRECTED` from `wowperf.domain.analysis.recap`; `ParseSubject` from `wowperf.domain.comparison.parse_axis`; `Roles`, `SelfResurrections` from `wowperf.domain.season`.
- Produces: `PaceSample.our_players: tuple[PlayerSeries, ...] = ()`; `clock_text(seconds: float) -> str`, `share_of(value: float, of: float) -> int` in `pace.py`; in `pace_player.py`: `PLAYER_PACE_PREFIX = "compare.pace.player."`, `PLAYER_UNAVAILABLE_PREFIX = "compare.pace.player.unavailable"`, `COMPARED_ROLES`, `SCOPE_LINE`, `NO_SPEC_TITLE`, `pair_label(class_name, spec, *, plural=True) -> str`, `Window`, `window_of(loaded, actor_id, self_resurrections) -> Window`, `analyse_player_pace(loaded: LoadedEncounter, sample: PaceSample, subjects: Sequence[ParseSubject], roles: Roles, self_resurrections: SelfResurrections) -> list[Finding]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/comparison/test_pace_player.py`:

```python
# ABOUTME: Each player's boss damage against the kills' players of the same class and spec.
# ABOUTME: Pins the titles, the time lag, the window's three ends, and every withhold.

import re

from tests.domain.comparison.test_pace_curve import steady
from tests.domain.report.test_raid_frame import an_encounter
from wowperf.domain.comparison.pace import NO_REFERENCE_KILL, PaceSample
from wowperf.domain.comparison.pace_curve import PaceReference, PlayerSeries
from wowperf.domain.comparison.pace_player import (
    NO_SPEC_TITLE,
    PLAYER_PACE_PREFIX,
    PLAYER_UNAVAILABLE_PREFIX,
    analyse_player_pace,
    pair_label,
)
from wowperf.domain.comparison.parse_axis import ParseSubject
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death, Resurrection
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.season import Roles, SelfResurrections

ROLES = Roles(tanks=("DeathKnight/Blood",), healers=("Priest/Holy",))
NO_SELF_RESURRECTIONS = SelfResurrections()

FROST = Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Frost", item_level=700)
BLOOD = Player(
    actor_id=2, name="Stonewake", class_name="DeathKnight", spec="Blood", item_level=700
)
HOLY = Player(actor_id=3, name="Bríala", class_name="Priest", spec="Holy", item_level=700)
UNNAMED = Player(actor_id=4, name="Кириллица", class_name="Mage", spec="", item_level=700)
AFFLICTION = Player(
    actor_id=5, name="Briala", class_name="Warlock", spec="Affliction", item_level=700
)
ROSTER = (FROST, BLOOD, HOLY, UNNAMED, AFFLICTION)


def subject(player: Player) -> ParseSubject:
    return ParseSubject(player=player, slug=f"p{player.actor_id}", display_name=player.name)


def a_peer(class_name: str, spec: str, per_second: int, **fields: float) -> PlayerSeries:
    return PlayerSeries(
        actor_id=90, class_name=class_name, spec=spec, damage=steady(per_second, 400), **fields
    )


def a_reference_kill(*players: PlayerSeries) -> PaceReference:
    return PaceReference(duration_seconds=400.0, damage=steady(1000, 400), players=players)


THREE_KILLS = (
    a_reference_kill(a_peer("Mage", "Frost", 90), a_peer("DeathKnight", "Blood", 50)),
    a_reference_kill(a_peer("Mage", "Frost", 100), a_peer("DeathKnight", "Blood", 50)),
    a_reference_kill(a_peer("Mage", "Frost", 110)),
)


def a_wipe(seconds: int = 200, **fields: object) -> LoadedEncounter:
    encounter = an_encounter(
        kill=False, start_ms=0, end_ms=seconds * 1000, fight_percentage=40.0, players=ROSTER
    )
    return LoadedEncounter(encounter=encounter, **fields)  # type: ignore[arg-type]


def a_sample(frost_per_second: int = 80, seconds: int = 200) -> PaceSample:
    ours = (PlayerSeries(actor_id=1, class_name="Mage", spec="Frost",
                         damage=steady(frost_per_second, seconds)),)
    return PaceSample(ours=steady(1000, seconds), references=THREE_KILLS, our_players=ours)


def analysed(
    loaded: LoadedEncounter | None = None,
    sample: PaceSample | None = None,
    players: tuple[Player, ...] = (FROST,),
) -> dict[str, Finding]:
    found = analyse_player_pace(
        loaded or a_wipe(),
        sample or a_sample(),
        tuple(subject(one) for one in players),
        ROLES,
        NO_SELF_RESURRECTIONS,
    )
    return {finding.id: finding for finding in found}


FROST_ID = f"{PLAYER_PACE_PREFIX}p1"


def test_the_pair_is_named_by_spec_then_class_split_at_its_capitals() -> None:
    assert pair_label("Mage", "Frost") == "Frost Mages"
    assert pair_label("DeathKnight", "Blood") == "Blood Death Knights"
    assert pair_label("DemonHunter", "Havoc", plural=False) == "Havoc Demon Hunter"


def test_a_player_behind_their_spec_gets_the_share_and_the_lag() -> None:
    """Peers at 90, 100 and 110 a second; ours at 80. By 200 s the median had 20000 and
    we had 16000, which the median reached at 160 s: forty seconds behind."""
    finding = analysed()[FROST_ID]
    assert finding.title == "Behind the kills' Frost Mages: 80% of their median boss damage by 3:20"
    assert finding.confidence is Confidence.DERIVED
    assert finding.player_slug == "p1"
    assert finding.evidence == (
        "Against 3 Frost Mages across 3 reference kills of this raid size",
        "Their range at 3:20: 90% to 110% of their median",
        "By 3:20 they had dealt what the kills' Frost Mages had dealt by 2:40: 40 seconds behind",
        "Compared through the wipe at 3:20",
        "Behind from 0:01 to 3:20",
    )
    assert "assigned to adds" in finding.detail


def test_ahead_reads_the_lag_as_seconds_ahead() -> None:
    """26000 by 200 s, which the median reached at 260 s."""
    finding = analysed(sample=a_sample(130))[FROST_ID]
    assert finding.title.startswith("Ahead of the kills' Frost Mages: 130% ")
    assert (
        "By 3:20 they had dealt what the kills' Frost Mages had dealt by 4:20: 60 seconds ahead"
        in finding.evidence
    )
    assert not any(line.startswith("Behind from") for line in finding.evidence)


def test_level_with_the_median_says_so_without_a_figure() -> None:
    finding = analysed(sample=a_sample(100))[FROST_ID]
    assert finding.title.startswith("On the kills' Frost Mages' pace: 100% ")
    assert (
        "By 3:20 they had dealt what the kills' Frost Mages had dealt by then" in finding.evidence
    )


def test_past_everything_the_median_reached_there_is_no_lag_figure() -> None:
    """60000 by 200 s; the median tops out at 40000 when the kills end at 400 s."""
    finding = analysed(sample=a_sample(300))[FROST_ID]
    assert (
        "More than the kills' median had dealt by 6:40, where fewer than three Frost Mages "
        "were still fighting"
    ) in finding.evidence


def test_a_death_nobody_answered_ends_the_comparison() -> None:
    death = Death(player_name="Emberkin", actor_id=1, timestamp_ms=125_000, killing_blow="Crush")
    finding = analysed(loaded=a_wipe(deaths=(death,)))[FROST_ID]
    assert finding.title.endswith("by 2:05")
    assert "Compared through their death at 2:05" in finding.evidence


def test_a_release_ends_the_comparison_at_the_death() -> None:
    death = Death(player_name="Emberkin", actor_id=1, timestamp_ms=50_000, killing_blow="Crush",
                  seconds_until_next_action=10.0)
    finding = analysed(loaded=a_wipe(deaths=(death,)))[FROST_ID]
    assert "Compared through their death at 0:50" in finding.evidence


def test_a_battle_resurrection_keeps_the_comparison_running_and_names_the_stretch() -> None:
    death = Death(player_name="Emberkin", actor_id=1, timestamp_ms=50_000, killing_blow="Crush",
                  seconds_until_next_action=35.0)
    rez = Resurrection(actor_id=1, caster_id=2, ability_id=20484, ability_name="Rebirth",
                       timestamp_ms=80_000)
    finding = analysed(loaded=a_wipe(deaths=(death,), resurrections=(rez,)))[FROST_ID]
    assert "Compared through the wipe at 3:20" in finding.evidence
    assert "Dead from 0:50 to 1:20, then resurrected" in finding.evidence


def test_a_reference_players_own_death_cuts_the_band() -> None:
    kills = (
        a_reference_kill(a_peer("Mage", "Frost", 90, until_seconds=100.0)),
        a_reference_kill(a_peer("Mage", "Frost", 100)),
        a_reference_kill(a_peer("Mage", "Frost", 110)),
    )
    finding = analysed(sample=a_sample().model_copy(update={"references": kills}))[FROST_ID]
    assert finding.title.endswith("by 1:40")
    assert (
        "Compared through 1:40, after which fewer than three Frost Mages were still fighting"
        in finding.evidence
    )


def test_a_player_the_graph_never_saw_dealt_nothing_and_has_no_lag() -> None:
    finding = analysed(sample=a_sample().model_copy(update={"our_players": ()}))[FROST_ID]
    assert finding.title.startswith("Behind the kills' Frost Mages: 0% ")
    assert not any(line.startswith("By ") for line in finding.evidence)


def test_a_tank_is_compared_and_below_three_peers_is_withheld_with_the_count() -> None:
    notice = analysed(players=(BLOOD,))[f"{PLAYER_UNAVAILABLE_PREFIX}.p2"]
    assert notice.title == (
        "Only 2 Blood Death Knights in the reference kills: fewer than three to compare against"
    )
    assert notice.confidence is Confidence.MEASURED
    assert notice.player_slug == "p2"


def test_no_peer_at_all_is_withheld_in_the_singular() -> None:
    notice = analysed(players=(AFFLICTION,))[f"{PLAYER_UNAVAILABLE_PREFIX}.p5"]
    assert notice.title == (
        "No Affliction Warlock in the reference kills: fewer than three to compare against"
    )


def test_a_healer_is_not_compared() -> None:
    assert analysed(players=(HOLY,)) == {}


def test_an_unnamed_specialisation_is_withheld_and_says_so() -> None:
    notice = analysed(players=(UNNAMED,))[f"{PLAYER_UNAVAILABLE_PREFIX}.p4"]
    assert notice.title == NO_SPEC_TITLE


def test_a_kill_is_never_compared() -> None:
    loaded = LoadedEncounter(encounter=an_encounter(kill=True, players=ROSTER))
    assert analysed(loaded=loaded) == {}


def test_nothing_is_said_per_player_when_the_raid_wide_comparison_was_withheld() -> None:
    assert analysed(sample=PaceSample(unavailable=NO_REFERENCE_KILL)) == {}


def test_no_finding_prints_a_raw_damage_figure() -> None:
    for finding in analysed(players=ROSTER).values():
        for text in (finding.title, finding.detail, *finding.evidence):
            assert not re.search(r"\d{4,}", text), text


def test_a_spec_name_two_classes_share_is_not_pooled() -> None:
    """Frost is a Mage spec and a Death Knight spec: three Frost Death Knights are no peers."""
    kills = tuple(a_reference_kill(a_peer("DeathKnight", "Frost", 100)) for _ in range(3))
    sample = a_sample().model_copy(update={"references": kills})
    notice = analysed(sample=sample)[f"{PLAYER_UNAVAILABLE_PREFIX}.p1"]
    assert notice.title == (
        "No Frost Mage in the reference kills: fewer than three to compare against"
    )
```

The expected strings were worked by hand in each docstring and then run against this task's code before the plan was committed (2026-09-28, 18 of 18 green). If one disagrees now, the code was transcribed differently: diff against the plan before changing a test.

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/comparison/test_pace_player.py -v`
Expected: FAIL at import -- `No module named 'wowperf.domain.comparison.pace_player'`.

- [ ] **Step 3: Share the clock and the share**

In `pace.py`, rename `_clock` to `clock_text` and `_share` to `share_of` at the definitions and at every call site in the file (nothing outside `pace.py` calls them today; `grep -rn "_clock\|_share(" src tests` to confirm). Give each a one-line docstring, add `PlayerSeries` to the `pace_curve` import, and give `PaceSample` its new field -- the class becomes:

```python
class PaceSample(Frozen):
    """What the pace comparison was given: our boss damage and the kills', or why neither.

    `unavailable` is set exactly when nothing can be compared, and names why.
    `our_players` splits `ours` by player, for the per-player comparison.
    """

    ours: BossDamage | None = None
    references: tuple[PaceReference, ...] = ()
    unavailable: str = ""
    our_players: tuple[PlayerSeries, ...] = ()


def clock_text(seconds: float) -> str:
    """Seconds from the pull as a clock, "3:20"; shared with the per-player findings."""
    whole = int(round(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def share_of(value: float, of: float) -> int:
    """`value` as a whole percentage of `of`; shared with the per-player findings."""
    return round(100 * value / of)
```

- [ ] **Step 4: Write the module**

Create `src/wowperf/domain/comparison/pace_player.py`:

```python
# ABOUTME: Each wiped player's boss damage against the kills' players of the same class and spec.
# ABOUTME: One finding or one notice per compared damage dealer or tank, read from pace_curve.

import re
from collections.abc import Sequence

from wowperf.domain.analysis.recap import RESURRECTED, SELF_RESURRECTED, return_of
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace import PaceSample, clock_text, share_of
from wowperf.domain.comparison.pace_curve import (
    BossDamage,
    PaceReading,
    PaceReference,
    PaceState,
    cumulative_at,
    earlier_behind,
    final_behind_start,
    lag_against,
    read_pace,
)
from wowperf.domain.comparison.parse_axis import ParseSubject
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.season import Roles, SelfResurrections

PLAYER_PACE_PREFIX = "compare.pace.player."
PLAYER_UNAVAILABLE_PREFIX = "compare.pace.player.unavailable"

COMPARED_ROLES = frozenset({"damage", "tank"})

PLAYER_DETAIL = (
    "Cumulative damage to the boss, second by second from the pull, against the reference "
    "kills' players of the same class and specialisation over the same seconds, both sides "
    "read from the same boss-only damage graph. Damage to the boss only: a player assigned "
    "to adds, or a tank who held adds, reads behind for that assignment, not for their play."
)
FEWER_THAN_THREE_DETAIL = (
    "Damage pace per player needs three or more players of the same class and specialisation "
    "across the reference kills: against fewer, it would mostly measure what those raids "
    "assigned them."
)
NO_SPEC_TITLE = "This report does not name their specialisation"
NO_SPEC_DETAIL = (
    "Damage pace per player compares players of the same class and specialisation, and this "
    "report leaves this player's specialisation unnamed."
)
NOTHING_TO_COMPARE_DETAIL = (
    "The reference players of this class and specialisation had dealt the boss no damage by "
    "the last second compared."
)
SCOPE_LINE = "Damage pace per player compares damage dealers and tanks only."


def pair_label(class_name: str, spec: str, *, plural: bool = True) -> str:
    """ "Frost Mages", "Blood Death Knights": the spec, then the class split at its capitals."""
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", class_name)
    return f"{spec} {words}{'s' if plural else ''}"


class Window(Frozen):
    """Where one player's comparison ends, and every stretch they spent dead before it.

    `end_seconds` counts from the pull. `by_death` says a death no resurrection
    answered ended it, rather than the wipe. `dead` holds (died, back) pairs,
    in seconds from the pull, for every death that was answered.
    """

    end_seconds: float
    by_death: bool
    dead: tuple[tuple[float, float], ...] = ()


def window_of(
    loaded: LoadedEncounter, actor_id: int, self_resurrections: SelfResurrections
) -> Window:
    """From the pull to the first death no resurrection answered, or to the wipe.

    `return_of` decides, as it does for the death recaps, so "brought back"
    means one thing on the whole page. A release ends the window: on a wipe
    it is the end of the attempt for that player.
    """
    start_ms = loaded.encounter.start_ms
    dead: list[tuple[float, float]] = []
    deaths = sorted(
        (death for death in loaded.deaths if death.actor_id == actor_id),
        key=lambda death: death.timestamp_ms,
    )
    for death in deaths:
        died_at = (death.timestamp_ms - start_ms) / 1000
        came_back = return_of(loaded.resurrections, loaded.casts, death, self_resurrections)
        if came_back.kind in (RESURRECTED, SELF_RESURRECTED):
            if came_back.seconds_after is not None:
                dead.append((died_at, died_at + came_back.seconds_after))
            continue
        return Window(end_seconds=died_at, by_death=True, dead=tuple(dead))
    return Window(
        end_seconds=loaded.encounter.duration_seconds, by_death=False, dead=tuple(dead)
    )


def analyse_player_pace(
    loaded: LoadedEncounter,
    sample: PaceSample,
    subjects: Sequence[ParseSubject],
    roles: Roles,
    self_resurrections: SelfResurrections,
) -> list[Finding]:
    """`compare.pace.player.<slug>` or its notice, for each damage dealer and tank asked for.

    Nothing on a kill, and nothing when the raid-wide comparison was itself
    withheld: its notice in Provenance already says why, for everyone. A
    healer is not compared. A player dead before the first second has no
    reading and no line.
    """
    if loaded.encounter.kill or sample.unavailable or not sample.references:
        return []
    ours_by_actor = {one.actor_id: one.damage for one in sample.our_players}

    findings: list[Finding] = []
    for subject in subjects:
        player = subject.player
        if roles.role_of(player.class_name, player.spec) not in COMPARED_ROLES:
            continue
        if not player.spec:
            findings.append(_notice(subject.slug, NO_SPEC_TITLE, NO_SPEC_DETAIL))
            continue
        window = window_of(loaded, player.actor_id, self_resurrections)
        if window.end_seconds < 1:
            continue
        peers, kills = _peers(sample, player)
        if len(peers) < MIN_SAMPLE_FOR_AGGREGATE:
            findings.append(
                _notice(subject.slug, _too_few_title(len(peers), player), FEWER_THAN_THREE_DETAIL)
            )
            continue
        ours = ours_by_actor.get(player.actor_id, BossDamage(interval_ms=1000.0))
        reading = read_pace(ours, peers, window.end_seconds)
        if reading is None or not reading.seconds or reading.seconds[-1].median <= 0:
            label = pair_label(player.class_name, player.spec)
            findings.append(
                _notice(
                    subject.slug,
                    f"No second of this attempt could be compared against the kills' {label}",
                    NOTHING_TO_COMPARE_DETAIL,
                )
            )
            continue
        findings.append(_finding(subject.slug, player, reading, ours, peers, kills, window))
    return findings


def _peers(sample: PaceSample, player: Player) -> tuple[tuple[PaceReference, ...], int]:
    """Every reference player of the same class and spec, each over their own part of the kill."""
    peers: list[PaceReference] = []
    kills = 0
    for kill in sample.references:
        matching = [
            one
            for one in kill.players
            if (one.class_name, one.spec) == (player.class_name, player.spec)
        ]
        if matching:
            kills += 1
        for one in matching:
            until = kill.duration_seconds
            if one.until_seconds is not None:
                until = min(until, one.until_seconds)
            peers.append(PaceReference(duration_seconds=until, damage=one.damage))
    return tuple(peers), kills


def _too_few_title(count: int, player: Player) -> str:
    one = pair_label(player.class_name, player.spec, plural=False)
    many = pair_label(player.class_name, player.spec)
    if count == 0:
        return f"No {one} in the reference kills: fewer than three to compare against"
    return (
        f"Only {count} {one if count == 1 else many} in the reference kills: "
        "fewer than three to compare against"
    )


def _notice(slug: str, title: str, detail: str) -> Finding:
    return Finding(
        id=f"{PLAYER_UNAVAILABLE_PREFIX}.{slug}",
        title=title,
        detail=detail,
        confidence=Confidence.MEASURED,
        player_slug=slug,
    )


def _lag_line(label: str, second: int, amount: float, peers: tuple[PaceReference, ...]) -> str:
    lag = lag_against(amount, peers)
    if lag.reached_at is None:
        return (
            f"More than the kills' median had dealt by {clock_text(lag.band_end)}, where fewer "
            f"than three {label} were still fighting"
        )
    gap = round(second - lag.reached_at)
    if gap == 0:
        return f"By {clock_text(second)} they had dealt what the kills' {label} had dealt by then"
    seconds = f"{abs(gap)} second{'s' if abs(gap) != 1 else ''}"
    return (
        f"By {clock_text(second)} they had dealt what the kills' {label} had dealt by "
        f"{clock_text(lag.reached_at)}: {seconds} {'behind' if gap > 0 else 'ahead'}"
    )


def _finding(
    slug: str,
    player: Player,
    reading: PaceReading,
    ours: BossDamage,
    peers: tuple[PaceReference, ...],
    kills: int,
    window: Window,
) -> Finding:
    label = pair_label(player.class_name, player.spec)
    last = reading.seconds[-1]
    clock = clock_text(last.second)
    lead = {
        PaceState.BEHIND: f"Behind the kills' {label}",
        PaceState.ON_PACE: f"On the kills' {label}' pace",
        PaceState.AHEAD: f"Ahead of the kills' {label}",
    }[last.state]

    evidence = [
        f"Against {len(peers)} {label} across {kills} reference kill{'s' if kills != 1 else ''} "
        "of this raid size",
        f"Their range at {clock}: {share_of(last.low, last.median)}% to "
        f"{share_of(last.high, last.median)}% of their median",
    ]
    dealt = cumulative_at(ours, last.second)
    if dealt > 0:
        evidence.append(_lag_line(label, last.second, dealt, peers))
    if reading.band_cut:
        evidence.append(
            f"Compared through {clock}, after which fewer than three {label} were still fighting"
        )
    elif window.by_death:
        evidence.append(f"Compared through their death at {clock}")
    else:
        evidence.append(f"Compared through the wipe at {clock}")
    evidence.extend(
        f"Dead from {clock_text(died)} to {clock_text(back)}, then resurrected"
        for died, back in window.dead
    )
    start = final_behind_start(reading)
    if start is not None:
        evidence.append(f"Behind from {clock_text(start)} to {clock}")
        evidence.extend(
            f"Also behind between {clock_text(first)} and {clock_text(end)}"
            for first, end in earlier_behind(reading)
        )

    return Finding(
        id=f"{PLAYER_PACE_PREFIX}{slug}",
        title=f"{lead}: {share_of(last.ours, last.median)}% of their median boss damage by {clock}",
        detail=PLAYER_DETAIL,
        confidence=Confidence.DERIVED,
        evidence=tuple(evidence),
        player_slug=slug,
    )
```

- [ ] **Step 5: Run, pass, prove**

Run the file: all pass. Prove, restoring after each:
- drop the `COMPARED_ROLES` check -> the healer test red;
- treat every `return_of` kind as ending the window -> the battle-resurrection test red;
- treat `RELEASED` as coming back -> the release test red;
- ignore `until_seconds` in `_peers` -> the reference-death test red;
- pool by spec alone, not `(class_name, spec)` -> the shared-spec-name test red (three Frost Death Knights become a Frost Mage's peers);
- drop the `dealt > 0` guard -> the never-seen player test red.

- [ ] **Step 6: Gate and commit**

Full gate (`test_pace.py` still green after the rename). Subject: `Say how far each wiped player trailed their spec in the kills`

---

### Task 3: Read the reference rosters and split the graphs by player

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py` (`REFERENCE_FIGHT_QUERY`)
- Modify: `src/wowperf/adapters/wcl/ingest.py` (`ReferenceFight.roster`, `RosterEntry`, `build_reference_fight`, `build_player_boss_damage`, `build_first_deaths`)
- Modify: `src/wowperf/adapters/wcl/pace.py` (`load_pace_sample`)
- Test: `tests/adapters/wcl/test_pace.py`

**Interfaces:**
- Consumes: Task 1's `PlayerSeries`, `PaceReference.players`; Task 2's `PaceSample.our_players`.
- Produces: `RosterEntry(actor_id: int, class_name: str, spec: str)`; `ReferenceFight.roster: tuple[RosterEntry, ...] = ()`; `build_player_boss_damage(payload, *, fight_start_ms: int) -> dict[int, BossDamage]`; `build_first_deaths(events: list[dict[str, Any]], actor_ids: frozenset[int], *, fight_start_ms: int) -> dict[int, float]`; `load_pace_sample` unchanged in signature, now filling `PaceReference.players` and `PaceSample.our_players`.

Read `.claude/skills/wcl-api/SKILL.md` first: "A reference kill's roster costs one point more, read in the same lookup" (2026-09-28) and the `friendlySpecs` / `playerDetails` / roster sections. Read `load_pace_sample`, `build_boss_damage`, `build_reference_fight`, `_reference_int` and `build_deaths` (for the death-event keys) whole before editing.

- [ ] **Step 1: The query**

`REFERENCE_FIGHT_QUERY` becomes:

```python
REFERENCE_FIGHT_QUERY = """
query ReferenceFight($code: String!, $fightId: Int!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      fights(fightIDs: [$fightId]) {
        id
        startTime
        endTime
        enemyNPCs { id gameID }
        friendlyPlayers
        friendlySpecs
      }
      masterData(translate: true) {
        actors(type: "Player") { id subType }
      }
    }
  }
}
"""
```

Extend its comment: the roster rides in this lookup for the per-player comparison, priced 2.00 points against 1.00 without it (wcl-api skill, 2026-09-28); `friendlySpecs` names the spec only, so the class comes from the player actors' `subType`, which span the whole report and are a lookup, never the roster. If `tests/adapters/wcl/test_queries.py` pins query text or fields, extend it; read it first.

- [ ] **Step 2: The builders, test first**

In `tests/adapters/wcl/test_pace.py`, beside the existing builder tests:

```python
def test_a_reference_fight_carries_its_roster_by_class_and_spec() -> None:
    payload = {"reportData": {"report": {
        "fights": [{"id": 12, "startTime": 1000, "endTime": 481000,
                    "enemyNPCs": [{"id": 31, "gameID": 900}],
                    "friendlyPlayers": [5, 6, 7, 8],
                    "friendlySpecs": ["Frost", "Blood", None, "Frost"]}],
        "masterData": {"actors": [
            {"id": 5, "subType": "Mage"}, {"id": 6, "subType": "DeathKnight"},
            {"id": 7, "subType": "Priest"}, {"id": 99, "subType": "Rogue"},
        ]},
    }}}
    fight = build_reference_fight(payload)
    assert fight is not None
    # 7 has no spec and 8 no class: neither is pooled, rather than guessed at.
    assert fight.roster == (
        RosterEntry(actor_id=5, class_name="Mage", spec="Frost"),
        RosterEntry(actor_id=6, class_name="DeathKnight", spec="Blood"),
    )


def test_a_reference_fight_without_roster_fields_has_an_empty_roster() -> None:
    payload = {"reportData": {"report": {"fights": [
        {"id": 12, "startTime": 1000, "endTime": 481000, "enemyNPCs": []},
    ]}}}
    fight = build_reference_fight(payload)
    assert fight is not None and fight.roster == ()


def test_every_player_series_becomes_boss_damage_and_total_is_left_out() -> None:
    payload = {"reportData": {"report": {"graph": {"data": {"series": [
        {"id": 7, "pointStart": 5000, "pointInterval": 2000.0, "data": [10.0, 20.0]},
        {"id": 8, "pointStart": 5000, "pointInterval": 2000.0, "data": [5.0]},
        {"id": "Total", "pointStart": 5000, "pointInterval": 2000.0, "data": [15.0, 20.0]},
    ]}}}}}
    assert build_player_boss_damage(payload, fight_start_ms=5000) == {
        7: BossDamage(interval_ms=2000.0, amounts=(20, 40)),
        8: BossDamage(interval_ms=2000.0, amounts=(10,)),
    }


def test_the_first_death_of_each_listed_player_is_read_in_seconds_from_the_pull() -> None:
    events = [
        {"type": "death", "targetID": 5, "timestamp": 61_000},
        {"type": "death", "targetID": 5, "timestamp": 90_000},
        {"type": "death", "targetID": 42, "timestamp": 30_000},
        {"type": "cast", "targetID": 6, "timestamp": 20_000},
    ]
    assert build_first_deaths(events, frozenset({5, 6}), fight_start_ms=1_000) == {5: 60.0}
```

Then in `ingest.py`:
- `RosterEntry(Frozen)` with `actor_id: int`, `class_name: str`, `spec: str`, and `ReferenceFight.roster: tuple[RosterEntry, ...] = ()`, both beside `ReferenceFight`. `build_reference_fight` pairs `friendlyPlayers[i]` with `friendlySpecs[i]` (index-aligned, as `_build_players` reads them), takes the class from `masterData.actors` by id, and **skips** an entry whose spec is null or missing, or whose id names no player actor -- a player not pooled rather than a guess. Ids go through `_reference_int`. Absent `friendlyPlayers` reads as an empty roster. Docstring says why the actors are a lookup and never the roster.
- `build_player_boss_damage(payload, *, fight_start_ms)`: every series whose `id` is an `int` (and not a `bool`), converted exactly as `build_boss_damage` converts `Total`. Extract the conversion both share into one private helper (`_boss_damage_row(row, fight_start_ms) -> BossDamage | None`) so the rate conversion lives once; a row with a non-positive interval is skipped. Update `build_boss_damage`'s docstring: the per-player rows are read by `build_player_boss_damage` now, not "left for slice 2".
- `build_first_deaths(events, actor_ids, *, fight_start_ms)`: the first `type == "death"` event per `targetID` in `actor_ids`, as `(timestamp - fight_start_ms) / 1000` -- the keys `build_deaths` reads.

Prove each red once (drop the null-spec skip; let `Total` through; take the last death, not the first).

- [ ] **Step 3: The loader, test first**

`load_pace_sample` changes, in order:
1. After our boss graph: `our_series = build_player_boss_damage(graph_payload, fight_start_ms=encounter.start_ms)`; `our_players = tuple(PlayerSeries(actor_id=p.actor_id, class_name=p.class_name, spec=p.spec, damage=our_series[p.actor_id]) for p in encounter.players if p.actor_id in our_series)`.
2. Per loaded reference, after its graph: `series = build_player_boss_damage(damage_payload, fight_start_ms=fight.start_ms)`; when `row.deaths > 0`, read that fight's death events with `fetch_all_events` (`src/wowperf/adapters/wcl/pagination.py`) and `DEATHS_QUERY` through `reference_cache` -- read how `repository.py` calls `fetch_all_events` with a cache and follow it -- over the fight's own `start_ms`/`end_ms`, then `deaths = build_first_deaths(events, frozenset(entry.actor_id for entry in fight.roster), fight_start_ms=fight.start_ms)`, else `{}`; `players = tuple(PlayerSeries(actor_id=e.actor_id, class_name=e.class_name, spec=e.spec, damage=series[e.actor_id], until_seconds=deaths.get(e.actor_id)) for e in fight.roster if e.actor_id in series)`; `PaceReference(..., players=players)`. A roster entry with no series is left out; a series with no roster entry is never read.
3. Return `PaceSample(ours=ours, references=..., our_players=our_players)`; on the no-member path keep `our_players` too.
4. Docstring: the roster and the per-player split, the deaths read only for a kill that lost someone, and that none of it is written anywhere.

Tests in `tests/adapters/wcl/test_pace.py`, with the file's existing MockTransport handler style (route on operation name; the `ReferenceFight` payload now carries `friendlyPlayers`, `friendlySpecs` and `masterData.actors`):
- three references loaded -> each `PaceReference.players` holds its roster's series with class and spec; `our_players` holds our encounter's players that the graph has, by actor id;
- a reference row with `deaths=0` -> no `Deaths` request (count by operation name); a row with `deaths=1` -> one `Deaths` request, through the reference cache, and the dying player's `until_seconds` set;
- a roster entry absent from the graph is left out; a graph series absent from the roster is not read.

Prove red: skip the `row.deaths > 0` guard (the no-request test); swap the deaths request onto `own_cache` (assert the reference cache directory gained the file); drop `until_seconds`.

- [ ] **Step 4: Gate and commit**

Full gate. Subject: `Read each reference kill's roster and split its boss graph by player`

---

### Task 4: On the player's card

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`PlayerCard.pace_rows`)
- Modify: `src/wowperf/domain/report/raid_players.py` (`build_raid_players`)
- Modify: `src/wowperf/domain/report/raid_build.py` (keep player pace off the tab rows; the Provenance line)
- Modify: `src/wowperf/domain/report/raid_model.py` (`all_raid_ledger_rows` walks `pace_rows`)
- Modify: `src/wowperf/adapters/render/_players.html.j2`
- Test: `tests/domain/report/test_raid_build.py`, `tests/domain/report/test_raid_ledger.py` if it enumerates card fields, `tests/adapters/render/test_raid_html_invariants.py`

**Interfaces:**
- Consumes: Task 2's `PLAYER_PACE_PREFIX`, `SCOPE_LINE`, `analyse_player_pace`.
- Produces: `PlayerCard.pace_rows: tuple[LedgerRow, ...] = ()`.

Read `build_raid_report`, `build_raid_players`, `all_raid_ledger_rows`, `place_rows` and `_players.html.j2` whole before editing.

- [ ] **Step 1: The card, test first**

1. `PlayerCard.pace_rows: tuple[LedgerRow, ...] = ()` beside `spell_and_talent_rows`, docstring: the per-player damage pace finding or its notice, raid wipes only; empty everywhere else, so the Mythic+ and night cards are unchanged.
2. `build_raid_players` fills it with `ledger_row(finding, titles_by_id, tooltips)` for every untimed finding whose id starts with `PLAYER_PACE_PREFIX` and whose `player_slug` is the card's slug.
3. `build_raid_report`: `RAID_PLACEMENTS`' `("compare.pace.", "damage_rows")` would also take `compare.pace.player.*` (first prefix wins), so the findings handed to `place_rows` leave out every id starting with `PLAYER_PACE_PREFIX`; the card builder still receives all findings. Comment why, in the style of the strip blocks beside it. When any finding id starts with `PLAYER_PACE_PREFIX`, add `SCOPE_LINE` once to Provenance's `withheld` lines, beside the "Damage pace against other kills" line.
4. `all_raid_ledger_rows` walks each card's `pace_rows` too, and its docstring says so -- so the page-wide "every finding placed exactly once" checks see them.

Tests in `tests/domain/report/test_raid_build.py`, with its `a_raid_fixture(kill=False, ...)` and findings from `analyse_player_pace` on a sample built with Task 1 and 2's helpers (never hand-typed pace findings): the player's card carries the `compare.pace.player.<slug>` row; no `damage_rows` row starts with `PLAYER_PACE_PREFIX`; a notice lands on its player's card; `SCOPE_LINE` appears exactly once in Provenance when a player finding exists and not at all when none does; the `placements(report)` helper (extend it to walk `pace_rows`) places each pace finding exactly once. Prove red: hand `place_rows` every finding (the Damage-tab test goes red); skip the slug match (a row lands on the wrong card).

- [ ] **Step 2: The template**

In `_players.html.j2`, after the `spell_and_talent_rows` block and in its style:

```jinja
  {% if player.pace_rows %}
  <h4>Damage pace against the kills</h4>
  {% for row in player.pace_rows %}
  {{ ledger_row(row) }}
  {% endfor %}
  {% endif %}
```

Read the file first: use the macro and heading level the `spell_and_talent_rows` block uses, not the ones written here if they differ.

- [ ] **Step 3: Render tests and goldens**

In `tests/adapters/render/test_raid_html_invariants.py`: a wipe page whose findings include a player's pace finding shows its title inside that player's card and nowhere on the Damage tab; a withheld player's card shows the notice's title; the page carries no `>None<`; a kill page shows no "Damage pace against the kills" heading. Every golden must stay byte-identical (the raid golden is a kill; `pace_rows` defaults to empty and the block is guarded) -- run the golden tests; if one moves, stop and report.

- [ ] **Step 4: Gate and commit**

Full gate. Subject: `Put each wiped player's pace on their card, off the Damage tab`

---

### Task 5: Wire the raid command

**Files:**
- Modify: `src/wowperf/domain/analysis/encounter_service.py` (`analyse_encounter`)
- Modify: `src/wowperf/cli.py` (the `raid` command)
- Test: `tests/domain/analysis/test_encounter_service.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 2's `analyse_player_pace`; Task 3's loader; Task 4's card.

- [ ] **Step 1: The service, test first**

`analyse_encounter` gains `self_resurrections: SelfResurrections = SelfResurrections()` (keyword, after `pace`). Where it runs `analyse_pace`, it also runs `analyse_player_pace(loaded, pace, parse_subjects, roles, self_resurrections)` and adds its findings. Docstring: one sentence on the per-player half and why it reads `parse_subjects`. Test in `tests/domain/analysis/test_encounter_service.py` (its `a_loaded_encounter` is a kill -- override `encounter` with a wipe): a wipe with a sample whose references carry three same-pair peers and a `ParseSubject` carries `compare.pace.player.<slug>`; the same call with `pace=None` carries none. Prove red by not calling it.

- [ ] **Step 2: The command, test first**

In `cli.py`'s `raid` command: load the self-resurrection list once (`self_resurrections = load_self_resurrections()` beside `roles = load_roles()`) and pass that one value both to `analyse_encounter` and to `build_raid_report`, which today loads its own inline (`self_resurrections=load_self_resurrections()` in the `build_raid_report(...)` call) -- so the recaps and the pace windows read one list. In `tests/test_cli.py`, extend the wipe fixture from slice 1's Task 5 so its `ReferenceFight` payloads carry a roster (`friendlyPlayers`, `friendlySpecs`, `masterData.actors`) matching the fixture raiders' class and spec across at least three references, and its `BossDamageGraph` payloads carry per-player series: a wipe run writes `compare.pace.player.<slug>` for the analysed player into the findings file; a kill run and a `--no-compare` wipe write no `compare.pace.player.` finding. Prove red by dropping the call in the service.

- [ ] **Step 3: Gate and commit**

Full gate. Subject: `Compare each wiped player's pace in the raid command`

---

### Task 6: Exercise it on the real report

**Files:**
- Modify: `tests/e2e/test_raid_e2e.py`
- Modify: `docs/plans/2026-09-27-wipe-damage-pace-design.md` (status, §13.7 live)

**This task is not optional.** A new judgement is not done until a live run has exercised it, and a state that never occurs is a defect.

- [ ] **Step 1: The e2e, run once**

Read `.claude/skills/wcl-api/SKILL.md`'s rate-limit sections and slice 1's `test_a_real_wipe_is_compared_against_the_kills_pace`. Extend that test, or add one beside it on the same run, with `--all-players`: every `compare.pace.player.*` finding is `derived` with a title starting `"Behind the kills' "`, `"On the kills' "` or `"Ahead of the kills' "`, its share (regex on the title) between 0 and 400; every `compare.pace.player.unavailable.*` is `measured`; at least one `compare.pace.player.` id of either kind is present; the cost bound updated from the measured figure, with the figure and date in a comment. Reduce every check to a bool before asserting, and give each assertion a message with no title or evidence text in it. Run once: `/c/Users/damien/.local/bin/uv.exe run pytest -m e2e tests/e2e/test_raid_e2e.py -k pace -v -s`. On failure, diagnose from the output before any second run.

- [ ] **Step 2: The live distribution**

Run `/c/Users/damien/.local/bin/uv.exe run wowperf raid cW38jmwdnZfbHVL4 --fight N --all-players` for N in 28, 29, 30, 31, 32, 33, 34, one at a time, reading the points each prints; stop and report if any single run passes 150 points. Read each `out/cW38jmwdnZfbHVL4-N.findings.json` -- never the HTML -- with a scratch script (session scratchpad, not the repo) that prints **no name, no slug, no raw id of a player finding**: per fight and player index, the role where the findings file states the player's class and spec (otherwise leave it out and say so), the state, the share, the lag (seconds, or "past the band"), the window end (wipe, death, band cut), whether a resurrection stretch was named, and for notices the reason. Report how often each state occurred: behind, on pace, ahead, lag past the band, window ended by death, resurrection named, withheld below three, withheld for an unnamed spec. Also scan each rendered `out/cW38jmwdnZfbHVL4-N.html` for `>None<` and similar template leaks with the script (a leak check, not a reading of the page).

A state that never occurs is reported as open, not settled; do not go looking for another report -- RwlRwl supplies one.

- [ ] **Step 3: Amend the design**

Status line: slice 2 planned in `docs/plans/2026-09-28-wipe-pace-per-player-plan.md` and built. Under §13.7, a "Live" paragraph with the per-state counts (numbers, fight and player indices only), the e2e cost, and every state that did not occur, marked open.

- [ ] **Step 4: Gate and commit**

Offline gate. Subject: `Exercise each wiped player's pace on a real report`. Body: the points spent and the per-state counts, no names.

---

## What this plan deliberately does not build

- Slice 3 (the night page).
- A per-player projection, chart, or Summary pointer.
- Healers.
- Any change to slice 1's raid-wide findings, chart or wording, beyond the helper rename.
