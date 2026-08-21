"""Schema do banco.

Visão geral (ver docs/schemas.md do repo para o porquê de cada decisão):

- `sport`, `channel`, `competition`: dimensões. `channel` e `competition` são os
  catálogos estáticos do site (canais.json / competicoes-futebol.json).
- `team`: dimensão derivada dos nomes vistos em `home`/`away`. A API não dá
  nenhum ID de time; a chave é o nome normalizado (sem acento, casefold).
  Times com o mesmo nome normalizado em ligas diferentes colidem — risco aceito
  e documentado no README.
- `game`: fato, uma linha por jogo. Chave natural = (sport_code, game_date,
  time_raw, home_text, away_text) — a API não dá ID de jogo. `sport_code` é o
  endpoint consultado (o melhor sinal disponível; o campo `sport` do payload
  não é confiável, por isso guardado à parte em `payload_sport`).
- `game_broadcast`: quebra `broadcast_raw` em tokens e casa cada um com
  `channel`. Guarda os dois níveis do valor (`YouTube (CazéTV)` -> plataforma
  "YouTube", qualificador "CazéTV"), porque o parêntese é a parte mais
  informativa do campo e não deve ser descartado.
- `scrape_run`: log de auditoria de cada execução do scheduler.
- `catalog_meta`: guarda a `version` de cada catálogo já sincronizado, para não
  regravar o catálogo inteiro quando ele não mudou.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Sport(Base):
    """Os 5 endpoints válidos da API (futebol/basquete/volei/nfl/nhl)."""

    __tablename__ = "sport"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)


class Channel(Base):
    """Catálogo de canais/plataformas (`GET /canais.json`)."""

    __tablename__ = "channel"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    color: Mapped[str | None] = mapped_column(String(32))
    dark_color: Mapped[str | None] = mapped_column(String(32))
    image: Mapped[str | None] = mapped_column(Text)
    dark_image: Mapped[str | None] = mapped_column(Text)
    selected_image: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    catalog_version: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    broadcasts: Mapped[list["GameBroadcast"]] = relationship(back_populates="channel")


class Competition(Base):
    """Catálogo de competições (`GET /competicoes-futebol.json`) — só futebol."""

    __tablename__ = "competition"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    image: Mapped[str | None] = mapped_column(Text)
    dark_image: Mapped[str | None] = mapped_column(Text)
    selected_image: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    catalog_version: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    games: Mapped[list["Game"]] = relationship(back_populates="competition")


class Team(Base):
    """Dimensão derivada de `home`/`away`. Sem ID estável na origem."""

    __tablename__ = "team"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    home_games: Mapped[list["Game"]] = relationship(
        back_populates="home_team", foreign_keys="Game.home_team_id"
    )
    away_games: Mapped[list["Game"]] = relationship(
        back_populates="away_team", foreign_keys="Game.away_team_id"
    )


class Game(Base):
    """Um jogo, identificado pela chave natural (sport_code, data, hora, times).

    `sport_code` é o endpoint consultado, não o campo `sport` do payload (que
    mente para nfl/nhl — ver docs/notas-de-campo.md #2). O campo cru fica em
    `payload_sport` só para referência/depuração.
    """

    __tablename__ = "game"
    __table_args__ = (
        UniqueConstraint(
            "sport_code", "game_date", "time_raw", "home_text", "away_text",
            name="uq_game_natural_key",
        ),
        Index("ix_game_date_sport", "game_date", "sport_code"),
        Index("ix_game_competition_id", "competition_id"),
        Index("ix_game_home_team_id", "home_team_id"),
        Index("ix_game_away_team_id", "away_team_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    sport_code: Mapped[str] = mapped_column(
        String(16), ForeignKey("sport.code"), nullable=False
    )
    payload_sport: Mapped[str] = mapped_column(String(16), nullable=False)

    game_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    time_raw: Mapped[str] = mapped_column(String(8), nullable=False)  # "13h00"
    kickoff_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    competition_text: Mapped[str] = mapped_column(String(128), nullable=False)
    competition_id: Mapped[int | None] = mapped_column(ForeignKey("competition.id"))
    round: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    home_text: Mapped[str] = mapped_column(String(128), nullable=False)
    home_team_id: Mapped[int | None] = mapped_column(ForeignKey("team.id"))
    away_text: Mapped[str] = mapped_column(String(128), nullable=False)
    away_team_id: Mapped[int | None] = mapped_column(ForeignKey("team.id"))

    broadcast_raw: Mapped[str] = mapped_column(Text, nullable=False, default="")
    has_broadcast: Mapped[bool] = mapped_column(
        Boolean, Computed("broadcast_raw <> ''", persisted=True), nullable=False
    )

    odds_home: Mapped[float | None] = mapped_column(Numeric(7, 2))
    odds_draw: Mapped[float | None] = mapped_column(Numeric(7, 2))
    odds_away: Mapped[float | None] = mapped_column(Numeric(7, 2))

    icon_emoji: Mapped[str | None] = mapped_column(String(8))
    country: Mapped[str | None] = mapped_column(String(8))
    youtube_url: Mapped[str | None] = mapped_column(Text)
    youtube_id: Mapped[str | None] = mapped_column(String(32))
    aggregate: Mapped[str | None] = mapped_column(String(32))

    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    competition: Mapped["Competition | None"] = relationship(back_populates="games")
    home_team: Mapped["Team | None"] = relationship(
        back_populates="home_games", foreign_keys=[home_team_id]
    )
    away_team: Mapped["Team | None"] = relationship(
        back_populates="away_games", foreign_keys=[away_team_id]
    )
    broadcasts: Mapped[list["GameBroadcast"]] = relationship(
        back_populates="game", cascade="all, delete-orphan", order_by="GameBroadcast.position"
    )


class GameBroadcast(Base):
    """Um token de `broadcast_raw` (ex.: "YouTube (CazéTV)") casado com `channel`.

    `platform_text` é o que tentamos casar contra o catálogo ("YouTube").
    `qualifier_text` é o conteúdo entre parênteses ("CazéTV"), guardado à parte
    porque é a parte mais informativa do campo e não deve ser descartada mesmo
    quando não fecha com nenhum item do catálogo.
    """

    __tablename__ = "game_broadcast"
    __table_args__ = (
        UniqueConstraint("game_id", "position", name="uq_game_broadcast_position"),
        Index("ix_game_broadcast_channel_id", "channel_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("game.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    raw_token: Mapped[str] = mapped_column(Text, nullable=False)
    platform_text: Mapped[str] = mapped_column(Text, nullable=False)
    qualifier_text: Mapped[str | None] = mapped_column(Text)

    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channel.id"))
    match_method: Mapped[str] = mapped_column(String(16), nullable=False)  # exact/alias/family/none

    game: Mapped["Game"] = relationship(back_populates="broadcasts")
    channel: Mapped["Channel | None"] = relationship(back_populates="broadcasts")


class CatalogMeta(Base):
    """`version` do catálogo já gravado, para não regravar quando não mudou."""

    __tablename__ = "catalog_meta"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)  # "canais" | "competicoes_futebol"
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    synced_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ScrapeRun(Base):
    """Log de auditoria de cada execução do scheduler."""

    __tablename__ = "scrape_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "games" | "catalogs"
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success | partial | error
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
