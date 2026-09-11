# ABOUTME: What a death recap's hover panel says about one event, straight from the log.
# ABOUTME: Proves the tooltip states the figures it has and attributes none of them.

from wowperf.domain.analysis.recap import HEAL, HIT, RecapEvent
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.report.tooltip import ability_tooltip, heal_tooltip, hit_tooltip


def test_a_hit_reports_its_four_figures_and_attributes_none_of_them() -> None:
    event = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar", ability_id=7,
                       amount=67343, absorbed=0, mitigated=15609, unmitigated=145434)
    labels = {line.label: line.value for line in hit_tooltip(event).lines}
    assert labels["Struck for"] == "145,434"
    assert labels["Mitigated"] == "15,609"
    assert labels["Reached health"] == "67,343"


def test_a_hit_tooltip_never_says_what_did_the_mitigating() -> None:
    # Spec 5. `mitigated` is one figure the log never attributes, and a tooltip
    # that named a cause would be the debuff half's failure again.
    event = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar", ability_id=7,
                       amount=1, mitigated=99, unmitigated=100)
    note = hit_tooltip(event).note
    assert "does not attribute" in note
    for line in hit_tooltip(event).lines:
        assert "%" not in line.value


def test_only_a_lethal_blow_reports_overkill() -> None:
    lethal = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar", ability_id=7,
                        amount=67343, unmitigated=145434, overkill=62482)
    ordinary = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar", ability_id=7,
                          amount=100, unmitigated=100)
    assert any(line.label == "Overkill" for line in hit_tooltip(lethal).lines)
    assert not any(line.label == "Overkill" for line in hit_tooltip(ordinary).lines)


def test_an_area_hit_reports_area_and_a_single_target_hit_does_not() -> None:
    # Task 1 carried `is_area` out of the log specifically for this line; the
    # false half catches a branch wired to always fire.
    area = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar", ability_id=7,
                      amount=100, unmitigated=100, is_area=True)
    single_target = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar",
                               ability_id=7, amount=100, unmitigated=100, is_area=False)
    assert any(line.label == "Area" for line in hit_tooltip(area).lines)
    assert not any(line.label == "Area" for line in hit_tooltip(single_target).lines)


def test_a_periodic_hit_reports_periodic_and_a_discrete_hit_does_not() -> None:
    # Plan ruling 2 chose `tick` over the undocumented `hitType` because
    # "periodic" is self-describing; the false half catches a branch wired to
    # always fire.
    tick = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar", ability_id=7,
                      amount=100, unmitigated=100, is_tick=True)
    discrete = RecapEvent(kind=HIT, timestamp_ms=1000, ability_name="Frigid Roar",
                          ability_id=7, amount=100, unmitigated=100, is_tick=False)
    assert any(line.label == "Periodic" for line in hit_tooltip(tick).lines)
    assert not any(line.label == "Periodic" for line in hit_tooltip(discrete).lines)


def test_a_heal_tooltip_says_the_log_reports_no_overheal() -> None:
    # Recorded 2026-09-06 in the wcl-api skill: the healing stream returns no
    # such field. Saying so beats omitting the row in silence.
    event = RecapEvent(kind=HEAL, timestamp_ms=1000, ability_name="Holy Word: Serenity",
                       ability_id=9, amount=42_000, source_id=3)
    assert "no overheal" in heal_tooltip(event, {3: "Bríala"}).note


def a_hit(timestamp_ms: int, swung: int, landed: int, buffs: tuple[int, ...]) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=1, ability_id=100, ability_name="Frigid Roar", amount=swung,
        timestamp_ms=timestamp_ms, health_damage=landed, buff_ids=buffs,
    )


def test_an_ability_tooltip_reports_presses_cover_and_what_arrived_inside_it() -> None:
    # Every figure here is a field on an event the log emitted, or a sum of
    # such fields over a window the aura table stated. Nothing is apportioned.
    tip = ability_tooltip(
        cooldown_seconds=120.0, cover=((1_000, 9_000),),
        hits=(a_hit(2_000, 1_000, 400, (48792,)), a_hit(20_000, 1_000, 800, ())),
        buff_id=48792, presses=1,
    )
    labels = {line.label: line.value for line in tip.lines}
    assert labels["Base cooldown"] == "120 s"
    assert labels["Presses"] == "1"
    assert labels["Cover"] == "8.0 s"
    assert labels["Arrived while it was up"] == "1,000"
    assert labels["Reached health"] == "400"
    assert labels["Mitigated inside / outside"] == "60% / 20%"


def test_an_ability_tooltip_states_the_rate_gap_as_suggestive_not_attributable() -> None:
    # Spec 5: the inside/outside gap is offered as suggestive and never as
    # damage this ability prevented.
    tip = ability_tooltip(
        cooldown_seconds=120.0, cover=((1_000, 9_000),),
        hits=(a_hit(2_000, 1_000, 400, (48792,)),), buff_id=48792, presses=1,
    )
    assert "does not attribute" in tip.note
    assert "suggestive, not attributable" in tip.note
    assert not any("prevented" in line.label.lower() for line in tip.lines)


def test_a_side_with_no_hits_reads_as_a_dash_rather_than_as_perfect_mitigation() -> None:
    # No hits outside the window is not the claim "nothing got through outside
    # the window", and a zero there would read as exactly that.
    tip = ability_tooltip(
        cooldown_seconds=120.0, cover=((1_000, 9_000),),
        hits=(a_hit(2_000, 1_000, 400, (48792,)),), buff_id=48792, presses=1,
    )
    assert tip.lines[-1].value == "60% / --"


def test_an_ability_with_no_band_reports_its_presses_and_no_cover() -> None:
    tip = ability_tooltip(cooldown_seconds=120.0, cover=(), hits=(), buff_id=48792, presses=2)
    assert not any(line.label == "Cover" for line in tip.lines)
    assert {line.label for line in tip.lines} == {"Base cooldown", "Presses"}
