# Amostras

Respostas reais capturadas em **2026-08-21**, recortadas para servir de fixture de teste offline.
São trechos curtos — o suficiente para exercitar o parser, não para substituir a API.

| Arquivo | Origem | Por que existe |
|---|---|---|
| `api-futebol-2026-08-21.json` | `/api/futebol?data=2026-08-21` | 5 jogos escolhidos para cobrir **todos** os campos opcionais de uma vez |
| `api-nhl-2026-08-22.json` | `/api/nhl?data=2026-08-22` | as duas maiores armadilhas, num arquivo só |
| `canais-trecho.json` | `/canais.json` | 6 dos 61 canais, com a forma completa preservada |
| `competicoes-trecho.json` | `/competicoes-futebol.json` | 4 das 224 competições, incluindo o caso de `image` emoji |

## O que cada fixture exercita

**`api-futebol-2026-08-21.json`** — os 5 jogos cobrem, entre eles, os 12 campos possíveis:

- `Al-Riyadh x Al-Nassr` — `broadcast` composto (`"XSports e YouTube (GOAT)"`), com `" e "` e
  parênteses no mesmo valor, mais `youtubeUrl`
- `Cajamarca x Grau` — `broadcast` vazio + `country` presente, sem `iconEmoji`
- `Al-Hazem x Al-Diriyah` — `broadcast` vazio + `iconEmoji`, sem `country`
- `Anderlecht x PAOK` — `aggregate` (`"IDA …"`), o campo mais raro (2,2% dos jogos)
- `Ponte Preta x Avaí` — **`broadcast: "<> e Disney+"`**, o valor sujo que precisa ser filtrado

O `availableDates` foi mantido íntegro (15 datas) para testar o recorte de ±7 dias.

**`api-nhl-2026-08-22.json`** — vale mais que a documentação:

- os jogos vêm com `"sport": "futebol"` embora o endpoint seja `/api/nhl`
- `availableDates` é `[]` mesmo com 10 jogos no dia, porque nenhum tem `broadcast`

Se o seu parser passar nesses dois arquivos, ele sobrevive à API real.

**`competicoes-trecho.json`** — inclui `"Mundial de Seleções"` com `image: "🌍"` (emoji cru, não
nome de arquivo) ao lado de três entradas com `.png`. É o caso que quebra quem monta a URL do
logo por concatenação cega.

## Regenerar

Nada aqui é gerado automaticamente. Para atualizar, capture de novo e recorte à mão:

```bash
curl -s "https://futnatv.net/api/futebol?data=$(date +%F)" | python3 -m json.tool
```

Lembre que os catálogos mudam em escala de semanas — compare o campo `version` de dentro do
JSON, não a query string `?v=`, que é ignorada pelo servidor.
