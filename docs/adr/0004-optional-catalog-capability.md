# Sincronização de catálogo é uma capacidade opcional da fonte, não obrigatória

Nem toda fonte tem um catálogo estático equivalente ao `canais.json`/`competicoes-futebol.json`
do futnatv — algumas podem só mandar o nome do canal como texto solto dentro do jogo, sem lista
separada pra sincronizar. Decidimos que a interface `Source` exige apenas `fetch_games` (e o
mapeamento de esporte canônico do ADR 0003); `sync_catalog` é opcional, implementado só pelas
fontes que de fato têm um catálogo real. O orquestrador consulta essa capacidade para decidir
se agenda o job de catálogo daquela fonte, em vez de toda fonte carregar um método no-op só por
uniformidade.
