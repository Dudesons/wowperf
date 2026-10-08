# ABOUTME: One player's debuffs on each boss, rebuilt from the group's paired debuff intervals.
# ABOUTME: Covered seconds per boss target, summed; a council or a missing boss is withheld.

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from itertools import combinations

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace_boss import NpcActor, find_bosses, named_after
from wowperf.domain.debuffs import DebuffLog, PairingTally, pair_debuffs
from wowperf.domain.model import Pull

Span = tuple[int, int]
"""A start and an end, in milliseconds of the log's clock."""

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


class BossTarget(Frozen):
    """One boss of a measured pull, and the span its figure is drawn over."""

    game_id: int
    start_ms: int
    end_ms: int

    @property
    def seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000


class BossWindow(Frozen):
    """One boss pull, and the bosses it is measured on, or why it is not."""

    encounter_id: int
    name: str
    start_ms: int
    end_ms: int
    targets: tuple[BossTarget, ...] = ()
    withheld: Withheld | None = None

    @property
    def seconds(self) -> float:
        """Boss-alive seconds: each target's span, summed. A withheld pull has none."""
        return sum(target.seconds for target in self.targets)


class BossDebuffs(Frozen):
    """One player's debuffs on the bosses of one run, as seconds covered per boss.

    A player's and their pets' copies of one debuff on one boss are merged
    before they are counted, so a second is never counted twice on one boss.
    A second covered on two bosses at once counts on each: the figure is
    coverage, debuff-seconds over boss-alive seconds.
    """

    windows: tuple[BossWindow, ...] = ()
    covered: tuple[tuple[int, int, int], ...] = ()
    """(encounter id, ability id, milliseconds it covered that encounter's measured bosses)."""
    names: tuple[tuple[int, str], ...] = ()
    """(ability id, name), for every debuff in `covered`."""
    tally: PairingTally = PairingTally()
    shared_with: tuple[tuple[int, tuple[int, ...]], ...] = ()
    """(ability id, the other players' actor ids), for each debuff `find_shared` finds shared."""

    @property
    def seconds(self) -> float:
        """The denominator: boss-alive seconds of the measured pulls, withheld ones left out."""
        return sum(window.seconds for window in self.windows if window.withheld is None)

    def covered_seconds(self, ability_id: int, encounter_id: int | None = None) -> float:
        """Seconds this debuff covered the measured bosses, of one encounter or of all."""
        return (
            sum(
                ms
                for encounter, ability, ms in self.covered
                if ability == ability_id and (encounter_id is None or encounter == encounter_id)
            )
            / 1000
        )


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
        windows.append(
            BossWindow(
                encounter_id=pull.encounter_id,
                name=pull.name,
                start_ms=pull.start_ms,
                end_ms=pull.end_ms,
                targets=()
                if isinstance(found, Withheld)
                else (BossTarget(game_id=found, start_ms=pull.start_ms, end_ms=pull.end_ms),),
                withheld=found if isinstance(found, Withheld) else None,
            )
        )
    return tuple(windows)


def boss_debuffs(
    log: DebuffLog, pulls: Sequence[Pull], owner_id: int, players: frozenset[int]
) -> BossDebuffs:
    """What this player, and their pets, kept on each measured boss of this run.

    The boss is matched by game id, for the same reason the pairing keys on it.
    Each interval is clipped to the span of the boss it sat on.

    `players` is the actor ids of the run's players, the only owners whose
    debuffs `find_shared` reads: a pet is already folded into its owner by the
    pairing, and an enemy is never a player. A reference is read with none, so
    nothing on its side is ever shared.
    """
    windows = boss_windows_of(pulls, log.npc_actors)
    intervals, tally = pair_debuffs(log)
    owners = players | {owner_id}
    held: dict[tuple[int, int], dict[tuple[int, int], list[Span]]] = {}
    for index, window in enumerate(windows):
        for target in window.targets:
            for one in intervals:
                if one.owner_id not in owners or one.target_game_id != target.game_id:
                    continue
                start_ms = max(one.start_ms, target.start_ms)
                end_ms = min(one.end_ms, target.end_ms)
                if end_ms > start_ms:
                    by_target = held.setdefault((one.owner_id, one.ability_id), {})
                    by_target.setdefault((index, target.game_id), []).append((start_ms, end_ms))

    covered: dict[tuple[int, int], int] = defaultdict(int)
    for (owner, ability_id), by_target in held.items():
        if owner != owner_id:
            continue
        for (index, _), spans in by_target.items():
            covered[(windows[index].encounter_id, ability_id)] += _length_ms(_merged(spans))
    names = dict(log.ability_names)
    return BossDebuffs(
        windows=windows,
        covered=tuple(
            (encounter_id, ability_id, ms)
            for (encounter_id, ability_id), ms in sorted(covered.items())
        ),
        names=tuple(
            (ability_id, names.get(ability_id, f"Unknown ability {ability_id}"))
            for ability_id in sorted({ability_id for _, ability_id in covered})
        ),
        tally=tally,
        shared_with=find_shared(held, owner_id),
    )


def find_shared(
    held: Mapping[tuple[int, int], Mapping[tuple[int, int], Sequence[Span]]], owner_id: int
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Each debuff this owner shares one slot of with other players, and who those are.

    `held` is every player's clipped spans on the measured bosses, keyed by
    (owner, ability id) and then by (window index, boss game id). A debuff is
    exclusive when at least two owners held it and no two of them overlapped by
    more than `SHARED_OVERLAP_TOLERANCE_S` in total, the overlaps measured
    boss by boss and summed: a teammate's application replaced the one before
    it. Several owners holding it is not enough on its own, since copies of a
    per-caster debuff coexist.

    It is shared with this owner when it is exclusive and someone else held it.
    That includes a debuff this owner never held, once two others took it over
    from each other. Beside a single other owner, the overlap that would show
    exclusivity has no second owner to be measured against, so the debuff is
    not shared and its zero stays unjudged.
    """
    holders: dict[int, dict[int, dict[tuple[int, int], list[Span]]]] = defaultdict(dict)
    for (owner, ability_id), by_target in held.items():
        holders[ability_id][owner] = {target: _merged(spans) for target, spans in by_target.items()}

    shared: list[tuple[int, tuple[int, ...]]] = []
    for ability_id in sorted(holders):
        owners = holders[ability_id]
        others = tuple(sorted(owner for owner in owners if owner != owner_id))
        exclusive = len(owners) >= 2 and all(
            _overlap_ms(first, second) <= SHARED_OVERLAP_TOLERANCE_S * 1000
            for first, second in combinations(owners.values(), 2)
        )
        if exclusive and others:
            shared.append((ability_id, others))
    return tuple(shared)


def _overlap_ms(
    first: Mapping[tuple[int, int], Sequence[Span]],
    second: Mapping[tuple[int, int], Sequence[Span]],
) -> int:
    """The milliseconds two owners' copies of one debuff sat on the same boss at once.

    Boss by boss, each alone less the two together is exactly the time counted
    twice; those are summed. Every edge is a whole millisecond, so it is exact.
    """
    return sum(
        _length_ms(first[target])
        + _length_ms(second[target])
        - _length_ms(_merged([*first[target], *second[target]]))
        for target in first.keys() & second.keys()
    )


def _merged(spans: Iterable[Span]) -> list[Span]:
    """The spans, overlaps joined, in order."""
    merged: list[Span] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _length_ms(spans: Iterable[Span]) -> int:
    return sum(end - start for start, end in spans)


def encounter_share(
    debuffs: BossDebuffs, ability_id: int, encounter_id: int
) -> float | Withheld | None:
    """The share of one encounter's boss-alive seconds this debuff covered.

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
    return debuffs.covered_seconds(ability_id, encounter_id) / seconds
