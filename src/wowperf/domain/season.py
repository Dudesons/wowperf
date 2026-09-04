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
