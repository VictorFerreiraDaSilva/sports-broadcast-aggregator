# Agregador de calendários esportivos

Agrega jogos e onde assisti-los a partir de múltiplas fontes públicas (sites/APIs de terceiros).
Cada fonte é coletada, normalizada para um modelo comum e gravada lado a lado com as demais —
sem tentar fundir o mesmo jogo real relatado por fontes diferentes (ver ADR 0002).

## Language

**Fonte (Source)**:
Um site/API externo do qual o agregador coleta jogos (ex.: futnatv.net, ESPN, Globo). Cada
fonte é implementada como um adapter que normaliza seus dados para o modelo comum e se
registra explicitamente no core (ADR 0001) — o core nunca conhece detalhes de uma fonte
específica.
_Avoid_: Provedor, scraper (scraper é a fonte futnatv especificamente, não o conceito geral)

**Jogo**:
Um evento esportivo entre dois participantes, do jeito que uma fonte específica o relatou.
Escopado por fonte — o mesmo jogo real relatado por duas fontes gera duas linhas
independentes, sem fusão (ver ADR 0002).
_Avoid_: Evento, partida, match

**Esporte canônico**:
Um dos poucos valores fixos e compartilhados entre todas as fontes (futebol, basquete, vôlei,
...). Cada fonte mapeia seu próprio vocabulário de esporte para esse conjunto antes de gravar
(ver ADR 0003). É a única dimensão unificada entre fontes — canal, competição e time não são.
_Avoid_: sport_code cru da fonte (esse é o esporte-da-fonte, não o canônico)

**Catálogo**:
Dimensão auxiliar (canal, competição ou time) usada para casar o texto livre de um jogo com
uma entidade conhecida. Escopado por fonte — não é fundido entre fontes (ver ADR 0003).
_Avoid_: Dimensão global, entidade compartilhada

**Nível da competição**:
Se uma competição é profissional ou de base. Eixo canônico do agregador, compartilhado entre
fontes — nenhuma fonte o publica, porque todas colapsam nível, gênero e geografia num campo
só (ver ADR 0008). Admite não saber: uma competição pode estar sem classificação.
_Avoid_: Categoria (categoria é o campo colapsado da fonte, não este eixo), divisão, série

**Gênero da competição**:
Se uma competição é masculina ou feminina. Eixo canônico independente do nível — uma
competição pode ser feminina e de base ao mesmo tempo, que é justamente o que o campo único
da fonte não consegue expressar (ver ADR 0008). Também admite não saber.
_Avoid_: Categoria, naipe

**Relevância**:
O quanto um jogo interessa a uma pessoa específica. **Não é conceito deste projeto** — o
agregador descreve o mundo e não sabe quem está assistindo (ver ADR 0009). Nível e gênero são
fatos sobre a competição; relevância é gosto, e mora no consumidor.
_Avoid_: Usar "relevante" para dizer "profissional" ou "com transmissão"
