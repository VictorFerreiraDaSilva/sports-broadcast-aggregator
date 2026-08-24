"""Teste de contrato: garante que a interface `Source` (app/core/source.py) é
genérica de verdade, exercitando-a contra toda fonte registrada — não só
contra futnatv. app/sources/_example/ existe para tornar isso possível sem
rede (ADR 0001/0004/0005).

Requer DATABASE_URL (ver tests/conftest.py) para os testes que tocam banco.
Os testes puramente estruturais (identidade, capacidade opcional) também
precisam de DATABASE_URL só porque app.core.registry importa app.core.config
no import chain — não fazem nenhuma query.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.core.ingest import upsert_games
from app.core.registry import SOURCES
from app.core.source import CronSchedule, NormalizedGame


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.code)
def test_source_declares_identity(source):
    assert isinstance(source.code, str) and source.code
    assert isinstance(source.name, str) and source.name
    assert len(source.games_schedule) > 0
    assert all(isinstance(c, CronSchedule) for c in source.games_schedule)


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.code)
def test_source_exposes_fetch_games(source):
    assert callable(source.fetch_games)


def test_catalog_sync_is_an_optional_capability():
    """ADR 0004: sync_catalog não é exigido pelo Protocol — cada fonte só
    aparece com a capacidade se de fato a implementar."""
    codes_with_catalog = {s.code for s in SOURCES if hasattr(s, "sync_catalog")}
    codes_without_catalog = {s.code for s in SOURCES if not hasattr(s, "sync_catalog")}

    assert "futnatv" in codes_with_catalog
    assert "_example" in codes_without_catalog

    # quem tem a capacidade também declara quando ela roda
    for source in SOURCES:
        if hasattr(source, "sync_catalog"):
            assert len(source.catalog_schedule) > 0


def test_example_source_round_trip(db_session):
    """Fim a fim contra banco de verdade: fetch_games -> upsert_games ->
    reconsulta, e idempotência no natural key (source_code, sport_code,
    game_date, time_raw, home_text, away_text)."""
    from app.sources._example.source import ExampleSource

    source = ExampleSource()
    dates = [dt.date(2026, 8, 24)]

    games = source.fetch_games(db_session, dates)
    assert games, "fonte de exemplo deveria devolver pelo menos um jogo"
    for game in games:
        assert isinstance(game, NormalizedGame)
        assert game.sport_code
        assert game.home_text and game.away_text
        assert isinstance(game.home_team_id, int)
        assert isinstance(game.away_team_id, int)

    count_first = upsert_games(db_session, source.code, games)
    db_session.commit()

    # recaptura os mesmos dados: upsert não deve duplicar linhas
    games_again = source.fetch_games(db_session, dates)
    count_second = upsert_games(db_session, source.code, games_again)
    db_session.commit()

    from app.core.models import Game

    persisted = (
        db_session.query(Game).filter(Game.source_code == source.code).all()
    )
    assert count_first == count_second == len(games) == len(persisted)
