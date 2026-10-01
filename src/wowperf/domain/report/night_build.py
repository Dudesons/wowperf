# ABOUTME: Turns a loaded night into the value the night page renders, one raid report a pull.
# ABOUTME: Grouping and delegation only -- no analyser is duplicated and none is invented here.

from collections.abc import Mapping, Sequence

from wowperf.domain.comparison.night_axis import parse_axis_not_drawn
from wowperf.domain.comparison.pace import PaceSample
from wowperf.domain.findings import Finding, fight_ranges
from wowperf.domain.night import FailedPull, LoadedNight
from wowperf.domain.report.frame import plural
from wowperf.domain.report.ledger import ledger_row
from wowperf.domain.report.model import ReferenceRecord
from wowperf.domain.report.night_frame import build_night_header, night_subject
from wowperf.domain.report.night_model import (
    BossSection,
    NightProvenance,
    NightReport,
    PullSection,
)
from wowperf.domain.report.progression_build import build_progression_report
from wowperf.domain.report.raid_build import build_raid_report
from wowperf.domain.season import (
    Consumables,
    Defensives,
    Externals,
    Roles,
    SelfResurrections,
    ThroughputCooldowns,
)

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

MIN_PULLS_FOR_SUMMARY = 1
"""Below this many drawn pulls a boss gets no summary: with none there is nothing to read."""

CARD_TIER_NONE = (
    "No death card was drawn on any pull: this night was read with death cards off, so the "
    "Deaths tab is empty because none was asked for rather than for want of a reading. No "
    "boss summary says which defensives were up at a death either, for the same reason."
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
    """One line per reason a pull is missing from the page, naming every pull it kept out.

    Built from the records the report carries rather than beside them, so the
    list and the paragraph cannot name different pulls. Reasons keep the order
    they were first seen in.
    """
    by_reason: dict[str, list[int]] = {}
    for one in failed_pulls:
        by_reason.setdefault(one.reason, []).append(one.fight_id)
    return tuple(
        f"{fight_ranges(ids)} {'is' if len(ids) == 1 else 'are'} not on this page: {reason}"
        for reason, ids in by_reason.items()
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
    pace_by_fight: Mapping[int, PaceSample] | None = None,
    records_by_fight: Mapping[int, tuple[ReferenceRecord, ...]] | None = None,
    throughput: ThroughputCooldowns | None = None,
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
    claim one ran and matched nobody -- no parse comparison ever runs on a
    night. `reference_records` is each pull's own records from
    `records_by_fight`, the same reference kills `raid --fight N` would draw
    for that pull, read back from the one-day reference cache the command
    shares across every pull at one boss and size.

    `parse_stated_elsewhere` is set for every pull. The parse axis's absence
    is the night's, not any pull's: `compare.parse.not_drawn` states it once
    for the page, worded for whether the night was compared against the
    reference kills. So no pull's card says it, no pull's Provenance repeats
    it, and no open Damage tab notes it. A pull whose Damage tab has no row
    points instead: a pull handed a pace sample says `PULL_DAMAGE_NOT_DRAWN`,
    naming the night's finding and its own Provenance, where its pace notice
    is; a pull handed none -- every pull of a `--no-compare` night -- says
    `PULL_DAMAGE_NOTHING_COMPARED`, naming the night's finding alone, since its
    Provenance carries no pace line to point to.

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

    `pace_by_fight` and `records_by_fight` are each pull's own `PaceSample`
    and reference records -- the mechanics sample's and the pace
    comparison's -- keyed by fight id and read as empty when the whole
    mapping is `None`: a night read with `--no-compare`, or a fight neither
    mapping names, falls back to no sample and no records the same way
    `findings_by_fight` falls back above.
    Each boss summary is handed `findings_by_fight` and `pace_by_fight` whole,
    so its attempt rows read each pull's own verdict and pace by fight id.
    `NightProvenance.references` is filled by walking every pull's own records
    in pull order, keeping the first copy seen of each `url`: a later pull's
    copy is the same reference kill read back from cache.
    `NightProvenance.withheld` holds one line per reason a pull failed to
    load, naming every pull that reason kept out. A withheld pace notice is
    stated once, in its own pull's Provenance, and is not repeated here.

    `throughput`, threaded straight into every pull's `build_raid_report`
    alongside `roles`, draws the Healers group on every pull's death cards;
    left at `None`, the default, no pull's cards carry one.
    """
    bosses: list[BossSection] = []
    reference_records_seen: dict[str, ReferenceRecord] = {}
    for boss in loaded.loaded:
        drawn = boss.attempts_with_events
        pulls: list[PullSection] = []
        for attempt in drawn:
            fight_id = attempt.encounter.fight_id
            tier = _tier(fight_id, deep_fights, death_cards=death_cards)
            pull_findings = findings_by_fight.get(fight_id, ())
            pull_records = (records_by_fight or {}).get(fight_id, ())
            for record in pull_records:
                reference_records_seen.setdefault(record.url, record)
            pace_sample = (pace_by_fight or {}).get(fight_id)
            pulls.append(
                PullSection(
                    report=build_raid_report(
                        attempt,
                        pull_findings,
                        night_subject(attempt.encounter),
                        None,
                        fetched_at,
                        defensives,
                        consumables,
                        roles,
                        externals,
                        self_resurrections,
                        reference_records=pull_records,
                        trimmed=tier == TRIMMED,
                        death_cards=tier != NO_CARDS,
                        pace=pace_sample,
                        parse_stated_elsewhere=True,
                        throughput=throughput,
                    ),
                    tier=tier,
                )
            )
        summary = (
            build_progression_report(
                boss,
                findings_by_boss.get(boss.progression.encounter_id, ()),
                fetched_at,
                pull_findings=findings_by_fight,
                pace=pace_by_fight,
            )
            if len(drawn) >= MIN_PULLS_FOR_SUMMARY
            else None
        )
        bosses.append(
            BossSection(
                boss_name=boss.progression.boss_name,
                pulls=tuple(pulls),
                summary=summary,
                summary_label=(
                    f"Summary: {summary.provenance.attempts_deepened} "
                    f"{plural(summary.provenance.attempts_deepened, 'pull')}"
                    if summary
                    else ""
                ),
            )
        )

    # Stated once for the page rather than on every pull's tab: the axis is
    # absent because this command never draws one, which is a fact about the
    # command and not about any pull -- so it holds even on a night where no
    # pull loaded at all. Its wording turns on whether the night was handed any
    # pace sample: one handed any asked the execution leaderboard for reference
    # kills, even if every pull then withheld, and may say only that no parse
    # comparison is drawn; a `--no-compare` night was handed none.
    not_drawn = ledger_row(parse_axis_not_drawn(compared=bool(pace_by_fight)), {})

    return NightReport(
        header=build_night_header(loaded),
        bosses=tuple(bosses),
        total_pulls=sum(len(boss.pulls) for boss in bosses),
        failed_pulls=loaded.failed_pulls,
        observations=(not_drawn,),
        provenance=NightProvenance(
            fetched_at=fetched_at,
            references=tuple(reference_records_seen.values()),
            withheld=_withheld(loaded.failed_pulls),
            methods=(_card_tier_method(deep_fights, death_cards=death_cards),),
        ),
    )
