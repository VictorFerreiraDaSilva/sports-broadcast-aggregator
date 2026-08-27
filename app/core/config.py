"""Generic aggregator config — nothing here is source-specific.

Per-source config lives in app/sources/<source>/config.py (ADR 0005).
"""

from __future__ import annotations

import os
from zoneinfo import ZoneInfo

DATABASE_URL = os.environ["DATABASE_URL"]

BRT = ZoneInfo("America/Sao_Paulo")

# How many days ahead of the current day to capture (0 = today only). The
# requirement is "today + 3 days", so 4 dates in total per `fetch_games` run.
DAYS_AHEAD = 3

RUN_ON_STARTUP = os.environ.get("RUN_ON_STARTUP", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)
