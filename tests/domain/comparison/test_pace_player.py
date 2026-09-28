# ABOUTME: Each player's boss damage against the kills' players of the same class and spec.
# ABOUTME: Pins the titles, the time lag, the window's three ends, and every withhold.

import re

from tests.domain.comparison.test_pace_curve import steady
from tests.domain.report.test_raid_frame import an_encounter
from wowperf.domain.comparison.pace import NO_REFERENCE_KILL, PaceSample
from wowperf.domain.comparison.pace_curve import PaceReference, PlayerSeries
from wowperf.domain.comparison.pace_player import (
    NO_SPEC_TITLE,
    PLAYER_PACE_PREFIX,
    PLAYER_UNAVAILABLE_PREFIX,
    analyse_player_pace,
    pair_label,
)
from wowperf.domain.comparison.parse_axis import ParseSubject
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death, Resurrection
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.season import Roles, SelfResurrections

ROLES = Roles(tanks=("DeathKnight/Blood",), healers=("Priest/Holy",))
NO_SELF_RESURRECTIONS = SelfResurrections()

FROST = Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Frost", item_level=700)
BLOOD = Player(
    actor_id=2, name="Stonewake", class_name="DeathKnight", spec="Blood", item_level=700
)
HOLY = Player(actor_id=3, name="Bríala", class_name="Priest", spec="Holy", item_level=700)
UNNAMED = Player(actor_id=4, name="Кириллица", class_name="Mage", spec="", item_level=700)
AFFLICTION = Player(
    actor_id=5, name="Briala", class_name="Warlock", spec="Affliction", item_level=700
)
ROSTER = (FROST, BLOOD, HOLY, UNNAMED, AFFLICTION)


def subject(player: Player) -> ParseSubject:
    return ParseSubject(player=player, slug=f"p{player.actor_id}", display_name=player.name)


def a_peer(class_name: str, spec: str, per_second: int, **fields: float) -> PlayerSeries:
    return PlayerSeries(
        actor_id=90, class_name=class_name, spec=spec, damage=steady(per_second, 400), **fields
    )


def a_reference_kill(*players: PlayerSeries) -> PaceReference:
    return PaceReference(duration_seconds=400.0, damage=steady(1000, 400), players=players)


THREE_KILLS = (
    a_reference_kill(a_peer("Mage", "Frost", 90), a_peer("DeathKnight", "Blood", 50)),
    a_reference_kill(a_peer("Mage", "Frost", 100), a_peer("DeathKnight", "Blood", 50)),
    a_reference_kill(a_peer("Mage", "Frost", 110)),
)


def a_wipe(seconds: int = 200, **fields: object) -> LoadedEncounter:
    encounter = an_encounter(
        kill=False, start_ms=0, end_ms=seconds * 1000, fight_percentage=40.0, players=ROSTER
    )
    return LoadedEncounter(encounter=encounter, **fields)  # type: ignore[arg-type]


def a_sample(frost_per_second: int = 80, seconds: int = 200) -> PaceSample:
    ours = (PlayerSeries(actor_id=1, class_name="Mage", spec="Frost",
                         damage=steady(frost_per_second, seconds)),)
    return PaceSample(ours=steady(1000, seconds), references=THREE_KILLS, our_players=ours)


def analysed(
    loaded: LoadedEncounter | None = None,
    sample: PaceSample | None = None,
    players: tuple[Player, ...] = (FROST,),
) -> dict[str, Finding]:
    found = analyse_player_pace(
        loaded or a_wipe(),
        sample or a_sample(),
        tuple(subject(one) for one in players),
        ROLES,
        NO_SELF_RESURRECTIONS,
    )
    return {finding.id: finding for finding in found}


FROST_ID = f"{PLAYER_PACE_PREFIX}p1"


def test_the_pair_is_named_by_spec_then_class_split_at_its_capitals() -> None:
    assert pair_label("Mage", "Frost") == "Frost Mages"
    assert pair_label("DeathKnight", "Blood") == "Blood Death Knights"
    assert pair_label("DemonHunter", "Havoc", plural=False) == "Havoc Demon Hunter"


def test_a_player_behind_their_spec_gets_the_share_and_the_lag() -> None:
    """Peers at 90, 100 and 110 a second; ours at 80. By 200 s the median had 20000 and
    we had 16000, which the median reached at 160 s: forty seconds behind."""
    finding = analysed()[FROST_ID]
    assert finding.title == "Behind the kills' Frost Mages: 80% of their median boss damage by 3:20"
    assert finding.confidence is Confidence.DERIVED
    assert finding.player_slug == "p1"
    assert finding.evidence == (
        "Against 3 Frost Mages across 3 reference kills of this raid size",
        "Their range at 3:20: 90% to 110% of their median",
        "By 3:20 they had dealt what the kills' median Frost Mage had dealt by 2:40: "
        "40 seconds behind",
        "Compared through the wipe at 3:20",
        "Behind from 0:01 to 3:20",
    )
    assert "assigned to adds" in finding.detail


def test_ahead_reads_the_lag_as_seconds_ahead() -> None:
    """26000 by 200 s, which the median reached at 260 s."""
    finding = analysed(sample=a_sample(130))[FROST_ID]
    assert finding.title.startswith("Ahead of the kills' Frost Mages: 130% ")
    assert (
        "By 3:20 they had dealt what the kills' median Frost Mage had dealt by 4:20: "
        "60 seconds ahead"
        in finding.evidence
    )
    assert not any(line.startswith("Behind from") for line in finding.evidence)


def test_level_with_the_median_says_so_without_a_figure() -> None:
    finding = analysed(sample=a_sample(100))[FROST_ID]
    assert finding.title.startswith("On the kills' Frost Mages' pace: 100% ")
    assert (
        "By 3:20 they had dealt what the kills' median Frost Mage had dealt by then"
        in finding.evidence
    )


def test_past_everything_the_median_reached_there_is_no_lag_figure() -> None:
    """60000 by 200 s; the median tops out at 40000 when the kills end at 400 s."""
    finding = analysed(sample=a_sample(300))[FROST_ID]
    assert (
        "More than the kills' median had dealt by 6:40, where fewer than three Frost Mages "
        "were still fighting"
    ) in finding.evidence


def test_a_death_nobody_answered_ends_the_comparison() -> None:
    death = Death(player_name="Emberkin", actor_id=1, timestamp_ms=125_000, killing_blow="Crush")
    finding = analysed(loaded=a_wipe(deaths=(death,)))[FROST_ID]
    assert finding.title.endswith("by 2:05")
    assert "Compared through their death at 2:05" in finding.evidence


def test_a_release_ends_the_comparison_at_the_death() -> None:
    death = Death(player_name="Emberkin", actor_id=1, timestamp_ms=50_000, killing_blow="Crush",
                  seconds_until_next_action=10.0)
    finding = analysed(loaded=a_wipe(deaths=(death,)))[FROST_ID]
    assert "Compared through their death at 0:50" in finding.evidence


def test_a_battle_resurrection_keeps_the_comparison_running_and_names_the_stretch() -> None:
    death = Death(player_name="Emberkin", actor_id=1, timestamp_ms=50_000, killing_blow="Crush",
                  seconds_until_next_action=35.0)
    rez = Resurrection(actor_id=1, caster_id=2, ability_id=20484, ability_name="Rebirth",
                       timestamp_ms=80_000)
    finding = analysed(loaded=a_wipe(deaths=(death,), resurrections=(rez,)))[FROST_ID]
    assert "Compared through the wipe at 3:20" in finding.evidence
    assert "Dead from 0:50 to 1:20, then resurrected" in finding.evidence


def test_a_reference_players_own_death_cuts_the_band() -> None:
    kills = (
        a_reference_kill(a_peer("Mage", "Frost", 90, until_seconds=100.0)),
        a_reference_kill(a_peer("Mage", "Frost", 100)),
        a_reference_kill(a_peer("Mage", "Frost", 110)),
    )
    finding = analysed(sample=a_sample().model_copy(update={"references": kills}))[FROST_ID]
    assert finding.title.endswith("by 1:40")
    assert (
        "Compared through 1:40, after which fewer than three Frost Mages were still fighting"
        in finding.evidence
    )


def test_a_death_after_the_band_cut_is_not_named_as_a_dead_stretch() -> None:
    """The band cuts the comparison at 1:40 (100 s); a death at 2:30, answered
    at 2:50, happened after the last second compared and must not be named --
    it would otherwise read as a stretch inside a comparison that had already
    ended."""
    kills = (
        a_reference_kill(a_peer("Mage", "Frost", 90, until_seconds=100.0)),
        a_reference_kill(a_peer("Mage", "Frost", 100)),
        a_reference_kill(a_peer("Mage", "Frost", 110)),
    )
    death = Death(player_name="Emberkin", actor_id=1, timestamp_ms=150_000, killing_blow="Crush")
    rez = Resurrection(actor_id=1, caster_id=2, ability_id=20484, ability_name="Rebirth",
                       timestamp_ms=170_000)
    finding = analysed(
        loaded=a_wipe(deaths=(death,), resurrections=(rez,)),
        sample=a_sample().model_copy(update={"references": kills}),
    )[FROST_ID]
    assert (
        "Compared through 1:40, after which fewer than three Frost Mages were still fighting"
        in finding.evidence
    )
    assert not any(line.startswith("Dead from") for line in finding.evidence)


def test_a_player_the_graph_never_saw_dealt_nothing_and_has_no_lag() -> None:
    finding = analysed(sample=a_sample().model_copy(update={"our_players": ()}))[FROST_ID]
    assert finding.title.startswith("Behind the kills' Frost Mages: 0% ")
    assert not any(line.startswith("By ") for line in finding.evidence)


def test_a_tank_is_compared_and_below_three_peers_is_withheld_with_the_count() -> None:
    notice = analysed(players=(BLOOD,))[f"{PLAYER_UNAVAILABLE_PREFIX}.p2"]
    assert notice.title == (
        "Only 2 Blood Death Knights in the reference kills: fewer than three to compare against"
    )
    assert notice.confidence is Confidence.MEASURED
    assert notice.player_slug == "p2"


def test_no_peer_at_all_is_withheld_in_the_singular() -> None:
    notice = analysed(players=(AFFLICTION,))[f"{PLAYER_UNAVAILABLE_PREFIX}.p5"]
    assert notice.title == (
        "No Affliction Warlock in the reference kills: fewer than three to compare against"
    )


def test_a_healer_is_not_compared() -> None:
    assert analysed(players=(HOLY,)) == {}


def test_an_unnamed_specialisation_is_withheld_and_says_so() -> None:
    notice = analysed(players=(UNNAMED,))[f"{PLAYER_UNAVAILABLE_PREFIX}.p4"]
    assert notice.title == NO_SPEC_TITLE


def test_a_kill_is_never_compared() -> None:
    loaded = LoadedEncounter(encounter=an_encounter(kill=True, players=ROSTER))
    assert analysed(loaded=loaded) == {}


def test_nothing_is_said_per_player_when_the_raid_wide_comparison_was_withheld() -> None:
    assert analysed(sample=PaceSample(unavailable=NO_REFERENCE_KILL)) == {}


def test_nothing_is_said_per_player_when_the_raid_wide_pace_has_nothing_to_compare() -> None:
    """The references dealt the boss zero aggregate damage through the wipe, so the
    raid-wide comparison withholds with `compare.pace.unavailable` (its
    NOTHING_TO_COMPARE reason) even though real per-player peer series exist:
    the per-player analyser must withhold too, not just the raid-wide one."""
    kills = tuple(
        a_reference_kill(a_peer("Mage", "Frost", rate)).model_copy(
            update={"damage": steady(0, 400)}
        )
        for rate in (90, 100, 110)
    )
    sample = a_sample().model_copy(update={"references": kills})
    assert analysed(sample=sample) == {}


def test_no_finding_prints_a_raw_damage_figure() -> None:
    for finding in analysed(players=ROSTER).values():
        for text in (finding.title, finding.detail, *finding.evidence):
            assert not re.search(r"\d{4,}", text), text


def test_a_spec_name_two_classes_share_is_not_pooled() -> None:
    """Frost is a Mage spec and a Death Knight spec: three Frost Death Knights are no peers."""
    kills = tuple(a_reference_kill(a_peer("DeathKnight", "Frost", 100)) for _ in range(3))
    sample = a_sample().model_copy(update={"references": kills})
    notice = analysed(sample=sample)[f"{PLAYER_UNAVAILABLE_PREFIX}.p1"]
    assert notice.title == (
        "No Frost Mage in the reference kills: fewer than three to compare against"
    )
