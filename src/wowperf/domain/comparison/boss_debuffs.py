# ABOUTME: One player's debuffs on each boss, rebuilt from the group's paired debuff intervals.
# ABOUTME: Covered seconds per boss, summed; a council's bosses each over their own life.

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from itertools import combinations

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace_boss import NpcActor, find_bosses, named_after
from wowperf.domain.debuffs import DebuffInterval, PairingTally
from wowperf.domain.model import Pull

Span = tuple[int, int]
"""A start and an end, in milliseconds of the log's clock."""

Target = tuple[int, ...]
"""What two owners' copies of a debuff are compared on: one target within one pull.

A boss is (window index, boss game id). An enemy's life is (game id, instance,
death ms), which names one life and so one pull. The two shapes differ in
length, so they never collide.
"""

Held = dict[tuple[int, int], dict[Target, list[Span]]]
"""Clipped spans keyed by (owner, ability id), then by the target they sat on."""

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

    The first is read off our own route: a boss pull may hold no enemy
    `bosses_of` can name. The last two are about the sample beside a figure of
    ours.
    """

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
    deathless: int = 0
    """Council bosses of a kill pull with no death inside it, measured to its end.

    A death counts from the pull's start, through its own span and up to the next
    pull's start, since the log stamps a kill's last death a few milliseconds after
    the pull closed.
    """

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
    reached: tuple[tuple[int, int], ...] = ()
    """(ability id, measured boss targets it covered for any time at all), for reach."""
    tally: PairingTally = PairingTally()
    shared_with: tuple[tuple[int, tuple[int, ...]], ...] = ()
    """(ability id, the other players' actor ids), for each debuff `find_shared` finds shared.

    It reads every target of the key, bosses and enemy lives alike.
    """

    @property
    def seconds(self) -> float:
        """The denominator: boss-alive seconds of the measured pulls, withheld ones left out."""
        return sum(window.seconds for window in self.windows if window.withheld is None)

    @property
    def deathless(self) -> int:
        """Council bosses of a kill pull that never died inside it, over every window."""
        return sum(window.deathless for window in self.windows)

    @property
    def targets(self) -> int:
        """Boss targets of the measured pulls: the Bosses stretch's lives, for reach."""
        return sum(len(window.targets) for window in self.windows if window.withheld is None)

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


class BossesFound(Frozen):
    """The game ids a boss pull is measured on, and whether they are a council's."""

    game_ids: tuple[int, ...]
    council: bool = False


def bosses_of(
    npc_actors: tuple[NpcActor, ...], enemy_ids: frozenset[int], pull_name: str
) -> BossesFound | Withheld:
    """The bosses a pull is measured on, or why it has none.

    Measured 2026-10-08: dungeon logs flag only some bosses as `Boss`, and a
    council's pull is named "A and B", which begins with A's name alone. So the
    pull's name is read first: split on " and " (never on a comma, which marks
    a title), each part names the pull's enemies that open with it, counted by
    game id because one enemy can be logged under two actor ids. A part naming
    two game ids is no boss. A pull named for several bosses is a council,
    measured on every one of them among its enemies, even one. One part with
    one game id is the boss. When the name matches no enemy, the boss flag is
    read as `find_bosses` reads it, also by game id: several flagged bosses are
    a council.
    """
    enemies = [one for one in npc_actors if one.actor_id in enemy_ids]
    parts = pull_name.split(" and ")
    named = [{one.game_id for one in enemies if named_after(one.name, part)} for part in parts]
    if any(len(game_ids) > 1 for game_ids in named):
        return Withheld.NO_BOSS
    found = sorted(set[int]().union(*named))
    if found:
        return BossesFound(game_ids=tuple(found), council=len(parts) > 1)
    flagged = sorted({one.game_id for one in find_bosses(npc_actors, enemy_ids, pull_name)})
    if not flagged:
        return Withheld.NO_BOSS
    return BossesFound(game_ids=tuple(flagged), council=len(flagged) > 1)


def boss_windows_of(
    pulls: Sequence[Pull],
    npc_actors: tuple[NpcActor, ...],
    deaths: tuple[tuple[int, int], ...] = (),
) -> tuple[BossWindow, ...]:
    """Every boss pull, with the bosses it is measured on, or the reason it has none.

    One boss is measured over the whole pull. A council's bosses are each
    measured from the pull's start to their last death in it, as below: the log
    records a death but never an appearance, so the start is the pull's. A
    council boss that never died there runs to the pull's end, and on a kill
    that is counted, since a killed council's bosses all died.

    A death is a pull's when it falls from the pull's start and either within
    the pull's own span, whatever pull follows, or before the next pull's start
    in `pulls`, which is in chronological order: the log stamps a kill's last
    death a few milliseconds after the pull closed. The span never runs past the
    pull's end.

    Warcraft Logs sometimes lists one physical boss pull twice, with the same
    encounter, start and end (measured 2026-10-08: 10 duplicated boss pulls in 5
    of 969 cached fights, all wipes). It is measured once, so its seconds and
    covered time are not counted twice. A duplicate of a pull, trash or boss, is
    never the next pull either, since it starts where this one does.
    """
    windows: list[BossWindow] = []
    previous: tuple[int, int, int] | None = None
    for position, pull in enumerate(pulls):
        if not pull.is_boss:
            continue
        listed = (pull.encounter_id, pull.start_ms, pull.end_ms)
        if listed == previous:
            continue
        previous = listed
        horizon = next(
            (
                later.start_ms
                for later in pulls[position + 1 :]
                if (later.start_ms, later.end_ms) != (pull.start_ms, pull.end_ms)
            ),
            None,
        )
        found = bosses_of(
            npc_actors, frozenset(enemy.actor_id for enemy in pull.enemies), pull.name
        )
        if isinstance(found, Withheld):
            windows.append(
                BossWindow(
                    encounter_id=pull.encounter_id,
                    name=pull.name,
                    start_ms=pull.start_ms,
                    end_ms=pull.end_ms,
                    withheld=found,
                )
            )
            continue
        targets: list[BossTarget] = []
        deathless = 0
        for game_id in found.game_ids:
            end_ms = pull.end_ms
            if found.council:
                died = [
                    at
                    for dead, at in deaths
                    if dead == game_id
                    and pull.start_ms <= at
                    and (at <= pull.end_ms or horizon is None or at < horizon)
                ]
                if died:
                    end_ms = min(max(died), pull.end_ms)
                elif pull.killed:
                    deathless += 1
            targets.append(BossTarget(game_id=game_id, start_ms=pull.start_ms, end_ms=end_ms))
        windows.append(
            BossWindow(
                encounter_id=pull.encounter_id,
                name=pull.name,
                start_ms=pull.start_ms,
                end_ms=pull.end_ms,
                targets=tuple(targets),
                deathless=deathless,
            )
        )
    return tuple(windows)


def held_on_bosses(
    windows: Sequence[BossWindow], intervals: Sequence[DebuffInterval], owners: frozenset[int]
) -> Held:
    """Every owner's spans on each measured boss, each clipped to that boss's span.

    The boss is matched by game id, for the same reason the pairing keys on it.
    """
    held: Held = {}
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
    return held


def bosses_held_by(
    windows: tuple[BossWindow, ...],
    held: Held,
    owner_id: int,
    ability_names: tuple[tuple[int, str], ...],
    tally: PairingTally,
    shared_with: tuple[tuple[int, tuple[int, ...]], ...],
) -> BossDebuffs:
    """One owner's figure on the measured bosses, from every owner's spans on them.

    A player's and their pets' copies on one boss are merged before they are
    counted, and a boss target reached for any time at all counts once.
    """
    covered: dict[tuple[int, int], int] = defaultdict(int)
    reached: dict[int, int] = defaultdict(int)
    for (owner, ability_id), by_target in held.items():
        if owner != owner_id:
            continue
        for (index, _), spans in by_target.items():
            covered[(windows[index].encounter_id, ability_id)] += length_ms(merged_spans(spans))
            reached[ability_id] += 1
    names = dict(ability_names)
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
        reached=tuple(sorted(reached.items())),
        tally=tally,
        shared_with=shared_with,
    )


def find_shared(
    held: Mapping[tuple[int, int], Mapping[Target, Sequence[Span]]], owner_id: int
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Each debuff this owner shares one slot of with other players, and who those are.

    `held` is every player's clipped spans on the measured targets, keyed by
    (owner, ability id) and then by target: a boss as (window index, boss game
    id), an enemy's life as (game id, instance, death ms). A debuff is
    exclusive when at least two owners held it and no two of them overlapped by
    more than `SHARED_OVERLAP_TOLERANCE_S` in total, the overlaps measured
    target by target and summed: a teammate's application replaced the one
    before it. Only owners who held it on a common target are compared: two
    copies that each kept to a different boss of a council, or to a different
    mob, never met, which shows nothing either way. Several owners holding it
    is not enough on its own, since copies of a per-caster debuff coexist.

    It is shared with this owner when it is exclusive and someone else held it.
    That includes a debuff this owner never held, once two others took it over
    from each other. Beside a single other owner, the overlap that would show
    exclusivity has no second owner to be measured against, so the debuff is
    not shared and its zero stays unjudged.
    """
    holders: dict[int, dict[int, dict[Target, list[Span]]]] = defaultdict(dict)
    for (owner, ability_id), by_target in held.items():
        holders[ability_id][owner] = {
            target: merged_spans(spans) for target, spans in by_target.items()
        }

    shared: list[tuple[int, tuple[int, ...]]] = []
    for ability_id in sorted(holders):
        owners = holders[ability_id]
        others = tuple(sorted(owner for owner in owners if owner != owner_id))
        pairs = [
            (first, second)
            for first, second in combinations(owners.values(), 2)
            if first.keys() & second.keys()
        ]
        exclusive = bool(pairs) and all(
            _overlap_ms(first, second) <= SHARED_OVERLAP_TOLERANCE_S * 1000
            for first, second in pairs
        )
        if exclusive and others:
            shared.append((ability_id, others))
    return tuple(shared)


def _overlap_ms(
    first: Mapping[Target, Sequence[Span]],
    second: Mapping[Target, Sequence[Span]],
) -> int:
    """The milliseconds two owners' copies of one debuff sat on the same target at once.

    Target by target, each alone less the two together is exactly the time
    counted twice; those are summed. Every edge is a whole millisecond, so it is
    exact.
    """
    return sum(
        length_ms(first[target])
        + length_ms(second[target])
        - length_ms(merged_spans([*first[target], *second[target]]))
        for target in first.keys() & second.keys()
    )


def merged_spans(spans: Iterable[Span]) -> list[Span]:
    """The spans, overlaps joined, in order."""
    merged: list[Span] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def length_ms(spans: Iterable[Span]) -> int:
    """The milliseconds the spans cover, summed as given."""
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
