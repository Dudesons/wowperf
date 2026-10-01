# ABOUTME: The findings one boss earns on the night page's summary, read from its pulls together.
# ABOUTME: Progression's own findings, plus what only a night holding every pull's casts can add.

from collections.abc import Mapping, Sequence

from wowperf.domain.analysis.defensives import repeat_defensives_up
from wowperf.domain.analysis.night_rollups import analyse_night_rollups
from wowperf.domain.analysis.progression_service import analyse_progression
from wowperf.domain.comparison.pace import PaceSample
from wowperf.domain.comparison.pace_night import analyse_night_pace
from wowperf.domain.findings import Finding
from wowperf.domain.progression import LoadedProgression
from wowperf.domain.season import Defensives


def analyse_night_boss(
    series: LoadedProgression,
    defensives: Defensives,
    *,
    death_cards: bool,
    pace: Mapping[int, PaceSample] | None = None,
    pull_findings: Mapping[int, Sequence[Finding]] | None = None,
    mechanics_compared: frozenset[int] = frozenset(),
) -> list[Finding]:
    """Every finding one boss's summary carries, in the order they are appended.

    `analyse_progression` first and unchanged: the standalone progression page
    and a night summary draw the same progression findings. The pooled
    defensives finding follows only with `death_cards` on -- the tier that
    fetches every pull's casts. Without it there is nothing to judge, and
    asking anyway would put a silence on the page that reads like a check that
    ran and found nothing. The pace line reads each wipe pull's own sample, so
    it is only there on a night that fetched them; a kill's sample is handed
    in too, and the line leaves it out.

    The boss-level rollups come last and only with `pull_findings`: they count
    the pulls' own findings, so they can only be read once every pull has been
    analysed. `mechanics_compared` names the pulls whose mechanics sample had
    members, the denominator of what kept over-landing.
    """
    findings = analyse_progression(series)
    if death_cards:
        findings += repeat_defensives_up(series, defensives)
    if pace:
        findings += analyse_night_pace(series.attempts_with_events, pace)
    if pull_findings is not None:
        findings += analyse_night_rollups(
            series.attempts_with_events, pull_findings, mechanics_compared
        )
    return findings
