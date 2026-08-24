# Fonte futnatv

Adapter da fonte `futnatv` (`app/sources/futnatv/source.py`) sobre a API não-oficial de
[futnatv.net](https://futnatv.net) — site brasileiro que lista os jogos do dia, a competição de
cada um e **onde cada jogo será transmitido**. Implementa o protocol `Source`
([app/core/source.py](../../core/source.py)) do agregador (ver [README.md](../../../README.md) da
raiz para a visão geral da arquitetura).

Levantado em **2026-08-21** por observação externa (requisições HTTP + leitura do JS público do
site). Não há documentação oficial; tudo aqui é comportamento observado e pode mudar sem aviso.

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

## Este adapter

`FutnatvSource` ([source.py](source.py)) implementa `fetch_games` e `sync_catalog`, e faz
internamente o que os documentos acima descrevem: uma chamada por esporte×data (não existe
endpoint de intervalo), casamento de `competition`/`broadcast` contra os catálogos estáticos
(`catalogs.py`, escopado a `source_code="futnatv"`), e o parsing de campos peculiares
(`normalize.py`) — odds, `youtubeUrl`, `iconEmoji`, `country`, `aggregate` — que vira
`source_data` opaco nas linhas de `game` (ver [ADR 0006](../../../docs/adr/0006-core-schema-plus-source-data-jsonb.md)).

Config namespaced em [config.py](config.py) (`FUTNATV_BASE_URL`,
`FUTNATV_REQUEST_DELAY_SECONDS`, `FUTNATV_CONTACT_INFO`, ...). Cadência de coleta declarada em
`FutnatvSource.games_schedule`/`catalog_schedule` — 6:00, 12:00, 18:00 e 23:40 (horário de
Brasília) para jogos, 5:55 para o catálogo (canais/competições mudam em escala de semanas, ver
[docs/legal-e-etiqueta.md](docs/legal-e-etiqueta.md)).

### Exemplos de análise

```sql
-- jogos da fonte futnatv transmitidos por canal
select c.name, count(*) from game_broadcast gb
join channel c on c.id = gb.channel_id
join game g on g.id = gb.game_id
where g.source_code = 'futnatv'
group by 1 order by 2 desc;

-- competições com mais transmissões anunciadas
select competition_text, count(*) filter (where has_broadcast) as com_transmissao
from game where source_code = 'futnatv' group by 1 order by 2 desc;
```

### Limitações herdadas da API (não do código)

- Times sem ID estável: reconciliação por nome normalizado tem ruído se o site reescrever um nome
  entre capturas (ver "o que não existe" em [docs/notas-de-campo.md](docs/notas-de-campo.md)).
- `broadcast`/`competition` são texto livre digitado à mão — o casamento com `channel`/`competition`
  é best-effort (exato → alias → redução de família tipo `ESPN 4`→`ESPN`) e pode não fechar para
  nomes muito novos ainda não catalogados.
