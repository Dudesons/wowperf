# ABOUTME: The run as a structure: who was there, which packs were pulled, and when.
# ABOUTME: Pure data with derived properties; imports nothing that performs I/O.

from wowperf.domain.base import Frozen


class Player(Frozen):
    actor_id: int
    name: str
    class_name: str
    spec: str
    item_level: int


class EnemyNpc(Frozen):
    actor_id: int
    game_id: int


class Pull(Frozen):
    index: int
    pull_id: int
    name: str
    encounter_id: int
    start_ms: int
    end_ms: int
    killed: bool
    x: int
    y: int
    enemies: tuple[EnemyNpc, ...]

    @property
    def is_boss(self) -> bool:
        """Warcraft Logs uses encounter ID 0 to mean a trash pull."""
        return self.encounter_id != 0

    @property
    def duration_seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000

    @property
    def signature(self) -> tuple[int, ...]:
        """Canonical identity of a pull, used to align two runs of the same dungeon."""
        return tuple(sorted(enemy.game_id for enemy in self.enemies))


class Run(Frozen):
    report_code: str
    fight_id: int
    dungeon_name: str
    keystone_level: int
    affix_ids: tuple[int, ...]
    keystone_time_ms: int
    keystone_bonus: int
    count_reached: int
    count_required: int
    npc_count_map: dict[int, int]
    players: tuple[Player, ...]
    pulls: tuple[Pull, ...]

    @property
    def keystone_time_seconds(self) -> float:
        return self.keystone_time_ms / 1000

    @property
    def total_pull_seconds(self) -> float:
        return sum(pull.duration_seconds for pull in self.pulls)

    @property
    def boss_pulls(self) -> tuple[Pull, ...]:
        return tuple(pull for pull in self.pulls if pull.is_boss)

    @property
    def trash_pulls(self) -> tuple[Pull, ...]:
        return tuple(pull for pull in self.pulls if not pull.is_boss)
