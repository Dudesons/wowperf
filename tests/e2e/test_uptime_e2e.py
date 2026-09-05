# ABOUTME: End-to-end aura uptime against the real Warcraft Logs API; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.cli import build_repository
from wowperf.domain.comparison.uptime import boss_windows
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_players_auras_come_back_with_usable_bands(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    runs = build_repository(tmp_path)
    loaded = runs.load(code, fight)
    subject = loaded.run.players[0]

    auras = runs.auras(loaded.run.report_code, loaded.run.fight_id, subject.actor_id)

    assert auras.actor_id == subject.actor_id
    assert auras.on_self, "a real player carries at least one buff"

    # Bands must be on the same clock as pulls, or every uptime figure is nonsense.
    windows = boss_windows(loaded.run)
    assert windows, "the reference report should contain boss pulls"
    earliest = min(band.start_ms for aura in auras.on_self for band in aura.bands)
    assert earliest >= 0
    assert earliest < max(end for _start, end in windows)

    # An aura cannot be up for longer than it exists.
    for aura in auras.on_self:
        spanned = sum(band.end_ms - band.start_ms for band in aura.bands)
        assert spanned <= aura.total_uptime_ms + 1, aura.name
