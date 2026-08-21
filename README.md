# API futnatv.net — documentação (não oficial)

Engenharia reversa da API que alimenta [futnatv.net](https://futnatv.net) — site brasileiro
que lista os jogos do dia, a competição de cada um e **onde cada jogo será transmitido**.

Levantado em **2026-08-21** por observação externa (requisições HTTP + leitura do JS público
do site). Não há documentação oficial; tudo aqui é comportamento observado e pode mudar sem aviso.

## Índice

| Documento | Conteúdo |
|---|---|
| [docs/api-reference.md](docs/api-reference.md) | Todos os endpoints, parâmetros, códigos de erro, CORS, limites |
| [docs/schemas.md](docs/schemas.md) | Estrutura de cada campo de cada payload, com domínios de valores reais |
| [docs/notas-de-campo.md](docs/notas-de-campo.md) | Armadilhas, dados sujos e decisões de parsing |
| [docs/legal-e-etiqueta.md](docs/legal-e-etiqueta.md) | robots.txt, Content-Signals e etiqueta de coleta |
| [examples/futnatv.py](examples/futnatv.py) | Cliente Python de referência (stdlib apenas) |
| [samples/](samples/README.md) | Respostas reais capturadas, para teste offline |

## TL;DR

```
GET https://futnatv.net/api/futebol?data=2026-08-21
GET https://futnatv.net/canais.json            # catálogo de canais/emissoras
GET https://futnatv.net/competicoes-futebol.json  # catálogo de competições
```

Cinco esportes existem: `futebol`, `basquete`, `volei`, `nfl`, `nhl` — todos sob
`/api/{esporte}?data=YYYY-MM-DD`. Cada chamada devolve **um único dia**.

```json
{
  "schedule": [
    {
      "key": "2026-08-21", "day": "21", "month": "AGO", "weekday": "SEX",
      "title": "SEXTA, 21 DE AGOSTO DE 2026",
      "games": [
        {
          "sport": "futebol", "time": "13h00",
          "competition": "Campeonato Saudita", "round": "2ª Rodada",
          "home": "Al-Riyadh", "away": "Al-Nassr",
          "broadcast": "XSports e YouTube (GOAT)",
          "youtubeUrl": "https://www.youtube.com/watch?v=CuUKvR-LoXo",
          "odds": ["-", "-", "-"], "iconEmoji": "⚽"
        }
      ]
    }
  ],
  "availableDates": ["2026-08-14", "…", "2026-08-28"]
}
```

## Os quatro achados que mais importam

1. **Não há CORS.** A resposta não traz nenhum header `Access-Control-Allow-*`. Um `fetch()`
   de outra origem no navegador é bloqueado. A extração precisa rodar em servidor, script,
   extensão ou proxy — não em JS de página cliente.

2. **`availableDates` não lista as datas que têm jogos.** São as datas com pelo menos um jogo de
   **transmissão anunciada**, recortadas em `[data−7, data+7]`. A NHL devolve 10 jogos por dia
   com `availableDates: []`. Quem usa o campo como índice de datas simplesmente não enxerga
   esses jogos. Regra verificada em 150 respostas, sem exceção.

3. **O campo `sport` não identifica o esporte — e o endpoint também vaza.** `/api/nfl` e
   `/api/nhl` devolvem jogos com `"sport": "futebol"`; `/api/volei` devolve 3 jogos de futebol
   sub-17 no meio dos de vôlei. Nenhum dos dois sinais fecha sozinho.

4. **Todas as páginas do site consomem o mesmo endpoint.** `/`, `/time/{slug}/` e
   `/campeonato/{slug}/` servem o mesmo HTML e chamam `/api/futebol?data=…`; o filtro por time
   ou campeonato é feito **no cliente**. Não existe API por time nem por competição — para
   recortar por time/campeonato, filtre você mesmo.

## Como o site monta a tela (útil para replicar)

O payload da agenda traz apenas **texto**: `competition` e `broadcast` são strings livres. Os
logos e o agrupamento visual vêm dos dois catálogos estáticos, casados **por nome** (com uma
lista de `aliases` para cobrir as variações de escrita):

```
/api/futebol → game.competition ─┬─ match por name/aliases → competicoes-futebol.json → /logo campeonatos/{image}
                game.broadcast  ─┴─ match por name/aliases → canais.json             → /logo canais/{image}
                game.home/away  ──── slug manual                                     → /logo times/{Nome}.svg
```

Detalhes do casamento em [docs/schemas.md](docs/schemas.md#casamento-entre-agenda-e-catálogos).

## Scraper (Docker Compose)

Além da documentação, o repositório tem um coletor de produção que roda 4x/dia, captura os 5
esportes para hoje + 3 dias à frente e grava tudo num Postgres.

```bash
cp .env.example .env    # ajuste a senha e o CONTACT_INFO
docker compose up -d --build
```

No primeiro boot (`RUN_ON_STARTUP=true`, default) ele já roda uma coleta completa; depois disso
o schedule é **6:00, 12:00, 18:00 e 23:40** (horário de Brasília), mais uma sincronização diária
dos catálogos (canais/competições) às 5:55 — eles mudam em escala de semanas, então não faz
sentido buscá-los 4x/dia (ver [docs/legal-e-etiqueta.md](docs/legal-e-etiqueta.md)).

As tabelas são criadas sozinhas: o container roda `alembic upgrade head` antes de iniciar o
scheduler. Para rodar um job manualmente (fora do agendamento):

```bash
docker compose run --rm scraper scrape      # coleta jogos agora
docker compose run --rm scraper catalogs    # sincroniza canais/competições agora
```

### Schema

| Tabela | Papel |
|---|---|
| `sport` | os 5 endpoints válidos (seed fixo, não sincroniza com a API) |
| `channel` | catálogo de `canais.json` (nome, categoria, aliases) |
| `competition` | catálogo de `competicoes-futebol.json` (só futebol) |
| `team` | dimensão derivada de `home`/`away`, chave = nome normalizado (sem acento/caixa) |
| `game` | um jogo por linha; chave natural = `(sport_code, game_date, time_raw, home_text, away_text)` — a API não dá ID de jogo, e `sport_code` é o endpoint consultado, não o campo `sport` do payload (que mente para nfl/nhl) |
| `game_broadcast` | quebra de `broadcast_raw` em tokens, casados com `channel`; guarda plataforma + qualificador entre parênteses separados (`YouTube (CazéTV)` → plataforma `YouTube`, qualificador `CazéTV`) |
| `scrape_run` | log de auditoria de cada execução (status, contagens, erros) |
| `catalog_meta` | última `version` sincronizada de cada catálogo, pra não regravar à toa |

Detalhes de cada decisão (por que a chave natural é essa, por que `sport_code` != campo `sport`,
como o split de `broadcast` trata parênteses e vírgulas) estão comentados em
[app/models.py](app/models.py), [app/normalize.py](app/normalize.py) e [app/ingest.py](app/ingest.py).

### Exemplos de análise

```sql
-- jogos transmitidos por canal
select c.name, count(*) from game_broadcast gb
join channel c on c.id = gb.channel_id
group by 1 order by 2 desc;

-- competições com mais transmissões anunciadas
select competition_text, count(*) filter (where has_broadcast) as com_transmissao
from game group by 1 order by 2 desc;

-- % dos jogos de um time em cada canal
select t.display_name, c.name, count(*),
       round(100.0 * count(*) / sum(count(*)) over (partition by t.display_name), 1) as pct
from game g
join team t on t.id in (g.home_team_id, g.away_team_id)
join game_broadcast gb on gb.game_id = g.id
join channel c on c.id = gb.channel_id
group by 1, 2 order by 1, 3 desc;
```

### Limitações herdadas da API (não do código)

- Times sem ID estável: reconciliação por nome normalizado tem ruído se o site reescrever um nome
  entre capturas (ver "o que não existe" em [docs/notas-de-campo.md](docs/notas-de-campo.md)).
- `broadcast`/`competition` são texto livre digitado à mão — o casamento com `channel`/`competition`
  é best-effort (exato → alias → redução de família tipo `ESPN 4`→`ESPN`) e pode não fechar para
  nomes muito novos ainda não catalogados.

## Status

Documentação da API + um scraper de produção (`docker compose up`). Este repositório ainda não
tem remoto configurado.
