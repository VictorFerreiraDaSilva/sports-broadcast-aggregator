# Fonte futebolnatv (candidata — sem adapter)

Levantamento de [www.futebolnatv.com.br](https://www.futebolnatv.com.br/) como possível segunda
fonte do agregador. **Ainda não existe adapter** — esta pasta contém só a engenharia reversa,
no lugar onde o código vai morar quando/se for implementado ([ADR 0005](../../../docs/adr/0005-source-package-layout.md)).
Nada aqui é importado por `app/`; a fonte não está no registro ([ADR 0001](../../../docs/adr/0001-explicit-source-registry.md)).

Levantado em **2026-08-27** por observação externa (requisições HTTP, leitura do HTML servido e
uma sessão no WebSocket do LiveView). Não há documentação oficial nem API pública; tudo aqui é
comportamento observado e pode mudar sem aviso.

## Índice

| Documento | Conteúdo |
|---|---|
| [docs/site-reference.md](docs/site-reference.md) | Todas as rotas, parâmetros, códigos de erro, o WebSocket do LiveView, custos e limites |
| [docs/schemas.md](docs/schemas.md) | Que campo sai de que página, com seletores e domínios de valores reais |
| [docs/field-notes.md](docs/field-notes.md) | Armadilhas, dados sujos e decisões de parsing |
| [docs/coverage-vs-futnatv.md](docs/coverage-vs-futnatv.md) | Comparação medida contra a fonte que já temos |
| [docs/legal-and-etiquette.md](docs/legal-and-etiquette.md) | robots.txt, termos de uso e etiqueta de coleta |

## A fonte real: não existe API

A pergunta que motivou o levantamento — "onde está o JSON?" — tem uma resposta negativa firme.

O site é uma aplicação **Phoenix LiveView 1.1.28** (Elixir), atrás de Cloudflare, operada por
*Sinc Lda* (rodapé, `© 2018–2026`). A página chega **renderizada no servidor**, completa, no
primeiro GET. Não há endpoint JSON, e não há como fabricar um:

- `/api`, `/api/`, `/api/v1`, `/api/games`, `/api/jogos`, `/jogos-hoje.json` → todos **404**.
- Não existe host de API: `api.`, `app.`, `data.`, `cdn.`, `m.`, `mobile.`, `ws.`
  `futebolnatv.com.br` são **NXDOMAIN**. O certificado cobre só `futebolnatv.com.br` e
  `*.futebolnatv.com.br`, e o único subdomínio vivo é `static.` (imagens).
- Os únicos literais de rota no bundle JS (`/assets/js/app-*.js`, 150 KB) são `"/live"` (o
  socket) e `"/prefs/exi/"` (preferência de exibição). Nenhuma chamada `fetch` de dados.
- Query params são **ignorados** nas páginas de agenda: `/jogos-hoje?data=2026-08-30`,
  `?date=`, `?dia=` devolvem exatamente a mesma página de hoje. Não há como pedir uma data
  arbitrária por URL.

O que existe além do HTML é o **WebSocket do LiveView** em `wss://.../live/websocket`
(`/live/websocket` responde 400 a um GET normal — espera upgrade). Ele não serve JSON de
domínio: serve *diffs de HTML* do Phoenix. Vale por um motivo só — é o único jeito de
**paginar** as listas que não têm paginação por URL. Protocolo e cliente mínimo em
[docs/site-reference.md](docs/site-reference.md#4-o-websocket-do-liveview).

Ou seja: a fonte real é o **HTML servido**, e a extração é scraping — não consumo de API.
Isso é uma diferença de natureza em relação ao futnatv, que expõe `/api/{esporte}?data=…`.

## Onde o site tira os dados

Não há como confirmar de fora, mas as evidências apontam para **duas origens distintas**, e a
distinção importa porque só uma delas é o diferencial da fonte:

1. **Jogos, times, ligas, placares e minuto ao vivo vêm de um feed esportivo externo.** Os
   rótulos de fase chegam em inglês não traduzido no meio da prosa em português
   (`Round of 64`, `Playoff round`, ao lado de `Rodada  1` e `Mata-mata`); os nomes de time são
   a grafia internacional (`SC Freiburg`, `Gornik Zabrze`, `Mjallby AIF`, `Vikingur Reykjavik`);
   times têm `Ano de Fundação` e país; ligas têm temporada com data de início e fim e barra de
   progresso. Isso é o formato típico de API de fixtures global, não de redação brasileira.
2. **A transmissão é editorial e é o produto deles.** Canais com id numérico próprio,
   logo hospedado, descrição escrita à mão (a da CazéTV tem um parágrafo), página de
   profissionais (narradores/comentaristas), recorte regional da Globo por estado, e o nome do
   canal do YouTube entre parênteses. Nada disso sai de feed global — é catalogação manual.

O `embed.onefootball.com/inline/futebol-na-tv.js` carregado nas páginas é o widget de vídeo
Dugout/OneFootball (`window.dugout_*`), **não** é fonte de agenda. Já `PPV ONEFOOTBALL` e
`ONEFOOTBALL` aparecem como *canais* — é a OneFootball vendendo PPV, coisa diferente.

## TL;DR das rotas

```
/jogos-hoje  /jogos-amanha  /jogos-ontem  /jogos-aovivo   # agenda: 1 dia por página, sem parâmetro de data
/aovivo/{home}-x-{away}-{id}.html                         # jogo: a página canônica, com JSON-LD
/canal/{slug}   /canal/{slug}/direitos  /canal/{slug}/profissionais
/liga/{slug}-{id}   /liga/{slug}-{id}/resultados  /liga/{slug}-{id}/direitos
/time/{slug}-{id}   /time/{slug}-{id}/jogos       /time/{slug}-{id}/resultados
/canais?tipo=a|f|internet   /ligas?pagina=N   /times?pagina=N   # catálogos
/site-map.xml                                             # o melhor índice de descoberta
```

## Os cinco achados que mais importam

1. **As listas de agenda só mostram jogos com transmissão anunciada.** Em 4 páginas medidas
   (`hoje`, `amanha`, `ontem`, `aovivo`), **100 % dos jogos listados tinham pelo menos um canal**
   — 26/26, 26/26, 22/22, 13/13. E há prova pelo contrapositivo: `Uruguai Sub-20 x Paraguai
   Sub-20`, hoje às 15:00, existe (página própria, `"Sem canais de transmissão definidos."`) e
   **não aparece** em `/jogos-hoje` nem no sitemap. Para o nosso caso de uso isso é uma
   vantagem, não um bug: a lista já vem filtrada pelo que nos interessa. Mas significa que a
   fonte **não serve** para "todos os jogos do dia".

2. **`broadcast` já vem estruturado, um canal por vez — e resolvido para uma entidade.** O
   futnatv devolve `"Globo (RS, SP) e SporTV"` como uma string só, que precisamos quebrar e
   casar contra catálogo. Aqui cada canal é um chip separado com **nome** e um **qualificador**
   opcional entre parênteses; e na página do jogo cada um é um link `/canal/{slug}`. O
   casamento nome→canal que o `catalogs.py` do futnatv faz por alias e por família
   (`ESPN 4`→`ESPN`) **não é necessário** — o site entrega a chave estrangeira.

3. **O `/site-map.xml` é o melhor índice de descoberta, e é uma requisição só.** 325 URLs,
   `lastmod` de hora em hora: 201 jogos (janela ≈ hoje → hoje+5; confirmado 01/09 dentro,
   02/09 fora), **100 canais**, 10 times, 9 ligas. Cobre `hoje` e `amanha` inteiros (26+26,
   interseção total) e mais 149 jogos que as listas de dia não alcançam.

4. **Nenhum catálogo do site é completo — nem o de canais.** `/canais` sem filtro é idêntico a
   `/canais?tipo=a` (renderiza só o grupo "TV aberta" — bug deles). A união dos três filtros dá
   **81 canais**; o sitemap tem **100**, superconjunto estrito, e os 19 a mais incluem
   `prime-video`, `ppv-onefootball`, `youtube`, `twitch`, `xsports` — canais que aparecem em
   jogos de hoje. Nunca tratar `/canais` como universo fechado.

5. **Só futebol, e o horizonte de transmissão é curto.** Não há basquete/NFL/NHL como no
   futnatv — é um guia de futebol e nada mais. Fixtures vão longe (a página do time alcança
   dezembro), mas a transmissão anunciada acaba em ~2–3 semanas: para o Grêmio, 4 dos 10
   próximos jogos têm canal (até 13/09) e os 6 seguintes vêm com `—`.

## Se virar adapter

Esboço, não decisão. O caminho barato é `/site-map.xml` (1 req) → `/aovivo/{slug}.html` por
jogo (~13 KB gzip, ~250 ms), o que dá ~200 requisições para a janela inteira e entrega, por
jogo: início exato em UTC, competição e times **resolvidos por link**, canais **resolvidos por
slug** com tipo (aberto/assinatura × TV/streaming), e ida/volta de mata-mata. As listas de dia
custam 1 requisição e dão quase tudo, menos os slugs de canal/time/liga.

Compatibilidade com o core: os `game.source_data` opacos ([ADR 0006](../../../docs/adr/0006-core-schema-plus-source-data-jsonb.md))
acomodam bem o que é específico daqui (id do jogo, slugs, recorte regional, placar ao vivo,
minuto). Catálogo escopado por `source_code="futebolnatv"` ([ADR 0003](../../../docs/adr/0003-canonical-sport-source-scoped-catalogs.md))
continua valendo — os canais daqui têm slug próprio e não devem ser fundidos com os do futnatv
([ADR 0002](../../../docs/adr/0002-source-scoped-games-no-cross-source-merge.md)).

O bloqueio não é técnico, é o de [docs/legal-and-etiquette.md](docs/legal-and-etiquette.md):
os termos de uso desta fonte são bem mais restritivos que os do futnatv. Ler antes de escrever
código.
