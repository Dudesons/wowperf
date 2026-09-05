# ABOUTME: End-to-end analysis against the real Warcraft Logs API; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.adapters.config.toml import (
    load_consumables,
    load_defensives,
    load_season_data,
    load_throughput_cooldowns,
)
from wowperf.cli import build_repository
from wowperf.domain.analysis.service import analyse
from wowperf.domain.findings import Confidence
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_run_produces_ranked_findings(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    loaded = build_repository(tmp_path).load(code, fight)
    findings = analyse(
        loaded, load_season_data(), load_defensives(), load_consumables(),
        load_throughput_cooldowns(),
    )

    assert findings, "a real run should produce at least one finding"
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
    assert len({finding.id for finding in findings}) == len(findings)

    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]
    assert timed == sorted(timed, reverse=True)

    # The streams the analysers depend on must have actually arrived.
    assert loaded.enemy_cast_rows, "no enemy casts fetched"
    assert loaded.damage_taken, "no damage-taken events fetched"
    assert loaded.enemy_deaths, "no enemy deaths fetched"

    # Sanity against the run itself: the residual cannot exceed the whole timer.
    residual = next(f for f in findings if f.id == "time.residual")
    assert residual.seconds_lost is not None
    assert abs(residual.seconds_lost) <= loaded.run.keystone_time_seconds
