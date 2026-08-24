"""Testes das funções de parsing puro da fonte futnatv — sem rede nem banco.

app/sources/futnatv/normalize.py não importa nada de app.core, então este
arquivo roda mesmo sem DATABASE_URL configurada.
"""

from app.sources.futnatv.normalize import (
    extract_youtube_id,
    family_fallback,
    normalize_key,
    parse_odds,
    parse_time,
    split_broadcast,
    split_platform_qualifier,
)


def test_split_broadcast_handles_e_and_comma():
    assert split_broadcast("SporTV, Premiere e Globo") == ["SporTV", "Premiere", "Globo"]


def test_split_broadcast_ignores_separators_inside_parentheses():
    assert split_broadcast("Globo (menos BA, PE, NE)") == ["Globo (menos BA, PE, NE)"]


def test_split_broadcast_filters_known_junk():
    assert split_broadcast("<> e Disney+") == ["Disney+"]


def test_split_broadcast_empty():
    assert split_broadcast("") == []


def test_split_platform_qualifier_with_parens():
    assert split_platform_qualifier("YouTube (CazéTV)") == ("YouTube", "CazéTV")


def test_split_platform_qualifier_without_parens():
    assert split_platform_qualifier("ESPN 4") == ("ESPN 4", None)


def test_family_fallback_reduces_trailing_variant():
    assert family_fallback(normalize_key("ESPN 4")) == "espn"
    assert family_fallback(normalize_key("SporTV")) is None


def test_parse_odds_sentinel_and_values():
    assert parse_odds(["1.66", "4.00", "4.50"]) == (1.66, 4.00, 4.50)
    assert parse_odds(["-", "-", "-"]) == (None, None, None)
    assert parse_odds(None) == (None, None, None)


def test_parse_time():
    assert parse_time("13h45") == (13, 45)
    assert parse_time("00h00") == (0, 0)


def test_extract_youtube_id_strips_extra_query_params():
    assert extract_youtube_id("https://www.youtube.com/watch?v=CuUKvR-LoXo&pp=xyz") == "CuUKvR-LoXo"
    assert extract_youtube_id(None) is None
