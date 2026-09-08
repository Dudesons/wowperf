# ABOUTME: Command-line entry point; the driving adapter that wires ports to implementations.
# ABOUTME: Holds no analysis logic, only construction, argument handling and output.

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
import typer

from wowperf.adapters.cache.disk import DiskCache
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
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import RateLimit, WclClient
from wowperf.adapters.wcl.cost import CostLedger
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.ingest import IngestError
from wowperf.adapters.wcl.ranking_repository import WclRankingRepository
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.domain.analysis.service import analyse
from wowperf.domain.auras import PlayerAuras
from wowperf.domain.comparison.alignment import align_pulls
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
from wowperf.domain.comparison.service import compare, find_player
from wowperf.domain.findings import rank_findings
from wowperf.domain.model import Player, Run
from wowperf.domain.report.build import build_report
from wowperf.domain.report.model import ReferenceRecord
from wowperf.domain.report.narrative import lines_with_digits
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


@app.callback()
def main() -> None:
    """Analyse World of Warcraft logs and report what to improve.

    Typer collapses a single-command app into a bare invocation; this callback
    keeps `fetch` addressable as a subcommand even before later plans add more.
    """


def build_repository(cache_dir: Path) -> WclRunRepository:
    client_id = os.environ.get("WCL_CLIENT_ID")
    client_secret = os.environ.get("WCL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise typer.BadParameter(
            "Set WCL_CLIENT_ID and WCL_CLIENT_SECRET. "
            "Create a client at https://www.warcraftlogs.com/api/clients/"
        )

    http = httpx.Client(timeout=60.0)
    return WclRunRepository(
        WclClient(TokenProvider(client_id, client_secret, http), http),
        DiskCache(cache_dir),
    )


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


def _resolve_player(run: Run, requested: str | None) -> Player:
    """Whose run this is, for the individual comparison.

    The report owner is the default because it is the only name the log itself
    volunteers. Warcraft Logs lowercases it, so the match folds case.
    """
    name = requested or run.owner_name
    if name is not None:
        found = find_player(run, name)
        if found is not None:
            return found

    roster = ", ".join(sorted(player.name for player in run.players)) or "nobody"
    raise ValueError(
        f"{name!r} is not in this run's roster. Pass --player with one of: {roster}"
    )


def _record(
    row: SpeedRow | ParseRow,
    axis: str,
    *,
    loaded: bool,
    reason: str = "",
    from_cache: bool = False,
) -> ReferenceRecord:
    """One leaderboard row's outcome, in the shape the report is allowed to keep forever.

    `row` gives up only its code, fight and level — never the team, the
    character name or the score a `SpeedRow`/`ParseRow` also carries, which is
    what keeps a `ReferenceRecord` a link rather than a tabulation of another
    player's run.
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
    )


def _samples(
    rankings: WclRankingRepository,
    runs: WclRunRepository,
    run: Run,
    subject: Player,
) -> tuple[SpeedSample, ParseSample, tuple[ReferenceRecord, ...]]:
    """Up to `SAMPLE_SIZE` references per axis, and a record of every row weighed.

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
                _record(parse_row, "parse", loaded=False, reason="this is the run under analysis")
            )
            continue
        try:
            theirs, from_cache = runs.load_parse_reference(
                parse_row.report_code, parse_row.fight_id
            )
        except (IngestError, WclError) as error:
            records.append(_record(parse_row, "parse", loaded=False, reason=str(error)))
            continue
        if any(player.name.casefold() in our_names for player in theirs.run.players):
            records.append(
                _record(
                    parse_row,
                    "parse",
                    loaded=True,
                    reason="the roster includes one of our own characters",
                    from_cache=from_cache,
                )
            )
            continue
        records.append(_record(parse_row, "parse", loaded=True, from_cache=from_cache))
        parse_members.append(
            ParseMember(row=parse_row, run=theirs.run, casts=theirs.casts)
        )

    return (
        SpeedSample(members=tuple(speed_members)),
        ParseSample(members=tuple(parse_members)),
        tuple(records),
    )


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


def _fetch_parse_auras(
    sample: ParseSample,
    ours: WclRunRepository,
    references: WclRunRepository,
    our_run: Run,
    subject: Player,
) -> tuple[ParseSample, PlayerAuras | None]:
    """Every parse member's own aura data, and our own side's, fetched at most once.

    A member's counterpart is resolved from that member's own roster,
    `find_player(member.run, member.row.character_name)`, before paying for
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
        their_player = find_player(member.run, member.row.character_name)
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
    player: str | None = typer.Option(
        None, help="Subject of the individual comparison; defaults to the report owner"
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
        # Loaded once and shared: the analysers and the death cards must read
        # the same cooldowns, or the page and the findings disagree.
        defensives = load_defensives()
        consumables = load_consumables()
        findings = analyse(
            loaded,
            load_season_data(),
            defensives,
            consumables,
            load_throughput_cooldowns(),
            roles=load_roles(),
            include_cooldown_ceiling=throughput_ceiling,
        )

        subject = _resolve_player(loaded.run, player)
        speed_sample: SpeedSample | None = None
        parse_sample: ParseSample | None = None
        reference_records: tuple[ReferenceRecord, ...] = ()
        if not no_compare:
            rankings, references = build_reference_repositories(repository.client, cache_dir)
            # Every candidate `_samples` weighed comes back as `reference_records`,
            # carried onto both the report's provenance below and the comparison
            # block of the findings JSON.
            speed_sample, parse_sample, reference_records = _samples(
                rankings, references, loaded.run, subject
            )

            parse_sample, our_auras = _fetch_parse_auras(
                parse_sample, repository, references, loaded.run, subject
            )

            findings += compare(
                ours=loaded,
                our_player=subject,
                speed=speed_sample,
                parse=parse_sample,
                our_auras=our_auras,
            )
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
                (speed_sample and speed_sample.members) or (parse_sample and parse_sample.members)
            ),
            "sample_size": {
                "speed": len(speed_sample.members) if speed_sample else 0,
                "parse": len(parse_sample.members) if parse_sample else 0,
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
                }
                for record in reference_records
            ],
        },
        "findings_are_ranked_not_additive": FINDINGS_ARE_RANKED_NOT_ADDITIVE,
        "findings": [finding.model_dump(mode="json") for finding in findings],
    }

    out.mkdir(parents=True, exist_ok=True)
    written = out / f"{run.report_code}-{run.fight_id}.findings.json"
    # Real rosters contain non-ASCII names; write_text's default encoding is
    # locale-dependent (commonly cp1252 on Windows) and would raise on them.
    written.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"{len(findings)} findings written to {written}")

    report_file = out / f"{run.report_code}-{run.fight_id}.html"
    report_file.write_text(
        render(
            build_report(
                loaded,
                findings,
                speed_sample,
                parse_sample,
                subject,
                narrative_text,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                defensives,
                consumables,
                externals=load_externals(),
                self_resurrections=load_self_resurrections(),
                reference_records=reference_records,
            )
        ),
        encoding="utf-8",
    )
    typer.echo(f"report written to {report_file}")
    typer.echo(_quota_sentence(before, after), err=True)
    _echo_cost_breakdown(repository.client.costs)


if __name__ == "__main__":
    app()
