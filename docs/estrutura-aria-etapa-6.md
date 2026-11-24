# AmbiDiff · Reconhecimento estrutural com HTML e ARIA

## Extração anterior

A Etapa 5 coletava links em `<a href>`, botões nativos, abas, itens de menu e
opções de `<select>`. Já usava `role`, `aria-label`, `aria-controls`, regiões
semânticas, posição visual e a assinatura estrutural do DOM. Retirava o nome
da tag e o conjunto de tags filhas em `estrutura_funcional()`, preservando o
papel declarado. Um link nativo e um link com `role="menuitem"` podiam ficar
sem correspondência estrutural embora apontassem para o mesmo destino.

A coleta anterior deixava de resolver `aria-labelledby` e de extrair
botões genéricos com `role="button"`. A leitura de estados iniciais como
`aria-selected` e `aria-disabled` era incompleta. Quando uma aba era aberta
para inspeção, sua coleta repetia o documento inteiro com o rótulo da aba
no contexto dos itens. Uma falha podia deixar uma diferença de conteúdo
sem a indicação de que o painel do outro ambiente não tinha sido inspecionado.

## Mudanças

- `JS_EXTRAIR` usa os sinais de `semantics.py`
  na avaliação já existente. Mantém o texto legível como rótulo de comparação.
  Para um controle sem esse texto, usa referências únicas de
  `aria-labelledby`, `aria-label` ou rótulos HTML associados. Referências
  incompletas, repetidas ou inválidas ficam explícitas. Um ícone cujo texto
  consiste só em símbolos pode usar o nome acessível.
- Os itens podem carregar metadados de papel, nome acessível, grupo, alvo
  e estado. A coleta combina os papéis de links, botões, itens de menu,
  abas, controles de seleção e regiões como `navigation`, `tablist` e
  `dialog` com elementos HTML nativos. `<summary>` usa o estado observado
  de `<details>`. Um alvo de `aria-controls` precisa ser resolvido no
  documento. Os IDs podem diferir entre ambientes.
- O modo inteligente usa rótulo exato normalizado, função, contexto
  semântico e destino real ou relação de controle observável. Exige
  unicidade nos dois sentidos. Estados observados diferentes produzem uma
  DIV de tipo `Estado` para revisão. Estados contraditórios ou disponíveis
  em apenas um ambiente podem deixar a avaliação inconclusiva. Os resultados
  entram em `otimizacao.equivalencias_verificadas` e
  `otimizacao.equivalencias_inconclusivas`. A confirmação de funcionamento
  depende de inspeção própria. A comparação comum continua usando o
  comparador existente.
- As inspeções de abas e expansíveis mantêm os seletores, a quantidade máxima
  e a política somente leitura existentes. Controles desabilitados, ocultos,
  associados a formulários ou com indícios de ação insegura ficam fora do
  clique. A guarda também considera o rótulo acessível. Para alvos vinculados
  e únicos, a coleta após o clique se limita aos descendentes do painel. Se
  um desses painéis não for observado, a ausência de itens observados no
  painel correspondente fica inconclusiva.
- O índice por rótulo restringe a comparação semântica a grupos pequenos.
  Mais de oito itens com o mesmo tipo e rótulo em um ambiente deixam o grupo
  inconclusivo. Os índices de links e de contexto evitam buscas repetidas em
  todos os itens. A coleta calcula as posições de irmãos uma vez por pai e
  agrupa as opções pelo menu mais próximo em uma passagem.
- `core.py`, `paired.py`, `smart.py` e `semantics.py` concentram as
  mudanças. `Item.semantica` tem valor vazio para checkpoints antigos.
  A suíte também verifica os contratos dos filtros de URL, da fila,
  do RapidFuzz, das exportações e da retomada já existentes.

## Exemplos e regras de decisão

| Cenário local | Resultado esperado |
| --- | --- |
| `<nav><a href="/servicos">` e `<div role="navigation"><div role="menu"><a role="menuitem" href="/servicos">` no rodapé | Correspondência observada com rótulo, menu e destino equivalentes. |
| Botão nativo com texto e `<div role="button" tabindex="0">` em região nomeada, com referências que formam o mesmo rótulo | Correspondência estrutural. A ativação por teclado depende da implementação do portal. |
| Aba nativa e aba ARIA com o mesmo nome sob `tablist`, cada qual ligada ao seu `tabpanel` | Correspondência estrutural quando os estados são compatíveis. Seleção diferente fica registrada. |
| `<details>` recolhido diante de um botão associado a conteúdo já expandido | Diferença de estado inicial preservada. |
| Dois botões «Consultar» em um contexto idêntico diante de um único controle | Inconclusivo por falta de par mútuo. |
| `role="link"` sem `href`, botão genérico sem foco ou `aria-controls` com IDs duplicados | O diagnóstico preserva a incerteza. Para roteamento, usa-se apenas o destino observado. |
| Menu responsivo com duas variantes CSS | A coleta considera a variante visível no viewport usado. |
| Mesma opção com rotas distintas, ou ÁUDIOS presente em só um ambiente | A diferença permanece para revisão. |

A prova pontual com `aria_snapshot()` do Playwright expôs nomes e papéis de
menu, botão e aba. Ficaram ausentes o ID do painel controlado e o destino do
`menuitem` nessa fixture. A execução usa o DOM coletado nos dois modos do
Playwright, onde essas relações podem ser cruzadas com os atributos de origem.

## Benchmark local

O script usa três repetições por padrão. Para reproduzir a comparação, na
raiz do repositório, aponte `--codigo` para o código da Etapa 5 em uma
exportação local, sem trocar de branch. As duas execuções usam as mesmas
fixtures da Etapa 6.

```sh
mkdir -p /tmp/ambidiff-etapa5
git archive d897a6f | tar -x -C /tmp/ambidiff-etapa5
PYTHONHASHSEED=0 python -B scripts/benchmark_aria.py --codigo /tmp/ambidiff-etapa5
PYTHONHASHSEED=0 python -B scripts/benchmark_aria.py
```

O cenário integral começa em portais loopback, inclui serviço, legislação,
documento, rotas divergentes, um expansível e conteúdo tardio. O teste de
escala usa duas páginas sem clique, com 600 controles adicionais por
ambiente. Uma variante combina dois tipos de markup e a segunda usa botões
nativos nos dois lados. Os tempos da execução integral são métricas do
motor, salvo o tempo total, medido na chamada inteira. A métrica
`extracao` inclui as inspeções de componentes. Os cliques contam tentativas
das APIs síncronas de Playwright, inclusive as que expiram. O RSS cobre o
processo Python inteiro, com exclusão dos subprocessos Chromium.

Medições em Linux x86-64, Python 3.12.14, Playwright 1.64.0 e Chromium
oculto. Os tempos são medianas de três amostras por versão.

| Varredura síncrona em loopback | Etapa 5 | Etapa 6 |
| --- | ---: | ---: |
| Tempo total (s) | 8,02 | 6,27 |
| Extração com inspeções (s) | 4,82 | 2,12 |
| Comparação (ms) | 6,47 | 0,88 |
| Pareamento de links (ms) | 0,42 | 0,15 |
| Cliques tentados | 9 | 5 |
| Pares HTML comparados | 1 | 3 |
| Pares falhos | 0 | 0 |
| Pico RSS Python no benchmark inteiro (MB decimais) | 68,87 | 73,80 |

| Duas páginas densas com 600 controles adicionais por lado | Versão | Itens coletados (PRD / DES) | Extração (ms) | Comparação com links (ms) |
| --- | --- | --- | ---: | ---: |
| Tags diferentes | Etapa 5 | 617 / 17 | 282 | 23,79 |
| Tags diferentes | Etapa 6 | 619 / 617 | 466 | 12,31 |
| Botões nativos dos dois lados | Etapa 5 | 617 / 617 | 468 | 811,33 |
| Botões nativos dos dois lados | Etapa 6 | 619 / 617 | 528 | 12,71 |

A extração ficou mais cara na amostra densa. A diferença de volume coletado
explica parte do custo na variante com tags diferentes. Na variante com
botões nativos, a extração subiu cerca de 13% e a comparação ficou mais curta,
pois o índice substitui buscas repetidas por rótulo. No cenário integral,
a inspeção limitada ao painel e as guardas de clique reduzem o trabalho
da coleta. A mudança de um para três pares comparados também altera a
carga de trabalho. Esses resultados descrevem as fixtures medidas.

| Avaliação das equivalências estruturais rotuladas | Etapa 5 | Etapa 6 |
| --- | ---: | ---: |
| Correspondências esperadas confirmadas no diagnóstico | 0/5 | 5/5 |
| Falsos positivos entre os 13 casos avaliados | 0 | 0 |
| Falsos negativos entre os cinco pares estruturais esperados | 5 | 0 |
| Diferenças relevantes esperadas registradas | 2/4 | 4/4 |
| Casos esperados com incerteza explícita | 1/4 | 4/4 |

Os cinco pares rotulados como equivalentes são Atendimento, Legislação,
Portaria 12, Preferências do portal e Resumo. A Etapa 5 podia parear links
por critérios de fila sem registrar a equivalência estrutural. Os casos
inconclusivos são Consultar duplicado, Rótulo inválido, Acesso sem foco e
Conteúdo tardio da aba inacessível. As diferenças relevantes são ÁUDIOS,
Rota divergente, Alternar opções e Bloqueio parcial.

O esquema de IDs continua sendo o existente. A numeração de uma nova
varredura muda quando sua lista de divergências muda. Na amostra, o primeiro
registro de ÁUDIOS passou de `DIV-0006` a `DIV-0004` e permaneceu relevante.
O primeiro registro da rota divergente permaneceu `DIV-0005`, agora como
Redirecionamento. O conteúdo tardio conservou `DIV-0001` e passou de
relevante a inconclusivo. A regressão de integração compara IDs,
classificações, ordem e estados dos pares com Chromium síncrono e assíncrono.

## Testes e limitações

Passaram **389 testes em 269,7 s**, com zero falhas e zero testes ignorados,
em `python -B -m unittest discover -s tests -v`. A execução focada passou
com 11 testes, incluindo as oito novas regressões de `test_estrutura_aria.py`.
A primeira rodada detectou a perda do aviso sobre uma inspeção desabilitada
e do contador de reaproveitamento de verificação estática. Os dois
comportamentos foram corrigidos e as regressões antigas passaram sem
alteração de suas expectativas. As verificações de sintaxe JavaScript e
de diff também passaram.

A validação disponível foi em Linux, com fixtures HTML, Chromium local
e loopback. Windows, portais institucionais e testes com tecnologia
assistiva ficaram sem validação nesta etapa.

A coleta interpreta um subconjunto do cálculo completo de nome acessível.
Dependem de revisão rótulos com referências múltiplas parcialmente inválidas,
grupos indistinguíveis, portais que replicam controles ativos, relações de
controle sem alvo único e widgets que usam somente handlers sem destino
observável. A inspeção dinâmica continua limitada aos controles elegíveis
e ao viewport da varredura. A comparação de estados se refere ao DOM
observado, sem validar navegação com teclado, comportamento de tecnologia
assistiva ou as múltiplas etapas de uma interação real.

A recomendação é conservar o reconhecimento no modo inteligente e tratar
as equivalências como evidência estrutural. A cobertura e o custo devem ser
monitorados em páginas densas e em componentes que exigem várias etapas.
