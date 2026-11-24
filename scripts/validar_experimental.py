"""Auditoria reproduzível de um checkout local. Todo o tráfego HTTP usa loopback."""
from collections import Counter
from contextlib import contextmanager
import argparse
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from zlib import crc32


RAIZ = Path(__file__).resolve().parents[1]
RID = '20261124_120000_abcdef'
SERVICOS = ('simcar', 'simlam', 'sisflora')
LEGISLACAO = ('/web/verde/legislacao?ano=2024', '/web/verde/legislacao?ano=2025')
MIDIA = ('/web/verde/radio-paiaguas', '/web/verde/tv-paiaguas')
PAGINAS_EDITORIAIS = ('/w/noticia-do-portal', '/-/noticia-do-portal')
PORTAL_VIZINHO = '/web/vizinho/institucional'
DOCUMENTO = '/documents/d/portaria-12'
ARQUIVO = '/midia/audio.mp3'
ALVO = 'Consultar serviço estadual'
CORPO = '<p>Informações públicas sobre o atendimento e a organização administrativa do órgão.</p>'


def links(referencias):
    return ''.join(f'<a href="{rota}">{nome}</a> ' for rota, nome in referencias)


def pagina(caso, lado, rota, pares):
    referencias = []
    p = urlsplit(rota)
    extra = ''
    titulo = 'Portal local de auditoria'
    if p.path == '/':
        if caso == 'filtros':
            referencias = [(f'/web/verde/servicos/{n}', n.upper()) for n in SERVICOS]
            referencias += [(u, 'Legislação '+u[-4:]) for u in LEGISLACAO]
            referencias += [(DOCUMENTO, 'Portaria 12'), *zip(MIDIA, ('Rádio', 'TV'))]
            referencias += [(u, 'Notícia editorial '+str(i)) for i,u in enumerate(PAGINAS_EDITORIAIS,1)]
            referencias += [(PORTAL_VIZINHO, 'Portal vizinho'), ('/abrir-guia', 'Guia de atendimento')]
        elif caso in ('painel','painel-container'):
            extra = '''<button aria-expanded="false" aria-controls="servico-revelado"
              onclick="document.getElementById('servico-revelado').hidden=false;
              this.setAttribute('aria-expanded','true')">Mais serviços</button>'''
            if lado == 'PRD':
                link = f'<a href="/servicos/especial">{ALVO}</a>'
                if caso=='painel-container':
                    extra += f'<div hidden id="servico-revelado">{link}</div>'
                else:
                    extra += f'<a hidden id="servico-revelado" href="/servicos/especial">{ALVO}</a>'
            else:
                extra += '<span hidden id="servico-revelado">Orientação local</span>'
        else:
            referencias = [(f'/setor/{n:02}', f'Área institucional {n:02}') for n in range(1, pares)]
        if lado == 'PRD' and caso not in ('painel','painel-container'):
            referencias.append((ARQUIVO, 'ÁUDIOS'))
    elif caso == 'filtros' and p.path in MIDIA:
        titulo = 'Rádio Paiaguás' if p.path == MIDIA[0] else 'TV Paiaguás'
        amostra = 'Almanac Quartz fiscal panorama' if lado == 'PRD' else 'Nebula topaz editorial release'
        extra = ('<article><h2>Publicações</h2><time datetime="2026-11-24">24/11</time>'
                 f'<p>{amostra}</p></article><nav aria-label="Paginação">{links([(p.path+"?_cast_x_cur=3", "Próximo")])}</nav>')
    elif caso == 'filtros' and p.path in PAGINAS_EDITORIAIS:
        extra = f'<article><h2>Notícia editorial</h2><time datetime="2026-11-24">24/11</time><p>Publicação de {lado}.</p></article>'
    canonico = '<link rel="canonical" href="/web/verde/inicio">' if caso=='filtros' and p.path=='/' else ''
    return (f'<!doctype html><meta charset="utf-8"><title>{titulo}</title>{canonico}'
            f'<nav aria-label="Portal local">{links(referencias)}</nav>'
            f'<main><h1>{titulo}</h1>{CORPO}{extra}</main>')


@contextmanager
def portais(caso, pares, atrasos):
    requisicoes = []
    servidores = []
    threads = []

    def handler(lado, atraso):
        class Portal(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def servir(self):
                requisicoes.append((lado, self.command, self.path))
                rota = urlsplit(self.path).path
                if caso == 'falhas' and lado == 'DES' and rota == '/setor/01':
                    self.send_error(503)
                    return
                if caso == 'falhas' and lado == 'DES' and rota == '/setor/02':
                    time.sleep(0.7)
                if self.command == 'GET':
                    time.sleep(atraso)
                if caso == 'filtros' and rota == '/abrir-guia':
                    self.send_response(302)
                    self.send_header('Location','/guia-a' if lado == 'PRD' else '/guia-b')
                    self.end_headers()
                    return
                if rota == DOCUMENTO:
                    dados, mime = b'%PDF-1.4\n%%EOF\n', 'application/pdf'
                elif rota == ARQUIVO:
                    dados, mime = b'', 'audio/mpeg'
                else:
                    dados = pagina(caso, lado, self.path, pares).encode()
                    mime = 'text/html; charset=utf-8'
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(dados)))
                self.end_headers()
                if self.command == 'GET':
                    try:
                        self.wfile.write(dados)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

            do_GET = do_HEAD = servir

            def do_POST(self):
                requisicoes.append((lado, self.command, self.path))
                self.send_error(405)

        return Portal

    try:
        for lado, atraso in zip(('PRD','DES'), atrasos):
            server = ThreadingHTTPServer(('127.0.0.1',0),handler(lado,atraso))
            thread = threading.Thread(target=server.serve_forever,daemon=True)
            servidores.append(server)
            threads.append(thread)
            thread.start()
        yield [f'http://127.0.0.1:{s.server_port}/' for s in servidores], requisicoes
    finally:
        for server in servidores:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()


def validar_png(arquivo):
    dados = arquivo.read_bytes()
    assert dados.startswith(b'\x89PNG\r\n\x1a\n'), arquivo
    pos = 8
    dimensoes = None
    while pos + 12 <= len(dados):
        n, tipo = struct.unpack_from('>I4s', dados, pos)
        fim = pos + 8 + n
        crc, = struct.unpack_from('>I', dados, fim)
        assert crc32(dados[pos+4:fim]) == crc, arquivo
        if tipo == b'IHDR':
            dimensoes = struct.unpack_from('>II', dados, pos+8)
        if tipo == b'IEND':
            assert fim + 4 == len(dados) and dimensoes and all(dimensoes), arquivo
            return dimensoes
        pos = fim + 4
    raise AssertionError(f'PNG incompleto: {arquivo}')


def artefatos(resultado, pasta, pdf):
    from ambidiff.exports import gerar_pdf
    from ambidiff.reports import exportar

    arquivos = exportar(dict(resultado, id=RID, exportacao_completa=True), pasta, RID)
    relatorio = json.loads(Path(arquivos['json']).read_text(encoding='utf-8'))
    html = Path(arquivos['html']).read_text(encoding='utf-8')
    with Path(arquivos['csv']).open(encoding='utf-8-sig', newline='') as stream:
        csv_ids = {d['id'] for d in csv.DictReader(stream, delimiter=';')}
    ids = {d['id'] for d in relatorio['divergencias']}
    for d in relatorio['divergencias']:
        assert d['id'] in csv_ids or set(d.get('ids_agrupados',())) & csv_ids
        assert d['id'] in html
    refs = {ref for d in resultado['divergencias'] for ref in d.get('evidencias',{}).values()}
    for ref in refs:
        validar_png(pasta / ref)
    pngs = list(pasta.rglob('*.png'))
    if pdf:
        destino = pasta/'comparacao.pdf'
        gerar_pdf(Path(arquivos['html']), destino)
        assert destino.read_bytes().startswith(b'%PDF')
    return dict(pngs=len(pngs), referencias_png=len(refs), ids_exportados=len(ids),
                bytes=sum(p.stat().st_size for p in pasta.rglob('*') if p.is_file()), pdf=pdf)


def rota(url):
    if not url:
        return ''
    u = urlsplit(url)
    return u.path + ('?' + u.query if u.query else '')


def resumir(res, requisicoes):
    from ambidiff.relevance import classificar
    fases = {k:v for k,v in res['metricas']['tempos_segundos'].items() if k in (
        'navegacao','preparacao','extracao','comparacao','comparacao_complementar','capturas',
        'checkpoint','navegacao_lado_0_segundos','navegacao_lado_1_segundos','recuperacao_falhas')}
    filtro = res.get('filtro_urls',{})
    divergencias = [dict(id=d['id'], tipo=d['tipo'], elemento=d['elemento'], local=d.get('local',''),
                        lado=d['presente_em'], origem=rota(d.get('url_presente')), destino_a=rota(d.get('destino_a')),
                        destino_b=rota(d.get('destino_b')), classe=classificar(d)[0]) for d in res['divergencias']]
    pares = [([rota(u) for u in d['par']],d['estado']) for d in res['estados_pares']]
    assert all(metodo in ('GET','HEAD') for _,metodo,_ in requisicoes), requisicoes
    return dict(
        tempos=fases, andamento={k:v for k,v in res['andamento'].items() if isinstance(v,int)},
        pares=pares, estados=dict(Counter(estado for _,estado in pares)),
        exclusoes=filtro.get('excluidas_por_categoria'),
        referencias_excluidas=[(ref['categoria'], [rota(u) for u in ref['urls']])
                              for ref in filtro.get('referencias',()) if ref['excluido']],
        editoriais=len(res.get('registros_editoriais',())), divergencias=divergencias,
        equivalencias=sorted({e['elemento'] for e in res['otimizacao']['equivalencias_verificadas']}),
        estrutura_inconclusiva=sorted({e['elemento'] for e in res['otimizacao']['equivalencias_inconclusivas']}),
        documentos=[(r.get('elemento'),r.get('classificacao')) for r in res.get('documentos_verificados',())],
        automacao=[{k:r[k] for k in ('ambiente','tipo','categoria','etapa','erro') if k in r} for r in res['falhas']],
        recuperacoes=res['metricas']['contagens'].get('recuperacoes_navegador',0),
        requisicoes=sorted({(lado,m,path) for lado,m,path in requisicoes}),
    )


def ordem_ids():
    from ambidiff.core import Pagina
    from ambidiff.paired import agrupar_registros, diferencas_de_ordem

    a = Pagina('http://127.0.0.1:8081/', '', 'Portal de teste', [])
    b = Pagina('http://127.0.0.1:8082/', '', 'Portal de teste', [])
    for nome, opcoes in (('Menu A',['Início','Contato']), ('Menu B',['Normas','Consulta'])):
        grupo = dict(nome=nome, posicao='Menu de navegação', opcoes=opcoes)
        a.menus.append(grupo)
        b.menus.append(dict(grupo, opcoes=opcoes[::-1]))
    return [(d['elemento'],d['id']) for d in agrupar_registros(diferencas_de_ordem(a,b))]


def medir_scan(args, pasta):
    from ambidiff import checkpoints, core
    from ambidiff.paired import executar_pareado
    from fixtures_aria import DIFERENCAS, EQUIVALENTES, INCONCLUSIVOS, portais_aria

    def salvar(snapshot):
        return checkpoints.gravar(arquivo, dict(snapshot,id=RID))

    opcoes = dict(varredura_inteligente=True, estrategia='dinamica', checkpoint=salvar)
    if 'navegacao_assincrona' in inspect.signature(executar_pareado).parameters:
        opcoes['navegacao_assincrona'] = args.assincrono
    elif args.assincrono:
        raise SystemExit('Checkout sem modo assíncrono.')
    if args.caso == 'filtros':
        opcoes['ambiente_desatualizado'] = 'DES'
    if args.caso == 'falhas':
        core.TEMPO_PAGINA_MS = 250
    if args.caso in ('escala','filtros','painel','painel-container'):
        opcoes['evidencias_dir'] = pasta/f'evidencias_{RID}'
    evento = threading.Event()
    arquivo = pasta/f'checkpoint_{RID}.json'

    def log(mensagem):
        if args.caso == 'retomada' and '[PRD/DES] 1 pares' in mensagem:
            evento.set()

    contexto = portais_aria() if args.caso=='aria' else portais(args.caso,args.pares,args.latencia_ms)
    with contexto as (bases, requisicoes):
        inicio = time.perf_counter()
        r = executar_pareado(*bases,'PRD','DES',evento,log,lambda _:None,**opcoes)
        segundos = time.perf_counter() - inicio
        ret = {}
        if args.caso == 'retomada':
            snap = json.loads(arquivo.read_bytes())
            estado = checkpoints.validar(snap['retomada'])
            parcial = checkpoints.recuperar(snap)
            artefatos(parcial,pasta/'parcial',args.pdf)
            antes = {d['elemento']:d['id'] for d in parcial['divergencias']}
            requisicoes.clear()
            r = executar_pareado(*bases,'PRD','DES',threading.Event(),lambda _:None,lambda _:None,
                                 retomada=snap['retomada'],**opcoes)
            depois = {d['elemento']:d['id'] for d in r['divergencias']}
            assert 'ÁUDIOS' in antes and antes['ÁUDIOS'] == depois.get('ÁUDIOS')
            assert not any(m=='GET' and rota=='/' for _,m,rota in requisicoes)
            ret = dict(parcial_comparados=parcial['andamento']['pares_comparados'],
                       pendentes_antes=len(estado['fila']), ids_antes=antes, ids_depois=depois,
                       comparados_retomados=r['andamento']['pares_comparados'])
        resultado = resumir(r,requisicoes)
    from ambidiff.diagnostics import montar_diagnostico
    diagnostico = montar_diagnostico(r)
    (pasta/'diagnostico.json').write_text(json.dumps(diagnostico,ensure_ascii=False),encoding='utf-8')
    resultado.update(artefatos=artefatos(r,pasta,args.pdf),segundos=segundos,retomada=ret,
                     diagnostico_desempenho='desempenho' in diagnostico)
    comparados = resultado['andamento']['pares_comparados']
    resultado['segundos_por_par'] = segundos/comparados if comparados and not ret else None
    if args.caso=='aria':
        eq = set(resultado['equivalencias'])
        esperado = EQUIVALENTES | INCONCLUSIVOS | DIFERENCAS
        resultado['precisao_aria'] = dict(acertos=len(eq & EQUIVALENTES),
            falsos_positivos=sorted((eq & esperado)-EQUIVALENTES),
            falsos_negativos=sorted(EQUIVALENTES-eq))
    if args.caso in ('painel','painel-container'):
        resultado['alvo_controlado'] = [d for d in resultado['divergencias'] if d['elemento']==ALVO]
    return resultado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codigo',type=Path,default=RAIZ)
    parser.add_argument('--caso',choices=('escala','filtros','aria','painel','painel-container','retomada','falhas','ids'),default='escala')
    parser.add_argument('--pares',type=int,default=4)
    parser.add_argument('--latencia-ms',type=int,nargs=2,default=(40,80),metavar=('PRD','DES'))
    parser.add_argument('--assincrono',action='store_true')
    parser.add_argument('--pdf',action='store_true')
    args = parser.parse_args()
    if args.pares < 2 or min(args.latencia_ms) < 0:
        parser.error('Informe pelo menos dois pares e latências não negativas.')
    if args.caso == 'falhas' and args.pares < 4:
        parser.error('Informe pelo menos quatro pares para exercitar sucesso e duas falhas.')
    sys.path[:0] = [str(args.codigo.resolve()),str(RAIZ/'tests')]
    args.latencia_ms = [ms/1000 for ms in args.latencia_ms]
    if args.caso == 'ids':
        resultado = ordem_ids()
    else:
        with tempfile.TemporaryDirectory(prefix='ambidiff-auditoria-') as temporario:
            resultado = medir_scan(args,Path(temporario))
        if sys.platform in ('linux','darwin'):
            import resource
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            resultado['rss_python_bytes'] = rss if sys.platform=='darwin' else rss*1024
    print(json.dumps(resultado,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
