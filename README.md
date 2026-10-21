# AmbiDiff v1.5 — Comparador local de ambientes web

**PRD × DES/LAB**, com comparação pareada, evidências e exportação local. Funciona no **Windows**, com Python + Playwright Chromium + painel Flask escuro. O programa lê páginas autorizadas sem editar sites.

## Instalação no Windows (primeira utilização)

1. Extraia **todo** o arquivo `AmbiDiff-v1.5.zip` em uma pasta (não rode dentro do ZIP).
2. Dentro da pasta `AmbiDiff-v1.5`, execute **`instalar.bat`**. É preciso Python instalado (com `py` ou `python` no PATH) e internet para instalar o navegador do Playwright. Aguarde o instalador terminar.
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
