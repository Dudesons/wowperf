# ABOUTME: Turns a loaded boss fight and its findings into the value the raid template renders.
# ABOUTME: A sibling of build.py: no route and no timeline, and a Damage tab a wipe withholds.

from collections import Counter
from collections.abc import Mapping, Sequence

from wowperf.domain.analysis.attempt_shape import WITHHELD_ID
from wowperf.domain.analysis.deaths import chains
from wowperf.domain.analysis.defensives import CEILING_WITHHELD_ID
from wowperf.domain.analysis.progression_repeats import collapse_seconds, first_roster_death
from wowperf.domain.comparison.kill_time import KILL_PREFIX
from wowperf.domain.comparison.night_axis import (
    PULL_DAMAGE_NOT_DRAWN,
    PULL_DAMAGE_NOTHING_COMPARED,
)
from wowperf.domain.comparison.pace import (
    PACE_ID,
    PACE_PREFIX,
    UNAVAILABLE_ID,
    PaceSample,
    pace_reading,
)
from wowperf.domain.comparison.pace_curve import PaceState
from wowperf.domain.comparison.pace_player import PLAYER_PACE_PREFIX, SCOPE_LINE
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Finding
from wowperf.domain.model import Player
from wowperf.domain.report.alive_chart import build_alive_chart
from wowperf.domain.report.build import _check_unique_finding_ids, ceiling_withheld_line
from wowperf.domain.report.deaths import HEALTH_METHOD, NO_CARDS_ASKED, build_deaths
from wowperf.domain.report.finding_tooltip import tooltips_by_finding_id
from wowperf.domain.report.frame import (
    NO_COMPARISON_RAN,
    PARSE_UNAVAILABLE_ID,
    finding_by_id,
    format_seconds,
)
from wowperf.domain.report.ledger import (
    build_observations,
    build_summary_pointers,
    ledger_row,
    place_rows,
    placed_finding_ids,
)
from wowperf.domain.report.model import (
    LedgerRow,
    Provenance,
    ReferenceRecord,
    Section,
    SectionState,
    Tooltip,
)
from wowperf.domain.report.pace_chart import build_pace_chart
from wowperf.domain.report.raid_frame import build_raid_header
from wowperf.domain.report.raid_grid import build_raid_grid
from wowperf.domain.report.raid_ledger import RAID_DECOMPOSITION_IDS, RAID_PLACEMENTS
from wowperf.domain.report.raid_model import RaidReport, WipeOpening
from wowperf.domain.report.raid_players import build_raid_players
from wowperf.domain.season import (
    Consumables,
    Defensives,
    Externals,
    Roles,
    SelfResurrections,
    ThroughputCooldowns,
)

VERDICT_ID = "wipe.cause"
"""`classify_attempt`'s id for the verdict it reaches, when it reaches one.

Matched on the whole id, like `WITHHELD_ID` beside it: `wipe.cause` is never
re-minted per raider, so a prefix match would buy nothing a whole-id match
does not already have, and would silently widen to any future `wipe.cause.*`
sibling that is not the verdict itself.
"""

FIRST_DEATH = "{name} ({spec} {class_name}) died first, to {ability}, at {clock}"
HELD = "The raid held {clock} after the first death"
NOBODY_DIED = "Nobody died in this attempt"
PACE_LEADS = {
    PaceState.BEHIND: "Ended behind the reference kills' pace.",
    PaceState.ON_PACE: "Ended on the reference kills' pace.",
    PaceState.AHEAD: "Ended ahead of the reference kills' pace.",
}
"""What a wipe's Summary says above its pointer to the pace card, by the state it ended in."""


def _deaths_finding_id(loaded: LoadedEncounter, death: Death) -> str | None:
    """The id `analyse_deaths` gives the group of deaths that holds `death`.

    Numbered the way `analyse_deaths` numbers them: each kind, chain or
    single, counts from 0 in time order. The group is looked for rather than
    taken first, because the analyser numbers every death the log holds, a
    pet's or an unidentified actor's too, and one of those dying alone before
    the first roster death would make the first group its card.
    """
    ranks: Counter[str] = Counter()
    for group in chains(loaded.deaths):
        kind = "chain" if len(group) > 1 else "single"
        if death in group:
            return f"deaths.{kind}.{ranks[kind]}"
        ranks[kind] += 1
    return None


def _wipe_opening(
    loaded: LoadedEncounter,
    findings: Sequence[Finding],
    titles_by_id: dict[str, str],
    tooltips: Mapping[str, Tooltip],
) -> WipeOpening:
    """Who died first, to what and when, how long the raid held, and that death's card.

    The first death is `first_roster_death`'s and the hold is
    `collapse_seconds`', the two the progression analysers read, so this
    Summary and the night's repeats never name different deaths. `chain` is
    None when the card it would point at is not among `findings`: a pointer
    to a card the page does not draw is worse than none.
    """
    death = first_roster_death(loaded)
    if death is None:
        return WipeOpening(first_death=NOBODY_DIED, line=f"{NOBODY_DIED}.")
    player = next(one for one in loaded.players if one.actor_id == death.actor_id)
    first_death = FIRST_DEATH.format(
        name=player.name, spec=player.spec, class_name=player.class_name,
        ability=death.killing_blow,
        clock=format_seconds((death.timestamp_ms - loaded.encounter.start_ms) / 1000),
    )
    held = HELD.format(clock=format_seconds(collapse_seconds(loaded)))
    finding_id = _deaths_finding_id(loaded, death)
    card = finding_by_id(findings, finding_id) if finding_id else None
    return WipeOpening(
        first_death=first_death,
        line=f"{first_death}. {held}.",
        held=held,
        chain=ledger_row(card, titles_by_id, tooltips) if card else None,
    )


def _damage_section(
    findings: Sequence[Finding],
    rows: tuple[LedgerRow, ...],
    *,
    fallback: str = NO_COMPARISON_RAN,
) -> Section:
    """The Damage tab: present when it has rows, withheld with the comparison's own reason.

    Matched by prefix and never by id. `compare_parse_axis` mints
    `compare.parse.unavailable` and `analyse_encounter` re-mints it as
    `compare.parse.unavailable.<slug>`, one per raider, so an equality test
    against the bare id matches nothing on any raid page: a wipe would then be
    withheld under "no reference was fetched", which is false of an
    analysis that fetched one and was told the boss lived. Every consumer of
    these ids matches by prefix, and a prefix survives a suffix.

    Gated on the rows rather than on that finding's absence, because the two
    disagree on a kill where one raider's leaderboard answered and another's
    did not: that page has damage rows to show, and withholding the whole tab
    would hide one raider's measured figures because of another raider's
    missing sample.

    `section_for` is not reused for the same reason: its reason is resolved
    through `finding_by_id`, an exact match, which is the half that cannot
    hold here.

    `fallback` is what the tab states when neither a row nor a
    `compare.parse.unavailable` finding is found. `NO_COMPARISON_RAN`, the
    default, is what that absence means on every page but the night's, whose
    pulls point to where the night states its reasons instead.
    """
    if rows:
        return Section(state=SectionState.PRESENT)
    unavailable = next(
        (finding for finding in findings if finding.id.startswith(PARSE_UNAVAILABLE_ID)), None
    )
    return Section(
        state=SectionState.WITHHELD,
        reason=unavailable.detail if unavailable else fallback,
    )


def build_raid_report(
    loaded: LoadedEncounter,
    findings: Sequence[Finding],
    subject: Player,
    compared_slugs: frozenset[str] | None,
    fetched_at: str,
    defensives: Defensives,
    consumables: Consumables,
    roles: Roles,
    externals: Externals = Externals(),
    self_resurrections: SelfResurrections = SelfResurrections(),
    reference_records: tuple[ReferenceRecord, ...] = (),
    *,
    trimmed: bool = False,
    death_cards: bool = True,
    pace: PaceSample | None = None,
    parse_stated_elsewhere: bool = False,
    throughput: ThroughputCooldowns | None = None,
) -> RaidReport:
    """Everything the raid page shows, decided here so the template decides nothing.

    `build_report`'s shape with the keystone half absent. `fetched_at` is a
    parameter rather than a clock read, because the domain performs no I/O and
    the same inputs must render the same report; `defensives`, `consumables`,
    `roles`, `externals` and `self_resurrections` are data files an adapter
    loads for the same reason. `subject` is the raider who was asked about and
    decides which card the Players tab opens on, nothing else: which card a
    comparison row reaches is decided by the slug the finding carries.
    `compared_slugs` is who a comparison was asked for, and `None` means none
    was asked for at all.

    `trimmed` and `death_cards` are the night command's tier ladder for the
    Deaths tab, not a raid-page concern: a raid fight always wants full cards,
    which is why both default to what the raid page has always rendered.
    `death_cards=False` skips `build_deaths` entirely rather than calling it
    and discarding the result, so `deaths` comes back `()` without the work
    ever being done. `trimmed` is threaded straight through to `build_deaths`
    when cards are built at all.

    Three of `build_report`'s parameters are deliberately absent, and each
    absence is a fact about a raid rather than an omission. There is no
    `narrative`: section 11 does not give `raid` that flag. There is no
    `speed`: a boss fight has no route to compare, which is why this page has
    no Route and tempo tab either. And there are no `comparison_measures`: a
    raid card carries no comparison tables, and the measures themselves are
    computed from a `LoadedRun`, which this path never holds. A parameter
    accepted and ignored is a lie the type system helps tell.

    `throughput` draws the Healers group on every death card, together with
    `roles`: left at `None`, the default, no card carries one -- a group built
    from `roles` alone would say a group healing cooldown the data file does
    list was never pressed, when it was simply never read.

    `parse_stated_elsewhere` is for a caller that states the parse
    comparison's absence once for a page holding many pulls: the night page,
    whose `compare.parse.not_drawn` finding says it for every pull at once.
    True, every card is withheld with no reason of its own, an open Damage
    tab carries no parse note, the Damage tab's fallback points to where the
    reasons are rather than restating them -- `PULL_DAMAGE_NOT_DRAWN` when
    `pace` was handed, `PULL_DAMAGE_NOTHING_COMPARED` when it was not -- and
    the Provenance carries neither a "Damage against other kills" nor a
    "Spell and talent comparison" line.
    False, the default, is the page `raid` draws, so `raid` itself passes
    nothing here.
    """
    _check_unique_finding_ids(findings)

    # The attempt verdict's withheld notice is disclosed in Provenance and
    # nowhere else, so it is taken out before anything below can place it.
    # `severity.SEVERITY_BY_FAMILY` ranks the `wipe` family first, because a
    # verdict frames every row under it; a notice saying there is no verdict
    # inherits that rank, and would take the Summary's headline to say
    # nothing. Matched on the whole id rather than a prefix: `wipe.cause` is
    # the verdict itself and belongs on the page. It is read out here rather
    # than stripped, so it can still reach `titles_by_id` and `tooltips`
    # below; `placed_ids`, further down, keeps it from also falling through
    # `build_observations`'s catch-all once `report.verdict` has claimed it.
    verdict_notices = [one for one in findings if one.id == WITHHELD_ID]
    verdict_finding = next((one for one in findings if one.id == VERDICT_ID), None)
    findings = [one for one in findings if one.id != WITHHELD_ID]

    # The defensive-ceiling withheld notice is disclosed in Provenance and
    # nowhere else, exactly like the attempt verdict's own withheld notice
    # above: left among `findings` it would match `RAID_PLACEMENTS`' bare
    # `defensives.` prefix and rank on the Players tab beside real per-ability
    # judgements, where "I could not judge this" would read as one of them.
    ceiling_notices = [one for one in findings if one.id == CEILING_WITHHELD_ID]
    findings = [one for one in findings if one.id != CEILING_WITHHELD_ID]

    # The damage-pace notice is disclosed in Provenance and nowhere else, for
    # the same reason as the two notices above: left among `findings` it would
    # match `RAID_PLACEMENTS`' `compare.pace.` prefix and land on the Damage
    # tab beside a real reading, where "nothing could be compared" would read
    # as one.
    pace_notices = [one for one in findings if one.id == UNAVAILABLE_ID]
    findings = [one for one in findings if one.id != UNAVAILABLE_ID]

    titles_by_id = {finding.id: finding.title for finding in findings}
    # Built once, here, because this is where `loaded`, the per-actor aura
    # tables and the defensives data file are all already in hand. Every row
    # builder below looks a panel up and none of them computes one.
    tooltips = tooltips_by_finding_id(findings, loaded, defensives)
    verdict = (
        ledger_row(verdict_finding, titles_by_id, tooltips) if verdict_finding else None
    )
    # A wipe is not a race, so its Summary ranks nothing in seconds: with no
    # decomposition, `deaths.total` falls through to the Deaths tab with the
    # death costs beside it, and the Summary opens on how the wipe started.
    wiped = not loaded.encounter.kill
    ledger_decomposition = () if wiped else tuple(
        ledger_row(finding, titles_by_id, tooltips)
        for finding in findings
        if finding.seconds_lost is not None and finding.id in RAID_DECOMPOSITION_IDS
    )
    decomposition_ids = {row.finding_id for row in ledger_decomposition}
    opening = _wipe_opening(loaded, findings, titles_by_id, tooltips) if wiped else None
    # A per-player pace reading lands on that raider's card via `build_raid_players`'
    # `pace_rows`, never here: `RAID_PLACEMENTS`' `("compare.pace.", "damage_rows")`
    # matches by prefix, so `compare.pace.player.*` would otherwise also land on
    # the Damage tab beside the fight-wide reading it is not. `build_raid_players`,
    # below, is handed the unfiltered `findings` and places these.
    findings_for_tabs = [
        finding for finding in findings if not finding.id.startswith(PLAYER_PACE_PREFIX)
    ]
    placed_rows = place_rows(
        findings_for_tabs, titles_by_id, decomposition_ids, tooltips, placements=RAID_PLACEMENTS
    )

    # Pace rows and the kill-time row would otherwise make the Damage tab
    # present on a wipe, or on a page whose parse axis was withheld or never
    # drawn, and turn the parse comparison's own withheld reason -- stated once
    # below for the whole fight -- into a claim that pace or kill time was
    # withheld for the same reason, which it never is: each is withheld
    # independently. `parse_damage` is read on the rows the parse comparison
    # itself placed, with the pace and kill-time rows filtered back out, so the
    # Provenance line and the per-card silence below both stay about the
    # parse comparison alone; `damage`, the tab's own section, opens whenever
    # any comparison left a row to show.
    #
    # Read before the cards are built, because what the Damage tab states is
    # what every card that would say the same thing leaves unsaid.
    parse_rows = tuple(
        row
        for row in placed_rows["damage_rows"]
        if not row.finding_id.startswith((PACE_PREFIX, KILL_PREFIX))
    )
    # A night pull's fallback points to where the night states its reasons. A
    # pull handed a pace sample carries its pace notice in its own Provenance,
    # and the sentence says so; a pull handed none carries no pace line at all,
    # so its sentence points to the night's finding alone.
    parse_damage = _damage_section(
        findings, parse_rows,
        fallback=(
            NO_COMPARISON_RAN if not parse_stated_elsewhere
            else PULL_DAMAGE_NOT_DRAWN if pace is not None
            else PULL_DAMAGE_NOTHING_COMPARED
        ),
    )
    damage = (
        Section(state=SectionState.PRESENT) if placed_rows["damage_rows"] else parse_damage
    )
    # A tab that pace or kill-time rows keep open never prints its withheld
    # paragraph, so the parse comparison's own withheld reason is its note
    # instead: on a raid wipe that draws a pace row, the tab is still where the
    # boss-lived reason is said, once. Empty wherever the parse comparison drew
    # rows (`parse_damage.reason` is "" then), wherever the tab is withheld (its
    # reason is the same sentence, already printed), and on a page that states
    # the parse axis's absence once for every pull.
    damage_note = (
        parse_damage.reason
        if damage.state is SectionState.PRESENT and not parse_stated_elsewhere
        else ""
    )

    # Said once for the whole fight, never once per raider. A wipe withholds
    # every raider's comparison for the same reason -- the boss lived, which is
    # a fact about the attempt and not about any of them -- and the Damage tab
    # prints it, as its withheld reason or as its note, so restating it on every
    # card would print the same paragraph twice per raider on a twenty-player
    # page: as the card's withheld line and as the card's own row.
    #
    # `build_report` does restate it per card, and this is the one place the
    # two siblings deliberately differ: the rule was always "say it once when
    # the reason is about the whole fight, per card when it is about that
    # card", and a keystone roster of five made the repetition read as emphasis
    # rather than as the bug it is at twenty. Do not fix this back.
    #
    # A raider whose reason differs is untouched: that reason is about them,
    # and the fight-wide statement does not cover it, so it stays on their card
    # and gets its own Provenance line below.
    #
    # What silences a card is exactly what the tab prints: its withheld reason,
    # or its note. A tab open on the parse comparison's own rows prints neither
    # and silences nothing -- which is what keeps a kill where one raider's
    # leaderboard answered from dropping another raider's own reason.
    stated_for_the_whole_fight = damage.reason or damage_note
    players = build_raid_players(
        loaded, findings, subject, compared_slugs, titles_by_id, tooltips,
        parse_withheld="" if parse_stated_elsewhere else None,
        stated_once=stated_for_the_whole_fight,
    )
    grid = build_raid_grid(loaded.players, loaded.damage_taken, roles, findings)
    # `Death.timestamp_ms` and `Resurrection.timestamp_ms` sit on the report's
    # own clock -- the one `Encounter.start_ms` sits on too, per
    # `deaths.py::_when`'s identical subtraction -- while `build_alive_chart`'s
    # x axis expects an elapsed clock starting at zero, the clock its own
    # tests are written against. Passing the raw timestamps through would
    # collapse every event onto the chart's right edge on any fight that does
    # not start at report time zero, which no real fight does.
    fight_start_ms = loaded.encounter.start_ms
    alive_chart = build_alive_chart(
        loaded.encounter.size or len(loaded.players),
        tuple(
            death.model_copy(
                update={"timestamp_ms": max(death.timestamp_ms - fight_start_ms, 0)}
            )
            for death in loaded.deaths
        ),
        tuple(
            rez.model_copy(update={"timestamp_ms": max(rez.timestamp_ms - fight_start_ms, 0)})
            for rez in loaded.resurrections
        ),
        duration_ms=loaded.encounter.end_ms - fight_start_ms,
        boss_percentage=loaded.encounter.boss_percentage,
    )

    summary_pointers = () if wiped else build_summary_pointers(
        findings, titles_by_id, decomposition_ids, tooltips
    )
    placed_ids = placed_finding_ids(ledger_decomposition, placed_rows, players)
    # `report.verdict` claims `wipe.cause` on its own, outside every field
    # `placed_finding_ids` reads back from -- no `RAID_PLACEMENTS` prefix
    # matches it, and it is left in `findings` rather than stripped, so
    # without this it would still fall through to `build_observations`'s
    # catch-all and draw the same finding a second time under "Other findings".
    if verdict_finding:
        placed_ids.add(verdict_finding.id)
    # The per-raider parse notices the Damage tab prints for the whole fight,
    # as its withheld reason or as its note, are claimed by that tab, for the
    # same reason: `build_raid_players` leaves
    # them off every card, so no field reads them back, and the catch-all would
    # otherwise draw the paragraph once per raider under "Other findings".
    placed_ids |= {
        finding.id
        for finding in findings
        if finding.id.startswith(PARSE_UNAVAILABLE_ID)
        and finding.detail == stated_for_the_whole_fight
    }

    withheld: list[str] = []
    for notice in verdict_notices:
        withheld.append(f"Why this attempt ended: {notice.detail}")
    for notice in ceiling_notices:
        withheld.append(ceiling_withheld_line(notice))
    for notice in pace_notices:
        withheld.append(f"Damage pace against other kills: {notice.detail}")
    # Stated once for the whole page rather than once per card, exactly like
    # the parse and pace lines beside it: every `compare.pace.player.*` row or
    # notice this fight carries shares the same scope, so the scope belongs
    # here and not repeated on every card it explains.
    if any(finding.id.startswith(PLAYER_PACE_PREFIX) for finding in findings):
        withheld.append(SCOPE_LINE)
    # A caller that states the parse axis's absence for the whole page states
    # it there, once, and this pull's Provenance does not repeat it.
    if parse_damage.state is SectionState.WITHHELD and not parse_stated_elsewhere:
        withheld.append(f"Damage against other kills: {parse_damage.reason}")

    # `--no-compare` fetched no reference at all, so the whole fight gets one
    # report-level line rather than one per card -- a line per raider here
    # would say a comparison for each of them was asked for and refused, when
    # none was ever asked for. When a comparison did run, a raider nobody
    # asked for is left off this list for the same reason: their comparison
    # was not withheld, it was not requested.
    #
    # A card withheld with no reason of its own is one whose reason the Damage
    # line above, or the page that states it once, already gave, so it gets
    # no line here either.
    if compared_slugs is None:
        if not parse_stated_elsewhere:
            withheld.append(f"Spell and talent comparison: {NO_COMPARISON_RAN}")
    else:
        for card in players:
            if (
                card.spell_and_talent.state is SectionState.WITHHELD
                and card.slug in compared_slugs
                and card.spell_and_talent.reason
            ):
                withheld.append(
                    f"Spell and talent comparison for {card.name}: {card.spell_and_talent.reason}"
                )

    # `death_cards=False` skips the call rather than building cards and
    # throwing them away: the tier exists so the work is never done.
    deaths = (
        build_deaths(loaded, defensives, consumables, externals, self_resurrections,
                     trimmed=trimmed,
                     roles=roles if throughput is not None else None,
                     throughput=throughput or ThroughputCooldowns())
        if death_cards
        else ()
    )
    methods = (HEALTH_METHOD,) if any(card.health_badge for card in deaths) else ()

    # `reading` is the one computation the pace finding's own sentence and the
    # chart's own coordinates both read, so the two can never disagree about
    # what "behind" meant. `pace_finding` gates the chart on the finding
    # actually being on the page rather than only on `pace` being given, so a
    # sample that could not be read (`pace_reading` returning `None`, e.g. one
    # with no reference kill) draws no orphaned chart with no card to badge it from.
    reading = pace_reading(loaded.encounter, pace) if pace is not None else None
    pace_finding = next((one for one in findings if one.id == PACE_ID), None)
    pace_chart = (
        build_pace_chart(reading, loaded.encounter.duration_seconds)
        if reading and pace_finding
        else None
    )
    # The Summary states a pace only on a wipe, and in whatever state it
    # ended: where a wipe stood against the kills is a question asked of every
    # wipe, not only a slow one. A kill is read against the execution
    # leaderboard's best kills, so ending behind them is the expected result;
    # its card and chart stay on the Damage tab, and its Summary belongs to
    # the kill-speed findings.
    pace_pointer = (
        ledger_row(pace_finding, titles_by_id, tooltips)
        if pace_finding and reading and reading.seconds and wiped
        else None
    )
    pace_lead = PACE_LEADS[reading.seconds[-1].state] if pace_pointer and reading else ""

    return RaidReport(
        header=build_raid_header(loaded.encounter),
        verdict=verdict,
        opening=opening,
        ledger_decomposition=ledger_decomposition,
        summary_pointers=summary_pointers,
        damage_rows=placed_rows["damage_rows"],
        damage=damage,
        damage_note=damage_note,
        mechanics_rows=placed_rows["mechanics_rows"],
        grid=grid,
        deaths=deaths,
        # Only this tier can leave the tab empty over a pull that had deaths,
        # so only this tier says why. Every other empty `deaths` is the log's
        # own answer, and the page states it as one.
        deaths_note="" if death_cards else NO_CARDS_ASKED,
        death_rows=placed_rows["death_rows"],
        interrupts=placed_rows["interrupts"],
        players=players,
        group_rows=placed_rows["group_rows"],
        observations=build_observations(findings, placed_ids, titles_by_id, tooltips),
        provenance=Provenance(
            report_code=loaded.encounter.report_code,
            fight_id=loaded.encounter.fight_id,
            fetched_at=fetched_at,
            references=reference_records,
            withheld=tuple(withheld),
            methods=methods,
        ),
        alive_chart=alive_chart,
        pace_chart=pace_chart,
        pace_pointer=pace_pointer,
        pace_lead=pace_lead,
    )
