"""Config específica da fonte futnatv — namespaced (ADR 0005)."""

from __future__ import annotations

import os

FUTNATV_SOURCE_CODE = "futnatv"
FUTNATV_SOURCE_NAME = "futnatv.net"

FUTNATV_BASE_URL = "https://futnatv.net"
FUTNATV_SPORTS = ("futebol", "basquete", "volei", "nfl", "nhl")

FUTNATV_CONTACT_INFO = os.environ.get(
    "FUTNATV_CONTACT_INFO", "fut-scraper/1.0 (uso pessoal; sem contato configurado)"
)
FUTNATV_USER_AGENT = FUTNATV_CONTACT_INFO

# Etiqueta técnica: ~1 req/s é folgado (ver docs/legal-e-etiqueta.md).
FUTNATV_REQUEST_DELAY_SECONDS = float(os.environ.get("FUTNATV_REQUEST_DELAY_SECONDS", "1.1"))
FUTNATV_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("FUTNATV_REQUEST_TIMEOUT_SECONDS", "30"))
