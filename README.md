<div align="center">

  <h1>AmbiDiff</h1>
  <p><strong>Compare ambientes web com mais contexto e menos falsos positivos.</strong></p>
  <p>Uma ferramenta <strong>local para Windows</strong> que analisa páginas, navegação, menus, serviços e referências entre ambientes, preservando evidências para revisão humana.</p>
  <p><strong>PRD · DES · LAB · HOMOL</strong> &nbsp;|&nbsp; <strong>Somente leitura</strong> &nbsp;|&nbsp; <strong>Relatórios locais</strong></p>
  <p><a href="#comece-em-5-minutos">Instalação</a> · <a href="#sua-primeira-comparação">Primeira comparação</a> · <a href="#como-interpretar-o-resultado">Como ler o resultado</a> · <a href="docs/guia-de-uso.md">Guia completo</a></p>

</div>

---

## O que o AmbiDiff faz?

O AmbiDiff percorre páginas públicas ou autorizadas de **dois ambientes** e procura diferenças que merecem investigação. Ele ajuda a identificar problemas de interface, navegação e conteúdo sem presumir que o ambiente de produção (PRD) esteja sempre correto.

| Analisa | Considera ao interpretar |
|---|---|
| Menus, opções e caminhos de navegação | Um elemento pode ser equivalente mesmo com HTML ou posição diferentes. |
| Serviços, textos, links e referências | Destinos diferentes nem sempre significam um link quebrado; é preciso revisar. |
| Notícias e conteúdo editorial | Bases desatualizadas podem explicar diferenças de dados, mas não justificam omissões estruturais. |
| Documentos vinculados e recursos | Verifica referências e respostas permitidas, **não compara o conteúdo interno de PDFs**. |
| Falhas, interrupções e cobertura | Uma página inconclusiva ou não examinada **não é considerada equivalente**. |

> **O resultado é uma triagem de QA, não um veredito automático.** Cada divergência relevante precisa de revisão. O AmbiDiff não modifica os sites analisados.

## Comece em 5 minutos

**Você precisa de:** Windows, Python 3 e permissão para instalar dependências e acessar os ambientes de teste. O projeto usa **Flask + Playwright (Chromium)** e não possui instalador `.exe`.

1. Na página do repositório, use **Code → Download ZIP** da branch `main` (ou receba o pacote por canal interno autorizado).
2. Extraia o ZIP para uma pasta própria, fora do arquivo compactado.
3. Execute **`instalar.bat`** uma vez. Ele cria `.venv`, instala as dependências e o Chromium.
4. Execute **`INICIAR_AMBIDIFF.bat`**. Mantenha a janela do terminal aberta durante o uso.
5. Acesse **http://127.0.0.1:8765** se o painel não abrir automaticamente.

```text
AmbiDiff/
├── instalar.bat             ← primeira instalação
├── INICIAR_AMBIDIFF.bat    ← iniciar o programa
└── ...
```

Em redes corporativas, a instalação ou o acesso ao DES/LAB/HOMOL pode depender de permissões, DNS ou VPN. **Não contorne bloqueios de segurança.** Veja o [guia de instalação e solução de problemas](docs/guia-de-uso.md).

## Sua primeira comparação

1. Abra **Comparar ambientes**.
2. Em **Ambiente A**, escolha PRD, DES ou LAB; em **Ambiente B**, escolha DES, LAB ou **HOMOL (Homologação)**. Informe as duas URLs autorizadas.
3. Em **Condição das bases (opcional)**, informe uma base desatualizada somente se houver confirmação. O AmbiDiff já separa diferenças editoriais por contexto mesmo sem essa declaração, **sem esconder problemas de menu ou navegação**.
4. Clique em **Iniciar varredura**. O Chromium trabalha **oculto**; acompanhe o progresso e o diagnóstico no painel.
5. Ao finalizar, revise as **Divergências**, classifique os achados e exporte os registros que interessam.

### Como a varredura funciona

| Regra | Comportamento |
|---|---|
| **Até 1.000 pares HTML** | Atingido o teto, não admite novos pares; conclui ou registra falha nos já admitidos. |
| **Prioridade inteligente** | Menus → serviços → notícias → legislação → institucionais → históricos. |
| **Arquivos e documentos** | Seguem verificações específicas e não consomem as vagas de páginas HTML. |
| **Sem tempo máximo global** | **1h30 é meta de desempenho**, não interrupção obrigatória. |
| **Parada e retomada** | Preserva resultados parciais e tenta manter checkpoints recuperáveis. |

As opções de verificações adicionais, como destinos externos e cliques internos, ficam desativadas por padrão e só devem ser usadas quando autorizadas.

## Como interpretar o resultado

| O que aparece | Como tratar |
|---|---|
| **Divergência** | Diferença encontrada; verifique o impacto e as evidências antes de confirmar. |
| **Variação editorial** | Notícias, datas e banners identificados por contexto podem ser agrupados mesmo quando nenhuma base foi declarada desatualizada. |
| **Inconclusivo / sem correspondência** | A ferramenta não reuniu evidência suficiente para concluir. |
| **Aviso ou falha técnica** | Pode indicar bloqueio, indisponibilidade, timeout ou falha da automação. |

**Atenção ao progresso:** 100% dos pares admitidos encerrados **não significa** que todas as páginas do portal foram analisadas nem que todas as comparações deram certo. Consulte sempre a cobertura, os pares falhos e o diagnóstico.

### Relatórios e evidências

- **CSV:** abrir e filtrar em planilhas.
- **HTML:** revisar divergências e imagens disponíveis.
- **PDF:** compartilhar uma apresentação legível dos resultados.
- **JSON:** dados estruturados, inclusive para análises posteriores.
- **Diagnóstico JSON e log TXT:** entender falhas, limitações e possíveis causas da execução.

Você pode **selecionar DIVs**, reclassificar relevância e confirmar manualmente achados sem alterar o relatório bruto. O histórico, as seleções e as evidências ficam **no computador local**. Confira o [guia de relatórios, recuperação e atualização](docs/guia-de-uso.md).

## Análise inteligente de divergências (opcional)

O **AmbiDiff IA** é um assistente complementar e **independente** da varredura. Ele ajuda a interpretar divergências a partir de **relatórios JSON exportados** e, quando disponíveis, diagnósticos e capturas de tela.

- Identifica achados com maior impacto em menus, navegação e serviços.
- Diferencia possíveis problemas estruturais, funcionais, editoriais e falsos positivos.
- Organiza prioridades e gera um resumo executivo com diagnóstico técnico.

A análise é **manual e opcional**: não há envio automático de dados pelo AmbiDiff. Antes de utilizar a IA, verifique se os arquivos contêm **somente informações públicas e sanitizadas**. As conclusões são recomendações que exigem **validação humana**.

O acesso ao assistente é destinado a colegas autorizados e depende da disponibilidade e das permissões da ferramenta; não é necessário para utilizar o AmbiDiff.

### Como instalar o AmbiDiff IA no ChatGPT

O assistente é um **plugin opcional do ChatGPT**, não um componente instalado no Windows junto com o AmbiDiff.

1. Tenha uma conta ChatGPT com acesso ao recurso **Plugins**. Solicite ao responsável pelo AmbiDiff IA o compartilhamento com seu usuário ou equipe.
2. No ChatGPT, abra **Plugins** (ou **Personalizar → Plugins**, conforme a interface), procure **AmbiDiff IA** na seção de plugins compartilhados e selecione **Instalar (+)**. A disponibilidade depende das permissões da conta e do ambiente.
3. Inicie uma **nova conversa**, digite **@AmbiDiff IA** e selecione o plugin.
4. Anexe os **JSONs exportados** pelo AmbiDiff e, se disponíveis, o **diagnóstico completo e as imagens**. Peça, por exemplo: *“Priorize as divergências, preserve os IDs e separe fatos, hipóteses e verificações necessárias.”*

Se o plugin não aparecer no catálogo ou na busca por `@`, confirme com o responsável se o compartilhamento foi habilitado e se sua conta tem permissão de instalar plugins. **Não é necessário instalar ou executar o arquivo `plugin.zip` no computador**: o ZIP é um pacote usado pelo mantenedor para configurar ou atualizar o plugin.

Antes de anexar relatórios, confirme que eles contêm **somente dados públicos verificados e sanitizados**. O uso do assistente não substitui a revisão humana.

## Limitações importantes

- Não determina qual ambiente está correto, nem garante igualdade visual pixel a pixel.
- Não executa testes completos de formulários, APIs ou todos os componentes dinâmicos.
- Não lê o conteúdo dos PDFs/documentos: analisa referências e verificações permitidas.
- Bloqueios de rede, login ou certificado podem impedir a coleta; **não são corrigidos automaticamente**.
- Tempos e ganhos observados em benchmarks sintéticos **não garantem desempenho em portais reais**.

## Quando algo não funciona

| Sintoma | Primeiro passo |
|---|---|
| Não inicia | Rode `instalar.bat` e confira o Python (`py -3 --version`). |
| `127.0.0.1:8765` não abre | Verifique se `INICIAR_AMBIDIFF.bat` continua aberto e se a porta está livre. |
| **Failed to fetch** no painel | Verifique `/api/status` no endereço local e o terminal; não presuma falha do portal. |
| Um ambiente não carrega | Confirme URL, rede/VPN, DNS e certificados com a TI. |
| Varredura parcial | Consulte diagnósticos, logs, páginas pendentes e checkpoints. |

O [guia completo](docs/guia-de-uso.md#4-solução-de-problemas) traz um roteiro de diagnóstico para esses casos.

## Documentação

| Quero saber sobre... | Onde ler |
|---|---|
| Instalação, uso, atualização e testes com colegas | [Guia de uso](docs/guia-de-uso.md) |
| Estabilização, Chromium oculto, progresso e HOMOL | [Estabilização da varredura](docs/estabilizacao-varredura.md) |
| Limite de 1.000 pares e gestão dinâmica da fila | [Otimização da fila](docs/otimizacao-fila-dinamica.md) |
| Checkpoints, portais extensos e cobertura | [Portais extensos](docs/atualizacao-portais-extensos.md) |
| Critérios de relevância e falsos positivos | [Filtro de relevância](docs/filtro-relevancia.md) |
| Histórico de decisões, testes e benchmarks | [Documentação técnica](docs/varredura-inteligente.md) · [Otimização](docs/otimizacao-varredura.md) · [Melhorias 13–17](docs/atualizacao-13-17.md) |

### Para quem desenvolve

Os testes automatizados locais utilizam o framework `unittest`:

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

O código é organizado em `ambidiff/` (comparação), `web/` (painel e API), `tests/` (regressão) e `scripts/` (benchmarks). Testes simulados **não substituem validação nos ambientes reais**.

---

<div align="center">

  <p><strong>AmbiDiff é uma ferramenta de apoio à revisão humana.</strong></p>
  <p>Use apenas em ambientes autorizados. Não compartilhe logs, capturas ou relatórios internos sem verificar e sanitizar o conteúdo.</p>

</div>
