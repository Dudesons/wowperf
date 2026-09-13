# ABOUTME: End-to-end comparison against the real Warcraft Logs API; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from tests.domain.comparison.test_tables import RATE_FAMILIES, fact_value, stretch_of
from wowperf.cli import (
    RequestedPlayer,
    _fetch_parse_auras,
    _samples,
    build_reference_repositories,
    build_repository,
)
from wowperf.domain.analysis.players import display_names
from wowperf.domain.comparison.reference import MAX_LEVEL_GAP
from wowperf.domain.comparison.service import ComparisonSubject, compare, find_player
from wowperf.domain.comparison.tables import comparison_measures
from wowperf.domain.comparison.trash_spells import aligned_trash
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


@pytest.mark.e2e
def test_a_real_run_compares_trash_packs_against_real_parses(tmp_path: Path) -> None:
    """The offline fixtures cut every pull by hand. Only a real run exercises the
    sweep-back in align_pulls, which is where the denominator defect would live."""
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

    subject_slug = slugs_by_actor(loaded.run)[subject.actor_id]
    subject_name = display_names(loaded.run)[subject.actor_id]
    speed_sample, parse_samples, _records = _samples(
        rankings,
        references,
        loaded.run,
        (RequestedPlayer(player=subject, slug=subject_slug, name=subject_name),),
    )
    parse_sample = parse_samples[subject.actor_id]
    assert parse_sample.members, "the score leaderboard should have a parse for this spec"

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

    trash = [f for f in findings if f.id.startswith("compare.spells.trash.")]
    assert trash, "a real run shared no trash with any reference, which needs investigating"

    for finding in trash:
        assert finding.confidence is Confidence.DERIVED
        assert finding.seconds_lost is None
        assert finding.player_slug == subject_slug

    rates = [f for f in trash if ".rate." in f.id]
    for rate in rates:
        # The pack count in the title is the claim this family's honesty rests on.
        assert "aligned pack" in rate.title

    # The denominator the rows were drawn from, recomputed here against the same
    # references: a real route is where one chain-pulled stretch of ours picks up
    # several counterparts, and our seconds must never exceed the trash we ran.
    our_trash = sum(
        pull.duration_seconds
        for pull in loaded.run.pulls
        if not pull.is_boss and pull.is_a_pack
    )
    for member in parse_sample.members:
        aligned = aligned_trash(loaded.run, member.run)
        assert aligned.our_seconds <= our_trash + 0.001, (
            f"aligned trash {aligned.our_seconds:.1f}s exceeds our own {our_trash:.1f}s, "
            "so a pull of ours was counted more than once"
        )


@pytest.mark.e2e
def test_a_real_run_measures_more_than_it_reports(tmp_path: Path) -> None:
    """Offline fixtures compare a handful of abilities chosen by hand. Only a real
    run shows whether the table holds abilities the rows are silent about — which
    is the whole of its reason to exist — and whether the two still state one
    figure over denominators nobody picked."""
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

    subject_slug = slugs_by_actor(loaded.run)[subject.actor_id]
    subject_name = display_names(loaded.run)[subject.actor_id]
    speed_sample, parse_samples, _records = _samples(
        rankings,
        references,
        loaded.run,
        (RequestedPlayer(player=subject, slug=subject_slug, name=subject_name),),
    )
    # The aura streams the CLI fetches before it compares. Without them our own
    # side has nothing to take a share of, and the aura table would come back
    # empty for a reason that is this test's setup rather than the run's.
    parse_sample, our_auras = _fetch_parse_auras(
        parse_samples[subject.actor_id], runs, references, loaded.run, subject
    )
    assert parse_sample.can_aggregate(parse_sample.members), (
        "this specialisation drew too small a sample to state any median, so neither "
        "a rate row nor a table row exists to compare"
    )

    subjects = (
        ComparisonSubject(
            player=subject,
            slug=subject_slug,
            display_name=subject_name,
            parse=parse_sample,
            our_auras=our_auras,
        ),
    )
    findings = compare(loaded, speed_sample, subjects)
    measures = comparison_measures(loaded, subjects)[subject_slug]

    named_in_rows = {f.ability_name for f in findings if f.ability_name}
    measured = {m.name for m in measures.boss + measures.trash}
    assert measured, "no ability was measured at all, so there is no table to judge"
    assert measured - named_in_rows, (
        "every measured ability produced a row, so the table adds nothing on this run"
    )
    assert measures.auras, "a real parse sample should carry aura data"

    # The anti-drift property the unit suite pins against fixtures whose
    # denominators it chose, held to a route the group actually ran.
    by_row = {(m.stretch, m.ability_id): m for m in measures.boss + measures.trash}
    rate_rows = [f for f in findings if f.id.startswith(RATE_FAMILIES)]
    # A row exists only where an ability cleared the gap bar, and most do not:
    # on the run this was written against, 24 of 34 measured abilities came out
    # level. With none of them clearing it the loop below would check nothing
    # while the assertions above passed — and `measured - named_in_rows` gets
    # easier in exactly that case, so it would read as a confident pass.
    assert rate_rows, "no rate row cleared the gap bar, so nothing was cross-checked"

    for finding in rate_rows:
        assert finding.ability_id is not None
        row = by_row[(stretch_of(finding), finding.ability_id)]
        assert finding.ability_name == row.name
        assert fact_value(finding, "Ours") == f"{row.ours:.1f} casts a minute"
        assert fact_value(finding, "Reference median") == (
            f"{row.their_median:.1f} casts a minute"
        )
