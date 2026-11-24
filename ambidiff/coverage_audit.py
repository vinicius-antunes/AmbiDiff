"""Projeção sanitizada da cobertura, persistida junto aos marcos do scanner."""
from collections import Counter, defaultdict
import csv
import hashlib
from io import StringIO
from itertools import chain
import json
import re
from urllib.parse import unquote, urlsplit

from .checkpoints import gravar
from .core import url_limpa
from .pagination import paginacao
from .security import url_diagnostica
from .storage import valid_run


VERSAO = 1
ESTADOS = {
    'candidato': 'descoberta', 'em_processamento': 'admitida', 'admitido': 'admitida',
    'comparado': 'comparada', 'falha': 'falha', 'sem_contraparte': 'sem_contraparte',
    'nao_html': 'nao_html', 'fora_escopo': 'fora_escopo', 'inconclusivo': 'inconclusiva',
    'redirecionamento': 'inconclusiva', 'duplicado': 'duplicada', 'nao_admitido': 'nao_admitida',
}
CATEGORIAS_EDITORIAIS = {'rota_editorial','conteudo_editorial_individual','editorial_sem_contraparte','filtros_editoriais'}
SENSIVEL = re.compile(r'(?:access[_-]?token|refresh[_-]?token|token|auth(?:orization)?|api[_-]?key|key|signature|sig|password|senha|secret|cookie|session(?:id)?|jsessionid|phpsessid|credencial)', re.I)
SEGREDO_TEXTO = re.compile(r'(?:\bbearer\s+\S+|\b(?:'+SENSIVEL.pattern+r')\s*[=:]\s*\S+)', re.I)
URL_TEXTO = re.compile(r'https?://[^\s<>"\']+', re.I)


def caminho_auditoria(pasta, run_id):
    if not valid_run(run_id):
        raise ValueError('ID de execução inválido.')
    return pasta / f'auditoria_cobertura_{run_id}.json'


def _url(url):
    if not url:
        return ''
    try:
        partes = urlsplit(url)
        if partes.scheme not in ('http', 'https') or not partes.hostname:
            return '[referência omitida]'
        segs = unquote(partes.path).split('/')
        if any(SENSIVEL.fullmatch(s) or SEGREDO_TEXTO.search(s) for s in segs):
            return url_diagnostica(f'{partes.scheme}://{partes.netloc}/[caminho omitido]')
        return url_diagnostica(url)
    except (TypeError, ValueError):
        return '[referência omitida]'


def _texto(valor):
    valor = URL_TEXTO.sub(lambda m: _url(m[0]), str(valor or ''))
    decodificado = unquote(valor)
    if SEGREDO_TEXTO.search(decodificado) or re.search(r'[?&#][^\s]*=',decodificado):
        return '[trecho omitido]'
    return ' '.join(valor.split())[:160]


def _origem(origem):
    if isinstance(origem, list):
        origem = {'trilha': origem}
    origem = origem or {}
    return {
        'pagina_a': _url(origem.get('pagina_a')),
        'pagina_b': _url(origem.get('pagina_b')),
        'trilha': [_texto(passo) for passo in origem.get('trilha', ())[-12:]],
    }


def _indices(url):
    try:
        return [{'parametro': k.rsplit('_', 1)[-1].lower(), 'valor': v}
                for k,v in paginacao(url)['indices'] if v <= 10**9] if url else []
    except (TypeError, ValueError):
        return []


def _identificador(par):
    return 'par-'+hashlib.sha256(json.dumps(par, ensure_ascii=False).encode()).hexdigest()[:20]


class AuditoriaCobertura:
    def __init__(self, pasta, run_id, *, retomada_de=None, retomada=None):
        self.caminho = caminho_auditoria(pasta, run_id)
        self.run_id = run_id
        self.referencias = {}
        self.politicas = {}
        self.anteriores = {}
        self.retomada_de = retomada_de if valid_run(retomada_de) else None
        self.historico_incompleto = bool(retomada)
        if self.retomada_de and retomada:
            try:
                doc = json.loads(caminho_auditoria(pasta,self.retomada_de).read_bytes())
                if (doc['versao'] == VERSAO and doc['checkpoint_sha256'] == retomada['sha256_estado']
                        and doc['execucao_id'] == self.retomada_de):
                    self.anteriores = {r['id_referencia']:r for r in doc['referencias']}
                    self.historico_incompleto = doc['historico_anterior_incompleto']
            except (OSError, ValueError, TypeError, KeyError):
                pass

    def observar(self, par, origem=None, *, status='descoberta', motivo='', categoria=''):
        if not any(par):
            return
        if par not in self.referencias:
            self.referencias[par] = {'origem':origem}
        elif origem and not self.referencias[par]['origem']:
            self.referencias[par]['origem'] = origem
        if status!='descoberta':
            self.referencias[par].update(status=status,motivo=motivo,categoria=categoria)

    def observar_coleta(self, pa, pb, pares, trilha):
        """Observa as referências lidas, inclusive as tratadas fora da fila HTML."""
        origem = (pa.url if pa else '', pb.url if pb else '')
        def fonte(item):
            return {'pagina_a':origem[0],'pagina_b':origem[1],'trilha':(*trilha,item.nome)}
        pareados = set()
        for a,b in pares:
            pareados.update((id(a),id(b)))
            self.observar((url_limpa(a.destino),url_limpa(b.destino)),fonte(a))
        for lado,pagina in enumerate((pa,pb)):
            if pagina is None:
                continue
            for i in pagina.itens:
                if id(i) in pareados or not i.destino or i.tipo not in ('Opção','Documento'):
                    continue
                destino = url_limpa(i.destino)
                par = (destino,'') if lado==0 else ('',destino)
                if i.recurso in ('documento','midia','auxiliar'):
                    self.observar(par,fonte(i),status='nao_html',
                        motivo='Referência sem contraparte no fluxo de documentos, mídia ou recursos auxiliares.',
                        categoria='documental' if i.tipo=='Documento' else '')
                else:
                    self.observar(par,fonte(i),status='sem_contraparte',
                        motivo='Referência observada sem contraparte confirmada.')

    def fora_escopo(self, url, lado):
        destino = url_limpa(url)
        par = (destino,'') if lado==0 else ('',destino)
        self.observar(par,status='fora_escopo',motivo='Destino fora da expansão HTML no escopo autorizado.')

    def observar_politica(self, par, trilha, provas, fontes, decisao):
        registro = self.politicas.setdefault(par,{'exclusoes_observadas':{},'trilha':trilha})
        registro.update(provas=list(provas),fontes_portal=list(fontes))
        if decisao['excecao_estrutural']:
            registro['excecao_observada'] = True
        if decisao['excluido']:
            registro['exclusoes_observadas'][decisao['categoria']] = {
                'motivo':decisao['motivo'],'evidencia':list(provas),'fontes_portal':list(fontes)}

    def salvar(self, snapshot):
        estado = snapshot['retomada']['estado']
        filtro = estado['filtro_urls']
        registros = {tuple(r['par']):r for r in filtro['registros']}
        diagnosticos = {tuple(r['par']):r for r in estado['diagnosticos_pares']}
        terminais = {tuple(r['par']):r['estado'] for r in estado['estados_pares']}
        admitidos = set(map(tuple,estado['pares_enfileirados']))
        erros = defaultdict(set)
        for erro in estado['falhas']:
            if erro.get('tipo_erro'):
                erros[erro.get('url')].add(erro['tipo_erro'])
        docs = {r['id_referencia']:{**r,'execucao_id':self.run_id} for r in self.anteriores.values()}
        ids_url = {'':''}
        for par in dict.fromkeys(chain(diagnosticos,registros,self.referencias,terminais,admitidos)):
            for url in par:
                if url not in ids_url:
                    ids_url[url] = 'url-'+hashlib.sha256(url.encode('utf-8')).hexdigest()[:20]
            ident = _identificador(par)
            linha = self._linha(par,ident,docs.get(ident,{}),diagnosticos.get(par,{}),
                                registros.get(par,{}),terminais.get(par),par in admitidos,erros)
            linha.update(id_url_a=ids_url[par[0]],id_url_b=ids_url[par[1]])
            docs[ident] = linha
        if not any(r['status'] not in ('descoberta','admitida') for r in docs.values()):
            return
        por_status = Counter()
        por_categoria = defaultdict(Counter)
        urls_unicas = {'a':set(),'b':set()}
        for r in docs.values():
            por_status[r['status']] += 1
            por_categoria[r['categoria']][r['status']] += 1
            for lado in urls_unicas:
                if r.get('id_url_'+lado):
                    urls_unicas[lado].add(r['id_url_'+lado])
        gravar(self.caminho, {
            'versao':VERSAO, 'execucao_id':self.run_id, 'retomada_de':self.retomada_de,
            'historico_anterior_incompleto':self.historico_incompleto,
            'marco':snapshot['motivo_checkpoint'], 'checkpoint_sha256':snapshot['retomada']['sha256_estado'],
            'ambientes':{lado:{'nome':estado['configuracao']['nome_'+lado],
                               'url_inicial':_url(estado['configuracao']['url_'+lado])} for lado in ('a','b')},
            'resumo':{'referencias_unicas':len(docs),'por_status':dict(por_status),
                      'urls_unicas_por_lado':{k:len(v) for k,v in urls_unicas.items()},
                      'por_categoria':{k:sum(v.values()) for k,v in por_categoria.items()},
                      'por_categoria_e_status':{k:dict(v) for k,v in por_categoria.items()}},
            'referencias':list(docs.values()),
            'nota':'Uma linha por referência ou par observado. Exclusão, documento e inspeção unilateral não comprovam equivalência HTML. URLs e origens são sanitizadas.',
        })

    def _linha(self, par, ident, anterior, diagnostico, politica, terminal, admitida, erros):
        extra = self.referencias.get(par,{})
        prova = self.politicas.get(par,{})
        filtrada = politica.get('excluido',False)
        if terminal:
            status = ESTADOS[terminal]
            motivo = diagnostico.get('motivo','Estado terminal restaurado do checkpoint.')
        elif filtrada and not admitida:
            status,motivo = 'excluida',politica['motivo']
        elif admitida:
            status,motivo = 'admitida','Aguardando processamento na fila admitida.'
        elif diagnostico:
            status = ESTADOS.get(diagnostico.get('estado'),'descoberta')
            motivo = diagnostico.get('motivo','Referência descoberta.')
        else:
            status = extra.get('status',anterior.get('status','descoberta'))
            motivo = extra.get('motivo',anterior.get('motivo','Referência descoberta.'))
        finalidades = politica.get('finalidades',anterior.get('finalidades',[]))
        categoria_filtro = politica.get('categoria',anterior.get('categoria_filtro',''))
        categoria = extra.get('categoria') or next(
            (x for x in finalidades if x!='indeterminada'),anterior.get('categoria','indeterminada'))
        if categoria_filtro in ('outro_portal','paginacao_editorial'):
            categoria = categoria_filtro
        elif categoria_filtro in CATEGORIAS_EDITORIAIS:
            categoria = 'editorial'
        categorias_filtro = {**anterior.get('exclusoes_observadas',{}),**prova.get('exclusoes_observadas',{})}
        origem = diagnostico.get('origem') or extra.get('origem') or prova.get('trilha')
        if isinstance(origem,list) and anterior.get('origem'):
            origem = None
        codigos = set(anterior.get('tipos_falha',()))
        for url in par:
            codigos.update(erros.get(url,()))
            codigos.update(erros.get(_url(url),()))
        evidencias = prova.get('provas',anterior.get('evidencia_utilizada',[]))
        fontes = prova.get('fontes_portal',anterior.get('fontes_portal',[]))
        return {
            'id_referencia':ident,'execucao_id':self.run_id,'url_a':_url(par[0]),'url_b':_url(par[1]),
            'origem':_origem(origem) if origem else anterior.get('origem',_origem(None)),
            'status':status,'motivo':_texto(motivo),'categoria':categoria,'categoria_filtro':categoria_filtro,
            'admitida':admitida or anterior.get('admitida',False),
            'comparacao_html':status=='comparada','estado_terminal':terminal,
            'finalidades':finalidades,'paginacao':[_indices(url) for url in par],
            'excecao_estrutural':politica.get('excecao_estrutural',anterior.get('excecao_estrutural',False)),
            'excecao_estrutural_observada':bool(prova.get('excecao_observada')
                                                   or anterior.get('excecao_estrutural_observada')),
            'preservada_pelo_filtro':not filtrada if politica else anterior.get('preservada_pelo_filtro'),
            'reconsiderada':politica.get('reconsiderado',anterior.get('reconsiderada',False)),
            'motivo_filtro':_texto(politica.get('motivo',anterior.get('motivo_filtro',''))),
            'fases_filtro':politica.get('fases',anterior.get('fases_filtro',[])),
            'exclusoes_observadas':categorias_filtro,
            'evidencia_utilizada':evidencias,'fontes_portal':fontes,
            'evidencia_unilateral':politica.get('evidencia_unilateral',anterior.get('evidencia_unilateral',False)),
            'heuristica':bool(politica or fontes),'inconclusiva':status in ('inconclusiva','sem_contraparte','falha')
                          or categoria=='indeterminada',
            'tipos_falha':sorted(codigos),
        }


def csv_auditoria(doc):
    def seguro(valor):
        if isinstance(valor,(dict,list)):
            valor = json.dumps(valor,ensure_ascii=False,separators=(',',':'))
        if isinstance(valor,str) and valor.lstrip().startswith(('=','+','-','@')):
            return "'"+valor
        return valor

    campos = ('execucao_id','id_referencia','url_a','url_b','id_url_a','id_url_b','origem','status','motivo','categoria','categoria_filtro',
              'admitida','comparacao_html','estado_terminal','finalidades','paginacao','excecao_estrutural',
              'excecao_estrutural_observada','preservada_pelo_filtro','reconsiderada','motivo_filtro','fases_filtro','exclusoes_observadas',
              'evidencia_utilizada','fontes_portal','evidencia_unilateral','heuristica','inconclusiva','tipos_falha')
    stream = StringIO()
    escritor = csv.writer(stream,delimiter=';')
    escritor.writerow(campos)
    yield '\ufeff'+stream.getvalue()
    for registro in doc['referencias']:
        stream.seek(0)
        stream.truncate(0)
        escritor.writerow([seguro(registro.get(k)) for k in campos])
        yield stream.getvalue()
