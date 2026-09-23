# ABOUTME: The night load reads one report once, keeps every boss, and deepens each pull by tier.
# ABOUTME: Counting operations sent proves the read does not narrow and that no tier overpays.

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.adapters.wcl.test_load_progression_attempts import _UncachedDiskCache
from tests.adapters.wcl.test_repository import operation_name
from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import RateLimitExceeded, WclClient
from wowperf.adapters.wcl.repository import WclRunRepository


def a_fight(
    fight_id: int,
    encounter_id: int,
    difficulty: int,
    left: float,
    seconds: float,
    players: tuple[int, ...] = (),
) -> dict[str, Any]:
    start = fight_id * 1_000_000
    return {
        "id": fight_id,
        "name": "Emberkin",
        "encounterID": encounter_id,
        "difficulty": difficulty,
        "size": 20,
        "kill": False,
        "fightPercentage": left,
        "bossPercentage": left,
        "lastPhase": 2,
        "lastPhaseIsIntermission": False,
        "phaseTransitions": [{"id": 1, "startTime": float(start)}],
        "startTime": start,
        "endTime": start + int(seconds * 1000),
        "friendlyPlayers": list(players),
        "friendlySpecs": ["Fire"] * len(players),
        "friendlyItemLevels": [670] * len(players),
        "dungeonPulls": [],
    }


# Three bosses: 3492 with two qualifying attempts and one reset, 3429 with one
# qualifying attempt, 3388 with a single qualifying attempt at a different
# difficulty than the other two -- so difficulty resolution is exercised per
# boss, not just once for the whole report.
THREE_BOSS_NIGHT: dict[str, Any] = {
    "reportData": {
        "report": {
            "code": "abc123",
            "title": "Raid",
            "startTime": 0,
            "endTime": 40_000_000,
            "owner": {"name": "Emberkin"},
            "phases": [
                {
                    "encounterID": 3492,
                    "separatesWipes": True,
                    "phases": [
                        {"id": 1, "name": "Stage One", "isIntermission": False},
                    ],
                },
            ],
            "fights": [
                a_fight(28, 3492, 5, 64.81, 215.7),
                a_fight(29, 3492, 5, 85.80, 105.9),
                a_fight(35, 3492, 5, 100.0, 15.8),
                a_fight(26, 3429, 5, 51.12, 271.3),
                a_fight(41, 3388, 4, 12.30, 300.0),
            ],
            "masterData": {"actors": []},
        }
    }
}


def a_repository_counting_calls(
    tmp_path: Path, payload: dict[str, Any] = THREE_BOSS_NIGHT
) -> tuple[WclRunRepository, list[str]]:
    """One repository over a mock transport, plus the operations it sent."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        calls.append(operation_name(json.loads(request.content)))
        return httpx.Response(200, json={"data": payload})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRunRepository(client, DiskCache(tmp_path)), calls


def test_a_whole_night_costs_one_query(tmp_path: Path) -> None:
    repository, calls = a_repository_counting_calls(tmp_path)

    repository.load_night("abc123", None)

    assert calls == ["Fights"]


def test_every_boss_the_report_holds_comes_back_as_its_own_progression(
    tmp_path: Path,
) -> None:
    """The presence a naive grouping would collapse: three bosses, not one or a refusal.

    Where `load_progression` would raise ("several bosses; pass --boss"),
    `load_night` must return all three, each carrying only its own attempts.
    """
    repository, _ = a_repository_counting_calls(tmp_path)

    night = repository.load_night("abc123", None)

    assert [boss.encounter_id for boss in night.bosses] == [3492, 3429, 3388]
    by_id = {boss.encounter_id: boss for boss in night.bosses}
    assert len(by_id[3492].attempts) == 2, "fight 35 is a reset and stays discarded"
    assert [a.fight_id for a in by_id[3492].discarded] == [35]
    assert len(by_id[3429].attempts) == 1
    assert len(by_id[3388].attempts) == 1
    assert by_id[3388].difficulty == 4


def test_a_boss_absent_at_the_requested_difficulty_is_skipped_not_a_refusal(
    tmp_path: Path,
) -> None:
    """The ordinary shape of a real raid night: some bosses cleared on Heroic,
    others pushed on Mythic. `--difficulty 5` must keep the two bosses
    THREE_BOSS_NIGHT fought at 5 (3492, 3429) and quietly drop 3388, which it
    only ever fought at 4 -- not fail the whole night the way `_pick_boss`
    fails a single `--boss`/`--difficulty` mismatch for `progression`.
    """
    repository, _ = a_repository_counting_calls(tmp_path)

    night = repository.load_night("abc123", 5)

    assert [boss.encounter_id for boss in night.bosses] == [3492, 3429]
    assert all(boss.difficulty == 5 for boss in night.bosses)


def test_the_skip_does_not_leak_into_the_default_difficulty_path(tmp_path: Path) -> None:
    """With no explicit difficulty, every boss is still present.

    The skip above is conditional on `difficulty is not None`; this pins that
    the default path -- each boss taking its own first fight's difficulty --
    is untouched by it.
    """
    repository, _ = a_repository_counting_calls(tmp_path)

    night = repository.load_night("abc123", None)

    assert [boss.encounter_id for boss in night.bosses] == [3492, 3429, 3388]


def test_a_difficulty_no_boss_in_the_report_ever_fought_says_so(tmp_path: Path) -> None:
    """Skipping every boss leaves nothing -- a real mismatch, not an empty report.

    Naming both the difficulty asked for and the ones the report actually
    holds keeps a reader from being told a false cause: this report does hold
    boss fights, just none at the difficulty requested.

    Every fight is set to difficulty 7 rather than reusing one of THREE_BOSS_
    NIGHT's own difficulties (4 or 5): 7 shares no digit with any encounter id
    in this fixture (3492, 3429, 3388), so the "7 in message" assertion below
    cannot pass by coincidentally matching a boss id instead of the difficulty
    the message is actually supposed to name.
    """
    all_at_seven: dict[str, Any] = json.loads(json.dumps(THREE_BOSS_NIGHT))
    for fight in all_at_seven["reportData"]["report"]["fights"]:
        fight["difficulty"] = 7
    repository, _ = a_repository_counting_calls(tmp_path, all_at_seven)

    with pytest.raises(ValueError) as error:
        repository.load_night("abc123", 5)

    message = str(error.value)
    assert "5" in message
    assert "7" in message


def test_a_report_with_no_boss_fight_is_an_empty_night_not_an_error(tmp_path: Path) -> None:
    """A report with no boss fights at all is a different case than one where
    an explicit difficulty matches none of them (see the test above): this one
    must stay an empty `Night`, whatever `difficulty` was asked for, rather
    than tripping the "no boss fight at this difficulty" refusal.
    """
    empty: dict[str, Any] = json.loads(json.dumps(THREE_BOSS_NIGHT))
    empty["reportData"]["report"]["fights"] = []
    repository, _ = a_repository_counting_calls(tmp_path, empty)

    assert repository.load_night("abc123", None).bosses == ()
    assert repository.load_night("abc123", 5).bosses == ()


# --- Deepening the attempts -------------------------------------------------
#
# Two bosses over four fights, with a two-player roster so an aura table is a
# per-player fetch rather than a no-op: 3492 fought three times (28 and 29
# qualify, 35 is a 15.8s reset `build_progression` discards) and 3429 once.
# Fight 29 is the one named deep below, with 28 beside it under the same boss
# and 26 under another -- so a `--deep` that leaked would be caught whether it
# leaked within a boss or across the night.

ROSTER: list[dict[str, Any]] = [
    {"id": 11, "name": "Stonewake", "type": "Player", "subType": "Warrior"},
    {"id": 12, "name": "Bríala", "type": "Player", "subType": "Mage"},
]

DEEP_NIGHT: dict[str, Any] = {
    "reportData": {
        "report": {
            "code": "abc123",
            "title": "Raid",
            "startTime": 0,
            "endTime": 40_000_000,
            "owner": {"name": "Emberkin"},
            "phases": [],
            "fights": [
                a_fight(28, 3492, 5, 64.81, 215.7, (11, 12)),
                a_fight(29, 3492, 5, 85.80, 105.9, (11, 12)),
                a_fight(35, 3492, 5, 100.0, 15.8, (11, 12)),
                a_fight(26, 3429, 5, 51.12, 271.3, (11, 12)),
            ],
            "masterData": {"actors": ROSTER},
        }
    }
}

QUALIFYING = (28, 29, 26)
"""The fights `build_progression` keeps, across both bosses. 35 is the reset."""

STREAM_FELL_OVER = "the damage-taken stream fell over"


def _events(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"reportData": {"report": {"events": {"data": rows, "nextPageTimestamp": None}}}}


ABILITIES_PAYLOAD: dict[str, Any] = {
    "reportData": {
        "report": {
            "masterData": {
                "abilities": [
                    {"gameID": 12345, "name": "Crashing Wave", "icon": "spell_frost_wave.jpg"}
                ]
            }
        }
    }
}
DEATHS_PAYLOAD: dict[str, Any] = _events(
    [{"type": "death", "sourceID": -1, "targetID": 11, "timestamp": 5000}]
)
DAMAGE_TAKEN_PAYLOAD: dict[str, Any] = _events(
    [
        {
            "type": "damage",
            "abilityGameID": 12345,
            "sourceID": 249,
            "targetID": 11,
            "amount": 1000,
            "timestamp": 4000,
        }
    ]
)
ENEMY_CASTS_PAYLOAD: dict[str, Any] = _events(
    [
        {
            "type": "begincast",
            "abilityGameID": 12345,
            "sourceID": 249,
            "timestamp": 3000,
        }
    ]
)
INTERRUPTS_PAYLOAD: dict[str, Any] = _events(
    [
        {
            "type": "interrupt",
            "sourceID": 12,
            "targetID": 249,
            "extraAbilityGameID": 12345,
            "timestamp": 3500,
        }
    ]
)
# The one cast carries hit points, so `build_health_samples` yields a reading
# from it: the health column and the cast stream are one fetch, not two.
CASTS_PAYLOAD: dict[str, Any] = _events(
    [
        {
            "type": "cast",
            "abilityGameID": 12345,
            "sourceID": 11,
            "timestamp": 4500,
            "hitPoints": 400,
            "maxHitPoints": 1000,
        }
    ]
)
HEALING_PAYLOAD: dict[str, Any] = _events(
    [
        {
            "type": "heal",
            "abilityGameID": 12345,
            "sourceID": 12,
            "targetID": 11,
            "amount": 500,
            "timestamp": 4800,
        }
    ]
)
AURA_TABLE_PAYLOAD: dict[str, Any] = {
    "reportData": {
        "report": {
            "onSelf": {
                "data": {
                    "auras": [
                        {
                            "guid": 12345,
                            "name": "Crashing Wave",
                            "totalUptime": 6000,
                            "totalUses": 2,
                            "abilityIcon": "spell_frost_wave.jpg",
                            "bands": [{"startTime": 1000, "endTime": 7000}],
                        }
                    ]
                }
            }
        }
    }
}

STREAM_PAYLOADS: dict[str, dict[str, Any]] = {
    "Fights": DEEP_NIGHT,
    "Abilities": ABILITIES_PAYLOAD,
    "Deaths": DEATHS_PAYLOAD,
    "DamageTaken": DAMAGE_TAKEN_PAYLOAD,
    "EnemyCasts": ENEMY_CASTS_PAYLOAD,
    "Interrupts": INTERRUPTS_PAYLOAD,
    "Casts": CASTS_PAYLOAD,
    "Healing": HEALING_PAYLOAD,
    "AuraTable": AURA_TABLE_PAYLOAD,
}


def a_repository_recording_calls(
    tmp_path: Path,
    payload: dict[str, Any] = DEEP_NIGHT,
    failing: tuple[str, int] | None = None,
    failure_status: int = 200,
    cache: DiskCache | None = None,
) -> tuple[WclRunRepository, list[tuple[str, dict[str, Any]]]]:
    """A repository over a mock transport, plus every operation it sent with its variables.

    The variables are recorded beside the name because a tier claim is about
    *which pull* a stream was asked for: counting names alone cannot tell a
    `--deep` that deepened one fight from one that deepened the whole night.

    `failing` names an (operation, fightId) pair that answers with a failure
    instead of its payload -- a 200 carrying GraphQL errors by default, which
    `WclClient.execute` raises as `WclError`, or `failure_status` where the
    failure is an HTTP one.
    """
    calls: list[tuple[str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        body = json.loads(request.content)
        name = operation_name(body)
        variables = body.get("variables") or {}
        calls.append((name, variables))
        if failing is not None and (name, variables.get("fightId")) == failing:
            if failure_status == 200:
                return httpx.Response(200, json={"errors": [{"message": STREAM_FELL_OVER}]})
            return httpx.Response(failure_status, json={})
        if name == "Fights":
            return httpx.Response(200, json={"data": payload})
        if name in STREAM_PAYLOADS:
            return httpx.Response(200, json={"data": STREAM_PAYLOADS[name]})
        raise AssertionError(f"unexpected operation {name!r} in load_night_attempts test")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRunRepository(client, cache if cache is not None else DiskCache(tmp_path)), calls


def _fights_for(calls: list[tuple[str, dict[str, Any]]], operation: str) -> set[int]:
    """Which fights one operation was sent for."""
    return {int(variables["fightId"]) for name, variables in calls if name == operation}


def test_no_death_cards_sends_neither_an_aura_table_nor_healing(tmp_path: Path) -> None:
    """The cheapest tier: the two streams plus enemy casts and interrupts, and nothing more.

    Asserting the operations sent rather than the fields that came back is the
    whole point. `auras` being empty would also be true of a method that
    fetched every table and dropped them, which is the mistake that costs one
    call a roster player on every run.
    """
    repository, calls = a_repository_recording_calls(tmp_path)
    night = repository.load_night("abc123", None)
    calls.clear()  # drop the Fights call load_night made above

    repository.load_night_attempts(night, deep_fights=frozenset(), death_cards=False)

    sent = [name for name, _ in calls]
    assert sent.count("Deaths") == 3
    assert sent.count("DamageTaken") == 3
    assert sent.count("EnemyCasts") == 3
    assert sent.count("Interrupts") == 3
    assert "AuraTable" not in sent
    assert "Healing" not in sent
    assert "Casts" not in sent
    assert _fights_for(calls, "Deaths") == set(QUALIFYING), "fight 35 is a reset, never deepened"


def test_the_default_tier_sends_the_aura_table_but_no_healing(tmp_path: Path) -> None:
    """The trimmed tier adds `AuraTable`, one call a roster player, and stops there.

    `AuraTable` is what refines a defensive press into held or faded. Without
    it every availability state collapses back to `pressed`, so the trimmed
    card would draw six states and reach one.
    """
    repository, calls = a_repository_recording_calls(tmp_path)
    night = repository.load_night("abc123", None)
    calls.clear()

    repository.load_night_attempts(night, deep_fights=frozenset(), death_cards=True)

    sent = [name for name, _ in calls]
    assert sent.count("AuraTable") == 6, "two roster players over three qualifying attempts"
    assert _fights_for(calls, "AuraTable") == set(QUALIFYING)
    assert "Healing" not in sent
    assert "Casts" not in sent


def test_only_the_fight_named_deep_reaches_the_deep_tier(tmp_path: Path) -> None:
    """One named pull is deepened; its neighbours stay where they were.

    The failure this exists to catch is a builder that reads `deep_fights` once
    for the night instead of once per attempt, which would put every pull at
    the dearest tier -- so the neighbours are asserted as explicitly as the
    named fight. 28 shares a boss with 29 and 26 does not, so a leak is caught
    whichever way it runs.
    """
    repository, calls = a_repository_recording_calls(tmp_path)
    night = repository.load_night("abc123", None)
    calls.clear()

    repository.load_night_attempts(night, deep_fights=frozenset({29}), death_cards=True)

    assert _fights_for(calls, "Healing") == {29}
    assert _fights_for(calls, "Casts") == {29}
    # Everything else was still fetched for all three: the named fight is
    # deepened, not substituted for the night.
    assert _fights_for(calls, "Deaths") == set(QUALIFYING)
    assert _fights_for(calls, "AuraTable") == set(QUALIFYING)


def test_the_streams_land_on_the_attempt_they_were_fetched_for(tmp_path: Path) -> None:
    """What came back, beside the tier tests' claim about what was asked for.

    The deep fight carries the health column and the healing its own tier pays
    for; the trimmed one beside it carries neither, and both carry the streams
    every tier fetches.
    """
    repository, _ = a_repository_recording_calls(tmp_path)
    night = repository.load_night("abc123", None)

    deep = repository.load_night_attempts(night, deep_fights=frozenset({29}), death_cards=True)

    by_fight = {
        one.encounter.fight_id: one for progression in deep.loaded for one in progression.loaded
    }
    assert sorted(by_fight) == sorted(QUALIFYING)
    named = by_fight[29]
    assert [death.actor_id for death in named.deaths] == [11]
    assert [hit.ability_id for hit in named.damage_taken] == [12345]
    assert [row.ability_id for row in named.enemy_cast_rows] == [12345]
    assert [one.actor_id for one in named.interrupts] == [12]
    assert [one.actor_id for one in named.auras] == [11, 12]
    assert [sample.hit_points for sample in named.health_samples] == [400]
    assert [heal.amount for heal in named.healing] == [500]
    # The report's icons ride on every attempt: a night's death cards and
    # ledger rows draw them, which is why both halves of the dictionary are kept.
    assert named.ability_icons == ((12345, "spell_frost_wave.jpg"),)

    neighbour = by_fight[28]
    assert neighbour.health_samples == ()
    assert neighbour.healing == ()
    assert neighbour.casts == ()
    assert [one.actor_id for one in neighbour.auras] == [11, 12]


def test_the_ability_dictionary_is_read_once_for_the_whole_night(tmp_path: Path) -> None:
    """One `Abilities` call answers every boss and every pull.

    An ordinary `DiskCache` keys that query on the report code alone, so a
    wrongly-per-pull call would come back as a hit and never reach the mock
    transport -- the assertion below would hold against the very mistake it
    exists to catch. `_UncachedDiskCache` cannot hide a repeat call, which is
    what makes this test able to fail; it is borrowed from the sibling test of
    `load_progression_attempts`, where the same claim is made for the same
    reason.
    """
    repository, calls = a_repository_recording_calls(
        tmp_path, cache=_UncachedDiskCache(tmp_path)
    )
    night = repository.load_night("abc123", None)
    calls.clear()

    repository.load_night_attempts(night, deep_fights=frozenset(), death_cards=True)

    assert [name for name, _ in calls].count("Abilities") == 1
    assert len(_fights_for(calls, "Deaths")) == 3


def test_a_night_with_nothing_to_deepen_fetches_nothing(tmp_path: Path) -> None:
    """Every attempt a reset: there is nothing to deepen and no dictionary to read.

    The bosses still come back, each with an empty `LoadedProgression`, so the
    page can say a boss was pulled and discarded rather than losing it.
    """
    resets: dict[str, Any] = json.loads(json.dumps(DEEP_NIGHT))
    for fight in resets["reportData"]["report"]["fights"]:
        fight["endTime"] = fight["startTime"] + 15_800
    repository, calls = a_repository_recording_calls(tmp_path, resets)
    night = repository.load_night("abc123", None)
    calls.clear()

    deep = repository.load_night_attempts(night, deep_fights=frozenset(), death_cards=True)

    assert calls == []
    assert [one.progression.encounter_id for one in deep.loaded] == [3492, 3429]
    assert all(one.loaded == () for one in deep.loaded)


def test_a_failing_pull_shrinks_the_night_and_is_recorded_with_its_reason(
    tmp_path: Path,
) -> None:
    """Spec section 10: one pull failing shrinks the night rather than failing it.

    Both halves are asserted here on purpose. A test that only counted the
    survivors would pass against a method that swallowed the failure in
    silence, which is how a night quietly comes to cover less than the report
    it names -- so the record naming the fight and the reason is asserted in
    the same test as the survival of its neighbours.
    """
    repository, _ = a_repository_recording_calls(tmp_path, failing=("DamageTaken", 29))
    night = repository.load_night("abc123", None)

    deep = repository.load_night_attempts(night, deep_fights=frozenset(), death_cards=True)

    survivors = [one.encounter.fight_id for p in deep.loaded for one in p.loaded]
    assert survivors == [28, 26]
    assert [(one.fight_id, one.reason) for one in deep.failed_pulls] == [(29, STREAM_FELL_OVER)]


def test_a_spent_budget_stops_the_night_rather_than_failing_every_pull(tmp_path: Path) -> None:
    """A spent quota is the one failure that must not become a per-pull record.

    `_affix_names` already rules it this way: a rate limit is not this pull's
    problem, it is every remaining pull's, and a Provenance section listing
    each of them as failed would name the wrong cause twenty times over.
    """
    repository, _ = a_repository_recording_calls(
        tmp_path, failing=("DamageTaken", 29), failure_status=429
    )
    night = repository.load_night("abc123", None)

    with pytest.raises(RateLimitExceeded):
        repository.load_night_attempts(night, deep_fights=frozenset(), death_cards=True)
