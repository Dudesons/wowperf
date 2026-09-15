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


class RaidParseRow(Frozen):
    """One row of a raid specialisation's parse leaderboard.

    Not `ParseRow`: measured 2026-09-14 against a raid `characterRankings` board,
    a row carries no `score`, no `medal` and no `affixes` -- fields a Mythic+ row
    always has and this one never sends. And the field whose name suggests it
    carries over does not: `bracketData`, which `build_parse_rows` writes into
    `keystone_level` for the Mythic+ axis, reads 319 to 325 here. That is not a
    keystone level, and what it does mean is unverified, so this row does not
    carry it under any name. `amount` is a per-second rate, not a total --
    dividing it by `duration_ms` would be the count-against-rate mistake the
    field table warns against.
    """

    report_code: str
    fight_id: int
    duration_ms: int
    character_name: str
    class_name: str
    spec: str
    amount: float
    size: int

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000


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

    def rows_named(self, name: str) -> tuple[RankedPlayer, ...]:
        """Every row whose character name folds to `name`: none, one, or several.

        A tuple rather than the first match, because "several" is a state this
        report cannot resolve and must not paper over. A rankings row carries no
        actor id -- `RankedPlayer` above records why -- so two roster members
        sharing a name, which twenty players make ordinary, are two rows nothing
        here can tell apart. Answering with the first would hand the second
        player the first one's percentile and throughput under their own name,
        badged `MEASURED`.

        Reading the count is the caller's job. Both raid callers withhold above
        one and say which name the two players share.
        """
        folded = name.casefold()
        return tuple(
            player for player in self.players if player.character_name.casefold() == folded
        )
