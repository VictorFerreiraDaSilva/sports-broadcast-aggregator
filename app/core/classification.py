"""Competition classification on two canonical axes — level (`tier`) and
`gender` — resolved at ingestion time and written onto `game` (ADR 0008).

Both are closed vocabularies shared across sources, in the same spirit as
`sport` (ADR 0003). Unlike `sport`, though, no source publishes them: sources
publish a single `category` field that collapses geography, gender and level
into one axis (futnatv's is `Destaques`/`Brasil`/`Feminino`/`Base`/...), which
is exactly why the aggregator has to rebuild the axes it actually needs.

The rule that shapes everything here: **a source category is positive evidence
for at most one axis, and silent on the others.** futnatv filing the Under-20
Women's World Cup under `Feminino` says it is women's football; it says nothing
about whether it is youth — and in fact it is. So all the youth evidence is
exhausted before the source's category is allowed to assert `professional`,
and all the women's evidence before it may assert `men`.

`*_method` records which rule fired, mirroring `game_broadcast.match_method`:
it is what makes the curation queue (`method = 'none'`) and the audit of how
much was guessed (`method = 'pattern'`) possible.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

TIER_PROFESSIONAL = "professional"
TIER_YOUTH = "youth"
TIER_UNKNOWN = "unknown"

GENDER_MEN = "men"
GENDER_WOMEN = "women"
GENDER_UNKNOWN = "unknown"

METHOD_CURATED = "curated"
METHOD_SOURCE = "source"
METHOD_PATTERN = "pattern"
METHOD_NONE = "none"

# Youth naming is remarkably regular in the schedules we collect: "Copa do
# Brasil sub-20", "Brasileirão sub-17", "UEFA Youth League", "Copa São Paulo de
# Futebol Júnior". Matched against the normalized (accent-free, casefolded)
# competition text, so "júnior" arrives here as "junior".
YOUTH_PATTERN = re.compile(
    r"\bsub[-\s]?\d{2}\b|\bu-?\d{2}\b|\bjunior\b|\bjuvenil\b|\byouth\b|\bacademy\b"
)

# Morphology only — no league names. A league name in a regex is a curated
# entry wearing a costume; NWSL belongs in CURATED_GENDER, not here.
WOMEN_PATTERN = re.compile(r"\bfeminin[ao]s?\b|\bwomen\b|\bwomens\b")

# Manual overrides, keyed by the normalized competition text and deliberately
# agnostic of source and sport: classifying by name is not the same as merging
# two sources' competitions into one entity (ADR 0002/0003 stay intact — no
# identity is claimed here).
#
# What earns a line here: a competition the automatic rules get wrong or cannot
# see. The seed below is the second kind — sports other than football have no
# competition catalog at the source at all (futnatv field-notes, "O que não
# existe"), so nothing but curation can ever classify them.
CURATED_TIER: dict[str, str] = {
    "nfl": TIER_PROFESSIONAL,
    "nhl": TIER_PROFESSIONAL,
    "copa do mundo feminina": TIER_PROFESSIONAL,  # basquete
    "sul-americano feminino": TIER_PROFESSIONAL,  # volei
    "cev eurovolley feminino": TIER_PROFESSIONAL,  # volei
}

CURATED_GENDER: dict[str, str] = {
    # No morphological marker in the name; the football catalog does carry it,
    # but that catalog only exists for football.
    "nwsl": GENDER_WOMEN,
    # Same reason as the two entries above them in CURATED_TIER: no catalog
    # for these sports, and nothing in the name to read.
    "nfl": GENDER_MEN,
    "nhl": GENDER_MEN,
}


@dataclass(frozen=True)
class Classification:
    tier: str
    tier_method: str
    gender: str
    gender_method: str


def normalize_key(text: str) -> str:
    """trim + casefold + accent-free — the lookup key.

    A third copy of this three-liner, on purpose and for the same reason
    app/core/ingest.py keeps its own: the core must not import from
    app/sources/ (ADR 0005), and this module must stay importable with no
    database and no source loaded.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip().casefold()


def classify(
    competition_text: str,
    tier_hint: str | None = None,
    gender_hint: str | None = None,
) -> Classification:
    """Resolve both axes for one game from its competition name plus whatever
    the source could tell us (`NormalizedGame.tier_hint`/`gender_hint`).

    Precedence, per axis: curation > evidence *for* the marked value (source,
    then name pattern) > the source's assertion of the unmarked value >
    unknown. The asymmetry is the whole point — see the module docstring.
    """
    key = normalize_key(competition_text)

    curated_tier = CURATED_TIER.get(key)
    if curated_tier is not None:
        tier, tier_method = curated_tier, METHOD_CURATED
    elif tier_hint == TIER_YOUTH:
        tier, tier_method = TIER_YOUTH, METHOD_SOURCE
    elif YOUTH_PATTERN.search(key):
        tier, tier_method = TIER_YOUTH, METHOD_PATTERN
    elif tier_hint == TIER_PROFESSIONAL:
        tier, tier_method = TIER_PROFESSIONAL, METHOD_SOURCE
    else:
        tier, tier_method = TIER_UNKNOWN, METHOD_NONE

    curated_gender = CURATED_GENDER.get(key)
    if curated_gender is not None:
        gender, gender_method = curated_gender, METHOD_CURATED
    elif gender_hint == GENDER_WOMEN:
        gender, gender_method = GENDER_WOMEN, METHOD_SOURCE
    elif WOMEN_PATTERN.search(key):
        gender, gender_method = GENDER_WOMEN, METHOD_PATTERN
    elif gender_hint == GENDER_MEN:
        gender, gender_method = GENDER_MEN, METHOD_SOURCE
    else:
        gender, gender_method = GENDER_UNKNOWN, METHOD_NONE

    return Classification(tier, tier_method, gender, gender_method)
