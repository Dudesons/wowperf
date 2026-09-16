# ABOUTME: A night of attempts on one raid boss, and which of them a reader should be shown.
# ABOUTME: Selection is a claim about the log's shape, so the floor carries its measurement.

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
