"""Config specific to the futnatv source — namespaced (ADR 0005)."""

from __future__ import annotations

import os

FUTNATV_SOURCE_CODE = "futnatv"
FUTNATV_SOURCE_NAME = "futnatv.net"

FUTNATV_BASE_URL = "https://futnatv.net"
FUTNATV_SPORTS = ("futebol", "basquete", "volei", "nfl", "nhl")

FUTNATV_CONTACT_INFO = os.environ.get(
    "FUTNATV_CONTACT_INFO", "fut-scraper/1.0 (personal use; no contact configured)"
)
FUTNATV_USER_AGENT = FUTNATV_CONTACT_INFO

# Technical etiquette: ~1 req/s is generous (see docs/legal-and-etiquette.md).
FUTNATV_REQUEST_DELAY_SECONDS = float(os.environ.get("FUTNATV_REQUEST_DELAY_SECONDS", "1.1"))
FUTNATV_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("FUTNATV_REQUEST_TIMEOUT_SECONDS", "30"))
