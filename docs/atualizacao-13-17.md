# AmbiDiff — melhorias 13 a 17

Entrega de 27/10/2026, base `b71d90f713141888163366b934807d49ca927550`
da branch `perf/otimizacao-varredura`. HEAD e diretório estavam limpos e iguais
ao remoto antes de começar. Não havia `AGENTS.md` disponível. README, relatório
das 12 melhorias, módulos e testes existentes foram revisados. Após a revisão
local, o mantenedor autorizou commit e envio somente para essa branch.
**Não há merge na `main`, deploy ou GitHub Pages.** As 12 melhorias permanecem.

## A — diagnóstico e referência

Baseline: **177 testes aprovados em 92,776 s**, sem falhas/ignorados. A comparação
é funcional; não foi medida porcentagem de cobertura de linhas/branches.

Não há relatório/log original da SEFAZ identificado no ambiente. Os números de
3h41min52s, 511 checkpoints e aproximadamente 53 minutos em checkpoints foram
informados pelo mantenedor e orientam hipóteses, mas não são um benchmark deste
trabalho. Não é possível contar DIVs reais de compartilhamento ou suas ocorrências
sem o relatório. Nenhum portal corporativo foi acessado.

Confirmado no código:

- `snapshot()` repetia `asdict()` sobre todas as páginas anteriores. A assinatura
  serializava o estado, e a escrita voltava a serializar um envelope extenso, com
  indentação. Havia gatilhos por tempo e por 20 pares; o segundo não renovava o
  relógio do primeiro. O custo crescia com o estado.
- Compartilhamento já era reconhecido para `Redirecionamento`, mas não para
  `Destino verificado`. O teste de origens usava um conjunto, sem exigir que cada
  destino correspondesse ao lado correto. Fragmentos e subpastas exigiam cuidado.
- A fila já deduplicava e priorizava. Ela não controlava o aprofundamento
  editorial; a estratégia completa podia seguir centenas de notícias. Rótulos
  dos ancestrais podiam rebaixar um serviço encontrado dentro de uma notícia.
- A exportação funcionava com relatório aberto, mas o erro de seleção vazia era
  colocado em `form-error`, que fica na outra tela. Aparência e feedback eram
  pouco claros. Seleção individual existia; faltava operação em lote.

Não confirmado: qual parcela dos 53 minutos reais foi disco, serialização, DOM
armazenado, antivírus ou infraestrutura Windows. A instrumentação nova permite
investigar isso numa execução posteriormente autorizada.

## B — melhoria 13: checkpoints

Mantido o formato JSON/checksum v1 e a retomada existente. `PaginasSerializadas`
converte cada objeto de **página concluída** uma vez; uma nova coleta substitui o
objeto e invalida a entrada. Não reaproveita evidência entre páginas distintas.
Resultados, editoriais, documentos, fila, visitados, falhas, métricas, configuração
e diagnósticos continuam no estado. Não foi criado journal ou banco adicional.

`checkpoints.gravar()` escreve JSON compacto em temporário único na mesma pasta,
faz flush/fsync, fecha e só então executa `os.replace`. Se escrita/substituição
falhar, o arquivo válido anterior permanece e o temporário é removido. Isso não
é uma transação única entre todos os arquivos, nem proteção contra qualquer
falha física do armazenamento.

Um agendamento único substitui os dois gatilhos: intervalo de pelo menos 30 s,
adaptado ao custo anterior (`custo × 20`, até 120 s). Inicial, encerramento e falha
fatal forçam uma tentativa; interrupção conserva o parcial. Erros de escrita são
registrados e não fazem uma varredura falhar silenciosamente nem apagam o último
checkpoint. Uma queda abrupta pode perder trabalho desde o último arquivo válido.

Métricas:

| Campo em `metricas.tempos_segundos` | Interpretação |
|---|---|
| `checkpoint` | Total das tentativas de checkpoint na varredura |
| `checkpoint_conversao_paginas` | Conversão das páginas novas/substituídas |
| `checkpoint_construcao_exclusiva` | Construção restante do snapshot, excluindo conversão e assinatura |
| `checkpoint_assinatura_json` | JSON canônico e SHA-256 da integridade |
| `checkpoint_serializacao_json` | JSON de saída para gravação |
| `checkpoint_gravacao` | Escrita, flush/fsync e substituição |
| `checkpoint_recuperacao_validacao` | Recuperação/validação numa retomada |
| `checkpoint_recuperacao_em_falha` | Projeção recuperada pelo worker após exceção |

**Não some o total `checkpoint` às suas subetapas.** O trabalho adicional pode
ser observado pela diferença entre total e fases exclusivas; recuperação é outra
operação. Contagens registram tentativas, sucessos, falhas, bytes e conversões
reutilizadas. Num checkpoint, métricas de I/O refletem salvamentos já terminados;
o relatório final inclui a última tentativa também. A versão anterior não media
todos os gatilhos; o benchmark usa medição externa para comparação justa.

`ate_primeira_div_relevante` preserva o valor já medido quando ele existe no
checkpoint. Sem esse campo num checkpoint antigo, mede a primeira observação
da etapa atual; não reconstrói o instante histórico da descoberta original.

O cache mantém estruturas serializadas em memória: há troca de memória por CPU.
A assinatura e a escrita ainda são completas e crescem com o estado. Não foi
eliminada a verificação de integridade para obter ganho artificial.

## C — melhoria 14: compartilhamento

Evolução de `_share_equivalent()` via `evidencia_compartilhamento()`. Padrões
explicitamente reconhecidos: Facebook (`facebook.com`/`www.facebook.com`,
`/sharer/sharer.php`, parâmetro `u`) e Twitter/X (`twitter.com`,
`www.twitter.com`, `x.com`, `/intent/tweet`, parâmetro `url`). Os dois lados
precisam usar o mesmo endpoint conhecido; não é uma regra genérica de rede social.

A referência compartilhada é validada, precisa estar na origem e subpasta do
seu ambiente, com caminho, query relevante e fragmento correspondentes. Só se
normalizam codificações percentuais de caracteres não reservados; `%2F` não vira
um separador. Destinatário repetido em ambiente errado, alvo diferente, URL
inválida, endpoint desconhecido, ausência de botão e acesso observado como falho
continuam sendo diferenças relevantes. Isso não presume PRD correto.

Equivalências ficam em baixa relevância e no diagnóstico, com destinos,
evidências e limite da conclusão. O bruto não é apagado. Revisão manual continua
prevalecendo. A tela informa separadamente grupos e ocorrências; disponibilidade,
clique e intenção editorial não são comprovados pela equivalência sintática.

## D — melhoria 15: padrão progressivo

Fluxo padrão do painel: informar URLs e clicar **Iniciar varredura**. Estratégia
progressiva e reconhecimento estático habilitados; orçamento de **20 minutos por
etapa**, configurável em Opções avançadas. `0` remove o orçamento; a estratégia
**profunda** remove a cota de exploração editorial, mantendo os demais limites.
Métodos seguros, escopo, autenticação/CAPTCHA, HEAD e cliques optativos não foram
relaxados.

A `Fila` existente mantém prioridade, antiguidade, descobertos e deduplicação.
Controles de serviços, consultas, instituições, legislação, normativos e ÁUDIOS
prevalecem sobre sinais de paginação. Usa-se o rótulo atual para não rebaixar um
serviço somente porque seu ancestral era uma notícia.

Áreas editoriais identificadas por rotas/contexto têm até **três representantes
por grupo e etapa**. Os demais pares são adiados dentro da própria fila e salvos.
Isso é política de escopo, **não prova de equivalência de templates**. Não se
declara que publicações não abertas foram verificadas. `/w/` do Liferay, sozinho,
não autoriza adiamento: exige contexto editorial observado no link de origem.
Rótulos/rotas importantes são exceções conservadoras. Parâmetros `c`/`e` continuam
distintos. Links presentes nas páginas visitadas são comparados antes de decidir
o aprofundamento; opções diferentes não desaparecem por compartilhar destino.

Não há limite funcional fixo de pares. Permanecem os limites preventivos de
memória/falhas existentes. Portais com mais de mil páginas importantes continuam
elegíveis, sujeitos ao orçamento e às condições de acesso.

Ao esgotar orçamento ou representantes elegíveis, a execução encerra de forma
cooperativa, salva o parcial e mantém os pares pendentes. Não se sinaliza parada
manual para representar orçamento: os estados existentes continuam distintos,
com `motivo_encerramento=orcamento` ou `estrategia_editorial`.

`cobertura` distingue DOM aprofundado, DOM estrutural, não inspecionados,
representantes e importantes ainda pendentes. DOM aprofundado não significa
validação integral de funcionamento. Progresso é **da fila conhecida**, não do
site inteiro. Descoberta pode aumentar os pendentes legitimamente. O painel
separa tempo acumulado de orçamento restante da etapa.

**Retomar** preserva pares concluídos e resultados, e escolhe representantes
novos entre os pendentes. **Continuar aprofundando** remove a cota editorial e
usa o orçamento das opções avançadas. A nova execução mantém vínculo com a
anterior, checkpoints, revisão, exclusões e seleção. A amostragem fica registrada
por segmento. Alterar ambientes ou opções incompatíveis é recusado, preservando
o arquivo. Uma retomada pode renovar orçamento e evoluir de progressiva para
profunda; não pode rebaixar uma execução profunda para progressiva.

Limitação fundamental: uma notícia adiada pode conter um defeito ou link próprio
que só será descoberto quando ela for aberta. Representantes não garantem a
ausência desses problemas. Use aprofundamento posterior quando necessário. A
meta de uma primeira comparação útil em 15–20 minutos na SEFAZ ainda depende de
validação real autorizada no Windows.

## E — melhorias 16 e 17: exportação e seleção em massa

Os quatro formatos têm foco, hover, estado desabilitado e processamento. Mensagens
de disponibilidade, seleção vazia, sucesso, cancelamento e erro ficam junto da
exportação, na tela de resultados. Sem relatório, a tela explica a indisponibilidade.
Nomes amigáveis, seletor de arquivos, fallback, CSV para Excel, HTML portátil,
PDF local, JSON e originais preservados permanecem.

Três ações: **Marcar todas do relatório**, **Marcar apenas as filtradas** e
**Desmarcar todas**. Todas inclui registros não renderizados; filtradas inclui
todos os resultados e preserva seleção fora deles. Grupos expandem IDs dos
membros; excluídos não são elegíveis. Estado parcial de grupo é indeterminado.
Seleção não confirma, exclui nem reclassifica DIVs.

Uma requisição pequena leva a ação/filtros ao backend, que valida a comparação e
os IDs/grupos elegíveis e grava `selecoes_<id>.json` atomicamente, sob o lock
local. Não há milhares de chamadas nem necessidade de ampliar o limite global
de corpo HTTP. Falha de escrita conserva seleção anterior e a tela se sincroniza
com o estado salvo. Seleção individual permanece; durante escrita o controle é
desabilitado e o resultado confirmado pelo servidor.

Filtros de texto/ID, categoria, ambiente, tipo, revisão e baixa relevância seguem
a semântica existente da tela. Busca por ID ignora categoria/lado/tipo, mas não
revisão/visibilidade. F5 e reabertura preservam IDs; retomadas compatíveis copiam
o arquivo auxiliar. Bruto, confirmações e classificação não são alterados.

## Compatibilidade e APIs

- Relatórios v1/v2, histórico, IDs e overlays continuam legíveis.
- Checkpoints anteriores com estado retomável são lidos sem regravação do
  original. Na ausência dos novos campos, retomam como profundos e sem orçamento,
  preservando o contrato anterior. Campos novos de estratégia são opcionais na
  leitura v1; leitores antigos podem recusar sua configuração com segurança.
- `POST /api/comparar` aceita `estrategia` (`progressiva`/`profunda`) e
  `orcamento_minutos` (número 0–1440). O padrão mudou intencionalmente para
  progressiva/20. Para exploração completa use profunda/0. O campo interno
  `varredura_inteligente` é preservado; representa reconhecimento estático.
- `POST /api/retomar/<id>` aceita `aprofundar: true` e orçamento opcional.
- `PUT /api/relatorio/<id>/selecao` recebe `acao` (`todas`, `filtradas`, `limpar`)
  e `filtros` opcionais. A API individual anterior continua disponível.
- Dados de cobertura são aditivos; clientes não devem interpretar a porcentagem
  da fila como conclusão global. Não houve dependência nova.

## Testes, falhas intermediárias e benchmarks

Regressões novas em `tests/test_update17.py`; cenários existentes continuam na
suíte. A fixture de grafo aceita opções adicionais. No teste de comparação dos
templates antigos, os dois modos são explicitamente profundos para manter a
mesma cobertura e todas as asserções; o teste de interface agora exige o novo
padrão habilitado.

Ocorrências intermediárias não foram ocultadas:

- Um comando direcionado usou o nome errado de uma classe de teste; corrigido.
- O teste de UI revelou restauração prematura do checkbox, corrigida no código.
- A simulação de cancelamento retornava uma função que o Playwright executava
  cedo demais; corrigida a fixture, mantendo o cenário de cancelamento real.
- A primeira suíte completa (194 testes) teve uma falha: a expectativa antiga de
  quatro inspeções profundas omitidas conflitou com a amostragem padrão.
  Corrigido o escopo explícito do teste, sem reduzir a asserção.
- A primeira rodada de benchmarks teve processos sobrepostos; esses tempos
  foram descartados. A série final roda sequencialmente. Memória é medida sem
  cProfile, numa execução separada com volume declarado.

**Suíte final: 198 testes aprovados em 101,368 s, sem falhas ou ignorados**:
177 anteriores e 21 novos. Depois, a asserção de equivalência no diagnóstico
também foi executada nos dois testes de compartilhamento: aprovados em 0,004 s.
`node --check web/static/app.js`, compilação dos Python alterados e
`git diff --check` passaram. Não foram feitos testes em produção.

### Checkpoints: conteúdo integral recuperado

Três snapshots do mesmo estado por volume (primeiro frio), com páginas novas e
DIVs fabricadas. A mediana captura reutilização de páginas inalteradas; a primeira
amostra também está no JSON. Assinatura, escrita e leitura/validação são reais.
Depois de ler, o benchmark exige **igualdade de todo o estado**, não só contagens.

| Páginas por ambiente | Antes | Depois | Redução do total |
|---:|---:|---:|---:|
| 50 | 0,035410 s | 0,009568 s | 72,98% |
| 200 | 0,144991 s | 0,041727 s | 71,22% |
| 800 | 0,581720 s | 0,158619 s | 72,73% |

A maior economia veio da conversão reaproveitada e da serialização compacta;
assinatura e tempo de armazenamento permaneceram próximos. Para 800 páginas por
ambiente, o arquivo passou de aproximadamente 22,40 MB para 12,42 MB, preservando
o conteúdo lógico. Isso não comprova como disco/antivírus Windows se comportarão.
Tempos de conversão, assinatura, JSON, escrita/metadados e validação estão
separados em [benchmark de checkpoints](benchmark-17-checkpoints.json). As
medianas de subetapas não precisam somar a mediana total.

### Estratégias: custo e cobertura declarados

Três repetições alternadas contra `b71d90f`, em subprocessos isolados, navegador
e extração simulados, com arquivo de checkpoint real. `cProfile` mede construção
e assinatura; o callback mede serialização/escrita separadamente, sem somar
tempos aninhados. A instrumentação participa desses tempos. Orçamento removido
nas duas versões para isolar a estratégia; interrupção por orçamento tem testes
próprios. Não havia suíte ou outro benchmark pesado simultâneo na série final.

| Métrica | Institucional antes → depois | Editorial antes → depois |
|---|---:|---:|
| Tempo total mediano | 12,437 → 0,916 s | 2,621 → 1,012 s |
| Tempo de checkpoints | 11,644 → 0,102 s | 1,582 → 0,023 s |
| Pares descobertos | 1.005 → 1.005 | 302 → 302 |
| Pares comparados | 1.005 → 1.005 | 302 → 5 |
| Pendentes | 0 → 0 | 0 → 297 |
| Notícias abertas individualmente | 0 → 0 | 300 → 3 |
| Aberturas simuladas, dois ambientes | 2.010 → 2.010 | 604 → 10 |
| Duplicações evitadas | 0 → 0 | 0 → 0 |
| Tempo até primeira DIV relevante | 0,00825 → 0,00790 s | 0,05298 → 0,05449 s |
| Tempo até controle crítico dentro de ramificação editorial | Não presente | 2,501 → 0,964 s |
| Sentinelas estruturais encontradas | ÁUDIOS nas duas | ÁUDIOS e controle crítico nas duas |
| Compartilhamentos relevantes indevidos no cenário básico | 0 → 0 | 0 → 0 |

No institucional, a redução foi **92,64% nessa carga instrumentada**, com mesma
cobertura; economia de checkpoints domina o resultado. No editorial, a redução
foi **61,37%**, com cobertura deliberadamente diferente. O controle crítico foi
observado **61,47% antes**; a primeira DIV relevante praticamente não mudou e
ficou ligeiramente mais lenta no cenário editorial. Não se usa somente redução
de DIVs para concluir qualidade. O caso básico de compartilhamento já era
reconhecido antes; as regressões novas cobrem os registros/tipos e exceções que
faltavam. Não se inventou uma contagem de falsos positivos da SEFAZ real.

Esses resultados **não** significam que as 297 notícias adiadas estavam corretas,
nem garantem que um problema exclusivo nelas seria descoberto. O teste de
continuação comprova que podem ser percorridas depois, sem repetir concluídas.
O grafo tem consultas descobertas a partir de notícias, sem ignorá-las cegamente.

Memória é medida em subprocessos separados, sem cProfile, para **200 páginas
planejadas por ambiente** (`--memory-pages 200`): pico de alocações Python de
6,57 → 4,36 MiB no institucional e 6,14 → 1,84 MiB no editorial. Não é RSS total,
não inclui Chromium e a cobertura editorial é diferente. A microcarga de
checkpoint com 800 páginas não mostrou redução material no pico de alocações de
conversão/assinatura; o cache tem custo de memória e não resolve toda escala.
Dados completos: [benchmark progressivo](benchmark-17-progressiva.json).

### Navegação real em Chromium, cenários locais pequenos

Mesmo benchmark da entrega anterior, agora contra `b71d90f`, três repetições,
três páginas por ambiente, sem captura, cliques ou checkpoints. Aqui a cobertura
e os achados foram equivalentes nos dois cenários.

| Métrica | Estável antes → depois | Dinâmico antes → depois |
|---|---:|---:|
| Tempo total mediano | 4,475 → 4,440 s | 12,484 → 12,504 s |
| Preparação | 2,536 → 2,535 s | 8,140 → 8,141 s |
| Navegação | 0,255 → 0,231 s | 0,278 → 0,239 s |
| Variação do total | Redução de 0,80% | Aumento de 0,16% |

**Não há ganho geral demonstrado na navegação do Chromium.** As diferenças são
pequenas e não justificam prometer aceleração do portal. O ganho maior está nos
checkpoints e no escopo progressivo declarado. Dados, variações e observações:
[benchmark de navegação](benchmark-17-navegacao.json). Taxa formal de falsos
positivos, memória total do navegador e a meta real de 15–20 minutos seguem
pendentes de avaliação autorizada.

Comandos no ambiente de desenvolvimento:

```bash
python -B -m unittest discover -s tests -v
node --check web/static/app.js
git diff --check
python -B scripts/benchmark_checkpoints.py --baseline /tmp/ambidiff17-baseline --pages 50 200 800
python -B scripts/benchmark_progressive.py --baseline /tmp/ambidiff17-baseline --repetitions 3 --memory-pages 200
python -B scripts/benchmark_perf.py --baseline /tmp/ambidiff17-baseline --pages 3 --repetitions 3
```

Não execute os benchmarks simultaneamente com a suíte ou outras cargas pesadas.
O checkout de referência deve ser o commit `b71d90f`. A instrumentação é local;
resultados sintéticos não devem ser extrapolados para os 53 minutos reais.

## Arquivos e funções relevantes

| Arquivo | Mudança |
|---|---|
| `checkpoints.py` | `PaginasSerializadas`, `gravar`, `empacotar`, `validar`, `recuperar`: desempenho, integridade, métricas e leitura compatível |
| `strategy.py` (novo) | `Escopo`, `grupo_editorial`, `opcoes`: política progressiva, orçamento e validação |
| `frontier.py` | `prioridade`, `Fila.adiar`, iteração: importância e fila adiada persistida |
| `paired.py` | `executar_pareado`, `snapshot`, `salvar_checkpoint`, `resumo_cobertura`, `emitir`: orquestração e continuação |
| `core.py` | `executar`: encaminhamento das opções e padrão de reconhecimento estático |
| `relevance.py` | `evidencia_compartilhamento`, `_share_equivalent`, `classificar`, `preparar`: equivalência auditável |
| `storage.py` | `filtrar_divergencias`, `selecionar_lote`, escopo selecionado com cobertura |
| `diagnostics.py`, `reports.py` | Cobertura/motivo/equivalências no diagnóstico e exportações |
| `web/server.py` | Configuração, orçamento público, writer de checkpoint, retomada e seleção em lote |
| `app.js`, `index.html`, `style.css` | Padrões, progresso, continuação, exportação e feedback da seleção |
| `test_update17.py` (novo) | Regressões locais e browser com transporte interceptado |
| `test_intermat.py`, `test_smart.py` | Fixture configurável e expectativas explícitas para o novo padrão |
| `benchmark_checkpoints.py`, `benchmark_progressive.py` (novos) | Medições reproduzíveis contra a referência |
| `README.md` e este documento | Uso, contratos e limitações atuais |

## Teste manual no Windows e pendências

Após o envio autorizado, obtenha esta entrega na branch
`perf/otimizacao-varredura`, seguindo o guia do README. Use instalação separada,
preservando a versão anterior e os dados locais. Não copie `.venv` entre
computadores; a `main` não é a referência desta entrega.

```cmd
instalar.bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
INICIAR_AMBIDIFF.bat
```

1. Abra `http://127.0.0.1:8765`; confira a gaveta fechada e padrão progressivo/20.
2. Em páginas locais/autorizadas, confira menus, ÁUDIOS, consultas e documentos.
3. Use orçamento curto, confira parcial e pendências; retome e aprofunde.
4. Interrompa uma etapa; confira fila, erro, diagnóstico e checkpoint íntegro.
5. Abra relatório grande, marque filtradas além dos 40 cartões, recarregue e
   confirme seleção e revisão independentes. Excluídos não devem exportar.
6. Exporte os quatro formatos, teste teclado, cancelar e indisponibilidade de
   `showSaveFilePicker`. Abra HTML fora da instalação e PDF em leitor local.
7. Avalie tempo real, checkpoints, memória do Chromium e qualidade das DIVs.

Pendentes: Windows nativo, antivírus/disco corporativo, diálogo real Salvar como,
memória total do navegador, páginas protegidas/tardias e portais reais autorizados.
Não houve validação em produção nem garantia da meta de 15–20 minutos. Falsos
positivos fora dos cenários conhecidos precisam de revisão humana. A seleção de
três representantes é heurística de escopo, ajustável futuramente após evidência;
o aprofundamento já permite sair dela sem perder o trabalho.

Nenhum log, checkpoint, relatório corporativo, credencial ou evidência real foi
enviado a serviços externos. Os únicos artefatos de medição desta entrega são
sintéticos. O envio autorizado restringe-se ao código, testes, documentação e
benchmarks sintéticos na branch de desenvolvimento.

Preparação do envio: branch `perf/otimizacao-varredura`, commit baseado em
`b71d90f713141888163366b934807d49ca927550`, com **23 arquivos alterados/novos**.
A tabela de arquivos acima descreve o código e testes;
os três `docs/benchmark-17-*.json` guardam somente os cenários sintéticos. Logs
temporários dos testes/benchmarks ficam em `/tmp` e não fazem parte da entrega.

Antes do envio autorizado, a suíte completa passou novamente: **198 testes em
103,264 s, sem falhas ou testes ignorados**. A sintaxe do JavaScript e o diff
também passaram nas verificações. A lista dos 23 arquivos foi conferida para
excluir credenciais, relatórios internos, logs, históricos e checkpoints reais.
