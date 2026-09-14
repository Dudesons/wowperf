# ABOUTME: Behaviour tests for compare_parse_axis -- the external frame of one raid boss fight.
# ABOUTME: The fixture's denominators all differ, so no rate assertion can pass by identity.

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.parse_axis import compare_parse_axis
from wowperf.domain.comparison.raid_reference import (
    RaidParseRow,
    RankedPlayer,
    ReportRankings,
)
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.comparison.targets import TargetRow
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player

ARCANE_BLAST = 30451
ARCANE_MISSILES = 5143
METEOR = 153561
ARCANE_SURGE = 365350
SIPHON_STORM = 384267

OUR_NAME = "Emberkin"

PLAYER = Player(
    actor_id=693,
    name="Emberkin",
    class_name="Mage",
    spec="Arcane",
    item_level=318,
    talent_import_string="CoPAAAAA",
)

THEIR_PLAYER = Player(
    actor_id=11,
    name="Stonewake",
    class_name="Mage",
    spec="Arcane",
    item_level=330,
    talent_import_string="CoPBBBBB",
)

OUR_SECONDS = 300.0
"""Our own boss time. Deliberately not 60: at a denominator of sixty
`count / seconds * 60` is the identity, and every rate assertion below would
then pass for a comparison that had multiplied by one."""


def raid_cast(actor_id: int, ability_id: int, name: str, at_ms: int) -> CastEvent:
    """One cast inside a raid boss fight, which carries no pull index at all.

    `pull_index` is left at its default `None`, which is what makes these events
    the real thing rather than Mythic+ events with the index blanked: a raid
    stream has no pulls to index into.
    """
    return CastEvent(
        actor_id=actor_id, ability_id=ability_id, ability_name=name, timestamp_ms=at_ms
    )


def casts_of(actor_id: int, ability_id: int, name: str, count: int, at_ms: int = 0) -> tuple[
    CastEvent, ...
]:
    return tuple(
        raid_cast(actor_id, ability_id, name, at_ms + one * 1000) for one in range(count)
    )


OUR_CASTS = casts_of(PLAYER.actor_id, ARCANE_BLAST, "Arcane Blast", 10) + casts_of(
    PLAYER.actor_id, ARCANE_MISSILES, "Arcane Missiles", 40, at_ms=100_000
)
"""Ten Arcane Blasts over three hundred seconds -- two a minute -- and forty Arcane
Missiles, eight a minute, which is far above what the sample casts and draws the
`compare.spells.above` row."""

OUR_AURAS = PlayerAuras(
    actor_id=PLAYER.actor_id,
    on_self=(
        Aura(
            ability_id=ARCANE_SURGE,
            name="Arcane Surge",
            total_uptime_ms=30_000,
            uses=1,
            bands=(AuraBand(start_ms=10_000, end_ms=40_000),),
        ),
    ),
)
"""Arcane Surge up for thirty of our three hundred seconds: a tenth of the fight."""


def a_member(
    report_code: str,
    boss_seconds: float,
    blasts: int,
    surge_ms: int,
) -> ParseMember:
    """One raid parse reference: its own fight length, its own casts, its own aura.

    `pulls` is left empty, which is what a raid reference is: there is no route
    to carry, and a route invented to satisfy a signature is the degenerate
    aggregate `ParseMember`'s own docstring records the harm of.

    Every reference is named `Stonewake`. What tells them apart here is their
    report code, their fight length and what they cast -- never their name, and
    no assertion below reads one.
    """
    return ParseMember(
        character_name="Stonewake",
        report_code=report_code,
        fight_id=1,
        boss_seconds=boss_seconds,
        players=(THEIR_PLAYER,),
        casts=(
            casts_of(THEIR_PLAYER.actor_id, ARCANE_BLAST, "Arcane Blast", blasts)
            + casts_of(THEIR_PLAYER.actor_id, METEOR, "Meteor", 4, at_ms=500_000)
            + casts_of(THEIR_PLAYER.actor_id, ARCANE_MISSILES, "Arcane Missiles", 4,
                       at_ms=700_000)
        ),
        auras=PlayerAuras(
            actor_id=THEIR_PLAYER.actor_id,
            on_self=(
                Aura(
                    ability_id=ARCANE_SURGE,
                    name="Arcane Surge",
                    total_uptime_ms=surge_ms,
                    uses=1,
                    bands=(AuraBand(start_ms=5_000, end_ms=5_000 + surge_ms),),
                ),
                # An aura the sample carries and we never do, which is the one
                # `compare.uptime.unjudged` names rather than scores.
                Aura(
                    ability_id=SIPHON_STORM,
                    name="Siphon Storm",
                    total_uptime_ms=60_000,
                    uses=1,
                    bands=(AuraBand(start_ms=1_000, end_ms=61_000),),
                ),
            ),
        ),
    )


SAMPLE = ParseSample(
    members=(
        a_member("REF1", 240.0, 14, 120_000),
        a_member("REF2", 270.0, 16, 130_000),
        a_member("REF3", 210.0, 12, 100_000),
        a_member("REF4", 255.0, 15, 128_000),
        a_member("REF5", 225.0, 13, 110_000),
    )
)
"""Five references, no two of which fought the boss for the same length of time,
and none of which fought it for as long as we did.

That is the point of the fixture rather than decoration. A sample whose members
all share our own denominator makes `count / seconds * 60` compare two counts,
and every rate below would then be reproducible without the denominator ever
being read. The Arcane Blast medians here are 3.5 casts a minute against our
2.0, which clears the gap multiple; recomputed against three hundred seconds
they are 2.8 against 2.0, which does not."""


def a_standing(amount: float, rank_percent: int, total_parses: int) -> ReportRankings:
    return ReportRankings(
        fight_id=7,
        difficulty=5,
        partition=2,
        size=20,
        kill=True,
        players=(
            RankedPlayer(
                character_name="Emberkin",
                class_name="Mage",
                spec="Arcane",
                role="dps",
                amount=amount,
                rank="~1200",
                best="~900",
                rank_percent=rank_percent,
                bracket_percent=rank_percent,
                total_parses=total_parses,
            ),
        ),
    )


def a_board(amounts: tuple[float, ...]) -> tuple[RaidParseRow, ...]:
    return tuple(
        RaidParseRow(
            report_code=f"BOARD{one}",
            fight_id=one + 1,
            duration_ms=240_000 + one * 5_000,
            character_name="Stonewake",
            class_name="Mage",
            spec="Arcane",
            amount=amount,
            size=20,
        )
        for one, amount in enumerate(amounts)
    )


OUR_TARGETS = (
    TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=880_000_000),
    TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=120_000_000),
)

THEIR_TARGETS = [
    (
        TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=470_000_000),
        TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=30_000_000),
    )
    for _ in range(5)
]

KILL_ARGS = {
    "our_player": PLAYER,
    "our_name": OUR_NAME,
    "our_seconds": OUR_SECONDS,
    "our_casts": OUR_CASTS,
    "our_auras": OUR_AURAS,
    "sample": SAMPLE,
    "standing": a_standing(1_450_000.0, 62, 4_100),
    "boss_standing": a_standing(1_180_000.0, 48, 3_900),
    "board": a_board((1_600_000.0, 1_720_000.0, 1_540_000.0, 1_880_000.0, 1_490_000.0)),
    "boss_board": a_board((1_310_000.0, 1_402_000.0, 1_255_000.0, 1_520_000.0, 1_190_000.0)),
    "our_targets": OUR_TARGETS,
    "their_targets": THEIR_TARGETS,
}

BELOW_FLOOR_ARGS = {**KILL_ARGS, "sample": ParseSample(members=(SAMPLE.members[0],))}
"""One reference, under `MIN_SAMPLE_FOR_AGGREGATE`, which is the delegation to the
pairwise comparison -- the whole reason `compare_spells` and `compare_uptime` were
narrowed, and a sample size a raid leaderboard produces readily."""

NO_SAMPLE_ARGS = {**KILL_ARGS, "sample": ParseSample()}
"""A kill whose parse leaderboard returned nobody, which is not the wipe."""

NO_SECONDS_ARGS = {
    **KILL_ARGS,
    "sample": ParseSample(members=(a_member("REF1", 0.0, 14, 120_000),)),
}
"""One reference whose fight length came back as nothing, which is what both
availability sentences are for."""


def one_of(findings: list[Finding], prefix: str) -> Finding:
    matching = [finding for finding in findings if finding.id.startswith(prefix)]
    assert matching, f"no finding under {prefix}: {[one.id for one in findings]}"
    return matching[0]


def test_a_wipe_withholds_the_whole_external_frame_in_one_sentence() -> None:
    """Design 14 item 4: `fightRankings` is a kill leaderboard under every metric
    and `Report.rankings` returns nothing for a wipe, so there is no external
    reference at all. Design 13's first risk is that readers expect one anyway."""
    findings = compare_parse_axis(
        our_player=PLAYER, our_name="Emberkin", our_seconds=300.0, our_casts=(),
        our_auras=None, sample=ParseSample(), standing=None, boss_standing=None,
        board=(), boss_board=(), our_targets=(), their_targets=[],
    )
    ids = [finding.id for finding in findings]
    assert ids == ["compare.parse.unavailable"]
    assert "did not kill" in findings[0].detail
    # Every comparison it stands in for is named, so no reader wonders which ran.
    for family in ("damage", "casts", "talents", "buff uptime", "percentile"):
        assert family in findings[0].detail


def test_a_kill_with_a_sample_emits_every_family_the_external_frame_owns() -> None:
    findings = compare_parse_axis(**KILL_ARGS)  # type: ignore[arg-type]
    families = {finding.id.rsplit(".", 1)[0] if finding.id[-1].isdigit() else finding.id
                for finding in findings}
    assert "compare.damage.total" in families
    assert "compare.damage.targets" in families
    assert "compare.rank" in families
    assert any(one.startswith("compare.spells") for one in families)
    assert "compare.talents" in families
    assert any(one.startswith("compare.uptime") for one in families)


def test_a_raid_cast_reaches_the_rate_comparison_at_all() -> None:
    """The Task 2 trap, asserted end to end rather than only at `casts_in`.
    Before the predicate, every ability counted zero here and nothing raised."""
    findings = compare_parse_axis(**KILL_ARGS)  # type: ignore[arg-type]
    rate_rows = [one for one in findings if one.id.startswith("compare.spells.rate")]
    assert rate_rows, "a raid cast counted for nothing -- casts_in is filtering on pull_index"


def test_no_finding_this_axis_emits_claims_a_player_should_have_done_anything() -> None:
    """Ruling R7: this repository bans a claim, not a word. A sentence may name a
    phrase in order to refuse it; none may assert intent the log cannot show.

    Every shape this axis can return is scanned, not only the kill: the wipe,
    the kill with no sample and the below-floor delegation each write sentences
    of their own, and a sentence nothing scans is a sentence nothing holds.
    """
    every = (
        compare_parse_axis(**KILL_ARGS)  # type: ignore[arg-type]
        + compare_parse_axis(**BELOW_FLOOR_ARGS)  # type: ignore[arg-type]
        + compare_parse_axis(**NO_SAMPLE_ARGS)  # type: ignore[arg-type]
        + compare_parse_axis(**NO_SECONDS_ARGS)  # type: ignore[arg-type]
        + compare_parse_axis(
            our_player=PLAYER, our_name="Emberkin", our_seconds=300.0, our_casts=(),
            our_auras=None, sample=ParseSample(), standing=None, boss_standing=None,
            board=(), boss_board=(), our_targets=(), their_targets=[],
        )
    )
    assert len(every) > len(compare_parse_axis(**KILL_ARGS))  # type: ignore[arg-type]
    for finding in every:
        sentence = f"{finding.title} {finding.detail}".lower()
        for claim in ("should have", "failed to", "was avoidable", "missed the"):
            assert claim not in sentence, f"{finding.id}: {claim}"


def test_every_finding_id_is_unique_over_one_kill() -> None:
    """The seam concatenates six families, each of which numbers its own rows.

    Two families minting the same id is how a page draws one card over another,
    and the sibling modules each keep this test for the same reason.
    """
    for arguments in (KILL_ARGS, BELOW_FLOOR_ARGS, NO_SAMPLE_ARGS, NO_SECONDS_ARGS):
        ids = [one.id for one in compare_parse_axis(**arguments)]  # type: ignore[arg-type]
        assert len(ids) == len(set(ids)), sorted(ids)


def test_the_percentile_is_emitted_last() -> None:
    """Section 6.7: a percentile is triage and never a headline.

    Every `compare` finding carries `seconds_lost=None`, so `rank_raid_findings`
    ties across the family and leaves this order untouched -- which makes the
    order built here the order a reader meets.
    """
    ids = [one.id for one in compare_parse_axis(**KILL_ARGS)]  # type: ignore[arg-type]
    assert ids[-1] == "compare.rank"
    assert ids[0] == "compare.damage.total"


# The raid renderings of every sentence this axis words differently from a
# dungeon's. Asserted whole, with their own numbers in, rather than by checking
# that a `Wording` arrived: plan 2's rulings record a scope parameter shipping a
# false sentence, and a test that reads the parameter would have passed for it.
# The Mythic+ renderings of the same sentences are asserted in `test_spells.py`
# and `test_uptime.py`, and the golden report file holds them byte for byte.


def test_the_raid_rate_sentence_measures_fight_time_and_names_no_dungeon() -> None:
    findings = compare_parse_axis(**KILL_ARGS)  # type: ignore[arg-type]
    row = one_of(findings, "compare.spells.rate")

    assert row.detail == (
        "Both rates are casts per minute of fight time, which is the whole of one boss "
        "fight and the same encounter in every kill compared. The reference side is the "
        "median across the sample, not one parse, so a single busy or quiet run cannot "
        "carry the comparison alone."
    )
    assert "ours over 300s of the fight" in row.evidence
    # 3.5 a minute across the sample against our 2.0, which is the fixture's own
    # arithmetic and not reproducible without the references' own denominators.
    assert "3.5" in row.title and "2.0" in row.title


def test_the_raid_above_sentence_asks_about_a_longer_attempt_and_not_a_harder_key() -> None:
    row = one_of(compare_parse_axis(**KILL_ARGS), "compare.spells.above")  # type: ignore[arg-type]

    assert row.detail == (
        "Both rates are casts per minute of fight time. This row states a difference and "
        "no verdict: casting something more often than the sample is not a fault, and on a "
        "class whose resources are shared it means those resources did not go somewhere "
        "else, which is the thing worth checking. A defensive, a taunt or a movement "
        "button pressed more often may simply be what the fight demanded, and a longer or "
        "harder attempt asks for more of them."
    )
    assert "ours over 300s of the fight" in row.evidence
    assert "8.0" in row.title and "1.0" in row.title


def test_the_raid_missing_cast_sentence_offers_no_trash_to_have_looked_at() -> None:
    row = one_of(compare_parse_axis(**KILL_ARGS), "compare.spells.missing")  # type: ignore[arg-type]

    assert row.detail == (
        "Meteor does not appear anywhere in this fight for Emberkin. That is a talent not "
        "taken, a button not pressed, or an item not owned; the log cannot tell which. The "
        "count is over the sample, not one parse, so no single reference needs naming to "
        "make the point."
    )
    assert "zero casts in the whole of this fight" in row.evidence


def test_the_raid_uptime_sentence_measures_fight_time_and_names_no_keystone_level() -> None:
    row = one_of(compare_parse_axis(**KILL_ARGS), "compare.uptime.self")  # type: ignore[arg-type]

    assert row.detail == (
        "Both figures are the share of fight time the aura was present, which is "
        "comparable even though the fights ran for different lengths. A shorter attempt "
        "still changes what fits, so read a narrow gap as noise. This compares by exact "
        "ability, so a gap can still mean a different item of the same kind — but the gap "
        "is stated over several top parses, not one player's build, so a single trinket "
        "this player happens not to own no longer explains it away."
    )
    assert "ours over 300s of the fight" in row.evidence
    # Arcane Surge, up a median 49% of the sample's fight time against our 10%.
    assert "49%" in row.title and "10%" in row.title


def test_the_raid_unjudged_aura_is_absent_from_a_fight_and_not_from_boss_pulls() -> None:
    row = one_of(compare_parse_axis(**KILL_ARGS), "compare.uptime.unjudged")  # type: ignore[arg-type]

    assert "Siphon Storm" in row.evidence[0]
    assert "absent from our own fight" in row.evidence


def test_a_raid_sample_of_one_delegates_to_the_pairwise_comparison_in_its_own_words() -> None:
    """The below-floor path, which is the whole reason the pairwise pair was narrowed.

    Its sentences are the pairwise ones, not the sample ones, and its figures
    are the reference's own -- so a raid rule that counted nothing, or dungeon
    words on a raid fight, both fail here rather than merely not raising.
    """
    findings = compare_parse_axis(**BELOW_FLOOR_ARGS)  # type: ignore[arg-type]

    rate = one_of(findings, "compare.spells.rate")
    assert rate.detail == (
        "Both rates are casts per minute of fight time, which is the whole of one boss "
        "fight and the same encounter on both sides. A longer attempt changes how many "
        "cooldowns fit, so treat a small gap as noise."
    )
    # 14 casts over the reference's own 240s against our 10 over 300s.
    assert "3.5" in rate.title and "2.0" in rate.title
    assert "ours over 300s of the fight" in rate.evidence
    assert "theirs over 240s of the fight" in rate.evidence

    missing = one_of(findings, "compare.spells.missing")
    assert missing.detail == (
        "Meteor does not appear anywhere in this fight for Emberkin. That is a talent not "
        "taken, a button not pressed, or an item not owned; the log cannot tell which."
    )
    assert "4 casts across 240s of their fight" in missing.evidence
    assert "zero casts in the whole of this fight" in missing.evidence

    uptime = one_of(findings, "compare.uptime.self")
    assert uptime.detail == (
        "Both figures are the share of fight time the aura was present, which is "
        "comparable even though the two fights ran for different lengths. A shorter "
        "attempt still changes what fits, so read a narrow gap as noise. This compares by "
        "exact ability, though, so a gap can also mean a different item of the same kind, "
        "or gear this player does not own — not that nothing was used at all."
    )
    assert "theirs over 240s of the fight" in uptime.evidence
    # One reference is stated as one reference, through the shared wording.
    assert any("a single reference, not an aggregate" in line for line in uptime.evidence)


def test_a_raid_reference_with_no_fight_time_says_so_in_this_axis_own_words() -> None:
    findings = compare_parse_axis(**NO_SECONDS_ARGS)  # type: ignore[arg-type]

    spells = one_of(findings, "compare.spells.unavailable")
    assert spells.detail == (
        "A spell comparison needs fight time on both sides and the reference player "
        "present in their own report. One of those is missing, so no ability numbers are "
        "reported rather than numbers from an unlike sample."
    )

    uptime = one_of(findings, "compare.uptime.unavailable")
    assert uptime.detail == (
        "An uptime comparison needs fight time on both sides and aura data for both "
        "players. One of those is missing, so no uptime numbers are reported rather than "
        "numbers from an unlike sample."
    )


def test_a_kill_with_no_parse_sample_says_which_three_families_are_missing() -> None:
    """A kill the leaderboard offered nobody for is not a wipe, and must not read as one.

    The three families that read this report's own rankings still run; the
    three that read a sample would otherwise have returned empty lists.
    """
    findings = compare_parse_axis(**NO_SAMPLE_ARGS)  # type: ignore[arg-type]
    ids = [one.id for one in findings]

    assert "compare.damage.total" in ids
    assert "compare.damage.targets" in ids
    assert "compare.rank" in ids
    note = one_of(findings, "compare.parse.unavailable")
    assert note.confidence is Confidence.MEASURED
    assert "did not kill" not in note.detail
    for family in ("casts a minute", "talents", "buff uptime"):
        assert family in note.detail
    assert not [one for one in ids if one.startswith("compare.spells")]
    assert not [one for one in ids if one.startswith("compare.uptime")]


def test_a_player_with_no_specialisation_is_never_said_to_have_an_empty_leaderboard() -> None:
    """No board was asked for, so no sentence may say one answered with nothing.

    A specialisation is what a parse leaderboard is queried for, so a player the
    log records none for has no board, no sample and no reference target table
    -- and `_no_sample`'s "the parse leaderboard returned no reference kills for
    this specialisation" would be false of a query never issued, as would
    `compare_targets`' claim about a table never fetched.

    The percentile is the one family that survives: it reads this report's own
    rankings row, which names a player by name.
    """
    findings = compare_parse_axis(
        **{
            **KILL_ARGS,
            "our_player": PLAYER.model_copy(update={"spec": ""}),
            "sample": ParseSample(),
            "board": (),
            "boss_board": (),
            "our_targets": (),
            "their_targets": [],
        }  # type: ignore[arg-type]
    )
    ids = [one.id for one in findings]

    assert ids == ["compare.parse.unavailable", "compare.rank"]
    note = findings[0]
    assert note.title == "No comparison against other kills is available for Emberkin (Mage)"
    assert "records no specialisation" in note.detail
    assert "did not kill" not in note.detail
    assert "returned no reference kills" not in note.detail
    assert note.confidence is Confidence.MEASURED
    # The percentile the rankings row does support is stated, not withheld.
    assert "62nd percentile" in findings[1].title
