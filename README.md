# Agregador de calendários esportivos

Agrega jogos e onde assisti-los a partir de múltiplas fontes públicas (sites/APIs de terceiros).
Cada fonte é coletada, normalizada para um modelo comum e gravada lado a lado com as demais —
sem tentar fundir o mesmo jogo real relatado por fontes diferentes.

Ver [CONTEXT.md](CONTEXT.md) para o glossário (Fonte, Jogo, Esporte canônico, Catálogo) e
[docs/adr/](docs/adr/) para as decisões de arquitetura por trás do que segue.

## Arquitetura

```
app/
├── core/            → genérico: schema, orquestrador, protocol Source, upsert
└── sources/
    ├── futnatv/      → fonte real, sobre a API de futnatv.net
    └── _example/     → fonte fake (dados hardcoded, sem rede) — prova o contrato
```

Uma fonte é uma classe que implementa o protocol `Source`
([app/core/source.py](app/core/source.py)):

- `code`, `name`: identidade da fonte.
- `fetch_games(session, dates) -> list[NormalizedGame]`: obrigatório. Busca e normaliza os jogos
  de `dates` — inclusive resolvendo `competition_id`/`team_id`/`channel_id` contra os catálogos
  escopados a ela mesma. Não grava em `game`; isso é genérico.
- `sync_catalog(session) -> dict`: opcional. Só as fontes que têm um catálogo estático real
  (canais, competições, ...) implementam — o orquestrador detecta a capacidade e agenda o job só
  para quem a tem.
- `games_schedule` / `catalog_schedule`: cada fonte declara sua própria cadência (cron); o
  orquestrador não fixa horários.

**Adicionar uma fonte nova não toca `app/core/`** — só soma uma entrada em
`app/core/registry.py` e uma pasta nova em `app/sources/<fonte>/`. `app/sources/_example/` existe
só para provar isso mecanicamente.

### Schema

Núcleo enxuto e comum a todas as fontes; peculiaridades de uma fonte (odds, ícones, payload cru,
...) vão em `game.source_data: JSONB`, opaco ao core.

| Tabela | Papel |
|---|---|
| `source` | fontes registradas (seedada a partir de `app/core/registry.py`, não digitada à mão) |
| `sport` | esporte canônico — a única dimensão compartilhada entre fontes |
| `channel`, `competition`, `team` | dimensões **escopadas por fonte** (`source_code` entra na unicidade); o mesmo nome em fontes diferentes é uma linha diferente |
| `game` | um jogo por linha, **por fonte que o relatou**; chave natural = `(source_code, sport_code, game_date, time_raw, home_text, away_text)` — sem fusão entre fontes |
| `game_broadcast` | tokens de `broadcast_raw` já casados contra `channel` pela própria fonte |
| `catalog_meta` | última `version` sincronizada de cada catálogo, por fonte |
| `scrape_run` | log de auditoria de cada execução de job, por fonte |

## Rodando (Docker Compose)

```bash
cp .env.example .env    # ajuste a senha e o FUTNATV_CONTACT_INFO
docker compose up -d --build
```

No primeiro boot (`RUN_ON_STARTUP=true`, default) o container já roda uma coleta completa de
todas as fontes registradas; depois disso cada fonte segue sua própria cadência (ver
`games_schedule`/`catalog_schedule` de cada uma).

As tabelas são criadas sozinhas: o container roda `alembic upgrade head` antes de iniciar o
scheduler. Para rodar um job manualmente (fora do agendamento):

```bash
docker compose run --rm aggregator games              # coleta jogos de todas as fontes
docker compose run --rm aggregator games --source futnatv
docker compose run --rm aggregator catalog             # sincroniza o catálogo de toda fonte que tiver um
```

## Testes

```bash
pip install -r requirements-dev.txt
DATABASE_URL=postgresql+psycopg://fut:fut@localhost:5432/fut_test pytest
```

`tests/test_futnatv_normalize.py` é parsing puro, sem banco. `tests/test_source_contract.py`
exercita o protocol `Source` contra toda fonte registrada — a parte que toca banco roda contra
`app/sources/_example/` (fake, sem rede) para não depender da API real; o schema é recriado do
zero no banco de `DATABASE_URL`, então aponte para um Postgres descartável.

## Fontes

| Fonte | Papel |
|---|---|
| [app/sources/futnatv/](app/sources/futnatv/README.md) | fonte real, sobre a API não-oficial de futnatv.net — documentação de engenharia reversa, samples e cliente de referência ficam lá |
| `app/sources/_example/` | fonte fake, sem rede, só para provar o contrato `Source` |

## Status

Este repositório ainda não tem remoto configurado.
