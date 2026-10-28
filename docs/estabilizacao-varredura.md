# Estabilização da varredura, progresso e interface

Base confirmada no GitHub antes das alterações:
`a46aad23c955c2bda40c928b693ee9d46f5c7b20`, branch
`perf/otimizacao-varredura`. A árvore estava limpa. Comparou-se também
`1ddc9d2a7bb0ca0ed090d6be8210881d6a7cc6d8`. Não foi usada a `main` como base,
nem restaurada integralmente uma versão antiga. Não havia AGENTS.md disponível.

## Comparação e atribuição das causas

| Item | Em `1ddc9d2` | Em `a46aad2` | Diagnóstico e correção |
|---|---|---|---|
| Chromium visível | `headless=True` | Oculto somente se `AMBIDIFF_HEADLESS=1` | Mudança confirmada que explica as janelas. Restaurado `headless=True`, inclusive no fallback, sem seletor ou dependência de variável |
| Recurso fechado | Registra checkpoint e propaga exceção | Conserva esse encerramento global | Limitação anterior, não causada comprovadamente pela fila. Agora recria recursos inválidos, limita tentativas e continua outros pares |
| Limpeza | Fechamentos sequenciais em `finally` | Mesma estrutura, com contextos de evidência separados | Uma exceção de limpeza podia impedir as etapas seguintes ou mascarar o erro original. Agora a liberação é independente, com diagnóstico |
| `ERR_ABORTED` | `_abrir` só recupera timeout; catálogo não reconhece esse código | Mesmo comportamento | Limitação preexistente. Tratamento local com observação do destino e até uma repetição segura; classificado como navegação interrompida |
| Certificado | Catálogo já reconhece TLS | Continua reconhecendo TLS | Não é regressão demonstrada da otimização. Mantida validação TLS, com orientação sobre endereço/domínio e ambiente/URL no aviso |
| Progresso | Avanço técnico e contadores coexistem | Finalização pode publicar 94–98%; API usa visitados na cobertura conhecida | Separados estados finais, comparados, pendentes e em processamento. Percentual deriva dos admitidos com estado final, sem contar coleta falha como comparação |
| Falha fatal sem contagem | Diagnóstico calcula a lista `falhas`; worker também usa campos separados | Mesmo caminho persiste | Reproduzível por injeção local: erro fatal podia ficar só em `erro_execucao`. Agora entra na lista com ID propagado e deduplicação |
| Interface | Exportações, seleção e detalhes existentes | Mesmos recursos, com muita informação simultânea | Resumo essencial, detalhes recolhíveis, seletor de formato + download e estados vazios menores |

A abertura visual é causa confirmada da mudança de apresentação. **Não comprova
por si só** a causa de cada `Target closed`, `ERR_ABORTED` ou falha real do Intermat.
Não foram encontrados arquivos locais de diagnóstico contendo Intermat; os dados
originais usados aqui são os trechos fornecidos na solicitação, não um rastreamento
completo de uma execução. Não se afirma que o usuário fechou uma janela, que houve
falha de memória ou que uma rotina específica encerrou o navegador no caso real.

O indicador próximo de 99% relatado também não foi reproduzido em um portal real.
Com todos os contadores íntegros, o caminho anterior já podia calcular 1/9 de forma
correta. Foram demonstrados os riscos do percentual técnico e do uso de visitados
como encerrados, e testou-se explicitamente um estado residual de 99% diante de
um comparado e oito pendentes. A API e o JavaScript novos mostram **11%** nesse
cenário, sem depender do valor residual.

## Navegador e recuperação

`ambidiff/browser.py` centraliza os recursos da execução, com **um navegador** e
contextos A/B independentes. O início normal é oculto. Em uma falha:

- Página fechada: cria outra página no contexto válido, conservando sua sessão.
- Contexto fechado: substitui o contexto afetado e reaplica as restrições.
- Navegador desconectado: cria outro Chromium oculto, com novos contextos isolados.
- Não compartilha cookies entre ambientes nem salva cookies/credenciais em checkpoint.
- Registra conexão do navegador, páginas fechadas, fechamento observado do contexto,
  ambiente, etapa e tentativa. Estado desconhecido não é apresentado como causa comprovada.

Há no máximo **duas tentativas de recurso por par**, preservadas na retomada, e
**três recuperações de recursos por segmento**. Um par que esgota suas tentativas
fica falho; os demais continuam. Esgotar a recuperação global conserva a fila e
encerra com resultado parcial, permitindo uma retomada explícita. A retomada não
reabre pares já terminais nem reinicia o teto. Uma nova sessão após perda total
do navegador pode voltar a exigir autenticação no ambiente autorizado; não há
contorno de login, CAPTCHA ou certificado.

Não abre outro Chromium ao retomar um checkpoint sem fila e sem novas capturas,
nem recria recursos ao esgotar o último par quando não restam tarefas/evidências.
A limpeza só ocorre ao substituir um recurso inválido ou finalizar/interromper
a execução. Cada recurso é liberado separadamente. Erros de limpeza não substituem
a exceção original. Capturas continuam locais e associadas ao ambiente correto;
falhas de evidência entram no diagnóstico e não são DIVs de conteúdo.

`ambidiff/navigation.py` recebe abortos de navegação de forma limitada. Um DOM só
pode ser aproveitado após observar mudança real do endereço dentro do escopo e
carregamento do documento; um DOM anterior parado na tela não comprova sucesso.
A comparação normal de destinos permanece, inclusive para login/redirecionamentos.
Se não existir evidência aproveitável, repete no máximo uma vez o endereço original
autorizado. A falha persistente afeta o par, com diagnóstico, sem cancelar pares
independentes. Nenhuma rota alternativa de Intermat é tentada automaticamente.

## Estados, contadores e persistência

`fila_execucao` é um campo adicional; os formatos de relatório e checkpoint
permanecem compatíveis. O estado da fila admite:

- `concluida`: todos os pares admitidos receberam estado final.
- `concluida_com_falhas`: todos encerrados, com erros técnicos/de acesso registrados.
- `parcial`: pares sem estado final ou uma falha fatal que encerrou o processamento.
- `interrompida`: pedido cooperativo do usuário.

A situação de cobertura (`situacao_analise`, `completo`, `cobertura`) continua
separada. Fila concluída não significa portal inteiro examinado, equivalência
completa, documentos binariamente iguais ou todos os pares comparados com sucesso.
O relatório HTML/PDF, a interface e o histórico apresentam essa distinção.
Registros anteriores sem `fila_execucao` conservam a interpretação histórica.

`execution.contadores` separa admitidos, concluídos, comparados, pendentes,
em processamento, não analisados e falhos. Estados terminais incluem também
redirecionamento, não HTML, falta de contraparte e inconclusivo. Só o estado
`comparado` incrementa comparações bem-sucedidas. A barra usa a proporção de
terminais/admitidos; **100% de fila encerrada pode conter falhas**. O número de
comparados fica ao lado. Um par em processamento não vira concluído antes da
hora. A ETA permanece uma estimativa identificada, sem prazo máximo global.

Um incidente de automação e um par falho são medidas diferentes: uma falha que
foi recuperada pode deixar todos os pares comparados e ainda constar no diagnóstico.
Uma falha fatal durante um par devolvido à fila não precisa incrementar o número
de pares terminais falhos. Isso não elimina a contagem da falha de automação.
IDs por incidente evitam contar novamente a mesma exceção ao propagá-la ao worker.
Tentativas distintas continuam rastreáveis.

Falhas inesperadas forçam checkpoint antes da limpeza. Uma transação leve por
par conserva os comprimentos das listas e referências anteriores das páginas;
se a comparação corrente não termina, preserva os resultados provisórios em
um evento técnico `TENTATIVA_DE_PAR_INCOMPLETA`, separa-os da lista de DIVs finais
e devolve o par à fila. Resultados completos anteriores, DIVs, editoriais,
metadados, falhas e evidências permanecem. A retomada não duplica as DIVs daquele
par incompleto. Assinatura, serialização em cache, gravação atômica e a preservação
do bruto/checkpoint original continuam. O worker recupera uma projeção para o
relatório parcial sem reescrever o checkpoint que documentou a falha.

## Fila, teto e precisão preservados

O teto interno continua em **1.000 admissões HTML**, sem campo de configuração.
Arquivos reconhecidos não consomem vagas; respostas não HTML, tipos mistos,
falhas e referências inconclusivas continuam distinguidos. Ao atingir o teto,
para a admissão e drena a fila existente. Novas execuções não ultrapassam mil;
filas legadas que já admitiram mais de mil continuam preservadas, sem abrir vagas
novas, conforme a política anterior de compatibilidade.

Mantidos: uma comparação por vez; prioridade menus/navegação, serviços, notícias,
legislação, institucional e histórico com rodízio; deduplicação conservadora;
parâmetros de conteúdo como `c`/`e`; componentes estáticos comprovados; janelas
adaptativas e releituras apenas com indícios; representantes sem concluir outras
páginas; interrupção cooperativa; agrupamento e rastreabilidade das ocorrências.
Não há pausa automática de vinte minutos, nem parada ao atingir noventa minutos.

Menus ocultos semanticamente identificáveis recebem prioridade sobre acordeões
secundários. Acrescentados controles de navegação `aria-haspopup`, mantendo
rolagem, abas, limites e restrições. Uma falha de controle não impede abrir o
seguinte. Rótulos de acessibilidade também são verificados contra ações proibidas;
abas com destino de navegação real não são clicadas como simples painel. Falhas
de interação são preservadas como inspeção inconclusiva. A regressão ÁUDIOS
verifica sua detecção em menu inicialmente oculto, sem depender de DIV-0004.

## Interface e HOMOL

O painel inicial mostra estado, admitidos, comparados, pendentes, falhos,
ocorrências **preliminares**, encerrados, tempo e etapa atual. Log/cursor, última
atividade e detalhes continuam em um expansor. Há um aviso estruturado para falha,
com motivo, ambiente, URL e quantidades, em vez de vários blocos repetidos.

Na exportação, escolhem-se escopo e formato e usa-se **Baixar relatório**.
Permanecem CSV/HTML/PDF/JSON, sugestões CSV para seleção e HTML para relatório
completo, Save As/fallback, proteção de CSV, evidências portáteis, seleção local,
confirmação independente, exclusões e agrupamentos. JSON do relatório respeita
seu escopo; JSON da execução e TXT ficam em **Diagnósticos técnicos**, com nomes
explicativos. Sem DIVs, os filtros desaparecem, a exportação completa continua
habilitada e a mensagem limita a conclusão aos pares efetivamente comparados.
Painéis vazios ficam ocultos e detalhes técnicos são recolhidos.

Novas execuções oferecem **DES (padrão), LAB e HOMOL** no Ambiente B. PRD continua
no Ambiente A. O backend recusa PRD em novas seleções B, mas lê relatórios e
checkpoints antigos sem alterar os nomes anteriores. HOMOL percorre API,
comparação, diagnóstico, histórico, relatórios e checkpoint usando a URL informada
pelo usuário; nenhuma URL de homologação é inventada. Rótulos fixos PRD/DES em
referências auxiliares foram substituídos pelos nomes efetivos dos ambientes.

## Validação e medições

**Corrigido e coberto por testes automatizados:** suíte final com **244 testes
aprovados em 115,518 s**, sem falhas ou skips. São 27 novas regressões em
`tests/test_update19.py`, além da adaptação dos testes existentes aos contratos
novos. Incluem navegador oculto, isolamento, página/contexto/navegador fechado,
limpeza com erro, tentativas limitadas, ERR_ABORTED, TLS, 1/9 na API e interface,
fatal sem duplicação, resultados provisórios, retomada sem novo navegador,
ÁUDIOS oculto, HOMOL, legado PRD em B e exportações completas.

**Executado de fato em ambiente local:** Chromium real com fechamento deliberado
de página e cookies isolados; portais HTTP loopback; geração local de capturas,
PDF/HTML/CSV/JSON; interação por teclado, cancelamento e fallback de salvamento.
Isso não é validação dos portais institucionais ou do Windows.

**Pendente:** Intermat real, Windows e carga longa representativa. Não houve
acesso a PRD/DES reais, validação em produção ou comprovação da meta de 1h30.

O baseline sem variável de ambiente teve 18 erros de inicialização por falta de
interface gráfica; com `AMBIDIFF_HEADLESS=1`, os 217 testes anteriores passaram
em 99,685 s. Durante a implementação, corrigiu-se uma referência local de
navegador não inicializada em retomada sem fila. Dois testes de interface foram
adaptados para abrir os expansores e a tela correspondente antes de consultar
conteúdo recolhido. Nenhuma asserção funcional foi removida para esconder falhas.
Python, `node --check` e `git diff --check` foram verificados.

Medições em subprocessos novos, três repetições alternadas por versão, sem suíte
simultânea; referência `a46aad2`, explicitamente oculta no benchmark:

| Cenário | Mediana anterior | Mediana atual | Variação |
|---|---:|---:|---|
| Três pares estáveis | 3.210881 s | 3.206404 s | Redução de 0.14% |
| Três pares dinâmicos/lazy/abas | 10.121685 s | 10.139810 s | Redução de -0.18% |

Cobertura e achados coincidiram integralmente nos cenários sem falha. As variações
são pequenas; não se afirma ganho novo nem se extrapola para mil pares. As
melhorias anteriores de preparação e fila foram mantidas.

No ensaio com fechamento real de página, as três repetições da referência
pararam com um par comparado, dois pendentes, zero capturas e contagem zero de
falhas de automação apesar da exceção fatal. Nas três repetições atuais, os três
pares foram comparados, não restaram pendências, o incidente foi contado uma vez
e foram gerados 18 PNGs. As coberturas são diferentes; o tempo total dessas
execuções não é uma comparação válida de velocidade.

Na versão atual desse ensaio, medianas por fase (algumas aninhadas):

- `navegacao`: 0.283553 s.
- `preparacao`: 1.188408 s.
- `descoberta`: 0.000130 s.
- `comparacao`: 0.009851 s.
- `capturas`: 2.417269 s.
- `recuperacao_falhas`: 0.073041 s.
- `checkpoint`: 0.005413 s.

Artefatos exclusivamente sintéticos: [navegação](benchmark-estabilidade-navegacao.json)
e [recuperação/evidências](benchmark-estabilidade-recuperacao.json). Para repetir:

```cmd
set AMBIDIFF_HEADLESS=1
.venv\Scripts\python.exe -B scripts\benchmark_dynamic.py --baseline C:\referencia-a46aad2 --scenario browser --pages 3 --repetitions 3
.venv\Scripts\python.exe -B scripts\benchmark_stability.py --baseline C:\referencia-a46aad2 --repetitions 3
set AMBIDIFF_HEADLESS=
```

A variável é necessária apenas para manter a referência antiga oculta; a versão
atual usa `headless=True` incondicionalmente. Os arquivos de execução, checkpoints,
relatórios e capturas ficam fora do commit; só os agregados sintéticos são versionados.


## Arquivos e funções

| Arquivo | Alteração principal |
|---|---|
| `ambidiff/browser.py` | `Navegador`, ciclo de vida, isolamento, recuperação e limpeza |
| `ambidiff/navigation.py` | `abrir`, recuperação limitada de abortos |
| `ambidiff/execution.py` | `contadores/resumir`, semântica de progresso e fila |
| `ambidiff/paired.py` | Integração, transação por par, checkpoints fatais, estados e evidências |
| `ambidiff/core.py` | `coletar_aba`, prioridade e segurança de menus ocultos |
| `ambidiff/diagnostics.py` | `classificar_erro`, IDs/deduplicação, erro fatal e orientação |
| `ambidiff/checkpoints.py` | `recuperar`, contadores/estado recuperados |
| `ambidiff/reports.py`, `storage.py` | Estado de fila nas saídas e exportações selecionadas |
| `web/server.py` | Worker/diagnóstico, progresso público e validação de HOMOL |
| `web/static/app.js`, `style.css`, `templates/index.html` | Resumos, expansão, exportações compactas e ambientes |
| `tests/test_update19.py` | Regressões e integração local desta atualização |
| Testes existentes alterados | Novos contratos de recuperação/configuração e navegação pelas áreas recolhíveis |
| `README.md` e este documento | Comportamento, comparação das versões e limites |

## Segurança e validação pendente

GET/HEAD/OPTIONS e o bloqueio de ações de escrita continuam ativos; cliques e
conferência externa permanecem opcionais e desligados. Não foram enviados
formulários ou dados internos, desativado TLS, alterados certificados ou acessados
recursos corporativos. Diagnósticos de novos incidentes reduzem URLs para não
registrar queries/credenciais indiscriminadamente; os arquivos locais originais
conservam a rastreabilidade autorizada. Não foram adicionadas dependências ou
serviços de conversão externos.

Não houve acesso aos portais reais do Intermat. Os erros relatados serviram para
simulações e testes locais, sem supor acesso seguro ao DES. Ainda dependem de
validação autorizada: comportamento no Windows, estabilidade numa varredura longa
real, certificado/endereço efetivamente correto, componentes específicos dos
portais e a meta de mil pares em cerca de 1h30. Navegações e interações têm limites
individuais; código síncrono de renderização bloqueado totalmente pelo navegador
continua sendo limitação da parada cooperativa. Não se promete término imediato
nem validação de conteúdo que só apareça em timers futuros arbitrários.

## Testar no Windows

Instale com `instalar.bat`, ou prepare as dependências locais:

```cmd
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -B -m unittest discover -s tests -v
INICIAR_AMBIDIFF.bat
```

Não é necessário configurar `AMBIDIFF_HEADLESS`. Em portais de teste/autorizados,
confira que nenhuma janela de automação abre; HOMOL usa a URL digitada; uma falha
apresenta motivo, ambiente e pendências; Interromper funciona com um clique;
retomar preserva contagem, resultados e seleção. Confirme separadamente o caso
ÁUDIOS, menus ocultos e cada exportação. Não habilite opções de cliques/externos
sem autorização para esses acessos.
