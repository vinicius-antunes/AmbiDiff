# AmbiDiff · Integração dos filtros de URL antes da Etapa 5

## Origem e escopo

A integração foi feita na branch `experimento/motor-eficiencia-v2` a
partir de `4150aac22fb714d4b3d43ebe9c54e44a10b04a5b`. O commit de origem
`ed743eae575a4f20d4cf29c24e90cd59545cf000` era o HEAD remoto de
`perf/filtro-urls-varredura`. O histórico tinha como base comum
`eef2f734a59707aedff18a65d22fffa6ee1a4383`.

O diff de origem foi revisado e aplicado por cherry-pick sem conflitos.
A comparação do índice com o commit de origem confirmou os seis
arquivos importados antes dos ajustes de compatibilidade. O comparador
com RapidFuzz, a instrumentação, a preparação e as evidências do
Playwright e os dois modos de navegação permanecem nas versões da
branch experimental.

O filtro reconhece a paginação de Rádio/TV e conserva a primeira
página, as exceções de serviços e documentos e os parâmetros
funcionais. A evidência editorial unilateral exige mesma rota,
índice e parâmetros funcionais nas duas origens configuradas.
A identidade do portal dá precedência a metadados explícitos e
expõe sua fonte no diagnóstico.

## Compatibilidade e ajustes

- **Raiz explícita em conflito.** A restauração de escopo preserva
  a identidade inconclusiva quando a própria raiz tem caminho
  `/web/...` e os metadados indicam outro site. O caminho inicial
  deixava de ser uma evidência válida ao detectar o conflito e
  voltava a definir o site indevidamente ao carregar o estado.
- **Diagnóstico de checkpoint.** A projeção usa os dois endereços
  da configuração validada do checkpoint para reconstruir os escopos.
  Ela conserva a origem e o grau de certeza da identidade.
- **Leitura legada.** Um checkpoint versão 1 foi gerado em
  `4150aac` com a fixture de fila e HEAD simulados. A integração
  restaurou o escopo legado, reaproveitou a evidência editorial
  gravada com query em outra ordem e concluiu três pares.
  A paginação editorial recém-descoberta foi excluída, enquanto
  a consulta com `c=42&e=7` foi visitada nos dois ambientes.
  ÁUDIOS conservou o mesmo ID no resultado retomado, no relatório
  JSON e no diagnóstico. O arquivo original manteve os mesmos bytes.

Os campos novos são opcionais, e a versão e a assinatura do checkpoint
seguem o formato existente. A retomada conserva os resultados anteriores
e honra os pares já admitidos. Os candidatos que aguardam admissão
passam pela política vigente.

## Testes

| Verificação | Resultado |
| --- | --- |
| Testes da Etapa 4 de filtros | 21 aprovados, incluindo os 19 de origem e os dois de compatibilidade. |
| Suíte completa | 373 aprovados em 237,170 s, sem falhas nem testes ignorados. Inclui RapidFuzz, Playwright síncrono e assíncrono, interrupção, retomada, evidências e relatórios. |
| Ensaio local com Chromium nos dois modos | Cinco pares comparados em cada modo com os mesmos filtros, divergências, IDs e estados. Incluiu ÁUDIOS, Rádio/TV, uma rota editorial `/w/`, legislação e parâmetros funcionais. |
| `node --check web/static/app.js`, `pip check` e `git diff --check` | Aprovados. |

Os dois testes de compatibilidade falharam contra o cherry-pick
original e passaram depois dos ajustes. Os testes de origem cobrem
também a preservação de serviços SIMCAR, SIMLAM e SISFLORA, de
documentos e resoluções, e da identificação tardia do portal.

O ambiente de validação foi Linux, Python 3.12.14, RapidFuzz 3.14.6 e
Chromium 154 do sistema. As fixtures e servidores de loopback cobriram
o fluxo local. Windows e portais institucionais ficaram fora desta
rodada. A identidade inferida pelo subdomínio continua registrada
como heurística quando a raiz carece de metadados explícitos.
