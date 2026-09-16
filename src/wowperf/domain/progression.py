# ABOUTME: A night of attempts on one raid boss, and which of them a reader should be shown.
# ABOUTME: Selection is a claim about the log's shape, so the floor carries its measurement.

from collections.abc import Sequence

from wowperf.domain.base import Frozen
from wowperf.domain.encounter import Encounter
from wowperf.domain.phases import Phase

MIN_ATTEMPT_SECONDS = 44.0

_MIN_ATTEMPT_SECONDS_NOTE = """Under this an attempt is a reset or an instant
disaster rather than a pull whose depth says anything about the night.

Measured 2026-09-16 over the response cache on disk (349 distinct boss
attempts across 37 cached reports, keyed by (report code, fight id) so a
report cached across several paginated response files is not counted twice).
That population mixes Mythic+ dungeon bosses with raid bosses, which this
constant is not about, so the two were separated first. A Mythic+ fight
carries a keystoneLevel or a dungeonPulls list; a raid fight carries neither.
`difficulty` and `size` were not used to draw that line, because several
cached responses never requested those two fields at all, and their absence
would otherwise have been misread as "not a raid fight". One further fight
carried neither a keystoneLevel nor a dungeonPulls list but was still not a
raid attempt: a Delve final boss, at `difficulty: 108, size: 1`, which no
10-to-30-person raid roster could produce. It was excluded rather than
counted as one, on size alone. That leaves 99 raid attempts across 7 reports.

Duration alone does not separate a reset from a real attempt: the widest
gap in the sorted short tail, 14.31s between 26.70s and 41.01s, ranks only
14th of 98 gaps in the whole distribution, so a floor read off a duration
gap would be arbitrary. `fightPercentage` -- boss health remaining, counting
down from 100 -- is what a reset actually is: nothing happened. Of the four
shortest raid attempts (18.68s, 20.70s, 23.81s, 24.40s), none had
`fightPercentage` cached, but the two next-shortest did, and both are
unambiguous resets: 26.70s moved the boss 0.07 points, to 99.93% remaining,
and 41.01s moved it 2.67 points, to 97.33%. The next attempt by duration,
47.17s, moved it 12.14 points, to 87.86% remaining -- four to five times as
much progress for six more seconds of combat, and a real attempt even
though shallow. High `fightPercentage` alone does not mean reset, though: a
72.46s attempt read 95.32%, and the design's own probed night (report
`cW38jmwdnZfbHVL4`, see below) kept two attempts at 85.80% and 85.40%
remaining lasting 105.9s and 110.0s as real qualifying attempts. What marks
a reset is the combination this population shows only below 41.01s:
near-total health remaining *and* well under a minute of combat.

A second, independent population exists, and it does not appear in this
project's cache: an earlier session probed report `cW38jmwdnZfbHVL4` live
through a scratch cache directory that was never part of this checkout, so
its 349-attempt count above does not include it. That report holds
nineteen fights across about eight bosses (section 7.1's fight count and
section 2.3's phase note, both in
docs/plans/2026-09-16-progression-analysis-design.md). Section 2.3 tables
eight of those nineteen -- a full night on one boss -- and it is the source
of two readings: 15.8s at 100% remaining (that night's own shortest,
its attempt 8) and 88.0s at 87.65% remaining (its next-shortest, attempt
5). Section 4.3 adds that three attempts across the *whole* report ran
15.8s, 17.1s and 25.4s at or near 100% remaining. Only 15.8s is in the
eight-attempt table; 17.1s and 25.4s must belong to two of the other eleven
fights, on other bosses, whose durations the design records nowhere.

So the second population corroborates this one's reset side without
bounding its real-attempt side. 15.8s, 17.1s and 25.4s confirm the same
shape recurs across several bosses in that report -- a pull under a minute
that ends at or near full boss health is a reset, matching this
population's 26.70s and 41.01s. But 88.0s is only known to be the shortest
real attempt on the *one* boss section 2.3 tables; the other eleven fights'
durations were never recorded, so nothing rules out a shorter real attempt
existing among them. This population's own 41.01s-47.17s corridor --
26.70s and 41.01s as confirmed resets, 47.17s as a confirmed real attempt
-- is therefore self-sufficient and is what governs the floor below. One
attempt sits inside that corridor unresolved: 44.56s, on the same boss
(Sszorak) as the 47.17s real attempt and 2.6s short of it, with no
`fightPercentage` ever cached for it. Its true classification is unknown;
the floor set below does not depend on it.

44.0 sits near the midpoint of this population's 41.01s-47.17s corridor:
2.99s above the longest confirmed reset and 3.17s below the shortest
confirmed real attempt. It is a considered value rather than a guess, but
the corridor rests on two confirmed points on the reset side and one on
the real side, and it has not been checked against a real-attempt reading
shorter than 47.17s, nor against a third population. Call it provisional
in that sense, and revisit it if either turns up."""


def remaining_percent(encounter: Encounter, *, uses_boss_health: bool) -> float | None:
    """How much was left when the attempt ended, on the scale the whole series uses.

    `bossPercentage` is the boss's own health and `fightPercentage` is the
    encounter's progress. They diverge sharply -- one measured attempt read
    51.12 against 3.76 -- so pooling the two under one label would make that
    label true of only some of the figures it describes. Which scale a series
    uses is therefore decided once, for every attempt in it, by
    `Progression.uses_boss_health`, and passed in here rather than re-decided
    per attempt: a series where even one qualifying attempt lacks a boss
    reading reads entirely on `fightPercentage`, never a mix of the two.

    Both count down: a kill reads about 0.01 and an instant wipe reads 100.
    """
    if uses_boss_health:
        return encounter.boss_percentage
    return encounter.fight_percentage


class Progression(Frozen):
    """Every attempt at one boss, at one difficulty, from one report.

    `attempts` are the ones worth reading, in pull order. `discarded` are the
    ones below `MIN_ATTEMPT_SECONDS`, kept rather than dropped so the report can
    say how many were excluded instead of leaving a reader to wonder.

    Carries no external reference of any kind. The series compares attempts to
    each other, which is what makes the command an order of magnitude cheaper
    than a compared raid analysis.
    """

    report_code: str
    encounter_id: int
    boss_name: str
    difficulty: int
    size: int
    phases: tuple[Phase, ...] = ()
    separates_wipes: bool = False
    attempts: tuple[Encounter, ...] = ()
    discarded: tuple[Encounter, ...] = ()

    @property
    def killed(self) -> bool:
        return any(attempt.kill for attempt in self.attempts)

    @property
    def uses_boss_health(self) -> bool:
        """Whether this whole series reads as boss health rather than encounter progress.

        True only when every attempt in `attempts` carries a `bossPercentage`
        reading. The choice is all-or-nothing for the series: pooling a night
        where only some attempts carry one would put two different scales
        under a single label, so even one qualifying attempt without a boss
        reading falls the whole series back to `fightPercentage`. This is the
        one place that decision is made; `deepest` and every finding in
        `progression_service.py` read it from here rather than deciding it
        again, so they cannot drift apart.

        `discarded` attempts are not consulted: they are excluded from every
        figure the series reports, so they take no part in choosing which
        figure that is.
        """
        return bool(self.attempts) and all(a.boss_percentage is not None for a in self.attempts)

    @property
    def deepest(self) -> Encounter | None:
        """The attempt that got furthest -- least left, not last pulled.

        Measured 2026-09-16: on a real eight-attempt night the deepest was the
        third. Reading the last attempt as the best one is the single mistake
        this whole design exists to avoid.
        """
        uses_boss_health = self.uses_boss_health
        rated = [
            (remaining_percent(a, uses_boss_health=uses_boss_health), a) for a in self.attempts
        ]
        scored = [(left, a) for left, a in rated if left is not None]
        if not scored:
            return None
        return min(scored, key=lambda pair: pair[0])[1]


class LoadedProgression(Frozen):
    """A `Progression` and whichever attempts have been deepened.

    Layer 1 needs no deepened attempt at all, so `loaded` is empty here and
    stays that way until the plan that builds Layer 2.
    """

    progression: Progression
    loaded: tuple[object, ...] = ()


def build_progression(
    encounters: Sequence[Encounter],
    *,
    encounter_id: int,
    difficulty: int,
    phases: tuple[Phase, ...] = (),
    separates_wipes: bool = False,
) -> Progression:
    """Select one boss's attempts at one difficulty, in pull order.

    Difficulty is never mixed. A Heroic pull is not evidence about a Mythic one,
    and slice 2 already refuses that comparison for the same reason.
    """
    mine = [
        e for e in encounters
        if e.encounter_id == encounter_id and e.difficulty == difficulty
    ]
    mine.sort(key=lambda e: e.start_ms)
    kept = tuple(e for e in mine if e.duration_seconds >= MIN_ATTEMPT_SECONDS)
    dropped = tuple(e for e in mine if e.duration_seconds < MIN_ATTEMPT_SECONDS)
    first = mine[0] if mine else None
    return Progression(
        report_code=first.report_code if first else "",
        encounter_id=encounter_id,
        boss_name=first.boss_name if first else "",
        difficulty=difficulty,
        size=first.size if first else 0,
        phases=phases,
        separates_wipes=separates_wipes,
        attempts=kept,
        discarded=dropped,
    )
