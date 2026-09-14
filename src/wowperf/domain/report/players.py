# ABOUTME: One card per player, carrying the facts measured about them.
# ABOUTME: Damage reads against the group median: a log cannot say a hit was avoidable.

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from wowperf.domain.analysis.players import summarise_players
from wowperf.domain.analysis.roster import display_names
from wowperf.domain.comparison.measures import (
    AbilityRate,
    AuraUptime,
    PlayerMeasures,
    StatShare,
    Verdict,
)
from wowperf.domain.comparison.statistics import observed_range
from wowperf.domain.findings import Finding
from wowperf.domain.model import LoadedRun, Player, Run
from wowperf.domain.report.frame import (
    NO_COMPARISON_RAN,
    NOT_REQUESTED,
    finding_by_id,
    format_seconds,
    parse_unavailable_id,
    plural,
    section_for,
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
}
"""Each branch, spelled for the reader of a column rather than for a stylesheet.

The table's own column holds these, because a tint carries no meaning alone:
several readers cannot separate two colours and every printed page separates
none of them. Only `unjudged` is spelled differently from the value it comes
from, being the one word here that is not ordinary English -- what the table
means by it is that the comparison declined to read anything into the figure
beside it, and a reader meeting the bare word would have no way to know that.
"""


def class_colour(class_name: str) -> str:
    return f"class-{class_name.lower()}" if class_name in CLASS_COLOURS else "class-unknown"


def slugs_by_actor(run: Run) -> dict[int, str]:
    """Every player's fragment id, keyed by actor id.

    Computed from the roster's own order, not from the order the cards are
    drawn in, so a player's fragment id does not move when a different subject
    reorders the cards -- a deep link into a report stays valid across a
    re-run that named someone else. Two display names can reduce to the same
    slug, so the roster index is appended to keep them apart.

    This is the only place a player *fragment* id is minted. The comparison's
    finding ids and the card they belong to both read from here, and that
    agreement is what makes a `#finding-...` link land in the right sub-tab.
    The slugging itself is `wowperf.domain.slug`, which analysis shares:
    `defensives.*` mints its own ids and needs the same alphabet.
    """
    names = display_names(run.players)
    return {
        player.actor_id: f"{player_slug(names[player.actor_id])}-{index}"
        for index, player in enumerate(run.players)
    }


def _comparison_section(
    findings: Sequence[Finding], slug: str, compared_slugs: frozenset[str] | None
) -> Section:
    """One player's comparison section, in whichever of three states it is in.

    A player nobody asked for is not the same as a player the leaderboard had
    nothing for, and neither is the same as a run that fetched no reference at
    all. Saying so is the whole job: a reader who cannot tell "not asked" from
    "not available" will read the second as the first and stop asking.
    """
    if compared_slugs is None:
        return Section(state=SectionState.WITHHELD, reason=NO_COMPARISON_RAN)
    if slug not in compared_slugs:
        return Section(state=SectionState.WITHHELD, reason=NOT_REQUESTED)
    unavailable_id = parse_unavailable_id(slug)
    return section_for(
        findings, unavailable_id, present=finding_by_id(findings, unavailable_id) is None
    )


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
    slugs = slugs_by_actor(loaded.run)

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
            f"{summary.casts_in_pulls} {plural(summary.casts_in_pulls, 'cast')} "
            f"in {total_pulls} of pulls · "
            f"{summary.deaths} {plural(summary.deaths, 'death')} · "
            f"{summary.interrupts} {plural(summary.interrupts, 'interrupt')}"
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
                comparison_tables=_tables(measures.get(slug)),
            )
        )
    return tuple(cards)


def _tables(measures: PlayerMeasures | None) -> tuple[ComparisonTable, ...]:
    """The three tables, each dropped when it has no rows to show."""
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
                    f"{measures.pack_count} {plural(measures.pack_count, 'pack')} both routes "
                    "fought, against the median of the parses that cast each. Derived."
                ),
                rows=_rate_rows(measures.trash),
            )
        )
    if measures.auras:
        built.append(
            ComparisonTable(
                heading="Buff uptime on boss pulls",
                caption=(
                    f"Share of {measures.boss_seconds:.0f}s of boss pulls, against the "
                    "median of the parses that carried each. Derived."
                ),
                rows=_aura_rows(measures.auras),
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


def _aura_rows(measures: Sequence[AuraUptime]) -> tuple[ComparisonRow, ...]:
    """Aura uptimes, our own highest first, as shares of boss time not seconds.

    The two cast tables lead with the widest gap. This one does not, because it
    is read differently: dozens of rows long, it answers "how much of the fight
    did I hold each of these for", and that is a list a reader scans from the
    top. Sorting by the gap scattered the figures a reader came for and led
    with whatever the player held *least*.
    """
    ordered = sorted(measures, key=lambda m: m.ours, reverse=True)
    rows = []
    for m in ordered:
        low, high = observed_range(m.their_fractions)
        rows.append(
            ComparisonRow(
                ability_id=m.ability_id,
                name=m.name,
                ours=f"{m.ours:.0%}",
                theirs=f"{m.their_median:.0%}",
                spread=f"{low:.0%} to {high:.0%}",
                sample=f"{len(m.their_fractions)} top parses",
                verdict=m.verdict.value,
                verdict_label=VERDICT_LABELS[m.verdict],
            )
        )
    return tuple(rows)
