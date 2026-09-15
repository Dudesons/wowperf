# ABOUTME: One player's damage as a share per target -- the boss against everything else.
# ABOUTME: compare_targets states shares only; a total confounds focus with fight length and gear.

from collections.abc import Sequence

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, too_few
from wowperf.domain.comparison.statistics import median, observed_range
from wowperf.domain.findings import Confidence, Finding, FindingFact, quantity


class TargetRow(Frozen):
    """One target's damage-done row, as `viewBy: Target` reports it, scoped to one subject.

    `kind` is the API's own `type` field, carried verbatim: `'Boss'`, `'NPC'` or `'Pet'`. F12
    is what makes this buildable without a per-encounter rule, a phase table or a boss list of
    this project's own -- the row already says which target it is.
    """

    target_id: int
    name: str
    kind: str
    total: int

    @property
    def is_boss(self) -> bool:
        return self.kind == "Boss"


UNAVAILABLE_ID = "compare.damage.targets.unavailable"

DETAIL = (
    "Reported as a share of the total, never as a total on its own: a total confounds where "
    "the damage landed with how long the fight ran and how the raid was geared. This states a "
    "difference in where the damage went, and makes no claim that it belonged anywhere else."
)
"""Design 6.2's own constraint, in the finding's own words: "totals confound target focus with
fight length and gear." The second sentence names a claim only to refuse it, which master
design 5.5 permits -- the same way `compare_mechanics` names and refuses "could have been
prevented" rather than leaving the refusal unsaid.

The refusal is written without the modal "should have".
`test_no_finding_this_axis_emits_claims_a_player_should_have_done_anything` scans every
sentence this axis emits for that phrase, and to a substring match a refusal and an
assertion are the same four words."""


def _unavailable(our_name: str, detail: str) -> Finding:
    return Finding(
        id=UNAVAILABLE_ID,
        title=f"No target-focus comparison is available for {our_name}",
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
    )


def _boss_share(rows: tuple[TargetRow, ...]) -> tuple[float, str] | None:
    """The percentage of `rows`' combined total that landed on the boss row, and its name.

    `None` where `rows` carries no boss row, or where the combined total is zero or negative
    and there is nothing to divide by.
    """
    total = sum(row.total for row in rows)
    if total <= 0:
        return None
    boss = next((row for row in rows if row.is_boss), None)
    if boss is None:
        return None
    return boss.total / total * 100, boss.name


def compare_targets(
    ours: tuple[TargetRow, ...],
    theirs: Sequence[tuple[TargetRow, ...]],
    our_name: str,
) -> list[Finding]:
    """Where the subject's damage went, boss against everything else, against the sample.

    Design 6.2: "A boss with one target produces one row and no finding." A fight with no add
    at all, or a `viewBy: Target` table that came back with a single row, has no split to
    compare -- `ours` shorter than two rows returns `compare.damage.targets.unavailable` rather
    than an empty list, so a real absence and a clean result never read alike.

    Every member of `theirs` is one reference kill's own per-target rows, scoped to its own
    subject exactly as `ours` is scoped to this one -- never a whole reference raid's table,
    which would compare one player's focus against a raid's. Below `MIN_SAMPLE_FOR_AGGREGATE`
    eligible references, the comparison states one reference rather than a statistic, through
    the same `too_few` wording every other axis in this codebase uses.

    Never states a total: `_boss_share` returns a percentage, and nothing here formats a
    `TargetRow.total` into a string. `DETAIL` quotes design 6.2's own reason why.
    """
    if len(ours) < 2:
        return [
            _unavailable(
                our_name,
                "This fight's damage-by-target table carried one target, so there is no split "
                "between the boss and everything else to compare.",
            )
        ]

    our_result = _boss_share(ours)
    if our_result is None:
        return [
            _unavailable(
                our_name,
                "This fight's damage-by-target table carried no boss row, so no share of "
                "damage sent to the boss can be stated.",
            )
        ]
    our_share, boss_name = our_result

    eligible = [share for member in theirs if (share := _boss_share(member)) is not None]
    if not eligible:
        return [
            _unavailable(
                our_name,
                "No reference in the sample carried a boss row, so no share of damage sent "
                "to the boss can be stated for the sample.",
            )
        ]

    used = eligible if len(eligible) >= MIN_SAMPLE_FOR_AGGREGATE else eligible[:1]
    their_shares = [share for share, _ in used]
    their_middle = median(their_shares)
    low, high = observed_range(their_shares)

    finding = Finding(
        id="compare.damage.targets",
        title=(
            f"{our_name} sent {our_share:.1f}% of their damage into {boss_name}, against "
            f"{their_middle:.1f}% for the sample"
        ),
        detail=DETAIL,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(
            f"ours {our_share:.1f}% into {boss_name}",
            f"sample {their_middle:.1f}%, range {low:.1f}% to {high:.1f}% over "
            f"{quantity(len(used), 'reference', 'references')}",
        ),
        facts=(
            FindingFact(label="This raid", value=f"{our_share:.1f}% into {boss_name}"),
            FindingFact(label="Sample", value=f"{their_middle:.1f}%"),
        ),
    )

    if len(eligible) < MIN_SAMPLE_FOR_AGGREGATE:
        finding = too_few([finding], len(eligible))[0]

    return [finding]
