# Manutenção assistida por IA

Esta infraestrutura adiciona instruções e CI à base estável `4f2b4bce…`, sem
alterar Python de produção, interface, testes, dependências ou benchmarks.

## Instruções e Skills

O `AGENTS.md` da raiz reúne contratos permanentes, segurança, comandos e contexto
mínimo. As Skills em `.agents/skills/<nome>/SKILL.md` têm frontmatter YAML com
`name` e `description`, seguido de um procedimento específico:

| Skill | Quando usar | Resultado esperado |
|---|---|---|
| `ambidiff-diagnostico` | Erro, interrupção, regressão ou inconclusivo | Evidências, causas versus hipóteses e correção mínima proposta |
| `ambidiff-otimizacao` | Lentidão, cache, descoberta ou fila | Gargalo medido, antes/depois com cobertura comparável e riscos |
| `ambidiff-validacao` | Correção, revisão ou preparação de entrega | Testes pertinentes, resultados, revisão e limitações |

Exemplos: “Use $ambidiff-diagnostico para investigar Target closed”,
“Use $ambidiff-otimizacao para medir o custo de checkpoints” e
“Use $ambidiff-validacao para validar esta correção”. Diagnóstico sozinho não
habilita alterações funcionais. Não há IA integrada ao produto ou aos relatórios.

Carregue só a Skill e os arquivos necessários. Comece pelo diff/teste afetado;
não leia todo o repositório, rode benchmarks ou gere relatórios longos em tarefas
simples. Regras comuns ficam no AGENTS; procedimentos, nas Skills; arquitetura e
histórico continuam nos documentos já existentes.

O agente principal resolve tarefas simples e moderadas. Subagentes só fazem
sentido em frentes complexas independentes ou revisão significativa, se houver
suporte: defina entregas/arquivos, evite trabalho duplicado e consolide resultados.
Não há orquestrador, execução múltipla obrigatória ou ferramenta adicional.

## Testes locais

Com Python 3.12 e Node disponíveis, na raiz:

```text
python -m venv .venv
```

Ative com `.venv\Scripts\activate` no CMD ou `source .venv/bin/activate` no POSIX:

```text
python -m pip install -r requirements.txt
python -m playwright install chromium
python -B -m unittest discover -s tests -p test_update19.py -v
python -B -m unittest discover -s tests -v
node --check web/static/app.js
git diff --check
```

A suíte usa `unittest`, simulações, HTML fabricado e servidores loopback. Chromium
é necessário para testes de DOM, recuperação, capturas e PDF. Não é necessário
configurar modo visível ou variável de headless. Não acesse portais reais por
conta de uma falha de fixture; investigue a dependência local.

## GitHub Actions

`.github/workflows/tests.yml` usa um único job `windows-latest`, Python 3.12 e
Node 22. Windows aproxima o CI da plataforma do produto; não foi criada matriz.
Instala apenas `requirements.txt` e Chromium, valida JavaScript e roda a suíte
existente, sem benchmarks. Os 20 minutos limitam somente o job de CI, não a
varredura do AmbiDiff nem sua meta de desempenho.

Dispara em pushes para `perf/otimizacao-varredura` e esta branch de infraestrutura,
e em PRs direcionados a essas branches ou `main`; permite execução manual.
Concorrência cancela execuções ultrapassadas da mesma origem/branch. Não usa
`pull_request_target`, credenciais corporativas, agentes pagos, MCP, upload de
artefatos, deploy, Pages, escrita no repositório ou merge automático. Permissão:
`contents: read`; o checkout não persiste credenciais. As etapas de instalação
consultam os distribuidores de dependências e Actions, não portais institucionais.
Não adicione dados internos como fixtures ao repositório.

Em **GitHub → Actions → Testes AmbiDiff**, escolha branch/commit e abra o job para
consultar cada etapa e a saída do unittest. No PR, use **Checks**. Se Actions
estiver desabilitado ou exigir aprovação de workflow, o mantenedor deve habilitar
ou aprovar no GitHub. O workflow não configura proteção de branch nem torna o
check obrigatório automaticamente. Não ignore falhas para incorporar alterações.

## Manter e confirmar

Ao mudar comandos, contratos ou organização, atualize a fonte correspondente,
confira referências, valide YAML/frontmatter e remova regras obsoletas. Não
atualize a quantidade de testes por estimativa: conte/execute a suíte atual.
Novas branches de manutenção podem exigir atualizar os filtros de push/PR do CI.

Confirmado neste ambiente: Git e arquivos locais acessíveis, estrutura das três
Skills e metadados legíveis, validação estática do workflow e execução dos testes
locais. Não foi usado subagente nem executado modelo pago no CI. A descoberta e
ativação automática das novas Skills pelo Codex no navegador só poderão ser
confirmadas após carregar a branch numa sessão que as exponha; criar os arquivos
não comprova registro ativo na sessão atual. A disponibilidade de delegação
também depende da interface e permissões da sessão, sem promessa de habilitação.

O job Windows e a interpretação final pelo GitHub dependem da primeira execução
remota. Testes Linux locais não comprovam execução Windows nem produção. Esta
entrega não investiga os inconclusivos da POLITEC e não acessa ambientes reais.

## Verificação desta entrega

Base: `4f2b4bce2f9be830b510d25454a37d3875e90f3e`, branch
`chore/infra-codex-agents-skills-ci`. A suíte existente passou com **244 testes,
sem falhas ou skips, em 115,354 s**, em Linux com Chromium local. A primeira
execução no sandbox restrito teve 45 erros, uma falha e um skip por bloqueio de
sockets/Chromium e efeitos em cascata; a repetição com permissão para recursos
locais passou, sem alterar produto ou testes.

Validaram-se frontmatter e estrutura das três Skills, YAML e estrutura do job,
permissões/eventos, `node --check`, whitespace e o diff vazio em produção,
interface, testes, scripts e dependências. PyYAML do ambiente foi usado somente
na verificação, sem adicioná-lo ao projeto. Não havia actionlint disponível;
a validação local não substitui o interpretador e a execução remota do Actions.
A instalação pip confirmou as dependências existentes e o instalador Chromium
foi conferido com `--dry-run`; o CI fará a instalação própria no runner Windows.
Nenhum benchmark foi executado nesta alteração de infraestrutura.
