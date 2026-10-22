# Atualização para portais extensos — execução, qualidade e revisão

Base: `perf/otimizacao-varredura`, commit `ea8abad`. Implementação autorizada
pelo usuário após a análise da especificação de 22/10/2026. Não incorpora
branches USEIA/CGE, não altera `main` e não publica o projeto.

## Diagnóstico e alcance da evidência

O código confirmou limites globais de 45 minutos nos dois coletores, teto de
2.500 URLs, fila FIFO, até 20 pares documentais, mistura de bloqueios intencionais
com falhas e checkpoints sem fila restaurável. A base já tinha cursor de logs,
reconexão, preparação adaptativa, releitura seletiva, HEAD sem corpo no fluxo
oficial, comparação contextual, revisão e exportações. Tudo isso foi preservado.

As métricas e DIVs do INTERMAT são **relatos fornecidos na especificação**.
`comparacao_filtrado_20261022_122514_b816d8.json` não foi anexado nesta etapa.
Não houve acesso ao INTERMAT, CGE, AGER, SEFAZ, POLITEC ou qualquer recurso
corporativo. Não afirmamos reproduzir ou validar as ocorrências reais.

## Etapa 1 — duração, fragmentos e tema

- Removido o limite global obrigatório de duração na comparação pareada e na
  coleta individual, sem outro teto de tempo global ou campo de duração na UI.
  Mantidos timeouts por operação, TLS, deduplicação, interrupção cooperativa e
  limite de 15 falhas consecutivas. O argumento interno antigo `max_segundos`
  de `coletar_site` foi retirado; não era opção do painel.
- Fragmentos não são apagados indiscriminadamente. Âncora existente no DOM da
  página atual, sem indicação observada de controle/roteador, é referência de
  rolagem; fica registrada como tal. Fragmento `#/...`, `#!...` ou com parâmetros
  continua sendo possível destino funcional. Fragmento cujo papel não foi
  comprovado vira referência/pendência inconclusiva, sem afirmar defeito.
  Um `#123` de outra página ainda não aberta não recebe equivalência presumida.
- Tema escuro aplicado globalmente a seletores, opções, checkboxes e links, com
  foco visível, contraste e adaptação a janela estreita. Aparência de menus
  nativos depende do navegador/Windows e requer conferência manual.

Arquivos: `core.py`, `paired.py`, novo `urlpolicy.py`, `web/static/style.css`.

## Etapa 2 — preparação, fila, escala e retomada

### Preparação e métricas

Páginas sem scripts/lazy/abas usam quietude semântica de 350 ms em vez da janela
mínima anterior de 450 ms. Páginas dinâmicas mantêm a janela de 1,3 s, verificações
de crescimento/rolagem e extração de abas/disclosures. Redução de espera **não**
é registrada como preparação profunda dispensada. A coleta descreve a decisão.
Não se bloqueiam recursos para fabricar ganho no benchmark.

Novos indicadores distinguem:

- `preparacoes_com_espera_reduzida`: houve inspeção, com espera menor;
- `preparacoes_realmente_dispensadas`: somente dispensas efetivas por template;
- `paginas_sem_par`: conteúdo sem par que não recebeu comparação profunda;
- `quantidade_paginas_sem_inspecao_profunda`: total de limitações, que pode
  incluir páginas sem par e não equivale a preparações economizadas.

Assim, muitas omissões e zero preparações evitadas podem coexistir sem que as
duas métricas representem a mesma operação. Não corrigimos números apenas para
fazê-los coincidir.

### Ordem e proteção de memória

A nova fila prioriza página inicial, institucional, serviços, demais seções,
editorial e paginação. A cada oito retiradas, atende a entrada mais antiga,
evitando inanição das notícias enquanto chegam páginas prioritárias. Mantém a
trilha descoberta e não descarta páginas por relevância. Prioridade usa indícios
de caminho/rótulo; não certifica a natureza do conteúdo ainda não aberto.

O teto passou a **100.000 URLs/pares descobertos ou visitados**, como proteção
de memória, com parada/pendências explícitas. Documentos e recursos decorativos
não são contados como páginas HTML. Não há promessa de capacidade infinita;
acima desse teto a execução continua sendo parcial. Teste de 2.603 pares verifica
a lógica da fila e da comparação com navegador simulado; não mede memória ou
tempo de 2.603 páginas reais no Chromium.

### Checkpoints e retomada

Checkpoint possui versão, horário, SHA-256 de integridade e estado JSON, sem
pickle. Guarda configuração, fila/trilhas, visitados, páginas comparadas, dados
coletados, divergências brutas, referências, limitações, métricas acumuladas,
estado de equivalência/template e segmentos temporais. É gravado atomicamente
antes de iniciar o navegador e entre operações, além dos checkpoints periódicos
e finais. O par ainda em extração não é marcado como comparado.

No painel, use **Consultar checkpoints → Retomar**. A lista mostra os ambientes
e opções persistidas; confira se o acesso continua autorizado. Não há retomada
automática. O backend valida versão, hash, configuração, escopo e consistência
antes de iniciar o navegador. Checkpoint legado/incompatível gera explicação.

A retomada cria **outro ID de execução**, conserva o relatório anterior e copia
decisões locais de confirmação, classificação e exclusão. Os IDs anteriores
permanecem estáveis pela preservação da ordem dos registros já coletados.
Resultados novos são acrescentados e a fila restante é restaurada. Um par ativo
interrompido durante a extração volta à fila; um par que falhou de forma
controlada permanece como tentativa inconclusiva, sem repetição automática infinita.

`segmentos_coleta` identifica os diferentes períodos. O tempo acumulado mede
execução ativa, excluindo a pausa entre processos. Caches HTTP/documentais não
são restaurados: as novas consultas recebem novo horário. Capturas da execução
anterior permanecem naquele relatório; as capturas do novo relatório podem ser
feitas novamente em outro momento e não devem ser tratadas como simultâneas.

Limites: SHA-256 detecta corrupção, não autentica a origem de um arquivo local
malicioso. Use somente checkpoints da instalação autorizada. Uma falha pode
exigir repetir trabalho desde o último checkpoint seguro, sem duplicar os
resultados persistidos. Disco cheio pode impedir a preservação. A gravação
integral do estado ainda tem custo crescente em portais muito grandes.

Arquivos: novos `frontier.py` e `checkpoints.py`; `adaptive.py`, `smart.py`,
`core.py`, `paired.py`, `web/server.py`, template e JavaScript.

## Etapa 3 — classificação, agrupamento e documentos

- Comparação permanece bidirecional e local à seção. ÁUDIOS, download, valores
  institucionais, nomes diferentes, links e documentos continuam relevantes.
  Uma ocorrência em outra seção não apaga a diferença de organização.
- Avisos com contexto editorial identificável, incluindo comunicado eleitoral
  em bloco de aviso, podem ser separados quando o usuário declarar uma base
  desatualizada. O grupo preserva todos os textos e a justificativa. Links de
  notícias continuam classificados como publicações; controles/downloads não
  viram editoriais só por estarem próximos. Sinal automático de base antiga
  continua não substituindo a declaração explícita do usuário.
- Textos e controles normativos da mesma seção/escopo podem formar grupo com
  todos os membros, IDs e valores. Isso não comprova substituição nem causa
  comum. Contextos, classificações ou decisões manuais incompatíveis não são
  misturados. Documentos ausentes continuam agrupados por seção.
- Documentos relevantes são priorizados entre as referências conhecidas. O
  limite passou de 20 para 10.000 pares e até 20.000 requisições documentais,
  sempre seriais e com timeouts/limites de redirects. Itens excedentes ficam
  inconclusivos. A referência é registrada mesmo quando a checagem não ocorre.
- URL sem extensão marcada como download é tratada como documento, sem crawl
  HTML. Imagens decorativas com extensão conhecida não são PDFs só por estarem
  na rota Liferay `/documents/d/`. Destinos sem extensão e sem semântica HTML
  documental suficiente ainda podem exigir análise manual.
- Fluxo oficial usa somente HEAD e não lê corpo. HEAD bloqueado/405 é
  inconclusivo, sem GET. Cada URL/origem reutiliza a observação desta execução,
  com seu horário e nota de que não foi revalidada. Isso não comprova
  disponibilidade permanente. A API legada conserva revalidação por frescor
  e seu fallback opcional por compatibilidade; o painel não o habilita.
- Conferência externa e cliques continuam opcionais, restritos e sem login,
  formulários ou operações destrutivas. Não houve ampliação para crawling externo.
  HEAD não verifica redirects por JavaScript; o resolvedor DNS do sistema pode
  demorar além do orçamento cooperativo antes de devolver o controle.

Arquivos: `intelligence.py`, `sections.py`, `relevance.py`, `documents.py`,
`core.py`, `paired.py`. Não há regras por órgão ou ID de DIV.

## Etapa 4 — diagnóstico, relatório e revisão

- Bloqueios de segurança deixam de entrar como falhas do portal. São agregados
  por método/domínio, com contagem e URLs observadas, preservando a política.
  Podem indicar limitação de cobertura; não são ocultados para declarar sucesso.
- Diagnóstico separa acesso observado, automação e bloqueios. HTTP observado
  não prova defeito permanente; DNS/TLS/timeout também exigem interpretação.
- Extrator valida `document.body`; a sonda de template tolera sua ausência.
  Extração tem no máximo duas tentativas, com pausa de 200 ms entre elas.
  Falha isolada registra pendência e não fabrica ausência entre ambientes.
  Encerramento do navegador propaga para recuperação do checkpoint.
- Progresso distingue visitação da comparação, pares com falha, fila pendente,
  etapa, última atividade, tempo decorrido e conexão. Percentual se refere à
  fila descoberta, que pode crescer. Logs/cursor e download completo permanecem.
- **Formato de relatório 2:** o principal guarda resultados e resumo; dados
  técnicos extensos ficam em `detalhes_<id>.json`. O leitor hidrata esses dados
  quando necessário. Relatórios antigos continuam legíveis, sem migração
  destrutiva. A exportação completa é autocontida; principal e detalhes separados
  precisam ser mantidos juntos quando a pasta local for transferida.
- Frontend pede relatório leve e carrega detalhes técnicos pelo botão explícito.
  A leitura leve evita carregar o arquivo técnico; exportação/diagnóstico
  completo ainda materializam os detalhes e podem consumir bastante memória.
- Revisão mostra classificação, motivo, confirmação humana e filtro de
  pendentes/confirmadas. Pesquisa encontra IDs internos dos grupos e seus textos.
  Confirmar um grupo confirma seus membros. Classificação manual prevalece.
  Exportação oferece principal, completa ou somente relevantes, sem exportar
  ao mudar o seletor. Originais continuam imutáveis.

Arquivos: novo `compact.py`; `diagnostics.py`, `reports.py`, `storage.py`,
`paired.py`, servidor, JavaScript, template e CSS.

## Testes e medições

Suíte inicial: **140 testes aprovados em 84,440 s**. Resultado final:
**161 testes aprovados em 83,778 s**, sem falhas ou testes ignorados, incluindo
21 novos casos e a suíte anterior. Sintaxe JavaScript e verificação de diff
aprovadas. Houve correções durante o desenvolvimento: configuração inicial da
fixture Playwright, base URL da fixture de download, preservação da separação
anterior de links de notícias e proteção de rótulos editoriais repetidos em
seções estruturais. Nenhuma dessas falhas permaneceu na rodada final. Comandos:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests -v
node --check web/static/app.js
git diff --check
python -B scripts/benchmark_perf.py --baseline /tmp/ambidiff-intermat-baseline --pages 3 --repetitions 3
python -B scripts/benchmark_reports.py --baseline /tmp/ambidiff-intermat-baseline --references 500 --repetitions 3
```

O checkout de referência é `ea8abad`, separado da árvore de desenvolvimento.
Benchmark de navegação usa três repetições alternadas por versão/cenário, três
páginas por ambiente, com mesmas opções e inspeção dos itens/achados extraídos.
O de relatórios usa as mesmas observações sintéticas e confere sua integridade
após leitura. Nenhum mede o Windows ou o portal real do INTERMAT. Não executar
testes pesados em paralelo às medições.

| Etapa | Regressões de validação |
|---|---|
| 1 | Mais de uma hora simulada nos coletores; âncora observada versus fragmento incerto/funcional; tema escuro e foco no Chromium. |
| 2 | 2.603 pares, ciclos/duplicatas, prioridade com atendimento dos antigos, falha do navegador, interrupção durante extração, versão/hash/escopo inválidos, retomada em novo ID sem duplicar pares e revisões. |
| 3 | ÁUDIOS nos testes anteriores e novos, 2.232 referências com duas URLs, mais de 20 documentos, nenhum corpo lido, aviso eleitoral, institucional/download preservados e rótulo de notícia repetido no menu. |
| 4 | DOM nulo com recuperação limitada, categorias de diagnóstico, leitura v1/v2, decisões imutáveis, pesquisa por ID membro, confirmação do grupo e exportação somente de relevantes. |

Novos testes estão em `tests/test_intermat.py`. O teste anterior de bloqueio de
POST em `tests/test_next.py` agora exige o bloqueio na categoria de segurança e
sua ausência na lista de falhas, mantendo a comprovação de que o POST não chegou
ao servidor e de que a cobertura não foi declarada completa.

### Resultados de navegação

| Indicador (mediana) | Estável anterior | Estável atual | Dinâmico anterior | Dinâmico atual |
|---|---:|---:|---:|---:|
| Duração total | 5,030 s | 4,428 s | 12,454 s | 12,477 s |
| Preparação acumulada | 3,145 s | 2,534 s | 8,126 s | 8,122 s |
| Navegação acumulada | 0,232 s | 0,259 s | 0,265 s | 0,239 s |
| Pares descobertos/comparados | 3/3 | 3/3 | 3/3 | 3/3 |
| Preparações realizadas | 6 | 6 | 6 | 6 |
| Esperas reduzidas | 0 | 6 | 0 | 0 |
| Preparações profundas dispensadas | 0 | 0 | 0 | 0 |
| Releituras | 0 | 0 | 0 | 0 |
| Requisições ao servidor | 6 | 6 | 6 | 6 |
| Falhas / pares pendentes / omissões profundas | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |

A redução total foi **11,97% no estável**. No dinâmico, a duração aumentou
**0,18%**; não se conclui diferença significativa com três amostras. A preparação
estável caiu aproximadamente 19,4%, mantendo seis preparações e todos os itens.
Cobertura e achados extraídos foram equivalentes nas doze execuções.
Contagens reais de cartões e observações normalizadas estão no artefato
[`benchmark-portais-extensos.json`](benchmark-portais-extensos.json).

Não foi atingida a meta de 50% contra `ea8abad`. O ensaio mantém desligados
capturas, cliques, externos, base antiga e checkpoint em ambos os checkouts;
portanto não mede custo de grandes checkpoints, geração de evidências ou
varredura real de milhares de páginas. Falsos positivos não receberam auditoria
humana formal; não se atribui artificialmente zero a esse indicador.

### Resultados de exportação

Em 500 referências documentais e 500 observações estáticas sintéticas idênticas:

| Indicador | Anterior | Atual |
|---|---:|---:|
| JSON principal | 325.873 bytes | 1.533 bytes |
| HTML principal | 469.992 bytes | 5.584 bytes |
| CSV principal | 886 bytes | 886 bytes |
| JSON total, incluindo detalhes | 325.873 bytes | 326.138 bytes |
| Mediana da exportação | 0,0356 s | 0,0384 s |

O principal ficou **99,53% menor**, com as observações integralmente restauradas
e comparadas por hash após leitura. Isso é separação para consulta, **não**
redução total do armazenamento: o JSON total cresceu 265 bytes, e a exportação
não ficou mais rápida nesse ensaio. Dados e limites em
[`benchmark-relatorios-v2.json`](benchmark-relatorios-v2.json). O relatório real
de aproximadamente 40 MB do INTERMAT não foi medido.

## Validação manual no Windows e atualização

Com o aplicativo fechado e sem mudanças locais não revisadas:

```cmd
git status
git fetch origin
git switch perf/otimizacao-varredura
git pull --ff-only origin perf/otimizacao-varredura
instalar.bat
INICIAR_AMBIDIFF.bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Mantenha a instalação anterior separada. Abra `http://127.0.0.1:8765` e confira
conexão e campos URL vazios. Instalação requer Python, dependências e Chromium;
não contorne restrições da TI, autenticação ou certificados.

1. **INTERMAT autorizado:** registre configuração e commit, compare portarias,
   Presidente do Conselho, download, Google+, aviso eleitoral e Próximo/Voltar.
   O efeito real dos fragmentos depende do DOM/JavaScript observado.
2. **AGER:** confira raízes em caminhos distintos e queries funcionais.
3. **CGE:** confirme ÁUDIOS exclusivo na seção, nos dois sentidos, com e sem
   declaração de base antiga. Não se deve usar a contagem de DIVs como qualidade.
4. **POLITEC/Legislação:** confira referências documentais, links externos
   autorizados e resultados HEAD inconclusivos. Nenhum PDF deve ser inspecionado.
5. Em uma execução controlada longa, ultrapasse 45 minutos e uma hora; confira
   fila, contadores, logs após 200 eventos, desconexão/F5 e interrupção por um
   clique. Não considere silêncio do log como travamento.
6. Interrompa, feche e reabra o programa. Consulte checkpoints, confirme as URLs,
   retome e confira novo ID, pares anteriores preservados, fila restante e
   revisões. Tente também arquivo incompatível em cópia da instalação.
7. Confira filtros, pesquisa de ID membro, confirmação, classificação, exportação
   relevante/completa, JSON v2 e detalhes. Teste teclado, foco, seletores e janela
   estreita no Windows. Preserve juntos principal, detalhes e evidências.

Relatórios, logs, checkpoints e capturas podem conter dados internos. São locais,
ignorados pelo Git e não devem ser enviados a serviços externos. Não há merge,
deploy, GitHub Pages ou publicação nesta entrega.
