"""Fixtures de teste.

Os testes que tocam banco (tests/test_source_contract.py::test_example_source_round_trip)
precisam de `DATABASE_URL` apontando para um Postgres descartável — o schema é
recriado do zero (`Base.metadata.drop_all` + `create_all`) a cada sessão de
teste. Não aponte para um banco com dados que importam.

    DATABASE_URL=postgresql+psycopg://fut:fut@localhost:55432/fut pytest
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def db_engine():
    from app.core.config import DATABASE_URL
    from app.core.models import Base, Sport
    from app.core.registry import seed_sources
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(DATABASE_URL, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    # create_all não roda o seed de dados da migration (só o DDL) — seed as
    # duas dimensões estáticas (sport, source) uma vez por sessão de teste.
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = Session()
    session.add_all(
        [
            Sport(code="futebol", name="Futebol"),
            Sport(code="basquete", name="Basquete"),
            Sport(code="volei", name="Vôlei"),
            Sport(code="nfl", name="NFL"),
            Sport(code="nhl", name="NHL"),
        ]
    )
    session.commit()
    seed_sources(session)
    session.close()

    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    from sqlalchemy.orm import sessionmaker

    from app.core.models import CatalogMeta, Channel, Competition, Game, ScrapeRun, Team

    Session = sessionmaker(bind=db_engine, expire_on_commit=False, future=True)
    session = Session()
    yield session
    session.rollback()
    # limpa as tabelas transacionais entre testes; `sport`/`source` são
    # dimensões estáticas seedadas uma vez em db_engine e ficam intactas.
    for model in (ScrapeRun, CatalogMeta, Game, Team, Competition, Channel):
        session.query(model).delete()
    session.commit()
    session.close()
