"""futnatv adapter: implements the `Source` protocol (app/core/source.py) over
the futnatv.net API.

One call = one day (there is no range endpoint — see docs/field-notes.md #4),
so a full run is `len(FUTNATV_SPORTS) * len(dates)` sequential requests, spaced
out by the HTTP client.
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

# The endpoint we query already uses the canonical sport vocabulary (ADR 0003)
# — an identity mapping, but an explicit one: every adapter declares this
# translation.
_SPORT_MAP = {sport: sport for sport in FUTNATV_SPORTS}


def _brief(raw: dict, limit: int = 200) -> str:
    """Short identification of a raw game, for the error message — the whole
    payload would blow past Pushover's 1024-character body."""
    text = repr(raw)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class FutnatvSource:
    code = FUTNATV_SOURCE_CODE
    name = FUTNATV_SOURCE_NAME

    # Collection times (project requirement, Brasília time): 6:00, 12:00,
    # 18:00 and 23:40. Catalog once a day, before the first collection — channels and
    # competitions change on a scale of weeks (docs/legal-and-etiquette.md), so
    # syncing 4x a day would be pointless.
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
                        "error fetching %s %s: %s: %s",
                        sport, day_key, type(exc).__name__, exc,
                    )
                    continue

                for day_obj in payload.get("schedule", []):
                    for raw in day_obj.get("games", []):
                        # A malformed game (a field that vanished, a time in a
                        # new format) must not take down the other ~500 of the
                        # run — drop just that one. The `log.error` is what
                        # carries the drop through to the notification
                        # (ADR 0007): without it, this would be silent data
                        # loss.
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
                                "game dropped (%s %s): %s: %s | payload=%s",
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
                # The payload's `sport` lies for nfl/nhl (docs/field-notes.md
                # #2) — kept aside, never used as sport_code.
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
