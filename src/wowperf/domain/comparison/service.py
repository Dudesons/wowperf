# ABOUTME: Runs every comparison against the two reference samples and ranks what they find.
# ABOUTME: Deliberately dull: all the judgement lives in the comparison modules, none of it here.

from wowperf.domain.analysis.trash import forces_by_pull
from wowperf.domain.auras import PlayerAuras
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


def compare(
    ours: LoadedRun,
    our_player: Player,
    speed: SpeedSample | None,
    parse: ParseSample | None,
    our_auras: PlayerAuras | None = None,
) -> list[Finding]:
    """Every comparison, one ranked list.

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

    if parse is None or not parse.members:
        findings.append(
            _unavailable(
                "compare.parse.unavailable",
                f"No ranked parse was available for {our_player.class_name} {our_player.spec}",
                "The score leaderboard returned nothing for this specialisation within one "
                "keystone level of this run, so spells, talents and uptime are not compared.",
            )
        )
    else:
        top = parse.top
        assert top is not None  # parse.members is non-empty here, so a top member exists
        findings += compare_spells_sample(ours, our_player, parse)
        findings += compare_talents(
            our_player, find_player(top.run, top.row.character_name), top.row
        )
        findings += compare_uptime_sample(ours.run, our_auras, our_player, parse)

    return rank_findings(findings)
