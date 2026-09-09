# ABOUTME: One card per player, carrying the facts measured about them.
# ABOUTME: Damage reads against the group median: a log cannot say a hit was avoidable.

from collections.abc import Sequence

from wowperf.domain.analysis.players import display_names, summarise_players
from wowperf.domain.comparison.sample import ParseSample
from wowperf.domain.findings import Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.frame import PARSE_UNAVAILABLE_ID, format_seconds, sampled, section_for
from wowperf.domain.report.ledger import collapse_repeated_details, ledger_row
from wowperf.domain.report.model import PlayerCard

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
"""Finding families that belong on the subject player's card rather than in the ledger."""


def class_colour(class_name: str) -> str:
    return f"class-{class_name.lower()}" if class_name in CLASS_COLOURS else "class-unknown"


def _plural(count: int, singular: str) -> str:
    """`singular` unless `count` is not one. The one pluralisation rule this report needs."""
    return singular if count == 1 else f"{singular}s"


def build_players(
    loaded: LoadedRun,
    findings: Sequence[Finding],
    parse: ParseSample | None,
    subject: Player,
    titles_by_id: dict[str, str],
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
    different log. Matching by `actor_id` rather than name also keeps two
    players who share a display name from both receiving the comparison rows.

    `parse` decides one thing here and reads nothing off its members: whether
    a parse comparison ran at all.
    """
    comparison_section = section_for(findings, PARSE_UNAVAILABLE_ID, sampled(parse))
    names_by_actor = display_names(loaded.run)

    untimed = [finding for finding in findings if finding.seconds_lost is None]
    damage = [finding for finding in untimed if finding.id.startswith("players.damage.")]
    comparison = [
        finding
        for finding in untimed
        if any(finding.id.startswith(prefix) for prefix in COMPARISON_PREFIXES)
    ]

    total_pulls = format_seconds(loaded.run.total_pull_seconds)
    assert total_pulls is not None  # a float input always formats to a string

    cards = []
    for summary in summarise_players(
        loaded.run, loaded.casts, loaded.deaths, loaded.interrupts
    ):
        display_name = names_by_actor[summary.actor_id]
        mine = collapse_repeated_details(
            [
                ledger_row(finding, titles_by_id)
                for finding in damage
                if finding.title.startswith(f"{display_name} took ")
            ]
        )
        is_subject = summary.actor_id == subject.actor_id
        stats_line = (
            f"{summary.casts_in_pulls} {_plural(summary.casts_in_pulls, 'cast')} "
            f"in {total_pulls} of pulls · "
            f"{summary.deaths} {_plural(summary.deaths, 'death')} · "
            f"{summary.interrupts} {_plural(summary.interrupts, 'interrupt')}"
        )
        cards.append(
            PlayerCard(
                name=display_name,
                class_name=summary.class_name,
                spec=summary.spec,
                colour=class_colour(summary.class_name),
                stats_line=stats_line,
                damage_rows=mine,
                spell_and_talent=comparison_section,
                spell_and_talent_rows=(
                    collapse_repeated_details(
                        [ledger_row(finding, titles_by_id) for finding in comparison]
                    )
                    if is_subject
                    else ()
                ),
            )
        )
    return tuple(cards)
