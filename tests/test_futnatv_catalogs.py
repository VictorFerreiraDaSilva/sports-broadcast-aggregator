"""Tests for the futnatv competition index — the part that decides whether a
schedule name reaches the catalog at all, and therefore whether the source can
contribute a hint to app/core/classification.py.

Touches the database (the index is built from `competition` rows), so it needs
`DATABASE_URL` pointing at a disposable Postgres — see tests/conftest.py.
"""

from __future__ import annotations

from app.core.models import Competition
from app.sources.futnatv.catalogs import CompetitionIndex
from app.sources.futnatv.config import FUTNATV_SOURCE_CODE


def _seed(session, *rows):
    """Seeds (name, category, aliases) triples as futnatv competitions."""
    for name, category, aliases in rows:
        session.add(
            Competition(
                source_code=FUTNATV_SOURCE_CODE,
                name=name,
                category=category,
                priority=1,
                aliases=list(aliases),
            )
        )
    session.commit()


def test_match_returns_category_alongside_the_id(db_session):
    _seed(db_session, ("Brasileirão - Série A", "Brasil", []))
    comp_id, category = CompetitionIndex(db_session).match("Brasileirão - Série A")
    assert isinstance(comp_id, int)
    assert category == "Brasil"


def test_match_is_accent_and_case_insensitive_and_reads_aliases(db_session):
    _seed(db_session, ("Libertadores", "Destaques", ["Copa Libertadores"]))
    index = CompetitionIndex(db_session)
    assert index.match("LIBERTADORES")[1] == "Destaques"
    assert index.match("Copa Libertadores")[1] == "Destaques"


def test_no_match_yields_no_evidence_either_way(db_session):
    _seed(db_session, ("Brasileirão - Série A", "Brasil", []))
    assert CompetitionIndex(db_session).match("Campeonato Inexistente") == (None, None)


def test_curated_alias_resolves_a_name_the_catalog_lacks(db_session):
    """The measured case: 18 games written `Champions League` matched nothing,
    because the catalog only carries `UEFA Champions League` with no aliases
    (docs/field-notes.md #16)."""
    _seed(
        db_session,
        ("UEFA Champions League", "Destaques", []),
        ("AFC Champions League", "Ásia", []),
        ("UEFA Women's Champions League", "Feminino", []),
    )
    uefa_id, _ = CompetitionIndex(db_session).match("UEFA Champions League")
    assert CompetitionIndex(db_session).match("Champions League") == (uefa_id, "Destaques")


def test_curated_alias_never_overrides_a_real_catalog_name(db_session):
    """If futnatv ever publishes `Champions League` as a competition of its
    own, the catalog wins — curation only fills gaps."""
    _seed(
        db_session,
        ("UEFA Champions League", "Destaques", []),
        ("Champions League", "Outros", []),
    )
    assert CompetitionIndex(db_session).match("Champions League")[1] == "Outros"


def test_curated_alias_pointing_nowhere_is_dropped_not_guessed(db_session):
    """Catalog renamed the target: leave the name unmatched rather than aim it
    at one of the four other competitions containing 'champions league'."""
    _seed(db_session, ("AFC Champions League", "Ásia", []))
    assert CompetitionIndex(db_session).match("Champions League") == (None, None)
