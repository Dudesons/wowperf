# ABOUTME: Behaviour tests for buff and debuff uptime against a top parse, on boss pulls only.
# ABOUTME: The interesting cases are a missing reference, a small sample, and a gap below cut-off.

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.reference import Comparability, ParseRow
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, ParseMember, ParseSample
from wowperf.domain.comparison.uptime import (
    UPTIME_GAP_FRACTION,
    boss_windows,
    compare_uptime,
    compare_uptime_sample,
)
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player, Pull, Run


def a_player(name: str = "Stonewake", actor_id: int = 7) -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=315
    )


def a_pull(index: int, start_ms: int, end_ms: int, encounter_id: int) -> Pull:
    return Pull(
        index=index,
        pull_id=index,
        name="Pack",
        encounter_id=encounter_id,
        start_ms=start_ms,
        end_ms=end_ms,
        killed=True,
        x=0,
        y=0,
        enemies=(),
    )


def a_run(*pulls: Pull, player: Player | None = None) -> Run:
    return Run(
        report_code="abc123",
        fight_id=1,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=16,
        affix_ids=(),
        keystone_time_ms=1_800_000,
        keystone_bonus=1,
        count_reached=100,
        count_required=100,
        npc_counts=(),
        players=(player or a_player(),),
        pulls=pulls,
    )


def an_aura(ability_id: int, name: str, *bands: tuple[int, int]) -> Aura:
    return Aura(
        ability_id=ability_id,
        name=name,
        total_uptime_ms=sum(end - start for start, end in bands),
        uses=len(bands),
        bands=tuple(AuraBand(start_ms=start, end_ms=end) for start, end in bands),
    )


def ids(findings: list[Finding], prefix: str) -> list[str]:
    return [f.id for f in findings if f.id.startswith(prefix)]


BOSS = a_pull(0, 0, 100_000, encounter_id=12825)
TRASH = a_pull(1, 100_000, 200_000, encounter_id=0)


def test_boss_windows_covers_boss_pulls_only() -> None:
    assert boss_windows(a_run(BOSS, TRASH)) == ((0, 100_000),)


def test_an_uptime_gap_on_self_is_reported() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),))

    findings = compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Wipsdk")
    reported = [f for f in findings if f.id.startswith("compare.uptime.self.")]

    assert len(reported) == 1
    assert "Coagulopathy" in reported[0].title
    assert reported[0].confidence is Confidence.DERIVED
    assert reported[0].seconds_lost is None


def test_the_inert_on_target_plumbing_still_reports_a_gap_if_ever_fed_data() -> None:
    """`on_targets` is always empty against the live API (2026-09-05,
    `.claude/skills/wcl-api/SKILL.md`, "The debuff half cannot be scoped to one
    caster"), so this path never fires in production. It is kept — deliberately, by
    controller ruling — as correct code for a query that returns nothing today, ready
    if a working query is ever found. This test hand-builds `on_targets` data rather
    than exercising the real query, so it covers the plumbing, not a working feature.
    """
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))
    our_auras = PlayerAuras(actor_id=7, on_targets=(an_aura(55095, "Frost Fever", (0, 10_000)),))
    their_auras = PlayerAuras(actor_id=3, on_targets=(an_aura(55095, "Frost Fever", (0, 95_000)),))

    findings = compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Wipsdk")

    assert ids(findings, "compare.uptime.target.") == ["compare.uptime.target.0"]
    assert ids(findings, "compare.uptime.self.") == []


def test_uptime_outside_boss_pulls_is_not_counted() -> None:
    ours = a_run(BOSS, TRASH)
    theirs = a_run(BOSS, TRASH, player=a_player("Wipsdk", 3))
    # Ours is up for the whole boss pull; theirs only during trash.
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 100_000)),))
    their_auras = PlayerAuras(
        actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (100_000, 200_000)),)
    )

    findings = compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Wipsdk")

    assert ids(findings, "compare.uptime.") == []


def test_a_gap_below_the_cut_off_is_left_alone() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))
    gap = int((UPTIME_GAP_FRACTION - 0.05) * 100_000)
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 80_000)),))
    their_auras = PlayerAuras(
        actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 80_000 + gap)),)
    )

    findings = compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Wipsdk")

    assert ids(findings, "compare.uptime.") == []


def test_an_aura_the_reference_barely_carried_is_not_argued_from() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 5_000)),))

    findings = compare_uptime(
        ours, PlayerAuras(actor_id=7), a_player(), theirs, their_auras, "Wipsdk"
    )

    assert ids(findings, "compare.uptime.") == []


def test_a_missing_reference_says_so_rather_than_reporting_nothing() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))

    findings = compare_uptime(ours, PlayerAuras(actor_id=7), a_player(), theirs, None, "Wipsdk")

    assert ids(findings, "compare.uptime.") == ["compare.uptime.unavailable"]
    assert findings[0].seconds_lost is None
    assert "our aura data present" in findings[0].evidence
    assert "their aura data absent" in findings[0].evidence


def test_our_own_missing_aura_data_is_named_as_the_cause() -> None:
    """Our aura data can be the missing half even when the reference's own data is real."""
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),))

    findings = compare_uptime(ours, None, a_player(), theirs, their_auras, "Wipsdk")

    assert ids(findings, "compare.uptime.") == ["compare.uptime.unavailable"]
    assert findings[0].seconds_lost is None
    assert "our aura data absent" in findings[0].evidence
    assert "their aura data present" in findings[0].evidence


def test_a_run_with_no_boss_pulls_says_so_instead_of_dividing_by_zero() -> None:
    ours = a_run(TRASH)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))

    findings = compare_uptime(
        ours, PlayerAuras(actor_id=7), a_player(), theirs, PlayerAuras(actor_id=3), "Wipsdk"
    )

    assert ids(findings, "compare.uptime.") == ["compare.uptime.unavailable"]


def test_a_gap_findings_detail_warns_the_comparison_is_by_exact_ability() -> None:
    """A 0% gap can be a different item of the same kind, or gear the player lacks —
    not proof that nothing was used, since the comparison keys on exact ability id."""
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),))

    findings = compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Wipsdk")
    reported = [f for f in findings if f.id.startswith("compare.uptime.self.")]

    assert "gear this player does not own" in reported[0].detail


def test_no_more_than_the_cap_is_reported() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))
    # Our side must carry each ability at a nonzero fraction, or every one of
    # these gaps would now be dropped as "we never had it at all" (see
    # test_an_aura_we_never_carried_at_all_produces_no_finding below).
    our_auras = PlayerAuras(
        actor_id=7,
        on_self=tuple(an_aura(100 + n, f"Buff {n}", (0, 10_000)) for n in range(8)),
    )
    their_auras = PlayerAuras(
        actor_id=3,
        on_self=tuple(an_aura(100 + n, f"Buff {n}", (0, 90_000)) for n in range(8)),
    )

    findings = compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Wipsdk")

    assert len(ids(findings, "compare.uptime.self.")) == 5


def test_an_aura_we_never_carried_at_all_produces_no_finding() -> None:
    """`onSelf` has no source filter, so it returns teammate-cast buffs, consumables,
    and gear procs alongside the player's own buffs. Reporting a 0% for one of those
    blames the player for a button that isn't theirs to press — a Shadow Priest's
    Power Infusion is not something a Blood Death Knight can act on. Attribution by
    exact ability id can only be trusted when our side carried the ability at all;
    "they used it and we never did" for anything a player actually casts is already
    covered by `compare_spells`'s missing-spell branch."""
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))
    their_auras = PlayerAuras(
        actor_id=3, on_self=(an_aura(10060, "Power Infusion", (0, 33_000)),)
    )

    findings = compare_uptime(
        ours, PlayerAuras(actor_id=7), a_player(), theirs, their_auras, "Wipsdk"
    )

    assert ids(findings, "compare.uptime.") == []


def test_an_aura_both_sides_carried_still_reports_a_real_gap() -> None:
    """Skipping abilities we never carried at all must not swallow the case the
    feature exists for: both sides had it, and one carried it much longer."""
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))
    our_auras = PlayerAuras(
        actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),)
    )
    their_auras = PlayerAuras(
        actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),)
    )

    findings = compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Wipsdk")

    assert ids(findings, "compare.uptime.self.") == ["compare.uptime.self.0"]


# --- compare_uptime_sample ---------------------------------------------------

ICEBOUND = 194879
"""Carried by only 2 of the 5 members below: below MIN_SAMPLE_FOR_AGGREGATE, reported nowhere."""


def a_sample_member(
    name: str, actor_id: int, auras: tuple[tuple[int, str, int], ...] | None
) -> ParseMember:
    """A parse-sample member on a BOSS-shaped pull matching OUR_RUN's.

    `auras` is (ability_id, name, end_ms) triples, each an on-self band running from 0 to
    end_ms — a fraction of BOSS's 100_000ms window. `None` means no aura data at all, the
    state `aura_eligible` excludes.
    """
    player = a_player(name, actor_id)
    run = a_run(BOSS, player=player)
    player_auras = (
        PlayerAuras(
            actor_id=actor_id,
            on_self=tuple(
                an_aura(ability_id, aura_name, (0, end_ms))
                for ability_id, aura_name, end_ms in auras
            ),
        )
        if auras is not None
        else None
    )
    return ParseMember(
        row=ParseRow(
            report_code=f"REF{actor_id}",
            fight_id=1,
            keystone_level=16,
            duration_ms=100_000,
            character_name=name,
            class_name="DeathKnight",
            spec="Blood",
        ),
        run=run,
        comparability=Comparability(our_level=16, their_level=16),
        auras=player_auras,
    )


SUBJECT = a_player()
OUR_RUN = a_run(BOSS)
OUR_AURAS = PlayerAuras(
    actor_id=7,
    on_self=(
        an_aura(391477, "Coagulopathy", (0, 20_000)),
        an_aura(ICEBOUND, "Icebound Fortitude", (0, 10_000)),
    ),
)

# Four of five carry Coagulopathy, at fractions whose median clears both
# MIN_UPTIME_FRACTION and UPTIME_GAP_FRACTION against OUR_AURAS's 20%. Two of
# those four also carry Icebound Fortitude — one short of the floor, so that
# gap must not surface no matter how wide it looks. The fifth carries no aura
# data at all.
SAMPLE_OF_FIVE = ParseSample(
    members=(
        a_sample_member(
            "Bríala",
            11,
            ((391477, "Coagulopathy", 90_000), (ICEBOUND, "Icebound Fortitude", 90_000)),
        ),
        a_sample_member(
            "Dawnseeker",
            12,
            ((391477, "Coagulopathy", 80_000), (ICEBOUND, "Icebound Fortitude", 85_000)),
        ),
        a_sample_member("Emberfall", 13, ((391477, "Coagulopathy", 70_000),)),
        a_sample_member("Frostwhisper", 14, ((391477, "Coagulopathy", 60_000),)),
        a_sample_member("Glimmerose", 15, None),
    )
)

SAMPLE_WITHOUT_AURAS = ParseSample(
    members=tuple(member.model_copy(update={"auras": None}) for member in SAMPLE_OF_FIVE.members)
)


def test_uptime_is_the_median_of_the_members_that_had_aura_data() -> None:
    findings = compare_uptime_sample(OUR_RUN, OUR_AURAS, SUBJECT, SAMPLE_OF_FIVE)

    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    assert "4 top parses kept" in gap.title and "a median" in gap.title
    assert gap.confidence is Confidence.DERIVED
    assert gap.seconds_lost is None
    # A median title states no count for a digit-free narrative to echo.
    assert gap.quantifier == ""


def test_members_without_aura_data_are_reported_not_silently_dropped() -> None:
    findings = compare_uptime_sample(OUR_RUN, OUR_AURAS, SUBJECT, SAMPLE_OF_FIVE)

    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    assert "1 of 5 references had no aura data" in gap.evidence


def test_the_detail_no_longer_blames_a_single_players_gear() -> None:
    findings = compare_uptime_sample(OUR_RUN, OUR_AURAS, SUBJECT, SAMPLE_OF_FIVE)

    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    assert "gear this player does not own" not in gap.detail


def test_an_ability_carried_by_too_few_parses_is_not_reported() -> None:
    """Icebound Fortitude reaches only 2 of the 5 members — one short of the floor
    the sample relies on to filter out a one-off proc — so it must not be reported
    even though both carriers are far above OUR_AURAS's 10% on it."""
    assert 2 < MIN_SAMPLE_FOR_AGGREGATE

    findings = compare_uptime_sample(OUR_RUN, OUR_AURAS, SUBJECT, SAMPLE_OF_FIVE)

    assert not any(str(ICEBOUND) in line for f in findings for line in f.evidence)
    assert not any("Icebound Fortitude" in f.title for f in findings)


def test_no_aura_data_at_all_still_reports_unavailable() -> None:
    findings = compare_uptime_sample(OUR_RUN, OUR_AURAS, SUBJECT, SAMPLE_WITHOUT_AURAS)

    assert findings[0].id == "compare.uptime.unavailable"


def test_no_reference_aura_data_blames_the_references_and_not_our_own_side() -> None:
    """`cli._fetch_parse_auras` asks for our own aura data only once a member's
    counterpart resolves, so with no member carrying auras our own query may
    never have been issued. Reporting "our aura data absent" would name a
    failure that never happened."""
    findings = compare_uptime_sample(OUR_RUN, None, SUBJECT, SAMPLE_WITHOUT_AURAS)

    assert findings[0].id == "compare.uptime.unavailable"
    assert "0 of 5 references returned aura data" in findings[0].evidence
    assert not any("our aura data" in line for line in findings[0].evidence)


def test_a_wholly_empty_sample_produces_no_findings() -> None:
    # `service.compare()` already says "nothing to compare against" once, as
    # `compare.parse.unavailable`; this must not crash, and must not repeat it.
    findings = compare_uptime_sample(OUR_RUN, OUR_AURAS, SUBJECT, ParseSample())

    assert findings == []


def test_below_the_floor_the_pairwise_wording_is_used() -> None:
    below_floor = ParseSample(members=SAMPLE_OF_FIVE.members[: MIN_SAMPLE_FOR_AGGREGATE - 1])

    findings = compare_uptime_sample(OUR_RUN, OUR_AURAS, SUBJECT, below_floor)

    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    assert "Bríala" in gap.title
    assert any("below the floor of" in line for line in gap.evidence)


def test_our_own_missing_aura_data_is_unavailable_even_with_an_aggregate_sample() -> None:
    """The sample has plenty of aura-eligible members; the failure is ours, not
    the sample's, so this must not read as "below the floor of"."""
    findings = compare_uptime_sample(OUR_RUN, None, SUBJECT, SAMPLE_OF_FIVE)

    assert findings[0].id == "compare.uptime.unavailable"
    assert not any(
        "below the floor of" in line for line in findings[0].evidence
    )


def test_our_own_run_with_no_boss_pulls_is_unavailable_even_with_an_aggregate_sample() -> None:
    """A run with no boss pulls has nothing to divide by on our side; the sample is
    otherwise well above the floor, so this must not read as "too few comparable
    references" either — the gap is ours, not the sample's."""
    ours_without_boss_pulls = a_run(TRASH)

    findings = compare_uptime_sample(ours_without_boss_pulls, OUR_AURAS, SUBJECT, SAMPLE_OF_FIVE)

    assert findings[0].id == "compare.uptime.unavailable"
    assert not any(
        "below the floor of" in line for line in findings[0].evidence
    )


def test_every_finding_id_is_unique_over_the_sample() -> None:
    ids_ = [f.id for f in compare_uptime_sample(OUR_RUN, OUR_AURAS, SUBJECT, SAMPLE_OF_FIVE)]

    assert len(ids_) == len(set(ids_))


def test_the_inert_on_target_plumbing_still_reports_a_gap_in_the_sample_if_ever_fed_data() -> None:
    """`on_targets` is always empty against the live API (2026-09-05,
    `.claude/skills/wcl-api/SKILL.md`, "The debuff half cannot be scoped to one caster"), so
    this path never fires in production, in the sample the same way it never fires pairwise.
    It is kept as correct code for a query that returns nothing today. This test hand-builds
    `on_targets` data rather than exercising the real query, so it covers the plumbing, not a
    working feature.
    """

    def a_target_member(name: str, actor_id: int, end_ms: int) -> ParseMember:
        run = a_run(BOSS, player=a_player(name, actor_id))
        auras = PlayerAuras(
            actor_id=actor_id, on_targets=(an_aura(55095, "Frost Fever", (0, end_ms)),)
        )
        return ParseMember(
            row=ParseRow(
                report_code=f"TGT{actor_id}",
                fight_id=1,
                keystone_level=16,
                duration_ms=100_000,
                character_name=name,
                class_name="DeathKnight",
                spec="Blood",
            ),
            run=run,
            comparability=Comparability(our_level=16, their_level=16),
            auras=auras,
        )

    sample = ParseSample(
        members=(
            a_target_member("Alpha", 21, 90_000),
            a_target_member("Beta", 22, 80_000),
            a_target_member("Gamma", 23, 70_000),
        )
    )
    our_target_auras = PlayerAuras(
        actor_id=7, on_targets=(an_aura(55095, "Frost Fever", (0, 10_000)),)
    )

    findings = compare_uptime_sample(OUR_RUN, our_target_auras, SUBJECT, sample)

    assert ids(findings, "compare.uptime.target.") == ["compare.uptime.target.0"]
    assert ids(findings, "compare.uptime.self.") == []
