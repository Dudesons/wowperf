# ABOUTME: The run as a structure: who was there, which packs were pulled, and when.
# ABOUTME: Pure data with derived properties; imports nothing that performs I/O.

from collections.abc import Mapping
from types import MappingProxyType

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.base import Frozen
from wowperf.domain.events import (
    CastEvent,
    DamageTakenEvent,
    Death,
    EnemyCastRow,
    EnemyDeath,
    HealingEvent,
    HealthSample,
    InterruptEvent,
    Resurrection,
)
from wowperf.domain.loadout import Loadout


class Player(Frozen):
    actor_id: int
    name: str
    class_name: str
    spec: str
    item_level: int
    # Absent until a talent query runs; `get` never pays for one.
    talent_import_string: str | None = None
    # Absent on the speed axis, which never fetches one, and on every run
    # cached before this query existed. None means unknown, never "wore nothing".
    loadout: Loadout | None = None


MIN_PACK_SECONDS = 1.0
"""Under this a pull is a segmentation artefact rather than a pack anybody chose.

Warcraft Logs closes and reopens a pull in the middle of an engagement, leaving
one of a few milliseconds whose enemies are a subset of the pull before it, and
it records the odd stray tag the same way. Measured over 98 cached pulls on
2026-09-11: six ran under a second — the longest of them 0.525s — and the next
shortest ran 6.770s. The floor therefore falls in an empty stretch of the
distribution rather than through a cluster of real packs, which is the whole of
its justification. It is a claim about how the log cuts a route, not a view about
how long a pack ought to last.

Of the five that carried any enemy at all, four were the last few milliseconds
of a boss pull, holding one of that pull's own enemies; the fifth was an
isolated tag 45 seconds clear of anything either side. The floor is written on
duration rather than on that shape because the shape is a tendency and the
duration is the thing every one of them shares.
"""


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
    def is_a_pack(self) -> bool:
        """Whether a route decision could have taken or left this pull.

        Two shapes of pull are not. One with no recorded enemies is nothing any
        route contains, and `comparison.alignment` can never pair it with
        anything, so it reads as unmatched however both routes were run. One
        under `MIN_PACK_SECONDS` is where Warcraft Logs cut a single engagement
        in two.

        Nothing counts pulls through this. A pull count describes how the log
        cut the route and must keep reporting every pull the log recorded; what
        this gates is whether a pull may be named to a reader as a pack — one a
        group chose, and can be held to account for, whether the charge is that
        the other route skipped it or that it bought almost nothing.
        """
        return bool(self.enemies) and self.duration_seconds >= MIN_PACK_SECONDS

    @property
    def signature(self) -> tuple[int, ...]:
        """The sorted multiset of enemy game IDs in this pull.

        Duplicates are kept: a pack of three casters and a pack of one caster are
        different packs, and this describes the pack rather than summarising it.
        It is not how two runs are matched — `comparison/alignment.py` works on the
        *set* of enemy types, so that a stretch Warcraft Logs recorded as one pull
        still matches each separate pull it covers.
        """
        return tuple(sorted(enemy.game_id for enemy in self.enemies))


class Run(Frozen):
    report_code: str
    fight_id: int
    dungeon_name: str
    # The rankings API keys on this, and the fight carries it, so no leaderboard
    # lookup in this project ever needs a hardcoded encounter or zone ID.
    encounter_id: int
    keystone_level: int
    affix_ids: tuple[int, ...]
    # Resolved from game data by the adapter, index-aligned with affix_ids.
    # Empty when no resolution ran; an id the game data does not list resolves
    # to the id as text, so the two tuples are equal in length whenever this
    # one is non-empty.
    affix_names: tuple[str, ...] = ()
    keystone_time_ms: int
    keystone_bonus: int
    count_reached: int
    count_required: int
    # Warcraft Logs lowercases the owner's name relative to the character's, so
    # anything matching against it must fold case.
    owner_name: str | None = None
    # Enemy-forces awarded per NPC game ID, as (game_id, count) pairs. A tuple, not
    # a dict, so that a Run is genuinely immutable and hashable; read it through
    # npc_count_map.
    npc_counts: tuple[tuple[int, int], ...]
    players: tuple[Player, ...]
    pulls: tuple[Pull, ...]

    @property
    def npc_count_map(self) -> Mapping[int, int]:
        """Enemy forces awarded per NPC game ID, as a read-only mapping."""
        return MappingProxyType(dict(self.npc_counts))

    @property
    def window_ms(self) -> tuple[int, int]:
        """The stretch of the log this run covers: first pull's start, last pull's end.

        The origin is the one `report/frame.py:run_start_ms` reports, so a
        death's elapsed time and the run's span are measured from the same
        point and cannot drift apart. Zero with no pulls, where the run has no
        clock of its own to offer.

        The end is computed through the span in whole seconds --
        `start + int((last_end - start) / 1000 * 1000)` -- rather than as
        `last_end` directly, which it is not always equal to: that round trip
        through a float is a millisecond short for about one integer in a
        hundred and twenty. Every reader of this window computed it that way
        before it was named here, and the only thing the window does is clip
        aura bands, so the arithmetic is preserved rather than corrected.
        Correcting it is a change of behaviour and belongs to a change that
        says so and tests it.
        """
        if not self.pulls:
            return (0, 0)
        start = min(pull.start_ms for pull in self.pulls)
        span_seconds = (max(pull.end_ms for pull in self.pulls) - start) / 1000
        return (start, start + int(span_seconds * 1000))

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


class DamageDoneSeries(Frozen):
    """One player's damage output over the run, in the buckets the API chose.

    `amounts` holds damage, never a rate: the response states damage per
    second and `build_damage_done` multiplies it back up at the adapter
    boundary, so nothing above it can print a figure section 5.5 refuses to
    produce. Bucket `i` covers `point_start_ms + i * interval_ms`.
    """

    actor_id: int
    point_start_ms: int
    interval_ms: float
    amounts: tuple[int, ...] = ()


class LoadedRun(Frozen):
    """Everything fetched about one run. Pure data — no adapter may leak into it."""

    run: Run
    casts: tuple[CastEvent, ...] = ()
    deaths: tuple[Death, ...] = ()
    enemy_cast_rows: tuple[EnemyCastRow, ...] = ()
    interrupts: tuple[InterruptEvent, ...] = ()
    enemy_deaths: tuple[EnemyDeath, ...] = ()
    damage_taken: tuple[DamageTakenEvent, ...] = ()
    # One graph call serves every player, so this carries the whole roster
    # however many are analysed. Fetched on the full profile only: no
    # comparison reads it.
    damage_done: tuple[DamageDoneSeries, ...] = ()
    # The three streams the death recap reads. Health samples come off the
    # player's own casts, healing is fetched per death, and resurrections are
    # fetched once for the whole fight.
    health_samples: tuple[HealthSample, ...] = ()
    healing: tuple[HealingEvent, ...] = ()
    resurrections: tuple[Resurrection, ...] = ()
    # Icon file names by ability game id, straight from the report's own ability
    # dictionary. A tuple of pairs, not a dict, so a LoadedRun stays immutable and
    # hashable; read it through ability_icon_map. A file name is data of the same
    # kind as an ability name, so carrying it performs no I/O.
    ability_icons: tuple[tuple[int, str], ...] = ()
    # Every roster player's own buff bands, as the aura table reports them. A
    # tuple rather than a dict for the same reason `ability_icons` is one: a
    # LoadedRun stays immutable and hashable. Empty when no aura table was
    # fetched, which is a report that draws no cover window rather than one
    # that draws a wrong window.
    auras: tuple[PlayerAuras, ...] = ()

    @property
    def players(self) -> tuple[Player, ...]:
        """Who was here, answered by the run itself.

        A recap reads a roster and does not care which kind of fight holds it,
        so both loaded aggregates answer this question in their own terms --
        see `domain/fight.py`. This one reads it off the run.
        """
        return self.run.players

    @property
    def window_ms(self) -> tuple[int, int]:
        """The stretch of the log this fight covers. `Run.window_ms` states it."""
        return self.run.window_ms

    @property
    def has_pulls(self) -> bool:
        """Whether this fight is cut into pulls. See `domain/fight.py`.

        A run whose log recorded none is as continuous as a boss fight, and a
        death card says the same thing about both: the elapsed time, with no
        pull named and none implied.
        """
        return bool(self.run.pulls)

    @property
    def ability_icon_map(self) -> Mapping[int, str]:
        """Icon file names by ability game id, as a read-only mapping."""
        return MappingProxyType(dict(self.ability_icons))

    @property
    def auras_by_actor(self) -> Mapping[int, PlayerAuras]:
        """Buff bands by actor id, as a read-only mapping."""
        return MappingProxyType({one.actor_id: one for one in self.auras})
