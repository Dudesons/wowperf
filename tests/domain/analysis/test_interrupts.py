# ABOUTME: Behaviour tests for reconstructing which enemy casts were kicked and which landed.
# ABOUTME: The excluded case is the one naive implementations get wrong, so it is pinned hard.

from wowperf.domain.analysis.interrupts import analyse_interrupts, reconstruct_enemy_casts
from wowperf.domain.events import DamageTakenEvent, EnemyCastRow, InterruptEvent
from wowperf.domain.findings import Confidence, Finding

SPELL = 1241214
OTHER = 1238440
THIRD = 1249001


def row(at: int, is_start: bool, instance: int = 0, ability: int = SPELL) -> EnemyCastRow:
    return EnemyCastRow(source_id=699, source_instance=instance, ability_id=ability,
                        ability_name="Searing Wave", timestamp_ms=at, is_start=is_start,
                        pull_index=0)


def kick(at: int, instance: int = 0, ability: int = SPELL) -> InterruptEvent:
    return InterruptEvent(player_name="Emberkin", actor_id=693,
                          interrupted_ability_id=ability, target_id=699,
                          target_instance=instance, timestamp_ms=at, pull_index=0)


def hit(at: int, amount: int, ability: int = SPELL) -> DamageTakenEvent:
    return DamageTakenEvent(actor_id=693, ability_id=ability, ability_name="Searing Wave",
                            amount=amount, timestamp_ms=at, pull_index=0)


def test_a_start_followed_by_a_completion_landed() -> None:
    casts = reconstruct_enemy_casts((row(1000, True), row(2500, False)), ())
    assert len(casts) == 1
    assert casts[0].landed is True
    assert casts[0].completed_ms == 2500


def test_a_start_followed_by_a_kick_was_interrupted() -> None:
    casts = reconstruct_enemy_casts((row(1000, True),), (kick(1800),))
    assert casts[0].was_kicked is True
    assert casts[0].interrupted_by == "Emberkin"
    assert casts[0].landed is False


def test_a_start_with_no_resolution_is_excluded_not_missed() -> None:
    casts = reconstruct_enemy_casts((row(1000, True),), ())
    assert casts[0].outcome_known is False
    assert casts[0].landed is False


def test_a_kick_on_a_different_instance_does_not_resolve_this_cast() -> None:
    casts = reconstruct_enemy_casts((row(1000, True, instance=0),), (kick(1800, instance=4),))
    assert casts[0].outcome_known is False


def test_a_completion_by_a_different_instance_does_not_resolve_this_cast() -> None:
    casts = reconstruct_enemy_casts(
        (row(1000, True, instance=0), row(2500, False, instance=4)), ()
    )
    resolved = [cast for cast in casts if cast.source_instance == 0]
    assert resolved[0].outcome_known is False


def test_a_kick_on_a_different_spell_does_not_resolve_this_cast() -> None:
    casts = reconstruct_enemy_casts((row(1000, True),), (kick(1800, ability=OTHER),))
    assert casts[0].outcome_known is False


def test_a_completion_after_the_next_start_belongs_to_the_next_cast() -> None:
    casts = reconstruct_enemy_casts(
        (row(1000, True), row(5000, True), row(6000, False)), ()
    )
    by_start = {cast.started_ms: cast for cast in casts}
    assert by_start[1000].outcome_known is False
    assert by_start[5000].landed is True


def test_an_instant_cast_with_no_start_is_ignored() -> None:
    assert reconstruct_enemy_casts((row(2500, False),), ()) == ()


def test_the_earlier_of_a_kick_and_a_completion_wins() -> None:
    casts = reconstruct_enemy_casts((row(1000, True), row(3000, False)), (kick(1800),))
    assert casts[0].was_kicked is True


def test_a_cast_never_carries_both_a_completion_and_a_kick() -> None:
    """Pin `EnemyCast`'s core invariant: a cast either landed or was kicked, never both.

    `landed` and `was_kicked` are derived properties that both go False/True
    correctly even if a broken reconstruction set both `completed_ms` and
    `interrupted_by` at once — `landed` requires `interrupted_by is None`, so a
    regression that wrongly stamps a completion onto a kicked cast is invisible
    to those properties. Assert on the two raw fields directly instead, across
    the three ways a kick and a completion can compete for the same cast: the
    kick strictly first, the completion strictly first, and an exact tie.
    """
    casts = reconstruct_enemy_casts(
        (
            row(1000, True, ability=SPELL),
            row(3000, False, ability=SPELL),
            row(10000, True, ability=OTHER),
            row(10800, False, ability=OTHER),
            row(20000, True, ability=THIRD),
            row(22500, False, ability=THIRD),
        ),
        (
            kick(1800, ability=SPELL),  # kick strictly before the completion
            kick(13000, ability=OTHER),  # kick strictly after the completion
            kick(22500, ability=THIRD),  # kick exactly at the completion
        ),
    )

    assert len(casts) == 3
    for cast in casts:
        assert not (cast.completed_ms is not None and cast.interrupted_by is not None)

    by_ability = {cast.ability_id: cast for cast in casts}

    kick_first = by_ability[SPELL]
    assert kick_first.interrupted_by == "Emberkin"
    assert kick_first.completed_ms is None

    completion_first = by_ability[OTHER]
    assert completion_first.completed_ms == 10800
    assert completion_first.interrupted_by is None

    tie = by_ability[THIRD]
    assert tie.interrupted_by == "Emberkin"
    assert tie.completed_ms is None


def test_landed_casts_are_ranked_by_the_damage_that_followed() -> None:
    casts = reconstruct_enemy_casts(
        (row(1000, True), row(2000, False), row(5000, True, ability=OTHER),
         row(6000, False, ability=OTHER)),
        (),
    )
    findings = analyse_interrupts(
        casts, (hit(2100, 50_000), hit(6100, 200_000, ability=OTHER))
    )
    ranked = [f for f in findings if f.id.startswith("interrupts.ability.")]
    # Thousands-separated, matching the death card's own convention for large amounts.
    assert "200,000" in ranked[0].evidence[0]


def test_the_detail_formats_the_damage_with_thousands_separators() -> None:
    # One landed cast followed by one hit large enough to need a separator.
    casts = reconstruct_enemy_casts((row(1000, True), row(2000, False)), ())
    findings = analyse_interrupts(casts, (hit(2100, 1_234_567),))
    ability = next(f for f in findings if f.id.startswith("interrupts.ability."))
    assert "1,234,567 unmitigated damage" in ability.detail
    assert "1234567" not in ability.detail


def test_damage_outside_the_follow_window_is_not_attributed() -> None:
    casts = reconstruct_enemy_casts((row(1000, True), row(2000, False)), ())
    findings = analyse_interrupts(casts, (hit(99_000, 500_000),))
    ranked = [f for f in findings if f.id.startswith("interrupts.ability.")]
    assert ranked == []


def test_the_summary_counts_kicked_missed_and_excluded_separately() -> None:
    casts = reconstruct_enemy_casts(
        (row(1000, True), row(2000, False), row(5000, True), row(9000, True),
         row(9500, False)),
        (kick(5500),),
    )
    findings = analyse_interrupts(casts, ())
    summary = next(f for f in findings if f.id == "interrupts.summary")
    assert summary.confidence is Confidence.DERIVED
    assert summary.seconds_lost is None
    # The title must never claim a landed cast was interruptible: the log carries
    # no such flag, so all the analyser knows is that the cast completed unkicked.
    assert summary.title == "2 casts landed, 1 was kicked"
    assert "interruptible" not in summary.title
    joined = " ".join(summary.evidence)
    assert "2 landed" in joined
    assert "1 kicked" in joined
    assert "0 excluded" in joined or "excluded" in joined


def test_no_casts_produces_no_findings() -> None:
    assert analyse_interrupts((), ()) == []


def test_the_summary_title_pluralises_a_single_landed_cast_correctly() -> None:
    casts = reconstruct_enemy_casts((row(1000, True), row(2000, False)), ())
    findings = analyse_interrupts(casts, ())
    summary = next(f for f in findings if f.id == "interrupts.summary")
    assert summary.title == "1 cast landed, 0 were kicked"


def a_landed_spell_and(
    *extra: EnemyCastRow, kicks: tuple[InterruptEvent, ...] = ()
) -> list[Finding]:
    """One cast of SPELL that landed and hurt, plus whatever else a test needs.

    A landed cast followed by damage is what makes an `interrupts.ability.`
    finding at all, so every test of that finding has to start from one.
    """
    casts = reconstruct_enemy_casts((row(1_000, True), row(3_000, False)) + extra, kicks)
    return analyse_interrupts(casts, (hit(3_100, 5_000),))


def test_a_spell_kicked_at_least_once_is_reported_interruptible() -> None:
    findings = a_landed_spell_and(row(10_000, True), kicks=(kick(10_500),))
    ability = next(f for f in findings if f.id.startswith("interrupts.ability."))
    assert "interruptible: kicked 1 time this run" in ability.evidence


def test_a_spell_never_kicked_is_reported_unknown_and_not_as_a_miss() -> None:
    # The log carries no interruptible flag -- `.claude/skills/wcl-api/SKILL.md`
    # lists the verified fields for `dataType: Interrupts` and there is none.
    # Silence is not a failure to kick, and a card that implied one would have
    # a reader supplying the missing half himself, wrongly.
    findings = a_landed_spell_and()
    ability = next(f for f in findings if f.id.startswith("interrupts.ability."))
    assert "never kicked this run; the log does not say whether it could be" in ability.evidence
    assert not any("missed" in item for item in ability.evidence)


def test_the_interruptible_claim_is_measured_not_derived() -> None:
    # It rests on interrupt events, not on a reconstruction: a kick that
    # happened proves the spell could be kicked.
    findings = a_landed_spell_and(row(10_000, True), kicks=(kick(10_500),))
    ability = next(f for f in findings if f.id.startswith("interrupts.ability."))
    fact = next(f for f in ability.facts if f.label == "Interruptible")
    assert fact.value == "kicked 1 time this run"
    assert fact.confidence is Confidence.MEASURED


def test_an_unproven_interruptible_claims_no_tier_of_its_own() -> None:
    # Abstention, not measurement. Stamping "measured" on the word unknown
    # would grade a claim nobody made; the finding's own badge covers it.
    findings = a_landed_spell_and()
    ability = next(f for f in findings if f.id.startswith("interrupts.ability."))
    fact = next(f for f in ability.facts if f.label == "Interruptible")
    assert fact.value == "unknown; never kicked this run"
    assert fact.confidence is None


def test_a_kick_of_a_different_spell_never_makes_this_one_interruptible() -> None:
    # Kicks are counted per ability id. Counting them across the run would
    # report every landed spell as provably interruptible the moment anybody
    # kicked anything.
    findings = a_landed_spell_and(
        row(10_000, True, ability=OTHER), kicks=(kick(10_500, ability=OTHER),)
    )
    ability = next(f for f in findings if f.id.startswith("interrupts.ability."))
    assert ability.ability_id == SPELL
    fact = next(f for f in ability.facts if f.label == "Interruptible")
    assert fact.value == "unknown; never kicked this run"


def test_an_unkicked_ability_finding_names_the_ability_it_is_about() -> None:
    # An unkicked cast that completed and was followed by damage is what makes
    # an `interrupts.ability.` finding at all.
    casts = reconstruct_enemy_casts((row(1_000, True), row(3_000, False)), ())
    findings = analyse_interrupts(casts, (hit(3_100, 5_000),))
    ability = next(f for f in findings if f.id.startswith("interrupts.ability."))
    assert ability.ability_id == SPELL
    assert ability.ability_name == "Searing Wave"
    assert ability.ability_name in ability.title
