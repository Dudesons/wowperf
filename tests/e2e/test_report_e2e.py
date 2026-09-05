# ABOUTME: End-to-end report rendering against a real run; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
import re
from pathlib import Path

import pytest

from wowperf.adapters.config.toml import load_defensives, load_season_data
from wowperf.adapters.render.html import render
from wowperf.cli import build_repository
from wowperf.domain.analysis.service import analyse
from wowperf.domain.report.build import build_report
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_run_renders_a_self_contained_report(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    loaded = build_repository(tmp_path).load(code, fight)
    findings = analyse(loaded, load_season_data(), load_defensives())

    html = render(build_report(loaded, findings, None, None, None, "2026-09-05 00:00"))

    # The report's one hard promise: it opens from disk, offline, forever. Checked by
    # what the page can execute or load, not by whether a URL string appears at all —
    # a link the reader may click and the SVG's own namespace both fetch nothing.
    assert "<script" not in html.lower()
    assert "@import" not in html.lower()
    assert "<link rel=" not in html.lower()
    for src in re.findall(r'src="([^"]*)"', html, flags=re.IGNORECASE):
        assert not src.startswith(("http://", "https://", "//")), src
    for href in re.findall(r'href="([^"]*)"', html):
        assert href.startswith("#") or href.startswith(
            "https://www.warcraftlogs.com/reports/"
        ), href

    # Real rosters carry non-ASCII names; the file must hold them.
    written = tmp_path / "report.html"
    written.write_text(html, encoding="utf-8")
    assert written.read_text(encoding="utf-8") == html

    # Every finding the analysis produced reaches the page exactly once. Anchored to
    # the row heading: a nested row quotes its parent's title in "Already counted
    # inside ...", which is a cross-reference, not a second copy of the parent's row.
    for finding in findings:
        assert html.count(f"<h3>{finding.title}</h3>") == 1, finding.id

    # Without a speed reference the timeline is withheld, and says so.
    assert "Aligned timeline" in html
