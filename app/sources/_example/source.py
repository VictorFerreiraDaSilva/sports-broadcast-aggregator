"""Fonte fake, sem rede — só para provar mecanicamente que registrar uma
segunda fonte não toca app/core/ (ADR 0001/0005). Dados hardcoded.

Não implementa `sync_catalog` de propósito: prova o outro lado do contrato
(ADR 0004) — uma fonte sem catálogo real simplesmente não expõe o método, e o
orquestrador não agenda o job de catálogo para ela.
"""

from __future__ import annotations

import datetime as dt
from typing import Sequence

from sqlalchemy.orm import Session

from app.core.ingest import TeamResolver
from app.core.source import CronSchedule, NormalizedBroadcast, NormalizedGame

_HARDCODED_GAMES = (
    {
        "sport": "futebol",
        "time": "16h00",
        "competition": "Liga Exemplo",
        "round": "1ª Rodada",
        "home": "Time Alfa",
        "away": "Time Beta",
        "broadcast": "Canal Exemplo",
    },
    {
        "sport": "basquete",
        "time": "20h30",
        "competition": "Copa Exemplo",
        "round": "",
        "home": "Clube Gama",
        "away": "Clube Delta",
        "broadcast": "",
    },
)


class ExampleSource:
    code = "_example"
    name = "Fonte de exemplo (fake)"

    games_schedule = (CronSchedule(hour="7", minute="0"),)

    def fetch_games(self, session: Session, dates: Sequence[dt.date]) -> list[NormalizedGame]:
        teams = TeamResolver(session, self.code)

        games: list[NormalizedGame] = []
        for d in dates:
            for raw in _HARDCODED_GAMES:
                hh, mm = (int(part) for part in raw["time"].split("h"))
                kickoff_at = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=dt.timezone.utc)
                broadcast_raw = raw["broadcast"]
                broadcasts: list[NormalizedBroadcast] = []
                if broadcast_raw:
                    broadcasts.append(
                        NormalizedBroadcast(
                            raw_token=broadcast_raw,
                            platform_text=broadcast_raw,
                            qualifier_text=None,
                            channel_id=None,  # sem catálogo — fonte não implementa sync_catalog
                            match_method="none",
                        )
                    )

                games.append(
                    NormalizedGame(
                        sport_code=raw["sport"],
                        game_date=d,
                        time_raw=raw["time"],
                        kickoff_at=kickoff_at,
                        competition_text=raw["competition"],
                        competition_id=None,
                        round=raw["round"],
                        home_text=raw["home"],
                        home_team_id=teams.resolve(raw["home"]),
                        away_text=raw["away"],
                        away_team_id=teams.resolve(raw["away"]),
                        broadcast_raw=broadcast_raw,
                        broadcasts=broadcasts,
                        source_data={"note": "dados fake, sem rede — app/sources/_example/"},
                    )
                )
        return games
