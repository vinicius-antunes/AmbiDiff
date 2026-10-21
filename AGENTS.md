# Diretrizes permanentes do AmbiDiff

## Contexto e escopo

O AmbiDiff é uma ferramenta local para Windows, baseada em Python, Flask e
Playwright Chromium, que compara sites entre PRD, DES e LAB. A versão presente
ao criar este documento é a 1.5; este número não deve limitar evoluções futuras.
Estas diretrizes se aplicam a todo o repositório.

## Desenvolvimento e preservação de comportamento

- Trabalhe sempre sobre a versão mais recente do código existente. Antes de
  editar, confira o checkout, o estado do Git, o README, os módulos e os testes
  relevantes. Preserve alterações locais; não use cópias antigas nem faça reset
  ou sobrescrita para atualizar o código. Se houver dúvida sobre a versão de
  referência ou acesso remoto indisponível, explicite a limitação.
- Preserve funcionalidades já validadas. Prefira mudanças pequenas e focadas;
  evite reescritas desnecessárias e alterações fora do escopo solicitado.
- Crie testes de regressão para correções importantes, reproduzindo o problema
  e verificando o comportamento esperado. Execute a suíte existente e informe
  separadamente testes aprovados, falhos, ignorados e não executados.
- Reduza falsos positivos sem ocultar problemas reais. Não elimine verificações
  ou enfraqueça asserções apenas para obter resultados positivos.
- Não considere PRD automaticamente correto. Uma diferença não determina qual
  ambiente está correto, atualizado ou defeituoso; descreva a evidência e seus
  limites, mantendo a necessidade de revisão humana.
- Explique alterações de maneira didática: problema, solução, comportamento
  preservado, validação executada e limitações conhecidas.

## Divergências estruturais, funcionais e editoriais

- Distinga divergências estruturais e funcionais de diferenças editoriais que
  possam decorrer de bases desatualizadas. Notícias, datas e imagens editoriais
  podem ser classificadas separadamente quando houver contexto suficiente e
  confirmação explícita da defasagem pelo usuário.
- Avisos no DOM são indícios, não confirmação automática de base desatualizada.
  A defasagem não justifica esconder menus, opções institucionais, destinos de
  navegação ou problemas funcionais. Na dúvida, mantenha o registro para revisão.
- Preserve a detecção do caso conhecido como **DIV-0004 da CGE: opção ÁUDIOS
  encontrada no PRD e ausente no DES**. Esse achado deve continuar sendo tratado
  como divergência estrutural, inclusive quando DES for declarado desatualizado.
  Não o reclassifique como conteúdo editorial para reduzir a contagem de DIVs.
- Os IDs atuais são sequenciais por execução: preserve o ID DIV-0004 nos
  relatórios históricos, sem forçar esse número em novas execuções. A regressão
  deve proteger a detecção semântica da opção ÁUDIOS, além da persistência do
  registro histórico.
- Preserve os registros completos e sua rastreabilidade ao agrupar diferenças;
  um resumo de interface não deve substituir os dados necessários à revisão.
- Falhas de acesso, downloads e coleta incompleta não comprovam ausência de
  conteúdo. Não declare equivalência dos ambientes a partir de varredura parcial
  ou ausência de divergências detectadas.

## Interrupções, dados e segurança

- Preserve resultados parciais, checkpoints disponíveis e diagnósticos quando
  houver interrupções ou falhas. Identifique explicitamente a cobertura parcial,
  os motivos da parada e as páginas pendentes, sem prometer recuperação integral.
- Preserve o relatório original e as decisões de revisão manual. Exclusões e
  confirmações devem manter a separação atual entre dados originais e auxiliares.
- Mantenha a aplicação local, escutando apenas em loopback por padrão. Não
  publique o projeto, não crie GitHub Pages e não envie dados internos, relatórios,
  capturas ou credenciais para serviços externos.
- Use somente sites autorizados. Prefira testes com HTML sintético, mocks e
  servidores locais. Não acesse sistemas internos sem autorização explícita,
  não contorne login, VPN ou restrições de rede e não exponha segredos nos logs.
- Não faça merge automaticamente. Apresente as mudanças e a validação para
  revisão do usuário.

## Estrutura atual

- `ambidiff/core.py`: modelos, normalização de URLs, extração do DOM e comparação.
- `ambidiff/paired.py`: varredura pareada, links, agrupamento e evidências.
- `ambidiff/intelligence.py`: classificação editorial e sinais de defasagem.
- `ambidiff/visual.py` e `functional.py`: indícios visuais e cliques opcionais.
- `ambidiff/storage.py`: persistência e revisão manual dos relatórios.
- `ambidiff/reports.py` e `diagnostics.py`: exportações e diagnósticos técnicos.
- `web/server.py`, `web/templates/` e `web/static/`: API Flask e interface local.
- `tests/test_core.py`, `test_v12.py`, `test_v13.py`, `test_v14.py` e
  `test_v15.py`: suíte de testes e regressões acumuladas.
- `relatorios/` e `historico.json`: saídas locais; preserve dados existentes.

## Comandos existentes

Execute os comandos abaixo no CMD, na raiz do repositório, com Python instalado.

### Instalação no Windows

```cmd
instalar.bat
```

O instalador seleciona `py -3` ou `python`, cria `.venv`, atualiza o pip, instala
`requirements.txt` e baixa o Chromium do Playwright. As dependências declaradas
atualmente são `Flask>=3.0,<4` e `playwright>=1.55,<2`.

### Execução no Windows

```cmd
INICIAR_AMBIDIFF.bat
```

O script executa `.venv\Scripts\python.exe web\server.py`. O painel escuta em
`127.0.0.1:8765` por padrão; `AMBIDIFF_PORT` permite alterar a porta.

### Testes existentes

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Em Linux, com um ambiente virtual já preparado, o comando equivalente é:

```bash
python -m unittest discover -s tests -v
```

Use o interpretador do ambiente virtual correspondente. Alguns testes de
navegador usam explicitamente `/usr/bin/chromium` e podem ser ignorados quando
esse executável não estiver disponível, inclusive no Windows. Uma suíte com
testes ignorados não comprova a execução dessas verificações. Testes simulados
não comprovam o comportamento de portais reais nem sua disponibilidade de rede.
