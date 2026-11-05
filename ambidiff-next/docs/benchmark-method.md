# Validação comparativa obrigatória

A meta **experimental** é reduzir significativamente o tempo do Next, de
preferência 30–50%, preservando a detecção relevante. A meta não é um ganho
comprovado nem um prazo de interrupção. INDEA, SEMA e outros portais reais
**não fazem parte deste benchmark**: dependem de autorização futura explícita.

## Executar

Instale as dependências de desenvolvimento e o Chromium. Na pasta do Next:

```text
python scripts/benchmark_comparative.py --program both --news 8 --repeats 1
python scripts/benchmark_comparative.py --program both --news 30 --repeats 3
python -m pytest tests/test_benchmark.py -q
```

Comece pelo cenário pequeno. O segundo comando é opcional e custa mais tempo;
não é um requisito para manutenção documental. O script aceita `both`, `next`
e `legacy`. Por padrão os artefatos ficam em `data/benchmarks/<data-hora>/`, fora
do Git. Nunca envie esses arquivos automaticamente. Um `--output` local pode
mudar a pasta. O script não aceita URLs arbitrárias.

No Linux usado para desenvolvimento, `AMBIDIFF_NEXT_CHROMIUM=/usr/bin/chromium`
pode selecionar o Chromium instalado. O caminho é uma preferência do harness,
não uma exigência do Windows. No Windows a instalação normal do Playwright
continua preferível. A versão do navegador e o hardware devem ser registrados
com os resultados antes de comparar execuções em máquinas distintas.

## Mesmos dados para os dois programas

`tests/benchmark_portals.py` inicia dois servidores exclusivamente em
`127.0.0.1` e portas efêmeras, mantidos vivos para os dois produtos. Os dois
recebem as mesmas raízes, viewport 1366×850, base HOMOL declarada desatualizada,
links e eventos. Não é importado código do legado no Next; somente o harness
de benchmark chama a API pública atual de `ambidiff.paired` como referência.
O código legado e seus relatórios não são modificados.

O manifesto da fixture contém oito diferenças conhecidas:

1. ÁUDIOS presente apenas em A.
2. Agendamento presente apenas em B.
3. Consulta Pública com destino final diferente após redirecionamento.
4. Regulamento com referências documentais diferentes em rota Liferay sem extensão.
5. Detalhes do serviço com aba responsiva apenas em A.
6. Acessar serviço com cor diferente.
7. Atendimento oculto invisível por CSS em B.
8. Painel de atendimento encoberto em B.

Casos negativos: Ouvidoria movida entre regiões HTML com mesma finalidade,
referência externa igual e datas editoriais distintas. As páginas de notícias
repetem um cabeçalho e possuem um controle Próximo que retorna ao começo no
último item; a árvore é finita, mas contém ciclo. Notícias podem ser aumentadas
até 100. As referências externas usam `.invalid` e não devem ser abertas.
O servidor conta chamadas HTML, documentos, redirects e métodos inseguros.
A fixture usa dados fictícios, incluindo o pequeno arquivo que simula PDF.

## O que é medido

- Tempo total de cada execução, incluindo evidências/checkpoints produzidos.
- Tempos instrumentados por fase; fases aninhadas não devem ser somadas.
- Navegações publicadas pelo produto e requisições HTML observadas pelo servidor.
  Este último inclui recargas de ações/evidências; redirects têm contador próprio.
- Elementos verificados, testes funcionais executados/inconclusivos, comparações
  visuais efetivamente concluídas e cobertura por categoria quando publicados.
- Número de arquivos e bytes produzidos, incluindo estado/checkpoints.
- Diferenças detectadas relacionadas ao manifesto por **natureza e nome**, não
  por número de DIV. O redirect pode também ser associado à rota `/consulta`,
  pois o legado usa o título da página nesse diagnóstico.
- TP, FP candidatos, FN identificáveis, precisão e recall no manifesto.
  Duplicar um mesmo achado não multiplica TP. Observações adicionais sem vínculo
  à verdade ficam visíveis como candidatos FP e precisam de revisão do manifesto
  e das imagens; não são descartadas para melhorar artificialmente a precisão.

O adaptador separa editoriais e falhas da automação das diferenças relevantes.
Achados possíveis contam como candidatos de diferença detectados, sem virarem
atestados de defeito. Essa distinção deve acompanhar qualquer interpretação da
precisão. O manifesto não representa todos os defeitos possíveis de um portal.

O legado não publica contagens diretamente equivalentes de elementos verificados
nem de comparação real de pixels. O harness registra **null**, não inventa zero
nem converte número de links encontrados em número de componentes validados.
Se for necessária uma métrica mais fina, instrumente o harness de observação de
maneira equivalente, com nova regressão; não altere o legado para favorecê-lo.

## Critério de aprovação

`qualify_gain` recusa ganho qualificado se:

- Next perdeu uma diferença conhecida que o legado detectou;
- restam FN conhecidos no Next;
- os candidatos FP aumentaram;
- cobertura obrigatória é inferior ou desconhecida;
- uma execução falhou/interrompeu;
- não houve redução do tempo total.

Em repetições usa-se mediana do tempo; cobertura é conservadora (mínimo do Next,
máximo do legado), e a detecção só ganha crédito se ocorreu em todas. A ordem
é alternada entre repetições para reduzir viés de aquecimento. Isso não controla
CPU/rede/disco perfeitamente; por isso o relatório continua experimental.

A ausência de métricas equivalentes do legado impede declarar ganho qualificado
com a instrumentação atual, mesmo que o tempo do Next seja menor. Os números
brutos, falhas, lacunas e motivos permanecem no `summary.json`. Assim, rapidez
por trabalho omitido não é aprovada e desconhecido não se torna sucesso.

## Resultados e limites

As dez regressões unitárias do benchmark foram executadas localmente: **10
aprovadas**, sem skips. Cobrem a rejeição de um Next 50% mais rápido que perdeu
ÁUDIOS, redução funcional, métricas ausentes, falhas, pontuação e ciclo local.
Uma tentativa no sandbox sem sockets falhou com `PermissionError`; a repetição
com permissão de loopback passou. Isso não é validação em portais institucionais.

Os resultados reais de execução dos motores devem ser registrados na entrega,
separadamente do sucesso dos testes do harness. Não substitua benchmark real
por tempos de mocks. Ganhos percentuais de um portal real só podem ser afirmados
após teste autorizado, com evidências, cobertura equivalente e medições antes/depois.
