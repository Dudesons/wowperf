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
from wowperf.domain.model import Player

ARCANE_BLAST = 30451
METEOR = 153561
ARCANE_SURGE = 365350

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


OUR_CASTS = casts_of(PLAYER.actor_id, ARCANE_BLAST, "Arcane Blast", 10)
"""Ten Arcane Blasts over three hundred seconds: two a minute."""

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
    phrase in order to refuse it; none may assert intent the log cannot show."""
    for finding in compare_parse_axis(**KILL_ARGS):  # type: ignore[arg-type]
        sentence = f"{finding.title} {finding.detail}".lower()
        for claim in ("should have", "failed to", "was avoidable", "missed the"):
            assert claim not in sentence, f"{finding.id}: {claim}"
