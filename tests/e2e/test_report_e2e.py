# ABOUTME: End-to-end report rendering against a real run; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
import re
from pathlib import Path

import pytest
from markupsafe import escape

from wowperf.adapters.config.toml import (
    load_consumables,
    load_defensives,
    load_season_data,
    load_throughput_cooldowns,
)
from wowperf.adapters.render.html import render
from wowperf.cli import (
    _auras,
    _references,
    _resolve_player,
    build_reference_repositories,
    build_repository,
)
from wowperf.domain.analysis.players import display_names
from wowperf.domain.analysis.service import analyse
from wowperf.domain.comparison.service import compare, find_player
from wowperf.domain.findings import rank_findings
from wowperf.domain.report.build import COMPARISON_PREFIXES, build_report
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
    subject = _resolve_player(loaded.run, None)
    rankings, references = build_reference_repositories(repository.client, tmp_path)
    speed, parse = _references(rankings, references, loaded.run, subject)

    our_auras = None
    if parse is not None:
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
        ours=loaded, our_player=subject, speed=speed, parse=parse, our_auras=our_auras
    )
    findings = rank_findings(findings)

    # A misconfigured WOWPERF_E2E_REPORT pointing at an empty or mismatched
    # fight must fail loudly here, not render a report with nothing to show
    # and pass vacuously.
    assert findings, "The analysis produced no findings at all"

    report = build_report(
        loaded, findings, speed, parse, subject, None, "2026-09-05 00:00", defensives,
        load_consumables(),
    )
    html = render(report)

    # The report's one hard promise: it opens from disk, offline, forever. Checked by
    # what the page can execute or load, not by whether a URL string appears at all —
    # a link the reader may click and the SVG's own namespace both fetch nothing.
    assert "<script" not in html.lower()
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
    if parse is not None:
        comparison_ids = {
            finding.id
            for finding in findings
            if finding.seconds_lost is None
            and any(finding.id.startswith(prefix) for prefix in COMPARISON_PREFIXES)
        }
        assert comparison_ids, "No compare.* findings were produced to test the routing"
        # A player card's `name` is the roster's disambiguated display name, which
        # only differs from the raw `subject.name` when another player shares it.
        subject_display_name = display_names(loaded.run)[subject.actor_id]
        subject_card = next(card for card in report.players if card.name == subject_display_name)
        assert subject_card.spell_and_talent.state.value == "present"
        assert {row.finding_id for row in subject_card.spell_and_talent_rows} == comparison_ids
        for card in report.players:
            if card is not subject_card:
                assert card.spell_and_talent_rows == ()
