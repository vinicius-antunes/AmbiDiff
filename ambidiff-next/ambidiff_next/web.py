"""Painel Flask restrito a loopback, com worker cooperativo e proteção de origem."""
from io import BytesIO
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, render_template, request, send_file
from .reporting import export_report, evidence_file


ALLOWED_LABELS={'PRD','HOMOL','DES','LAB'}
ACTIONS={'confirmed','false_positive','editorial','corrected','hidden','pending','select'}


def create_app(data_dir=None,engine_factory=None,store_factory=None):
    app=Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=128_000,JSON_SORT_KEYS=False)
    app.json.ensure_ascii=False
    root=Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent/'data'
    root.mkdir(parents=True,exist_ok=True)
    if store_factory is None:
        from .store import Store
        store_factory=Store
    store=store_factory(root/'next.sqlite3')
    app.extensions['next_store']=store
    app.extensions['next_token']=secrets.token_urlsafe(32)
    workers={};guard=threading.Lock()
    app.extensions['next_workers']=workers

    @app.before_request
    def local_only():
        if request.host.split(':',1)[0].lower() not in ('localhost','127.0.0.1'):abort(403,description='Somente acesso local.')
        origin=request.headers.get('Origin')
        if origin and origin.rstrip('/')!=request.host_url.rstrip('/'):abort(403,description='Origem não autorizada.')
        if request.method not in ('GET','HEAD','OPTIONS'):
            if not secrets.compare_digest(request.headers.get('X-Next-Token',''),app.extensions['next_token']):abort(403,description='Token local necessário.')

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cross-Origin-Resource-Policy']='same-origin'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
        return response

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    def error(response):return jsonify(error=response.description),response.code

    def get_run(run_id):
        try:return store.get_run(run_id)
        except KeyError:abort(404,description='Execução não encontrada.')

    def launch(run_id):
        stop=threading.Event()
        def worker():
            try:
                factory=engine_factory
                if factory is None:
                    from .engine import Engine
                    factory=Engine
                factory(store,root/'evidence'/run_id).run(run_id,stop)
            except Exception:
                # O engine mantém o diagnóstico técnico local. Não expor traceback
                # ou credenciais de uma exceção arbitrária em resposta HTTP.
                if hasattr(store,'update_run'):store.update_run(run_id,status='failed',current='Falha no worker; consulte o diagnóstico local.')
            finally:
                with guard:workers.pop(run_id,None)
        thread=threading.Thread(target=worker,name='ambidiff-next-'+run_id,daemon=True)
        workers[run_id]={'stop':stop,'thread':thread};thread.start()

    @app.get('/')
    def index():return render_template('index.html',token=app.extensions['next_token'])

    @app.get('/api/runs')
    def runs():return jsonify(store.list_runs())

    @app.post('/api/runs')
    def start():
        data=request.get_json(silent=True)
        if not isinstance(data,dict):abort(400,description='Configuração JSON necessária.')
        roots=data.get('roots',[]);labels=data.get('labels',['PRD','HOMOL'])
        if not isinstance(roots,list) or len(roots)!=2:abort(400,description='Informe os dois ambientes.')
        from .policy import normalize_url,safe_url
        try:
            roots=[normalize_url(u) for u in roots]
            if not all(safe_url(u) for u in roots):raise ValueError()
        except (TypeError,ValueError):abort(400,description='Informe URLs HTTP/HTTPS seguras, completas e sem credenciais.')
        if len(set(roots))!=2:abort(400,description='Os ambientes devem ter URLs distintas.')
        if not isinstance(labels,list) or len(labels)!=2 or not all(v in ALLOWED_LABELS for v in labels) or labels[0]==labels[1]:abort(400,description='Rótulos de ambiente inválidos.')
        try:
            capacity=int(data.get('max_pages',100))
            if not 1<=capacity<=1000:raise ValueError()
        except (ValueError,TypeError):abort(400,description='Capacidade deve estar entre 1 e 1.000 pares.')
        viewport=data.get('viewport',{'width':1366,'height':850})
        if not isinstance(viewport,dict) or not all(type(viewport.get(k)) is int and 320<=viewport[k]<=2560 for k in ('width','height')):abort(400,description='Viewport inválido.')
        config={'roots':roots,'labels':labels,'name':str(data.get('name',''))[:100],
                'outdated':str(data.get('outdated','')) if data.get('outdated','') in ('',*labels) else '',
                'max_pages':capacity,'viewport':viewport}
        with guard:
            if workers:abort(409,description='Já existe uma comparação em execução.')
            run_id=store.create_run(config);launch(run_id)
        return jsonify(id=run_id),202

    @app.get('/api/runs/<run_id>')
    def report(run_id):
        get_run(run_id)
        result=store.report(run_id)
        result['worker_active']=run_id in workers
        result['can_resume']=run_id not in workers and result['run'].get('status')!='completed'
        return jsonify(result)

    @app.get('/api/runs/<run_id>/logs')
    def logs(run_id):
        get_run(run_id)
        try:after=max(0,int(request.args.get('after','0')))
        except ValueError:abort(400,description='Cursor inválido.')
        return jsonify(store.logs(run_id,after))

    @app.post('/api/runs/<run_id>/stop')
    def stop(run_id):
        get_run(run_id)
        with guard:
            worker=workers.get(run_id)
            if worker:
                store.interrupt(run_id);worker['stop'].set()
                return jsonify(status='stop_requested',message='Interrupção solicitada — aguardando operação atual'),202
        return jsonify(status=get_run(run_id)['status'],message='Execução já encerrada.'),200

    @app.post('/api/runs/<run_id>/resume')
    def resume(run_id):
        state=get_run(run_id)
        tasks=store.report(run_id).get('tasks',[])
        if state.get('status')=='completed' and not any(t.get('state') in ('pending','running') for t in tasks):abort(409,description='Execução não possui trabalho pendente.')
        with guard:
            if workers:abort(409,description='Já existe uma comparação em execução.')
            launch(run_id)
        return jsonify(id=run_id),202

    @app.post('/api/runs/<run_id>/review')
    def review(run_id):
        get_run(run_id);data=request.get_json(silent=True) or {}
        ids=data.get('ids',[]);action=data.get('action')
        if not isinstance(ids,list) or len(ids)>5000 or not all(isinstance(v,str) and len(v)<100 for v in ids) or action not in ACTIONS:abort(400,description='Revisão inválida.')
        if action=='select' and type(data.get('selected')) is not bool:abort(400,description='Seleção deve ser verdadeira ou falsa.')
        existing={row['id'] for row in store.report(run_id).get('findings',[])}
        if not set(ids)<=existing:abort(400,description='DIV desconhecida nesta comparação.')
        store.review(run_id,ids,action,selected=data.get('selected'))
        return jsonify(ok=True)

    @app.get('/api/runs/<run_id>/export')
    def export(run_id):
        get_run(run_id)
        try:
            result=export_report(store.report(run_id),request.args.get('format','html'),root/'evidence'/run_id,request.args.get('scope','all'))
        except ValueError as exc:abort(400,description=str(exc))
        return send_file(BytesIO(result.data),mimetype=result.mimetype,as_attachment=True,download_name=result.filename,max_age=0)

    @app.get('/api/runs/<run_id>/evidence/<path:name>')
    def evidence(run_id,name):
        get_run(run_id);file=evidence_file(root/'evidence'/run_id,name)
        if file is None:abort(404,description='Evidência não disponível.')
        return send_file(file,mimetype='image/png',max_age=0)

    return app
