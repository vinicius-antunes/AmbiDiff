# Plano de desempenho — meta de reduzir em pelo menos 50% o tempo de varredura

**Status:** diagnóstico técnico e backlog, **não implementado nem validado em portal real**.
**Escopo:** AmbiDiff em Windows, modos convencional e inteligente; acesso autorizado a PRD/DES/LAB; preservar resultados parciais e diagnóstico.

## Linha de base real disponível: SEFAZ v1.5

Relatório recebido `comparacao_20261021_110633_91d24f.json`, coletado em 21/10/2026:

| Evidência | Valor |
|---|---|
| Início inferido do identificador | 11:06:33 |
| Geração do relatório (`gerado_em`) | 11:54:29 |
| Tempo decorrido até gerar relatório | 47 min 56 s (2.876 s) |
| Limite preventivo do crawler | 45 min |
| Pares visitados, incluindo tentativas/arquivos/erros | 637 |
| Pares ainda na fila | 319 |
| Páginas coletadas | PRD: 529; DES: 528 |
| Situação | Parcial por limite preventivo de tempo |

**Meta A comparável:** visitar e analisar os *mesmos 637 pares* com cobertura e evidências equivalentes em **até 23min58s**; não declarar sucesso se a redução vier de menos inspeções sem contabilizá-las.

**Meta B ampliada:** concluir a fila de aproximadamente 956 pares conhecidos no mesmo teto de 23min58s, **se novos links não alterarem o total**, o que exige velocidade substancialmente maior; base parcial não permite garantir conclusão. Não elevar o limite de 45 min como substituto de otimização.

A v1.5 não traz `metricas.tempos_segundos` nem `operacoes_segunda_leitura`. Portanto, não existe medição real de quanto tempo a SEFAZ gastou em segunda leitura. A média bruta aproximada de 2.876/637 = 4,51 s/par inclui geração do relatório e etapas finais; não é latência de navegação isolada.

O benchmark existente do modo inteligente (portais HTTP sintéticos) mostrou 25,274 s → 13,047 s, 48,38% de redução, mas dispensou 12 de 18 preparações profundas. **Não é evidência de ganho semelhante no Liferay da SEFAZ**.

## Hipóteses técnicas priorizadas (precisam ser medidas no portal)

| Ordem | Candidato | Indício no código | Experimento conservador | Risco principal |
|---|---|---|---|---|
| P0 | Segunda leitura excessiva no modo inteligente | `paired.py` marca `duvida_estrutural` com qualquer diferença não editorial ou inconclusivo; espera 950 ms em cada ambiente e faz outra preparação/extração | Registrar motivo por par e comparar rechecagem seletiva baseada em coleta instável, bloco de ausências ou incerteza fundamentada | Ocultar divergência de menu ou confundir carregamento tardio com ausência real |
| P0 | Rolagem e estabilidade repetidas em toda página | `_preparar_conteudo` inicia com 250 ms, percorre até 35 passos com 160 ms, volta ao topo, espera 250 ms e exige duas leituras estáveis a intervalos de 380 ms; até 7 s + estabilidade | Medir tempo/passo e testar janela adaptativa baseada em mutações/DOM, com preparação profunda quando sinais de dinâmica/lazy loading existirem | Perder conteúdo carregado tardiamente, abas, documentos e controles ocultos |
| P1 | Preparação paralela PRD/DES | Navegação, rolagem e extração acontecem de modo sequencial em duas páginas | Prototipar API Playwright assíncrona para executar somente A e B do mesmo par em paralelo, concorrência limitada; comparar exatamente os mesmos snapshots | Regressões de estado do navegador, custo de CPU/RAM e tráfego do órgão; API sync não é thread-safe |
| P1 | Otimização de templates reais do Liferay | `smart.py:JS_TEMPLATE` recusa qualquer elemento `script`, de modo que páginas Liferay com scripts ficam no percurso completo | Investigar equivalência por sinais estáticos relevantes e dados de DOM efetivamente carregados; provas por amostras profundas e alternância periódica | Declarar igual uma página com comportamento dinâmico/menus divergentes |
| P2 | Recursos e renderização | Imagens/fontes/terceiros podem atrasar `domcontentloaded` ou estabilidade visual | Medir primeiro número de requisições por origem; só estudar bloqueio estrito de recursos externos não essenciais mediante autorização e testes de equivalência | Falha de lazy loading, SVG, layout, screenshot ou funcionalidade |
| P2 | Capturas, auditoria, documentos e exportação | Até 40 evidências, 240 s em capturas; modo inteligente verifica até 20 pares de documentos com tempo/requisições limitados | Medir separados `capturas`, `auditoria`, `documentos`; reutilização local de metadados sem ignorar divergência; gerar capturas somente para DIVs importantes quando permitido | Perda de provas, relatórios incompletos, resultados inconclusivos |
| P2 | Fila, normalização e checkpoints | URLs são normalizadas/deduplicadas; checkpoint a cada 20 pares; links são inspecionados por par | Medir custo de checkpoint/serialização e categorias das URLs; reduzir trabalho repetitivo sem descartar pares válidos | Excluir seção real, não recuperar resultados parciais |

**Não fazer para "ganhar velocidade":** reduzir artificialmente páginas visitadas; esconder diferenças; considerar PRD automaticamente correto; remover toda segunda leitura; pular páginas institucionais; reduzir indiscriminadamente timeout; desligar TLS; bloquear scripts/imagens/recursos essenciais; disparar muitas requisições paralelas aos portais; aumentar o limite de tempo e apresentar isso como ganho.

## Telemetria e campos JSON — primeira melhoria a implementar

Adicionar em **todas** as execuções, inclusive interrupção, erro com checkpoint e recuperação:

- `iniciado_em`: data e hora local registradas ao iniciar; preferir também ISO 8601 com fuso em campo adicional se houver necessidade;
- `finalizado_em`: data/hora em que o processamento efetivamente terminou, incluindo exportações ou com semântica explicitamente documentada;
- `duracao_segundos`: duração real medida com relógio monotônico (não depender do ID nem de diferença entre horários de parede);
- `status_final`: concluído, parcial, interrompido, erro ou inconclusivo;
- `motivo_parada`, páginas visitadas/coletadas, pendentes e profundidade realmente inspecionada;
- `metricas.tempos_segundos`: navegação, preparação, rolagem, extração, segunda leitura, comparação, documentos, evidências, auditoria e exportação, com contagens;
- `segunda_leitura`: total, motivo, página, se havia carregamento incompleto, resultados antes/depois e custo individual com amostragem limitada;
- `media_segundos_por_par`, `requisicoes_por_par` e indicadores de falhas/timeout, quando fundamentados.

Distinguir tempo de varredura de tempo de geração do relatório; não somar tempos aninhados de segunda leitura com preparação/extração para inferir duração total. Salvar métricas no checkpoint de maneira consistente, sem corromper/reescrever relatórios originais.

A interface pode exibir **% de progresso e tempo restante aproximado** calculado a partir de avanço recente; não garantir ETA quando a fila cresce ou nas etapas finais. Até esta documentação, esses campos e a ETA **não são considerados entrega validada**.

## Experimentos e critérios de aceite

1. **Instrumentar antes de otimizar.** Capturar duas ou três execuções representativas autorizadas, nos mesmos URLs, mesma rede/perfil de máquina, mesmas opções de clique/auditoria e modo de varredura. Dados sensíveis não devem sair do órgão.
2. **A/B sobre mesma cobertura.** Comparar commit base e protótipos em 3 repetições, alternando ordem e registrando mediana, p95 por par, tempo até checkpoint e tempo final.
3. **Mudança isolada.** Primeiro controlar segundas leituras redundantes; depois preparação/rolagem; em seguida experimentar paralelismo limitado. A cada etapa, suíte de regressão, comparação de DIVs, falhas, pares concluídos e relatórios parciais.
4. **Proteções obrigatórias.** CGE opção ÁUDIOS ausente no DES continua relevante; SEFAZ avisos institucionais confirmados preservados; documento 2026 segue para revisão, sem declarar erro; links, ícones realmente ausentes e controles institucionais devem permanecer detectáveis; widget externo repetido não deve dominar relatório.
5. **Gatilho de fallback.** Caso estabilidade/DOM/abas/menus falhem ou resultado fique inconclusivo, retornar à preparação profunda e registrar motivo. Interrupção deve produzir resultados parciais e diagnóstico.
6. **Comparabilidade.** Relatar cobertura estrutural, páginas omitidas de inspeção profunda e documentos verificados. Nunca comparar somente tempos se a versão otimizada fez menos trabalho; promover ganho experimental apenas com perdas explicitadas.
7. **Alvo:** redução ≥50% da mediana **para o mesmo conjunto de páginas e a mesma cobertura declarada**, sem regressões críticas. Separadamente medir se o portal inteiro pode ser concluído dentro dos limites.

## Ordem de implementação sugerida

- **Entrega 1 (P0):** timestamps e métricas de custo/causas da segunda leitura, testes de serialização, erro e interrupção.
- **Entrega 2 (P0):** releitura seletiva conservadora e regressões sem omitir diferenças reais.
- **Entrega 3 (P0/P1):** otimização adaptativa da preparação/rolagem e fallback profundo.
- **Entrega 4 (P1):** prova de conceito de preparação PRD/DES concorrente com limite de rede e testes Windows.
- **Entrega 5:** benchmark comparável em cenários SEFAZ/CGE/USEIA autorizados, com documentação e decisão de merge.

**Integração:** manter esta iniciativa separada da `main`, preservar os PRs USEIA/CGE e validar conflitos antes de unir melhorias.