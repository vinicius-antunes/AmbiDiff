<div align="center">

# AmbiDiff

**Compare ambientes web com mais contexto, menos ruído e evidências para revisão.**

Ferramenta local para Windows que identifica diferenças de estrutura, navegação, conteúdo e referências entre ambientes **PRD, DES, LAB e HOMOL**.

**Somente leitura · Chromium oculto · Relatórios locais**

[Instalação](#instalação) · [Como usar](#primeira-comparação) · [Resultados](#entenda-os-resultados) · [AmbiDiff IA](#análise-assistida-por-inteligência-artificial) · [Documentação](#documentação)

</div>

---

## Visão geral

O **AmbiDiff** percorre dois ambientes web autorizados e registra diferenças que merecem investigação. O objetivo é apoiar testes de homologação, revisão de portais e validações após alterações de infraestrutura — sem considerar automaticamente que o ambiente de produção está correto.

| O que é analisado | O que o resultado significa |
| --- | --- |
| Menus, opções e estrutura | Elementos ausentes ou diferentes podem indicar uma divergência estrutural. |
| Links, rotas, serviços e redirecionamentos | Destinos e respostas observadas são comparados; um link diferente não é necessariamente um defeito. |
| Textos, notícias e conteúdos editoriais | Diferenças de atualização podem ser tratadas como editoriais, sem ocultar alterações estruturais. |
| Documentos e downloads | Referências e disponibilidade observável são verificadas; o conteúdo interno de PDFs não é comparado. |
| Falhas de coleta e navegação | Erros, limitações e verificações inconclusivas são registrados separadamente. |

> **Importante:** o AmbiDiff é uma ferramenta de triagem de QA. Uma DIV precisa de revisão humana para determinar causa, impacto e qual ambiente apresenta o comportamento esperado.

## Instalação

**Requisitos:** Windows, Python 3, conexão para instalar as dependências e permissão para acessar os ambientes a serem comparados. O programa utiliza **Python, Flask, Playwright e Chromium**; não é distribuído como instalador `.exe`.

1. Na [página do repositório](https://github.com/vinicius-antunes/AmbiDiff), selecione a branch `main` e use **Code → Download ZIP**.
2. Extraia o conteúdo para uma pasta no computador.
3. Execute **`instalar.bat`** uma vez. Ele prepara o ambiente virtual, instala as dependências e configura o Chromium.
4. Execute **`INICIAR_AMBIDIFF.bat`** para iniciar o programa.
5. Caso o navegador não abra automaticamente, acesse **http://127.0.0.1:8765**.

```text
AmbiDiff/
├── instalar.bat              # primeira instalação
├── INICIAR_AMBIDIFF.bat     # iniciar o programa
├── ambidiff/                # motor de comparação
├── web/                     # interface e API locais
├── tests/                   # testes de regressão
└── docs/                    # documentação complementar
```

O servidor escuta localmente. Dependendo da rede corporativa, o acesso a DES, LAB ou HOMOL pode exigir DNS, VPN ou permissões específicas. **Não contorne restrições de acesso ou de segurança.**

## Primeira comparação

1. Abra **Comparar ambientes**.
2. Selecione os tipos de ambiente **A** e **B** e informe as duas URLs iniciais autorizadas.
3. Se houver confirmação de que uma base está desatualizada, indique isso na opção de condição das bases. Não é obrigatório.
4. Clique em **Iniciar varredura** e acompanhe o progresso, as falhas e a cobertura.
5. Ao terminar, abra **Divergências** ou **Histórico** para revisar, selecionar e exportar os resultados.

O Chromium funciona em segundo plano, sem abrir janelas durante a varredura. A análise é bidirecional: diferenças exclusivas de qualquer um dos ambientes podem ser registradas.

### Como funciona a varredura

| Regra | Comportamento |
| --- | --- |
| **Fila por relevância** | Prioriza menus, serviços, notícias, legislação, páginas institucionais e históricas. |
| **Até 1.000 pares HTML** | Limite de admissão de páginas HTML; os pares já admitidos são concluídos ou recebem diagnóstico de falha. |
| **Filtro de URLs** | Evita aprofundamento editorial e paginações redundantes, com exceções para conteúdos estruturais relevantes. |
| **Documentos** | Seguem verificações próprias e não ocupam as vagas de pares HTML. |
| **Sem prazo rígido** | 1h30 é uma meta de desempenho, não uma condição automática de parada. |
| **Interrupção e retomada** | Procura preservar checkpoints, resultados parciais, diagnósticos e dados já coletados. |

**Cobertura não é o mesmo que conclusão da fila:** 100% dos pares admitidos encerrados não significa que todas as URLs do portal foram examinadas. Uma referência excluída pelo filtro, uma página inacessível ou uma verificação inconclusiva **não comprova equivalência**.

O filtro evita expandir indiscriminadamente páginas editoriais, incluindo rotas e paginações Liferay, mas deve preservar indícios de opções ausentes, menus, serviços, legislação e documentos. Consulte a [política de filtros e sua evolução](docs/filtro-urls-varredura.md).

## Entenda os resultados

| Situação observada | Como interpretar |
| --- | --- |
| **Divergência (DIV)** | Diferença registrada com contexto e, quando disponível, evidências. Precisa de revisão. |
| **Possível diferença editorial** | Pode decorrer de notícias ou bases atualizadas em momentos diferentes. |
| **Inconclusivo / sem contraparte** | Faltam elementos suficientes para confirmar equivalência ou defeito. |
| **Falha de coleta** | Pode envolver HTTP, timeout, acesso, navegação ou erro da automação. |

**Exemplo:** se a opção “ÁUDIOS” aparece em um ambiente e não é identificada no outro, a ausência merece investigação. Não se deve descartá-la apenas porque os ambientes têm notícias diferentes ou estruturas HTML distintas.

### Relatórios e histórico

O programa permite revisar ocorrências, selecionar DIVs e manter registros locais das execuções. Os formatos disponíveis incluem:

- **JSON:** dados estruturados para análises e diagnósticos posteriores.
- **CSV:** organização e filtragem em planilhas.
- **HTML:** leitura das ocorrências e evidências disponíveis.
- **PDF:** relatório para consulta e compartilhamento autorizado.
- **Diagnóstico JSON e log TXT:** informações técnicas sobre falhas, limitações e execução.

A exportação prepara o formato solicitado, evitando gerar todos os formatos desnecessariamente. O navegador gerencia o local de download; para escolher a pasta, habilite **“Perguntar onde salvar cada arquivo”** nas configurações dele.

### Análise assistida por inteligência artificial

O **AmbiDiff IA — Analisador Inteligente de Divergências** é um complemento opcional, utilizado no ChatGPT após a varredura. Ele ajuda a interpretar os resultados, mas não integra o motor de comparação local nem participa automaticamente da coleta.

**Como utilizar:**

1. No AmbiDiff, abra **Divergências** e selecione as DIVs que deseja investigar.
2. Exporte as ocorrências selecionadas em **JSON**.
3. No ChatGPT, abra o complemento **AmbiDiff IA**, caso tenha acesso autorizado, e anexe o JSON.
4. Se necessário, inclua capturas de tela e o diagnóstico JSON da execução, devidamente sanitizados.
5. Solicite uma análise técnica das divergências e revise as conclusões antes de encaminhá-las à equipe responsável.

**O que a IA pode ajudar a identificar:**

- Divergências estruturais e funcionais que merecem investigação prioritária.
- Possíveis diferenças editoriais decorrentes de bases desatualizadas.
- Possíveis falsos positivos, equivalências e falhas da automação.
- Impacto, nível de confiança, evidências disponíveis e verificações recomendadas, preservando os IDs originais das DIVs.
- Resumos técnicos e executivos para apoiar a revisão humana.

A IA deve separar fatos observados de hipóteses, não assumir que PRD está correto e não tratar resultados parciais como uma varredura completa. Suas conclusões não substituem testes nos ambientes reais.

**Privacidade:** utilize somente arquivos públicos devidamente sanitizados e com autorização para compartilhamento. Não envie credenciais, dados internos ou informações sensíveis. O uso do complemento é independente da execução local do AmbiDiff.

### Casos de uso

O AmbiDiff pode apoiar **comparações entre produção e homologação**, conferência de menus e serviços após atualizações e verificações de sites associados a mudanças de infraestrutura.

Ele **não confirma sozinho** a integridade de bancos de dados, a configuração de servidores, o funcionamento de todas as APIs ou fluxos completos de negócio. Essas verificações exigem testes complementares e acesso autorizado às ferramentas da equipe responsável.

## Limitações e segurança

- O programa compara comportamentos **observados**, não garante cobertura integral nem igualdade visual pixel a pixel.
- URLs com conteúdos não examinados não devem ser tratadas como equivalentes; documentos não têm seu conteúdo interno comparado.
- Diferenças editoriais, defeitos estruturais e falhas da automação devem permanecer distinguíveis.
- Formulários, autenticação, ações modificadoras e funcionalidades complexas não recebem validação funcional completa.
- O uso é local e deve se limitar a ambientes autorizados. Não compartilhe checkpoints, logs, imagens ou relatórios internos sem revisar e sanitizar os dados.
- Testes simulados e benchmarks não substituem validação em portais reais.

## Solução de problemas

| Sintoma | O que verificar primeiro |
| --- | --- |
| Programa não inicia | Execute `instalar.bat` e confira `py -3 --version`. |
| Painel local não abre | Confira se `INICIAR_AMBIDIFF.bat` permanece aberto e se a porta `8765` está disponível. |
| Mensagem **Failed to fetch** | Verifique o terminal e `http://127.0.0.1:8765/api/status`. |
| Um ambiente não carrega | Revise URL, DNS, VPN, certificado e permissões com a equipe responsável. |
| Varredura interrompida ou parcial | Consulte o diagnóstico, as falhas e a possibilidade de retomada pelo histórico. |
| Download não aparece | Confira os downloads do navegador (`Ctrl + J`), o terminal e a pasta de relatórios. |

Para começar uma nova verificação, consulte também [Primeira comparação](#primeira-comparação).

## Documentação

| Assunto | Referência |
| --- | --- |
| Instalação, uso e solução de problemas | [Instalação](#instalação) · [Primeira comparação](#primeira-comparação) · [Solução de problemas](#solução-de-problemas) |
| Navegação, estabilidade e recuperação | [Estabilização da varredura](docs/estabilizacao-varredura.md) |
| Prioridades e limite de páginas | [Fila dinâmica](docs/otimizacao-fila-dinamica.md) · [Portais extensos](docs/atualizacao-portais-extensos.md) |
| Política de URLs e exclusões | [Visão geral](docs/filtro-urls-varredura.md) · [Etapa 2](docs/filtro-urls-etapa2.md) · [Etapa 3](docs/filtro-urls-etapa3.md) · [Etapa 4](docs/filtro-urls-etapa4.md) |
| Pareamento e relevância | [Eficiência do pareamento](docs/pareamento-eficiencia.md) · [Filtro de relevância](docs/filtro-relevancia.md) |
| Desenvolvimento e manutenção | [AGENTS.md](AGENTS.md) · [Guia de manutenção](docs/manutencao-ia.md) |

### Para quem desenvolve

A aplicação organiza o motor em `ambidiff/`, a interface/API em `web/` e as regressões em `tests/`. Com o ambiente virtual instalado, execute:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Para alterações no JavaScript, utilize também `node --check web/static/app.js`, caso o Node.js esteja disponível. O repositório inclui um fluxo de testes no [GitHub Actions](https://github.com/vinicius-antunes/AmbiDiff/actions).

A manutenção deve preservar as funcionalidades existentes, criar regressões para correções importantes e distinguir resultados testados em fixtures de validações nos ambientes reais.


---

<div align="center">

**AmbiDiff — comparação de ambientes com evidências e revisão humana.**

Uso local · Ambientes autorizados · Sem assumir que PRD esteja sempre correto

</div>