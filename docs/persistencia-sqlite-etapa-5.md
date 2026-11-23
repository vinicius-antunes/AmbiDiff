# Etapa 5 — Persistência experimental de varreduras com SQLite

O worker do AmbiDiff continua usando checkpoints JSON v1. O SQLite está
disponível como protótipo para experimentos locais por meio do callback de
checkpoint do motor.

## Diagnóstico do fluxo atual

- O motor registra configurações, fila na ordem de execução, candidatos, pares
  admitidos, visitados e falhos, páginas comparadas, divergências, referências
  de evidência e diagnóstico. Em caso de falha durante uma comparação, o motor
  descarta o estado provisório do par e mantém o trabalho já confirmado. Essa
  fronteira é a mesma para as APIs síncrona e assíncrona do Playwright.
- O checkpoint v1 assina com SHA-256 o estado canônico inteiro. A gravação
  serializa um snapshot completo, grava em temporário na mesma pasta, executa
  `flush` e `fsync` e substitui o arquivo com `os.replace`. Um encerramento
  abrupto antes da substituição pode deixar um temporário órfão. O servidor
  procura apenas o nome final, valida o pacote e oferece retomada quando há fila
  pendente. A retomada tem novo ID de execução e preserva a origem.
- O motor reaproveita a conversão de páginas já coletadas e ajusta os intervalos
  periódicos de 30 a 120 segundos conforme o custo do último checkpoint. Há
  gravações fora do intervalo para marcos como início, falha de recurso,
  interrupção, evidências e finalização.
- `checkpoints.recuperar` projeta o relatório do snapshot, agrupando os registros
  pelo mesmo mecanismo que gera os IDs das DIVs. Em falhas tratadas, o worker
  pode exportar um relatório parcial do último JSON válido. Relatórios,
  referências e arquivos PNG, diagnósticos, histórico e revisões manuais ficam
  em arquivos locais. O histórico e as revisões usam a gravação atômica de
  `storage.py`, com ciclo de vida próprio.
- Antes de implementar, os snapshots JSON de 20, 300 e 980 pares levaram,
  respectivamente, **1,9 / 34 / 85 ms** para gravar, **5,8 / 109 / 306 ms** para
  ler e validar e **12 / 189 / 685 ms** para reconstruir o relatório. No maior,
  a assinatura consumiu **112 ms** e o arquivo ocupou **12,16 MB**. Essa primeira
  amostra usou `tmpfs`. A comparação abaixo usa outro cenário controlado, em
  que o snapshot cresce durante a medição.

## Arquitetura experimental

`ambidiff/checkpoint_sqlite.py` usa somente `sqlite3` da biblioteca padrão.
Cada execução experimental tem um arquivo `checkpoint_<id>.sqlite3` com
identificação do aplicativo, versão do banco e uma linha de snapshot. A
transação `BEGIN IMMEDIATE` com `synchronous=FULL` confirma de uma vez o
snapshot inteiro, incluindo fila, resultados e metadados. O SQLite usa seu
journal de rollback padrão. O pacote de retomada continua em v1 e conserva
sua assinatura. Um hash adicional protege o envelope completo, incluindo
os registros usados para projetar o relatório.
O arquivo nasce com permissões de acesso limitadas ao proprietário em
sistemas POSIX. No Windows, herda as permissões da pasta local.

O callback espera por bloqueios por até 250 ms por padrão. Bloqueio, disco
cheio, falha de escrita e corrupção têm erros locais tratados pelo contrato
de checkpoint existente. Se uma transação falhar antes de confirmar, a
leitura volta ao último snapshot confirmado. Arquivo ilegível, versão
incompatível e divergência de hash são recusados. O banco pode existir
vazio após falha na primeira gravação.

Cada execução experimental é conduzida por um único escritor. O callback
recusa gravar se o ID já tiver checkpoint JSON na mesma pasta. Para partir de
um JSON v1, valide seu campo `retomada` e alimente o motor com esse campo,
usando um novo ID SQLite. O JSON de origem continua disponível. O mesmo
pacote pode alimentar uma execução nova com callback JSON. As exportações
continuam sendo relatórios e ficam fora da retomada.

Um chamador de teste pode usar `CheckpointSQLite(pasta, novo_id).gravar` como
`checkpoint=` em `core.executar`, passar o pacote recuperado em `retomada=`
e optar pelo Playwright assíncrono pelo mecanismo existente. Para continuar
depois de reiniciar o processo, abra o banco anterior com
`CheckpointSQLite(pasta, id_anterior).ler()['retomada']`. Quando a integridade
do envelope estiver confirmada, `recuperar()` pode projetar as divergências
do último snapshot mesmo se o pacote interno de retomada for incompatível.
O chamador pode gravar o resultado via `reports.exportar`; o servidor já
serve esses relatórios, capturas e downloads após reiniciar. Os endpoints de
listagem e retomada do servidor continuam operando com JSON.

## Benchmark

Executar na raiz do projeto com Python do ambiente virtual. Para medir em
um volume local persistente, aponte o diretório temporário do sistema
(`TMPDIR` no Linux, `TEMP` e `TMP` no Windows) para o volume desejado.

```text
python -B scripts/benchmark_persistencia_sqlite.py
```

Cada combinação de backend e tamanho roda em processo próprio. Cinco
snapshots crescentes chegam a 20, 300 ou 980 pares admitidos. A fixture
inclui 20 elementos por página, fila pendente, um par falho, DIVs e uma
referência de evidência. A cada checkpoint, o script confere igualdade do
estado, ordem da fila, estados dos pares, IDs e referência no relatório.
Os tempos abaixo são medianas em milissegundos. **Gravação** inclui
serialização e I/O. **Assinatura + gravação** mede em conjunto o empacotamento
v1 e a gravação. **Leitura validada** termina com o estado validado para a
retomada. **Relatório parcial** termina com a projeção em memória, já
incluindo leitura e validação. Essas colunas medem operações independentes.

Resultados em Linux x86-64, Python 3.12.14, SQLite 3.53.1, com os arquivos
temporários no volume de trabalho (`overlayfs`).

| Pares | Backend | Gravação (ms) | Assinatura + gravação (ms) | Leitura validada (ms) | Relatório parcial (ms) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 20 | JSON | 3,7 | 5,6 | 6,2 | 12,3 |
| 20 | SQLite | 3,7 | 5,7 | 5,6 | 11,8 |
| 300 | JSON | 34,6 | 69,7 | 87,1 | 197,4 |
| 300 | SQLite | 34,9 | 72,3 | 101,9 | 206,8 |
| 980 | JSON | 102,7 | 225,2 | 271,0 | 656,2 |
| 980 | SQLite | 108,3 | 225,1 | 308,8 | 655,6 |

Os tamanhos abaixo são de arquivos confirmados, após a primeira e a quinta
gravações. Os picos de alocação Python usam `tracemalloc` em gravação e leitura
separadas, excluindo as alocações nativas. O pico de RSS inclui o processo
inteiro, incluindo a fixture e as operações medidas. MB equivale a 1.000.000
bytes. O tamanho do journal temporário fica fora da medição.

| Pares | Backend | Arquivo inicial (MB) | Arquivo final (MB) | Pico Python na escrita (MB) | Pico Python na leitura (MB) | Pico de RSS (MB) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 20 | JSON | 0,22 | 0,24 | 0,72 | 1,27 | 31,21 |
| 20 | SQLite | 0,23 | 0,46 | 0,71 | 1,27 | 31,73 |
| 300 | JSON | 3,43 | 3,72 | 11,16 | 20,09 | 61,94 |
| 300 | SQLite | 3,44 | 7,38 | 11,15 | 20,09 | 65,54 |
| 980 | JSON | 11,21 | 12,18 | 36,52 | 65,80 | 142,15 |
| 980 | SQLite | 11,22 | 24,14 | 36,51 | 65,80 | 143,58 |

No cenário de 980 pares, **11,95 MB** do arquivo SQLite final estavam em
páginas livres para uso futuro. A fórmula já usada pelo motor, `max(30,
min(120, 20 * custo_em_segundos))`, estimou **30 segundos** para todos os
cenários com o custo medido. Esse cálculo é um limite inferior porque usa
apenas assinatura e gravação. A janela real de trabalho entre checkpoints
segue o agendamento do motor. A amostra comparativa em `tmpfs` também chegou
ao piso de 30 segundos e a arquivos SQLite finais perto do dobro do JSON.

## Validação e decisão

Os testes específicos exercitam interrupção solicitada, reabertura em outro
processo e retomada sem reabrir pares concluídos. Exercitam também falha de
comparação, fechamento real do Chromium local com retomada no Playwright
assíncrono, interrupção de um processo entre a gravação e a confirmação
nos dois formatos, banco bloqueado, `SQLITE_FULL` por limite real de páginas,
banco em modo somente leitura, corrupção e alteração do conteúdo persistido.
Na comparação de encerramento abrupto, os dois formatos recuperaram o
snapshot anterior, com o par interrompido pendente e os IDs preservados.

O teste do relatório parcial usa um pacote com assinatura de retomada
inválida e envelope íntegro. Um processo separado extrai o relatório.
Após corromper o banco e reiniciar o servidor local, verificam-se as
referências, uma imagem PNG por sua URL e os downloads JSON, CSV, HTML e PDF.

A suíte completa (`python -B -m unittest discover -s tests -v`) passou em
Linux com Python 3.12.14 e Chromium local. Foram **381 testes em 250,8 s**,
com zero falhas e zero testes ignorados. A suíte inclui filtros de URL e
paginação, Rádio/TV, outros portais, ÁUDIOS da CGE, comparação bidirecional,
RapidFuzz, prioridade e limite de 1.000 pares HTML, Playwright síncrono e
assíncrono, relatórios e revisões manuais. As oito regressões do protótipo
também foram executadas separadamente. A verificação de sintaxe JavaScript
e as verificações de diff passaram. A execução foi local, com fixtures e
loopback. Validação em Windows e ensaios em portais institucionais ficaram
fora desta etapa.

O teste de encerramento abrupto mede a morte do processo. Queda de energia,
disco fisicamente cheio, antivírus, interação com processos concorrentes por
um mesmo ID e perda ou corrupção de todos os arquivos da execução ficam fora
da validação. Um banco corrompido pode impedir a extração de um relatório
ainda ausente. Os relatórios já materializados continuam acessíveis
independentemente do banco. O benchmark cobre persistência e projeção em
memória com dados sintéticos. Ficam fora do custo medido a coleta Playwright,
a conversão original de DOM e a gravação dos PNG e das exportações.

O JSON v1 deve continuar como persistência padrão, com o SQLite isolado.
As amostras em volume de trabalho apresentaram tempos de gravação e
memória semelhantes, a mesma cadência estimada e recuperação equivalente na
interrupção de processo avaliada. O SQLite foi mais lento para validar a
retomada nos cenários de 300 e 980 pares e ocupou quase o dobro do espaço ao
final. Este desenho transacional regrava o snapshot completo e continua
pagando os custos de serialização e validação v1.

### Arquivos

- `ambidiff/checkpoint_sqlite.py` implementa o backend isolado.
- `scripts/benchmark_persistencia_sqlite.py` reproduz a comparação.
- `tests/test_checkpoint_sqlite.py` cobre as regressões de persistência.
- Este documento registra a arquitetura, medições e decisão.
