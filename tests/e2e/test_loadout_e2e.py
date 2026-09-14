# ABOUTME: End-to-end: a real report's loadouts, against the live API, no mocks.
# ABOUTME: Spends quota. Marked e2e so the offline gate never runs it.

import os
from pathlib import Path

import pytest

from wowperf.cli import build_repository
from wowperf.domain.loadout import TIER_SLOTS
from wowperf.domain.model import LoadedRun
from wowperf.urls import parse_report_url

pytestmark = pytest.mark.e2e

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


def a_loaded_report(tmp_path: Path) -> LoadedRun:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )
    code, fight = parse_report_url(REPORT)
    return build_repository(tmp_path).load(code, fight)


def test_every_player_in_a_real_report_gets_a_loadout(tmp_path: Path) -> None:
    loaded = a_loaded_report(tmp_path)
    assert loaded.run.players
    assert all(player.loadout is not None for player in loaded.run.players)


def test_a_real_loadout_carries_eighteen_slots_and_a_stat_block(tmp_path: Path) -> None:
    loaded = a_loaded_report(tmp_path)
    player = loaded.run.players[0]
    assert player.loadout is not None
    assert len(player.loadout.items) == 18
    assert player.loadout.stats is not None
    assert player.loadout.stats.total_secondary() > 0


def test_a_real_loadout_counts_tier_pieces_in_the_plausible_range(tmp_path: Path) -> None:
    # Measured 2026-09-14: real counts ran 4 or 5. A count above 5 means the
    # slot rule folded a non-tier set in, which is the defect this guards.
    loaded = a_loaded_report(tmp_path)
    for player in loaded.run.players:
        assert player.loadout is not None
        assert 0 <= player.loadout.tier_pieces() <= len(TIER_SLOTS)
