"""Registro explícito de fontes ativas (ADR 0001).

Adicionar uma fonte é editar a lista `SOURCES` abaixo — nada mais no core
muda. Import tardio (dentro do módulo, não no topo de app/core/*) evitaria
o acoplamento inverso; como é o próprio registro que precisa conhecer as
fontes, o import aqui é o único lugar do core que sabe que "futnatv" e
"_example" existem.
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import Source as SourceRow
from app.core.source import Source
from app.sources._example.source import ExampleSource
from app.sources.futnatv.source import FutnatvSource

SOURCES: list[Source] = [
    FutnatvSource(),
    ExampleSource(),
]


def get_source(code: str) -> Source:
    for source in SOURCES:
        if source.code == code:
            return source
    raise KeyError(f"fonte desconhecida: {code!r} (registradas: {[s.code for s in SOURCES]})")


def seed_sources(session: Session) -> None:
    """Upsert de `source` a partir do registro — a dimensão é derivada do
    código, não digitada à mão numa migration (ADR 0001)."""
    for source in SOURCES:
        stmt = (
            pg_insert(SourceRow)
            .values(code=source.code, name=source.name)
            .on_conflict_do_update(index_elements=[SourceRow.code], set_={"name": source.name})
        )
        session.execute(stmt)
    session.commit()
