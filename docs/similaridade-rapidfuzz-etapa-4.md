# AmbiDiff · RapidFuzz na etapa 4

A comparação parte do commit `6b2f8826850c496bd7aa7f9f2894ccb2659d8dea`
da branch `experimento/motor-eficiencia-v2`.

## Escopo da similaridade

| Ponto do código | Evidência usada |
| --- | --- |
| `core.comparacao` e antiga `_texto_parecido` | Presença exata por tipo e chave normalizada. Entre textos restantes, dois nomes de pelo menos 24 caracteres e contexto compatível podem formar uma divergência de substituição. A nota confirmatória é a razão de `SequenceMatcher`. |
| `paired._link_pairs` e `_pares_por_rota` | Tipo, rótulo exato normalizado, contexto, estrutura, função e destino, conforme a regra aplicável. A associação por rota exige candidato único nos dois sentidos. Um rótulo igual em contexto igual pode continuar expondo redirecionamento diferente. |
| `smart.Inteligencia.comparar` e `sections.comparar_secoes` | Evidências de contexto e elemento. Rótulos diferentes em controles exigem associação única por estrutura, papel e destino. A associação de textos informativos por seção exige seletor único nos dois lados. |
| `documents.Documentos.comparar` | Sobreposição de termos, nome normalizado, destino e metadados HTTP. Conteúdo de arquivos permanece fora dessa inferência. |
| `intelligence.separar_editoriais` | Contexto do DOM e evidência de uma área editorial correspondente. Diferenças preservam seu registro editorial ou estrutural. |

O RapidFuzz passa a eliminar candidatos inviáveis apenas no trecho de textos
já elegíveis à comparação aproximada. Menus, botões, serviços, documentos,
destinos e redirecionamentos continuam com suas regras próprias.

## Comparação entre algoritmos

O painel tem 12 pares de frases sintéticas, com sete associações esperadas.
O rótulo indica que as duas frases ocupam o mesmo papel no exemplo. Uma
associação aceita ainda pode representar uma divergência, como dois prazos
diferentes. As notas abaixo estão na escala 0–1. As métricas por tokens do
RapidFuzz retornam 0–100 e foram divididas por 100 para a comparação.

| Algoritmo como decisão direta | Corte no painel | Corretas | Falsos positivos | Falsos negativos |
| --- | ---: | ---: | ---: | ---: |
| `SequenceMatcher` | 0,82 | 4 | 2 | 3 |
| RapidFuzz Indel | 0,92 | 3 | 0 | 4 |
| RapidFuzz Levenshtein | 0,85 | 3 | 0 | 4 |
| RapidFuzz `token_sort_ratio` | 0,85 | 4 | 1 | 3 |
| RapidFuzz `token_set_ratio` | 0,82 | 6 | 3 | 1 |

O corte da Etapa 3 foi mantido na primeira linha. Para os demais, foi
escolhido o menor total de erros entre 0,50 e 0,99, em passos de 0,01,
com preferência por menos falsos positivos e, depois, pela proximidade
de 0,82. A calibração é descritiva e usa o próprio painel. Por exemplo,
os textos sobre transporte de resíduos e armazenamento de produtos
obtiveram 0,8264 no Indel e 0,7934 no `SequenceMatcher`. As frases em que
cidadão e servidor trocam de papel obtiveram 1,0 nas duas métricas por
tokens. Nenhum corte direto foi adotado.

## Mudança implementada

O comparador normaliza cada nome como antes e indexa textos elegíveis do
segundo ambiente pelo contexto. A ausência de contexto em um dos lados
continua permitindo a comparação, conforme a regra anterior. Nomes
normalizados repetidos no mesmo contexto são consultados uma vez por
busca. As confirmações ficam em um cache de até 256 entradas, limitado à
comparação atual.

A similaridade Indel é duas vezes o comprimento da maior subsequência
comum dividido pela soma dos comprimentos. Os blocos que o
`SequenceMatcher` utiliza também formam uma subsequência comum. Portanto,
Indel é um limite superior para a nota de `SequenceMatcher`. O RapidFuzz
faz a triagem em fluxo. Só chegam à confirmação candidatos capazes de
alcançar o corte legado ou de igualar o melhor resultado já encontrado.
Uma margem de `1e-12` cobre arredondamentos do limite superior. A
aceitação continua usando a nota original de 0,82.

A seleção percorre os mesmos itens e desempata pelo primeiro índice
original disponível. O ID e a classificação continuam ligados à mesma
ocorrência de divergência. As associações únicas e recíprocas dos fluxos
de seção e links mantêm as suas evidências. Para textos com candidatos
ambíguos, conservamos a representação histórica de divergência e as
ausências remanescentes. Exigir um novo desempate recíproco na
similaridade textual mudaria o agrupamento e poderia renumerar DIVs
posteriores, já que os IDs são sequenciais. O painel mostrou erros
diferentes nas alternativas de pontuação, sem base suficiente para
trocar essa regra nesta etapa.

## Benchmark do comparador

`scripts/benchmark_rapidfuzz.py --baseline CAMINHO_DA_ETAPA_3` executa a
referência e a otimização em processos separados com os mesmos elementos.
Foram usadas cinco medições de tempo para cada versão e cenário, com
Python 3.12.14 em Linux e RapidFuzz 3.14.6 com extensão nativa. O relógio
mede `comparacao` sobre itens prontos. A medição de pico Python usa
`tracemalloc` em uma rodada separada, e RSS é o pico do processo
incluindo imports e a rodada com rastreamento.

| Cenário | Elementos A/B | Mediana antes → depois (ms) | Pico Python antes → depois (KiB) | Pico RSS antes → depois (MiB) |
| --- | ---: | ---: | ---: | ---: |
| Pequeno, com textos, controles e duplicados | 18/19 | 2,240 → 1,038 | 32,1 → 61,2 | 24,6 → 29,1 |
| Grande, com textos variados em quatro seções | 458/459 | 3.818,582 → 53,832 | 675,9 → 911,9 | 25,8 → 31,1 |
| Denso, com muitos textos parecidos na mesma seção | 138/139 | 584,373 → 103,153 | 204,4 → 376,2 | 24,7 → 29,1 |

| Cenário | Associações corretas | Falsos positivos | Falsos negativos | DIVs | Registros editoriais | Mudanças de classificação ou ID |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pequeno | 5 | 2 | 3 | 23 | 1 | 0 |
| Grande | 445 | 2 | 3 | 463 | 1 | 0 |
| Denso | 125 | 2 | 3 | 144 | 1 | 0 |

As duas versões produziram os mesmos resultados completos nos três
cenários. A verificação compara o hash dos registros agregados, IDs,
classes, registros editoriais e pares de links. Um grupo ambíguo por
cenário é contado separadamente da precisão, pois a fixture não
estabelece contraparte entre os candidatos empatados. Ele manteve a
divergência agrupada e as ausências restantes.

A triagem reduziu o custo de processamento e aumentou o pico de memória
observado. A memória auxiliar do índice cresce com a quantidade de
textos. Em uma seção com muitos candidatos viáveis, o pior caso ainda
pode exigir um número quadrático de pontuações dentro daquela seção.
O benchmark mede listas sintéticas de elementos com a extensão nativa
em Linux. Os números descrevem a etapa de comparação nessas listas,
com precisão de associação avaliada pelos rótulos da fixture.

## Instalação e testes

`requirements.txt` inclui `RapidFuzz>=3.14.5,<4`. O instalador
`instalar.bat` já instala esse arquivo. O download de wheels Windows x64
com o resolvedor do pip selecionou a versão 3.14.5 para CPython 3.10 e a
3.14.6 para 3.11 e 3.12. O conjunto completo de requisitos também
foi resolvido e baixado como wheels Windows x64 para CPython 3.12.
`pip install -r requirements.txt` e `pip check` passaram no ambiente
local. A execução do instalador e da suíte em Windows ficou fora
desta rodada.

| Verificação | Resultado |
| --- | --- |
| `python -B -m unittest discover -s tests -v` na Etapa 3 | 343 testes aprovados em 239,727 s. |
| `python -B -m unittest discover -s tests -v` com a triagem | 352 testes aprovados em 252,027 s, incluindo nove novos. |
| RapidFuzz 3.14.5 nativo e implementação Python | Oito regressões sem navegador passaram em cada implementação. |
| `node --check web/static/app.js` e `git diff --check` | Aprovados. |

As duas suítes completas passaram sem falhas nem testes ignorados no
Linux, com Chromium real e servidores de loopback.

As nove regressões cobrem normalização exata, variações de texto inclusive
no corte, assuntos distintos com nota alta de Indel, duplicados e
ambiguidade, menus reposicionados, rótulos semelhantes com rotas diferentes,
portarias, diferenças editoriais, ÁUDIOS, IDs, redirecionamentos e PNGs
nos dois modos do Playwright. Há comparação de paridade do seletor
legado nas duas orientações, com espaços, contextos ausentes e textos
com mais de 200 caracteres.
