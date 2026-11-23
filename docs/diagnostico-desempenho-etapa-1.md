# AmbiDiff · Diagnóstico de desempenho da etapa 1

A referência desta etapa é o HEAD remoto `eef2f734a59707aedff18a65d22fffa6ee1a4383`
da branch `experimento/motor-eficiencia-v2`. A instrumentação usa o relógio
monotônico do Python e o diagnóstico JSON existente.

## 1. Onde a execução consome tempo

- **Navegação.** O Playwright aguarda `domcontentloaded` para cada ambiente.
  Em caso de timeout, o motor pode aproveitar o DOM observado ou repetir a
  abertura aguardando `commit`. A recuperação de `ERR_ABORTED` também pode
  aguardar o DOM ou repetir a abertura. O contador de visitas mede chamadas
  do motor à rotina de navegação e o tempo inclui essas recuperações.
- **Estabilização e extração.** A preparação percorre a página e aguarda
  quietude semântica. Ela já mede as pausas explícitas da rolagem e da sondagem.
  A extração executa JavaScript, inspeciona abas, reconstrói os itens em Python
  e pode repetir a leitura. Antes desta etapa, uma extração que terminava em
  erro ficava fora do tempo acumulado.
- **Pareamento e comparação.** A medição anterior cobria o comparador
  principal e o pareamento de links. Foram incluídos o alinhamento de
  componentes, a comparação de conteúdo em releituras, as verificações de
  seções, aparência e ordem, e o pareamento de controles e candidatos
  semânticos. As verificações de documentos, destinos e cliques têm
  cronômetros próprios.
- **Fila.** A descoberta mede deduplicação, filtros, prioridades e admissão.
  Uma proposta ou reposição da fila pode disparar uma conferência HEAD.
  Seu tempo é descontado da descoberta. A seleção na fila também mede a
  avaliação do adiamento editorial.
- **Evidências e persistência.** Capturas podem abrir páginas, esperar
  renderização, localizar elementos e gravar PNGs. O cronômetro existente
  cobre a geração de evidências inteira. O checkpoint combina preparação de
  dados, assinatura, serialização e I/O. A exportação final mede a geração e a
  escrita dos relatórios pelo worker.

### Amostra de tempo em loopback

Foi usada a fixture `portais_perf(4)`, com PRD e LAB sintéticos, comparação
inteligente, geração de evidências e exportação padrão do worker. Foram
executadas três invocações independentes por versão, em ordem alternada,
com os mesmos Python e Chromium. Cada invocação comparou quatro pares,
tentou oito visitas HTML e gerou 18 capturas. IDs, elementos, tipos,
ambientes e contagens de ocorrências das divergências coincidiram.

| Medição | Mediana com instrumentação (s) |
| --- | ---: |
| Evidências | 3,127 |
| Preparação e estabilização | 2,631 |
| Espera explícita, incluída na preparação | 1,427 |
| Navegação HTML | 0,639 |
| Extração de DOM | 0,268 |
| Pareamento e comparação | 0,035 |
| Exportação dos relatórios | 0,015 |
| Checkpoints | 0,008 |
| Seleção e descoberta na fila | 0,002 |
| Tempo total da coleta no motor | 7,783 |

Evidências e preparação tiveram os maiores tempos observados. O tempo
externo do worker, medido até seu retorno, variou de 8,284 a 8,713 s no
HEAD de referência, com mediana de 8,539 s. Na versão instrumentada,
variou de 8,039 a 8,392 s, com mediana de 8,180 s. Os intervalos se
sobrepõem. A amostra serve como referência local e tem tamanho limitado
para atribuir a diferença à instrumentação.

## 2. Métricas no diagnóstico JSON

O objeto `desempenho` tem versão própria e usa apenas números, rótulos fixos
e descrições de escopo. Ele é aditivo ao diagnóstico existente.

| Campo | Unidade e abrangência |
| --- | --- |
| `tempo_total_coleta_segundos` | Segundos de tempo decorrido no motor até o fechamento das métricas. Na retomada soma o tempo acumulado no checkpoint ao novo trecho. |
| `etapas_coleta_segundos` | Segundos por etapa disjunta. Inclui navegação HTML, preparação e estabilização, extração de DOM, pareamento e comparação, fila e descoberta, evidências, checkpoints e verificações de destinos, documentos e cliques. |
| `espera_explicita_na_preparacao_segundos` | Segundos das pausas instrumentadas na preparação adaptativa e na confirmação de template. Já integra a etapa de preparação e estabilização. |
| `exportacao_relatorios_segundos` | Segundos da geração e escrita dos relatórios nesta invocação do worker. Na recuperação, inclui a escrita do relatório parcial ou do arquivo de recuperação. |
| `tempo_worker_ate_gravacao_diagnostico_segundos` | Segundos nesta invocação, da entrada do worker até o diagnóstico pronto em memória. Inclui a exportação de relatórios. |
| `contagens.visitas_html_tentadas` | Aberturas no fluxo de coleta HTML por ambiente, incluindo as que falham. Tentativas internas de `goto` pertencem à abertura que as disparou. |
| `contagens.paginas_com_dom_preservado` | Páginas cujo DOM consta do resultado, incluindo inspeções unilaterais. Uma releitura pode substituir uma coleta sem aumentar esse contador. |
| `contagens.pares_comparados`, `pares_inconclusivos` e `pares_falhos` | Pares em estados terminais do motor. Inconclusivos incluem redirecionamentos, inspeções unilaterais e saídas de escopo. Um resultado não HTML nos dois lados tem estado próprio. |
| `contagens.urls_excluidas_intencionalmente` | URLs distintas ainda classificadas como excluídas pela política de admissão, segundo `filtro_urls.urls_excluidas`. |
| `tempo_medio_por_par_comparado_segundos` | Tempo total da coleta dividido pelos pares efetivamente comparados. Vale `null` quando nenhum par foi comparado. |
| `origem_coleta`, `historico_metricas_legado` e `escopo` | Indicam a origem da leitura, lacunas anteriores à retomada e a abrangência das medidas. |

O custo total de checkpoints já inclui os subtempos legados de conversão,
assinatura, serialização e escrita. Navegação e esperas feitas para captura
integram evidências. A duração de releitura legada inclui preparação e
extração. Use as etapas disjuntas para comparar custos. Cada subtempo é uma
parcela da etapa que o contém.

## 3. Arquivos modificados

- `ambidiff/smart.py` reutiliza o cronômetro existente, mantém o tempo inclusivo
  da descoberta e adiciona seu tempo sem a conferência de destino.
- `ambidiff/adaptive.py` registra o tempo de uma espera mesmo quando ela falha.
- `ambidiff/paired.py` mede extração com falhas, seleção da fila e os trechos de
  pareamento e comparação que faltavam. Propaga a indicação de histórico legado
  na retomada.
- `ambidiff/diagnostics.py` monta os agregados de desempenho a partir dos
  cronômetros, da fila e do resumo da política de URLs.
- `web/server.py` registra o limite temporal do worker e o custo de persistência
  do relatório recuperado.
- `tests/test_desempenho.py` cobre as métricas e os contratos de integração.
- `docs/diagnostico-desempenho-etapa-1.md` documenta a referência e a validação.

## 4. Testes e resultados

| Verificação | Resultado |
| --- | --- |
| `python -B -m unittest discover -s tests -v` no HEAD de referência | 317 testes aprovados em 172,002 s. |
| `python -B -m unittest discover -s tests -p test_desempenho.py -v` | 9 testes aprovados. |
| `python -B -m unittest discover -s tests -v` com instrumentação | 326 testes aprovados em 177,501 s. |
| `node --check web/static/app.js` e `git diff --check` | Aprovados. |

A suíte Linux usou Python 3.12.14, Playwright 1.64.0 e Chromium 154 do
sistema. O CDN retornou HTTP 403 para o download do Chromium empacotado.
A suíte não registrou falhas nem saltos com o Chromium local. A execução
no Windows e com o Chromium empacotado não foi realizada neste ambiente.

Os testes novos usam relógio controlado, mocks e material sintético. Cobrem
segundos e denominadores, escopos disjuntos, timeout de extração, timeout e HTTP
503 de navegação, download inconclusivo, exclusões e privacidade, detecção de
ÁUDIOS, invariância das divergências e da fila, interrupção, retomada, leitura
legada e gravação do diagnóstico JSON. O microteste compara dois cronômetros
aninhados com contextos neutros e exige menos de 20 µs de CPU adicional por
iteração.

## 5. Limitações da medição

- As etapas medem tempo decorrido, inclusive espera e chamadas ao navegador.
  Elas cobrem parte do total. Inicialização, consolidação final, atualização
  de progresso e a pausa nominal de 40 ms entre pares estão entre os custos
  que podem aparecer fora dessas etapas. O arredondamento é de seis casas
  decimais.
- O tempo da coleta do motor termina antes da montagem final do resultado e
  do fechamento do Chromium. O tempo do worker abrange essas operações e
  termina antes da escrita do próprio diagnóstico JSON e log TXT e da
  atualização do histórico. Assim, o diagnóstico é escrito uma vez.
- Em uma falha recuperada, os tempos da coleta refletem o último snapshot
  válido, que registra os custos acumulados antes de sua própria gravação.
  Invocações retomadas carregam os tempos persistidos. Um histórico legado
  carece dos trechos que a versão anterior não media. Diagnósticos antigos
  podem ter somente os campos legados.
- O teste em loopback mede um portal sintético pequeno. O perfil de rede, a
  complexidade do DOM, a quantidade de abas e a latência de disco variam com
  o ambiente. Nenhum portal institucional foi consultado.

## 6. Próxima etapa · Playwright + AsyncIO

1. Repetir medições com fixtures locais que reproduzam latência, navegação
   com timeout, conteúdo tardio e diferentes volumes de evidências. Registrar
   a versão do navegador, o armazenamento, o número de pares e a variação
   entre execuções.
2. Usar os tempos de navegação e preparação para selecionar as primeiras
   operações a avaliar com Playwright assíncrono. Conservar contextos
   independentes e a coordenação da fila, dos checkpoints e do limite de
   1.000 pares HTML admitidos.
3. Distinguir tempo decorrido, tempo de operação acumulado e tempo de
   espera por recursos quando houver tarefas sobrepostas. Comparar a nova
   etapa com esta referência usando os mesmos cenários, estados terminais e
   divergências, inclusive com interrupção e retomada.
