"""Fake source, no network — purely to prove mechanically that a second source
plugs into app/core/ without touching it (ADR 0001/0005). Hardcoded data.

Deliberately absent from app/core/registry.py: registering it would schedule a
daily job writing these fake games into the production database. The contract
test (tests/test_source_contract.py) instantiates it directly instead.

It deliberately does not implement `sync_catalog`: that proves the other side of
the contract (ADR 0004) — a source with no real catalog simply does not expose
the method, and the orchestrator schedules no catalog job for it.
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
        "competition": "Example League",
        "round": "Round 1",
        "home": "Team Alpha",
        "away": "Team Beta",
        "broadcast": "Example Channel",
    },
    {
        "sport": "basquete",
        "time": "20h30",
        "competition": "Example Cup",
        "round": "",
        "home": "Gamma Club",
        "away": "Delta Club",
        "broadcast": "",
    },
)


class ExampleSource:
    code = "_example"
    name = "Example source (fake)"

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
                            channel_id=None,  # no catalog — the source does not implement sync_catalog
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
                        source_data={"note": "fake data, no network — app/sources/_example/"},
                    )
                )
        return games
