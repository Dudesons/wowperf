# ABOUTME: One card per player, carrying the facts measured about them.
# ABOUTME: Damage reads against the group median: a log cannot say a hit was avoidable.

from collections import Counter
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from wowperf.domain.analysis.players import summarise_players
from wowperf.domain.analysis.roster import display_names
from wowperf.domain.comparison.boss_debuffs import Withheld
from wowperf.domain.comparison.measures import (
    AbilityRate,
    AuraRow,
    AuraUptime,
    BossCell,
    DebuffRow,
    DebuffTable,
    PlayerMeasures,
    StatShare,
    StretchCell,
    Verdict,
)
from wowperf.domain.comparison.pace_player import pair_label
from wowperf.domain.comparison.statistics import observed_range
from wowperf.domain.comparison.uptime import MIN_UPTIME_FRACTION
from wowperf.domain.findings import Finding, quantity
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.frame import (
    NO_COMPARISON_RAN,
    NOT_REQUESTED,
    finding_by_id,
    format_seconds,
    parse_unavailable_id,
    section_for,
    stated_elsewhere,
)
from wowperf.domain.report.ledger import NO_TOOLTIPS, collapse_repeated_details, ledger_row
from wowperf.domain.report.model import (
    ComparisonRow,
    ComparisonTable,
    PlayerCard,
    Section,
    SectionState,
    Tooltip,
)
from wowperf.domain.report.player_timeline import build_player_timeline
from wowperf.domain.season import Defensives, ThroughputCooldowns
from wowperf.domain.slug import player_slug

NO_MEASURES: Mapping[str, PlayerMeasures] = MappingProxyType({})
"""The default for every caller that has no comparison measures to offer: tests,
and any surface where a card is built without the comparison behind it."""

CLASS_COLOURS = (
    "DeathKnight", "DemonHunter", "Druid", "Evoker", "Hunter", "Mage", "Monk",
    "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Warrior",
)
"""Classes with a palette token. A class absent here still renders, in a neutral tone.

The colour never carries meaning alone: every card prints the class name too,
because several class colours are hard to tell apart and reports get
screenshotted and recompressed.
"""

COMPARISON_PREFIXES = (
    "compare.spells.",
    "compare.talents",
    "compare.uptime.",
    "compare.gear.",
    "compare.stats.",
    "compare.consumables.",
)
"""Finding families that belong on a player's card rather than in the ledger.

Which card is decided by the slug the finding carries, never by who the
subject is: a run can compare a teammate the reader did not name, and can
compare several players at once, so routing these to the subject's card would
put one player's rows under another player's name.
"""

VERDICT_LABELS = {
    Verdict.BELOW: "Below",
    Verdict.ABOVE: "Above",
    Verdict.LEVEL: "Level",
    Verdict.UNJUDGED: "Not judged",
    Verdict.BOSSES_ONLY: "Not judged",
}
"""Each branch, spelled for the reader of a column rather than for a stylesheet.

The table's own column holds these, because a tint carries no meaning alone:
several readers cannot separate two colours and every printed page separates
none of them. Only `unjudged` is spelled differently from the value it comes
from, being the one word here that is not ordinary English -- what the table
means by it is that the comparison declined to read anything into the figure
beside it, and a reader meeting the bare word would have no way to know that.
`bosses_only` reads the same, and is told apart on the page by the sentence
under the table that says why such a row is kept.
"""

DESCRIBED = "described"
"""The row class of a table that judges nothing.

No stylesheet rule tints it, so its figures read in the page's own ink: reach is
a description, and a verdict's tint on it would claim a judgement nobody made.
"""

DEBUFF_NOTE = (
    "Coverage: the share of the enemies' alive time this player's debuff was on them, summed "
    "over every enemy, so a long-lived mob weighs more than one that dies in seconds. "
    "Reached: the share of the enemies that carried it at least once. Low coverage with high "
    "reach means it was spread but not kept up; low coverage with low reach means it stayed "
    "on too few mobs. A trash mob's life runs from the first debuff anyone put on it to its "
    "death; adds that spawn during a boss fight count in Overall only."
)
"""What the two debuff tables measure, drawn once under the pair."""

KEPT_FOR_BOSSES = (
    f"Not judged: the references keep it on under {MIN_UPTIME_FRACTION:.0%} of the key's "
    "enemy-alive time, so the row is kept for its boss figure."
)
"""What a debuff row kept only for its Bosses figure is, drawn under the coverage table."""


def class_colour(class_name: str) -> str:
    return f"class-{class_name.lower()}" if class_name in CLASS_COLOURS else "class-unknown"


def slugs_by_actor(players: tuple[Player, ...]) -> dict[int, str]:
    """Every player's fragment id, keyed by actor id.

    Computed from the roster's own order, not from the order the cards are
    drawn in, so a player's fragment id does not move when a different subject
    reorders the cards -- a deep link into a report stays valid across a
    re-run that named someone else. Two display names can reduce to the same
    slug, so the roster index is appended to keep them apart.

    This function takes a roster because both a run and an encounter have one
    and neither is what it reads.

    This is the only place a player *fragment* id is minted. The comparison's
    finding ids and the card they belong to both read from here, and that
    agreement is what makes a `#finding-...` link land in the right sub-tab.
    The slugging itself is `wowperf.domain.slug`, which analysis shares:
    `defensives.*` mints its own ids and needs the same alphabet.
    """
    names = display_names(players)
    return {
        player.actor_id: f"{player_slug(names[player.actor_id])}-{index}"
        for index, player in enumerate(players)
    }


def _comparison_section(
    findings: Sequence[Finding],
    slug: str,
    compared_slugs: frozenset[str] | None,
    *,
    parse_withheld: str | None = None,
    stated_once: str = "",
) -> Section:
    """One player's comparison section, in whichever of three states it is in.

    A player nobody asked for is not the same as a player the leaderboard had
    nothing for, and neither is the same as a run that fetched no reference at
    all. Saying so is the whole job: a reader who cannot tell "not asked" from
    "not available" will read the second as the first and stop asking.

    `parse_withheld` stands in for `NO_COMPARISON_RAN` where no subject was
    handed (`compared_slugs` is `None`). The empty string is the night page's:
    its parse axis's absence is stated once for the whole page, so the card
    is withheld and says nothing.

    `stated_once` is a reason the page prints once for the whole fight -- the
    raid page's Damage tab, as its withheld reason or, when other rows keep
    the tab open, as its note. A player whose own
    `compare.parse.unavailable` finding gives that very reason is withheld
    with no reason of their own; one whose reason differs keeps it, because
    the fight-wide statement does not cover it. The same holds where no
    subject was handed: `raid --no-compare`'s Damage tab says
    `NO_COMPARISON_RAN`, so no card says it again. The empty default means
    nothing is stated once, and the two branches read it differently. Where no
    subject was handed, a reason is silenced when it equals `stated_once`, so
    the empty default silences only a reason that is itself empty, which the
    card would have printed as an empty line anyway. For a player's own
    notice it silences nothing, not even a notice whose detail is empty
    (`stated_elsewhere`). The Mythic+ page, which passes none, therefore keeps
    `NO_COMPARISON_RAN` on every card.
    """
    if compared_slugs is None:
        reason = parse_withheld if parse_withheld is not None else NO_COMPARISON_RAN
        return Section(
            state=SectionState.WITHHELD, reason="" if reason == stated_once else reason
        )
    if slug not in compared_slugs:
        return Section(state=SectionState.WITHHELD, reason=NOT_REQUESTED)
    unavailable_id = parse_unavailable_id(slug)
    unavailable = finding_by_id(findings, unavailable_id)
    if unavailable is not None and stated_elsewhere(unavailable, stated_once):
        return Section(state=SectionState.WITHHELD, reason="")
    return section_for(findings, unavailable_id, present=unavailable is None)


def build_players(
    loaded: LoadedRun,
    findings: Sequence[Finding],
    compared_slugs: frozenset[str] | None,
    subject: Player,
    titles_by_id: dict[str, str],
    defensives: Defensives,
    throughput: ThroughputCooldowns,
    tooltips: Mapping[str, Tooltip] = NO_TOOLTIPS,
    measures: Mapping[str, PlayerMeasures] = NO_MEASURES,
) -> tuple[PlayerCard, ...]:
    """One card per player.

    Damage is stated as `players.damage.*` states it — a multiple of the group
    median, with the analyser's own caveat that this is a difference and not a
    mistake. The log does not record whether a hit could have been dodged;
    this card carries the analyser's findings unchanged and adds no framing
    of its own.

    `name` is the roster's disambiguated display name, not the raw one: two
    players who share a display name must never render as two identical-
    looking cards. `subject` is the player being analysed, from our own
    roster — never a reference's own top parser, a different character in a
    different log. It decides the order the cards come in and nothing else;
    which card carries comparison rows is decided by the slug each finding
    names, so a run that compared several players fills several cards.

    The subject's card comes first, and everyone else keeps the roster's own
    order behind them. The page opens whichever sub-tab is drawn first, so
    ordering the cards is what makes the player the reader asked for the
    player the reader is shown; leaving the roster order alone would open a
    teammate's drawing four times out of five. Nav and panel are emitted from
    this one sequence, so they cannot fall out of step.

    `compared_slugs` is who the comparison was asked for, and `None` means it
    was not asked for anybody.
    """
    names_by_actor = display_names(loaded.run.players)
    slugs = slugs_by_actor(loaded.run.players)
    specs = {player.actor_id: (player.class_name, player.spec) for player in loaded.run.players}

    untimed = [finding for finding in findings if finding.seconds_lost is None]
    damage = [finding for finding in untimed if finding.id.startswith("players.damage.")]
    comparison = [
        finding
        for finding in untimed
        if any(finding.id.startswith(prefix) for prefix in COMPARISON_PREFIXES)
    ]

    total_pulls = format_seconds(loaded.run.total_pull_seconds)
    assert total_pulls is not None  # a float input always formats to a string

    summaries = sorted(
        summarise_players(loaded.run, loaded.casts, loaded.deaths, loaded.interrupts),
        key=lambda summary: summary.actor_id != subject.actor_id,
    )

    cards = []
    for summary in summaries:
        display_name = names_by_actor[summary.actor_id]
        slug = slugs[summary.actor_id]
        mine = collapse_repeated_details(
            [
                ledger_row(finding, titles_by_id, tooltips)
                for finding in damage
                if finding.title.startswith(f"{display_name} took ")
            ]
        )
        stats_line = (
            f"{quantity(summary.casts_in_pulls, 'cast', 'casts')} "
            f"in {total_pulls} of pulls · "
            f"{quantity(summary.deaths, 'death', 'deaths')} · "
            f"{quantity(summary.interrupts, 'interrupt', 'interrupts')}"
        )
        cards.append(
            PlayerCard(
                name=display_name,
                class_name=summary.class_name,
                spec=summary.spec,
                colour=class_colour(summary.class_name),
                stats_line=stats_line,
                damage_rows=mine,
                spell_and_talent=_comparison_section(findings, slug, compared_slugs),
                spell_and_talent_rows=collapse_repeated_details(
                    [
                        ledger_row(finding, titles_by_id, tooltips)
                        for finding in comparison
                        if finding.player_slug == slug
                    ]
                ),
                slug=slug,
                timeline=build_player_timeline(
                    loaded, summary.actor_id, summary.class_name, summary.spec,
                    defensives, throughput,
                ),
                comparison_tables=_tables(measures.get(slug), specs),
            )
        )
    return tuple(cards)


def _tables(
    measures: PlayerMeasures | None, specs: Mapping[int, tuple[str, str]]
) -> tuple[ComparisonTable, ...]:
    """The three tables, each dropped when it has no rows to show.

    `specs` holds each of the run's players' (class, specialisation), keyed by
    actor id, to name the teammates a debuff row was shared with.
    """
    if measures is None:
        return ()
    built = []
    if measures.boss:
        built.append(
            ComparisonTable(
                heading="Casts on boss pulls",
                caption=(
                    f"Casts a minute over {measures.boss_seconds:.0f}s of boss pulls, "
                    "against the median of the parses that cast each. Derived."
                ),
                rows=_rate_rows(measures.boss),
            )
        )
    if measures.trash:
        built.append(
            ComparisonTable(
                heading="Casts on shared trash packs",
                caption=(
                    f"Casts a minute over {measures.trash_seconds:.0f}s of trash across "
                    f"{quantity(measures.pack_count, 'pack', 'packs')} both routes "
                    "fought, against the median of the parses that cast each. Derived."
                ),
                rows=_rate_rows(measures.trash),
            )
        )
    if measures.auras:
        built.append(
            ComparisonTable(
                heading="Buff uptime",
                caption=(
                    f"Share of {measures.key_seconds:.0f}s of key time, from the key's start to "
                    "its end with the walking between pulls included, against the median of "
                    "the parses that carried each. The verdict reads Overall, and Range and "
                    "Sample are Overall's. Without bosses is the key less its boss pulls and "
                    "Bosses the boss pulls; each reads ours against the median and carries no "
                    "verdict. A buff only up in combat reads lower over the whole key the more "
                    "of it was spent between pulls, so a reference that walked less reads "
                    "higher whatever either player did. Derived."
                ),
                figures=False,
                cell_headings=("Overall", "Range", "Sample", "Without bosses", "Bosses"),
                rows=_aura_rows(measures.auras),
            )
        )
    debuffs = measures.debuffs
    if debuffs.rows:
        tally = debuffs.tally
        assert tally is not None  # rows are built only from a stream that was read
        deathless = (
            f"{quantity(debuffs.deathless, 'council boss', 'council bosses')} of a kill pull "
            "had no death in the log and "
            f"{'was' if debuffs.deathless == 1 else 'were'} measured to the pull's end. "
            if debuffs.deathless
            else ""
        )
        built.append(
            ComparisonTable(
                heading="Debuff coverage",
                caption=(
                    f"Share of {debuffs.seconds:.0f}s of enemy-alive time, summed over every "
                    "enemy measured, that carried each debuff from this player or their pets, "
                    "against the median of the parses that applied each. The verdict reads "
                    "Overall, and Range and Sample are Overall's. Trash is the mobs of trash "
                    "pulls; Bosses is the bosses themselves, a council's each from the pull's "
                    "start to their own death, or to the pull's end if they did not die there; "
                    "adds that spawn during a boss fight, and the enemies of a pull with no "
                    "boss found, count in Overall only. Those columns and each boss's read ours "
                    "against the median and carry no verdict. A debuff a teammate's "
                    "application replaces is marked shared, not judged. The group's log for "
                    "the whole fight held "
                    f"{quantity(tally.orphan_removes, 'removal', 'removals')} with no "
                    "application, dropped (a pet copy's second removal counts here); "
                    f"{quantity(tally.closed_at_end, 'application', 'applications')} still "
                    "open at the fight's end, closed there; and "
                    f"{quantity(tally.unresolved_targets, 'row', 'rows')} on an enemy with no "
                    f"game id, skipped. {deathless}Derived."
                ),
                figures=False,
                cell_headings=(
                    "Overall", "Range", "Sample", "Trash", "Bosses", *debuffs.bosses
                ),
                rows=_debuff_rows(debuffs.rows, specs),
                note=KEPT_FOR_BOSSES if _has_kept_row(debuffs.rows) else "",
            )
        )
        built.append(
            ComparisonTable(
                heading="Debuff reach",
                caption=(
                    "Share of the enemies measured that carried each debuff from this player "
                    "or their pets at least once, against the median of the parses that "
                    "applied each. Range and Sample are Overall's. A boss counts as one "
                    "enemy. Reach describes and is never judged. Derived."
                ),
                figures=False,
                judged=False,
                cell_headings=("Overall", "Range", "Sample", "Trash", "Bosses"),
                rows=_reach_rows(debuffs.rows),
                note=DEBUFF_NOTE,
                warning=_unmeasured(debuffs),
            )
        )
    if measures.stats:
        built.append(
            ComparisonTable(
                heading="Secondary stat balance",
                caption=(
                    "Each secondary as a share of this player's own rating budget, against "
                    "the median of the sample's, with the rating itself in brackets. Level "
                    "means the share sits inside the range every reference sat in. The "
                    "ratings are not compared directly: a top parse out-gears this run and "
                    "so holds more of every stat at once. Derived."
                ),
                rows=_stat_rows(measures.stats),
            )
        )
    return tuple(built)


def _rate_rows(measures: Sequence[AbilityRate]) -> tuple[ComparisonRow, ...]:
    """Cast rates, widest difference first, whichever direction it runs in."""
    ordered = sorted(measures, key=lambda m: abs(m.ours - m.their_median), reverse=True)
    rows = []
    for m in ordered:
        low, high = observed_range(m.their_rates)
        rows.append(
            ComparisonRow(
                ability_id=m.ability_id,
                name=m.name,
                ours=f"{m.ours:.1f}",
                theirs=f"{m.their_median:.1f}",
                spread=f"{low:.1f} to {high:.1f}",
                sample=f"{len(m.their_rates)} top parses",
                verdict=m.verdict.value,
                verdict_label=VERDICT_LABELS[m.verdict],
            )
        )
    return tuple(rows)


def _stat_rows(measures: Sequence[StatShare]) -> tuple[ComparisonRow, ...]:
    """Secondary shares in the order they are held, each with its rating beside it.

    Not sorted by the widest gap the way the three tables above are. A balance
    is read down a column, and a reader comparing two player cards wants crit
    in the same place on both.
    """
    rows = []
    for m in measures:
        low, high = observed_range(m.their_shares)
        rows.append(
            ComparisonRow(
                # Not an ability. A stat has no spell behind it and no icon to
                # draw, and saying so is what keeps the column honest.
                ability_id=None,
                name=m.name.capitalize(),
                ours=f"{m.ours:.0%} ({m.our_rating})",
                theirs=f"{m.their_median:.0%} ({m.their_median_rating:g})",
                spread=f"{low:.0%} to {high:.0%}",
                sample=f"{len(m.their_shares)} top parses",
                verdict=m.verdict.value,
                verdict_label=VERDICT_LABELS[m.verdict],
            )
        )
    return tuple(rows)


def _aura_rows(rows: Sequence[AuraRow]) -> tuple[ComparisonRow, ...]:
    """Aura uptimes, our own highest first, as shares not seconds.

    The two cast tables lead with the widest gap. This one does not, because it
    is read differently: dozens of rows long, it answers "how much of the fight
    did I hold each of these for", and that is a list a reader scans from the
    top. Sorting by the gap scattered the figures a reader came for and led
    with whatever the player held *least*.

    Its cells read Overall, Overall's range and sample, then Without bosses and
    Bosses.
    """
    ordered = sorted(rows, key=lambda row: row.uptime.ours, reverse=True)
    return tuple(
        ComparisonRow(
            ability_id=row.uptime.ability_id,
            name=row.uptime.name,
            verdict=row.uptime.verdict.value,
            verdict_label=VERDICT_LABELS[row.uptime.verdict],
            cells=(
                _overall(row.uptime),
                *_spread_and_sample(row.uptime.their_fractions),
                _cell(row.without_bosses),
                _cell(row.bosses),
            ),
        )
        for row in ordered
    )


WITHHELD_LABELS = {
    Withheld.NO_BOSS: "no boss found",
    Withheld.NO_TRASH: "no trash measured",
    Withheld.NOTHING_OUTSIDE_BOSSES: "nothing outside boss pulls",
    Withheld.NOT_REACHED: "no reference measured it",
    Withheld.NOT_APPLIED: "no reference applied it",
    Withheld.TOO_FEW: "too few references",
}
"""How a boss or stretch cell with no figure says why, in the reader's words."""


def _shared_label(shared_with: Sequence[int], specs: Mapping[int, tuple[str, str]]) -> str:
    """ "Shared with 2 Windwalker Monks and Frost Death Knight": each spec and class once.

    Teammates of one specialisation and class are counted rather than
    repeated, so the label still says how many players held the slot.
    """
    counts = Counter(specs[one] for one in shared_with)
    named = [
        f"{count} {pair_label(class_name, spec)}"
        if count > 1
        else pair_label(class_name, spec, plural=False)
        for (class_name, spec), count in counts.items()
    ]
    return "Shared with " + " and ".join(named)


def _has_kept_row(rows: Sequence[DebuffRow]) -> bool:
    return any(row.uptime.verdict is Verdict.BOSSES_ONLY for row in rows)


def _in_table_order(rows: Sequence[DebuffRow]) -> list[DebuffRow]:
    """Judged debuffs first, then those kept for their boss figure; our highest first in each."""
    return sorted(
        rows, key=lambda row: (row.uptime.verdict is Verdict.BOSSES_ONLY, -row.uptime.ours)
    )


def _debuff_rows(
    rows: Sequence[DebuffRow], specs: Mapping[int, tuple[str, str]]
) -> tuple[ComparisonRow, ...]:
    """Debuff uptimes, our own highest first, for the reason `_aura_rows` gives.

    A row kept only for its boss figure follows the judged ones, and is tinted
    as an unjudged row is: it too says nothing about this player's play.

    A shared row keeps its figures and names who it was shared with in place
    of a verdict. It takes the `unjudged` tint, because like that row it says
    nothing about this player's play.

    Its cells read Overall, Overall's range and sample, Trash and Bosses, then
    each boss.
    """
    built = []
    for row in _in_table_order(rows):
        m = row.uptime
        verdict, label = m.verdict, VERDICT_LABELS[m.verdict]
        if row.shared_with:
            verdict = Verdict.UNJUDGED
            label = _shared_label(row.shared_with, specs)
        built.append(
            ComparisonRow(
                ability_id=m.ability_id,
                name=m.name,
                verdict=verdict.value,
                verdict_label=label,
                cells=(
                    _overall(m),
                    *_spread_and_sample(m.their_fractions),
                    _cell(row.trash),
                    _cell(row.bosses),
                    *(_cell(cell) for cell in row.cells),
                ),
            )
        )
    return tuple(built)


def _cell(cell: BossCell | StretchCell) -> str:
    """One boss's or one stretch's cell: ours against the median, or ours and why not."""
    reason = WITHHELD_LABELS[cell.withheld] if cell.withheld is not None else ""
    if cell.ours is None:
        return reason
    if cell.their_median is None:
        return f"{cell.ours:.0%}; {reason}" if reason else f"{cell.ours:.0%}"
    return f"{cell.ours:.0%} against {cell.their_median:.0%}"


def _overall(m: AuraUptime) -> str:
    """The judged figure as a cell: ours against the median, the verdict beside it."""
    return f"{m.ours:.0%} against {m.their_median:.0%}"


def _spread_and_sample(fractions: Sequence[float]) -> tuple[str, str]:
    """The Range and Sample cells of the references behind an Overall median.

    Two empty cells when there are none, as on a reach no reference measured.
    """
    if not fractions:
        return "", ""
    low, high = observed_range(fractions)
    return f"{low:.0%} to {high:.0%}", f"{len(fractions)} top parses"


def _reach_rows(rows: Sequence[DebuffRow]) -> tuple[ComparisonRow, ...]:
    """Each debuff's reach, in the coverage table's order so a reader can look across.

    Its cells read Overall, Overall's range and sample, then Trash and Bosses.
    """
    return tuple(
        ComparisonRow(
            ability_id=row.uptime.ability_id,
            name=row.uptime.name,
            verdict=DESCRIBED,
            cells=(
                _cell(row.reach.overall),
                *_spread_and_sample(row.reach.overall_fractions),
                _cell(row.reach.trash),
                _cell(row.reach.bosses),
            ),
        )
        for row in _in_table_order(rows)
    )


def _unmeasured(debuffs: DebuffTable) -> str:
    """The warning under the debuff tables, a clause per count above zero, or nothing.

    A clause stating zero would warn about nothing, so each is drawn only when
    its own count is above zero.
    """
    unmeasured, undebuffed = debuffs.unmeasured_no_death, debuffs.undebuffed_deaths
    clauses: list[str] = []
    if unmeasured:
        clauses.append(
            f"{quantity(unmeasured, 'enemy', 'enemies')} had no death in the log and "
            f"{'was' if unmeasured == 1 else 'were'} not measured"
        )
    if undebuffed:
        who = str(undebuffed) if clauses else quantity(undebuffed, "enemy", "enemies")
        clauses.append(
            f"{who} died without anyone debuffing {'it' if undebuffed == 1 else 'them'} and "
            f"{'counts' if undebuffed == 1 else 'count'} only toward reached"
        )
    return "; ".join(clauses) + "." if clauses else ""
