# ABOUTME: End-to-end test against the real Warcraft Logs API; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.cli import build_repository
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_report_becomes_a_run(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this test"
        )

    code, fight = parse_report_url(REPORT)
    run = build_repository(tmp_path).get(code, fight)

    assert run.keystone_level > 0
    assert run.pulls, "a Mythic+ run should have dungeon pulls"
    assert len(run.players) == 5
    assert run.count_required > 0
