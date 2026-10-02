"""Syncing of the static catalogs (canais.json, competicoes-futebol.json) and
the matching indexes used by app/sources/futnatv/source.py to resolve
`broadcast`/`competition` (free text) into `channel`/`competition` (dimension)
— all of it scoped to `source_code="futnatv"` (ADR 0003).

The API's `?v=` is only a cache buster (see docs/field-notes.md #12); the real
content version is the `version` field inside the JSON. We only rewrite when
that version changes.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import CatalogMeta, Channel, Competition
from app.sources.futnatv.client import Futnatv
from app.sources.futnatv.config import FUTNATV_SOURCE_CODE
from app.sources.futnatv.normalize import family_fallback, normalize_key

log = logging.getLogger(__name__)


def _catalog_version(session: Session, key: str) -> str | None:
    row = session.get(CatalogMeta, (FUTNATV_SOURCE_CODE, key))
    return row.version if row else None


def _set_catalog_version(session: Session, key: str, version: str) -> None:
    stmt = (
        pg_insert(CatalogMeta)
        .values(source_code=FUTNATV_SOURCE_CODE, key=key, version=version)
        .on_conflict_do_update(
            index_elements=[CatalogMeta.source_code, CatalogMeta.key], set_={"version": version}
        )
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
                source_code=FUTNATV_SOURCE_CODE,
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
                index_elements=[Channel.source_code, Channel.name],
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
    log.info("channel catalog synced: %d items, version=%s", len(payload.get("channels", [])), version)
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
                source_code=FUTNATV_SOURCE_CODE,
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
                index_elements=[Competition.source_code, Competition.name],
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
        "competition catalog synced: %d items, version=%s",
        len(payload.get("competitions", [])),
        version,
    )
    return {"skipped": False, "version": version, "count": len(payload.get("competitions", []))}


def sync_all_catalogs(session: Session, client: Futnatv) -> dict:
    channels = sync_channels(session, client)
    competitions = sync_competitions(session, client)
    return {"channels": channels, "competitions": competitions}


# ------------------------------------------------------------------------------ matching indexes


class ChannelIndex:
    """normalized name/alias -> Channel.id, with a family fallback (ESPN 4 -> ESPN)."""

    def __init__(self, session: Session):
        self._by_key: dict[str, int] = {}
        stmt = select(Channel).where(Channel.source_code == FUTNATV_SOURCE_CODE)
        for ch in session.scalars(stmt):
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


# Names the schedule writes that the published catalog carries under a
# different name and does not list as an alias. Each entry is a *curated*
# claim, never a heuristic: the catalog holds five competitions containing
# "champions league" (UEFA, AFC, AFC 2, UEFA Women's, Pré-), so any generic
# substring or family fallback here would silently pick the wrong one — which
# is why ChannelIndex's family reduction has no counterpart in this class.
#
# `Champions League` was verified against the games themselves (Real Madrid,
# Barcelona, PSG, Bayern, "Fase de Liga"): the schedule uses the bare name for
# the UEFA competition and the catalog's own name for the others. If futnatv
# ever starts writing the bare name for an AFC game, this line becomes wrong —
# the curation query in the README (tier_method = 'none') is not what catches
# that, so treat it as a claim to re-check when the AFC season starts.
EXTRA_COMPETITION_ALIASES = {
    "champions league": "UEFA Champions League",
}


class CompetitionIndex:
    """normalized name/alias -> (Competition.id, Competition.category).

    The category comes out with the id because the source, not the core, is
    what may interpret futnatv's own vocabulary (ADR 0003) — it becomes the
    `tier_hint`/`gender_hint` of app/core/classification.py (ADR 0008).
    """

    def __init__(self, session: Session):
        self._by_key: dict[str, tuple[int, str]] = {}
        # Real catalog names only: an EXTRA_COMPETITION_ALIASES target must be
        # a competition the catalog actually publishes, never another alias.
        by_name: dict[str, tuple[int, str]] = {}
        stmt = select(Competition).where(Competition.source_code == FUTNATV_SOURCE_CODE)
        for comp in session.scalars(stmt):
            entry = (comp.id, comp.category)
            by_name[normalize_key(comp.name)] = entry
            self._by_key[normalize_key(comp.name)] = entry
            for alias in comp.aliases or []:
                self._by_key.setdefault(normalize_key(alias), entry)

        for alias, target_name in EXTRA_COMPETITION_ALIASES.items():
            entry = by_name.get(normalize_key(target_name))
            if entry is None:
                # The catalog dropped or renamed the target: leave the alias
                # unresolved rather than pointing it somewhere else.
                log.warning("extra competition alias %r targets unknown %r", alias, target_name)
                continue
            self._by_key.setdefault(normalize_key(alias), entry)

    def match(self, competition_text: str) -> tuple[int | None, str | None]:
        entry = self._by_key.get(normalize_key(competition_text))
        return entry if entry is not None else (None, None)
