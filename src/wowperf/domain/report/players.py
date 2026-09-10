# ABOUTME: One card per player, carrying the facts measured about them.
# ABOUTME: Damage reads against the group median: a log cannot say a hit was avoidable.

import unicodedata
from collections.abc import Sequence

from wowperf.domain.analysis.players import display_names, summarise_players
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
from wowperf.domain.report.ledger import collapse_repeated_details, ledger_row
from wowperf.domain.report.model import PlayerCard, Section, SectionState
from wowperf.domain.report.player_timeline import build_player_timeline
from wowperf.domain.season import Defensives, ThroughputCooldowns

CLASS_COLOURS = (
    "DeathKnight", "DemonHunter", "Druid", "Evoker", "Hunter", "Mage", "Monk",
    "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Warrior",
)
"""Classes with a palette token. A class absent here still renders, in a neutral tone.

The colour never carries meaning alone: every card prints the class name too,
because several class colours are hard to tell apart and reports get
screenshotted and recompressed.
"""

COMPARISON_PREFIXES = ("compare.spells.", "compare.talents", "compare.uptime.")
"""Finding families that belong on a player's card rather than in the ledger.

Which card is decided by the slug the finding carries, never by who the
subject is: a run can compare a teammate the reader did not name, and can
compare several players at once, so routing these to the subject's card would
put one player's rows under another player's name.
"""


def class_colour(class_name: str) -> str:
    return f"class-{class_name.lower()}" if class_name in CLASS_COLOURS else "class-unknown"


SLUG_FALLBACK = "player"
"""What a name reduces to when nothing in it survives the transliteration.

A wholly non-Latin name — `Кириллица` — keeps no ASCII letter after
decomposition, and an empty id is not addressable. The index the caller
appends is what keeps two such names apart.
"""


def player_slug(display_name: str) -> str:
    """A display name reduced to what an HTML id and a URL fragment both carry.

    Accents decompose and their marks are dropped, so `Bríala` and `Briala`
    reach the same slug — which is why the caller appends an index rather than
    trusting this to be unique. Everything else outside the ASCII alphabet and
    digits becomes a hyphen, and runs of hyphens collapse.
    """
    decomposed = unicodedata.normalize("NFKD", display_name)
    kept = [
        character.lower() if character.isascii() and character.isalnum() else "-"
        for character in decomposed
        if not unicodedata.combining(character)
    ]
    slug = "".join(kept).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or SLUG_FALLBACK


def slugs_by_actor(run: Run) -> dict[int, str]:
    """Every player's fragment id, keyed by actor id.

    Computed from the roster's own order, not from the order the cards are
    drawn in, so a player's fragment id does not move when a different subject
    reorders the cards -- a deep link into a report stays valid across a
    re-run that named someone else. Two display names can reduce to the same
    slug, so the roster index is appended to keep them apart.

    This is the only place a slug is minted. The comparison's finding ids and
    the card they belong to both read from here, and that agreement is what
    makes a `#finding-...` link land in the right sub-tab.
    """
    names = display_names(run)
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
    names_by_actor = display_names(loaded.run)
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
                ledger_row(finding, titles_by_id)
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
                        ledger_row(finding, titles_by_id)
                        for finding in comparison
                        if finding.player_slug == slug
                    ]
                ),
                slug=slug,
                timeline=build_player_timeline(
                    loaded, summary.actor_id, summary.class_name, summary.spec,
                    defensives, throughput,
                ),
            )
        )
    return tuple(cards)
