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

Mechanics engaged (the default, no `--no-compare`), measured the same way: 16.22 points for the
kill, 39.22 for the wipe. Both add one `EncounterKillRankings` call (1.01 points) plus one
`AbilityTakenTable` call per report actually weighed -- our own report always, plus one per
reference kill whose size matched. The kill's own leaderboard page carried no row at our size 20
(its 50 rows ran 10 to 25, none of them 20), so only our own report's table was fetched: 14.21 +
1.01 + 1.00 = 16.22, exactly. The wipe's page offered two rows at size 20, so three tables were
fetched (39.22, against a naive 34.21 + 1.01 + 3.00 = 38.22; the two 34.21-shaped runs were
measured minutes apart against a cost the API does not document per query, so a one-point gap
between them is not chased further here).

Below the aggregate floor of three comparable members, a two-reference sample like the wipe's
still produces a finding -- stated as one reference, not an aggregate, per `too_few` in
`src/wowperf/domain/comparison/mechanics.py` -- while the kill's zero-reference sample produces
none. Both are real, current outcomes of `select_reference_kills`' size filter meeting this
report's own leaderboard, not a defect: see `.claude/skills/wcl-api/SKILL.md`, "`fightRankings`
echoes no `difficulty` per row" (2026-09-14), for why the filter matches size alone.
"""

import os
from pathlib import Path

import pytest

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.config.toml import load_consumables, load_defensives
from wowperf.adapters.wcl.encounter_rankings import WclEncounterRankingRepository
from wowperf.cli import (
    REFERENCE_CACHE_SECONDS,
    REFERENCE_CACHE_SUBDIR,
    _ability_taken,
    _mechanics_sample,
    build_repository,
)
from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.analysis.severity import SEVERITY_BY_FAMILY, UNKNOWN_SEVERITY, family_of
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
    repository = build_repository(tmp_path)
    loaded = repository.load_encounter(code, fight)

    # Rebuilds what `raid` passes to `analyse_encounter`: the reference sample
    # and our own report's ability-taken table, fetched the same way the
    # command does, so this test actually exercises the mechanics comparison
    # instead of defaulting it away.
    transient = DiskCache(
        tmp_path / REFERENCE_CACHE_SUBDIR, max_age_seconds=REFERENCE_CACHE_SECONDS
    )
    rankings = WclEncounterRankingRepository(repository.client, transient)
    mechanics_sample, _reference_records = _mechanics_sample(
        rankings, repository.client, transient, loaded.encounter
    )
    our_abilities, _ = _ability_taken(
        repository.client, repository.cache, loaded.encounter.report_code, loaded.encounter.fight_id
    )

    findings = analyse_encounter(
        loaded,
        load_defensives(),
        load_consumables(),
        mechanics=mechanics_sample,
        our_abilities=our_abilities,
    )

    assert loaded.encounter.kill is True
    assert loaded.encounter.duration_seconds > 0
    assert findings, "a real boss kill should produce at least one finding"
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
    assert len({finding.id for finding in findings}) == len(findings)

    leaked = [f.id for f in findings if f.id.startswith(KEYSTONE_SHAPED)]
    assert leaked == [], f"Mythic+ findings reached a raid report: {leaked}"

    severities = [SEVERITY_BY_FAMILY.get(family_of(f.id), UNKNOWN_SEVERITY) for f in findings]
    assert severities == sorted(severities), "findings are not ranked by severity first"

    # A comparable reference sample must actually have produced a finding, or
    # a real one that came back empty must be why there is none -- silence for
    # any other reason is exactly the gap this test guards against.
    mechanics_ids = [f.id for f in findings if f.id.startswith("mechanics.ability")]
    if mechanics_sample.members:
        assert mechanics_ids, "a loaded reference sample produced no mechanics finding"
    else:
        assert not mechanics_ids, "no reference sample loaded, but a mechanics finding exists"

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
    repository = build_repository(tmp_path)
    loaded = repository.load_encounter(code, fight)

    # See the matching comment in the kill test above: this rebuilds what
    # `raid` passes to `analyse_encounter` for the mechanics comparison.
    transient = DiskCache(
        tmp_path / REFERENCE_CACHE_SUBDIR, max_age_seconds=REFERENCE_CACHE_SECONDS
    )
    rankings = WclEncounterRankingRepository(repository.client, transient)
    mechanics_sample, _reference_records = _mechanics_sample(
        rankings, repository.client, transient, loaded.encounter
    )
    our_abilities, _ = _ability_taken(
        repository.client, repository.cache, loaded.encounter.report_code, loaded.encounter.fight_id
    )

    findings = analyse_encounter(
        loaded,
        load_defensives(),
        load_consumables(),
        mechanics=mechanics_sample,
        our_abilities=our_abilities,
    )

    assert loaded.encounter.kill is False
    assert loaded.encounter.outcome.startswith("wiped")
    assert findings, "an empty list is exactly the silent failure this slice guards against"
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
    assert loaded.casts, "no casts fetched for the wipe"

    leaked = [f.id for f in findings if f.id.startswith(KEYSTONE_SHAPED)]
    assert leaked == [], f"Mythic+ findings reached a raid report: {leaked}"

    severities = [SEVERITY_BY_FAMILY.get(family_of(f.id), UNKNOWN_SEVERITY) for f in findings]
    assert severities == sorted(severities), "findings are not ranked by severity first"

    # A wipe with no comparable reference kill is a real outcome, not a
    # failure -- assert the withholding, not a finding.
    mechanics_ids = [f.id for f in findings if f.id.startswith("mechanics.ability")]
    if mechanics_sample.members:
        assert mechanics_ids, "a loaded reference sample produced no mechanics finding"
    else:
        assert not mechanics_ids, "no reference sample loaded, but a mechanics finding exists"
