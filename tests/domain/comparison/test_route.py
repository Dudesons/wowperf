# ABOUTME: Behaviour tests for turning a route alignment into findings a reader can act on.
# ABOUTME: The headline is what a faster group skipped, priced with our own clock.

from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.comparison.route import MAX_PACKS_REPORTED, compare_route
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import EnemyNpc, Pull, Run


def a_pull(
    index: int,
    game_ids: tuple[int, ...],
    seconds: float = 60.0,
    boss: bool = False,
    name: str | None = None,
) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name=name if name is not None else ("Boss" if boss else "Pack"),
        encounter_id=2607 if boss else 0,
        start_ms=index * 200_000,
        end_ms=index * 200_000 + int(seconds * 1000),
        killed=True,
        x=100 + index,
        y=200 + index,
        enemies=tuple(
            EnemyNpc(actor_id=100 + n, game_id=game_id) for n, game_id in enumerate(game_ids)
        ),
    )


def a_run(pulls: tuple[Pull, ...], counts: tuple[tuple[int, int], ...] = ()) -> Run:
    return Run(
        report_code="abc123",
        fight_id=36,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=16,
        affix_ids=(9, 10, 147),
        keystone_time_ms=1_909_000,
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=counts,
        players=(),
        pulls=pulls,
    )


def findings_by_prefix(findings: list[Finding], prefix: str) -> list[Finding]:
    return [finding for finding in findings if finding.id.startswith(prefix)]


def test_a_pack_they_skipped_is_priced_with_our_own_clock() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,), seconds=45.0), a_pull(2, (3,))),
                 counts=((2, 12),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))
    skipped = findings_by_prefix(findings, "compare.route.skipped.")

    assert len(skipped) == 1
    assert skipped[0].seconds_lost == 45.0
    assert skipped[0].confidence is Confidence.MEASURED
    assert skipped[0].pull_index == 1
    assert any("12" in line for line in skipped[0].evidence)


def test_a_boss_is_never_reported_as_a_skipped_pack() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (99,), boss=True)))
    theirs = a_run((a_pull(0, (1,)),))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))

    assert findings_by_prefix(findings, "compare.route.skipped.") == []


def test_a_boss_is_never_reported_as_an_extra_pack() -> None:
    ours = a_run((a_pull(0, (1,)),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (99,), boss=True)))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))

    assert findings_by_prefix(findings, "compare.route.extra.") == []


def test_a_pack_only_they_killed_carries_no_seconds() -> None:
    ours = a_run((a_pull(0, (1,)),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,), seconds=77.0)))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))
    extra = findings_by_prefix(findings, "compare.route.extra.")

    assert len(extra) == 1
    assert extra[0].seconds_lost is None


def test_the_extra_pack_evidence_carries_no_duration() -> None:
    """A cross-gap duration would import a number from the other side of a keystone
    gap; the pack's name and enemy count already identify it without one."""
    ours = a_run((a_pull(0, (1,)),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,), seconds=77.0)))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))
    extra = findings_by_prefix(findings, "compare.route.extra.")[0]

    assert not any("77" in line or "lasted" in line for line in extra.evidence)


def test_the_extra_pack_detail_makes_no_claim_about_keystone_levels() -> None:
    ours = a_run((a_pull(0, (1,)),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))
    extra = findings_by_prefix(findings, "compare.route.extra.")[0]

    assert "keystone" not in extra.detail.lower()
    assert "level" not in extra.detail.lower()


def test_the_evidence_names_the_pack_for_both_skipped_and_extra_findings() -> None:
    ours = a_run(
        (a_pull(0, (1,)), a_pull(1, (2,), name="Thornclaw Gatherer")),
        counts=((2, 12),),
    )
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,), name="Spirit of Hunger")))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))
    skipped = findings_by_prefix(findings, "compare.route.skipped.")
    extra = findings_by_prefix(findings, "compare.route.extra.")

    assert skipped[0].evidence[0] == "Thornclaw Gatherer"
    assert extra[0].evidence[0] == "Spirit of Hunger"


def test_the_summary_counts_both_routes() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,))))
    theirs = a_run((a_pull(0, (1,)),))

    summary = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                                 "compare.route.summary")[0]

    assert "2" in summary.title
    assert "1" in summary.title
    assert summary.seconds_lost is None


def test_the_summary_evidence_accounts_for_every_pull_including_reordered_ones() -> None:
    """matched + only_ours + only_theirs + reordered must partition both routes; a
    swap that moves packs into `out_of_order` must not silently vanish from the count."""
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,))))
    theirs = a_run((a_pull(0, (2,)), a_pull(1, (1,)), a_pull(2, (3,))))

    summary = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                                 "compare.route.summary")[0]

    assert any("reordered" in line for line in summary.evidence)
    assert not any(line.startswith("0 reordered") for line in summary.evidence)


def test_the_summary_pluralises_a_single_pack_correctly() -> None:
    ours = a_run((a_pull(0, (1,)),))
    theirs = ours

    summary = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                                 "compare.route.summary")[0]

    assert "1 pack," in summary.title
    assert "1 packs" not in summary.title
    assert "1 pack matched on composition" in summary.detail
    assert "1 pack in common" in " ".join(summary.evidence)


def test_a_single_enemy_pack_is_singular_in_skipped_evidence() -> None:
    ours = a_run((a_pull(0, (1,)),), counts=((1, 5),))
    theirs = a_run(())

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))
    skipped = findings_by_prefix(findings, "compare.route.skipped.")[0]

    assert "1 enemy" in skipped.evidence
    assert "1 enemies" not in skipped.evidence


def test_a_single_reordered_pack_is_singular_and_uses_was() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,))))
    theirs = a_run((a_pull(0, (2,)), a_pull(1, (1,))))

    order = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                               "compare.route.order")[0]

    assert order.title == "1 pack was taken in a different order"


def test_only_the_worst_packs_are_reported() -> None:
    # Eight packs they skipped, each one second shorter than the last.
    skipped_pulls = tuple(
        a_pull(index, (index + 10,), seconds=float(60 - index)) for index in range(1, 9)
    )
    ours = a_run((a_pull(0, (1,)), *skipped_pulls))
    theirs = a_run((a_pull(0, (1,)),))

    skipped = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                                 "compare.route.skipped.")

    assert len(skipped) == MAX_PACKS_REPORTED
    seconds = [finding.seconds_lost for finding in skipped]

    def as_sortable(value: float | None) -> float:
        return value if value is not None else float("-inf")

    assert seconds == sorted(seconds, key=as_sortable, reverse=True)


def test_a_reordered_route_is_reported_once() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,))))
    theirs = a_run((a_pull(0, (2,)), a_pull(1, (1,)), a_pull(2, (3,))))

    order = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                               "compare.route.order")

    assert len(order) <= 1


def test_identical_routes_report_only_the_summary() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,))))

    findings = compare_route(ours, ours, align_pulls(ours, ours))

    assert [finding.id for finding in findings] == ["compare.route.summary"]


def test_no_finding_prints_a_map_position() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,), seconds=45.0), a_pull(2, (3,))),
                 counts=((2, 12),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))
    for finding in findings:
        for line in finding.evidence:
            assert "map position" not in line, finding.id


def test_every_finding_id_is_unique() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (4,))))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,))))

    ids = [finding.id for finding in compare_route(ours, theirs, align_pulls(ours, theirs))]

    assert len(ids) == len(set(ids))
