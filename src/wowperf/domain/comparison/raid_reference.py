# ABOUTME: What a raid leaderboard row and a report's own rankings row are, as domain values.
# ABOUTME: A rank is a string here because the API puts a tilde on it, and int() rejects that.

from wowperf.domain.base import Frozen


class RankedPlayer(Frozen):
    """One player's standing on this boss, as the report's own rankings row states it.

    `rank` and `best` are strings, not integers: measured 2026-09-14, they read
    "~5764" and "~3746" -- the API's own approximation marker, which `int()`
    rejects. Anything that needs arithmetic uses `rank_percent`.

    There is no actor id here on purpose. A rankings entry's `id` is a Warcraft
    Logs character id, not this report's actor id, so joining the two on it
    would match nothing while looking exactly like a join that works.
    """

    character_name: str
    class_name: str
    spec: str
    role: str
    amount: float
    rank: str
    best: str
    rank_percent: int
    bracket_percent: int
    total_parses: int


class ReportRankings(Frozen):
    """The report's own rankings for one fight, and the roster's standings in it.

    Absent entirely for an attempt that did not kill -- design section 14 item 7
    measured a kill returning one row and a wipe returning none, with no field
    telling the two apart. `build_report_rankings` returns `None` rather than an
    empty `ReportRankings`, so a caller cannot read a difficulty of 0 off a wipe.
    """

    fight_id: int
    difficulty: int
    partition: int
    size: int
    kill: bool
    players: tuple[RankedPlayer, ...] = ()

    def player_named(self, name: str) -> RankedPlayer | None:
        folded = name.casefold()
        return next(
            (player for player in self.players if player.character_name.casefold() == folded),
            None,
        )
