# ABOUTME: Boss debuff uptime against the parse sample: the buff family's thresholds, debuff words.
# ABOUTME: Pins the gap, level, unjudged, the pairwise fallback and every unavailable branch.

from tests.domain.comparison.test_uptime import BOSS, a_player, a_run
from wowperf.domain.auras import Aura, AuraBand
from wowperf.domain.comparison.boss_debuffs import BossDebuffs, BossWindow, Withheld
from wowperf.domain.comparison.debuff_uptime import compare_boss_debuffs_sample
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.comparison.service import ComparisonSubject, compare
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun

OUR_NAME = "Stonewake (actor 7)"
DOT, DOT_NAME = 55078, "Blood Plague"
REFERENCE_NAMES = ("Bríala", "Кириллица", "Emberkin")


def on_the_boss(*shares: tuple[int, str, float], seconds: float = 100.0) -> BossDebuffs:
    """One measured boss pull of `seconds`, each debuff on it for its share from the pull."""
    end_ms = int(seconds * 1000)
    window = BossWindow(
        encounter_id=2001, name="The Test Colossus", start_ms=0, end_ms=end_ms, boss_game_id=5000
    )
    auras = tuple(
        Aura(
            ability_id=ability_id,
            name=name,
            total_uptime_ms=int(end_ms * share),
            uses=1,
            bands=(AuraBand(start_ms=0, end_ms=int(end_ms * share)),),
        )
        for ability_id, name, share in shares
        if share > 0
    )
    return BossDebuffs(windows=(window,), auras=auras)


def a_member(name: str, debuffs: BossDebuffs | None) -> ParseMember:
    return ParseMember(
        character_name=name, report_code="ref", fight_id=1, boss_seconds=100.0, boss_debuffs=debuffs
    )


def a_sample(*shares: float) -> ParseSample:
    return ParseSample(
        members=tuple(
            a_member(name, on_the_boss((DOT, DOT_NAME, share)))
            for name, share in zip(REFERENCE_NAMES, shares, strict=False)
        )
    )


def by_id(findings: list[Finding]) -> dict[str, Finding]:
    return {finding.id: finding for finding in findings}


def test_a_debuff_kept_up_well_below_the_sample_is_a_gap() -> None:
    findings = by_id(
        compare_boss_debuffs_sample(
            on_the_boss((DOT, DOT_NAME, 0.5)), OUR_NAME, a_sample(0.9, 0.9, 0.9)
        )
    )

    gap = findings["compare.uptime.boss.0"]
    assert gap.confidence is Confidence.DERIVED
    assert gap.title == (
        "Blood Plague was on the boss a median 90% of boss time across 3 top parses; "
        "50% for Stonewake (actor 7)"
    )
    assert "range 90% to 90% across 3 top parses" in gap.evidence
    assert "0 of 3 references had no debuff data" in gap.evidence
    assert (gap.ability_id, gap.ability_name) == (DOT, DOT_NAME)


def test_a_narrow_difference_is_level_and_reports_nothing() -> None:
    findings = compare_boss_debuffs_sample(
        on_the_boss((DOT, DOT_NAME, 0.85)), OUR_NAME, a_sample(0.9, 0.9, 0.9)
    )

    assert findings == []


def test_a_debuff_the_sample_kept_and_we_never_applied_is_named_not_judged() -> None:
    findings = by_id(compare_boss_debuffs_sample(on_the_boss(), OUR_NAME, a_sample(0.9, 0.9, 0.9)))

    assert set(findings) == {"compare.uptime.boss.unjudged"}
    assert findings["compare.uptime.boss.unjudged"].evidence[0] == DOT_NAME


def test_below_the_floor_one_reference_is_stated_pairwise() -> None:
    findings = by_id(
        compare_boss_debuffs_sample(on_the_boss((DOT, DOT_NAME, 0.5)), OUR_NAME, a_sample(0.9, 0.9))
    )

    gap = findings["compare.uptime.boss.0"]
    assert gap.title == (
        "Blood Plague was on the boss for 90% of Bríala's boss time, 50% of Stonewake (actor 7)'s"
    )
    assert gap.evidence[-1].startswith("a single reference, not an aggregate")


def test_below_the_floor_a_narrow_difference_is_not_a_gap() -> None:
    findings = compare_boss_debuffs_sample(
        on_the_boss((DOT, DOT_NAME, 0.85)), OUR_NAME, a_sample(0.9, 0.9)
    )

    assert findings == []


def test_below_the_floor_a_debuff_we_never_applied_is_passed_over() -> None:
    findings = compare_boss_debuffs_sample(on_the_boss(), OUR_NAME, a_sample(0.9, 0.9))

    assert findings == []


def test_an_empty_sample_says_nothing_here() -> None:
    assert compare_boss_debuffs_sample(on_the_boss(), OUR_NAME, ParseSample()) == []


def test_no_reference_with_debuff_data_is_unavailable() -> None:
    sample = ParseSample(members=(a_member("Bríala", None), a_member("Кириллица", None)))

    [finding] = compare_boss_debuffs_sample(on_the_boss(), OUR_NAME, sample)

    assert finding.id == "compare.uptime.boss.unavailable"
    assert finding.confidence is Confidence.MEASURED
    assert "0 of 2 references returned debuff data" in finding.evidence


def test_our_own_missing_stream_is_unavailable() -> None:
    [finding] = compare_boss_debuffs_sample(None, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert finding.id == "compare.uptime.boss.unavailable"
    assert "our debuff data absent" in finding.evidence


def test_a_run_whose_every_boss_was_withheld_is_unavailable() -> None:
    council = BossDebuffs(
        windows=(
            BossWindow(
                encounter_id=2001,
                name="The Twin Council",
                start_ms=0,
                end_ms=60_000,
                withheld=Withheld.COUNCIL,
            ),
        )
    )

    [finding] = compare_boss_debuffs_sample(council, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert finding.id == "compare.uptime.boss.unavailable"
    assert "our measured boss time 0s" in finding.evidence


def test_at_most_five_gaps_are_reported() -> None:
    six = tuple((DOT + offset, f"Debuff {offset}", 0.9) for offset in range(6))
    ours = tuple((ability_id, name, 0.3) for ability_id, name, _ in six)
    sample = ParseSample(
        members=tuple(a_member(name, on_the_boss(*six)) for name in REFERENCE_NAMES)
    )

    findings = compare_boss_debuffs_sample(on_the_boss(*ours), OUR_NAME, sample)

    assert sorted(finding.id for finding in findings) == [
        f"compare.uptime.boss.{rank}" for rank in range(5)
    ]


def test_the_service_files_the_gap_under_the_players_own_slug() -> None:
    subject = ComparisonSubject(
        player=a_player(),
        slug="stonewake-0",
        display_name=OUR_NAME,
        parse=a_sample(0.9, 0.9, 0.9),
        our_boss_debuffs=on_the_boss((DOT, DOT_NAME, 0.5)),
    )

    ids = [finding.id for finding in compare(LoadedRun(run=a_run(BOSS)), None, [subject])]

    assert "compare.uptime.boss.0.stonewake-0" in ids
