# ABOUTME: One player's debuffs over every enemy of a key: coverage and reach on each stretch.
# ABOUTME: Bosses keep the boss rule; trash and adds are read life by life, first debuff to death.

from collections import defaultdict
from collections.abc import Sequence

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.boss_debuffs import (
    BossDebuffs,
    Held,
    boss_windows_of,
    bosses_held_by,
    find_shared,
    held_on_bosses,
    length_ms,
    merged_spans,
)
from wowperf.domain.comparison.enemy_lives import EnemyLife, LifeStretch, enemy_lives
from wowperf.domain.debuffs import DebuffInterval, DebuffLog, pair_debuffs
from wowperf.domain.model import Pull


class StretchCover(Frozen):
    """One stretch of a key: its measured lives, and what one player's debuffs did on them.

    `covered` sums, life by life, the time a debuff sat on each life, the
    player's and their pets' copies merged per life first. `reached` counts the
    lives it sat on at all. A life of no length adds a life and no time.
    """

    lives: int = 0
    alive_ms: int = 0
    covered: tuple[tuple[int, int], ...] = ()
    """(ability id, milliseconds it covered these lives, summed over them)."""
    reached: tuple[tuple[int, int], ...] = ()
    """(ability id, lives it covered for any time at all)."""

    @property
    def seconds(self) -> float:
        """The stretch's summed alive time: the denominator of its coverage."""
        return self.alive_ms / 1000

    def coverage(self, ability_id: int) -> float | None:
        """The share of the alive time this debuff covered, or None with none to share."""
        if self.alive_ms <= 0:
            return None
        return dict(self.covered).get(ability_id, 0) / self.alive_ms

    def reach(self, ability_id: int) -> float | None:
        """The share of the lives this debuff sat on at all, or None with no life measured."""
        if self.lives <= 0:
            return None
        return dict(self.reached).get(ability_id, 0) / self.lives


def combined(*covers: StretchCover) -> StretchCover:
    """Several stretches read as one: lives, alive time, covered time and reach summed."""
    covered: dict[int, int] = defaultdict(int)
    reached: dict[int, int] = defaultdict(int)
    for cover in covers:
        for ability_id, ms in cover.covered:
            covered[ability_id] += ms
        for ability_id, count in cover.reached:
            reached[ability_id] += count
    return StretchCover(
        lives=sum(cover.lives for cover in covers),
        alive_ms=sum(cover.alive_ms for cover in covers),
        covered=tuple(sorted(covered.items())),
        reached=tuple(sorted(reached.items())),
    )


class KeyDebuffs(Frozen):
    """One player's debuffs over every enemy of one key, stretch by stretch.

    `bosses` is the boss figure, built by the boss rule: its covered time, reach
    and seconds are unmoved by anything that died beside a boss, though its
    `shared_with` reads the trash and add lives too. `trash` holds every life
    whose death fell in a trash pull, and `adds` every other life whose death
    fell in a boss pull.
    Overall is the three summed, and it is the stretch the verdict reads.
    """

    bosses: BossDebuffs = BossDebuffs()
    trash: StretchCover = StretchCover()
    adds: StretchCover = StretchCover()
    life_names: tuple[tuple[int, str], ...] = ()
    """(ability id, name), for every debuff in `trash` or `adds`."""
    unmeasured_no_death: int = 0
    """Enemies debuffed after their last death with no death to close them: left out."""
    undebuffed_deaths: int = 0
    """Deaths with no application since that copy's previous death: lives of no length."""

    @property
    def on_bosses(self) -> StretchCover:
        """The Bosses stretch: each boss target of a measured pull is one life."""
        targets = [
            target
            for window in self.bosses.windows
            if window.withheld is None
            for target in window.targets
        ]
        covered: dict[int, int] = defaultdict(int)
        for _, ability_id, ms in self.bosses.covered:
            covered[ability_id] += ms
        return StretchCover(
            lives=len(targets),
            alive_ms=sum(target.end_ms - target.start_ms for target in targets),
            covered=tuple(sorted(covered.items())),
            reached=self.bosses.reached,
        )

    @property
    def overall(self) -> StretchCover:
        """Bosses, trash and adds together: the stretch the verdict reads."""
        return combined(self.on_bosses, self.trash, self.adds)

    @property
    def names(self) -> tuple[tuple[int, str], ...]:
        """(ability id, name) of every debuff covering any measured target, by id."""
        return tuple(sorted((dict(self.bosses.names) | dict(self.life_names)).items()))

    @property
    def shared_with(self) -> tuple[tuple[int, tuple[int, ...]], ...]:
        """(ability id, the other players' actor ids) for each debuff found shared."""
        return self.bosses.shared_with


def held_on_lives(
    lives: Sequence[EnemyLife], intervals: Sequence[DebuffInterval], owners: frozenset[int]
) -> Held:
    """Every owner's spans on each enemy life, each clipped to that life.

    A life is matched by game id and copy number, as the pairing keys a target,
    so a debuff on one copy of a mob never counts on another copy beside it.
    """
    by_enemy: dict[tuple[int, int], list[EnemyLife]] = defaultdict(list)
    for life in lives:
        by_enemy[(life.game_id, life.instance)].append(life)
    held: Held = {}
    for one in intervals:
        if one.owner_id not in owners:
            continue
        for life in by_enemy.get((one.target_game_id, one.target_instance), ()):
            start_ms = max(one.start_ms, life.start_ms)
            end_ms = min(one.end_ms, life.end_ms)
            if end_ms > start_ms:
                by_life = held.setdefault((one.owner_id, one.ability_id), {})
                by_life.setdefault(life.key, []).append((start_ms, end_ms))
    return held


def key_debuffs(
    log: DebuffLog, pulls: Sequence[Pull], owner_id: int, players: frozenset[int]
) -> KeyDebuffs:
    """What this player, and their pets, kept on every enemy of this key.

    The boss is matched by game id, for the same reason the pairing keys on it,
    and each interval is clipped to the span of the boss it sat on. Every other
    enemy is cut into lives by `enemy_lives` and matched by game id and copy
    number; each interval is clipped to the life it sat on.

    `players` is the actor ids of the run's players, the only owners whose
    debuffs `find_shared` reads: a pet is already folded into its owner by the
    pairing, and an enemy is never a player. A reference is read with none, so
    nothing on its side is ever shared. The shared rule reads every target of
    the key at once, bosses and lives, and the boss figure carries its answer.
    """
    windows = boss_windows_of(pulls, log.npc_actors, log.deaths)
    intervals, tally = pair_debuffs(log)
    owners = players | {owner_id}
    boss_ids = frozenset(target.game_id for window in windows for target in window.targets)
    found = enemy_lives(log, pulls, boss_ids)
    on_bosses = held_on_bosses(windows, intervals, owners)
    on_lives = held_on_lives(found.lives, intervals, owners)
    everywhere: Held = {key: dict(by_target) for key, by_target in on_bosses.items()}
    for key, by_life in on_lives.items():
        everywhere.setdefault(key, {}).update(by_life)
    trash = _cover(found.lives, on_lives, owner_id, LifeStretch.TRASH)
    adds = _cover(found.lives, on_lives, owner_id, LifeStretch.ADDS)
    names = dict(log.ability_names)
    on_lives_abilities = {ability_id for ability_id, _ in (*trash.covered, *adds.covered)}
    return KeyDebuffs(
        bosses=bosses_held_by(
            windows,
            on_bosses,
            owner_id,
            log.ability_names,
            tally,
            find_shared(everywhere, owner_id),
        ),
        trash=trash,
        adds=adds,
        life_names=tuple(
            (ability_id, names.get(ability_id, f"Unknown ability {ability_id}"))
            for ability_id in sorted(on_lives_abilities)
        ),
        unmeasured_no_death=found.unmeasured_no_death,
        undebuffed_deaths=found.undebuffed_deaths,
    )


def boss_debuffs(
    log: DebuffLog, pulls: Sequence[Pull], owner_id: int, players: frozenset[int]
) -> BossDebuffs:
    """The boss half of `key_debuffs`: what this player kept on each measured boss.

    Kept as its own reading because every boss test, and the boss end-to-end
    test, read the boss figure through it: they pin the very path the
    comparison runs, so nothing that died beside a boss can move its covered
    time, reach or seconds unnoticed.
    """
    return key_debuffs(log, pulls, owner_id, players).bosses


def _cover(
    lives: Sequence[EnemyLife], held: Held, owner_id: int, stretch: LifeStretch
) -> StretchCover:
    """One stretch's lives, and this owner's merged time on them and lives reached."""
    mine = [life for life in lives if life.stretch is stretch]
    keys = {life.key for life in mine}
    covered: dict[int, int] = defaultdict(int)
    reached: dict[int, int] = defaultdict(int)
    for (owner, ability_id), by_life in held.items():
        if owner != owner_id:
            continue
        for key, spans in by_life.items():
            if key in keys:
                covered[ability_id] += length_ms(merged_spans(spans))
                reached[ability_id] += 1
    return StretchCover(
        lives=len(mine),
        alive_ms=sum(life.end_ms - life.start_ms for life in mine),
        covered=tuple(sorted(covered.items())),
        reached=tuple(sorted(reached.items())),
    )
