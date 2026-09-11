# ABOUTME: What a death recap's hover panel says about one event, straight from the log.
# ABOUTME: Proves the tooltip states the figures it has and attributes none of them.

from wowperf.domain.analysis.recap import HEAL, HIT, RecapEvent
from wowperf.domain.report.tooltip import heal_tooltip, hit_tooltip


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
