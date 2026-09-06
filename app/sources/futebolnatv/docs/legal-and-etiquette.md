# Legal e etiqueta de coleta

Levantado em 2026-08-27. Não é aconselhamento jurídico — é o que o próprio site declara, para
você decidir com a informação na mão.

**Resumo:** tecnicamente esta fonte é a mais fácil de coletar das duas; juridicamente é a mais
restritiva. Vale ler antes de escrever qualquer linha de adapter.

---

## O que o `robots.txt` diz

`https://www.futebolnatv.com.br/robots.txt`, na íntegra — três linhas:

```
User-agent: *
Allow: /
Sitemap: https://www.futebolnatv.com.br/site-map.xml
```

É tudo. Nenhum `Disallow`, nenhum crawler bloqueado por nome, e — diferente do futnatv —
**nenhum `Content-Signal`**. Não há reserva de direitos declarada ali, nem restrição a
`ai-train`. O site também publica um sitemap justamente para ser rastreado.

Pelo `robots.txt`, portanto, coleta automatizada não é objetada.

## O que os Termos de Uso dizem — e aqui muda a história

`/info/termo-de-uso/`. O §7 ("Regras: faça e não faça") é bem mais duro que o silêncio do
`robots.txt`:

> **7.1** Somos os proprietários ou licenciados de todos os direitos de propriedade
> intelectual […] Todo o conteúdo, incluindo, mas não limitado ao design, texto, software,
> gráficos, material e imagens que são disponibilizados para você (e qualquer seleção ou
> disposição dos mesmos) está sujeito aos nossos direitos autorais e/ou de terceiros.

> **7.2** As Plataformas são apenas para **seu uso pessoal**. Isso significa que em nenhuma
> circunstância você pode usá-los para fazer ou promover negócios. […] qualquer uso que vá
> além do seu uso pessoal em seu ambiente privado e/ou para fins comerciais […] em particular
> transmissões lineares e/ou não lineares, radiodifusão, repostagem e/ou **disponibilização
> pública** […] **live tickers**, serviços SMS, e **qualquer forma de processamento, edição
> e/ou duplicação do conteúdo** […] são estritamente proibidos.

> **7.4** Você é obrigado a **não copiar, gravar ou salvar** as Plataformas e seu conteúdo no
> todo ou em parte […] ou redirecionar, encaminhar, compartilhar, retransmitir, gravar ou
> compartilhar o conteúdo no todo ou em parte com outras pessoas.

E no rodapé de toda página:

> © 2026 FutebolnaTV · Todos os direitos reservados
> \* É proibida a reprodução parcial ou total do nosso conteúdo.
> © 2018–2026 Sinc Lda.

### Lendo isso com honestidade

Três leituras, da mais defensável à menos:

1. **Uso pessoal, sem publicar.** Um agregador privado que consulta a agenda para você ver
   onde passa o jogo é o caso que o §7.2 explicitamente contempla ("seu uso pessoal em seu
   ambiente privado"). É o uso mais defensável — e é o que este projeto é hoje.
2. **Salvar em banco.** O §7.4 fala em "não copiar, gravar ou salvar […] no todo ou em parte".
   Lido ao pé da letra, isso alcança um `insert` numa tabela `game`. Lido com o resto do §7.2,
   o que a cláusula está mirando é redistribuição e uso comercial, não cache privado. É uma
   zona cinzenta real, e o texto é mais amplo do que o do futnatv, que não tem cláusula
   equivalente.
3. **Publicar o agregado.** Aqui não há cinza: §7.2 proíbe "disponibilização pública" e cita
   **live tickers** nominalmente — que é exatamente a forma de um agregador de jogos ao vivo.
   Se este projeto virar algo público, esta fonte precisa de permissão explícita, não de uma
   interpretação favorável.

Some-se um ponto de fundo: a curadoria de transmissão **é** o produto deles. A agenda de jogos
vem de feed; o "onde assistir", o recorte regional da Globo, o nome do canal do YouTube, os
narradores — isso é redação. Copiar exatamente a parte que dá trabalho é o que mais incomoda
um site desses, e é justamente o que nos interessa.

## Se for pedir permissão

Contato declarado nos termos: **`contato(a)futebolnatv.com.br`** (o `(a)` é ofuscação de `@`
no HTML deles). Também há `/info/contato/` e `/info/suporte/`, e as redes
[@FutebolnaTVbr](https://x.com/FutebolnaTVbr) e
[@FutebolnaTVapp](https://www.instagram.com/FutebolnaTVapp).

Operador: **Sinc Lda** (rodapé). A analítica do site roda em `hits.sincnetwork.com.br`, mesmo
grupo. A grafia europeia em vários textos ("registado", "Secções", "protecção") sugere
operação em Portugal.

Vale mencionar, ao pedir: uso pessoal, volume baixo, sem redistribuição, com crédito e link.

## Etiqueta técnica

O servidor não impõe nada — o que torna a etiqueta responsabilidade nossa:

- **Nenhum rate limit foi observado.** 20 requisições consecutivas sem pausa à mesma página →
  20× 200. Não há 429, não há challenge da Cloudflare.
- **Nenhum bloqueio por user-agent.** UA de browser, UA custom, `python-urllib/3.12` e
  requisição sem UA nenhum, todas 200.

Recomendações, na mesma linha do que já fazemos com o futnatv
([config.py](../../futnatv/config.py), `FUTNATV_REQUEST_DELAY_SECONDS = 1.1`):

- **~1 req/s**, com jitter. Fartamente suficiente: o plano barato é ~200 requisições para a
  janela inteira do sitemap, ou seja ~3,5 minutos de coleta.
- **User-Agent identificável e com contato.** Já é o padrão do projeto
  (`FUTNATV_CONTACT_INFO`); replicar como `FUTEBOLNATV_CONTACT_INFO`. Se incomodarmos, que
  saibam quem procurar.
- **Sempre `Accept-Encoding: gzip`.** As páginas caem de 60–270 KB para 10–23 KB. É o gesto de
  etiqueta com melhor relação custo/benefício aqui.
- **Começar pelo `/site-map.xml`.** É o índice que eles mesmos publicam para rastreamento —
  usar o caminho oficial em vez de varrer páginas é literalmente seguir a instrução do site.
- **Cadência baixa.** `lastmod` do sitemap é horário; os catálogos (canais, ligas, times) mudam
  em escala de semanas. Não há razão para bater mais que algumas vezes por dia na agenda e uma
  vez por dia nos catálogos.
- **Não martelar o WebSocket.** Cada sessão custa um GET + um join de ~49 KB. Usar só quando a
  paginação for realmente necessária, e fechar a conexão depois.
- **Não hotlinkar imagens** de `static.futebolnatv.com.br`. Se precisar de logo, baixar uma vez
  e servir do nosso lado — ou, melhor, não copiar logo nenhum.
- **Não tocar em nada autenticado.** `/sign-in`, `/profile/*` não foram testados e não devem
  ser. Não há dado de agenda atrás de login.

## Comparação com a outra fonte

| | futnatv.net | futebolnatv.com.br |
|---|---|---|
| `robots.txt` | `Allow: /` + Content-Signals (`ai-train=no`) + 9 crawlers bloqueados | `Allow: /` puro, sem sinais, com sitemap |
| Termos de uso | não encontrados | **§7 explícito**: uso pessoal, proíbe cópia, salvar e disponibilização pública |
| Aviso de copyright | — | rodapé em toda página |
| Rate limit observado | nenhum | nenhum |
| Postura resultante | permissiva por omissão | **restritiva por escrito** |

Traduzindo: o futnatv não disse nada sobre o assunto; o futebolnatv disse, e disse não. Isso
não impede uso privado, mas é a diferença entre "não perguntaram" e "responderam antes de
perguntarmos" — e deve pesar mais que a facilidade técnica na hora de decidir adotar a fonte.
