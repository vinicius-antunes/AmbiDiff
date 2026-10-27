# AmbiDiff v1.5 — Comparador local de ambientes web

**PRD × DES/LAB**, com comparação pareada, evidências e exportação local. Funciona no **Windows**, com Python + Playwright Chromium + painel Flask escuro. O programa lê páginas autorizadas sem editar sites.

> **Estado do desenvolvimento:** as melhorias **13 a 17** integram esta entrega da branch `perf/otimizacao-varredura`, sobre `b71d90f`, com commit e envio autorizados pelo mantenedor. Não há merge na `main`, deploy ou GitHub Pages. Leia [diagnóstico, testes e benchmarks desta rodada](docs/atualizacao-13-17.md). A [entrega das 12 melhorias](docs/atualizacao-12-melhorias.md) permanece como referência histórica.

## Visão geral

O AmbiDiff é uma ferramenta **local de apoio a QA**: recebe as URLs de dois ambientes autorizados, percorre páginas e compara elementos de interface, estrutura, textos, menus, opções e destinos de links. O resultado é um relatório com divergências, evidências e limitações de cobertura — **não um veredito automático de qual ambiente está correto**.

| Recurso | Para que serve |
|---|---|
| Comparação PRD × DES/LAB | Detectar diferenças nos dois sentidos entre ambientes autorizados |
| Varredura inteligente (padrão) | Até 1.000 pares HTML, fila dinâmica e continuação automática, sem prazo global; arquivos fora do teto |
| Base desatualizada | Separar possíveis diferenças editoriais sem ocultar problemas de navegação ou estrutura |
| Documentos e links | Conferir referências e, conforme as opções, respostas HTTP HEAD; **não lê o corpo de PDFs ou arquivos** |
| Progresso e checkpoints | Acompanhar pares visitados/comparados, interromper e retomar a fila quando houver checkpoint válido |
| Relatórios e revisão | Pesquisar DIVs, confirmar/reclassificar, selecionar independentemente para CSV/HTML/PDF/JSON e baixar diagnósticos |

**Leitura recomendada:** [Instalação no Windows](#instalação-no-windows-primeira-utilização) · [Primeira comparação](#primeira-comparação-passo-a-passo) · [Solução de problemas](#solução-de-problemas-no-windows) · [Arquivos e relatórios](#exportações-e-histórico) · [Atualização para portais extensos](docs/atualizacao-portais-extensos.md).

## Instalação no Windows (primeira utilização)

Este projeto é executado com **Python + Flask + Playwright (Chromium)**. **Não há instalador `.exe`:** os dois arquivos `.bat` na raiz do projeto cuidam da instalação e da inicialização.

### Antes de começar

- Utilize **Windows**, em um computador onde a instalação e a execução de ferramentas de desenvolvimento sejam autorizadas.
- Instale o **Python 3** (caso ainda não esteja disponível). O script procura `py -3` e, se não encontrar, tenta `python`.
- Tenha acesso permitido à instalação das dependências e ao download do Chromium do Playwright. Em rede corporativa, consulte a TI se essas operações forem bloqueadas.
- Confirme o acesso às URLs dos portais pelo navegador ou pela rede/VPN autorizada. Ter internet não garante acesso ao DES/LAB.
- Use **uma instalação separada por computador**. Não copie a pasta `.venv` de outro PC.

Para conferir o Python, abra o **Prompt de Comando (CMD)** e execute:

```cmd
py -3 --version
```

Caso o comando não exista, tente:

```cmd
python --version
```

Se nenhum funcionar, instale/configure o Python pelo canal aprovado pela TI e abra um novo terminal.

### Passo a passo

1. **Obtenha a versão correta.** No repositório privado, escolha a branch `perf/otimizacao-varredura` e utilize **Code → Download ZIP**, ou receba o pacote por canal interno autorizado. Confira a branch/versão: um ZIP da `main` ou uma cópia antiga pode ter outro comportamento.
2. **Extraia todo o ZIP** para uma pasta própria, por exemplo `Documentos\AmbiDiff-Teste`. Não execute o projeto diretamente do arquivo compactado. Mantenha instalações antigas em pastas separadas.
3. **Execute `instalar.bat`** na pasta extraída. Ele cria a `.venv`, instala as bibliotecas de `requirements.txt` e baixa o Chromium usado pelo Playwright. Aguarde a mensagem **"Instalacao concluida!"**. Se aparecer erro, mantenha a janela aberta e anote as últimas mensagens.
4. **Execute `INICIAR_AMBIDIFF.bat`** na mesma pasta. Ele utiliza o Python da `.venv` e inicia o servidor local. **Não feche a janela preta** enquanto estiver usando o AmbiDiff.
5. **Abra o painel** em `http://127.0.0.1:8765` se o navegador não abrir automaticamente. O endereço `127.0.0.1` aponta para **o computador em que o programa está rodando**, não para o PC de outro colega.
6. **Faça primeiro uma comparação pequena** entre duas URLs autorizadas, usando [o roteiro abaixo](#primeira-comparação-passo-a-passo). Depois, amplie o escopo conforme a autorização do setor.

**Se preferir iniciar pelo CMD**, abra o terminal na pasta extraída e execute `instalar.bat` (somente na instalação) e depois `INICIAR_AMBIDIFF.bat`. Em outro computador, repita a instalação localmente.

> **Rede e privacidade:** o servidor Flask usa `127.0.0.1` por padrão e não deve ser publicado na rede. O AmbiDiff não fornece acesso a portais restritos, não contorna certificados, VPN ou login e não deve ser executado em sites não autorizados.

## Primeira comparação: passo a passo

1. No painel, abra **Comparar ambientes**. O nome do portal é identificado automaticamente por metadados, título inicial ou domínio; não há campo de nome no formulário.
2. Em **Ambiente A** e **Ambiente B**, selecione PRD/DES/LAB conforme o caso e cole as URLs completas (`https://...`). Não use o mesmo ambiente nos dois campos.
3. Se houver informação **confirmada** de que uma base está desatualizada, marque o ambiente correspondente. Isso modifica a classificação de possíveis conteúdos editoriais; não prova que uma diferença está correta.
4. A **varredura inteligente** está sempre ativa: admite até **1.000 pares HTML únicos**, organiza as prioridades e continua até dar um resultado a todos os pares admitidos, sem prazo global. O teto não é configurável na tela. **Opções avançadas** conserva apenas destinos externos e cliques internos, desmarcados; habilite-os somente quando autorizados.
5. Clique **Iniciar varredura**. Observe o terminal, o tempo decorrido e os contadores **descobertos / visitados / comparados / pendentes**. O percentual representa apenas a **fila conhecida**, que pode crescer.
6. Ao terminar, abra **Divergências**. Verifique as diferenças principais e as seções informativas de dados, documentos e avisos técnicos; uma execução parcial não comprova equivalência.
7. Use **Confirmar DIV** somente após sua revisão. O seletor de classificação permite **Automática, Relevante, Baixa relevância, Editorial ou Inconclusivo**. Marcação manual não significa que o site foi testado integralmente.
8. Marque **Exportar** nas DIVs desejadas e escolha **Somente DIVs selecionadas**; a seleção é salva localmente por comparação e não confirma um defeito. Também estão disponíveis **Relatório completo**, **Relatório principal** e **Somente relevantes**. Clique no formato: **CSV** para planilhas, **HTML** para revisão visual, **PDF** para apresentação/arquivo ou **JSON** para dados estruturados. **Mudar o seletor não exporta sozinho.**

**Interrupção e retomada:** use **Interromper** uma vez para solicitar a parada cooperativa; a operação atual precisa devolver o controle. Resultados e fila são preservados. Use **Consultar checkpoints → Retomar** para continuar com outro identificador, mantendo o histórico, as revisões, a seleção e a contagem acumulada de admissões. A execução não pausa por 20 minutos nem por cota editorial. Referências além do teto não são admitidas; a fila já aceita é concluída. Checkpoints anteriores já acima de 1.000 conservam suas admissões, sem criar novas vagas. Timeouts individuais e proteção de memória continuam ativos.

Os estados distinguem execução concluída, parcial, interrompida e falha. Salvar um relatório parcial após uma falha não conclui a varredura nem leva o progresso a 100%. Após duas tentativas fatais no mesmo par, ele permanece identificado como falho e os demais ramos podem ser retomados. Logs de bloqueios são agrupados, sem query/credenciais nos exemplos; restrições que afetam componentes continuam no diagnóstico. Analytics bloqueado isoladamente não comprova defeito.

## Solução de problemas no Windows

| Sintoma | O que conferir primeiro |
|---|---|
| `instalar.bat` informa Python não encontrado | Teste `py -3 --version` e `python --version` no CMD; confirme a instalação/PATH com a TI |
| Falha ao instalar bibliotecas ou Chromium | Leia o erro na janela do instalador; confira acesso permitido à internet, proxy corporativo e permissões. Não desative proteções para forçar a instalação |
| `INICIAR_AMBIDIFF.bat` pede instalação | A pasta `.venv` não existe nessa cópia; execute `instalar.bat` no próprio computador |
| O endereço `127.0.0.1:8765` não abre | Confirme que a janela preta está aberta e sem erro. Feche outra instância do AmbiDiff caso a porta esteja ocupada |
| Painel abre, mas **Iniciar comparação** mostra **Failed to fetch** | Veja os passos de diagnóstico abaixo: normalmente é uma falha de comunicação navegador ↔ servidor, não uma DIV do portal |
| DES/LAB não carrega, mas o painel funciona | Confira URL, DNS, rede/VPN autorizada e certificado com a TI; não presuma falha do AmbiDiff |
| Navegação interrompida ou comparação parcial | Consulte o motivo de parada, as páginas pendentes, o diagnóstico e os logs. Parcial não significa equivalência |
| Histórico ou capturas não aparecem após copiar a pasta | Confirme a cópia de `relatorios/` e `historico.json`; nos relatórios atuais preserve também `detalhes_<id>.json` junto do principal |

### Quando aparece "Failed to fetch" ao iniciar uma comparação

Esse aviso significa que o navegador **não conseguiu obter uma resposta válida da API local**. Não prova, por si só, que o portal PRD ou DES está indisponível.

1. **Não clique várias vezes em Iniciar.** Verifique a janela do `INICIAR_AMBIDIFF.bat` para identificar se o servidor ainda está rodando ou se apareceu um erro.
2. No **mesmo PC**, abra `http://127.0.0.1:8765/api/status` no navegador:
   - Se surgir JSON com `"status": "executando"`, a execução pode ter começado; a interface pode ter perdido a comunicação.
   - Se surgir `"status": "erro"`, consulte o diagnóstico ou as mensagens do terminal.
   - Se o endereço não responder, investigue o servidor, a porta e a instalação.
3. Pressione **F12 → Rede (Network)**, clique uma única vez em **Iniciar comparação** e localize a chamada `POST /api/comparar`. Selecione-a e confira o resultado:
   - **200:** a API aceitou o início da execução; eventuais falhas posteriores aparecem no status/log.
   - **400:** URL ou configuração inválida; leia a resposta.
   - **409:** já existe comparação em andamento.
   - **500:** erro interno do servidor; consulte o terminal.
   - **(failed)/(canceled):** conexão interrompida, bloqueio ou requisição cancelada; verifique se o servidor continua respondendo.
4. Se a API continuar ativa, tente **Ctrl+F5** para atualizar os arquivos do painel. Isso é especialmente útil após substituir uma cópia antiga por outra na mesma porta.
5. Se o problema só acontece em outro computador, compare a **branch/versão**, repita `instalar.bat` naquela instalação e confira as restrições locais. Não use a `.venv` de outro computador.
6. Para relatar o problema, registre **versão/commit, etapa, mensagem do terminal, código HTTP e horário**. Envie somente informações permitidas, **sem credenciais ou dados pessoais**.

**Logs e diagnóstico:** ao iniciar uma execução, o painel pode oferecer **Baixar log completo**. Os arquivos locais em `relatorios/` incluem, quando gerados, `execucao_<id>.log`, `diagnostico_<id>.json` e `log_<id>.txt`. Se a falha ocorrer antes de criar a execução, esses arquivos podem ainda não existir.

### Como atualizar em outro PC sem perder o histórico

1. **Feche o programa** e mantenha a instalação antiga como cópia de segurança.
2. Extraia a versão atualizada em **outra pasta**. Não misture códigos-fonte nem transfira `.venv`.
3. Execute `instalar.bat` na nova pasta e abra o programa uma vez para conferir a instalação.
4. Com o programa fechado, copie da instalação antiga **`historico.json` e a pasta `relatorios/` completa** para a nova, se precisar preservar o histórico. Inclua `comparacao_<id>.json`, `detalhes_<id>.json`, evidências, diagnósticos, checkpoints e demais arquivos existentes; não selecione só o HTML/CSV.
5. Reabra o AmbiDiff e confira o histórico. Relatórios antigos mantêm o formato original e não ganham retroativamente novas verificações.

**Atenção:** histórico, logs, capturas e checkpoints podem conter dados dos portais. Transfira-os somente quando autorizado e por meios aprovados pelo setor/TI.


## Testes internos com colegas do setor

O AmbiDiff pode ser avaliado por colegas em **computadores Windows autorizados**, cada um com sua instalação local. O objetivo é verificar a qualidade das divergências detectadas, encontrar falsos positivos e identificar limitações de execução, antes de qualquer integração definitiva.

### Como distribuir o pacote de testes

1. Um responsável com acesso ao repositório privado abre a branch `perf/otimizacao-varredura`, seleciona **Code → Download ZIP** e confirma que não baixou a `main`.
2. Compartilha o ZIP **somente por canal interno aprovado pelo setor/TI**. Não é necessário tornar o repositório público nem habilitar GitHub Pages.
3. Cada colega extrai o conteúdo em **uma pasta própria**, sem substituir instalações anteriores. Pode renomear a pasta extraída para `AmbiDiff-Teste-Interno`.
4. Antes de distribuir qualquer pasta montada manualmente, **exclua e confira** relatórios, capturas, arquivos auxiliares, `historico.json`, `.env`, credenciais, sessões, perfis de navegador e `.venv`. O ZIP de código gerado pelo GitHub não deve conter arquivos de execução locais ignorados pelo Git; ainda assim, revise os arquivos distribuídos.

**Pré-requisitos:** Python 3 disponível por `py` ou `python`, acesso permitido para instalar dependências do `requirements.txt` e o Chromium do Playwright, e conectividade aos endereços de teste pela rede/VPN autorizada. Se o computador tiver restrições de instalação ou execução de `.bat`, consulte a TI; não tente contornar essas restrições. **Esta branch não fornece um executável `.exe` pronto.**

### Roteiro sugerido para cada colega

1. Execute `instalar.bat` **uma vez** na pasta extraída. Aguarde concluir; a instalação cria a pasta local `.venv`.
2. Execute `INICIAR_AMBIDIFF.bat` para abrir o painel em `http://127.0.0.1:8765`. Caso a porta esteja ocupada, feche outra instância do programa antes de iniciar.
3. Informe **dois endereços autorizados** (PRD e DES/LAB), com seus respectivos nomes. Se a base de algum ambiente estiver desatualizada, marque essa condição no formulário.
4. Faça primeiro uma comparação pequena, observando páginas iniciais, menus, avisos institucionais, links e documentos. Depois, se autorizado, amplie o escopo.
5. Registre cobertura, admissões HTML, duração, divergências relevantes e resultados inconclusivos. Compare somente medições com escopo e condições equivalentes; não use apenas a quantidade de DIVs.
6. Revise os alertas, utilize **Mostrar todas as diferenças** e, quando pertinente, **Confirme DIV** ou reclassifique a relevância. Uma classificação automática nunca substitui a conferência manual.
7. Registre os achados no formulário/planilha definido pelo setor, com os dados mínimos abaixo.

| Campo do registro | Exemplo do que informar |
|---|---|
| Versão usada | Branch `perf/otimizacao-varredura` e commit, se conhecido |
| Ambientes | Identificação do portal, PRD e DES/LAB (sem credenciais) |
| Configuração | Varredura inteligente; admissões HTML, opções autorizadas e base desatualizada, se aplicável |
| Localização | Caminho da página, seção e elemento afetado |
| Resultado observado | Divergência correta, possível falso positivo, diferença editorial ou falha da automação |
| Evidência e impacto | Descrição breve, horário, ID da DIV (se houver) e imagem **sem dados sensíveis** |
| Execução | Se foi completa ou parcial, tempo aproximado e mensagens de erro relevantes |

**Não compartilhe relatórios brutos, capturas internas, credenciais ou dados pessoais sem autorização.** Em caso de dúvida, envie apenas uma descrição anonimizada do problema. Evite realizar várias varreduras extensas simultâneas que possam sobrecarregar os portais.

### Limites conhecidos desta versão de testes

- O filtro de relevância prioriza itens institucionais e reduz diferenças estritamente técnicas de SVG, sem comprovar que os ícones são visualmente idênticos.
- Widgets recebem tratamento genérico de relevância e estabilidade. A **DIV-0028 (Messenger) da SEFAZ real** ainda exige validação manual; decoração isolada não comprova equivalência funcional.
- Documentos e destinos externos recebem somente conferência de referências/HEAD, sem corpo, PDF ou hash. HEAD bloqueado ou não suportado é inconclusivo.
- A otimização pode reduzir inspeções profundas de certas páginas editoriais estáticas, com a cobertura omitida declarada no relatório.
- As branches específicas USEIA/CGE não foram incorporadas. Esta atualização implementa independentemente cursor de logs, progresso e interrupção; a futura integração desses PRs requer revisão de conflitos.
- Os testes automatizados disponíveis foram executados em ambiente de desenvolvimento; **não há validação concluída nos portais reais do setor ou no Windows de todos os colegas**.

**Critério de sucesso:** identificar diferenças relevantes sem ocultar problemas estruturais ou funcionais, registrar corretamente limites e falhas e preservar resultados parciais. PRD não é considerado automaticamente correto.



## Novidades v1.5

### 1. Bases desatualizadas — controle explícito

No formulário **Atualização das bases de dados**, selecione:

- **Bases equivalentes / não informado**: não separa conteúdo editorial automaticamente (modo padrão).
- **Ambiente A está desatualizado** ou **Ambiente B está desatualizado**: separa diferenças reconhecidas como publicações/notícias para **Variações de dados / bases desatualizadas**. A configuração é lembrada por domínio no navegador deste computador.

O programa tenta reconhecer avisos públicos de desatualização no DOM e mostra-os como **sinais**, sem ativar esse modo por conta própria. Menus, opções de navegação, redirecionamentos e diferenças de estrutura **não** são ocultados só por haver defasagem. Diferenças editoriais **continuam registradas no JSON**, mas agrupadas como informações, e não como DIVs de defeitos.

O reconhecimento editorial é **conservador**: usa contexto de cartões/artigos, URLs de notícia e elementos que o HTML renderizado oferece. Se a página não fornecer indícios suficientes, a DIV permanece na lista principal para revisão. Dados alterados por outra causa podem parecer uma defasagem; a ferramenta não presume a causa.

### 2. Menos falso positivo; mesma estrutura em lugar diferente

O comparador já verifica rótulos no conjunto da página e não apenas na posição. A v1.5 melhora o reconhecimento do conteúdo editorial dos cartões, separando datas/títulos/imagens relacionadas quando a base é declarada antiga. Isso **não** suprime diferenças de menu como a opção **ÁUDIOS** da CGE. As referências da imagem de logo do Liferay que diferem apenas no parâmetro de cache `t` não aparecem como mudanças de imagem. Mudanças reais de `img_id` continuam sendo verificadas.

### 3. Correção da varredura de documentos

Rotas `.../documents/d/...` do Liferay podem retornar PDFs mesmo sem a extensão `.pdf`. Agora são classificadas como documentos e não colocadas na fila de páginas HTML. Se uma rota iniciar download inesperadamente, **isso não incrementa o contador de falhas consecutivas**. Downloads e documentos continuam informados nos avisos, sem fingir que o conteúdo do arquivo foi comparado.

### 4. Diagnósticos com possíveis causas

Após cada execução v1.5, na seção **Divergências**, você pode baixar:

- **Diagnóstico JSON**: lista técnica estruturada, URLs, ambiente, eventos de navegação, número do par, falhas conhecidas, possíveis causas, motivo da parada e quantidade de páginas pendentes.
- **Log TXT**: resumo legível e últimas mensagens do terminal, incluindo orientações por erro.

Erros reconhecidos: DNS, certificado TLS, timeout, status HTTP, navegação interrompida, downloads, extração e desconhecido. **Possível causa não é causa comprovada.** Se o programa for interrompido pelo usuário, tenta exportar o que já coletou. Tenta manter *checkpoints* num agendamento único, normalmente a cada 30 segundos e adaptado ao custo até 120 segundos, além de salvamentos no início, encerramento, interrupção e erro fatal. A gravação compacta é atômica e o formato v1 continua legível. Uma queda abrupta ainda pode perder trabalho posterior ao último checkpoint válido. Se ocorrer falha antes do primeiro checkpoint, somente o diagnóstico de exceção poderá estar disponível; não há garantia de recuperação total.

### 5. Revisão manual das DIVs

Cada DIV tem botão **Confirmar DIV**. A escolha é preservada em arquivo auxiliar, sem alterar o relatório bruto original; aparece na interface e nas exportações filtradas. Clique novamente para remover a confirmação. O botão de excluir DIV continua funcionando como antes (oculta da exibição e exportação, mantendo o relatório original).

### 6. Ícones/layout e teste opcional de clique

- Compara marcas **SVG** ou classes de ícones em controles equivalentes dos dois ambientes. Diferenças puramente técnicas/decorativas ficam nas observações, sem DIV isolada; ausência de ícone informativo permanece relevante. Não comprova aparência visual.
- Deslocamentos **muito grandes** de controles equivalentes geram **referências de layout para revisão**. Não é comparação visual por pixels.
- **Testar cliques de navegação internos** é opcional e fica **desmarcado por padrão**: testa no máximo 12 pares de links de consulta/abertura de destinos equivalentes, usando navegador isolado e bloqueando requisições que não sejam GET/HEAD ou que saiam do domínio. O comportamento observado pode ser inconclusivo. Evite ativar em sites com links sensíveis, mesmo com a proteção.
- Testar cliques não submete formulários nem interage com sites externos. Controles internos com `aria-controls` reconhecido e disclosures seguros podem ser observados; botões arbitrários, autenticação e ações de escrita não são executados.

## Como interpretar o relatório

| Área | Significado |
|---|---|
| **Divergências** | Diferenças entre elementos coletados nos dois ambientes (exigem validação). |
| **Variações de dados** | Possíveis diferenças editoriais por atualização, agrupadas quando a defasagem foi confirmada pelo usuário. |
| **Sinais de desatualização** | Avisos localizados no DOM, sem conclusão automática. |
| **Referências diferentes** | Diferenças de URLs, imagens ou layout sem prova de defeito visual. |
| **Avisos técnicos** | Falhas de carregamento, arquivos ignorados e coleta parcial. |
| **Páginas sem correspondência** | Não puderam ser comparadas; não provam ausência de conteúdo. |
| **Diagnóstico JSON/TXT** | Causas prováveis, URL, par, erros e situação da execução. |

**Importante:** `Varredura parcial` significa cobertura insuficiente. Mesmo se nenhuma DIV aparecer, não se deve declarar os ambientes equivalentes. A ferramenta também **não determina** qual ambiente está correto.

## Exportações e histórico

A pasta `relatorios` contém `comparacao_<id>.json`, `.html` e `.csv`, `diagnostico_<id>.json`, `log_<id>.txt` e a pasta de `evidencias_<id>/` quando disponíveis. As capturas são limitadas por duração e quantidade; alguns elementos não possuem evidência por timeout ou limitação de navegação.

`selecoes_<id>.json` guarda a seleção de exportação separada das revisões, exclusões e do relatório bruto. Excluídos não entram na seleção exportada. Checkpoints e relatórios antigos continuam legíveis; nomes e caminhos internos não mudaram. Uma recuperação adicional preserva o bruto existente e usa `recuperacao_<id>.json` quando necessário.

Os downloads usam nomes como `SEFAZ_DIVs_Selecionadas_2026-10-23_abcdef.csv`, sanitizados para Windows. Chrome/Edge compatível pode abrir **Salvar como**, sugerindo a última pasta quando permitido; há confirmação antes de substituir um arquivo com dados. Sem essa API, vale o download normal do navegador. Ative **Perguntar onde salvar cada arquivo** para escolher o local no fallback. Não há garantia de pasta persistente entre navegadores ou sessões.

HTML incorpora PNGs locais com limite de **3 MB por captura e 20 MB por exportação**, indicando evidências ausentes ou excedentes. PDF é gerado localmente com Chromium, sem serviço externo, com orçamento de 60 s. Downloads usam arquivos temporários isolados; não substituem os originais. CSV conserva UTF-8 com BOM, `;` e proteção contra fórmulas. Diagnósticos JSON/TXT continuam disponíveis separadamente.

**Seleção em massa:** use **Marcar todas do relatório**, **Marcar apenas as filtradas** ou **Desmarcar todas**. A operação inclui itens ainda não renderizados, trata membros dos grupos e preserva confirmações e classificações. Marcar filtradas mantém seleções fora dos filtros. A busca por ID conserva a regra da tela: ignora categoria/lado/tipo, mas respeita revisão e visibilidade de baixa relevância. Uma única requisição em lote aplica os filtros no servidor e salva a seleção atomicamente.

Com relatório aberto, os quatro formatos têm foco/hover e feedback próximo dos controles. Sem relatório, a tela explica a indisponibilidade; sem DIV marcada no escopo selecionado, orienta a seleção. Falhas e cancelamentos ficam na própria tela de resultados.

O histórico é agrupado por site. É possível excluir uma execução ou várias, excluir DIVs individuais e confirmar resultados manualmente. Todas essas alterações ficam **somente no seu computador**.

### Migrando relatórios da versão 1.4

**Não misture os códigos-fonte.** Com o programa fechado:

1. Extraia a v1.5 em uma **pasta nova** e instale normalmente.
2. Se quiser manter o histórico antigo, copie o conteúdo da pasta `relatorios` da v1.4 para `relatorios` da v1.5; copie também `historico.json` da pasta antiga para a nova.
3. Inicie a v1.5. Os relatórios antigos são preservados **como foram gerados**; não recebem retroativamente o novo diagnóstico ou classificação editorial. Novas regras valem para novas execuções.

Você também pode manter a v1.4 intacta e começar um histórico separado na v1.5.

## Testes locais

### Fila dinâmica e reconhecimento estático

A estratégia dinâmica e o reconhecimento de equivalências estáticas são o padrão.
Não há seletor de estratégia ou orçamento na interface. A ordem é menus/navegação,
serviços, notícias, legislação, institucional e histórico, com rodízio entre
categorias para evitar inanição. Representantes editoriais são inspecionados
primeiro; as demais páginas admitidas continuam automaticamente. Uma amostra
não conclui outra página. Páginas exclusivas são inspecionadas apenas onde o
link foi encontrado e ficam sem comparação quando não há contraparte comprovada.

Notícias escolhidas para inspeção recebem navegação e coleta. Somente
templates estáticos comprovados por duas amostras profundas, sem scripts ou
marcadores conhecidos de interação/lazy loading, podem dispensar preparação
profunda quando a defasagem tiver sido declarada. Páginas institucionais e
diferenças estruturais não são dispensadas por essa regra. ÁUDIOS exclusivo na
CGE continua sendo divergência.

Metadados semelhantes de documentos não comprovam arquivos idênticos. Inspeções
profundas omitidas e verificações inconclusivas limitam a cobertura. A ausência
de comparação do corpo dos documentos é uma decisão de escopo, não prova de
identidade dos arquivos. O CSV
continua dedicado às divergências; JSON, HTML e diagnósticos incluem as novas
categorias.

Consulte [arquitetura, limites, benchmark e conflitos de integração](docs/varredura-inteligente.md).
Para reproduzir o benchmark com portais sintéticos locais:

```cmd
.venv\Scripts\python.exe scripts\benchmark_smart.py --articles 8 --repetitions 3
```

No CMD dentro da pasta:

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes incluem regressão de links equivalentes, varredura pareada, menu não ocultado por defasagem, classificação de notícia e download do Liferay, ícones de SVG, geração de diagnóstico e marcação manual. Os testes simulados não garantem que os portais PRD/DES reais vão responder da mesma maneira, pois a rede corporativa é variável. Acessibilidade, reprodução pixel a pixel, comportamento integral de scripts, APIs e conteúdo do banco de dados não são verificados completamente.

As regressões desta entrega estão em `tests/test_update12.py`: bloqueios e URLs inválidas, recuperação/retomada, classificação de recursos, seleção persistente, CSV, HTML/PDF com capturas e deduplicação. Resultados e benchmarks contra `f7ba62e` estão na [documentação das 12 melhorias](docs/atualizacao-12-melhorias.md). Ganho de CPU sintética não equivale a redução comprovada do tempo nos portais; não houve validação em produção ou do diálogo nativo no Windows.

## Estrutura

```text
AmbiDiff-v1.5/
├── instalar.bat
├── INICIAR_AMBIDIFF.bat
├── requirements.txt
├── ambidiff/
│   ├── core.py
│   ├── paired.py
│   ├── intelligence.py
│   ├── diagnostics.py
│   ├── visual.py
│   ├── functional.py
│   ├── storage.py
│   └── reports.py
├── web/
│   ├── server.py
│   ├── templates/index.html
│   └── static/app.js, style.css
├── tests/
└── relatorios/
```

Esta ferramenta serve como apoio a QA e não substitui testes manuais dos achados relevantes.

### Indicadores de acompanhamento durante a execução

O painel agora apresenta o **percentual aproximado** do progresso, o **tempo decorrido** e, quando há amostras recentes suficientes, uma **estimativa de tempo restante**. Se a fila crescer, o ritmo ficar instável ou a varredura estiver nas etapas finais, a previsão pode ficar indisponível. O percentual reflete o avanço estimado do percurso e **não** confirma que a cobertura estrutural foi completa. A implementação ainda requer validação funcional no Windows e com portais autorizados.

## Desempenho: meta de reduzir em 50% o tempo da varredura

Registramos um plano técnico de otimização com a medição real da SEFAZ, gargalos possíveis, segurança das verificações, benchmark comparável e inclusão futura dos campos `iniciado_em`, `finalizado_em` e `duracao_segundos` nos JSONs. **A meta ainda não foi validada em portal real**.

Leia [Plano de desempenho — SEFAZ](docs/plano-desempenho-sefaz.md) antes de alterar timeouts, segunda leitura, rolagem ou paralelismo. A redução de tempo não deve ocorrer à custa de omitir divergências institucionais, documentos, falhas ou resultados parciais.

## Filtro de relevância e diferenças SVG

A lista principal prioriza diferenças estruturais, funcionais e institucionais.
Diferenças puramente técnicas/decorativas de SVG ficam nas observações técnicas,
sem DIV isolada e sem presumir equivalência visual. Há reclassificação manual e exportação principal ou
completa. Veja [critérios, formatos e limitações](docs/filtro-relevancia.md).

## Histórico: otimização de preparação e releitura

A branch `perf/otimizacao-varredura` acrescenta preparação por sinais do DOM,
releitura seletiva, tags de evidência, relações entre ocorrências e horários/duração
nos relatórios. O benchmark equivalente entre checkouts mediu redução sintética de
76,78% (estável) e 59,22% (dinâmico), sem omissões profundas ou perda dos achados
inspecionados. Isso não comprova o ganho em portais reais. Consulte
[metodologia, testes e limites](docs/otimizacao-varredura.md) e
[séries completas de medição](docs/benchmark-perf.json).

## Atualização: seções, referências e acompanhamento confiável

Opções ausentes são verificadas na seção correspondente, nos dois sentidos;
referências em outra seção não apagam uma possível diferença de organização.
Vários documentos ausentes formam uma DIV por seção, com todos os membros
preservados. Nomenclatura e valores informativos diferentes continuam visíveis.

Logs usam IDs/cursor, janela de 200 eventos e terminal limitado a 500 linhas,
com aviso de lacuna e arquivo local completo `execucao_<id>.log`. O polling
reconecta sem interromper o backend. O percentual representa a fila conhecida,
e o tempo decorrido independe da ETA. Um clique solicita interrupção cooperativa
e preserva os resultados parciais. Os campos de URL começam vazios.

Consulte [o relatório técnico A–I](docs/proxima-atualizacao.md) para os requisitos
atendidos, limites de HEAD/cliques, comandos, resultados e validação manual.

## Portais extensos, retomada e revisão

A execução admite até **1.000 pares HTML**, incluindo unidades com apenas um
ambiente. PDFs, imagens e recursos auxiliares não usam vagas. Referências ainda
sem tipo conhecido reservam uma vaga conservadora; respostas identificadas como
não HTML liberam-na. A descoberta/admissão para no teto, mas a fila admitida
continua até concluir ou registrar uma falha. Não existe prazo global de execução.
O teto preventivo de memória de 100.000 referências candidatas permanece separado.
A cobertura nunca é apresentada como integral por ter esgotado a fila conhecida.

Use **Consultar checkpoints → Retomar** para continuar uma fila persistida em
nova execução, preservando o relatório anterior e as revisões. Confira os
ambientes e opções mostrados antes de retomar. Checkpoints antigos sem estado
restaurável continuam úteis para diagnóstico, mas não são retomados.

Documentos recebem somente HEAD, com até 10.000 pares e 20.000 pedidos seriais,
cache de observações por URL e horário preservado. Não são lidos PDFs ou corpos.
Bloqueios de segurança aparecem separados das falhas de acesso/automação.
Fragmentos sem função comprovada ficam inconclusivos; âncoras de rolagem
observadas não geram defeitos funcionais.

O formato 2 separa o principal de `detalhes_<id>.json`; preserve ambos ao copiar
a instalação. O diagnóstico completo e a exportação completa mantêm os detalhes.
O painel carrega os dados técnicos sob demanda, pesquisa IDs dentro de grupos,
filtra revisão pendente/confirmada e oferece exportação somente de relevantes.

Confira [arquivos, testes, benchmark, limites e roteiro Windows](docs/atualizacao-portais-extensos.md).

## Melhorias 13 a 17 — histórico da evolução

Consulte [o relatório técnico](docs/atualizacao-13-17.md) para causas confirmadas,
compatibilidade de checkpoints/API, cenários de regressão, resultados controlados
e limitações daquela entrega. A etapa seguinte substitui o orçamento e a pausa
editorial por continuação automática. Tempos sintéticos não garantem desempenho
real, e a amostragem nunca comprova páginas não abertas.

## Nova otimização — fila dinâmica de até 1.000 pares HTML

Consulte [decisões, testes e medições](docs/otimizacao-fila-dinamica.md).
A referência de até 1.000 comparações em cerca de **1h30** orienta o trabalho;
não é prazo de parada nem garantia para qualquer portal. Não houve validação
em produção ou em recursos corporativos. No uso normal, Chromium fica visível,
com contextos isolados e um par por vez. Para testes em Linux sem interface,
use `AMBIDIFF_HEADLESS=1`; essa variável é uma opção interna de teste.
