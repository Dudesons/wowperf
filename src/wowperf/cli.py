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
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.ingest import IngestError
from wowperf.adapters.wcl.ranking_repository import WclRankingRepository
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.domain.analysis.service import analyse
from wowperf.domain.auras import PlayerAuras
from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.comparison.reference import Comparability, ParseReference, SpeedReference
from wowperf.domain.comparison.sample import ParseMember, ParseSample, SpeedMember, SpeedSample
from wowperf.domain.comparison.service import compare, find_player
from wowperf.domain.findings import rank_findings
from wowperf.domain.model import Player, Run
from wowperf.domain.report.build import build_report
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
    "findings are ranked by seconds_lost, not additive: compare.duration is the "
    "total gap against the reference and already contains every other seconds_lost "
    "figure in this report; time.gap.* and compare.downtime both nest inside "
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

    Point cost per query is undocumented, so both commands read the quota
    before and after their work. The reading itself is a query too, so the
    difference also counts the cost of these two quota reads, not only the
    work between them.
    """
    spent = after.points_spent_this_hour - before.points_spent_this_hour
    remaining = after.limit_per_hour - after.points_spent_this_hour
    return (
        f"Rate limit: {spent:.2f} points spent, including the cost of these two "
        f"quota reads themselves; {remaining:.2f} of {after.limit_per_hour} remain this hour."
    )


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
    typer.echo(run.model_dump_json(indent=2))


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


def _references(
    rankings: WclRankingRepository,
    runs: WclRunRepository,
    run: Run,
    subject: Player,
) -> tuple[SpeedReference | None, ParseReference | None]:
    """The two reference runs, or None where the leaderboard had nothing to offer.

    A candidate row whose report fails to load — deleted, private, an
    unfinished fight, or a roster gap in its master data — is skipped rather
    than fatal: falling through to the next row (and to None once the
    leaderboard is exhausted) keeps a broken reference from discarding the
    findings already computed for the run under analysis. The leaderboard
    query itself is not guarded here: a `BracketMismatch` there means the
    bracket convention this tool relies on has changed, and that must still
    stop the command.
    """
    speed = None
    for row in rankings.fastest_runs(run.encounter_id, run.keystone_level):
        # Comparing a run against itself would report a perfect route and teach
        # the reader nothing.
        if row.report_code == run.report_code and row.fight_id == run.fight_id:
            continue
        try:
            loaded = runs.load_reference(row.report_code, row.fight_id)
        except (IngestError, WclError):
            continue
        speed = SpeedReference(row=row, loaded=loaded)
        break

    parse = None
    for parse_row in rankings.top_parses(
        run.encounter_id, run.keystone_level, subject.class_name, subject.spec
    ):
        if parse_row.report_code == run.report_code and parse_row.fight_id == run.fight_id:
            continue
        try:
            loaded = runs.load_reference(parse_row.report_code, parse_row.fight_id)
        except (IngestError, WclError):
            continue
        parse = ParseReference(row=parse_row, loaded=loaded)
        break

    return speed, parse


def _speed_sample(speed: SpeedReference | None, ours: Run) -> SpeedSample | None:
    """Wrap the one speed reference `_references` found into a one-member sample.

    Task 12 replaces this with a real sample of up to `SAMPLE_SIZE` references
    fetched from the leaderboard; until then, `compare` always sees exactly the
    single candidate `_references` already fetched.
    """
    if speed is None:
        return None
    theirs = speed.loaded
    return SpeedSample(
        members=(
            SpeedMember(
                row=speed.row,
                run=theirs.run,
                comparability=Comparability(
                    our_level=ours.keystone_level, their_level=theirs.run.keystone_level
                ),
                alignment=align_pulls(ours, theirs.run),
                deaths=theirs.deaths,
                enemy_cast_rows=theirs.enemy_cast_rows,
                interrupts=theirs.interrupts,
            ),
        )
    )


def _parse_sample(parse: ParseReference | None, ours: Run) -> ParseSample | None:
    """Wrap the one parse reference `_references` found into a one-member sample.

    Task 12 replaces this with a real sample of up to `SAMPLE_SIZE` references
    fetched from the leaderboard; until then, `compare` always sees exactly the
    single candidate `_references` already fetched.
    """
    if parse is None:
        return None
    theirs = parse.loaded
    return ParseSample(
        members=(
            ParseMember(
                row=parse.row,
                run=theirs.run,
                comparability=Comparability(
                    our_level=ours.keystone_level, their_level=theirs.run.keystone_level
                ),
                casts=theirs.casts,
                auras=parse.auras,
            ),
        )
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
        speed: SpeedReference | None = None
        parse: ParseReference | None = None
        if not no_compare:
            rankings, references = build_reference_repositories(repository.client, cache_dir)
            speed, parse = _references(rankings, references, loaded.run, subject)

            our_auras = None
            if parse is not None:
                # Resolve the counterpart before paying for our own aura fetch: when
                # the reference's own roster does not contain the player the
                # leaderboard row names, find_player can never resolve them, and
                # fetching our side first would pay for a query with no use once
                # that failure is discovered.
                their_player = find_player(parse.loaded.run, parse.row.character_name)
                if their_player is not None:
                    our_auras = _auras(
                        repository, loaded.run.report_code, loaded.run.fight_id, subject.actor_id
                    )
                    parse = parse.model_copy(
                        update={
                            "auras": _auras(
                                references,
                                parse.loaded.run.report_code,
                                parse.loaded.run.fight_id,
                                their_player.actor_id,
                            )
                        }
                    )

            findings += compare(
                ours=loaded,
                our_player=subject,
                speed=_speed_sample(speed, loaded.run),
                parse=_parse_sample(parse, loaded.run),
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
            "compared": speed is not None or parse is not None,
            "speed_reference": (
                {
                    "report_code": speed.row.report_code,
                    "fight_id": speed.row.fight_id,
                    "keystone_level": speed.row.keystone_level,
                    "duration_seconds": speed.row.duration_seconds,
                    "medal": speed.row.medal,
                }
                if speed
                else None
            ),
            "parse_reference": (
                {
                    "report_code": parse.row.report_code,
                    "fight_id": parse.row.fight_id,
                    "keystone_level": parse.row.keystone_level,
                    "character_name": parse.row.character_name,
                    "class_name": parse.row.class_name,
                    "spec": parse.row.spec,
                    "medal": parse.row.medal,
                }
                if parse
                else None
            ),
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
                speed,
                parse,
                subject,
                narrative_text,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                defensives,
                consumables,
                externals=load_externals(),
                self_resurrections=load_self_resurrections(),
            )
        ),
        encoding="utf-8",
    )
    typer.echo(f"report written to {report_file}")
    typer.echo(_quota_sentence(before, after), err=True)


if __name__ == "__main__":
    app()
