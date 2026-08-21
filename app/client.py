"""Cliente HTTP para futnatv.net.

Sem CORS no servidor (ver docs/notas-de-campo.md #1) — isso não afeta um
cliente server-side como este, mas é por isso que a extração precisa rodar
aqui e não em JS de página. Serializa as requisições com uma pausa mínima
entre elas e usa um User-Agent identificável, conforme
docs/legal-e-etiqueta.md.
"""

from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from app.config import (
    BASE_URL,
    REQUEST_DELAY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)

log = logging.getLogger(__name__)


class FutnatvError(RuntimeError):
    """A API respondeu 200 com a chave `erro` (ou um 4xx/5xx com corpo JSON)."""


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
            raise FutnatvError(f"resposta não-JSON de {path}") from exc

        # Erros vêm com HTTP 400/404 e corpo {"erro": "..."} , ou (raramente)
        # um 200 com a mesma chave — ver docs/api-reference.md.
        if isinstance(data, dict) and "erro" in data:
            raise FutnatvError(data["erro"])
        resp.raise_for_status()
        return data

    def day(self, sport: str, date_str: str) -> dict:
        """Payload cru de `/api/{sport}?data=YYYY-MM-DD`."""
        return self._get(f"/api/{sport}?data={date_str}")

    def channels_catalog(self) -> dict:
        return self._get("/canais.json")

    def competitions_catalog(self) -> dict:
        return self._get("/competicoes-futebol.json")
