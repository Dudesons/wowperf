# ABOUTME: One real report read whole -- every boss and every pull -- from the live API.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

"""Report `cW38jmwdnZfbHVL4` holds twenty real people; see CLAUDE.md's test-data rule. Assert
on counts, shapes and uniqueness only, never on a name.

**The shape, verified live 2026-09-24.** `wowperf night cW38jmwdnZfbHVL4` reads the whole
report: 8 bosses and 19 boss fights, of which 16 are long enough to read as attempts -- the
other three are resets that `MIN_ATTEMPT_SECONDS` discards, one of them already recorded in
`tests/e2e/test_progression_e2e.py`'s own header from a 2026-09-16 read of the same report.
`PULLS_PER_BOSS` below is that read taken one level up: every boss's drawn pull count, in the
order `load_night` returns bosses, which is first appearance in the report's fight list. No
pull failed to deepen, so `withheld_pulls` is empty and the page shrank from the report by
nothing but those three resets.

**Cost, measured 2026-09-24 against a cold cache, at this test's own `--no-deaths` tier.** Two
runs of this very test, minutes apart, came to **118.17** and **106.01** points of 3600 -- 6.6
to 7.4 a pull. Both are cold: `tmp_path` is a fresh cache directory every run, so neither was
served anything from disk. The 12-point spread over ~97 calls is the per-query fraction drift
`.claude/skills/wcl-api/SKILL.md` already records under "Every query reports its own cost",
which is why the bound below is a bound and not an equality. What each run fetches is one
`Fights` query for the report's shape, then per attempt the deaths, damage-taken, enemy-cast,
interrupt, resurrection and damage-graph streams that every tier fetches. It is the cheapest of
the three rungs in the design's section 7 on purpose. At the default tier the same night costs
several times that --
see the README's quota table and `.claude/skills/wcl-api/SKILL.md` for the reading taken the
same day -- because a trimmed death card adds one `AuraTable` per roster player per pull, 320
of them on a sixteen-pull night with twenty raiders. A suite that spent an eighth of the hourly
budget per run would get quietly stopped from running, which is why the end-to-end tier is the
one that draws no card at all.

The two flags are therefore not interchangeable here, and `TIER` states which one this test
exercises: under `--no-deaths` every pull's tier is `"none"` and no death card, and so no
availability state, exists on the page at all. The states the design's section 7 protects --
`held` and `faded`, the refinement of a press by whether its aura was still up -- are a
property of the default tier, and this test would pass unchanged if every one of them broke.
What pins them is a live run at the default tier, reported once per plan rather than per suite
run.

**No comparison of any kind is drawn**, and that is the design rather than a gap in the fetch:
section 5 rules the parse axis out for this command (it is per player per boss, and across a
report would cost more than everything else put together), and no mechanics sample is fetched
either. `NOT_DRAWN_ID` is the page saying so once, in as many words, instead of leaving the
comparison families silently missing -- which is why this test counts that disclosure rather
than merely finding it.

**Verified live 2026-09-26.** The boss summaries this plan built draw on the same report: a
summary sits on exactly the two 2-pull bosses and the 7-pull boss, nowhere else, at the same
`--no-deaths` tier and the same cost as before -- summaries fetch nothing, being built from
streams every tier already reads. Each summary's control opens on its own `b{i}-summary`
option first, each summary's finding ids match what the command wrote for that boss in the
findings file, and each summary's own titles are drawn inside its own block and no other
boss's.
"""

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest
from markupsafe import escape
from typer.testing import CliRunner

from wowperf.adapters.config.toml import (
    load_consumables,
    load_defensives,
    load_externals,
    load_roles,
    load_self_resurrections,
)
from wowperf.cli import app, build_repository
from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.analysis.progression_service import analyse_progression
from wowperf.domain.analysis.severity import rank_raid_findings
from wowperf.domain.comparison.night_axis import NOT_DRAWN_ID
from wowperf.domain.report.night_build import build_night_report
from wowperf.domain.report.night_model import all_night_ledger_rows
from wowperf.domain.report.raid_model import RaidReport

REPORT_CODE = "cW38jmwdnZfbHVL4"

PULLS_PER_BOSS = (1, 2, 1, 1, 1, 1, 2, 7)
"""Drawn pulls per boss, in the order the report's fight list first named each boss.

Measured 2026-09-24, and not predicted: this tuple was first written as
`(2, 1, 3, 2, 1, 1, 7, 1)` from the fight counts recorded in
`tests/e2e/test_progression_e2e.py`'s header, and the live read disagreed on
both the order and three of the counts. `load_night` returns bosses in first
appearance order, which is not the sorted-encounter-id order that header lists
them in, and three fights across three bosses fall under
`MIN_ATTEMPT_SECONDS` rather than the one that header names for its own boss.

Pinned per boss rather than as a total, because a total is what a builder that
grouped every pull under the first boss would still get right: 16 pulls under
one boss and 16 under eight are the same sum. The run of 1s is not padding
either -- a night whose middle bosses were one-shot is exactly the shape that
hides an off-by-one in the grouping.
"""

DISCARDED = 3
"""Fights under `MIN_ATTEMPT_SECONDS`, across the whole report.

19 boss fights, 16 of them attempts. Asserted beside the pull counts so a floor
that discarded everything -- or nothing -- fails here rather than downstream,
where it would read as a night that simply had fewer pulls.
"""

TIER = "none"
"""The tier `--no-deaths` draws every pull at; see the header on why this suite runs there."""


@pytest.mark.e2e
def test_a_whole_report_reads_as_one_night(tmp_path: Path) -> None:
    """Eight bosses and sixteen pulls on one page, every one of them cardless.

    The cheap tier end to end: what the loader fetched, what the builder made
    of it, and what the command wrote -- against the real report rather than a
    fixture whose every pull was built to be identical.
    """
    repository = build_repository(tmp_path / "cache")

    before = repository.rate_limit().points_spent_this_hour
    night = repository.load_night(REPORT_CODE, None)

    # The report's own shape, before a single stream is deepened. Eight bosses,
    # each holding its own attempts -- `load_night` is the one read that says
    # how wide the night is, and everything below is priced off it.
    assert len(night.bosses) == len(PULLS_PER_BOSS)
    assert len({boss.encounter_id for boss in night.bosses}) == len(night.bosses), (
        "two bosses shared an encounter id"
    )
    assert tuple(len(boss.attempts) for boss in night.bosses) == PULLS_PER_BOSS
    assert sum(len(boss.discarded) for boss in night.bosses) == DISCARDED

    loaded = repository.load_night_attempts(
        night, deep_fights=frozenset(), death_cards=False
    )
    after = repository.rate_limit().points_spent_this_hour
    spent = after - before
    # Measured at 118.17 and 106.01 on two cold runs (see the header): six
    # streams a pull over sixteen pulls, plus the report's own `Fights` query.
    # The bound clears the higher of the two by enough not to fail on the
    # fractions the API moves between runs -- 12 points separated those two --
    # and is far tighter than the tier above it, which adds one `AuraTable` per
    # roster player per pull and lands in the hundreds.
    assert spent < 150, f"the cheap tier spent {spent:.2f} points, want under 150"
    # Windows gives the process a cp1252 stdout, and `-s` sends this straight to
    # it rather than through pytest's own capture, as the raid and report suites
    # already do with their own measurements. A run that spends real quota
    # should say what it spent: the figure in the header above is one day's
    # reading, and this is how the next one gets taken.
    print(f"night, --no-deaths, cold cache: {spent:.2f} points over {sum(PULLS_PER_BOSS)} pulls")

    # Nothing shrank quietly. A pull whose streams fail is dropped from its
    # boss and named in `failed_pulls`; on this report none does, so an empty
    # list here is the measurement rather than an untested default.
    assert loaded.failed_pulls == ()
    assert tuple(len(boss.attempts_with_events) for boss in loaded.loaded) == PULLS_PER_BOSS

    defensives, consumables, roles = load_defensives(), load_consumables(), load_roles()
    drawn = [attempt for boss in loaded.loaded for attempt in boss.attempts_with_events]
    findings_by_fight = {
        attempt.encounter.fight_id: analyse_encounter(
            attempt, defensives, consumables, roles=roles
        )
        for attempt in drawn
    }
    assert len(findings_by_fight) == sum(PULLS_PER_BOSS), "two pulls shared a fight id"

    report = build_night_report(
        loaded,
        findings_by_fight,
        "2026-09-24 00:00",
        defensives,
        consumables,
        roles,
        deep_fights=frozenset(),
        death_cards=False,
        findings_by_boss={
            boss.progression.encounter_id: tuple(rank_raid_findings(analyse_progression(boss)))
            for boss in loaded.loaded
        },
        externals=load_externals(),
        self_resurrections=load_self_resurrections(),
    )

    assert tuple(len(boss.pulls) for boss in report.bosses) == PULLS_PER_BOSS
    assert report.total_pulls == sum(PULLS_PER_BOSS)
    # A summary sits exactly where the pull counts say two or more: the two
    # 2-pull bosses and the 7-pull boss, and nowhere else.
    assert tuple(boss.summary is not None for boss in report.bosses) == tuple(
        count >= 2 for count in PULLS_PER_BOSS
    )
    for boss in report.bosses:
        for pull in boss.pulls:
            # Every pull is a whole raid report -- the reuse section 8 rests on.
            # A pull that lost it would be a tab group with nothing in it.
            assert isinstance(pull.report, RaidReport)
            assert pull.report.provenance is not None
            # Cardless, because this run asked for no cards. A pull fetched
            # without the cast stream and drawn with a card renders one with an
            # empty timeline and no explanation at all, which is the exact
            # mismatch one pair of values read in the command rules out.
            assert pull.tier == TIER
            assert pull.report.deaths == ()

    # Once for the page, not once per pull: sixteen copies of the same
    # paragraph is what a disclosure attached to the wrong layer looks like.
    ids = [row.finding_id for row in all_night_ledger_rows(report)]
    assert ids.count(NOT_DRAWN_ID) == 1

    # The command itself, over the cache the reads above already filled. Every
    # query it makes is warm, so this costs the two `RateLimit` reads it
    # brackets its own work with rather than a second night -- spent after
    # `after` was read, so outside the bound asserted above. Driving it rather
    # than re-rendering its parts is the point: which files the night lands in,
    # what the page is handed for icons, and the order the two writes happen in
    # are decided in `cli.night` and nowhere else.
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        [
            "night", REPORT_CODE,
            "--no-deaths",
            "--cache-dir", str(tmp_path / "cache"),
            "--out", str(out),
        ],
    )
    # Both halves of the diagnosis, as the raid and progression suites do: a
    # refusal the command wrote itself goes to stderr, an exception it never
    # expected is held on the result. Neither prints a roster.
    assert result.exit_code == 0, f"{result.stderr}\n{result.exception!r}"

    [written_json] = out.glob("*.night.json")
    [page] = out.glob("*.night.html")
    payload = cast(dict[str, Any], json.loads(written_json.read_text(encoding="utf-8")))
    html = page.read_text(encoding="utf-8")
    assert html.strip(), "the command wrote an empty page"

    # The findings file, against the same figures the loader gave above. What
    # was asked for is written out too, because a night where every pull was
    # cardless cannot be told from one where every card failed without it.
    assert payload["report_code"] == REPORT_CODE
    assert payload["bosses_counted"] == len(PULLS_PER_BOSS)
    assert payload["pulls_drawn"] == sum(PULLS_PER_BOSS)
    assert payload["withheld_pulls"] == []
    assert payload["asked_for"] == {
        "difficulty": None, "deep_fights": [], "death_cards": False
    }
    assert tuple(len(boss["pulls"]) for boss in payload["bosses"]) == PULLS_PER_BOSS

    # One boss control, and one pull control per boss -- the two-dropdown
    # design, over eight real bosses rather than the fixture's two. A page that
    # drew one control for the whole night, or one per pull, fails on the count.
    selects = re.findall(r"<select\b[^>]*>", html)
    assert len(selects) == 1 + len(report.bosses)
    assert sum("data-night-boss" in one for one in selects) == 1
    assert sum("data-night-pull" in one for one in selects) == len(report.bosses)

    # Every boss with a summary opens its own pull control on that summary --
    # the first option, so a fresh page and a boss change both land on it --
    # and the finding ids drawn on the summary section are exactly the ids the
    # findings file wrote for that boss: one findings object, two readers.
    for index, boss in enumerate(report.bosses):
        control = re.search(
            rf'<select id="night-pull-b{index}" data-night-pull>(.*?)</select>', html, re.S
        )
        assert control is not None
        first = re.search(r'<option value="([^"]+)"', control.group(1))
        assert first is not None
        if boss.summary is not None:
            assert first.group(1) == f"b{index}-summary"
            drawn_ids = set(re.findall(rf'id="b{index}-finding-([^"]+)"', html))
            written_ids = {finding["id"] for finding in payload["bosses"][index]["findings"]}
            assert drawn_ids == written_ids
        else:
            assert first.group(1).endswith("-pull"), "a single-pull boss opens on its pull"
            assert f'id="b{index}-summary"' not in html

    # Every one of a boss's finding titles, escaped as the page escapes them,
    # is drawn inside that boss's own summary block -- not merely somewhere on
    # the page, and not another boss's block, which the id check alone cannot
    # rule out: `analyse_progression` mints boss-agnostic ids
    # (`progression.best`, `.cluster`, `.movement`), so two different bosses'
    # findings can share an id set even though nothing else about them agrees.
    for index, boss in enumerate(report.bosses):
        if boss.summary is None:
            continue
        match = re.search(
            rf'<section class="pull" data-night-pull-panel id="b{index}-summary">.*?'
            r'(?=<section class="pull"|<section class="night-notes")',
            html,
            re.DOTALL,
        )
        assert match, f"boss {index}'s summary section is not on the page"
        block = match.group(0)
        for finding in payload["bosses"][index]["findings"]:
            assert str(escape(finding["title"])) in block

    # Every pull is its own tab group, across sixteen of them, plus one group
    # per boss summary: ids that collide send every button on the page to
    # whichever panel the browser picked first, and eight bosses is where a
    # scoping bug that survives two shows itself.
    groups = re.findall(r'<section class="panel" data-tab-panel="([^"]+)"', html)
    assert len(set(groups)) == report.total_pulls + sum(
        1 for boss in report.bosses if boss.summary
    )

    # One player card per raider, per pull. This page names its raiders, unlike
    # the progression page, whose own end-to-end test asserts that no roster
    # member appears on it: a night is a stack of `RaidReport`s, and a raid
    # report's Players tab is a card per player by construction. An assertion
    # borrowed from the progression suite was tried here first and failed on
    # the real report, correctly -- the two pages make opposite promises about
    # names, and only one of them can be pinned this way.
    #
    # Counted against each pull's own roster rather than against one figure for
    # the night. They agree on this report -- every attempt carries twenty
    # player rows -- but its own `size` does not: one boss reports 19 while its
    # attempts each carry 20, so `size` is the wrong denominator for a card
    # count and a literal 20 would hide that they can differ at all. A card
    # silently dropped, or an extra one minted, shows up here; a slug is read
    # off the page and never written into this file, on CLAUDE.md's test-data
    # rule.
    for attempt in drawn:
        fight_id = attempt.encounter.fight_id
        slugs = re.findall(
            rf'data-tab-panel="f{fight_id}-players" id="f{fight_id}-player-([^"]+)"', html
        )
        expected = len(attempt.encounter.players)
        assert expected, f"fight {fight_id} loaded with an empty roster"
        assert len(slugs) == expected, (
            f"fight {fight_id} drew {len(slugs)} player card(s) for a roster of {expected}"
        )
        assert len(set(slugs)) == expected, f"fight {fight_id} minted a slug twice"

    # No element id minted twice across the whole night. Sixteen pulls of
    # twenty real names is where a scoping bug that survives a two-pull fixture
    # shows itself, and a duplicate is invalid HTML that sends every pointer on
    # the page to whichever of the two the browser picked first. Same care the
    # raid suite takes: a player card's id carries a real slug, so a failure
    # reports a count and the families, never the ids -- `has_duplicates` is
    # asserted rather than the set itself so pytest's own introspection cannot
    # print one either.
    element_ids = re.findall(r'\sid="([^"]+)"', html)
    assert element_ids, "a page with no element ids would pass this vacuously"
    duplicates = {value for value in element_ids if element_ids.count(value) > 1}
    families = sorted({
        "player" if "-player-" in value else value.rsplit(".", 1)[0] for value in duplicates
    })
    has_duplicates = bool(duplicates)
    assert not has_duplicates, (
        f"{len(duplicates)} duplicate element id(s) across families {families}"
    )

    # No link back to the report. This page draws one group's own night and
    # never a corpus of anyone else's logs (RPGLogs terms SS5d).
    assert "warcraftlogs.com/reports/" not in html
