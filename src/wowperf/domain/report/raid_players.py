# ABOUTME: One card per raider: identity, and whichever of the three comparison states applies.
# ABOUTME: A boss fight has no pulls, so this card carries neither a timeline nor a trash table.

from collections.abc import Mapping, Sequence

from wowperf.domain.analysis.roster import display_names
from wowperf.domain.comparison.pace_player import PLAYER_PACE_PREFIX
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Finding, quantity
from wowperf.domain.model import Player
from wowperf.domain.report.frame import format_seconds, stated_elsewhere
from wowperf.domain.report.ledger import NO_TOOLTIPS, collapse_repeated_details, ledger_row
from wowperf.domain.report.model import PlayerCard, Tooltip
from wowperf.domain.report.players import _comparison_section, class_colour, slugs_by_actor
from wowperf.domain.report.raid_ledger import RAID_COMPARISON_PREFIXES


def build_raid_players(
    loaded: LoadedEncounter,
    findings: Sequence[Finding],
    subject: Player,
    compared_slugs: frozenset[str] | None,
    titles_by_id: dict[str, str],
    tooltips: Mapping[str, Tooltip] = NO_TOOLTIPS,
    *,
    parse_withheld: str | None = None,
    stated_once: str = "",
) -> tuple[PlayerCard, ...]:
    """One card per raider.

    `build_players`' card carries two things a boss fight has nothing to build
    from: a timeline banded over pulls, and a table comparing shared trash
    packs. Neither is built here -- `timeline` and `comparison_tables` stay at
    `PlayerCard`'s own defaults, `None` and `()`. What is left is what this
    function actually builds: the raider's own facts, stated over the whole
    attempt rather than "in pulls" since a boss fight has only the one window,
    and their comparison section in whichever of its three states
    `_comparison_section` finds it in.

    `subject` orders the cards exactly as `build_players` does -- their card
    comes first and the rest keep the roster's own order -- and decides
    nothing else. Which card a comparison row reaches is decided by the slug
    the finding carries, never by who the subject is: a raid compares many
    raiders at once, and routing to the subject would put every other
    raider's rows under one name.

    `pace_rows` is filled the same way, from every untimed finding whose id
    starts with `PLAYER_PACE_PREFIX` -- a per-player damage-pace reading or its
    notice, both minted by `analyse_player_pace`. `build_raid_report` strips
    these out of the findings it hands `place_rows`, since `RAID_PLACEMENTS`'
    `compare.pace.` prefix would otherwise take them onto the Damage tab; this
    function still receives every finding and routes them here instead.

    `parse_withheld` is handed to every card's comparison section: the reason
    each card states in place of `NO_COMPARISON_RAN` when no parse subject was
    handed at all, and the empty string when the page states it once for
    every card.

    `stated_once` is the reason the page's Damage tab prints for the whole
    fight, as its withheld reason or as its note. A raider's
    `compare.parse.unavailable` notice carrying that very reason is said
    there, so it is neither the card's withheld line nor one of its rows; a
    notice whose reason differs is about that raider and stays on their card.
    With no parse subject handed, `NO_COMPARISON_RAN` is that reason on a
    `raid --no-compare` page, so no card states it either.
    Empty, the default, states nothing and drops nothing.
    """
    players = loaded.encounter.players
    names_by_actor = display_names(players)
    slugs = slugs_by_actor(players)

    untimed = [finding for finding in findings if finding.seconds_lost is None]
    comparison = [
        finding
        for finding in untimed
        if any(finding.id.startswith(prefix) for prefix in RAID_COMPARISON_PREFIXES)
        and not stated_elsewhere(finding, stated_once)
    ]
    pace = [finding for finding in untimed if finding.id.startswith(PLAYER_PACE_PREFIX)]

    ordered = sorted(players, key=lambda player: player.actor_id != subject.actor_id)

    cards = []
    for player in ordered:
        slug = slugs[player.actor_id]
        cards.append(
            PlayerCard(
                name=names_by_actor[player.actor_id],
                class_name=player.class_name,
                spec=player.spec,
                colour=class_colour(player.class_name),
                stats_line=_stats_line(loaded, player.actor_id),
                spell_and_talent=_comparison_section(
                    findings, slug, compared_slugs,
                    parse_withheld=parse_withheld, stated_once=stated_once,
                ),
                spell_and_talent_rows=collapse_repeated_details(
                    [
                        ledger_row(finding, titles_by_id, tooltips)
                        for finding in comparison
                        if finding.player_slug == slug
                    ]
                ),
                pace_rows=tuple(
                    ledger_row(finding, titles_by_id, tooltips)
                    for finding in pace
                    if finding.player_slug == slug
                ),
                slug=slug,
            )
        )
    return tuple(cards)


def _stats_line(loaded: LoadedEncounter, actor_id: int) -> str:
    """A raider's activity over the whole attempt.

    `build_players` states a cast count against the pull time it happened in,
    because a dungeon run has pulls to hold it against. A boss fight has one
    window and no others to distinguish it from, so this states the same
    three facts against the attempt itself rather than an "in pulls" phrase
    that would imply a distinction this fight does not have.
    """
    casts = sum(1 for cast in loaded.casts if cast.actor_id == actor_id)
    deaths = sum(1 for death in loaded.deaths if death.actor_id == actor_id)
    interrupts = sum(1 for interrupt in loaded.interrupts if interrupt.actor_id == actor_id)
    duration = format_seconds(loaded.encounter.duration_seconds)
    assert duration is not None  # a float input always formats to a string
    return (
        f"{quantity(casts, 'cast', 'casts')} in {duration} of the fight · "
        f"{quantity(deaths, 'death', 'deaths')} · "
        f"{quantity(interrupts, 'interrupt', 'interrupts')}"
    )
