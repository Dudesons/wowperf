# ABOUTME: One player's debuffs on each boss, rebuilt from the group's paired debuff intervals.
# ABOUTME: A single boss is measured over its own pull; a council or a missing boss is withheld.

from collections import defaultdict
from collections.abc import Mapping, Sequence
from enum import StrEnum
from itertools import combinations

from wowperf.domain.auras import Aura, AuraBand, uptime_seconds_in
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace_boss import NpcActor, find_bosses, named_after
from wowperf.domain.debuffs import DebuffLog, PairingTally, pair_debuffs
from wowperf.domain.model import Pull

SHARED_OVERLAP_TOLERANCE_S = 1.0
"""The most two players' copies of one debuff may overlap, in total, and still be one slot.

Measured 2026-10-08 on a cached key's 438s of measured boss time. Mortal Wounds,
one per target, was held by an Arms Warrior for 69.1% and a Windwalker Monk for
27.1% of it, and the two overlapped for 0.0s: each application replaced the
other's. Rune of Lingering, one per caster, was held by five players, and the
smallest overlap of any pair was 7.9s. One second sits above the first and well
below the second.
"""


class Withheld(StrEnum):
    """Why a boss, or one boss's cell, carries no figure.

    The first two are read off our own route: a council's bosses can die
    apart, which needs the alive-span inference this design defers, and a boss
    pull may hold no enemy `boss_game_id_of` can name. The last two are about the
    sample beside a figure of ours.
    """

    COUNCIL = "council"
    NO_BOSS = "no boss found"
    NOT_REACHED = "no reference measured this boss"
    TOO_FEW = "too few references"


class BossWindow(Frozen):
    """One boss pull, and the boss it is measured on, or why it is not."""

    encounter_id: int
    name: str
    start_ms: int
    end_ms: int
    boss_game_id: int | None = None
    withheld: Withheld | None = None

    @property
    def seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000


class BossDebuffs(Frozen):
    """One player's debuffs on the bosses of one run, as auras with bands.

    The `Aura` shape is the buff family's own, so the same arithmetic reads
    both: `uptime_seconds_in` merges overlapping bands, which is what keeps a
    player's and their pet's copies of one debuff from counting twice.
    """

    windows: tuple[BossWindow, ...] = ()
    auras: tuple[Aura, ...] = ()
    tally: PairingTally = PairingTally()
    shared_with: tuple[tuple[int, tuple[int, ...]], ...] = ()
    """(ability id, the other players' actor ids), for each debuff `shared_with` finds shared."""

    @property
    def measured(self) -> tuple[tuple[int, int], ...]:
        """The millisecond spans of the boss pulls a figure was drawn over."""
        return tuple(
            (window.start_ms, window.end_ms) for window in self.windows if window.withheld is None
        )

    @property
    def seconds(self) -> float:
        """The denominator: single-boss pull seconds, withheld pulls left out."""
        return sum(window.seconds for window in self.windows if window.withheld is None)


def boss_game_id_of(
    npc_actors: tuple[NpcActor, ...], enemy_ids: frozenset[int], pull_name: str
) -> int | Withheld:
    """The game id of a pull's one boss, or why it has none to measure.

    Measured 2026-10-08: dungeon logs flag only some bosses as `Boss`, and a
    council's pull is named "A and B", which begins with A's name alone. So the
    pull's name is read first: split on " and " (never on a comma, which marks
    a title), each part names the pull's enemies that open with it, counted by
    game id because one enemy can be logged under two actor ids. A part naming
    two game ids is no boss. Several parts with one named is a council. One
    part with one game id is the boss. When the name matches no enemy, the
    boss flag is read as `find_bosses` reads it, also by game id.
    """
    enemies = [one for one in npc_actors if one.actor_id in enemy_ids]
    parts = pull_name.split(" and ")
    named = [{one.game_id for one in enemies if named_after(one.name, part)} for part in parts]
    if any(len(game_ids) > 1 for game_ids in named):
        return Withheld.NO_BOSS
    if len(parts) > 1 and any(named):
        return Withheld.COUNCIL
    if named[0]:
        return next(iter(named[0]))
    flagged = {one.game_id for one in find_bosses(npc_actors, enemy_ids, pull_name)}
    if len(flagged) > 1:
        return Withheld.COUNCIL
    return next(iter(flagged), Withheld.NO_BOSS)


def boss_windows_of(
    pulls: Sequence[Pull], npc_actors: tuple[NpcActor, ...]
) -> tuple[BossWindow, ...]:
    """Every boss pull, with its one boss, or the reason it has none to measure.

    `boss_game_id_of` reads the pull's own enemies against the pull's name
    first and their boss flag second. One boss is measured. A council, or a
    pull named for several bosses, is withheld; so is a pull with no boss found.
    """
    windows: list[BossWindow] = []
    for pull in pulls:
        if not pull.is_boss:
            continue
        found = boss_game_id_of(
            npc_actors, frozenset(enemy.actor_id for enemy in pull.enemies), pull.name
        )
        boss_game_id, withheld = (None, found) if isinstance(found, Withheld) else (found, None)
        windows.append(
            BossWindow(
                encounter_id=pull.encounter_id,
                name=pull.name,
                start_ms=pull.start_ms,
                end_ms=pull.end_ms,
                boss_game_id=boss_game_id,
                withheld=withheld,
            )
        )
    return tuple(windows)


def boss_debuffs(
    log: DebuffLog, pulls: Sequence[Pull], owner_id: int, players: frozenset[int]
) -> BossDebuffs:
    """What this player, and their pets, kept on each measured boss of this run.

    The boss is matched by game id, for the same reason the pairing keys on it.
    Each interval is clipped to the pull it falls in.

    `players` is the actor ids of the run's players, the only owners whose
    debuffs `shared_with` reads: a pet is already folded into its owner by the
    pairing, and an enemy is never a player. A reference is read with none, so
    nothing on its side is ever shared.
    """
    windows = boss_windows_of(pulls, log.npc_actors)
    intervals, tally = pair_debuffs(log)
    names = dict(log.ability_names)
    owners = players | {owner_id}
    bands: dict[tuple[int, int], list[AuraBand]] = defaultdict(list)
    for window in windows:
        if window.withheld is not None:
            continue
        for one in intervals:
            if one.owner_id not in owners or one.target_game_id != window.boss_game_id:
                continue
            start_ms = max(one.start_ms, window.start_ms)
            end_ms = min(one.end_ms, window.end_ms)
            if end_ms > start_ms:
                bands[(one.owner_id, one.ability_id)].append(
                    AuraBand(start_ms=start_ms, end_ms=end_ms)
                )

    measured = tuple(
        (window.start_ms, window.end_ms) for window in windows if window.withheld is None
    )
    held = {
        (owner, ability_id): Aura(
            ability_id=ability_id,
            name=names.get(ability_id, f"Unknown ability {ability_id}"),
            total_uptime_ms=0,
            uses=len(found),
            bands=tuple(sorted(found, key=lambda band: band.start_ms)),
        )
        for (owner, ability_id), found in bands.items()
    }
    auras: list[Aura] = []
    for owner, ability_id in sorted(held):
        if owner != owner_id:
            continue
        aura = held[(owner, ability_id)]
        total_ms = round(uptime_seconds_in(aura, measured) * 1000)
        auras.append(aura.model_copy(update={"total_uptime_ms": total_ms}))
    return BossDebuffs(
        windows=windows,
        auras=tuple(auras),
        tally=tally,
        shared_with=shared_with(held, owner_id, measured),
    )


def shared_with(
    held: Mapping[tuple[int, int], Aura], owner_id: int, measured: tuple[tuple[int, int], ...]
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Each debuff this owner shares one slot of with other players, and who those are.

    `held` is every player's bands on the measured bosses, keyed by (owner,
    ability id), each with some time in it. A debuff is exclusive when at least
    two owners held it and no two of them overlapped by more than
    `SHARED_OVERLAP_TOLERANCE_S` in total: a teammate's application replaced
    the one before it. Several owners holding it is not enough on its own,
    since copies of a per-caster debuff coexist.

    It is shared with this owner when it is exclusive and someone else held it.
    That includes a debuff this owner never held, once two others took it over
    from each other. Beside a single other owner, the overlap that would show
    exclusivity has no second owner to be measured against, so the debuff is
    not shared and its zero stays unjudged.
    """
    holders: dict[int, dict[int, Aura]] = defaultdict(dict)
    for (owner, ability_id), aura in held.items():
        holders[ability_id][owner] = aura

    shared: list[tuple[int, tuple[int, ...]]] = []
    for ability_id in sorted(holders):
        auras = holders[ability_id]
        others = tuple(sorted(owner for owner in auras if owner != owner_id))
        exclusive = len(auras) >= 2 and all(
            _overlap_ms(first, second, measured) <= SHARED_OVERLAP_TOLERANCE_S * 1000
            for first, second in combinations(auras.values(), 2)
        )
        if exclusive and others:
            shared.append((ability_id, others))
    return tuple(shared)


def _overlap_ms(first: Aura, second: Aura, measured: tuple[tuple[int, int], ...]) -> int:
    """The milliseconds two owners' bands of one debuff sat on the bosses at once.

    Each alone, less the two together: `uptime_seconds_in` merges what overlaps,
    so the difference is exactly the time counted twice. Every band edge is a
    whole millisecond, so rounding removes only the float's own error.
    """
    both = first.model_copy(update={"bands": first.bands + second.bands})
    seconds = (
        uptime_seconds_in(first, measured)
        + uptime_seconds_in(second, measured)
        - uptime_seconds_in(both, measured)
    )
    return round(seconds * 1000)


def encounter_share(
    debuffs: BossDebuffs, ability_id: int, encounter_id: int
) -> float | Withheld | None:
    """The share of one boss's measured pulls this debuff was on it.

    A boss fought more than once, after a wipe, is summed over its measured
    pulls. `Withheld` when every pull of it was withheld, giving the first
    reason. None when this run fought no such boss at all.
    """
    pulls = [window for window in debuffs.windows if window.encounter_id == encounter_id]
    measured = [window for window in pulls if window.withheld is None]
    if not measured:
        return pulls[0].withheld if pulls else None
    seconds = sum(window.seconds for window in measured)
    if seconds <= 0:
        return None
    aura = next((one for one in debuffs.auras if one.ability_id == ability_id), None)
    if aura is None:
        return 0.0
    spans = tuple((window.start_ms, window.end_ms) for window in measured)
    return uptime_seconds_in(aura, spans) / seconds
