# ABOUTME: End-to-end report rendering against a real run; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import json
import os
import re
from pathlib import Path
from typing import Any, cast

import pytest
from markupsafe import escape
from typer.testing import CliRunner

from wowperf.adapters.config.toml import (
    load_consumables,
    load_defensives,
    load_externals,
    load_season_data,
    load_self_resurrections,
    load_throughput_cooldowns,
)
from wowperf.adapters.render.html import render
from wowperf.cli import (
    RequestedPlayer,
    _auras,
    _resolve_player,
    _samples,
    app,
    build_reference_repositories,
    build_repository,
)
from wowperf.domain.analysis.roster import display_names
from wowperf.domain.analysis.service import analyse
from wowperf.domain.comparison.service import ComparisonSubject, compare, find_player
from wowperf.domain.findings import rank_findings
from wowperf.domain.report.build import build_report
from wowperf.domain.report.players import COMPARISON_PREFIXES, slugs_by_actor
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_run_renders_a_self_contained_report(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    repository = build_repository(tmp_path)
    loaded = repository.load(code, fight)
    defensives = load_defensives()
    findings = analyse(
        loaded, load_season_data(), defensives, load_consumables(),
        load_throughput_cooldowns(),
    )

    # Mirrors `analyze`'s own resolution (cli.py), so this is the only place
    # `--compare`'s default path -- both reference runs, spell/talent/uptime
    # comparison, and the routing of their findings onto one player's card --
    # is exercised against real data instead of only offline fixtures.
    names = display_names(loaded.run.players)
    subject = _resolve_player(loaded.run.players, loaded.run.owner_name, None, names)
    rankings, references = build_reference_repositories(repository.client, tmp_path)
    subject_slug = slugs_by_actor(loaded.run.players)[subject.actor_id]
    subject_name = names[subject.actor_id]
    speed_sample, parse_samples, reference_records = _samples(
        rankings,
        references,
        loaded.run,
        (RequestedPlayer(player=subject, slug=subject_slug, name=subject_name),),
    )
    parse_sample = parse_samples[subject.actor_id]
    assert reference_records, "no candidate was weighed at all"

    our_auras = None
    if parse_sample.members:
        top = parse_sample.members[0]
        their_player = find_player(top.players, top.character_name)
        if their_player is not None:
            our_auras = _auras(
                repository, loaded.run.report_code, loaded.run.fight_id, subject.actor_id
            )
            top = top.model_copy(
                update={
                    "auras": _auras(
                        references, top.report_code, top.fight_id, their_player.actor_id
                    )
                }
            )
            parse_sample = parse_sample.model_copy(
                update={"members": (top, *parse_sample.members[1:])}
            )

    findings += compare(
        ours=loaded,
        speed=speed_sample,
        subjects=(
            ComparisonSubject(
                player=subject,
                slug=subject_slug,
                display_name=subject_name,
                parse=parse_sample,
                our_auras=our_auras,
            ),
        ),
    )
    findings = rank_findings(findings)

    # A misconfigured WOWPERF_E2E_REPORT pointing at an empty or mismatched
    # fight must fail loudly here, not render a report with nothing to show
    # and pass vacuously.
    assert findings, "The analysis produced no findings at all"

    report = build_report(
        loaded, findings, speed_sample, frozenset({subject_slug}), subject, None,
        "2026-09-05 00:00",
        defensives,
        load_consumables(),
        externals=load_externals(),
        self_resurrections=load_self_resurrections(),
        reference_records=reference_records,
    )
    html = render(report)

    # Every death on a real run renders a recap: a timeline, three availability
    # groups, and one return line with its badge.
    for recap in report.deaths:
        assert recap.timeline, f"{recap.player}: no timeline"
        assert [group.title for group in recap.availability] == [
            "Defensives", "Consumables", "Teammates' externals"
        ]
        assert recap.came_back and recap.came_back_badge is not None

    # The report's one hard promise: it opens from disk, offline, forever. Checked by
    # what the page can execute or load, not by whether a URL string appears at all —
    # a link the reader may click and the SVG's own namespace both fetch nothing.
    # One inline script is allowed — the tab toggle — and only one; its text is
    # checked in `test_html_invariants.py`.
    scripts = re.findall(r"<script\b([^>]*)>", html, flags=re.I)
    assert len(scripts) == 1 and "src=" not in scripts[0].lower()
    assert "@import" not in html.lower()
    assert "<link rel=" not in html.lower()
    for src in re.findall(r'src="([^"]*)"', html, flags=re.IGNORECASE):
        assert not src.startswith(("http://", "https://", "//")), src
    for href in re.findall(r'href="([^"]*)"', html):
        assert href.startswith("#") or href.startswith(
            "https://www.warcraftlogs.com/reports/"
        ), href

    # Real rosters carry non-ASCII names; the file must hold them.
    written = tmp_path / "report.html"
    written.write_text(html, encoding="utf-8")
    assert written.read_text(encoding="utf-8") == html

    # Every finding the analysis produced reaches the page exactly once. Anchored to
    # the row heading: a nested row quotes its parent's title in "Already counted
    # inside ...", which is a cross-reference, not a second copy of the parent's row.
    # Compared against the escaped title, since the template renders it through
    # Jinja's autoescape (markupsafe.escape) and a real ability name commonly
    # carries an apostrophe that autoescape turns into `&#39;`.
    for finding in findings:
        assert html.count(f"<h3>{escape(finding.title)}</h3>") == 1, finding.id

    # The timeline heading always renders, whether present or withheld.
    assert "Aligned timeline" in html

    # Spell, talent and uptime comparison rows must land on the analysed
    # player's own card, never a namesake's card. The code matches by actor id,
    # not by name, to avoid routing comparison rows to the wrong player when
    # names collide.
    if parse_sample.members:
        comparison_ids = {
            finding.id
            for finding in findings
            if finding.seconds_lost is None
            and any(finding.id.startswith(prefix) for prefix in COMPARISON_PREFIXES)
        }
        assert comparison_ids, "No compare.* findings were produced to test the routing"
        # A player card's `name` is the roster's disambiguated display name, which
        # only differs from the raw `subject.name` when another player shares it.
        subject_display_name = display_names(loaded.run.players)[subject.actor_id]
        subject_card = next(card for card in report.players if card.name == subject_display_name)
        assert subject_card.spell_and_talent.state.value == "present"
        assert {row.finding_id for row in subject_card.spell_and_talent_rows} == comparison_ids
        for card in report.players:
            if card is not subject_card:
                assert card.spell_and_talent_rows == ()


@pytest.mark.e2e
def test_all_players_compares_everyone_and_collides_no_ids(tmp_path: Path) -> None:
    r"""`--all-players` end to end: the real command, a cold cache, the real API.

    Driven as the command rather than reassembled from its parts, unlike the
    test above. Who is compared is decided in `analyze` and nowhere else --
    the flag, the roster it sweeps up, the slug stamped on every finding it
    mints and the cards the report then fills -- so a reassembly here would
    exercise the reassembly.

    A parse sample is drawn per player, so this is also the run that prices
    the flag. What `analyze` says about its own spend goes to stderr, which
    the runner captures rather than shows; it is echoed back so that
    `pytest -s` prints it, which is how the figure in
    `.claude/skills/wcl-api/SKILL.md` was read. Take it from a cache this run
    filled itself -- against a warm one the command truthfully reports
    spending almost nothing.

    To take the reading again, at a cost of roughly 190 points of the 3600 an
    hour:

        WCL_CLIENT_ID=... WCL_CLIENT_SECRET=... \
        WOWPERF_E2E_REPORT='https://www.warcraftlogs.com/reports/<code>?fight=<n>' \
        uv run pytest -m e2e -s \
          tests/e2e/test_report_e2e.py::test_all_players_compares_everyone_and_collides_no_ids

    Both overrides earn their place. `pyproject.toml` sets `addopts = "-m 'not
    e2e' --strict-markers"`, and pytest applies `-m` to a node-id selection
    too, so without `-m e2e` this test is deselected and the command spends
    nothing; without `-s` the block below goes into pytest's capture and is
    never seen. The exact string behind the 2026-09-11 reading is recorded
    nowhere -- this is the smallest invocation that reproduces it, not a
    transcript of it.
    """
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    out = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        [
            "analyze", REPORT,
            "--all-players",
            "--cache-dir", str(tmp_path / "cache"),
            "--out", str(out),
        ],
    )
    # Both halves of the diagnosis: a refusal the command wrote itself goes to
    # stderr, and an exception it never expected is held on the result instead.
    # This run costs real quota, so a failure has to say which it was.
    assert result.exit_code == 0, f"{result.stderr}\n{result.exception!r}"

    [written] = out.glob("*.findings.json")
    findings = cast(dict[str, Any], json.loads(written.read_text(encoding="utf-8")))
    [page] = out.glob("*.html")
    html = page.read_text(encoding="utf-8")

    # Every finding id is minted once. The parse families are suffixed with the
    # player they are about, and five players' worth of them is where a suffix
    # that failed to distinguish anybody would first show. Named rather than
    # counted, as `test_html_invariants.py`'s offline sibling names them: a
    # failure here has already spent the run's quota, so it has to say which id
    # collided and not merely that one did.
    ids = [finding["id"] for finding in findings["findings"]]
    assert ids, "the run produced no findings at all"
    duplicate_ids = {value for value in ids if ids.count(value) > 1}
    assert duplicate_ids == set()

    # The same claim about the page, which mints an element id per card, per
    # sub-tab and per row. A duplicate is invalid HTML and sends the page's own
    # pointers to whichever of the two the browser happens to pick.
    element_ids = re.findall(r'\sid="([^"]+)"', html)
    assert element_ids, "a page with no element ids would pass this vacuously"
    duplicate_element_ids = {value for value in element_ids if element_ids.count(value) > 1}
    assert duplicate_element_ids == set()

    # Everyone means everyone: a card per roster member, and each of them
    # compared. A player the log records no specialisation for is compared too
    # -- their comparison is one finding saying why it is empty.
    compared = findings["comparison"]["players"]
    assert len(compared) > 1, "a roster of one cannot show that --all-players widened anything"
    assert set(compared) == set(re.findall(r'data-tab-panel="players" id="player-([^"]+)"', html))
    for slug in compared:
        assert any(finding.get("player_slug") == slug for finding in findings["findings"]), slug

    # Every parse candidate names whose comparison weighed it, and names
    # somebody who was actually compared.
    references = findings["comparison"]["references"]
    parse_references = [record for record in references if record["axis"] == "parse"]
    assert parse_references, "no parse candidate was weighed at all"
    assert {record["player_slug"] for record in parse_references} <= set(compared)

    # A reference is cheap for the second player who wants it: the cache is
    # keyed by report and fight with no character in it, so `from_cache` on a
    # candidate two players' samples both name is a load nobody paid for twice.
    slugs_by_reference: dict[tuple[str, int], set[str]] = {}
    for record in parse_references:
        key = (record["report_code"], record["fight_id"])
        slugs_by_reference.setdefault(key, set()).add(record["player_slug"])
    shared = [
        record
        for record in parse_references
        if record["from_cache"]
        and len(slugs_by_reference[(record["report_code"], record["fight_id"])]) > 1
    ]

    # The rest of the conditions the skill entry records, so that whoever
    # retakes the reading reproduces the whole entry and not only its total.
    # Printed and never asserted: how far two specialisations' leaderboards
    # overlap moves daily, and a partial failure that excluded a candidate is
    # a legitimate run whose figures are still worth reading.
    speed_references = [record for record in references if record["axis"] == "speed"]
    speed_keys = {(record["report_code"], record["fight_id"]) for record in speed_references}
    parse_keys = set(slugs_by_reference)
    excluded = [record for record in references if not record["loaded"]]

    assert "Where they went:" in result.stderr
    measurement = "\n".join(
        [
            result.stderr,
            f"players compared: {len(compared)}",
            f"parse candidates weighed: {len(parse_references)}",
            f"speed candidates weighed: {len(speed_references)}",
            f"distinct reference runs: {len(speed_keys | parse_keys)}",
            f"speed references also drawn as a parse: {len(speed_keys & parse_keys)}",
            f"candidates loaded: {len(references) - len(excluded)} of {len(references)}",
            f"candidates excluded: {len(excluded)}",
            f"served from another player's sample: {len(shared)}",
        ]
    )
    # Windows gives the process a cp1252 stdout, and `-s` sends this straight
    # to it rather than through pytest's own capture. A run that has already
    # spent its quota must not end in a UnicodeEncodeError over a character in
    # a dungeon or ability name, so the escape is taken here.
    print(measurement.encode("ascii", "backslashreplace").decode("ascii"))
