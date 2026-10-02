# Nível e gênero da competição são eixos nossos, resolvidos no jogo

As fontes não publicam nível nem gênero. Publicam **um** campo `category` que colapsa três
eixos: geografia (`Brasil`, `Europa`), gênero (`Feminino`) e nível (`Base`). Como os valores são
mutuamente exclusivos, uma competição que é feminina *e* de base só pode aparecer num deles.

Decidimos que o agregador mantém dois eixos canônicos próprios — `tier`
(`professional`/`youth`/`unknown`) e `gender` (`men`/`women`/`unknown`) — resolvidos na ingestão
por [app/core/classification.py](../../app/core/classification.py) e gravados em `game`, junto
com `tier_method` e `gender_method`, que registram qual regra decidiu
(`curated`/`source`/`pattern`/`none`), no mesmo espírito do `game_broadcast.match_method`.

**No jogo, não na competição.** `competition` é escopada por fonte (ADR 0003) e só existe para
futebol — a fonte não publica catálogo de competições para vôlei, basquete, NFL ou NHL. Prender
a classificação à dimensão deixaria 100 % desses jogos sem classificação nenhuma, e também os
jogos de futebol cujo nome ainda não entrou no catálogo.

**A categoria da fonte é evidência apenas positiva.** `Base` afirma que é base; qualquer outra
categoria **não afirma nada** sobre o nível, porque o eixo da fonte é colapsado. O caso que
fixou a regra foi medido: a `Copa do Mundo Feminina sub-20` (19 jogos) está em `Feminino`, então
a categoria da fonte, lida ingenuamente, a classificaria como profissional. Por isso toda a
evidência de base é esgotada — dica da fonte, depois padrão no nome — antes de a categoria poder
afirmar `professional`; e o mesmo vale, espelhado, para `women` antes de `men`.

**Classificar pelo nome não é fundir competições.** A regra "todo nome que casa `sub-\d\d` é
base" não afirma que o `Brasileiro Sub-20` de duas fontes é a mesma entidade, não cria
identidade e não funde linha alguma — os ADRs 0002 e 0003 seguem valendo. É por isso que as
listas curadas em `classification.py` são chaveadas pelo nome normalizado e são agnósticas de
fonte.

**Alternativa descartada:** um booleano `is_youth`. Sem um estado `unknown`, tudo que ninguém
classificou entra silenciosamente na conta como profissional — exatamente o viés que a
classificação existe para eliminar. Medido nos 270 jogos de 06–11/09: incluir base derruba a
cobertura de transmissão de 75,8 % para 62,2 %.

**Consequência aceita:** como a classificação é resolvida na ingestão e a coleta só cobre
hoje..hoje+`DAYS_AHEAD`, editar as listas curadas não reclassifica o passado.
`python -m app.main reclassify` cobre isso, mas só reescreve o que não depende de dica da fonte
(`curated`/`pattern`) — a dica vivia no índice do catálogo no momento da captura, não na linha,
e recomputá-la às cegas rebaixaria a linha para `unknown`.
