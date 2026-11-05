# Validação da versão 0.1.0

Versão experimental executável, não uma substituição validada em produção para
AmbiDiff 1.5. Nenhum acesso a INDEA, SEMA, CGE real ou outros portais institucionais
foi realizado. Os testes usaram dados fictícios e loopback.

## Ambiente e testes

Python 3.12, Flask, Playwright, Pillow 12.3 e pytest 9.2 em Linux. Chromium 154
instalado localmente foi configurado explicitamente. Isso não é validação Windows
ou do Chromium oficial esperado pelo Playwright instalado.

A suíte cobre URLs/escopo, referência Liferay, parâmetros c/e, ÁUDIOS oculto/ausente
nos dois sentidos, estruturas rearranjadas, ambiguidade, corroboração semântica,
erros HTTP/rede/carregamento, redirecionamentos, HEAD sem corpo, funções ARIA,
bloqueio de POST/GET perigoso, imagens reais, região oculta, sobreposição, máscaras,
rasterização, amostragem, ciclos, interrupção, recuperação do navegador, retomada,
SQLite, logs acima de 200 entradas, seleção persistente, busca ID/lista/faixa,
CSV, JSON, HTML e ZIP. Testes de navegador usam Chromium real, não só mocks.

A primeira execução integrada encontrou falha no próprio teste de interface:
`wait_for_function` dependia de eval proibido pela CSP. O teste passou a aguardar
locators, preservando a proteção de segurança e as asserções.

## Benchmark obrigatório

O protocolo está em `benchmark-method.md`. Os mesmos portais, viewport 1366×850,
oito diferenças conhecidas e negativos são usados nos dois programas. Resultados
completos ficam em `data/benchmarks/`, ignorado no Git. Só agregados são documentados.

O primeiro experimento identificou oito diferenças conhecidas no Next e quatro
no legado, mas também falsos positivos candidatos e cobertura funcional não
equivalente. Não qualificou ganho. Orientou regressões para notícias sem classes
específicas e rasterização textual. O manifesto não foi alterado para melhorar a
pontuação. A meta de 30–50% continua experimental: métricas ausentes do legado
permanecem desconhecidas. Tempo menor com menos cobertura, mais FP ou perda de
casos relevantes não é aprovado como melhoria.

## Segurança e compatibilidade

- Não há IA remota, telemetria, upload, publicação ou dependência do legado na
  execução normal do Next.
- Servidor loopback, token para mutações locais, Origin/Host validados, CSP,
  proteção contra fórmulas CSV e travessia de caminhos de evidências.
- Capturas/banco são locais; senhas não são extraídas e valores de query são
  redigidos nos logs. URLs de comparação podem conter dados internos: revise
  exportações antes de encaminhá-las.
- Revisão/seleção não altera ocorrências brutas. Ocultar preserva o registro;
  seleção omite DIVs ocultas e inventários/logs alheios.
- HTML: PNG até 3 MB cada/20 MB total. ZIP: até 100 MB de imagens, mesmo limite
  individual. Omissões não apagam arquivos originais.
- Scripts `.cmd` foram inspecionados, mas não executados em Windows. São
  preparação local de venv/dependências/Chromium, não instalador binário assinado.

## Pendências conhecidas

Amostragem, capacidade e orçamento de interações/capturas não validam itens
omitidos. Funções sem contrato seguro ou que dependam de rede durante o clique
ficam inconclusivas. Não se exercitam handlers inline, autenticação, CAPTCHA ou
escrita. Um viewport é avaliado por execução.

Containers com filhos diferentes podem produzir candidatos visuais relacionados;
um redirecionamento diferente pode gerar diferenças estruturais consequentes.
O avaliador preserva candidatos fora do manifesto para revisão, limitando uma
interpretação universal da precisão. Não há equivalência semântica universal,
avaliação integral de acessibilidade ou cobertura de todos os dispositivos.

Próximas avaliações: Windows/Chromium oficial; revisão dos candidatos visuais e
contextuais; cobertura funcional por tipo de ação; ampliação de fixtures sem
alterar o legado; comparação INDEA/SEMA somente com autorização explícita futura.

## Resultados medidos nesta entrega

Next: **82 testes aprovados em 38,45 s**, sem falhas/skips, incluindo ponta a ponta
API → worker real → Chromium → SQLite → exportação. Compilação Python e sintaxe
JS aprovadas. Ensaios anteriores de 77/79 testes também passaram; regressões
adicionais foram incluídas após o benchmark revelar limitações.

Benchmark final: duas repetições, ordem alternada, oito notícias por ambiente,
sem outra carga de navegador em paralelo. Base do legado:
`1f79c55c0b187a5a159d54c84344f6dcd98ff342`. Código funcional Next medido:
`1f9a579` (mesmos arquivos usados antes do commit). Dados são sintéticos locais.

| Medida | AmbiDiff atual | Next |
| --- | ---: | ---: |
| Tempo mediano | 64,701 s | 17,034 s |
| Tempos individuais | 64,340 / 65,061 s | 17,090 / 16,978 s |
| Navegações reportadas pelo motor | 30 | 23 |
| GETs HTML observados pelo servidor, incluindo evidências/interações | 108 | 23 |
| Elementos verificados reportados | não disponível | 114 |
| Ações funcionais executadas por ambiente, conforme adaptador | 24 | 4 |
| Ações funcionais inconclusivas | 0 | 2 |
| Comparações reais de imagem reportadas | não disponível | 44 |
| Casos verdadeiros detectados | 4/8 | 8/8 |
| Candidatos fora do manifesto (FP a revisar) | 4 | 5 |
| Falsos negativos sobre o manifesto | 4 | 0 |
| Precisão sobre candidatos do manifesto | 50,0% | 61,5% |
| Recall sobre manifesto | 50,0% | 100,0% |
| Falhas técnicas finais | 0 | 0 |
| Artefatos por repetição | ~1,47 MB | ~0,78 MB |

O legado não contabiliza navegações auxiliares na mesma unidade do Next; o
observador HTTP independente torna essa diferença explícita. As ações funcionais
dos motores também abrangem tipos diferentes: o Next restringe cliques a contratos
seguros, enquanto conferir destino não equivale a validar handler JS. Não se deve
compensar isso somando navegações ao contador de cliques.

A redução observada de tempo foi **73,67% neste cenário**, mas **não constitui
ganho qualificado nem aprovação da meta**. O gate recusou: mais candidatos FP,
menor contagem funcional, métricas de cobertura indisponíveis no legado e escopo
Next parcial (amostragem e inspeções unilaterais). Esta recusa é esperada e fica
nos resultados; não foi contornada para anunciar sucesso de desempenho.

As fases de uma repetição ilustram a distribuição (não somar fases aninhadas):
legado: navegação 1,313 s, preparação 6,039 s, extração 1,596 s, cliques 33,603 s,
capturas 17,893 s, checkpoint 0,039 s. Next: navegação 0,697 s, extração 0,277 s,
comparação 0,057 s, visual 0,056 s, funções 6,960 s, capturas 8,060 s.
O Next não possui preparação profunda independente como o legado. Seus campos
reservados de descoberta/preparação inicialmente zerados não são medições
isoladas e não devem ser utilizados para reivindicar ganho nessas fases;
o tempo total é medido externamente. A duração de transações SQLite não tem
instrumentação isolada nesta versão; volume de arquivos é medido pelo harness.

Os cinco candidatos do Next fora do manifesto envolvem título/estrutura
consequentes de redirecionamento, container de menu, Ouvidoria reposicionada e
referência de Regulamento. Permanecem nos dados para revisão, sem remoção para
melhorar artificialmente a pontuação. O ensaio cobre apenas uma família de
portais fictícios; não estabelece precisão universal.

Preservação do legado: **272 testes aprovados em 141,715 s**, sem falhas/skips.
O diff em relação à base fora de `ambidiff-next/` é vazio: código, interface,
relatórios antigos, dependências e testes do programa original não foram alterados.
