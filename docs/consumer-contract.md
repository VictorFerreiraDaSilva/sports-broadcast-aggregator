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

## Jogos que a fonte deixou de relatar

O agregador **nunca apaga** um jogo. Uma linha de `game` é o que a fonte relatou em algum
momento, e `last_seen_at` diz quando foi a última vez — só a coleta escreve nessa coluna. Daí
saem duas situações que o consumidor precisa conhecer:

- **Fantasma.** A fonte corrige o horário ou a grafia de um time (`Al-Shabab x Al-Taawon` de 15h00
  para 14h45, `Rodina Moscow` para `Rodina`). Isso muda a chave natural, então entra uma linha
  nova e a antiga fica para trás, com `last_seen_at` parado.
- **Jogo retirado.** A fonte também tira da grade, ao longo do dia, jogos que não mudaram nem têm
  substituto. Medido no backup de 11/10: em 04/10, 18 jogos (Argentino, Neerlandês Feminino,
  amistosos) aparecem só na coleta das 06:00; em 12/09, 53 de 128. Não há como, olhando só o
  banco, distinguir esse caso do fantasma.

Por isso o agregador não faz pruning: "a fonte não listou mais" apagaria jogos reais junto com os
fantasmas. Quem quiser só o que a fonte relata **agora** filtra pela última coleta bem-sucedida:

```sql
AND g.last_seen_at >= (
  SELECT max(started_at) FROM scrape_run
  WHERE source_code = g.source_code AND job_type = 'games' AND status = 'success'
)
```

O custo é esconder também os jogos retirados — para uma grade enviada logo depois da coleta das
06:00, é quase sempre o que se quer.

E há duplicata que **vem da própria fonte**: em 11/10 o futnatv listava ao mesmo tempo
`Abha x Al-Faisaly 12h15` e `Abha x Al-Faysaly 12h25`. Ambas foram vistas na última coleta, então o
filtro acima não pega; se incomodar, deduplicar por competição + horário próximo + um time em comum
é decisão do consumidor (ADR 0002).

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
