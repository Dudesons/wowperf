# ABOUTME: Which ledger finding gets a hover panel, and where each panel's figures come from.
# ABOUTME: Two rules: a defensive is measured against the run, anything else brings its own facts.

from collections.abc import Sequence

from wowperf.domain.analysis.defensives import defensive_base_ids
from wowperf.domain.findings import Finding
from wowperf.domain.model import LoadedRun
from wowperf.domain.report.frame import badge_for, run_seconds, run_start_ms
from wowperf.domain.report.model import Tooltip, TooltipLine
from wowperf.domain.report.tooltip import run_ability_tooltip
from wowperf.domain.season import Defensives

DEFENSIVE_FAMILIES = ("defensives.ceiling.", "defensives.never.")
"""The two families whose panel is measured here rather than carried on the finding.

Both name one ability of one player over one run, which is what
`run_ability_tooltip` already answers for a death card. A ledger card differs
only in passing the whole run instead of a run-up.
"""


def _from_facts(finding: Finding) -> Tooltip:
    """A finding's own labelled figures, laid out as panel lines.

    Nothing is computed and nothing is parsed: the analyser put these numbers
    on the finding at the moment it already had them, and this only changes
    their shape. A fact claiming no tier of its own keeps none -- the
    finding's own badge grades it, and stamping a word here would grade a
    claim nobody made.
    """
    return Tooltip(
        lines=tuple(
            TooltipLine(
                label=fact.label,
                value=fact.value,
                tier=None if fact.confidence is None else badge_for(fact.confidence),
            )
            for fact in finding.facts
        )
    )


def tooltips_by_finding_id(
    findings: Sequence[Finding],
    loaded: LoadedRun,
    defensives: Defensives,
) -> dict[str, Tooltip]:
    """The hover panel for every finding that earns one, keyed by finding id.

    Built once, where `loaded`, the per-actor aura tables and the defensives
    data file are all already in hand, so that `ledger_row` can look a panel up
    rather than compute one. Keeping the decision here is what lets that
    function stay a formatter, which is the part of the 2026-09-11 ruling
    against these tooltips that was right.

    The defensives ids are generated from the roster through
    `defensive_base_ids` rather than read off the findings, because those
    findings carry no `player_slug`: their owner lives only inside the minted
    id, and taking it apart again would be parsing a string the analysis had
    just formatted.

    A finding with neither an ability measured here nor facts of its own gets
    nothing, and its heading stays a plain name. Twenty-one of one real run's
    thirty-four findings name no ability at all.
    """
    start_ms = run_start_ms(loaded.run)
    window = (start_ms, start_ms + int(run_seconds(loaded.run) * 1000))
    by_id = {finding.id: finding for finding in findings}
    tooltips: dict[str, Tooltip] = {}

    cooldowns = {
        (player.actor_id, ability.ability_id): ability
        for player in loaded.run.players
        for ability in defensives.for_spec(player.class_name, player.spec)
    }
    for (actor_id, ability_id), base_id in defensive_base_ids(loaded.run, defensives).items():
        wanted = [f"{family}{base_id}" for family in DEFENSIVE_FAMILIES if
                  f"{family}{base_id}" in by_id]
        if not wanted:
            continue
        ability = cooldowns[(actor_id, ability_id)]
        panel = run_ability_tooltip(
            ability_id,
            ability.name,
            ability.cooldown_seconds,
            actor_id,
            loaded,
            loaded.auras_by_actor.get(actor_id),
            tuple(hit for hit in loaded.damage_taken if hit.actor_id == actor_id),
            window,
        )
        if panel is not None:
            tooltips.update({finding_id: panel for finding_id in wanted})

    for finding in findings:
        if finding.id not in tooltips and finding.facts:
            tooltips[finding.id] = _from_facts(finding)
    return tooltips
