# ABOUTME: Behaviour tests for compare_parse_axis -- the external frame of one raid boss fight.
# ABOUTME: The fixture's denominators all differ, so no rate assertion can pass by identity.

from wowperf.domain.analysis.roster import display_names
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
ARCANE_BARRAGE = 44425
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


OUR_CASTS = (
    casts_of(PLAYER.actor_id, ARCANE_BLAST, "Arcane Blast", 10)
    + casts_of(PLAYER.actor_id, ARCANE_MISSILES, "Arcane Missiles", 40, at_ms=100_000)
    + casts_of(PLAYER.actor_id, ARCANE_BARRAGE, "Arcane Barrage", 10, at_ms=200_000)
)
"""Ten Arcane Blasts over three hundred seconds -- two a minute -- and forty Arcane
Missiles, eight a minute, which is far above what the sample casts and draws the
`compare.spells.above` row.

Ten Arcane Barrages are two a minute as well, which is the sample's own median for
it: inside the band in both directions, so it draws the `compare.spells.level` row
instead. That row exists in this fixture because it is the one row of this family
whose sentence nothing else here renders, and its wording was wrong on a raid until
a live run read it."""

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
            # Eight over this member's own fight length, which is about two a
            # minute for every member and for us -- the level row's whole point.
            + casts_of(THEIR_PLAYER.actor_id, ARCANE_BARRAGE, "Arcane Barrage", 8,
                       at_ms=900_000)
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


def a_ranked_player(amount: float, rank_percent: int, total_parses: int) -> RankedPlayer:
    """One row of this report's own rankings, always named for our subject.

    The name is the constant here and the figures vary, which is what the
    shared-name case needs: two rows a reader could tell apart by their numbers
    and a join cannot tell apart at all.
    """
    return RankedPlayer(
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
    )


def a_standing_of(*players: RankedPlayer) -> ReportRankings:
    return ReportRankings(
        fight_id=7,
        difficulty=5,
        partition=2,
        size=20,
        kill=True,
        players=players,
    )


def a_standing(amount: float, rank_percent: int, total_parses: int) -> ReportRankings:
    return a_standing_of(a_ranked_player(amount, rank_percent, total_parses))


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

DOUBLED_STANDING = a_standing_of(
    a_ranked_player(1_450_000.0, 62, 4_100), a_ranked_player(990_000.0, 41, 4_100)
)
"""A kill whose rankings row names two players alike -- the shape twenty raiders make.

The two rows differ in every figure a finding would print, so a comparison that
took either of them states a number this fixture can point at.
"""

SHARED_NAME_ARGS = {
    **KILL_ARGS,
    "our_name": "Emberkin (actor 693)",
    "standing": DOUBLED_STANDING,
    "boss_standing": DOUBLED_STANDING,
}
"""The same kill, read for a player whose name this report carries twice."""


def one_of(findings: list[Finding], prefix: str) -> Finding:
    matching = [finding for finding in findings if finding.id.startswith(prefix)]
    assert matching, f"no finding under {prefix}: {[one.id for one in findings]}"
    return matching[0]


def evidence_of(findings: list[Finding], finding_id: str) -> list[str]:
    """One finding's evidence, as a list, so an assertion can state the whole tuple."""
    [finding] = [one for one in findings if one.id == finding_id]
    return list(finding.evidence)


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


def test_a_raider_who_shares_a_name_is_still_joined_to_their_rankings_row() -> None:
    """The rankings row carries a plain name, and the seam is handed a disambiguated one.

    Two roster members sharing a name is ordinary in a twenty-player raid, and
    `display_names` rewrites both spellings when it happens. A join on the
    rewritten spelling matches nobody, and the two families that read this
    report's own rankings would then tell a player on a kill that the boss was
    never killed -- beside families that compared perfectly well.

    So the join is the roster's plain name and the sentences keep the
    disambiguated one: a reader handed a name that could mean two people is
    what `display_names` exists to prevent.
    """
    twin = PLAYER.model_copy(update={"actor_id": 700})
    shown = display_names((PLAYER, twin))[PLAYER.actor_id]
    assert shown == "Emberkin (actor 693)"

    findings = compare_parse_axis(**{**KILL_ARGS, "our_name": shown})  # type: ignore[arg-type]
    by_id = {one.id: one for one in findings}

    assert "compare.damage.total.unavailable" not in by_id
    assert "compare.rank.unavailable" not in by_id
    assert "1450000.0 against a median of 1600000.0" in [
        fact.value for fact in by_id["compare.damage.total"].facts
    ]
    assert "62nd percentile" in by_id["compare.rank"].title
    # Six of the eight names the seam writes are title text, and every one of
    # them keeps the spelling that tells the two players apart.
    assert shown in by_id["compare.damage.total"].title
    assert shown in by_id["compare.rank"].title
    assert shown in by_id["compare.damage.targets"].title


def test_a_report_naming_two_raiders_alike_withholds_the_two_families_that_read_its_row() -> None:
    """The other half of the case the disambiguated display name exists for.

    Joining on the plain roster name is what puts a shared-name player back on
    their own rankings row -- and where the name really is shared, it finds two
    rows with nothing to separate them, because a rankings row carries a
    character name and no actor id. Taking the first would print the other
    player's percentile, parse count and throughput on this player's card under
    a title naming this player, badged `MEASURED`: the loud wrong answer the
    join replaced, turned into a quiet one.

    The four families that read a leaderboard rather than this report's own row
    are untouched, so the shared name costs a reader two cards and not the axis.
    """
    findings = compare_parse_axis(**SHARED_NAME_ARGS)  # type: ignore[arg-type]
    by_id = {one.id: one for one in findings}

    assert "compare.rank" not in by_id
    assert "compare.damage.total" not in by_id
    for withheld in ("compare.rank.unavailable", "compare.damage.total.unavailable"):
        note = by_id[withheld]
        assert note.confidence is Confidence.MEASURED
        assert "More than one player in this report is named Emberkin" in note.detail
        assert "did not kill" not in note.detail
        assert note.title.endswith("Emberkin (actor 693)")
        # Neither row's figures reach the page under one player's name.
        assert "1450000" not in note.detail and "990000" not in note.detail

    assert "compare.damage.targets" in by_id
    assert any(one.startswith("compare.spells") for one in by_id)
    assert "compare.talents" in by_id
    assert any(one.startswith("compare.uptime") for one in by_id)


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
        + compare_parse_axis(**SHARED_NAME_ARGS)  # type: ignore[arg-type]
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
    for arguments in (
        KILL_ARGS, BELOW_FLOOR_ARGS, NO_SAMPLE_ARGS, NO_SECONDS_ARGS, SHARED_NAME_ARGS
    ):
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
        "median across the sample, not one parse, so a single busy or quiet fight cannot "
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


def test_no_raid_title_says_a_cast_or_a_share_was_counted_on_bosses() -> None:
    """Every title of this axis, whole, in the words a reader actually meets.

    The gap this closes was found by a live run and not by this suite: the
    detail sentences were wired to `Wording` and the titles were not, so a raid
    finding read "cast Fire Breath on bosses" and a fact beside it read "46% of
    boss time" while its own detail said fight time. A raid fight has one boss
    and no boss pulls, and the raid counting rule counts every cast of the
    fight rather than the casts aimed at the boss -- so both phrases claimed
    something the measurement had not done.

    Asserted whole rather than by substring, because the assertions that let
    this through were substring checks on the figures: "3.5 in the title"
    passes for any sentence containing the number.
    """
    findings = compare_parse_axis(**KILL_ARGS)  # type: ignore[arg-type]
    titles = {one.id: one.title for one in findings}

    assert titles["compare.spells.missing.0"] == (
        "5 of 5 top parses cast Meteor on this encounter; Emberkin never did"
    )
    assert titles["compare.spells.rate.0"] == (
        "5 top parses cast Arcane Blast a median 3.5 times a minute on this encounter; "
        "Emberkin casts it 2.0"
    )
    assert titles["compare.spells.above.0"] == (
        "Emberkin casts Arcane Missiles 8.0 times a minute on this encounter; "
        "5 top parses cast it a median 1.0"
    )
    assert titles["compare.spells.level"] == (
        "1 ability Emberkin cast on this encounter was compared and showed no gap"
    )
    assert titles["compare.uptime.self.0"] == (
        "Arcane Surge was up a median 49% of fight time across 5 top parses; 10% for Emberkin"
    )

    assert_no_dungeon_vocabulary(findings)


DUNGEON_ONLY = ("on bosses", "boss time", "boss pull", "keystone", "run")
"""Phrases a raid sentence may not carry, in any of the four places one is written.

`run` is the bare noun rather than the two phrases it replaced, `this run` and
`reference run`: both of those were written from the sentences that had already
been caught, and the one that had not -- "a single busy or quiet run" -- sat one
clause away from a phrase this list did name. A raid axis has no honest use for
the word in any composition, so the word itself is what is banned.

A backstop and never the assertion: each of these entered the codebase as a
phrase that was true when only a dungeon reached it, and the list can only ever
name the ones somebody has already thought of. What catches the next one is the
whole-string assertions above and below, which fail on the sentence itself.
"""


def assert_no_dungeon_vocabulary(findings: list[Finding]) -> None:
    """Sweep every string a reader meets, not the subset the last bug happened to use.

    `detail` and a fact's `label` are swept as well as titles, evidence and
    fact values. Leaving either out is the shape of the defect this whole group
    exists for: the details were right and the titles were wrong, the sweep was
    written over titles, and a wrong phrase in the half nobody swept would pass
    exactly as the first one did.
    """
    for finding in findings:
        lines = (
            finding.title,
            finding.detail,
            *finding.evidence,
            *(fact.label for fact in finding.facts),
            *(fact.value for fact in finding.facts),
        )
        for line in lines:
            for phrase in DUNGEON_ONLY:
                assert phrase not in line, f"{finding.id}: {phrase!r} in {line!r}"


def test_every_raid_fact_a_reader_meets_is_worded_for_a_fight() -> None:
    """The half the first sweep did not cover, pinned whole.

    Facts are what a panel lays out beside a title, and they carried the second
    half of the live defect: a finding whose detail said "the share of fight
    time" put "46% of boss time" in the fact below it. Every raid fact of the
    sample shape is stated here as the label-and-value pair a reader sees.
    """
    findings = compare_parse_axis(**KILL_ARGS)  # type: ignore[arg-type]
    facts = {
        one.id: [(fact.label, fact.value) for fact in one.facts] for one in findings
    }

    assert facts["compare.damage.total"] == [
        ("All damage", "1450000.0 against a median of 1600000.0"),
        ("Boss damage only", "1180000.0 against a median of 1310000.0"),
    ]
    assert facts["compare.damage.targets"] == [
        ("This raid", "88.0% into The Twin Fangs"),
        ("Sample", "94.0%"),
    ]
    assert facts["compare.spells.rate.0"] == [
        ("Ours", "2.0 casts a minute"),
        ("Reference median", "3.5 casts a minute"),
        ("Observed range", "3.4 to 3.6"),
        ("Sample", "5 top parses"),
    ]
    assert facts["compare.spells.above.0"] == [
        ("Ours", "8.0 casts a minute"),
        ("Reference median", "1.0 casts a minute"),
        ("Observed range", "0.9 to 1.1"),
        ("Sample", "5 top parses"),
    ]
    assert facts["compare.uptime.self.0"] == [
        ("Ours", "10% of fight time"),
        ("Reference median", "49% of fight time"),
        ("Observed range", "48% to 50%"),
        ("Sample", "5 top parses"),
    ]
    assert facts["compare.rank"] == [
        ("All damage", "62nd percentile of 4100 parses"),
        ("Boss damage only", "48th percentile of 3900 parses"),
    ]


def test_every_raid_evidence_line_a_reader_meets_is_worded_for_a_fight() -> None:
    """Every evidence tuple of the sample shape, whole.

    Evidence is where the counting rule shows: "at least 3 times on this
    encounter" is the sentence that says what `whole_fight_casts` counted, and
    it was one of the lines the live run caught reading "on bosses".
    """
    findings = compare_parse_axis(**KILL_ARGS)  # type: ignore[arg-type]
    evidence = {one.id: list(one.evidence) for one in findings}

    assert evidence["compare.spells.missing.0"] == [
        f"ability {METEOR}",
        "5 of 5 top parses cast it at least 3 times on this encounter",
        "zero casts in the whole of this fight",
    ]
    assert evidence["compare.spells.rate.0"] == [
        f"ability {ARCANE_BLAST}",
        "ours over 300s of the fight",
        "range 3.4 to 3.6 casts a minute across 5 top parses",
    ]
    assert evidence["compare.spells.above.0"] == [
        f"ability {ARCANE_MISSILES}",
        "ours over 300s of the fight",
        "range 0.9 to 1.1 casts a minute across 5 top parses",
    ]
    assert evidence["compare.spells.level"] == [
        "Arcane Barrage",
        "compared against at least 3 top parses each",
    ]
    assert evidence["compare.uptime.self.0"] == [
        f"ability {ARCANE_SURGE}",
        "ours over 300s of the fight",
        "range 48% to 50% across 5 top parses",
        "0 of 5 references had no aura data",
    ]
    assert evidence["compare.uptime.unjudged"] == [
        "Siphon Storm",
        "carried by at least 3 top parses each",
        "absent from our own fight",
    ]


def test_no_raid_title_says_on_bosses_in_the_pairwise_shape_either() -> None:
    """The below-floor delegation writes its own sentences, and a raid
    leaderboard produces that shape readily."""
    findings = compare_parse_axis(**BELOW_FLOOR_ARGS)  # type: ignore[arg-type]
    titles = {one.id: one.title for one in findings}

    assert titles["compare.spells.missing.0"] == (
        "Stonewake cast Meteor 4 times on this encounter; Emberkin never cast it"
    )
    assert titles["compare.spells.rate.0"] == (
        "Stonewake cast Arcane Blast 3.5 times a minute on this encounter, Emberkin 2.0"
    )
    assert titles["compare.uptime.self.0"] == (
        "Arcane Surge was up for 50% of Stonewake's fight time, 10% of Emberkin's"
    )

    assert_no_dungeon_vocabulary(findings)


def test_the_pairwise_raid_shape_counts_one_reference_fight_and_not_one_reference_run() -> None:
    """A raid kill is not a run, and the fact that counts the sample said it was.

    `Wording.reference_noun` is the bare noun this slot wanted -- "run" for a
    dungeon, "fight" for a raid. It is a field of its own rather than `run`,
    which is the demonstrative ("this run", "this fight") and renders
    "1 reference this fight" here.

    Both members of the pair are pinned, because the fact is written in two
    modules and only one of them would move if the field were threaded at one
    site. The dungeon renderings of the same two facts are pinned in
    `test_spells.py` and `test_uptime.py`, so a swap of the two values fails in
    both directions rather than silently trading one axis for the other.
    """
    findings = compare_parse_axis(**BELOW_FLOOR_ARGS)  # type: ignore[arg-type]
    facts = {
        one.id: [(fact.label, fact.value) for fact in one.facts] for one in findings
    }

    assert facts["compare.spells.rate.0"] == [
        ("Ours", "2.0 casts a minute"),
        ("Reference", "3.5 casts a minute"),
        ("Sample", "1 reference fight"),
    ]
    assert facts["compare.uptime.self.0"] == [
        ("Ours", "10% of fight time"),
        ("Reference", "50% of fight time"),
        ("Sample", "1 reference fight"),
    ]
    assert evidence_of(findings, "compare.spells.missing.0") == [
        f"ability {METEOR}",
        "4 casts across 240s of their fight",
        "zero casts in the whole of this fight",
        "a single reference, not an aggregate: 1 of the sample was comparable, "
        "below the floor of 3",
    ]
    assert evidence_of(findings, "compare.uptime.self.0") == [
        f"ability {ARCANE_SURGE}",
        "ours over 300s of the fight",
        "theirs over 240s of the fight",
        "a single reference, not an aggregate: 1 of the sample was comparable, "
        "below the floor of 3",
    ]


def test_a_raid_availability_line_counts_fight_time_and_not_boss_time() -> None:
    """Both unavailable rows state the seconds each side had, and name them.

    Asserted whole: these two evidence tuples are the only place the seconds of
    a failed comparison are written, and a substring check on "fight time"
    would pass for "our boss time 300s, of our fight time".
    """
    findings = compare_parse_axis(**NO_SECONDS_ARGS)  # type: ignore[arg-type]

    assert evidence_of(findings, "compare.spells.unavailable") == [
        "our fight time 300s",
        "their fight time 0s",
        "reference player 'Stonewake' found",
        "a single reference, not an aggregate: 1 of the sample was comparable, "
        "below the floor of 3",
    ]
    assert evidence_of(findings, "compare.uptime.unavailable") == [
        "our fight time 300s",
        "their fight time 0s",
        "our aura data present",
        "their aura data present",
        "a single reference, not an aggregate: 1 of the sample was comparable, "
        "below the floor of 3",
    ]
    assert_no_dungeon_vocabulary(findings)


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
    """Title and detail whole, not the evidence alone.

    This row's detail names the stretch the sample carried the aura over, and a
    dungeon's noun for it would survive every assertion that read only the
    evidence -- which is the residual the bare-word backstop above was widened
    for. The Mythic+ rendering of the same two sentences is pinned in
    `test_uptime.py`, so a swap of the two fails in both directions.
    """
    row = one_of(compare_parse_axis(**KILL_ARGS), "compare.uptime.unjudged")  # type: ignore[arg-type]

    assert row.title == "1 aura the sample carried is not judged for Emberkin"
    assert row.detail == (
        "Each of these was present over enough of the sample's fight time to compare, and "
        "absent from ours. It is named rather than measured: the aura table cannot say "
        "whose buff a row was, so a zero here may be a button this player never pressed or "
        "one a teammate never gave them, and the log does not separate the two. Check "
        "whether the build produces it before reading anything into it."
    )
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
