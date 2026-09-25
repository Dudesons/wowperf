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
    load_consumable_buffs,
    load_consumables,
    load_defensives,
    load_externals,
    load_roles,
    load_season_data,
    load_self_resurrections,
    load_slot_names,
    load_throughput_cooldowns,
)
from wowperf.adapters.render.html import render, render_night, render_progression, render_raid
from wowperf.adapters.render.icons import CdnIcons
from wowperf.adapters.wcl.ability_tables import build_ability_taken_rows
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import RateLimit, WclClient
from wowperf.adapters.wcl.cost import CostLedger
from wowperf.adapters.wcl.damage_tables import build_target_rows
from wowperf.adapters.wcl.encounter_rankings import WclEncounterRankingRepository
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.ingest import IngestError
from wowperf.adapters.wcl.queries import ABILITY_TAKEN_TABLE_QUERY, DAMAGE_DONE_TARGETS_QUERY
from wowperf.adapters.wcl.ranking_repository import WclRankingRepository
from wowperf.adapters.wcl.repository import RaidReference, WclRunRepository
from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.analysis.progression_service import analyse_progression
from wowperf.domain.analysis.roster import display_names
from wowperf.domain.analysis.service import analyse
from wowperf.domain.analysis.severity import rank_raid_findings
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
from wowperf.domain.comparison.parse_axis import ParseSubject
from wowperf.domain.comparison.raid_reference import RaidParseRow
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
from wowperf.domain.comparison.spells import boss_seconds
from wowperf.domain.comparison.tables import comparison_measures
from wowperf.domain.comparison.targets import TargetRow
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.findings import rank_findings
from wowperf.domain.model import LoadedRun, Player, Run
from wowperf.domain.report.build import build_report
from wowperf.domain.report.model import ReferenceRecord
from wowperf.domain.report.narrative import lines_with_digits
from wowperf.domain.report.night_build import build_night_report
from wowperf.domain.report.players import slugs_by_actor
from wowperf.domain.report.progression_build import build_progression_report
from wowperf.domain.report.raid_build import build_raid_report
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
    "findings are ranked by severity, and their seconds are not additive: "
    "deaths.single.*, deaths.chain.* and deaths.repeat.* all nest inside "
    "deaths.total; severity decides the order and seconds_lost sorts only within "
    "one family, so this order must not be read as a ranking by time"
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

The ordering rule differs from the Mythic+ sibling's, so this one states its
own rather than borrowing the wording: `analyse_encounter` ranks with
`rank_raid_findings`, which sorts by finding family before it ever looks at
`seconds_lost`, where `rank_findings` orders by time alone. A reader who read
`FINDINGS_ARE_RANKED_NOT_ADDITIVE` first and carried its rule across would take
a mechanics finding outranking a longer death for a mistake in the seconds,
when it is the severity table doing exactly what it is for.
"""

PROGRESSION_FINDINGS_ARE_RANKED_NOT_ADDITIVE = (
    "Findings are ranked by severity, never summed. No figure here is a "
    "share of another, and the night's shape is stated as a median and a "
    "range rather than as a trend."
)
"""Why the figures in a progression findings file must never be summed.

A third sibling, not a reuse of either warning above: `analyse_progression`
reads fight metadata only and sets `seconds_lost` on no finding at all, so
there is no nesting to name the way the Mythic+ and raid warnings each do.
What this states instead is the one thing a reader could still get wrong --
that the median and the range progression.cluster reports are a summary of
where attempts sat, never a trend a slope could be drawn through.
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


def _aura_icons(auras: PlayerAuras | None) -> dict[int, str]:
    """An aura table's own art, keyed by id, skipping any row it named none for.

    The aura table is the only source for a passive talent's icon: a
    permanently applied aura is never cast, so its id reaches no cast
    dictionary. An empty name is not a file name and is left out rather than
    addressed, which draws a clean gap instead of a broken image.
    """
    if auras is None:
        return {}
    return {aura.ability_id: aura.icon for aura in auras.on_self if aura.icon}


def build_icons(
    loaded: LoadedRun | LoadedEncounter,
    parse_samples: Sequence[ParseSample],
    our_auras: Sequence[PlayerAuras | None] = (),
) -> CdnIcons:
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
            names.update(_aura_icons(member.auras))
    for auras in our_auras:
        names.update(_aura_icons(auras))
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
                    character_name=parse_row.character_name,
                    report_code=parse_row.report_code,
                    fight_id=parse_row.fight_id,
                    boss_seconds=boss_seconds(theirs.run.pulls),
                    players=theirs.run.players,
                    casts=theirs.casts,
                    ability_icons=theirs.ability_icons,
                    pulls=theirs.run.pulls,
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

    Every size-matching row is offered to the loop, which breaks once it holds
    `SAMPLE_SIZE` members -- `_samples`' own shape, and for its reason: slicing
    to `SAMPLE_SIZE` first would let each discard shrink the sample instead of
    being refilled from the rows behind it. Measured 2026-09-14, size-matching
    rows are scarce (none on one live kill's page, two on a wipe's), so losing
    one to a self-match is most of a sample. The break still caps the fetches:
    at most `SAMPLE_SIZE` tables are loaded successfully, plus whatever failed.

    `select_reference_kills` has already refused a size that does not match
    ours, so what reaches this loop is comparable by construction; only
    reachability is judged here. Difficulty needs no matching filter here:
    `reference_kills` already passes `encounter.difficulty` as the query's own
    argument, so every row it returns is at that difficulty already.
    """
    rows = rankings.reference_kills(
        encounter.encounter_id, encounter.difficulty, encounter.partition
    )
    selected = select_reference_kills(rows, our_size=encounter.size, limit=None)

    members: list[MechanicsMember] = []
    records: list[ReferenceRecord] = []
    for row in selected:
        if len(members) >= SAMPLE_SIZE:
            break
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


DAMAGE_METRICS = ("dps", "bossdps")
"""The two throughput metrics a raid comparison reports, in the order it reports them.

Both, because a reader given one figure cannot tell which it is: measured
2026-09-14, the same tank read 59991.46 under `dps` and 44818.48 under
`bossdps`. A statement about what this command reads, not about what it found --
`comparison.compared` and `comparison.sample_size` say that.
"""

SAMPLE_BOARD = "dps"
"""Which of the two boards the reference kills themselves are drawn from.

The boards are not a reordering of each other -- measured 2026-09-14, their top
rows are different reports entirely -- so drawing a sample from each would be
two samples and twice the fetching. One is drawn, and the findings file says
which, rather than leaving a reader to assume.
"""


def _damage_targets(
    client: WclClient, cache: DiskCache, code: str, fight_id: int, actor_id: int
) -> tuple[tuple[TargetRow, ...], bool]:
    """One player's damage-done table split by target, cached, and whether it hit.

    Scoped to one subject by `sourceID`, and one query per subject rather than
    one for the roster: a `viewBy: Target` table's nested arrays cap at five
    rows, so an unscoped call could not answer for twenty players (design
    section 14 item 6).

    Shared by our own report and every reference kill weighed, exactly as
    `_ability_taken` is -- what differs between the two sides is which cache
    they are stored in, which is the caller's decision and not this one's.
    """
    variables = {"code": code, "fightId": fight_id, "sourceId": actor_id}
    payload, from_cache = cache.get_or_fetch(
        cache_key(DAMAGE_DONE_TARGETS_QUERY, variables),
        lambda: client.execute(DAMAGE_DONE_TARGETS_QUERY, variables),
    )
    return build_target_rows(payload, "targets"), from_cache


def _parse_record(
    row: RaidParseRow, *, loaded: bool, reason: str = "", from_cache: bool = False
) -> ReferenceRecord:
    """One raid parse-leaderboard row's outcome, in `_record`'s own shape.

    `keystone_level` is written as 0, for `_mechanics_record`'s reason: a boss
    kill has none, and a raid row's `bracketData` is not one either -- measured
    2026-09-14 it reads 319 to 325, and what it means is unverified.

    `player_slug` and `player_name` stay at their empty default. A raid parse
    sample is drawn once per class-and-specialisation pair and shared by every
    subject of that pair, so no candidate here was weighed for one particular
    player -- unlike the Mythic+ parse axis, where a sample belongs to one
    subject and the record says whose.
    """
    return ReferenceRecord(
        report_code=row.report_code,
        fight_id=row.fight_id,
        keystone_level=0,
        url=REPORT_URL.format(code=row.report_code, fight=row.fight_id),
        axis="parse",
        loaded=loaded,
        reason=reason,
        from_cache=from_cache,
    )


class _SpecReferences(NamedTuple):
    """Everything drawn for one class-and-specialisation pair, shared by its players.

    Two players of one specialisation read the same leaderboards and the same
    reference kills; only their own side differs. Keeping the shared half in one
    value is what makes "one sample per specialisation, not one per player" a
    property of the code rather than of a comment.

    `targets` is index-aligned with `sample.members`: each entry is that
    member's own subject's per-target table, never the reference raid's.
    """

    board: tuple[RaidParseRow, ...] = ()
    boss_board: tuple[RaidParseRow, ...] = ()
    sample: ParseSample = ParseSample()
    targets: tuple[tuple[TargetRow, ...], ...] = ()


def _draw_spec_references(
    rankings: WclEncounterRankingRepository,
    references: WclRunRepository,
    encounter: Encounter,
    class_name: str,
    spec: str,
    records: list[ReferenceRecord],
) -> _SpecReferences:
    """Both boards for one specialisation, and up to `SAMPLE_SIZE` kills off the first.

    Mirrors `_samples`' parse half, and skips a row for the same three reasons,
    each recorded rather than silently dropped: it is our own report and fight,
    its report failed to load, or its roster names one of our own characters.
    That last check can only run after the load, because the roster arrives with
    the fight and not with the leaderboard row -- so a self-match still costs
    one fetch, and the alternative is comparing a raid against itself.

    Every row is offered to the loop, which breaks once it holds `SAMPLE_SIZE`
    members, for `_mechanics_sample`'s reason: slicing first would let each
    discard shrink the sample instead of being refilled from the rows behind it.

    The boards are not filtered by raid size. Measured 2026-09-14, our own raid
    was 20 and the top five parse references ran 22 to 30 while the full board
    ran 11 to 30, so a size filter would empty most samples; design section 14.1
    records the confound this leaves standing, and `compare_damage_total`
    medians the board exactly as it arrives.
    """
    board = rankings.top_parses(
        encounter.encounter_id, encounter.difficulty, encounter.partition,
        class_name, spec, "dps",
    )
    boss_board = rankings.top_parses(
        encounter.encounter_id, encounter.difficulty, encounter.partition,
        class_name, spec, "bossdps",
    )

    our_names = frozenset(player.name.casefold() for player in encounter.players)
    members: list[ParseMember] = []
    targets: list[tuple[TargetRow, ...]] = []
    for row in board:
        if len(members) >= SAMPLE_SIZE:
            break
        if row.report_code == encounter.report_code and row.fight_id == encounter.fight_id:
            records.append(
                _parse_record(row, loaded=False, reason="this is the run under analysis")
            )
            continue
        try:
            theirs, from_cache = references.load_raid_parse_reference(
                row.report_code, row.fight_id
            )
        except (IngestError, WclError) as error:
            records.append(_parse_record(row, loaded=False, reason=str(error)))
            continue
        if any(player.name.casefold() in our_names for player in theirs.players):
            records.append(
                _parse_record(
                    row,
                    loaded=True,
                    reason="the roster includes one of our own characters",
                    from_cache=from_cache,
                )
            )
            continue
        records.append(_parse_record(row, loaded=True, from_cache=from_cache))
        members.append(
            ParseMember(
                character_name=row.character_name,
                report_code=row.report_code,
                fight_id=row.fight_id,
                # The leaderboard row's own `duration`, not the fight's
                # timestamps: the row is what named this kill, and reading the
                # length twice is two places for one fact to be got from.
                boss_seconds=row.duration_seconds,
                players=theirs.players,
                casts=theirs.casts,
                ability_icons=theirs.ability_icons,
                auras=_reference_auras(references, row, theirs),
            )
        )
        targets.append(_reference_targets(references, row, theirs))

    return _SpecReferences(
        board=board,
        boss_board=boss_board,
        sample=ParseSample(members=tuple(members)),
        targets=tuple(targets),
    )


def _reference_actor(row: RaidParseRow, theirs: RaidReference) -> Player | None:
    """The reference's own subject, resolved from its own roster.

    Resolved before either per-actor query is paid for: a reference whose roster
    does not name the character its leaderboard row names can never be scoped to
    them, and fetching first would buy two tables with no use. That member still
    counts toward the sample, with no auras and no target table -- dropping it
    would let a title name more references than it measured.
    """
    return find_player(theirs.players, row.character_name)


def _reference_auras(
    references: WclRunRepository, row: RaidParseRow, theirs: RaidReference
) -> PlayerAuras | None:
    their_player = _reference_actor(row, theirs)
    if their_player is None:
        return None
    return _auras(references, row.report_code, row.fight_id, their_player.actor_id)


def _reference_targets(
    references: WclRunRepository, row: RaidParseRow, theirs: RaidReference
) -> tuple[TargetRow, ...]:
    """One reference's per-target table, or nothing where it cannot be had.

    A failure is not fatal and is not recorded as a lost reference either: the
    member is still compared on every other family, and `compare_targets` reads
    an empty table as a reference with no boss row rather than as a zero share.
    """
    their_player = _reference_actor(row, theirs)
    if their_player is None:
        return ()
    try:
        rows, _ = _damage_targets(
            references.client, references.cache,
            row.report_code, row.fight_id, their_player.actor_id,
        )
    except (IngestError, WclError, httpx.HTTPError):
        return ()
    return rows


def _parse_samples(
    rankings: WclEncounterRankingRepository,
    ours: WclRunRepository,
    references: WclRunRepository,
    loaded: LoadedEncounter,
    subjects: Sequence[Player],
    names: Mapping[int, str],
) -> tuple[tuple[ParseSubject, ...], tuple[ReferenceRecord, ...]]:
    """One external frame per subject, and a record of every reference weighed.

    Drawn once per distinct `(class_name, spec)` pair and shared by every
    subject of it, because a leaderboard belongs to a specialisation and not to
    a player: measured 2026-09-14, a twenty-player roster held nineteen distinct
    pairs, so the saving is small in the worst case and free to have.

    Nothing is fetched for an attempt that did not kill. Every family of this
    axis reads either this report's own rankings row or a sample drawn to stand
    beside it, and a wipe has no row -- `compare_parse_axis` withholds the whole
    frame in one sentence, so a board, five reference reports and their tables
    would be paid for and then discarded. The subjects are still built, or that
    sentence would never be written.

    Nothing is fetched for a player the log records no specialisation for
    either, for the reason `compare_parse_axis` states in the finding it
    returns for them: a specialisation is what a leaderboard is asked for.
    """
    encounter = loaded.encounter
    records: list[ReferenceRecord] = []
    drawn: dict[tuple[str, str], _SpecReferences] = {}
    built: list[ParseSubject] = []
    # The only place this loop mints a slug: `analyse_encounter` stamps it onto
    # every finding this subject's comparison produces, and the report matches
    # their card by it. Read from the whole roster, never from `names`' own
    # spelling -- two roster members can share a display name, and only the
    # roster index tells them apart.
    slugs = slugs_by_actor(encounter.players)

    for player in subjects:
        comparable = loaded.standing is not None and bool(player.spec)
        if comparable:
            key = (player.class_name, player.spec)
            if key not in drawn:
                drawn[key] = _draw_spec_references(
                    rankings, references, encounter, player.class_name, player.spec, records
                )
        spec_references = drawn.get((player.class_name, player.spec), _SpecReferences())
        built.append(
            ParseSubject(
                player=player,
                slug=slugs[player.actor_id],
                display_name=names[player.actor_id],
                our_auras=(
                    _auras(ours, encounter.report_code, encounter.fight_id, player.actor_id)
                    if comparable
                    else None
                ),
                sample=spec_references.sample if comparable else ParseSample(),
                board=spec_references.board if comparable else (),
                boss_board=spec_references.boss_board if comparable else (),
                our_targets=(
                    _our_targets(ours, encounter, player.actor_id) if comparable else ()
                ),
                their_targets=spec_references.targets if comparable else (),
            )
        )
    return tuple(built), tuple(records)


def _our_targets(
    ours: WclRunRepository, encounter: Encounter, actor_id: int
) -> tuple[TargetRow, ...]:
    """Our own subject's per-target table, cached beside the rest of our report.

    Not guarded: a failure here is a failure to read our own report, which is
    the same class of problem as our own ability-taken table failing, and that
    one stops the command too. Degrading would leave `compare_targets` saying
    this fight's table carried one target, which would be false of a table that
    was never read.
    """
    rows, _ = _damage_targets(
        ours.client, ours.cache, encounter.report_code, encounter.fight_id, actor_id
    )
    return rows


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


def load_encounter_with_auras(
    runs: WclRunRepository, code: str, fight_id: int, loaded: LoadedEncounter
) -> LoadedEncounter:
    """The fight, with every roster player's buff bands attached.

    One `AuraTable` query per player, about 1.06 points each, so about 21 for a
    twenty-player fight against an hourly budget of 3600. The raid path fetched
    these only for comparable parse subjects, which measured at one table for a
    twenty-player report -- and a held-or-faded answer drawn from bands is
    silent for every player without one.

    A player whose fetch fails simply has no bands, and the states that read
    them say `pressed` rather than guessing. `_auras` already swallows the
    failure for the same reason on the Mythic+ side: a report that has been
    fetched and paid for is not discarded over one player's table.
    """
    fetched = tuple(
        one
        for one in (
            _auras(runs, code, fight_id, player.actor_id) for player in loaded.players
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
    `find_player(member.players, member.character_name)`, before paying for
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
        their_player = find_player(member.players, member.character_name)
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
                        member.report_code,
                        member.fight_id,
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
        consumable_buffs = load_consumable_buffs()
        throughput = load_throughput_cooldowns()
        slot_names = load_slot_names()
        # The comparison's combat-potion family reads this one category rather
        # than all of `consumables`: `for_survival()` excludes it (it shares no
        # cooldown with a health potion), but `categories` still carries it.
        combat_potion_ids = next(
            (category.ability_ids for category in consumables.categories
             if category.name == "combat potion"),
            (),
        )
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
            slugs = slugs_by_actor(loaded.run.players)
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
                        consumable_buffs=consumable_buffs,
                        potion_ids=combat_potion_ids,
                        slot_names=slot_names,
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
                    tuple(one.our_auras for one in subjects),
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
        help="Name every player in the run in the findings file, not only the subject. "
        "The mechanics comparison is raid-wide either way.",
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
        # Fetched here, once, so every consumer below sees the same
        # LoadedEncounter -- a held-or-faded answer drawn from bands is silent
        # for a player whose table was never fetched, and the parse-subject
        # loop below only ever fetched one for a comparable subject.
        loaded = load_encounter_with_auras(repository, code, loaded.encounter.fight_id, loaded)
        # Loaded once and shared, exactly as `analyze` shares them between its
        # analysers and its report builder -- there is no report builder here
        # yet, but a later plan that adds one must still read the same data
        # this command already paid for.
        defensives = load_defensives()
        consumables = load_consumables()
        roles = load_roles()

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
        parse_subjects: tuple[ParseSubject, ...] = ()
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
            # The reference reports this axis draws go in the transient store
            # beside the reference kills': they are other players' logs, kept
            # for one comparison and expired, never warehoused.
            parse_subjects, parse_records = _parse_samples(
                encounter_rankings,
                repository,
                WclRunRepository(repository.client, transient),
                loaded,
                to_compare,
                names,
            )
            reference_records += parse_records

        compared_slugs: frozenset[str] | None = None
        if parse_subjects:
            compared_slugs = frozenset(one.slug for one in parse_subjects)

        findings = analyse_encounter(
            loaded,
            defensives,
            consumables,
            roles=roles,
            mechanics=mechanics_sample,
            our_abilities=our_abilities,
            parse_subjects=parse_subjects,
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
        # Where the partition every leaderboard was queried at came from: this
        # report's own rankings row, or the dated file that stands in when a
        # wipe leaves no row to read one off.
        "partition_source": loaded.partition_source,
        "player": subject.name,
        "comparison": {
            "compared": bool(
                mechanics_sample.members
                or any(one.sample.members for one in parse_subjects)
            ),
            # Who `--player`/`--all-players` named, subject first -- the same
            # promise `analyze`'s own "players" list keeps. Empty only when
            # nobody could be named at all, which never happens here: the
            # subject always resolves to at least the report owner.
            "players": [names[one.actor_id] for one in to_compare],
            # What this command reports throughput on, and which single board
            # its reference kills were drawn from. Both are statements about
            # the method rather than about what was found, so both stand
            # whatever the leaderboards answered.
            "metrics": list(DAMAGE_METRICS),
            "sample_board": SAMPLE_BOARD,
            "sample_size": {
                "mechanics": len(mechanics_sample.members),
                # The parse axis is drawn per specialisation and read per
                # player, so its size is a figure per player: one number could
                # only ever describe one of them.
                "parse": {
                    one.display_name: len(one.sample.members) for one in parse_subjects
                },
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
        "findings_are_ranked_not_additive": RAID_FINDINGS_ARE_RANKED_NOT_ADDITIVE,
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "comparison_tables": {},
    }

    written = out / f"{encounter.report_code}-{encounter.fight_id}.findings.json"
    report_file = out / f"{encounter.report_code}-{encounter.fight_id}.html"
    # A guard of its own, because this phase fails differently from the one
    # above: nothing here can be degraded or retried, and a failure can arrive
    # after the findings have been computed. `OSError` alone -- the API
    # errors the first block names cannot reach a filesystem write.
    try:
        out.mkdir(parents=True, exist_ok=True)
        # Real rosters contain non-ASCII names; write_text's default encoding is
        # locale-dependent (commonly cp1252 on Windows) and would raise on them.
        written.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        typer.echo(f"{len(findings)} findings written to {written}")

        report_file.write_text(
            render_raid(
                build_raid_report(
                    loaded,
                    findings,
                    subject,
                    compared_slugs,
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    defensives,
                    consumables,
                    roles=roles,
                    externals=load_externals(),
                    self_resurrections=load_self_resurrections(),
                    reference_records=reference_records,
                ),
                icons=build_icons(
                    loaded,
                    tuple(one.sample for one in parse_subjects),
                    tuple(one.our_auras for one in parse_subjects),
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
def progression(
    report: str = typer.Argument(..., help="Report URL or code"),
    boss: int | None = typer.Option(
        None, help="Encounter id; required when the report holds more than one boss"
    ),
    difficulty: int | None = typer.Option(
        None, help="Difficulty id; defaults to the boss's own first fight in the report"
    ),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Where to cache API responses"),
    out: Path = typer.Option(Path("out"), help="Where to write the findings JSON"),
) -> None:
    """Analyse a night of attempts on one raid boss and write its findings as JSON.

    A sibling of `raid`, not a mode of it: `raid` compares one fight against
    other reports' kills, while this compares a report's own attempts at one
    boss against each other, which is what makes it an order of magnitude
    cheaper -- one query answers every fight in the report's metadata at
    once, and each qualifying attempt costs one more pair of streams: its
    deaths and its damage taken. It still draws no external reference, so
    `--player`, `--all-players` and `--no-compare` do not apply here and are
    not offered.

    The page beside the findings carries five tabs -- Summary, Attempts,
    Repeats, Best attempt, Provenance -- which hold the night's shape: how deep
    each attempt got, what kept ending it, and what the deepest one did
    differently. It deliberately redraws no single attempt's anatomy: health
    curves, death cards and defensive states belong to `wowperf raid --fight
    N`, and the findings that want one carry that invocation.
    """
    # See the matching comment on `fetch`: Windows gives the process a
    # locale-dependent stdout encoding that cannot hold non-ASCII names.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        code, _ = parse_report_url(report)
        repository = build_repository(cache_dir)
        before = repository.rate_limit()
        progression = repository.load_progression(code, boss, difficulty)
        deep = repository.load_progression_attempts(progression)
        findings = rank_raid_findings(analyse_progression(deep))
        after = repository.rate_limit()
    except (ValueError, WclError, httpx.HTTPError, OSError) as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    payload = {
        "report_code": progression.report_code,
        "encounter_id": progression.encounter_id,
        "boss_name": progression.boss_name,
        "difficulty": progression.difficulty,
        "size": progression.size,
        "killed": progression.killed,
        "attempts_counted": len(progression.attempts),
        "attempts_discarded": len(progression.discarded),
        "attempts_deepened": len(deep.loaded),
        "separates_wipes": progression.separates_wipes,
        "phases": [phase.model_dump(mode="json") for phase in progression.phases],
        "findings_are_ranked_not_additive": PROGRESSION_FINDINGS_ARE_RANKED_NOT_ADDITIVE,
        "findings": [finding.model_dump(mode="json") for finding in findings],
    }

    written = out / f"{progression.report_code}-{progression.encounter_id}.progression.json"
    # A guard of its own, on the same reasoning `raid`'s write phase carries
    # one: this fails differently from the block above, and can fail after
    # the findings have already been computed.
    try:
        out.mkdir(parents=True, exist_ok=True)
        # Real rosters and boss names contain non-ASCII characters; write_text's
        # default encoding is locale-dependent (commonly cp1252 on Windows) and
        # would raise on them.
        written.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    typer.echo(f"{len(findings)} findings written to {written}")

    report_file = out / f"{progression.report_code}-{progression.encounter_id}.progression.html"
    # A second guard, for the same reason the first one exists and `raid`'s
    # write phase carries its own: rendering fails differently from fetching,
    # and it fails after the findings have already been computed and written.
    try:
        report_file.write_text(
            render_progression(
                build_progression_report(
                    deep, findings, datetime.now().strftime("%Y-%m-%d %H:%M")
                ),
                # No icons, because this command fetches none.
                # `load_progression_attempts` reads the report's ability
                # dictionary for its names and drops the icon half, so every
                # `LoadedEncounter` it builds carries an empty `ability_icons`.
                # `build_icons` over the deepest of them would hand
                # `render_progression` a `CdnIcons` that resolves nothing --
                # the same blank page, dressed as an icon source. The `ability`
                # macro renders a bare name without one, which is what the
                # Mythic+ comparison tables drew for months.
                icons=None,
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
def night(
    report: str = typer.Argument(..., help="Report URL or code"),
    deep: list[int] = typer.Option(
        [],
        "--deep",
        help="Draw this pull's whole death anatomy -- its run-up timeline and its health "
        "curve. Repeatable, and priced per pull rather than per night.",
    ),
    no_deaths: bool = typer.Option(
        False,
        "--no-deaths",
        help="Draw no death card at all, which is the cheapest tier a pull can be read at",
    ),
    difficulty: int | None = typer.Option(
        None,
        help="Difficulty id; skips any boss this report holds only at another difficulty. "
        "Defaults per boss to that boss's own first fight in the report.",
    ),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Where to cache API responses"),
    out: Path = typer.Option(Path("out"), help="Where to write the findings JSON"),
) -> None:
    """Analyse every boss fight one report holds and write them as one page.

    The fourth sibling of `analyze`, `raid` and `progression`, and the widest:
    `raid` reads one pull, `progression` one boss's pulls, this one the whole
    report. There is no `--fight`, because covering every fight is the point.

    It draws no parse axis. That sample is per player per boss, and across a
    report it would cost an order of magnitude more than everything else here
    put together -- so `--player`, `--all-players` and `--no-compare` are not
    offered, there being no per-player reference for them to widen or skip. The
    page says so once, in as many words, rather than leaving six families
    silently missing.

    What a pull costs is chosen per pull, on three rungs: `--no-deaths` draws
    no death card at all, the default trims every card to what each player had
    at the moment of death, and `--deep FIGHT` buys back the named pull's
    timeline and health curve. `--deep` and `--no-deaths` contradict each other
    and are refused together.
    """
    # See the matching comment on `fetch`: Windows gives the process a
    # locale-dependent stdout encoding that cannot hold non-ASCII names.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # Refused before the repository is built, so a contradiction costs nothing
    # at all: one flag asks for a fuller card on a named pull and the other for
    # no card anywhere, and letting either win silently would draw a night
    # nobody asked for.
    if deep and no_deaths:
        raise typer.BadParameter(
            "--deep asks for a fuller death card on a named pull and --no-deaths asks for "
            "no death card at all; pass one or the other"
        )

    # The tier, read off the flags once. Both `load_night_attempts` and
    # `build_night_report` take this pair, the first to decide what to fetch and
    # the second to decide what to draw, and neither can detect that the other
    # was handed something else: a pull fetched with no cards and drawn with one
    # renders a card with an empty timeline and no explanation on the page at
    # all. One pair of names, read here and passed to both, is what rules that
    # out; `tests/test_cli_night.py` pins it.
    deep_fights = frozenset(deep)
    death_cards = not no_deaths

    try:
        code, _ = parse_report_url(report)
        repository = build_repository(cache_dir)
        before = repository.rate_limit()
        night = repository.load_night(code, difficulty)
        # `load_night` answers a report with no boss fight with an empty
        # `Night` rather than raising, because only the command knows which
        # report was asked for. Worded as `load_progression` words the same
        # refusal, so the two siblings say one thing about one report.
        if not night.bosses:
            raise ValueError(f"Report {code} holds no boss fight")
        # `--deep` is checked against the attempts this night will actually
        # draw, not against every fight in the report: an id that names a fight
        # too short to read would otherwise be accepted and deepen nothing,
        # which is the flag silently doing nothing at the price of a full run.
        drawable = sorted({one.fight_id for boss in night.bosses for one in boss.attempts})
        unknown = sorted(deep_fights.difference(drawable))
        if unknown:
            named = ", ".join(str(one) for one in unknown)
            if drawable:
                holds = ", ".join(str(one) for one in drawable)
                raise ValueError(
                    f"--deep names fight {named}, which this night has no attempt for; "
                    f"its attempts are {holds}"
                )
            # A night every one of whose fights fell under the duration floor
            # has no id to offer back, and "its attempts are " followed by
            # nothing would read as a bug rather than as an answer.
            raise ValueError(
                f"--deep names fight {named}, and no fight in this report is long enough "
                "to read as an attempt"
            )
        loaded = repository.load_night_attempts(
            night, deep_fights=deep_fights, death_cards=death_cards
        )
        # Loaded once and shared between the pull analyser and the page builder
        # below, exactly as `raid` shares them between its own two readers.
        defensives = load_defensives()
        consumables = load_consumables()
        roles = load_roles()
        # Every pull the night drew, in the order the page draws them, walked
        # once and named once: what follows prices icons, findings and the
        # payload off this single list rather than rebuilding it three times.
        drawn = [attempt for boss in loaded.loaded for attempt in boss.attempts_with_events]
        # Two lists, not one. A boss's findings read its attempts' metadata and
        # a pull's read that pull's own streams; neither is a summary of the
        # other, and section 9 writes both out under the boss they belong to.
        boss_findings = {
            boss.progression.encounter_id: rank_raid_findings(analyse_progression(boss))
            for boss in loaded.loaded
        }
        # No mechanics sample and no parse subject: this command fetches no
        # reference kill of any kind, and handing the analyser an empty sample
        # is what leaves those families undrawn rather than drawn from nothing.
        findings_by_fight = {
            attempt.encounter.fight_id: analyse_encounter(
                attempt, defensives, consumables, roles=roles
            )
            for attempt in drawn
        }
        after = repository.rate_limit()
    except (ValueError, WclError, httpx.HTTPError, OSError) as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    payload = {
        "report_code": night.report_code,
        # What was asked for, which is the half a reader cannot recover from
        # the findings themselves -- least of all on a night where every pull
        # failed and there is nothing left to infer it from.
        "asked_for": {
            "difficulty": difficulty,
            "deep_fights": sorted(deep_fights),
            "death_cards": death_cards,
        },
        "bosses_counted": len(night.bosses),
        "pulls_drawn": len(drawn),
        "withheld_pulls": [
            {"fight_id": one.fight_id, "reason": one.reason} for one in loaded.failed_pulls
        ],
        # A warning per family rather than one for the file: the two lists come
        # from two analysers with two different ordering rules, and one sentence
        # over both would state an accounting neither of them keeps.
        "boss_findings_are_ranked_not_additive": PROGRESSION_FINDINGS_ARE_RANKED_NOT_ADDITIVE,
        "pull_findings_are_ranked_not_additive": RAID_FINDINGS_ARE_RANKED_NOT_ADDITIVE,
        "bosses": [
            {
                "encounter_id": boss.progression.encounter_id,
                "boss_name": boss.progression.boss_name,
                "difficulty": boss.progression.difficulty,
                "size": boss.progression.size,
                "killed": boss.progression.killed,
                "attempts_counted": len(boss.progression.attempts),
                "attempts_discarded": len(boss.progression.discarded),
                "attempts_deepened": len(boss.loaded),
                "findings": [
                    finding.model_dump(mode="json")
                    for finding in boss_findings[boss.progression.encounter_id]
                ],
                "pulls": [
                    {
                        "fight_id": attempt.encounter.fight_id,
                        "kill": attempt.encounter.kill,
                        "duration_seconds": attempt.encounter.duration_seconds,
                        "fight_percentage": attempt.encounter.fight_percentage,
                        "findings": [
                            finding.model_dump(mode="json")
                            for finding in findings_by_fight[attempt.encounter.fight_id]
                        ],
                    }
                    for attempt in boss.attempts_with_events
                ],
            }
            for boss in loaded.loaded
        ],
    }
    counted = sum(len(one) for one in boss_findings.values()) + sum(
        len(one) for one in findings_by_fight.values()
    )

    # Built and rendered before either file is written, and guarded on its own.
    # A page that cannot be built must leave nothing behind: written after the
    # findings, it would hand a reader a findings file naming a report that does
    # not exist, and no page to open. `ValueError` alongside `OSError` because
    # `night_frame.night_subject` refuses a pull whose roster is empty -- a shape
    # `Encounter` allows and the loader passes through -- and it names the fight
    # when it does, which is an answer rather than the traceback this would
    # otherwise print after both writes had already claimed to succeed.
    try:
        page = render_night(
            build_night_report(
                loaded,
                findings_by_fight,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                defensives,
                consumables,
                roles,
                deep_fights=deep_fights,
                death_cards=death_cards,
                findings_by_boss=boss_findings,
                externals=load_externals(),
                self_resurrections=load_self_resurrections(),
            ),
            # One ability dictionary answers the whole night --
            # `load_night_attempts` fetches it once per report and hands the same
            # icon half to every pull -- so any drawn pull addresses the art for
            # all of them. None when no pull was drawn at all: there is then no
            # dictionary to read and nothing on the page to address with it.
            icons=build_icons(drawn[0], ()) if drawn else None,
        )
    except (ValueError, OSError) as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    written = out / f"{night.report_code}.night.json"
    # A guard of its own, on the same reasoning `progression`'s write phase
    # carries one: this fails differently from the block above, and can fail
    # after every finding has already been computed.
    try:
        out.mkdir(parents=True, exist_ok=True)
        # Real rosters and boss names contain non-ASCII characters; write_text's
        # default encoding is locale-dependent (commonly cp1252 on Windows) and
        # would raise on them.
        written.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    typer.echo(f"{counted} findings written to {written}")

    report_file = out / f"{night.report_code}.night.html"
    # A guard of its own again, and for the reason the other two carry theirs:
    # this fails differently from building the page and from writing the
    # findings, and it fails after both have already succeeded.
    try:
        report_file.write_text(page, encoding="utf-8")
    except OSError as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    typer.echo(f"report written to {report_file}")
    typer.echo(_quota_sentence(before, after), err=True)
    _echo_cost_breakdown(repository.client.costs)


if __name__ == "__main__":
    app()
