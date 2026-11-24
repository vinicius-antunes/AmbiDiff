# AmbiDiff · Auditoria inteligente de cobertura

A auditoria exporta as decisões observadas em uma execução. Usa o mesmo
pareamento, política de URLs, fila e critérios do relatório de comparação.
Na tela **Histórico**, abra a pasta, localize a execução e escolha
**Exportar auditoria de cobertura**, em JSON ou CSV. Relatórios anteriores
sem arquivo de auditoria mostram uma mensagem de indisponibilidade.

## Funcionamento

- `ambidiff/urlfilter.py` fornece as evidências e fontes de identidade de
  portal usadas pela decisão atual. A política existente continua
  determinando admissão, exclusão e reconsideração.
- `ambidiff/paired.py` e `ambidiff/core.py` fornecem o contexto de descoberta,
  as observações de referências fora da fila HTML e os marcos confirmados.
  `ambidiff/coverage_audit.py` reúne essas informações com os estados
  terminais e os diagnósticos do checkpoint já produzido.
- `web/server.py` associa o arquivo à execução e oferece os downloads.
  `web/static/app.js` mostra a ação no histórico.
  `ambidiff/storage.py` remove o arquivo junto com a execução.
- `tests/test_coverage_audit.py` cobre decisões, volume acima da amostra,
  segurança de exportação, retomada e a ação no Chromium.

A unidade da auditoria é uma referência unilateral ou uma combinação de
URLs efetivamente observada pelo motor. Uma redescoberta da mesma chave
preserva uma linha e a primeira origem observada. O resumo também conta
URLs distintas por lado, sem contar novamente a mesma URL quando ela
aparece em combinações diferentes. Referências reconhecidas como
duplicadas pelo scanner ficam explícitas e fora das comparações novas.
Os estados do JSON distinguem descoberta, admissão, comparação, exclusão,
falha, falta de contraparte, referência não HTML, destino fora do escopo,
duplicação, falta de admissão e análise inconclusiva.

`comparacao_html` reflete o estado terminal do par. Uma exclusão, uma
conferência documental ou uma inspeção unilateral não comprova
equivalência do conteúdo. `categoria_filtro`, `motivo_filtro` e
`exclusoes_observadas` permitem revisar a regra aplicada, inclusive em uma
reconsideração. `categoria` agrupa finalidades para análise. O sinal
`heuristica` identifica a classificação baseada na política e
`inconclusiva` indica falta de evidência de análise ou de classificação.
Uma linha comparada pode ter categoria indeterminada. O CSV tem as mesmas
linhas do JSON. As contagens agrupadas por categoria e resultado estão no
resumo JSON e podem ser reproduzidas agrupando as colunas do CSV.

O arquivo local `auditoria_cobertura_<id>.json` é atualizado em lote
após checkpoints confirmados, por substituição atômica. A lista de
auditoria fica fora do relatório e do checkpoint padrão. O arquivo
preserva o último lote gravado em caso de falha de escrita. A retomada
usa o lote anterior se a assinatura corresponder ao checkpoint de
origem. Quando falta esse lote, a nova auditoria sinaliza
`historico_anterior_incompleto` e trabalha com o que o checkpoint
realmente preservou e com o que foi observado na continuação.
A disponibilidade exige ao menos uma decisão além de descoberta ou
admissão pendente. Os mesmos marcos permitem exportar coletas interrompidas.

URLs e origens passam pela sanitização de diagnóstico. Credenciais,
queries, fragmentos e marcas comuns de segredo em caminhos e rótulos
são omitidos. IDs opacos mantêm referências distintas quando a exibição
sanitizada coincide. A paginação registra somente o tipo normalizado
de controle e o índice numérico dentro do limite aceito pela exportação.
A auditoria usa códigos de falha, sem copiar as mensagens de erro do
navegador. O CSV protege células iniciadas por caracteres de fórmula.

## Exemplo fictício

Recorte de uma linha JSON de paginação excluída.

```json
{
  "execucao_id": "20261124_120000_abcdef",
  "id_referencia": "par-0123456789abcdefabcd",
  "url_a": "https://prd.exemplo.test/radio-local",
  "url_b": "https://des.exemplo.test/radio-local",
  "origem": {
    "pagina_a": "https://prd.exemplo.test/radio-local",
    "pagina_b": "https://des.exemplo.test/radio-local",
    "trilha": ["Página inicial", "Rádio", "Página 43"]
  },
  "status": "excluida",
  "categoria": "paginacao_editorial",
  "motivo_filtro": "paginacao editorial",
  "paginacao": [[{"parametro": "cur", "valor": 43}], [{"parametro": "cur", "valor": 43}]],
  "comparacao_html": false
}
```

O CSV usa ponto e vírgula, com objetos e listas em JSON dentro da
célula. As colunas `status` e `categoria` bastam para uma tabela
dinâmica de exclusões.

```csv
execucao_id;id_referencia;status;categoria;comparacao_html
20261124_120000_abcdef;par-0123456789abcdefabcd;excluida;paginacao_editorial;False
```

## Validação e desempenho

A suíte geral passou com **343 testes em 181,2 s**, sem falhas ou testes
ignorados, em Linux com Python 3.12.14 e Chromium local. As sete regressões
direcionadas passaram, assim como `node --check web/static/app.js` e
`git diff --check`.

A fixture registrou 122 exclusões distintas de paginação e conservou a
amostra normal de 100 referências. As decisões com e sem auditoria
mantiveram navegações, estados, documentos e DIVs iguais. O teste de
retomada preservou o ID de ÁUDIOS e restaurou a cobertura anterior quando
a assinatura correspondia. O teste de falha de escrita confirmou a
preservação do checkpoint e do resultado de comparação.

O tempo abaixo foi medido em chamadas do motor com checkpoint em volume
local. A cadeia de `tests/test_update18.py` foi medida em cinco repetições
por configuração sem atrasos de rede ou Chromium. A fixture
`portais_perf(3)` usou Chromium real em loopback, com três repetições
por configuração. A ordem de ativação foi alternada e as saídas foram
comparadas em todas as amostras. Os valores são medianas.

| Cenário | Sem auditoria | Com auditoria | Gravação e projeção em lote | Arquivo de auditoria |
| --- | ---: | ---: | ---: | ---: |
| 25 pares simulados | 27,4 ms | 30,8 ms | 2,6 ms | 28,6 kB |
| 1.000 pares simulados | 759,8 ms | 908,4 ms | 79,8 ms | 1,12 MB |
| 3 pares com Chromium em loopback | 4,228 s | 4,056 s | 1,4 ms | 3,6 kB |

O custo adicional observado na cadeia de 1.000 pares foi de cerca de
149 ms, ou 19,5% em um cenário sem espera de navegação. A diferença do
loopback ficou na faixa de variação observada e não demonstra ganho de
velocidade. O checkpoint final da cadeia maior cresceu 130 bytes pela
instrumentação. A lista detalhada ficou no arquivo separado.

## Limites e validação manual

A auditoria descreve referências observadas e decisões registradas.
Conteúdo atrás de referência excluída, em página inacessível ou em
navegação que não chegou à coleta continua fora da cobertura. Um par
pode usar outro ambiente que não DES, conforme a configuração da
execução. O formato mantém as posições A e B e os nomes de ambiente no
envelope JSON. A auditoria usa a primeira origem registrada, e as
redescobertas em todos os menus não formam uma lista de ocorrências.
A exportação pode apresentar o mesmo texto de URL para queries diferentes.
O arquivo retrata o último marco gravado e pode ficar atrás do estado
em memória após um encerramento abrupto.
Windows e portais institucionais ficaram sem validação nesta etapa.

Em uma execução autorizada pelo mantenedor:

1. Iniciar uma comparação pequena em modo somente leitura e manter a
   configuração de escopo acordada para os dois ambientes.
2. Exportar JSON e CSV pelo Histórico. Conferir IDs, contagens e origens.
   Verificar uma referência presente no menu e uma página efetivamente
   comparada.
3. Confirmar exemplos de exclusão de paginação e de portal vizinho,
   observando a regra e a evidência registradas. Conferir também um
   serviço ou documento relevante que tenha sido preservado.
4. Comparar a DIV de uma opção exclusiva, como ÁUDIOS, com sua referência
   na auditoria. Verificar que uma exclusão não aparece como equivalência.
5. Interromper uma execução, abrir o relatório parcial, retomar e
   confirmar que o histórico anterior segue acessível e que os registros
   preservados aparecem na nova auditoria.
