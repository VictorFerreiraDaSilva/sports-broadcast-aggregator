"""The `Source` contract — the only coupling point between the core and a source.

See docs/adr/0001 (explicit registry), 0003 (canonical sport), 0004 (optional
`sync_catalog`), 0005 (core vs app/sources/<source>/) and 0006 (lean schema +
opaque `source_data`).

`fetch_games` is the only obligation. `sync_catalog` is an optional capability —
the orchestrator detects whether a source implements it with
`hasattr(source, "sync_catalog")` (see app/core/registry.py) instead of forcing
every source to carry a no-op method just for uniformity.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CronSchedule:
    """A cron time, in the `app.core.config.BRT` timezone."""

    hour: str
    minute: str = "0"


@dataclass(frozen=True)
class NormalizedBroadcast:
    """A broadcast token already matched (or not) against the source's catalog.

    The core does not know *how* a source tokenizes/matches `broadcast_raw` —
    that is a source peculiarity (ADR 0003/0006). The source hands over the
    resolved result; the core only writes it.
    """

    raw_token: str
    platform_text: str
    qualifier_text: str | None
    channel_id: int | None
    match_method: str  # "exact" | "alias" | "family" | "none"


@dataclass(frozen=True)
class NormalizedGame:
    """A game normalized to the canonical sport, ready for the core to write.

    `competition_id`/`home_team_id`/`away_team_id`/`channel_id` (inside
    `broadcasts`) already come resolved by the source against its own scoped
    catalogs (ADR 0003) — the core never does that matching.

    `source_data` carries everything peculiar to the source that has no column
    of its own in the core (odds, icons, raw payload, ...) — ADR 0006.

    `tier_hint`/`gender_hint` are the only optional *contributions*: what the
    source can say about the competition's level and gender from its own
    vocabulary, for app/core/classification.py to weigh against the name (ADR 0008). A
    source that knows nothing leaves them at None and is classified from the
    name alone — nothing here is required to implement them.
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
    tier_hint: str | None = None  # "youth" | "professional" | None
    gender_hint: str | None = None  # "women" | "men" | None


class Source(Protocol):
    """What every source must implement to enter the registry (ADR 0001)."""

    code: str
    name: str
    games_schedule: Sequence[CronSchedule]

    def fetch_games(self, session: Session, dates: Sequence[dt.date]) -> list[NormalizedGame]:
        """Fetch and normalize the games for `dates`.

        May read/write the dimensions scoped to this source (`team`, `channel`,
        `competition`) through `session` to resolve the IDs it returns in
        `NormalizedGame` — but does not write to `game`/`game_broadcast` nor
        commit: that is the core's generic responsibility (app/core/ingest.py).
        """
        ...

    # Optional capability (ADR 0004) — implemented only by sources with a real
    # catalog to sync. Not formally part of the Protocol because not every
    # source has it; see app/core/registry.py for the detection.
    #
    # def sync_catalog(self, session: Session) -> dict: ...
    # catalog_schedule: Sequence[CronSchedule]
