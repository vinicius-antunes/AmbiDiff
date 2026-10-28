# Diretrizes permanentes do AmbiDiff

## Trabalho e contexto

- Confirme repositório, branch, HEAD remoto e estado local antes de editar. Use a
  versão mais recente da branch da tarefa; não presuma que `main` é a referência.
  Preserve mudanças preexistentes e informe impedimentos de sincronização.
- Preserve comportamentos validados. Investigue a causa, compare versões em
  regressões e faça mudanças pequenas e revisáveis; não reescreva módulos sem
  justificativa. Crie/atualize regressões para comportamentos importantes.
- Leia apenas arquivos relacionados ao pedido. Acione uma Skill especializada
  quando necessário; não carregue todas nem releia a arquitetura inteira.
- Diagnóstico não autoriza implementação. Siga o escopo autorizado; não faça
  commit, push, merge, deploy, publicação ou GitHub Pages sem autorização.
- Documente mudanças relevantes, testes aprovados/falhos/não executados e limites.
  Testes locais/simulados não constituem validação em produção.

## Contratos a preservar

- Compare estrutura, função, navegação, documentos e conteúdo nos dois sentidos;
  PRD não é automaticamente correto. Reconheça equivalência mesmo com posição ou
  HTML distintos, sem ocultar opções ausentes ou divergências para reduzir números.
- Separe defeitos confirmados, hipóteses editoriais/bases desatualizadas,
  verificações inconclusivas e falhas da automação. Defasagem editorial não
  justifica ocultar problemas estruturais.
- Preserve **ÁUDIOS da CGE**: opção presente em um ambiente e não identificada no
  correspondente (caso histórico DIV-0004; não dependa do número exato no teste).
- Preserve o teto interno de **1.000 pares HTML admitidos**, o fluxo documental e
  as compatibilidades legadas. No teto, cesse admissões e conclua a fila aceita.
  **1h30 é meta**, não prazo de parada. Prioridades: menus, serviços, notícias,
  legislação, institucionais e históricos, sem abandonar admitidos.
- Mantenha Chromium oculto, isolamento dos ambientes, PRD/DES/LAB/HOMOL e as
  restrições de novas seleções e compatibilidades históricas já implementadas.
- Preserve interrupção cooperativa, diagnósticos, resultados parciais, checkpoints
  e retomada possível; exportações, evidências, IDs e revisões manuais.

## Segurança

- Testes automatizados usam fixtures, simulações e loopback. Não acesse portais
  institucionais reais sem autorização específica; não execute escrita nos sites.
- Não envie dados internos, credenciais ou evidências sensíveis a serviços externos.
  Não versione logs de execução, checkpoints, relatórios internos ou temporários.
- Não contorne autenticação, certificados, bloqueios ou restrições de acesso;
  preserve os mecanismos existentes de somente leitura.

## Comandos e referências

Na raiz, com o ambiente virtual ativo (Windows: `.venv\Scripts\activate`;
POSIX: `source .venv/bin/activate`; criação: `python -m venv .venv`):

```text
python -m pip install -r requirements.txt
python -m playwright install chromium
python -B -m unittest discover -s tests -p test_update19.py -v
python -B -m unittest discover -s tests -v
node --check web/static/app.js
git diff --check
git diff --cached --check
```

Instalação/uso Windows: `README.md`. Contexto técnico sob demanda:
`docs/estabilizacao-varredura.md`, `docs/otimizacao-fila-dinamica.md`,
`docs/atualizacao-13-17.md`. Rotina de manutenção, Skills e CI:
`docs/manutencao-ia.md`. Não rode benchmarks em mudanças documentais.

## Subagentes

Resolva sozinho tarefas simples/moderadas. Considere delegação apenas se o recurso
estiver disponível e houver frentes complexas independentes: delimite papéis e
arquivos, evite leituras duplicadas e edições conflitantes e consolide a revisão.
Não há execução múltipla obrigatória; não instale ferramentas para forçá-la.
