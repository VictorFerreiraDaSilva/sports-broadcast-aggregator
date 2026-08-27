"""Sending error notifications through Pushover — generic, it knows no source
at all (ADR 0005/0007).

Two guarantees the rest of the code relies on:

1. **Never propagates.** A failure here (network, wrong credential, Pushover
   rate limit) becomes a `log.error` and returns `False`. Notification is
   observability; taking a collection down because the push failed would trade
   a small problem for a big one.
2. **No-op without credentials.** Without `PUSHOVER_TOKEN`/`PUSHOVER_USER_KEY`
   the module stays inert (a single warning, on first use). That is what lets
   `pytest` and local dev run with no network and no configuration.
"""

from __future__ import annotations

import logging
import os
import threading

import requests

log = logging.getLogger(__name__)

PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"

PUSHOVER_TOKEN = os.environ.get("PUSHOVER_TOKEN", "").strip()
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY", "").strip()

# Title prefix, to tell this app apart from others pushing to the same phone.
# Configurable because whoever runs two instances (prod/staging) needs to know
# which one a push came from.
PUSHOVER_APP_NAME = os.environ.get("PUSHOVER_APP_NAME", "fut").strip()

PUSHOVER_TIMEOUT_SECONDS = float(os.environ.get("PUSHOVER_TIMEOUT_SECONDS", "10"))

# Severities used by the project -> Pushover priority (ADR 0007).
# Priority 2 (emergency: repeats until the user acknowledges in the app) is
# deliberately left unused — nothing in a sports calendar aggregator justifies
# waking someone at 3 a.m.
PRIORITY_CRITICAL = 1  # pierces the phone's quiet hours; does not self-recover
PRIORITY_ERROR = 0  # normal sound; the next scheduled run may well fix it
PRIORITY_WARNING = -1  # silent; only shows up in the notification list

# API limits (https://pushover.net/api): title 250, body 1024.
_TITLE_LIMIT = 250
_MESSAGE_LIMIT = 1024

_warned_lock = threading.Lock()
_warned_unconfigured = False


def is_configured() -> bool:
    return bool(PUSHOVER_TOKEN and PUSHOVER_USER_KEY)


def _warn_unconfigured_once() -> None:
    global _warned_unconfigured
    with _warned_lock:
        if _warned_unconfigured:
            return
        _warned_unconfigured = True
    log.warning(
        "PUSHOVER_TOKEN/PUSHOVER_USER_KEY not configured — "
        "error notifications disabled (errors still go to the log and to scrape_run)"
    )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def notify(title: str, message: str, priority: int = PRIORITY_ERROR) -> bool:
    """Send a push. Returns `True` if Pushover accepted it.

    Never raises under any circumstance — see the module docstring.
    """
    if not is_configured():
        _warn_unconfigured_once()
        return False

    payload = {
        "token": PUSHOVER_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": _truncate(f"{PUSHOVER_APP_NAME} · {title}", _TITLE_LIMIT),
        "message": _truncate(message, _MESSAGE_LIMIT),
        "priority": priority,
    }

    try:
        resp = requests.post(PUSHOVER_API_URL, data=payload, timeout=PUSHOVER_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            # A 4xx carries {"errors": [...]}; logging the body is what tells
            # "invalid token" from "rate limit" when someone investigates.
            log.error(
                "Pushover refused the notification: HTTP %s %s", resp.status_code, resp.text[:500]
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001 - a notification never takes down its caller
        log.error("failed to send Pushover notification: %s", exc)
        return False
