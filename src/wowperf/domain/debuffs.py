# ABOUTME: Enemy-debuff applications and removals as pure values, paired into intervals.
# ABOUTME: A pet's application belongs to its owner, and a target is keyed by game id, not actor id.

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace_boss import NpcActor


class DebuffEvent(Frozen):
    """One `applydebuff` or `removedebuff` row of the enemy-debuff stream.

    Refreshes and stack changes are dropped at ingest: neither changes whether
    the debuff is on. An absent instance is the stream's first copy, read as 0.
    """

    applied: bool
    timestamp_ms: int
    source_id: int
    source_instance: int = 0
    target_id: int
    target_instance: int = 0
    ability_id: int


class DebuffLog(Frozen):
    """One run's enemy-debuff stream, with what reading it per player needs.

    The stream covers the whole group, so one log serves every player in it.
    Pairs rather than dicts, so the log is immutable and hashable like a `Run`.
    `end_ms` is the fight's own end, where an interval still open is closed.
    """

    events: tuple[DebuffEvent, ...] = ()
    pet_owners: tuple[tuple[int, int], ...] = ()
    """(pet actor id, owning actor id), for every actor carrying `petOwner`."""
    game_ids: tuple[tuple[int, int], ...] = ()
    """(actor id, game id), for every actor in the report."""
    npc_actors: tuple[NpcActor, ...] = ()
    ability_names: tuple[tuple[int, str], ...] = ()
    end_ms: int


class DebuffInterval(Frozen):
    """One unbroken stretch an owner's debuff sat on one copy of one kind of enemy."""

    owner_id: int
    ability_id: int
    target_game_id: int
    target_instance: int
    start_ms: int
    end_ms: int


class PairingTally(Frozen):
    """What the pairing met that a clean log would not hold. Recorded, never judged.

    These counts are the evidence a live run reads back: how often the log's
    own applications and removals failed to meet, and how often a target could
    not be named at all.
    """

    orphan_removes: int = 0
    closed_at_end: int = 0
    unresolved_targets: int = 0


Key = tuple[int, int, int, int, int]
"""(source id, source instance, ability id, target game id, target instance)."""


def pair_debuffs(log: DebuffLog) -> tuple[tuple[DebuffInterval, ...], PairingTally]:
    """Every interval the log's applications and removals describe, and what did not pair.

    The target is keyed on its game id and copy number rather than its actor id.
    Measured 2026-10-07 (`.claude/skills/wcl-api/SKILL.md`, "The debuff event
    stream does name the caster"): one enemy can be logged under two actor ids
    of the same game id, its application on one and its removal on the other.
    Keyed on the actor id, 13 of one player's 168 applications never closed.
    Keyed on the game id, the same ability balanced completely.

    The source stays raw in the key, instance and all, so two summons of one
    pet never close each other's debuff. It is folded to its owner only when
    the interval is written.

    A second application while one is open keeps the first start: the debuff
    never came off. A removal with nothing open is counted and dropped rather
    than guessed at. An interval still open when the stream ends is closed at
    the fight's end.
    """
    owners = dict(log.pet_owners)
    game_ids = dict(log.game_ids)
    opened: dict[Key, int] = {}
    intervals: list[DebuffInterval] = []
    orphan_removes = 0
    unresolved = 0

    def written(key: Key, start_ms: int, end_ms: int) -> DebuffInterval:
        source_id, _, ability_id, game_id, instance = key
        return DebuffInterval(
            owner_id=owners.get(source_id, source_id),
            ability_id=ability_id,
            target_game_id=game_id,
            target_instance=instance,
            start_ms=start_ms,
            end_ms=end_ms,
        )

    # Stable, so rows sharing a millisecond keep the order the log wrote them in.
    for event in sorted(log.events, key=lambda one: one.timestamp_ms):
        game_id = game_ids.get(event.target_id)
        if game_id is None:
            unresolved += 1
            continue
        key = (
            event.source_id,
            event.source_instance,
            event.ability_id,
            game_id,
            event.target_instance,
        )
        if event.applied:
            opened.setdefault(key, event.timestamp_ms)
            continue
        start_ms = opened.pop(key, None)
        if start_ms is None:
            orphan_removes += 1
            continue
        intervals.append(written(key, start_ms, event.timestamp_ms))

    for key, start_ms in opened.items():
        intervals.append(written(key, start_ms, max(start_ms, log.end_ms)))

    return tuple(intervals), PairingTally(
        orphan_removes=orphan_removes,
        closed_at_end=len(opened),
        unresolved_targets=unresolved,
    )
