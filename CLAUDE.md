# CLAUDE.md

Agregador de calendários esportivos. Ver [README.md](README.md) para a arquitetura,
[CONTEXT.md](CONTEXT.md) para o glossário e [docs/adr/](docs/adr/) para as decisões.

## Convenção de idioma

**Código é em inglês. Prosa de documentação é em português.**

Em inglês, sem exceção:

- **Nomes de arquivo e diretório** — inclusive de `.md`, migrations e samples.
  (`0001_initial_schema.py`, `docs/adr/0007-error-notification-via-logging.md`,
  `samples/channels-excerpt.json`.)
- **Identificadores** — módulos, classes, funções, variáveis, constantes, fixtures
  e nomes de teste.
- **Comentários e docstrings.**
- **Mensagens de log** (`log.info("starting games collection: source=%s", ...)`).
- **Notificações Pushover** — títulos e corpos (`"{job_label} failed"`,
  `"database unreachable"`).
- **Mensagens de exceção** e textos de `argparse` (`help=`, descrições).
- **Comentários de config** — `.env.example`, `docker-compose.yml`,
  `docker/entrypoint.sh`, `Dockerfile`.
- **Schema do banco** — tabelas, colunas, índices, constraints.

Em português:

- A prosa de todo `.md`: `README.md`, `CONTEXT.md`, os ADRs em `docs/adr/` e os docs
  da fonte em `app/sources/futnatv/docs/`. Só os *nomes* desses arquivos são em inglês.

### Exceções deliberadas

Não "corrigir" estas — são dados ou vocabulário externo, não código:

- **Códigos de esporte canônicos**: `futebol`, `basquete`, `volei` (+ `nfl`, `nhl`).
  São valores em `sport.code`/`game.sport_code` e espelham os endpoints da fonte
  (`/api/futebol`). Traduzir exigiria migration de dados e transformaria o
  `_SPORT_MAP` identidade num mapa de tradução real.
- **Chaves de `catalog_meta`**: `canais`, `competicoes_futebol` — espelham
  `canais.json` e `competicoes-futebol.json` da API do futnatv.
- **Vocabulário da API externa**: a chave de erro `erro`, o query param `data=`,
  os separadores `" e "` em `broadcast`.
- **Revision id do Alembic**: `0001_schema_inicial`. O arquivo foi renomeado para
  `0001_initial_schema.py`, mas o id continua igual — ele está gravado em
  `alembic_version` nos bancos existentes, e mudá-lo quebraria
  `alembic upgrade head` em qualquer deploy já rodando.
- **Nomes próprios**: `CazéTV`, `Brasília`, nomes de canais e competições.

## Verificação

Rodar os testes exige um Postgres descartável (o `conftest.py` faz `drop_all`):

```bash
docker run -d --rm --name fut-test-pg -e POSTGRES_USER=fut -e POSTGRES_PASSWORD=fut \
  -e POSTGRES_DB=fut -p 55432:5432 postgres:16-alpine
PYTHONPATH=. DATABASE_URL=postgresql+psycopg://fut:fut@localhost:55432/fut pytest
```

Nunca apontar `DATABASE_URL` de teste para o Postgres de desenvolvimento na 5432.
