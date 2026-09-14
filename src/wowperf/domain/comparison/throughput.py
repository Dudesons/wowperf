# ABOUTME: How a raid player's throughput stacks up against the board, on two axes.
# ABOUTME: compare_rank flags a percentile without diagnosing; compare_damage_total never divides.

from wowperf.domain.comparison.raid_reference import RaidParseRow, RankedPlayer, ReportRankings
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, SAMPLE_SIZE, too_few
from wowperf.domain.comparison.statistics import median, observed_range
from wowperf.domain.findings import Confidence, Finding, FindingFact, quantity

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


DAMAGE_UNAVAILABLE_ID = "compare.damage.total.unavailable"

DAMAGE_DETAIL = (
    "Both figures are damage per second, not a total over the fight, so our own figure and "
    "the sample's median are the same unit throughout. Sitting on one side of the median for "
    "all damage and the other for boss damage only states a difference between the two: where "
    "the damage landed, on the boss alone or on adds as well. It states no verdict on which is "
    "right for this kill."
)
"""What `compare.damage.total` tells a reader, in the finding's own words.

Both `RankedPlayer.amount` and `RaidParseRow.amount` are per-second rates already
(measured 2026-09-14; `RaidParseRow`'s own docstring records the same fact for its
side). Nothing in this module divides either by `duration_seconds` or multiplies
either by one -- doing so would be the count-against-rate mistake a plan already
shipped once, comparing an absolute total against a per-minute figure.
"""


def _damage_unavailable(our_name: str) -> Finding:
    return Finding(
        id=DAMAGE_UNAVAILABLE_ID,
        title=f"No damage comparison is available for {our_name}",
        detail=(
            "This attempt did not kill the boss, so Warcraft Logs computed no damage "
            "rankings for it, and no comparison against the board can be made."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
    )


def _status(ours: float, middle: float) -> str:
    """Where our figure sits against the sample's middle, as the title's own word."""
    if ours > middle:
        return "above"
    if ours < middle:
        return "below"
    return "level with"


def _metric_state(board: tuple[RaidParseRow, ...]) -> tuple[float, float, float, int, int]:
    """This metric's median (or a single reference, below the aggregate floor), its
    observed range, how many rows fed that figure, and how many were eligible before
    the floor collapsed them to one.

    Sliced to `SAMPLE_SIZE` first, exactly like every other sample in this codebase.
    `RaidParseRow.amount` is a per-second rate already -- nothing here divides it by
    `duration_seconds`, and nothing multiplies it by one.
    """
    eligible = board[:SAMPLE_SIZE]
    used = eligible if len(eligible) >= MIN_SAMPLE_FOR_AGGREGATE else eligible[:1]
    amounts = [row.amount for row in used]
    middle = median(amounts)
    low, high = observed_range(amounts)
    return middle, low, high, len(used), len(eligible)


def compare_damage_total(
    ours: RankedPlayer | None,
    our_boss: RankedPlayer | None,
    board: tuple[RaidParseRow, ...],
    boss_board: tuple[RaidParseRow, ...],
    our_name: str,
) -> list[Finding]:
    """Our damage throughput against the board median, on both metrics at once.

    `ours` and `our_boss` are the player's own rows on the all-damage and the
    boss-damage-only leaderboards. Either is `None` on an attempt that produced no
    rankings row at all (a wipe), and that returns `compare.damage.total.unavailable`
    rather than an empty list: silence would read as a clean result, and this says
    why there is nothing instead.

    `board` and `boss_board` are two independent leaderboards, not the same
    references read twice -- a top parse by all damage need not be a top parse by
    boss damage alone -- so each is sliced to `SAMPLE_SIZE` and medianed on its own,
    and each falls back to `too_few`'s single-reference wording on its own below
    `MIN_SAMPLE_FOR_AGGREGATE`.

    Both `RankedPlayer.amount` and `RaidParseRow.amount` are per-second rates
    already, so nothing here divides by a duration or multiplies by one -- F9 is
    the whole of this function's arithmetic risk.

    A player above one median and below the other is the signal this pair exists
    to show: the title states it as a difference in where the damage landed, never
    as a claim that either outcome was avoidable.
    """
    if ours is None:
        return [_damage_unavailable(our_name)]

    all_middle, all_low, all_high, all_used, all_eligible = _metric_state(board)
    all_status = _status(ours.amount, all_middle)
    facts = [
        FindingFact(
            label="All damage",
            value=f"{ours.amount:.1f} against a median of {all_middle:.1f}",
        )
    ]
    evidence = [
        f"all damage range {all_low:.1f} to {all_high:.1f} over "
        f"{quantity(all_used, 'reference', 'references')}"
    ]
    below_floor = {all_eligible} if all_eligible < MIN_SAMPLE_FOR_AGGREGATE else set()

    if our_boss is None:
        title = f"{our_name} sat {all_status} the sample median on all damage"
    else:
        boss_middle, boss_low, boss_high, boss_used, boss_eligible = _metric_state(boss_board)
        boss_status = _status(our_boss.amount, boss_middle)
        facts.append(
            FindingFact(
                label="Boss damage only",
                value=f"{our_boss.amount:.1f} against a median of {boss_middle:.1f}",
            )
        )
        evidence.append(
            f"boss damage range {boss_low:.1f} to {boss_high:.1f} over "
            f"{quantity(boss_used, 'reference', 'references')}"
        )
        if boss_eligible < MIN_SAMPLE_FOR_AGGREGATE:
            below_floor.add(boss_eligible)

        if boss_status == all_status:
            title = (
                f"{our_name} sat {all_status} the sample median on both all damage and "
                "boss damage"
            )
        else:
            title = (
                f"{our_name} sat {boss_status} the sample median on boss damage while "
                f"{all_status} it on all damage"
            )

    findings = [
        Finding(
            id="compare.damage.total",
            title=title,
            detail=DAMAGE_DETAIL,
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            evidence=tuple(evidence),
            facts=tuple(facts),
        )
    ]
    for count in sorted(below_floor):
        findings = too_few(findings, count)
    return findings
