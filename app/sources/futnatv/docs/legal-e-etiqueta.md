# Legal e etiqueta de coleta

Levantado em 2026-08-21. Não é aconselhamento jurídico — é o que o próprio site declara,
para você decidir com a informação na mão.

---

## O que o `robots.txt` diz

`https://futnatv.net/robots.txt` (servido via bloco gerenciado pela Cloudflare):

```
User-agent: *
Content-Signal: search=yes,ai-train=no,use=reference
Allow: /
```

Traduzindo os Content-Signals conforme a própria explicação no arquivo:

| Sinal | Valor | Significado declarado |
|---|---|---|
| `search` | `yes` | pode indexar para busca |
| `ai-train` | `no` | **não** pode usar para treinar ou fazer fine-tuning de modelos |
| `use` | `reference` | consumo por IA permitido como referência |

O arquivo afirma explicitamente que restrições expressas por Content-Signal são reserva de
direitos sob o Artigo 4 da Diretiva 2019/790 da União Europeia.

### Crawlers bloqueados por nome

`Disallow: /` para: `Amazonbot`, `Applebot-Extended`, `Bytespider`, `CCBot`, `ClaudeBot`,
`CloudflareBrowserRenderingCrawler`, `Google-Extended`, `GPTBot`, `meta-externalagent`.

São os crawlers de coleta em massa para treinamento de modelos. Um script seu, buscando dados
para uso próprio, não é nenhum deles — mas o padrão geral é claro: **o site aceita acesso e
indexação, e recusa uso do conteúdo como material de treino.**

### O que isso implica para o seu caso

Extrair a agenda para consumo próprio (ver que jogo passa onde) cai no `User-agent: * Allow: /`
e no sinal `use=reference`. O que o site pediu para não acontecer é o conteúdo virar dataset de
treinamento de modelo. Se em algum momento o projeto mudar de "consultar a agenda" para
"alimentar um modelo", vale reler isso.

Redistribuir o dataset em público é uma terceira coisa, diferente das duas anteriores — a agenda
é trabalho editorial deles (a curadoria de "onde passa" é o produto do site). Se for publicar,
crédito e link para `futnatv.net` são o mínimo, e vale perguntar antes.

## Termos do site

Há páginas `/sobre/` e `/privacidade/`. Não foram encontrados Termos de Uso com cláusula
explícita sobre acesso automatizado ou uso da API. A API não é anunciada publicamente: é
infraestrutura interna do site, o que significa que **pode mudar ou sumir sem aviso** e que
nenhuma estabilidade é prometida.

Contato do responsável, se você quiser pedir permissão ou avisar do uso:
[@futnatv no X](https://x.com/futnatv), [@futenatv no Instagram](https://instagram.com/futenatv).

## Etiqueta técnica

Nenhum rate limit foi observado (~150 requisições em poucos minutos passaram sem bloqueio), mas
ausência de limite não é permissão para abusar — e há Cloudflare na frente, que pode passar a
barrar a qualquer momento.

Recomendações concretas:

- **Serialize e espaçe.** ~1 req/s é folgado. O servidor leva ~0,5 s por resposta; não pare-
  lelize dezenas de dias de uma vez.
- **Cacheie do seu lado.** A API não manda `Cache-Control`, mas a agenda de um dia passado não
  muda mais. Guarde datas passadas permanentemente e reconsulte só hoje e o futuro.
- **Não faça polling apertado.** Um jogo não muda de canal de minuto em minuto. Uma atualização
  a cada 30–60 min cobre qualquer caso real.
- **Baixe os catálogos raramente.** `canais.json` e `competicoes-futebol.json` mudam em escala de
  semanas (compare o campo `version`). Uma vez por dia já é mais que suficiente.
- **Identifique-se.** Um `User-Agent` com nome do projeto e forma de contato faz de você um
  vizinho identificável em vez de tráfego anônimo suspeito.
- **Falhe com elegância.** Backoff exponencial em 429/5xx, e pare de vez se começar a tomar 403 —
  é o sinal de que o Cloudflare passou a te barrar.

O cliente em [examples/futnatv.py](../examples/futnatv.py) já vem com pausa entre requisições,
cache em disco e `User-Agent` identificável.
