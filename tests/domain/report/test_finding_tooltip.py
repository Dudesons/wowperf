# ABOUTME: Behaviour tests for which findings get a hover panel and where each panel comes from.
# ABOUTME: Two rules and no third: a defensive is measured against the run, anything else brings
# ABOUTME: its figures with it on the finding.

from tests.domain.analysis.test_players import a_run as an_analysed_run
from tests.domain.analysis.test_players import hit as damage_hit
from tests.domain.report.test_build_frame import a_pull, a_run
from wowperf.domain.analysis.players import analyse_players
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence, Finding, FindingFact
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.finding_tooltip import tooltips_by_finding_id
from wowperf.domain.season import DefensiveAbility, Defensives

STONEWAKE = Player(actor_id=1, name="Stonewake", class_name="DeathKnight", spec="Blood",
                   item_level=680)
ICEBOUND = DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=120.0)
CEILING_ID = "defensives.ceiling.stonewake.48792"
NEVER_ID = "defensives.never.stonewake.48792"


def a_defensives_file() -> Defensives:
    return Defensives(entries=(("DeathKnight/Blood", (ICEBOUND,)),))


def a_loaded_run() -> LoadedRun:
    """One player who pressed Icebound twice, with the aura table that proves it."""
    return LoadedRun(
        run=a_run(players=(STONEWAKE,), pulls=(a_pull(0, 0, 600_000),)),
        casts=(
            CastEvent(actor_id=1, ability_id=48792, ability_name="Icebound Fortitude",
                      timestamp_ms=100_000),
            CastEvent(actor_id=1, ability_id=48792, ability_name="Icebound Fortitude",
                      timestamp_ms=300_000),
        ),
        auras=(
            PlayerAuras(actor_id=1, on_self=(
                Aura(ability_id=48792, name="Icebound Fortitude", total_uptime_ms=16_000, uses=2,
                     bands=(AuraBand(start_ms=100_000, end_ms=108_000),
                            AuraBand(start_ms=300_000, end_ms=308_000))),
            )),
        ),
    )


def a_finding(finding_id: str, **changes: object) -> Finding:
    finding = Finding(id=finding_id, title="x", detail="detail", confidence=Confidence.DERIVED)
    return finding.model_copy(update=changes)


def a_ceiling_finding() -> Finding:
    return a_finding(CEILING_ID, ability_id=48792, ability_name="Icebound Fortitude",
                     confidence=Confidence.INFERRED)


def test_a_defensives_finding_gets_the_measured_ability_panel() -> None:
    tooltips = tooltips_by_finding_id((a_ceiling_finding(),), a_loaded_run(), a_defensives_file())
    lines = tooltips[CEILING_ID].lines
    assert [line.label for line in lines][:2] == ["Base cooldown", "Presses"]


def test_the_panel_counts_the_presses_the_run_actually_holds() -> None:
    # Scoped to the whole run rather than to a death's run-up, which is the
    # only thing a ledger card changes about the same builder.
    tooltips = tooltips_by_finding_id((a_ceiling_finding(),), a_loaded_run(), a_defensives_file())
    values = {line.label: line.value for line in tooltips[CEILING_ID].lines}
    assert values["Presses"] == "2"


def test_a_never_cast_defensive_gets_the_same_panel_as_a_ceiling_one() -> None:
    # Both families name one ability of one player measured over one run, so
    # both take the builder the death card already uses. Two rules, not five.
    never = a_finding(NEVER_ID, ability_id=48792, ability_name="Icebound Fortitude")
    assert NEVER_ID in tooltips_by_finding_id((never,), a_loaded_run(), a_defensives_file())


def test_a_finding_with_facts_gets_a_panel_built_from_them() -> None:
    finding = a_finding("interrupts.ability.0", facts=(
        FindingFact(label="Interruptible", value="kicked 6 times this run"),
    ))
    lines = tooltips_by_finding_id(
        (finding,), a_loaded_run(), a_defensives_file()
    )["interrupts.ability.0"].lines
    assert [(line.label, line.value) for line in lines] == [
        ("Interruptible", "kicked 6 times this run")
    ]


def test_a_facts_own_tier_reaches_its_line_and_no_tier_stays_no_tier() -> None:
    # A panel mixes tiers, so the tier travels on the line. A fact that claims
    # none must not acquire one on the way through.
    finding = a_finding("interrupts.ability.0", facts=(
        FindingFact(label="Interruptible", value="kicked 6 times",
                    confidence=Confidence.MEASURED),
        FindingFact(label="Landed", value="18 times"),
    ))
    lines = tooltips_by_finding_id(
        (finding,), a_loaded_run(), a_defensives_file()
    )["interrupts.ability.0"].lines
    assert lines[0].tier is not None and lines[0].tier.label == "measured"
    assert lines[1].tier is None


def test_a_damage_outlier_the_analyser_built_earns_a_panel() -> None:
    """The seam, walked with a real finding rather than a hand-built one.

    `players.damage.*` carries an ability id but was named in neither list of
    the second-reading design, so nothing decided whether it got a panel and
    nothing wired one. The producer sets `facts` now, and this is the test that
    the family reaches a panel rather than only that facts in general do: a
    hand-built fixture would pass on either side of that change.
    """
    damage = (
        damage_hit(0, 100_000), damage_hit(1, 10_000), damage_hit(2, 10_000),
        damage_hit(3, 10_000), damage_hit(4, 10_000),
    )
    findings = analyse_players(an_analysed_run(), (), (), (), damage)
    outlier = next(f for f in findings if f.id.startswith("players.damage."))

    panel = tooltips_by_finding_id((outlier,), a_loaded_run(), a_defensives_file())[outlier.id]
    assert [(line.label, line.value) for line in panel.lines] == [
        ("This player", "100,000 unmitigated"),
        ("Group median", "10,000 unmitigated"),
        ("Multiple", "10.0x"),
        ("Median over", "5 players who took it"),
    ]
    # The divided figure carries its own tier and the logged sums carry none.
    tiers = {line.label: line.tier for line in panel.lines}
    assert tiers["Multiple"] is not None and tiers["Multiple"].label == "derived"
    assert tiers["This player"] is None and tiers["Group median"] is None


def test_a_finding_with_no_ability_and_no_facts_gets_no_panel() -> None:
    # Twenty-one of one run's thirty-four findings name no ability. An empty
    # panel is a hover target that rewards nothing.
    assert tooltips_by_finding_id(
        (a_finding("time.residual"),), a_loaded_run(), a_defensives_file()
    ) == {}


def test_a_defensive_of_a_player_with_no_aura_table_gets_no_panel() -> None:
    # The same abstention `run_ability_tooltip` already makes: without the
    # table there is nothing measured to put in a panel, and a panel of
    # assumptions is worse than none.
    bare = LoadedRun(run=a_run(players=(STONEWAKE,), pulls=(a_pull(0, 0, 600_000),)))
    assert tooltips_by_finding_id((a_ceiling_finding(),), bare, a_defensives_file()) == {}


def test_a_defensives_finding_for_a_player_off_the_roster_is_not_invented() -> None:
    # The ids are generated from the roster rather than read off the finding,
    # so a finding naming somebody this run does not carry must simply miss.
    other = a_finding("defensives.ceiling.emberkin.48792", ability_id=48792,
                      ability_name="Icebound Fortitude")
    assert tooltips_by_finding_id((other,), a_loaded_run(), a_defensives_file()) == {}
