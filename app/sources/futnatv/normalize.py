"""Funções de parsing/normalização — regras extraídas de docs/schemas.md e
docs/notas-de-campo.md. Nada aqui acessa rede ou banco.
"""

from __future__ import annotations

import re
import unicodedata
import urllib.parse

BROADCAST_SPLIT = re.compile(r"\s+e\s+|,\s*")
BROADCAST_JUNK = {"<>", "", "-"}
PAREN_RE = re.compile(r"^(?P<platform>.*?)\s*\((?P<qualifier>.+)\)\s*$")
# "ESPN 4" -> "ESPN", "SporTV 2" -> "SporTV" — redução de família documentada
# em docs/schemas.md#casamento-entre-agenda-e-catálogos.
TRAILING_VARIANT_RE = re.compile(r"^(?P<base>.+?)\s+\d+\+?$")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize_key(text: str) -> str:
    """trim + casefold + sem acento — chave de casamento/índice."""
    return strip_accents(text).strip().casefold()


def normalize_team_name(name: str) -> str:
    return normalize_key(name)


def split_broadcast(raw: str) -> list[str]:
    """'ESPN 4 e Disney+' -> ['ESPN 4', 'Disney+']. Filtra lixo conhecido (`"<>"`).

    Só quebra em `" e "`/`", "` fora de parênteses — valores como
    `"Globo (menos BA, PE, NE)"` têm vírgula dentro do qualificador, e um
    split ingênuo os estilhaça em tokens que não casam com nada.
    """
    if not raw:
        return []

    tokens: list[str] = []
    buf: list[str] = []
    depth = 0
    i, n = 0, len(raw)
    while i < n:
        ch = raw[i]
        if ch == "(":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
            i += 1
            continue
        if depth == 0:
            m = BROADCAST_SPLIT.match(raw, i)
            if m:
                tokens.append("".join(buf).strip())
                buf = []
                i = m.end()
                continue
        buf.append(ch)
        i += 1
    tokens.append("".join(buf).strip())

    return [t for t in tokens if t and t not in BROADCAST_JUNK]


def split_platform_qualifier(token: str) -> tuple[str, str | None]:
    """'YouTube (CazéTV)' -> ('YouTube', 'CazéTV'). Sem parênteses -> (token, None)."""
    m = PAREN_RE.match(token)
    if not m:
        return token.strip(), None
    return m.group("platform").strip(), m.group("qualifier").strip()


def family_fallback(platform_key: str) -> str | None:
    """'espn 4' -> 'espn'. Usado só quando o match exato/alias falhou."""
    m = TRAILING_VARIANT_RE.match(platform_key)
    return m.group("base").strip() if m else None


def parse_odds(raw: list[str] | None) -> tuple[float | None, float | None, float | None]:
    """['1.66','4.00','4.50'] -> floats; sentinela de ausência é a string '-'."""
    values = (raw or []) + ["-", "-", "-"]
    out: list[float | None] = []
    for v in values[:3]:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(None)
    return out[0], out[1], out[2]


def parse_time(time_raw: str) -> tuple[int, int]:
    """'13h45' -> (13, 45)."""
    hh, mm = time_raw.split("h")
    return int(hh), int(mm)


def extract_youtube_id(url: str | None) -> str | None:
    """Extrai `v=` por query-parsing — alguns valores trazem `&pp=` colado."""
    if not url:
        return None
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    ids = qs.get("v")
    return ids[0] if ids else None
