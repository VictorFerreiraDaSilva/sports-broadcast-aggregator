# Relevância pessoal fica fora do agregador

Existe uma vontade natural de o agregador responder "quais jogos me interessam hoje" — foi o que
um fluxo n8n anterior fazia, com uma tabela `user_preferences` (`team`/`competition`/`blacklist`)
consultada por um `JOIN` contra os jogos do dia.

Decidimos que isso **não entra aqui**. São três coisas distintas, e só a primeira é do agregador:

1. **Nível e gênero da competição** — fato objetivo sobre a competição, verdadeiro independente de
   quem pergunta. Fica aqui (ADR 0008).
2. **Preferência de uma pessoa** — quais times e competições interessam, o que ignorar. Subjetiva,
   muda toda semana. Fica fora, numa planilha lida pelo nó nativo de Google Sheets do n8n.
3. **"Este jogo entra na mensagem de hoje"** — 1 + 2 + data. Lógica de consumidor, fica fora.

O princípio: **o agregador descreve o mundo; ele não sabe quem está assistindo.** No momento em
que `user_preferences` entra neste schema, o agregador passa a ter *um usuário* — e o
[CONTEXT.md](../../CONTEXT.md), o README e os ADRs anteriores estão todos escritos sem esse
conceito. Toda fonte nova e toda consulta futura passariam a ter que raciocinar sobre ele.

Manter a preferência fora também evita trazer para o container credencial do Google, token de bot
e uma dependência de rede nova na ingestão — hoje o único canal de saída é o Pushover do ADR 0007.

O contrato com o consumidor é o próprio banco: ele lê `game` com `tier`, `gender` e
`has_broadcast` já resolvidos, e cruza com a planilha por conta própria. Ver
[docs/consumer-contract.md](../consumer-contract.md).

**Consequência aceita:** a lógica de casar preferência com jogo continua sendo SQL dentro de um nó
do n8n, sem teste e sem versionamento — inclusive o casamento de nome de time, que já produziu um
falso positivo conhecido (`Atlético` casando com `Atlético Madrid`). O ganho de trazer isso para cá
seria testabilidade; o custo seria o modelo de domínio parar de descrever o que o projeto é.
