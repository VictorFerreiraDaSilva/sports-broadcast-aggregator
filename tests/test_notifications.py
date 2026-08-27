"""Tests for the error notification system (ADR 0007).

Nothing here touches the network or the database: `requests.post` is always
replaced and the notifier is called directly. The goal is to pin down the three
guarantees the rest of the code relies on — the collector picks up what it
should and only what it should, the notification never propagates an exception,
and the severity table does not change by accident.
"""

from __future__ import annotations

import logging
import threading

import pytest

from app.core import notify as notify_mod
from app.core.errors import APP_LOGGER_NAME, collect_errors


# --------------------------------------------------------------------------
# Collector (app/core/errors.py)
# --------------------------------------------------------------------------


def test_groups_errors_by_signature_not_by_formatted_message():
    """The 16 failures of "error fetching %s %s" become one group, not 16 lines."""
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        for sport in ("futebol", "basquete"):
            for day in ("2026-08-27", "2026-08-28"):
                log.error("error fetching %s %s: %s", sport, day, "HTTP 503")

    assert collected
    assert collected.total == 4
    assert len(collected.groups) == 1

    (group,) = collected.groups.values()
    assert group.count == 4
    assert group.first_message == "error fetching futebol 2026-08-27: HTTP 503"

    summary = collected.summary()
    # without exc_info, the header is the module minus the "app." prefix
    assert "sources.fake ×4" in summary
    assert "(+3 identical)" in summary


def test_separates_groups_by_exception_type():
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        try:
            raise KeyError("team")
        except KeyError:
            log.exception("game dropped")
        try:
            raise ValueError("time")
        except ValueError:
            log.exception("game dropped")

    assert len(collected.groups) == 2
    assert {g.exc_type for g in collected.groups.values()} == {"KeyError", "ValueError"}


def test_ignores_levels_below_error():
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        log.info("collecting")
        log.warning("channel did not match")

    assert not collected
    assert collected.total == 0


def test_ignores_loggers_outside_the_application_tree():
    """A log.error from urllib3 or SQLAlchemy is not a collection failure."""
    with collect_errors() as collected:
        logging.getLogger("urllib3.connectionpool").error("Retrying after connection broken")
        logging.getLogger("sqlalchemy.engine").error("something generic")

    assert not collected


def test_ignores_errors_from_another_thread():
    """APScheduler runs jobs in a pool — one job's errors must not leak into
    another's notification."""
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")
    started = threading.Event()

    def other_collection():
        started.wait(timeout=5)
        log.error("error from another job")

    thread = threading.Thread(target=other_collection)

    with collect_errors() as collected:
        thread.start()
        started.set()
        thread.join(timeout=5)
        log.error("error from this job")

    assert collected.total == 1
    (group,) = collected.groups.values()
    assert group.first_message == "error from this job"


def test_handler_is_removed_on_leaving_the_block():
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    before = len(app_logger.handlers)

    with collect_errors():
        assert len(app_logger.handlers) == before + 1

    assert len(app_logger.handlers) == before


def test_summary_condenses_when_there_are_too_many_groups():
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        for i in range(8):
            log.error("error of type %d occurred" % i)  # noqa: UP031 - distinct template on purpose

    assert len(collected.groups) == 8
    assert "(+3 other error type(s))" in collected.summary()


# --------------------------------------------------------------------------
# Notifier (app/core/notify.py)
# --------------------------------------------------------------------------


@pytest.fixture()
def pushover_configured(monkeypatch):
    """Fake credentials + capture of the POST, without touching the network."""
    monkeypatch.setattr(notify_mod, "PUSHOVER_TOKEN", "test-token")
    monkeypatch.setattr(notify_mod, "PUSHOVER_USER_KEY", "test-user")
    monkeypatch.setattr(notify_mod, "PUSHOVER_APP_NAME", "fut-test")

    sent = []

    class FakeResponse:
        status_code = 200
        text = '{"status":1}'

    def fake_post(url, data=None, timeout=None):
        sent.append(data)
        return FakeResponse()

    monkeypatch.setattr(notify_mod.requests, "post", fake_post)
    return sent


def test_without_credentials_it_is_a_no_op(monkeypatch):
    monkeypatch.setattr(notify_mod, "PUSHOVER_TOKEN", "")
    monkeypatch.setattr(notify_mod, "PUSHOVER_USER_KEY", "")

    def explode(*args, **kwargs):
        raise AssertionError("should not touch the network without credentials")

    monkeypatch.setattr(notify_mod.requests, "post", explode)

    assert notify_mod.notify("title", "body") is False


def test_sends_with_prefix_and_priority(pushover_configured):
    assert notify_mod.notify("futnatv/games failed", "body", priority=1) is True

    (payload,) = pushover_configured
    assert payload["title"] == "fut-test · futnatv/games failed"
    assert payload["message"] == "body"
    assert payload["priority"] == 1


def test_truncates_at_the_api_limits(pushover_configured):
    notify_mod.notify("t" * 500, "m" * 5000)

    (payload,) = pushover_configured
    assert len(payload["title"]) == 250
    assert len(payload["message"]) == 1024
    assert payload["message"].endswith("…")


def test_send_failure_never_propagates(monkeypatch):
    monkeypatch.setattr(notify_mod, "PUSHOVER_TOKEN", "test-token")
    monkeypatch.setattr(notify_mod, "PUSHOVER_USER_KEY", "test-user")

    def explode(*args, **kwargs):
        raise ConnectionError("network down")

    monkeypatch.setattr(notify_mod.requests, "post", explode)

    assert notify_mod.notify("title", "body") is False


def test_non_200_response_returns_false(monkeypatch, pushover_configured):
    class Refusal:
        status_code = 400
        text = '{"errors":["application token is invalid"]}'

    monkeypatch.setattr(notify_mod.requests, "post", lambda *a, **k: Refusal())

    assert notify_mod.notify("title", "body") is False


# --------------------------------------------------------------------------
# Severity table (app/core/jobs.py::_notify_result)
# --------------------------------------------------------------------------


class FakeSource:
    code = "test-source"
    name = "Test Source"


@pytest.fixture()
def notifications(monkeypatch):
    """Capture what `jobs` would notify, without going through Pushover."""
    from app.core import jobs

    captured = []
    monkeypatch.setattr(
        jobs,
        "notify",
        lambda title, message, priority=0: captured.append((title, message, priority)),
    )
    return jobs, captured


def _collected(*messages):
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")
    with collect_errors() as collected:
        for msg in messages:
            log.error(msg)
    return collected


def test_clean_run_does_not_notify(notifications):
    jobs, captured = notifications
    jobs._notify_result(
        "games", FakeSource(), "success", {"games_count": 142}, None, _collected(), 7
    )
    assert captured == []


def test_failed_job_notifies_at_normal_priority(notifications):
    jobs, captured = notifications
    jobs._notify_result(
        "games", FakeSource(), "error", {}, "ConnectionError: network down", _collected(), 7
    )

    (title, message, priority) = captured[0]
    assert title == "test-source/games failed"
    assert priority == notify_mod.PRIORITY_ERROR
    assert "ConnectionError: network down" in message
    assert "run #7" in message


def test_partial_error_notifies_as_degraded(notifications):
    jobs, captured = notifications
    jobs._notify_result(
        "games",
        FakeSource(),
        "success",
        {"games_count": 142},
        None,
        _collected("a failed", "b failed"),
        7,
    )

    (title, message, priority) = captured[0]
    assert title == "test-source/games degraded"
    assert priority == notify_mod.PRIORITY_WARNING
    assert "2 errors swallowed" in message
    assert "142 game(s) written" in message


def test_empty_collection_without_error_notifies(notifications):
    jobs, captured = notifications
    jobs._notify_result("games", FakeSource(), "success", {"games_count": 0}, None, _collected(), 7)

    (title, _message, priority) = captured[0]
    assert title == "test-source/games no games"
    assert priority == notify_mod.PRIORITY_WARNING


def test_empty_catalog_does_not_trigger_the_zero_games_rule(notifications):
    """The "no games" rule belongs to the games job; a catalog that merely
    skipped (unchanged version) is a legitimate success."""
    jobs, captured = notifications
    jobs._notify_result(
        "catalog", FakeSource(), "success", {"skipped": True}, None, _collected(), 7
    )
    assert captured == []


def test_at_most_one_notification_per_run(notifications):
    jobs, captured = notifications
    jobs._notify_result(
        "games",
        FakeSource(),
        "error",
        {"games_count": 0},
        "boom",
        _collected("partial a", "partial b"),
        7,
    )
    assert len(captured) == 1


# --------------------------------------------------------------------------
# Waiting for the database (app/core/wait_for_db.py)
# --------------------------------------------------------------------------


class FakeEngine:
    """Fails `failures` times before connecting."""

    def __init__(self, failures: int):
        self.failures = failures
        self.attempts = 0

    def connect(self):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise OSError("connection refused")
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, _stmt):
        return None


@pytest.fixture()
def wait_mod(monkeypatch):
    from app.core import wait_for_db as mod

    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    captured = []
    monkeypatch.setattr(
        mod, "notify", lambda title, message, priority=0: captured.append((title, priority))
    )
    return mod, captured


def test_database_available_right_away_does_not_notify(wait_mod):
    mod, captured = wait_mod
    mod.wait_for_db(FakeEngine(failures=0))
    assert captured == []


def test_short_failure_does_not_notify(wait_mod, monkeypatch):
    """A routine Postgres restart must not become a push."""
    mod, captured = wait_mod
    monkeypatch.setattr(mod, "DB_WAIT_NOTIFY_AFTER_SECONDS", 3600)
    mod.wait_for_db(FakeEngine(failures=3))
    assert captured == []


def test_prolonged_failure_notifies_once_and_reports_recovery(wait_mod, monkeypatch):
    mod, captured = wait_mod
    monkeypatch.setattr(mod, "DB_WAIT_NOTIFY_AFTER_SECONDS", 0)

    engine = FakeEngine(failures=5)
    mod.wait_for_db(engine)

    assert engine.attempts == 6
    assert [t for t, _p in captured] == ["database unreachable", "database recovered"]
    assert captured[0][1] == notify_mod.PRIORITY_CRITICAL
    assert captured[1][1] == notify_mod.PRIORITY_WARNING


def test_wait_ceiling_raises(wait_mod, monkeypatch):
    mod, _captured = wait_mod
    monkeypatch.setattr(mod, "DB_WAIT_MAX_SECONDS", 0.0001)
    monkeypatch.setattr(mod, "DB_WAIT_NOTIFY_AFTER_SECONDS", 3600)

    with pytest.raises(RuntimeError, match="database unreachable"):
        mod.wait_for_db(FakeEngine(failures=99))


# --------------------------------------------------------------------------
# Persistence of the degraded state (app/core/jobs.py::_run + scrape_run)
# --------------------------------------------------------------------------


def test_as_records_carries_every_group_structured():
    """`summary()` is text trimmed to fit Pushover; `as_records()` is what goes
    to the database and trims nothing."""
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        for i in range(8):
            log.error("error of type %d occurred" % i)  # noqa: UP031
        log.error("error of type %d occurred" % 0)  # noqa: UP031 - repeats the first

    assert "(+3 other error type(s))" in collected.summary()

    records = collected.as_records()
    assert len(records) == 8, "as_records must not trim at MAX_GROUPS_IN_SUMMARY"
    assert sum(r["count"] for r in records) == collected.total == 9
    assert records[0] == {
        "label": "sources.fake",
        "logger": "app.sources.fake",
        "template": "error of type 0 occurred",
        "exc_type": None,
        "count": 2,
        "example": "error of type 0 occurred",
    }


def test_as_records_distinguishes_error_types_from_the_same_module():
    """`label` falls back to the module name when there is no exc_info, so two
    different errors from the same source would collide in an aggregation.
    `template` is the field that separates them."""
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        log.error("error fetching %s %s: %s", "futebol", "2026-08-27", "HTTP 503")
        log.error("game dropped (%s %s): %s", "volei", "2026-08-27", "KeyError")

    records = collected.as_records()
    assert len({r["label"] for r in records}) == 1, "label alone does not distinguish"
    assert {r["template"] for r in records} == {
        "error fetching %s %s: %s",
        "game dropped (%s %s): %s",
    }


def _example_source_that_logs(messages, explode=None):
    """ExampleSource with `fetch_games` instrumented to log errors (and,
    optionally, to blow up) before returning the hardcoded games."""
    from app.sources._example.source import ExampleSource

    source = ExampleSource()
    original = source.fetch_games
    log = logging.getLogger("app.sources._example.source")

    def fetch_games(session, dates):
        for sport, day in messages:
            log.error("error fetching %s %s: %s", sport, day, "HTTP 503")
        if explode is not None:
            raise explode
        return original(session, dates)

    source.fetch_games = fetch_games
    return source


@pytest.fixture()
def jobs_without_push(monkeypatch):
    """The real `jobs` against the real database, only with Pushover turned off."""
    from app.core import jobs

    monkeypatch.setattr(jobs, "notify", lambda *a, **k: None)
    return jobs


def _last_run(db_session):
    from app.core.models import ScrapeRun

    return db_session.query(ScrapeRun).order_by(ScrapeRun.id.desc()).first()


def test_clean_run_writes_success_without_noise(db_session, jobs_without_push):
    result = jobs_without_push.run_games_scrape(_example_source_that_logs([]))

    assert result["status"] == "success"

    run = _last_run(db_session)
    assert run.status == "success"
    assert run.error_message is None
    assert run.details["games_count"] > 0
    assert "errors_collected" not in run.details
    assert "error_groups" not in run.details


def test_swallowed_error_writes_degraded_with_the_groups(db_session, jobs_without_push):
    """The point of the item: a run that only notified could not go on being
    counted as a clean success by whoever queried `scrape_run`."""
    source = _example_source_that_logs(
        [("futebol", "2026-08-27"), ("futebol", "2026-08-28"), ("basquete", "2026-08-27")]
    )
    result = jobs_without_push.run_games_scrape(source)

    assert result["status"] == "degraded"

    run = _last_run(db_session)
    assert run.status == "degraded"
    # the fatal failure remains the sole owner of error_message
    assert run.error_message is None
    # it wrote what it could: degraded is not the same as lost
    assert run.details["games_count"] > 0
    assert run.details["errors_collected"] == 3

    (group,) = run.details["error_groups"]
    assert group["count"] == 3
    assert group["label"] == "sources._example.source"
    assert group["logger"] == "app.sources._example.source"
    assert group["example"] == "error fetching futebol 2026-08-27: HTTP 503"


def test_fatal_failure_stays_error_but_preserves_the_partials(db_session, jobs_without_push):
    """A run that swallowed errors and then died is `error` — the fatal failure
    is the more severe one — but the partials stop being lost."""
    source = _example_source_that_logs(
        [("futebol", "2026-08-27"), ("volei", "2026-08-27")],
        explode=ConnectionError("network down"),
    )
    result = jobs_without_push.run_games_scrape(source)

    assert result["status"] == "error"

    run = _last_run(db_session)
    assert run.status == "error"
    assert run.error_message == "ConnectionError: network down"
    assert run.details["errors_collected"] == 2
    assert len(run.details["error_groups"]) == 1


def test_empty_collection_without_error_stays_success(db_session, jobs_without_push):
    """"No games" notifies, but is not a degradation: no error happened. The
    signal lives in games_count, not in a fourth status value."""
    from app.sources._example.source import ExampleSource

    source = ExampleSource()
    source.fetch_games = lambda session, dates: []

    result = jobs_without_push.run_games_scrape(source)
    assert result["status"] == "success"

    run = _last_run(db_session)
    assert run.status == "success"
    assert run.details["games_count"] == 0
    assert "errors_collected" not in run.details


def test_collector_is_not_muted_by_a_high_log_level():
    """A `basicConfig(level=CRITICAL)` must not silently turn the notification
    off: `log.error` never even creates the record if the effective level is
    above ERROR."""
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")
    original_level = app_logger.level
    app_logger.setLevel(logging.CRITICAL)
    try:
        with collect_errors() as collected:
            log.error("error that would be swallowed by the log level")
        assert collected.total == 1
        # and the level is restored on exit
        assert app_logger.level == logging.CRITICAL
    finally:
        app_logger.setLevel(original_level)
