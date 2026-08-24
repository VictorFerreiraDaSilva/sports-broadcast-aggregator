# Jogos são escopados por fonte; sem fusão entre fontes no v1

Com múltiplas fontes, o mesmo jogo real pode ser reportado por futnatv, ESPN e Globo, cada
uma com seu próprio texto de time/hora/transmissão. Consideramos duas formas: (A) tratar cada
fonte como uma verdade independente — `source` entra na chave natural do jogo, e o mesmo jogo
real gera uma linha por fonte que o reportou; ou (B) uma entidade "jogo canônico" com
observações por fonte casadas por heurística (times + data + janela de horário).

Decidimos por (A) para o v1. (B) exige entity-resolution entre convenções de nome
heterogêneas por fonte — o mesmo problema que já existe hoje só dentro do futnatv para times
(sem ID estável), multiplicado por N fontes, e sem dados reais de outras fontes ainda para
calibrar a heurística. "Agregar" significa unir os calendários lado a lado, uma linha por
fonte por jogo; uma visão unificada por jogo fica como evolução futura, depois que houver
≥2 fontes reais em produção.
