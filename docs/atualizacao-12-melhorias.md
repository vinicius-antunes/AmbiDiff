# Atualização de estabilidade, exportação e deduplicação — 12 melhorias

Referência inspecionada: branch `perf/otimizacao-varredura`, HEAD `f7ba62e`.
O checkout estava em `61e06f5`; foi atualizado por avanço direto para o commit
remoto informado, cuja alteração era somente o guia Windows do README.
Não foi usada a `main`. O mantenedor autorizou posteriormente o commit e o
envio destas alterações somente para `perf/otimizacao-varredura`. Não há merge
de branches, deploy ou publicação do aplicativo/GitHub Pages.

## Fase A — diagnóstico e baseline

Foram revisados `core.py`, `paired.py`, `frontier.py`, `documents.py`,
`functional.py`, `reports.py`, `storage.py`, `diagnostics.py`, `checkpoints.py`,
`web/server.py`, JavaScript, template e testes relacionados.

A base já tinha filas com `visitados`/`pares_enfileirados`, comparação
bidirecional e por seção, reconhecimento de equivalências estáticas, preparação
adaptativa, documentos por HEAD, checkpoints retomáveis, editoriais separados,
revisões imutáveis e relatórios v1/v2. Não foi criado outro sistema para essas
funções. A suíte inicial aprovou **161 testes em 84,947 s**. O baseline de
cobertura é funcional (casos e itens coletados); não foi medida porcentagem de
linhas/branches por ferramenta de cobertura.

Não foram encontrados logs identificados como SEFAZ nos arquivos locais
disponíveis na fase de diagnóstico. Não houve acesso ao portal real nem foi
solicitada outra varredura de duas horas. Todos os cenários novos são fabricados,
com navegador simulado, HTML local, transporte simulado ou rotas interceptadas.

As causas confirmadas no código foram:

- cada URL bloqueada diferente gerava mensagem, incluindo parâmetros;
- comparadores puros podiam propagar `ValueError` de URL;
- o worker convertia salvamento parcial em status `concluido`, 100%, erro vazio;
- recuperação preenchia variações e referências com listas vazias;
- falha fatal podia voltar à mesma URL indefinidamente entre retomadas;
- rotas documentais e mídia sem extensão precisavam de mais contexto;
- seleção de exportação e PDF ainda não existiam;
- a fila já deduplicava páginas, mas faltavam métricas e havia normalização
  sintática repetida de URLs.

## Resumo por melhoria

| Nº | Implementado | Evidência e limite |
|---|---|---|
| 1 | Bloqueios por categoria, domínio, método e motivo; resumos periódicos/finais. Exemplos sem query/credenciais, limitados a 20 por grupo. | Teste de 2.200 bloqueios sem token nos diagnósticos; total preservado inclusive após migração. Não altera decisões da política. |
| 2 | Domínio/porta/controles validados; comparadores retornam não equivalência em referências inválidas; pendência com origem e razão, continuando os demais pares. | URLs relativas resolvidas no contexto de origem. Invalidade não é tratada como equivalência ou ausência global. |
| 3 | Status `concluido`, `parcial`, `interrompido` e `erro`; erro e contadores preservados. Recuperação de falha continua sendo falha, com relatório parcial disponível. | Estado do processo e situação da análise são dimensões diferentes. Salvar com sucesso não conclui a varredura. |
| 4 | Recuperação reaproveita editoriais, referências, fila, visitados, métricas, divergências e andamento. Escrita atômica; bruto existente não é sobrescrito. | Quando já existe bruto, a recuperação adicional fica em `recuperacao_<id>.json`. Não é transação única entre todos os arquivos. |
| 5 | Mesmo checkpoint versionado; até duas tentativas fatais por par entre retomadas. Após a segunda, o par fica falho e outros ramos permanecem disponíveis. | Reinício é explícito. Falhas controladas continuam inconclusivas; não são repetidas infinitamente. |
| 6 | Classificação de documento, mídia, auxiliar, navegação e inconclusivo por extensão/contexto e MIME de HEAD. | Prévia editorial não vira documento só por `/documents/d/`. PDF versus imagem preserva divergência de tipo observada. Nenhum corpo é lido. |
| 7 | Analytics bloqueado isoladamente não torna a comparação falha. reCAPTCHA/consentimento e componentes afetados mantêm limitação explícita. | Diferenças no componente protegido podem ficar inconclusivas; opções fora dele, como ÁUDIOS, continuam relevantes. Não se libera método ou origem. |
| 8 | Gaveta nativa “Opções avançadas”, fechada e com opções desmarcadas no carregamento inicial. | Identificadores e payloads existentes das opções foram preservados. Teclado funciona pelo `details/summary` nativo. |
| 9 | Campo visual de nome removido. Nome por metadado do site, título inicial ou domínio. | Backend, histórico, checkpoint e relatórios antigos conservam `site_nome`. Nome automático é identificação, não prova de qual ambiente está correto. |
| 10 | Nomes sanitizados com site, escopo, data da execução e sufixo do ID; salvamento via File System Access quando disponível. | Sugestão de pasta é melhor esforço do navegador; fallback é download normal, sem promessa de diálogo nativo ou pasta persistente. |
| 11 | Seleção por comparação em arquivo auxiliar; grupos/membros, CSV/HTML/PDF/JSON, escopos e evidências portáteis. | Seleção não confirma nem reclassifica. Excluídos ficam fora. PDF local; imagens têm limites explícitos. |
| 12 | Estruturas existentes mantidas; caches limitados para funções puras de URL; novos contadores de deduplicação e tempo. | Não se reutiliza coleta integral sem prova. `paginas_reutilizadas=0` é intencional; não se inventa economia a partir de componentes. |

## Fases B e C — estabilidade e classificação

`security.registrar()` agrega os bloqueios e remove query, fragmento e usuário
das URLs de exemplo. Parâmetros de caminho como `;jsessionid` são removidos;
segmentos muito longos são substituídos por identificador.
Os contadores incluem também pedidos sem exemplo armazenado. `security.restaurar()`
migra os dados antigos na memória e preserva o total; o checkpoint original
permanece intacto. Campos de domínio/categoria/motivo continuam investigáveis.
Frequências de cada URL de exemplo também são preservadas; migrar novamente o
mesmo diagnóstico não altera suas contagens.
Isso reduz a exposição, mas caminhos, logs e relatórios locais ainda podem
conter informações do portal e precisam de proteção pelo usuário.

`url_limpa()` valida esquema HTTP/HTTPS, domínio, porta e caracteres inválidos.
O comparador não considera duas URLs inválidas equivalentes. Referências
relativas válidas são resolvidas usando a página de origem; as inválidas têm
pendência e não interrompem outras páginas. Parâmetros `c`, `e` e demais queries
funcionais continuam significativos. Fragmentos mantêm a política conservadora
da entrega anterior.

O filtro Playwright mantém os mesmos métodos, ações e escopos de segurança.
Não foi criado um allowlist que libere Analytics ou reCAPTCHA: a mudança é de
diagnóstico e interpretação. reCAPTCHA pode continuar bloqueado na varredura
passiva. Nos componentes identificados como dependentes, a observação não vira
defeito funcional comprovado. Consentimento ou recurso desconhecido pode afetar
a renderização e mantém aviso conservador.

O worker usa `checkpoints.recuperar()` para reconstruir a projeção parcial,
aproveitando dados da raiz legada e do estado retomável. A fila completa continua
no checkpoint; a projeção recuperada também informa fila/visitados. Versão e
integridade são validadas antes de retomada. Campos novos são opcionais para
ler checkpoints anteriores compatíveis; checkpoints sem fila restaurável não
passam a ser retomáveis por suposição.

Um erro mantém `status=erro`, `estado_execucao=falha` e situação da análise
parcial. O relatório e o diagnóstico permanecem acessíveis. A interface não
fica tentando abrir um relatório inexistente quando só existe diagnóstico.
Percentuais de encerramentos incompletos ficam abaixo de 100%; contadores
reais são mostrados separadamente. Clientes da API devem reconhecer os estados
terminais adicionais `parcial` e `interrompido`.

`resources.classificar()` usa evidência de caminho, contexto HTML e MIME seguro.
Imagens/prévias e fontes/scripts não recebem automaticamente a finalidade de
documento relevante. Referências desconhecidas ficam inconclusivas. Se um lado
responde PDF e o outro imagem, a diferença de tipo é registrada sem comparar
conteúdo binário ou declarar culpa de PRD/DES. Links de menu para mídia continuam
tendo os destinos comparados: evitar abrir um JPG não oculta uma opção que aponta
para outro JPG. A regressão desse caminho primeiro falhou, antes da correção.

## Fase D — revisão, escolha e exportação

### Seleção independente

O checkbox “Exportar” chama a API local e grava `selecoes_<id>.json`, ao lado
dos arquivos auxiliares de revisão. Ao reabrir ou usar F5, os IDs são restaurados.
Marcar um grupo seleciona seus membros visíveis; seleção parcial de um grupo
é exibida como indeterminada. IDs gerados com mais de cinco dígitos também são
aceitos. Excluir uma DIV impede sua exportação, mesmo que seu ID tenha sido
selecionado anteriormente. Decisões de seleção também acompanham a retomada.

Selecionar não cria confirmação, não muda relevância e não altera o bruto. CSV
selecionado tem uma linha por grupo consolidado, com IDs e resumo dos membros,
sem duplicar a mesma ocorrência. O escopo completo preserva a visão detalhada.
CSV mantém BOM UTF-8, delimitador `;` e proteção de células contra fórmulas.

### Nomes e salvamento

Nome sugerido: `SEFAZ_DIVs_Selecionadas_2026-10-23_abcdef.csv`, por exemplo.
A data identifica a execução e o sufixo evita colisão entre execuções. Nomes
reservados e caracteres inválidos no Windows são tratados; URLs, e-mails e
padrões numéricos reconhecidos são removidos do nome sugerido. A ferramenta
não consegue garantir que todo título arbitrário do site esteja livre de dados
sensíveis; revise o nome antes de compartilhar.

Em navegadores compatíveis, `showSaveFilePicker()` é chamado a partir do clique,
com ID estável de preferência e último handle disponível nesta página. O próprio
navegador pode lembrar a pasta entre visitas; não há garantia ou acesso irrestrito
ao disco. Se o arquivo escolhido já contém dados, existe confirmação explícita
antes da escrita. Cancelar o seletor não provoca um download em outro lugar.

Sem suporte, o navegador recebe um download com nome amigável. Para exibir
sempre “Salvar como”, configure **Perguntar onde salvar cada arquivo** no
Chrome/Edge. A ferramenta não consegue forçar essa preferência do navegador.
Não foram alterados os caminhos de relatórios brutos, históricos ou checkpoints
para implementar a preferência. Exportações de download usam pasta temporária
isolada e não mantêm o lock da varredura durante a conversão PDF.

### Portabilidade e PDF

HTML incorpora capturas PNG locais válidas, inclusive de membros dos grupos,
com até **3 MB por captura** e **20 MB de imagens brutas por exportação**.
Arquivos fora da pasta autorizada, ausentes, inválidos ou excedentes recebem
indicação de indisponibilidade; não há carregamento remoto de imagens.
Links para páginas são preservados. Diagnósticos auxiliares referenciados em
relatórios antigos podem exigir os arquivos da instalação original.

PDF usa o Chromium/Playwright já instalado. O HTML é carregado localmente em
processo separado, sem JavaScript e com requisições bloqueadas. Traz nome,
ambientes, data, resumo, DIVs do escopo escolhido, links e capturas disponíveis.
O processo de conversão tem orçamento de 60 s; falha não altera os originais.
PDF não depende de serviço de conversão, bibliotecas de escritório ou upload.

JSON de download é autocontido, identifica o escopo e mantém os dados
estruturados exportados. Formatos internos v1/v2 e diagnósticos JSON/TXT
continuam disponíveis. Exportação selecionada não inclui as DIVs excluídas ou
os outros registros não escolhidos. O relatório original continua completo no
disco, separado da exportação. O escopo selecionado usa uma lista explícita de
campos de contexto e métricas resumidas: não copia o DOM das releituras, sinais
editoriais ou revisões de DIVs fora da seleção.

## Fase E — deduplicação e desempenho

O crawler continua usando a fila existente e seus conjuntos de descobertos e
visitados. Menus de cada página continuam comparados, ainda que seus links
apontem para a mesma página já visitada. Rótulos e seções diferentes continuam
sendo diferenças possíveis. Não são eliminadas páginas por semelhança de título,
DOM ou caminho. Não foi introduzida exploração externa.

Caches de no máximo 8.192 entradas reutilizam somente resultados puros para
os mesmos argumentos: normalização, classificação por caminho e comparação
sintática de URLs nos mesmos ambientes. Eles não comprovam igualdade de página,
não mudam permissões e não dispensam coleta por aparência.

Diagnóstico inclui `links_encontrados`, pares únicos/comparados/falhos/pendentes,
`urls_duplicadas`, `normalizacoes_reaproveitadas`,
`comparacoes_url_reaproveitadas`, `paginas_reutilizadas`, `divs_consolidadas`
e tempos. Links contam referências nos estados de página adotados; duplicações
evitadas contam pares já conhecidos, não necessariamente toda repetição textual.
Tempo editorial/paginação é heurístico por rota/rótulo. Contadores de cache
medem atividade do processo; outras consultas locais concorrentes podem afetar
seus deltas. Não representam tempo economizado nem requisições evitadas.

### Resultados controlados contra `f7ba62e`

Três repetições alternadas por versão, sem suíte pesada simultânea, em Linux e
Python 3.12.14. Medianas do tempo total de cada cenário:

| Cenário | Referência | Atual | Resultado |
|---|---:|---:|---|
| Chromium, três páginas por ambiente, DOM estável | 4,370 s | 4,415 s | 1,02% mais lento; nenhum ganho demonstrado |
| Chromium, três páginas por ambiente, conteúdo dinâmico | 12,445 s | 12,484 s | 0,31% mais lento; nenhum ganho demonstrado |
| Grafo simulado, 1.000 pares, 30 links repetidos por página | 6,089 s | 4,158 s | Redução de 31,72% somente nesta carga de CPU |

Nos três cenários, cobertura e achados observados foram equivalentes. O grafo
manteve 2.000 aberturas simuladas, 1.000 pares comparados e 30.000 duplicações
evitadas nas duas versões. A versão atual contabilizou 62.003 links, 439.999
acertos de normalização e 31.002 comparações de URL reaproveitadas; nenhuma
coleta integral de página foi reutilizada. O hash confere os itens/contextos,
aberturas e divergências do cenário, não todo comportamento futuro do site.

Dados reproduzíveis: [navegação Chromium](benchmark-12-navegacao.json) e
[grafo/deduplicação](benchmark-12-deduplicacao.json). O tempo de navegador é
dominado por navegação e preparação; a diferença pequena não comprova regressão
ou aceleração geral sem mais amostras. Não há evidência para prometer redução
de 50% nem ganho em SEFAZ/CGE real. Não foi medida taxa formal de falsos positivos
com revisão humana, consumo de memória ou custo de checkpoints em portais reais.

## Arquivos e funções principais

| Arquivo | Responsabilidade |
|---|---|
| `ambidiff/security.py` (novo) | Categoria, URL de diagnóstico, agregação, resumo e migração de bloqueios. |
| `ambidiff/core.py` | `url_limpa`, validação/cache, metadados do nome do site, extração dos componentes protegidos e `inferir_site`. |
| `ambidiff/paired.py` | `executar_pareado` e helpers locais `validar_itens`/`registrar_fatal`; wrappers/cache de `link_equivalente`, `imagem_equivalente` e `e_arquivo`; metadados em `_extrair_page`. |
| `ambidiff/checkpoints.py` | `recuperar`, mantendo projeção e dados do checkpoint. |
| `ambidiff/resources.py` (novo), `documents.py` | `classificar`, `Documentos._conferir`/`comparar`: classificação sem corpo e diferenças observadas de MIME. |
| `functional.py`, `relevance.py` | `_um_clique`/`classificar`: diagnóstico limitado pela automação e classificação inconclusiva. |
| `storage.py` | `ler_selecao`, `selecionar`, `somente_selecionadas`, `preparar_relatorio`, `excluir_execucoes`: seleção persistente, membros, exclusões e compatibilidade de IDs. |
| `reports.py` | `exportar` e helper `incorporar`: escopo selecionado, CSV deduplicado e capturas seguras. |
| `exports.py`, `pdfexport.py` (novos) | `nome_amigavel`, `gerar_pdf`, `converter`: nome sanitizado e conversão PDF local. |
| `smart.py` | Explicação das métricas de deduplicação. |
| `web/server.py` | `worker`, `percentual_final`, `estado_publico`, `atualizar`, `comparar`, `retomar`, `selecionar_div`, `baixar`: estados, erro, seleção e downloads. |
| `web/static/app.js` | `renderNext`, `selectionSummary`, `downloadExport`, `poll`, `displayReport`, `updateProgressInfo`, `normalizedDivSearch` e handlers: seleção, salvamento, status e parciais. |
| `index.html`, `style.css` | Opções avançadas, ausência do campo de nome e descrição dos formatos. |
| `tests/test_update12.py` | Regressões de estabilidade, recursos, exportação, PDF e deduplicação. |
| `tests/test_intermat.py` | Extensão da fixture de grafo, mantendo as asserções anteriores. |
| `scripts/benchmark_dedup.py` (novo) | Benchmark controlado de CPU em grafo com links repetidos. |

## Verificação e comandos

As fases foram verificadas antes de avançar: baseline de 161 testes; estabilidade
com suíte de 166 testes e seis regressões novas direcionadas; classificação com
sete direcionadas; interface/exportação com suíte de 171 testes e PDF real local;
deduplicação com testes de consultas significativas e grafos repetidos. A rodada
final incorpora também migração de contagens e IDs longos.

**Resultado final: 177 testes aprovados em 92,361 s, sem falhas ou testes
ignorados** (161 existentes + 16 novos). As 16 regressões novas direcionadas
aprovaram em 8,666 s após a proteção dos links de mídia e das frequências dos
exemplos de bloqueio. `node --check` e
`git diff --check` também passaram. O teste que reproduziu a regressão de
mídia falhou antes da correção e passou depois.

### Cenários obrigatórios e rastreabilidade

| Cenário solicitado | Testes locais de referência |
|---|---|
| 1 — ÁUDIOS exclusivo e sentidos | `test_update12.StabilityTests`, `test_perf.ComparisonPerfTests`, `test_smart` |
| 2 — Rótulos diferentes e destino igual | `test_next.BrowserNextTests.test_nomes_html_diferentes_mesmo_destino_mantem_rotulo_divergente` |
| 3 — Destinos repetidos em vários menus | `test_update12.DeduplicationTests` |
| 4 — Destino diferente interrompe só o ramo | `test_v12.TestsV12.test_fluxo_nao_entra_no_link_diferente` |
| 5 — Externos conforme permissões | Casos HEAD, bloqueio de privados, autorização e cancelamento de `test_next.py` |
| 6 — Documentos versus imagens | `test_update12.ResourceTests`, `test_smart.DocumentTests` |
| 7 — Defasagem sem ocultar estrutura | `test_v15.py`, templates estruturais de `test_smart.py` e caso ÁUDIOS |
| 8 — Ciclos | `test_intermat.ExecutionTests.test_ciclo_voltar_e_repeticao_nao_ampliam_cobertura` |
| 9 — URL inválida isolada | `test_update12.StabilityTests.test_referencia_invalida_preserva_os_demais_pares` |
| 10 — Falha, salvamento e retomada | `test_update12.StabilityTests` e `test_intermat.ExecutionTests` |
| 11 — Bloqueios auxiliares | `test_update12.BrowserStabilityTests`, agregação e migração em `StabilityTests` |
| 12 — Falha da automação inconclusiva | `test_intermat` (extração isolada) e `test_perf` (classificação da automação) |
| 13 — Seleção após F5 | `test_update12.BrowserExportTests` |
| 14 — CSV selecionado sem duplicatas | `test_update12.ExportTests.test_selecao_persistente_grupo_exclusao_e_csv_sem_duplicar` |
| 15 — PDF/HTML e evidências | `test_update12.ExportTests.test_nomes_windows_e_pdf_html_portateis_com_evidencia_local` |
| 16 — Formatos antigos | `test_smart` (interface/API antiga), `test_intermat` (v2 e retomada), `test_relevance` |
| 17 — Ausência de escritas | `test_next.py` (requisição de escrita não atinge transporte), `test_v15.py` (candidatos inseguros) |

São nomes de métodos/arquivos, para localizar cenários na suíte; alguns cenários
reutilizam regressões existentes, sem enfraquecer suas asserções. Não são testes
nos portais institucionais reais.

### Revisão de segurança e compatibilidade

- A política de métodos/ações e escopos foi mantida; requisições inseguras
  continuam bloqueadas. Os testes não acessaram portais corporativos.
- Nenhuma dependência nova: PDF reutiliza Playwright/Chromium e conversão local.
  O HTML gerado é escapado; CSV mantém proteção contra fórmulas.
- Incorporação de evidências valida raiz resolvida, extensão, assinatura PNG e
  tamanho. Caminhos externos/symlinks fora da raiz não são incorporados.
- Downloads selecionados não carregam registros não escolhidos ou DOM de
  releitura. Brutos e diagnósticos continuam no disco local; seu conteúdo requer
  revisão humana antes de qualquer compartilhamento autorizado.
- Checkpoints v1, relatórios v1/v2, campos internos de nome e decisões de revisão
  continuam compatíveis nos cenários automatizados. Arquivos são gravados
  atomicamente; não existe uma transação única para toda a pasta.
- A checagem dos 24 arquivos da entrega não encontrou padrões de chave privada,
  token GitHub ou chave AWS; somente código, testes e documentação/benchmarks
  sintéticos estão na alteração. Não substitui uma auditoria formal.
- A validação foi em Linux. Compatibilidade nativa com Windows, diálogo real
  “Salvar como” e comportamento de portais autorizados permanecem pendentes.

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests -v
node --check web/static/app.js
git diff --check
python -B scripts/benchmark_perf.py --baseline /tmp/ambidiff-12-baseline --pages 3 --repetitions 3
python -B scripts/benchmark_dedup.py --baseline /tmp/ambidiff-12-baseline --pages 1000 --repetitions 3
```

Os benchmarks devem rodar sem testes pesados simultâneos. O checkout separado
de referência é `f7ba62e`. O grafo usa navegador simulado e mede CPU; o benchmark
de navegação usa Chromium e portais loopback sintéticos. Ambos conferem cobertura
e achados, sem usar redução da quantidade de DIVs como indicador isolado.

## Teste local no Windows e pendências

Use a branch `perf/otimizacao-varredura` após o envio autorizado, seguindo o guia
de atualização por Git do README. Preserve a instalação anterior e os dados
locais antes de atualizar. A `main` não é a referência desta entrega.

```cmd
instalar.bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
INICIAR_AMBIDIFF.bat
```

1. Abra `http://127.0.0.1:8765`. Confira URLs vazias, identificação automática e
   gaveta avançada fechada, com ambas as opções desmarcadas.
2. Use páginas locais ou portais autorizados; verifique ausência nos dois
   sentidos, rótulos distintos, ÁUDIOS e referências documentais/mídia.
3. Interrompa e retome uma execução de teste. Confira fila, pares concluídos,
   falhos, erro e parcial sem 100% de conclusão fictícia.
4. Selecione uma DIV e um grupo. Recarregue a página; confira seleção e revisão
   independentes. Exclua um membro e confirme que não sai na exportação.
5. Exporte CSV, HTML, PDF e JSON selecionados/completos. Abra HTML fora da pasta
   e PDF num leitor local; confira nomes, links, imagens e os avisos de ausência.
6. Teste Salvar como no Chrome/Edge, cancelamento, arquivo existente e fallback
   com a API indisponível. A pasta lembrada depende das permissões do navegador.

Não houve validação nativa no Windows nem em portais reais. Limitações de DNS,
autenticação, HEAD não suportado, scripts tardios e controles não seguros
permanecem explícitas. Não se contorna autenticação nem se altera a política para
obter aparente sucesso. Os formatos binários dos documentos não são inspecionados.

## Registro do planejamento e envio autorizado

- `fix: preservar falhas e dados na recuperação de varreduras`
- `fix: classificar bloqueios, URLs e recursos sem falsos defeitos`
- `feat: selecionar DIVs e exportar PDF local com salvamento amigável`
- `perf: reutilizar comparações puras de URL e medir deduplicação`

As sugestões acima pertencem ao planejamento inicial. O mantenedor autorizou
um único commit para esta entrega, com a mensagem:

`feat: implementar 12 melhorias de estabilidade, interface e desempenho`

O envio é restrito à branch `perf/otimizacao-varredura`. Merge na `main`, deploy
e GitHub Pages não estão autorizados.

Antes do envio autorizado, a suíte completa foi executada novamente:
**177 testes aprovados em 92,878 s, sem falhas ou testes ignorados**.
`node --check web/static/app.js` e `git diff --check` também passaram.
A revisão dos 24 arquivos não identificou remoções funcionais inesperadas nem
credenciais reais; a URL com usuário/senha em teste é uma referência sintética
inválida do domínio `.test`. Os JSONs de benchmark contêm cenários fabricados.
Logs, checkpoints, históricos e relatórios internos de execução não fazem parte
do commit. A validação segue local, sem testes em portais corporativos reais.
