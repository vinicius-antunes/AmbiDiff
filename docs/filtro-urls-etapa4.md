# Etapa 4 — Correção da paginação em Rádio/TV e inferência conservadora de portal

Base prevista: `perf/filtro-urls-varredura`, commit `eef2f734a59707aedff18a65d22fffa6ee1a4383` (18/11/2026).

## Diagnóstico no código

- `pagination.finalidade`: a rota editorial aceitava `/radio` e `/tv`, mas não `/radio-paiaguas` ou `/tv-paiaguas`; controles rotulados como "Próximo" perdiam o contexto de mídia.
- `portal.EscopoPortal`: uma raiz institucional com `group_id` numérico, porém sem `site_url` ou canonical/friendly específico, não conseguia reconhecer `/web/mt` como portal distinto. Sem identidade comprovada, o tratamento original era conservador e expandia as referências.
- `urlfilter.PoliticaURLs`: a decisão de exclusão exigia ambas as laterais; evidência editorial HTML unilateral podia não bloquear paginação da mesma rota e índice. Além disso, URLs observadas no DOM eram armazenadas sem a mesma normalização que a admissão aplica a parâmetros de consulta.

## Correções

1. Reconhecimento de rotas editoriais genéricas `radio-*`, `radio_*`, `tv-*`, `tv_*`, sem cadastrar nomes de portais ou simplesmente bloquear qualquer URL que contenha "radio".
2. Inferência **heurística e registrada** de site a partir de host institucional dedicado `orgao.estado.gov.br` quando não existem canonical/friendly explícitos. O algoritmo não infere identidade em `www.estado.gov.br` e respeita metadados explícitos, inclusive quando conflitantes. Por ser heurística, necessita validação em mais portais antes de assumir cobertura confiável.
3. Normalização das evidências HTML pela mesma rotina usada na fila e exclusão de paginação com evidência observada em **apenas um ambiente**, exclusivamente quando o outro apresenta a **mesma rota e índice de paginação**, não possui exceção estrutural e não há outro portal identificado. O motivo unilateral fica explícito no diagnóstico; não se afirma equivalência de conteúdo.

## Revisão do pacote e adaptações

Os três Git blob SHA do `LEIA-ME.txt` coincidiram com a base local/remota, e
`git apply --check` aprovou o patch antes da aplicação. O aplicador alternativo
não foi executado: a pasta preexistente `ambidiff-next/` foi preservada, sem exigir
limpeza da árvore. Patch, ZIP, aplicador e logs de execução não são versionados.
Foram mantidos os oito testes fornecidos e acrescentadas regressões locais.

A revisão reproduziu lacunas do patch original e motivou ajustes direcionados:

- **Ordem real de coleta:** o motor observa a raiz antes de extrair o HTML.
  Por isso, uma identidade heurística inicial precisa ser substituída quando o
  canonical/friendly explícito chegar. Metadados explícitos contraditórios,
  inclusive em observações sucessivas, ficam inconclusivos e não reativam a
  heurística após retomada. A URL inicial explícita também participa desse exame.
  Checkpoints anteriores sem a origem da identidade continuam aceitos como legados.
- **Correspondência segura:** exige as duas origens configuradas, caminho igual,
  exatamente um índice numérico posterior de mesmo tipo/valor e demais parâmetros
  funcionais iguais. Prefixos de instância podem diferir apenas no parâmetro de
  paginação reconhecido. Divergências de `c`, `e`, `delta`, filtros, índices extras
  ou fragmentos impedem essa inferência. `delta` isolado não é índice posterior.
  URLs inválidas não são promovidas a correspondências.
- **Colisões na normalização:** evidências documentais/de serviço prevalecem sobre
  editoriais, inclusive ao recuperar chaves antigas que passam a representar a
  mesma URL normalizada. A ordem das entradas não deve apagar uma exceção importante.

Isso restringe apenas a inferência nova entre ambientes. Quando há provas
editoriais independentes nos dois lados, ou evidências suficientes de outro portal,
as regras anteriores continuam aplicáveis. Não se afirma equivalência de conteúdo,
mesmo quando a navegação posterior é contida.

No diagnóstico, `escopos_portais` informa `fonte_identidade`, `identidade_inferida`
e `identidade_inconclusiva`. O contador `paginacoes_assimetricas_com_evidencia`
mede pares únicos excluídos dessa maneira; o evento
`paginacoes_inferidas_por_um_ambiente` conta avaliações e pode ser maior.
Os novos campos de checkpoint são opcionais, dentro do mecanismo existente.

## Regressões e critérios

Executar `python -B -m unittest discover -s tests -p test_filter_stage4.py -v`, depois toda a suíte. Conferir que ÁUDIOS da CGE segue sendo detectado e que as páginas posteriores de Rádio/TV Paiaguás não entram na fila. Verificar documentação, portarias e serviços, além de retomadas com checkpoints.

A correção não inclui nova classificação de HTTP, ajustes na interface ou agrupamento de DIVs. O filtro não considera PRD referência absoluta.

### Comandos da entrega

Com o ambiente virtual ativo, inclusive no Windows:

```text
python -B -m unittest discover -s tests -p test_filter_stage4.py -v
python -B -m unittest discover -s tests -p test_update19.py -v
python -B -m unittest discover -s tests -v
node --check web/static/app.js
git diff --check
git diff --cached --check
```

Dependências e Chromium, quando ainda não instalados: `python -m pip install -r
requirements.txt` e `python -m playwright install chromium`. Não foram adicionadas
dependências. O ambiente de verificação desta entrega é Linux/Python 3.12, com
Chromium de sistema indicado ao Playwright por alias local fora do repositório;
isso não substitui a validação no Windows com o Chromium oficial.

### Resultados verificados

- Antes da aplicação: 17 regressões da etapa 3 aprovadas, em 5,458 s.
- Patch fornecido: seus oito testes passaram. Os cenários adicionais reproduziram
  falhas na prioridade tardia de metadados, conflitos sucessivos, correspondência
  de query/índices e colisão de evidências normalizadas; foram corrigidas sem
  remover ou alterar os oito testes originais.
- Etapa 4 final: **19 testes aprovados**, em 0,225 s, incluindo os oito fornecidos
  e onze complementares. Os testes do motor usam navegação e HEAD simulados.
- Suíte completa final: **336 testes aprovados**, em 191,020 s, sem falhas,
  erros ou testes ignorados. Inclui ÁUDIOS, serviços, CONSEMA, teto de 1.000 pares,
  exclusivas, links/redirecionamentos, checkpoints, retomada, relatórios e evidências.
- Verificação direcionada do `AGENTS.md` (`test_update19.py`): **36 testes
  aprovados**, em 30,868 s; já integram os 336, não são testes únicos adicionais.
- Sintaxe dos quatro arquivos Python da etapa, JavaScript da interface e
  `git diff --check` aprovados; dependências existentes verificadas por `pip check`.

Os tempos acima são da execução de testes e não medem desempenho de varredura.

### Limitações e validação manual pendente

- O subdomínio pode não coincidir com a friendly URL real; a fonte heurística
  precisa ser conferida. Conflitos de identidade não provam que um link seja de
  outro portal; o limite de rede e as restrições existentes permanecem ativos.
- Rotas diferentes entre ambientes, múltiplos portlets ou parâmetros funcionais
  diferentes ficam conservadoramente fora da inferência unilateral, podendo
  demandar mais análise. Não se elimina qualquer query para forçar correspondência.
- No Windows autorizado, confirmar primeira página e controles de Rádio/TV na
  SEMA, ausência de expansão das páginas posteriores e de outros portais, origem
  da identidade, links/redirecionamentos e serviços SIMCAR/SIMLAM/SISFLORA/CONSEMA.
- Na CGE, confirmar novamente ÁUDIOS ausente no ambiente correspondente e revisar
  que exclusões editoriais não ocultem menus, legislação ou documentos relevantes.
- Comparar cobertura, falhas e tempos nas mesmas condições de uma execução
  anterior. Nenhum ganho em minutos ou percentual foi medido nesta etapa.

**Limites:** teste local/fixture não comprova funcionamento nos portais reais; é necessário repetir CGE e SEMA com os mesmos ambientes e comparar pares efetivamente comparados, DIVs editoriais posteriores, exclusões justificadas e tempo. Não assumir ganho de desempenho somente pela redução da quantidade de DIVs.
