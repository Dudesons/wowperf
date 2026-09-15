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
from collections.abc import Sequence
from pathlib import Path

import pytest

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.config.toml import load_consumables, load_defensives
from wowperf.adapters.wcl.encounter_rankings import WclEncounterRankingRepository
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.cli import (
    REFERENCE_CACHE_SECONDS,
    REFERENCE_CACHE_SUBDIR,
    _ability_taken,
    _mechanics_sample,
    _parse_samples,
    _resolve_requested,
    build_repository,
)
from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.analysis.roster import display_names
from wowperf.domain.analysis.severity import SEVERITY_BY_FAMILY, UNKNOWN_SEVERITY, family_of
from wowperf.domain.comparison.mechanics import AbilityTakenRow, MechanicsSample
from wowperf.domain.comparison.parse_axis import ParseSubject
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.urls import parse_report_url

KILL = os.environ.get("WOWPERF_E2E_RAID_KILL", "")
WIPE = os.environ.get("WOWPERF_E2E_RAID_WIPE", "")

# Findings a boss fight cannot support. Slice 1 emits all four; if one reaches a
# raid report, an analyser is reading an aggregate that has no such thing and
# answering zero rather than abstaining.
KEYSTONE_SHAPED = ("time.", "trash.", "compare.route", "compare.downtime")


def assert_mechanics_output_is_well_formed(
    findings: Sequence[Finding],
    mechanics_sample: MechanicsSample,
    our_abilities: Sequence[AbilityTakenRow],
) -> None:
    """What the mechanics comparison must be true of, whatever it found.

    A raid in line with its references legitimately produces no finding at
    all -- `test_an_ability_in_line_with_the_sample_states_nothing` pins that
    offline -- so a loaded sample cannot be asked to yield one. What it can be
    asked for is that both sides of the comparison actually arrived and that
    everything it did emit is well formed.

    The other direction is still absolute: with no reference loaded there is
    nothing to compare against, so a `mechanics.ability.*` finding would be the
    comparison inventing a reference side.
    """
    mechanics = [f for f in findings if f.id.startswith("mechanics.ability")]
    if not mechanics_sample.members:
        assert not mechanics, "no reference sample loaded, but a mechanics finding exists"
        return

    assert our_abilities, "a reference sample loaded but our own ability table did not"
    assert len({f.id for f in mechanics}) == len(mechanics), "duplicate mechanics ids"
    for finding in mechanics:
        assert finding.confidence is Confidence.DERIVED, finding.id
        assert finding.ability_id is not None, finding.id
        assert finding.ability_name, finding.id
        assert finding.ability_name in finding.title, finding.title
        assert finding.evidence, finding.id
        assert finding.seconds_lost is None, "a landing rate is not priced in seconds"


def draw_parse_subjects(
    repository: WclRunRepository,
    rankings: WclEncounterRankingRepository,
    transient: DiskCache,
    loaded: LoadedEncounter,
) -> tuple[ParseSubject, ...]:
    """What `raid` hands `analyse_encounter` for the external frame, for the report owner.

    Rebuilt here rather than mocked, for the reason the mechanics sample above
    gives: a defaulted-away comparison is exactly the shape these tests exist to
    catch.
    """
    encounter = loaded.encounter
    names = display_names(encounter.players)
    _subject, to_compare = _resolve_requested(
        encounter.players, encounter.owner_name, [], False, names
    )
    subjects, _records = _parse_samples(
        rankings,
        repository,
        WclRunRepository(repository.client, transient),
        loaded,
        to_compare,
        names,
    )
    return subjects


def assert_no_aura_band_overhangs_the_fight(loaded: LoadedEncounter, subject: ParseSubject) -> None:
    """The one thing `seconds_up_over_the_fight` trusts and has never measured on a raid.

    That rule divides the seconds an aura's own bands cover by the fight's
    duration, and nothing clips the numerator: a band running past the fight it
    was queried for would render an uptime above 100%. Measured across 22 cached
    Mythic+ tables and 49,514 bands, none was outside its fight, and
    `.claude/skills/wcl-api/SKILL.md` records that the measurement covered no
    raid table at all. This is the raid half, taken live against the one
    endpoint that could contradict it.
    """
    if subject.our_auras is None:
        pytest.fail("no aura table fetched, so the band check below asserts nothing")
    fight = (loaded.encounter.start_ms, loaded.encounter.end_ms)
    overhanging = [
        (aura.ability_id, band.start_ms, band.end_ms)
        for aura in subject.our_auras.on_self
        for band in aura.bands
        if band.start_ms < fight[0] or band.end_ms > fight[1]
    ]
    assert overhanging == [], (
        f"a raid aura band falls outside fight {fight}, so an uptime fraction can exceed "
        f"100%: {overhanging[:5]}"
    )


@pytest.mark.e2e
def test_a_real_boss_kill_is_measured_against_the_world(tmp_path: Path) -> None:
    """The external frame, end to end, against a real leaderboard.

    Every assertion below names something only a fetched reference side can
    produce, and the sample's own presence is asserted first: an empty sample
    fails here rather than quietly reducing this test to "the command did not
    crash", which is the shape plan 2's kill test degraded into.
    """
    if not KILL:
        pytest.fail(
            "Set WOWPERF_E2E_RAID_KILL to a public report URL naming a boss kill "
            "(include the #fight=N fragment) to run this"
        )

    code, fight = parse_report_url(KILL)
    repository = build_repository(tmp_path)
    loaded = repository.load_encounter(code, fight)
    assert loaded.standing is not None, "a kill returned no rankings row of its own"

    transient = DiskCache(
        tmp_path / REFERENCE_CACHE_SUBDIR, max_age_seconds=REFERENCE_CACHE_SECONDS
    )
    rankings = WclEncounterRankingRepository(repository.client, transient)
    [subject] = draw_parse_subjects(repository, rankings, transient, loaded)

    assert subject.board, "the all-damage leaderboard offered no row for this specialisation"
    assert subject.boss_board, "the boss-damage leaderboard offered no row"
    assert subject.sample.members, "no reference kill loaded, so nothing was compared"
    assert subject.our_targets, "our own damage-by-target table never arrived"
    assert any(subject.their_targets), "no reference's damage-by-target table arrived"
    assert_no_aura_band_overhangs_the_fight(loaded, subject)

    findings = analyse_encounter(
        loaded, load_defensives(), load_consumables(), parse_subjects=(subject,)
    )
    ids = [finding.id for finding in findings]

    assert "compare.damage.total" in ids
    assert "compare.damage.targets" in ids
    assert "compare.rank" in ids
    assert "compare.parse.unavailable" not in ids, "the frame was withheld from a kill"

    external = [f for f in findings if f.id.startswith("compare.")]
    for finding in external:
        assert isinstance(finding.confidence, Confidence), finding.id
        assert finding.seconds_lost is None, "an external comparison is not priced in seconds"
        assert subject.display_name in finding.title, finding.title

    # F9, live: both sides of the damage comparison are per-second rates, and a
    # raid boss total runs to hundreds of millions. A nine-digit figure here
    # means a total reached a sentence that says "per second".
    [damage] = [f for f in findings if f.id == "compare.damage.total"]
    for fact in damage.facts:
        for number in fact.value.replace(",", " ").split():
            digits = number.split(".")[0]
            if digits.isdigit():
                assert len(digits) < 9, f"a total reached a per-second sentence: {fact.value}"


@pytest.mark.e2e
def test_a_real_wipe_withholds_the_external_frame_and_pays_for_none_of_it(
    tmp_path: Path,
) -> None:
    """Design 13's first risk, live: a reader must not read absence as a clean result.

    And the saving beside it: every family of this axis reads a rankings row
    this attempt does not have, so no leaderboard, no reference report and no
    per-target table is bought.
    """
    if not WIPE:
        pytest.fail(
            "Set WOWPERF_E2E_RAID_WIPE to a public report URL naming a wiped attempt "
            "(include the #fight=N fragment) to run this"
        )

    code, fight = parse_report_url(WIPE)
    repository = build_repository(tmp_path)
    loaded = repository.load_encounter(code, fight)
    assert loaded.standing is None, "a wipe carried a rankings row after all"

    transient = DiskCache(
        tmp_path / REFERENCE_CACHE_SUBDIR, max_age_seconds=REFERENCE_CACHE_SECONDS
    )
    rankings = WclEncounterRankingRepository(repository.client, transient)
    before = repository.rate_limit().points_spent_this_hour
    [subject] = draw_parse_subjects(repository, rankings, transient, loaded)
    after = repository.rate_limit().points_spent_this_hour

    assert not subject.board and not subject.sample.members and not subject.our_targets
    # Two quota reads and nothing between them. Their own cost is billed to the
    # read that follows, so the gap is what the frame spent: zero.
    assert after - before <= 2.0, f"a withheld frame still spent {after - before:.2f} points"

    findings = analyse_encounter(
        loaded, load_defensives(), load_consumables(), parse_subjects=(subject,)
    )
    ids = [finding.id for finding in findings]

    assert "compare.parse.unavailable" in ids
    assert [one for one in ids if one.startswith("compare.")] == ["compare.parse.unavailable"]
    [withheld] = [f for f in findings if f.id == "compare.parse.unavailable"]
    assert "did not kill" in withheld.detail
    assert findings != [withheld], "the internal frame went with the external one"


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

    assert_mechanics_output_is_well_formed(findings, mechanics_sample, our_abilities)

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

    assert_mechanics_output_is_well_formed(findings, mechanics_sample, our_abilities)
