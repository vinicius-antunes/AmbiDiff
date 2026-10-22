# Próxima atualização — comparação rastreável e execução confiável

Implementação na branch `perf/otimizacao-varredura`, sobre o commit
`208ed2b9a1fa0265b9ec1b7b270bf9d790b5718d`. Não incorpora as branches de
USEIA/CGE nem altera `main`. Exemplos e medições usam somente HTML sintético,
domínios de teste e servidores loopback. Não houve acesso aos portais reais.

## A. Diagnóstico inicial

O projeto já tinha comparação pareada, modo inteligente opcional, preparação
adaptativa, releitura seletiva, classificação editorial explícita, evidências,
revisão manual, checkpoints e exportações locais. A suíte inicial passou:
112 testes em 57,008 s. Essas funcionalidades foram estendidas, sem reescrita.

Problemas encontrados:

- O servidor retinha 200 mensagens e o frontend acompanhava o tamanho da lista:
  ao atingir o limite, novas mensagens deixavam de aparecer.
- O polling não distinguia adequadamente conexão temporariamente indisponível
  de término da execução. Atualizações antigas podiam competir com uma nova.
- A equivalência da raiz com uma implantação em subpasta era inconsistente.
- Associações globais podiam ocultar uma opção ausente na seção correspondente;
  marcação HTML diferente também podia prejudicar o reconhecimento funcional.
- Documentos ausentes produziam cartões separados e a auditoria externa podia
  ler páginas externas. O fluxo oficial agora confere somente referências e HEAD.
- Mutações cosméticas podiam invalidar a estabilidade; testes de clique eram
  restritos a links e não distinguiam todos os resultados de popup/HTTP.

PRD continua sendo apenas um dos lados. Nenhuma observação determina
automaticamente qual ambiente está correto.

## B. Arquivos e responsabilidades

| Arquivos | Alteração |
|---|---|
| `ambidiff/live.py` (novo), `web/server.py` | IDs/cursor de logs, arquivo completo local, status/atividade/fila, ETA recente, interrupção idempotente. |
| `web/static/app.js`, `web/templates/index.html` | Reconexão, relógio independente, proteção contra respostas antigas, URLs vazias, ambientes neutros, detalhes dos grupos e resultados técnicos. |
| `ambidiff/sections.py` (novo) | Comparação por seção, possíveis realocações, valores informativos pareados e agrupamento documental preservando membros. |
| `ambidiff/destinations.py` (novo) | HEAD com validação de destino, IP fixado, limites, cache por execução e classificação observada. |
| `ambidiff/core.py`, `ambidiff/smart.py` | Extração semântica, disclosures/submenus seguros, associação funcional tolerante a HTML e preservação de queries significativas. |
| `ambidiff/paired.py` | Integração, equivalência contextual de raízes, eventos de andamento, política de navegação, checagens de referências e checkpoints. |
| `ambidiff/documents.py` | HEAD sem fallback GET no fluxo oficial; sem proxy ambiental; ações inseguras bloqueadas. |
| `ambidiff/functional.py` | Observação de resposta, navegação, popup e controle com `aria-controls`; falhas de acesso separadas de defeitos funcionais. |
| `ambidiff/adaptive.py`, `ambidiff/visual.py` | Estabilidade por conteúdo relevante e decoração sem DIV isolada. |
| `ambidiff/relevance.py`, `ambidiff/taxonomy.py` | Projeção dos grupos e classificação compatível com registros anteriores. |
| `ambidiff/reports.py`, `ambidiff/diagnostics.py`, `ambidiff/storage.py` | Exportação detalhada, JSON atômico, observações/URLs finais e ciclo de vida do log completo. |
| `tests/test_next.py` (novo), `tests/test_v14.py` | 28 novas regressões; adaptação do contexto simulado de captura à política de rotas, sem retirar asserções. |
| `scripts/benchmark_perf.py` | Comparação entre checkouts, observações de texto normalizadas, contagens reais e cobertura. |
| `README.md`, este documento, `benchmark-proxima-atualizacao.json` | Instruções, limites, resultados e medição reproduzível. |

## C. Funcionalidades e limites de atendimento

| Requisito | Implementação e limite |
|---|---|
| COMP-001 — documentos | Compara nomes, referências e destinos observados por cabeçalhos. Não lê PDF, corpo, conteúdo ou hash. `HEAD` não suportado é inconclusivo. |
| COMP-002 — opção ausente | Ausência é local à seção identificada, nos dois sentidos. Um item encontrado em outra seção vira possível realocação, sem apagar a diferença de organização. Preserva ÁUDIOS e outras opções pelo mesmo mecanismo genérico. |
| COMP-003 — nomenclatura | Rótulos diferentes continuam registrados mesmo com destino/função equivalentes. HTML incidental não basta para declarar ausência. Ambiguidades não são pareadas à força. |
| COMP-004 — externos | Opt-in, somente HEAD e redirecionamentos HTTP seguros. Registra equivalente/divergente/inacessível/inconclusivo. Sem páginas externas, crawling, cookies ou login. JS externo não é seguido. |
| COMP-005 — listas | Cada referência fica registrada, inclusive itens não verificados por limite. Cache por execução evita pedidos repetidos; limites não viram equivalência. |
| COMP-006 — agrupamento | Vários documentos ausentes na mesma seção/escopo viram uma DIV principal. IDs, nomes, referências, ocorrências e registros originais permanecem nos detalhes; exportação completa expande os membros. Seção/natureza/revisão/escopo diferentes não são misturados. |
| COMP-007 — estética | Decoração, geometria e diferenças técnicas de SVG isoladas ficam em observações técnicas, sem DIV principal. Ícones informativos, rótulos, visibilidade e ausência funcional continuam relevantes. Não é comparação por pixels. |
| COMP-008 — funcionamento | Opt-in limitado a navegação de leitura e controles reconhecidos fora de formulários. Observa mudança de conteúdo/estado, popup, navegação e destino final. Uma diferença observada é suficiente para registro; timeout, bloqueio, HTTP e automação têm diagnóstico próprio. Não cobre controles arbitrários ou fluxos completos. |
| COMP-009 — informação | Nomes/cargos/datas e outros valores em contextos correspondentes preservam os dois valores e a hipótese de diferença de dados. Causa desconhecida; conteúdo institucional não some por suposição de base antiga. A separação editorial anterior continua dependendo da declaração explícita. |

### Logs, comunicação e progresso

O servidor fornece `eventos_logs`, `cursor_logs`, `lacuna_logs` e identificação
da execução. IDs não voltam a zero entre execuções no mesmo processo. A janela
de transporte tem 200 eventos e o DOM no máximo 500 linhas. Cursor vencido ou
posterior ao atual causa ressincronização com aviso, sem fingir entrega completa.
O arquivo `relatorios/execucao_<id>.log` mantém as mensagens recebidas durante
a execução; falha de gravação é informada. O TXT diagnóstico resumido continua
existindo e não substitui esse arquivo completo. Reinício do processo não mantém
o cursor em memória; o identificador da execução permite reiniciar a leitura.

Polling tem timeout de 8 s, repetição com espera crescente limitada a 10 s,
sem sobreposição, e invalidação de respostas antigas. Falha de comunicação não
solicita parada nem declara término. O relatório final abre uma vez após leitura
bem-sucedida; erro de carregamento permite nova tentativa. F5 reconecta ao estado
do backend e não reinicia a varredura.

O relógio continua avançando localmente durante perda de comunicação, sem criar
atividade fictícia no servidor. A interface distingue último par processado,
etapa atual, descobertos/visitados/comparados/pendentes, última atividade e conexão.
O percentual é o avanço da **fila conhecida**, não a cobertura total do portal;
pode diminuir se novas páginas forem descobertas. A ETA usa amostras recentes,
fica indisponível sem dados suficientes, com fila crescente, amostra antiga ou
na finalização. Silêncio dos logs não prova travamento.

Um clique solicita interrupção, confirma visualmente
“Interrupção solicitada — aguardando operação atual” e desabilita o botão.
O backend aceita pedidos repetidos sem duplicar a ação. A parada é cooperativa:
a chamada em andamento precisa devolver o controle. Navegação, preparação,
cliques, referências e capturas possuem limites; não é necessário matar o processo.
Checkpoints são tentados no primeiro par, em intervalos de 15 s entre operações,
a cada 20 pares e antes da finalização. Interrupção mantém resultados e diagnóstico.
JSON é escrito atomicamente; não há transação única envolvendo todos os formatos
nem retomada automática após reiniciar o processo.

### Raízes e segurança

`/` de uma origem e `/web/portal` da outra são tratados como as raízes
explicitamente informadas, inclusive sem barra final. Não se remove esse prefixo
de caminhos parecidos. Caixa, queries funcionais e fragmentos de links importam;
parâmetros conhecidos de rastreamento continuam normalizados. A deduplicação do
crawl não percorre um mesmo documento novamente só por fragmento.

Destinos externos exigem habilitação, IPs públicos em todas as respostas DNS,
porta 80/443 e URL sem credenciais/indícios de escrita. Cada redirecionamento é
revalidado e a conexão usa o IP validado, mantendo Host, SNI e TLS verificado.
Sem proxy ambiental, cookies, Authorization ou envio de conteúdo interno.
Queries externas com credenciais reconhecidas ou outra URL são recusadas.
Origens A/B explicitamente configuradas podem ser privadas; outros destinos
privados/reservados/loopback são bloqueados. O navegador bloqueia escritas e
navegações fora do escopo, inclusive nas capturas; recursos normais de leitura
necessários à renderização não constituem uma auditoria externa.

Limites de HEAD: até 100 pedidos, até três redirecionamentos seguidos, timeout de
até 3 s por pedido e orçamento cooperativo de 8 s por referência. Há execução
serial e cache somente desta execução, inclusive de erros. O resolvedor DNS do
sistema operacional pode exceder esse orçamento antes de devolver o controle;
esse limite não é uma garantia de cancelamento imediato. A biblioteca legada
`Documentos` conserva a opção de fallback Range para compatibilidade de API,
mas o fluxo oficial a instancia com `permitir_range=False`; não baixa arquivos.

## D. Testes

Ambiente: Linux, Python em `/workspace/ambidiff-venv`, Chromium do sistema.
Playwright utiliza páginas simuladas ou servidores locais. Nenhuma credencial,
relatório real ou conteúdo corporativo integra as fixtures.

```bash
PYTHONDONTWRITEBYTECODE=1 /workspace/ambidiff-venv/bin/python -B -m unittest discover -s tests -v
node --check web/static/app.js
git diff --check
```

Resultado final: **140 testes aprovados em 84,740 s**, sem falhas ou testes
ignorados. Sintaxe JavaScript e verificação de espaços/diff também aprovadas.

Cobertura adicional: 199/200/201/1.000 mensagens, cursores e lacunas, nova
execução sem vazamento de logs anteriores, arquivo completo, reconexão, relógio,
abertura única do relatório, formulários inicialmente vazios, ambiente neutro,
raízes/subpastas, queries/case/fragmentos, seções nos dois sentidos, ÁUDIOS e
outros nomes, agrupamento e revisão/exportação, HEAD sem corpo e sem GET,
redirecionamentos e limites, bloqueio de privados/credenciais/escrita, popup,
JS interno, disclosure, controle inerte, HTML diferente, valores informativos e
mutação estética versus relevante. A suíte anterior continua verificando
interrupção, checkpoint, recuperação de falha e preservação das exportações.

Falhas encontradas durante o desenvolvimento foram corrigidas: fixtures com
Playwright aninhado, alteração da lista de disclosures durante a abertura,
assinatura de `ElementHandle.inner_text` e resposta de popup antes de existir
seu frame. Nenhuma asserção histórica foi removida para aprovar a suíte.

## E. Benchmark

Resultados: **sem ganho adicional de velocidade em relação a `208ed2b`**.

| Cenário | Mediana anterior | Mediana atual | Variação de duração |
|---|---:|---:|---:|
| Estável | 4,950 s | 4,989 s | +0,79% |
| Dinâmico | 12,276 s | 12,470 s | +1,58% |

Os intervalos observados foram 4,927–4,961 / 4,973–4,995 s no estável e
12,267–12,368 / 12,434–12,474 s no dinâmico (anterior/atual).
Não há teste estatístico ou comprovação de causa para essa pequena diferença.
A meta de reduzir 50% **não foi atingida contra essa referência**. Os ganhos
históricos contra uma versão mais antiga não são ganhos novos desta entrega.

Em todas as execuções: três pares descobertos/visitados/comparados, seis páginas
nos dois ambientes, seis requisições ao servidor, zero pares pendentes, falhas,
interrupções ou páginas sem inspeção profunda. As observações normalizadas e
os itens extraídos foram equivalentes. Os cartões caíram de 16 para 9 porque
textos dos dois ambientes passaram a ser apresentados juntos, sem perda dos
valores originais. Houve zero equivalências estáticas inconclusivas no cenário
estável e três no dinâmico, igualmente nas duas versões. Métricas por etapa,
releituras e contagens estão no artefato completo
[`benchmark-proxima-atualizacao.json`](benchmark-proxima-atualizacao.json).
Os benchmarks anteriores permanecem históricos, sem substituir esta referência.

```bash
python -B scripts/benchmark_perf.py --baseline /tmp/ambidiff-next-baseline --pages 3 --repetitions 3
```

A referência é um checkout separado do commit `208ed2b`. São três repetições por
versão/cenário, ordem alternada, três páginas por ambiente, cenários estável e
dinâmico, modo inteligente ligado, base antiga/capturas/cliques/externos desligados
igualmente. Não execute testes pesados simultaneamente à medição.

Além do tempo, comparam-se itens/contextos efetivamente extraídos em cada página,
pares, pendências, falhas, omissões e observações. Um texto diferente agora pode
formar um cartão com dois valores em vez de dois cartões independentes: o script
decompõe esses valores em observações por ambiente **nos dois checkouts** para
comparar evidência, e registra separadamente a quantidade real de cartões.
Isso não autoriza ignorar desaparecimento de evidência.

Este ensaio não mede listas externas, custo de TLS público, screenshots ou todos
os estados de JavaScript. Falsos positivos não recebem auditoria humana formal.
Não comprova redução de 50% em SEFAZ ou outro portal real.

## F. Riscos e pendências

- Contextos de seção genéricos/ambíguos e HTML mal rotulado podem exigir revisão;
  “não identificado na seção” não é prova de inexistência em todo o portal.
- HEAD 200 comprova somente uma resposta, não conteúdo correto, login satisfeito
  ou funcionamento no navegador. HEAD bloqueado/405, TLS, DNS e timeout podem
  deixar a observação inconclusiva. Não existe fallback que leia página externa.
- Cache é observação temporária, não garantia de disponibilidade permanente.
- Cliques são limitados e opcionais. Autenticação, formulários, escrita,
  downloads e controles sem semântica segura não são executados. Eventos GET
  com efeito indevido no servidor não podem ser detectados com certeza absoluta.
- Páginas dinâmicas que carreguem após os limites mantêm limitação explícita;
  estabilidade do DOM não prova todos os estados futuros de interação.
- Mudanças de texto em widgets relevantes continuam observadas; não se ignora
  todo componente dinâmico para melhorar artificialmente o benchmark.
- Logs, URLs e capturas locais podem conter dados do portal. Não devem ser
  publicados ou anexados automaticamente. Falha de disco pode impedir checkpoint.
- Não houve teste de Windows, AGER, CGE, SEFAZ, POLITEC ou Legislação reais.
  Integração futura com os PRs USEIA/CGE exige revisar conflitos em navegação,
  status, polling e interrupção; as branches não foram misturadas.

## G. Validação manual autorizada no Windows

1. Use instalação isolada e URLs permitidas, sem credenciais na URL. Confirme
   URLs vazias e seleção independente PRD/DES/LAB nos lados A/B. Uma mesma
   classificação de ambiente nos dois lados deve ser recusada.
2. **AGER:** configure explicitamente raiz e subpasta correspondentes. Confira
   página inicial e links internos, com/sem barra; não deve aparecer diferença
   só pelo prefixo configurado. Queries funcionais diferentes devem permanecer.
3. **CGE:** confira ÁUDIOS presente num lado e ausente na seção do outro, inclusive
   se houver referência em outra seção. Invertendo A/B, a observação deve inverter
   os lados. Navegue por mais de 200 mensagens, desconecte/reconecte o painel e
   faça F5; verifique aviso de lacuna e download do log completo.
4. **SEFAZ:** confira dados institucionais e widget Messenger. Só decoração não
   deve gerar DIV; nome/cargo diferente ou controle ausente deve permanecer.
   Compare modos com iguais escopo/opções; registre cobertura além da duração.
5. **POLITEC:** confira rótulos diferentes com mesmo destino e opções movidas
   entre seções; não confundir organização com desaparecimento global.
6. **Legislação:** vários documentos ausentes devem formar uma DIV por seção,
   expansível com todos os nomes, referências e IDs. Compare JSON, HTML, CSV
   principal e completo. Documento com HEAD bloqueado deve ficar inconclusivo,
   sem abrir PDF. Ative externos somente quando autorizado; confira destino
   HTTP final, sem entrar na página externa.
7. Em página de teste de leitura autorizada, habilite cliques e observe Início,
   aba/disclosure, popup, controle inerte e resposta de acesso. Não teste ações
   com efeito em dados. Um timeout isolado não deve virar defeito permanente.
8. Interrompa uma vez durante operação lenta. Confira confirmação/botão
   desabilitado, encerramento cooperativo, fila pendente, relatório parcial,
   checkpoint e diagnóstico. Uma perda temporária de comunicação não deve
   interromper o backend ou duplicar a abertura do relatório.

Registre commit, opções, horário, contagens e resultado esperado/observado em
canal interno aprovado. Não envie relatórios ou capturas sensíveis para serviços
externos. Restrição de acesso é limitação a registrar, não algo a contornar.

## H. Instalação, atualização e confirmação de funcionamento

Com o aplicativo fechado, preserve a instalação anterior e os dados locais.
Se houver modificações no checkout, revise-as antes de atualizar; não use reset
destrutivo. Para um checkout limpo e autorizado:

```cmd
git status
git fetch origin
git switch perf/otimizacao-varredura
git pull --ff-only origin perf/otimizacao-varredura
instalar.bat
INICIAR_AMBIDIFF.bat
```

Alternativamente extraia o ZIP **desta branch** em pasta nova. `instalar.bat`
cria `.venv`, instala `requirements.txt` e Chromium; requer Python 3 por `py`
ou `python` e permissão de instalação. O iniciador executa `web\server.py`.
Não exponha o servidor na rede; use `http://127.0.0.1:8765`.

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Confirme no navegador: formulário sem URLs preenchidas, status de conexão,
ausência de execução automática e resposta JSON em
`http://127.0.0.1:8765/api/status?cursor=0`. Durante teste autorizado, compare
`eventos_logs`, `cursor_logs`, `andamento` e estado do backend com o painel.
Se o painel desconectar, não inicie outra execução antes de consultar o status.
Não desabilite TLS nem contorne autenticação/restrições da TI para testar.

## I. Controle de versão

Branch de trabalho: `perf/otimizacao-varredura`; base `208ed2b`.
O hash do commit de entrega é informado pelo Git e na resposta de entrega
(não é embutido neste arquivo para evitar autorreferência). Nenhum merge,
deploy, GitHub Pages ou publicação de dados internos faz parte desta atualização.
