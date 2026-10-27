# Nova otimização: fila dinâmica e até 1.000 pares HTML

Referência examinada: `1ddc9d2a7bb0ca0ed090d6be8210881d6a7cc6d8`, branch
`perf/otimizacao-varredura`, confirmada por fetch antes das alterações. A árvore
estava limpa. Não foi usado ZIP antigo ou `main`; não havia AGENTS.md no ambiente.
Os ensaios usam fixtures fabricadas e servidores loopback. Não foram acessados
portais corporativos nem usados logs internos. O histórico de aproximadamente
2h11 no Intermat não é uma medição desta atualização.

## Diagnóstico e decisões

A versão anterior já tinha fila única, deduplicação, contextos isolados, tentativas
controladas, segurança de métodos, sondagem semântica, coleta de abas/rolagem,
seleção de DIVs, exportações e checkpoint atômico. Esses mecanismos foram
aproveitados. As diferenças que exigiram alterações foram:

- A estratégia progressiva encerrava por 20 minutos ou por amostragem editorial.
- A admissão usava apenas o teto preventivo de memória, de 100.000 referências.
- Páginas exclusivas eram registradas sem visita, nos dois sentidos.
- A contagem de páginas armazenadas não distinguia todos os desfechos individuais.
- Cada ambiente iniciava sua janela de estabilidade somente ao entrar na coleta,
  mesmo que o segundo documento já estivesse carregado durante a primeira coleta.
- As evidências abriam novamente a mesma página para cada DIV e usavam um único
  contexto de captura para ambos os ambientes.

## Comportamento implementado

### Admissão e término

`strategy.LIMITE_PARES_HTML = 1000` define o padrão, sem controle visual.
Referências candidatas e pares admitidos usam a fila existente, em instâncias
separadas. A reposição admite até oito pendências de cada vez; isso permite que
novas referências prioritárias concorram antes de preencher o teto inteiro.
Ao alcançar 1.000 admissões HTML, não entram novos pares. Todos os admitidos
continuam automaticamente até um desfecho ou interrupção/falha que exija retomada.
Candidatos não admitidos permanecem rastreáveis no checkpoint; sua existência
não cria autorização para ultrapassar o teto ao retomar.

Documentos, imagens e auxiliares reconhecidos são tratados como referências,
fora da fila HTML. URLs de tipo ainda desconhecido reservam uma vaga de forma
conservadora. Se ambos os destinos forem identificados como não HTML, a vaga é
liberada. Um destino HTML diante de um PDF permanece inconclusivo e reserva vaga.
Uma falha no outro ambiente não é escondida pela presença de um documento.
Os corpos documentais não são baixados pelo verificador HEAD. Uma navegação a
uma URL sem tipo conhecido ainda pode receber um recurso não HTML pelo navegador;
a classificação posterior não representa comparação do conteúdo desse arquivo.

Cada unidade tem estado terminal: comparado, falha, sem contraparte,
redirecionamento, fora do escopo, não HTML ou inconclusivo. Os contadores distinguem
admissões HTML, referências candidatas, descobertos, visitados, comparados,
pendentes, falhos e inconclusivos. Apenas uma comparação concluída incrementa
`pares_comparados`. Falhas individuais não encerram a fila dinâmica após quinze
erros consecutivos; cada par falho recebe diagnóstico, e os demais continuam.
A perda do navegador mantém a recuperação existente com duas tentativas fatais,
sem repetição infinita do mesmo par.

Chegar ao teto não significa varrer todo o portal. O relatório informa o teto e
as admissões em texto discreto, conserva os detalhes de cobertura e apresenta
resultado parcial quando a cobertura permanece limitada. Referências além do
teto continuam tendo seus rótulos/destinos comparados na página de origem; seus
corpos HTML não são percorridos. O limite preventivo separado de 100.000
referências candidatas protege a memória e não promete descoberta ilimitada.

### Prioridades, amostras e URLs

Ordem de prioridade: menus/navegação, serviços, notícias, legislação,
institucional e histórico. A classificação usa rótulo, rota e contexto observado,
sem inferir identidade de páginas. A cada oito saídas há rodízio entre categorias
presentes; a ordem não exige esgotar uma classe antes de trabalhar nas demais.
Os primeiros representantes de um grupo editorial são identificados, mas
nenhuma outra página é marcada como analisada por causa deles. As demais
admitidas continuam na mesma execução.

A deduplicação usa as regras conservadoras de URL já existentes e URLs observadas
em cada ambiente. Não usa aparência, título ou rota parecida. Parâmetros `c` e
`e` continuam distintos. Opções com mesmo destino ainda são comparadas por
rótulo/contexto. Uma referência de retorno exclusiva não abre novamente uma URL
exata já coberta no mesmo ambiente. Diferenças de destino encerram somente aquele
ramo, mantendo a divergência na origem.

Páginas exclusivas são inspecionadas somente onde foram encontradas, com
rastreamento de seus links internos seguros. Não se fabrica uma URL no outro
ambiente nem se compara com uma página vazia. Uma unidade exclusiva consome uma
admissão HTML e fica sem contraparte/inconclusiva. O conteúdo não é apresentado
como comparado. Essa inspeção pode aumentar o trabalho legítimo em relação à
versão que apenas registrava a omissão.

### Gerenciamento dinâmico, interface e navegação

A nova estratégia interna `dinamica` é padrão, sem prazo global e sem parada por
cota editorial. A meta de 1h30 para até 1.000 pares orienta a otimização; não é
limite de execução nem garantia universal. Não há aviso especial após 1h30.
O relógio e o progresso continuam normais. Os controles de estratégia, orçamento
e ativação de equivalência estática foram removidos da interface. O
reconhecimento estático fica ativo por padrão. Cliques e destinos externos
continuam opcionais, desmarcados, na gaveta avançada.

As estratégias anteriores permanecem disponíveis internamente para testar
compatibilidade e permitir comparar o mesmo escopo em benchmarks. Nenhum novo
modo rápido/padrão/completo foi adicionado à interface.

A execução segue um par por vez, com Chromium visível por padrão e contextos
independentes por ambiente. `AMBIDIFF_HEADLESS=1` é uma opção interna explícita
para testes em máquinas sem interface, não um controle novo na tela. Não foi
adicionado paralelismo entre pares ou compartilhamento de cookies/coletas.

Após navegar o par, ambas as páginas começam sua própria observação semântica.
A preparação da segunda aproveita o tempo já observado enquanto a primeira era
inspecionada. As janelas mínimas de 350 ms (estática) e 1.300 ms (scripts/lazy/abas)
e a quietude de 350 ms permanecem. A rolagem, coleta de abas e abertura segura de
componentes ocultos continuam. Indicadores de carregamento, mutações e imagens
pendentes impedem declarar estabilidade prematura; a preparação parcial mantém
seus diagnósticos e limites.

Não se repete a coleta por uma diferença persistente apenas. Uma confirmação
curta de 200 ms verifica também ausências isoladas; se o DOM mudar, a releitura
existente é executada, sem substituir a primeira coleta por uma menos completa.
Isso corrige a regressão encontrada durante os testes desta otimização.

### Evidências e persistência

A análise continua ocorrendo antes das capturas. Cada ambiente agora possui
contexto de evidência próprio. Uma captura pode ser reutilizada apenas para o
mesmo ambiente, URL, seletor e área de referência, no mesmo documento observado
estável e sem scripts/lazy/abas. Documento alterado ou dinâmico conserva o
carregamento/captura individual. Destaques anteriores são restaurados antes de
outro elemento ser marcado. Não se pressupõe que duas regiões visuais sejam
iguais. A ausência de seletor continua identificada como captura de área, sem
comprovar ausência do elemento.

O teste de três DIVs na mesma área preserva seis referências de evidência usando
duas imagens reais e duas navegações, com quatro reutilizações. Os contadores
separam capturas realmente geradas de referências e reutilizações. Os limites
anteriores de quarenta DIVs com captura e quatro minutos da etapa de evidências
permanecem; não são limites globais de varredura. O relatório informa ausência
de evidência quando não existe captura disponível. Capturas não certificam
igualdade visual pixel a pixel.

Checkpoints conservam fila admitida, candidatas, categorias/rodízio, total
acumulado, estados individuais, páginas exclusivas, resultados, variações
editoriais, diagnósticos e segmentos da execução. Evidências já geradas também
são associadas à projeção recuperada e à retomada. O bruto não é sobrescrito por
uma lista vazia. Ao drenar a fila no teto ou com referências não admitidas, o
worker conserva o checkpoint para auditoria, sem oferecer uma retomada que
ultrapasse o limite. O cache de serialização, o agendamento adaptativo de 30–120 s,
SHA-256, flush/fsync e substituição atômica continuam.

Retomar não reinicia a contagem nem repete pares terminais. A API migra retomadas
para a política dinâmica, preservando ambiente/opções e criando outro ID com
`retomada_de`. Checkpoints legados sem política são aceitos. **Exceção de
compatibilidade:** se o checkpoint legado já admitiu mais de 1.000 pares, essas
admissões são honradas sem abrir vagas adicionais; descartar a fila antiga
violaria a preservação dos resultados/trabalhos aceitos. Novas execuções usam
exatamente 1.000. Há regressão com 1.002 admissões históricas.

## Instrumentação e medições

Tempos de navegação, preparação, espera de carregamento, extração, comparação,
links/descoberta, releituras, evidências, checkpoint e recuperação estão disponíveis
nas métricas. A espera é parte da preparação; releituras incluem preparação e
extração; checkpoint inclui construção, assinatura e I/O. Não somar fases
aninhadas. Tentativas, falhas e ritmo de pares por minuto também são registrados.

Medições finais em subprocessos novos, sequenciais, alternando versões, três
repetições por cenário; sem execução simultânea da suíte. Referência: `1ddc9d2`.
Chromium headless foi usado explicitamente apenas nos testes.

| Cenário | Mediana anterior | Mediana nova | Resultado |
|---|---:|---:|---|
| Chromium: três pares estáveis | 4.466312 s | 3.229475 s | Redução de 27.69% |
| Chromium: três pares dinâmicos/lazy/abas | 12.531998 s | 10.264897 s | Redução de 18.09% |
| Fila simulada: mil pares, mesmo escopo e checkpoint real | 0.302460 s | 0.372969 s | Acréscimo de 0.070509 s (23.31%) |

Nos cenários Chromium, coincidiram integralmente os itens/contextos coletados,
as páginas, divergências, falhas, pendências e omissões. A comparação foi feita
antes de compactar as listas em quantidade/SHA-256 no artefato. Não houve
redução de cobertura para produzir esses ganhos. O principal ganho observado
está na preparação; navegação, extração e demais fases continuam instrumentadas.

Preparação estavel: 2.540060 → 1.177720 s (medianas).
Preparação dinamico: 8.149657 → 5.646840 s (medianas).

A fila simulada expõe um custo adicional de CPU para classificação, prioridades
e estados auditáveis. Não é um ganho nessa carga sem navegação. A revisão
removeu recontagens lineares dos estados em cada atualização de progresso e
classificações de URL repetidas. O custo restante foi mantido para preservar
admissão correta, rastreabilidade e contadores, e está explícito na medição.
As duas versões compararam mil pares, preservaram ÁUDIOS, terminaram sem
pendências/falhas e produziram checkpoints lidos e validados. O baseline usa
`profunda/0` neste microteste para garantir a mesma cobertura da política nova.

Checkpoint (anterior): mediana de 0.042209 s, inclusive construção/assinatura/I/O.
Checkpoint (otimizada): mediana de 0.046834 s, inclusive construção/assinatura/I/O.

Artefatos sintéticos: [navegação](benchmark-fila-dinamica-navegacao.json) e
[fila/checkpoint](benchmark-fila-dinamica-fila.json). As capturas não foram
incluídas no benchmark de navegação: a regressão específica mediu redução de
seis para duas navegações no caso de três DIVs na mesma área estática, sem
remover nenhuma das seis referências de evidência. Não é uma projeção de tempo
de captura para todo portal. Não se extrapolam esses tempos para a meta de
mil pares em 1h30, que depende de testes reais autorizados.

Não foram alteradas as frequências de logs/polling: não há medição mostrando que
esse ajuste traria benefício suficiente para justificar alterar a percepção de
progresso. IDs sequenciais, cursor, detecção de lacunas e confirmação de uma
única solicitação de interrupção permanecem.

## Testes e revisão

Baseline: **198 testes**, sem falhas ou skips, **102,931 s**. Houve testes
intermediários, não uma alteração única sem validação:

- Primeiro ensaio: detectou duplicação de URLs por retorno exclusivo/ambíguo;
  corrigida com deduplicação por ambiente.
- Expectativas de mais de mil páginas e controles removidos foram atualizadas
  para distinguir API legada explícita do novo comportamento da interface.
- Primeira suíte ampla: uma falha de releitura tardia e um erro de teste procurando
  controle removido. A falha funcional foi corrigida, não suprimida; os testes de
  carregamento passaram novamente (30 testes).
- Primeiros 13 novos testes passaram; com recuperação/tipos adicionais, a suíte
  passou com **216 testes em 102,169 s**. A revisão das contagens foi otimizada
  posteriormente para não varrer todos os estados a cada atualização de progresso.
- Suíte final: **217 testes em 100,390 s**, todos aprovados, sem skips.
  Inclui regressão do worker que conserva o checkpoint quando a fila é drenada
  no teto ou existem referências não admitidas. Sintaxe Python, `node --check`
  e `git diff --check` também passaram.

As dezenove regressões em `tests/test_update18.py`, combinadas às existentes,
cobrem teto exato, drenagem, menos de mil, ciclos, múltiplos menus, prioridades,
notícias numerosas, exclusivos nos dois sentidos, falhas isoladas, arquivos/MIME,
querys, interrupção aos 995 pares e retomada até mil, orçamento ignorado pela
política dinâmica, compatibilidade legada, evidências, corrupção e segurança de
escopo. A suíte existente verifica carregamento tardio/lazy/abas, estados ocultos,
ÁUDIOS da CGE, ícones, dados editoriais sem perda estrutural, requests bloqueados,
formulários, exportações, seleção persistente e recuperação de falhas.

Revisão: métodos de escrita e ações destrutivas continuam bloqueados. Não houve
envio de formulários, credenciais, relatórios internos ou dados sensíveis. Não
foram adicionados serviços externos nem dependências. CSV protegido, PDF local,
HTML portátil, JSON/TXT, revisão e exclusões continuam cobertos pelos testes.
A meta de desempenho e compatibilidade com Windows real dependem de validação
posterior autorizada; os testes foram executados em Linux, com Chromium local.

## Arquivos/funções principais

| Arquivo | Responsabilidade alterada |
|---|---|
| `ambidiff/strategy.py` | Constante de admissão; `Escopo`, política dinâmica e compatibilidade |
| `ambidiff/frontier.py` | `categoria`, `Fila.append/popleft`, prioridades/rodízio |
| `ambidiff/paired.py` | `executar_pareado`, admissão, terminalização, exclusivos, retomada, métricas; `_extrair_page`; `_salvar_evidencias` |
| `ambidiff/adaptive.py` | `JS_SONDA`, `preparar`, `decidir_releitura`, observação/espera |
| `ambidiff/checkpoints.py` | `validar/recuperar`, estado novo e compatibilidade |
| `ambidiff/smart.py` | `Metricas.resultado`, semântica dos tempos aninhados |
| `ambidiff/diagnostics.py` | Estados individuais no diagnóstico |
| `ambidiff/reports.py` | Teto discreto e detalhes de cobertura recolhíveis |
| `web/server.py` | Padrões de início e migração das retomadas |
| `web/static/app.js`, `web/templates/index.html` | Formulário simplificado, cobertura, retomada única |
| `tests/test_update18.py` | Novas regressões locais |
| `tests/test_intermat.py`, `test_smart.py`, `test_update17.py` | Expectativas de padrões novos e caminhos legados explícitos |
| `scripts/benchmark_dynamic.py` | Repetição antes/depois em Chromium e fila simulada |
| `README.md`, este documento e JSONs de benchmark | Uso atual, decisões, medições e limitações |

## Reproduzir no Windows

Na pasta do projeto, instale usando `instalar.bat`, ou execute:

```cmd
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
set AMBIDIFF_HEADLESS=1
.venv\Scripts\python.exe -B -m unittest discover -s tests -v
set AMBIDIFF_HEADLESS=
INICIAR_AMBIDIFF.bat
```

No uso normal, deixe `AMBIDIFF_HEADLESS` ausente. Em um portal local/autorizado,
confira os navegadores visíveis, a fila, as categorias e os contadores; interrompa
uma vez e retome, verificando que o acumulado não volta a zero. Confirme ÁUDIOS
somente onde o cenário for real e autorizado. Verifique uma exportação com
imagens, a seleção persistente e arquivos antigos. Não habilite cliques/destinos
externos sem autorização para esses acessos.

Para repetir medições, mantenha um checkout da referência e execute:

```cmd
set AMBIDIFF_HEADLESS=1
.venv\Scripts\python.exe -B scripts\benchmark_dynamic.py --baseline C:\referencia-AmbiDiff --scenario browser --pages 3 --repetitions 3
.venv\Scripts\python.exe -B scripts\benchmark_dynamic.py --baseline C:\referencia-AmbiDiff --scenario queue --repetitions 3
set AMBIDIFF_HEADLESS=
```

## Limitações restantes

Nenhuma janela finita certifica timers futuros arbitrários. Conteúdo carregado
após a janela, autenticação, CAPTCHA e regiões não identificadas continuam
limitando a cobertura; não há tentativa de contorná-los. Navegação tem timeout
de 30 s por tentativa, preparação preserva o limite de 7 s + tolerância de 2 s,
e capturas/interações mantêm limites próprios. `page.evaluate()` síncrono não
recebe timeout do Playwright pelo `set_default_timeout`; uma renderização que
bloqueie completamente o processo do navegador continua sendo limitação da
interrupção cooperativa. Não se promete parada instantânea de toda chamada.

Um serviço ainda não descoberto só pode disputar admissão quando sua referência
aparecer. Nenhuma prioridade garante encontrar links escondidos em páginas além
do teto. As contagens não devem ser confundidas com cobertura integral,
funcionamento completo ou comparação binária de documentos. Não foi comprovada
a meta de 1h30 em portais reais ou hardware Windows.
