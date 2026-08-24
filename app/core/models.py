"""Schema central do agregador (ver docs/adr/0002, 0003, 0006 para o porquê).

- `source`: dimensão das fontes registradas (ADR 0001), seedada a partir do
  registro em app/core/registry.py — não é um catálogo digitado à mão aqui.
- `sport`: a única dimensão compartilhada entre fontes — um vocabulário
  pequeno e fechado que cada adapter mapeia o seu próprio para (ADR 0003).
- `channel`, `competition`, `team`: dimensões escopadas por fonte
  (`source_code` entra na unicidade) — o mesmo nome em fontes diferentes é
  uma linha diferente, sem tentativa de fusão (ADR 0002/0003).
- `game`: fato, uma linha por jogo *por fonte que o relatou* — `source_code`
  entra na chave natural (ADR 0002). Colunas peculiares de uma fonte (odds,
  ícones, payload cru, ...) não têm coluna própria aqui: vão em
  `source_data: JSONB`, opaco ao core (ADR 0006).
- `game_broadcast`: quebra de `broadcast_raw` em tokens casados com
  `channel` — a fonte já entrega isso resolvido (ver app/core/source.py).
- `catalog_meta`: `version` do catálogo já sincronizado, por fonte, para não
  regravar quando não mudou.
- `scrape_run`: log de auditoria de cada execução de job, por fonte.
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


class Source(Base):
    """Uma fonte registrada em app/core/registry.py (ADR 0001)."""

    __tablename__ = "source"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)


class Sport(Base):
    """Esporte canônico, compartilhado por todas as fontes (ADR 0003)."""

    __tablename__ = "sport"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)


class Channel(Base):
    """Catálogo de canais/plataformas de uma fonte — escopado por `source_code`."""

    __tablename__ = "channel"
    __table_args__ = (
        UniqueConstraint("source_code", "name", name="uq_channel_source_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("source.code"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
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
    """Catálogo de competições de uma fonte — escopado por `source_code`."""

    __tablename__ = "competition"
    __table_args__ = (
        UniqueConstraint("source_code", "name", name="uq_competition_source_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("source.code"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
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
    """Dimensão derivada de `home`/`away` — escopada por `source_code`.

    Sem ID estável na origem; a chave é o nome normalizado (sem acento,
    casefold) dentro da fonte.
    """

    __tablename__ = "team"
    __table_args__ = (
        UniqueConstraint(
            "source_code", "normalized_name", name="uq_team_source_normalized_name"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("source.code"), nullable=False
    )
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False)
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
    """Um jogo, do jeito que uma fonte específica o relatou (ADR 0002).

    Chave natural = (source_code, sport_code, game_date, time_raw, home_text,
    away_text) — nenhuma fonte dá ID de jogo estável. O mesmo jogo real
    relatado por duas fontes gera duas linhas independentes, sem fusão.
    """

    __tablename__ = "game"
    __table_args__ = (
        UniqueConstraint(
            "source_code", "sport_code", "game_date", "time_raw", "home_text", "away_text",
            name="uq_game_natural_key",
        ),
        Index("ix_game_date_sport", "game_date", "sport_code"),
        Index("ix_game_source", "source_code"),
        Index("ix_game_competition_id", "competition_id"),
        Index("ix_game_home_team_id", "home_team_id"),
        Index("ix_game_away_team_id", "away_team_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    source_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("source.code"), nullable=False
    )
    sport_code: Mapped[str] = mapped_column(
        String(16), ForeignKey("sport.code"), nullable=False
    )

    game_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    time_raw: Mapped[str] = mapped_column(String(8), nullable=False)
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

    source_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

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
    """Um token de `broadcast_raw` casado (ou não) com `channel`.

    A fonte já resolveu o casamento (ver app/core/source.py); esta tabela só
    guarda o resultado. Não carrega `source_code` próprio — herda o da fonte
    do jogo via `game_id`.
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
    """`version` do catálogo já gravado por fonte, para não regravar à toa."""

    __tablename__ = "catalog_meta"

    source_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("source.code"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    synced_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ScrapeRun(Base):
    """Log de auditoria de cada execução de job, por fonte."""

    __tablename__ = "scrape_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("source.code"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "games" | "catalog"
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success | error
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
