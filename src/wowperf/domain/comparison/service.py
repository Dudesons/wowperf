# ABOUTME: Runs every comparison against the two reference samples and ranks what they find.
# ABOUTME: Deliberately dull: all the judgement lives in the comparison modules, none of it here.

from collections.abc import Sequence

from pydantic import Field

from wowperf.domain.analysis.trash import forces_by_pull
from wowperf.domain.auras import PlayerAuras
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.confounds import declare_confounds_sample
from wowperf.domain.comparison.route import compare_route_sample
from wowperf.domain.comparison.sample import ParseSample, SpeedSample
from wowperf.domain.comparison.sample import find_player as find_player
from wowperf.domain.comparison.spells import compare_spells_sample, compare_talents
from wowperf.domain.comparison.tempo import compare_tempo_sample
from wowperf.domain.comparison.trash_spells import compare_trash_spells_sample
from wowperf.domain.comparison.uptime import compare_uptime_sample
from wowperf.domain.findings import Confidence, Finding, rank_findings
from wowperf.domain.model import LoadedRun, Player


def _unavailable(finding_id: str, title: str, detail: str) -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=("no reference run was available",),
    )


class ComparisonSubject(Frozen):
    """One player to compare, with everything that comparison needs.

    `slug` comes from `slugs_by_actor` and is what makes this player's
    findings addressable: the report's card for the same player carries the
    identical string, so a pointer into a finding lands in the right sub-tab.
    It cannot be empty, because both of the ways an empty one goes wrong are
    silent: `_for_player` would mint `compare.talents.`, a family prefix with
    a trailing dot, and stamp a `player_slug` of "" that no consumer can tell
    from a run-level finding's.

    `display_name` is the spelling every finding title uses for this player,
    and it is carried rather than taken from `player.name`: two roster members
    can share a name, and only `display_names` tells them apart -- the same
    function `slugs_by_actor` reads, so a title, a card heading and a
    provenance row all name a player the one way. It cannot be empty either: a
    title built around an empty name reads as a sentence with a hole in it,
    and no reader could tell whose finding it was.
    """

    player: Player
    slug: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    parse: ParseSample | None
    our_auras: PlayerAuras | None = None


def _for_player(findings: list[Finding], slug: str) -> list[Finding]:
    """Re-mint plain comparison ids as one player's own.

    The comparison modules know nothing about who else is in the run, so they
    mint `compare.talents` and this appends the player. Doing it in one place
    is what keeps five modules from each having to be told about the roster,
    and it is why the id is a suffix: every consumer of these ids matches by
    prefix, and a prefix survives anything appended to it.
    """
    return [
        finding.model_copy(update={"id": f"{finding.id}.{slug}", "player_slug": slug})
        for finding in findings
    ]


def _compare_player(ours: LoadedRun, subject: ComparisonSubject) -> list[Finding]:
    """Everything measured about one player against their own parse sample.

    A player the log records no specialisation for is a separate absence from
    a leaderboard that offered nothing, and must not be reported as one: no
    leaderboard was asked, because a specialisation is what one is asked for.
    """
    if not subject.player.spec:
        return [
            _unavailable(
                "compare.parse.unavailable",
                f"No ranked parse was available for {subject.display_name} "
                f"({subject.player.class_name})",
                "This log records no specialisation for this player, so no score "
                "leaderboard could be asked for one, and spells, talents and uptime "
                "are not compared.",
            )
        ]
    parse = subject.parse
    if parse is None or not parse.members:
        return [
            _unavailable(
                "compare.parse.unavailable",
                f"No ranked parse was available for {subject.display_name} "
                f"({subject.player.class_name} {subject.player.spec})",
                "The score leaderboard returned nothing for this specialisation within one "
                "keystone level of this run, so spells, talents and uptime are not compared.",
            )
        ]
    top = parse.top
    assert top is not None  # parse.members is non-empty here, so a top member exists
    return [
        *compare_spells_sample(ours, subject.player, subject.display_name, parse),
        *compare_trash_spells_sample(ours, subject.player, subject.display_name, parse),
        *compare_talents(
            subject.player,
            subject.display_name,
            find_player(top.run, top.row.character_name),
            top.row,
        ),
        *compare_uptime_sample(ours.run, subject.our_auras, subject.display_name, parse),
    ]


def compare(
    ours: LoadedRun,
    speed: SpeedSample | None,
    subjects: Sequence[ComparisonSubject],
) -> list[Finding]:
    """Every comparison, one ranked list.

    The speed axis is a statement about the run and is compared once, whoever
    is being looked at. The parse axis is a statement about a player and is
    compared once per subject, each against their own specialisation's sample.

    An empty sample and no sample at all mean the same thing to a reader: the
    leaderboard offered nothing to compare against.
    """
    findings: list[Finding] = []

    if speed is None or not speed.members:
        findings.append(
            _unavailable(
                "compare.speed.unavailable",
                "No faster run was available to compare the route against",
                "The speed leaderboard returned nothing for this dungeon within one keystone "
                "level of this run, so route, downtime, deaths and interrupts are not compared.",
            )
        )
    else:
        findings += compare_route_sample(ours.run, speed, forces_by_pull(ours.enemy_deaths))
        findings += compare_tempo_sample(ours, speed)
        findings += declare_confounds_sample(ours, speed)

    for subject in subjects:
        findings += _for_player(_compare_player(ours, subject), subject.slug)

    return rank_findings(findings)
