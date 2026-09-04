# ABOUTME: The run as a sequence: deaths and casts, each located in time and in a pull.
# ABOUTME: Pure data; analysers derive meaning from these, adapters produce them.

from wowperf.domain.base import Frozen


class Death(Frozen):
    player_name: str
    actor_id: int
    timestamp_ms: int
    killing_blow: str
    pull_index: int | None = None
    seconds_until_next_action: float | None = None


class CastEvent(Frozen):
    actor_id: int
    ability_id: int
    ability_name: str
    timestamp_ms: int
    pull_index: int | None = None


class EnemyCastRow(Frozen):
    """One raw enemy cast event, translated but not yet resolved."""

    source_id: int
    source_instance: int
    ability_id: int
    ability_name: str
    timestamp_ms: int
    is_start: bool
    pull_index: int | None = None


class EnemyCast(Frozen):
    """One enemy cast start, resolved to an outcome.

    Three states, mutually exclusive: the cast landed, a player kicked it, or
    the log does not say. The third is real — the caster may have died, been
    crowd-controlled, or cancelled — and those casts are excluded from the
    interrupt analysis rather than counted as misses.
    """

    source_id: int
    source_instance: int
    ability_id: int
    ability_name: str
    started_ms: int
    completed_ms: int | None = None
    interrupted_by: str | None = None
    pull_index: int | None = None

    @property
    def landed(self) -> bool:
        return self.completed_ms is not None and self.interrupted_by is None

    @property
    def was_kicked(self) -> bool:
        return self.interrupted_by is not None

    @property
    def outcome_known(self) -> bool:
        return self.landed or self.was_kicked


class InterruptEvent(Frozen):
    player_name: str
    actor_id: int
    interrupted_ability_id: int
    target_id: int
    target_instance: int
    timestamp_ms: int
    pull_index: int | None = None


class EnemyDeath(Frozen):
    """An enemy kill and the enemy forces it awarded."""

    game_id: int
    actor_id: int
    timestamp_ms: int
    forces: int
    pull_index: int | None = None


class DamageTakenEvent(Frozen):
    """One hit on a player. `amount` is the unmitigated figure.

    A Warcraft Logs damage event's `amount` excludes what was absorbed, so a
    fully absorbed hit reads zero. `unmitigatedAmount` is the honest answer to
    "how hard did this hit", which is what the per-ability comparison asks.
    """

    actor_id: int
    ability_id: int
    ability_name: str
    amount: int
    timestamp_ms: int
    pull_index: int | None = None
