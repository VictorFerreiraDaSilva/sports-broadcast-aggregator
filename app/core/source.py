"""O contrato `Source` — o único ponto de acoplamento entre o core e uma fonte.

Ver docs/adr/0001 (registro explícito), 0003 (esporte canônico), 0004
(`sync_catalog` opcional), 0005 (core vs app/sources/<fonte>/) e 0006 (schema
enxuto + `source_data` opaco).

`fetch_games` é a única obrigação. `sync_catalog` é uma capacidade opcional —
o orquestrador detecta se uma fonte a implementa com
`hasattr(source, "sync_catalog")` (ver app/core/registry.py) em vez de exigir
um método no-op de toda fonte só por uniformidade.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CronSchedule:
    """Um horário cron, no fuso de `app.core.config.BRT`."""

    hour: str
    minute: str = "0"


@dataclass(frozen=True)
class NormalizedBroadcast:
    """Um token de transmissão já casado (ou não) contra o catálogo da fonte.

    O core não sabe *como* uma fonte tokeniza/casa `broadcast_raw` — isso é
    peculiaridade de fonte (ADR 0003/0006). A fonte entrega o resultado já
    resolvido; o core só grava.
    """

    raw_token: str
    platform_text: str
    qualifier_text: str | None
    channel_id: int | None
    match_method: str  # "exact" | "alias" | "family" | "none"


@dataclass(frozen=True)
class NormalizedGame:
    """Um jogo normalizado para o esporte canônico, pronto para o core gravar.

    `competition_id`/`home_team_id`/`away_team_id`/`channel_id` (dentro de
    `broadcasts`) já vêm resolvidos pela fonte contra seus próprios catálogos
    escopados (ADR 0003) — o core nunca faz esse casamento.

    `source_data` carrega tudo que é peculiar da fonte e não tem coluna
    própria no core (odds, ícones, payload cru, ...) — ADR 0006.
    """

    sport_code: str
    game_date: dt.date
    time_raw: str
    kickoff_at: dt.datetime
    competition_text: str
    competition_id: int | None
    round: str
    home_text: str
    home_team_id: int
    away_text: str
    away_team_id: int
    broadcast_raw: str
    broadcasts: list[NormalizedBroadcast] = field(default_factory=list)
    source_data: dict = field(default_factory=dict)


class Source(Protocol):
    """O que toda fonte precisa implementar para entrar no registro (ADR 0001)."""

    code: str
    name: str
    games_schedule: Sequence[CronSchedule]

    def fetch_games(self, session: Session, dates: Sequence[dt.date]) -> list[NormalizedGame]:
        """Busca e normaliza os jogos de `dates`.

        Pode ler/escrever nas dimensões escopadas por esta fonte (`team`,
        `channel`, `competition`) através de `session` para resolver os IDs
        que devolve em `NormalizedGame` — mas não grava em `game`/
        `game_broadcast` nem faz commit: isso é responsabilidade genérica do
        core (app/core/ingest.py).
        """
        ...

    # Capacidade opcional (ADR 0004) — implementada só por fontes com um
    # catálogo real para sincronizar. Não faz parte do Protocol formalmente
    # porque nem toda fonte a tem; ver app/core/registry.py para a detecção.
    #
    # def sync_catalog(self, session: Session) -> dict: ...
    # catalog_schedule: Sequence[CronSchedule]
