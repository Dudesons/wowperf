# ABOUTME: A display name reduced to something an HTML id and a URL fragment can both carry.
# ABOUTME: The one place a player slug is minted, for every layer that mints finding ids.

import unicodedata

SLUG_FALLBACK = "player"
"""What a name reduces to when nothing in it survives the transliteration.

A wholly non-Latin name -- `Кириллица` -- keeps no ASCII letter after
decomposition, and an empty id is not addressable. The caller is responsible
for whatever keeps two such names apart.
"""


def player_slug(display_name: str) -> str:
    """A display name reduced to what an HTML id and a URL fragment both carry.

    Accents decompose and their marks are dropped, so `Bríala` and `Briala`
    reach the same slug -- which is why every caller disambiguates rather than
    trusting this to be unique. Everything else outside the ASCII alphabet and
    digits becomes a hyphen, and runs of hyphens collapse.

    This lives below both the analysis and the report layers because both mint
    finding ids and every finding id becomes an element id on the page. It sat
    in the report layer once, and `defensives.*` -- which analysis mints --
    embedded a raw display name instead, so a non-Latin character reached the
    page's own ids.
    """
    decomposed = unicodedata.normalize("NFKD", display_name)
    kept = [
        character.lower() if character.isascii() and character.isalnum() else "-"
        for character in decomposed
        if not unicodedata.combining(character)
    ]
    slug = "".join(kept).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or SLUG_FALLBACK
