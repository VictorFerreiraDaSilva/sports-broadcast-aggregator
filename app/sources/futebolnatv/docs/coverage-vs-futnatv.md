# Cobertura: futebolnatv × futnatv

Comparação medida em 2026-08-27 contra a fonte que já está no ar
([app/sources/futnatv](../../futnatv/README.md)). Objetivo: saber se a nova fonte **substitui**,
**complementa** ou **duplica** a atual.

**Resposta curta: complementa.** Cada uma tem jogos que a outra não tem, e cada uma sabe coisas
sobre transmissão que a outra não sabe. Nenhuma é superconjunto da outra.

Antes de tudo, o desencontro de nomes: `futnatv.net` e `futebolnatv.com.br` são **sites
diferentes**, de operadores diferentes. O `futnatv` que aparece nas `<meta keywords>` do
futebolnatv é a abreviação que eles usam para si mesmos. Ver
[field-notes §19](field-notes.md#19-cuidado-com-o-nome-futnatv-é-como-eles-se-chamam).

---

## 1. Volume por dia

| Dia | futebolnatv | futnatv | observação |
|---|---|---|---|
| 26/08 (ontem) | 22 | 29 | futnatv não tem jogos antes de 14h45 nesse dia |
| 27/08 (hoje) | 26 | 47 | os 26 são os que ainda não terminaram **e** têm canal |
| 28/08 (amanhã) | 26 | 43 | dia inteiro dos dois lados |

O futnatv lista **mais jogos**. Mas a comparação é injusta: o futnatv lista tudo, com
`broadcast: ""` em ~40 % dos casos; o futebolnatv lista **só o que tem transmissão anunciada**
([field-notes §1](field-notes.md#1-a-lista-de-agenda-é-filtrada-por-transmissão-anunciada)).

Números de 28/08: dos 43 jogos do futnatv, **23 têm broadcast**. Dos 26 do futebolnatv,
**26 têm**. Ou seja, no recorte que interessa a este projeto — jogo com transmissão — o
futebolnatv entrega **mais**: 26 contra 23.

## 2. Quem cobre o quê (28/08)

Competições onde o **futebolnatv tem e o futnatv não**:

- MLS Next Pro (2 jogos), 3ª Divisão Alemã, Campeonato Austríaco, Brasileiro Sub-20,
  NWSL Feminina (2), Campeonato Peruano, Campeonato Uruguaio, Campeonato Turco.

Competições onde o **futnatv tem e o futebolnatv não**:

- Campeonato Chinês (3 jogos, 08h35–09h00), parte do Campeonato Saudita, Campeonato Russo.

No dia 26/08 o padrão se repete com outros nomes: o futnatv trouxe Copa Rio, Paulista Feminino
e NWSL que o futebolnatv não tinha; o futebolnatv trouxe `Whitecaps II x Los Angeles II` (MLS
Next Pro) que o futnatv não tinha.

Não há regra limpa do tipo "um cobre feminino e o outro não" — no dia 26 o futebolnatv perdeu
NWSL e no dia 28 tinha. São dois catálogos editoriais diferentes, com sobreposição grande e
bordas distintas.

## 3. Qualidade do dado de transmissão

Aqui a diferença é estrutural, e é o argumento mais forte a favor da nova fonte.

| | futnatv | futebolnatv |
|---|---|---|
| Formato | **uma string** por jogo | **uma lista** de chips |
| Exemplo | `"Globo (RJ, BA, ES, MA, PA, RN e SE), SporTV 2, Premiere, YouTube (GE TV) e Prime Video"` | 5 chips: `GLOBO` + `(RJ, BA, …)`, `SPORTV 2`, `PREMIERE`, `YOUTUBE` + `(GE TV)`, `PRIME VIDEO` |
| Separadores | `", "` e `" e "`, misturados | nenhum — são nós separados |
| Qualificador regional | dentro da string | `<span>` próprio |
| Identidade do canal | só o nome; precisa casar contra `canais.json` por nome/alias/família | **link `/canal/{slug}`** na página do jogo |
| Tipo do canal | não existe | 4 grupos: sinal aberto / assinatura / streaming aberto / streaming assinatura |
| Vazio | `""` em 40 % dos jogos | o jogo simplesmente não é listado |

O `catalogs.py` do futnatv existe para resolver `"ESPN 4"` → canal, com alias e redução de
família. **Com o futebolnatv esse trabalho não existe** — o site entrega a chave. Isso remove
a maior fonte de erro silencioso que temos hoje na fonte atual.

## 4. O que a fonte atual tem e a nova não

- **Cinco esportes.** O futnatv tem `futebol`, `basquete`, `volei`, `nfl`, `nhl`. O
  futebolnatv é **só futebol**. Se basquete/NFL/NHL importam, o futnatv não pode ser
  aposentado.
- **Consulta por data arbitrária.** `/api/futebol?data=YYYY-MM-DD` alcança qualquer dia. O
  futebolnatv só tem D−1…D+1 por URL, e nada de histórico
  ([field-notes §20](field-notes.md#20-sem-cors-não-é-o-problema-sem-histórico-é)).
- **JSON.** Um endpoint estável e barato de parsear, contra HTML de LiveView que muda a cada
  ajuste de design.
- **Odds e `youtubeUrl`.** O futnatv traz `odds[3]` e o link direto do vídeo no YouTube. O
  futebolnatv dá o canal (`YOUTUBE (GOL BRASIL)`) mas **não** a URL do stream.
- **Termos permissivos.** Ver [legal-and-etiquette.md](legal-and-etiquette.md#comparação-com-a-outra-fonte).

## 5. O que a nova fonte tem e a atual não

- **Canal resolvido por slug e classificado por tipo** (§3).
- **Início exato em UTC** (`startDate` ISO com offset + link do Google Agenda), contra
  `"13h00"` em horário de Brasília implícito.
- **Placar e minuto ao vivo.** O futnatv não tem placar.
- **Ida e volta de mata-mata** explícitos (`Jogo 1 de 2` + link para o outro jogo). O futnatv
  tem só o campo `aggregate` com o placar do jogo de ida, em 2,2 % dos jogos.
- **Entidades navegáveis com id estável**: `/liga/{slug}-{id}`, `/time/{slug}-{id}`,
  `/canal/{slug}` — com país, ano de fundação, temporada com início e fim.
- **Horizonte longo de fixtures** (até dezembro pela página do time), ainda que a transmissão
  só seja anunciada com 2–3 semanas de antecedência.
- **Um índice de descoberta publicado**: `/site-map.xml`, 325 URLs numa requisição.
- **Esporte confiável.** O futnatv tem duas falhas conhecidas — `/api/nfl` devolve
  `"sport": "futebol"` e `/api/volei` vaza jogos de futebol. Aqui é tudo futebol, por
  construção: não há como errar o esporte.

## 6. Conclusão prática

Se a decisão for adotar, o desenho natural é **as duas fontes convivendo**, que é exatamente o
que o [ADR 0002](../../../../docs/adr/0002-source-scoped-games-no-cross-source-merge.md) já prevê
— jogos escopados por `source_code`, sem merge entre fontes:

- `futnatv` continua sendo a fonte de **cobertura ampla e multiesporte**, com consulta por data.
- `futebolnatv` entra como a fonte de **transmissão de qualidade** para futebol: canal
  identificado, tipo, região, horário exato, placar.

O que **não** faz sentido é trocar uma pela outra. E o que decide não é técnica: é o §7 dos
termos de uso ([legal-and-etiquette.md](legal-and-etiquette.md)).
