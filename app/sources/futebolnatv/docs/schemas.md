# Schemas

Não há payload — há HTML. Este documento descreve **que campo sai de que página**, por qual
âncora, e com que domínio de valores. Medido em 2026-08-27 sobre `/jogos-hoje` (26 jogos),
`/jogos-amanha` (26), `/jogos-ontem` (22), `/jogos-aovivo` (13), 7 páginas de jogo, 5 de
liga/time/canal e os três catálogos.

> **Ancorar em `id`, `role` e `aria-*`, nunca em classe.** As classes são Tailwind gerado
> (`text-[0.65rem] font-bold uppercase tracking-wide sm:text-xs text-zinc-700 …`) e mudam a
> cada ajuste de design. Os `id` são semânticos e estáveis: `fntv-hr-{n}`,
> `jogo-card-team-a-{slug}`, `liga-header-logo-{slug}`, `channel-list-logo-{id}`,
> `tabpanel-onde-assistir`.

---

## 1. Lista de agenda (`/jogos-hoje`, `/jogos-amanha`, `/jogos-ontem`, `/jogos-aovivo`)

Três blocos com jogos na mesma página, **os três com o mesmo conjunto de jogos**:

| Bloco | Âncora | Conteúdo |
|---|---|---|
| Destaques | `#fntv-destaque-scroller` > `#fntv-dc-{n}` | 3 jogos do dia, cartão resumido, com enquete |
| Lista por hora | `#fntv-jogos-por-hora` > `#fntv-hr-{n}` | **a lista completa**, ordenada por horário |
| Texto por competição | `section[aria-labelledby="fntv-jogos-hoje-texto-heading"]` | bloco de SEO, `<h3>` = competição, `<li>` = `"Casa x Fora — HH:MM"` |

O bloco de SEO é o mais fácil de parsear e serve de **conferência**: em todas as capturas
listou exatamente os mesmos jogos da lista por hora. Não tem canal nem placar.

Cuidado: `#fntv-hr-{n}` **não é contíguo** — a cada ~5 cartões entra um `<div>` de anúncio com
o mesmo padrão de id e sem `<a href="/aovivo/">`. Filtrar por presença do link.

### `Game` (cartão da lista por hora)

| Campo | Âncora | Presença | Domínio observado |
|---|---|---|---|
| `url` / `id` | `a[href^="/aovivo/"]` | 100 % | `{home}-x-{away}-{hex}.html`; hex de 10, 12 ou 13 chars |
| `competition` | `#liga-header-logo-{slug}` + `<p>` irmão, 1º `<span>` | 100 % | texto livre: `UEFA Conference League`, `Copa da liga Inglesa`, `Brasileirão Série D` |
| `round` | mesmo `<p>`, 2º `<span>` | ~90 % | `- Playoff round`, `- Rodada  2` (dois espaços), `- Round of 64`, `- Mata-mata`, `- Quartas de Final` |
| `competition_logo` | `img` dentro de `#liga-header-logo-…` | 100 % | `…/upload/ligas/{40}.png`, ou **a bandeira do país** (`…/upload/countries/{40}.png`) quando a liga não tem logo |
| `time` | `<time>` | 100 % | `HH:MM`, 24 h, **fuso de Brasília** |
| `home` / `away` | `img[alt]` em `#jogo-card-team-a-{slug}` / `-team-b-{slug}` | 100 % | nome de exibição; grafia internacional |
| `home_logo` / `away_logo` | `img[src]` idem | 100 % | `…/upload/teams/{md5}.png` |
| `score` | `<span>` irmão do bloco de time | só ao vivo/encerrado | inteiro como string |
| `status` | bloco após `<time>` | ver §1.1 | `72'`, `FIM DE`+`JOGO`, ou vazio |
| `broadcast[]` | chips no rodapé do `<article>` (`span` contendo `.hero-tv`) | **100 %** | ver §1.2 |

### 1.1 Status ao vivo

Três formas, todas texto:

- **Agendado** — bloco vazio.
- **Em andamento** — `<span>` com o minuto: `17'`, `62'`, `77'`. Só o minuto; não vi
  `INTERVALO`, `PRORROGAÇÃO`, `PÊNALTIS`, `ADIADO` na amostra (não significa que não existam).
- **Encerrado** — dois `<span>` separados, `FIM DE` e `JOGO`. Um parser ingênuo que pega
  `<span>` isolados vai reportar dois campos; juntar.

`/jogos-aovivo` traz só os em andamento (13 no momento da captura) e o contador aparece no
próprio menu (`Agora  13`).

### 1.2 O chip de transmissão

É a estrutura mais valiosa da fonte. Um chip por canal, **já separado** — nada de string única
com `" e "` para quebrar:

```html
<span class="inline-flex … rounded-full border …">
  <span class="hero-tv …"></span>                    <!-- ícone: sempre hero-tv -->
  <span class="truncate …">GLOBO</span>              <!-- nome do canal, CAIXA ALTA -->
  <span class="shrink-0 …">(RS, SP(BRAGAÇA))</span>  <!-- qualificador, opcional -->
</span>
```

**Nome** (`102` chips na amostra, 23 valores distintos): `PPV ONEFOOTBALL` (26), `DISNEY+` (13),
`YOUTUBE` (11), `PRIME VIDEO` (10), `SPORTV` (6), `GLOBO` (5), `HBO MAX` (4), `PREMIERE` (4),
`CAZÉTV` (3), `ESPN` (3), `XSPORTS` (2), `PREMIERE FC` (2), `GE TV` (2), `APPLE TV` (2),
`BANDSPORTS`, `CANAL GOAT`, `SBT`, `TNT`, `SPACE`, `SPORTV 2`, `PREMIERE 2`, `PREMIERE 3`,
`ONEFOOTBALL`.

**Qualificador** — mesmo campo, dois significados completamente diferentes:

| Uso | Exemplos | Como ler |
|---|---|---|
| Canal dentro da plataforma | `YOUTUBE (GOL BRASIL)`, `(METRÓPOLES)`, `(UOL ESPORTE)`, `(TNT SPORTS)`, `(XSPORTS)` | identifica *quem* transmite no YouTube |
| Recorte regional | `GLOBO (RJ, BA, ES, PA, SE, RN, MA)`, `GLOBO (RS, SP(BRAGAÇA))` | siglas de UF, **com parênteses aninhados** |

O aninhamento (`SP(BRAGAÇA)`) quebra regex de `\(([^)]*)\)`. Ver [field-notes.md](field-notes.md).

O ícone é sempre `hero-tv` — **não** codifica tipo de canal. O tipo vem do catálogo (§4) ou do
agrupamento na página do jogo (§2.2).

---

## 2. Página do jogo (`/aovivo/{slug}-{id}.html`)

A página canônica. É a única que **resolve as entidades**: competição, times e canais viram
links com slug.

### 2.1 JSON-LD

Quatro blocos `<script type="application/ld+json">`. O primeiro é o que interessa:

```jsonc
{ "@type": "SportsEvent",
  "name": "Internacional x Grêmio",
  "startDate": "2026-08-27T20:00:00-03:00",   // ISO com offset — o campo mais confiável
  "endDate":   "2026-08-27T22:00:00-03:00",   // sempre startDate + 2h, fixo
  "eventStatus": "https://schema.org/EventScheduled",
  "homeTeam": {"@type":"SportsTeam","name":"Internacional"},
  "awayTeam": {"@type":"SportsTeam","name":"Grêmio"},
  "competitor": [ /* os dois de novo */ ],
  "organizer": {"@type":"SportsOrganization","name":"Copa Do Brasil"},
  "location": {"@type":"Place","name":"Estádio"},   // placeholder literal, sempre igual
  "sport": "Soccer",
  "url": "…" }
```

Os outros três: `BreadcrumbList` (traz a **URL da liga com id**), `FAQPage` (frases prontas com
os canais — redundante, mas é onde a ausência de transmissão fica explícita) e `Organization`.

FAQ quando não há canal:
`"A transmissão ainda não foi confirmada. Acompanhe esta página para atualizações."`

### 2.2 Corpo

| Campo | Âncora | Notas |
|---|---|---|
| `competition` + `competition_id` | `div[role="navigation"]` > `a[href^="/liga/"]` | `/liga/copa-do-brasil-ek15w9aq8d` |
| `phase` | `<span>` seguinte | `Quartas de Final` |
| `leg` | `<span role="status">` | `Jogo 1 de 2`, só em mata-mata |
| `other_leg` | link rotulado `Ida` / `Volta` | `/aovivo/gremio-x-internacional-2fc0285afa86.html` + data `03/09` |
| `home_id` / `away_id` | `a[href^="/time/"]` | `/time/internacional-u20bwm9vcq` |
| `start_utc` | `a#jogo-add-google-calendar` | `dates=20260827T230000Z%2F20260828T010000Z` — **UTC exato**; ausente em jogos já encerrados |
| `channels[]` | `#tabpanel-onde-assistir` | ver abaixo |

**Canais, agrupados por tipo.** Cada `<section>` tem um `<h3>` com o tipo e um `<ul>` de canais:

| `<h3>` observado | Significado |
|---|---|
| `Canal com sinal aberto` | TV aberta |
| `Canal por assinatura` | TV fechada |
| `Streeming aberto` | streaming gratuito (**sim, com dois "e" — erro deles**) |
| `Streeming por assinatura` | streaming pago |

Cada item:

```html
<li><a href="/canal/youtube">
  <img src="https://static.futebolnatv.com.br/upload/channel/1573426975_youtube.png">
  <p>YOUTUBE</p>
  <p>ESPN BRASIL</p>   <!-- qualificador, SEM parênteses aqui; vazio quando não há -->
</a></li>
```

Diferença sutil e importante: na lista o qualificador vem `(ESPN BRASIL)`, na página do jogo
vem `ESPN BRASIL`. Normalizar antes de comparar.

Quando não há transmissão: `<p>Sem canais de transmissão definidos.</p>` e nenhum
`a[href^="/canal/"]`.

---

## 3. Liga e time

### `/liga/{slug}-{id}`

| Campo | Exemplo |
|---|---|
| `name` | `Copa Do Brasil` |
| `logo` | `…/upload/ligas/{40}.png` |
| `country` + bandeira | `Brasil`, `…/upload/countries/{40}.png` |
| `season` | `Temporada: 2026` |
| `season_start` / `season_end` | `17 de fev.` / `3 de set.` (PT abreviado, **sem ano**) |
| `progress` | `div[role="progressbar"][aria-valuenow]` — `97`, `69` |
| `fixtures[]` | cartões idênticos aos da lista de agenda, agrupados por `<h3>` de data |

Cabeçalhos de data nos agrupamentos: `Hoje`, `Amanhã`, `Sáb, 29/08`, `Ter, 01/09` — **sem ano**.

### `/time/{slug}-{id}`

`País: BR` (alpha-2), `Ano de Fundação: 1903`, logo, e as abas *Visão geral* (último + próximo
jogo), *Jogos* e *Resultados*.

---

## 4. Catálogo de canais

### `/canais` e `/canais?tipo=…`

Duas seções: "Com transmissão agora ou em breve" (12 canais, repetidos em todos os filtros) e
"Demais canais" agrupados por `<h3>` de tipo.

| Campo | Âncora | Notas |
|---|---|---|
| `id` (numérico) | `div[id="channel-list-logo-{N}"]` | **só na seção de destaque**; observados 345–462 |
| `slug` | `a[href="/canal/{slug}"]` | a chave usável |
| `name` | `<span>` | `ESPN 4`, `CAZÉTV`, `CULTURA (PA)` |
| `logo` | `img[src]` | `…/upload/channel/{40}.png`, ou nome legado `1573481112_band.png` |
| `description` | `<span>` seguinte | raro; só alguns canais editoriais (a da CazéTV tem um parágrafo) |
| `type` | `<h3>` do grupo / o `?tipo=` pedido | `TV aberta` (`a`), `TV fechada` (`f`), `Internet` (`internet`) |

Os nomes de arquivo de logo são de dois formatos — 40 chars aleatórios (estilo storage do
Laravel) e `{unixtime}_{nome}.png` — o que sugere um backend administrativo mais antigo por
trás do app Phoenix atual.

### `/canal/{slug}`

`name`, `logo`, `site oficial` (link externo: ESPN → `disneyplus.com`) e a programação —
próximos jogos agrupados por dia, paginada só por WebSocket.

---

## 5. Cardinalidades medidas

| | |
|---|---|
| Jogos por lista de dia | 22–26 (hoje 26, amanhã 26, ontem 22, ao vivo 13) |
| Jogos no sitemap | 201 (janela ≈ D → D+5) |
| Ligas em `/ligas` | 75 |
| Times em `/times` | 143 |
| Canais na união de `/canais?tipo=*` | 81 |
| Canais no sitemap | **100** (superconjunto estrito) |
| Canais distintos nos chips da amostra | 23 |
| Competições em um dia | 8 (hoje) / 18 (amanhã) |
