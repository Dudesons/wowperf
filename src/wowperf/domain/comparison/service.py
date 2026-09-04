# ABOUTME: Runs every comparison against the two reference runs and ranks what they find.
# ABOUTME: Deliberately dull: all the judgement lives in the comparison modules, none of it here.

from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.comparison.confounds import declare_confounds
from wowperf.domain.comparison.reference import Comparability, ParseReference, SpeedReference
from wowperf.domain.comparison.route import compare_route
from wowperf.domain.comparison.spells import compare_spells, compare_talents
from wowperf.domain.comparison.tempo import compare_tempo
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
    speed: SpeedReference | None,
    parse: ParseReference | None,
) -> list[Finding]:
    """Every comparison, one ranked list."""
    findings: list[Finding] = []

    if speed is None:
        findings.append(
            _unavailable(
                "compare.speed.unavailable",
                "No faster run was available to compare the route against",
                "The speed leaderboard returned nothing for this dungeon within one keystone "
                "level of this run, so route, downtime, deaths and interrupts are not compared.",
            )
        )
    else:
        rule = Comparability(
            our_level=ours.run.keystone_level, their_level=speed.loaded.run.keystone_level
        )
        findings += compare_route(
            ours.run, speed.loaded.run, align_pulls(ours.run, speed.loaded.run)
        )
        findings += compare_tempo(ours, speed.loaded, rule)
        findings += declare_confounds(ours, speed.loaded, rule)

    if parse is None:
        findings.append(
            _unavailable(
                "compare.parse.unavailable",
                f"No ranked parse was available for {our_player.class_name} {our_player.spec}",
                "The score leaderboard returned nothing for this specialisation within one "
                "keystone level of this run, so spells and talents are not compared.",
            )
        )
    else:
        findings += compare_spells(ours, our_player, parse.loaded, parse.row.character_name)
        findings += compare_talents(
            our_player, find_player(parse.loaded.run, parse.row.character_name)
        )

    return rank_findings(findings)
