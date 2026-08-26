# Erro parcial chega ao core por `logging`, e cada execução notifica no máximo uma vez

O agregador roda desatendido num container. Até aqui, um erro tinha três destinos possíveis —
`log.error`, a coluna `scrape_run.error_message`, ou nada — e os três exigiam alguém abrir o
terminal para descobrir que algo quebrou. Pior: a falha mais provável era justamente a mais
silenciosa. Uma fonte que engole erro para continuar (futnatv pula a data que a API recusou)
termina com `status="success"` mesmo tendo perdido 16 das 20 requisições da execução.

Decidimos notificar por Pushover, e três escolhas aqui merecem registro.

## Erro parcial chega ao core por `logging`, não por um canal novo

Para o core notificar um erro que a fonte engoliu, o erro precisa chegar até
`app/core/jobs.py`. Consideramos três caminhos:

1. **Mudar a assinatura do Protocol** — `fetch_games` devolveria
   `FetchResult(games, errors)` em vez de uma lista. É o mais explícito, e foi descartado por
   quebrar o contrato do ADR 0001/0005 e obrigar toda fonte (inclusive `_example`) a mudar por
   uma razão que não é do domínio delas.
2. **Um coletor explícito no core** — `report_partial_failure(...)`, importado pela fonte. Não
   quebra assinatura, mas transfere para cada fonte futura a obrigação de lembrar de chamá-lo;
   esquecer significa voltar exatamente ao problema que estamos resolvendo.
3. **Um `logging.Handler` plugado durante a execução** — escolhido. `collect_errors()`
   (`app/core/errors.py`) escuta a árvore `app.*` em nível ERROR enquanto o job roda. O
   `log.error` que a fonte já escrevia *é* o sinal.

A terceira mantém a promessa do README nas duas direções: adicionar uma fonte não toca
`app/core/`, e o core não passa a exigir nada novo da fonte. O preço é um acoplamento a
convenção em vez de a tipo — uma fonte que engula um erro sem logar nada continua invisível, e
nenhum type checker avisa. Aceitamos: "logue seus erros" é uma convenção que já valia antes.

O handler tem dois filtros que não são opcionais. Ele só aceita registros da árvore `app.*`
(um `log.error` de retry do urllib3 não é falha de coleta) e só os da thread que abriu o
coletor — o APScheduler executa jobs num pool, e sem esse filtro os erros de uma coleta
vazariam para a notificação de outra.

## No máximo uma notificação por execução

Uma execução de `fetch_games` da futnatv são 20 requisições (5 esportes × 4 datas), 4 vezes por
dia. Com a API fora do ar, notificar por erro geraria 80 pushes num dia — e o dia em que a API
cai é exatamente o dia em que ler o celular importa. Os erros são agregados por *assinatura*
(logger + template da mensagem + tipo da exceção), não pela mensagem já formatada, de modo que
as 16 falhas de `"erro ao buscar %s %s"` viram um grupo com contagem 16.

A tabela de severidade está em `app/core/notify.py`. A prioridade 2 do Pushover (emergência,
repete até o usuário confirmar) fica deliberadamente sem uso: nada num agregador de calendário
esportivo justifica acordar alguém às 3h da manhã.

| Situação | Prioridade |
|---|---|
| Banco inacessível no boot | `1` — fura as quiet hours; não volta sozinho |
| Job inteiro falhou | `0` — a próxima execução agendada pode resolver |
| Execução degradada (engoliu erros) | `-1` |
| Execução sem nenhum jogo, e sem erro | `-1` |
| Job do scheduler estourou ou execução perdida | `-1` |

Execução limpa **não** notifica. Um push por coleta bem-sucedida, 4x por dia por fonte, treinaria
qualquer um a ignorar os pushes.

A linha "sem nenhum jogo" não é exceção nenhuma: é a fonte respondendo 200, o parser aceitando, e
não sobrando nada — o único modo de falha aqui que nenhum `except` denuncia.

## O estado degradado vive no banco, não só no push

A primeira versão deste sistema tinha uma incoerência: "degradado" existia como categoria de
notificação e não existia em lugar nenhum do banco. Uma execução que engoliu 16 erros gravava
`scrape_run.status="success"` e mandava um push — de modo que qualquer consulta posterior a
`scrape_run` a contaria como sucesso limpo, e a única cópia do que deu errado estava numa
notificação no celular de alguém.

Isso quebra justamente o caso que o push de prioridade `-1` não consegue cobrir sozinho: a
**degradação lenta**. Cada aviso isolado passa batido; o que denuncia o problema é a soma
("24 das últimas 28 execuções degradadas"), e a soma exige que o estado esteja no banco.

`scrape_run.status` passou a ter três valores:

| `status` | significado |
|---|---|
| `success` | execução limpa |
| `degraded` | gravou o que deu, mas engoliu erros pelo caminho |
| `error` | perdeu a execução inteira |

Nenhuma migration foi necessária: a coluna já era `String(16)` sem `CHECK`, e nenhum consumidor
filtrava por `status = 'success'`.

Três decisões dentro dessa:

- **`error_message` continua exclusivo da falha fatal.** Os erros engolidos vão para `details`,
  em `errors_collected` (contagem) e `error_groups` (os grupos, estruturados). Misturar os dois
  na mesma coluna apagaria a distinção entre "o que matou a execução" e "o que ela sobreviveu".
- **Um run `error` que também engoliu parciais continua `error`.** A falha fatal é a mais grave,
  mas os parciais anteriores a ela agora vão para `details` do mesmo jeito — antes se perdiam
  por completo, já que o `details` de um run que falhou era `{}`.
- **`details.error_groups` é estruturado, não o texto do push.** `summary()` é renderização para
  os 1024 caracteres do Pushover e corta em 5 grupos; `as_records()` leva todos, em campos
  separados, para que uma consulta agregue por tipo de erro sem fazer parsing de string. A chave
  para agregar é `template` (o `"erro ao buscar %s %s"` do `log.error`, não a mensagem
  formatada) — `label` cai no nome do módulo quando não há `exc_info`, e aí dois erros
  diferentes da mesma fonte colidiriam.

"Sem jogos" deliberadamente **não** ganhou um quarto valor de status: nenhum erro aconteceu, e o
sinal já está em `details.games_count`.

## O container espera o banco em vez de morrer

`docker/entrypoint.sh` roda `alembic upgrade head` antes de qualquer código nosso. Com o banco
fora do ar, o alembic morria primeiro, o container morria junto e o `restart: unless-stopped`
o reiniciava — um crash loop no qual nenhuma linha de Python nossa chegava a rodar, e portanto
completamente mudo. Notificar de dentro desse loop trocaria o silêncio por dezenas de pushes
idênticos.

`python -m app.core.wait_for_db` passou a rodar antes do alembic: insiste com backoff, notifica
**uma vez** após ~60s de falha contínua, continua tentando em silêncio e avisa de novo ao
conectar. O container fica de pé, então não há loop e não há spam. Um banco fora por 10 minutos
gera duas notificações: caiu e voltou.

O mesmo raciocínio vale para uma falha de boot do scheduler, que é determinística: ela notifica
no máximo uma vez por container, via um marcador em `/tmp` que sobrevive a `restart` e some no
recriar.

## Consequência: um jogo malformado deixou de derrubar a coleta

Notificar o caso "a API mudou o formato de um jogo" só é útil se sobrar coleta para salvar. Antes
disso, um único `KeyError` em `_normalize_game` derrubava os outros ~500 jogos da execução.
`app/sources/futnatv/source.py` passou a normalizar cada jogo sob `try/except`: o jogo ruim é
descartado com `log.error` (que o coletor agrega e notifica), os demais gravam. É uma mudança de
resiliência, não só de observabilidade, e está registrada aqui por isso.

## Buraco conhecido

Uma migration quebrada faz `alembic upgrade head` falhar *depois* de `wait_for_db` ter
confirmado que o banco responde. O container morre e nenhum push sai — o processo Python que
saberia notificar é o que não subiu. Cobrir isso exigiria um wrapper em shell chamando a API do
Pushover via `curl`, e não vale o custo: uma migration quebrada aparece no terminal de quem está
fazendo o deploy naquele instante, ao contrário de todas as outras falhas deste documento, que
acontecem com o operador dormindo.
