# ABOUTME: The run as a sequence: deaths and casts, each located in time and in a pull.
# ABOUTME: Pure data; analysers derive meaning from these, adapters produce them.

from wowperf.domain.base import Frozen


class Death(Frozen):
    player_name: str
    actor_id: int
    timestamp_ms: int
    killing_blow: str
    killing_blow_id: int = 0
    pull_index: int | None = None
    seconds_until_next_action: float | None = None


class CastEvent(Frozen):
    actor_id: int
    ability_id: int
    ability_name: str
    timestamp_ms: int
    pull_index: int | None = None
    # The actor the cast was aimed at. None when the log recorded no target,
    # which is how self-only movement and shield spells appear.
    target_id: int | None = None


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

    `health_damage` is that `amount`: what reached the player's health after
    mitigation and absorption, which is what a health curve subtracts.
    `absorbed` is what a shield soaked. A fully absorbed hit therefore reads as
    unmitigated damage above zero, health damage zero, and absorbed equal to
    the shield's share — three facts, not one.
    """

    actor_id: int
    ability_id: int
    ability_name: str
    amount: int
    timestamp_ms: int
    pull_index: int | None = None
    health_damage: int = 0
    absorbed: int = 0


class HealthSample(Frozen):
    """The player's own health, read off an event they were the source of.

    Only events a player causes carry their hit points; the hits they take do
    not. A health curve is therefore a sequence of these, sparse wherever the
    player was idle, and the recap reconstructs the gaps.
    """

    actor_id: int
    timestamp_ms: int
    hit_points: int
    max_hit_points: int


class HealingEvent(Frozen):
    """One heal landing on a player, or one hit a shield on them soaked.

    `absorbed` tells the two apart. A heal restores `amount` health. An absorb
    prevented `amount` damage without touching health, and `ability_name` then
    names the shield that soaked it rather than a heal.
    """

    actor_id: int
    source_id: int
    ability_id: int
    ability_name: str
    amount: int
    timestamp_ms: int
    absorbed: bool = False


class Resurrection(Frozen):
    """A dead player brought back by a spell.

    `caster_id` equal to `actor_id` is a self-resurrection. A player who
    released and ran back has no record here at all: the log emits nothing.
    """

    actor_id: int
    caster_id: int
    ability_id: int
    ability_name: str
    timestamp_ms: int
