# Agregador de calendários esportivos

Agrega jogos e onde assisti-los a partir de múltiplas fontes públicas (sites/APIs de terceiros).
Cada fonte é coletada, normalizada para um modelo comum e gravada lado a lado com as demais —
sem tentar fundir o mesmo jogo real relatado por fontes diferentes.

Ver [CONTEXT.md](CONTEXT.md) para o glossário (Fonte, Jogo, Esporte canônico, Catálogo) e
[docs/adr/](docs/adr/) para as decisões de arquitetura por trás do que segue.

## Arquitetura

```
app/
├── core/            → genérico: schema, orquestrador, protocol Source, upsert,
│                      coleta de erros + notificação (errors.py, notify.py)
└── sources/
    ├── futnatv/      → fonte real, sobre a API de futnatv.net
    └── _example/     → fonte fake (dados hardcoded, sem rede) — prova o contrato,
                       fora do registro: só os testes a instanciam
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
só para provar isso mecanicamente — e fica **fora** do registro, porque uma fonte de dados
inventados agendada em produção gravaria jogos falsos na mesma tabela dos reais.

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
| `scrape_run` | log de auditoria de cada execução de job, por fonte — `status` é `success`, `degraded` (gravou, mas engoliu erros) ou `error` |

## Rodando (Docker Compose)

```bash
cp .env.example .env    # ajuste a senha e o FUTNATV_CONTACT_INFO
docker compose up -d --build
```

A cada boot (`RUN_ON_STARTUP=true`, default) o container roda uma coleta completa de todas as
fontes registradas — catálogo primeiro, para quem tiver, depois os jogos — antes de iniciar o
agendamento; daí em diante cada fonte segue sua própria cadência (ver
`games_schedule`/`catalog_schedule` de cada uma). Vale também para `docker compose restart`: o
upsert é idempotente pela chave natural do jogo, então recoletar não duplica nada.

As tabelas são criadas sozinhas: o container roda `alembic upgrade head` antes de iniciar o
scheduler. Para rodar um job manualmente (fora do agendamento):

```bash
docker compose run --rm aggregator games              # coleta jogos de todas as fontes
docker compose run --rm aggregator games --source futnatv
docker compose run --rm aggregator catalog             # sincroniza o catálogo de toda fonte que tiver um
```

## Notificações de erro

O agregador roda desatendido, então toda falha que valha a pena saber vira um push no
[Pushover](https://pushover.net) (ver [ADR 0007](docs/adr/0007-error-notification-via-logging.md)).

```bash
# em .env — crie a aplicação em https://pushover.net/apps/build
PUSHOVER_TOKEN=...
PUSHOVER_USER_KEY=...
```

**Sem essas duas variáveis o notificador fica inerte** e nada mais muda: os erros continuam indo
para o log e para a tabela `scrape_run`. É o que permite rodar os testes e o dev local sem
configurar nada nem tocar a rede.

O que notifica, e com que prioridade Pushover:

| Situação | Prioridade | Efeito no celular |
|---|---|---|
| Banco inacessível no boot | `1` | fura as quiet hours |
| Job inteiro falhou | `0` | som normal |
| Execução degradada — gravou, mas engoliu erros pelo caminho | `-1` | mudo, só na lista |
| Execução sem nenhum jogo, e sem erro algum | `-1` | mudo |
| Job do scheduler estourou, ou execução perdida | `-1` | mudo |

Duas regras que valem mais que a tabela:

- **Execução limpa não notifica.** Um push por coleta bem-sucedida, 4x/dia por fonte, treinaria
  qualquer um a ignorar os pushes.
- **No máximo um push por execução.** Uma coleta da futnatv são 20 requisições; com a API fora do
  ar, notificar por erro daria 80 pushes/dia. Os erros são agregados por assinatura e resumidos
  numa mensagem só:

  ```
  fut · futnatv/games degradado                     (prioridade -1)

  16 erros engolidos durante a execução.

  sources.futnatv.source ×16
    erro ao buscar futebol 2026-08-27: FutnatvError: HTTP 503
    (+15 iguais)

  142 jogo(s) gravado(s) · run #1284
  ```

Toda execução que notifica também **fica registrada** em `scrape_run` — o push é o alerta, o
banco é o histórico:

| Situação | `status` | `details` |
|---|---|---|
| Limpa | `success` | `games_count` |
| Degradada | `degraded` | `+ errors_collected`, `error_groups` (todos os grupos, estruturados) |
| Falhou | `error` | `+ errors_collected`, `error_groups`; a causa fatal em `error_message` |

Isso é o que torna a **degradação lenta** detectável: cada push de prioridade `-1` passa batido
sozinho, mas a soma não. Quantas das últimas execuções foram degradadas:

```sql
SELECT source_code, status, count(*)
FROM scrape_run
WHERE job_type = 'games' AND started_at > now() - interval '7 days'
GROUP BY source_code, status;
```

E quais erros, por tipo — agregando pelo `template` do `log.error`, sem parsing de string:

```sql
SELECT g->>'template' AS tipo, sum((g->>'count')::int) AS total, max(g->>'example') AS exemplo
FROM scrape_run, jsonb_array_elements(details->'error_groups') AS g
WHERE started_at > now() - interval '7 days'
GROUP BY 1 ORDER BY 2 DESC;
```

A coleta desses erros não passa por nenhum canal novo: `collect_errors()`
([app/core/errors.py](app/core/errors.py)) pluga um `logging.Handler` durante a execução do job e
agrega tudo que `app.*` logar em nível ERROR. O `log.error` que uma fonte já escreve ao engolir um
erro *é* o sinal — **uma fonte nova não precisa saber que este sistema existe**, só continuar
logando seus erros.

Variáveis opcionais (defaults em [.env.example](.env.example)): `PUSHOVER_APP_NAME` prefixa o
título para distinguir instâncias, `DB_WAIT_NOTIFY_AFTER_SECONDS` define quanto tempo de banco
fora do ar tolera antes de incomodar (abaixo disso, um restart rotineiro do Postgres passa
despercebido) e `MISFIRE_GRACE_SECONDS` separa "o job atrasou" de "o job não rodou".

## Testes

```bash
pip install -r requirements-dev.txt
DATABASE_URL=postgresql+psycopg://fut:fut@localhost:5432/fut_test pytest
```

`tests/test_futnatv_normalize.py` é parsing puro, sem banco. `tests/test_source_contract.py`
exercita o protocol `Source` contra toda fonte registrada mais a `_example`, que o próprio teste
instancia — a parte que toca banco roda contra ela (fake, sem rede) para não depender da API
real; o schema é recriado do zero no banco de `DATABASE_URL`, então aponte para um Postgres
descartável.

## Fontes

| Fonte | Papel |
|---|---|
| [app/sources/futnatv/](app/sources/futnatv/README.md) | fonte real, sobre a API não-oficial de futnatv.net — documentação de engenharia reversa, samples e cliente de referência ficam lá |
| `app/sources/_example/` | fonte fake, sem rede, só para provar o contrato `Source` — não registrada, não roda em produção |

## Status

Remoto configurado em [github.com/VictorFerreiraDaSilva/sports-broadcast-aggregator](https://github.com/VictorFerreiraDaSilva/sports-broadcast-aggregator).
