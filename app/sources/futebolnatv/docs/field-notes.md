# Notas de campo

Armadilhas e dados sujos observados em 2026-08-27. Ordenado por quanto estrago causa se
passar despercebido.

---

## 1. A lista de agenda é filtrada por transmissão anunciada

**Se você tratar `/jogos-hoje` como "os jogos de hoje", vai estar errado.** É "os jogos de hoje
que já têm canal anunciado".

Evidência direta, dos dois lados:

- Em quatro páginas, **todo** jogo listado tinha pelo menos um chip de canal: `hoje` 26/26,
  `amanha` 26/26, `ontem` 22/22, `aovivo` 13/13.
- Varrendo 22 páginas de liga atrás de jogos de hoje/amanhã **sem** canal, apareceu exatamente
  um: `Uruguai Sub-20 x Paraguai Sub-20`, hoje às 15:00
  (`/aovivo/uruguai-sub-20-x-paraguai-sub-20-14565b85687c.html`, `Amistosos Seleções`). A
  página dele existe, diz `"Sem canais de transmissão definidos."` e o FAQ diz
  `"A transmissão ainda não foi confirmada."` **Ele não está em `/jogos-hoje` nem no
  `/site-map.xml`.**

Para o nosso agregador isso é conveniente — é exatamente o recorte que interessa. Mas mude a
expectativa: a fonte responde "onde assistir", não "o que vai acontecer". Jogos sem
transmissão só aparecem por `/liga/…` e `/time/…`.

Compare com o futnatv, onde o análogo é o `availableDates` — lá o filtro por transmissão vaza
num campo mal nomeado; aqui ele é a própria definição da lista.

## 2. Query param de data é aceito e ignorado — silenciosamente

`/jogos-hoje?data=2026-08-30` responde **200** com a página de hoje, byte a byte. Idem
`?date=` e `?dia=`. Um coletor que "varra 30 datas" vai fazer 30 requisições bem-sucedidas e
gravar 30 cópias de hoje, sem um único erro para avisar.

Não existe consulta por data. O horizonte por URL é D−1…D+1; além disso, sitemap, liga, time
ou canal.

## 3. URL de jogo errada devolve 302, não 404

Slug errado, id errado, id sem slug, slug sem id — tudo responde **302 → `/jogos-hoje`**.
Quem seguir redirect por padrão (`curl -L`, `requests` com `allow_redirects=True`) recebe 200
com a página de agenda e pode achar que parseou um jogo. Tratar `302` como "não existe" e
**não** seguir redirect.

A chave é a URL inteira (`{home}-x-{away}-{id}.html`), não o id.

## 4. Nenhum catálogo do site é completo

- `/canais` **sem filtro é idêntico a `/canais?tipo=a`** — renderiza só o grupo "TV aberta".
  É bug deles. Para o catálogo é obrigatório fazer as três requisições (`a`, `f`, `internet`)
  e unir → 81 canais.
- E 81 ainda não é tudo: o `/site-map.xml` lista **100**, superconjunto estrito. Faltam nos
  catálogos, entre outros, **`prime-video`** e **`ppv-onefootball`** — dois dos canais mais
  frequentes nos jogos de hoje, e `youtube`, `twitch`, `xsports`, `twitter`, `pluto-tv`.
- Os 12 canais "com transmissão agora ou em breve" repetem em todos os filtros; deduplicar.
- O id numérico (`channel-list-logo-451`) só aparece na seção de destaque. O identificador
  utilizável em todo lugar é o **slug**.

Regra: descobrir canal pelo sitemap **e** pelos links `/canal/{slug}` das páginas de jogo;
usar `/canais?tipo=*` só para saber o **tipo**.

## 5. O qualificador entre parênteses tem parênteses aninhados

`GLOBO (RS, SP(BRAGAÇA))`.

`\(([^)]*)\)` captura `RS, SP(BRAGAÇA` e deixa lixo. Ou casar parênteses balanceados, ou —
melhor — **não parsear**: na lista o qualificador já vem num `<span>` próprio, separado do
nome. Pegar o nó, não a string concatenada.

E o mesmo campo carrega duas semânticas: `YOUTUBE (GOL BRASIL)` é *qual canal do YouTube*;
`GLOBO (RS, SP(BRAGAÇA))` é *em quais praças*. Decidir se viram campos diferentes no
`source_data` — não dá para inferir pelo formato, só pelo canal.

## 6. O mesmo campo muda de forma entre a lista e a página do jogo

Na lista: `(ESPN BRASIL)`, com parênteses, num `<span>`.
Na página do jogo: `ESPN BRASIL`, sem parênteses, num `<p>`.

Se as duas rotas alimentarem o mesmo campo, normalizar (tirar parênteses externos, `strip`)
antes de comparar ou deduplicar.

## 7. Datas sem ano e datas relativas

Os agrupamentos de liga/time/canal usam `Hoje`, `Amanhã`, `Sáb, 29/08`, `Ter, 01/09` — **sem
ano**. Uma coleta que atravesse 31/12 vai atribuir o ano errado, e `Hoje`/`Amanhã` dependem do
fuso do servidor.

Na página de liga, a temporada vem como `17 de fev.` / `3 de set.`, também sem ano.

**Fonte confiável de data:** o `startDate` do JSON-LD da página do jogo
(`2026-08-27T20:00:00-03:00`, ISO com offset) e o link do Google Agenda
(`dates=20260827T230000Z/…`, UTC explícito). Nas listas há só `HH:MM` em horário de Brasília —
correto na maior parte do ano, mas é conversão implícita, não dado.

## 8. `endDate` e `location` do JSON-LD são fabricados

`endDate` é **sempre** `startDate + 2h` (o próprio link de calendário diz
`"Duração estimada: 2h"`). Não é fim real de jogo.

`location` é sempre `{"@type":"Place","name":"Estádio"}` — a palavra "Estádio", literal, em
todos os jogos. Não existe estádio nesta fonte.

O link do Google Agenda **não existe** em jogos já encerrados; só em jogos futuros.

## 9. `FIM DE` e `JOGO` são dois elementos

O rótulo de jogo encerrado vem partido em dois `<span>` irmãos (`FIM DE`, `JOGO`) por causa da
quebra de linha do layout. Extração ingênua de `<span>` produz dois campos com metade da
palavra cada. Concatenar com espaço.

Do status ao vivo só foi observado o minuto (`17'`, `62'`, `77'`). `INTERVALO`,
`PRORROGAÇÃO`, `PÊNALTIS`, `ADIADO`, `CANCELADO` **não apareceram** na amostra — o que não
prova que não existam. Tratar o status como texto livre com um caso conhecido, não como enum
fechado.

## 10. Anúncios usam o mesmo padrão de id dos cartões

`#fntv-hr-{n}` numera cartões **e** blocos de anúncio na mesma sequência — a cada ~5 jogos
entra um sem `<a href="/aovivo/">`. Na home de hoje: 32 blocos, 26 jogos, 6 anúncios.
Filtrar por presença do link, nunca contar ids.

## 11. Cada jogo aparece três vezes na mesma página

Destaques (`#fntv-dc-{n}`), lista por hora (`#fntv-hr-{n}`) e bloco de texto por competição —
todos com `href` para o mesmo jogo. Na home: 84 ocorrências de `/aovivo/`, 26 jogos. Deduplicar
pela URL antes de qualquer contagem.

## 12. Nomes de fase vêm meio traduzidos

No mesmo dia: `Rodada  1`, `Round of 64`, `Playoff round`, `Mata-mata`, `Quartas de Final`,
`Rodada  25`. Português e inglês misturados, e `Rodada` vem com **dois espaços** antes do
número. É sinal de feed externo traduzido por cima só em parte. Tratar como texto livre e
normalizar espaço em branco.

## 13. Times aparecem só por nome nas listas

Nas listas, o time é `img[alt="Grêmio"]` — nome de exibição, sem id. O `/time/{slug}-{id}` só
existe na página do jogo. Reconciliação por nome tem o mesmo ruído do futnatv, com o agravante
de a grafia ser internacional (`SC Freiburg`, `Mjallby AIF`, `Vikingur Reykjavik`,
`FC ST. Gallen`) e às vezes inconsistente com a do futnatv para o mesmo time
(`Freiburg` × `SC Freiburg`, `M. Tel Aviv` × `Hapoel Tel Aviv`).

Idem competição: nas listas é texto; o `/liga/{slug}-{id}` só na página do jogo. Se os ids
importarem, o custo é uma requisição por jogo.

## 14. O logo da competição pode ser a bandeira do país

Quando a liga não tem logo próprio, o `<img>` do cabeçalho do cartão aponta para
`…/upload/countries/{hash}.png` em vez de `…/upload/ligas/{hash}.png`. É o caso de toda
competição brasileira (Brasileirão, Copa do Brasil). Se for cachear logo de competição,
checar o caminho — senão dez competições diferentes ficam com a mesma bandeira.

## 15. Formato do id do jogo não é uma coisa só

10, 12 ou 13 dígitos hex na mesma amostra. E há blocos com prefixo comum:
`696cf338ef1c6`, `696cf3385c4e3`, `696cf339094e0`, `696cf33d2be46` — todos jogos do
Brasileirão, provavelmente inseridos na mesma carga. Não assumir largura fixa, não tentar
decodificar, não derivar ordem cronológica do valor.

## 16. Horizonte de transmissão decai, e não é uniforme

Fixtures vão longe (a página do Grêmio alcança 02/12). Transmissão, não: dos 10 próximos jogos
do Grêmio, **4 têm canal** (até 13/09) e 6 vêm com `—`. Por outro lado, a rodada 25 do
Brasileirão (29–31/08) já está com canal completo, e a Copa do Brasil tem canal até 03/09.

Ou seja: o anúncio de transmissão chega por competição e por rodada, não por janela de dias
fixa. Uma coleta que só olhe D−1…D+1 perde pouco; uma que queira "tudo que já se sabe" precisa
varrer ligas.

## 17. As classes CSS não são API

Todo o HTML é Tailwind gerado inline. Já apareceram duas variantes do mesmo cartão neste
levantamento, e um seletor por classe deu falso negativo (jogos do Brasileirão pareceram estar
sem canal quando tinham). **Ancorar em `id`, `role`, `aria-*` e `<time>`.** Se precisar de
classe, usar só a marca semântica `hero-tv` (presença de chip de canal), não a lista inteira.

## 18. O WebSocket exige tokens frescos

`data-phx-session` e `data-phx-static` são assinados e casados com o cookie
`_futebolnatv_key` **daquela** resposta. Não dá para guardar; cada sessão de paginação começa
por um GET da página. Se `phx_join` falhar, quase sempre é token/cookie de origens diferentes.

## 19. Cuidado com o nome: "futnatv" é como *eles* se chamam

O `<meta name="keywords">` deste site inclui `futnatv`, e os títulos de página terminam em
`| FutebolnaTV`. É a abreviação **deles** — e colide de frente com o `source_code = "futnatv"`
que já usamos para `futnatv.net`, que é **outro site**. Se esta fonte virar adapter, usar
`futebolnatv` e nunca abreviar em log, config ou nome de coluna.

## 20. Sem CORS não é o problema; sem histórico é

Não testei CORS porque não há endpoint de dados para chamar do browser. O que importa aqui é
que **não existe arquivo**: `/jogos-ontem` é a única janela para trás, e some no dia seguinte.
Quem quiser série histórica precisa capturar todo dia — a fonte não devolve o passado.
