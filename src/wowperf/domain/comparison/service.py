# ABOUTME: Runs every comparison against the two reference samples and ranks what they find.
# ABOUTME: Deliberately dull: all the judgement lives in the comparison modules, none of it here.

from collections.abc import Sequence

from wowperf.domain.analysis.trash import forces_by_pull
from wowperf.domain.auras import PlayerAuras
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.confounds import declare_confounds_sample
from wowperf.domain.comparison.route import compare_route_sample
from wowperf.domain.comparison.sample import ParseSample, SpeedSample
from wowperf.domain.comparison.spells import compare_spells_sample, compare_talents
from wowperf.domain.comparison.tempo import compare_tempo_sample
from wowperf.domain.comparison.uptime import compare_uptime_sample
from wowperf.domain.findings import Confidence, Finding, rank_findings
from wowperf.domain.model import LoadedRun, Player, Run


def find_player(run: Run, name: str) -> Player | None:
    """Find a roster member by name, folding case.

    The report owner's name comes back from Warcraft Logs lowercased while the
    roster carries the character's own capitalisation, so an exact match would
    fail on the default path every time.
    """
    folded = name.casefold()
    return next((player for player in run.players if player.name.casefold() == folded), None)


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
    """

    player: Player
    slug: str
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
    """Everything measured about one player against their own parse sample."""
    parse = subject.parse
    if parse is None or not parse.members:
        return [
            _unavailable(
                "compare.parse.unavailable",
                f"No ranked parse was available for {subject.player.name} "
                f"({subject.player.class_name} {subject.player.spec})",
                "The score leaderboard returned nothing for this specialisation within one "
                "keystone level of this run, so spells, talents and uptime are not compared.",
            )
        ]
    top = parse.top
    assert top is not None  # parse.members is non-empty here, so a top member exists
    return [
        *compare_spells_sample(ours, subject.player, parse),
        *compare_talents(
            subject.player, find_player(top.run, top.row.character_name), top.row
        ),
        *compare_uptime_sample(ours.run, subject.our_auras, subject.player, parse),
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
