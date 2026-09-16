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

Cost. Layer 1 alone costs the 2.01-point `Fights` query documented above, itself measured against
a cold cache -- this test's `tmp_path` is fresh every run, so it is always cold in that sense.
`load_progression_attempts` adds one deaths stream and one damage-taken stream per qualifying
attempt on top of that; its own docstring estimates about 1.00 point per stream, so this night's
seven qualifying attempts add roughly fourteen points to the `Fights` query's 2.01. That combined,
cold-cache figure is not the same measurement as a warm-cache run of the same two calls -- one
where the report's `Fights` response is already on disk, as a repeated CLI invocation against a
persisted cache directory would be, paying nothing for it a second time -- so a lower point count
measured that way is a different scenario, not a contradiction. Rather than pin an exact figure
for either case here, the test reads `repository.rate_limit()` itself, once before
`load_progression` and once after `load_progression_attempts`, and asserts the gap stays under 40
points. That is loose relative to the roughly 18-point cold cost above: a stray third stream per
attempt would land near 25 and even a whole `Casts` stream near 36, both still under 40, so this
bound does not catch one unnoticed extra stream --
`test_sends_only_deaths_and_damage_taken_per_attempt` proves that narrower claim offline instead,
by counting operations directly. What the 40-point bound catches here is a wholesale change in
shape against the real API: doubling every stream, or refetching the whole night a second time,
the kind of drift that would blow past it rather than nudge it.
"""

import re
from pathlib import Path
from statistics import median

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

    before = repository.rate_limit().points_spent_this_hour
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

    # Layer 2 reads the deepened attempts `load_progression_attempts` fetches;
    # see the cost note above for what that spends on top of Layer 1's `Fights`
    # query.
    series = repository.load_progression_attempts(progression)
    after = repository.rate_limit().points_spent_this_hour
    spent = after - before
    assert spent < 40, f"the whole command spent {spent:.2f} points, want under 40"

    findings = rank_raid_findings(analyse_progression(series))
    assert {f.id for f in findings} >= {
        "progression.best", "progression.cluster", "progression.movement",
        "progression.collapse", "progression.repeat.phase",
    }
    assert len({f.id for f in findings}) == len(findings), "ids must be unique"

    best = next(f for f in findings if f.id == "progression.best")
    # 23.15 bossPercentage on fight 30, not section 2.3's 16.49 fightPercentage --
    # the two scales agree on which attempt is deepest here, not on its figure.
    assert "(boss health)" in best.title
    assert "23.1" in best.title

    # Seven attempts deepened (fight ids 28-34); fight 35 was discarded at
    # 15.8s and never reaches `load_progression_attempts`. A wrong filter --
    # deepening a discarded attempt, or dropping a qualifying one -- shows up
    # as a count other than 7.
    assert len(series.attempts_with_events) == 7

    # The night's shortest qualifying attempt is 88 seconds -- long enough
    # that an attempt with zero damage-taken rows means a stream came back
    # empty, not that nothing happened during it.
    for loaded in series.attempts_with_events:
        assert loaded.damage_taken, (
            f"fight {loaded.encounter.fight_id} deepened with no damage-taken rows"
        )

    # A collapse window is the tail of an attempt -- from its first death to
    # its end -- never the whole of it. Bounding the median only by the
    # longest attempt's duration is too loose to prove that: an anchor bug
    # that started the window at the attempt's start instead of its first
    # death would make every window equal that attempt's own duration, and
    # the median of seven real durations still sits comfortably under the
    # longest one. Bounding it by the *median* attempt duration instead closes
    # that gap -- under the anchor bug the collapse-median and the
    # attempt-duration median are computed from the same set of numbers, so
    # they would be equal and the strict "<" below would fail exactly when
    # the bug is present.
    collapse_finding = next(f for f in findings if f.id == "progression.collapse")
    collapse_match = re.search(r"median of (\d+) seconds", collapse_finding.title)
    assert collapse_match is not None, collapse_finding.title
    collapse_median = float(collapse_match.group(1))
    median_attempt_seconds = median(a.duration_seconds for a in progression.attempts)
    assert 0 < collapse_median < median_attempt_seconds, (
        f"collapse median {collapse_median}s not below median attempt duration "
        f"{median_attempt_seconds}s"
    )

    # Phases 1 and 2 tie at three attempts each (measured 2026-09-16, encounter
    # 3492 reports `separatesWipes: true` with four phases); `repeat_phase`
    # names every phase tied for the top count rather than picking one.
    # Asserting the count both sides of that tie share -- 3 of the 7 attempts
    # that carried a phase -- exercises the counting a wrong implementation
    # could get wrong (a miscount, or excluding an attempt that does carry a
    # phase) without pinning the exact wording of which phases get named.
    phase_finding = next(f for f in findings if f.id == "progression.repeat.phase")
    assert phase_finding.title.startswith("3 of 7 attempts ended in "), phase_finding.title

    # The report holds twenty real people (CLAUDE.md's test-data rule): read
    # the roster back from the loaded progression itself, rather than listing
    # a name here, and check that no finding's title, detail, evidence, facts,
    # ability name or player slug -- the free-text fields a name could
    # plausibly land in, unlike `id` and `quantifier`, which are fixed machine
    # strings no player name could reach -- repeats one. A finding that names
    # a player -- say, by building a detail string from `Player.name` instead
    # of `.spec`/`.class_name` -- would be caught here. Matched on a word
    # boundary rather than a bare substring, so
    # a short roster name does not raise a false alarm just because it happens
    # to sit inside an unrelated word of ordinary finding prose.
    roster_names = {
        player.name
        for attempt in (*progression.attempts, *progression.discarded)
        for player in attempt.players
    }
    assert roster_names, "the fixture roster should not be empty"
    roster_patterns = [re.compile(rf"\b{re.escape(name)}\b") for name in roster_names]
    for finding in findings:
        haystack = " ".join(
            (
                finding.title,
                finding.detail,
                finding.ability_name,
                finding.player_slug,
                *finding.evidence,
                *(fact.label for fact in finding.facts),
                *(fact.value for fact in finding.facts),
            )
        )
        for pattern in roster_patterns:
            assert pattern.search(haystack) is None, f"finding {finding.id} named a roster member"
