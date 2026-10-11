"""Generic upsert of `NormalizedGame` into `game`/`game_broadcast`, plus `team`
resolution — the only dimension whose matching logic (normalized name) is
generic enough to live in the core instead of in each source (ADR 0003:
`channel`/`competition` remain source-specific matching).

It also applies the canonical competition classification (app/core/classification.py,
ADR 0008) — generic for the same reason team resolution is: it works off
`competition_text`, which every source hands over, and a source that offers no
hint still gets classified from the name.

Nothing here knows the format of a specific source — only the shape of
`NormalizedGame` (app/core/source.py).
"""

from __future__ import annotations

import datetime as dt
import unicodedata
from typing import Callable, Mapping

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import BRT, DAYS_AHEAD
from app.core.models import Competition, Game, GameBroadcast, Team
from app.core.source import NormalizedGame
from app.core.classification import METHOD_NONE, classify

_NATURAL_KEY_COLS = {
    "source_code", "sport_code", "game_date", "time_raw", "home_text", "away_text",
}


def target_dates(today: dt.date | None = None) -> list[dt.date]:
    """Today (BRT) + DAYS_AHEAD days — the requirement is "today + 3 days"."""
    base = today or dt.datetime.now(BRT).date()
    return [base + dt.timedelta(days=i) for i in range(DAYS_AHEAD + 1)]


def _normalize_name(name: str) -> str:
    """trim + casefold + accent-free — the team matching key.

    Deliberately minimal normalization, independent of any source's own (e.g.
    app/sources/futnatv/normalize.py) — the core does not depend on source
    code (ADR 0005).
    """
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip().casefold()


class TeamResolver:
    """In-memory cache of normalized_name -> Team.id for one run, scoped by
    `source_code` (each instance serves a single source, so the cache does not
    need the source in its key)."""

    def __init__(self, session: Session, source_code: str):
        self.session = session
        self.source_code = source_code
        self._cache: dict[str, int] = {}

    def resolve(self, display_name: str) -> int:
        key = _normalize_name(display_name)
        if key in self._cache:
            return self._cache[key]

        stmt = (
            pg_insert(Team)
            .values(source_code=self.source_code, normalized_name=key, display_name=display_name)
            .on_conflict_do_nothing(index_elements=[Team.source_code, Team.normalized_name])
            .returning(Team.id)
        )
        team_id = self.session.execute(stmt).scalar()
        if team_id is None:
            team_id = self.session.execute(
                select(Team.id).where(
                    Team.source_code == self.source_code, Team.normalized_name == key
                )
            ).scalar_one()
        self._cache[key] = team_id
        return team_id


def _replace_broadcasts(session: Session, game_id: int, game: NormalizedGame) -> None:
    """Recomputed from scratch on every capture — the source already handed
    over the resolved tokens (NormalizedGame.broadcasts); the core only
    writes them."""
    session.execute(delete(GameBroadcast).where(GameBroadcast.game_id == game_id))
    for position, b in enumerate(game.broadcasts):
        session.add(
            GameBroadcast(
                game_id=game_id,
                position=position,
                raw_token=b.raw_token,
                platform_text=b.platform_text,
                qualifier_text=b.qualifier_text,
                channel_id=b.channel_id,
                match_method=b.match_method,
            )
        )


def upsert_games(session: Session, source_code: str, games: list[NormalizedGame]) -> int:
    """Generic upsert of `game` + `game_broadcast` from already-normalized
    games. Does not commit — the caller decides the granularity
    (see app/core/jobs.py)."""
    for game in games:
        # Recomputed on every capture, like the broadcasts below: the source's
        # hints and the curated lists can both have changed since last time
        # (ADR 0008).
        classification = classify(game.competition_text, game.tier_hint, game.gender_hint)
        values = dict(
            source_code=source_code,
            sport_code=game.sport_code,
            game_date=game.game_date,
            time_raw=game.time_raw,
            kickoff_at=game.kickoff_at,
            competition_text=game.competition_text,
            competition_id=game.competition_id,
            round=game.round,
            home_text=game.home_text,
            home_team_id=game.home_team_id,
            away_text=game.away_text,
            away_team_id=game.away_team_id,
            broadcast_raw=game.broadcast_raw,
            source_data=game.source_data,
            tier=classification.tier,
            tier_method=classification.tier_method,
            gender=classification.gender,
            gender_method=classification.gender_method,
        )
        update_values = {k: v for k, v in values.items() if k not in _NATURAL_KEY_COLS}
        update_values["last_seen_at"] = func.now()

        stmt = (
            pg_insert(Game)
            .values(**values)
            .on_conflict_do_update(constraint="uq_game_natural_key", set_=update_values)
            .returning(Game.id)
        )
        game_id = session.execute(stmt).scalar_one()
        _replace_broadcasts(session, game_id, game)

    return len(games)


def reclassify_games(
    session: Session,
    competition_hints: Mapping[str, Callable[[str], tuple[str | None, str | None]]] | None = None,
) -> dict:
    """Re-apply app/core/classification.py to games already stored — what to run after
    editing the curated lists, since `tier`/`gender` are resolved at ingestion
    and the collection window only covers today..today+DAYS_AHEAD.

    The source hint is recomputed from what the row does keep: its
    `competition_id`, whose `competition.category` each source translates
    through its optional `competition_hints` (`competition_hints` here maps
    source code -> that method). A source without it, or a game whose name never
    matched the catalog, gets no hint — the same as at ingestion.

    It only ever adds knowledge: an axis is rewritten only when the fresh
    classification has a rule behind it (anything but `none`), so a row is
    never demoted to `unknown`. That makes it idempotent and safe to rerun.
    """
    competition_hints = competition_hints or {}
    updated = 0
    rows = session.execute(
        select(Game, Competition.category).outerjoin(
            Competition, Competition.id == Game.competition_id
        )
    )
    for game, category in rows:
        to_hints = competition_hints.get(game.source_code)
        tier_hint, gender_hint = (
            to_hints(category) if to_hints is not None and category is not None else (None, None)
        )
        fresh = classify(game.competition_text, tier_hint, gender_hint)
        if fresh.tier_method != METHOD_NONE and (
            game.tier != fresh.tier or game.tier_method != fresh.tier_method
        ):
            game.tier = fresh.tier
            game.tier_method = fresh.tier_method
            updated += 1
        if fresh.gender_method != METHOD_NONE and (
            game.gender != fresh.gender or game.gender_method != fresh.gender_method
        ):
            game.gender = fresh.gender
            game.gender_method = fresh.gender_method
            updated += 1
    return {"rows_updated": updated}
