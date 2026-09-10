# ABOUTME: End-to-end comparison against the real Warcraft Logs API; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.cli import (
    RequestedPlayer,
    _samples,
    build_reference_repositories,
    build_repository,
)
from wowperf.domain.analysis.players import display_names
from wowperf.domain.comparison.reference import MAX_LEVEL_GAP
from wowperf.domain.comparison.service import ComparisonSubject, compare, find_player
from wowperf.domain.findings import Confidence
from wowperf.domain.report.players import slugs_by_actor
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_run_compares_against_real_leaderboards(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    runs = build_repository(tmp_path)
    loaded = runs.load(code, fight)
    rankings, references = build_reference_repositories(runs.client, tmp_path)

    subject = find_player(loaded.run, loaded.run.owner_name or loaded.run.players[0].name)
    assert subject is not None, "the report owner should be in the roster"

    # `load` fetches talent import codes, and nothing offline proves the live shape.
    assert any(
        player.talent_import_string for player in loaded.run.players
    ), "at least one player should carry a talent import string"

    subject_slug = slugs_by_actor(loaded.run)[subject.actor_id]
    subject_name = display_names(loaded.run)[subject.actor_id]
    speed_sample, parse_samples, records = _samples(
        rankings,
        references,
        loaded.run,
        (RequestedPlayer(player=subject, slug=subject_slug, name=subject_name),),
    )
    parse_sample = parse_samples[subject.actor_id]
    assert speed_sample.members, "the speed leaderboard should have a run for this dungeon"
    assert records, "no candidate was weighed at all"

    # The bracket convention is asserted inside the repository; this checks the
    # consequence a reader depends on, which is that we got the key we asked for.
    assert all(
        abs(member.row.keystone_level - loaded.run.keystone_level) <= MAX_LEVEL_GAP
        for member in speed_sample.members
    )

    findings = compare(
        loaded,
        speed_sample,
        (
            ComparisonSubject(
                player=subject,
                slug=subject_slug,
                display_name=subject_name,
                parse=parse_sample,
            ),
        ),
    )

    assert findings
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
    assert len({finding.id for finding in findings}) == len(findings)

    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]
    assert timed == sorted(timed, reverse=True)

    # The reference run must actually be the same dungeon we ran.
    top_speed = speed_sample.members[0]
    assert top_speed.run.encounter_id == loaded.run.encounter_id
    assert top_speed.run.pulls, "a reference with no pulls cannot be a route"
