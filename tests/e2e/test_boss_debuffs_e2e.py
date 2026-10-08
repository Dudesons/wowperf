# ABOUTME: End-to-end boss debuff uptime against the real Warcraft Logs API; no mocks.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.cli import build_repository
from wowperf.domain.auras import uptime_seconds_in
from wowperf.domain.comparison.boss_debuffs import boss_debuffs
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_keys_debuffs_on_its_bosses_stay_inside_the_boss_pulls(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    runs = build_repository(tmp_path)
    run = runs.get(code, fight)
    log = runs.debuff_log(run.report_code, run.fight_id)

    assert log.events, "a real key applies debuffs to enemies"
    assert all(event.timestamp_ms <= log.end_ms for event in log.events)

    boss_pulls = [pull for pull in run.pulls if pull.is_boss]
    landed = 0
    for player in run.players:
        mine = boss_debuffs(log, run.pulls, player.actor_id)
        assert len(mine.windows) == len(boss_pulls)
        for aura in mine.auras:
            # An uptime cannot exceed the stretch it was measured over.
            assert uptime_seconds_in(aura, mine.measured) <= mine.seconds + 1e-9, aura.name
            landed += 1
    assert landed, "no player's debuff landed on any measured boss of this key"
