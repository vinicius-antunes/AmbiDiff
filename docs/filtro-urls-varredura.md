# Admissão de URLs com contexto

**Regras atuais:** a [segunda etapa](filtro-urls-etapa2.md) refina esta versão;
a presença em menus não é uma exceção automática e os diagnósticos são limitados
a amostras sanitizadas. Os resultados abaixo descrevem a primeira etapa.

Base: `main` remota em `52e8676`. Branch: `perf/filtro-urls-varredura`.
A branch Next não foi usada como base e não recebe alterações desta tarefa.

## Comportamento

`ambidiff/urlfilter.py` centraliza a política aplicada por `_propor`, antes de
admitir candidatos ou consumir vagas HTML. O motor de comparação permanece ativo
na origem: opções ausentes, destinos diferentes, documentos e menus continuam
sendo verificados. Excluir navegação não prova que o conteúdo dos destinos seja
igual, correto ou inexistente.

São evitados, com evidência editorial:

- Rotas contendo segmentos `/w/` ou `/-/`;
- Paginação adicional por cur/page/start, inclusive chaves de portlets Liferay,
  caminhos page/pagina e controles Próximo/Anterior;
- Combinações de ano/mês/dia/categoria/ordenação;
- Resultados reconhecidos de pesquisa interna;
- Impressão derivada por padrão reconhecido **e** URL original já representada.

A listagem inicial permanece admissível: cur/page=1, start=0 e delta isolado não
significam página adicional. Parâmetros c/e e referências de conteúdo não são
eliminados. A dúvida preserva a visita. Serviços, legislação/documentos, páginas
institucionais e referências em menus/submenus são exceções; uma contraparte
estrutural ou desconhecida preserva o par inteiro. Raízes informadas pelo usuário
não passam pelo filtro, e pares já admitidos não são removidos.

A normalização existente em `core.url_limpa` já remove rastreamento reconhecido.
Essa capacidade foi reaproveitada. A política também mantém identidade conservadora
para admissão, removendo somente tracking conhecido; não reescreve o destino do
Item ou os comparadores. URLs originais continuam nas evidências existentes.
Parâmetros funcionais e fragmentos não são removidos pela nova função de identidade.

Referências excluídas não entram em candidatos_vistos/admitidos. Se depois forem
observadas como estruturais, podem ser reconsideradas. Quando a nova observação
identifica um candidato pendente já conhecido com prioridade maior, `Fila.promover`
reorganiza o heap sem duplicá-lo. Rotação e drenagem da fila continuam existentes.
Não há novo modo, checkbox, prazo de varredura ou alteração de segurança.

## Diagnóstico e retomada

`filtro_urls` no JSON, diagnóstico e checkpoint guarda os motivos e contadores.
O resumo de cobertura inclui contagem de pares/referências excluídos, URLs únicas,
URLs por categoria, duplicações evitadas e exceções estruturais preservadas.
`excluidas_por_categoria` contabiliza pares; `urls_excluidas_por_categoria` usa
URLs únicas. Comparados/pendências/falhas continuam nos contadores originais.
Exclusões intencionais não viram falhas de acesso ou pares inconclusivos. Uma
URL pode aparecer em referências de categorias diferentes; não some essas
categorias como conjuntos disjuntos. O total global de URLs é único.
`duplicacoes_evitadas` conta pares normalizados repetidos; a métrica original
`urls_duplicadas` também inclui o reaproveitamento de inspeções unilaterais.

As referências detalhadas do filtro removem query, credenciais e fragmentos via
`security.url_diagnostica`. Checkpoints locais mantêm o estado necessário à
retomada, assim como já mantêm a fila original; devem ser tratados como dados
internos. Não são enviados ao GitHub. Checkpoints anteriores sem filtro continuam
aceitos e a fila já admitida é honrada, mesmo se contiver notícias.

Cobertura integral não é declarada quando existem exclusões ativas. A conclusão
da fila permanece distinta da cobertura do portal. A meta de 1h30 não é prazo de
parada; o teto HTML de 1.000 pares permanece inalterado.

## Testes

```text
python -B -m unittest discover -s tests -p test_urlfilter.py -v
python -B -m unittest discover -s tests -v
node --check web/static/app.js
git diff --check
python scripts/benchmark_urlfilter.py --root /copia/da/versao --repeats 3
```

As 13 regressões novas verificam os padrões/exceções, c/e/fragmentos, busca,
impressão, tracking, 1.100 referências editoriais sem consumir o teto, ÁUDIOS,
HTTP/destinos diferentes, URLs iniciais, promoção, sanitização e retomada atual e
legada. Os três testes antigos de templates editoriais agora usam links em um
menu institucional fictício, para exercitar a exceção estrutural com o filtro
ativo. Todas as asserções originais de diferenças editoriais, estrutura, documentos
e reuso foram mantidas. Não foi criado desligamento do filtro em produção.

A primeira suíte ampliada teve três falhas decorrentes da mudança deliberada na
exploração de notícias. Após ajustar esse contexto da fixture, os 23 testes de
`test_smart.py` passaram, preservando as verificações do motor profundo.

## Limitações

A decisão usa evidência de contexto disponível, não análise semântica do conteúdo
ainda não visitado. Menus ricos e contextos ambíguos podem preservar muitas URLs.
Não se garante excluir todo editorial, e podem existir diferenças dentro de
páginas intencionalmente não abertas. Essa redução de exploração é explícita,
não validação do conteúdo omitido. Apenas a origem e exceções efetivamente
visitadas sustentam as conclusões.

Comparadores, servidor Flask, interface, exportações e parâmetros funcionais do
motor não foram reescritos. Nenhum portal institucional foi acessado. Testes usam
Chromium instalado no Linux e fixtures; Windows e portais reais não foram validados.

## Resultados desta entrega

- Baseline isolado da main: 272 testes aprovados em 178,862 s.
- Regressões novas: 13 aprovadas; comparação profunda: 23 aprovados.
- Suíte final: **285 testes aprovados em 184,841 s**, sem falhas ou skips.
- Sintaxe JavaScript, compilação Python e diff verificados.

O benchmark reproduz o mesmo grafo fictício em ambas as versões, com 49 referências
por ambiente e ÁUDIOS unilateral. Ele usa as fixtures simuladas existentes, sem
navegador/rede, adicionando **4 ms fixos por abertura simulada**. Três repetições
por versão, sem outros testes de navegador concorrentes na medição final:

| Medida | main 52e8676 | filtro |
| --- | ---: | ---: |
| Tempo mediano simulado | 0,483006 s | 0,058316 s |
| Aberturas simuladas | 100 | 6 |
| Pares HTML admitidos/comparados | 50 | 3 |
| Falhas | 0 | 0 |
| DIVs na origem | 1 | 1 |
| Detecção de ÁUDIOS | preservada | preservada |
| Duas páginas estruturais conhecidas visitadas nos dois ambientes | sim | sim |

Os 47 pares intencionalmente omitidos são 30 rotas editoriais, 10 paginações,
5 filtros de datas, 1 pesquisa e 1 impressão redundante. A diferença de tempo
(~87,9%) decorre principalmente dessa exploração evitada. **Não representa ganho
em portal real nem cobertura equivalente do conteúdo profundo dessas 47 páginas.**
A verificação das referências na origem permanece; novas divergências que só
existam dentro de conteúdo omitido não podem ser afirmadas como detectadas.

Para comparar outra cópia da base sem modificar branches, forneça seu caminho a
`--root`. O script produz JSON em stdout; redirecione para uma pasta local fora
do Git. Nenhum log, relatório, checkpoint ou evidência de execução foi versionado.
