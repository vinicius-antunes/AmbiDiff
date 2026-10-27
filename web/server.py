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
from flask import Flask,jsonify,render_template,request,send_from_directory,send_file

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ambidiff.core import executar,validacao_inicial
from ambidiff.reports import exportar
from ambidiff.checkpoints import gravar as gravar_checkpoint
from ambidiff.diagnostics import montar_diagnostico,exportar_diagnostico
from ambidiff.storage import (preparar_relatorio,excluir_div,excluir_execucoes,registrar_revisao,
    atomic_json,valid_run,ler_exclusoes)

app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=12*1024
PASTA=ROOT/'relatorios';PASTA.mkdir(exist_ok=True)
HISTORY_PATH=ROOT/'historico.json'
from ambidiff.live import Logs
FEED=Logs()
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
        if kw.get('status') in ('concluido','parcial','erro','interrompido'):
            STATE['fim_monotonic']=time.monotonic()
        STATE.update(kw)


def estado_publico(agora=None):
    with LOCK:
        dados={k:v for k,v in STATE.items() if k not in
               ('inicio_monotonic','fim_monotonic','amostras_progresso','amostras_pares','andamento_monotonic')}
        dados['logs']=list(STATE['logs'])
        dados['interrupcao_solicitada']=PARAR.is_set() and dados['status']=='executando'
        d=STATE.get('andamento',{})
        restante=d.get('orcamento_restante_segundos')
        if isinstance(restante,(int,float)) and dados['status']=='executando':
            instante=time.monotonic() if agora is None else agora
            restante=max(0,restante-max(0,instante-STATE.get('andamento_monotonic',instante)))
        dados['orcamento_restante_segundos']=restante
        total=d.get('pares_visitados',0)+d.get('pares_pendentes',0)
        dados['cobertura_conhecida_percentual']=min(99 if dados['status']!='concluido' else 100,round(100*d.get('pares_visitados',0)/total)) if total else None
        dados['progresso_semantica']='Fila descoberta até o momento, não conclusão global nem inspeção profunda'
        dados['servidor_agora']=datetime.now().astimezone().isoformat()
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
        if STATE.get('andamento'):
            amostras=STATE.get('amostras_pares',[])
            dados['tempo_restante_segundos']=None
            d=STATE['andamento']
            if dados['status']=='executando' and d.get('etapa') not in ('capturas','processamento_final','auditoria') and len(amostras)>=3:
                t0,n0=amostras[0];t1,n1=amostras[-1]
                if t1-t0>=10 and n1>n0 and time.monotonic()-t1<30:
                    dados['tempo_restante_segundos']=round(d.get('pares_pendentes',0)*(t1-t0)/(n1-n0)) or None
        return dados


def log(msg):
    with LOCK:
        texto=str(msg)[:700]
        STATE['logs'].append(texto);STATE['logs']=STATE['logs'][-200:]
        FEED.adicionar(texto)
        rid=STATE.get('execucao_id')
        if rid and valid_run(rid):
            try:
                with (PASTA/f'execucao_{rid}.log').open('a',encoding='utf-8') as out:out.write(texto+'\n')
            except OSError as exc:STATE['falha_log_completo']=str(exc)[:180]


def andamento(dados):
    with LOCK:
        anterior=STATE.get('andamento',{})
        agora=time.monotonic();samples=STATE.setdefault('amostras_pares',[])
        if dados.get('pares_pendentes',0)>anterior.get('pares_pendentes',0):samples.clear()
        if dados.get('pares_comparados',0)>anterior.get('pares_comparados',0):samples.append((agora,dados['pares_comparados']))
        STATE['amostras_pares']=samples[-30:]
        STATE['andamento']=dict(dados);STATE['andamento_monotonic']=agora



def _hist():
    try:
        h=json.loads(HISTORY_PATH.read_text(encoding='utf-8')) if HISTORY_PATH.exists() else []
        return h if isinstance(h,list) else []
    except (OSError,ValueError):return []


def percentual_final(resultado,status):
    if status=='concluido':return 100
    d=resultado.get('andamento',{})
    total=d.get('pares_descobertos',0)
    return min(99,round(100*d.get('pares_comparados',0)/total)) if total else 0


def worker(params,run_id):
    inicio_worker=time.monotonic();inicio_iso=datetime.now().astimezone().isoformat()
    try:
        resultado=executar(params['url_a'],params['url_b'],params['nome_a'],params['nome_b'],
                           PARAR,log,atualizar_progresso,observador=andamento,
                           site_nome=params['site_nome'], evidencias_dir=PASTA/f'evidencias_{run_id}',
                           auditar_externos=params['auditar_externos'],
                           verificar_cliques=params.get('verificar_cliques',False),
                           varredura_inteligente=params.get('varredura_inteligente',False),
                           ambiente_desatualizado=params.get('ambiente_desatualizado',''),
                           checkpoint=lambda d:gravar_checkpoint(PASTA/f'checkpoint_{run_id}.json',dict(d,id=run_id)),
                           estrategia=params.get('estrategia'),orcamento_minutos=params.get('orcamento_minutos'),
                           **({'retomada':params['retomada']} if params.get('retomada') else {}))
        if resultado is None:
            raise RuntimeError('A varredura não produziu relatório; consulte o diagnóstico.')
        if params.get('retomada_de'):resultado['retomada_de']=params['retomada_de']
        resultado['formato_compacto']=True
        resultado['gerado_em']=datetime.now().strftime('%d/%m/%Y %H:%M:%S');resultado['id']=run_id
        chave=params['url_a'].split('//',1)[-1].split('/',1)[0].lower()+'/'+urlsplit(params['url_a']).path.strip('/')
        resultado['site_id']=hashlib.sha256(chave.encode('utf-8')).hexdigest()[:16]
        inicio_exportacao=time.monotonic()
        exportar(resultado,PASTA,run_id)
        resultado['exportacao_worker_segundos']=time.monotonic()-inicio_exportacao
        exportar_diagnostico(montar_diagnostico(resultado,list(STATE.get('logs',[]))),PASTA,run_id)
        cobertura=resultado.get('cobertura',{})
        if not PARAR.is_set() and not resultado.get('andamento',{}).get('pares_pendentes') and not (cobertura.get('teto_atingido') or cobertura.get('referencias_nao_admitidas')):
            (PASTA/f'checkpoint_{run_id}.json').unlink(missing_ok=True)
        from ambidiff.sections import agrupar_documentos
        total_agrupado=len(agrupar_documentos(resultado['divergencias']))
        entrada={'id':run_id,'data':resultado['gerado_em'],'site_nome':resultado['site_nome'],
                 'site_id':resultado['site_id'],'ambientes':resultado['ambientes'],
                 'situacao':resultado['situacao_analise'],'modo_varredura':resultado.get('modo_varredura','atual'),
                 'total':total_agrupado, 'ocorrencias_brutas':resultado.get('ocorrencias_brutas',len(resultado['divergencias'])),
                 'avisos':sum(r['quantidade'] for r in resultado['avisos_tecnicos']),
                 'paginas':resultado['paginas'],
                 'variacoes_dados':len(resultado.get('variacoes_dados',[])),
                 'ambiente_desatualizado':resultado.get('ambiente_desatualizado','')}
        with LOCK:
            h=_hist();h.insert(0,entrada)
            atomic_json(HISTORY_PATH,h[:350])
        final='interrompido' if resultado.get('estado_execucao')=='interrompido' else 'concluido' if resultado.get('situacao_analise')=='concluido' else 'parcial'
        atualizar(status=final,progresso=percentual_final(resultado,final),andamento=resultado.get('andamento',{}),ultimo_id=run_id,erro=None,relatorio_disponivel=True,
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
                from ambidiff.checkpoints import recuperar
                snap=recuperar(json.loads(cp.read_text(encoding='utf-8')))
                parcial={**snap,'formato_compacto':True,'versao':'1.5','situacao_analise':'parcial',
                   'completo':{k:False for k in snap.get('ambientes',{})},
                   'estado_execucao':'falha','erro_execucao':str(ex)[:550],
                   'motivo_recuperacao':'Recuperação do último checkpoint: '+str(ex)[:250]}
                parcial['andamento']['etapa']='falha'
                for meta in parcial.get('meta_varredura',{}).values():meta['motivo_parada']='Falha da automação: '+str(ex)[:200]
                parcial['duracao_no_checkpoint_segundos']=snap.get('duracao_segundos')
                parcial['iniciado_em']=snap.get('iniciado_em',inicio_iso)
                parcial['finalizado_em']=datetime.now().astimezone().isoformat()
                parcial['duracao_segundos']=round(time.monotonic()-inicio_worker+params.get('retomada',{}).get('estado',{}).get('duracao_acumulada',0),6)
                parcial['registros_editoriais']=snap.get('registros_editoriais',[])
                parcial['gerado_em']=datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                parcial['id']=run_id
                parcial['site_nome']=parcial.get('site_nome') or urlsplit(params['url_a']).hostname or 'Portal'
                chave=params['url_a'].split('//',1)[-1].split('/',1)[0].lower()+'/'+urlsplit(params['url_a']).path.strip('/')
                parcial['site_id']=hashlib.sha256(chave.encode()).hexdigest()[:16]
                if (PASTA/f'comparacao_{run_id}.json').exists():atomic_json(PASTA/f'recuperacao_{run_id}.json',parcial)
                else:exportar(parcial,PASTA,run_id)
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
                atualizar(status='erro',progresso=percentual_final(parcial,'erro'),ultimo_id=run_id,erro=str(ex)[:550],andamento=parcial['andamento'],relatorio_parcial=True,relatorio_disponivel=True)
                # Checkpoint conservado para diagnosticar a falha original.
                return
            diag={'iniciado_em':inicio_iso,'finalizado_em':datetime.now().astimezone().isoformat(),
                 'duracao_segundos':round(time.monotonic()-inicio_worker,6),'grau_confianca':'falha_automacao','versao':'1.5','site_nome':params.get('site_nome',''),'situacao_analise':'erro',
                 'interrupcao':{'ocorreu':True,'motivos':{'programa':'Falha inesperada'},'pares_visitados':0,'pares_na_fila':0},
                 'falhas_por_tipo':{'FALHA_CRITICA':1},'falhas':[{'ambiente':'programa','url':'', 'erro':str(ex)[:600]}],
                 'eventos':[],'mensagens_de_execucao':list(STATE.get('logs',[])),
                 'erro_critico':traceback.format_exc()[-2000:]}
            exportar_diagnostico(diag,PASTA,run_id)
        except Exception as falha_diag:log('Falha ao gravar diagnóstico: '+str(falha_diag)[:120])
        atualizar(status='erro',erro=str(ex)[:550],ultimo_id=run_id,relatorio_disponivel=(PASTA/f'comparacao_{run_id}.json').exists())


@app.get('/')
def index():return render_template('index.html')


@app.get('/api/status')
def status():
    try:cursor=max(0,int(request.args.get('cursor','0')))
    except ValueError:return jsonify(erro='Cursor inválido'),400
    with LOCK:
        inicio=STATE.get('execucao_log_inicio',0)
        feed=FEED.consultar(max(cursor,inicio))
        if FEED.eventos and max(cursor,inicio)<FEED.eventos[0]['id']-1:feed['lacuna_logs']=True
        return jsonify({**estado_publico(),**feed})


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
            from ambidiff.strategy import opcoes
            estrategia,orcamento=opcoes(args.get('estrategia','dinamica'),args.get('orcamento_minutos',0))
            desatualizado=str(args.get('ambiente_desatualizado','')).strip().upper()
            if desatualizado not in ('',nome_a,nome_b):raise ValueError('Escolha um ambiente válido para a base desatualizada.')
        except (ValueError,TypeError) as e:return jsonify(erro=str(e)),400
        PARAR.clear()
        inicio=time.monotonic()
        STATE.update(status='executando',progresso=0,logs=[],
                     erro=None,resumo=None,ultimo_id=None,relatorio_disponivel=False,relatorio_parcial=False,
                     inicio_monotonic=inicio,fim_monotonic=None,
                     amostras_progresso=[(inicio,0)])
        run_id=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
        FEED.eventos.clear()
        STATE.update(execucao_id=run_id,execucao_log_inicio=FEED.seq,andamento={},amostras_pares=[],falha_log_completo=None)
        log('Iniciando Chromium...')
        params=dict(url_a=url_a,url_b=url_b,nome_a=nome_a,nome_b=nome_b,site_nome=site_nome,
                    auditar_externos=(args.get('auditar_externos') is True),
                    verificar_cliques=(args.get('verificar_cliques') is True),
                    varredura_inteligente=(args.get('varredura_inteligente',True) is True),
                    estrategia=estrategia,orcamento_minutos=orcamento,ambiente_desatualizado=desatualizado)
        threading.Thread(target=worker,args=(params,run_id),daemon=True).start()
        return jsonify(ok=True,id=run_id)


@app.get('/api/checkpoints')
def checkpoints_disponiveis():
    from ambidiff.checkpoints import validar
    rows=[]
    for path in sorted(PASTA.glob('checkpoint_*.json'),reverse=True):
        rid=path.stem.removeprefix('checkpoint_')
        if not valid_run(rid):continue
        try:
            payload=json.loads(path.read_text(encoding='utf-8'))
            estado=validar(payload.get('retomada',{}))
            if estado['fila']:rows.append({'id':rid,'pendentes':len(estado['fila']),
                'site_nome':estado['configuracao'].get('site_nome',''),'configuracao':estado['configuracao'],'salvo_em':payload['retomada']['salvo_em'],'valido':True})
        except (ValueError,TypeError,KeyError,OSError) as exc:
            rows.append({'id':rid,'valido':False,'motivo':str(exc)[:180]})
    return jsonify(rows)


@app.post('/api/retomar/<run_id>')
def retomar(run_id):
    from ambidiff.checkpoints import validar
    if not valid_run(run_id):return jsonify(erro='ID inválido'),400
    with LOCK:
        if STATE['status']=='executando':return jsonify(erro='Já existe uma comparação em andamento.'),409
        try:
            payload=json.loads((PASTA/f'checkpoint_{run_id}.json').read_text(encoding='utf-8'))
            estado=validar(payload.get('retomada',{}))
            if not estado['fila']:raise ValueError('Checkpoint sem pares pendentes.')
            params=dict(estado['configuracao'],retomada=payload['retomada'],retomada_de=run_id)
            args=request.get_json(silent=True) or {}
            # Atualiza checkpoints antigos sem pausar por tempo ou amostragem.
            params['estrategia']='dinamica';params['orcamento_minutos']=0
            if 'orcamento_minutos' in args:
                from ambidiff.strategy import opcoes
                _,params['orcamento_minutos']=opcoes(params.get('estrategia','profunda'),args['orcamento_minutos'])
            novo=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
            # Nova execução: preserva arquivos e decisões do relatório anterior.
            for prefix in ('exclusoes','relevancia','revisoes','selecoes'):
                origem=PASTA/f'{prefix}_{run_id}.json'
                if origem.exists():atomic_json(PASTA/f'{prefix}_{novo}.json',json.loads(origem.read_text(encoding='utf-8')))
            atomic_json(PASTA/f'checkpoint_{novo}.json',dict(payload,id=novo,retomada_de=run_id))
        except FileNotFoundError:return jsonify(erro='Checkpoint não encontrado.'),404
        except (ValueError,TypeError,KeyError,OSError) as exc:return jsonify(erro='Retomada recusada: '+str(exc)[:220]),400
        PARAR.clear();inicio=time.monotonic();FEED.eventos.clear()
        STATE.update(status='executando',progresso=0,logs=[],erro=None,resumo=None,ultimo_id=None,relatorio_disponivel=False,relatorio_parcial=False,
            inicio_monotonic=inicio-estado['duracao_acumulada'],fim_monotonic=None,amostras_progresso=[],
            execucao_id=novo,execucao_log_inicio=FEED.seq,andamento={},amostras_pares=[],falha_log_completo=None)
        log('Retomando checkpoint '+run_id+' em nova execução '+novo)
        threading.Thread(target=worker,args=(params,novo),daemon=True).start()
        return jsonify(ok=True,id=novo,retomada_de=run_id)


@app.post('/api/parar')
def parar():
    with LOCK:
        if STATE['status']=='executando':PARAR.set()
    return jsonify(ok=True,interrupcao_solicitada=PARAR.is_set())


@app.get('/api/execucao/<run_id>/logs')
def logs_completos(run_id):
    if not valid_run(run_id):return jsonify(erro='ID inválido'),400
    return send_from_directory(PASTA,f'execucao_{run_id}.log',as_attachment=True)


@app.get('/api/historico')
def historico():return jsonify(_hist())


@app.get('/api/relatorio/<run_id>')
def relatorio(run_id):
    if not valid_run(run_id):return jsonify(erro='ID inválido'),400
    try:return jsonify(preparar_relatorio(PASTA,run_id,detalhes=request.args.get('leve')!='1'))
    except FileNotFoundError:return jsonify(erro='Relatório não encontrado'),404
    except ValueError as exc:return jsonify(erro=str(exc)),400


@app.get('/evidencia/<run_id>/<nome>')
def evidencia(run_id,nome):
    if not valid_run(run_id):
        return jsonify(erro='ID inválido'),400
    if not re.fullmatch(r'DIV-[0-9]{4,5}(?:_(?:PRD|DES|LAB))?\.png',nome):
        return jsonify(erro='Nome inválido'),400
    return send_from_directory(PASTA/f'evidencias_{run_id}',nome,as_attachment=False)


@app.get('/api/relatorio/<run_id>/detalhes')
def detalhes_relatorio(run_id):
    if not valid_run(run_id):return jsonify(erro='ID inválido'),400
    try:
        from ambidiff.compact import separar
        _,detalhes=separar(preparar_relatorio(PASTA,run_id))
        return jsonify(detalhes)
    except FileNotFoundError:return jsonify(erro='Relatório não encontrado.'),404
    except ValueError as exc:return jsonify(erro=str(exc)),400


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


@app.put('/api/relatorio/<run_id>/selecao/<div_id>')
def selecionar_div(run_id,div_id):
    from ambidiff.storage import selecionar
    if not valid_run(run_id):return jsonify(erro='ID inválido.'),400
    try:
        with LOCK:
            if STATE['status']=='executando':return jsonify(erro='Aguarde a conclusão.'),409
            ids=selecionar(PASTA,run_id,div_id,(request.get_json(silent=True) or {}).get('selecionado'))
        return jsonify(ids_selecionados=ids)
    except ValueError as exc:return jsonify(erro=str(exc)),400
    except (KeyError,FileNotFoundError):return jsonify(erro='DIV não encontrada.'),404


@app.put('/api/relatorio/<run_id>/selecao')
def selecionar_divs_lote(run_id):
    from ambidiff.storage import selecionar_lote
    if not valid_run(run_id):return jsonify(erro='ID inválido.'),400
    args=request.get_json(silent=True)
    if not isinstance(args,dict) or set(args)-{'acao','filtros'}:return jsonify(erro='Operação em lote inválida.'),400
    try:
        with LOCK:
            if STATE['status']=='executando':return jsonify(erro='Aguarde a conclusão.'),409
            dados=selecionar_lote(PASTA,run_id,args.get('acao'),args.get('filtros'))
        return jsonify(dados)
    except (ValueError,TypeError) as exc:return jsonify(erro=str(exc)),400
    except FileNotFoundError:return jsonify(erro='Relatório não encontrado.'),404
    except OSError:return jsonify(erro='Não foi possível salvar a seleção. A seleção anterior foi preservada.'),500


@app.get('/download/<run_id>/<ext>')
def baixar(run_id,ext):
    if not valid_run(run_id) or ext not in ('csv','json','html','pdf','diagnostico-json','diagnostico-txt'):
        return jsonify(erro='Arquivo inválido'),400
    try:
        from ambidiff.exports import nome_amigavel,gerar_pdf
        escopo='selecionadas' if request.args.get('selecionadas')=='1' else 'completo'
        if ext=='diagnostico-json':
            with LOCK:
                dados=preparar_relatorio(PASTA,run_id)
                path=PASTA/f'diagnostico_{run_id}.json'
                diag=json.loads(path.read_text(encoding='utf-8')) if path.exists() else montar_diagnostico(dados)
                diag.update(diferencas_completas=dados['divergencias'],editoriais=dados.get('editoriais_preservados',[]),resumo_relevancia=dados.get('resumo_relevancia',{}))
            response=jsonify(diag)
            response.headers['Content-Disposition']='attachment; filename="'+nome_amigavel(dados.get('site_nome'),ext,escopo,run_id)+'"'
            return response
        if ext=='diagnostico-txt':
            nome=(f'diagnostico_{run_id}.json' if ext=='diagnostico-json' else f'log_{run_id}.txt')
            return send_from_directory(PASTA,nome,as_attachment=True,download_name=nome_amigavel(preparar_relatorio(PASTA,run_id).get('site_nome'),ext,escopo,run_id))
        # Recria a exportação filtrada sem alterar o relatório bruto.
        with LOCK:
            dados=preparar_relatorio(PASTA,run_id)
            dados['formato_compacto']=False;dados['formato_relatorio']=1;dados.pop('detalhes_locais',None)
            if request.args.get('completo')=='1':dados['exportacao_completa']=True
            if request.args.get('relevantes')=='1':
                dados['divergencias']=[r for r in dados['divergencias'] if r.get('classificacao')=='relevante']
                dados.pop('registros_originais',None)
                dados['escopo_exportacao']='Somente relevantes'
            if escopo=='selecionadas':
                from ambidiff.storage import somente_selecionadas
                dados=somente_selecionadas(dados,set(dados.get('ids_selecionados',[])))
                if not dados['divergencias']:return jsonify(erro='Selecione ao menos uma DIV visível para exportar.'),400
            else:dados['escopo_exportacao']='Relatório completo' if dados.get('exportacao_completa') else dados.get('escopo_exportacao','Relatório principal')
        # Snapshot separado do lock da varredura; conversão lenta não bloqueia Interromper.
        import tempfile,io
        with tempfile.TemporaryDirectory(prefix='ambidiff_export_') as td:
            pasta_export=Path(td)
            paths=exportar(dados,pasta_export,'filtrado_'+run_id,evidencias_root=PASTA)
            if ext=='pdf':
                target=pasta_export/'relatorio.pdf';gerar_pdf(paths['html'],target)
            else:target=Path(paths[ext])
            conteudo=target.read_bytes()
        tipos={'pdf':'application/pdf','csv':'text/csv','json':'application/json','html':'text/html'}
        return send_file(io.BytesIO(conteudo),mimetype=tipos[ext],as_attachment=True,download_name=nome_amigavel(dados.get('site_nome'),ext,escopo,run_id))
    except RuntimeError as exc:return jsonify(erro=str(exc)),500
    except FileNotFoundError:return jsonify(erro='Relatório não encontrado'),404
    except ValueError as exc:return jsonify(erro=str(exc)),400


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
