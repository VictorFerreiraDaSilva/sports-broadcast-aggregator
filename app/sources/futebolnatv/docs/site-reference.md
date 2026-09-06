# Referência do site

Base: `https://www.futebolnatv.com.br` (o apex `futebolnatv.com.br` redireciona para `www`).

Tudo aqui foi verificado por requisição direta em 2026-08-27. Nada é oficial nem contratual.
Versão do site no rodapé naquele dia: **v4.0.16**.

---

## 1. Stack e infraestrutura

| | |
|---|---|
| Framework | Phoenix LiveView **1.1.28** (Elixir) — `data-phx-session`, `phx-click`, `phx-hook` no HTML |
| Renderização | **Server-side completa** no primeiro GET; o LiveView só assume depois |
| CDN | Cloudflare (`server: cloudflare`, `cf-ray`, `cf-cache-status: DYNAMIC`) |
| Imagens | `https://static.futebolnatv.com.br/upload/{teams,ligas,channel,countries}/…` |
| Cookie | `_futebolnatv_key`, cookie de sessão assinado do Phoenix, `HttpOnly; SameSite=Lax` |
| CSP | `base-uri 'self'; frame-ancestors 'self'` — não restringe coleta server-side |
| Analytics | Plausible self-hosted em `hits.sincnetwork.com.br` |
| Operador | Sinc Lda (rodapé). Contato: `contato(a)futebolnatv.com.br` |

Há apps móveis (`com.futebolnatv`, App Store `id6444346088`). **Não foram inspecionados** —
não sei se falam com uma API própria. Como não existe subdomínio de API resolvendo, se houver
é no mesmo host, mas nenhuma rota `/api*` respondeu.

## 2. Rotas

### 2.1 Agenda — 4 páginas fixas, sem parâmetro de data

```
GET /jogos-hoje      (= /)     GET /jogos-amanha
GET /jogos-ontem               GET /jogos-aovivo
```

Uma página = um dia. **Não existe forma de pedir uma data arbitrária.**

| Tentativa | Resultado |
|---|---|
| `/jogos-hoje?data=2026-08-30` | **200**, byte-a-byte a página de hoje — param ignorado |
| `/jogos-hoje?date=…`, `?dia=…` | idem |
| `/jogos/2026-08-30`, `/jogos-hoje/2026-08-30`, `/agenda/2026-08-30`, `/jogos-2026-08-30` | **404** |
| `/jogos-depois-de-amanha`, `/jogos-amanha/2` | **404** |

Barra final é aceita (`/jogos-hoje/` funciona; o rodapé do próprio site linka assim).
`/` serve o mesmo conteúdo de `/jogos-hoje` com `<link rel="canonical" href="…/">`.

O horizonte, portanto, é **D−1 … D+1**. Para além disso é preciso ir por liga, por time, por
canal ou pelo sitemap.

### 2.2 Jogo — a página canônica

```
GET /aovivo/{home-slug}-x-{away-slug}-{id}.html
```

O `{id}` é hexadecimal de **10, 12 ou 13 dígitos** (no sitemap: 10×10, 166×12, 25×13).
**A URL inteira é a chave** — id sozinho não resolve:

| URL | Resultado |
|---|---|
| `/aovivo/internacional-x-gremio-f621879a903a.html` | **200** |
| `/aovivo/f621879a903a.html` (só id) | **302** → `/jogos-hoje` |
| `/aovivo/foo-x-bar-f621879a903a.html` (slug errado) | **302** → `/jogos-hoje` |
| `/aovivo/internacional-x-gremio.html` (sem id) | **302** → `/jogos-hoje` |
| id inexistente | **302** → `/jogos-hoje` |

Note o **302, não 404**: um coletor que trate "não-200" como erro vai gerar ruído; e um que
siga redirect vai achar que encontrou a página de agenda. Tratar `302 → /jogos-hoje` como
"jogo não existe mais".

### 2.3 Canal

```
GET /canal/{slug}                 # "Programação" — próximos jogos do canal, paginado
GET /canal/{slug}/direitos        # direitos de transmissão por competição
GET /canal/{slug}/profissionais   # narradores/comentaristas
```

`{slug}` é só nome (`espn-4`, `premiere-fc`, `ppv-onefootball`) — **sem id**. As duas abas
extras costumam vir vazias: `/canal/espn/direitos` responde
`"Nenhum direito de transmissão registado para este canal."`

A programação é paginada **sem URL** — só pelo evento `proximos_pagina` no WebSocket (§4).
Para a ESPN: 3 páginas, alcançando D+3.

### 2.4 Liga e time

```
GET /liga/{slug}-{id10}                 # próximos jogos (paginado por WS)
GET /liga/{slug}-{id10}/resultados
GET /liga/{slug}-{id10}/direitos
GET /time/{slug}-{id10}                 # visão geral: último jogo + próximo jogo
GET /time/{slug}-{id10}/jogos           # próximos jogos (paginado por WS: evento jogos_tab_pagina)
GET /time/{slug}-{id10}/resultados
```

`{id10}` é uma string de 10 chars alfanuméricos minúsculos, estilo Sqids/nanoid
(`ek15w9aq8d`, `ne9wa6elab`, `ue8wst5vay`). Ao contrário do jogo, aqui **o id é o que importa**
— é estável e o slug é derivado do nome.

`/time/{…}/jogos` é a rota com o horizonte mais longo do site: 10 jogos na página 1 (hoje até
25/10 para o Grêmio) e mais 6 na página 2 pelo WS (até 02/12).

### 2.5 Catálogos

```
GET /canais            GET /canais?tipo=a | ?tipo=f | ?tipo=internet
GET /ligas             GET /ligas?pagina=2
GET /times             GET /times?pagina=2
```

Aqui a paginação **é** por URL (`?pagina=N`), diferente das listas de jogo.

| Rota | Itens | Observação |
|---|---|---|
| `/ligas` + `/ligas?pagina=2` | **75** ligas | página 1 = "Letras A–O", página 2 = "P–Z"; os 9 "Em destaque" repetem nas duas |
| `/times` + `/times?pagina=2` | **143** times | mesma divisão alfabética |
| `/canais` (sem filtro) | 36 | **idêntico a `?tipo=a`** — renderiza só o grupo "TV aberta" |
| `/canais?tipo=a` | 36 | 12 em destaque + 24 de TV aberta |
| `/canais?tipo=f` | 34 | 12 em destaque + 22 de TV fechada |
| `/canais?tipo=internet` | 35 | 12 em destaque + 23 de internet |
| união dos três filtros | **81** | e ainda assim incompleto — ver §3 |

`/times` tem busca: `phx-submit="search"` e o JSON-LD do site declara
`urlTemplate: "…/times?q={search_term_string}"`.

### 2.6 Outras

`/sign-in`, `/profile/pro`, `/profile/settings`, `/app`, `/info/{futebol-na-tv,contato,suporte,politica,termo-de-uso,advertising}/`.
Conta de usuário serve para seguir time/liga (`phx-click="toggle_follow"`) e tirar anúncios —
nada que abra dado novo. **Não foi testado nada autenticado.**

`/prefs/exi/{valor}?sync=1` — GET disparado pelo JS para gravar preferência de exibição na
sessão. `/prefs/exi/` sem valor dá 404.

## 3. `/site-map.xml` — o índice de descoberta

`robots.txt` aponta para `https://www.futebolnatv.com.br/site-map.xml` (com hífen;
`/sitemap.xml` dá 404). **325 URLs**, uma requisição:

| Tipo | Qtd | `changefreq` |
|---|---|---|
| `/aovivo/…` (jogos) | **201** | `always` (53) / `daily` (270 no total do arquivo) |
| `/canal/…` | **100** | `daily` |
| `/time/…` | 10 | `daily` |
| `/liga/…` | 9 | `daily` |
| páginas de agenda + `/` | 5 | `hourly` / `always` |

Duas propriedades medidas que fazem dele o melhor ponto de partida:

- **Janela de jogos ≈ hoje → hoje+5.** Contém 26/26 de `/jogos-hoje` e 26/26 de
  `/jogos-amanha` (interseção total), mais 149 jogos que as listas de dia não alcançam.
  Confirmado: `atletico-mg-x-cruzeiro` (01/09) está dentro; `santos-x-palmeiras` e
  `vitoria-x-vasco` (02/09) e `gremio-x-internacional` (03/09) estão fora. De ontem sobram
  poucos (3 de 25).
- **É o catálogo de canais mais completo que existe.** 100 slugs, superconjunto estrito dos 81
  da união de `/canais?tipo=*`. Os 19 exclusivos:
  `paramount`, `pluto-tv`, `ppv`, `ppv-onefootball`, `ppv-twitch`, `ppv-youtube`,
  `prime-video`, `r7-com`, `rede-furacao`, `redeon-app`, `tv-do-ze-youtube`, `tv-itnet`,
  `tv-mar`, `tv5-monde`, `twitch`, `twitter`, `xsports`, `youtube`, `zapping-tv`.
  Entre eles `prime-video` e `ppv-onefootball` — dois dos canais mais frequentes nos jogos de
  hoje.

O sitemap herda o filtro de transmissão: `uruguai-sub-20-x-paraguai-sub-20`, jogo de hoje sem
canal, não está nele.

## 4. O WebSocket do LiveView

Único jeito de paginar programação de canal e jogos de time/liga. Não devolve JSON de domínio
— devolve *diffs de template* do Phoenix, dos quais se extrai HTML.

**Handshake.** Do HTML da página, tirar três coisas:

```
<meta name="csrf-token" content="…">           → _csrf_token
<div id="phx-XXXXXXXX" data-phx-main
     data-phx-session="…" data-phx-static="…">  → topic, session, static
```

Conectar com o cookie de sessão da mesma resposta:

```
wss://www.futebolnatv.com.br/live/websocket?_csrf_token={csrf}&_mounts=0&_live_referer=undefined&vsn=2.0.0
```

Entrar no tópico (formato de array do `vsn=2.0.0`):

```json
["4","4","lv:phx-XXXXXXXX","phx_join",
 {"url":"https://www.futebolnatv.com.br/time/gremio-ue8wst5vay/jogos",
  "params":{"_csrf_token":"…","_mounts":0},
  "session":"…","static":"…"}]
```

A resposta (`phx_reply`, ~49 KB) traz `liveview_version` e o template `rendered` inteiro.

**Eventos de paginação** (`type: "click"`):

| Evento | Página | Valor |
|---|---|---|
| `jogos_tab_pagina` | `/time/{…}/jogos` | `{"dir":"next"}` / `{"dir":"prev"}` |
| `proximos_pagina` | `/canal/{slug}` | idem |

```json
["4","5","lv:phx-XXXXXXXX","event",
 {"type":"click","event":"jogos_tab_pagina","value":{"dir":"next"}}]
```

Verificado: a página 2 do Grêmio devolve um diff de 5,6 KB com 6 jogos entre 28/10 e 02/12; a
ESPN chega até 30/08 na página 3 de 3.

Outros eventos vistos no HTML, sem valor de dados: `toggle_follow`, `toggle_filtro_sheet`
(ordenação da lista), `set_jogo_tab`, `destaque_poll_vote` / `destaque_poll_open_edit`
(enquete). Hooks JS: `AdsenseUnit`, `DestaqueScroll`, `RoundImageSkeleton`, `ChannelSearch`,
`DestaqueCountdown`, `SyncExibicaoSession`.

Um cliente WebSocket mínimo em stdlib (~60 linhas: handshake HTTP + frames mascarados) é
suficiente; não precisa de biblioteca.

## 5. Custo e limites

Medido em 2026-08-27, com `--compressed`:

| Página | Tamanho (gzip) | TTFB |
|---|---|---|
| `/jogos-hoje` | 22,6 KB | 0,47 s |
| `/aovivo/{jogo}.html` | 13,0 KB | 0,25 s |
| `/liga/{…}` | 11,5 KB | 0,29 s |
| `/time/{…}/jogos` | 10,7 KB | 0,25 s |
| `/canal/{slug}` | 10,2 KB | 0,34 s |
| `/canais`, `/ligas`, `/times` | 9,9–11,7 KB | 0,26–0,29 s |

Sem compressão o HTML é ~60–270 KB (a home crua tem 267 KB, quase tudo Tailwind inline).
**Sempre pedir gzip.**

**Não foi observado nenhum rate limit**: 20 requisições seguidas sem pausa à mesma página →
20× 200. Também não há bloqueio por user-agent — UA de browser, UA custom, `python-urllib/3.12`
e requisição sem UA nenhum, todas 200. Isso é o que o servidor *permite*, não o que é
apropriado fazer: ver [legal-and-etiquette.md](legal-and-etiquette.md).

## 6. O que não existe

- Endpoint JSON, de qualquer forma.
- Consulta por data arbitrária.
- Paginação por URL nas listas de jogo (só nos catálogos).
- Estádio/local: o JSON-LD traz `"location": {"@type":"Place","name":"Estádio"}` — literal,
  placeholder, igual em todos os jogos.
- Árbitro, escalação, estatística de partida.
- Esporte que não seja futebol.
- Id externo de qualquer provedor (nada de referência a Sofascore, API-Football, etc.).
