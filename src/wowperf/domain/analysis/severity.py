# ABOUTME: Raid findings rank by severity, then by what each analyser measured.
# ABOUTME: A family absent from the table ranks last rather than first: visible, not silent.

from collections.abc import Iterable

from wowperf.domain.findings import Finding

SEVERITY_BY_FAMILY = {
    "deaths": 0,
    "progression": 1,
    "mechanics": 2,
    "players": 3,
    "defensives": 4,
    "consumables": 5,
    "interrupts": 6,
    "compare": 7,
}
"""How much each finding family is worth reading first, lowest first.

A table rather than a field on `Finding`: a required field would touch every
slice-1 analyser, which design 7 says not to disturb, and an optional one would
let a new analyser rank on a default nobody chose. The weakness of a table is
that same silent default, and it is still open.
`test_every_family_the_raid_path_emits_has_a_severity` enumerates a
hand-written list of families and asserts each is a key here, so it catches a
family *dropped* from this table. It cannot catch a family *added* to
`analyse_encounter`: nothing derives that list from the analysers, so a new
analyser emitting a new family ranks on `UNKNOWN_SEVERITY` with the whole suite
green. Closing that direction needs a fixture that fires every analyser, which
nothing here has.

Deaths first because a death ends a player's contribution outright. Mechanics
next because it is the one finding that says what to do differently. `compare`
last because a confound explains the others rather than standing beside them.
"""

UNKNOWN_SEVERITY = max(SEVERITY_BY_FAMILY.values()) + 1


def family_of(finding_id: str) -> str:
    return finding_id.split(".", 1)[0]


def rank_raid_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Severity first, then time cost within a family, as design 7 specifies.

    `rank_findings` is untouched and still ranks Mythic+: slice 1 depends on
    its present behaviour, and nothing about Mythic+ changes here.
    """
    return sorted(
        findings,
        key=lambda finding: (
            SEVERITY_BY_FAMILY.get(family_of(finding.id), UNKNOWN_SEVERITY),
            finding.seconds_lost is None,
            -(finding.seconds_lost or 0.0),
        ),
    )
