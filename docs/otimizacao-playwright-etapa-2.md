# AmbiDiff · Otimização do Playwright na etapa 2

A comparação parte do commit `5ba4ad86811815b9ec76eb343c1ce8dc5b47be33`
da branch `experimento/motor-eficiencia-v2`, com a instrumentação da Etapa 1.
O trabalho concentra-se na preparação do DOM e na produção de evidências
pelo Playwright síncrono.

## Alterações

- **Preparação do DOM.** O motor usa a amostra já feita no fim da rolagem
  quando a página está no topo. Uma nova amostra é feita após
  reposicionamento ou espera. A cadência máxima da sondagem continua em
  100 ms e a última espera usa apenas o tempo restante. As janelas mínimas
  de 350 ms e de 1,3 s, os 350 ms de quietude semântica, a rolagem, a inspeção
  de abas e a confirmação de ausências isoladas continuam em vigor.
- **Prontidão para capturas.** A pausa de 450 ms deu lugar à verificação do
  estado do documento, fontes, imagens e indicadores de carregamento. A
  captura de páginas estáticas pode começar assim que esses sinais estiverem
  prontos. Páginas dinâmicas mantêm uma janela de 450 ms. Um alvo esperado
  no ambiente de origem pode receber até 1,5 s de observação. Depois de rolar
  até um alvo em página dinâmica, o navegador também verifica os recursos
  que ficaram visíveis. Quando a espera expira, a captura disponível é
  preservada. `capturas_com_recursos_pendentes` contabiliza PNGs gravados com
  sinais de carregamento ainda presentes.
- **Enquadramento e repetição.** O reset do destaque e o enquadramento
  usam a mesma chamada ao navegador. A localização do elemento usa o
  primeiro resultado do seletor e evita uma contagem separada. O reuso de
  PNG exige o mesmo ambiente, endereço, seletor e posição de referência,
  além de um documento estático com a mesma identidade, revisão do DOM e
  dimensões. Cada ambiente mantém um contexto próprio de evidências,
  separado da coleta. O worker pula a etapa quando a lista de divergências
  está vazia.
- **Interrupção e recuperação.** O evento de parada é consultado durante
  a prontidão e antes de iniciar a próxima captura. Evidências já geradas
  são anexadas ao resultado parcial. O fechamento de um contexto conserva
  as imagens já registradas e segue a recuperação limitada do scanner.
  Os nomes de PNG, IDs, marcações de elemento e área, tratamento de timeouts
  e políticas de somente leitura continuam nos contratos existentes.

A pausa de 200 ms prevista para o enquadramento por posição foi substituída
pela verificação de prontidão quando há rolagem. Nos cenários medidos, o
enquadramento usou o seletor do elemento ou a área padrão. As pausas de
rolagem para lazy loading, de interação com abas e de confirmação de
ausências permanecem pela possibilidade de alterações tardias no DOM.

## Medições antes e depois

Os dois checkouts foram comparados em Linux com o Chromium 154 do sistema,
Playwright 1.64.0 e Python 3.12.14. As fixtures `portais_perf(3)` e
`portais_perf(3, dinamico=True)` foram servidas em loopback. Cada cenário usou
os mesmos endereços e três processos independentes por versão em ordem
alternada, com comparação inteligente, evidências e exportação padrão
do worker.

Preparação, evidências e tempo total de coleta vêm do diagnóstico da
Etapa 1. O tempo total do worker foi medido da chamada até seu retorno,
incluindo exportação e gravação do diagnóstico. A qualidade das capturas
foi verificada pela decodificação dos PNGs, dimensões de 1.366 × 850,
imagem com conteúdo e correspondência do contorno laranja com a marcação.

| Cenário | Medição | Referência (s) | Otimizada (s) | Redução da mediana |
| --- | --- | ---: | ---: | ---: |
| Estável | Preparação e estabilização | 2,023 | 1,757 | 13,1% |
| Estável | Evidências | 3,053 | 2,493 | 18,3% |
| Estável | Coleta do motor | 7,018 | 6,353 | 9,5% |
| Estável | Total do worker | 7,219 | 6,541 | 9,4% |
| Dinâmico | Preparação e estabilização | 6,494 | 6,184 | 4,8% |
| Dinâmico | Evidências | 11,873 | 11,761 | 0,9% |
| Dinâmico | Coleta do motor | 23,030 | 22,429 | 2,6% |
| Dinâmico | Total do worker | 23,224 | 22,656 | 2,4% |

No cenário estável, o total do worker variou de 7,020 a 7,846 s na
referência e de 6,425 a 6,715 s na versão otimizada. No dinâmico, os
intervalos foram de 22,997 a 23,427 s e de 22,572 a 23,254 s. A sobreposição
no cenário dinâmico limita a interpretação da diferença. Nele, a janela
de observação de 450 ms continuou aplicável às 18 navegações de evidência.
O cenário estável usou duas navegações de evidência em cada execução.

| Cenário | Pares comparados | Inconclusivos | Falhos | Divergências | Evidências por execução |
| --- | ---: | ---: | ---: | ---: | --- |
| Estável | 3 | 0 | 0 | 9 | 18 PNGs, 16 com destaque e 2 de área |
| Dinâmico | 3 | 0 | 0 | 9 | 18 PNGs, 16 com destaque e 2 de área |
| HTTP 503 e resposta não HTML unilateral | 1 | 1 | 1 | 0 | 0 PNGs |

Em cada cenário, as duas versões produziram os mesmos itens extraídos,
estados terminais, divergências, IDs e referências de evidência. Os PNGs
dos cenários estável e dinâmico tiveram pixels idênticos em todas as
repetições, comparados pela imagem RGB decodificada. O reuso de PNG para
o mesmo seletor foi verificado separadamente em uma regressão automatizada.

O cenário de HTTP 503 e resposta não HTML unilateral teve uma execução
por versão. Conservou os diagnósticos correspondentes e a coleta parcial.
A etapa de evidências passou de 0,390 s para zero por dispensar o
lançamento de contextos com a lista de divergências vazia. O total do
worker foi de 2,805 s na referência e 2,184 s na versão otimizada. Essa
execução serve para verificar o comportamento em falha.

## Testes e limites

| Verificação | Resultado |
| --- | --- |
| `python -B -m unittest discover -s tests -v` na referência | 326 testes aprovados em 175,576 s. |
| `python -B -m unittest discover -s tests -p test_playwright_etapa2.py -v` | 7 testes aprovados em 12,787 s. |
| `python -B -m unittest discover -s tests -v` com a otimização | 333 testes aprovados em 184,836 s. |
| `node --check web/static/app.js` e `git diff --check` | Aprovados. |

A suíte completa passou sem falhas nem saltos nas duas versões. Os testes
originais de filtros, pareamento, ÁUDIOS da CGE, exportação e retomada
participaram da execução.

As regressões novas usam Chromium real e servidores locais. Elas verificam
a reutilização por seletor e contexto, a invalidação após mutação, a
presença de destaque em PNG para um alvo inserido após 650 ms, uma imagem
lazy que só carrega após a rolagem, o limite da espera visual, timeout de
captura, interrupção e recuperação de contexto encerrado.

A janela de observação detecta condições observáveis no DOM e no navegador.
Tarefas com eventos futuros, aplicações com estados de interface externos
ao DOM e imagens específicas de uma sessão podem exigir nova captura.
Os tempos incluem renderização, fontes, latência da máquina de teste e
escrita em disco. São resultados locais com Chromium real sobre portais
sintéticos. Windows e portais institucionais ficaram fora da validação.
