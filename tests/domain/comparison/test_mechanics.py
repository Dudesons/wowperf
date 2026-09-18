# ABOUTME: The mechanics comparison: which references it draws, and what it states.
# ABOUTME: Size is matched, not annotated, because the rate is over a whole raid.

from wowperf.domain.comparison.mechanics import (
    AbilityTakenRow,
    MechanicsMember,
    MechanicsSample,
    ReferenceKillRow,
    compare_lethal_abilities,
    compare_mechanics,
    compare_phase_cost,
    hostile_rows,
    select_reference_kills,
)
from wowperf.domain.comparison.sample import SAMPLE_SIZE
from wowperf.domain.events import DamageTakenEvent, Death
from wowperf.domain.findings import Confidence, Finding, FindingFact
from wowperf.domain.phase_windows import PhaseShare
from wowperf.domain.phases import Phase, PhaseTransition

# Local to this module rather than imported from tests/domain/test_phase_windows.py:
# those constants belong to a different test module, and importing fixtures
# across test files couples two otherwise-unrelated tests for three lines saved.
STAGE_ONE = Phase(id=1, name="Stage One")
STAGE_TWO = Phase(id=2, name="Stage Two", is_intermission=True)
PHASES = (STAGE_ONE, STAGE_TWO)
TRANSITIONS = (PhaseTransition(id=1, start_ms=0), PhaseTransition(id=2, start_ms=5000))


def kill(code: str, size: int) -> ReferenceKillRow:
    return ReferenceKillRow(
        report_code=code, fight_id=1, size=size,
        duration_ms=480000, deaths=0,
    )


def test_only_references_of_our_own_size_are_drawn() -> None:
    rows = (kill("a", 20), kill("b", 30), kill("c", 20), kill("d", 14))
    drawn = select_reference_kills(rows, our_size=20)
    assert [row.report_code for row in drawn] == ["a", "c"]


def test_no_more_than_the_sample_size_is_drawn() -> None:
    rows = tuple(kill(str(index), 20) for index in range(SAMPLE_SIZE + 3))
    drawn = select_reference_kills(rows, our_size=20)
    assert len(drawn) == SAMPLE_SIZE


def test_no_limit_returns_every_match_and_still_refuses_another_size() -> None:
    # A caller that discards rows after this filter -- `_mechanics_sample`
    # drops our own report and any row whose table failed to load -- has to see
    # all of them and stop at its own count, or each discard costs it a member
    # the leaderboard had offered. The size filter is unaffected.
    rows = (*(kill(str(index), 20) for index in range(SAMPLE_SIZE + 3)), kill("wrong", 30))
    drawn = select_reference_kills(rows, our_size=20, limit=None)
    assert len(drawn) == SAMPLE_SIZE + 3
    assert "wrong" not in [row.report_code for row in drawn]


def ability(ability_id: int, name: str, hits: int, sources: tuple[str, ...]) -> AbilityTakenRow:
    return AbilityTakenRow(
        ability_id=ability_id, ability_name=name, hit_count=hits, source_types=sources
    )


def member(
    code: str, abilities: tuple[AbilityTakenRow, ...], seconds: float = 120.0
) -> MechanicsMember:
    # Its own row rather than `kill()`: the duration is the denominator under
    # test, so it has to be visible here and equal to ours, or a rate
    # comparison would be testing two things at once.
    return MechanicsMember(
        row=ReferenceKillRow(
            report_code=code, fight_id=1, size=20,
            duration_ms=int(seconds * 1000), deaths=0,
        ),
        abilities=abilities,
    )


def test_a_row_sourced_only_by_players_is_not_a_mechanic() -> None:
    rows = (
        ability(6940, "Blessing of Sacrifice", 2, ("Warrior",)),
        ability(400, "Ravenous Feast", 4, ("Boss",)),
    )
    assert [row.ability_id for row in hostile_rows(rows)] == [400]


def test_an_unrecognised_source_type_is_kept() -> None:
    # The filter fails toward showing a mechanic. A hostile type this code has
    # never seen must not make an ability disappear in silence.
    rows = (ability(401, "Coiling Ichor", 9, ("Leviathan",)),)
    assert [row.ability_id for row in hostile_rows(rows)] == [401]


def test_an_ability_we_took_far_more_of_than_the_sample_is_a_finding() -> None:
    # Ours: 12 landings in 120s = 6.0 a minute. The five references took
    # 1, 2, 3, 4 and 5 in 120s: a median of 3 landings, 1.5 a minute.
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    sample = MechanicsSample(
        members=tuple(
            member(str(index), (ability(400, "Ravenous Feast", index, ("Boss",)),))
            for index in (1, 2, 3, 4, 5)
        )
    )
    findings = compare_mechanics(ours, 120.0, sample, scope="the raid")
    assert findings, "a 4x gap against five references should state something"
    assert findings[0].id.startswith("mechanics.ability.")
    # Both sides of this finding are rates this function divided out, and
    # `FindingFact`'s own rule is that a rate the report computed is derived.
    # Its own facts already badge the identical figures that way.
    assert findings[0].confidence.value == "derived"
    # Both absolute rates are pinned, not only their ratio. A ratio is
    # scale-free, so an assertion resting on it alone survives deleting the
    # per-minute conversion from both sides -- mutation shape 2. The sample
    # median (1.5) also differs from its max (2.5) and its mean (1.5 here is
    # both, so the rates are 0.5/1.0/1.5/2.0/2.5 and only the median is 1.5).
    assert any("6.0" in line for line in findings[0].evidence), "our own rate"
    assert any("1.5" in line for line in findings[0].evidence), "the sample median rate"
    # The claim is a count, never an intent. Master design 5.5 refuses the
    # latter, and names four words that would smuggle it back in. Checked
    # over every finding the call produced, and both the title and the
    # detail of each -- a single word slipping past one of the eight checks
    # is exactly how "avoidable" shipped past a check that only tried "missed".
    for finding in findings:
        for word in ("missed", "avoidable", "should have", "failed"):
            assert word not in finding.title.lower(), finding.title
            assert word not in finding.detail.lower(), finding.detail


def test_a_reference_tick_count_counts_toward_its_landings() -> None:
    # A channelled tick lands just as certainly as a hit. If a reference's rate
    # were read from hit_count alone, every fixture elsewhere in this file
    # would still pass -- none gives a reference a tick_count, so landings and
    # hit_count agree everywhere else. This is the one fixture that gives a
    # reference a nonzero tick_count, so the median actually moves if hits
    # alone were substituted for landings.
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    ticking = AbilityTakenRow(
        ability_id=400, ability_name="Ravenous Feast", hit_count=1, tick_count=4,
        source_types=("Boss",),
    )
    sample = MechanicsSample(
        members=(
            member("a", (ticking,)),
            *(
                member(str(index), (ability(400, "Ravenous Feast", index, ("Boss",)),))
                for index in (2, 3, 4, 5)
            ),
        )
    )
    findings = compare_mechanics(ours, 120.0, sample, scope="the raid")
    assert findings
    # Landings per reference: 5, 2, 3, 4, 5 in 120s -> 2.5, 1.0, 1.5, 2.0, 2.5 a
    # minute; median 2.0. Reading hit_count alone instead gives 1, 2, 3, 4, 5
    # landings -> a median of 1.5, which is a different, wrong number.
    assert any("2.0" in line for line in findings[0].evidence), "ticks must count as landings"


def test_a_reference_with_zero_duration_is_dropped_before_dividing() -> None:
    # Nothing upstream refuses a zero-duration reference: select_reference_kills
    # matches size only, and ReferenceKillRow.duration_ms is a plain int with
    # no lower bound. A member like this must be dropped before
    # the loop divides by its duration, not after, and it must not still be
    # counted in the reference total the evidence and quantifier read.
    ours = (ability(400, "Ravenous Feast", 24, ("Boss",)),)
    broken = member("broken", (ability(400, "Ravenous Feast", 50, ("Boss",)),), seconds=0.0)
    sample = MechanicsSample(
        members=(
            broken,
            member("a", (ability(400, "Ravenous Feast", 2, ("Boss",)),)),
            member("b", (ability(400, "Ravenous Feast", 4, ("Boss",)),)),
            member("c", (ability(400, "Ravenous Feast", 6, ("Boss",)),)),
        )
    )
    findings = compare_mechanics(ours, 120.0, sample, scope="the raid")
    assert findings, "the call must not raise, and the three valid references still compare"
    # Surviving landings 2, 4, 6 in 120s -> 1.0, 2.0, 3.0 a minute; median 2.0.
    # Had the broken member instead been kept with its rate specialcased to
    # zero, the median over four values would read 1.5, not 2.0. Had it been
    # kept out of the rates but left in the denominator, the total would read
    # 4, not 3.
    assert any("2.0" in line for line in findings[0].evidence), "median over survivors only"
    assert any(
        "3 of 3" in line for line in findings[0].evidence
    ), "the broken member must not count toward the total"


def test_an_ability_in_line_with_the_sample_states_nothing() -> None:
    ours = (ability(400, "Ravenous Feast", 3, ("Boss",)),)
    sample = MechanicsSample(
        members=tuple(
            member(str(index), (ability(400, "Ravenous Feast", index, ("Boss",)),))
            for index in (2, 3, 3, 4, 3)
        )
    )
    assert compare_mechanics(ours, 120.0, sample, scope="the raid") == []


def test_the_title_states_our_own_side_as_a_rate_and_not_as_a_count() -> None:
    # The title's two halves have to be the same kind of number. 24 landings
    # over 240s is 6.0 a minute, so a count and a rate are visibly different
    # here -- a fixture over 60s would make them equal and could not tell a
    # correct title from a broken one. The references took 3, 4 and 5 over
    # their own 240s: 0.75, 1.0 and 1.25 a minute, a median of 1.0 that is
    # neither the lowest nor the highest of them.
    ours = (ability(400, "Ravenous Feast", 24, ("Boss",)),)
    sample = MechanicsSample(
        members=tuple(
            member(code, (ability(400, "Ravenous Feast", landings, ("Boss",)),), seconds=240.0)
            for code, landings in (("first", 3), ("second", 4), ("third", 5))
        )
    )
    findings = compare_mechanics(ours, 240.0, sample, scope="the raid")
    assert findings, "a 6x gap against three references should state something"
    title = findings[0].title
    assert "6.0 times a minute" in title, title
    assert "a median of 1.0 a minute" in title, title
    assert "24" not in title, f"the title states a count beside a per-minute figure: {title}"
    # The count is not lost by stating a rate; it moves to where it reads as one.
    assert any(
        fact.label == "Landings" and fact.value == "24" for fact in findings[0].facts
    ), "the absolute count must survive as a fact"


def test_below_the_aggregate_floor_the_finding_says_it_is_one_reference() -> None:
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    sample = MechanicsSample(
        members=(member("only", (ability(400, "Ravenous Feast", 1, ("Boss",)),)),)
    )
    findings = compare_mechanics(ours, 120.0, sample, scope="the raid")
    assert findings, "one reference is still a comparison, stated as one"
    assert any("single reference" in line for line in findings[0].evidence)
    assert any("reference kill only fight 1" in line for line in findings[0].evidence)


def test_two_references_are_stated_as_one_reference_rather_than_as_a_median() -> None:
    """Below the floor, `too_few`'s note has to be true of the finding it joins.

    The note reads "a single reference, not an aggregate", so the finding it is
    appended to must state a single reference. The two members here differ on
    purpose: 2 landings in 120s is 1.0 a minute and 6 is 3.0, so a median over
    the pair would read 2.0 and a range 1.0 to 3.0 -- numbers that appear
    nowhere below, and whose appearance is exactly the contradiction this pins.
    """
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    sample = MechanicsSample(
        members=(
            member("first", (ability(400, "Ravenous Feast", 2, ("Boss",)),)),
            member("second", (ability(400, "Ravenous Feast", 6, ("Boss",)),)),
        )
    )
    [one] = compare_mechanics(ours, 120.0, sample, scope="the raid")

    assert "the reference took 1.0 a minute" in one.title, one.title
    assert "median" not in one.title.lower(), one.title
    assert any("single reference" in line for line in one.evidence)
    assert any("reference kill first fight 1" in line for line in one.evidence)

    stated = " ".join(one.evidence)
    assert "2.0" not in stated, f"a median over the two references reached the evidence: {stated}"
    assert "range" not in stated, stated
    assert "2 of 2" not in stated, stated
    assert one.quantifier == "", "a single reference is not an aggregate over a sample"


def test_at_the_aggregate_floor_the_finding_states_a_median_and_carries_no_note() -> None:
    # Three comparable references is the floor. 2, 4 and 6 landings in 120s
    # are 1.0, 2.0 and 3.0 a minute: the median is 2.0 and equals neither end
    # of the range the evidence states beside it.
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    sample = MechanicsSample(
        members=(
            member("first", (ability(400, "Ravenous Feast", 2, ("Boss",)),)),
            member("second", (ability(400, "Ravenous Feast", 4, ("Boss",)),)),
            member("third", (ability(400, "Ravenous Feast", 6, ("Boss",)),)),
        )
    )
    [one] = compare_mechanics(ours, 120.0, sample, scope="the raid")

    assert "a median of 2.0 a minute" in one.title, one.title
    assert not any("single reference" in line for line in one.evidence), one.evidence
    assert any("range 1.0 to 3.0" in line for line in one.evidence), one.evidence
    assert any("3 of 3 references took it at all" in line for line in one.evidence), one.evidence


def test_an_empty_sample_states_nothing_rather_than_everything() -> None:
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    assert compare_mechanics(ours, 120.0, MechanicsSample(), scope="the raid") == []


def test_a_mechanics_finding_names_the_phase_its_landings_fell_in() -> None:
    shares = {
        11: PhaseShare(phase=Phase(id=2, name="Stage Two"), landings=19, total=27),
    }
    ours = (ability(11, "Ravenous Feast", 27, ("Boss",)),)
    sample = MechanicsSample(
        members=(member("only", (ability(11, "Ravenous Feast", 2, ("Boss",)),), seconds=300.0),)
    )

    findings = compare_mechanics(ours, 300.0, sample, scope="the raid", phase_shares=shares)

    assert any("Stage Two" in fact.value for fact in findings[0].facts)
    assert any("19 of 27" in line for line in findings[0].evidence)


def test_a_mechanics_finding_without_a_phase_share_names_no_phase() -> None:
    ours = (ability(11, "Ravenous Feast", 27, ("Boss",)),)
    sample = MechanicsSample(
        members=(member("only", (ability(11, "Ravenous Feast", 2, ("Boss",)),), seconds=300.0),)
    )

    findings = compare_mechanics(ours, 300.0, sample, scope="the raid")

    assert all(fact.label != "Mostly in" for fact in findings[0].facts)


def test_a_phase_finding_states_no_reference_figure_in_the_same_fact() -> None:
    """The reference table carries no timestamps, so a phase fact may never
    carry a reference number beside it. Design section 9."""
    shares = {11: PhaseShare(phase=Phase(id=2, name="Stage Two"), landings=19, total=27)}
    ours = (ability(11, "Ravenous Feast", 27, ("Boss",)),)
    sample = MechanicsSample(
        members=(member("only", (ability(11, "Ravenous Feast", 2, ("Boss",)),), seconds=300.0),)
    )

    findings = compare_mechanics(ours, 300.0, sample, scope="the raid", phase_shares=shares)

    phase_facts = [fact for fact in findings[0].facts if fact.label == "Mostly in"]
    assert phase_facts
    assert all("reference" not in fact.value.lower() for fact in phase_facts)


def _death(ability_id: int, name: str) -> Death:
    return Death(
        player_name="Emberkin",
        actor_id=1,
        timestamp_ms=1000,
        killing_blow=name,
        killing_blow_id=ability_id,
    )


def _sample_losing(*counts: int) -> MechanicsSample:
    return MechanicsSample(
        members=tuple(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code="AbCdEf",
                    fight_id=index,
                    size=20,
                    duration_ms=300_000,
                    deaths=count,
                ),
                abilities=(),
            )
            for index, count in enumerate(counts)
        )
    )


def test_an_ability_that_killed_more_than_the_references_lost_in_total() -> None:
    deaths = tuple(_death(11, "Caustic Waves") for _ in range(4))

    findings = compare_lethal_abilities(deaths, _sample_losing(0, 1, 2, 3, 1))

    assert findings[0].id == "mechanics.lethal.0"
    assert findings[0].confidence is Confidence.DERIVED
    assert "Caustic Waves" in findings[0].title
    assert findings[0].ability_id == 11
    assert any("0 to 3" in line for line in findings[0].evidence)


def test_the_deadliest_ability_is_reported_first() -> None:
    deaths = (
        _death(11, "Caustic Waves"),
        _death(22, "Purge"),
        _death(22, "Purge"),
        _death(22, "Purge"),
    )

    findings = compare_lethal_abilities(deaths, _sample_losing(0, 1, 2))

    assert findings[0].ability_name == "Purge"
    assert findings[1].ability_name == "Caustic Waves"


def test_at_most_five_abilities_are_reported() -> None:
    deaths = tuple(_death(identifier, f"Ability {identifier}") for identifier in range(9))

    assert len(compare_lethal_abilities(deaths, _sample_losing(0, 1, 2))) == 5


def test_a_sample_below_the_aggregate_floor_names_one_reference_kill() -> None:
    deaths = (_death(11, "Caustic Waves"),)

    findings = compare_lethal_abilities(deaths, _sample_losing(2, 3))

    assert any("1 reference kill" in fact.value for fact in findings[0].facts)
    assert all("median" not in line for line in findings[0].evidence)


def test_no_sample_yields_no_finding() -> None:
    assert compare_lethal_abilities((_death(11, "Caustic Waves"),), MechanicsSample()) == []


def test_no_deaths_yields_no_finding() -> None:
    assert compare_lethal_abilities((), _sample_losing(0, 1, 2)) == []


def _reference_deaths_fact(findings: list[Finding]) -> FindingFact:
    return next(fact for fact in findings[0].facts if fact.label == "Reference deaths, all sources")


def test_the_reference_deaths_fact_is_derived_at_the_aggregate_floor() -> None:
    # Three members clears MIN_SAMPLE_FOR_AGGREGATE, so the phrase is a median
    # this function computed over the sample -- derived, not read off one row.
    findings = compare_lethal_abilities((_death(11, "Caustic Waves"),), _sample_losing(0, 1, 2))

    assert _reference_deaths_fact(findings).confidence is Confidence.DERIVED


def test_the_reference_deaths_fact_is_unbadged_below_the_aggregate_floor() -> None:
    # One member is below the floor: the phrase is that one row's own death
    # count with no computation in between, so it is measured -- None, per
    # FindingFact's own rule that an unset confidence means exactly that.
    findings = compare_lethal_abilities((_death(11, "Caustic Waves"),), _sample_losing(2))

    assert _reference_deaths_fact(findings).confidence is None


def test_a_tie_in_kill_count_breaks_by_ability_name() -> None:
    # Both abilities killed twice: the ranking key's first term ties, so only
    # its second term -- ascending ability name -- decides. "Caustic Waves"
    # sorts before "Purge", and the fixture lists Purge's deaths first, so an
    # insertion-order tiebreak (or none at all) would rank Purge first instead.
    deaths = (
        _death(22, "Purge"),
        _death(22, "Purge"),
        _death(11, "Caustic Waves"),
        _death(11, "Caustic Waves"),
    )

    findings = compare_lethal_abilities(deaths, _sample_losing(0, 1, 2))

    assert findings[0].ability_name == "Caustic Waves"
    assert findings[1].ability_name == "Purge"


def test_no_finding_from_compare_lethal_abilities_claims_intent() -> None:
    """Mirrors the guard on compare_mechanics's own findings, above.

    compare_lethal_abilities is the one function in this module licensed to
    judge -- deaths, never damage -- and that license runs only as far as
    "killed". Checked over the title, the detail, every fact's label and
    value, and every evidence line: five places this function's own wording
    can appear, and a single word slipping past one of them is exactly how
    "avoidable" would ship past a check that only tried "missed".
    """
    deaths = tuple(_death(11, "Caustic Waves") for _ in range(4)) + tuple(
        _death(22, "Purge") for _ in range(2)
    )
    findings = compare_lethal_abilities(deaths, _sample_losing(0, 1, 2, 3, 1))
    assert findings, "the guard needs at least one finding to check"

    for finding in findings:
        for word in ("missed", "avoidable", "should have", "failed"):
            assert word not in finding.title.lower(), finding.title
            assert word not in finding.detail.lower(), finding.detail
            for fact in finding.facts:
                assert word not in fact.label.lower(), fact.label
                assert word not in fact.value.lower(), fact.value
            for line in finding.evidence:
                assert word not in line.lower(), line


def _taken(ability_id: int, timestamp_ms: int, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=1,
        ability_id=ability_id,
        ability_name="Caustic Waves",
        amount=amount,
        timestamp_ms=timestamp_ms,
    )


def test_the_phase_taking_the_most_damage_is_reported_first() -> None:
    events = (
        _taken(ability_id=11, timestamp_ms=100, amount=50),
        _taken(ability_id=11, timestamp_ms=6000, amount=400),
        _taken(ability_id=11, timestamp_ms=7000, amount=300),
    )

    findings = compare_phase_cost(events, PHASES, TRANSITIONS)

    assert findings[0].id == "mechanics.phase.0"
    assert "Stage Two" in findings[0].title
    assert findings[0].confidence is Confidence.DERIVED


def test_a_phase_finding_carries_no_reference_figure() -> None:
    """Design section 9: the reference table has no timestamps, so no phase
    finding may imply a reference side."""
    events = (_taken(ability_id=11, timestamp_ms=6000, amount=400),)

    finding = compare_phase_cost(events, PHASES, TRANSITIONS)[0]

    assert all(
        "reference" not in text.lower()
        for text in (finding.title, finding.detail, *finding.evidence)
    )
    assert all(fact.label != "Reference" for fact in finding.facts)


def test_an_encounter_with_no_phases_reports_nothing() -> None:
    events = (_taken(ability_id=11, timestamp_ms=100, amount=50),)

    assert compare_phase_cost(events, (), TRANSITIONS) == []


def test_the_share_is_of_damage_not_of_landings() -> None:
    """One huge hit in Stage Two must outrank three small ones in Stage One.

    An implementation counting events passes every test above and fails this.
    """
    events = (
        _taken(ability_id=11, timestamp_ms=100, amount=10),
        _taken(ability_id=11, timestamp_ms=200, amount=10),
        _taken(ability_id=11, timestamp_ms=300, amount=10),
        _taken(ability_id=11, timestamp_ms=6000, amount=900),
    )

    assert "Stage Two" in compare_phase_cost(events, PHASES, TRANSITIONS)[0].title


def test_no_events_placed_in_any_phase_reports_nothing() -> None:
    """A distinct empty-result path from having no phases at all: phases and
    transitions are both present, but every event predates the first
    transition, so `phase_at` places none of them and the totals stay empty."""
    late_transitions = (PhaseTransition(id=1, start_ms=5000), PhaseTransition(id=2, start_ms=9000))
    events = (_taken(ability_id=11, timestamp_ms=100, amount=50),)

    assert compare_phase_cost(events, PHASES, late_transitions) == []


def test_a_tie_in_phase_damage_breaks_by_phase_id() -> None:
    """Stage One and Stage Two take equal damage, so only the ranking key's
    second term -- ascending phase id -- can decide the order.

    The Stage Two event is listed first on purpose: `totals` is a `Counter`,
    which reports its `.items()` in insertion order, so its Stage Two key
    would come first were the tie-break term deleted and the sort left stable
    on the (also tied) damage term alone. Only the ascending-id tie-break
    corrects that back to Stage One first.
    """
    events = (
        _taken(ability_id=11, timestamp_ms=6000, amount=100),
        _taken(ability_id=11, timestamp_ms=100, amount=100),
    )

    findings = compare_phase_cost(events, PHASES, TRANSITIONS)

    assert findings[0].id == "mechanics.phase.0"
    assert "Stage One" in findings[0].title
    assert findings[1].id == "mechanics.phase.1"
    assert "Stage Two" in findings[1].title


def test_at_most_five_phases_are_reported() -> None:
    """Mirrors compare_lethal_abilities's own cap test, one function above.

    An encounter can genuinely carry more than five named phases once stages
    and intermissions are counted, so six distinct phases here is not a
    hypothetical input -- and each is given a distinct damage total so the
    ranking has only one correct answer to check against.
    """
    phases = tuple(Phase(id=n, name=f"Stage {n}") for n in range(1, 7))
    transitions = tuple(PhaseTransition(id=n, start_ms=n * 1000) for n in range(1, 7))
    # Descending by phase number: Stage 1 costs the most, Stage 6 the least.
    events = tuple(
        _taken(ability_id=11, timestamp_ms=n * 1000, amount=(7 - n) * 100) for n in range(1, 7)
    )

    findings = compare_phase_cost(events, phases, transitions)

    assert len(findings) == 5
    titles = [finding.title for finding in findings]
    # Not just a count of five: the five highest-cost phases, in cost order,
    # with the cheapest -- Stage 6 -- the one left out.
    assert all(f"Stage {n}" in titles[n - 1] for n in range(1, 6)), titles
    assert not any("Stage 6" in title for title in titles), titles
