"""Coleta e upsert dos jogos (`/api/{sport}?data=...`) no banco.

Uma chamada = um dia (não existe endpoint de intervalo — ver
docs/notas-de-campo.md #4), então uma execução completa é
`len(SPORTS) * (DAYS_AHEAD + 1)` requisições sequenciais, espaçadas pelo
cliente HTTP.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.catalogs import ChannelIndex, CompetitionIndex
from app.client import Futnatv, FutnatvError
from app.config import BRT, DAYS_AHEAD, SPORTS
from app.models import Game, GameBroadcast, Team
from app.normalize import (
    extract_youtube_id,
    normalize_team_name,
    parse_odds,
    parse_time,
    split_broadcast,
    split_platform_qualifier,
)

log = logging.getLogger(__name__)

# Colunas da chave natural — nunca entram no SET do upsert.
_NATURAL_KEY_COLS = {"sport_code", "game_date", "time_raw", "home_text", "away_text"}


def target_dates(today: dt.date | None = None) -> list[dt.date]:
    """Hoje (BRT) + DAYS_AHEAD dias — o pedido é "hoje + 3 dias"."""
    base = today or dt.datetime.now(BRT).date()
    return [base + dt.timedelta(days=i) for i in range(DAYS_AHEAD + 1)]


class TeamResolver:
    """Cache em memória de normalized_name -> Team.id para uma execução."""

    def __init__(self, session: Session):
        self.session = session
        self._cache: dict[str, int] = {}

    def resolve(self, display_name: str) -> int:
        key = normalize_team_name(display_name)
        if key in self._cache:
            return self._cache[key]

        stmt = (
            pg_insert(Team)
            .values(normalized_name=key, display_name=display_name)
            .on_conflict_do_nothing(index_elements=[Team.normalized_name])
            .returning(Team.id)
        )
        team_id = self.session.execute(stmt).scalar()
        if team_id is None:
            team_id = self.session.execute(
                select(Team.id).where(Team.normalized_name == key)
            ).scalar_one()
        self._cache[key] = team_id
        return team_id


def _upsert_game(
    session: Session,
    sport_code: str,
    day_key: str,
    raw: dict,
    competitions: CompetitionIndex,
    teams: TeamResolver,
) -> int:
    hh, mm = parse_time(raw["time"])
    game_date = dt.date.fromisoformat(day_key)
    kickoff_at = dt.datetime(game_date.year, game_date.month, game_date.day, hh, mm, tzinfo=BRT)
    odds_home, odds_draw, odds_away = parse_odds(raw.get("odds"))

    values = dict(
        sport_code=sport_code,
        payload_sport=raw.get("sport", sport_code),
        game_date=game_date,
        time_raw=raw["time"],
        kickoff_at=kickoff_at,
        competition_text=raw["competition"],
        competition_id=competitions.match(raw["competition"]),
        round=raw.get("round", "") or "",
        home_text=raw["home"],
        home_team_id=teams.resolve(raw["home"]),
        away_text=raw["away"],
        away_team_id=teams.resolve(raw["away"]),
        broadcast_raw=raw.get("broadcast", "") or "",
        odds_home=odds_home,
        odds_draw=odds_draw,
        odds_away=odds_away,
        icon_emoji=raw.get("iconEmoji"),
        country=raw.get("country"),
        youtube_url=raw.get("youtubeUrl"),
        youtube_id=extract_youtube_id(raw.get("youtubeUrl")),
        aggregate=raw.get("aggregate"),
        raw_payload=raw,
    )

    update_values = {k: v for k, v in values.items() if k not in _NATURAL_KEY_COLS}
    update_values["last_seen_at"] = func.now()

    stmt = (
        pg_insert(Game)
        .values(**values)
        .on_conflict_do_update(constraint="uq_game_natural_key", set_=update_values)
        .returning(Game.id)
    )
    return session.execute(stmt).scalar_one()


def _replace_broadcasts(
    session: Session, game_id: int, broadcast_raw: str, channels: ChannelIndex
) -> None:
    """Recalcula a quebra de `broadcast_raw` do zero a cada captura — mais
    simples e correto do que tentar casar/atualizar tokens incrementalmente,
    e o campo é curto o bastante para o custo ser irrelevante."""
    session.execute(delete(GameBroadcast).where(GameBroadcast.game_id == game_id))
    for position, token in enumerate(split_broadcast(broadcast_raw)):
        platform_text, qualifier_text = split_platform_qualifier(token)
        channel_id, match_method = channels.match(platform_text)
        session.add(
            GameBroadcast(
                game_id=game_id,
                position=position,
                raw_token=token,
                platform_text=platform_text,
                qualifier_text=qualifier_text,
                channel_id=channel_id,
                match_method=match_method,
            )
        )


def scrape_games(
    session: Session, client: Futnatv, dates: list[dt.date] | None = None
) -> dict:
    """Captura todos os esportes para `dates` (default: target_dates()) e
    faz upsert no banco. Retorna um resumo por esporte/data para o log de
    auditoria (`scrape_run.details`)."""
    dates = dates or target_dates()
    competitions = CompetitionIndex(session)
    channels = ChannelIndex(session)
    teams = TeamResolver(session)

    per_sport: dict[str, dict[str, int]] = {}
    errors: list[str] = []

    for sport in SPORTS:
        per_date: dict[str, int] = {}
        for d in dates:
            day_key = d.isoformat()
            try:
                payload = client.day(sport, day_key)
            except FutnatvError as exc:
                log.error("erro ao buscar %s %s: %s", sport, day_key, exc)
                errors.append(f"{sport} {day_key}: {exc}")
                continue

            games_count = 0
            for day_obj in payload.get("schedule", []):
                for raw in day_obj.get("games", []):
                    game_id = _upsert_game(session, sport, day_obj["key"], raw, competitions, teams)
                    _replace_broadcasts(session, game_id, raw.get("broadcast", "") or "", channels)
                    games_count += 1
            per_date[day_key] = games_count
            session.commit()
        per_sport[sport] = per_date
        log.info("sport=%s capturado: %s", sport, per_date)

    return {"per_sport": per_sport, "errors": errors}
