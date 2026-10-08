# ABOUTME: End-to-end boss debuff uptime against the real Warcraft Logs API; no mocks.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.cli import build_repository
from wowperf.domain.auras import uptime_seconds_in
from wowperf.domain.comparison.boss_debuffs import boss_debuffs, boss_windows_of
from wowperf.domain.debuffs import pair_debuffs
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_keys_debuffs_on_its_bosses_close_before_the_key_ends(tmp_path: Path) -> None:
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

    # A boss that died has had its debuffs removed, so one still open on it when
    # the key ends is a pairing failure. The uptime bound above cannot see it:
    # clipping to the pull hides an interval that ran on to the fight's end.
    # The assertion bites only on a key where a pet's application and removal
    # carry different instance numbers on a measured boss, such as a Mage's
    # Mirror Image; a key without one passes under any pairing.
    measured = [w for w in boss_windows_of(run.pulls, log.npc_actors) if w.withheld is None]
    assert measured, "a real key has at least one boss pull with a single boss"
    boss_ids = {window.boss_game_id for window in measured}
    last_end = max(window.end_ms for window in measured)
    names = dict(log.ability_names)
    intervals, _ = pair_debuffs(log)
    left_open = [
        f"{names.get(one.ability_id, one.ability_id)} on game id {one.target_game_id}"
        for one in intervals
        if one.target_game_id in boss_ids
        and one.end_ms == log.end_ms
        and one.start_ms < last_end
    ]
    assert not left_open, f"debuffs left open on a measured boss to the key's end: {left_open}"
