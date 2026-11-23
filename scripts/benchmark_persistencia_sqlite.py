"""Compara os backends com snapshots sintéticos v1, sem Chromium nem rede."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from statistics import median
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ambidiff import checkpoints
from ambidiff.core import Item, Pagina

RUN_ID = '20261123_120000_abcdef'
BASES = ('https://prd.test/', 'https://des.test/')


def estado_sintetico(admitidos):
    pares = [[base+f'pagina/{i}' for base in BASES] for i in range(admitidos)]
    visitados = pares[:-max(1, admitidos//20)]
    comparados = visitados[:-1]
    falha = visitados[-1]
    estado = {
        chave: [] for chave in ('brutos', 'falhas', 'pendencias', 'refs', 'editoriais',
        'eventos', 'avisos_coleta', 'documentos_relatorio', 'verificacoes_destinos',
        'resultados_funcionais', 'diferencas_esteticas', 'segmentos')
    }
    estado.update(
        configuracao=dict(url_a=BASES[0], url_b=BASES[1], nome_a='PRD', nome_b='DES',
                          site_nome='Portal sintético', auditar_externos=False, verificar_cliques=False,
                          varredura_inteligente=True, ambiente_desatualizado='', estrategia='dinamica'),
        politica_html=1, limite_html=1000, duracao_acumulada=120,
        iniciado_em='2026-11-23T12:00:00+00:00', cliques_testados=0,
        metricas=dict(tempos_segundos={}, contagens={}), excluded={}, bloqueios={},
        inteligencia={k: [] for k in ('equivalencias', 'inconclusivos', 'omissoes',
                                      'estruturas', 'componentes', 'templates', 'nao_pareadas')},
        visitados=visitados, pares_enfileirados=pares, pares_falhos=[falha],
        fila=[par+[['Início']] for par in pares[len(visitados):]],
        estados_pares=[dict(par=par, estado='comparado') for par in comparados]+[dict(par=falha, estado='falha')],
        falhas=[dict(ambiente='DES', url=falha[1], erro='HTTP 503 sintético')],
        brutos=[dict(tipo='Opção', elemento=f'Consulta local {i}', presente_em='PRD', nao_identificado_em='DES',
                     url_presente=a, url_comparada=b) for i, (a,b) in enumerate(comparados)],
        evidencias_preservadas={'DIV-0001': {'evidencias': {'PRD': f'evidencias_{RUN_ID}/DIV-0001_PRD.png'}}},
    )
    cache = checkpoints.PaginasSerializadas()
    for lado, chave in enumerate(('paginas_a','paginas_b')):
        paginas = {par[lado]: Pagina(par[lado], '', 'Portal de teste', [
            Item('Texto', f'Aviso institucional {j}', f'Aviso institucional {j}', local='Atendimento')
            for j in range(20)], ['Início'], coleta={'estavel':True}) for par in comparados}
        estado[chave] = cache.converter(paginas)
    return estado


def pico(funcao):
    tracemalloc.start()
    try:
        funcao()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def pico_processo():
    if sys.platform not in ('linux', 'darwin'):
        return None
    import resource
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == 'darwin' else rss * 1024


def medir(backend, n, repeticoes, pasta):
    arquivo = pasta / f'checkpoint_{RUN_ID}.json'
    if backend == 'sqlite':
        from ambidiff.checkpoint_sqlite import CheckpointSQLite
        banco = CheckpointSQLite(pasta, RUN_ID)
        gravar, ler, recuperar = banco.gravar, banco.ler, banco.recuperar
        arquivo = banco.caminho
    else:
        def gravar(dados):
            return checkpoints.gravar(arquivo, dados)

        def ler():
            dados = json.loads(arquivo.read_bytes())
            checkpoints.validar(dados['retomada'])
            return dados

        def recuperar():
            return checkpoints.recuperar(json.loads(arquivo.read_bytes()))

    amostras = []
    for i in range(repeticoes):
        # O último snapshot chega ao tamanho solicitado. Usar sempre o mesmo
        # BLOB permitiria ao SQLite dispensar parte das escritas de páginas.
        admitidos = max(3, n - n*(repeticoes-1-i)//(10*repeticoes))
        estado = estado_sintetico(admitidos)
        estado['duracao_acumulada'] += i
        inicio = perf_counter()
        snapshot = dict(id=RUN_ID, retomada=checkpoints.empacotar(estado), brutos=estado['brutos'],
                        paginas={'PRD':len(estado['paginas_a']), 'DES':len(estado['paginas_b'])})
        assinatura = perf_counter()-inicio
        inicio = perf_counter()
        io = gravar(snapshot)
        escrita = perf_counter()-inicio
        if i == 0:
            bytes_primeira = arquivo.stat().st_size
        inicio = perf_counter()
        leitura = ler()
        leitura_validada = perf_counter()-inicio
        assert leitura == snapshot
        del leitura
        inicio = perf_counter()
        parcial = recuperar()
        projecao = perf_counter()-inicio
        assert parcial['fila_pendente'] == estado['fila']
        assert parcial['estados_pares'] == estado['estados_pares']
        assert [d['id'] for d in parcial['divergencias']] == [
            f'DIV-{i:04d}' for i in range(1, len(estado['brutos'])+1)]
        assert parcial['divergencias'][0]['evidencias'] == estado['evidencias_preservadas']['DIV-0001']['evidencias']
        del parcial
        amostras.append(dict(assinatura=assinatura, escrita=escrita, assinatura_e_escrita=assinatura+escrita,
                            serializacao=io['serializacao_json'], io=io['gravacao'],
                            leitura_validada=leitura_validada, projecao=projecao))

    medianas = {k:median(d[k] for d in amostras) for k in amostras[0]}
    bytes_repetidas = arquivo.stat().st_size
    pico_rss = pico_processo()
    bytes_paginas_livres = None
    if backend == 'sqlite':
        with closing(sqlite3.connect(arquivo)) as con:
            livres, = con.execute('PRAGMA freelist_count').fetchone()
            tamanho_pagina, = con.execute('PRAGMA page_size').fetchone()
        bytes_paginas_livres = livres * tamanho_pagina
    pico_escrita = pico(lambda: gravar(snapshot))
    pico_leitura = pico(ler)
    return dict(pares_admitidos=n, medianas_segundos=medianas, amostras_segundos=amostras,
                bytes_primeira_gravacao=bytes_primeira, bytes_apos_repeticoes=bytes_repetidas,
                pico_python_escrita_bytes=pico_escrita, pico_python_leitura_bytes=pico_leitura,
                pico_rss_processo_bytes=pico_rss, bytes_paginas_livres=bytes_paginas_livres,
                intervalo_estimado_segundos=max(30,min(120,20*medianas['assinatura_e_escrita'])),
                estado_ids_e_evidencias_preservados=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pares', nargs='+', type=int, default=[20,300,980])
    parser.add_argument('--repeticoes', type=int, default=5)
    parser.add_argument('--backend', choices=('json','sqlite'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeticoes < 1 or any(not 3 <= n <= 1000 for n in args.pares):
        parser.error('Informe 3–1.000 pares e pelo menos uma repetição.')
    if args.backend:
        with TemporaryDirectory() as tmp:
            print(json.dumps(medir(args.backend, args.pares[0], args.repeticoes, Path(tmp))))
    else:
        resultados = {}
        for i, n in enumerate(args.pares):
            resultados[n] = {}
            backends = ('json','sqlite') if i % 2 == 0 else ('sqlite','json')
            for backend in backends:
                print(f'{n} pares, {backend}', file=sys.stderr, flush=True)
                dados = subprocess.check_output([sys.executable,'-B',__file__, '--backend',backend,
                    '--pares',str(n),'--repeticoes',str(args.repeticoes)], text=True)
                resultados[n][backend] = json.loads(dados)
        print(json.dumps(resultados, ensure_ascii=False, indent=2))
