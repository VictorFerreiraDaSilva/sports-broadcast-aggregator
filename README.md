# Agregador de calendários esportivos

Agrega jogos e onde assisti-los a partir de múltiplas fontes públicas (sites/APIs de terceiros).
Cada fonte é coletada, normalizada para um modelo comum e gravada lado a lado com as demais —
sem tentar fundir o mesmo jogo real relatado por fontes diferentes.

Ver [CONTEXT.md](CONTEXT.md) para o glossário (Fonte, Jogo, Esporte canônico, Catálogo, Nível e
Gênero da competição) e [docs/adr/](docs/adr/) para as decisões de arquitetura por trás do que
segue. O agregador não decide o que é relevante para ninguém nem envia mensagem alguma
([ADR 0009](docs/adr/0009-personal-relevance-stays-out.md)) — quem consome o banco encontra em
[docs/consumer-contract.md](docs/consumer-contract.md) o que ele oferece e o que fica do outro
lado da fronteira.

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
| `game` | um jogo por linha, **por fonte que o relatou**; chave natural = `(source_code, sport_code, game_date, time_raw, home_text, away_text)` — sem fusão entre fontes. Carrega também `tier`/`gender`, a classificação canônica da competição (ver abaixo) |
| `game_broadcast` | tokens de `broadcast_raw` já casados contra `channel` pela própria fonte |
| `catalog_meta` | última `version` sincronizada de cada catálogo, por fonte |
| `scrape_run` | log de auditoria de cada execução de job, por fonte — `status` é `success`, `degraded` (gravou, mas engoliu erros) ou `error` |

### Nível e gênero da competição

As fontes publicam **um** campo `category` que espreme três eixos — geografia, gênero e nível
(`Destaques`, `Brasil`, `Feminino`, `Base`, ...). Como os valores são exclusivos, uma competição
feminina *e* de base só cabe num deles: a `Copa do Mundo Feminina sub-20` está em `Feminino`, e
lida ingenuamente contaria como profissional.

Por isso o agregador mantém dois eixos próprios, resolvidos na ingestão por
[app/core/classification.py](app/core/classification.py) e gravados em `game`
([ADR 0008](docs/adr/0008-competition-tier-and-gender-at-ingestion.md)):

| Coluna | Valores | |
|---|---|---|
| `tier` | `professional` `youth` `unknown` | nível |
| `gender` | `men` `women` `unknown` | gênero |
| `tier_method` / `gender_method` | `curated` `source` `pattern` `none` | qual regra decidiu |

A regra que dá forma a tudo: **a categoria da fonte é evidência apenas positiva.** `Base` afirma
que é base; qualquer outra categoria não afirma nada sobre o nível. Então a precedência esgota a
evidência de base antes de deixar a fonte afirmar `professional`:

```
1. curadoria em classification.py (nome normalizado)        → esse valor      [curated]
2. dica da fonte diz base                          → youth           [source]
3. padrão no nome (sub-NN, U-NN, júnior, youth...) → youth           [pattern]
4. só então, dica da fonte diz não-base            → professional    [source]
5. nada disparou                                   → unknown         [none]
```

`unknown` é valor explícito e contável de propósito: sem ele, tudo que ninguém classificou entra
silenciosamente na conta como profissional — que é o viés a eliminar.

**Por que isso importa.** Medido em 270 jogos (06–11/09, futnatv): base é 23 % do volume e 6,5 %
das transmissões. Contá-la derruba a cobertura aparente em 13,6 pontos.

| Recorte | Jogos | Com transmissão | % |
|---|---:|---:|---:|
| Tudo | 270 | 168 | 62,2 % |
| Só profissional | 207 | 157 | **75,8 %** |
| Só base | 63 | 11 | 17,5 % |

Cobertura de transmissão por nível — **sempre por fonte**, nunca somando: cada fonte tem um
recorte editorial diferente (o futebolnatv só lista jogo que já tem transmissão anunciada, então
pontuaria 100 % por construção), e o [ADR 0002](docs/adr/0002-source-scoped-games-no-cross-source-merge.md)
não funde o mesmo jogo entre fontes:

```sql
SELECT source_code, sport_code, tier,
       count(*) AS jogos,
       count(*) FILTER (WHERE has_broadcast) AS com_transmissao,
       round(100.0 * count(*) FILTER (WHERE has_broadcast) / count(*), 1) AS pct
FROM game
WHERE game_date >= current_date - 30
GROUP BY source_code, sport_code, tier
ORDER BY source_code, sport_code, tier;
```

E a **fila de curadoria** — o que nenhuma regra classificou, ordenado por quanto pesa. É assim que
se descobre o que falta em `classification.py` (e foi assim que apareceram os 18 jogos de
`Champions League` que não casavam com o catálogo):

```sql
SELECT sport_code, competition_text,
       count(*) AS jogos,
       count(*) FILTER (WHERE has_broadcast) AS com_transmissao
FROM game
WHERE tier_method = 'none'
GROUP BY sport_code, competition_text
ORDER BY jogos DESC;
```

Trocar `tier_method = 'none'` por `= 'pattern'` mostra o outro lado: o que foi **adivinhado** pelo
nome, sem confirmação da fonte nem da curadoria.

Depois de editar as listas curadas em `classification.py`, os jogos já gravados fora da janela de
coleta continuam com a classificação antiga — `docker compose run --rm aggregator reclassify`
reaplica as regras que não dependem de dica da fonte (`curated` e `pattern`), sem nunca rebaixar
uma linha.

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
docker compose run --rm aggregator reclassify          # reaplica classification.py aos jogos já gravados
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

Os testes recriam o schema do zero (`drop_all`), então rodam contra um Postgres descartável numa
porta própria — **nunca** contra o de desenvolvimento na 5432:

```bash
docker run -d --rm --name fut-test-pg -e POSTGRES_USER=fut -e POSTGRES_PASSWORD=fut \
  -e POSTGRES_DB=fut -p 55432:5432 postgres:16-alpine
pip install -r requirements-dev.txt
PYTHONPATH=. DATABASE_URL=postgresql+psycopg://fut:fut@localhost:55432/fut pytest
docker stop fut-test-pg   # --rm apaga o container junto
```

`tests/test_futnatv_normalize.py` e `tests/test_classification.py` são lógica pura, sem banco — o
segundo cobre a precedência da classificação com casos tirados de jogos reais.
`tests/test_futnatv_catalogs.py` cobre o índice de competições, incluindo os aliases curados.
`tests/test_source_contract.py`
exercita o protocol `Source` contra toda fonte registrada mais a `_example`, que o próprio teste
instancia — a parte que toca banco roda contra ela (fake, sem rede) para não depender da API
real.

## Fontes

| Fonte | Papel |
|---|---|
| [app/sources/futnatv/](app/sources/futnatv/README.md) | fonte real, sobre a API não-oficial de futnatv.net — documentação de engenharia reversa, samples e cliente de referência ficam lá |
| `app/sources/_example/` | fonte fake, sem rede, só para provar o contrato `Source` — não registrada, não roda em produção |

## Status

Remoto configurado em [github.com/VictorFerreiraDaSilva/sports-broadcast-aggregator](https://github.com/VictorFerreiraDaSilva/sports-broadcast-aggregator).
