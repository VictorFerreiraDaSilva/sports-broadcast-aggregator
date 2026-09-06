"""Test fixtures.

The tests that touch the database
(tests/test_source_contract.py::test_example_source_round_trip) need
`DATABASE_URL` pointing at a disposable Postgres — the schema is recreated from
scratch (`Base.metadata.drop_all` + `create_all`) on every test session. Do not
point it at a database holding data you care about.

    DATABASE_URL=postgresql+psycopg://fut:fut@localhost:55432/fut pytest
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def db_engine():
    from app.core.config import DATABASE_URL
    from app.core.models import Base, Source, Sport
    from app.core.registry import seed_sources
    from app.sources._example.source import ExampleSource
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(DATABASE_URL, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    # create_all does not run the migration's data seed (only the DDL) — seed
    # the two static dimensions (sport, source) once per test session.
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

    # The example source is not in the registry (it must never run in
    # production), so seed_sources does not cover it — but the tests that
    # exercise it write rows with a foreign key to `source`.
    example = ExampleSource()
    session.add(Source(code=example.code, name=example.name))
    session.commit()
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
    # clear the transactional tables between tests; `sport`/`source` are static
    # dimensions seeded once in db_engine and are left intact.
    for model in (ScrapeRun, CatalogMeta, Game, Team, Competition, Channel):
        session.query(model).delete()
    session.commit()
    session.close()
