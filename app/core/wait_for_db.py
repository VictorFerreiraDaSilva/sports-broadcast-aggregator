"""Wait for Postgres to accept a connection before anything else comes up.

Runs in the entrypoint *before* `alembic upgrade head` (ADR 0007). The reason is
specific: with the database down, alembic dies first, the container dies with
it and compose's `restart: unless-stopped` restarts it — not a line of our
Python ever runs, and the crash loop is completely mute.

Instead of dying, this module keeps at it. The container stays up, notifies
**once** that the database is unreachable, keeps retrying quietly and reports
again once it connects. A database down for 10 minutes yields 2 notifications
(down, back up) instead of the dozens of identical pushes a crash loop would
produce.

    python -m app.core.wait_for_db
"""

from __future__ import annotations

import logging
import os
import sys
import time

from sqlalchemy import text

from app.core.notify import PRIORITY_CRITICAL, PRIORITY_WARNING, notify

log = logging.getLogger(__name__)

# How much continuous failure before bothering the user. A routine Postgres
# restart takes a few seconds; notifying on the first attempt would turn normal
# maintenance into a push.
DB_WAIT_NOTIFY_AFTER_SECONDS = float(os.environ.get("DB_WAIT_NOTIFY_AFTER_SECONDS", "60"))

# Total wait ceiling. 0 = wait indefinitely, which is the default: that is what
# keeps the container alive (and therefore quiet) instead of crash-looping.
DB_WAIT_MAX_SECONDS = float(os.environ.get("DB_WAIT_MAX_SECONDS", "0"))

_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 30.0


def _check(engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def wait_for_db(engine=None) -> None:
    """Block until the database answers. Only raises if `DB_WAIT_MAX_SECONDS`
    is exceeded (not the default)."""
    if engine is None:
        from app.core.db import engine as default_engine

        engine = default_engine

    started = time.monotonic()
    backoff = _INITIAL_BACKOFF
    notified = False
    last_error = "unknown error"
    attempt = 0

    while True:
        attempt += 1
        try:
            _check(engine)
        except Exception as exc:  # noqa: BLE001 - any connection failure counts
            last_error = f"{type(exc).__name__}: {exc}"
            elapsed = time.monotonic() - started

            if not notified and elapsed >= DB_WAIT_NOTIFY_AFTER_SECONDS:
                notify(
                    "database unreachable",
                    "The container is up but cannot connect to Postgres "
                    f"for {int(elapsed)}s ({attempt} attempts).\n"
                    "No collection will run until this clears.\n\n"
                    f"{last_error[:500]}",
                    priority=PRIORITY_CRITICAL,
                )
                notified = True

            if DB_WAIT_MAX_SECONDS and elapsed >= DB_WAIT_MAX_SECONDS:
                raise RuntimeError(
                    f"database unreachable after {int(elapsed)}s: {last_error}"
                ) from exc

            log.warning(
                "database unreachable (attempt %d, %ds): %s — retrying in %.0fs",
                attempt, int(elapsed), last_error, backoff,
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
            continue

        elapsed = time.monotonic() - started
        if notified:
            notify(
                "database recovered",
                f"Connection to Postgres restored after {int(elapsed)}s "
                f"and {attempt} attempts. Startup proceeds normally.",
                priority=PRIORITY_WARNING,
            )
        if attempt > 1:
            log.info("database available after %ds (%d attempts)", int(elapsed), attempt)
        return


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    wait_for_db()


if __name__ == "__main__":
    main()
