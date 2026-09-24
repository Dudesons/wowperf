# ABOUTME: The night page's frame: the one fact above its dropdowns, and each pull's subject.
# ABOUTME: A sibling of progression_frame.py -- formatting and selection, never a judgement.

from wowperf.domain.comparison.sample import find_player
from wowperf.domain.encounter import Encounter
from wowperf.domain.model import Player
from wowperf.domain.night import LoadedNight
from wowperf.domain.report.night_model import NightHeader


def build_night_header(loaded: LoadedNight) -> NightHeader:
    """The one fact printed above a night page's two dropdowns.

    Its two siblings, `build_raid_header` and `build_progression_header`, each
    describe one fight or one boss and say much more. A night has no boss name,
    no difficulty and no single outcome to head its page with: it covers every
    boss the report pulled, at whatever difficulty each was pulled.

    Read off the `Night` rather than off a pull, because the report code is the
    one fact still available when no pull loaded at all.
    """
    return NightHeader(report_code=loaded.night.report_code)


def night_subject(encounter: Encounter) -> Player:
    """Whose card opens one pull's Players tab.

    `wowperf night` names no player: no flag asks for one, and no finding on
    the page belongs to one. The report owner stands in, because it is the only
    name the log itself volunteers. The match folds case through `find_player`,
    since Warcraft Logs lowercases the owner's name while the roster carries
    the character's own spelling.

    An owner who is not on this pull's roster falls back to the first raider in
    roster order rather than refusing the pull. A raider who sat out one boss is
    an ordinary night, and `cli._resolve_player`'s refusal belongs to the
    commands that were asked about a player by name -- here the subject decides
    which card opens first and nothing else, so falling back costs a reader an
    extra click and no accuracy.

    A pull whose roster is empty has no card for the tab to open on at all, and
    is refused naming the fight. `Encounter.players` carries no non-empty
    guarantee, so this is a shape the type allows rather than one ruled out;
    the alternative is an `IndexError` on the line below, which names nothing
    and takes the whole page down over one pull -- undoing, one layer up, the
    ruling that a pull which will not load shrinks the night rather than
    failing it. `FailedPull` is deliberately not minted here: that type belongs
    to the load layer, and a pull that loaded is not a pull that failed.
    """
    if not encounter.players:
        raise ValueError(
            f"fight {encounter.fight_id} carries no roster, "
            "so no card can open its Players tab"
        )
    owner = encounter.owner_name
    found = find_player(encounter.players, owner) if owner else None
    return found or encounter.players[0]
