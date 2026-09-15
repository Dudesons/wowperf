# ABOUTME: How a raid player's throughput stacks up against the board, on two axes.
# ABOUTME: compare_rank flags a percentile without diagnosing; compare_damage_total never divides.

from wowperf.domain.comparison.raid_reference import RaidParseRow, ReportRankings
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


def _shared_name_detail(ranked_name: str, withheld: str) -> str:
    """Why a lookup that found two rows answers with neither, in a reader's words.

    The third reason a lookup into this report's own rankings comes back with
    nothing, and it must not read as either of the others. "There was no kill"
    is about the attempt; "you are not on this board" is about one player's
    absence from a row that exists; this one is about a row that exists, names
    this player, and names somebody else identically.

    A rankings row carries a character name and no actor id (`RankedPlayer`
    records the measurement), so where two roster members share a name the two
    rows cannot be told apart by anything the API sends. Taking the first would
    print one player's standing on the other player's card under a
    disambiguated title, badged `MEASURED` -- a confident wrong answer where
    this says nothing and explains why.

    Written for two or more matches: "more than one" stays true of three, which
    a large guild raid can produce.
    """
    return (
        f"More than one player in this report is named {ranked_name}, and a rankings row "
        "carries a character name with no actor id beside it, so which of those rows is this "
        f"player's cannot be established. {withheld} is stated rather than one that may be "
        "another player's."
    )


def compare_rank(
    standing: ReportRankings | None,
    boss_standing: ReportRankings | None,
    our_name: str,
    ranked_name: str,
) -> list[Finding]:
    """The subject's percentile on this boss, on both metrics, as one triage line.

    `standing` is the report's `dps` rankings row and `boss_standing` its `bossdps`
    row -- both metrics of the same kill, never a second reference. Either is
    `None` on an attempt that produced no rankings row at all (a wipe, design
    section 14 item 7), and a wipe, a player missing from a present row and a
    name that row carries twice all return `compare.rank.unavailable` rather
    than an empty list: silence would read as a clean result, and this says why
    there is nothing instead.

    `our_name` is the spelling every sentence below shows a reader, which
    `display_names` disambiguates as `Emberkin (actor 693)` whenever two roster
    members share a name. `ranked_name` is the plain roster name the rankings
    row itself carries, and is the only one the join may read: a raid of twenty
    produces a shared name readily, and joining on the shown spelling matches
    nobody and reports a kill as an attempt with no rankings row. Two arguments
    rather than one because the two jobs are genuinely different -- collapsing
    them is what produced that sentence.

    The plain name is what a row can be found by and not what tells two players
    apart, so the shared-name case has a third sentence of its own: two rows
    folding to one name are two rows the API gives nothing to separate, and this
    withholds rather than take the first. A reader can tell the three states
    apart -- no kill, absent from a row that exists, or a name this report
    carries twice.

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
    rows = standing.rows_named(ranked_name)
    boss_rows = boss_standing.rows_named(ranked_name) if boss_standing is not None else ()
    # Both metrics are checked before either is read: the two boards are the
    # same roster under two measurements, so a name shared on one is shared on
    # the other, and a card that stated an unambiguous all-damage percentile
    # beside somebody else's boss-damage one would be half right and wholly
    # unreadable.
    if len(rows) > 1 or len(boss_rows) > 1:
        return [_unavailable(our_name, _shared_name_detail(ranked_name, "No percentile"))]
    if not rows:
        return [
            _unavailable(
                our_name,
                f"{our_name} does not appear in this report's rankings, so no percentile can "
                "be stated for them.",
            )
        ]
    player = rows[0]
    boss_player = boss_rows[0] if boss_rows else None

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
    "the one it is set against are the same unit throughout. Sitting on one side of that "
    "figure for all damage and the other for boss damage only states a difference between "
    "the two: where the damage landed, on the boss alone or on adds as well. It states no "
    "verdict on which is right for this kill."
)
"""What `compare.damage.total` tells a reader, in the finding's own words.

Names no statistic. One detail is written for a card whose two metrics reach the
aggregate floor independently, so it can be beside a median, beside a single
reference, or beside one of each -- and "the sample's median" is false of two of
those three. The title and the facts say which of the two each metric got; this
sentence says what the comparison means either way.

Both `RankedPlayer.amount` and `RaidParseRow.amount` are per-second rates already
(measured 2026-09-14; `RaidParseRow`'s own docstring records the same fact for its
side). Nothing in this module divides either by `duration_seconds` or multiplies
either by one -- doing so would be the count-against-rate mistake a plan already
shipped once, comparing an absolute total against a per-minute figure.
"""


def _damage_unavailable(our_name: str, detail: str) -> Finding:
    """One title over four reasons, each of which a reader must be able to name.

    The title says what is missing and the detail says why. Four states leave
    this comparison with nothing to state -- no kill, a name this report carries
    twice, a player absent from a row that exists, and a leaderboard that came
    back empty -- and each asks something different of a reader, so each carries
    a sentence of its own rather than a shared apology.
    """
    return Finding(
        id=DAMAGE_UNAVAILABLE_ID,
        title=f"No damage comparison is available for {our_name}",
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
    )


DAMAGE_WIPE_DETAIL = (
    "This attempt did not kill the boss, so Warcraft Logs computed no damage "
    "rankings for it, and no comparison against the board can be made."
)
"""Why there is no damage comparison at all: Warcraft Logs ranks kills alone."""


def _damage_absent_detail(our_name: str) -> str:
    """The kill happened and the rankings row does not carry this player.

    Distinct from the wipe above and from the shared name beside it: a row
    exists, it names other players, and it names nobody as this one. "This
    attempt did not kill the boss" is false of that attempt, and a reader acting
    on it would go looking for a kill the log already holds.
    """
    return (
        f"This attempt killed the boss, but {our_name} does not appear in this report's "
        "damage rankings for it, so there is no figure of theirs to set against the board."
    )


def _damage_no_sample_detail(axis: str) -> str:
    """The kill happened, but the axis named by `axis` has nothing to compare against.

    Worded so it cannot be mistaken for the wipe case: this attempt killed the
    boss, and the log says so. What is missing is the leaderboard's own
    reference sample -- a thin sample for an uncommon spec at this difficulty,
    or a fetch that returned nothing -- not a rankings row for us. A reader must
    be able to tell "there was no kill" from "there was a kill and no reference
    sample to compare it against", because those call for different things.
    """
    return (
        f"This attempt killed the boss, but the {axis} leaderboard returned no "
        "reference rows to compare against, so no median can be stated for that metric."
    )


def _reference(eligible: int) -> str:
    """What one metric's reference side is, as a title names it.

    Below `MIN_SAMPLE_FOR_AGGREGATE` the figure is one board row and `too_few`
    says so in the evidence, so a title calling it the sample median would
    contradict the line beneath it. The siblings that call `too_few` --
    `compare_mechanics`, `compare_tempo`, `compare_route` and `compare_spells`
    -- each delegate to a pairwise form for the same reason; this comparison
    states two metrics on one card and switches the noun per metric instead.
    """
    return "the sample median" if eligible >= MIN_SAMPLE_FOR_AGGREGATE else "a single reference"


def _against(ours: float, middle: float, eligible: int) -> str:
    """Our figure and the one it is set against, as a fact states the pair."""
    if eligible >= MIN_SAMPLE_FOR_AGGREGATE:
        return f"{ours:.1f} against a median of {middle:.1f}"
    return f"{ours:.1f} against a single reference's {middle:.1f}"


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


def _labelled_too_few(finding: Finding, axis: str, eligible: int) -> Finding:
    """`too_few`'s own note, prefixed with which axis it belongs to.

    Two axes can each fall below `MIN_SAMPLE_FOR_AGGREGATE` with different
    counts, and a finding stating two bare counts with no label leaves a
    reader unable to pair either back to all damage or boss damage only.
    `too_few` itself appends its note to a finding's evidence and returns a
    new finding; this reuses that exact wording (so the pluralisation rule
    is not duplicated) by running it against a throwaway finding with no
    evidence of its own, then carries only the note it produced, labelled,
    onto the finding this module is actually building.
    """
    placeholder = Finding(id="_", title="", detail="", confidence=Confidence.MEASURED)
    note = too_few([placeholder], eligible)[0].evidence[-1]
    return finding.model_copy(update={"evidence": (*finding.evidence, f"{axis}: {note}")})


def compare_damage_total(
    standing: ReportRankings | None,
    boss_standing: ReportRankings | None,
    board: tuple[RaidParseRow, ...],
    boss_board: tuple[RaidParseRow, ...],
    our_name: str,
    ranked_name: str,
) -> list[Finding]:
    """Our damage throughput against the board median, on both metrics at once.

    `standing` and `boss_standing` are this report's own rankings rows for the
    all-damage and the boss-damage-only metrics -- the whole containers and not
    our row out of them, exactly as `compare_rank` takes them and for the same
    reason: the three ways a row can fail to yield our figure say different
    things to a reader, and a caller that resolved the row first could only hand
    over `None` for all three. Either is `None` on an attempt that produced no
    rankings row at all (a wipe), and that returns
    `compare.damage.total.unavailable` rather than an empty list: silence would
    read as a clean result, and this says why there is nothing instead.

    `our_name` is the spelling every sentence shows a reader and `ranked_name`
    the plain roster name a rankings row carries; `compare_rank`'s docstring
    records why the two are separate arguments. A name two roster members share
    folds to two rows with nothing to separate them, and that withholds too --
    the first match would be another player's throughput printed under this
    player's disambiguated title and badged `MEASURED`.

    A kill can still leave `board` or `boss_board` empty -- the two leaderboards
    are fetched independently of whether this report's own rankings produced a
    row, and a thin sample for an uncommon spec at this difficulty, or a fetch
    that returned nothing, is a real state rather than a failure to guard
    against. Either board empty also returns `compare.damage.total.unavailable`,
    worded so it cannot be mistaken for the wipe case: this attempt killed the
    boss, and what is missing is the leaderboard's own reference sample, not a
    rankings row for us.

    `board` and `boss_board` are two independent leaderboards, not the same
    references read twice -- a top parse by all damage need not be a top parse by
    boss damage alone -- so each is sliced to `SAMPLE_SIZE` and medianed on its own,
    and each falls back to `too_few`'s single-reference wording on its own below
    `MIN_SAMPLE_FOR_AGGREGATE`, labelled by which axis it belongs to so two
    different counts on the two axes never read as one ambiguous pair. Each
    metric's own title clause and fact name what it stands against as well, so
    that neither says "the sample median" over a figure `too_few` has just
    called a single reference.

    Both `RankedPlayer.amount` and `RaidParseRow.amount` are per-second rates
    already, so nothing here divides by a duration or multiplies by one -- F9 is
    the whole of this function's arithmetic risk.

    A player above one median and below the other is the signal this pair exists
    to show: the title states it as a difference in where the damage landed, never
    as a claim that either outcome was avoidable.
    """
    if standing is None:
        return [_damage_unavailable(our_name, DAMAGE_WIPE_DETAIL)]

    rows = standing.rows_named(ranked_name)
    boss_rows = boss_standing.rows_named(ranked_name) if boss_standing is not None else ()
    # Both metrics are checked before either is read, for the reason
    # `compare_rank` gives at the same check: the two boards measure one roster
    # twice, so a name shared on one is shared on the other.
    if len(rows) > 1 or len(boss_rows) > 1:
        return [
            _damage_unavailable(
                our_name, _shared_name_detail(ranked_name, "No damage comparison")
            )
        ]
    if not rows:
        return [_damage_unavailable(our_name, _damage_absent_detail(our_name))]
    ours = rows[0]
    our_boss = boss_rows[0] if boss_rows else None

    # A kill can still leave a leaderboard empty -- a thin sample for an
    # uncommon spec at this difficulty, or a fetch that returned nothing.
    # That is a real state, not a failure to guard against: `_metric_state`
    # would otherwise hand an empty list to `median`, which raises. Checked
    # before either axis is touched, so neither board is read past its own
    # emptiness, and the four reasons -- no kill, a name this report carries
    # twice, a player absent from the row, no reference sample -- stay
    # distinguishable in the finding's own words.
    if not board:
        return [_damage_unavailable(our_name, _damage_no_sample_detail("all damage"))]
    if our_boss is not None and not boss_board:
        return [_damage_unavailable(our_name, _damage_no_sample_detail("boss damage"))]

    all_middle, all_low, all_high, all_used, all_eligible = _metric_state(board)
    all_status = _status(ours.amount, all_middle)
    all_reference = _reference(all_eligible)
    facts = [
        FindingFact(
            label="All damage",
            value=_against(ours.amount, all_middle, all_eligible),
        )
    ]
    evidence = [
        f"all damage range {all_low:.1f} to {all_high:.1f} over "
        f"{quantity(all_used, 'reference', 'references')}"
    ]

    if our_boss is None:
        title = f"{our_name} sat {all_status} {all_reference} on all damage"
    else:
        boss_middle, boss_low, boss_high, boss_used, boss_eligible = _metric_state(boss_board)
        boss_status = _status(our_boss.amount, boss_middle)
        boss_reference = _reference(boss_eligible)
        facts.append(
            FindingFact(
                label="Boss damage only",
                value=_against(our_boss.amount, boss_middle, boss_eligible),
            )
        )
        evidence.append(
            f"boss damage range {boss_low:.1f} to {boss_high:.1f} over "
            f"{quantity(boss_used, 'reference', 'references')}"
        )

        if boss_status == all_status and boss_reference == all_reference:
            title = (
                f"{our_name} sat {all_status} {all_reference} on both all damage and "
                "boss damage"
            )
        else:
            # "it" only where both metrics stand against the same kind of
            # reference side. The two boards fall below the aggregate floor
            # independently, so one can be a median while the other is a single
            # reference -- and there the pronoun would point at the wrong one.
            tail = "it" if boss_reference == all_reference else all_reference
            title = (
                f"{our_name} sat {boss_status} {boss_reference} on boss damage while "
                f"{all_status} {tail} on all damage"
            )

    finding = Finding(
        id="compare.damage.total",
        title=title,
        detail=DAMAGE_DETAIL,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=tuple(evidence),
        facts=tuple(facts),
    )

    # Each axis is labelled on its own note rather than pooled into one set of
    # counts: two axes can fall below the floor with different counts, and an
    # unlabelled pair of numbers leaves a reader with no way to say which
    # count belongs to which metric.
    if all_eligible < MIN_SAMPLE_FOR_AGGREGATE:
        finding = _labelled_too_few(finding, "all damage", all_eligible)
    if our_boss is not None and boss_eligible < MIN_SAMPLE_FOR_AGGREGATE:
        finding = _labelled_too_few(finding, "boss damage", boss_eligible)

    return [finding]
