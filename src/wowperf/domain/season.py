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


class CooldownAbility(Frozen):
    """One ability on a cooldown, identified by its spell id.

    Shared by the defensive and throughput lists, which differ in what they mean
    rather than in what they hold.
    """

    ability_id: int
    name: str
    # Required, not defaulted: an ability whose cooldown is unknown has no honest
    # ceiling, and a default would let that travel silently into a printed number.
    cooldown_seconds: float
    charges: int = 1


class DefensiveAbility(CooldownAbility):
    """One personal damage-reduction cooldown."""


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


class ExternalAbility(CooldownAbility):
    """One cooldown a player casts on someone else to keep them alive."""


class Externals(Frozen):
    """Externals per class and specialisation, keyed like the defensives.

    Kept apart from the defensives because the question differs: a defensive
    is the dying player's own answer, an external is a teammate's, and the
    death card names the owner of every external so nobody reads "Ironbark
    ready" as a button the dying player could have pressed.
    """

    entries: tuple[tuple[str, tuple[ExternalAbility, ...]], ...] = ()

    def for_spec(self, class_name: str, spec: str) -> tuple[ExternalAbility, ...]:
        """The known externals for a class/spec, or `()` if the list has none."""
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


class ConsumableBuffs(Frozen):
    """Buff ability ids by consumable category, from the committed TOML file.

    A tuple of pairs rather than a mapping, like every other curated list here:
    the domain layer's values are frozen and hashable, and a dict is neither.
    """

    entries: tuple[tuple[str, tuple[int, ...]], ...] = ()

    def categories(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.entries)

    def ids_for(self, category: str) -> tuple[int, ...]:
        """The ability ids in this category, or `()` if the list has none."""
        for name, ability_ids in self.entries:
            if name == category:
                return ability_ids
        return ()


class SelfResurrections(Frozen):
    """Spells a dead player casts to bring themselves back.

    A player who returns without a resurrect event either released or cast one
    of these; the list is what tells the two apart. Empty when the log itself
    records a self-resurrection as a resurrect event, in which case nothing
    here is consulted.
    """

    ability_ids: tuple[int, ...] = ()


class Roles(Frozen):
    """Which specialisations tank and which heal, as "Class/Spec" entries.

    Empty by default, so a caller without the data file treats everyone as
    damage — the direction that produces a finding rather than silence.
    """

    tanks: tuple[str, ...] = ()
    healers: tuple[str, ...] = ()

    def role_of(self, class_name: str, spec: str) -> str:
        key = f"{class_name}/{spec}"
        if key in self.tanks:
            return "tank"
        if key in self.healers:
            return "healer"
        return "damage"


class ThroughputCooldowns(Frozen):
    """Throughput cooldowns per class and specialisation.

    Held apart from the defensive list rather than merged into it: the two ask
    opposite questions of the same shape of data. A defensive unpressed while
    dying is a loss; a throughput cooldown unpressed on a trivial pack is
    correct play, and only the pulls that mattered make it a question.
    """

    entries: tuple[tuple[str, tuple[CooldownAbility, ...]], ...] = ()

    def for_spec(self, class_name: str, spec: str) -> tuple[CooldownAbility, ...]:
        """The known throughput cooldowns for a class/spec, or `()` if none are listed."""
        wanted = f"{class_name}/{spec}"
        for key, abilities in self.entries:
            if key == wanted:
                return abilities
        return ()
