# Escopo lógico do portal e listagens editoriais

Base: `86c28cb`, na branch `perf/filtro-urls-varredura`. Esta etapa complementa
[a segunda etapa](filtro-urls-etapa2.md), sem mudar interface, modos de comparação,
agrupamento de DIVs ou o limite de 1.000 pares HTML. Não houve acesso a portais reais.

## Diagnóstico

O limite de rede existente (`permitido`) verifica origem e prefixo da URL inicial.
Uma entrada na raiz do domínio, portanto, pode permitir vários sites Liferay.
O filtro anterior reconhecia índices dinâmicos `_INSTANCE_…_cur`, mas dependia
principalmente de rota/rótulo/contexto para identificar a finalidade editorial.
Fotografias, rádio/TV e listagens em rotas opacas podiam escapar dessa classificação.
Destinos finais de redirecionamentos também precisavam passar pela política de
expansão, sem gerar comparações de conteúdo para páginas fora dela.

Os números fornecidos pelo mantenedor sobre CGE/SEMA são relatos de testes reais,
não medições reproduzidas aqui. Nenhum relatório real foi incorporado ao código.

## Regras implementadas

- **Escopo por ambiente:** `portal.EscopoPortal` usa `/web/<site>`, `/group/<site>`
  (inclusive com locale), a entrada configurada, destino inicial observado,
  canonical/friendly URL na mesma origem e groupId/siteId numérico. Na extração,
  consulta APIs opcionais de `Liferay.ThemeDisplay`; não depende de um tema fixo.
  Sem identidade explícita, duas referências distintas da navegação principal
  apontando para um único site podem estabelecer a identidade. Evidências de
  páginas filhas não alargam o portal; metadados conflitantes não estabelecem
  uma nova identidade. Os nomes de site e grupos não precisam coincidir entre
  PRD e HOMOL/LAB.
- **Outro portal:** compara a referência na origem e verifica existência/destino
  por HEAD na mesma origem autorizada, usando `Destinos`, seus limites, cache,
  bloqueio de ações inseguras e classificação inconclusiva existentes. Não lê
  corpo por HEAD, não abre a árvore HTML do portal vizinho e não presume
  equivalência. Diferenças observadas de destino/acesso permanecem registradas.
  HEAD recusado, limite de requisições ou ausência de autorização são limitações,
  não prova de defeito. Outros domínios continuam dependendo da opção externa.
- **Serviços compartilhados:** finalidade de serviço comprovada pela referência
  (por exemplo, em seção Serviços ou rota de serviço) pode admitir a URL exata
  na mesma origem, inclusive fora do prefixo inicial. Isso não libera o prefixo
  inteiro do outro portal. Não há lista especial de SIMCAR/SIMLAM/SISFLORA/CONSEMA;
  os testes usam esses nomes em contextos de serviço fictícios.
- **Editorial:** acrescenta fotos/fotografias, rádio, TV e arquivo editorial às
  evidências semânticas já existentes. O HTML fornece evidências por componente:
  cabeçalho semântico, cartões temporais e paginação no mesmo caminho. Isso
  permite reconhecer uma listagem mesmo em rota opaca. Uma seção documental/
  administrativa ou de serviços mantém prioridade sobre sinais editoriais.
  Widgets de galerias e legislação no mesmo HTML são classificados separadamente.
- **Primeira página:** permanece comparada, incluindo presença, rótulos e destinos
  dos controles. Índices posteriores não são admitidos automaticamente. Os
  parâmetros dinâmicos/offsets continuam reconhecidos; `delta` sozinho não indica
  página posterior. A deduplicação pode retirar somente índices iniciais
  comprovados, mantendo `c`, `e`, `delta` e demais parâmetros funcionais.
- **Itens individuais e exclusivas:** cartões editoriais identificados por
  evidência HTML mantêm a referência comparada e a verificação limitada do link,
  sem expansão HTML. Institucionais/serviços exclusivos e páginas indeterminadas
  continuam recebendo inspeção conservadora, sem inventar contraparte. A política
  anterior de não expandir descendentes unilaterais sem prova estrutural permanece.
  ÁUDIOS ausente continua detectado nos dois sentidos; seu ID não é fixado.
- **Redirecionamentos:** após a navegação, restringe expansão para outro portal
  ou paginação editorial identificada; preserva os destinos, motivo e eventuais
  diferenças de redirecionamento. Se a finalidade só aparece no HTML, pode ser
  necessária uma coleta para decidir, sem gerar DIVs de conteúdo desse ramo.
  Falhas HTTP/coleta seguem o fluxo anterior, sem inventar conteúdo ausente.

## Checkpoints, diagnósticos e unidades

O mesmo estado `filtro_urls` recebe campos opcionais `portais` e
`finalidades_observadas`. Não há novo formato paralelo de checkpoint. Resultados,
fila, evidências e relatórios parciais continuam no mecanismo anterior. Checkpoints
legados sem metadados permanecem legíveis; a identidade pode ficar indeterminada.
Pares anteriormente admitidos continuam sendo drenados; candidatos ainda não
admitidos são reavaliados. Retomar uma comparação antiga não equivale a aplicar
o filtro retroativamente a toda a fila; prefira uma comparação nova para medir.

No diagnóstico existente:

| Campo | Unidade/significado |
| --- | --- |
| `escopos_portais` | Identidade inferida por ambiente e quantidade de serviços compartilhados |
| `urls_excluidas_por_categoria` | URLs únicas por categoria, incluindo outro portal e paginação editorial |
| `pares_excluidos` / `excluidas_por_categoria` | Pares de referências únicos, incluindo unilaterais |
| `exclusivas_classificadas_por_finalidade` | Registros unilaterais únicos classificados; não total de tentativas |
| `excecoes_estruturais` / `referencias[].motivo` | Exceções atuais e justificativas; compartilhamento é explícito |
| `urls_unicas_admitidas` | URLs distintas em pares admitidos, no resumo de cobertura |
| `navegacoes_planejadas_evitadas` | Oportunidades de abertura excluídas antes da admissão por referência única; não requisições de rede medidas |
| `pares_contidos_apos_redirecionamento` | Pares contidos após abertura/coleta; não aberturas evitadas |
| `metricas.contagens.navegacoes_html_tentadas` | Chamadas ao abridor HTML, incluindo repetição controlada; não todos os pedidos HTTP ou subrecursos |
| `metricas.contagens.requisicoes_destinos` | Requisições HEAD efetuadas pelo verificador existente |

As categorias podem compartilhar URLs; não some categorias para obter o total
global. Fases de avaliação ficam registradas. Exemplos continuam limitados a 100,
com URLs sanitizadas sem query/credenciais e índices de paginação separados.
Observações HEAD recuperadas são históricas, não nova prova de disponibilidade.

## Validação local

- Referência: **300 testes aprovados**, sem falhas/ignorados, em 184,261 s.
- Novas regressões: **17 testes aprovados**, incluindo Chromium com HTML
  interceptado em loopback; o grafo do motor e HEAD são simulados, sem DNS real.
- Suíte ampliada: **317 testes aprovados**, sem falhas/ignorados, em 184,605 s.
  Após o último ajuste de proteção a cartões de serviços/imagens institucionais,
  as 17 regressões da etapa foram reexecutadas e passaram em 3,656 s.
- Sintaxe dos oito arquivos Python envolvidos, `node --check web/static/app.js`
  e `git diff --check` aprovados. Não houve alteração de JavaScript da interface.
- A suíte completa verifica também teto/drenagem de 1.000 pares, exportações,
  compatibilidade de relatórios e checkpoints, falhas de automação e segurança.

Durante a preparação, três expectativas/fixtures dos novos testes foram
corrigidas: HTML com charset UTF-8 explícito, estado `interrompido` separado de
cobertura `parcial`, e contagem por par único em vez de tentativas repetidas.
Não foram removidos testes ou enfraquecidas verificações existentes.

No Windows, com o ambiente virtual ativado:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python -B -m unittest discover -s tests -p test_filter_stage3.py -v
python -B -m unittest discover -s tests -v
node --check web/static/app.js
git diff --check
python -B scripts/benchmark_filter_stage3.py --repeats 3
```

O ambiente desta entrega é Linux/Python 3.12, com Chromium de sistema 154 indicado
ao Playwright por alias local fora do repositório. Isso não comprova execução no
Windows ou com o binário oficial do Playwright; não foram alteradas dependências.

### Comparação controlada

`scripts/benchmark_filter_stage3.py` aplica o mesmo grafo nas duas versões: 115
páginas editoriais em rota opaca, um portal vizinho com dez páginas filhas, um
serviço compartilhado e ÁUDIOS ausente. São três repetições por versão em processos
separados, sem suíte concorrente, com custo simulado de 4 ms/abertura HTML e
1 ms/HEAD. O processamento Python também integra o tempo; não representa latência
de rede de um portal real.

| Métrica | Referência `86c28cb` | Atual |
| --- | ---: | ---: |
| Tempo mediano do grafo | 6,371248 s | 0,112791 s |
| Aberturas HTML | 260 | 6 |
| HEAD simulados | 0 | 4 |
| Pares admitidos/comparados | 130/130 | 3/3 |
| Aberturas em páginas editoriais posteriores | 228 | 0 |
| Aberturas no portal vizinho | 22 | 0 |
| ÁUDIOS identificado | Sim | Sim |
| Serviço compartilhado inspecionado em ambos | Sim | Sim |
| Falhas/pendências de pares | 0/0 | 0/0 |

A redução decorre da política solicitada: omissão de 114 páginas posteriores,
uma repetição da primeira página e 12 páginas de portais fora do escopo funcional.
Essas páginas **não têm cobertura profunda equivalente** na versão atual. O
benchmark comprova contenção desse grafo, não melhoria geral de precisão nem
ganho de tempo em CGE/SEMA. A leitura do HTML para inferir finalidade é exercitada
pelos testes Chromium; o benchmark injeta os mesmos metadados em ambas as versões.
O verificador permanece sujeito a limites; os quatro HEAD são contados à parte.

Para reproduzir a referência sem trocar/desfazer sua branch, extraia `86c28cb` em
outra pasta e use `python -B scripts/benchmark_filter_stage3.py --root CAMINHO --repeats 3`.

## Limitações

Identidade, finalidade e compartilhamento dependem de evidências disponíveis.
Rotas opacas sem semântica/HTML suficiente ficam conservadoramente analisáveis;
não se promete eliminar toda navegação editorial. Aliases de site não comprovados
não são fundidos automaticamente. O próprio Liferay pode emitir metadados
incompletos; a decisão deve ser conferida no diagnóstico. Evidência estrutural
é necessária para um serviço compartilhado; o nome de uma sigla, isoladamente,
não libera um portal.

Referências em páginas ignoradas profundamente não têm cobertura integral; isso
é uma limitação explícita, não equivalência presumida. Uma raiz explicitamente
configurada como página editorial posterior continua respeitada. 1h30 é meta,
não um prazo de encerramento. Não houve nova classificação geral de erros HTTP,
mudança de segurança global, interface, exportação ou agrupamento de DIVs.
