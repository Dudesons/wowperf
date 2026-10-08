# ABOUTME: One player's debuffs on each boss, rebuilt from the group's paired debuff intervals.
# ABOUTME: A single boss is measured over its own pull; a council or a missing boss is withheld.

from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum

from wowperf.domain.auras import Aura, AuraBand, uptime_seconds_in
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace_boss import NpcActor, find_bosses
from wowperf.domain.debuffs import DebuffLog, PairingTally, pair_debuffs
from wowperf.domain.model import Pull


class Withheld(StrEnum):
    """Why a boss, or one boss's cell, carries no figure.

    The first two are read off our own route: a council's bosses can die
    apart, which needs the alive-span inference this design defers, and a boss
    pull may hold no enemy `find_bosses` can name. The last two are about the
    sample beside a figure of ours.
    """

    COUNCIL = "council"
    NO_BOSS = "no boss found"
    NOT_REACHED = "no reference reached this boss"
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


def boss_windows_of(
    pulls: Sequence[Pull], npc_actors: tuple[NpcActor, ...]
) -> tuple[BossWindow, ...]:
    """Every boss pull, with its one boss, or the reason it has none to measure.

    `find_bosses` reads the pull's own enemies, their boss flag and the pull's
    name. One boss is measured. Several are a council, withheld. None, which
    includes two named after the pull, is no boss found, withheld.
    """
    windows: list[BossWindow] = []
    for pull in pulls:
        if not pull.is_boss:
            continue
        bosses = find_bosses(
            npc_actors, frozenset(enemy.actor_id for enemy in pull.enemies), pull.name
        )
        boss_game_id = bosses[0].game_id if len(bosses) == 1 else None
        withheld = (
            None if len(bosses) == 1 else Withheld.COUNCIL if bosses else Withheld.NO_BOSS
        )
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


def boss_debuffs(log: DebuffLog, pulls: Sequence[Pull], owner_id: int) -> BossDebuffs:
    """What this player, and their pets, kept on each measured boss of this run.

    The boss is matched by game id, for the same reason the pairing keys on it.
    Each interval is clipped to the pull it falls in.
    """
    windows = boss_windows_of(pulls, log.npc_actors)
    intervals, tally = pair_debuffs(log)
    names = dict(log.ability_names)
    bands: dict[int, list[AuraBand]] = defaultdict(list)
    for window in windows:
        if window.withheld is not None:
            continue
        for one in intervals:
            if one.owner_id != owner_id or one.target_game_id != window.boss_game_id:
                continue
            start_ms = max(one.start_ms, window.start_ms)
            end_ms = min(one.end_ms, window.end_ms)
            if end_ms > start_ms:
                bands[one.ability_id].append(AuraBand(start_ms=start_ms, end_ms=end_ms))

    measured = tuple(
        (window.start_ms, window.end_ms) for window in windows if window.withheld is None
    )
    auras: list[Aura] = []
    for ability_id in sorted(bands):
        aura = Aura(
            ability_id=ability_id,
            name=names.get(ability_id, f"Unknown ability {ability_id}"),
            total_uptime_ms=0,
            uses=len(bands[ability_id]),
            bands=tuple(sorted(bands[ability_id], key=lambda band: band.start_ms)),
        )
        total_ms = round(uptime_seconds_in(aura, measured) * 1000)
        auras.append(aura.model_copy(update={"total_uptime_ms": total_ms}))
    return BossDebuffs(windows=windows, auras=tuple(auras), tally=tally)


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
