# Pareamento conservador e eficiência da fila

Base de desenvolvimento: `6b0bc9b`, obtida da branch remota
`chore/infra-codex-agents-skills-ci`. Na consulta desta manutenção,
`perf/otimizacao-varredura` já não existia no remoto. A correção fica em
`fix/pareamento-eficiencia-varredura`; `main` não foi utilizada como base.

## Diagnóstico

O relato agregado do PROCON informa 89 comparados,
876 inconclusivos e 35 falhos, cuja soma é 1.000. Também informa 1.008
admissões totais. Não foi disponibilizado o JSON individual dessa execução:
não é possível atribuir causas aos 876 pares, nem identificar as oito entradas
adicionais com certeza. Tempos aninhados não devem ser somados.

No código, foram confirmados estes comportamentos:

- `_link_pairs` associava texto e região, mas não recuperava referências únicas
  com rótulo e rota iguais quando a região HTML mudava. Essas referências eram
  enfileiradas separadamente, uma por ambiente.
- Inspeções unilaterais chamavam a preparação profunda, com espera e expansão
  de abas, embora não executassem uma comparação de conteúdo entre ambientes.
- Rotas distintas encerravam o ramo mesmo quando havia finalidade comum.
- Os estados terminais guardavam URLs e status, sem origem, critério e motivo
  próprios para cada par. Eventos limitados não substituem esse inventário.
- O limite reserva vagas HTML: ao reconhecer uma resposta como não HTML, o
  sistema libera a reserva, mantendo a admissão no histórico. Assim, total de
  admissões e reservas HTML podem diferir; isso é uma possibilidade de mecanismo,
  não uma explicação comprovada para as oito entradas do PROCON.

## Alterações

1. **Fallback de referências:** mantém as regras existentes e tenta associar os
   itens restantes por tipo, nome e URL normalizada equivalente, com unicidade
   mútua. A posição do menu pode mudar. Rótulos distintos e associações ambíguas
   continuam sujeitos às verificações existentes; o fallback não apaga DIVs.
2. **Rotas distintas:** a diferença de destino continua registrada. Somente uma
   opção estrutural única, observada nos dois ambientes, com mesmo nome, URLs
   internas e mesma query/fragmento, pode originar uma sondagem superficial. Conteúdo
   editorial e documentos não usam essa sondagem. Não são inventadas URLs.
3. **Corroboração local:** a sondagem exige título específico igual, diferente do título da origem (para não
   usar apenas a marca do portal), e pelo menos
   duas referências de navegação nomeadas, únicas e equivalentes no conteúdo,
   excluindo menus, cabeçalhos, rodapés e links genéricos como Início/Voltar.
   Título ou aparência sozinhos não bastam. Redirecionamento durante a sondagem
   impede essa associação. Se aceita, a comparação completa continua obrigatória,
   usando as páginas já abertas; conteúdo igual não é presumido. Caso ambíguo
   encerra somente o ramo. Falhas da sondagem são registradas por par e não
   interrompem os outros pares. Recuperação do navegador permanece limitada.
4. **Inspeção unilateral:** extrai o DOM atual e referências sem preparação
   profunda/expansão de abas. Não comprova ausência no outro ambiente. A limitação
   é explícita; conteúdo dinâmico ainda não exposto pode não ser descoberto nesse
   ramo. Pares efetivamente comparados mantêm a preparação completa existente.
5. **Prioridade dinâmica:** menus → serviços → documentos/legislação →
   institucionais/demais páginas → notícias → históricos. A rotação existente
   continua prevenindo inanição. Checkpoints preservam categorias já gravadas;
   novas descobertas recebem a classificação atual.
6. **Auditoria:** `diagnosticos_pares` acrescenta ID estável derivado das URLs,
   origem, URLs, critério, estado, motivo e erros/evidências quando disponíveis.
   Está no JSON, diagnóstico e checkpoint; a recuperação aceita a ausência do
   campo nos arquivos antigos. IDs das DIVs não foram alterados pelo novo ID de par.
7. **Progresso:** HTML/PDF explicam que processar a fila não significa comparar
   todas as páginas. `cobertura.reconciliacao` permite verificar:

   ```text
   total_admitido = html_reservado + nao_html_observado
   total_admitido = soma(terminais) + pendentes + em_processamento
   ```

   Os terminais são mutuamente exclusivos: comparado, sem_contraparte,
   redirecionamento, fora_escopo, nao_html, falha ou inconclusivo. O contador legado
   `pares_inconclusivos` inclui sem_contraparte, redirecionamento e fora_escopo;
   não deve ser somado novamente às inspeções unilaterais. Referências candidatas
   ainda não admitidas e recusadas pelo teto ficam fora da primeira igualdade.
   `referencias_nao_admitidas` preserva o contador legado de ocorrências;
   `referencias_nao_admitidas_unicas` distingue referências únicas. URLs descartadas
   por duplicação de uma inspeção já descoberta recebem motivo próprio.

## Comparação controlada

`python scripts/benchmark_pairing.py [raiz_da_versao]` usa os mesmos grafos
fictícios e fixtures em ambas as versões, sem rede e sem Chromium. A preparação
é simulada: os valores abaixo medem solicitações de trabalho, não tempo real de
carregamento. O script mostra tempo da simulação, que não demonstra ganho em portal.

| Cenário / métrica | Base 6b0bc9b | Correção |
| --- | ---: | ---: |
| 25 destinos em menus reposicionados: comparados | 1 | 26 |
| Mesmo cenário: inconclusivos | 50 | 0 |
| Mesmo cenário: admissões | 51 | 26 |
| Mesmo cenário: aberturas | 52 | 52 |
| Mesmo cenário: DIVs preservadas | 50 | 50 |
| 25 notícias unilaterais: comparados | 1 | 1 |
| Mesmo cenário: inconclusivos | 25 | 25 |
| Mesmo cenário: aberturas | 27 | 27 |
| Mesmo cenário: coletas que pedem preparação profunda | 27 | 2 |
| Mesmo cenário: coletas superficiais | 0 | 25 |
| Mesmo cenário: DIVs preservadas | 25 | 25 |

Não foi eliminado trabalho de comparação para melhorar esses números. No primeiro
cenário a cobertura comparada aumenta; no segundo apenas se evita preparação
profunda de conteúdo que continuaria sem contraparte. Não se declara redução
percentual de tempo real nem cumprimento da meta de 1h30.

## Validação e uso local

Com o ambiente virtual ativo, inclusive no Windows:

```text
python -m pip install -r requirements.txt
python -m playwright install chromium
python -B -m unittest discover -s tests -p test_pairing_efficiency.py -v
python -B -m unittest discover -s tests -v
python scripts/benchmark_pairing.py
node --check web/static/app.js
git diff --check
```

As 12 regressões novas cobrem fallback entre regiões, ambiguidade, rótulos
diferentes, queries Liferay, sondagem corroborada/rejeitada, falha de extração,
inspeção superficial, notícia unilateral, ÁUDIOS, ciclos, HTTP, destinos
externos/invalidos, reconciliação, texto do HTML e retomada com/sem o novo campo.
O teste existente de prioridade foi atualizado para a ordem solicitada,
preservando a verificação de rotação e o restante da suíte.

Baseline isolado: **260 testes aprovados em 150,078 s**, sem falhas ou skips.
Entrega final: **272 testes aprovados em 144,411 s**, sem falhas ou skips
(260 existentes + 12 regressões novas). A duração total da suíte não é um
benchmark de varredura. Sintaxe JavaScript, compilação Python e `git diff --check`
também aprovados.
A primeira tentativa registrou dois erros e seis skips por ausência do navegador
esperado. O download oficial retornou HTTP 403. Para validar sem alterar o projeto,
foi utilizado Chromium 154 instalado no sistema, com caminho temporário fora do
repositório para os testes que dependem da localização padrão do Playwright.
Isso difere do Chromium 156 esperado pela instalação atual do Playwright; o CI
com o navegador oficial e o Windows continuam sendo validações distintas.

Nenhum portal real foi acessado. Permanecem preservados teto de 1.000 reservas
HTML, drenagem da fila admitida, Chromium oculto, segurança somente leitura,
exportações, evidências, revisão manual, ambientes e compatibilidades anteriores.
`web/server.py` e `web/static/app.js` não foram modificados.

A sondagem entre rotas distintas está restrita a opções estruturais únicas
observadas numa origem comparada. Não faz associação semântica global entre
ramos desconectados, nem promete resolver todos os inconclusivos do PROCON.
O fallback conserva diferenças de região já registradas pela comparação:
reconhecer o destino para navegação não significa apagar diferenças de contexto.
