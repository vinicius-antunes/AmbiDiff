# Filtros de varredura — segunda etapa

Base: `01f10d4`, branch existente `perf/filtro-urls-varredura`. Main e Next não
são modificadas. Esta etapa substitui a exceção genérica de menus da primeira.

## Diagnóstico confirmado no código

O relato agregado da CGE informa 97 comparados, 890 inspeções sem contraparte,
1.010 admissões e páginas posteriores de notícias/vídeos. Não foram fornecidos
os registros individuais; não é possível classificar retroativamente as 890
inspeções, vincular cada DIV ou explicar todas as diferenças de contadores.

Foram identificadas lacunas independentes:

1. `importante or menu` era avaliado antes da paginação: qualquer link em menu,
   rodapé ou com marcador genérico de estrutura podia atravessar o filtro.
2. O regex editorial não incluía explicitamente vídeos/áudios; `offset` também
   não era reconhecido. Esses destinos podiam ser admitidos mesmo com cur>1.
3. Candidatos já vistos escapavam da avaliação e `repor_fila` admitia candidatos
   restaurados sem revalidar a política. Uma correção só no regex não bastaria.
4. Uma página unilateral podia descobrir recursivamente todos os seus links.
5. O contexto de controles vinha do título mais próximo de artigo/section/li.
   O comparador interpretava títulos editoriais diferentes como contexto funcional
   diferente para o mesmo botão. A numeração com um dígito nem entrava no modelo.
6. Testes opcionais de cliques tinham um caminho de navegação separado da fila.
   Não há evidência de que essa opção estivesse ativa no teste real da CGE.

## Regras atuais e fluxo

`pagination.py` interpreta query strings com `parse_qsl`, sem depender do INSTANCE
específico do Liferay: cur/page/pagina>1, start/offset>0 e caminhos page/pagina/N.
Delta isolado representa tamanho de página e não autoriza inferir página posterior.
Cur/page=1 e start/offset=0 são iniciais; a identidade de admissão pode retirar
somente esses parâmetros quando o destino é editorial e a referência sem eles já
está representada. Delta, c/e, filtros funcionais e fragmentos são preservados.
Isso não afirma funcionamento nem altera globalmente a comparação de destinos.

Agora: referência observada → finalidade do destino → filtro central → identidade
conservadora → deduplicação/pareamento existentes → candidato → revalidação →
admissão HTML. Redescobertas e candidatos restaurados passam pela política.
Não se inventa contraparte: o pareamento existente continua exigindo evidências.
Links do mapa do site extraídos do DOM recebem a mesma política; não foi criado
um novo leitor de sitemap XML ou um segundo crawler.

Paginação editorial de notícias/vídeos/áudios/galerias é excluída antes da fila,
mesmo em menus, mapas ou conteúdo institucional. Ser encontrado em menu/main,
vir de página institucional, conter palavra importante ou ser unilateral não
comprova finalidade estrutural. URLs ambíguas ficam preservadas, com incerteza.

Serviços, documentos/legislação, portarias e institucionais recebem motivos
concretos por finalidade. Campanha de integridade com rota `/w/integridade-mt-2`
é preservada por combinação de rota e rótulo institucional; `/w/` não é, sozinho,
prova de notícia. Paginação documental/relevante permanece analisável.

Notícia/vídeo individual sem contraparte fica registrado na origem e no filtro,
sem abrir árvore. Páginas unilaterais relevantes continuam recebendo inspeção
superficial; descendentes sem finalidade estrutural comprovada não são expandidos,
com motivo `ramificacao_unilateral_nao_expandida`. Isso limita cobertura, não prova
que estejam ausentes ou sejam defeituosos. Serviços exclusivos continuam sendo
inspecionados e a opção estrutural ausente continua no relatório.

Raízes explícitas são respeitadas, inclusive cur=12. **Pares já admitidos em um
checkpoint antigo são concluídos**, preservando o contrato de retomada. A nova
política impede novas admissões, inclusive de candidatos ainda não admitidos.
Portanto retomar uma execução antiga pode ainda processar páginas posteriores
que já tinham sido admitidas; um teste novo deve começar uma comparação nova.
Referências rejeitadas antes da admissão não ficam marcadas como duplicações
para sempre: nova evidência institucional pode reativá-las. Contadores de
referências mantêm deduplicação e representação sem reintroduzir pares repetidos.
Caches genéricos de exceções de menus da versão anterior não viram prova atual;
são identificados como legados sem revalidação. O checkpoint original não é editado.

## Componentes e funcionamento

A extração identifica paginação por containers/classe, acessibilidade e controles
com parâmetros reconhecidos. O contexto fica `Paginação` ou usa o nome acessível do próprio paginador,
sem o título da notícia;
o papel é `paginacao`, inclusive nos números de um dígito. Primeiro/Anterior/
Próximo/Último continuam sendo comparados por presença, estrutura e referência.
Uma opção ausente gera observação; mudar a notícia vizinha não gera Contexto.
Isso ocorre antes da comparação, sem esconder DIVs já geradas.

Cliques opcionais também respeitam o filtro. Um controle excluído tem referência
comparada, mas teste funcional não executado e inconclusivo; presença não comprova
funcionamento. Não se enviam formulários nem se alteram dados nos sites.

## Diagnóstico

- `filtro_urls.eventos`: avaliações, exclusões/preservações, propostas e
  redescobertas; são eventos, não URLs únicas.
- `pares_excluidos`, `urls_excluidas`, categorias e duplicações mantêm as unidades
  anteriores. Categorias podem se sobrepor entre referências; não some categorias
  como conjuntos disjuntos. A soma global de URLs usa unicidade.
- Rotas `/w/` e `/-/`, exclusivas descartadas por categoria, paginação documental
  preservada e exceções legadas/revalidadas têm contadores separados.
- `cobertura.filtro_urls` acrescenta comparados, pares com falha, URLs únicas
  admitidas e exclusivas inspecionadas por finalidade (documental, serviço,
  institucional, editorial ou indeterminada).
- As decisões trazem motivo concreto ou incerteza e até 100 amostras sanitizadas,
  com quantidade de amostras omitidas. Query bruta, credenciais e fragmentos não aparecem
  nessas amostras. Somente o tipo e o valor numérico dos índices conhecidos de
  paginação são incluídos separadamente, sem o identificador da instância do portlet. O estado local de retomada contém as referências necessárias
  e deve continuar sendo tratado como interno.

Inconclusão, exclusão intencional, pendência e falha de automação não são sinônimos.
Nenhum contador afirma que uma contraparte não encontrada é ausência comprovada.
O teto de 1.000 pares HTML, drenagem, headless, 1h30 como meta, revisões, evidências,
exportações e relatórios antigos permanecem compatíveis. Não há modos/opções novos.

## Validação e repetição

```text
python -B -m unittest discover -s tests -p test_filter_stage2.py -v
python -B -m unittest discover -s tests -v
node --check web/static/app.js
python scripts/benchmark_filter_stage2.py --root /copia/da/versao --repeats 3
```

Há regressões para 12 páginas de notícias e 4 de vídeos, menus/mapas, portlets
variáveis, delta/primeira página, serviço exclusivo, editorial unilateral,
campanha de integridade, c/e, ÁUDIOS, cliques, semântica DOM em Chromium real,
checkpoints legados e candidatos restaurados. O teste inspeciona efetivamente
`pares_enfileirados` e as aberturas, não apenas as DIVs do relatório.

Os testes existentes tiveram contexto/expectativa adaptados sem eliminar
verificações: notícia unilateral agora é excluída antes da inspeção; os testes de
template profundo usam referências institucionais explícitas da campanha de
integridade. Os critérios de estrutura/editorial/reuso/documentos são mantidos. O teste de
revogação de exclusão exige evidência de legislação, em vez de um menu genérico.
Um rótulo alterado entre paginadores nomeados continua gerando diferença de
rótulo; não é confundido com ausência ou contexto editorial.

Primeira execução do baseline encontrou falta do executável Chromium em dois
testes e ignorou outros dois. O ambiente foi preparado com Chromium local, sem
mudar segurança do programa; resultados finais são registrados abaixo.
Testes locais Linux não constituem validação Windows ou nos portais reais.

## Repetir a comparação da CGE (após autorização)

1. Usar esta branch, instalar dependências/Chromium normalmente e iniciar o painel.
2. Informar os mesmos ambientes autorizados, em uma comparação **nova**. Não usar
   como início uma URL explicitamente na página posterior se quiser testar exclusão.
3. Conferir no JSON: primeiras listagens comparadas, páginas 2–12 de notícias e
   2–4 de vídeos excluídas antes da admissão, candidatos/pendências e contadores.
4. Conferir ÁUDIOS, serviços, portarias e campanha institucional; ausência de DIV
   não substitui a verificação da página/componente efetivamente analisado.
5. Examinar as exclusivas por finalidade, motivos de inconclusão, falhas e amostras;
   não atribuir todas as 890 inspeções anteriores a uma única causa.
6. Comparar escopo/ações/imagens preservados e tempo. Não usar redução no número
   de DIVs como critério isolado de sucesso. Manter dados/evidências localmente.

Nenhum portal real foi acessado nesta implementação. O exemplo de rota da campanha
não foi consultado; apenas sua categoria foi reproduzida com dados fictícios.

## Resultados da entrega

- Baseline isolado `01f10d4`: **285 testes aprovados**, sem falhas/skips após
  disponibilizar o navegador local.
- Suíte completa: **300 testes aprovados em 226,540 s**, sem falhas/skips.
- Os 15 casos do módulo novo também passaram em execução direcionada; após o
  ajuste final de amostras sanitizadas, repetidos: **15 aprovados em 4,005 s**.
- Compilação Python, sintaxe JavaScript e diff verificados. O ambiente reiniciou
  durante uma tentativa da suíte; essa execução parcial não foi considerada
  aprovada e a suíte completa foi executada novamente.

Benchmark: mesmo grafo fictício, 12 páginas de notícias e 4 de vídeos, 3 repetições
por versão, sem outros testes de navegador em paralelo. O harness simula 4 ms
por abertura e não usa rede/navegador; não mede uma varredura real.

| Medida | Etapa 1 | Etapa 2 |
| --- | ---: | ---: |
| Tempo mediano simulado | 0.205817 s | 0.050358 s |
| Aberturas simuladas | 40 | 8 |
| Pares admitidos/comparados | 20 | 4 |
| Aberturas em páginas posteriores | 28 | 0 |
| ÁUDIOS e serviço conhecido preservados | sim | sim |
| Falhas | 0 | 0 |

O trabalho omitido é intencional: 11 páginas posteriores de notícias, 3 de vídeos
e duplicações de primeira página. A origem, as primeiras listagens e o serviço
conhecido continuam comparados. Não se validou o conteúdo profundo das páginas
omitidas e não se projeta esse tempo para a CGE. A duração da suíte de testes
também não é benchmark de varredura. Não houve validação em produção ou Windows.
