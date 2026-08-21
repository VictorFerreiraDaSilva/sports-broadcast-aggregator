"""Sincronização dos catálogos estáticos (canais.json, competicoes-futebol.json)
e os índices de casamento usados por app/ingest.py para resolver
`broadcast`/`competition` (texto livre) em `channel`/`competition` (dimensão).

Os `?v=` da API são só cache-buster (ver docs/notas-de-campo.md #12); a versão
real do conteúdo é o campo `version` de dentro do JSON. Só regravamos quando
essa versão muda.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.client import Futnatv
from app.models import CatalogMeta, Channel, Competition
from app.normalize import family_fallback, normalize_key

log = logging.getLogger(__name__)


def _catalog_version(session: Session, key: str) -> str | None:
    row = session.get(CatalogMeta, key)
    return row.version if row else None


def _set_catalog_version(session: Session, key: str, version: str) -> None:
    stmt = (
        pg_insert(CatalogMeta)
        .values(key=key, version=version)
        .on_conflict_do_update(index_elements=[CatalogMeta.key], set_={"version": version})
    )
    session.execute(stmt)


def sync_channels(session: Session, client: Futnatv) -> dict:
    payload = client.channels_catalog()
    version = payload.get("version", "")
    if version and version == _catalog_version(session, "canais"):
        return {"skipped": True, "version": version}

    for item in payload.get("channels", []):
        stmt = (
            pg_insert(Channel)
            .values(
                name=item["name"],
                category=item["category"],
                priority=item["priority"],
                color=item.get("color"),
                dark_color=item.get("darkColor"),
                image=item.get("image"),
                dark_image=item.get("darkImage"),
                selected_image=item.get("selectedImage"),
                aliases=item.get("aliases", []),
                catalog_version=version,
            )
            .on_conflict_do_update(
                index_elements=[Channel.name],
                set_={
                    "category": item["category"],
                    "priority": item["priority"],
                    "color": item.get("color"),
                    "dark_color": item.get("darkColor"),
                    "image": item.get("image"),
                    "dark_image": item.get("darkImage"),
                    "selected_image": item.get("selectedImage"),
                    "aliases": item.get("aliases", []),
                    "catalog_version": version,
                },
            )
        )
        session.execute(stmt)

    _set_catalog_version(session, "canais", version)
    log.info("catálogo de canais sincronizado: %d itens, version=%s", len(payload.get("channels", [])), version)
    return {"skipped": False, "version": version, "count": len(payload.get("channels", []))}


def sync_competitions(session: Session, client: Futnatv) -> dict:
    payload = client.competitions_catalog()
    version = payload.get("version", "")
    if version and version == _catalog_version(session, "competicoes_futebol"):
        return {"skipped": True, "version": version}

    for item in payload.get("competitions", []):
        stmt = (
            pg_insert(Competition)
            .values(
                name=item["name"],
                category=item["category"],
                priority=item["priority"],
                image=item.get("image"),
                dark_image=item.get("darkImage"),
                selected_image=item.get("selectedImage"),
                aliases=item.get("aliases", []),
                catalog_version=version,
            )
            .on_conflict_do_update(
                index_elements=[Competition.name],
                set_={
                    "category": item["category"],
                    "priority": item["priority"],
                    "image": item.get("image"),
                    "dark_image": item.get("darkImage"),
                    "selected_image": item.get("selectedImage"),
                    "aliases": item.get("aliases", []),
                    "catalog_version": version,
                },
            )
        )
        session.execute(stmt)

    _set_catalog_version(session, "competicoes_futebol", version)
    log.info(
        "catálogo de competições sincronizado: %d itens, version=%s",
        len(payload.get("competitions", [])),
        version,
    )
    return {"skipped": False, "version": version, "count": len(payload.get("competitions", []))}


def sync_all_catalogs(session: Session, client: Futnatv) -> dict:
    channels = sync_channels(session, client)
    competitions = sync_competitions(session, client)
    return {"channels": channels, "competitions": competitions}


# --------------------------------------------------------------------------- índices de casamento


class ChannelIndex:
    """nome/alias normalizado -> Channel.id, com fallback de família (ESPN 4 -> ESPN)."""

    def __init__(self, session: Session):
        self._by_key: dict[str, int] = {}
        for ch in session.scalars(select(Channel)):
            self._by_key[normalize_key(ch.name)] = ch.id
            for alias in ch.aliases or []:
                self._by_key.setdefault(normalize_key(alias), ch.id)

    def match(self, platform_text: str) -> tuple[int | None, str]:
        key = normalize_key(platform_text)
        if key in self._by_key:
            return self._by_key[key], "exact"
        base = family_fallback(key)
        if base and base in self._by_key:
            return self._by_key[base], "family"
        return None, "none"


class CompetitionIndex:
    """nome/alias normalizado -> Competition.id."""

    def __init__(self, session: Session):
        self._by_key: dict[str, int] = {}
        for comp in session.scalars(select(Competition)):
            self._by_key[normalize_key(comp.name)] = comp.id
            for alias in comp.aliases or []:
                self._by_key.setdefault(normalize_key(alias), comp.id)

    def match(self, competition_text: str) -> int | None:
        return self._by_key.get(normalize_key(competition_text))
