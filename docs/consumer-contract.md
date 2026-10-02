# Contrato com o consumidor

O agregador não decide o que é relevante para ninguém, não monta mensagem e não envia nada
([ADR 0009](adr/0009-personal-relevance-stays-out.md)). O contrato com quem consome é o próprio
banco. Este documento descreve o que ele oferece e o que fica do outro lado — hoje, um fluxo n8n
que manda a grade do dia no Telegram.

Nada aqui é código deste repositório. É a fronteira, escrita para não ser redescoberta.

## O que o agregador entrega

Uma linha de `game` por jogo **por fonte que o relatou** (ADR 0002), com o trabalho pesado já
feito:

| Campo | Por que interessa ao consumidor |
|---|---|
| `kickoff_at` | instante absoluto, já resolvido de `game_date` + `time_raw` em Brasília |
| `has_broadcast` | coluna computada; `broadcast_raw <> ''` |
| `tier` | `professional` / `youth` / `unknown` — dispensa adivinhar o que é base |
| `gender` | `men` / `women` / `unknown` |
| `competition_text`, `home_text`, `away_text` | o texto como a fonte escreveu |
| `competition_id`, `home_team_id`, `away_team_id` | casados contra os catálogos da fonte; podem ser `NULL` |
| `game_broadcast` | `broadcast_raw` já quebrado em tokens e casado contra `channel` |

A grade do dia, pronta para formatar:

```sql
SELECT g.competition_text,
       g.home_text,
       g.away_text,
       to_char(g.kickoff_at AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI') AS horario,
       string_agg(DISTINCT b.raw_token, ', ') AS canais
FROM game g
LEFT JOIN game_broadcast b ON b.game_id = g.id
WHERE g.source_code = 'futnatv'
  AND g.game_date = current_date
  AND g.has_broadcast
  AND g.tier <> 'youth'          -- <> e não = 'professional': unknown ainda é jogo de gente grande
GROUP BY g.id, g.competition_text, g.home_text, g.away_text, g.kickoff_at
ORDER BY g.kickoff_at;
```

Duas coisas a notar nessa query:

- **`tier <> 'youth'`, não `tier = 'professional'`.** `unknown` significa "nenhuma regra
  disparou", não "é de base". Excluí-lo esconderia competição nova, que é justamente onde estão
  os jogos que ainda não entraram em catálogo nenhum.
- **`source_code` fixo.** Somar fontes conta o mesmo jogo duas vezes (ADR 0002). Quando houver
  uma segunda fonte, escolha uma como principal ou deduplique explicitamente no consumidor — o
  agregador não faz isso por você.

## O que fica do lado do consumidor

**As preferências**, numa planilha do Google, lida pelo nó nativo de Sheets do n8n. Formato que
o fluxo antigo usava, e que continua servindo:

| coluna | valores | |
|---|---|---|
| `category` | `team` / `competition` / `blacklist` | o que a linha significa |
| `term` | texto livre | `Palmeiras`, `Libertadores`, `Campeonato Peruano` |

**O casamento entre preferência e jogo.** Aqui mora a única armadilha conhecida: casar time por
`ILIKE '%' || term || '%'` faz `Atlético` casar com `Atlético Madrid`. Time precisa de casamento
por palavra inteira sobre o nome normalizado (sem acento, minúsculas); competição pode ser
frouxo, porque o nome é mais estável.

**A formatação e o envio.** Se um LLM montar a mensagem, ele deve receber só a lista de jogos e
formatar — sem inventar contexto de tabela, classificação ou fase de torneio, que não estão em
lugar nenhum deste banco.

## Por que a fronteira é aqui

O agregador descreve o mundo; não sabe quem está assistindo. Nível e gênero são fatos sobre a
competição, verdadeiros independente de quem pergunta, e por isso ficam aqui
([ADR 0008](adr/0008-competition-tier-and-gender-at-ingestion.md)). "Eu gosto do Palmeiras" é
gosto, muda toda semana, e não tem nada a ver com agregar.
