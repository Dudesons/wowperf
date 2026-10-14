# ABOUTME: The group ledger: completion time, deaths, downtime and kick share, run by run, counted.
# ABOUTME: These appear in every run whatever happened, so they are counted and never judged.

from collections.abc import Iterable, Sequence

from wowperf.domain.base import Frozen
from wowperf.domain.character.model import CharacterRun
from wowperf.domain.comparison.tempo import DURATION_WITHHELD_REASON


class GroupColumn(Frozen):
    """How many runs sat above, below or on the fast runs' median for one comparison."""

    above: int = 0
    below: int = 0
    level: int = 0
    compared: int = 0


class GroupLedger(Frozen):
    """The four group columns, and the character's own deaths counted by run.

    `time_withheld_reason` is set when any run's completion time was withheld
    for the keystone-level gap: those runs are left out of the time column, with
    the reason the tempo findings give.
    """

    time: GroupColumn
    deaths: GroupColumn
    downtime: GroupColumn
    kick_share: GroupColumn
    subject_died_in: int
    time_withheld_reason: str | None = None


def _count(pairs: Iterable[tuple[float, float]]) -> GroupColumn:
    above = below = level = 0
    for ours, theirs in pairs:
        if ours > theirs:
            above += 1
        elif ours < theirs:
            below += 1
        else:
            level += 1
    return GroupColumn(above=above, below=below, level=level, compared=above + below + level)


def group_ledger(runs: Sequence[CharacterRun]) -> GroupLedger:
    tempos = [run.tempo for run in runs if run.tempo is not None]
    time_withheld = any(t.their_time is None for t in tempos)
    return GroupLedger(
        time=_count(
            (t.our_time, their) for t in tempos if (their := t.their_time) is not None
        ),
        deaths=_count((float(t.our_deaths), t.their_deaths) for t in tempos),
        downtime=_count((t.our_downtime, t.their_downtime) for t in tempos),
        kick_share=_count(
            (ours, t.their_kick_share) for t in tempos if (ours := t.our_kick_share) is not None
        ),
        subject_died_in=sum(1 for run in runs if run.subject_deaths > 0),
        time_withheld_reason=DURATION_WITHHELD_REASON if time_withheld else None,
    )
