"""Generic upsert of `NormalizedGame` into `game`/`game_broadcast`, plus `team`
resolution — the only dimension whose matching logic (normalized name) is
generic enough to live in the core instead of in each source (ADR 0003:
`channel`/`competition` remain source-specific matching).

Nothing here knows the format of a specific source — only the shape of
`NormalizedGame` (app/core/source.py).
"""

from __future__ import annotations

import datetime as dt
import unicodedata

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import BRT, DAYS_AHEAD
from app.core.models import Game, GameBroadcast, Team
from app.core.source import NormalizedGame

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
