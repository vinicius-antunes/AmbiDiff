# Comparação PRD × PRD

Implementação sobre a `main`, referência inicial `8b592af`. Não houve integração
de branches experimentais nem alteração do AmbiDiff Next.

## Comportamento e identidade

O seletor B oferece DES, LAB, HOMOL e PRD, nessa ordem, com DES como padrão. O
seletor A, CSS, layout e componentes existentes permanecem intactos. A comparação
continua bidirecional: A é uma referência, não uma fonte automaticamente correta.

O problema era usar a sigla tanto como tipo quanto como chave de armazenamento.
Remover apenas o bloqueio de siglas iguais sobrescreveria ambientes, contadores,
falhas e capturas. Somente na combinação PRD × PRD são gerados `PRD_A` e `PRD_B`.
Os nomes tradicionais de comparações distintas não mudam; DES × DES, LAB × LAB e
HOMOL × HOMOL continuam recusados. Os identificadores técnicos não são novos tipos
aceitos nos seletores/API de início.

Os campos existentes (`ambientes`, `paginas`, `presente_em`, `nao_identificado_em`,
`evidencias` e outros) usam essas chaves técnicas no JSON. IDs de DIVs continuam
inalterados. Dois objetos opcionais acrescentam o contexto para análise posterior:

```json
{
  "ambiente_a": {
    "identificador": "PRD_A", "tipo": "PRD", "posicao": "A",
    "funcao": "base", "url": "https://servidor-a.exemplo.test/",
    "rotulo": "PRD (A) — Base"
  },
  "ambiente_b": {
    "identificador": "PRD_B", "tipo": "PRD", "posicao": "B",
    "funcao": "comparado", "url": "https://servidor-b.exemplo.test/",
    "rotulo": "PRD (B) — Comparado"
  }
}
```

Relatórios visuais e CSV exibem rótulos distintos para os lados. CSV mantém suas
colunas tradicionais e, somente em PRD × PRD, acrescenta identificador, tipo e URL
de A/B. JSON completo/selecionado e diagnóstico conservam IDs técnicos, URLs e
metadados; isso permite distinguir as evidências no AmbiDiff IA, sem qualquer
integração automática ou envio externo. PDF é gerado localmente a partir do HTML.

As capturas usam `DIV-0001_PRD_A.png` e `DIV-0001_PRD_B.png`, sob a pasta da execução.
As chaves do mapa e os caminhos permanecem técnicos, inclusive quando o rótulo
mostrado é amigável. A validação de downloads aceita esses dois sufixos e os
legados, incluindo HOMOL, sem liberar nomes arbitrários ou caminhos relativos.

## Base desatualizada, histórico e retomada

A indicação visual continua sendo nenhuma, A ou B. O JavaScript envia `PRD_A` ou
`PRD_B` para a combinação nova. A API também aceita A/B como posição; `PRD` isolado
é recusado nesse caso por ser ambíguo. Nos pares tradicionais, siglas continuam
aceitas. O contexto editorial usa a identidade resolvida, mantendo as verificações
estruturais e a detecção de ÁUDIOS nos dois sentidos.

O histórico e os relatórios parciais preservam os dois objetos. O checkpoint usa
o formato existente, com os nomes técnicos na configuração original; não foi
criado um novo esquema paralelo. A retomada exige o mesmo par ordenado de nomes,
URLs e opções. Checkpoints que troquem `PRD_A`/`PRD_B` são recusados, com os arquivos
preservados. Relatórios, evidências e checkpoints tradicionais continuam legíveis.

Os logs usam os identificadores técnicos. O diagnóstico TXT acrescenta rótulos e
origens sanitizadas, sem novos registros de tokens de query. Os JSONs continuam
locais e podem conter as URLs da comparação: revisar antes de compartilhar.

## Arquivos e motivos

| Arquivo/função | Responsabilidade da alteração |
| --- | --- |
| `ambidiff/environments.py` | Resolver identidades, metadados e rótulos em um ponto comum |
| `ambidiff/paired.py`: `executar_pareado`, `snapshot` | Resolver nomes antes dos dicionários; incluir metadados nos resultados/checkpoints parciais |
| `ambidiff/checkpoints.py`: `validar` | Recusar inversão dos IDs reservados ou base desatualizada ambígua |
| `web/server.py`: `comparar`, `worker`, `evidencia` | Aceitar PRD em B; encaminhar IDs distintos; preservar histórico; validar arquivos de captura |
| `ambidiff/reports.py`: `exportar` | Manter JSON técnico e apresentar rótulos/URLs inequívocos em CSV/HTML/PDF |
| `ambidiff/storage.py`: `somente_selecionadas` | Preservar os novos metadados na seleção de DIVs |
| `ambidiff/diagnostics.py` | Metadados no JSON e cabeçalho dos dois servidores no TXT |
| `web/static/app.js` | Enviar o lado desatualizado sem ambiguidade e exibir rótulos sem alterar valores técnicos de filtros/evidências |
| `web/templates/index.html` | Única alteração visual: opção PRD ao final do seletor B |
| `tests/test_prd_prd.py`, `tests/test_update19.py`, `tests/test_next.py` | Novas regressões e expectativas antigas atualizadas para a aceitação solicitada; `test_next.py` é da suíte do AmbiDiff atual, não do projeto `ambidiff-next/` |
| `README.md` | Anúncio pontual do novo suporte; seção AmbiDiff IA preservada |

Não foram alterados algoritmos de pareamento, filtros Liferay/URLs, fila dinâmica,
prioridades, limite HTML, documentos, políticas de somente leitura ou parâmetros
de desempenho. No motor, a alteração limita-se à resolução dos nomes e metadados.

## Validação e uso local

Com o ambiente virtual ativado (Windows: `.venv\Scripts\activate`), use:

```text
python -B -m unittest discover -s tests -p test_prd_prd.py -v
python -B -m unittest discover -s tests -v
node --check web/static/app.js
git diff --check
```

As 15 regressões novas cobrem API, seletores/payload, identidades e contextos,
equivalência sem falsas DIVs, ÁUDIOS nos dois sentidos, falha individual, bases
desatualizadas, interrupção/recuperação/retomada, histórico/legados, seleção,
evidências e exportações JSON/CSV/HTML/PDF/diagnóstico. Uma comparação usa HTTP em
loopback com Chromium real e verifica isolamento de cookies; outras usam fixtures
e rotas interceptadas. O PDF e as duas capturas são gerados e inspecionados localmente.

Nos testes intermediários foram corrigidos dois problemas das fixtures novas:
uma tentativa de interagir com a tela de comparação ainda oculta no dashboard e
o nome incorreto de um helper de exportação. Nenhum teste antigo foi removido.
As expectativas de PRD bloqueado/três opções em B foram atualizadas porque
esse contrato mudou explicitamente; rejeições de outros tipos iguais continuam
testadas.

A primeira suíte completa identificou uma regressão no novo formatador JavaScript
quando um relatório legado não tinha metadados e uma DIV não informava o ambiente.
O formatador passou a exigir a existência do objeto antes de acessar seu rótulo;
o teste legado de abertura/relacionamento de DIVs foi preservado e reexecutado.
Na revisão final, um teste adicional no cenário de exportação reproduziu a
conversão indevida de textos literais `PRD_A`/`PRD_B` do portal em rótulos.
A formatação foi restrita aos campos de ambiente; textos, URLs, descrições,
caminhos de evidência e IDs originais permanecem intactos.

Resultados intermediários e verificações:

- Referência direcionada antes das mudanças: 36 testes de `test_update19.py`
  aprovados em 24,304 s.
- Novas regressões na versão final: 15 aprovadas em 10,894 s. O cenário HTTP real
  foi exercitado com varredura inteligente ativada e desativada.
- Suíte completa na versão definitiva: **351 testes executados e aprovados**,
  em 155,747 s; **zero falhas, zero erros e zero testes ignorados**. Os 15 novos
  casos e os 36 de `test_update19.py` estão incluídos nesse total.
- Primeira suíte completa: 351 executados, com uma expectativa antiga falha e
  dois erros de interface causados pelo formatador legado. Os três cenários
  afetados foram reexecutados e aprovados após a correção.
- O teste de conteúdo literal na exportação também falhou antes do ajuste e
  passou após limitar a formatação aos campos de ambiente.
- Sintaxe dos dez arquivos Python envolvidos, `node --check web/static/app.js`
  e `git diff --check` aprovados. Uma comparação dos bytes do template confirmou
  que apenas a opção PRD foi inserida no seletor B. O README foi comparado com a
  referência: fora do parágrafo novo, inclusive a seção AmbiDiff IA, é idêntico.

Limitações: validação em Linux/Python 3.12 com Chromium de sistema indicado por
alias local ao Playwright; nenhuma dependência adicionada. Ainda é necessário
validar a execução no Windows e em duas infraestruturas reais autorizadas. Os
JSONs têm campos opcionais novos, que consumidores externos podem passar a usar;
esta entrega não valida automaticamente o serviço AmbiDiff IA. Não houve teste
em portais institucionais nem afirmação de validação em produção.
