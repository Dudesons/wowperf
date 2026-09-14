# ABOUTME: One real raid fight, fetched from the live API, analysed end to end.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

"""Measured 2026-09-14 against report cW38jmwdnZfbHVL4, a fresh cache directory each time,
using `WclRunRepository.load_encounter` as this module's two tests call it.

- The kill (a boss with zero deaths): 14.21 points -- under the 20-point guess in
  `docs/plans/2026-09-14-raid-foundation-plan.md`.
- The wipe (a boss with 21 deaths across the raid): 34.21 points -- over that guess.

The gap is not noise: `WclRunRepository.load_encounter` fetches one `HEALING_QUERY` per
healing window, and a healing window is opened per death (see the comment above that loop
in `src/wowperf/adapters/wcl/repository.py`). The kill's `Deaths` query returned zero rows,
so no healing window ever opened and no `Healing` line appears in the command's own
breakdown. The wipe's did open 21, one per healing query, and each cost a full point. A
cold raid load's cost therefore scales with how many players died in the fight, not with a
fixed per-fight overhead -- so "under 20" is not a safe claim for a chaotic wipe, only for a
clean kill. Both numbers came from `uv run wowperf raid <code> --fight <id> --cache-dir
<fresh>`, read from the command's own "Rate limit: ... points spent" line.
"""

import os
from pathlib import Path

import pytest

from wowperf.adapters.config.toml import load_consumables, load_defensives
from wowperf.cli import build_repository
from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.findings import Confidence
from wowperf.urls import parse_report_url

KILL = os.environ.get("WOWPERF_E2E_RAID_KILL", "")
WIPE = os.environ.get("WOWPERF_E2E_RAID_WIPE", "")

# Findings a boss fight cannot support. Slice 1 emits all four; if one reaches a
# raid report, an analyser is reading an aggregate that has no such thing and
# answering zero rather than abstaining.
KEYSTONE_SHAPED = ("time.", "trash.", "compare.route", "compare.downtime")


@pytest.mark.e2e
def test_a_real_boss_kill_produces_ranked_findings(tmp_path: Path) -> None:
    if not KILL:
        pytest.fail(
            "Set WOWPERF_E2E_RAID_KILL to a public report URL naming a boss kill "
            "(include the #fight=N fragment) to run this"
        )

    code, fight = parse_report_url(KILL)
    loaded = build_repository(tmp_path).load_encounter(code, fight)
    findings = analyse_encounter(loaded, load_defensives(), load_consumables())

    assert loaded.encounter.kill is True
    assert loaded.encounter.duration_seconds > 0
    assert findings, "a real boss kill should produce at least one finding"
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
    assert len({finding.id for finding in findings}) == len(findings)

    leaked = [f.id for f in findings if f.id.startswith(KEYSTONE_SHAPED)]
    assert leaked == [], f"Mythic+ findings reached a raid report: {leaked}"

    # The streams the analysers depend on must have actually arrived, or every
    # assertion above holds over an empty list and proves nothing.
    assert loaded.casts, "no casts fetched"
    assert loaded.damage_taken, "no damage taken fetched"


@pytest.mark.e2e
def test_a_real_wipe_is_analysed_rather_than_refused(tmp_path: Path) -> None:
    if not WIPE:
        pytest.fail(
            "Set WOWPERF_E2E_RAID_WIPE to a public report URL naming a wiped attempt "
            "(include the #fight=N fragment) to run this"
        )

    code, fight = parse_report_url(WIPE)
    loaded = build_repository(tmp_path).load_encounter(code, fight)
    findings = analyse_encounter(loaded, load_defensives(), load_consumables())

    assert loaded.encounter.kill is False
    assert loaded.encounter.outcome.startswith("wiped")
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
    assert loaded.casts, "no casts fetched for the wipe"
