# Referência da API

Base: `https://futnatv.net`

Tudo aqui foi verificado por requisição direta em 2026-08-21. Nada é oficial nem contratual.

---

## 1. Agenda — `GET /api/{esporte}`

O único endpoint dinâmico do site. Devolve a agenda de **um dia**.

```
GET https://futnatv.net/api/futebol?data=2026-08-21
```

### Esportes válidos

A lista é fechada e **sensível a maiúsculas** (só minúsculo funciona):

| Esporte | Status em 2026-08-21 | Observação |
|---|---|---|
| `futebol` | ativo, ~40 jogos/dia | o principal; o único com o campo `aggregate` |
| `basquete` | ativo, ~3 jogos/dia | WNBA |
| `volei` | **sazonal** | 15 jogos em 9 datas (25/07–08/08); zerado fora disso |
| `nfl` | ativo, ~4 jogos/dia | futebol americano, pré-temporada |
| `nhl` | ativo, ~8 jogos/dia | hóquei no gelo |

> **Um esporte vazio hoje não é um esporte inexistente.** O `volei` responde `schedule: []` em
> agosto e parecia morto numa varredura de 30 dias a partir de 10/08 — mas tem competição
> cadastrada (Liga das Nações) em julho. Antes de concluir que um endpoint não tem dados, varra
> um intervalo largo.

Qualquer outro valor → **404** `{"erro":"Endpoint inválido."}`. Foram testados e rejeitados:
`tenis`, `f1`, `formula1`, `ufc`, `mma`, `boxe`, `nba`, `mlb`, `esports`, `handebol`, `rugby`,
`golfe`, `news`, `noticias`, `todos`, `all`, `agenda`, `esportes`, `canais`, `competicoes`,
`hoje`, `jogos`, `futsal`, `beisebol`, `hoquei`, `olimpiadas`, `wnba`, `kings`, `motogp`,
`brasileirao`, `libertadores`, `champions`, `soccer`, `basketball`, `football`, `volleyball`,
além de `FUTEBOL` e `Futebol` (confirmando a sensibilidade a caixa).

Barra final é aceita: `/api/futebol/?data=…` funciona igual.
`/api/` sozinho → 404 `{"erro":"Endpoint inválido."}`.

### Parâmetro `data` (obrigatório)

| | |
|---|---|
| Formato | `YYYY-MM-DD` — validado por regex estrito de `\d{4}-\d{2}-\d{2}` |
| Ausente / vazio / malformado | **400** `{"erro":"Informe uma data válida no formato AAAA-MM-DD."}` |
| Rejeitados | `2026-8-21` (sem zero à esquerda), `26-08-21`, `abc`, `` (vazio) |
| Aceitos mas sem sentido | `2026-13-01`, `2026-02-30` → **200** com `schedule: []` e `availableDates: []` (a regex passa, o calendário não existe) |
| Fora do dataset | `1999-01-01` → **200** `{"schedule":[],"availableDates":[]}` |

Não existe forma de pedir mais de um dia por chamada. Não foram encontrados parâmetros
adicionais (`dias`, `days`, `limit`, `sport`, `format` etc. são todos ignorados).

### Resposta

```jsonc
{
  "schedule":       [ /* 0 ou 1 objeto-dia — nunca mais que 1 */ ],
  "availableDates": [ "2026-08-14", /* … */ "2026-08-28" ]
}
```

`schedule` vem com **um** objeto-dia quando a data pedida tem jogos, e vazio quando não tem.
Estrutura completa em [schemas.md](schemas.md).

### `availableDates` — datas com transmissão anunciada, não datas com jogos

Este é o campo mais mal-interpretável da API, e o nome atrapalha. A regra exata, **verificada em
150 respostas (30 datas × 5 esportes) sem uma única divergência**, é:

> `availableDates(D)` = { datas que têm **pelo menos um jogo com `broadcast` não vazio** }
> ∩ `[D−7, D+7]`

Ou seja: duas coisas ao mesmo tempo — um filtro por transmissão anunciada, e um recorte de ±7
dias em torno da data pedida.

**Uma data pode ter jogos e não estar em `availableDates`.** É o caso mais comum de erro:

| Esporte | Datas com jogos (amostra de 30 dias) | Datas em `availableDates` |
|---|---|---|
| `futebol` | 19 | 19 — coincidem |
| `nfl` | 9 | 9 — coincidem |
| `basquete` | **15** | **2** (`08-16`, `08-18`) |
| `nhl` | **6** | **0** — sempre vazio |
| `volei` | 0 nessa janela (9 em julho) | 0 nessa janela |

A NHL devolve 7 a 10 jogos por dia com `availableDates` **sempre `[]`**, porque nenhum jogo de
NHL tem emissora cadastrada. O basquete tem jogos todo dia, mas só dois dias com transmissão
anunciada. Em futebol e NFL os dois conjuntos coincidem por acaso — praticamente todo dia com
jogo tem alguma transmissão —, e é isso que faz a leitura errada parecer certa.

O recorte de ±7 dias é fácil de confirmar isolando um esporte esparso: para `basquete`, o
conjunto-base é `{08-16, 08-18}` e a resposta varia só pelo recorte —

| `data=` | janela `[D−7, D+7]` | `availableDates` |
|---|---|---|
| `2026-08-10` | `08-03 … 08-17` | `["2026-08-16"]` |
| `2026-08-16` | `08-09 … 08-23` | `["2026-08-16","2026-08-18"]` |
| `2026-08-24` | `08-17 … 08-31` | `["2026-08-18"]` |
| `2026-08-26` | `08-19 … 09-02` | `[]` |

**O conjunto não é contíguo.** Em futebol ele parece um intervalo fechado, mas isso é
coincidência de haver jogo todo dia. O `volei` mostra a forma real — buracos no meio:

```
GET /api/volei?data=2026-08-01
→ ["2026-07-25","2026-07-26","2026-07-29","2026-07-30","2026-08-01","2026-08-02"]
                              ↑ faltam 27 e 28
```

Não trate `availableDates[0]` e `availableDates[-1]` como um intervalo — itere a lista.

#### Consequências práticas

- **Não use `availableDates` para descobrir onde há jogos.** Ele responde outra pergunta.
  A única forma confiável é pedir a data e olhar `schedule`.
- **Não use `availableDates` como calendário global.** Ele nunca mostra mais de 15 dias, e
  o conteúdo muda a cada chamada porque a janela acompanha a `data` pedida.
- **Use-o para o que ele serve:** montar um seletor de datas que só oferece dias com transmissão
  confirmada — que é exatamente o uso do site.
- Para enumerar o conjunto-base inteiro, caminhe: peça uma data, salte 7 dias além de cada borda
  retornada, repita até parar de crescer. Isso funciona porque o conjunto-base é fixo; mas
  **um vão maior que 15 dias interrompe a caminhada**, então o resultado é um limite inferior.

### Comportamento HTTP

| Aspecto | Observado |
|---|---|
| **CORS** | **Nenhum header `Access-Control-Allow-*`.** Fetch cross-origin no browser é bloqueado. |
| Método | Ignorado. `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD` e `OPTIONS` devolvem 200 com o mesmo corpo do `GET`. |
| Cache | Nenhum `Cache-Control`, `ETag`, `Expires` ou `Last-Modified`. O site chama sempre com `cache: 'no-store'`. |
| Content-Type | `application/json; charset=UTF-8` — inclusive nos erros 400/404 |
| Infra | Cloudflare (headers `cf-ray`, `nel`, `report-to`) |
| Latência | ~0,5 s por requisição, estável em amostra de 5 |
| Autenticação | Nenhuma. Sem chave, sem cookie, sem `Referer` obrigatório. |
| Rate limit | Nenhum observado — ~150 requisições em poucos minutos passaram sem bloqueio. Isso **não** é garantia; veja [legal-e-etiqueta.md](legal-e-etiqueta.md). |

### Erros

| HTTP | Corpo | Quando |
|---|---|---|
| 400 | `{"erro":"Informe uma data válida no formato AAAA-MM-DD."}` | `data` ausente, vazio ou fora do formato |
| 404 | `{"erro":"Endpoint inválido."}` | esporte fora da lista branca, ou `/api/` sem esporte |

Um erro sempre traz a chave `erro` e **nunca** as chaves `schedule`/`availableDates` —
é o teste mais barato para distinguir sucesso de falha.

---

## 2. Catálogo de canais — `GET /canais.json`

```
GET https://futnatv.net/canais.json
```

61 canais/plataformas de transmissão, com categoria, prioridade de exibição e arquivo de logo.
Serve para transformar a string livre `game.broadcast` em entidade estruturada + logo.

O `?v=20260722-3` que o site usa é **apenas cache-buster**: `?v=1`, `?v=xxxx` e a ausência do
parâmetro devolvem exatamente os mesmos 13.032 bytes. A versão real do conteúdo está no campo
`version` de dentro do JSON (`"2026-08-10"` na captura).

Schema em [schemas.md](schemas.md#canaisjson).

---

## 3. Catálogo de competições — `GET /competicoes-futebol.json`

```
GET https://futnatv.net/competicoes-futebol.json
```

224 competições de futebol, com categoria (`Destaques`, `Brasil`, `Europa`, `Feminino`, `Base`…),
prioridade e logo. Mesmo papel: casar a string livre `game.competition` com uma entidade + logo.
O `?v=` também é ignorado.

**Só existe a versão de futebol.** Retornam 404 (HTML): `competicoes-basquete.json`,
`competicoes-volei.json`, `competicoes-nfl.json`, `competicoes-nhl.json`, `competicoes.json`.
Os demais esportes não têm catálogo de competições publicado.

Schema em [schemas.md](schemas.md#competicoes-futeboljson).

---

## 4. Assets estáticos (logos)

Servidos de três diretórios com **espaço no nome** — precisa de URL-encoding (`%20`):

| Diretório | Origem do nome do arquivo | Exemplo |
|---|---|---|
| `/logo canais/` | campo `image` / `darkImage` / `selectedImage` de `canais.json` | `https://futnatv.net/logo%20canais/Globo.svg` |
| `/logo campeonatos/` | campo `image` / `darkImage` de `competicoes-futebol.json` | `https://futnatv.net/logo%20campeonatos/Libertadores.png` |
| `/logo times/` | nome do time **sem acentos**, sempre `.svg` | `https://futnatv.net/logo%20times/Palmeiras.svg` |

Todos verificados com HTTP 200 e content-type correto (`image/svg+xml`, `image/png`).

Duas diferenças de construção entre eles, herdadas do JS do site:

- `/logo canais/` e `/logo campeonatos/` usam o nome de arquivo **completo, com extensão**, exatamente
  como está no JSON (`"Record.png"`, `"UEFA Champions League_n.png"`).
- `/logo times/` **não** vem de nenhum JSON: a extensão `.svg` é anexada em código a um nome de time
  já normalizado sem acentos (`Atlético-MG` → `Atletico-MG.svg`, `São Paulo` → `Sao Paulo.svg`).
  Não existe lista pública desses arquivos — só os times embutidos no HTML do site (60 no total,
  divididos em Série A, Série B e Internacionais) têm escudo garantido.

Convenção de sufixos, consistente nos três diretórios:

| Sufixo | Uso |
|---|---|
| *(nenhum)* | tema claro |
| `_n` | tema escuro (`night`) — só existe para alguns; caia no `image` quando faltar |
| `_c` | estado selecionado/colorido — idem |

Bandeiras de país não são locais: o site usa `https://flagcdn.com/w40/{country}.png`,
alimentado pelo campo `country` do jogo.

---

## 5. Rotas HTML (contexto, não API)

Todas servem o **mesmo** shell SPA (~270 KB) e buscam `/api/futebol` no cliente:

| Rota | Papel |
|---|---|
| `/` e `/?data=YYYY-MM-DD` | agenda do dia |
| `/time/{slug}/` | 60 páginas de time — filtro client-side |
| `/campeonato/{slug}/` | 23 páginas de competição — filtro client-side |
| `/basquete/`, `/nfl/`, `/volei/` | mesma SPA apontando para outro esporte |
| `/news/{slug}/` | 167 artigos, HTML estático (sem API) |
| `/assistir/`, `/app/`, `/sobre/`, `/privacidade/` | páginas institucionais (todas HTTP 200) |

`sitemap.xml` lista **258 URLs** e é a forma mais barata de enumerar os slugs — 167 de `/news/`,
60 de `/time/`, 23 de `/campeonato/` e 8 páginas fixas. (`/assistir/` existe e responde 200, mas
não está no sitemap; só é alcançável pelo link da home.)

O HTML expõe `window.__FUTNATV_INITIAL_SCHEDULE__` como possível payload embutido, mas em produção
ele vem **nulo** — não dá para pular a chamada de API lendo o HTML.

### Arquivos que existem só no build local

O JS referencia `8f4c2b91-f.json`, `8f4c2b91-b.json` e `8f4c2b91-v.json` (futebol / basquete /
vôlei) como fonte de dados quando a página roda via `file://`. **Em produção os três dão 404.**
São o fallback offline do desenvolvedor, não um endpoint alternativo.
