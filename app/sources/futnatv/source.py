"""Adapter futnatv: implementa o protocol `Source` (app/core/source.py) sobre
a API de futnatv.net.

Uma chamada = um dia (não existe endpoint de intervalo — ver
docs/notas-de-campo.md #4), então uma execução completa é
`len(FUTNATV_SPORTS) * len(dates)` requisições sequenciais, espaçadas pelo
cliente HTTP.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Sequence

from sqlalchemy.orm import Session

from app.core.config import BRT
from app.core.ingest import TeamResolver
from app.core.source import CronSchedule, NormalizedBroadcast, NormalizedGame
from app.sources.futnatv.catalogs import ChannelIndex, CompetitionIndex, sync_all_catalogs
from app.sources.futnatv.client import Futnatv, FutnatvError
from app.sources.futnatv.config import FUTNATV_SOURCE_CODE, FUTNATV_SOURCE_NAME, FUTNATV_SPORTS
from app.sources.futnatv.normalize import (
    extract_youtube_id,
    parse_odds,
    parse_time,
    split_broadcast,
    split_platform_qualifier,
)

log = logging.getLogger(__name__)

# O endpoint consultado já usa o vocabulário canônico de esporte (ADR 0003) —
# mapeamento identidade, mas explícito: todo adapter declara essa tradução.
_SPORT_MAP = {sport: sport for sport in FUTNATV_SPORTS}


def _brief(raw: dict, limit: int = 200) -> str:
    """Identificação curta de um jogo cru, para a mensagem de erro — o payload
    inteiro estouraria o corpo de 1024 caracteres do Pushover."""
    text = repr(raw)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class FutnatvSource:
    code = FUTNATV_SOURCE_CODE
    name = FUTNATV_SOURCE_NAME

    # Horários dos jogos (pedido do projeto, horário de Brasília): 6:00,
    # 12:00, 18:00 e 23:40. Catálogo uma vez por dia, antes da primeira
    # coleta — canais/competições mudam em escala de semanas
    # (docs/legal-e-etiqueta.md), sincronizar 4x/dia seria desnecessário.
    games_schedule = (
        CronSchedule(hour="6,12,18", minute="0"),
        CronSchedule(hour="23", minute="40"),
    )
    catalog_schedule = (CronSchedule(hour="5", minute="55"),)

    def __init__(self) -> None:
        self._client = Futnatv()

    def sync_catalog(self, session: Session) -> dict:
        return sync_all_catalogs(session, self._client)

    def fetch_games(self, session: Session, dates: Sequence[dt.date]) -> list[NormalizedGame]:
        competitions = CompetitionIndex(session)
        channels = ChannelIndex(session)
        teams = TeamResolver(session, self.code)

        games: list[NormalizedGame] = []
        for sport in FUTNATV_SPORTS:
            for d in dates:
                day_key = d.isoformat()
                try:
                    payload = self._client.day(sport, day_key)
                except FutnatvError as exc:
                    log.error(
                        "erro ao buscar %s %s: %s: %s",
                        sport, day_key, type(exc).__name__, exc,
                    )
                    continue

                for day_obj in payload.get("schedule", []):
                    for raw in day_obj.get("games", []):
                        # Um jogo malformado (campo que sumiu, horário num
                        # formato novo) não pode derrubar os outros ~500 da
                        # execução — descarta só ele. O `log.error` é o que faz
                        # o descarte chegar até a notificação (ADR 0007): sem
                        # ele, isto seria perda de dado silenciosa.
                        try:
                            games.append(
                                self._normalize_game(
                                    raw,
                                    _SPORT_MAP[sport],
                                    day_obj.get("key", ""),
                                    competitions,
                                    channels,
                                    teams,
                                )
                            )
                        except Exception as exc:  # noqa: BLE001
                            log.error(
                                "jogo descartado (%s %s): %s: %s | payload=%s",
                                sport, day_key, type(exc).__name__, exc, _brief(raw),
                            )
        return games

    def _normalize_game(
        self,
        raw: dict,
        sport_code: str,
        day_key: str,
        competitions: CompetitionIndex,
        channels: ChannelIndex,
        teams: TeamResolver,
    ) -> NormalizedGame:
        hh, mm = parse_time(raw["time"])
        game_date = dt.date.fromisoformat(day_key)
        kickoff_at = dt.datetime(game_date.year, game_date.month, game_date.day, hh, mm, tzinfo=BRT)
        odds_home, odds_draw, odds_away = parse_odds(raw.get("odds"))
        broadcast_raw = raw.get("broadcast", "") or ""

        broadcasts: list[NormalizedBroadcast] = []
        for token in split_broadcast(broadcast_raw):
            platform_text, qualifier_text = split_platform_qualifier(token)
            channel_id, match_method = channels.match(platform_text)
            broadcasts.append(
                NormalizedBroadcast(
                    raw_token=token,
                    platform_text=platform_text,
                    qualifier_text=qualifier_text,
                    channel_id=channel_id,
                    match_method=match_method,
                )
            )

        return NormalizedGame(
            sport_code=sport_code,
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
            broadcast_raw=broadcast_raw,
            broadcasts=broadcasts,
            source_data={
                # `sport` do payload mente para nfl/nhl (docs/notas-de-campo.md
                # #2) — guardado à parte, nunca usado como sport_code.
                "payload_sport": raw.get("sport", sport_code),
                "odds_home": odds_home,
                "odds_draw": odds_draw,
                "odds_away": odds_away,
                "icon_emoji": raw.get("iconEmoji"),
                "country": raw.get("country"),
                "youtube_url": raw.get("youtubeUrl"),
                "youtube_id": extract_youtube_id(raw.get("youtubeUrl")),
                "aggregate": raw.get("aggregate"),
                "raw": raw,
            },
        )
