# Schema central enxuto; peculiaridades de cada fonte vão num JSONB opaco

As tabelas centrais (`game`, `channel`, `competition`, `team`) hoje misturam colunas
universais (data, hora, times, competição, transmissão) com colunas 100% futnatv (`odds_*`,
`youtube_url`, `icon_emoji`, `aggregate`, `payload_sport`). Consideramos: (A) manter só o
universal como colunas tipadas no core, e tudo peculiar de uma fonte vai num campo
`source_data: JSONB` opaco ao core, preenchido e lido só pelo adapter daquela fonte; ou (B)
uma tabela satélite tipada por fonte (`futnatv_game_detail`, `espn_game_detail`, ...) ligada
por FK.

Decidimos por (A). (B) exigiria uma migration no schema compartilhado toda vez que uma fonte
nova é adicionada, o que contradiz o objetivo de "adicionar fonte não toca o core" (ADR 0001).
O custo é perder tipagem/constraints nesses campos peculiares — aceitável, já que são dados
best-effort por natureza (a própria origem já os trata como texto livre sem garantia).
