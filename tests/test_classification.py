"""Tests for the canonical competition classification — pure, no network, no
database (app/core/classification.py imports neither).

Every case below is a real competition observed in the production database on
2026-09-08, not an invented one; the counts in the docstrings are what that
day's 268 games actually looked like.
"""

from app.core.classification import (
    GENDER_MEN,
    GENDER_UNKNOWN,
    GENDER_WOMEN,
    METHOD_CURATED,
    METHOD_NONE,
    METHOD_PATTERN,
    METHOD_SOURCE,
    TIER_PROFESSIONAL,
    TIER_UNKNOWN,
    TIER_YOUTH,
    classify,
)


def test_source_base_category_marks_youth():
    """43 games: futnatv files these under `Base`, and it is right."""
    result = classify("Copa do Brasil sub-20", TIER_YOUTH, GENDER_MEN)
    assert (result.tier, result.tier_method) == (TIER_YOUTH, METHOD_SOURCE)


def test_name_pattern_beats_source_asserting_professional():
    """The case that shaped the precedence: 19 games of the Under-20 Women's
    World Cup, which futnatv files under `Feminino` — so its category asserts
    `professional` on the level axis. The name has to win, on that axis only."""
    result = classify("Copa do Mundo Feminina sub-20", TIER_PROFESSIONAL, GENDER_WOMEN)
    assert (result.tier, result.tier_method) == (TIER_YOUTH, METHOD_PATTERN)
    assert (result.gender, result.gender_method) == (GENDER_WOMEN, METHOD_SOURCE)


def test_name_pattern_beats_source_asserting_men():
    """The mirror case, on the other axis: a women's competition the source
    filed under `Base`, so its category asserts `men`."""
    result = classify("Brasileirão Feminino sub-17", TIER_YOUTH, GENDER_MEN)
    assert (result.tier, result.tier_method) == (TIER_YOUTH, METHOD_SOURCE)
    assert (result.gender, result.gender_method) == (GENDER_WOMEN, METHOD_PATTERN)


def test_source_category_asserts_professional_when_no_youth_evidence():
    result = classify("Brasileirão - Série A", TIER_PROFESSIONAL, GENDER_MEN)
    assert (result.tier, result.tier_method) == (TIER_PROFESSIONAL, METHOD_SOURCE)
    assert (result.gender, result.gender_method) == (GENDER_MEN, METHOD_SOURCE)


def test_no_hint_and_no_pattern_is_unknown_not_professional():
    """18 games of `Champions League` sat here before the catalog alias: no
    match, so no hint. Absence of evidence must not read as professional."""
    result = classify("Champions League")
    assert (result.tier, result.tier_method) == (TIER_UNKNOWN, METHOD_NONE)
    assert (result.gender, result.gender_method) == (GENDER_UNKNOWN, METHOD_NONE)


def test_curation_wins_over_every_other_signal():
    result = classify("NFL", TIER_YOUTH, GENDER_WOMEN)
    assert (result.tier, result.tier_method) == (TIER_PROFESSIONAL, METHOD_CURATED)


def test_curated_covers_sports_with_no_catalog():
    """Volleyball/basketball/NFL/NHL have no competition catalog at the source
    at all, so they arrive with no hint — curation is the only mechanism."""
    for name in ("Sul-Americano Feminino", "CEV EuroVolley Feminino"):
        result = classify(name)
        assert (result.tier, result.tier_method) == (TIER_PROFESSIONAL, METHOD_CURATED)
        assert (result.gender, result.gender_method) == (GENDER_WOMEN, METHOD_PATTERN)


def test_curated_gender_for_name_without_morphological_marker():
    """NWSL is women's football with nothing in the name to say so."""
    result = classify("NWSL")
    assert (result.gender, result.gender_method) == (GENDER_WOMEN, METHOD_CURATED)


def test_pattern_is_accent_and_case_insensitive():
    for name in ("Copa São Paulo de Futebol Júnior", "COPA SAO PAULO DE FUTEBOL JUNIOR"):
        assert classify(name).tier == TIER_YOUTH


def test_pattern_variants():
    for name in ("UEFA Youth League", "Liga U-19", "Torneio U20", "Campeonato Juvenil"):
        assert classify(name).tier == TIER_YOUTH, name


def test_pattern_does_not_fire_on_senior_competitions():
    """No senior competition in the observed data trips the youth pattern —
    this is the regression guard for widening it."""
    for name in (
        "Brasileirão - Série A",
        "Campeonato Saudita",
        "UEFA Champions League",
        "Pré-Europa League",
        "Campeonato Peruano",
        "MLS Next Pro",
    ):
        assert classify(name).tier == TIER_UNKNOWN, name


def test_women_pattern_does_not_fire_on_mens_competitions():
    for name in ("Brasileirão - Série A", "Campeonato Alemão", "NBA"):
        assert classify(name).gender == GENDER_UNKNOWN, name


def test_hints_are_optional():
    """A source that contributes nothing still gets classified from the name —
    no source is required to know this system exists."""
    result = classify("Brasileirão sub-17")
    assert (result.tier, result.tier_method) == (TIER_YOUTH, METHOD_PATTERN)
