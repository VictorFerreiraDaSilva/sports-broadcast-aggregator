# Schemas

Todos os domínios de valores abaixo foram medidos sobre uma amostra real de **891 jogos**
(30 dias × 5 esportes, capturados em 2026-08-21). Percentuais são dessa amostra.

---

## Resposta de `/api/{esporte}`

```jsonc
{
  "schedule": [ Day ],        // 0 ou 1 elemento
  "availableDates": [ "YYYY-MM-DD" ]
}
```

> `availableDates` **não** lista as datas que têm jogos. São as datas com pelo menos um jogo de
> transmissão anunciada, recortadas em `[D−7, D+7]`. Regra completa e tabelas em
> [api-reference.md](api-reference.md#availabledates--datas-com-transmissão-anunciada-não-datas-com-jogos).

### `Day`

| Campo | Tipo | Sempre? | Exemplo | Notas |
|---|---|---|---|---|
| `key` | string | sim | `"2026-08-21"` | ISO. Igual ao `data` pedido. **Único campo confiável para data.** |
| `day` | string | sim | `"21"` | dia com zero à esquerda, **como string** |
| `month` | string | sim | `"AGO"` | mês abreviado em PT-BR, caixa alta |
| `weekday` | string | sim | `"SEX"` | `DOM` `SEG` `TER` `QUA` `QUI` `SEX` `SAB` (sem acento em `SAB`) |
| `title` | string | sim | `"SEXTA, 21 DE AGOSTO DE 2026"` | rótulo pronto, com acento (`SÁBADO`) |
| `games` | array | sim | | ordenado por horário crescente |

`day`/`month`/`weekday`/`title` são derivados de `key` — são conveniência de renderização.
Prefira parsear `key` a reverter as abreviações em português.

### `Game`

| Campo | Tipo | Presença | Domínio observado |
|---|---|---|---|
| `sport` | string | 100% | `"futebol"`, `"basquete"`, `"volei"` — **não corresponde ao endpoint**, veja o alerta abaixo |
| `time` | string | 100% | `"HHhMM"`, sempre 5 chars, de `00h00` a `23h45`. Fuso de Brasília (BRT). Zero exceções de formato na amostra. |
| `competition` | string | 100% | texto livre, ex. `"Campeonato Saudita"`, `"Copa da Alemanha"` |
| `round` | string | 100% | texto livre, **`""` em 26%**. 52 valores distintos. |
| `home` | string | 100% | nome do mandante |
| `away` | string | 100% | nome do visitante |
| `broadcast` | string | 100% | texto livre, **`""` em 40%** |
| `odds` | array[3] string | 100% | sempre exatamente 3 elementos |
| `iconEmoji` | string | 58,5% | `⚽` `🏀` `🌍` `🤝` |
| `country` | string | 44,2% | ISO-3166 alpha-2 minúsculo + o pseudo-código `int` |
| `youtubeUrl` | string | 18,9% | URL `watch?v=` |
| `aggregate` | string | 2,2% | placar do jogo de ida |

> **`sport` não é o esporte, e o endpoint também não é garantia.** Duas falhas independentes:
>
> 1. `/api/nfl` e `/api/nhl` devolvem jogos marcados `"sport": "futebol"`. Na amostra de 891
>    jogos: 849 `futebol` contra 42 `basquete` — os 79 jogos de NFL/NHL estão embutidos nos 849.
> 2. `/api/volei` devolve **3 jogos de futebol** (`"Mundial Feminino - sub-17"`, com
>    `"sport": "futebol"`) misturados aos 12 de vôlei. O endpoint vaza conteúdo de outro esporte.
>
> Na prática: o endpoint é o melhor sinal disponível, mas nenhum dos dois é confiável sozinho.
> Se a distinção importar para você, cruze endpoint + `sport` + `competition` — e espere exceções.

#### Campos que só aparecem em alguns endpoints

| Endpoint | Campos possíveis |
|---|---|
| `futebol` | todos os 12 |
| `nfl` | os 8 obrigatórios + `iconEmoji`, `youtubeUrl` |
| `basquete` | os 8 obrigatórios + `iconEmoji` |
| `nhl` | os 8 obrigatórios + `iconEmoji` |
| `volei` | os 8 obrigatórios + `iconEmoji`, `country` |

Essa tabela vale para a amostra medida, não é contrato. `volei` aparentava não ter campo nenhum
até a varredura alcançar julho — a ausência de um campo pode ser só ausência de dados na janela
que você olhou.

Os campos opcionais são **omitidos**, não vêm `null`. Sempre acesse com default
(`game.get("country")`, `game.country ?? null`).

#### `time`

`"13h45"`, não `"13:45"`. Para converter:

```python
h, m = game["time"].split("h")          # sempre 2+2 dígitos
```

O horário é o de Brasília, o mesmo mostrado no site. A API não devolve fuso, offset nem
timestamp — combine com `Day.key` e assuma `America/Sao_Paulo` para obter um instante absoluto.

#### `odds`

Sempre uma lista de 3 strings, na ordem **[casa, empate, fora]**, em formato decimal europeu:

```json
"odds": ["1.66", "4.00", "4.50"]
"odds": ["-", "-", "-"]      // sem cotação — 82% dos jogos
```

O sentinela de ausência é a string `"-"`, não `null` nem `""`. Trate `"-"` antes de converter
para float. Em esportes sem empate a posição do meio continua existindo.

#### `country`

Código de país minúsculo, usado pelo site para montar `https://flagcdn.com/w40/{country}.png`.
Observados: `br` (166), `int` (77), `us` (58), `uy` (26), `ar` (25), `mx` (13), `cn` (12),
`pe` (10), `jp` (7).

`int` **não é ISO** — é o pseudo-código do site para competição internacional. Trate como
exceção antes de mandar para qualquer biblioteca de países.

`country` e `iconEmoji` são mutuamente quase exclusivos: o site usa a bandeira quando há
`country`, e o emoji caso contrário. Por isso `iconEmoji` está ausente em 41,5% dos jogos —
ausência não significa "sem ícone", significa "use a bandeira".

#### `iconEmoji`

| Valor | Ocorrências | Significado |
|---|---|---|
| `⚽` | 443 | futebol genérico |
| `🏀` | 42 | basquete |
| `🌍` | 24 | competição mundial/intercontinental |
| `🤝` | 12 | amistoso |

#### `youtubeUrl`

`https://www.youtube.com/watch?v={ID}` em 151 dos 168 casos. Os outros 17 trazem
parâmetros extras colados (`&pp=…`). **Extraia o `v=` por query-parsing**, não por regex de
sufixo, ou você vai capturar o `pp` junto.

Quando `youtubeUrl` existe, o `broadcast` normalmente também menciona YouTube — mas os dois
campos são independentes e podem divergir.

#### `aggregate`

Formato `"IDA {casa}x{fora}"` — o placar do jogo de ida, para partidas de volta em mata-mata.
Valores na amostra: `IDA 1x1`, `IDA 0x0`, `IDA 1x0`, `IDA 1x6`, `IDA 0x1`, `IDA 2x1`, `IDA 1x3`,
`IDA 1x2`. Só aparece em `futebol`, e apenas em 20 dos 891 jogos.

Cuidado: o placar é sempre do ponto de vista **mandante-do-jogo-de-volta**? Não dá para afirmar
pela amostra — 20 casos é pouco. Se for usar, valide contra um jogo conhecido antes.

#### `broadcast` — o campo que interessa

String livre, editada à mão. É onde está a informação de "onde passa". Regras extraídas de 539
valores não vazios (60 emissoras distintas após tokenizar):

**Separadores.** Múltiplas emissoras aparecem separadas por `" e "` (171 jogos) e, em menor
escala, `", "` (29 jogos). Um valor pode combinar os dois:

```
"ESPN 4 e Disney+"
"SporTV, Premiere e Globo"
"SportyNet e YouTube (SportyNet)"
```

Split recomendado: `re.split(r"\s+e\s+|,\s*", broadcast)`.

**Parênteses** (239 jogos) qualificam a plataforma com o canal/produtora específico:

```
"YouTube (CazéTV)"          → plataforma YouTube, canal CazéTV
"DAZN (NFL Game Pass)"      → plataforma DAZN, produto NFL Game Pass
```

Guarde os dois níveis: `"YouTube"` é a plataforma, o parêntese é a entidade que transmite.
Descartar o parêntese perde a informação mais útil do campo.

**Emissoras mais frequentes** (após split): Disney+ (187), Apple TV (54), YouTube/SportyNet (49),
YouTube/CazéTV (48), Premiere (33), ESPN (32), DAZN NFL Game Pass (30), YouTube/GOAT (28),
SportyNet (27), ESPN 4 (25).

**`""` significa "não anunciado", não "não transmitido".** 40% dos jogos — sobretudo ligas
estrangeiras menores. Não renderize como "sem transmissão".

**Valor sujo conhecido: `"<>"`** — aparece em 23 jogos, sempre como primeiro token
(`"<> e Disney+"`), em Brasileirão Série B, Campeonato Inglês e Campeonato Italiano.
Não é um placeholder do JS do site — é lixo de digitação no cadastro. Filtre.

---

## `canais.json`

```jsonc
{
  "version": "2026-08-10",
  "defaultImage": "📺",
  "categoryOrder": [ "Abertos", "Fechados", "PAY-PER-VIEW",
                     "Streaming pago", "Streaming gratuito", "YouTube", "Outros" ],
  "channels": [ Channel ]
}
```

`categoryOrder` define a ordem de exibição das seções — inclui `"Outros"`, que **não é usado por
nenhum canal** na captura (é a categoria de escape para nomes não catalogados).

### `Channel` (61 itens)

| Campo | Presença | Exemplo | Notas |
|---|---|---|---|
| `priority` | 100% | `1` | ordem dentro da categoria. **Não é único nem sequencial** — não use como ID. |
| `name` | 100% | `"TV Brasil"` | chave de casamento com `broadcast`. É o identificador de fato. |
| `category` | 100% | `"Abertos"` | um dos 6 valores realmente usados |
| `color` | 100% | `"Padrão"` | `Padrão` (32), `Azul` (15), `Vermelho` (14) — tema claro |
| `darkColor` | 100% | `"Padrão"` | idem, tema escuro |
| `image` | 100% | `"TV Brasil.svg"` | 49 `.svg`, 12 `.png` |
| `aliases` | 28% | `["TVE BA", "TVE-BA"]` | grafias alternativas |
| `darkImage` | 26% | `"TV Brasil_n.svg"` | ausente ⇒ use `image` |
| `selectedImage` | 15% | `"Globo_c.svg"` | ausente ⇒ use `image` |

Distribuição por categoria: Abertos 16, Fechados 14, Streaming pago 14, YouTube 12,
Streaming gratuito 3, PAY-PER-VIEW 2.

---

## `competicoes-futebol.json`

```jsonc
{
  "sport": "futebol",
  "version": "2026-07-19",
  "categoryOrder": [ /* 14 categorias */ ],
  "competitions": [ Competition ]
}
```

`categoryOrder`: `Destaques`, `Eliminatórias`, `Brasil`, `Regionais`, `Estaduais`, `Europa`,
`América do Sul`, `América do Norte`, `Ásia`, `Outros estaduais`, `Feminino`,
`Eliminatórias Feminina`, `Base`, `Outros`.

### `Competition` (224 itens)

| Campo | Presença | Exemplo | Notas |
|---|---|---|---|
| `priority` | 100% | `7` | ordem de exibição |
| `name` | 100% | `"Libertadores"` | chave de casamento com `competition` |
| `category` | 100% | `"Destaques"` | uma das 14 |
| `image` | 100% | `"Libertadores.png"` **ou** `"🌍"` | **pode ser um emoji cru** — veja abaixo |
| `aliases` | 9% | `["Copa Libertadores"]` | grafias alternativas, inclusive erros de digitação assumidos (`"Internacontinental FIFA"`) |
| `darkImage` | 4% | `"UEFA Champions League_n.png"` | |
| `selectedImage` | 0,4% | `"Caribbean Cup_c.png"` | 1 único caso |

> **`image` é polimórfico.** Dos 224 itens: 139 `.png`, 54 `.svg` e **31 emojis crus**
> (`"🌍"`, etc.). Teste se a string contém `.` antes de montar uma URL — senão você vai pedir
> `/logo campeonatos/🌍` e tomar 404. Mesma regra vale para `defaultImage: "📺"` em `canais.json`.

Distribuição por categoria: Europa 40, Base 35, Destaques 28, Feminino 26, Outros 21,
Outros estaduais 16, Estaduais 11, América do Sul 9, Eliminatórias 8, América do Norte 8,
Ásia 8, Brasil 6, Regionais 5, Eliminatórias Feminina 3.

---

## Casamento entre agenda e catálogos

A agenda só tem strings. Para chegar aos logos e ao agrupamento do site:

```
game.competition ──match──> competicoes-futebol.json[].name ou .aliases[]
game.broadcast   ──split e match──> canais.json[].name ou .aliases[]
game.home/away   ──normalizar──> /logo times/{Nome sem acento}.svg
```

Ordem de resolução recomendada, na mesma lógica que o site usa:

1. Monte um índice `nome_normalizado → item` incluindo **`name` e todos os `aliases`**.
   Normalize com trim + casefold; sem isso o índice erra em variação de caixa.
2. Para `broadcast`, faça o split por `" e "` / `", "` **antes** de casar, e case cada token.
3. Um token com parêntese (`"YouTube (CazéTV)"`) pode não estar no catálogo inteiro. O site
   agrupa por "família" — reduz `ESPN 2`/`ESPN 4` a `ESPN`, `SporTV 2` a `SporTV`, `YT` a
   `YouTube` — antes de tentar de novo. Replique isso se quiser cobertura alta.
4. Sem match: use `defaultImage` (`"📺"`) e categoria `"Outros"`.

Esse casamento é **frouxo por natureza** — `competition` e `broadcast` são digitados à mão e o
catálogo só é atualizado depois. Espere e trate o miss: nomes novos aparecem na agenda antes de
entrarem no catálogo.
