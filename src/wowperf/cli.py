# ABOUTME: Command-line entry point; the driving adapter that wires ports to implementations.
# ABOUTME: Holds no analysis logic, only construction, argument handling and output.

import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import httpx
import typer

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.config.dotenv import apply_dotenv
from wowperf.adapters.config.toml import (
    load_consumables,
    load_defensives,
    load_externals,
    load_roles,
    load_season_data,
    load_self_resurrections,
    load_throughput_cooldowns,
)
from wowperf.adapters.render.html import render
from wowperf.adapters.render.icons import CdnIcons
from wowperf.adapters.wcl.ability_tables import build_ability_taken_rows
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import RateLimit, WclClient
from wowperf.adapters.wcl.cost import CostLedger
from wowperf.adapters.wcl.encounter_rankings import WclEncounterRankingRepository
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.ingest import IngestError
from wowperf.adapters.wcl.queries import ABILITY_TAKEN_TABLE_QUERY
from wowperf.adapters.wcl.ranking_repository import WclRankingRepository
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.analysis.roster import display_names
from wowperf.domain.analysis.service import analyse
from wowperf.domain.auras import PlayerAuras
from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.comparison.measures import PlayerMeasures
from wowperf.domain.comparison.mechanics import (
    AbilityTakenRow,
    MechanicsMember,
    MechanicsSample,
    ReferenceKillRow,
    select_reference_kills,
)
from wowperf.domain.comparison.reference import (
    REPORT_URL,
    Comparability,
    ParseRow,
    SpeedRow,
)
from wowperf.domain.comparison.sample import (
    SAMPLE_SIZE,
    ParseMember,
    ParseSample,
    SpeedMember,
    SpeedSample,
)
from wowperf.domain.comparison.service import ComparisonSubject, compare, find_player
from wowperf.domain.comparison.tables import comparison_measures
from wowperf.domain.encounter import Encounter
from wowperf.domain.findings import rank_findings
from wowperf.domain.model import LoadedRun, Player, Run
from wowperf.domain.report.build import build_report
from wowperf.domain.report.model import ReferenceRecord
from wowperf.domain.report.narrative import lines_with_digits
from wowperf.domain.report.players import slugs_by_actor
from wowperf.urls import parse_report_url

app = typer.Typer(help="Analyse World of Warcraft logs and report what to improve.")

DEFAULT_CACHE_DIR = Path("cache")

REFERENCE_CACHE_SUBDIR = "references"
REFERENCE_CACHE_SECONDS = 24 * 3600.0
"""How long a leaderboard row or a reference run's responses are kept.

Long enough for the narrative re-run the analyzing-a-run skill relies on to be
served from cache; short enough that no standing store of other players' logs
accumulates (RPGLogs terms §5d). Our own run's responses never expire.
"""

FINDINGS_ARE_RANKED_NOT_ADDITIVE = (
    "findings are ranked by seconds_lost, not additive: compare.duration measures the "
    "gap against the median of the sample, while every other seconds_lost figure is "
    "priced against a particular run's route, so the two overlap without one "
    "containing the other; time.gap.* and compare.downtime both nest inside "
    "time.residual; deaths.single.*, deaths.chain.* and deaths.repeat.* all nest "
    "inside deaths.total; and compare.route.skipped.* overlaps the waste "
    "trash.overage already reports"
)
"""Why the seconds in this file must never be summed.

Every containment this names is one the report also relies on, in
`report.build.NESTS_INSIDE`; the two are held in step by
`test_cli.test_the_warning_names_exactly_the_nestings_the_report_draws`.
"""

RAID_FINDINGS_ARE_RANKED_NOT_ADDITIVE = (
    "findings are ranked by seconds_lost, not additive: deaths.single.*, "
    "deaths.chain.* and deaths.repeat.* all nest inside deaths.total; findings are "
    "ordered by severity first and by seconds_lost only within one family, so this "
    "order must not be read as a ranking by time either"
)
"""Why the seconds in a raid findings file must never be summed.

A sibling of `FINDINGS_ARE_RANKED_NOT_ADDITIVE`, not a reuse of it: this one is
read by `raid`, and `analyse_encounter` runs none of `decompose_time` or
`analyse_trash` -- a boss fight carries no keystone timer and no
enemy-forces requirement (see `analyse_encounter`'s own docstring) -- so
naming compare.duration, time.gap.*, compare.downtime, time.residual,
compare.route.skipped.* or trash.overage here would claim an accounting the
findings file does not hold. Only the deaths.* nesting applies to a raid
fight; `test_cli.test_the_raid_warning_names_only_findings_the_encounter_analyser_emits`
holds this in step with that.

The severity clause is new: `analyse_encounter` ranks with `rank_raid_findings`,
which sorts by finding family before it ever looks at `seconds_lost`, unlike
`rank_findings`'s pure time ordering. A reader who skimmed `FINDINGS_ARE_RANKED_NOT_ADDITIVE`
first and assumed the same rule here would read a mechanics finding outranking a
longer death as a mistake in the seconds, when it is the severity table doing
exactly what it is for.
"""


@app.callback()
def main() -> None:
    """Analyse World of Warcraft logs and report what to improve.

    Typer collapses a single-command app into a bare invocation; this callback
    keeps `fetch` addressable as a subcommand even before later plans add more.
    """


def build_repository(cache_dir: Path) -> WclRunRepository:
    # Credentials come from a `.env` in the working directory, which is how a
    # fresh clone is told to hold them, or from the environment, which wins.
    apply_dotenv(Path.cwd() / ".env", os.environ)

    client_id = os.environ.get("WCL_CLIENT_ID")
    client_secret = os.environ.get("WCL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise typer.BadParameter(
            "Set WCL_CLIENT_ID and WCL_CLIENT_SECRET, either in your environment or "
            "in a .env file in the directory you run this from: copy .env.example to "
            ".env and fill both values in. Create a client at "
            "https://www.warcraftlogs.com/api/clients/"
        )

    http = httpx.Client(timeout=60.0)
    return WclRunRepository(
        WclClient(TokenProvider(client_id, client_secret, http), http),
        DiskCache(cache_dir),
    )


def build_icons(loaded: LoadedRun, parse_samples: Sequence[ParseSample]) -> CdnIcons:
    """Icons for one run: its own ability dictionary and every parse sample's.

    Nothing here can fail and nothing here is fetched. An icon is an address the
    reader's browser resolves when the page is opened, so building them is string
    work over dictionaries the run already carries -- no request, no cache, and
    no way for a report to be written without its art.

    A comparison names an ability our player never cast, so that ability's file
    name is in the reference's own dictionary and in no other. Every compared
    player's sample is read, not only the subject's: a teammate's comparison
    draws on their own specialisation's references, and a card whose rows the
    resolver has never heard of draws them with no icon at all. Ours is
    overlaid last: where both name an id they name the same file, so the order
    settles determinism rather than correctness.
    """
    names: dict[int, str] = {}
    for sample in parse_samples:
        for member in sample.members:
            names.update(member.ability_icons)
    names.update(loaded.ability_icon_map)
    return CdnIcons(names)


def build_reference_repositories(
    client: WclClient, cache_dir: Path
) -> tuple[WclRankingRepository, WclRunRepository]:
    """The leaderboards and the reference runs, behind the expiring cache."""
    transient = DiskCache(
        cache_dir / REFERENCE_CACHE_SUBDIR, max_age_seconds=REFERENCE_CACHE_SECONDS
    )
    return WclRankingRepository(client, transient), WclRunRepository(client, transient)


def _quota_sentence(before: RateLimit, after: RateLimit) -> str:
    """State the cost of a command's own queries, quota read before and after.

    Point cost per query is undocumented, so both commands read the quota before
    and after their work. A reading reports the spend before its own query is
    billed, measured 2026-09-08, so the difference covers the opening read and
    everything after it, but never the closing read's own cost. `remaining` is
    optimistic by that same unbilled amount; the figure is the API's own and is
    not adjusted, because the API does not say what the read cost.
    """
    remaining = after.limit_per_hour - after.points_spent_this_hour
    if after.points_spent_this_hour < before.points_spent_this_hour:
        return (
            "Rate limit: the hourly counter reset while this command ran, so what it spent "
            f"cannot be read from it; {remaining:.2f} of {after.limit_per_hour} remain "
            "this hour."
        )

    spent = after.points_spent_this_hour - before.points_spent_this_hour
    return (
        f"Rate limit: {spent:.2f} points spent, the opening quota read included and the "
        f"closing one not; {remaining:.2f} of {after.limit_per_hour} remain this hour."
    )


def _cost_breakdown(costs: CostLedger) -> str:
    """What this command's points went on, dearest operation first.

    A reading reports the spend before its own query is billed, so the last query
    of a run is unpriced when this is written. The closing note names it, rather
    than leaving a row quietly short of the calls it claims.
    """
    if not costs.costs():
        return ""

    rows = costs.by_operation()

    width = max(len(row.operation) for row in rows)
    lines = ["Where they went:"]
    lines += [
        f"  {row.operation:<{width}}  {row.calls:>3} "
        f"{'call' if row.calls == 1 else 'calls':<5}  {row.points:>8.2f} points"
        for row in rows
    ]

    pending = costs.pending()
    if pending is not None:
        lines.append(
            f"  {pending} ran last, so one of its calls is unpriced: a query's cost "
            "is only known once the next one runs."
        )
    return "\n".join(lines)


@app.command()
def fetch(
    report: str = typer.Argument(..., help="Report URL or code"),
    fight: int | None = typer.Option(None, help="Fight ID; defaults to the only keystone run"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Where to cache API responses"),
) -> None:
    """Fetch a Mythic+ run and print it as JSON."""
    # Windows gives the process a locale-dependent stdout encoding (commonly cp1252),
    # which cannot hold the non-ASCII player names and dungeon names real reports
    # contain. Reconfigure to UTF-8 so the JSON reaches stdout intact instead of
    # crashing with a UnicodeEncodeError after the API quota has already been spent.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        code, fight_from_url = parse_report_url(report)
        repository = build_repository(cache_dir)

        before = repository.rate_limit()
        run = repository.get(code, fight if fight is not None else fight_from_url)
        after = repository.rate_limit()
    except (ValueError, WclError, httpx.HTTPError, OSError) as error:
        # IngestError subclasses ValueError. Anything else keeps its traceback,
        # because an unexpected failure is a bug and should look like one.
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    typer.echo(_quota_sentence(before, after), err=True)
    _echo_cost_breakdown(repository.client.costs)
    typer.echo(run.model_dump_json(indent=2))


def _echo_cost_breakdown(costs: CostLedger) -> None:
    breakdown = _cost_breakdown(costs)
    if breakdown:
        typer.echo(breakdown, err=True)


def _roster_hint(names: Mapping[int, str]) -> str:
    """Who is on the roster, for a message that has just refused a name.

    Spelled the way the report spells them, which is also a spelling
    `_resolve_player` accepts: every name printed here resolves, so a reader
    who copies one back into `--player` is never refused a second time. Two
    roster members can share a name, and the raw roster would print that name
    twice, telling a reader neither that there are two nor which of them a
    name would reach.
    """
    roster = ", ".join(sorted(names.values())) or "nobody"
    return f"Pass --player with one of: {roster}"


def _by_display_name(
    players: Sequence[Player], requested: str, names: Mapping[int, str]
) -> Player | None:
    """The roster member a disambiguated spelling names, or None.

    Takes the roster directly rather than a `Run`, so a Mythic+ roster and a
    raid `Encounter`'s roster resolve the same way without either aggregate
    being named here: `Encounter` is deliberately not a `Run` (see its own
    ABOUTME), and this narrows to the value both expose in common.

    Folds case the same way `find_player` does, for the same reason. An empty
    request matches nobody rather than the first member with no spelling of
    their own: equality against an empty string is as indiscriminate as
    membership in one.
    """
    folded = requested.casefold()
    if not folded:
        return None
    return next(
        (player for player in players if names.get(player.actor_id, "").casefold() == folded),
        None,
    )


def _resolve_player(
    players: Sequence[Player],
    owner_name: str | None,
    requested: str | None,
    names: Mapping[int, str],
) -> Player:
    """Whose run this is, for the individual comparison.

    The report owner is the default because it is the only name the log itself
    volunteers. Warcraft Logs lowercases it, so the match folds case.

    A raw roster name is tried first and the disambiguated spelling
    `display_names` gives -- `Emberkin (actor 700)` -- second. Raw first leaves
    the common invocation exactly as it was: a name two members share still
    reaches the first of them rather than becoming an error. The second pass is
    what makes the other one reachable at all, and what keeps `_roster_hint`
    from offering a name this would refuse.
    """
    name = requested or owner_name
    if name is not None:
        found = find_player(players, name) or _by_display_name(players, name, names)
        if found is not None:
            return found

    raise ValueError(f"{name!r} is not in this run's roster. {_roster_hint(names)}")


def _resolve_requested(
    players: Sequence[Player],
    owner_name: str | None,
    requested: Sequence[str],
    everyone: bool,
    names: Mapping[int, str],
) -> tuple[Player, tuple[Player, ...]]:
    """The subject, and every player to compare.

    The subject is the first name given, or the report owner when none is: it
    decides whose card opens the Players tab and whose name the findings file
    carries, and a report with no subject at all would leave both undecided.
    `--all-players` widens who is compared without touching who the subject is,
    so the two flags combine rather than conflict.

    A name the tool cannot honour is refused rather than substituted, and an
    empty one is such a name: `--player "$WHO"` with `WHO` unset would
    otherwise mean the report owner, so a reader who asked for one player
    would silently be charged for two. Only a *supplied* name is checked here
    — with no `--player` at all, `_resolve_player`'s own default still stands.

    Keyed by actor id throughout, so a player named twice — or named and then
    swept up by `--all-players` — is compared once. Two comparisons of one
    player would mint every one of their findings twice under a single id, and
    the page would draw the pair under duplicate element ids.

    Takes the roster and the owner's name directly, rather than a `Run`, so
    `analyze` and `raid` share this one resolver instead of each keeping their
    own copy -- a `Run` and an `Encounter` each expose a roster and an owner
    name, and nothing here reads either aggregate beyond that.
    """
    for name in requested:
        if not name:
            raise ValueError(f"{name!r} is not a name. {_roster_hint(names)}")

    subject = _resolve_player(players, owner_name, requested[0] if requested else None, names)
    named = [subject] + [
        _resolve_player(players, owner_name, name, names) for name in requested[1:]
    ]
    by_actor = {player.actor_id: player for player in named}
    if everyone:
        for player in players:
            by_actor.setdefault(player.actor_id, player)
    return subject, tuple(by_actor.values())


def _record(
    row: SpeedRow | ParseRow,
    axis: str,
    *,
    loaded: bool,
    reason: str = "",
    from_cache: bool = False,
    player_slug: str = "",
    player_name: str = "",
) -> ReferenceRecord:
    """One leaderboard row's outcome, in the shape the report is allowed to keep forever.

    `row` gives up only its code, fight and level — never the team, the
    character name or the score a `SpeedRow`/`ParseRow` also carries, which is
    what keeps a `ReferenceRecord` a link rather than a tabulation of another
    player's run.

    `player_slug` and `player_name` name whose comparison weighed the row, the
    first for matching and the second for reading. Both are empty on the speed
    axis, which is drawn once for the run rather than per player.
    """
    return ReferenceRecord(
        report_code=row.report_code,
        fight_id=row.fight_id,
        keystone_level=row.keystone_level,
        url=REPORT_URL.format(code=row.report_code, fight=row.fight_id),
        axis=axis,
        loaded=loaded,
        reason=reason,
        from_cache=from_cache,
        player_slug=player_slug,
        player_name=player_name,
    )


class RequestedPlayer(NamedTuple):
    """One player a comparison was asked for, and the two strings that name them.

    A bare tuple would put `slug` and `name` side by side as two positional
    strings of the same type, and a caller that swapped them would type-check
    cleanly: the slug would be printed to a reader and the display name stamped
    onto a `ReferenceRecord`, the record the RPGLogs terms section 5d posture
    rests on.
    """

    player: Player
    slug: str
    name: str


def _samples(
    rankings: WclRankingRepository,
    runs: WclRunRepository,
    run: Run,
    subjects: Sequence[RequestedPlayer],
) -> tuple[SpeedSample, dict[int, ParseSample], tuple[ReferenceRecord, ...]]:
    """Up to `SAMPLE_SIZE` references per axis, and a record of every row weighed.

    Each subject arrives as the player, their slug and the name the page
    spells them by. The caller mints both, and this loop only stamps them
    onto the parse records it keeps: computing either here would be a second
    source of a player's identity, and the two could then disagree.

    The speed axis is drawn once, for the run: the route and the tempo are
    facts about the group, and every player is measured against the same fast
    completions. The parse axis is drawn once per subject, because a
    specialisation's leaderboard is the only place its own references live —
    so the result is keyed by actor id, and a player's sample is theirs alone.
    A subject whose specialisation never arrived in the log is not asked
    about: `specName: ""` matches no row at any keystone level, so the whole
    widening loop of queries would be paid for nothing, and
    `compare.parse.unavailable` says why their card is empty.

    A row is skipped, never fatal, for three reasons, and every one of them is
    recorded rather than silently dropped: it is our own report and fight
    (comparing a run against itself would report a perfect route and teach the
    reader nothing); its report failed to load — deleted, private, an
    unfinished fight, or a roster gap in its master data; or, once loaded, its
    roster names one of our own characters. That last check can only run after
    the load, because the roster arrives with the run and not with the
    leaderboard row — so a self-match still costs one fetch. The alternative is
    worse: at `SAMPLE_SIZE` references instead of one, a reference that is
    quietly the analysed player's own other run is no longer a rounding error,
    and "the fast runs did this" would be a small lie if one of them is you.

    The leaderboard query itself is not guarded here: a `BracketMismatch` there
    means the bracket convention this tool relies on has changed, and that
    must still stop the command.

    Each speed member's `Comparability` and pull alignment are built once,
    here, and stored on the member — not recomputed by whatever renders the
    sample afterwards.
    """
    our_names = frozenset(player.name.casefold() for player in run.players)
    records: list[ReferenceRecord] = []

    speed_members: list[SpeedMember] = []
    for row in rankings.fastest_runs(run.encounter_id, run.keystone_level, minimum=SAMPLE_SIZE):
        if len(speed_members) >= SAMPLE_SIZE:
            break
        if row.report_code == run.report_code and row.fight_id == run.fight_id:
            records.append(
                _record(row, "speed", loaded=False, reason="this is the run under analysis")
            )
            continue
        try:
            theirs, from_cache = runs.load_speed_reference(row.report_code, row.fight_id)
        except (IngestError, WclError) as error:
            records.append(_record(row, "speed", loaded=False, reason=str(error)))
            continue
        if any(player.name.casefold() in our_names for player in theirs.run.players):
            records.append(
                _record(
                    row,
                    "speed",
                    loaded=True,
                    reason="the roster includes one of our own characters",
                    from_cache=from_cache,
                )
            )
            continue
        records.append(_record(row, "speed", loaded=True, from_cache=from_cache))
        speed_members.append(
            SpeedMember(
                row=row,
                run=theirs.run,
                comparability=Comparability(
                    our_level=run.keystone_level, their_level=theirs.run.keystone_level
                ),
                alignment=align_pulls(run, theirs.run),
                deaths=theirs.deaths,
                enemy_cast_rows=theirs.enemy_cast_rows,
                interrupts=theirs.interrupts,
            )
        )

    parse_samples: dict[int, ParseSample] = {}
    for subject, slug, name in subjects:
        if not subject.spec:
            parse_samples[subject.actor_id] = ParseSample()
            continue
        parse_members: list[ParseMember] = []
        for parse_row in rankings.top_parses(
            run.encounter_id,
            run.keystone_level,
            subject.class_name,
            subject.spec,
            minimum=SAMPLE_SIZE,
        ):
            if len(parse_members) >= SAMPLE_SIZE:
                break
            if parse_row.report_code == run.report_code and parse_row.fight_id == run.fight_id:
                records.append(
                    _record(
                        parse_row,
                        "parse",
                        loaded=False,
                        reason="this is the run under analysis",
                        player_slug=slug,
                        player_name=name,
                    )
                )
                continue
            try:
                theirs, from_cache = runs.load_parse_reference(
                    parse_row.report_code, parse_row.fight_id
                )
            except (IngestError, WclError) as error:
                records.append(
                    _record(
                        parse_row,
                        "parse",
                        loaded=False,
                        reason=str(error),
                        player_slug=slug,
                        player_name=name,
                    )
                )
                continue
            if any(player.name.casefold() in our_names for player in theirs.run.players):
                records.append(
                    _record(
                        parse_row,
                        "parse",
                        loaded=True,
                        reason="the roster includes one of our own characters",
                        from_cache=from_cache,
                        player_slug=slug,
                        player_name=name,
                    )
                )
                continue
            records.append(
                _record(
                    parse_row,
                    "parse",
                    loaded=True,
                    from_cache=from_cache,
                    player_slug=slug,
                    player_name=name,
                )
            )
            parse_members.append(
                ParseMember(
                    row=parse_row,
                    run=theirs.run,
                    casts=theirs.casts,
                    ability_icons=theirs.ability_icons,
                )
            )
        parse_samples[subject.actor_id] = ParseSample(members=tuple(parse_members))

    return SpeedSample(members=tuple(speed_members)), parse_samples, tuple(records)


def _mechanics_record(
    row: ReferenceKillRow, *, loaded: bool, reason: str = "", from_cache: bool = False
) -> ReferenceRecord:
    """One execution-leaderboard kill's outcome, in the shape `_record` keeps for Mythic+.

    A `ReferenceKillRow` carries no keystone level at all -- a boss kill has
    none -- so `keystone_level` is written as 0 here, a value no real keystone
    level ever is, rather than reusing `size` under a field named for a
    different game mode's number.

    `player_slug` and `player_name` stay at their empty default: the mechanics
    axis is drawn once for the whole encounter, exactly as the speed axis is
    drawn once for the whole run rather than per player, so no candidate here
    was weighed for one particular player.
    """
    return ReferenceRecord(
        report_code=row.report_code,
        fight_id=row.fight_id,
        keystone_level=0,
        url=REPORT_URL.format(code=row.report_code, fight=row.fight_id),
        axis="mechanics",
        loaded=loaded,
        reason=reason,
        from_cache=from_cache,
    )


def _ability_taken(
    client: WclClient, cache: DiskCache, code: str, fight_id: int
) -> tuple[tuple[AbilityTakenRow, ...], bool]:
    """One report's raid-wide damage-taken-by-ability table, cached, and whether it hit.

    Shared by our own report and every reference kill weighed: both read
    `ABILITY_TAKEN_TABLE_QUERY`, aliased `taken`, and neither is scoped by
    `sourceID` -- `compare_mechanics`'s own evidence labels the figure "This
    raid", a statement about the whole encounter on both sides of the
    comparison, not about one player.
    """
    variables = {"code": code, "fightId": fight_id}
    payload, from_cache = cache.get_or_fetch(
        cache_key(ABILITY_TAKEN_TABLE_QUERY, variables),
        lambda: client.execute(ABILITY_TAKEN_TABLE_QUERY, variables),
    )
    return build_ability_taken_rows(payload, "taken"), from_cache


def _mechanics_sample(
    rankings: WclEncounterRankingRepository,
    client: WclClient,
    cache: DiskCache,
    encounter: Encounter,
) -> tuple[MechanicsSample, tuple[ReferenceRecord, ...]]:
    """Up to `SAMPLE_SIZE` execution-leaderboard kills of this boss, and a record of
    every one weighed.

    Mirrors `_samples`: a row naming our own report and fight is never a
    reference for it (comparing a kill against itself would report a perfect
    match and teach the reader nothing), and a row whose ability table failed
    to load is skipped, never fatal, with the reason recorded rather than
    silently dropped.

    `select_reference_kills` has already refused a size that does not match
    ours, so what reaches this loop is comparable by construction; only
    reachability is judged here. Difficulty needs no matching filter here:
    `reference_kills` already passes `encounter.difficulty` as the query's own
    argument, so every row it returns is at that difficulty already.
    """
    rows = rankings.reference_kills(
        encounter.encounter_id, encounter.difficulty, encounter.partition
    )
    selected = select_reference_kills(rows, our_size=encounter.size)

    members: list[MechanicsMember] = []
    records: list[ReferenceRecord] = []
    for row in selected:
        if row.report_code == encounter.report_code and row.fight_id == encounter.fight_id:
            records.append(
                _mechanics_record(row, loaded=False, reason="this is the run under analysis")
            )
            continue
        try:
            abilities, from_cache = _ability_taken(client, cache, row.report_code, row.fight_id)
        except (IngestError, WclError) as error:
            records.append(_mechanics_record(row, loaded=False, reason=str(error)))
            continue
        records.append(_mechanics_record(row, loaded=True, from_cache=from_cache))
        members.append(MechanicsMember(row=row, abilities=abilities))

    return MechanicsSample(members=tuple(members)), tuple(records)


def _auras(runs: WclRunRepository, code: str, fight_id: int, actor_id: int) -> PlayerAuras | None:
    """One player's auras, or None if they cannot be had.

    A failed aura fetch must not discard the whole report: everything else has
    already been fetched and paid for, and `compare.uptime.unavailable` states
    the gap rather than hiding it. `httpx.HTTPError` covers a non-2xx aura
    response that is not itself a rate limit: `WclClient.execute` raises
    `RateLimitExceeded` (a `WclError`) for 429 before it ever calls
    `raise_for_status`, so that deliberate handling still goes through the
    `WclError` branch above and is untouched by the wider catch here.
    """
    try:
        return runs.auras(code, fight_id, actor_id)
    except (IngestError, WclError, httpx.HTTPError):
        return None


def load_run_with_auras(
    runs: WclRunRepository, code: str, fight_id: int, loaded: LoadedRun
) -> LoadedRun:
    """The run, with every roster player's buff bands attached.

    One `AuraTable` query per player, measured at about 1.06 points
    (`.claude/skills/wcl-api/SKILL.md`). A player whose parse comparison
    already fetched theirs costs nothing the second time: our own run's cached
    responses never expire. A player whose fetch fails simply has no bands, and
    the drawings that read them draw nothing rather than guessing a window.
    """
    fetched = tuple(
        one
        for one in (
            _auras(runs, code, fight_id, player.actor_id) for player in loaded.run.players
        )
        if one is not None
    )
    return loaded.model_copy(update={"auras": fetched})


def _fetch_parse_auras(
    sample: ParseSample,
    ours: WclRunRepository,
    references: WclRunRepository,
    our_run: Run,
    subject: Player,
) -> tuple[ParseSample, PlayerAuras | None]:
    """Every parse member's own aura data, and our own side's, fetched at most once.

    A member's counterpart is resolved from that member's own roster,
    `find_player(member.run.players, member.row.character_name)`, before paying for
    its aura query: when the reference's own roster does not contain the
    player its leaderboard row names, `find_player` can never resolve them,
    and fetching first would pay for a query with no use. A member whose
    counterpart cannot be resolved, or whose aura fetch fails (`_auras`
    returns `None`), keeps `auras=None` — `compare_uptime_sample` already
    states how many references had no aura data, rather than the whole
    comparison being discarded.

    `our_auras` is our own player's data, shared across every member inside
    `compare_uptime_sample` — not a per-member fetch — so it is fetched
    exactly once, the first time any counterpart resolves at all. A sample in
    which no member's counterpart resolves fetches it not at all.
    """
    our_auras: PlayerAuras | None = None
    our_auras_fetched = False
    updated_members: list[ParseMember] = []
    for member in sample.members:
        their_player = find_player(member.run.players, member.row.character_name)
        if their_player is None:
            updated_members.append(member)
            continue
        if not our_auras_fetched:
            our_auras = _auras(ours, our_run.report_code, our_run.fight_id, subject.actor_id)
            our_auras_fetched = True
        updated_members.append(
            member.model_copy(
                update={
                    "auras": _auras(
                        references,
                        member.row.report_code,
                        member.row.fight_id,
                        their_player.actor_id,
                    )
                }
            )
        )
    return sample.model_copy(update={"members": tuple(updated_members)}), our_auras


def _parse_sample_size(subject: ComparisonSubject) -> int:
    """How many parse references this player's comparison actually drew.

    A sample nobody could fill and a sample never drawn read the same to a
    reader — the leaderboard offered nothing — so both count zero.
    """
    return len(subject.parse.members) if subject.parse else 0


def _narrative_digits_message(path: Path, offending: tuple[tuple[int, str], ...]) -> str:
    """Explain the rule once, then list every line that breaks it."""
    lines = "\n".join(f"  line {number}: {line}" for number, line in offending)
    return (
        f"{path}: the narrative states no numbers — the figures live in the "
        f"report's own sections, directly below it.\n{lines}"
    )


@app.command()
def analyze(
    report: str = typer.Argument(..., help="Report URL or code"),
    fight: int | None = typer.Option(None, help="Fight ID; defaults to the only keystone run"),
    throughput_ceiling: bool = typer.Option(
        False,
        "--throughput-ceiling",
        help="Also report throughput cooldowns used far below what their cooldown allowed",
    ),
    player: list[str] = typer.Option(
        [],
        "--player",
        help="Compare this player against top parses of their specialisation. "
        "Repeatable; the first one given is the report's subject. "
        "Defaults to the report owner.",
    ),
    all_players: bool = typer.Option(
        False,
        "--all-players",
        help="Compare every player in the run, not only the subject",
    ),
    no_compare: bool = typer.Option(
        False, "--no-compare", help="Skip both reference runs and analyse in isolation"
    ),
    narrative: Path | None = typer.Option(
        None, help="Plain text notes to render as the report's interpretation section"
    ),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Where to cache API responses"),
    out: Path = typer.Option(Path("out"), help="Where to write the findings JSON and HTML report"),
) -> None:
    """Analyse a Mythic+ run and write its findings as JSON and an HTML report."""
    # See the matching comment on `fetch`: Windows gives the process a
    # locale-dependent stdout encoding that cannot hold non-ASCII names.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        # Read this before anything is fetched: a typo in the path must cost
        # nothing, and must never quietly produce a report with no narrative.
        narrative_text = None
        if narrative:
            try:
                narrative_text = narrative.read_text(encoding="utf-8")
            except UnicodeDecodeError as error:
                # UnicodeDecodeError's own message never names the file it came
                # from, so a bad-encoding narrative would otherwise print a
                # codec complaint with no way to tell which path caused it.
                raise ValueError(f"{narrative}: {error}") from error

            offending = lines_with_digits(narrative_text)
            if offending:
                raise ValueError(_narrative_digits_message(narrative, offending))

        code, fight_from_url = parse_report_url(report)
        repository = build_repository(cache_dir)
        before = repository.rate_limit()
        loaded = repository.load(code, fight if fight is not None else fight_from_url)
        # Fetched here, once, so the comparison below and the report builder
        # after it both see the same LoadedRun -- a --no-compare report still
        # gets its own roster's cover windows.
        loaded = load_run_with_auras(repository, code, loaded.run.fight_id, loaded)
        # Loaded once and shared: the analysers and the death cards must read
        # the same cooldowns, or the page and the findings disagree.
        defensives = load_defensives()
        consumables = load_consumables()
        throughput = load_throughput_cooldowns()
        findings = analyse(
            loaded,
            load_season_data(),
            defensives,
            consumables,
            throughput,
            roles=load_roles(),
            include_cooldown_ceiling=throughput_ceiling,
        )

        # The roster's own spelling, disambiguated where two members share a
        # name, computed once and read by everything that names a player: the
        # names `--player` accepts, the roster a refusal lists, and the name
        # stamped onto every comparison subject below. One mapping rather than
        # three calls, so a finding's title, a card heading, a provenance row
        # and the argument that asked for them cannot spell a player
        # differently.
        names = display_names(loaded.run.players)
        subject, to_compare = _resolve_requested(
            loaded.run.players, loaded.run.owner_name, player, all_players, names
        )
        speed_sample: SpeedSample | None = None
        # Everyone the comparison was asked for: the subject, then the order
        # the reader named the rest, then whoever `--all-players` swept up.
        # That is not the order the cards come in -- those are the subject
        # first and the roster's own order behind -- so nothing may read this
        # sequence as a card order. It is the one source for *who* was
        # compared: the slugs stamped onto the findings, the slugs the report
        # matches cards by, the JSON's own list, the per-player sample sizes
        # and the page's icons are all read off it, so none of them can drift
        # from another. Empty means the comparison did not run.
        subjects: list[ComparisonSubject] = []
        compared_slugs: frozenset[str] | None = None
        reference_records: tuple[ReferenceRecord, ...] = ()
        tables: dict[str, PlayerMeasures] = {}
        if not no_compare:
            rankings, references = build_reference_repositories(repository.client, cache_dir)
            # The only place this command mints a slug: the comparison stamps a
            # player's slug onto every finding it emits about them, and the report
            # matches their card by it. The name beside it is `names`' spelling,
            # so a provenance row naming a player names the same one their card
            # does -- and the same one `--player` would have to be given.
            slugs = slugs_by_actor(loaded.run)
            requested: tuple[RequestedPlayer, ...] = tuple(
                RequestedPlayer(
                    player=one, slug=slugs[one.actor_id], name=names[one.actor_id]
                )
                for one in to_compare
            )
            # Every candidate `_samples` weighed comes back as `reference_records`,
            # carried onto both the report's provenance below and the comparison
            # block of the findings JSON.
            speed_sample, parse_samples, reference_records = _samples(
                rankings, references, loaded.run, requested
            )

            for player_to_compare, slug, name in requested:
                sample, our_auras = _fetch_parse_auras(
                    parse_samples[player_to_compare.actor_id],
                    repository,
                    references,
                    loaded.run,
                    player_to_compare,
                )
                subjects.append(
                    ComparisonSubject(
                        player=player_to_compare,
                        slug=slug,
                        display_name=name,
                        parse=sample,
                        our_auras=our_auras,
                    )
                )
            compared_slugs = frozenset(one.slug for one in subjects)

            findings += compare(ours=loaded, speed=speed_sample, subjects=subjects)
            tables = comparison_measures(ours=loaded, subjects=subjects)
            findings = rank_findings(findings)
        after = repository.rate_limit()
    except (ValueError, WclError, httpx.HTTPError, OSError) as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    run = loaded.run
    payload = {
        "report_code": run.report_code,
        "fight_id": run.fight_id,
        "dungeon_name": run.dungeon_name,
        "keystone_level": run.keystone_level,
        "keystone_time_seconds": run.keystone_time_seconds,
        "in_time": run.keystone_bonus >= 1,
        "player": subject.name,
        "comparison": {
            "compared": bool(
                (speed_sample and speed_sample.members)
                or any(_parse_sample_size(one) for one in subjects)
            ),
            # Who was compared, subject first. An empty list says nobody was
            # asked for, which a reader can now tell from a leaderboard that
            # had nothing to offer without inspecting the findings.
            "players": [one.slug for one in subjects],
            "sample_size": {
                "speed": len(speed_sample.members) if speed_sample else 0,
                # The parse axis is drawn once per player, so its size is a
                # figure per player: one number could only ever describe one
                # of them, and would under-report the rest.
                "parse": {one.slug: _parse_sample_size(one) for one in subjects},
            },
            "references": [
                {
                    "axis": record.axis,
                    "report_code": record.report_code,
                    "fight_id": record.fight_id,
                    "keystone_level": record.keystone_level,
                    "url": record.url,
                    "loaded": record.loaded,
                    "reason": record.reason,
                    "from_cache": record.from_cache,
                    "player_slug": record.player_slug,
                    "player_name": record.player_name,
                }
                for record in reference_records
            ],
        },
        "findings_are_ranked_not_additive": FINDINGS_ARE_RANKED_NOT_ADDITIVE,
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "comparison_tables": {
            slug: measured.model_dump(mode="json") for slug, measured in tables.items()
        },
    }

    written = out / f"{run.report_code}-{run.fight_id}.findings.json"
    report_file = out / f"{run.report_code}-{run.fight_id}.html"
    # A guard of its own, because this phase fails differently from the one
    # above: nothing here can be degraded or retried, and a failure can arrive
    # after the findings have been written and announced. `OSError` alone --
    # the API errors the first block names cannot reach a filesystem write.
    try:
        out.mkdir(parents=True, exist_ok=True)
        # Real rosters contain non-ASCII names; write_text's default encoding is
        # locale-dependent (commonly cp1252 on Windows) and would raise on them.
        written.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        typer.echo(f"{len(findings)} findings written to {written}")

        report_file.write_text(
            render(
                build_report(
                    loaded,
                    findings,
                    speed_sample,
                    compared_slugs,
                    subject,
                    narrative_text,
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    defensives,
                    consumables,
                    externals=load_externals(),
                    self_resurrections=load_self_resurrections(),
                    throughput=throughput,
                    reference_records=reference_records,
                    comparison_measures=tables,
                ),
                icons=build_icons(
                    loaded,
                    tuple(one.parse for one in subjects if one.parse is not None),
                ),
            ),
            encoding="utf-8",
        )
    except OSError as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    typer.echo(f"report written to {report_file}")
    typer.echo(_quota_sentence(before, after), err=True)
    _echo_cost_breakdown(repository.client.costs)


@app.command()
def raid(
    report: str = typer.Argument(..., help="Report URL or code"),
    fight: int | None = typer.Option(None, help="Fight ID; defaults to the only boss fight"),
    player: list[str] = typer.Option(
        [],
        "--player",
        help="Analyse this player as the report's subject. Repeatable; the first "
        "one given is the subject and the rest are named alongside it. "
        "Defaults to the report owner.",
    ),
    all_players: bool = typer.Option(
        False,
        "--all-players",
        help="Compare every player in the run, not only the subject",
    ),
    no_compare: bool = typer.Option(
        False, "--no-compare", help="Skip the reference kills and analyse this fight in isolation"
    ),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Where to cache API responses"),
    out: Path = typer.Option(Path("out"), help="Where to write the findings JSON"),
) -> None:
    """Analyse a raid boss fight and write its findings as JSON.

    A sibling of `analyze`, not a mode of it. A boss fight carries no keystone
    timer, no enemy-forces requirement and no pulls worth ranking a throughput
    cooldown against, so the two flags that need one are not offered here at
    all -- not disabled, simply absent. `--player`, `--all-players` and
    `--no-compare` behave as they do for `analyze`: they choose the report's
    subject and who else is named alongside it, and `--no-compare` skips the
    execution-leaderboard sample the mechanics comparison draws on.

    The mechanics comparison itself is drawn once for the whole encounter, not
    per player -- `compare_mechanics` states its own figure "This raid", the
    same way `analyze`'s speed axis is compared once for the whole run rather
    than per subject. `--player` and `--all-players` decide who the report's
    subject is and who is named in the findings file's `comparison.players`;
    they do not narrow which ability-taken table feeds the comparison.
    """
    # See the matching comment on `fetch`: Windows gives the process a
    # locale-dependent stdout encoding that cannot hold non-ASCII names.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        code, fight_from_url = parse_report_url(report)
        repository = build_repository(cache_dir)
        before = repository.rate_limit()
        loaded = repository.load_encounter(code, fight if fight is not None else fight_from_url)
        # Loaded once and shared, exactly as `analyze` shares them between its
        # analysers and its report builder -- there is no report builder here
        # yet, but a later plan that adds one must still read the same data
        # this command already paid for.
        defensives = load_defensives()
        consumables = load_consumables()

        encounter = loaded.encounter
        # The roster's own spelling, computed once and read by everything that
        # names a player below -- see the matching comment in `analyze`.
        names = display_names(encounter.players)
        subject, to_compare = _resolve_requested(
            encounter.players, encounter.owner_name, player, all_players, names
        )

        mechanics_sample = MechanicsSample()
        our_abilities: tuple[AbilityTakenRow, ...] = ()
        reference_records: tuple[ReferenceRecord, ...] = ()
        if not no_compare:
            transient = DiskCache(
                cache_dir / REFERENCE_CACHE_SUBDIR, max_age_seconds=REFERENCE_CACHE_SECONDS
            )
            encounter_rankings = WclEncounterRankingRepository(repository.client, transient)
            mechanics_sample, reference_records = _mechanics_sample(
                encounter_rankings, repository.client, transient, encounter
            )
            # Our own report's responses never expire, so this is cached
            # beside every other query `load_encounter` already issued for it,
            # not in the transient store the reference kills' tables share.
            our_abilities, _ = _ability_taken(
                repository.client, repository.cache, encounter.report_code, encounter.fight_id
            )

        findings = analyse_encounter(
            loaded,
            defensives,
            consumables,
            roles=load_roles(),
            mechanics=mechanics_sample,
            our_abilities=our_abilities,
        )
        after = repository.rate_limit()
    except (ValueError, WclError, httpx.HTTPError, OSError) as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    payload = {
        "report_code": encounter.report_code,
        "fight_id": encounter.fight_id,
        "boss_name": encounter.boss_name,
        "difficulty": encounter.difficulty,
        "partition": encounter.partition,
        "size": encounter.size,
        "kill": encounter.kill,
        "fight_percentage": encounter.fight_percentage,
        "duration_seconds": encounter.duration_seconds,
        "player": subject.name,
        "comparison": {
            "compared": bool(mechanics_sample.members),
            # Who `--player`/`--all-players` named, subject first -- the same
            # promise `analyze`'s own "players" list keeps. Empty only when
            # nobody could be named at all, which never happens here: the
            # subject always resolves to at least the report owner.
            "players": [names[one.actor_id] for one in to_compare],
            "sample_size": {"mechanics": len(mechanics_sample.members)},
            "references": [
                {
                    "axis": record.axis,
                    "report_code": record.report_code,
                    "fight_id": record.fight_id,
                    "keystone_level": record.keystone_level,
                    "url": record.url,
                    "loaded": record.loaded,
                    "reason": record.reason,
                    "from_cache": record.from_cache,
                    "player_slug": record.player_slug,
                    "player_name": record.player_name,
                }
                for record in reference_records
            ],
        },
        "findings_are_ranked_not_additive": RAID_FINDINGS_ARE_RANKED_NOT_ADDITIVE,
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "comparison_tables": {},
    }

    written = out / f"{encounter.report_code}-{encounter.fight_id}.findings.json"
    # A guard of its own, because this phase fails differently from the one
    # above: nothing here can be degraded or retried, and a failure can arrive
    # after the findings have been computed. `OSError` alone -- the API
    # errors the first block names cannot reach a filesystem write.
    try:
        out.mkdir(parents=True, exist_ok=True)
        # Real rosters contain non-ASCII names; write_text's default encoding is
        # locale-dependent (commonly cp1252 on Windows) and would raise on them.
        written.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    typer.echo(f"{len(findings)} findings written to {written}")
    typer.echo(_quota_sentence(before, after), err=True)
    _echo_cost_breakdown(repository.client.costs)


if __name__ == "__main__":
    app()
