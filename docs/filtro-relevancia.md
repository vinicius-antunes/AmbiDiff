# Relevância e evidências de ícones

O filtro atua na apresentação, depois da coleta. Não altera os caminhos percorridos,
não cancela verificações e funciona nos modos convencional e inteligente. Não usa
IDs DIV, nomes de órgãos ou o ambiente PRD como referência de correção.

## Critérios conservadores

- **Relevante:** padrão para menus, controles ausentes, avisos e textos institucionais,
  destinos documentais diferentes, falhas funcionais e indícios estruturais. Um destino
  diferente merece revisão; não comprova que o documento esteja errado.
- **Baixa relevância:** somente diferença de assinatura SVG/classe nos controles já
  correspondentes; links para o mesmo destinatário no endpoint HTTPS `m.me`, sem
  parâmetros extras; compartilhamento nos endpoints reconhecidos de Facebook/Twitter
  cuja diferença seja apenas a origem dos ambientes autorizados. O nome “Messenger”
  isoladamente não basta. Destinatários distintos e serviços internos continuam relevantes.
- **Editorial:** mantém a separação contextual já existente, condicionada à defasagem
  explicitamente informada pelo usuário; também pode ser atribuída manualmente.
  Não classifica um texto institucional como editorial apenas por mencionar notícias.
- **Inconclusivo:** diferenças de contexto ou situação explicitamente inconclusiva.
  Continua na lista principal para revisão. Documentos e equivalências inconclusivas
  também mantêm suas seções específicas existentes.

Diferenças técnicas de SVG não comprovam mudança visual. O filtro também não afirma
que os ícones sejam visualmente iguais. Evidências explícitas de impacto visual,
funcional, acessibilidade ou estrutura prevalecem sobre a baixa relevância.
Um controle correspondente com ícone reconhecido somente em um dos lados gera
registro estrutural prioritário. A detecção existente de controles ausentes e da
opção ÁUDIOS permanece ativa. Não foi implementada auditoria integral de
acessibilidade, comparação de pixels ou novos cliques de diagnóstico.

## Consulta e revisão

A lista principal e seu contador excluem baixa relevância e editoriais. Inconclusivos
permanecem visíveis. **Mostrar todas as diferenças** revela os registros classificados
fora da lista principal; as variações editoriais da coleta continuam na seção própria.
Cada cartão informa classe e motivo e oferece reclassificação (inclusive retorno à
automática). Confirmações manuais anteriores continuam prioritárias por padrão.

Somente diferenças técnicas com a mesma assinatura, elemento, tipo, destinos e lados
são consolidadas. Todos os IDs, registros e localizações ficam preservados. Reclassificar
um grupo pela interface aplica a escolha aos IDs indicados no cartão; a API também
permite alterar um membro individualmente. Ao reclassificar, os membros podem deixar
de formar um grupo. Exclusão/confirmacão preexistentes agem sobre o ID representativo;
não equivalem à reclassificação de todo o grupo.

As escolhas ficam em `relevancia_<execução>.json`, gravado atomicamente sob o lock da
aplicação. O JSON original não é regravado por nenhuma decisão manual. Relatórios
antigos recebem a classificação ao serem abertos, sem migração destrutiva. Se só
possuem resumos editoriais antigos, não é possível recuperar exemplos já ausentes.
Novas coletas preservam `registros_editoriais` completos nos dois modos.

## Exportações

| Formato | Relatório principal | Diagnóstico completo |
|---|---|---|
| JSON | Sempre contém todas as classes e evidências preservadas | Mesmo conteúdo completo, com decisões e resumo |
| HTML | Cartões prioritários; dados técnicos em seção recolhida | Cartões de todas as classes; seção técnica preservada |
| CSV | Linhas prioritárias | Todas as classes, mais registros editoriais completos disponíveis |
| Diagnóstico JSON | Inclui classes completas e decisões atuais | Mesmo diagnóstico completo |
| Log TXT | Log histórico da execução | Mesmo log; não é uma lista de revisão |

Escolha o escopo em **Exportação** antes de baixar. CSV mantém delimitador `;`, BOM
UTF-8, proteção de fórmulas e campos anteriores, mas acrescenta colunas de classificação,
motivo e IDs agrupados. Consumidores devem ler os nomes dos cabeçalhos; não presumir
as posições antigas. Dados de documentos/métricas continuam nas seções específicas
de JSON/HTML, não são artificialmente transformados em DIVs no CSV.

Downloads são gerados como cópias filtradas. O diagnóstico JSON baixado reflete as
reclassificações atuais sem sobrescrever o diagnóstico histórico. Exclusões manuais
anteriores continuam valendo na apresentação; o arquivo original permanece no disco.

## Testes e limitações

`tests/test_relevance.py` usa somente dados sintéticos, Chromium local e rotas Flask
interceptadas, sem portais corporativos. Cobre SVG, impacto explícito, ícone ausente,
ÁUDIOS, avisos/textos institucionais, documentos, reconhecimento estrito de widgets,
compartilhamento, agrupamento, persistência, interface e exportações. Casos históricos
SEFAZ são representações semânticas sintéticas, sem assumir que reproduzem seu DOM
ou comprovam defeitos reais. Os testes existentes de extração/crawler preservam a
regressão de ÁUDIOS com base defasada.

A classificação é heurística, não certifica equivalência nem prova defeitos. Widgets
não reconhecidos permanecem relevantes por segurança. Não cobre todos os provedores
de compartilhamento, todas as maneiras de desenhar ícones ou nomes acessíveis de
controles. Assinaturas limitadas e extração parcial mantêm as limitações do comparador.
Windows é o destino do produto; os testes desta entrega foram executados em Linux.

Esta alteração não incorpora PR #1 nem PR #2. Há áreas de conflito prováveis em
`paired.py`, `web/server.py`, `web/static/app.js`, template, relatórios e documentação.
Uma integração futura exige resolução e nova suíte, especialmente nas rotas de
exportação/relatórios e no progresso da interface.

## Arquivos desta extensão

- `ambidiff/relevance.py`: classificação e consolidação sem apagar evidências.
- `ambidiff/visual.py`: diferença de código e ícone não identificado.
- `ambidiff/paired.py`: preservação editorial nos dois modos.
- `ambidiff/storage.py`: decisões em arquivo auxiliar e membros agrupados.
- `ambidiff/reports.py`: JSON, HTML e CSV com escopos e classificação.
- `ambidiff/diagnostics.py`: diagnóstico completo com classes e editoriais.
- `web/server.py`: API de reclassificação e exportações atualizadas.
- `web/static/app.js`: filtro, contadores, reclassificação e escopo de exportação.
- `web/templates/index.html`: controles de consulta e exportação.
- `tests/test_relevance.py`: 12 regressões sintéticas.
- `README.md`, `docs/varredura-inteligente.md` e este documento: uso e limites.

Comando da suíte no Windows:

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

A suíte desta branch soma 77 testes: 43 da main, 22 da varredura inteligente e
12 desta extensão. A validação inclui também `node --check web/static/app.js` e
`git diff --check`. Não foi realizada validação real dos portais nem em Windows.
