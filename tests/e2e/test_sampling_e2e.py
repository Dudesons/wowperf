# ABOUTME: End-to-end sampled comparison against the real Warcraft Logs API; no mocks.
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
from wowperf.domain.analysis.roster import display_names
from wowperf.domain.comparison.sample import SAMPLE_SIZE
from wowperf.domain.comparison.service import ComparisonSubject, compare, find_player
from wowperf.domain.report.model import Provenance
from wowperf.domain.report.players import slugs_by_actor
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_run_fills_its_sample_and_states_a_quantifier(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    runs = build_repository(tmp_path)
    loaded = runs.load(code, fight)
    rankings, references = build_reference_repositories(runs.client, tmp_path)

    subject = find_player(loaded.run.players, loaded.run.owner_name or loaded.run.players[0].name)
    assert subject is not None, "the report owner should be in the roster"

    subject_slug = slugs_by_actor(loaded.run.players)[subject.actor_id]
    subject_name = display_names(loaded.run.players)[subject.actor_id]
    speed_sample, parse_samples, records = _samples(
        rankings,
        references,
        loaded.run,
        (RequestedPlayer(player=subject, slug=subject_slug, name=subject_name),),
    )
    parse_sample = parse_samples[subject.actor_id]

    # Both leaderboards for a real dungeon should hold enough eligible, non-self
    # candidates to fill the sample this project draws per axis.
    assert len(speed_sample.members) == SAMPLE_SIZE, (
        f"speed sample only filled to {len(speed_sample.members)} of {SAMPLE_SIZE}"
    )
    assert len(parse_sample.members) == SAMPLE_SIZE, (
        f"parse sample only filled to {len(parse_sample.members)} of {SAMPLE_SIZE}"
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
    assert findings, "no comparison findings were produced at all"

    # A quantifier is only stamped on a finding aggregated over the sample, so
    # its presence is the real proof that this run exercised the aggregate path
    # rather than falling back to a single pairwise reference.
    assert any(
        finding.quantifier for finding in findings
    ), "no finding carried a quantifier; the aggregate path may not have run"

    # `reference_records` is exactly what the report's provenance carries
    # forward unchanged (see `build_report`); wrapping it here exercises the
    # same type the page reads, not just the loose list `_samples` returned.
    provenance = Provenance(
        report_code=loaded.run.report_code,
        fight_id=loaded.run.fight_id,
        fetched_at="2026-09-08 00:00",
        references=records,
    )
    assert len(provenance.references) > 1, "provenance recorded one reference or none"
