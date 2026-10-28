# Guia de uso do AmbiDiff

**Instalação, operação, relatórios e solução de problemas no Windows.** Este guia complementa o [README](../README.md); a arquitetura, os benchmarks e as decisões técnicas estão nos demais arquivos de `docs/`.

## 1. Instalação no Windows

### Pré-requisitos

- Windows com permissão para executar arquivos `.bat` e instalar ferramentas de desenvolvimento.
- **Python 3** disponível por `py -3` ou `python` no Prompt de Comando (CMD).
- Acesso autorizado para instalar dependências de `requirements.txt` e baixar o Chromium do Playwright.
- Acesso aos portais pela rede/VPN corporativa, quando necessário.

Confira o Python no CMD:

```cmd
py -3 --version
```

Se esse comando não funcionar, tente `python --version`. Se nenhum funcionar, consulte a TI para instalar/configurar o Python.

### Passo a passo

1. Baixe o ZIP do código da branch **`main`** no repositório privado, ou receba o pacote por canal interno autorizado.
2. Extraia em uma pasta própria, por exemplo `Documentos\AmbiDiff`. Não execute diretamente do ZIP e não misture arquivos de instalações diferentes.
3. Execute `instalar.bat` e aguarde **"Instalacao concluida!"**. O script cria `.venv`, instala Flask/Playwright e baixa o Chromium.
4. Execute `INICIAR_AMBIDIFF.bat`. Mantenha o terminal aberto durante a utilização.
5. Acesse `http://127.0.0.1:8765` no mesmo computador se o navegador não abrir automaticamente.

`127.0.0.1` é o endereço **local**. Cada colega precisa instalar o AmbiDiff no próprio computador: **não copie a `.venv` entre máquinas**. O programa não oferece um instalador `.exe` nem deve ser publicado na rede.

## 2. Configurar e executar uma comparação

No painel, abra **Comparar ambientes**:

1. Escolha o tipo e cole a URL completa do **Ambiente A** (PRD, DES ou LAB).
2. Escolha o tipo e cole a URL do **Ambiente B** (DES, LAB ou HOMOL). Evite selecionar o mesmo ambiente em ambos os lados. Relatórios antigos continuam legíveis.
3. Se uma base estiver **comprovadamente desatualizada**, informe qual. Isso ajuda a separar notícias, datas e outros conteúdos editoriais, mas **não oculta diferenças estruturais**.
4. Mantenha as verificações avançadas desativadas, exceto quando houver autorização específica para testar destinos externos ou cliques internos seguros.
5. Clique em **Iniciar varredura**. O Chromium opera oculto. O nome do portal é identificado automaticamente.

### O que acontece durante a varredura

- São admitidos até **1.000 pares HTML**, com prioridade para menus e serviços, seguida por notícias, legislação, institucionais e históricos.
- No teto, a descoberta de novos pares para; **os pares admitidos continuam** até serem comparados ou receberem um estado de falha.
- PDFs e outros arquivos têm verificação separada e não consomem as 1.000 vagas HTML. O conteúdo interno dos arquivos não é comparado.
- Não existe parada global obrigatória após 1h30. Esse valor é apenas **meta de desempenho**; timeouts individuais e salvaguardas de recursos continuam ativos.
- O percentual indica pares **admitidos com estado final** — inclusive falhas — e não o percentual do site inteiro inspecionado.

Em **Diagnóstico e log da execução**, acompanhe erros, pendências, admissões e recuperação de recursos. Uma execução com 100% de itens encerrados pode ainda ser **parcial em cobertura**.

### Interrupção e retomada

Use **Interromper** uma vez e aguarde a parada cooperativa da operação atual. Resultados parciais e checkpoints são preservados quando possível. Em **Consultar checkpoints → Retomar**, confira os ambientes e as opções antes de continuar.

A retomada cria outra execução vinculada, preservando histórico e seleções anteriores quando o checkpoint é válido. Uma queda abrupta pode perder o trabalho posterior ao último checkpoint; um checkpoint inválido continua útil para diagnóstico, mas não garante retomada.

## 3. Revisar divergências e exportar

Após a execução, abra **Divergências**. Separe:

| Categoria | Como interpretar |
|---|---|
| Divergência detectada | Evidência de diferença que ainda exige avaliação de impacto. |
| Variação editorial | Pode ser consequência de bases em datas diferentes. |
| Inconclusivo / sem correspondência | Falta de informação ou acesso; não representa equivalência. |
| Falha da automação / aviso técnico | Timeout, bloqueio, navegação ou extração incompleta. |

- Busque pelo ID `DIV-xxxx`, pesquise elementos e examine as evidências disponíveis.
- Use **Confirmar DIV** somente após revisão humana. A classificação pode ser ajustada entre automática, relevante, baixa relevância, editorial e inconclusivo.
- Marque **Exportar** nas DIVs desejadas; essa seleção é **independente** da confirmação.
- Escolha o escopo (**completo**, **principal**, **relevantes** ou **somente selecionadas**) e o formato **CSV, HTML, PDF ou JSON**. Depois clique **Baixar relatório**; alterar o seletor sozinho não faz o download.
- Em **Diagnósticos técnicos**, obtenha separadamente **JSON da execução** e **log TXT**.

O histórico e os dados são salvos localmente. A pasta `relatorios/` pode conter `comparacao_<id>.json`, `detalhes_<id>.json`, diagnósticos, capturas, logs e checkpoints. Nem toda DIV terá imagem; falhas e limites são registrados no relatório. Ao transferir uma execução, preserve também seus arquivos auxiliares.

**Atenção:** PRD não é automaticamente correto. A opção **ÁUDIOS** da CGE é um exemplo histórico de diferença de menu que deve continuar sendo detectada mesmo quando há defasagem editorial.

## 4. Solução de problemas

| Sintoma | O que conferir primeiro |
|---|---|
| Python não encontrado no `instalar.bat` | `py -3 --version` ou `python --version`; instale/configure pelo canal aprovado pela TI. |
| Falha no download das bibliotecas ou Chromium | Proxy corporativo, internet, permissões e mensagem do instalador; não desative proteções. |
| Iniciador informa que falta instalação | Execute `instalar.bat` **na mesma pasta**. |
| Painel não abre em `127.0.0.1:8765` | Terminal ainda aberto, mensagem de erro, porta já ocupada por outra instância. |
| DES/LAB/HOMOL não carrega | URL, DNS, VPN autorizada, acesso e certificado com a TI. |
| Varredura parcial ou interrompida | Motivo da parada, páginas pendentes, diagnóstico, logs e checkpoints. |
| Relatório antigo aparece sem imagens/detalhes | Preserve `relatorios/`, `historico.json` e os arquivos auxiliares de cada execução. |

### Se aparecer **Failed to fetch** ao iniciar

Esse aviso significa que o navegador não obteve resposta válida da **API local**. **Não prova** indisponibilidade do portal comparado.

1. Não clique repetidamente em **Iniciar**. Confirme se a janela do `INICIAR_AMBIDIFF.bat` está aberta e sem erro.
2. No mesmo PC, abra `http://127.0.0.1:8765/api/status`. Se não responder, examine servidor e porta. Se retornar JSON, confira `status` e o diagnóstico.
3. Se necessário, pressione **F12 → Rede (Network)**, inicie uma vez e examine `POST /api/comparar`:
   - **200:** início aceito pela API; falhas posteriores aparecem no status/log.
   - **400:** parâmetros ou URLs inválidos.
   - **409:** já há uma comparação em andamento.
   - **500:** erro no servidor; examine o terminal.
   - **failed/canceled:** conexão local interrompida ou bloqueada.
4. Se o servidor ainda responder após uma atualização do código, experimente **Ctrl+F5** no navegador para recarregar os arquivos do painel.
5. Ao solicitar suporte, anote **versão/commit, etapa, mensagem, horário e código HTTP**, sem compartilhar credenciais, tokens ou dados pessoais.

Os arquivos `execucao_<id>.log`, `diagnostico_<id>.json` e `log_<id>.txt` ficam em `relatorios/` quando gerados. Falhas anteriores à criação de uma execução podem não produzir todos eles.

## 5. Atualizar sem perder o histórico

1. **Feche o AmbiDiff** e preserve a instalação antiga como cópia de segurança.
2. Extraia o novo código em **outra pasta** e execute `instalar.bat` novamente; não reaproveite a `.venv` anterior.
3. Se precisar do histórico, copie **`historico.json` e a pasta `relatorios/` completa** da instalação antiga para a nova, com o programa fechado.
4. Inicie a nova instalação e confira o histórico. Relatórios antigos mantêm os dados e a cobertura originais: atualizações não os reprocessam retroativamente.

Não distribua histórico ou relatórios para colegas sem autorização: podem conter capturas, URLs e dados dos portais.

## 6. Testes com colegas autorizados

- Compartilhe um **ZIP da branch `main`** por canal interno aprovado, sem incluir `.venv`, credenciais, `.env`, sessões de navegador, capturas ou relatórios locais.
- Cada colega instala e executa no próprio Windows e inicia com **um escopo pequeno** antes de varreduras extensas.
- Para reportar um achado, registre **versão/commit, portal/ambientes, ID da DIV, página/seção, tipo da diferença, impacto, evidência permitida e estado da execução** (completa/parcial).
- Classifique separadamente defeitos confirmados, diferenças editoriais, falsos positivos e falhas da automação.
- Não compartilhe arquivos brutos com dados internos, pessoais ou sensíveis; use evidências públicas sanitizadas.

### Limitações para quem está validando

O AmbiDiff não comprova equivalência visual por pixels, funcionamento integral de formulários, conteúdo de PDFs, ortografia, consultas protegidas por login ou scripts não inspecionados. Respostas HEAD bloqueadas são inconclusivas. Confira [filtro de relevância](filtro-relevancia.md), [limites de portais extensos](atualizacao-portais-extensos.md) e [estabilização da varredura](estabilizacao-varredura.md).

---

[← Voltar ao README](../README.md)
