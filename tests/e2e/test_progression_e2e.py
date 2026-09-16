# ABOUTME: One real night of raid attempts, fetched from the live API, read as a series.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

"""Report `cW38jmwdnZfbHVL4` holds twenty real people; see CLAUDE.md's test-data rule. Assert
on counts, shapes and uniqueness only, never on a name.

**Encounter id, verified rather than assumed.**
`docs/plans/2026-09-16-progression-analysis-design.md` section 2.3 records an eight-attempt,
no-kill night on one boss in this report, with per-attempt boss-health-remaining and duration,
but names neither the boss nor its encounter id. Every task
before this one reused `3492` as a fixture value against synthetic data, where any integer works,
so it was not safe to assume that number named the right boss here.

Checked 2026-09-16 with one live query: `wowperf progression cW38jmwdnZfbHVL4` with no `--boss`
raised "This report holds several bosses (3420, 3421, 3429, 3445, 3455, 3470, 3492, 3497); pass
--boss" -- one `Fights` query, the whole report's fight list. (Its own price was not bracketed in
that run, since the command exits on the `ValueError` before printing one; a later, deliberately
bracketed run of the same query -- see the cost paragraph below -- read it at 2.01 points, and
nothing suggests this one differed.) Rereading that same response from a warm cache (free) for
each of the eight ids and comparing their attempts against section 2.3's table found exactly one
match: encounter `3492` is Ula'tek, difficulty 4,
size 20, `killed` False, 8 total fights (7 kept, 1 discarded under the 44.0s floor
`MIN_ATTEMPT_SECONDS` documents), with `fight_percentage`/duration in pull order --
64.81/215.7s, 85.80/105.9s, 16.49/480.0s, 85.40/110.0s, 87.65/88.0s, 53.30/278.8s, 55.65/227.0s,
100.0/15.8s -- matching section 2.3's table exactly, including the discarded 15.8s reset. This
also matches what `src/wowperf/domain/progression.py`'s own `MIN_ATTEMPT_SECONDS` docstring
already recorded about this report (nineteen fights across about eight bosses; the sum of every
boss's fight count found here is 2+1+3+2+1+1+8+1 = 19).

The same live read settled the two API-shape facts the design's section 2.1/2.2 leave
per-encounter: Ula'tek's `separates_wipes` is True, and `Report.phases` names four phases for it
(three stages and one intermission). Both happened to match this test's original draft, so
neither assertion below was corrected -- they are recorded here as verified, not as assumed.

**Measures design section 11 item 3, previously left open.** Every one of the 7 qualifying
attempts on this boss carries a `bossPercentage` reading, not only some -- so
`Progression.uses_boss_health` is True for this series and every finding reads on the boss-health
scale, not the encounter-progress one. That matters because design section 2.3's own table --
64.81, 85.80, 16.49, 85.40, 87.65, 53.30, 55.65, 100 -- is stated in `fightPercentage`
(confirmed above), and is *not* what this report's `bossPercentage` reads for the same eight
attempts: 59.25, 80.08, 23.15, 79.52, 82.68, 54.14, 50.92, 100.0, measured live 2026-09-16 against
the same fetch this test makes. The two scales diverge by 3 to 8 points on six of the eight
attempts, consistent with design section 2.4's general observation that they diverge sharply.

They agree, on this one series, about *which* attempt is deepest: fight 30 (16.49 fightPercentage,
23.15 bossPercentage) is the minimum on both scales, so section 2.3's headline claim -- the
deepest attempt is the third of eight, not the last -- holds regardless of which scale is read.
That agreement is this series' own property, not a general guarantee: a series where the two
scales ranked attempts differently would report a different "best" attempt depending on which one
`uses_boss_health` picked, and nothing rules that out for some other boss. The assertions below
pin the fight id, not just "not last", precisely so a future series where the two scales disagree
would be caught here rather than passing by the same luck `deepest is not attempts[-1]` used to
rely on.

Cost, measured 2026-09-16. This test calls `build_repository` and `load_progression` directly and
makes no quota-reading call of its own, so its only network cost is the one `Fights` query
`load_progression` sends. That query's own price -- 2.01 points -- was read from
`wowperf progression cW38jmwdnZfbHVL4 --boss 3492`'s own cost ledger, run twice directly against a
persisted cache directory the same way `test_raid_e2e.py`'s docstring measures its two commands:
cold (a cache directory that had never seen this report), it printed "Fights 1 call 2.01 points"
inside a total of 3.01 points spent (the extra 1.00 is that command's own opening quota read,
which this test never makes); re-run against the same, now-warm cache directory, it spent 1.00
point total with no `Fights` line at all -- the two `RateLimit` reads its quota check makes and
nothing else, because the report's `Fights` response was already on disk. So this test's own
marginal cost is 2.01 points against a cold `tmp_path` (its only possible state, since `tmp_path`
is a fresh directory every run) and would be 0.00 against a warm one. Both figures are
measurements, not the design's own 40-to-60-point projection for a *deepened* night: this test
stops at Layer 1, deepens no attempt, and so never approaches that projection's shape.
"""

from pathlib import Path

import pytest

from wowperf.cli import build_repository
from wowperf.domain.analysis.progression_service import analyse_progression
from wowperf.domain.analysis.severity import rank_raid_findings


@pytest.mark.e2e
def test_a_real_night_of_attempts_reads_as_a_series(tmp_path: Path) -> None:
    """The eight-attempt night measured 2026-09-16. No kill, deepest attempt third.

    Asserts the specific truth rather than a shape that would pass by luck:
    which fight is deepest, which scale the series reads on, and the figure
    the best-attempt finding actually prints -- not merely "not the last
    attempt", which a wrong implementation could satisfy on 6 of 7 qualifying
    attempts without being right.
    """
    repository = build_repository(tmp_path / "cache")

    progression = repository.load_progression("cW38jmwdnZfbHVL4", 3492, None)

    assert len(progression.attempts) + len(progression.discarded) == 8
    assert progression.killed is False
    # Every qualifying attempt on this boss carries a bossPercentage reading,
    # so the series reads on that scale throughout -- design section 11 item 3,
    # measured for the first time by this test.
    assert progression.uses_boss_health is True
    # The finding the whole design exists to get right, pinned by fight id
    # rather than merely "not the last one".
    assert progression.deepest is not None
    assert progression.deepest.fight_id == 30
    assert progression.deepest is not progression.attempts[-1]
    assert progression.separates_wipes is True
    assert len(progression.phases) == 4
    assert any(p.is_intermission for p in progression.phases)

    findings = rank_raid_findings(analyse_progression(progression))
    assert {f.id for f in findings} >= {
        "progression.best", "progression.cluster", "progression.movement"
    }
    assert len({f.id for f in findings}) == len(findings), "ids must be unique"

    best = next(f for f in findings if f.id == "progression.best")
    # 23.15 bossPercentage on fight 30, not section 2.3's 16.49 fightPercentage --
    # the two scales agree on which attempt is deepest here, not on its figure.
    assert "(boss health)" in best.title
    assert "23.1" in best.title
