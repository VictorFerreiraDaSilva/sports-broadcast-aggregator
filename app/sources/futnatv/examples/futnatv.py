#!/usr/bin/env python3
"""Reference client for the futnatv.net API.

Stdlib only. Implements what is documented in ../docs/, including the traps: the
unreliable `sport` field, `availableDates` as a sliding window, `"-"` as the
odds null, and the parsing of `broadcast`.

    python3 futnatv.py 2026-08-21              # the day's football schedule
    python3 futnatv.py 2026-08-21 --sport nfl
    python3 futnatv.py 2026-08-21 --range --sport all   # real coverage of all 5 sports
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = "https://futnatv.net"
SPORTS = ("futebol", "basquete", "volei", "nfl", "nhl")
TZ = ZoneInfo("America/Sao_Paulo")

# An identifiable UA is basic etiquette: see ../docs/legal-and-etiquette.md
USER_AGENT = "futnatv-docs/1.0 (unofficial documentation; personal use)"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BROADCAST_SPLIT = re.compile(r"\s+e\s+|,\s*")
# Typo junk that shows up in ~23 games as a broadcast token.
BROADCAST_JUNK = {"<>", "", "-"}


class FutnatvError(RuntimeError):
    """The API answered with the `erro` key."""


# ---------------------------------------------------------------------------- model


@dataclass
class Game:
    sport: str  # stamped from the endpoint, NOT from the payload's `sport` field
    date: str
    time: str
    competition: str
    round: str
    home: str
    away: str
    broadcast_raw: str
    broadcasters: list[str] = field(default_factory=list)
    odds: tuple[float | None, float | None, float | None] = (None, None, None)
    country: str | None = None
    youtube_id: str | None = None
    aggregate: str | None = None
    icon_emoji: str | None = None

    @property
    def kickoff(self) -> datetime:
        """Absolute instant. The payload carries no timezone; it is always Brasília time."""
        hh, mm = self.time.split("h")
        y, m, d = (int(p) for p in self.date.split("-"))
        return datetime(y, m, d, int(hh), int(mm), tzinfo=TZ)

    @property
    def has_broadcast(self) -> bool:
        """An empty `broadcast` means 'not announced', not 'no broadcast'."""
        return bool(self.broadcasters)


def _parse_odds(raw: list[str]) -> tuple[float | None, float | None, float | None]:
    """['1.66','4.00','4.50'] -> floats; the absence sentinel is the string '-'."""
    out: list[float | None] = []
    for v in (raw + ["-", "-", "-"])[:3]:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(None)
    return out[0], out[1], out[2]


def parse_broadcast(raw: str) -> list[str]:
    """'ESPN 4 e Disney+' -> ['ESPN 4', 'Disney+']. Preserves the parentheses."""
    if not raw:
        return []
    parts = (p.strip() for p in BROADCAST_SPLIT.split(raw))
    return [p for p in parts if p not in BROADCAST_JUNK]


def youtube_id(url: str | None) -> str | None:
    """Extracts `v=` by query-parsing — 17 of the 168 URLs carry `&pp=` glued on."""
    if not url:
        return None
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    ids = qs.get("v")
    return ids[0] if ids else None


def _to_game(raw: dict, sport: str, day_key: str) -> Game:
    return Game(
        sport=sport,
        date=day_key,
        time=raw["time"],
        competition=raw["competition"],
        round=raw.get("round", ""),
        home=raw["home"],
        away=raw["away"],
        broadcast_raw=raw.get("broadcast", ""),
        broadcasters=parse_broadcast(raw.get("broadcast", "")),
        odds=_parse_odds(raw.get("odds", [])),
        country=raw.get("country"),  # may be the pseudo-code "int"
        youtube_id=youtube_id(raw.get("youtubeUrl")),
        aggregate=raw.get("aggregate"),
        icon_emoji=raw.get("iconEmoji"),
    )


# --------------------------------------------------------------------------- client


class Futnatv:
    def __init__(self, cache_dir: Path | None = None, delay: float = 1.0):
        self.cache_dir = cache_dir
        self.delay = delay
        self._last_request = 0.0
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _get(self, path: str, cache_key: str | None = None) -> dict:
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        # Serializes and spaces out requests — see docs/legal-and-etiquette.md
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

        req = urllib.request.Request(BASE + path, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self._last_request = time.monotonic()

        # Errors come as HTTP 400/404 (urlopen raises) OR as the `erro` key in a 200.
        if "erro" in data:
            raise FutnatvError(data["erro"])

        self._write_cache(cache_key, data)
        return data

    def _read_cache(self, key: str | None) -> dict | None:
        if not (self.cache_dir and key):
            return None
        f = self.cache_dir / f"{key}.json"
        return json.loads(f.read_text("utf-8")) if f.exists() else None

    def _write_cache(self, key: str | None, data: dict) -> None:
        if self.cache_dir and key:
            (self.cache_dir / f"{key}.json").write_text(
                json.dumps(data, ensure_ascii=False), "utf-8"
            )

    # -- schedule ----------------------------------------------------------

    def raw_day(self, day: str, sport: str = "futebol") -> dict:
        """Raw payload for one day. `day` in YYYY-MM-DD format."""
        if sport not in SPORTS:
            raise ValueError(f"invalid sport: {sport!r} (valid: {SPORTS})")
        if not DATE_RE.match(day):
            raise ValueError(f"date must be YYYY-MM-DD, got {day!r}")
        # The API accepts impossible dates (2026-02-30) and returns empty — we validate here.
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError(f"date does not exist in the calendar: {day}") from exc

        # Only the past is cached: today and the future still change.
        key = f"{sport}_{day}" if day < date.today().isoformat() else None
        return self._get(f"/api/{sport}?data={day}", cache_key=key)

    def games(self, day: str, sport: str = "futebol") -> list[Game]:
        payload = self.raw_day(day, sport)
        return [
            _to_game(g, sport, d["key"])
            for d in payload.get("schedule", [])
            for g in d["games"]
        ]

    def all_sports(self, day: str) -> list[Game]:
        """The day's schedule across all five sports, with the sport stamped correctly."""
        out: list[Game] = []
        for sport in SPORTS:
            out.extend(self.games(day, sport))
        return sorted(out, key=lambda g: (g.time, g.competition))

    def broadcast_dates(self, sport: str = "futebol", seed: str | None = None) -> list[str]:
        """Dates with at least one game whose broadcast has been announced.

        That — and only that — is what `availableDates` reports; it does NOT list
        the dates that have games (the NHL returns games every day with
        `availableDates` always empty). To find where the games are, use
        scan_days().

        Since each response only shows the [D-7, D+7] slice of a fixed base set,
        we walk 7 days past each edge until the set stops growing. Limitation: a
        gap larger than 15 days breaks the walk, so the return value is a lower
        bound on the real set.
        """
        found: set[str] = set()
        cursor = seed or date.today().isoformat()
        dates = self.raw_day(cursor, sport).get("availableDates", [])
        if not dates:
            return []  # no broadcast announced near the seed
        found.update(dates)

        for direction in (-7, +7):  # backwards, then forwards
            for _ in range(52):  # safety stop: ~1 year of hops
                edge = min(found) if direction < 0 else max(found)
                probe = (date.fromisoformat(edge) + timedelta(days=direction)).isoformat()
                fresh = set(self.raw_day(probe, sport).get("availableDates", []))
                if not fresh - found:
                    break  # the window brought nothing new: final edge
                found |= fresh
        return sorted(found)

    def scan_days(self, start: str, end: str, sport: str = "futebol") -> dict[str, int]:
        """Scan a range and return {date: game count} for the dates with games only.

        One request per day — there is no range endpoint. Respect the `delay`.
        """
        out: dict[str, int] = {}
        cur, last = date.fromisoformat(start), date.fromisoformat(end)
        while cur <= last:
            key = cur.isoformat()
            n = sum(len(d["games"]) for d in self.raw_day(key, sport).get("schedule", []))
            if n:
                out[key] = n
            cur += timedelta(days=1)
        return out


# --------------------------------------------------------------------------- CLI


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("day", nargs="?", default=date.today().isoformat(), help="YYYY-MM-DD")
    ap.add_argument("--sport", default="futebol", choices=[*SPORTS, "all"])
    ap.add_argument("--range", action="store_true",
                    help="scan ±20 days around `day` and show the real coverage")
    ap.add_argument("--json", action="store_true", help="print the raw payload")
    ap.add_argument("--cache", type=Path, default=Path(".cache"))
    args = ap.parse_args()

    client = Futnatv(cache_dir=args.cache)

    if args.range:
        middle = date.fromisoformat(args.day)
        start, end = (middle - timedelta(days=20)).isoformat(), (middle + timedelta(days=20)).isoformat()
        print(f"scanning {start} .. {end}\n")
        print(f"{'sport':10s} {'dates with games':>16s}  {'games':>6s}   dates with announced broadcast")
        for sport in (SPORTS if args.sport == "all" else [args.sport]):
            days = client.scan_days(start, end, sport)
            bc = client.broadcast_dates(sport, seed=args.day)
            span = f"{min(days)}..{max(days)}" if days else "—"
            print(f"{sport:10s} {span:>16s}  {sum(days.values()):6d}   {len(bc):2d}"
                  + (f"  ({bc[0]}..{bc[-1]})" if bc else "  (none)"))
        return

    if args.json:
        print(json.dumps(client.raw_day(args.day, args.sport if args.sport != "all" else "futebol"),
                         ensure_ascii=False, indent=2))
        return

    games = client.all_sports(args.day) if args.sport == "all" else client.games(args.day, args.sport)
    if not games:
        print(f"no games on {args.day}")
        return

    print(f"{args.day} — {len(games)} games\n")
    for g in games:
        where = " / ".join(g.broadcasters) if g.has_broadcast else "— not announced"
        round_ = f" ({g.round})" if g.round else ""
        yt = f"  ▶ youtu.be/{g.youtube_id}" if g.youtube_id else ""
        print(f"  {g.time}  {g.home} x {g.away}")
        print(f"         {g.competition}{round_}")
        print(f"         {where}{yt}")


if __name__ == "__main__":
    main()
