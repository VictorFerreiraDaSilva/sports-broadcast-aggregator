# Código específico de fonte vive em app/sources/<fonte>/

Para que "adicionar fonte não toca o core" seja verdade fisicamente, e não só por convenção,
separamos `app/` em duas áreas: um núcleo genérico (db, models, o `Source` protocol, o
orquestrador/scheduler) e `app/sources/<fonte>/` — uma pasta por fonte com tudo que é
específico dela (cliente HTTP, normalização, casamento de catálogo, mapeamento pro esporte
canônico). O código hoje em `app/client.py`, `app/normalize.py`, `app/catalogs.py` (específicos
do futnatv) move para `app/sources/futnatv/`.

A documentação de engenharia reversa da API (`docs/api-reference.md`, `docs/schemas.md`,
`docs/notas-de-campo.md`, `docs/legal-e-etiqueta.md`), os `samples/` e `examples/futnatv.py`
também são específicos do futnatv — não do agregador — e movem junto para dentro de
`sources/futnatv/`.
