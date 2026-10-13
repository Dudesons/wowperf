# ABOUTME: Behaviour tests for buff uptime against a top parse or sample, by each caller's rule.
# ABOUTME: The interesting cases are a missing reference, a small sample, and a gap below cut-off.

from collections.abc import Callable, Sequence

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.boss_debuffs import Withheld
from wowperf.domain.comparison.measures import StretchCell, Verdict
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, ParseMember, ParseSample
from wowperf.domain.comparison.spells import boss_seconds
from wowperf.domain.comparison.uptime import (
    UPTIME_GAP_FRACTION,
    boss_windows,
    compare_uptime,
    compare_uptime_sample,
    fight_seconds,
    fight_seconds_of,
    key_clock_uptime,
    seconds_up_in,
    seconds_up_over_the_fight,
    stretch_cell,
    uptime_measures,
    whole_fight_uptime,
    without_boss_pulls,
)
from wowperf.domain.comparison.wording import DUNGEON, KEY
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player, Pull, Run


def a_player(name: str = "Stonewake", actor_id: int = 7) -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=315
    )


OUR_NAME = "Stonewake (actor 7)"
"""The spelling `display_names` gives a name two roster members share.

Deliberately not `a_player().name`: every title below is built from the name
the caller passes in, and a fixture that passed the roster's own name would
keep passing if this module went back to reading it off `Player` — which is
the bug that put one player's name on another player's finding.
"""


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


def a_reference(
    run: Run, auras: PlayerAuras | None, name: str = "Bríala", report_code: str = "REF1"
) -> ParseMember:
    """One parse reference, built from the run a test wrote to describe it.

    The member carries that run's boss seconds, roster and route rather than
    the run itself, which is the whole of design 8.2's narrowing: a raid
    reference has none of the three to take from a run it does not have.
    """
    return ParseMember(
        character_name=name,
        report_code=report_code,
        fight_id=1,
        boss_seconds=boss_seconds(run.pulls),
        players=run.players,
        auras=auras,
        pulls=run.pulls,
    )


def on_boss_pulls(
    pulls: Sequence[Pull], fight_ms: tuple[int, int] | None
) -> Callable[[Aura], float]:
    """This module's rule: uptime inside a route's boss pulls, the fight's clock ignored.

    The comparison's own branches -- the floor, the gap bar, the fallbacks -- do
    not depend on which stretch a rule reads, so this module drives them over
    boss pulls, where its fixtures put their bands. The rule a real key binds
    is `key_clock_uptime`, pinned below.
    """
    return seconds_up_in(boss_windows(pulls))


def pairwise_uptime(
    ours: Run,
    our_auras: PlayerAuras | None,
    our_name: str,
    theirs: ParseMember,
) -> list[Finding]:
    """`compare_uptime` for a Mythic+ run, whose route decides which milliseconds count.

    Every run in this module is a dungeon, read here over its boss pulls by
    `on_boss_pulls`, and our own side is the two values that route produces.
    What a raid binds instead is `test_parse_axis`'s subject.
    """
    return compare_uptime(
        ours.pulls, boss_seconds(ours.pulls), our_auras, our_name, theirs,
        measured=on_boss_pulls, words=DUNGEON,
    )


def sample_uptime(
    ours: Run, our_auras: PlayerAuras | None, our_name: str, sample: ParseSample
) -> list[Finding]:
    """`compare_uptime_sample` for a Mythic+ run, bound the way `pairwise_uptime` is."""
    return compare_uptime_sample(
        ours.pulls, boss_seconds(ours.pulls), our_auras, our_name, sample,
        measured=on_boss_pulls, words=DUNGEON,
    )


def test_boss_windows_covers_boss_pulls_only() -> None:
    assert boss_windows(a_run(BOSS, TRASH).pulls) == ((0, 100_000),)


def test_overlapping_bands_over_a_whole_fight_are_counted_once() -> None:
    """The raid rule's one distinguishing behaviour: it merges before it sums.

    Nothing in the aura table's own response promises the bands it returns are
    disjoint. A rule that added band lengths, or that read `total_uptime_ms`,
    would report 25s here for 20s of real uptime -- and every other fixture in
    this suite carries one band per aura, where all three readings agree.
    """
    aura = an_aura(391477, "Coagulopathy", (0, 10_000), (5_000, 20_000))

    assert aura.total_uptime_ms == 25_000  # the sum of the parts, which is not the union
    assert seconds_up_over_the_fight(aura) == 20.0
    assert whole_fight_uptime((), None) is seconds_up_over_the_fight


def test_an_aura_with_no_bands_is_up_for_no_seconds_over_a_whole_fight() -> None:
    assert seconds_up_over_the_fight(an_aura(391477, "Coagulopathy")) == 0.0


def test_the_dungeon_wording_over_a_boss_pull_rule_names_boss_pull_time() -> None:
    """The comparison's pairwise sentences under `DUNGEON`'s words and a boss-pull rule.

    A Mythic+ run's buffs are bound to `KEY` and the key clock, not to this
    pairing; their sentences are pinned by the key-clock tests below. This
    one holds the sentences `DUNGEON` alone words, whole and with numbers. The
    raid rendering is asserted in `test_parse_axis.py`. The two sides' boss
    time differs, so neither figure below is reproducible from the other's
    denominator.
    """
    ours = a_run(BOSS)
    theirs = a_run(a_pull(0, 0, 80_000, encounter_id=12825), player=a_player("Bríala", 3))
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 60_000)),))

    findings = pairwise_uptime(
        ours, our_auras, OUR_NAME, a_reference(theirs, their_auras)
    )

    assert findings[0].detail == (
        "Both figures are the share of boss-pull time the aura was present, which is "
        "comparable even though the two fights ran for different lengths. A shorter fight "
        "at a different keystone level still changes what fits, so read a narrow gap as "
        "noise. This compares by exact ability, though, so a gap can also mean a different "
        "item of the same kind, or gear this player does not own — not that nothing was "
        "used at all."
    )
    # 60s of their 80s against 20s of our 100s: 75% against 20%.
    assert "75%" in findings[0].title and "20%" in findings[0].title
    assert "ours over 100s of boss pulls" in findings[0].evidence
    assert "theirs over 80s of boss pulls" in findings[0].evidence


def test_the_dungeon_unavailable_sentence_names_boss_pulls() -> None:
    ours = a_run(BOSS)
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),))
    theirs = a_reference(a_run(TRASH), our_auras)

    findings = pairwise_uptime(ours, our_auras, OUR_NAME, theirs)

    assert findings[0].detail == (
        "An uptime comparison needs boss pulls on both sides and aura data for both "
        "players. One of those is missing, so no uptime numbers are reported rather than "
        "numbers from an unlike sample."
    )


def test_the_reference_named_in_a_pairwise_title_is_the_member_being_compared() -> None:
    """One identity, one channel.

    The member already carries its own name, and a second argument carrying one
    beside it is exactly the shape `compare_uptime`'s docstring warns of: two
    channels for one identity is how one player's figure ends up under another
    player's name. The name in this sentence is the member's own.
    """
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Кириллица", 3))
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),))

    findings = pairwise_uptime(
        ours, our_auras, OUR_NAME, a_reference(theirs, their_auras, name="Кириллица")
    )

    assert findings[0].title == (
        f"Coagulopathy was up for 90% of Кириллица's boss time, 20% of {OUR_NAME}'s"
    )


def test_an_uptime_gap_on_self_is_reported() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),))

    findings = pairwise_uptime(
        ours, our_auras, OUR_NAME, a_reference(theirs, their_auras)
    )
    reported = [f for f in findings if f.id.startswith("compare.uptime.self.")]

    assert len(reported) == 1
    assert "Coagulopathy" in reported[0].title
    assert reported[0].confidence is Confidence.DERIVED
    assert reported[0].seconds_lost is None


def test_uptime_outside_boss_pulls_is_not_counted() -> None:
    ours = a_run(BOSS, TRASH)
    theirs = a_run(BOSS, TRASH, player=a_player("Bríala", 3))
    # Ours is up for the whole boss pull; theirs only during trash.
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 100_000)),))
    their_auras = PlayerAuras(
        actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (100_000, 200_000)),)
    )

    findings = pairwise_uptime(
        ours, our_auras, OUR_NAME, a_reference(theirs, their_auras)
    )

    assert ids(findings, "compare.uptime.") == []


def test_a_gap_below_the_cut_off_is_left_alone() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    gap = int((UPTIME_GAP_FRACTION - 0.05) * 100_000)
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 80_000)),))
    their_auras = PlayerAuras(
        actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 80_000 + gap)),)
    )

    findings = pairwise_uptime(
        ours, our_auras, OUR_NAME, a_reference(theirs, their_auras)
    )

    assert ids(findings, "compare.uptime.") == []


def test_an_aura_the_reference_barely_carried_is_not_argued_from() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 5_000)),))

    findings = pairwise_uptime(
        ours, PlayerAuras(actor_id=7), OUR_NAME, a_reference(theirs, their_auras)
    )

    assert ids(findings, "compare.uptime.") == []


def test_a_missing_reference_says_so_rather_than_reporting_nothing() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))

    findings = pairwise_uptime(
        ours, PlayerAuras(actor_id=7), OUR_NAME, a_reference(theirs, None)
    )

    assert ids(findings, "compare.uptime.") == ["compare.uptime.unavailable"]
    assert findings[0].seconds_lost is None
    # Whole, because the two seconds lines name what those seconds are seconds
    # of, and that noun comes from `Wording` now that a raid reads this row too.
    # A substring check on the aura halves never looked at it.
    assert list(findings[0].evidence) == [
        "our boss time 100s",
        "their boss time 100s",
        "our aura data present",
        "their aura data absent",
    ]


def test_our_own_missing_aura_data_is_named_as_the_cause() -> None:
    """Our aura data can be the missing half even when the reference's own data is real."""
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),))

    findings = pairwise_uptime(
        ours, None, OUR_NAME, a_reference(theirs, their_auras)
    )

    assert ids(findings, "compare.uptime.") == ["compare.uptime.unavailable"]
    assert findings[0].seconds_lost is None
    assert "our aura data absent" in findings[0].evidence
    assert "their aura data present" in findings[0].evidence


def test_a_run_with_no_boss_pulls_says_so_instead_of_dividing_by_zero() -> None:
    ours = a_run(TRASH)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))

    findings = pairwise_uptime(
        ours, PlayerAuras(actor_id=7), OUR_NAME, a_reference(theirs, PlayerAuras(actor_id=3))
    )

    assert ids(findings, "compare.uptime.") == ["compare.uptime.unavailable"]


def test_a_gap_findings_detail_warns_the_comparison_is_by_exact_ability() -> None:
    """A 0% gap can be a different item of the same kind, or gear the player lacks —
    not proof that nothing was used, since the comparison keys on exact ability id."""
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),))

    findings = pairwise_uptime(
        ours, our_auras, OUR_NAME, a_reference(theirs, their_auras)
    )
    reported = [f for f in findings if f.id.startswith("compare.uptime.self.")]

    assert "gear this player does not own" in reported[0].detail


def test_no_more_than_the_cap_is_reported() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
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

    findings = pairwise_uptime(
        ours, our_auras, OUR_NAME, a_reference(theirs, their_auras)
    )

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
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    their_auras = PlayerAuras(
        actor_id=3, on_self=(an_aura(10060, "Power Infusion", (0, 33_000)),)
    )

    findings = pairwise_uptime(
        ours, PlayerAuras(actor_id=7), OUR_NAME, a_reference(theirs, their_auras)
    )

    assert ids(findings, "compare.uptime.") == []


def test_an_aura_both_sides_carried_still_reports_a_real_gap() -> None:
    """Skipping abilities we never carried at all must not swallow the case the
    feature exists for: both sides had it, and one carried it much longer."""
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    our_auras = PlayerAuras(
        actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),)
    )
    their_auras = PlayerAuras(
        actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),)
    )

    findings = pairwise_uptime(
        ours, our_auras, OUR_NAME, a_reference(theirs, their_auras)
    )

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
    return a_reference(run, player_auras, name=name, report_code=f"REF{actor_id}")


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


SIPHON_STORM = 384267


def a_worded_member(actor_id: int, boss_ms: int, coagulopathy_ms: int, siphon_ms: int
                    ) -> ParseMember:
    """A reference on a boss pull of its own length, carrying two auras.

    The lengths differ from each other and from `OUR_RUN`'s, so no fraction the
    test below reads back could have come from the wrong denominator and still
    matched.
    """
    player = a_player("Stonewake", actor_id)
    run = a_run(a_pull(0, 0, boss_ms, encounter_id=12825), player=player)
    return a_reference(
        run,
        PlayerAuras(
            actor_id=actor_id,
            on_self=(
                an_aura(391477, "Coagulopathy", (0, coagulopathy_ms)),
                an_aura(SIPHON_STORM, "Siphon Storm", (0, siphon_ms)),
            ),
        ),
        name="Stonewake",
        report_code=f"REF{actor_id}",
    )


WORDED_SAMPLE = ParseSample(
    members=(
        a_worded_member(21, 90_000, 72_000, 27_000),
        a_worded_member(22, 80_000, 56_000, 24_000),
        a_worded_member(23, 120_000, 90_000, 36_000),
    )
)
"""Three references at 80%, 70% and 75% of their own boss time on Coagulopathy, and
30% each on a Siphon Storm our own side never carries."""


def test_the_dungeon_wording_over_a_boss_pull_rule_names_boss_pulls_in_a_sample() -> None:
    """The two sampled sentences under `DUNGEON`'s words and a boss-pull rule.

    A Mythic+ run's buffs are bound to `KEY` and the key clock, whose sampled
    sentences are pinned by `test_the_key_sampled_uptime_sentences_...` below.
    The golden report file holds neither: its fixture carries no reference
    run, so no comparison family reaches the page it renders.
    """
    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, WORDED_SAMPLE)
    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    unjudged = next(f for f in findings if f.id == "compare.uptime.unjudged")

    assert gap.detail == (
        "Both figures are the share of boss-pull time the aura was present, which is "
        "comparable even though the fights ran for different lengths. A shorter fight at a "
        "different keystone level still changes what fits, so read a narrow gap as noise. "
        "This compares by exact ability, so a gap can still mean a different item of the "
        "same kind — but the gap is stated over several top parses, not one player's "
        "build, so a single trinket this player happens not to own no longer explains it "
        "away."
    )
    assert gap.title == (
        f"Coagulopathy was up a median 75% of boss time across 3 top parses; 20% for "
        f"{OUR_NAME}"
    )
    assert "ours over 100s of boss pulls" in gap.evidence

    assert unjudged.title == f"1 aura the sample carried is not judged for {OUR_NAME}"
    assert unjudged.detail == (
        "Each of these was present over enough of the sample's boss time to compare, and "
        "absent from ours. It is named rather than measured: the aura table cannot say "
        "whose buff a row was, so a zero here may be a button this player never pressed or "
        "one a teammate never gave them, and the log does not separate the two. Check "
        "whether the build produces it before reading anything into it."
    )
    assert "Siphon Storm" in unjudged.evidence[0]
    assert "absent from our own boss pulls" in unjudged.evidence


def test_uptime_is_the_median_of_the_members_that_had_aura_data() -> None:
    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)

    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    # Both percentages are pinned, and against the right side of the sentence.
    # The reference's median is the higher of the two by construction, so a
    # title that swapped them would praise the player for the gap it reports.
    assert gap.title == (
        "Coagulopathy was up a median 75% of boss time across 4 top parses; 20% for "
        f"{OUR_NAME}"
    )
    assert gap.confidence is Confidence.DERIVED
    assert gap.seconds_lost is None
    # A median title states no count for a digit-free narrative to echo.
    assert gap.quantifier == ""


def test_a_sampled_uptime_finding_carries_both_sides_as_facts() -> None:
    # The same figures the title above pins, taken a third way for a panel to
    # lay out. Nothing recomputed, nothing parsed back out of the title.
    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)
    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    assert [(fact.label, fact.value) for fact in gap.facts] == [
        ("Ours", "20% of boss time"),
        ("Reference median", "75% of boss time"),
        ("Observed range", "60% to 90%"),
        ("Sample", "4 top parses"),
    ]


def test_an_uptime_fact_is_derived_because_a_share_is_computed() -> None:
    # An unset tier is what a panel draws measured with, so a share this
    # report divided out has to say derived rather than leave the line bare.
    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)
    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    assert all(fact.confidence is Confidence.DERIVED for fact in gap.facts[:3])
    assert gap.facts[3].confidence is None  # a count of parses, read not computed


def test_a_sampled_uptime_panel_reports_a_median_and_a_range_never_a_mean() -> None:
    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)
    labels = [fact.label for fact in
              next(f for f in findings if f.id == "compare.uptime.self.0").facts]
    assert "Reference median" in labels and "Observed range" in labels
    assert not any("mean" in label.lower() for label in labels)


def test_no_reference_player_is_named_in_a_sampled_uptime_finding() -> None:
    """An aggregate uptime is a claim about a population, the same as a sampled
    spell finding, so no member's character name may reach the page. The one
    place a name still appears is the below-floor pairwise fallback, which is a
    single reference's own comparison and says so."""
    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)

    assert findings, "the fixture must produce at least one aggregate finding"
    for name in ("Bríala", "Dawnseeker", "Emberfall", "Frostwhisper", "Glimmerose"):
        assert all(name not in finding.title for finding in findings)
        assert all(name not in finding.detail for finding in findings)
        assert all(name not in line for finding in findings for line in finding.evidence)


def test_members_without_aura_data_are_reported_not_silently_dropped() -> None:
    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)

    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    assert "1 of 5 references had no aura data" in gap.evidence


OUR_AURAS_WITHOUT_COAGULOPATHY = PlayerAuras(
    actor_id=7, on_self=(an_aura(ICEBOUND, "Icebound Fortitude", (0, 10_000)),)
)
"""Our side carries none of the aura four of the five members carry."""


def test_an_aura_the_sample_carried_and_we_did_not_is_named_as_unjudged() -> None:
    """Dropping it silently reads exactly like having nothing to say about it.

    The drop itself stays — `onSelf` has no source filter, so a zero here may be a
    teammate's buff this player was never given rather than a button they never
    pressed. What changes is that the reader is told the aura exists and was set
    aside, instead of the page implying it was never looked at.
    """
    findings = sample_uptime(
        OUR_RUN, OUR_AURAS_WITHOUT_COAGULOPATHY, OUR_NAME, SAMPLE_OF_FIVE
    )

    unjudged = next(f for f in findings if f.id == "compare.uptime.unjudged")
    assert "Coagulopathy" in " ".join(unjudged.evidence)


def test_an_unjudged_aura_produces_no_gap_row() -> None:
    """Naming it must not smuggle it back in as a measured gap: the whole reason it
    is set aside is that its zero cannot be attributed to this player."""
    findings = sample_uptime(
        OUR_RUN, OUR_AURAS_WITHOUT_COAGULOPATHY, OUR_NAME, SAMPLE_OF_FIVE
    )

    assert not any(f.id.startswith("compare.uptime.self.") for f in findings)


def test_an_aura_carried_by_too_few_parses_is_not_called_unjudged() -> None:
    """Icebound Fortitude reaches 2 of 5, below the aggregate floor, so the sample
    never had a figure to set aside. Naming it would invent a comparison."""
    ours = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),))

    findings = sample_uptime(OUR_RUN, ours, OUR_NAME, SAMPLE_OF_FIVE)

    assert not any(f.id == "compare.uptime.unjudged" for f in findings)


def test_the_detail_no_longer_blames_a_single_players_gear() -> None:
    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)

    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    assert "gear this player does not own" not in gap.detail


def test_an_ability_carried_by_too_few_parses_is_not_reported() -> None:
    """Icebound Fortitude reaches only 2 of the 5 members — one short of the floor
    the sample relies on to filter out a one-off proc — so it must not be reported
    even though both carriers are far above OUR_AURAS's 10% on it."""
    assert 2 < MIN_SAMPLE_FOR_AGGREGATE

    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)

    assert not any(str(ICEBOUND) in line for f in findings for line in f.evidence)
    assert not any("Icebound Fortitude" in f.title for f in findings)


def test_no_aura_data_at_all_still_reports_unavailable() -> None:
    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_WITHOUT_AURAS)

    assert findings[0].id == "compare.uptime.unavailable"


def test_no_reference_aura_data_blames_the_references_and_not_our_own_side() -> None:
    """`cli._fetch_parse_auras` asks for our own aura data only once a member's
    counterpart resolves, so with no member carrying auras our own query may
    never have been issued. Reporting "our aura data absent" would name a
    failure that never happened."""
    findings = sample_uptime(OUR_RUN, None, OUR_NAME, SAMPLE_WITHOUT_AURAS)

    assert findings[0].id == "compare.uptime.unavailable"
    assert "0 of 5 references returned aura data" in findings[0].evidence
    assert not any("our aura data" in line for line in findings[0].evidence)


def test_both_ways_of_being_unavailable_name_the_player() -> None:
    """Two branches mint `compare.uptime.unavailable` — one reference lacking
    aura data, and no reference having any — and a whole-group run emits one per
    player. A title naming nobody reads identically under every card, and the
    findings file the narrative is written from could not say whose it was."""
    no_reference_has_auras = sample_uptime(
        OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_WITHOUT_AURAS
    )
    our_own_side_has_none = sample_uptime(OUR_RUN, None, OUR_NAME, SAMPLE_OF_FIVE)

    for findings in (no_reference_has_auras, our_own_side_has_none):
        assert findings[0].id == "compare.uptime.unavailable"
        assert OUR_NAME in findings[0].title


def test_no_uptime_finding_promises_a_debuff_comparison() -> None:
    """Nothing here compares debuffs: the enemy-debuff table cannot be scoped to
    one caster, measured 2026-09-05 and recorded in the wcl-api skill under "The
    debuff half cannot be scoped to one caster". A title promising one is a
    promise the report cannot keep, so every branch is swept rather than the two
    that happened to carry the wording."""
    every_branch = (
        sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_WITHOUT_AURAS)
        + sample_uptime(OUR_RUN, None, OUR_NAME, SAMPLE_OF_FIVE)
        + sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)
        + pairwise_uptime(OUR_RUN, None, OUR_NAME, a_reference(OUR_RUN, None))
    )

    assert every_branch
    for finding in every_branch:
        assert "debuff" not in finding.title.lower()
        assert "debuff" not in finding.detail.lower()


def test_an_unavailable_uptime_says_which_half_it_could_not_compare() -> None:
    unavailable = [
        f
        for f in sample_uptime(OUR_RUN, None, OUR_NAME, SAMPLE_OF_FIVE)
        + sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_WITHOUT_AURAS)
        if f.id == "compare.uptime.unavailable"
    ]

    assert len(unavailable) == 2
    for finding in unavailable:
        assert finding.title.startswith("Buff uptime could not be compared")


def test_a_wholly_empty_sample_produces_no_findings() -> None:
    # `service.compare()` already says "nothing to compare against" once, as
    # `compare.parse.unavailable`; this must not crash, and must not repeat it.
    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, ParseSample())

    assert findings == []


def test_below_the_floor_the_pairwise_wording_is_used() -> None:
    below_floor = ParseSample(members=SAMPLE_OF_FIVE.members[: MIN_SAMPLE_FOR_AGGREGATE - 1])

    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, below_floor)

    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    # The pairwise branch's own wording, both percentages against the name
    # whose boss time each was measured over.
    assert gap.title == (
        f"Icebound Fortitude was up for 90% of Bríala's boss time, 10% of {OUR_NAME}'s"
    )
    # The facts whole, and the sample's noun stated as a literal: it is
    # `Wording`'s now, because a raid kill is not a run and this row serves
    # both axes -- and the dungeon rendering must not have moved a byte for
    # that. The twin of this assertion lives in `test_spells.py`, on the
    # pairwise rate row, because the two facts are written in two modules and
    # only one of them would move if the field were threaded at one site.
    assert [(fact.label, fact.value) for fact in gap.facts] == [
        ("Ours", "10% of boss time"),
        ("Reference", "90% of boss time"),
        ("Sample", "1 reference run"),
    ]
    assert any("below the floor of" in line for line in gap.evidence)


def test_our_own_missing_aura_data_is_unavailable_even_with_an_aggregate_sample() -> None:
    """The sample has plenty of aura-eligible members; the failure is ours, not
    the sample's, so this must not read as "below the floor of"."""
    findings = sample_uptime(OUR_RUN, None, OUR_NAME, SAMPLE_OF_FIVE)

    assert findings[0].id == "compare.uptime.unavailable"
    assert not any(
        "below the floor of" in line for line in findings[0].evidence
    )


def test_our_own_run_with_no_boss_pulls_is_unavailable_even_with_an_aggregate_sample() -> None:
    """A run with no boss pulls has nothing to divide by on our side; the sample is
    otherwise well above the floor, so this must not read as "too few comparable
    references" either — the gap is ours, not the sample's."""
    ours_without_boss_pulls = a_run(TRASH)

    findings = sample_uptime(ours_without_boss_pulls, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)

    assert findings[0].id == "compare.uptime.unavailable"
    assert not any(
        "below the floor of" in line for line in findings[0].evidence
    )


def test_every_finding_id_is_unique_over_the_sample() -> None:
    ids_ = [f.id for f in sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)]

    assert len(ids_) == len(set(ids_))


def test_an_uptime_gap_finding_names_the_aura_against_one_reference() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),))
    gap = next(
        f
        for f in pairwise_uptime(
            ours, our_auras, OUR_NAME, a_reference(theirs, their_auras)
        )
        if f.id.startswith("compare.uptime.")
    )
    assert gap.ability_id == 391477
    assert gap.ability_name == "Coagulopathy"
    assert gap.ability_name in gap.title


def test_an_uptime_gap_finding_names_the_aura_across_the_sample() -> None:
    gap = next(
        f for f in sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)
        if f.id.startswith("compare.uptime.")
    )
    assert gap.ability_id == 391477
    assert gap.ability_name == "Coagulopathy"
    assert gap.ability_name in gap.title


def test_no_uptime_title_says_a_player_kept_an_aura_up() -> None:
    """The family measures presence, and presence is all it may claim.

    A proc is not something a player keeps up: an execute-window proc and a
    proc-based hand buff both appear here, and "kept it up" credits the
    player with an agency the buff never gave them. The measurement is sound;
    the verb was the defect. Both wordings are checked, because the pairwise
    branch and the aggregate branch build their titles separately.
    """
    below_floor = ParseSample(members=SAMPLE_OF_FIVE.members[: MIN_SAMPLE_FOR_AGGREGATE - 1])
    aggregate = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)
    pairwise = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, below_floor)

    # Anchored on the row each branch must produce, so the absences below
    # cannot pass by the branch simply emitting nothing.
    assert any(f.id == "compare.uptime.self.0" for f in aggregate)
    assert any(f.id == "compare.uptime.self.0" for f in pairwise)
    for finding in aggregate + pairwise:
        assert "kept" not in finding.title, finding.title


def test_an_uptime_title_names_the_aura_before_it_names_anyone() -> None:
    """What was up is the subject; whose time it was up over is the measure.

    The old wording opened on a player and made the aura the object of a verb
    they did not perform.
    """
    findings = sample_uptime(OUR_RUN, OUR_AURAS, OUR_NAME, SAMPLE_OF_FIVE)

    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    # The literal, not `gap.ability_name`: an expected value read off the
    # object under test passes when the object is wrong in both places.
    assert gap.title.startswith("Coagulopathy was up")


# --- uptime_measures -----------------------------------------------------------


def test_uptime_measures_carry_a_verdict_per_aura() -> None:
    """Four outcomes, and the table has to tell them apart: a gap, a level aura,
    one we show none of, and one too few of the sample carried to judge."""
    names = {1: "Wide gap", 2: "Level", 3: "We have none", 4: "Too few carried it"}
    # Wide gap's three carriers are spread across 0.70, 0.90 and 0.95 rather than
    # a flat 0.90: with every carrier alike, their_median could be a mean, a
    # first or a last reading and still land on 0.90. Spread this way, only the
    # true middle value produces it -- a mean would read 0.85.
    per_member = [
        {1: 0.70, 2: 0.80, 3: 0.70, 4: 0.60},
        {1: 0.90, 2: 0.80, 3: 0.70},
        {1: 0.95, 2: 0.80, 3: 0.70},
    ]
    our_fractions = {1: ("Wide gap", 0.10), 2: ("Level", 0.78), 3: ("We have none", 0.0)}

    measures = {m.name: m for m in uptime_measures(our_fractions, per_member, names)}

    assert measures["Wide gap"].verdict is Verdict.BELOW
    assert measures["Wide gap"].their_median == 0.90
    assert measures["Level"].verdict is Verdict.LEVEL
    assert measures["We have none"].verdict is Verdict.UNJUDGED
    assert "Too few carried it" not in measures


def test_an_aura_the_sample_barely_carried_is_not_measured() -> None:
    """Below MIN_UPTIME_FRACTION the reference barely had it either, so there is
    nothing to argue from and nothing to put in a table."""
    names = {1: "Barely up"}
    per_member = [{1: 0.05}, {1: 0.05}, {1: 0.05}]

    measures = uptime_measures({1: ("Barely up", 0.0)}, per_member, names)

    assert measures == ()


def test_the_key_clock_rule_reads_the_fight_from_its_start_to_its_end() -> None:
    aura = an_aura(1, "Fixture Ward", (0, 50_000), (150_000, 250_000))

    assert key_clock_uptime((BOSS, TRASH), (0, 200_000))(aura) == 100.0
    assert key_clock_uptime((BOSS, TRASH), None)(aura) == 0.0


def test_without_boss_pulls_is_the_clock_less_every_boss_pull() -> None:
    first = a_pull(0, 100_000, 160_000, encounter_id=2001)
    trash = a_pull(1, 200_000, 260_000, encounter_id=0)
    second = a_pull(2, 300_000, 360_000, encounter_id=2002)

    assert without_boss_pulls((0, 400_000), (first, trash, second)) == (
        (0, 100_000),
        (160_000, 300_000),
        (360_000, 400_000),
    )
    assert without_boss_pulls((0, 100_000), (a_pull(0, 0, 100_000, encounter_id=2001),)) == ()


def test_without_boss_pulls_walks_past_overlapping_and_unordered_boss_pulls() -> None:
    # A boss pull nested inside another leaves no gap behind it, and a route
    # listed out of order is still walked from the clock's start to its end.
    wide = a_pull(0, 100_000, 300_000, encounter_id=2001)
    nested = a_pull(1, 150_000, 200_000, encounter_id=2002)
    assert without_boss_pulls((0, 400_000), (wide, nested)) == (
        (0, 100_000),
        (300_000, 400_000),
    )

    early = a_pull(0, 100_000, 160_000, encounter_id=2001)
    late = a_pull(1, 300_000, 360_000, encounter_id=2002)
    assert without_boss_pulls((0, 400_000), (late, early)) == (
        (0, 100_000),
        (160_000, 300_000),
        (360_000, 400_000),
    )


def test_without_boss_pulls_never_leaves_the_clock() -> None:
    boss = a_pull(0, 100_000, 160_000, encounter_id=2001)
    after = a_pull(1, 150_000, 200_000, encounter_id=2002)

    # The clock starts after zero, and a boss pull opens past its end.
    assert without_boss_pulls((10_000, 400_000), (boss,)) == (
        (10_000, 100_000),
        (160_000, 400_000),
    )
    assert without_boss_pulls((0, 100_000), (after,)) == ((0, 100_000),)


def test_a_fights_seconds_are_its_clock_and_no_clock_reads_zero() -> None:
    assert fight_seconds((10_000, 1_810_000)) == 1800.0
    assert fight_seconds(None) == 0.0


def test_a_boss_pull_warcraft_logs_lists_twice_is_one_window() -> None:
    # One encounter, start and end listed twice, as `dungeonPulls` lists some
    # wipes. Two windows would count its seconds twice in a sum over them while
    # `uptime_seconds_in` merges the aura's seconds in it once. The same boss
    # pulled again later is a window of its own.
    relisted = BOSS.model_copy(update={"index": 2, "pull_id": 2})
    again = a_pull(3, 300_000, 400_000, encounter_id=12825)

    assert boss_windows((BOSS, relisted, TRASH, again)) == (
        (0, 100_000),
        (300_000, 400_000),
    )


def test_a_reference_is_read_over_its_own_clock_when_the_rule_reads_one() -> None:
    # The reference's key runs 300s and carried the buff for 150s of it; its boss
    # pull, the default denominator, is 100s. Ours ran the same 300s and carried
    # it 30s. Over the two clocks that is 50% against 10%. Divided by boss
    # seconds, the reference would read 150%.
    theirs = a_reference(
        a_run(BOSS, TRASH),
        PlayerAuras(actor_id=11, on_self=(an_aura(1, "Fixture Ward", (0, 150_000)),)),
    ).model_copy(update={"fight_ms": (0, 300_000)})
    ours = PlayerAuras(actor_id=7, on_self=(an_aura(1, "Fixture Ward", (0, 30_000)),))

    findings = compare_uptime(
        (BOSS, TRASH), 300.0, ours, OUR_NAME, theirs,
        measured=key_clock_uptime, words=KEY, our_fight_ms=(0, 300_000), over=fight_seconds_of,
    )

    [gap] = [finding for finding in findings if finding.id == "compare.uptime.self.0"]
    assert gap.title == (
        "Fixture Ward was up for 50% of Bríala's key time, 10% of Stonewake (actor 7)'s"
    )


KEY_CLOCK_MS = (0, 300_000)


def a_key_clock_member(
    actor_id: int, key_ms: int, coagulopathy_ms: int, siphon_ms: int
) -> ParseMember:
    """A reference whose key ran `key_ms`, carrying two auras over its own clock.

    The clocks differ from each other and from `KEY_CLOCK_MS`, so no figure read
    back below could have come from the wrong denominator and still matched.
    """
    return a_worded_member(actor_id, 100_000, coagulopathy_ms, siphon_ms).model_copy(
        update={"fight_ms": (0, key_ms)}
    )


KEY_CLOCK_SAMPLE = ParseSample(
    members=(
        a_key_clock_member(31, 200_000, 160_000, 60_000),
        a_key_clock_member(32, 250_000, 175_000, 75_000),
        a_key_clock_member(33, 400_000, 300_000, 120_000),
    )
)
"""Three keys at 80%, 70% and 75% of their own clock on Coagulopathy, and 30% each on a
Siphon Storm our own side never carries."""

KEY_CLOCK_AURAS = PlayerAuras(
    actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 60_000)),)
)
"""Coagulopathy up for 60s of our 300s key: 20%."""


def test_the_key_sampled_uptime_sentences_name_the_key_clock_and_walking_between_pulls() -> None:
    """The Mythic+ rendering of the sampled sentences, bound the way `service.compare` binds them.

    Every buff finding of a real key reads these words, so the walking caveat
    that the key clock's decision accepts reaches the reader here, in the
    finding's own detail, as well as in the page's caption.
    """
    findings = compare_uptime_sample(
        OUR_RUN.pulls, fight_seconds(KEY_CLOCK_MS), KEY_CLOCK_AURAS, OUR_NAME, KEY_CLOCK_SAMPLE,
        measured=key_clock_uptime, words=KEY, our_fight_ms=KEY_CLOCK_MS, over=fight_seconds_of,
    )
    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    unjudged = next(f for f in findings if f.id == "compare.uptime.unjudged")

    assert gap.title == (
        f"Coagulopathy was up a median 75% of key time across 3 top parses; 20% for {OUR_NAME}"
    )
    assert gap.detail == (
        "Both figures are the share of the key's clock the aura was present, which is "
        "comparable even though the fights ran for different lengths. Key time runs from the "
        "key's start to its end with the walking between pulls included, so a buff only up "
        "in combat reads lower the more of the key was spent between pulls, and a reference "
        "that walked less reads higher whatever either player did. A different keystone "
        "level still changes what fits, so read a narrow gap as noise. This compares by "
        "exact ability, so a gap can still mean a different item of the same kind — but the "
        "gap is stated over several top parses, not one player's build, so a single trinket "
        "this player happens not to own no longer explains it away."
    )
    assert gap.evidence == (
        "ability 391477",
        "ours over 300s of the key",
        "range 70% to 80% across 3 top parses",
        "0 of 3 references had no aura data",
    )
    assert [(fact.label, fact.value) for fact in gap.facts] == [
        ("Ours", "20% of key time"),
        ("Reference median", "75% of key time"),
        ("Observed range", "70% to 80%"),
        ("Sample", "3 top parses"),
    ]

    assert unjudged.title == f"1 aura the sample carried is not judged for {OUR_NAME}"
    assert unjudged.detail == (
        "Each of these was present over enough of the sample's key time to compare, and "
        "absent from ours. It is named rather than measured: the aura table cannot say "
        "whose buff a row was, so a zero here may be a button this player never pressed or "
        "one a teammate never gave them, and the log does not separate the two. Check "
        "whether the build produces it before reading anything into it."
    )
    assert unjudged.evidence == (
        "Siphon Storm",
        "carried by at least 3 top parses each",
        "absent from our own key",
    )


def test_the_key_pairwise_uptime_sentences_name_the_key_clock_and_walking_between_pulls() -> None:
    theirs = a_key_clock_member(41, 200_000, 160_000, 60_000)

    findings = compare_uptime(
        OUR_RUN.pulls, fight_seconds(KEY_CLOCK_MS), KEY_CLOCK_AURAS, OUR_NAME, theirs,
        measured=key_clock_uptime, words=KEY, our_fight_ms=KEY_CLOCK_MS, over=fight_seconds_of,
    )
    [gap] = [finding for finding in findings if finding.id == "compare.uptime.self.0"]

    assert gap.detail == (
        "Both figures are the share of the key's clock the aura was present, which is "
        "comparable even though the two fights ran for different lengths. Key time runs from "
        "the key's start to its end with the walking between pulls included, so a buff only "
        "up in combat reads lower the more of the key was spent between pulls, and a "
        "reference that walked less reads higher whatever either player did. A different "
        "keystone level still changes what fits, so read a narrow gap as noise. This "
        "compares by exact ability, though, so a gap can also mean a different item of the "
        "same kind, or gear this player does not own — not that nothing was used at all."
    )
    assert gap.evidence == (
        "ability 391477",
        "ours over 300s of the key",
        "theirs over 200s of the key",
    )
    assert [(fact.label, fact.value) for fact in gap.facts] == [
        ("Ours", "20% of key time"),
        ("Reference", "80% of key time"),
        ("Sample", "1 reference run"),
    ]


def test_the_key_unavailable_sentence_names_a_key_clock() -> None:
    """A side with no clock has no key time, and the finding says which clock was missing."""
    theirs = a_key_clock_member(42, 200_000, 160_000, 60_000)

    [finding] = compare_uptime(
        OUR_RUN.pulls, fight_seconds(None), KEY_CLOCK_AURAS, OUR_NAME, theirs,
        measured=key_clock_uptime, words=KEY, our_fight_ms=None, over=fight_seconds_of,
    )

    assert finding.id == "compare.uptime.unavailable"
    assert finding.confidence is Confidence.MEASURED
    assert finding.detail == (
        "An uptime comparison needs a key clock on both sides and aura data for both "
        "players. One of those is missing, so no uptime numbers are reported rather than "
        "numbers from an unlike sample."
    )
    assert finding.evidence == (
        "our key time 0s",
        "their key time 200s",
        "our aura data present",
        "their aura data present",
    )


def test_a_kept_aura_under_the_floor_is_not_judged_and_comes_after_the_judged() -> None:
    names = {1: "Kept", 2: "Judged"}
    per_member = [{1: 0.05, 2: 0.6}] * 3

    measures = uptime_measures({1: ("Kept", 0.3), 2: ("Judged", 0.6)}, per_member, names, kept={1})

    assert [(m.name, m.verdict) for m in measures] == [
        ("Judged", Verdict.LEVEL),
        ("Kept", Verdict.BOSSES_ONLY),
    ]


def test_a_kept_aura_still_needs_enough_carriers() -> None:
    names = {1: "Kept"}
    per_member = [{1: 0.05}, {1: 0.05}, {}]

    assert uptime_measures({1: ("Kept", 0.3)}, per_member, names, kept={1}) == ()


def test_an_aura_over_the_floor_is_judged_whether_or_not_it_is_kept() -> None:
    names = {1: "Both"}
    per_member = [{1: 0.6}] * 3

    [measure] = uptime_measures({1: ("Both", 0.1)}, per_member, names, kept={1})

    assert measure.verdict is Verdict.BELOW


# --- stretch_cell ---------------------------------------------------------------


def test_a_stretch_every_reference_measured_and_none_applied_it_in_says_so() -> None:
    assert stretch_cell(0.4, [0.0] * 5) == StretchCell(ours=0.4, withheld=Withheld.NOT_APPLIED)


def test_a_stretch_with_too_few_references_measuring_it_is_too_few_not_unapplied() -> None:
    assert stretch_cell(0.4, [0.0, 0.0]) == StretchCell(ours=0.4, withheld=Withheld.TOO_FEW)


def test_a_stretch_some_references_never_measured_counts_only_those_that_did() -> None:
    # Two measured it, at zero; the other three had nothing there to measure.
    assert stretch_cell(0.4, [0.0, 0.0, None, None, None]) == StretchCell(
        ours=0.4, withheld=Withheld.TOO_FEW
    )
    assert stretch_cell(0.4, [0.0, 0.0, 0.0, None, None]) == StretchCell(
        ours=0.4, withheld=Withheld.NOT_APPLIED
    )


def test_a_stretch_no_reference_measured_is_not_reached() -> None:
    assert stretch_cell(0.4, [None, None, None]) == StretchCell(
        ours=0.4, withheld=Withheld.NOT_REACHED
    )


def test_a_stretch_three_references_carried_gives_their_median() -> None:
    assert stretch_cell(0.4, [0.5, 0.7, 0.9, 0.0]) == StretchCell(ours=0.4, their_median=0.7)


def test_a_stretch_fewer_than_three_carried_is_too_few_even_if_others_measured_zero() -> None:
    assert stretch_cell(0.4, [0.5, 0.7, 0.0, 0.0, 0.0]) == StretchCell(
        ours=0.4, withheld=Withheld.TOO_FEW
    )


def test_a_stretch_our_side_measured_nothing_over_keeps_its_reason() -> None:
    assert stretch_cell(Withheld.NO_TRASH, [0.0] * 5) == StretchCell(withheld=Withheld.NO_TRASH)
