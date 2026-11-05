# Arquitetura e manutenção

## Fluxo

```text
Painel localhost -> worker Engine -> Planner -> tarefas SQLite
                               -> BrowserSession (contexto A / contexto B)
                               -> modelos Page / Element
                               -> Matching -> Comparison / Visual / funções
                               -> ocorrências -> DIVs consolidadas -> revisões
```

O programa não importa o AmbiDiff legado. Apenas o script comparativo importa o
motor antigo, de forma explícita, para medi-lo sem alterar seus arquivos.

## Responsabilidades

| Arquivo | Responsabilidade |
| --- | --- |
| models.py | Contratos de página/elemento, IDs e observações serializáveis |
| policy.py | Normalização, escopo, classificação de referência e proibição de escrita |
| extract.js | Coleta semântica e geométrica somente de leitura |
| browser.py | Chromium, isolamento, capturas, HEAD, ações permitidas e recuperação |
| matching.py | Escolha mútua por evidências, hipóteses e ambiguidade |
| comparison.py | Estrutura, destinos, documentos referenciados e observações funcionais |
| visual.py | Imagens reais, geometria, diferenças e máscaras explícitas |
| planner.py | Prioridades, deduplicação, capacidade e amostragem |
| engine.py | Executa o plano, registra cobertura e preserva parciais |
| store.py | SQLite transacional incremental e histórico separado de revisão |
| reporting.py | Projeções selecionadas, HTML portátil, CSV, JSON e ZIP |
| web.py / static / templates | API local, worker, painel e revisão |

## Planejamento e cobertura

A fila é uma prioridade de verificações, não uma meta de páginas. Pares de páginas
são contêineres para componentes; tarefas documentais têm fluxo próprio por HEAD.
Opções correspondentes podem levar a caminhos diferentes, mantendo o fato de que
seus destinos diferem. Semântica é um vocabulário determinístico limitado, não IA.

Correspondências intermediárias não entram no contador de equivalências altas.
Quando há dois destinos internos, podem receber uma observação adicional: título
específico distinto do título da origem e pelo menos dois componentes estruturais
compatíveis de alta confiança. Sem corroboração, a tarefa é inconclusiva; não se
expande sua árvore. Isso não prova identidade completa de finalidade.

Menus e serviços precedem documentos/legislação, institucionais e editoriais.
Representantes de notícias e uma rota de paginação por padrão são admitidos;
outros ficam `sampled`, com URL e motivo persistidos. A proteção até 1.000 pares
não é uma meta nem autorização para validar itens não vistos. Árvores unilaterais
não são expandidas por padrão. Todos os limites ficam explícitos nos resultados.

Cada tarefa tem estado `pending`, `running`, `done`, `failed`, `inconclusive`,
`sampled` ou `blocked`. O inventário permite reconciliar a quantidade planejada
com esses estados. `pages_discovered` distingue URLs observadas nas tarefas de
páginas visitadas e pares comparados. Funções executadas podem ainda ser
inconclusivas: uma ação sem efeito em ambos os lados não comprova sucesso.

## Persistência e recuperação

SQLite usa transações e WAL. Cada tarefa, página, ocorrência, log e revisão é
persistido separadamente, sem serializar novamente todo o histórico como um
checkpoint JSON. O banco constitui o checkpoint incremental. Não remova arquivos
WAL/SHM de uma execução ativa; para cópias use o servidor parado ou backup SQLite.

Ao retomar, tarefas `running` tornam-se pendentes com limite de duas admissões;
concluídas não são repetidas. Falhas definitivas permanecem registradas, sem retry
infinito. A sessão do navegador pode ser recuperada uma vez por coleta se encerrar.
O ID da comparação é mantido. Uma interrupção não apaga evidências nem revisões.

Ocorrências usam ID determinístico e inserção idempotente. Grupos recebem DIVs
estáveis durante a execução. Agrupamento considera fatos, contexto, destinos e
páginas; não apenas rótulo. Esta versão conserva contextos de componentes globais,
mas não presume que toda instância tenha comportamento funcional igual.

## Visual e funções

Os contextos compartilham viewport/escala/locale configurados, sem compartilhar
cookies. Animações são reduzidas/desativadas durante capturas. Cada componente
capturado é comparado com a região correspondente, e os PNGs permanecem locais.
Campos de senha nunca têm seus valores extraídos; páginas com autenticação
identificada não recebem capturas de evidência automaticamente.

A comparação usa diferenças de pixels e geometria. Diferença visual é candidata
para revisão, não julgamento de qual ambiente está correto. Alterações de texto
puro com estilo, texto visível e dimensões compatíveis podem ter diagnóstico de
rasterização inconclusiva: as imagens e a fração de pixels são preservadas. Ícones,
imagens, recortes, sobreposição e estilos diferentes não usam essa exceção.

Máscaras precisam aparecer nos dois modelos com motivo igual; área individual e
acumulada não pode exceder 25% do componente. A interface atual não oferece editor
de máscaras. Conteúdo editorial não autoriza mascarar estruturas ausentes.

Controles com contrato ARIA/details são testados em páginas temporárias, com
limite explícito de ações. Novas requisições durante o clique são bloqueadas;
interferência gera inconclusão. Controles sem contrato seguro não são clicados.
Links podem ter destinos HTTP inspecionados, sem alegar validação do handler JS.

## Manutenção

Use testes direcionados primeiro e a suíte completa para integração. O benchmark
possui adaptadores para os dois formatos; alterações nesses adaptadores exigem
regressões, pois mudar a pontuação pode alterar a interpretação dos resultados.
Consulte `benchmark-method.md`. Não edite o legado para favorecer comparações.

Futuras melhorias precisam preservar ÁUDIOS nos dois sentidos, segurança, IDs,
revisões, parciais e evidências. Portais reais e autenticação exigem autorização
específica. Subagentes são opcionais no desenvolvimento, não componentes do Next.
