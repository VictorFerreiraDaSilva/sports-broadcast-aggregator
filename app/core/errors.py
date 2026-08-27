"""Collection of a run's partial errors, through `logging` (ADR 0007).

The problem: a source that swallows an error to keep going (e.g. futnatv skips
a date the API refused) finishes with the job at `status="success"` — the core
has no way to know that 16 out of 20 requests failed. Notifying requires that
error to reach `app/core/jobs.py`.

The chosen solution is to invent no new channel: `collect_errors()` plugs a
`logging.Handler` in for the duration of the run and aggregates everything the
application logs at ERROR level or above. The `log.error(...)` the source
already writes *is* the signal — no source needs to know this module exists,
nor that Pushover exists (the README's promise, "adding a new source does not
touch app/core/", holds in the opposite direction too).

Two things the handler has to get right:

- **Logger scope.** It listens only to the `app.*` tree; a `log.error` from
  urllib3 or SQLAlchemy is not a collection failure and must not become a push.
- **Thread scope.** APScheduler runs jobs in a thread pool, so two collections
  may be running at the same time. The handler is global (it hangs off the
  `app` logger), but only accepts records from the thread that opened the
  collector — otherwise one job's errors would leak into the other's
  notification.

Aggregation is by *signature* (logger + message template + exception type),
not by the already-formatted message: the 16 failures of
`"error fetching %s %s: %s"` collapse into a single group with count 16,
instead of 16 nearly identical lines inside the push.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

# Root of the application's logger tree. Every module uses
# `logging.getLogger(__name__)`, and `__name__` always starts with "app.".
APP_LOGGER_NAME = "app"

# How many distinct groups fit in the notification body before the rest is
# summarized in a single line — the Pushover body holds 1024 characters.
MAX_GROUPS_IN_SUMMARY = 5


@dataclass
class ErrorGroup:
    """Errors sharing a signature, collapsed together."""

    logger_name: str
    # The `log.error` template ("error fetching %s %s"), not the formatted
    # message: it is what defines the group, and the only field stable enough
    # to aggregate by error type in a later query.
    template: str
    exc_type: str | None
    first_message: str
    count: int = 1

    @property
    def label(self) -> str:
        """How the group identifies itself in a message.

        Without `exc_info` (the common case: the source logged an error it had
        already handled itself), the best label available is the reporting
        module — minus the "app." prefix, which is the same for all of them and
        only takes up space.
        """
        return self.exc_type or self.logger_name.removeprefix(f"{APP_LOGGER_NAME}.")


@dataclass
class CollectedErrors:
    """Result of a `collect_errors()` — empty when nothing failed."""

    groups: dict[tuple, ErrorGroup] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.groups)

    @property
    def total(self) -> int:
        """How many error records came in, before aggregation."""
        return sum(g.count for g in self.groups.values())

    def add(self, record: logging.LogRecord) -> None:
        exc_type = record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else None
        signature = (record.name, str(record.msg), exc_type)

        group = self.groups.get(signature)
        if group is not None:
            group.count += 1
            return

        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - malformed args must not break collection
            message = str(record.msg)

        self.groups[signature] = ErrorGroup(
            logger_name=record.name,
            template=str(record.msg),
            exc_type=exc_type,
            first_message=message,
        )

    def summary(self) -> str:
        """Readable body for the notification: one block per group, with a count."""
        lines: list[str] = []
        for group in list(self.groups.values())[:MAX_GROUPS_IN_SUMMARY]:
            header = group.label
            if group.count > 1:
                header = f"{header} ×{group.count}"
            lines.append(header)
            lines.append(f"  {group.first_message}")
            if group.count > 1:
                lines.append(f"  (+{group.count - 1} identical)")

        remaining = len(self.groups) - MAX_GROUPS_IN_SUMMARY
        if remaining > 0:
            lines.append(f"(+{remaining} other error type(s))")

        return "\n".join(lines)

    def as_records(self) -> list[dict]:
        """The groups in structured form, to write into `scrape_run.details`.

        Unlike `summary()`, which is text rendered to fit Pushover's 1024
        characters: **all** groups go here, in separate fields, so that a later
        query can aggregate by error type instead of parsing strings.
        """
        return [
            {
                "label": group.label,
                "logger": group.logger_name,
                "template": group.template,
                "exc_type": group.exc_type,
                "count": group.count,
                "example": group.first_message,
            }
            for group in self.groups.values()
        ]


class _CollectingHandler(logging.Handler):
    def __init__(self, collected: CollectedErrors, thread_ident: int):
        super().__init__(level=logging.ERROR)
        self._collected = collected
        self._thread_ident = thread_ident
        self._lock_ = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread != self._thread_ident:
            return
        with self._lock_:
            self._collected.add(record)

    def handleError(self, record: logging.LogRecord) -> None:
        # Stay silent: an error inside the error collector must not write to
        # stderr nor propagate to whoever was merely logging.
        pass


@contextmanager
def collect_errors() -> Iterator[CollectedErrors]:
    """Aggregate everything `app.*` logs at ERROR+ on this thread, for as long
    as the block lasts.

        with collect_errors() as collected:
            ...
        if collected:
            notify(...)
    """
    collected = CollectedErrors()
    handler = _CollectingHandler(collected, threading.get_ident())
    app_logger = logging.getLogger(APP_LOGGER_NAME)

    # A handler only receives records that actually got created, and
    # `log.error()` creates nothing if the logger's effective level is above
    # ERROR. Without this guarantee, raising the log level
    # (`basicConfig(level=CRITICAL)`, a `LOG_LEVEL` in the environment) would
    # silently mute the entire notification system — the worst possible failure
    # mode for this subsystem of all things. We lower the level only for the
    # duration of the run and restore it afterwards. The side effect is that
    # errors also start showing up on stdout, which is desirable.
    original_level = app_logger.level
    if app_logger.getEffectiveLevel() > logging.ERROR:
        app_logger.setLevel(logging.ERROR)

    app_logger.addHandler(handler)
    try:
        yield collected
    finally:
        app_logger.removeHandler(handler)
        app_logger.setLevel(original_level)
