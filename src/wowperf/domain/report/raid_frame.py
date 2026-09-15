# ABOUTME: Builds the raid report's header: boss, difficulty by name, outcome, partition.
# ABOUTME: A sibling of the Mythic+ Header -- a boss fight has no dungeon or keystone level.

from wowperf.domain.base import Frozen
from wowperf.domain.encounter import Encounter

# Warcraft Logs' own difficulty numbers for a raid encounter. Neither
# `ReportFight` nor `worldData.encounter` echoes a name alongside the number
# (introspected 2026-09-15: `ReportFight`'s field list carries `difficulty`
# and nothing that names it; `Encounter`'s fields are `id, name,
# characterRankings, fightRankings, zone, journalID`, none of them a
# difficulty's name either). A name does exist one hop further out, on
# `Zone.difficulties` -- verified live the same day against
# `worldData.encounter(id: 3470).zone`, which named its own ids 5, 4, 3 and 1
# as Mythic, Heroic, Normal and LFR -- but reaching it needs a query this
# project does not otherwise make for a fight, so the mapping is hand-kept
# here and in `data/season.toml`'s `[raid.difficulty_names]`, dated the same
# day and against the same query. See `.claude/skills/wcl-api/SKILL.md` for
# the full note. A number this table does not carry prints as a number
# rather than a guess.
_DIFFICULTY_NAMES: dict[int, str] = {3: "Normal", 4: "Heroic", 5: "Mythic"}


class RaidHeader(Frozen):
    """The facts printed above a raid report's tabs.

    `Header` (`model.py`) carries a dungeon, a keystone level and affixes --
    none of which a boss fight has, which is why this is a type of its own
    rather than a reused field on that one.
    """

    boss: str
    difficulty: str
    outcome: str
    partition: str
    size: int


def build_raid_header(encounter: Encounter) -> RaidHeader:
    if encounter.kill:
        outcome = "Killed"
    else:
        outcome = f"Wiped at {encounter.fight_percentage:.1f}% remaining"
    difficulty = _DIFFICULTY_NAMES.get(encounter.difficulty, f"Difficulty {encounter.difficulty}")
    return RaidHeader(
        boss=encounter.boss_name,
        difficulty=difficulty,
        outcome=outcome,
        partition=f"Partition {encounter.partition}",
        size=encounter.size,
    )
