# Notas de campo

Armadilhas encontradas na prática, em ordem de quanto custam se você não souber delas.

---

## 1. Sem CORS — decida a arquitetura antes de escrever código

A resposta de `/api/{esporte}` não traz **nenhum** header `Access-Control-Allow-*`. Verificado
com `Origin` explícito:

```
$ curl -sD- -o /dev/null -H "Origin: https://exemplo.com" \
    "https://futnatv.net/api/futebol?data=2026-08-23" | grep -i access-control
(nada)
```

Um `fetch()` de página web em outro domínio será bloqueado pelo navegador. Funciona em:
servidor (Node/Python/Go), CLI, cron job, worker, extensão de navegador com permissão de host,
ou por trás de um proxy seu que reinjete os headers. Não funciona: JS de uma página sua no browser.

O `OPTIONS` responder 200 **não** ajuda — ele devolve o corpo JSON inteiro em vez de um preflight
válido, então o navegador rejeita mesmo assim.

## 2. `sport` mente — e o endpoint vaza

`/api/nfl` e `/api/nhl` devolvem `"sport": "futebol"`. Se você agregar os cinco endpoints numa
tabela só e confiar no campo, futebol americano e hóquei viram futebol.

Mas carimbar pelo endpoint também não fecha: `/api/volei` devolve 3 jogos de
`"Mundial Feminino - sub-17"` — futebol, marcado `"sport": "futebol"` — junto com os 12 de vôlei.

Nenhum dos dois sinais é confiável sozinho. Se a classificação importa, cruze
endpoint + `sport` + `competition`, e assuma que vai haver exceção.

## 3. Endpoint vazio ≠ endpoint sem dados

Eu documentei `volei` como "dataset vazio" depois de varrer 30 dias a partir de 10/08 e não
achar nada. Estava errado: o vôlei tem 15 jogos em 9 datas entre **25/07 e 08/08** (Liga das
Nações masculina e feminina). Fora de janela, simplesmente.

O mesmo vale para NFL e NHL, que são sazonais por natureza. A janela que você varre determina o
que você conclui — varra largo antes de declarar um endpoint morto, e re-cheque de tempos em
tempos, porque temporada que acabou volta.

## 4. Uma chamada = um dia

Não há endpoint de intervalo. Para uma semana, são 7 requisições por esporte. Com os 5 esportes,
uma janela de 15 dias custa 75 requisições. Faça sequencial com pausa; veja
[legal-e-etiqueta.md](legal-e-etiqueta.md).

## 5. `availableDates` não lista as datas que têm jogos

O nome engana. A regra verificada é:

> datas com **pelo menos um jogo de transmissão anunciada** (`broadcast` não vazio), ∩ `[D−7, D+7]`

Duas armadilhas empilhadas:

**(a) O filtro é por transmissão, não por jogo.** A NHL devolve 7–10 jogos por dia e
`availableDates: []` em todas as datas, porque nenhum jogo de NHL tem emissora cadastrada.
O basquete tem jogos em 15 datas e aparece em 2. Quem usar o campo para decidir quais datas
buscar vai simplesmente **não ver** esses esportes.

Em futebol e NFL os dois conjuntos coincidem — quase todo dia com jogo tem transmissão — e é por
isso que a leitura errada sobrevive ao teste superficial. Teste com `basquete` ou `nhl`.

**(b) A janela acompanha a data pedida.** Nunca são mais de 15 datas, e o conteúdo muda a cada
chamada. Guardar a primeira resposta como "o calendário do site" é errado.

Para saber se uma data tem jogos, **peça a data e olhe `schedule`**. Não há atalho.
Detalhamento e tabelas em [api-reference.md](api-reference.md#availabledates--datas-com-transmissão-anunciada-não-datas-com-jogos).

## 6. Datas impossíveis não dão erro

`2026-02-30` e `2026-13-01` passam pela regex e devolvem **200 com resultado vazio** — idênticas
a uma data válida sem jogos. Se você gera datas programaticamente, valide no seu lado; a API não
vai te avisar.

## 7. Campos opcionais são omitidos, não nulos

`country`, `youtubeUrl`, `aggregate` e `iconEmoji` simplesmente não aparecem na chave. Código que
faz `game["country"]` quebra em 56% dos jogos. Sempre `.get()` / `??`.

## 8. `"-"` é o nulo de `odds`

`["-","-","-"]` em 82% dos jogos. Não é `null`, não é `""`, não é `0`. Converta com guarda.

## 9. `"int"` não é um código de país

O campo `country` mistura ISO-3166 alpha-2 (`br`, `us`, `ar`…) com o pseudo-código `int`
("internacional"), presente em 77 jogos. Qualquer biblioteca de países vai falhar nele.

## 10. `broadcast` é texto livre com lixo

- 40% vazio — significa "não anunciado", **não** "sem transmissão"
- separadores `" e "` e `", "`, podendo coexistir no mesmo valor
- `"<>"` aparece em 23 jogos como token inicial (`"<> e Disney+"`) — lixo de digitação, filtre
- variações da mesma emissora convivem (`ESPN`, `ESPN 2`, `ESPN 4`; `SporTV`, `SporTV 2`)
- o conteúdo entre parênteses é a parte mais informativa (`YouTube (CazéTV)`), não descarte

## 11. `image` dos catálogos pode ser emoji

31 das 224 competições e o `defaultImage` de `canais.json` trazem emoji cru no lugar de nome de
arquivo. Cheque se há `.` antes de montar a URL do logo.

## 12. Os `?v=` são teatro

`canais.json?v=20260722-3` e `competicoes-futebol.json?v=20260717-3` devolvem o mesmo byte-count
com `?v=1`, `?v=xxxx` ou sem parâmetro nenhum. Não são versionamento de conteúdo — são
cache-busters do site. A versão real está no campo `version` **dentro** do JSON. Se você quer
detectar mudança de catálogo, compare esse campo (ou um hash do corpo), nunca a query string.

## 13. Não existe API por time nem por competição

As 60 páginas `/time/{slug}/` e as 23 `/campeonato/{slug}/` são o mesmo SPA de 270 KB chamando
`/api/futebol`. O recorte é client-side. Filtrar por conta própria sobre a agenda completa é
mais barato do que raspar 83 páginas HTML.

## 14. O HTML não tem os dados

`window.__FUTNATV_INITIAL_SCHEDULE__` existe no código mas vem nulo em produção. Não há SSR do
schedule — baixar o HTML não substitui a chamada de API.

## 15. Fusos

Horários são de Brasília, sem indicação no payload. Combine `Day.key` + `Game.time` e localize
em `America/Sao_Paulo` para virar um instante absoluto. Um jogo de liga asiática às `06h00` BRT
já é "amanhã" no país de origem — o agrupamento por dia é o do site, não o local do evento.

---

## O que não existe (testado e negativo)

- Nenhum endpoint de resultados/placar ao vivo. `aggregate` só traz o placar do jogo de ida.
- Nenhum endpoint de classificação, elenco, estádio ou árbitro.
- Nenhum endpoint de notícias em JSON — `/news/` é HTML estático.
- Nenhum catálogo de competições fora do futebol (404 para basquete/vôlei/NFL/NHL).
- Nenhum catálogo público de times — a lista de escudos está embutida no HTML do site.
- Nenhum campo de ID estável em jogo algum. A chave natural precisa ser você que monta, algo
  como `(data, time, home, away)`. Nomes de time podem ser reescritos entre capturas, então
  reconciliação por chave composta vai ter ruído.
