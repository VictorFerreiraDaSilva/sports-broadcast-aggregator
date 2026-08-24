#!/usr/bin/env python3
"""Cliente de referência para a API do futnatv.net.

Só stdlib. Implementa o que está documentado em ../docs/, incluindo as armadilhas:
o campo `sport` não confiável, `availableDates` como janela deslizante, `"-"` como
nulo de odds, e o parsing de `broadcast`.

    python3 futnatv.py 2026-08-21              # agenda de futebol do dia
    python3 futnatv.py 2026-08-21 --sport nfl
    python3 futnatv.py 2026-08-21 --range --sport todos   # cobertura real dos 5 esportes
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = "https://futnatv.net"
SPORTS = ("futebol", "basquete", "volei", "nfl", "nhl")
TZ = ZoneInfo("America/Sao_Paulo")

# Um UA identificável é etiqueta básica: veja ../docs/legal-e-etiqueta.md
USER_AGENT = "futnatv-docs/1.0 (documentacao nao-oficial; uso pessoal)"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BROADCAST_SPLIT = re.compile(r"\s+e\s+|,\s*")
# Lixo de digitação que aparece em ~23 jogos como token de broadcast.
BROADCAST_JUNK = {"<>", "", "-"}


class FutnatvError(RuntimeError):
    """A API respondeu com a chave `erro`."""


# --------------------------------------------------------------------------- modelo


@dataclass
class Game:
    sport: str  # carimbado a partir do endpoint, NÃO do campo `sport` do payload
    date: str
    time: str
    competition: str
    round: str
    home: str
    away: str
    broadcast_raw: str
    broadcasters: list[str] = field(default_factory=list)
    odds: tuple[float | None, float | None, float | None] = (None, None, None)
    country: str | None = None
    youtube_id: str | None = None
    aggregate: str | None = None
    icon_emoji: str | None = None

    @property
    def kickoff(self) -> datetime:
        """Instante absoluto. O payload não traz fuso; é sempre horário de Brasília."""
        hh, mm = self.time.split("h")
        y, m, d = (int(p) for p in self.date.split("-"))
        return datetime(y, m, d, int(hh), int(mm), tzinfo=TZ)

    @property
    def has_broadcast(self) -> bool:
        """`broadcast` vazio significa 'não anunciado', não 'sem transmissão'."""
        return bool(self.broadcasters)


def _parse_odds(raw: list[str]) -> tuple[float | None, float | None, float | None]:
    """['1.66','4.00','4.50'] -> floats; o sentinela de ausência é a string '-'."""
    out: list[float | None] = []
    for v in (raw + ["-", "-", "-"])[:3]:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(None)
    return out[0], out[1], out[2]


def parse_broadcast(raw: str) -> list[str]:
    """'ESPN 4 e Disney+' -> ['ESPN 4', 'Disney+']. Preserva os parênteses."""
    if not raw:
        return []
    parts = (p.strip() for p in BROADCAST_SPLIT.split(raw))
    return [p for p in parts if p not in BROADCAST_JUNK]


def youtube_id(url: str | None) -> str | None:
    """Extrai o `v=` por query-parsing — 17 das 168 URLs trazem `&pp=` colado."""
    if not url:
        return None
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    ids = qs.get("v")
    return ids[0] if ids else None


def _to_game(raw: dict, sport: str, day_key: str) -> Game:
    return Game(
        sport=sport,
        date=day_key,
        time=raw["time"],
        competition=raw["competition"],
        round=raw.get("round", ""),
        home=raw["home"],
        away=raw["away"],
        broadcast_raw=raw.get("broadcast", ""),
        broadcasters=parse_broadcast(raw.get("broadcast", "")),
        odds=_parse_odds(raw.get("odds", [])),
        country=raw.get("country"),  # pode ser o pseudo-código "int"
        youtube_id=youtube_id(raw.get("youtubeUrl")),
        aggregate=raw.get("aggregate"),
        icon_emoji=raw.get("iconEmoji"),
    )


# --------------------------------------------------------------------------- cliente


class Futnatv:
    def __init__(self, cache_dir: Path | None = None, delay: float = 1.0):
        self.cache_dir = cache_dir
        self.delay = delay
        self._last_request = 0.0
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _get(self, path: str, cache_key: str | None = None) -> dict:
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        # Serializa e espaça as requisições — ver docs/legal-e-etiqueta.md
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

        req = urllib.request.Request(BASE + path, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self._last_request = time.monotonic()

        # Erros vêm com HTTP 400/404 (urlopen levanta) OU com a chave `erro` num 200.
        if "erro" in data:
            raise FutnatvError(data["erro"])

        self._write_cache(cache_key, data)
        return data

    def _read_cache(self, key: str | None) -> dict | None:
        if not (self.cache_dir and key):
            return None
        f = self.cache_dir / f"{key}.json"
        return json.loads(f.read_text("utf-8")) if f.exists() else None

    def _write_cache(self, key: str | None, data: dict) -> None:
        if self.cache_dir and key:
            (self.cache_dir / f"{key}.json").write_text(
                json.dumps(data, ensure_ascii=False), "utf-8"
            )

    # -- agenda ------------------------------------------------------------

    def raw_day(self, day: str, sport: str = "futebol") -> dict:
        """Payload cru de um dia. `day` no formato YYYY-MM-DD."""
        if sport not in SPORTS:
            raise ValueError(f"esporte inválido: {sport!r} (válidos: {SPORTS})")
        if not DATE_RE.match(day):
            raise ValueError(f"data deve ser YYYY-MM-DD, recebi {day!r}")
        # A API aceita datas impossíveis (2026-02-30) e devolve vazio — validamos aqui.
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError(f"data inexistente no calendário: {day}") from exc

        # Só cacheia o passado: hoje e o futuro ainda mudam.
        key = f"{sport}_{day}" if day < date.today().isoformat() else None
        return self._get(f"/api/{sport}?data={day}", cache_key=key)

    def games(self, day: str, sport: str = "futebol") -> list[Game]:
        payload = self.raw_day(day, sport)
        return [
            _to_game(g, sport, d["key"])
            for d in payload.get("schedule", [])
            for g in d["games"]
        ]

    def all_sports(self, day: str) -> list[Game]:
        """Agenda do dia nos cinco esportes, com o esporte carimbado corretamente."""
        out: list[Game] = []
        for sport in SPORTS:
            out.extend(self.games(day, sport))
        return sorted(out, key=lambda g: (g.time, g.competition))

    def broadcast_dates(self, sport: str = "futebol", seed: str | None = None) -> list[str]:
        """Datas com pelo menos um jogo de transmissão anunciada.

        É isso — e só isso — que `availableDates` informa; ele NÃO lista as datas que
        têm jogos (a NHL devolve jogos todo dia com `availableDates` sempre vazio).
        Para saber onde há jogos, use scan_days().

        Como cada resposta só mostra o recorte [D-7, D+7] de um conjunto-base fixo,
        caminhamos 7 dias além de cada borda até o conjunto parar de crescer.
        Limitação: um vão maior que 15 dias interrompe a caminhada, então o retorno
        é um limite inferior do conjunto real.
        """
        achadas: set[str] = set()
        cursor = seed or date.today().isoformat()
        dates = self.raw_day(cursor, sport).get("availableDates", [])
        if not dates:
            return []  # nenhuma transmissão anunciada perto da semente
        achadas.update(dates)

        for sentido in (-7, +7):  # para trás, depois para frente
            for _ in range(52):  # trava de segurança: ~1 ano de saltos
                borda = min(achadas) if sentido < 0 else max(achadas)
                probe = (date.fromisoformat(borda) + timedelta(days=sentido)).isoformat()
                novas = set(self.raw_day(probe, sport).get("availableDates", []))
                if not novas - achadas:
                    break  # a janela não trouxe nada novo: borda final
                achadas |= novas
        return sorted(achadas)

    def scan_days(self, start: str, end: str, sport: str = "futebol") -> dict[str, int]:
        """Varre um intervalo e devolve {data: nº de jogos} só das datas com jogos.

        Uma requisição por dia — não existe endpoint de intervalo. Respeite o `delay`.
        """
        out: dict[str, int] = {}
        cur, last = date.fromisoformat(start), date.fromisoformat(end)
        while cur <= last:
            key = cur.isoformat()
            n = sum(len(d["games"]) for d in self.raw_day(key, sport).get("schedule", []))
            if n:
                out[key] = n
            cur += timedelta(days=1)
        return out


# --------------------------------------------------------------------------- CLI


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("day", nargs="?", default=date.today().isoformat(), help="YYYY-MM-DD")
    ap.add_argument("--sport", default="futebol", choices=[*SPORTS, "todos"])
    ap.add_argument("--range", action="store_true",
                    help="varre ±20 dias em torno de `day` e mostra a cobertura real")
    ap.add_argument("--json", action="store_true", help="imprime o payload cru")
    ap.add_argument("--cache", type=Path, default=Path(".cache"))
    args = ap.parse_args()

    client = Futnatv(cache_dir=args.cache)

    if args.range:
        meio = date.fromisoformat(args.day)
        ini, fim = (meio - timedelta(days=20)).isoformat(), (meio + timedelta(days=20)).isoformat()
        print(f"varrendo {ini} .. {fim}\n")
        print(f"{'esporte':10s} {'datas com jogos':>15s}  {'jogos':>6s}   datas com transmissão anunciada")
        for sport in (SPORTS if args.sport == "todos" else [args.sport]):
            dias = client.scan_days(ini, fim, sport)
            bc = client.broadcast_dates(sport, seed=args.day)
            span = f"{min(dias)}..{max(dias)}" if dias else "—"
            print(f"{sport:10s} {span:>15s}  {sum(dias.values()):6d}   {len(bc):2d}"
                  + (f"  ({bc[0]}..{bc[-1]})" if bc else "  (nenhuma)"))
        return

    if args.json:
        print(json.dumps(client.raw_day(args.day, args.sport if args.sport != "todos" else "futebol"),
                         ensure_ascii=False, indent=2))
        return

    games = client.all_sports(args.day) if args.sport == "todos" else client.games(args.day, args.sport)
    if not games:
        print(f"nenhum jogo em {args.day}")
        return

    print(f"{args.day} — {len(games)} jogos\n")
    for g in games:
        onde = " / ".join(g.broadcasters) if g.has_broadcast else "— não anunciado"
        rodada = f" ({g.round})" if g.round else ""
        yt = f"  ▶ youtu.be/{g.youtube_id}" if g.youtube_id else ""
        print(f"  {g.time}  {g.home} x {g.away}")
        print(f"         {g.competition}{rodada}")
        print(f"         {onde}{yt}")


if __name__ == "__main__":
    main()
