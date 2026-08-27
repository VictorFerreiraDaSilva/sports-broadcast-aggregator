"""Contract test: ensures the `Source` interface (app/core/source.py) is
genuinely generic, by exercising it against every registered source — not only
against futnatv. app/sources/_example/ exists to make that possible without a
network (ADR 0001/0004/0005).

Requires DATABASE_URL (see tests/conftest.py) for the tests that touch the
database. The purely structural tests (identity, optional capability) also need
DATABASE_URL, but only because app.core.registry imports app.core.config in the
import chain — they run no query at all.
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
    """ADR 0004: sync_catalog is not required by the Protocol — a source only
    shows up with the capability if it actually implements it."""
    codes_with_catalog = {s.code for s in SOURCES if hasattr(s, "sync_catalog")}
    codes_without_catalog = {s.code for s in SOURCES if not hasattr(s, "sync_catalog")}

    assert "futnatv" in codes_with_catalog
    assert "_example" in codes_without_catalog

    # whoever has the capability also declares when it runs
    for source in SOURCES:
        if hasattr(source, "sync_catalog"):
            assert len(source.catalog_schedule) > 0


def test_example_source_round_trip(db_session):
    """End to end against a real database: fetch_games -> upsert_games ->
    re-query, plus idempotence on the natural key (source_code, sport_code,
    game_date, time_raw, home_text, away_text)."""
    from app.sources._example.source import ExampleSource

    source = ExampleSource()
    dates = [dt.date(2026, 8, 24)]

    games = source.fetch_games(db_session, dates)
    assert games, "the example source should return at least one game"
    for game in games:
        assert isinstance(game, NormalizedGame)
        assert game.sport_code
        assert game.home_text and game.away_text
        assert isinstance(game.home_team_id, int)
        assert isinstance(game.away_team_id, int)

    count_first = upsert_games(db_session, source.code, games)
    db_session.commit()

    # recapture the same data: upsert must not duplicate rows
    games_again = source.fetch_games(db_session, dates)
    count_second = upsert_games(db_session, source.code, games_again)
    db_session.commit()

    from app.core.models import Game

    persisted = (
        db_session.query(Game).filter(Game.source_code == source.code).all()
    )
    assert count_first == count_second == len(games) == len(persisted)
