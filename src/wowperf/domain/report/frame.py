# ABOUTME: The pieces every other part of the report needs: badges, formatted seconds, run bounds.
# ABOUTME: A section's state is decided here too, from the finding that explains an absence.

from collections.abc import Sequence

from wowperf.domain.comparison.sample import ParseSample, SpeedSample
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Run
from wowperf.domain.report.model import Badge, Header, Section, SectionState

SPEED_UNAVAILABLE_ID = "compare.speed.unavailable"
PARSE_UNAVAILABLE_ID = "compare.parse.unavailable"

# Said when `--no-compare` skipped the comparison entirely, so no finding explains the absence.
NO_COMPARISON_RAN = (
    "No reference run was fetched for this analysis, so there is nothing to compare against."
)

# Said when the comparison ran but this player was not among the ones asked for.
# Distinct from NO_COMPARISON_RAN, which says nothing was compared at all, and
# from a withheld section, which says the leaderboard had nothing to offer.
NOT_REQUESTED = (
    "No parse comparison was requested for this player. Name them with --player, "
    "or pass --all-players, to compare them against top parses of their specialisation."
)


def parse_unavailable_id(slug: str) -> str:
    """This player's own `compare.parse.unavailable`."""
    return f"{PARSE_UNAVAILABLE_ID}.{slug}"


def plural(count: int, singular: str) -> str:
    """`singular` unless `count` is not one. The one pluralisation rule this report needs."""
    return singular if count == 1 else f"{singular}s"


def badge_for(confidence: Confidence) -> Badge:
    """A word and a palette token. The word is what a reader without colour sees."""
    return Badge(label=str(confidence), tint=f"badge-{confidence}")


def format_seconds(seconds: float | None) -> str | None:
    """Minutes and seconds, or nothing at all.

    `None` stays `None` rather than becoming "0:00": a finding with no honest
    seconds figure must not read as one that cost no time.
    """
    if seconds is None:
        return None
    whole = int(round(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def finding_by_id(findings: Sequence[Finding], finding_id: str) -> Finding | None:
    return next((finding for finding in findings if finding.id == finding_id), None)


def sampled(sample: SpeedSample | ParseSample | None) -> bool:
    """Whether a comparison actually had a reference to run against.

    No sample at all (`--no-compare`) and a sample the leaderboard could not
    fill are the same thing to every section that gates on one.
    """
    return sample is not None and bool(sample.members)


def section_for(findings: Sequence[Finding], unavailable_id: str, present: bool) -> Section:
    """Present, or withheld with the reason the comparison itself gave.

    When no comparison ran at all there is no finding to quote, so the fallback
    states that plainly rather than implying a leaderboard came back empty.
    """
    if present:
        return Section(state=SectionState.PRESENT)
    finding = finding_by_id(findings, unavailable_id)
    return Section(
        state=SectionState.WITHHELD,
        reason=finding.detail if finding else NO_COMPARISON_RAN,
    )


def run_start_ms(run: Run) -> int:
    """The run's own clock origin: the earliest pull's start, or zero with no pulls.

    Shared by `run_seconds` and `_when` so a death's elapsed time and the
    run's span are measured from the same point and cannot drift apart.
    """
    return min((p.start_ms for p in run.pulls), default=0)


def run_seconds(run: Run) -> float:
    """Wall-clock span from the first pull's start to the last pull's end.

    Not `total_pull_seconds`, which sums pull durations and so omits every
    second spent travelling — the very time this report exists to show.
    """
    if not run.pulls:
        return 0.0
    return (max(p.end_ms for p in run.pulls) - run_start_ms(run)) / 1000


def build_header(loaded: LoadedRun) -> Header:
    run = loaded.run
    verb = "Timed" if run.keystone_bonus >= 1 else "Depleted"
    duration = format_seconds(run.keystone_time_seconds)
    assert duration is not None  # keystone_time_seconds is never None
    return Header(
        dungeon=run.dungeon_name,
        keystone_level=run.keystone_level,
        affixes=(
            run.affix_names
            if run.affix_names
            else tuple(str(affix_id) for affix_id in run.affix_ids)
        ),
        result=f"{verb} in {duration}",
    )
