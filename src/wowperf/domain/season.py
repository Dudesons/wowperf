# ABOUTME: Season constants the API does not expose, as a pure value object.
# ABOUTME: Reading them off disk is an adapter's job; this file performs no I/O.

from wowperf.domain.base import Frozen


class SeasonData(Frozen):
    """Timer constants Blizzard retunes between seasons."""

    death_penalty_seconds: float
    death_penalty_seconds_high_key: float
    high_key_threshold: int

    def death_penalty(self, keystone_level: int) -> float:
        """Seconds a single death adds to the keystone timer at this level."""
        if keystone_level >= self.high_key_threshold:
            return self.death_penalty_seconds_high_key
        return self.death_penalty_seconds


class DefensiveAbility(Frozen):
    """One personal damage-reduction cooldown, identified by its spell id."""

    ability_id: int
    name: str
    # Required, not defaulted: an ability whose cooldown is unknown has no honest
    # ceiling, and a default would let that travel silently into a printed number.
    cooldown_seconds: float
    charges: int = 1


class Defensives(Frozen):
    """Personal damage-reduction cooldowns per class and specialisation.

    A tuple of pairs rather than a dict, so the model stays hashable and cannot
    be mutated through the field.
    """

    entries: tuple[tuple[str, tuple[DefensiveAbility, ...]], ...] = ()

    def for_spec(self, class_name: str, spec: str) -> tuple[DefensiveAbility, ...]:
        """The known defensive abilities for a class/spec, or `()` if the list has none."""
        wanted = f"{class_name}/{spec}"
        for key, abilities in self.entries:
            if key == wanted:
                return abilities
        return ()


class ConsumableCategory(Frozen):
    """Healing consumables that share one cooldown.

    The category is the unit of availability, not the item: drinking any id in
    it blocks every other id in it. That is what makes a rank-upgraded potion
    join a group rather than needing the analyser to learn a new cooldown.
    """

    name: str
    # Required for the same reason a defensive's is: a category whose cooldown is
    # unknown cannot say whether anything was available.
    cooldown_seconds: float
    ability_ids: tuple[int, ...] = ()


class Consumables(Frozen):
    """Healing consumables by cooldown category."""

    categories: tuple[ConsumableCategory, ...] = ()
