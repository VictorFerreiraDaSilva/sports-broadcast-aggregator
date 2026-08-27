"""The aggregator's central schema (see docs/adr/0002, 0003, 0006 for the why).

- `source`: dimension of registered sources (ADR 0001), seeded from the
  registry in app/core/registry.py — not a catalog hand-typed here.
- `sport`: the only dimension shared across sources — a small, closed
  vocabulary that each adapter maps its own onto (ADR 0003).
- `channel`, `competition`, `team`: source-scoped dimensions (`source_code` is
  part of the uniqueness) — the same name in different sources is a different
  row, with no attempt at merging (ADR 0002/0003).
- `game`: the fact table, one row per game *per source that reported it* —
  `source_code` is part of the natural key (ADR 0002). Columns peculiar to a
  single source (odds, icons, raw payload, ...) get no column of their own
  here: they go into `source_data: JSONB`, opaque to the core (ADR 0006).
- `game_broadcast`: `broadcast_raw` split into tokens matched against
  `channel` — the source hands this over resolved (see app/core/source.py).
- `catalog_meta`: `version` of the catalog already synced, per source, to
  avoid rewriting when nothing changed.
- `scrape_run`: audit log of each job run, per source.
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
    """A source registered in app/core/registry.py (ADR 0001)."""

    __tablename__ = "source"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)


class Sport(Base):
    """Canonical sport, shared by every source (ADR 0003)."""

    __tablename__ = "sport"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)


class Channel(Base):
    """A source's channel/platform catalog — scoped by `source_code`."""

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
    """A source's competition catalog — scoped by `source_code`."""

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
    """Dimension derived from `home`/`away` — scoped by `source_code`.

    No stable ID at the origin; the key is the normalized name (accent-free,
    casefolded) within the source.
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
    """A game, the way one specific source reported it (ADR 0002).

    Natural key = (source_code, sport_code, game_date, time_raw, home_text,
    away_text) — no source provides a stable game ID. The same real game
    reported by two sources yields two independent rows, with no merging.
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
    """A `broadcast_raw` token matched (or not) against `channel`.

    The source already resolved the match (see app/core/source.py); this table
    only stores the result. It carries no `source_code` of its own — it
    inherits the game's source through `game_id`.
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
    """`version` of the catalog already written, per source, to avoid pointless rewrites."""

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
    """Audit log of each job run, per source."""

    __tablename__ = "scrape_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("source.code"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "games" | "catalog"
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # success  = clean run
    # degraded = wrote what it could, but swallowed errors along the way
    #            (ADR 0007); the count and the groups live in `details`
    # error    = lost the entire run; the cause lives in `error_message`
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Besides the job result (e.g. games_count), carries `errors_collected` and
    # `error_groups` when the run swallowed errors — including on "error" runs,
    # where the partials preceding the fatal failure would otherwise be lost.
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Fatal failure only. A partial error does not write here — see `details`.
    error_message: Mapped[str | None] = mapped_column(Text)
