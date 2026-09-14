# ABOUTME: The report's own percentile for a player, stated as triage and never as a target.
# ABOUTME: Master design section 6.7 binds the words here: it flags, it never diagnoses.

from wowperf.domain.comparison.raid_reference import ReportRankings
from wowperf.domain.findings import Confidence, Finding, FindingFact

UNAVAILABLE_ID = "compare.rank.unavailable"

DETAIL = (
    "A percentile is triage, not a verdict: it says that something about this performance is "
    "worth a closer look, never what that something is, and it names no cause on its own. It is "
    "not a target -- nothing here asks a player to chase a higher number."
)
"""Section 6.7's constraint, in the finding's own words: it indicates that something is
wrong and never what, it is never a headline, and it is never an optimisation target."""


def _ordinal(n: int) -> str:
    """`n` spelled as an ordinal: 96 -> "96th", 71 -> "71st", 11 -> "11th".

    Percentiles run 1 to 100, and 11 to 13 (and their hundreds-multiples) take
    "th" where the last-digit rule alone would say "st"/"nd"/"rd".
    """
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _unavailable(our_name: str, detail: str) -> Finding:
    return Finding(
        id=UNAVAILABLE_ID,
        title=f"No percentile is available for {our_name}",
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
    )


def compare_rank(
    standing: ReportRankings | None,
    boss_standing: ReportRankings | None,
    our_name: str,
) -> list[Finding]:
    """The subject's percentile on this boss, on both metrics, as one triage line.

    `standing` is the report's `dps` rankings row and `boss_standing` its `bossdps`
    row -- both metrics of the same kill, never a second reference. Either is
    `None` on an attempt that produced no rankings row at all (a wipe, design
    section 14 item 7), and a wipe or a player missing from a present row both
    return `compare.rank.unavailable` rather than an empty list: silence would
    read as a clean result, and this says why there is nothing instead.

    Badged `MEASURED`: Warcraft Logs computed the percentile itself and nothing
    here reconstructs it. `seconds_lost` is always `None` -- a percentile costs
    no time, and `rank_raid_findings` sorts a `None` last within its family,
    which is where section 6.7 wants a triage line.
    """
    if standing is None:
        return [
            _unavailable(
                our_name,
                "This attempt did not kill the boss, so Warcraft Logs computed no rankings "
                "row for it, and no percentile can be stated.",
            )
        ]
    player = standing.player_named(our_name)
    if player is None:
        return [
            _unavailable(
                our_name,
                f"{our_name} does not appear in this report's rankings, so no percentile can "
                "be stated for them.",
            )
        ]
    boss_player = boss_standing.player_named(our_name) if boss_standing is not None else None

    all_ordinal = _ordinal(player.rank_percent)
    facts = [
        FindingFact(
            label="All damage",
            value=f"{all_ordinal} percentile of {player.total_parses} parses",
        )
    ]
    if boss_player is not None and boss_player.rank_percent != player.rank_percent:
        boss_ordinal = _ordinal(boss_player.rank_percent)
        facts.append(
            FindingFact(
                label="Boss damage only",
                value=f"{boss_ordinal} percentile of {boss_player.total_parses} parses",
            )
        )
        title = (
            f"{our_name} ranks in the {all_ordinal} percentile on all damage and the "
            f"{boss_ordinal} percentile on boss damage only"
        )
    else:
        if boss_player is not None:
            facts.append(
                FindingFact(
                    label="Boss damage only",
                    value=f"{all_ordinal} percentile of {boss_player.total_parses} parses",
                )
            )
        title = f"{our_name} ranks in the {all_ordinal} percentile on this boss"

    return [
        Finding(
            id="compare.rank",
            title=title,
            detail=DETAIL,
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            facts=tuple(facts),
        )
    ]
