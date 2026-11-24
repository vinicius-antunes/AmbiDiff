# AmbiDiff · Validação geral das seis etapas

## Resumo executivo

**Decisão sugerida. Corrigir a regressão da Etapa 6 antes da validação em portais reais.**
A coleta deixou de detectar uma opção estrutural revelada por um expansível
quando `aria-controls` aponta para o próprio elemento coletável. A reprodução
inclui o commit anterior à Etapa 6, o comportamento da versão experimental
e um controle com o link dentro de um painel. A auditoria também encontrou
instabilidade preexistente dos IDs em novas varreduras com duas reordenações
de menu de mesmo tamanho.

Os filtros acumulados preservaram ÁUDIOS, serviços, legislação e documento
na fixture de cobertura. A extração semântica recuperou correspondências
rotuladas em outra fixture. O relatório traz os resultados das suítes, a
comparação em carga equivalente e a origem das regressões.

## Referências e método

| Branch | HEAD remoto auditado | Papel |
| --- | --- | --- |
| `main` | `52e867655733df2ab9e3bf1f0703acc4a9c89285` | Referência comum, com pareamento conservador e medições básicas existentes |
| `perf/filtro-urls-varredura` | `ed743eae575a4f20d4cf29c24e90cd59545cf000` | Isola admissão por finalidade, paginação editorial e identidade de portal |
| `experimento/motor-eficiencia-v2` | `69cf31e1334d9ac9b177a4e03b1b027ad148b958` | Seis etapas e integração dos filtros |
| Experimental antes da Etapa 6 | `d897a6f46f255da676ad8fa01004bfdd9a16574f` | Isola a regressão de coleta sob `aria-controls` |

Cada HEAD foi exportado em diretório independente por `git archive`.
A base comum entre `main` e o experimental é `52e8676`. Os comandos usaram
Linux x86-64, Python 3.12.14, Playwright 1.64.0 e Chromium 154 local oculto.
O teste de desempenho manteve parâmetros de execução, conteúdo e latência.
A avaliação funcional usou HTML de fixture, origens distintas em loopback
e apenas GET/HEAD observados pelo servidor. A suíte também cobre o bloqueio
de POST. Em cada verificação, «relevante» é a classificação do relatório.
A precisão usa exclusivamente os casos com resultado esperado na fixture.

## Comparação funcional

### Cobertura, exclusões e relatórios

| Fixture de filtros | `main` | Filtros | Experimental síncrono | Experimental assíncrono |
| --- | ---: | ---: | ---: | ---: |
| Pares descobertos / admitidos / comparados | 14 / 14 / 13 | 9 / 9 / 8 | 9 / 9 / 8 | 9 / 9 / 8 |
| Pares excluídos de navegação pela política de URL | Campo ausente | 5 | 5 | 5 |
| Inconclusivos por redirecionamento final divergente | 1 | 1 | 1 | 1 |
| Falhas de automação | 0 | 0 | 0 | 0 |
| DIVs classificadas como relevantes | 4 | 3 | 3 | 3 |
| Registros editoriais informativos | 1 | 0 | 0 | 0 |
| PNGs com referências válidas | 8 | 6 | 6 | 6 |

Filtros e experimental excluíram dois pares de rotas editoriais
(`/w/` e `/-/`), duas páginas posteriores de Rádio/TV com índice Liferay e
um portal vizinho. O conteúdo profundo desses cinco pares ficou fora da
cobertura. Os oito pares comparados foram a raiz, SIMCAR, SIMLAM, SISFLORA,
os dois parâmetros de ano de legislação e as páginas iniciais de Rádio/TV.
A Portaria 12 em `/documents/d/` foi verificada por metadados nas quatro
execuções. A classificação registrada foi «Documento acessível e
provavelmente equivalente». O redirecionamento de Guia de atendimento
teve destinos finais diferentes em todos os checkouts.
Os 13 e os oito pares representam, respectivamente, 26 e 16 páginas
efetivamente comparadas. A contagem de descoberta exibida pelo motor
reflete a entrada na fila. As exclusões anteriores à admissão aparecem
na política de URL e ficam fora desse número.

ÁUDIOS ficou relevante e conservou `DIV-0001` nessa fixture. O guia ficou
como `DIV-0004` em `main` e `DIV-0003` em filtros e experimental
porque uma publicação deixou de entrar no conjunto comparado. Os dois
modos experimentais produziram as mesmas DIVs, classificações e estados
dos pares. Os relatórios exportados foram verificados em JSON, CSV, HTML
e PDF, com IDs consistentes entre JSON, CSV e HTML, referências de PNG
existentes, dimensões positivas e CRC válido. A verificação do PDF cobriu
geração e assinatura do arquivo.

### Precisão estrutural e recuperação

| Fixture ARIA rotulada | `main` | Filtros | Experimental nos dois modos |
| --- | ---: | ---: | ---: |
| Equivalências esperadas registradas | 0/5 | 0/5 | 5/5 |
| Falsos positivos de equivalência nos 13 casos rotulados | 0 | 0 | 0 |
| Falsos negativos de equivalência nos cinco casos positivos | 5 | 5 | 0 |
| Pares descobertos / admitidos / comparados | 5 / 5 / 1 | 5 / 5 / 1 | 4 / 4 / 3 |
| Inspeções unilaterais / redirecionamentos inconclusivos | 4 / 0 | 4 / 0 | 0 / 1 |

As equivalências esperadas eram Atendimento, Legislação, Portaria 12,
Preferências do portal e Resumo. A leitura por nome acessível, contexto,
destino e papel explica a melhora nessa amostra. Nas referências, a
coleta pós-clique repetia itens da página e emitia falsas ausências para
opções equivalentes. A versão experimental separou os estados de
indisponibilidade e expansão, preservou o redirecionamento diferente e
classificou como inconclusivo o conteúdo da aba cuja inspeção falhou.
ÁUDIOS permaneceu relevante. Esses números de precisão cobrem somente
esta fixture. O caso adicional `painel` expôs um falso negativo novo.

Na fixture de falhas, as três referências síncronas e o experimental
assíncrono terminaram com dois pares comparados e dois falhos. O DES
recebeu HTTP 503 em uma rota e excedeu um timeout controlado de 250 ms
em outra. A tentativa de navegação até commit também expirou na rota
lenta. ÁUDIOS permaneceu no relatório e a fila continuou até o outro par.
Na fixture de retomada, cada execução parou com um par concluído e três
pendentes. O JSON v1 foi validado em disco e gerou um parcial exportável.
Após retomar, havia quatro pares comparados, sem novo GET na raiz e com o
mesmo ID de ÁUDIOS. Os testes completos também exercitam navegador
encerrado, recuperação de recursos, relatório parcial após reinício,
limites de fila e preservação de evidências.

Em um ensaio separado com os mesmos servidores ativos, um JSON v1
produzido pela `main` foi lido em outro processo pelo experimental
assíncrono. A retomada totalizou quatro pares, preservou o ID e marcou
`historico_metricas_legado=true`. A raiz também ficou sem novo GET.

### Regressões e IDs

1. **Bloqueante. O alvo de `aria-controls` pode ser a própria opção.**
   Em `--caso painel`, um botão revela um `<a hidden id="servico-revelado">`
   apenas no PRD. No commit `d897a6f`, a opção «Consultar serviço estadual»
   resultou em DIV relevante, duas capturas e uma inspeção unilateral da
   rota. Em `69cf31e`, desapareceram a opção, a visita unilateral e as
   capturas correspondentes nos dois modos. No controle
   `--caso painel-container`, com o
   mesmo link como filho de uma `<div>` controlada, a versão experimental
   volta a produzir a DIV. A mudança está em `coletar_aba()`, que envia o
   seletor do alvo para `JS_EXTRAIR`, e nas consultas
   `escopo.querySelectorAll()` da Etapa 6. A API retorna apenas descendentes.
   A correção sugerida é incluir o elemento raiz quando combinar com o
   seletor de cada família já inspecionada. A regressão deve cobrir alvo
   `<a>` e alvo `<p>`, elemento indisponível, segurança de ações, inspeção
   de contêiner e paridade síncrona/assíncrona.
2. **Instabilidade preexistente. IDs de dois menus podem trocar de posição.**
   Em `--caso ids`, a semente `PYTHONHASHSEED=0` atribui `DIV-0001` ao Menu A e
   `DIV-0002` ao Menu B. A semente 3 inverte o resultado nas três branches,
   com opções, conteúdo e cardinalidade idênticos. `diferencas_de_ordem()`,
   em `paired.py`, começa com uma interseção de conjuntos e ordena os
   candidatos somente pelo tamanho. `agrupar_registros()` numera na ordem
   de chegada. O desempate deve ser explícito e estável, com teste em
   processos de sementes diferentes. Uma eventual mudança de ordenação
   deve preservar revisões e evidências já armazenadas com o relatório
   original.
3. **Classificação editorial compartilhada pelas três branches.**
   A fixture de Rádio/TV traz uma publicação textual variante sob
   `<article>` com data e título. O texto virou DIV relevante nas três
   referências. A coleta já identifica a finalidade de listagem para
   filtrar a paginação, enquanto `editorialRef()` exige sinais de
   publicação no item ou uma rota de artigo reconhecida. Em seguida,
   `item_editorial()` preserva a marca estrutural emitida pelo extrator.
   Vale avaliar uma correção separada, com prova contextual dos blocos
   correspondentes e regressões para controles e referências estruturais
   no mesmo portal.

Uma inclusão, exclusão ou fusão legítima de ocorrências pode renumerar DIVs
de uma nova varredura. Mudança de numeração por entrada idêntica é outro
caso. Na retomada local, a DIV de ÁUDIOS conservou seu ID. IDs de par e
IDs de DIV têm escopos distintos.

## Auditoria da integração

| Etapa | Resultado e manutenção |
| --- | --- |
| 1. Instrumentação | Campos de desempenho complementam as métricas legadas. Checkpoints preservam custos acumulados. As fronteiras de `checkpoint`, releitura e espera já incluem subetapas. Usar tempo decorrido para o total. |
| 2. Preparação e evidências | As janelas de estabilidade e o cache de captura atuam no caminho de coleta existente. A auditoria verificou referências e CRC dos PNGs, além de IDs nos formatos exportados. A comparação anterior da Etapa 2 verificou pixels e marcações em fixtures específicas. |
| 3. Navegação assíncrona | A concorrência está limitada às duas navegações do mesmo par. Fila, preparação, extração e comparação continuam compartilhadas. O modo síncrono é o padrão. `AMBIDIFF_NAVEGACAO_ASSINCRONA=1` habilita o experimento pelo caminho de entrada existente. `navigation_async.py` repete partes das regras síncronas de timeout e `ERR_ABORTED`. Mudanças nessas regras devem atualizar os testes de paridade nos dois modos. |
| 4. RapidFuzz | É a única dependência nova nos requisitos. O limite superior Indel reduz candidatos e `SequenceMatcher` ainda determina as pontuações finais do caminho aproximado. A correspondência semântica utiliza rótulos exatos e contexto, separadamente. |
| 5. SQLite | O único caminho do servidor para a retomada padrão é JSON v1. O protótipo tem callback próprio e usa `sqlite3` da biblioteca padrão. A gravação confirma um snapshot integral, com assinatura v1 e hash do envelope. Mesmo com rollback transacional, mantém o custo de serialização completa. |
| 6. HTML/ARIA | Nome, papel, hierarquia, destino e estado são observações estruturais. A combinação encontra opções equivalentes com tags diferentes e preserva contexto inconclusivo. A consulta pós-clique omite o alvo quando ele próprio é coletável, conforme a regressão bloqueante. |

O ganho acumulado entre branches inclui mudanças de cobertura, preparação,
comparação e escrita. A tabela de desempenho separa a comparação de
carga fixa da comparação dos filtros. A diferença entre os dois modos do
mesmo HEAD mede o efeito do modo de navegação nesse experimento.

## Desempenho em carga equivalente

O cenário `escala` usa uma raiz com referências para páginas de
serviços estáveis, latências fixas de 40 ms no PRD e 80 ms no DES, uma
DIV esperada de ÁUDIOS, captura e persistência JSON. Em cada configuração
foram medidos dois processos independentes, com a ordem da segunda rodada
invertida. O total externo mede da chamada do motor ao seu retorno,
incluindo inicialização, encerramento, checkpoints e capturas. A geração
posterior dos arquivos de exportação fica fora desse tempo.

As 24 execuções concluíram exatamente os pares previstos, com a mesma
ordem, uma DIV de ÁUDIOS com o mesmo ID e dois PNGs referenciados por
execução. Houve zero erros, timeouts, recuperações ou exclusões nessas
cargas. Os valores são medianas de duas amostras.

| Pares comparados | `main` total / s por par | Filtros total / s por par | Experimental síncrono total / s por par | Experimental assíncrono total / s por par |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 5,115 / 2,557 | 5,313 / 2,657 | 4,592 / 2,296 | 4,140 / 2,070 |
| 8 | 9,769 / 1,221 | 9,805 / 1,226 | 8,421 / 1,053 | 8,176 / 1,022 |
| 20 | 18,887 / 0,944 | 18,602 / 0,930 | 16,486 / 0,824 | 15,205 / 0,760 |

| Fases da carga de 20 pares | `main` | Filtros | Experimental síncrono | Experimental assíncrono |
| --- | ---: | ---: | ---: | ---: |
| Navegação decorrida (s) | 4,402 | 4,286 | 4,362 | 2,892 |
| Preparação (s) | 8,545 | 8,496 | 6,813 | 6,814 |
| Extração (s) | 1,144 | 1,099 | 1,142 | 1,133 |
| Comparação principal (ms) | 2,2 | 2,2 | 3,2 | 3,3 |
| Comparação complementar (ms) | Campo ausente | Campo ausente | 59,6 | 61,3 |
| Capturas (s) | 1,918 | 2,019 | 1,344 | 1,373 |
| Checkpoints (ms) | 13,3 | 18,8 | 21,1 | 20,9 |
| Pico de RSS Python (MiB) | 34,92 | 35,87 | 39,07 | 39,17 |
| Volume final de artefatos (MB) | 0,484 | 0,538 | 0,552 | 0,552 |

Com 20 pares iguais, o experimental síncrono levou **12,7% menos tempo**
que a `main`. Nesse cenário, a diferença apareceu sobretudo na
preparação e nas capturas. Na troca isolada do modo síncrono para
assíncrono no mesmo HEAD, a navegação decorrida caiu **33,7%** e o total
caiu **7,8%**. Os tempos individuais dos dois lados se sobrepõem.
A comparação principal nessa fixture é curta e a tabela separa esse
trecho dos custos complementares. A triagem de textos tem medição
própria abaixo.

As amostras de 20 pares variaram de 18,85 a 18,92 s na `main`, de
16,46 a 16,52 s no experimental síncrono e de 15,19 a 15,22 s no
assíncrono. O pico de RSS exclui o driver e os processos do Chromium.
O volume final inclui checkpoint, diagnóstico, PNGs e relatórios
JSON/CSV/HTML, sem PDF. A amostra cobre o efeito de latências
artificiais e conteúdo estável. A carga de filtros compara coberturas
diferentes e ficou fora da avaliação de ganho de velocidade.

### SQLite em separado

O benchmark da Etapa 5 foi reexecutado em volume de trabalho com
cinco gravações por tamanho. Estado, fila, IDs e referências foram
conferidos. Cada célula mostra JSON / SQLite.

| Pares admitidos | Assinatura + gravação (ms) | Leitura validada (ms) | Arquivo final (MB) |
| ---: | ---: | ---: | ---: |
| 20 | 4,6 / 5,6 | 5,4 / 5,6 | 0,248 / 0,487 |
| 300 | 75,1 / 69,5 | 91,0 / 98,9 | 3,888 / 7,721 |
| 980 | 238,3 / 242,0 | 331,3 / 372,7 | 12,734 / 25,248 |

A 980 pares, a projeção do parcial levou 931,0 ms no JSON e 948,8 ms
no SQLite. O pico de RSS dos processos de persistência foi 145,3 MB e
146,0 MB, respectivamente. Ambos permaneceram no piso estimado de
30 s entre checkpoints. O arquivo SQLite final ficou em torno do dobro
nos três cenários. A suíte reproduziu encerramento de processo durante
gravação, com retorno ao último estado confirmado nos dois formatos.
Os tempos do scanner foram medidos com JSON.

### Comparação textual em separado

O mesmo microbenchmark comparou `6b2f882` e `4150aac` em três repetições
por caso. Ele mede `comparacao()` sobre itens já extraídos. O hash da
saída, incluindo DIVs, IDs, classes, editoriais e links, foi igual nos
três conjuntos.

| Lista textual | Itens PRD / DES | Antes (ms) | Com a triagem (ms) | Pico de alocação Python antes / depois (KiB) |
| --- | ---: | ---: | ---: | ---: |
| Pequena | 18 / 19 | 1,888 | 1,110 | 32,1 / 60,2 |
| Grande | 458 / 459 | 3.640,425 | 47,972 | 675,9 / 911,9 |
| Densa | 138 / 139 | 538,716 | 93,334 | 204,4 / 367,6 |

Cada caso manteve dois falsos positivos e três falsos negativos de
associação textual já presentes no seletor anterior. A melhora
comprovada aqui é de tempo de comparação, com maior alocação auxiliar.
Esses números não estimam o efeito em todo o scanner.

## Verificações automatizadas e limitações

| Suite completa de cada checkout | Aprovados | Falhas | Ignorados | Tempo |
| --- | ---: | ---: | ---: | ---: |
| `main` | 272 | 0 | 0 | 161,6 s |
| Filtros | 336 | 0 | 0 | 198,9 s |
| Experimental | 389 | 0 | 0 | 283,5 s |

`python -B -m unittest discover -s tests -v`, `node --check
web/static/app.js`, `pip check` e `git diff --check` passaram. As suítes
têm quantidades e cenários diferentes. Seus tempos servem ao registro de
testes. Os dois problemas reproduzidos acima foram encontrados com fixtures
adicionais fora das suítes anteriores.

O teste automatizado do teto usa uma fixture simulada para percorrer mais
de 1.000 candidatos, incluindo retomada próxima do limite. A varredura com
Chromium real mede até 20 pares no benchmark. Os tempos incluem o navegador
local, a fixture e o volume de trabalho desta máquina. Rede institucional,
autenticação, sessões reais, VPN, antivírus, tecnologia assistiva e Windows
ficaram sem validação. A configuração atual do workflow inclui disparo
manual para Windows e a branch experimental está fora das branches de
`push` listadas.

## Roteiro manual condicionado à autorização do mantenedor

1. Registrar o commit corrigido, versões de Windows, Python, Chromium e
   dependências. Instalar pelo procedimento do projeto e executar a suíte
   Windows. Usar a mesma máquina, viewport, rede, opções de coleta e
   estado de sessão autorizado nas comparações.
2. Para cada portal, obter autorização explícita para as origens e o escopo
   de leitura. Confirmar a URL inicial e a contraparte autorizada para cada
   ambiente. Começar com uma amostra pequena. Usar cada ambiente de forma
   simétrica, preservar certificados e bloqueios e manter desabilitados
   os cliques opcionais e a auditoria de destinos externos na primeira
   rodada. Evitar ações de escrita, login automatizado e redistribuição de
   dados internos.
3. Na CGE, conferir a opção ÁUDIOS nos menus autorizados de cada ambiente,
   sua rota e a presença ou ausência observada. Conferir os menus
   recolhidos com manipulação somente de leitura. Associar a evidência ao
   elemento e ao contexto, sem exigir um número fixo de DIV.
4. Na SEMA, registrar serviços autorizados como SIMCAR, SIMLAM e SISFLORA,
   legislação e documentos acessíveis. Conferir as primeiras páginas de
   Rádio/TV e a classificação de paginação editorial posterior, `/w/`,
   `/-/` e referências a portais vizinhos. Guardar separado o que foi
   observado na origem e o conteúdo profundo efetivamente comparado.
5. No PROCON, registrar menus e destinos com correspondência inequívoca,
   referências unilaterais, redirecionamentos, páginas inconclusivas e
   falhas. Se a autorização abranger um volume alto, reconciliar admitidos,
   comparados, pendentes e motivos de exclusão. Confirmar o teto de 1.000
   pares HTML antes de ampliar a amostra.
6. Repetir a mesma amostra com o modo síncrono e o assíncrono. Interromper
   uma execução de teste pelo controle suportado, exportar o parcial,
   reiniciar o servidor local e retomar. Conferir IDs, capturas, relatórios
   JSON, CSV, HTML e PDF. Registrar falsos positivos e negativos pela
   identidade do elemento e pela cobertura, anexando apenas artefatos
   autorizados e sanitizados.

## Recomendação técnica

| Critério | Parecer local |
| --- | --- |
| Divergências estruturais relevantes | Reprovado pelo alvo direto de `aria-controls`. |
| Falsos positivos | Sem aumento nos 13 casos rotulados de ARIA. Persiste a classificação editorial conservadora em Rádio/TV. |
| Segurança e somente leitura | Aprovado nas fixtures e nos testes de bloqueio. |
| Limite de 1.000 pares e recuperação | Aprovado nas regressões de teto, interrupção e retomada. |
| Benefício mensurável | Aprovado nas fixtures de precisão e nos cenários de desempenho com cobertura igual descritos acima. |
| Cobertura e ambiente | Exclusões documentadas. Windows e portais reais ainda sem validação. |

Corrigir a seleção do alvo da Etapa 6 em uma mudança isolada. Acrescentar
o teste de estabilidade dos IDs como correção independente por afetar um
comportamento anterior às otimizações. Manter o JSON v1 como padrão,
SQLite isolado e modo síncrono como referência operacional. Depois de
reexecutar os cenários de cobertura e a suíte Windows, submeter o roteiro
de validação real à autorização do mantenedor. A decisão de produção
depende dessa validação.

## Reprodução

Na raiz da branch que contém este relatório, com as dependências e o
Chromium de Playwright instalados, exportar os commits auditados.

```sh
auditoria=$(mktemp -d)
mkdir -p "$auditoria"/{main,filtros,experimental,etapa3,etapa4,etapa5,volume}
git archive 52e8676 | tar -x -C "$auditoria/main"
git archive ed743ea | tar -x -C "$auditoria/filtros"
git archive 69cf31e | tar -x -C "$auditoria/experimental"
git archive 6b2f882 | tar -x -C "$auditoria/etapa3"
git archive 4150aac | tar -x -C "$auditoria/etapa4"
git archive d897a6f | tar -x -C "$auditoria/etapa5"
for versao in main filtros experimental; do
  (cd "$auditoria/$versao" && PYTHONHASHSEED=0 python -B -m unittest discover -s tests -v)
  for caso in filtros aria retomada falhas; do
    PYTHONHASHSEED=0 python -B scripts/validar_experimental.py \
      --codigo "$auditoria/$versao" --caso "$caso" --latencia-ms 0 0
  done
done
for caso in filtros aria retomada falhas painel; do
  PYTHONHASHSEED=0 python -B scripts/validar_experimental.py \
    --codigo "$auditoria/experimental" --caso "$caso" --latencia-ms 0 0 --assincrono
done
for versao in etapa5 experimental; do
  python -B scripts/validar_experimental.py --codigo "$auditoria/$versao" \
    --caso painel --latencia-ms 0 0
done
python -B scripts/validar_experimental.py --caso painel-container --latencia-ms 0 0
for semente in 0 3; do
  PYTHONHASHSEED=$semente python -B scripts/validar_experimental.py --caso ids
done
```

Acrescentar `--pdf` ao cenário `filtros` para repetir a verificação PDF.
Para os tempos, rodar o cenário `escala` com `--pares 2`, `--pares 8` e
`--pares 20`, em dois processos independentes por configuração, usando
`--latencia-ms 40 80`, `PYTHONHASHSEED=0` e o mesmo volume local como
`TMPDIR`. Na primeira repetição, usar a ordem main, filtros,
experimental síncrono e experimental assíncrono. Na segunda, inverter
a ordem.

```sh
TMPDIR="$auditoria/volume" python -B "$auditoria/experimental/scripts/benchmark_persistencia_sqlite.py"
PYTHONHASHSEED=0 python -B "$auditoria/etapa4/scripts/benchmark_rapidfuzz.py" \
  --baseline "$auditoria/etapa3" --repeticoes 3
```

### Relatórios de origem

- [Diagnóstico de desempenho da Etapa 1](diagnostico-desempenho-etapa-1.md)
- [Preparação e evidências da Etapa 2](otimizacao-playwright-etapa-2.md)
- [Navegação assíncrona da Etapa 3](navegacao-assincrona-etapa-3.md)
- [Triagem de similaridade da Etapa 4](similaridade-rapidfuzz-etapa-4.md)
- [Integração dos filtros de URL](integracao-filtros-etapa-4.md)
- [Persistência SQLite e JSON da Etapa 5](persistencia-sqlite-etapa-5.md)
- [Reconhecimento estrutural da Etapa 6](estrutura-aria-etapa-6.md)
