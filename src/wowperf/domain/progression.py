# ABOUTME: A night of attempts on one raid boss, and which of them a reader should be shown.
# ABOUTME: Selection is a claim about the log's shape, so the floor carries its measurement.

MIN_ATTEMPT_SECONDS = 10.0

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
counted as one, on size alone.

That leaves 99 raid attempts across 7 reports. Sorted, the short tail runs
18.68s, 20.70s, 23.81s, 24.40s, 26.70s, 41.01s, 44.56s, 47.17s, 50.06s,
62.86s, 64.36s, 64.73s, 66.85s, 67.13s, 72.46s. Unlike MIN_PACK_SECONDS, this
population shows no empty stretch for the floor to fall through: the widest
gap in that short tail, 14.31s between 26.70s and 41.01s, ranks only 14th of
98 gaps in the full 99-attempt distribution, whose gaps run as high as
41.29s further up, among ordinary long attempts. Where a short attempt also
carried `fightPercentage`, several read at or near full boss health
remaining -- 99.93%, 97.33%, 90.89%, 90.93%, 90.24%, 90.28%, 95.32% -- which
is consistent with an early wipe but is not, on its own, a confirmed reset:
nothing in this sample is a reset the way MIN_PACK_SECONDS had six confirmed
segmentation artifacts to measure directly.

The floor is therefore provisional. It is chosen to sit under the shortest
attempt this population actually contains (18.68s), so that no attempt this
measurement found is misclassified, and to still be large enough to catch a
pull that resets within a few real-time seconds -- the failure mode this
constant exists to guard against -- rather than drawn from an observed gap,
because this population does not have one. Revisit it once a night's data
contains a confirmed reset to measure against."""
