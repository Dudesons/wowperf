# ABOUTME: The name a report shows for each player, disambiguated when two share one.
# ABOUTME: Its own module so two analysers can share it without importing each other.

from collections import defaultdict

from wowperf.domain.model import Player


def display_names(players: tuple[Player, ...]) -> dict[int, str]:
    """Map each player's actor id to the name a report should show for them.

    Two players can share a display name (cross-realm groups ordinarily
    produce this); when that happens the actor id disambiguates both, so a
    reader — and any code matching against a finding's title — is never
    handed one name that could mean two different people. A name held by
    exactly one player stays plain, since the common case needs no clutter.
    Computed once from the roster, the same rule `analyse_damage_outliers`
    applies to its own damage-outlier titles.
    """
    name_counts: dict[str, int] = defaultdict(int)
    for player in players:
        name_counts[player.name] += 1
    return {
        player.actor_id: (
            player.name
            if name_counts[player.name] == 1
            else f"{player.name} (actor {player.actor_id})"
        )
        for player in players
    }
