# AmbiDiff Next — 0.1.0 experimental

Ferramenta independente de QA comparativo local, desenvolvida ao lado do AmbiDiff
1.5. A unidade de análise é o componente: menus, controles, referências,
comportamento observado e capturas. Descoberta de URLs organiza verificações,
sem meta de atingir 1.000 páginas.

## Instalação no Windows

Requisitos: Python 3.10 ou superior com Python Launcher, acesso para instalar
pacotes e Chromium. Nesta pasta, execute `instalar.cmd` e depois `iniciar.cmd`.
Abra **http://127.0.0.1:5011**. O instalador é um script local de preparação de
venv/dependências, não um executável autônomo ou instalador assinado.

Alternativa manual (PowerShell, nesta pasta):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python -m ambidiff_next
```

O AmbiDiff anterior mantém porta e diretórios próprios. O Next grava somente em
`ambidiff-next/data/`: SQLite, evidências e benchmarks, ignorados pelo Git. Para
outra pasta/porta, use `python -m ambidiff_next --data-dir CAMINHO --port 5012`.
O servidor sempre escuta em 127.0.0.1, sem depuração, telemetria ou upload.

## Uso

1. Informe órgão, URLs e identificações dos ambientes (PRD, HOMOL, DES ou LAB).
2. Opcionalmente registre qual base pode estar desatualizada. Isso não torna
   diferenças estruturais editoriais e não considera PRD automaticamente correto.
3. Inicie e acompanhe a fila, componentes, testes, imagens e limitações.
4. Interromper solicita parada cooperativa em um clique; uma operação já iniciada
   pode aguardar seu timeout. O relatório parcial e tarefas pendentes permanecem.
5. Retome pelo histórico, inclusive após reiniciar o servidor. Tarefas concluídas
   e ocorrências estáveis são preservadas; falhas definitivas não entram em ciclo.
6. Revise DIVs e selecione para exportar separadamente. Confirmar, falso positivo,
   editorial, corrigida e ocultar não reescrevem ocorrências brutas.

Buscas aceitam ID, texto, `12,15,19` e `12-20`. “Todas as filtradas” seleciona o
conjunto filtrado, não confirma defeitos. JSON completo/selecionado, CSV com BOM
UTF-8 e `;`, HTML com PNGs incorporados dentro dos limites e ZIP de evidências
são gerados localmente. Diagnóstico JSON e log de execução integram o ZIP; o JSON completo também
preserva o diagnóstico estruturado.
A exportação selecionada evita anexar filas/logs/inventários não relacionados.
A janela de salvar depende do navegador; cancelamento e download nativo têm
tratamento explícito. O browser pode manter a última pasta quando suportado.

## O que esta versão implementa

- Modelo semântico independente de igualdade de seletores; extração de elementos
  visíveis e ocultos, hierarquia, destinos, geometria e estilos.
- Pareamento mútuo conservador por nome, tipo, contexto, destino e vocabulário
  português limitado. Hipóteses intermediárias de rotas internas recebem uma
  verificação adicional de título específico e estrutura; ambiguidade permanece
  inconclusiva. Não há IA remota ou modelo de linguagem em execução.
- Comparação estrutural bidirecional, inclusive ÁUDIOS da CGE, opções ausentes,
  diferenças documentais, de destino e redirecionamento. Mudar de posição HTML
  sozinho não comprova divergência.
- Controles ARIA/details reconhecidos podem ser exercitados em páginas isoladas,
  com capturas antes/depois. Não são enviados formulários. Um controle existente
  ou um destino que responde HTTP não comprova funcionamento integral.
- Capturas reais por componente, análise Pillow e geometria para visibilidade,
  sobreposição, recorte, dimensões e pixels. Sem duas imagens válidas, não há
  comparação de imagem concluída. `visibility:hidden` pode ser evidenciado pela
  região vazia real; `display:none` fica como observação DOM com limitação visual.
- Planejamento por prioridade, deduplicação, representantes editoriais e paginação,
  inspeção unilateral sem expansão indiscriminada, capacidade configurável até
  1.000 pares como proteção. Não há prazo global obrigatório para parar.
- SQLite transacional incremental, logs com cursor sequencial, retomada, falhas por
  tarefa e recuperação limitada do navegador. Ocorrências e revisões são separadas.

## Segurança e limites

Somente escopos configurados são navegados. Métodos modificadores, URLs com
credenciais/tokens e GETs reconhecidamente perigosos são bloqueados. Durante
cliques ARIA/details, novas requisições são bloqueadas, inclusive GET; interferência
vira inconclusão. A aplicação não autentica, resolve CAPTCHA nem ignora TLS.
A máquina continua executando JavaScript das páginas autorizadas: semântica de
negócio de um endpoint GET desconhecido não pode ser provada por sua URL. Utilize
somente ambientes e rotas autorizados para inspeção de leitura.

Handlers inline desconhecidos e ações sem contrato seguro não são testados.
Modais e menus sem ARIA/details suficiente podem ficar inconclusivos. Links usam
navegação HTTP direta; o handler JavaScript de clique desses links não é validado.
Documentos recebem somente HEAD, não leitura de corpo; HEAD recusado não prova
arquivo ausente. Recursos externos podem afetar widgets e produzir limitações.

Amostragem não valida páginas omitidas. Componentes compartilhados têm mapa
reutilizável, mas suas funções não são presumidas corretas em todas as páginas.
Extração após DOMContentLoaded pode não encontrar conteúdo tardio; isso é
registrado. Semântica, responsividade, acessibilidade e alinhamento não são uma
avaliação humana integral. Viewport é configurável; cada execução usa um tamanho,
sem prometer cobertura de todos os dispositivos. Máscaras exigem limites e
justificativa explícita; esta versão não inventa máscaras universais de notícias.

## Testes e desempenho

```text
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest -q
node --check ambidiff_next/static/app.js
node --check ambidiff_next/extract.js
python scripts/benchmark_comparative.py --program both --news 8 --repeats 3
```

Confira [arquitetura e manutenção](docs/arquitetura.md),
[método de benchmark](docs/benchmark-method.md) e
[resultados e pendências](docs/validacao.md).

**Meta experimental:** reduzir 30–50% do tempo com cobertura e detecção preservadas.
Isso não é ganho comprovado. O comparativo usa os mesmos portais fictícios para
Next e legado, verdade conhecida, negativos, tempos, navegações, elementos,
funções, imagens, FP/FN e volume de artefatos. Métrica ausente fica desconhecida.
Nenhum teste de INDEA, SEMA ou outro portal institucional foi autorizado/executado.
Esses testes dependerão de autorização futura e de cenários comparáveis.
