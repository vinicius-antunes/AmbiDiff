# Varredura inteligente: arquitetura, cobertura e medição

## Escolha do modo

O formulário oferece **Varredura inteligente (otimizada)**, desmarcada por
padrão. A API aceita `varredura_inteligente: true` em `POST /api/comparar`.
Sem esse campo, permanece o percurso da v1.5. Não há configuração de rotas
equivalentes, alteração do protocolo de logs ou novo mecanismo de interrupção
dos PRs pendentes nesta implementação.

O mecanismo não considera PRD a referência correta. Toda divergência e hipótese
de equivalência é simétrica e exige interpretação no contexto do teste.

## Diagnóstico dos custos

Na implementação original, cada página pareada recebe navegação, rolagem,
estabilização e extração em ambos os ambientes. Isso se repete nas páginas
editoriais com o mesmo template. Há ainda releitura em bloco, comparação de
opções e possíveis cliques/capturas/auditoria opcionais. Esperas são necessárias
para conteúdo dinâmico; removê-las globalmente produziria falsos negativos.

As medições agora separam navegação, preparação/rolagem/estabilização, extração,
comparação, segunda leitura, links, cliques, sondagem de template, documentos,
capturas e auditoria. Segunda leitura inclui suas suboperações: não some tempos
aninhados para estimar tempo total. O benchmark mede também o tempo de parede,
incluindo inicialização e fechamento do navegador.

## Equivalência de elementos e reaproveitamento

`ambidiff/smart.py` associa candidatos únicos por tipo, rótulo e contexto. Para
registrar equivalência estática, exige também papel, estrutura do elemento e
destino compatíveis. A estrutura considera tag, papel, tipo, estado desabilitado,
popup, target e filhos imediatos; não usa o seletor ou a posição como identidade.
Assim, wrappers e posições diferentes não impedem parear o mesmo controle.

A prova é refeita sobre o DOM de cada página. Uma assinatura de componente
permite registrar reutilização das evidências já conhecidas e excluir os pares
estáticos comprovados da comparação residual. Não se reutiliza uma ausência ou
divergência anterior para decidir o resultado de uma página nova. Itens exclusivos
permanecem na comparação residual.

Botões, tabs, controles dinâmicos e papéis/estruturas/destinos incompatíveis não
recebem essa equivalência. A comparação normal continua, e diferenças ou dúvidas
estruturais motivam releitura. Os testes opcionais de clique existentes continuam
independentes: equivalência DOM **não** prova funcionamento, eventos JavaScript,
aparência por pixels ou igualdade de conteúdo oculto.

ÁUDIOS exclusivo no PRD continua sendo divergência. No modo inteligente, regiões
institucionais prevalecem sobre a classificação editorial dos itens coletados,
inclusive quando DES é declarado desatualizado. O ID histórico DIV-0004 não é
forçado em novas execuções; a detecção semântica é protegida pelos testes.

## Notícias: otimização conservadora da preparação profunda

Esta primeira implementação não pula centenas de URLs por suposição. **Toda
notícia pareada que usa a otimização ainda é navegada e sondada no DOM.** Reduz
a preparação profunda repetida, não promete eliminar o custo de navegação.

Para dispensar rolagem/abas/estabilização completas de uma notícia, exige:

1. Defasagem declarada pelo usuário.
2. Página reconhecida como artigo único, com título e data semântica, em uma rota
   editorial conhecida.
3. Árvore, classes, papéis, controles e destinos compatíveis nos dois ambientes.
4. Duas amostras anteriores preparadas profundamente, estáveis, com a mesma
   assinatura antes e depois da preparação.
5. Nova sondagem nas duas páginas após uma espera de confirmação.
6. Ausência de scripts, handlers inline, formulários, tabs, botões, iframe,
   vídeo e marcadores conhecidos de lazy loading.

Páginas Liferay com scripts/dinâmica e templates não comprovados mantêm o
percurso profundo. Essa restrição é deliberada: o ganho medido em páginas
sintéticas estáticas não comprova ganho em portais reais.

Mesmo nas páginas rasas, os elementos carregados são extraídos e comparados.
Títulos/datas diferentes com contexto editorial e defasagem declarada seguem
para variações de dados. Os registros completos dessas variações são preservados
em `registros_editoriais` no modo inteligente. Estrutura de Notícias, controles,
paginação e navegação permanecem relevantes. Estruturas distintas ou seção
ausente geram registros de revisão estrutural, sem presumir defeito confirmado.

Páginas institucionais não recebem a dispensa de preparação por template. Links
sem par inequívoco têm sua divergência preservada e a falta de inspeção profunda
registrada, em vez de serem tratados como conteúdo equivalente.

## Documentos: somente verificação rápida

`ambidiff/documents.py` usa apenas bibliotecas padrão do Python e TLS verificado.
Reconhece os formatos existentes e rotas Liferay `/documents/d/...`, mesmo quando
um lado tem extensão e o outro não. A classificação como documento é normalizada
somente no modo inteligente.

O pareamento exige evidências de rótulo/contexto; documentos exclusivos ou
ambíguos ficam como inconclusivos sem acesso especulativo ao destino. A checagem
usa HEAD e avalia status, MIME, nome em Content-Disposition/URL, tamanho declarado,
Last-Modified e ETag disponíveis. Similaridade de nomes/assunto é conservadora;
nomes genéricos ou evidências insuficientes não confirmam equivalência.

Limites por execução e documento:

| Limite | Valor |
|---|---:|
| Pares avaliados | 20 |
| Requisições HTTP documentais | 100 |
| Redirecionamentos por tentativa documental | 3 |
| Timeout por requisição | até 4 s |
| Orçamento de um documento | 10 s, checado entre requisições |
| Fallback solicitado | GET com Range `bytes=0-0` |
| Bytes de corpo lidos pela aplicação | **0** |

HEAD 405/501 permite fallback. O cliente não lê o corpo nem mesmo nesse fallback;
usa somente cabeçalhos. Se o servidor não responder 206 com Range coerente de no
máximo um byte, a resposta é fechada como inconclusiva. Não existe `read()` sem
limite, análise de PDF ou download para disco. Buffers de transporte podem receber
bytes antes do fechamento caso o servidor ignore Range: o limite de leitura da
aplicação não é uma garantia de bytes exatos transmitidos na rede.

Redirecionamentos são resolvidos manualmente e só podem manter a origem
(protocolo, host e porta) do respectivo ambiente. Não são reutilizados cookies,
credenciais ou sessão do navegador. Restrições de acesso permanecem limitações;
não há login ou contorno de autenticação. Nenhum serviço externo analisa arquivos.

Resultados possíveis:

- Documento acessível e provavelmente equivalente.
- Possível divergência de destino, tipo ou finalidade.
- Falha de acesso confirmada em um ambiente.
- Verificação inconclusiva.

Metadados compatíveis **não comprovam arquivos idênticos**. HTTP 403/404 é uma
resposta de acesso observada, sem atribuir culpa ao site. A ausência de leitura
integral também não valida links internos ao arquivo ou seu conteúdo.

O cache documental só é usado durante o frescor explícito de Cache-Control
max-age de ambos os lados, descontado Age e limitado a 30 s. no-cache/no-store ou
frescor ausente exigem nova checagem. Assim, a deduplicação não transforma uma
resposta antiga sem validade em prova para o restante da varredura.

GET e HEAD são métodos de leitura do protocolo; não garantem ausência de efeitos
em um servidor mal implementado. Use somente URLs autorizadas de consulta.

## Relatórios, cobertura e interrupção

JSON, HTML, interface e diagnósticos distinguem equivalências estáticas,
inconclusivos, documentos, variações editoriais, divergências e inspeções profundas
omitidas. O CSV de divergências mantém sua finalidade; a extensão de relevância acrescenta colunas de classificação (ver [filtro de relevância](filtro-relevancia.md)); os
registros documentais e de cobertura completos estão no JSON/HTML/diagnósticos.

O modo inteligente marca resultado parcial quando há inspeções profundas
omitidas, páginas sem par ou documentos sem comparação integral. Omitir conteúdo
profundo não conta como uma visita profunda realizada. O progresso indica término
do percurso, não garantia de cobertura integral.

Os checkpoints periódicos incluem as novas categorias. Uma interrupção no modo
inteligente também tenta salvar um checkpoint final com o material já coletado,
preservando relatório parcial e diagnósticos. O checkpoint é mantido na parada;
não há retomada automática. Limitações de disco ou falhas anteriores à coleta
podem impedir recuperação completa.

## Benchmark reproduzível

Instale as dependências e o Chromium como no README. Na raiz, execute com o
interpretador do ambiente virtual:

```cmd
.venv\Scripts\python.exe scripts\benchmark_smart.py --articles 8 --repetitions 3
```

Em Linux, o comando equivalente é `python scripts/benchmark_smart.py --articles 8
--repetitions 3`. Não usa portais externos: cria dois servidores HTTP locais com
um índice, oito notícias estáticas por ambiente e um documento com metadados.
Alterna a ordem dos modos. Emite JSON com cada execução, medianas, páginas,
requisições vistas pelo servidor, tempos por etapa, reutilizações e omissões.

`paginas_visitadas` conta tentativas de navegação; `paginas_coletadas` conta páginas
extraídas. Requisições instrumentadas incluem eventos Playwright e metadados, não
DNS/TLS ou todo tráfego interno do navegador. No benchmark, o servidor fornece
uma contagem HTTP independente; favicon usa data URI para evitar ruído.

Os modos têm coberturas distintas: o inteligente acrescenta checagem documental
e pode omitir preparação profunda de notícias já sondadas. Uma redução local de
tempo não comprova desempenho de produção nem equivalência funcional dos sites.
O artefato `benchmark-smart.json` registra as medições desta alteração.

### Resultado medido neste ambiente

Três repetições por modo, oito notícias por ambiente, Python 3.12.14,
Playwright 1.64.0, Flask 3.1.3 e Chromium 154.0.8037.57 em Linux. Os timeouts e
as esperas do modo atual foram mantidos; não foram trocados por mocks no benchmark.

| Medida | Atual | Inteligente |
|---|---:|---:|
| Tempo de parede mediano | 25,274 s | 13,047 s |
| Tempo mediano em preparação | 22,970 s | 7,660 s |
| Tempo mediano em navegação | 0,561 s | 0,586 s |
| Páginas navegadas/coletadas, somando ambientes | 18 | 18 |
| Preparações profundas executadas | 18 | 6 |
| Páginas sem preparação profunda | 0 | 12 |
| Requisições HTTP vistas pelo servidor | 18 | 20 |
| Reutilizações de equivalência de componentes | 0 | 16 |
| Bytes de corpo de documentos lidos | 0 | 0 |
| Divergências nas fixtures | 0 | 0 |

Redução observada do tempo mediano: **48,38% neste cenário**. A maior economia
veio da preparação, que representou aproximadamente 91% do tempo de parede do
modo atual. A navegação não ficou mais rápida. As duas requisições adicionais
são HEAD documentais; não houve redução de requisições HTTP neste cenário.

O relatório inteligente é parcial: doze páginas não tiveram preparação profunda,
e nenhum documento foi comparado integralmente. Zero divergências nessas fixtures
não valida equivalência funcional ou conteúdo tardio. Os números não são uma
previsão de ganho em portais reais, especialmente os que exigem JavaScript,
autenticação ou carregamento dinâmico.

## Integração futura com PRs pendentes

Não há commits de `fix/useia-navegacao-redirecionamentos` ou
`fix/cge-progresso-interrupcao` nesta branch, criada diretamente da main atualizada.

São esperados conflitos em `paired.py`, `core.py`, `web/server.py`,
`web/static/app.js`, `web/templates/index.html`, relatórios e diagnósticos. Ao
integrar, concilie explicitamente os novos argumentos, classificação de rotas,
políticas de requisição, cursor de logs, cancelamento cooperativo, geração de
checkpoints e métricas. Não substitua a lógica de um PR pela de outro. Reexecute
as suítes combinadas, incluindo ÁUDIOS, redirecionamentos e interrupção, e repita
o benchmark sobre a versão integrada.

## Arquivos desta implementação

- Motor e metadados: `ambidiff/smart.py`, `ambidiff/documents.py`.
- Extração, percurso e exportações: `ambidiff/core.py`, `ambidiff/paired.py`,
  `ambidiff/reports.py`, `ambidiff/diagnostics.py`.
- API e interface: `web/server.py`, `web/static/app.js`, `web/templates/index.html`.
- Regressões e fixtures: `tests/test_smart.py`, `tests/fixtures_smart.py`.
- Medição: `scripts/benchmark_smart.py`, `docs/benchmark-smart.json`.
- Orientações: `README.md` e este documento.

Os testes anteriores não foram removidos nem tiveram asserções alteradas.
