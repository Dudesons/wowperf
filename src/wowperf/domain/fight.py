# ABOUTME: What a loaded fight offers a reader: a roster, a window, and the streams of events.
# ABOUTME: A description of what those readers read, never a switch on which kind of fight it is.

from collections.abc import Mapping
from typing import Protocol

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.events import (
    CastEvent,
    DamageTakenEvent,
    Death,
    HealingEvent,
    HealthSample,
    Resurrection,
)
from wowperf.domain.model import Player


class LoadedFight(Protocol):
    """The shape `LoadedRun` and `LoadedEncounter` already share.

    A death recap and a run-wide ability panel read a roster, whether the
    fight is cut into pulls, the stretch of time the log covers, and seven
    event and aura streams: `casts`, `deaths`, `damage_taken`, `healing`,
    `health_samples`, `resurrections` and `auras_by_actor`. Both aggregates
    carry all ten members, so a function typed on this is stating what it
    reads rather than which command loaded it -- which is what lets one recap
    serve a keystone run and a boss fight without either of them learning
    about the other.

    Declared as a protocol rather than as a union of the two, and rather than
    as a base class they both inherit. A union would put an `isinstance` in
    every reader, and a reader that asks which fight it was handed is one edit
    away from answering differently for each. A base class would be a claim
    that a run and an encounter are kinds of one thing, which design section
    5.3 measured and rejected.

    Every member is a read-only property here, which a plain frozen field
    satisfies as readily as a computed one: `casts` is a field on both
    aggregates, `players` and `window_ms` are properties on each, and nothing
    outside them needs to know the difference.

    Deliberately smaller than either aggregate. `LoadedRun.enemy_deaths` and
    `LoadedEncounter.standing` have no counterpart across the pair and no
    reader of this protocol wants one; naming them would make this a
    lowest-common-denominator copy of two models instead of a statement about
    what a recap needs.
    """

    @property
    def players(self) -> tuple[Player, ...]: ...

    @property
    def window_ms(self) -> tuple[int, int]: ...

    @property
    def has_pulls(self) -> bool:
        """Whether this fight is cut into pulls at all.

        A death card states when it happened, and what "when" means depends on
        this: a fight cut into pulls names the one a death fell in, or says it
        fell between them, while a fight that is one continuous window has
        nothing to be between and states the elapsed time alone. Declared here
        so the card reads a fact about the fight rather than asking which kind
        of fight it was handed.
        """
        ...

    @property
    def casts(self) -> tuple[CastEvent, ...]: ...

    @property
    def deaths(self) -> tuple[Death, ...]: ...

    @property
    def damage_taken(self) -> tuple[DamageTakenEvent, ...]: ...

    @property
    def healing(self) -> tuple[HealingEvent, ...]: ...

    @property
    def health_samples(self) -> tuple[HealthSample, ...]: ...

    @property
    def resurrections(self) -> tuple[Resurrection, ...]: ...

    @property
    def auras_by_actor(self) -> Mapping[int, PlayerAuras]: ...
