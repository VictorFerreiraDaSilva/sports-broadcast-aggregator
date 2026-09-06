"""Explicit registry of active sources (ADR 0001).

Adding a source means editing the `SOURCES` list below — nothing else in the
core changes. A late import (inside the module, not at the top of app/core/*)
would avoid the inverted coupling; since it is the registry itself that has to
know the sources, the import here is the only place in the core that knows
"futnatv" exists.

`app/sources/_example/` is deliberately absent: it is a fixture for the contract
test (tests/test_source_contract.py), and registering it would schedule a daily
job writing hardcoded games into the production database.
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import Source as SourceRow
from app.core.source import Source
from app.sources.futnatv.source import FutnatvSource

SOURCES: list[Source] = [
    FutnatvSource(),
]


def get_source(code: str) -> Source:
    for source in SOURCES:
        if source.code == code:
            return source
    raise KeyError(f"unknown source: {code!r} (registered: {[s.code for s in SOURCES]})")


def seed_sources(session: Session) -> None:
    """Upsert `source` from the registry — the dimension is derived from code,
    not hand-typed into a migration (ADR 0001)."""
    for source in SOURCES:
        stmt = (
            pg_insert(SourceRow)
            .values(code=source.code, name=source.name)
            .on_conflict_do_update(index_elements=[SourceRow.code], set_={"name": source.name})
        )
        session.execute(stmt)
    session.commit()
