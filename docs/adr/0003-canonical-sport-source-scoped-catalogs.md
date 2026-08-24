# Esporte é uma dimensão canônica; canal/competição/time ficam escopados por fonte

Diferente de canal/competição/time (ADR 0002), esporte é um vocabulário pequeno e fechado
(~5-10 valores conhecidos de antemão: futebol, basquete, vôlei, futebol americano, hóquei...).
Decidimos que existe uma dimensão `sport` canônica compartilhada por todas as fontes, e cada
adapter é responsável por mapear seu próprio vocabulário de esporte (ex.: "soccer" da ESPN)
para esse conjunto canônico antes de gravar — o core só entende códigos canônicos.

Canal, competição e time continuam escopados por fonte, pela mesma razão do ADR 0002: são
vocabulários abertos, sem ID estável, e tentar unificá-los entre fontes heterogêneas agora
seria chute sem dados reais de ESPN/Globo. Hoje `channel`/`competition` também não são
dimensões genéricas — são espelhos dos catálogos que o próprio futnatv publica (cor, imagem,
prioridade de UI); outras fontes podem nem ter um catálogo equivalente para casar.
