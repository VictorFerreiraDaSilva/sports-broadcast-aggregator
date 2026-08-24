# Registro explícito de fontes, sem auto-discovery

O core (ingest loop, scheduler, models) não deve mudar ao adicionar uma fonte nova, mas uma
fonte nova precisa aparecer em algum lugar para ser executada. Consideramos auto-discovery
(scan de diretório ou entry points do Python) contra um registro explícito (uma lista/dict
central listando as fontes ativas). Decidimos pelo registro explícito: entry points via
packaging adicionam complexidade desproporcional a um projeto pequeno, e um scan de diretório
em runtime dificulta desabilitar uma fonte ou dar config por fonte. Adicionar uma fonte edita
uma linha nesse registro — não o ingest, o scheduler nem os models.
