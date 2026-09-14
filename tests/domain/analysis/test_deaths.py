# ABOUTME: Behaviour tests for what deaths actually cost and which ones caused others.
# ABOUTME: A death with no measured cost must stay uncounted rather than get a default.

from wowperf.domain.analysis.deaths import analyse_deaths, fight_offset, pull_offset
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=60_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=744, count_required=729, npc_counts=(),
        players=(
            Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane",
                   item_level=318),
            Player(actor_id=12, name="Sublime", class_name="Shaman", spec="Elemental",
                   item_level=311),
        ),
        pulls=pulls,
    )


def a_death(
    name: str, actor_id: int, at: int, cost: float | None, pull_index: int | None = 0,
    killing_blow_id: int = 0,
) -> Death:
    return Death(player_name=name, actor_id=actor_id, timestamp_ms=at,
                 killing_blow="Molten Scar", pull_index=pull_index,
                 seconds_until_next_action=cost, killing_blow_id=killing_blow_id)


def locate_in_a_run(death: Death) -> str:
    """The real `locate` a caller would build for `a_run()`'s single pull."""
    return pull_offset(a_run().pulls, death)


SCOPE_A_RUN = f"across {len(a_run().pulls)} pulls"
"""The real `scope` a caller would build for `a_run()`'s single pull."""


def test_a_death_locates_against_the_fight_when_there_are_no_pulls() -> None:
    death = Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
                  killing_blow="Ravenous Feast", seconds_until_next_action=3.0,
                  pull_index=None)
    assert fight_offset(1_000, death) == "60s in"


def test_the_scope_phrase_reaches_the_evidence_verbatim() -> None:
    """A raid report must not print 'across 0 pulls'."""
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              killing_blow="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    findings = analyse_deaths(deaths, lambda d: fight_offset(1_000, d),
                              "in 374s of The Twin Fangs")

    assert findings, "one death must produce one finding"
    assert "1 deaths in 374s of The Twin Fangs" in findings[0].evidence
    assert not any("pull" in line for line in findings[0].evidence)


def test_the_total_cost_is_the_measured_time_not_played() -> None:
    findings = analyse_deaths(
        (a_death("Emberkin", 11, 1_000, 20.0), a_death("Sublime", 12, 40_000, 12.5)),
        locate_in_a_run,
        SCOPE_A_RUN,
    )
    total = next(f for f in findings if f.id == "deaths.total")
    assert total.seconds_lost == 32.5
    assert total.confidence is Confidence.MEASURED


def test_a_death_with_no_measured_cost_is_excluded_and_said_so() -> None:
    findings = analyse_deaths(
        (a_death("Emberkin", 11, 1_000, 20.0), a_death("Sublime", 12, 40_000, None)),
        locate_in_a_run,
        SCOPE_A_RUN,
    )
    total = next(f for f in findings if f.id == "deaths.total")
    assert total.seconds_lost == 20.0
    assert any("1 death" in item and "not measured" in item for item in total.evidence)


def test_a_wholly_unmeasured_run_of_deaths_reports_no_total_cost_rather_than_zero() -> None:
    findings = analyse_deaths(
        (a_death("Emberkin", 11, 1_000, None), a_death("Sublime", 12, 40_000, None)),
        locate_in_a_run,
        SCOPE_A_RUN,
    )
    total = next(f for f in findings if f.id == "deaths.total")
    assert total.seconds_lost is None
    assert "cannot be measured" in total.detail
    assert any("2 deaths" in item and "not measured" in item for item in total.evidence)


def test_no_deaths_produces_no_findings() -> None:
    assert analyse_deaths((), locate_in_a_run, SCOPE_A_RUN) == []


def test_deaths_close_together_are_reported_as_one_chain() -> None:
    findings = analyse_deaths(
        (
            a_death("Emberkin", 11, 30_000, 10.0),
            a_death("Sublime", 12, 33_000, 8.0),
        ),
        locate_in_a_run,
        SCOPE_A_RUN,
    )
    chain = next(f for f in findings if f.id.startswith("deaths.chain."))
    assert chain.seconds_lost == 18.0
    assert "Emberkin" in chain.detail
    assert chain.confidence is Confidence.MEASURED
    # Pull 0 starts at 0ms: 30_000ms and 33_000ms are 30s and 33s into it.
    assert chain.evidence == (
        "Emberkin at pull 0, 30s in to Molten Scar",
        "Sublime at pull 0, 33s in to Molten Scar",
    )


def test_deaths_far_apart_are_reported_separately() -> None:
    findings = analyse_deaths(
        (
            a_death("Emberkin", 11, 1_000, 10.0),
            a_death("Sublime", 12, 200_000, 8.0),
        ),
        locate_in_a_run,
        SCOPE_A_RUN,
    )
    assert [f.id for f in findings if f.id.startswith("deaths.chain.")] == []
    assert len([f for f in findings if f.id.startswith("deaths.single.")]) == 2


def test_a_repeat_dier_is_named() -> None:
    findings = analyse_deaths(
        (
            a_death("Emberkin", 11, 1_000, 10.0),
            a_death("Emberkin", 11, 200_000, 8.0),
        ),
        locate_in_a_run,
        SCOPE_A_RUN,
    )
    repeat = next(f for f in findings if f.id == "deaths.repeat.Emberkin")
    assert repeat.seconds_lost == 18.0
    assert "2" in repeat.detail


def test_a_single_death_is_reported_alone_with_correct_grammar() -> None:
    findings = analyse_deaths(
        (a_death("Emberkin", 11, 1_000, 10.0),), locate_in_a_run, SCOPE_A_RUN
    )
    assert [f.id for f in findings if f.id.startswith("deaths.chain.")] == []
    assert [f.id for f in findings if f.id.startswith("deaths.repeat.")] == []
    singles = [f for f in findings if f.id.startswith("deaths.single.")]
    assert [f.id for f in singles] == ["deaths.single.0"]
    # Pull 0 starts at 0ms, so a death at 1_000ms is 1s into it: the evidence
    # must read as time within the pull, never as a raw report-wide offset.
    assert singles[0].evidence == ("pull 0, 1s in",)

    total = next(f for f in findings if f.id == "deaths.total")
    assert total.title.startswith("1 death cost"), total.title


def test_a_wholly_unmeasured_death_reports_no_seconds_lost_rather_than_zero() -> None:
    findings = analyse_deaths(
        (a_death("Emberkin", 11, 1_000, None),), locate_in_a_run, SCOPE_A_RUN
    )
    single = next(f for f in findings if f.id == "deaths.single.0")
    assert single.seconds_lost is None
    assert "cannot be measured" in single.detail


def test_a_single_death_finding_names_the_ability_that_killed() -> None:
    deaths = (a_death("Emberkin", 11, 1_000, 10.0, killing_blow_id=1297749),)
    findings = analyse_deaths(deaths, locate_in_a_run, SCOPE_A_RUN)
    single = next(f for f in findings if f.id.startswith("deaths.single."))
    assert single.ability_id == 1297749
    assert single.ability_name == "Molten Scar"


def test_a_death_whose_killing_blow_has_no_id_names_no_ability() -> None:
    # `a_death` leaves killing_blow_id at Death's default of 0, which the
    # dictionary maps to "Unknown Ability" with a real axe icon.
    findings = analyse_deaths(
        (a_death("Emberkin", 11, 1_000, 10.0),), locate_in_a_run, SCOPE_A_RUN
    )
    single = next(f for f in findings if f.id.startswith("deaths.single."))
    assert single.ability_id is None


def test_a_chain_of_wholly_unmeasured_deaths_reports_no_seconds_lost() -> None:
    findings = analyse_deaths(
        (
            a_death("Emberkin", 11, 30_000, None),
            a_death("Sublime", 12, 33_000, None),
        ),
        locate_in_a_run,
        SCOPE_A_RUN,
    )
    chain = next(f for f in findings if f.id.startswith("deaths.chain."))
    assert chain.seconds_lost is None
    assert "cannot be measured" in chain.detail


def test_repeat_dying_players_sharing_a_name_are_kept_separate() -> None:
    findings = analyse_deaths(
        (
            a_death("Emberkin", 11, 1_000, 10.0),
            a_death("Emberkin", 12, 100_000, 5.0),
            a_death("Emberkin", 11, 200_000, 8.0),
            a_death("Emberkin", 12, 300_000, 3.0),
        ),
        locate_in_a_run,
        SCOPE_A_RUN,
    )
    repeats = [f for f in findings if f.id.startswith("deaths.repeat.")]
    assert len(repeats) == 2

    actor_11 = next(f for f in repeats if f.id == "deaths.repeat.Emberkin.11")
    actor_12 = next(f for f in repeats if f.id == "deaths.repeat.Emberkin.12")
    assert actor_11.id != actor_12.id

    assert "2" in actor_11.detail
    assert actor_11.seconds_lost == 18.0
    # Pull 0 starts at 0ms: the pull-relative offsets below are unambiguous, and
    # the other actor's deaths (at 100_000ms and 300_000ms) must not leak in.
    assert actor_11.evidence == ("Molten Scar at pull 0, 1s in", "Molten Scar at pull 0, 200s in")

    assert "2" in actor_12.detail
    assert actor_12.seconds_lost == 8.0
    assert actor_12.evidence == (
        "Molten Scar at pull 0, 100s in", "Molten Scar at pull 0, 300s in"
    )


def test_a_transitive_chain_groups_all_three_deaths() -> None:
    # A-B within CHAIN_WINDOW_MS, B-C within CHAIN_WINDOW_MS, A-C outside it: the
    # module groups each death against the last one already in its group, so all
    # three belong to a single chain rather than A splitting off from C.
    findings = analyse_deaths(
        (
            a_death("Emberkin", 11, 0, 10.0),
            a_death("Sublime", 12, 9_000, 8.0),
            a_death("Emberkin", 11, 17_000, 5.0),
        ),
        locate_in_a_run,
        SCOPE_A_RUN,
    )
    chains = [f for f in findings if f.id.startswith("deaths.chain.")]
    assert len(chains) == 1
    assert chains[0].title == "3 deaths within 10s"
    assert chains[0].seconds_lost == 23.0


def test_the_total_does_not_claim_to_exceed_the_timer_penalty() -> None:
    findings = analyse_deaths(
        (a_death("Emberkin", 11, 1_000, 3.0),), locate_in_a_run, SCOPE_A_RUN
    )
    total = next(f for f in findings if f.id == "deaths.total")
    assert "longer than the timer penalty" not in total.detail
    assert "cast at another actor" in total.detail


def test_the_default_cost_detail_names_the_time_decomposition() -> None:
    """A caller that says nothing gets the Mythic+ sentence, byte-identical.

    `analyse` (the Mythic+ service) calls `analyse_deaths` without
    `cost_detail_suffix` at all, so this default is what every keystone report
    has always read; it must not drift when a raid caller starts passing its
    own.
    """
    findings = analyse_deaths(
        (a_death("Emberkin", 11, 1_000, 3.0),), locate_in_a_run, SCOPE_A_RUN
    )
    total = next(f for f in findings if f.id == "deaths.total")
    assert total.detail == (
        "Measured from each death to that player's first cast at another actor: the "
        "time the group played without them. The timer penalty is counted separately, "
        "in the time decomposition."
    )


def test_a_caller_can_omit_the_timer_penalty_sentence() -> None:
    """A raid fight has no timer penalty and no time decomposition to point at.

    `analyse_encounter` passes `cost_detail_suffix=""` for exactly this reason;
    this is the same behaviour exercised directly, at the unit this branch
    settled on: a caller-supplied piece of text, not a branch on aggregate type.
    """
    findings = analyse_deaths(
        (a_death("Emberkin", 11, 1_000, 3.0),), locate_in_a_run, SCOPE_A_RUN,
        cost_detail_suffix="",
    )
    total = next(f for f in findings if f.id == "deaths.total")
    assert total.detail == (
        "Measured from each death to that player's first cast at another actor: the "
        "time the group played without them."
    )
    assert "timer penalty" not in total.detail
    assert "time decomposition" not in total.detail


def test_a_death_outside_every_pull_is_reported_without_inventing_one() -> None:
    """A death whose `pull_index` is None fell outside every pull window.

    The evidence must say so rather than reporting a raw report-wide millisecond
    offset (meaningless across an evening-long log) or attributing the death to
    a pull it did not happen in.
    """
    findings = analyse_deaths(
        (a_death("Emberkin", 11, 1_000, 10.0, pull_index=None),),
        locate_in_a_run,
        SCOPE_A_RUN,
    )
    single = next(f for f in findings if f.id == "deaths.single.0")
    assert single.evidence == ("outside any pull",)
    assert single.pull_index is None
