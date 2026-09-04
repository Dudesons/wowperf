# ABOUTME: End-to-end comparison against the real Warcraft Logs API; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.adapters.wcl.ranking_repository import WclRankingRepository
from wowperf.cli import build_repository
from wowperf.domain.comparison.reference import MAX_LEVEL_GAP, ParseReference, SpeedReference
from wowperf.domain.comparison.service import compare, find_player
from wowperf.domain.findings import Confidence
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_run_compares_against_real_leaderboards(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    runs = build_repository(tmp_path)
    loaded = runs.load(code, fight)
    rankings = WclRankingRepository(runs.client, runs.cache)

    subject = find_player(loaded.run, loaded.run.owner_name or loaded.run.players[0].name)
    assert subject is not None, "the report owner should be in the roster"

    # `load` fetches talent import codes, and nothing offline proves the live shape.
    assert any(
        player.talent_import_string for player in loaded.run.players
    ), "at least one player should carry a talent import string"

    speed_rows = rankings.fastest_runs(loaded.run.encounter_id, loaded.run.keystone_level)
    assert speed_rows, "the speed leaderboard should have a run for this dungeon"

    # The bracket convention is asserted inside the repository; this checks the
    # consequence a reader depends on, which is that we got the key we asked for.
    assert all(
        abs(row.keystone_level - loaded.run.keystone_level) <= MAX_LEVEL_GAP for row in speed_rows
    )

    parse_rows = rankings.top_parses(
        loaded.run.encounter_id, loaded.run.keystone_level, subject.class_name, subject.spec
    )

    speed = None
    for row in speed_rows:
        if (row.report_code, row.fight_id) != (loaded.run.report_code, loaded.run.fight_id):
            speed = row
            break
    assert speed is not None

    speed_reference = SpeedReference(row=speed, loaded=runs.load(speed.report_code, speed.fight_id))
    parse_reference = None
    if parse_rows:
        parse_row = parse_rows[0]
        parse_reference = ParseReference(
            row=parse_row, loaded=runs.load(parse_row.report_code, parse_row.fight_id)
        )

    findings = compare(loaded, subject, speed_reference, parse_reference)

    assert findings
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
    assert len({finding.id for finding in findings}) == len(findings)

    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]
    assert timed == sorted(timed, reverse=True)

    # Both reference runs must actually be the same dungeon we ran.
    assert speed_reference.loaded.run.encounter_id == loaded.run.encounter_id
    assert speed_reference.loaded.run.pulls, "a reference with no pulls cannot be a route"
