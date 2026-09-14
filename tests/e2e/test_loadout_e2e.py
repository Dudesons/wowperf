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
    # Checked across the whole roster, not just the first player: a
    # role-group-specific bug in `build_loadouts`'s tanks/healers/dps loop
    # would only show up on a player outside whichever group happens to be
    # first.
    loaded = a_loaded_report(tmp_path)
    assert loaded.run.players
    for player in loaded.run.players:
        assert player.loadout is not None
        assert len(player.loadout.items) == 18
        assert player.loadout.stats is not None
        assert player.loadout.stats.total_secondary() > 0


def test_a_real_loadout_counts_tier_pieces_in_the_plausible_range(tmp_path: Path) -> None:
    # `tier_pieces()` only counts items in the five TIER_SLOTS, so any single
    # player's count is bounded above by 5 no matter what the API returns --
    # that upper bound alone cannot fail and cannot catch a broken read. What
    # a broken read looks like on real data is `setID` coming back absent or
    # unreadable, in which case every player counts zero and the whole tier
    # family goes quiet without erroring. Measured 2026-09-14 across ten
    # players in two reports, real counts ran 4 or 5, never zero, so at least
    # one nonzero count across the roster is the property real data can
    # actually violate.
    loaded = a_loaded_report(tmp_path)
    counts = []
    for player in loaded.run.players:
        assert player.loadout is not None
        count = player.loadout.tier_pieces()
        assert 0 <= count <= len(TIER_SLOTS)
        counts.append(count)
    assert any(count > 0 for count in counts)
