# Desempenho, equivalência e qualidade das evidências

Base de desenvolvimento: `feat/varredura-inteligente`, commit `dddda4e567978e8b408975cf044c87ec478b22b`.
Branch da implementação: `perf/otimizacao-varredura`. Não incorpora os PRs USEIA e
CGE nem altera a main. As melhorias anteriores de progresso/ETA dessa base foram
preservadas. Aplicação local, sem deploy, publicação ou acesso a portais corporativos.

## 1. Diagnóstico e instrumentação

A regra anterior de `duvida_estrutural` acionava releitura por qualquer diferença
não editorial ou correspondência inconclusiva. A existência de uma diferença não
é evidência de carregamento incompleto. Também havia gatilho de seis textos/imagens
unilaterais, duas esperas de 950 ms e duas preparações completas adicionais.
Widgets repetidos podiam perpetuar esse custo em cada página. Não é necessário
classificar o widget como irrelevante para deixar de reler um DOM estável.

A preparação anterior somava 250 ms antes de rolar, 250 ms depois e duas esperas
mínimas de 380 ms para igualdade de contagens/tamanho. Alterações de texto com o
mesmo comprimento podiam passar despercebidas. O reconhecimento de templates
avaliava duas vezes a mesma árvore inicial; a extração repetia a identificação
editorial do mesmo elemento. Foram removidas essas duplicações sem eliminar seus
critérios de segurança.

O diagnóstico real recebido da SEFAZ continua sendo evidência histórica fornecida
pelo usuário, sem reprodução nesta entrega. Os 1.268,67 s de segunda leitura incluem
preparação/extração: **não devem ser somados** aos 1.631,21 s de preparação para
estimar a duração. Nenhum resultado sintético comprova que a SEFAZ já atingiu
23min58s, nem que agora concluirá todo o portal.

### Campos temporais e métricas

- `iniciado_em`: ISO 8601 com fuso da máquina, registrado no início do motor; não
  inferido do ID da execução. No Windows utiliza o fuso configurado localmente.
- `finalizado_em`: fim da montagem do resultado, após varredura, capturas e auditoria;
  antecede fechamento dos contextos/navegador e exportação. Não é fim da descoberta
  de páginas nem horário inferido do nome do arquivo.
- `duracao_segundos`: intervalo real por relógio monotônico, com a mesma fronteira
  de processamento descrita acima. O benchmark mede separadamente a chamada inteira,
  incluindo fechamento do Playwright. O painel mede a execução do worker.
- Checkpoints têm início e duração já percorrida; `finalizado_em` permanece nulo.
  Recuperação informa o fim do tratamento da falha, preserva o início do checkpoint,
  registra `duracao_no_checkpoint_segundos` e a duração monotônica do worker atual.
  O checkpoint original permanece no disco. Não existe retomada automática após
  reinício do processo nem recuperação garantida além do último checkpoint.
- `metricas.tempos_segundos`: navegação, preparação, extração, abas, sonda de
  releitura, comparação, releitura, documentos, capturas e auditoria. `varredura`
  inclui suas subetapas; `processamento_final` inclui agrupamento/capturas/auditoria.
  **Releitura inclui preparação/extração, e extração inclui abas.** Não somar tempos
  aninhados. Não confundir duração das etapas com tempo exclusivo de CPU.
- `metricas.releituras`: URLs, motivos verificáveis, duração individual, diferenças
  antes/depois, adoção e mudança do diagnóstico, erro/limitação e ambas as coletas.
- Contadores: operações, releituras dispensadas por estabilidade, releituras que
  mudaram o diagnóstico, preparações profundas, pares comparados e pendentes.
  Média por par e requisições por par são nulas quando não há par coletado.
- `andamento`: etapa, par atual e último par processado, preservados no snapshot.
  Isso é diagnóstico no relatório; não substitui a sincronização de logs do PR CGE.
- Exportação: `exportacao.duracao_antes_json_segundos` mede CSV/HTML e preparação do
  JSON, excluindo a escrita final do próprio JSON. O diagnóstico também contém
  `exportacao_worker_segundos`, incluindo a exportação completa pelo worker.
  A cópia filtrada de download recebe sua própria medição de exportação.

JSONs históricos não são regravados para acrescentar esses campos. Downloads e
reclassificações mantêm a separação entre evidência original e cópia/arquivo auxiliar.

## 2. Preparação adaptativa e segunda leitura seletiva

`ambidiff/adaptive.py` instala um MutationObserver local que acompanha mudanças de
filhos, texto e atributos. Não se baseia só no tamanho do texto ou quantidade de nós.
A sonda também verifica readyState, indicadores aria-busy/progressbar, imagens
pendentes, altura/posição, scripts, lazy loading e abas.

A preparação mantém a rolagem completa, com passos de 80% da altura da janela e
espera de 160 ms por passo; detecta crescimento da página e continua a percorrê-la.
Mantém o teto de 35 passos e orçamento de aproximadamente 7+2 s. Não dispensa
rolagem porque o template parece conhecido. Aguarda pelo menos 450 ms, ou 1.300 ms
com scripts/lazy/abas, e quietude observada de 350 ms. A sondagem ocorre em intervalos
de 100 ms. Busy, imagens pendentes, mutações contínuas ou orçamento esgotado impedem
a declaração de estabilidade. Telemetria sem mutação relevante do DOM não exige
networkidle. JavaScript, imagens, fontes, SVG e TLS continuam habilitados.

As abas continuam sob o limite de 35, com os mesmos cliques/esperas existentes, e
agora verificam cancelamento entre abas. A preparação verifica cancelamento entre
sondagens/rolagens. Não passa objetos síncronos do Playwright para outras threads.
Uma operação Playwright em andamento ainda precisa devolver o controle.

A releitura acontece por DOM alterado após a coleta, preparação limitada/instável,
carregamento pendente ou impossibilidade de sondagem. Ausências numerosas em DOM
aparentemente estável recebem uma confirmação curta de 150 ms; só uma mudança
observada justifica reler. Divergência persistente ou correspondência semântica
inconclusiva, isoladamente, não exige repetir o navegador.

Cada releitura conserva a primeira e a segunda coleta completas. Só substitui o
resultado se a nova preparação estiver estável, sem limitação de rolagem, não reduzir
itens/links e conservar os controles e destinos já identificados. Uma nova coleta
pode revelar diferenças adicionais, e não somente reduzir a quantidade de DIVs.
Caso perca cobertura ou falhe, a primeira fica ativa e a limitação é registrada.

**Limite:** quietude observada não prova que nenhum timer futuro alterará o DOM.
Nenhuma espera finita prova isso. Lazy loading fora dos sinais observados, iframes,
shadow DOM e conteúdo protegido continuam exigindo revisão. A preparação incompleta
fica sinalizada; não é convertida em prova de ausência. A política antiga de omissão
profunda de templates editoriais continua opcional/conservadora, explicitamente
registrada. Ela não é utilizada no benchmark equivalente desta entrega.

## 3. Correspondência, tags e confiança

Rótulos diferentes passam a gerar uma ocorrência `Rótulo` no modo inteligente quando
há destino equivalente único nos dois sentidos, mesmo contexto, tipo, papel e
estrutura. Não usa sinônimos fixos como CONSULTAR/PESQUISAR. Ambiguidade, papel ou
estrutura diferentes impedem essa associação. Um candidato com o mesmo rótulo
existente não é trocado por outro controle renomeado. Os links associados também
podem entrar na navegação conservadora, em vez de produzir duas ausências e uma
omissão de cobertura. Não afirma equivalência funcional.

Mudança de posição não gera ausência por si só. Ordem diferente continua podendo
produzir o registro específico de ordem já validado; isso não é uma alegação de
controle ausente nem comprovação de defeito. Semântica e contexto incertos continuam
acessíveis para revisão. ÁUDIOS e qualquer outra opção exclusiva são tratados pela
mesma regra, nos dois sentidos e sem presumir PRD correto.

`ambidiff/taxonomy.py` acrescenta campos, preservando tipo/categoria/IDs anteriores:

| Tag | Evidência/limite |
|---|---|
| OPCAO_AUSENTE | Controle sem correspondência identificada; ausência visual não comprovada |
| ROTULO_DIVERGENTE | Associação conservadora; rótulos observados diferentes |
| FUNCAO_DIVERGENTE | Papéis DOM diferentes ou comportamento ainda sem teste registrado |
| DESTINO_DIVERGENTE | Referências observadas diferentes; não determina qual destino é correto |
| COMPONENTE_DIVERGENTE | Imagem/ícone/componente diferente; não presume impacto visual |
| ESTRUTURA_DIVERGENTE | Ordem ou composição estrutural diferente |
| DOCUMENTO_DIVERGENTE | Referência documental diferente/sem correspondência; não compara corpos |
| FALHA_FUNCIONAL_VERIFICADA | Somente quando o teste limitado de clique registra execução e resultados diferentes |
| DADOS_VARIAVEIS | Variação editorial contextual/manual; não confirma a causa da diferença |
| COLETA_INCONCLUSIVA | Contexto insuficiente ou falha de coleta, discriminados pela confiança |

`tag_tecnica`, `tags`, `grau_confianca`, `justificativa_evidencia` e
`teste_funcional_executado` tornam explícito o que foi inspecionado. Confiança separa
possível, inconclusiva, diferença de dados, observação/referência confirmada e falha
da automação. Uma falha de navegação não vira defeito confirmado do site.

Um controle com a palavra “baixar” não é necessariamente documento. A extração usa
extensão/rota documental reconhecida; destinos sem extensão não reconhecidos
continuam links comuns. HEAD, MIME, Range e os limites seguros do módulo documental
permanecem. Metadados não provam igualdade nem diferença dos conteúdos. Não foram
acrescentadas ações de envio ou testes destrutivos.

## 4. Agrupamentos e relatórios

A repetição conserva `registros_individuais`, identificadores OCO por ocorrência,
URLs, caminhos, seletores e evidências. O ID DIV continua identificando o grupo de
repetições da execução. Destinos, textos observados e assinaturas distintas não são
fundidos por terem o mesmo rótulo. IDs históricos não são renumerados em arquivos
originais. Os IDs OCO são locais à execução, não identificadores globais entre runs.

A extração registra ancestrais de componente (`data-component`, role group, fieldset
ou classe widget) e de seção (section/article/region), sem depender do nome do órgão
ou rótulo. `grupos_relacionados` relaciona IDs que compartilham ancestral observado
num par de páginas. Aceita diferenças presentes em lados opostos do mesmo par.
Somente estar na mesma página não basta. Concentração numa seção exige mais de um
tipo de ocorrência. O vínculo expressa uma **hipótese**, nunca causa confirmada.
Seletores de DOM não são identidade absoluta de componente entre portais diferentes.

O fixture de 208 páginas conserva 416 ocorrências individuais de imagem+controle,
consolidadas em duas DIVs, e relaciona as partes por ancestral em cada par de páginas.
A interface mantém essas relações recolhidas, com botões para acessar cada DIV.
Nenhum registro relevante deixa de aparecer por pertencer a um grupo.

JSON preserva evidências e classificações. HTML/CSV exibem tags e confiança; HTML
inclui tempos, relações e registro técnico de releituras. A interface mostra tags,
justificativa, horários, duração, relações e motivos/resultados de releitura. CSV
mantém seus campos e acrescenta colunas; leitores devem usar os cabeçalhos. Editorial,
baixa relevância e inconclusivo continuam nas estruturas existentes, com uma visão
editorial classificada adicional. O log TXT continua sendo histórico da execução.

O progresso/ETA da base foi preservado: usa avanço recente, pode ficar indisponível
e não certifica cobertura. A correção de cursor de logs/interrupção do PR CGE continua
separada; esta branch não a substitui silenciosamente.

## 5. Concorrência e limites restantes

A análise favorece primeiro a eliminação de trabalho redundante: preparação e
releitura dominam os dados recebidos, enquanto comparação consome cerca de 1,77 s.
A preparação usa objetos síncronos, callbacks de extração, abas e checkpoint
compartilhados pelo laço. Colocar os dois objetos Page em threads seria incorreto.
A API assíncrona exige adaptar esse caminho inteiro, os mocks e a propagação de
cancelamento/falhas. Não basta envolver chamadas síncronas em gather/to_thread.

**Não foi implementado paralelismo nesta entrega.** Mantém-se uma operação por vez
e contextos isolados por ambiente. Isso limita carga, preserva suporte local e evita
misturar uma migração de arquitetura com a correção principal. Um futuro protótipo
async deve limitar concorrência a 1/2 por par, ser configurável, medir memória/carga,
verificar cancelamento e manter resultado individual quando um ambiente falhar.
Não há alegação de ganho de concorrência nem opção fictícia na interface.

Capturas mantêm 40 grupos/240 s; cliques opcionais mantêm 12 candidatos; documentos
mantêm 20 pares/100 pedidos, 4 s por pedido e orçamento cooperativo. Não foram
removidas capturas para cumprir meta. O benchmark usa capturas/cliques/auditoria
explicitamente desativados nos **dois** checkouts; seus custos reais não estão
validados por essa medição. Não foi aumentada a carga em servidores externos.

## Validação e reprodução

Suíte completa no Windows:

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Benchmark da versão anterior e da otimizada (três repetições alternadas, loopback):

```cmd
git worktree add --detach ..\AmbiDiff-referencia dddda4e
.venv\Scripts\python.exe scripts\benchmark_perf.py --baseline ..\AmbiDiff-referencia --pages 3 --repetitions 3
```

O script executa cada checkout em subprocesso isolado, com as mesmas opções,
servidores e HTML. Compara páginas, pares, falhas, omissões, divergências e itens,
contextos, papéis e destinos efetivamente extraídos na primeira coleta de cada página.
Releituras redundantes não contam como cobertura adicional. O benchmark antigo
`benchmark_smart.py` compara modos com cobertura diferente; não serve para aceitar
a meta desta entrega. Não há auditoria humana formal de falsos positivos no novo
benchmark; esse campo é nulo, e as regressões genéricas cobrem erros conhecidos.

Resultados numéricos, ambiente e arquivos alterados constam abaixo após a rodada
final. Validação real e execução em Windows continuam pendentes: esta sessão usa
Linux/Chromium. As novas regressões usam o Chromium instalado pelo Playwright, com
fallback para Chromium do sistema, sem depender obrigatoriamente de caminho Linux.

## Resultado do benchmark final

Ambiente: Linux x86_64/glibc 2.41, Python 3.12.14, Playwright 1.64.0, Flask 3.1.3,
Chromium 154.0.8037.57. Três execuções por versão/cenário, sem a suíte rodando em
paralelo. Dados integrais: [benchmark-perf.json](benchmark-perf.json).

| Cenário | Mediana anterior | Mediana otimizada | Redução | Cobertura/achados equivalentes |
|---|---:|---:|---:|---|
| Institucional estável | 22,926 s | 5,324 s | 76,78% | Sim, nas propriedades inspecionadas |
| Scripts, conteúdo tardio, rolagem e abas | 31,975 s | 13,040 s | 59,22% | Sim, nas propriedades inspecionadas |

Variação estável: anterior 22,834–23,838 s; otimizada 5,126–6,109 s.
Variação dinâmica: anterior 31,972–32,419 s; otimizada 12,922–13,351 s.

Em cada execução: três pares percorridos/comparados, seis páginas, 16 DIVs agrupadas,
zero pendências de navegação, falhas ou omissões profundas; seis requisições de
navegador nos dois checkouts. São os mesmos itens/contextos/papéis/destinos extraídos,
incluindo conteúdo de rolagem e abas. O número de preparações passou de 12 para 6
porque deixou de repetir a preparação dos mesmos seis documentos HTML; não houve
redução de páginas ou retirada da inspeção inicial. Segundas leituras passaram de
3 para 0 nesses cenários estáveis após a preparação. O teste separado de mudança
real do DOM comprova a manutenção da releitura quando necessária.

Tempos medianos de preparação: estável 15,306 → 3,152 s; dinâmico 19,755 → 8,124 s.
Tempo mediano de releitura anterior: 13,442 s/17,723 s, respectivamente. São medidas
sobrepostas; não somá-las à preparação. No cenário dinâmico a extração passou de
4,919 para 2,576 s ao não repetir abas; na versão nova 2,521 s foram medidos dentro
das abas. A versão anterior não tinha esse contador específico (ausência não é custo
zero). Navegação não demonstrou ganho: estável 0,292 → 0,285 s; dinâmico 0,297 → 0,401 s.
O ganho veio de trabalho/esperas redundantes, não de redução de requisições.

**Aceite sintético:** meta de 50% atingida nos dois cenários, mantendo a cobertura
observada. **Aceite real SEFAZ:** pendente de execução autorizada em Windows/portais,
com mesmas opções/páginas e análise das divergências. Não extrapolar as porcentagens
acima para os 47min56s históricos. Capturas, documentos e outros padrões de conteúdo
podem dominar outra execução. Não há promessa de concluir portais inteiros dentro
do limite preventivo sem medição real.

## Cobertura das regressões solicitadas

Os nomes abaixo referem-se a `tests/test_perf.py`, salvo indicação contrária.
Os 82 testes anteriores foram mantidos, sem enfraquecimento de suas asserções.

| Casos solicitados | Regressões |
|---|---|
| 1–2: opções exclusivas com nomes variados e nos dois sentidos | `test_opcoes_exclusivas_nomes_e_sentidos_variados` e regressões CGE anteriores |
| 3–4: posição/menu reorganizado | `test_posicao_diferente_equivalencia_sem_ausencia`, `test_menu_reorganizado_mantem_elementos`, testes de ordem em `test_v13.py` |
| 5–6: rótulo diferente com correspondência | `test_rotulo_novo_associado_por_destino_papel_contexto`, `test_rotulos_nao_pareiam_ambiguidade_ou_funcao_distinta`, `test_par_com_mesmo_rotulo_nao_e_trocado_por_outro` |
| 7: destino diferente | `test_destinos_distintos_continuam_visiveis`, `test_v12.py` |
| 8–9: partes do widget, repetição | `test_widget_repetido_preserva_registros_e_relaciona_partes`, `test_nome_baixar_nao_comprova_documento_e_ancestrais_coletados` |
| 10: controles e seção ausentes | `test_controles_ausentes_junto_com_secao_permanecem_relacionados` |
| 11–12: editorial e estrutura preservada | `test_smart.py` e `test_v15.py`, com defasagem explícita e ÁUDIOS |
| 13, 19: conteúdo tardio/releitura necessária | `test_atraso_real_justifica_releitura_e_muda_diagnostico`, `test_pagina_dinamica_lazy_e_aba_sao_inspecionadas` |
| 14: documento sem comparação integral | `DocumentTests` em `test_smart.py`, além de tags documentais e extração por rota |
| 15: captura sem localizar DOM presente | `test_captura_sem_seletor_nao_comprova_ausencia_visual` — captura real somente loopback |
| 16: comportamento funcional testado | `test_diferenca_funcional_observada_por_clique_local` — GET local, link inerte vs navegação |
| 17: inconclusivo | `test_coleta_inconclusiva_e_evidencia_sem_seletor` e correspondência ambígua |
| 18: interrupção parcial | `test_interrupcao_preserva_tempo_diagnostico_checkpoint_e_exportacao`, `test_interrupcao_cooperativa_da_preparacao` |
| 20–21: releitura/preparação repetida desnecessária | `test_diferenca_estavel_nao_rele_imagem_botao_e_textos`, `test_estavel_sem_segunda_preparacao_por_divergencia` |
| 22: dinâmica/abas/lazy | `test_pagina_dinamica_lazy_e_aba_sao_inspecionadas`, `test_v14.py` |
| 23: ícone e estrutura visual | `test_relevance.py`, `test_v15.py` e tags de componente |
| 24: navegação/redirecionamento | `test_redirecionamento_inicial_divergente_preserva_diagnostico` — HTTP local real |
| 25: duração/serialização | `test_metricas_duracao_monotonica_e_serializacao` e relatórios parciais |
| 26–28: relações, independência, IDs/evidências | testes de widget, seção, página independente, IDs e destinos; `test_interface_tags_relacoes_ids_e_tempos` |
| 29: filtro sem ocultar estrutura | opção ausente, destino, seção, `test_relevance.py`, confirmações manuais anteriores |
| 30: exportação parcial e diagnóstico | testes de interrupção/recuperação e exportação JSON/HTML/CSV |

Também há regressões de recuperação com e sem checkpoint, preservação do arquivo
original e campos temporais, além de manutenção da primeira coleta se a segunda
perder estabilidade, controles ou quantidade de itens/links.

## Arquivos desta entrega e revisão futura

- `ambidiff/adaptive.py` (novo): observação do DOM, preparação e decisão de releitura.
- `ambidiff/paired.py`: integra a política, métricas, coletas preservadas e checkpoint final.
- `ambidiff/smart.py`: cronologia, correspondência por destino e sonda de template sem duplicação.
- `ambidiff/core.py`: ancestrais explícitos, referência editorial reutilizada, tipo documental e cancelamento entre abas.
- `ambidiff/taxonomy.py` (novo): tags, confiança e relações por ancestral/par de páginas.
- `ambidiff/relevance.py`: projeção classificada e relações, preservando as evidências.
- `ambidiff/functional.py`: registra execução e resultados individuais do teste limitado.
- `ambidiff/reports.py` e `diagnostics.py`: formatos, confiança, relações e fronteiras de tempo.
- `web/server.py`: cronologia de erro/recuperação e custo da exportação, sem migrar para async.
- `web/static/app.js`: explicação das evidências, tags, tempos e consulta de relações.
- `scripts/benchmark_perf.py` e `tests/fixtures_perf.py` (novos): comparação entre checkouts, somente local.
- `tests/test_perf.py` (novo): regressões genéricas adicionais.
- Documentação, README e arquivo sintético do benchmark.

`documents.py` e `storage.py` foram revisados e mantidos: limites, bloqueio de
redirecionamentos externos, ausência de leitura do corpo, revisões em arquivo auxiliar
e gravação atômica de checkpoint continuam. Não foi necessário reescrevê-los.

Integração futura pode conflitar em `paired.py`, `core.py`, `web/server.py`, interface
e relatórios com os PRs USEIA/CGE. Comparar as políticas de cancelamento, navegação,
progressão, checkpoint e argumentos antes de resolver esses conflitos; executar toda
a suíte após a integração. Esta branch depende da inteligente e não deve ser tratada
como alteração independente da main. Não houve merge automático.

Próximos passos recomendados: validação autorizada em Windows com corpus fixo e
mesmas opções; medir capturas/documentos com dados locais mais variados; só então
prototipar concorrência limitada a dois ambientes, preservando a mesma cobertura.

## Resultado final da suíte e riscos

**112 testes aprovados, zero falhas, zero erros, zero testes ignorados**, em 66,486 s:
82 existentes e 30 regressões novas. `node --check web/static/app.js` e
`git diff --check` também passaram. Permanecem ResourceWarning preexistentes dos
testes de download; não foram convertidos em testes ignorados ou sucesso artificial.

Snapshots de releitura podem aumentar o tamanho do JSON/memória em portais muito
instáveis. O observador considera mutações de atributos, portanto widgets que mudam
continuamente podem alcançar o orçamento e continuar inconclusivos. Vínculos exigem
ancestral identificável: componentes sem esses sinais podem permanecer sem relação.
A associação não deduz causalidade só por posição ou texto. Esses limites favorecem
preservar evidências em vez de ocultar ausências e problemas reais para ganhar tempo.
