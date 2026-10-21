"""Painel Flask local. Relatórios agrupados por site e execução."""
from __future__ import annotations
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import uuid
import webbrowser
from urllib.parse import urlsplit
from flask import Flask,jsonify,render_template,request,send_from_directory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ambidiff.core import executar,validacao_inicial
from ambidiff.reports import exportar
from ambidiff.diagnostics import montar_diagnostico,exportar_diagnostico
from ambidiff.storage import (preparar_relatorio,excluir_div,excluir_execucoes,registrar_revisao,
    atomic_json,valid_run,ler_exclusoes)

app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=12*1024
PASTA=ROOT/'relatorios';PASTA.mkdir(exist_ok=True)
HISTORY_PATH=ROOT/'historico.json'
LOCK=threading.RLock();PARAR=threading.Event()
STATE={'status':'pronto','progresso':0,'logs':[],'ultimo_id':None,'erro':None,'resumo':None,
       'inicio_monotonic':None,'fim_monotonic':None,'amostras_progresso':[]}


def estimar_tempo_restante(amostras,agora,progresso,decorrido,status):
    """ETA aproximado apenas quando há ritmo recente de avanço observável."""
    if status!='executando' or not 10<=progresso<85 or decorrido<30:
        return None
    if len(amostras)<2 or agora-amostras[-1][0]>90:
        return None
    recentes=[(t,p) for t,p in amostras if agora-t<=120]
    if len(recentes)<2:
        return None
    t0,p0=recentes[0]
    t1,p1=recentes[-1]
    if t1-t0<20 or p1-p0<2:
        return None
    taxa=(p1-p0)/(t1-t0)
    restante=(100-progresso)/taxa
    return round(restante) if 1<=restante<=6*3600 else None


def atualizar_progresso(valor):
    with LOCK:
        if STATE['status']!='executando':
            return
        novo=min(99,max(0,round(float(valor)*100)))
        if novo>STATE['progresso']:
            STATE['progresso']=novo
            STATE['amostras_progresso'].append((time.monotonic(),novo))
            STATE['amostras_progresso']=STATE['amostras_progresso'][-90:]


def atualizar(**kw):
    with LOCK:
        if kw.get('status') in ('concluido','erro','interrompido'):
            STATE['fim_monotonic']=time.monotonic()
        STATE.update(kw)


def estado_publico(agora=None):
    with LOCK:
        dados={k:v for k,v in STATE.items() if k not in
               ('inicio_monotonic','fim_monotonic','amostras_progresso')}
        dados['logs']=list(STATE['logs'])
        inicio=STATE['inicio_monotonic']
        if inicio is None:
            dados['tempo_decorrido_segundos']=None
            dados['tempo_restante_segundos']=None
        else:
            agora=time.monotonic() if agora is None else agora
            fim=STATE['fim_monotonic'] if STATE['fim_monotonic'] is not None else agora
            decorrido=max(0,int(fim-inicio))
            dados['tempo_decorrido_segundos']=decorrido
            dados['tempo_restante_segundos']=estimar_tempo_restante(
                STATE['amostras_progresso'],agora,dados['progresso'],decorrido,dados['status'])
        return dados


def log(msg):
    with LOCK:
        STATE['logs'].append(str(msg)[:700]);STATE['logs']=STATE['logs'][-200:]


def _hist():
    try:
        h=json.loads(HISTORY_PATH.read_text(encoding='utf-8')) if HISTORY_PATH.exists() else []
        return h if isinstance(h,list) else []
    except (OSError,ValueError):return []


def worker(params,run_id):
    try:
        resultado=executar(params['url_a'],params['url_b'],params['nome_a'],params['nome_b'],
                           PARAR,log,atualizar_progresso,
                           site_nome=params['site_nome'], evidencias_dir=PASTA/f'evidencias_{run_id}',
                           auditar_externos=params['auditar_externos'],
                           verificar_cliques=params.get('verificar_cliques',False),
                           varredura_inteligente=params.get('varredura_inteligente',False),
                           ambiente_desatualizado=params.get('ambiente_desatualizado',''),
                           checkpoint=lambda d:atomic_json(PASTA/f'checkpoint_{run_id}.json',d))
        if resultado is None:
            raise RuntimeError('A varredura não produziu relatório; consulte o diagnóstico.')
        resultado['gerado_em']=datetime.now().strftime('%d/%m/%Y %H:%M:%S');resultado['id']=run_id
        chave=params['url_a'].split('//',1)[-1].split('/',1)[0].lower()+'/'+urlsplit(params['url_a']).path.strip('/')
        resultado['site_id']=hashlib.sha256(chave.encode('utf-8')).hexdigest()[:16]
        exportar(resultado,PASTA,run_id)
        exportar_diagnostico(montar_diagnostico(resultado,list(STATE.get('logs',[]))),PASTA,run_id)
        if not PARAR.is_set():
            (PASTA/f'checkpoint_{run_id}.json').unlink(missing_ok=True)
        entrada={'id':run_id,'data':resultado['gerado_em'],'site_nome':resultado['site_nome'],
                 'site_id':resultado['site_id'],'ambientes':resultado['ambientes'],
                 'situacao':resultado['situacao_analise'],'modo_varredura':resultado.get('modo_varredura','atual'),
                 'total':len(resultado['divergencias']), 'ocorrencias_brutas':resultado.get('ocorrencias_brutas',len(resultado['divergencias'])),
                 'avisos':sum(r['quantidade'] for r in resultado['avisos_tecnicos']),
                 'paginas':resultado['paginas'],
                 'variacoes_dados':len(resultado.get('variacoes_dados',[])),
                 'ambiente_desatualizado':resultado.get('ambiente_desatualizado','')}
        with LOCK:
            h=_hist();h.insert(0,entrada)
            atomic_json(HISTORY_PATH,h[:350])
        atualizar(status='concluido',progresso=100,ultimo_id=run_id,erro=None,
                  resumo={'total':entrada['total'],'paginas':entrada['paginas'],
                          'situacao':entrada['situacao'],'nome':entrada['site_nome']})
        log(f'Finalizado ({entrada["situacao"]}): {entrada["total"]} diferenças de conteúdo; '
            f'{entrada["avisos"]} avisos técnicos.')
    except Exception as ex:
        import traceback
        log('ERRO: '+str(ex)[:500])
        cp=PASTA/f'checkpoint_{run_id}.json'
        try:
            if cp.exists():
                from ambidiff.paired import agrupar_registros
                snap=json.loads(cp.read_text(encoding='utf-8'))
                brutos=snap.pop('brutos',[]);var=snap.pop('variacoes_editoriais',[])
                parcial={**snap,'versao':'1.5','situacao_analise':'parcial',
                   'completo':{k:False for k in snap.get('ambientes',{})},
                   'divergencias':agrupar_registros(brutos),
                   'variacoes_dados':[], 'itens_editoriais_agrupados':len(var),
                   'avisos_tecnicos':[],'referencias_pendentes':[],
                   'ocorrencias_brutas':len(brutos)+len(var),
                   'motivo_recuperacao':'Recuperação do último checkpoint: '+str(ex)[:250]}
                parcial['gerado_em']=datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                parcial['id']=run_id
                chave=params['url_a'].split('//',1)[-1].split('/',1)[0].lower()+'/'+urlsplit(params['url_a']).path.strip('/')
                parcial['site_id']=hashlib.sha256(chave.encode()).hexdigest()[:16]
                exportar(parcial,PASTA,run_id)
                diag=montar_diagnostico(parcial,list(STATE.get('logs',[])))
                diag['erro_critico']=str(ex)[:600]
                exportar_diagnostico(diag,PASTA,run_id)
                with LOCK:
                    h=_hist();h.insert(0,{'id':run_id,'data':parcial['gerado_em'],'site_nome':parcial['site_nome'],
                       'site_id':parcial['site_id'],'ambientes':parcial['ambientes'],'situacao':'parcial',
                       'total':len(parcial['divergencias']),'avisos':len(parcial.get('falhas',[])),
                       'paginas':parcial.get('paginas',{})})
                    atomic_json(HISTORY_PATH,h[:350])
                log('Último checkpoint recuperado. Relatório parcial e diagnóstico salvos.')
                atualizar(status='concluido',progresso=100,ultimo_id=run_id,erro=None)
                cp.unlink(missing_ok=True)
                return
            diag={'versao':'1.5','site_nome':params.get('site_nome',''),'situacao_analise':'erro',
                 'interrupcao':{'ocorreu':True,'motivos':{'programa':'Falha inesperada'},'pares_visitados':0,'pares_na_fila':0},
                 'falhas_por_tipo':{'FALHA_CRITICA':1},'falhas':[{'ambiente':'programa','url':'', 'erro':str(ex)[:600]}],
                 'eventos':[],'mensagens_de_execucao':list(STATE.get('logs',[])),
                 'erro_critico':traceback.format_exc()[-2000:]}
            exportar_diagnostico(diag,PASTA,run_id)
        except Exception as falha_diag:log('Falha ao gravar diagnóstico: '+str(falha_diag)[:120])
        atualizar(status='erro',erro=str(ex)[:550],ultimo_id=run_id)


@app.get('/')
def index():return render_template('index.html')


@app.get('/api/status')
def status():
    return jsonify(estado_publico())


@app.post('/api/comparar')
def comparar():
    args=request.get_json(silent=True) or {}
    with LOCK:
        if STATE['status']=='executando':return jsonify(erro='Já existe uma comparação em andamento.'),409
        try:
            url_a,url_b=validacao_inicial(str(args.get('url_a','')).strip(),str(args.get('url_b','')).strip())
            nome_a=re.sub(r'[^A-Za-z0-9_-]','',str(args.get('nome_a','PRD')).upper())[:12] or 'PRD'
            nome_b=re.sub(r'[^A-Za-z0-9_-]','',str(args.get('nome_b','LAB')).upper())[:12] or 'LAB'
            if nome_a==nome_b:raise ValueError('Use nomes de ambientes diferentes.')
            site_nome=str(args.get('site_nome','')).strip()[:120]
            if any(ord(c)<32 for c in site_nome):raise ValueError('Nome da comparação inválido.')
            desatualizado=str(args.get('ambiente_desatualizado','')).strip().upper()
            if desatualizado not in ('',nome_a,nome_b):raise ValueError('Escolha um ambiente válido para a base desatualizada.')
        except (ValueError,TypeError) as e:return jsonify(erro=str(e)),400
        PARAR.clear()
        inicio=time.monotonic()
        STATE.update(status='executando',progresso=0,logs=['Iniciando Chromium...'],
                     erro=None,resumo=None,ultimo_id=None,
                     inicio_monotonic=inicio,fim_monotonic=None,
                     amostras_progresso=[(inicio,0)])
        run_id=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
        params=dict(url_a=url_a,url_b=url_b,nome_a=nome_a,nome_b=nome_b,site_nome=site_nome,
                    auditar_externos=(args.get('auditar_externos') is True),
                    verificar_cliques=(args.get('verificar_cliques') is True),
                    varredura_inteligente=(args.get('varredura_inteligente') is True),
                    ambiente_desatualizado=desatualizado)
        threading.Thread(target=worker,args=(params,run_id),daemon=True).start()
        return jsonify(ok=True,id=run_id)


@app.post('/api/parar')
def parar():PARAR.set();return jsonify(ok=True)


@app.get('/api/historico')
def historico():return jsonify(_hist())


@app.get('/api/relatorio/<run_id>')
def relatorio(run_id):
    if not valid_run(run_id):return jsonify(erro='ID inválido'),400
    try:return jsonify(preparar_relatorio(PASTA,run_id))
    except FileNotFoundError:return jsonify(erro='Relatório não encontrado'),404


@app.get('/evidencia/<run_id>/<nome>')
def evidencia(run_id,nome):
    if not valid_run(run_id):
        return jsonify(erro='ID inválido'),400
    if not re.fullmatch(r'DIV-[0-9]{4,5}(?:_(?:PRD|DES|LAB))?\.png',nome):
        return jsonify(erro='Nome inválido'),400
    return send_from_directory(PASTA/f'evidencias_{run_id}',nome,as_attachment=False)


@app.put('/api/relatorio/<run_id>/divergencias/<div_id>/revisao')
def revisar_div(run_id,div_id):
    if not valid_run(run_id):return jsonify(erro='ID inválido'),400
    situacao=(request.get_json(silent=True) or {}).get('situacao')
    try:
        with LOCK:
            if STATE['status']=='executando':return jsonify(erro='Aguarde a conclusão.'),409
            report=registrar_revisao(PASTA,run_id,div_id,situacao,LOCK)
        return jsonify(ok=True,revisoes=report.get('revisoes_manuais',{}))
    except ValueError as e:return jsonify(erro=str(e)),400
    except (KeyError,FileNotFoundError):return jsonify(erro='Relatório ou DIV não encontrada.'),404


@app.put('/api/relatorio/<run_id>/divergencias/<div_id>/relevancia')
def relevancia(run_id,div_id):
    from ambidiff.storage import reclassificar
    if not valid_run(run_id):return jsonify(erro='ID inválido'),400
    try:
        with LOCK:
            if STATE['status']=='executando':return jsonify(erro='Aguarde a conclusão.'),409
            reclassificar(PASTA,run_id,div_id,(request.get_json(silent=True) or {}).get('classe'))
        return jsonify(ok=True)
    except ValueError as e:return jsonify(erro=str(e)),400
    except (KeyError,FileNotFoundError):return jsonify(erro='Relatório ou DIV não encontrada.'),404


@app.get('/download/<run_id>/<ext>')
def baixar(run_id,ext):
    if not valid_run(run_id) or ext not in ('csv','json','html','diagnostico-json','diagnostico-txt'):
        return jsonify(erro='Arquivo inválido'),400
    try:
        if ext=='diagnostico-json':
            with LOCK:
                dados=preparar_relatorio(PASTA,run_id)
                path=PASTA/f'diagnostico_{run_id}.json'
                diag=json.loads(path.read_text(encoding='utf-8')) if path.exists() else montar_diagnostico(dados)
                diag.update(diferencas_completas=dados['divergencias'],editoriais=dados.get('editoriais_preservados',[]),resumo_relevancia=dados.get('resumo_relevancia',{}))
            response=jsonify(diag)
            response.headers['Content-Disposition']=f'attachment; filename="diagnostico_{run_id}.json"'
            return response
        if ext=='diagnostico-txt':
            nome=(f'diagnostico_{run_id}.json' if ext=='diagnostico-json' else f'log_{run_id}.txt')
            return send_from_directory(PASTA,nome,as_attachment=True)
        # Recria a exportação filtrada sem alterar o relatório bruto.
        with LOCK:
            dados=preparar_relatorio(PASTA,run_id)
            if request.args.get('completo')=='1':dados['exportacao_completa']=True
            exportar(dados,PASTA,'filtrado_'+run_id)
            nome=f'comparacao_filtrado_{run_id}.{ext}'
        return send_from_directory(PASTA,nome,as_attachment=True)
    except FileNotFoundError:return jsonify(erro='Relatório não encontrado'),404


@app.delete('/api/relatorio/<run_id>/divergencias/<div_id>')
def remover_div(run_id,div_id):
    if not valid_run(run_id):return jsonify(erro='Relatório inválido'),400
    try:
        with LOCK:
            if STATE['status']=='executando':return jsonify(erro='Aguarde a conclusão da comparação.'),409
        novo=excluir_div(PASTA,run_id,div_id,LOCK)
        with LOCK:
            h=_hist()
            for row in h:
                if row['id']==run_id:row['total']=len(novo['divergencias'])
            atomic_json(HISTORY_PATH,h)
        return jsonify(ok=True,total=len(novo['divergencias']),ocultadas=novo['divergencias_ocultadas'])
    except ValueError as e:return jsonify(erro=str(e)),400
    except (KeyError,FileNotFoundError):return jsonify(erro='Divergência ou relatório não encontrado.'),404


@app.post('/api/relatorios/excluir')
def remover_relatorios():
    args=request.get_json(silent=True) or {}
    ids=args.get('ids')
    with LOCK:
        if STATE['status']=='executando':return jsonify(erro='Aguarde a conclusão da comparação.'),409
        try:
            count=excluir_execucoes(PASTA,HISTORY_PATH,ids,LOCK)
            if STATE.get('ultimo_id') in ids:
                STATE['ultimo_id']=None;STATE['resumo']=None
            return jsonify(ok=True,excluidos=count)
        except ValueError as e:return jsonify(erro=str(e)),400
        except (KeyError,FileNotFoundError):return jsonify(erro='Um dos relatórios não foi encontrado.'),404



if __name__=='__main__':
    import time
    port=int(os.getenv('AMBIDIFF_PORT','8765'))
    print(f'AmbiDiff em http://127.0.0.1:{port}')
    def abrir():
        time.sleep(1);webbrowser.open(f'http://127.0.0.1:{port}')
    threading.Thread(target=abrir,daemon=True).start()
    app.run(host='127.0.0.1',port=port,threaded=True,debug=False)
