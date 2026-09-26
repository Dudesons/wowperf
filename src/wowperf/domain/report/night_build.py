# ABOUTME: Turns a loaded night into the value the night page renders, one raid report a pull.
# ABOUTME: Grouping and delegation only -- no analyser is duplicated and none is invented here.

from collections.abc import Mapping, Sequence

from wowperf.domain.comparison.night_axis import parse_axis_not_drawn
from wowperf.domain.findings import Finding
from wowperf.domain.night import FailedPull, LoadedNight
from wowperf.domain.report.frame import plural
from wowperf.domain.report.ledger import ledger_row
from wowperf.domain.report.night_frame import build_night_header, night_subject
from wowperf.domain.report.night_model import (
    BossSection,
    NightProvenance,
    NightReport,
    PullSection,
)
from wowperf.domain.report.progression_build import build_progression_report
from wowperf.domain.report.raid_build import build_raid_report
from wowperf.domain.season import Consumables, Defensives, Externals, Roles, SelfResurrections

# The three tiers a pull can be drawn at, in cost order. Named here so the
# builder cannot spell one of them two ways, and asserted as bare strings in
# the tests rather than through these names: a test that imported them would
# agree with a typo instead of catching it.
NO_CARDS = "none"
TRIMMED = "trimmed"
DEEP = "deep"

WHAT_TRIMMING_DROPS = (
    "A trimmed card keeps what each player had at the moment of death, and drops the run-up "
    "timeline and the health curve. Those two are what `wowperf night --deep <fight>` buys "
    "back for a named pull, and what `wowperf raid --fight N` draws for one pull on its own."
)
"""What a trimmed card is, true of both trimmed branches and claimed by neither.

Split from the clause that says *which* cards are trimmed, because that clause
is the half that changes: an explanation appended to a universal does not
qualify it, and a page that opened by claiming every card was trimmed and named
the exception a sentence later would have told a reader something false about a
card on the very same page.
"""

MIN_PULLS_FOR_SUMMARY = 2
"""Below this many drawn pulls a boss gets no summary: there is nothing to compare."""

CARD_TIER_NONE = (
    "No death card was drawn on any pull: this night was read with death cards off, so the "
    "Deaths tab is empty because none was asked for rather than for want of a reading."
)


def _tier(fight_id: int, deep_fights: frozenset[int], *, death_cards: bool) -> str:
    """Which tier one pull is drawn at, decided per pull and never for the night.

    `death_cards` wins over `deep_fights` where both are given, and that is not
    a silent precedence: section 10 has the command refuse `--deep` and
    `--no-deaths` together, naming both, so a pull can only reach here under
    one of them.
    """
    if not death_cards:
        return NO_CARDS
    return DEEP if fight_id in deep_fights else TRIMMED


def _card_tier_method(deep_fights: frozenset[int], *, death_cards: bool) -> str:
    """What depth this run asked for, in one line, for a reader who did not type it.

    Read from the same two arguments the tiers themselves are read from, so
    the sentence and the pages it describes cannot disagree.

    A line rather than a `tier` field on the report: on a `--deep` night the
    tier is per pull by design, and one field would be false of every pull the
    flag did not name. This states what was asked for, which is the half a
    reader cannot recover from the page itself -- least of all on a night where
    every pull failed and there is no card to look at.

    The named fights are sorted, because a frozenset has no order and a page
    whose prose reshuffles between two builds of the same night is a page
    nobody can diff. They are stated as named rather than as drawn: a named
    fight whose streams failed carries no card at all, and its own Provenance
    line above already says so.

    Which cards are trimmed is claimed in the opening clause and qualified
    there, never by a sentence appended after it. "Every death card on this
    page is trimmed" is false the moment `--deep` names one, and an exception
    stated a sentence later does not retract it for the reader who stopped at
    the full stop.
    """
    if not death_cards:
        return CARD_TIER_NONE
    if not deep_fights:
        return (
            "Every death card on this page is trimmed, and no pull was named for a "
            f"deeper read. {WHAT_TRIMMING_DROPS}"
        )
    named = sorted(deep_fights)
    ids = ", ".join(str(one) for one in named)
    return (
        "Every death card on this page is trimmed except on the "
        f"{plural(len(named), 'fight')} `--deep` named: {ids}. {WHAT_TRIMMING_DROPS}"
    )


def _withheld(failed_pulls: Sequence[FailedPull]) -> tuple[str, ...]:
    """One line per pull the night could not load, naming the fight and the reason.

    Built from the records the report carries rather than beside them, so the
    list and the paragraph cannot name different pulls.
    """
    return tuple(
        f"Fight {one.fight_id} is not on this page: {one.reason}" for one in failed_pulls
    )


def build_night_report(
    loaded: LoadedNight,
    findings_by_fight: Mapping[int, Sequence[Finding]],
    fetched_at: str,
    defensives: Defensives,
    consumables: Consumables,
    roles: Roles,
    *,
    deep_fights: frozenset[int],
    death_cards: bool,
    findings_by_boss: Mapping[int, Sequence[Finding]],
    externals: Externals = Externals(),
    self_resurrections: SelfResurrections = SelfResurrections(),
) -> NightReport:
    """Every boss and every pull, each pull built by the raid builder it reuses whole.

    Section 8: the reuse is structural. A `LoadedProgression.loaded` entry is a
    `LoadedEncounter`, which is exactly `build_raid_report`'s first argument, so
    this function groups and delegates and computes no judgement of its own. A
    step here that needed a new analyser would belong in a later spec.

    `fetched_at` is a parameter rather than a clock read, because the domain
    performs no I/O and the same inputs must render the same page.

    Two of `build_raid_report`'s arguments a night has no obvious source for are
    decided here. `subject` is the report owner, resolved per pull by
    `night_subject`, since a night page names no player. `compared_slugs` is
    `None`: the raid builder reads that as "no comparison was asked for at all",
    which is true of every pull on this page, where an empty frozenset would
    claim one ran and matched nobody. `reference_records` is left at its empty
    default for the same reason -- this command fetches no reference run, and a
    record of one would be an invention rather than a reading.

    Walks `loaded.loaded` rather than `loaded.night.bosses`: the two run
    parallel by `LoadedNight`'s own contract, and each `LoadedProgression`
    already carries the boss it belongs to, so there is no index to keep in
    step. Pulls come from `attempts_with_events`, which is pull order whatever
    order the streams arrived in.

    `findings_by_boss` is the per-boss findings the progression analyser
    produced, keyed by encounter id -- the same mapping the command writes to
    the JSON. A boss with fewer than `MIN_PULLS_FOR_SUMMARY` drawn pulls gets no
    summary, so its findings are never read even when present. A boss missing
    from the mapping entirely draws a summary with no findings, the same
    `.get(..., ())` fallback `findings_by_fight` relies on above.
    """
    bosses: list[BossSection] = []
    for boss in loaded.loaded:
        drawn = boss.attempts_with_events
        pulls: list[PullSection] = []
        for attempt in drawn:
            fight_id = attempt.encounter.fight_id
            tier = _tier(fight_id, deep_fights, death_cards=death_cards)
            pulls.append(
                PullSection(
                    report=build_raid_report(
                        attempt,
                        findings_by_fight.get(fight_id, ()),
                        night_subject(attempt.encounter),
                        None,
                        fetched_at,
                        defensives,
                        consumables,
                        roles,
                        externals,
                        self_resurrections,
                        trimmed=tier == TRIMMED,
                        death_cards=tier != NO_CARDS,
                    ),
                    tier=tier,
                )
            )
        summary = (
            build_progression_report(
                boss, findings_by_boss.get(boss.progression.encounter_id, ()), fetched_at
            )
            if len(drawn) >= MIN_PULLS_FOR_SUMMARY
            else None
        )
        bosses.append(
            BossSection(
                boss_name=boss.progression.boss_name, pulls=tuple(pulls), summary=summary
            )
        )

    # Stated once for the page rather than on every pull's tab: the axis is
    # absent because this command never draws one, which is a fact about the
    # command and not about any pull -- so it holds even on a night where no
    # pull loaded at all.
    not_drawn = ledger_row(parse_axis_not_drawn(), {})

    return NightReport(
        header=build_night_header(loaded),
        bosses=tuple(bosses),
        total_pulls=sum(len(boss.pulls) for boss in bosses),
        failed_pulls=loaded.failed_pulls,
        observations=(not_drawn,),
        provenance=NightProvenance(
            fetched_at=fetched_at,
            withheld=_withheld(loaded.failed_pulls),
            methods=(_card_tier_method(deep_fights, death_cards=death_cards),),
        ),
    )
