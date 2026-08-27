"""HTTP client for futnatv.net.

No CORS on the server (see docs/field-notes.md #1) — that does not affect a
server-side client like this one, but it is why extraction has to run here and
not in page JS. It serializes requests with a minimum pause between them and
uses an identifiable User-Agent, per docs/legal-and-etiquette.md.
"""

from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from app.sources.futnatv.config import (
    FUTNATV_BASE_URL as BASE_URL,
    FUTNATV_REQUEST_DELAY_SECONDS as REQUEST_DELAY_SECONDS,
    FUTNATV_REQUEST_TIMEOUT_SECONDS as REQUEST_TIMEOUT_SECONDS,
    FUTNATV_USER_AGENT as USER_AGENT,
)

log = logging.getLogger(__name__)


class FutnatvError(RuntimeError):
    """The API answered 200 with the `erro` key (or a 4xx/5xx with a JSON body)."""


class Futnatv:
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        retry = Retry(
            total=4,
            backoff_factor=2.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < REQUEST_DELAY_SECONDS:
            time.sleep(REQUEST_DELAY_SECONDS - elapsed)

    def _get(self, path: str) -> dict:
        self._throttle()
        resp = self._session.get(
            BASE_URL + path, timeout=REQUEST_TIMEOUT_SECONDS
        )
        self._last_request = time.monotonic()

        try:
            data = resp.json()
        except ValueError as exc:
            resp.raise_for_status()
            raise FutnatvError(f"non-JSON response from {path}") from exc

        # Errors come as HTTP 400/404 with a {"erro": "..."} body, or (rarely)
        # a 200 with the same key — see docs/api-reference.md.
        if isinstance(data, dict) and "erro" in data:
            raise FutnatvError(data["erro"])
        resp.raise_for_status()
        return data

    def day(self, sport: str, date_str: str) -> dict:
        """Raw payload of `/api/{sport}?data=YYYY-MM-DD`."""
        return self._get(f"/api/{sport}?data={date_str}")

    def channels_catalog(self) -> dict:
        return self._get("/canais.json")

    def competitions_catalog(self) -> dict:
        return self._get("/competicoes-futebol.json")
