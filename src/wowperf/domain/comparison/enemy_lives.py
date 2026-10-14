# ABOUTME: Every enemy of a key cut into lives, from the first debuff anyone applied to its death.
# ABOUTME: A life belongs to the pull holding its death; a measured boss is left to the boss rule.

from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum

from wowperf.domain.base import Frozen
from wowperf.domain.debuffs import DebuffLog
from wowperf.domain.model import Pull


class LifeStretch(StrEnum):
    """Which stretch of the key holds a life: the pull holding its death decides."""

    TRASH = "trash"
    ADDS = "adds"


class EnemyLife(Frozen):
    """One life of one copy of one kind of enemy, from its first debuff to its death."""

    game_id: int
    instance: int
    start_ms: int
    end_ms: int
    stretch: LifeStretch

    @property
    def key(self) -> tuple[int, int, int]:
        """This life and no other: what two players' copies are compared on when shared."""
        return (self.game_id, self.instance, self.end_ms)


class EnemyLives(Frozen):
    """Every measured enemy life of a key, and what could not be measured, counted."""

    lives: tuple[EnemyLife, ...] = ()
    unmeasured_no_death: int = 0
    """Copies debuffed after their last death with no death to close them: left out."""
    undebuffed_deaths: int = 0
    """Deaths with no application since that copy's previous death: lives of no length."""


def enemy_lives(log: DebuffLog, pulls: Sequence[Pull], bosses: frozenset[int]) -> EnemyLives:
    """Every enemy life of the key outside the measured bosses, and what could not be measured.

    An enemy is (game id, instance), as the pairing keys a target: one creature
    can be logged under two actor ids, and the log reuses copy numbers, so each
    copy is cut into lives at its deaths. A life opens at the first application
    by anyone on that copy after its previous death, so a removal logged just
    after a death never opens one, and it closes at its death. Measured
    2026-10-13 (`docs/plans/2026-10-13-key-uptime-coverage-design.md` §3.1):
    the pull's start would triple a trash mob's alive time, since pulls chain
    packs, and the first debuff sits within about a second of the richest
    stream's first sight of the mob.

    A copy that died with no application since its previous death is a life of
    no length, counted in `undebuffed_deaths`: it adds no alive time and still
    counts for reach. Applications after a copy's last death with no death to
    close them are one life left out, counted in `unmeasured_no_death`. A death
    the log writes twice at one millisecond is one death.

    Left out entirely: a player, and a pet a player owns, which the log lists
    as hostile (Glacial Tomb, A Knot of Snakes); an actor with no game id, which
    nothing keys; and every game id in `bosses`, which the boss rule measures.

    A life belongs to the pull holding its death, the last pull starting at or
    before it: the log stamps a kill's last death a few milliseconds after its
    pull closed (measured 2026-10-08 on council kills), so a death between two
    pulls is the earlier pull's, and a death before every pull is the first
    pull's. A boss pull makes a life an add, a trash pull trash. A fight with no
    pulls has no stretch to put a life in, and holds none.
    """
    if not pulls:
        return EnemyLives()
    game_ids = dict(log.game_ids)
    owners = dict(log.pet_owners)
    players = frozenset(log.player_ids)

    def enemy(actor_id: int) -> int | None:
        """The game id this actor is measured under, or None when it is no enemy here."""
        if actor_id in players or owners.get(actor_id) in players:
            return None
        game_id = game_ids.get(actor_id)
        if game_id is None or game_id in bosses:
            return None
        return game_id

    applied: dict[tuple[int, int], list[int]] = defaultdict(list)
    for event in log.events:
        if not event.applied:
            continue
        game_id = enemy(event.target_id)
        if game_id is not None:
            applied[(game_id, event.target_instance)].append(event.timestamp_ms)
    died: dict[tuple[int, int], set[int]] = defaultdict(set)
    for row in log.death_rows:
        game_id = enemy(row.target_id)
        if game_id is not None:
            died[(game_id, row.target_instance)].add(row.timestamp_ms)

    lives: list[EnemyLife] = []
    unmeasured = 0
    undebuffed = 0
    for key in sorted(applied.keys() | died.keys()):
        game_id, instance = key
        applications = sorted(applied.get(key, ()))
        previous: int | None = None
        for death_ms in sorted(died.get(key, ())):
            opened = next(
                (
                    at
                    for at in applications
                    if (previous is None or at > previous) and at <= death_ms
                ),
                None,
            )
            if opened is None:
                undebuffed += 1
                opened = death_ms
            lives.append(
                EnemyLife(
                    game_id=game_id,
                    instance=instance,
                    start_ms=opened,
                    end_ms=death_ms,
                    stretch=_stretch_at(pulls, death_ms),
                )
            )
            previous = death_ms
        if any(previous is None or at > previous for at in applications):
            unmeasured += 1
    return EnemyLives(
        lives=tuple(lives), unmeasured_no_death=unmeasured, undebuffed_deaths=undebuffed
    )


def _stretch_at(pulls: Sequence[Pull], at_ms: int) -> LifeStretch:
    """The stretch of the pull holding a death: the last pull starting at or before it."""
    started = [pull for pull in pulls if pull.start_ms <= at_ms]
    holder = (
        max(started, key=lambda pull: pull.start_ms)
        if started
        else min(pulls, key=lambda pull: pull.start_ms)
    )
    return LifeStretch.ADDS if holder.is_boss else LifeStretch.TRASH
