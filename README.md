# AmbiDiff v1.5 — Comparador local de ambientes web

**PRD × DES/LAB**, com comparação pareada, evidências e exportação local. Funciona no **Windows**, com Python + Playwright Chromium + painel Flask escuro. O programa lê páginas autorizadas sem editar sites.

> **Estado do desenvolvimento:** a branch `main` contém a base v1.5. A branch [`feat/varredura-inteligente`](https://github.com/vinicius-antunes/AmbiDiff/tree/feat/varredura-inteligente) é uma **versão experimental para testes internos**, ainda em revisão no [PR #3](https://github.com/vinicius-antunes/AmbiDiff/pull/3). Ela não inclui automaticamente as correções pendentes dos PRs [#1 (USEIA)](https://github.com/vinicius-antunes/AmbiDiff/pull/1) e [#2 (CGE)](https://github.com/vinicius-antunes/AmbiDiff/pull/2). Nenhuma dessas alterações foi integrada à `main`.

## Testes internos com colegas do setor

O AmbiDiff pode ser avaliado por colegas em **computadores Windows autorizados**, cada um com sua instalação local. O objetivo é verificar a qualidade das divergências detectadas, encontrar falsos positivos e identificar limitações de execução, antes de qualquer integração definitiva.

### Como distribuir o pacote de testes

1. Um responsável com acesso ao repositório privado abre a branch `feat/varredura-inteligente`, seleciona **Code → Download ZIP** e confirma que não baixou a `main`.
2. Compartilha o ZIP **somente por canal interno aprovado pelo setor/TI**. Não é necessário tornar o repositório público nem habilitar GitHub Pages.
3. Cada colega extrai o conteúdo em **uma pasta própria**, sem substituir instalações anteriores. Pode renomear a pasta extraída para `AmbiDiff-Teste-Interno`.
4. Antes de distribuir qualquer pasta montada manualmente, **exclua e confira** relatórios, capturas, arquivos auxiliares, `historico.json`, `.env`, credenciais, sessões, perfis de navegador e `.venv`. O ZIP de código gerado pelo GitHub não deve conter arquivos de execução locais ignorados pelo Git; ainda assim, revise os arquivos distribuídos.

**Pré-requisitos:** Python 3 disponível por `py` ou `python`, acesso permitido para instalar dependências do `requirements.txt` e o Chromium do Playwright, e conectividade aos endereços de teste pela rede/VPN autorizada. Se o computador tiver restrições de instalação ou execução de `.bat`, consulte a TI; não tente contornar essas restrições. **Esta branch não fornece um executável `.exe` pronto.**

### Roteiro sugerido para cada colega

1. Execute `instalar.bat` **uma vez** na pasta extraída. Aguarde concluir; a instalação cria a pasta local `.venv`.
2. Execute `INICIAR_AMBIDIFF.bat` para abrir o painel em `http://127.0.0.1:8765`. Caso a porta esteja ocupada, feche outra instância do programa antes de iniciar.
3. Informe **dois endereços autorizados** (PRD e DES/LAB), com seus respectivos nomes. Se a base de algum ambiente estiver desatualizada, marque essa condição no formulário.
4. Faça primeiro uma comparação pequena, observando páginas iniciais, menus, avisos institucionais, links e documentos. Depois, se autorizado, amplie o escopo.
5. Compare os modos **convencional** e **Varredura inteligente (otimizada)** quando houver tempo. Compare também cobertura, duração, divergências relevantes e resultados inconclusivos.
6. Revise os alertas, utilize **Mostrar todas as diferenças** e, quando pertinente, **Confirme DIV** ou reclassifique a relevância. Uma classificação automática nunca substitui a conferência manual.
7. Registre os achados no formulário/planilha definido pelo setor, com os dados mínimos abaixo.

| Campo do registro | Exemplo do que informar |
|---|---|
| Versão usada | Branch `feat/varredura-inteligente` e commit, se conhecido |
| Ambientes | Identificação do portal, PRD e DES/LAB (sem credenciais) |
| Modo de comparação | Convencional ou inteligente; base desatualizada, se aplicável |
| Localização | Caminho da página, seção e elemento afetado |
| Resultado observado | Divergência correta, possível falso positivo, diferença editorial ou falha da automação |
| Evidência e impacto | Descrição breve, horário, ID da DIV (se houver) e imagem **sem dados sensíveis** |
| Execução | Se foi completa ou parcial, tempo aproximado e mensagens de erro relevantes |

**Não compartilhe relatórios brutos, capturas internas, credenciais ou dados pessoais sem autorização.** Em caso de dúvida, envie apenas uma descrição anonimizada do problema. Evite realizar várias varreduras extensas simultâneas que possam sobrecarregar os portais.

### Limites conhecidos desta versão de testes

- O filtro de relevância prioriza itens institucionais e reduz diferenças estritamente técnicas de SVG, sem comprovar que os ícones são visualmente idênticos.
- A **DIV-0028 (widget Messenger) da SEFAZ** ainda demanda ajuste na regra automática para o formato real dessa ocorrência; não use esse caso como evidência de filtro já validado.
- A verificação rápida de documentos analisa acesso e metadados, **não** a igualdade integral do conteúdo dos arquivos.
- A otimização pode reduzir inspeções profundas de certas páginas editoriais estáticas, com a cobertura omitida declarada no relatório.
- As correções específicas de navegação USEIA e dos logs/interrupção CGE estão em **branches separadas**, ainda não incorporadas.
- Os testes automatizados disponíveis foram executados em ambiente de desenvolvimento; **não há validação concluída nos portais reais do setor ou no Windows de todos os colegas**.

**Critério de sucesso:** identificar diferenças relevantes sem ocultar problemas estruturais ou funcionais, registrar corretamente limites e falhas e preservar resultados parciais. PRD não é considerado automaticamente correto.



## Instalação no Windows (primeira utilização)

1. Extraia **todo** o ZIP da versão escolhida em uma pasta (não rode dentro do ZIP). A versão da branch experimental deve ficar separada da v1.5 anterior.
2. Dentro da pasta extraída, execute **`instalar.bat`**. É preciso Python instalado (com `py` ou `python` no PATH) e internet para instalar o navegador do Playwright. Aguarde o instalador terminar.
3. Execute **`INICIAR_AMBIDIFF.bat`**. O painel abrirá em `http://127.0.0.1:8765`.
4. Escolha os nomes de PRD/DES ou LAB, insira os dois endereços e clique **Iniciar comparação**.

> A ferramenta não deve ser exposta na rede: o servidor escuta apenas em `127.0.0.1`. Para endereços `*.des.mt.gov.br`, o computador precisa ter acesso pela própria rede/VPN autorizada. O programa não burla login ou restrições da rede.

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

Erros reconhecidos: DNS, certificado TLS, timeout, status HTTP, navegação interrompida, downloads, extração e desconhecido. **Possível causa não é causa comprovada.** Se o programa for interrompido pelo usuário, tenta exportar o que já coletou. Mantém *checkpoints* a cada 20 pares comparados para permitir recuperar parte do trabalho após falha inesperada. Se ocorrer falha antes do primeiro checkpoint, somente o diagnóstico de exceção poderá estar disponível; não há garantia de recuperação total.

### 5. Revisão manual das DIVs

Cada DIV tem botão **Confirmar DIV**. A escolha é preservada em arquivo auxiliar, sem alterar o relatório bruto original; aparece na interface e nas exportações filtradas. Clique novamente para remover a confirmação. O botão de excluir DIV continua funcionando como antes (oculta da exibição e exportação, mantendo o relatório original).

### 6. Ícones/layout e teste opcional de clique

- Compara marcas **SVG** ou classes de ícones em controles equivalentes dos dois ambientes. Diferenças geram registros de *ícone para revisão*, não afirmações de aparência visual comprovada.
- Deslocamentos **muito grandes** de controles equivalentes geram **referências de layout para revisão**. Não é comparação visual por pixels.
- **Testar cliques de navegação internos** é opcional e fica **desmarcado por padrão**: testa no máximo 12 pares de links de consulta/abertura de destinos equivalentes, usando navegador isolado e bloqueando requisições que não sejam GET/HEAD ou que saiam do domínio. O comportamento observado pode ser inconclusivo. Evite ativar em sites com links sensíveis, mesmo com a proteção.
- Testar cliques **não** tenta submeter formulários, clicar botões sem links, auditar destinos divergentes nem interagir com sites externos.

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

O histórico é agrupado por site. É possível excluir uma execução ou várias, excluir DIVs individuais e confirmar resultados manualmente. Todas essas alterações ficam **somente no seu computador**.

### Migrando relatórios da versão 1.4

**Não misture os códigos-fonte.** Com o programa fechado:

1. Extraia a v1.5 em uma **pasta nova** e instale normalmente.
2. Se quiser manter o histórico antigo, copie o conteúdo da pasta `relatorios` da v1.4 para `relatorios` da v1.5; copie também `historico.json` da pasta antiga para a nova.
3. Inicie a v1.5. Os relatórios antigos são preservados **como foram gerados**; não recebem retroativamente o novo diagnóstico ou classificação editorial. Novas regras valem para novas execuções.

Você também pode manter a v1.4 intacta e começar um histórico separado na v1.5.

## Testes locais

### Varredura inteligente (opcional)

O formulário permite selecionar **Varredura inteligente (otimizada)**. Desmarcada,
mantém o modo atual. A opção acrescenta evidências de equivalência estática,
reutilização de componentes, checagem rápida de documentos por cabeçalhos e
limitações de cobertura no relatório.

Notícias pareadas continuam recebendo navegação e inspeção estrutural. Somente
templates estáticos comprovados por duas amostras profundas, sem scripts ou
marcadores conhecidos de interação/lazy loading, podem dispensar preparação
profunda quando a defasagem tiver sido declarada. Páginas institucionais e
diferenças estruturais não são dispensadas por essa regra. ÁUDIOS exclusivo na
CGE continua sendo divergência.

Metadados semelhantes de documentos não comprovam arquivos idênticos. Inspeções
profundas omitidas e documentos sem comparação integral limitam a cobertura; o
modo inteligente não os apresenta como varredura totalmente completa. O CSV
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
Diferenças somente técnicas de SVG ficam disponíveis em **Mostrar todas as diferenças**,
sem presumir equivalência visual. Há reclassificação manual e exportação principal ou
completa. Veja [critérios, formatos e limitações](docs/filtro-relevancia.md).
