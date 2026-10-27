"""Estado local versionado, sem pickle ou execução de conteúdo do checkpoint."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
from dataclasses import asdict
from datetime import datetime
from .core import Pagina,Item,validacao_inicial,permitido

VERSAO=1


def assinar(estado):
    return hashlib.sha256(json.dumps(estado,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def empacotar(estado,metricas=None):
    inicio=time.perf_counter()
    pacote={'versao_checkpoint':VERSAO,'salvo_em':datetime.now().astimezone().isoformat(),
            'sha256_estado':assinar(estado),'estado':estado}
    if metricas:metricas.tempos['checkpoint_assinatura_json']+=time.perf_counter()-inicio
    return pacote


class PaginasSerializadas:
    """Só páginas concluídas: substituir a coleta invalida a entrada por identidade."""
    def __init__(self):self.cache={};self.convertidas=0;self.reutilizadas=0
    def converter(self,paginas):
        out={}
        for url,pagina in paginas.items():
            anterior=self.cache.get(url)
            if anterior is None or anterior[0] is not pagina:
                anterior=(pagina,asdict(pagina));self.cache[url]=anterior;self.convertidas+=1
            else:self.reutilizadas+=1
            out[url]=anterior[1]
        return out


def gravar(path,snapshot):
    """Mesmo JSON v1, compacto. Só substitui o anterior após flush/fsync e close."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    inicio=time.perf_counter();texto=json.dumps(snapshot,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    serializacao=time.perf_counter()-inicio;inicio=time.perf_counter();temp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as out:
            temp=Path(out.name);out.write(texto);out.flush();os.fsync(out.fileno())
        os.replace(temp,path)
    finally:
        if temp:temp.unlink(missing_ok=True)
    return {'serializacao_json':serializacao,'gravacao':time.perf_counter()-inicio,'bytes':len(texto.encode('utf-8'))}


def validar(payload,urls=None):
    if not isinstance(payload,dict) or payload.get('versao_checkpoint')!=VERSAO:
        raise ValueError('Checkpoint incompatível: versão não suportada; relatório anterior preservado.')
    estado=payload.get('estado')
    if not isinstance(estado,dict) or payload.get('sha256_estado')!=assinar(estado):
        raise ValueError('Checkpoint inválido: integridade do estado não confirmada.')
    params=estado.get('configuracao',{})
    obrigatorios={'url_a','url_b','nome_a','nome_b','site_nome','auditar_externos','verificar_cliques','varredura_inteligente','ambiente_desatualizado'}
    if not isinstance(params,dict) or not obrigatorios<=set(params) or set(params)-obrigatorios-{'estrategia','orcamento_minutos'}:
        raise ValueError('Configuração incompleta/incompatível no checkpoint.')
    from .strategy import opcoes
    opcoes(params.get('estrategia','profunda'),params.get('orcamento_minutos',0))
    if not all(isinstance(params[k],str) for k in ('url_a','url_b','nome_a','nome_b','site_nome','ambiente_desatualizado')) or not all(type(params[k]) is bool for k in ('auditar_externos','verificar_cliques','varredura_inteligente')):
        raise ValueError('Tipos da configuração inválidos.')
    if not params['nome_a'] or not params['nome_b']:raise ValueError('Nomes de ambientes ausentes.')
    for chave in ('brutos','falhas','pendencias','refs','editoriais','eventos','avisos_coleta','documentos_relatorio','verificacoes_destinos','resultados_funcionais','diferencas_esteticas','segmentos'):
        if not isinstance(estado.get(chave),list) or any(not isinstance(x,dict) for x in estado[chave]):raise ValueError('Registros inválidos: '+chave)
    for chave in ('paginas_a','paginas_b','metricas','inteligencia','excluded','bloqueios'):
        if not isinstance(estado.get(chave),dict):raise ValueError('Estado incompleto: '+chave)
    duracao=estado.get('duracao_acumulada')
    if not isinstance(duracao,(int,float)) or not math.isfinite(duracao) or duracao<0:raise ValueError('Duração inválida.')
    if not isinstance(estado.get('iniciado_em'),str) or type(estado.get('cliques_testados')) is not int:raise ValueError('Cronologia/contadores inválidos.')
    if not all(isinstance(estado['metricas'].get(k),dict) for k in ('contagens','tempos_segundos')):raise ValueError('Métricas inválidas.')
    if not all(k in estado['inteligencia'] for k in ('equivalencias','inconclusivos','omissoes','estruturas','componentes','templates','nao_pareadas')):raise ValueError('Estado da comparação incompleto.')
    a,b=validacao_inicial(params.get('url_a',''),params.get('url_b',''))
    if urls and (a,b)!=tuple(urls):raise ValueError('Checkpoint de outros ambientes.')
    if params.get('nome_a')==params.get('nome_b'):raise ValueError('Ambientes do checkpoint inválidos.')
    fila=estado.get('fila');visitados=estado.get('visitados')
    if not isinstance(fila,list) or not isinstance(visitados,list):raise ValueError('Fila/visitados ausentes no checkpoint.')
    vistos=set()
    candidatos=estado.get('candidatos_html',[])
    if not isinstance(candidatos,list):raise ValueError('Candidatos HTML inválidos.')
    for par in fila+candidatos:
        if not isinstance(par,list) or len(par)!=3 or not isinstance(par[2],list) or not all(isinstance(x,str) for x in par[2]):raise ValueError('Par inválido no checkpoint.')
        exclusivo=estado.get('politica_html')==1 and (par[0]=='' or par[1]=='') and bool(par[0] or par[1])
        if not all((u=='' and exclusivo) or permitido(u,base) for u,base in zip(par[:2],(a,b))):raise ValueError('Par fora do escopo autorizado.')
        key=tuple(par[:2])
        if key in vistos:raise ValueError('Fila duplicada no checkpoint.')
        vistos.add(key)
    vistos={tuple(p[:2]) for p in fila}
    if any(not isinstance(p,list) or len(p)!=2 for p in visitados):raise ValueError('Visitados inválidos.')
    if any(not isinstance(u,str) for p in visitados for u in p):raise ValueError('URLs visitadas inválidas.')
    if len(set(map(tuple,visitados)))!=len(visitados):raise ValueError('Visitados duplicados.')
    if not isinstance(estado.get('pares_enfileirados'),list):raise ValueError('Descobertas ausentes.')
    if any(not isinstance(p,list) or len(p)!=2 or not all(isinstance(u,str) for u in p) for p in estado['pares_enfileirados']):raise ValueError('Descobertas inválidas.')
    descobertos=set(map(tuple,estado['pares_enfileirados']))
    if estado.get('politica_html')==1:
        limite=estado.get('limite_html')
        if type(limite) is not int or not 1000<=limite<=100000:raise ValueError('Limite HTML inválido.')
        nao_html=set(map(tuple,estado.get('pares_nao_html',[])))
        if not nao_html<=descobertos or (params.get('estrategia')=='dinamica' and len(descobertos-nao_html)>limite):raise ValueError('Admissões HTML inconsistentes.')
        if {tuple(p[:2]) for p in candidatos}&descobertos:raise ValueError('Candidato já admitido no checkpoint.')
        estados=estado.get('estados_pares',[])
        if not isinstance(estados,list):raise ValueError('Estados dos pares inválidos.')
        terminais=set();visitados_set=set(map(tuple,visitados))
        for registro in estados:
            if not isinstance(registro,dict) or not isinstance(registro.get('par'),list) or len(registro['par'])!=2 or not all(isinstance(u,str) for u in registro['par']) or registro.get('estado') not in ('comparado','falha','sem_contraparte','redirecionamento','fora_escopo','nao_html','inconclusivo'):raise ValueError('Estado de par inválido.')
            key=tuple(registro['par'])
            if key in terminais or key not in visitados_set:raise ValueError('Estado terminal sem visita única.')
            terminais.add(key)
        for registro in estado.get('categorias_html',[]):
            if not isinstance(registro,dict) or not isinstance(registro.get('par'),list) or len(registro['par'])!=2 or type(registro.get('categoria')) is not int or not 0<=registro['categoria']<=5:raise ValueError('Categoria HTML inválida.')
        for env,paginas in estado.get('paginas_exclusivas',{}).items():
            if env not in (params['nome_a'],params['nome_b']) or not isinstance(paginas,dict):raise ValueError('Páginas exclusivas inválidas.')
            base=a if env==params['nome_a'] else b
            for url,pagina in paginas.items():
                if url!=pagina.get('url') or not permitido(url,base):raise ValueError('Página exclusiva fora do escopo.')
                restaurar_pagina(pagina)
    if not (vistos|set(map(tuple,visitados)))<=descobertos:raise ValueError('Fila/visitados sem descoberta correspondente.')
    if vistos.intersection(map(tuple,visitados)):raise ValueError('Par pendente já consta como visitado.')
    for lado in ('paginas_a','paginas_b'):
        for url,pagina in estado.get(lado,{}).items():
            if url!=pagina.get('url') or not permitido(url,a if lado=='paginas_a' else b):raise ValueError('Página fora do escopo.')
            try:restaurar_pagina(pagina)
            except (ValueError,TypeError,KeyError) as exc:raise ValueError('Página incompatível no checkpoint.') from exc
    if len(estado['paginas_a'])!=len(estado['paginas_b']):raise ValueError('Pares comparados inconsistentes.')
    return estado


def restaurar_pagina(dados):
    d=dict(dados);d['itens']=[Item(**i) for i in d.get('itens',[])]
    return Pagina(**d)


def recuperar(snapshot):
    """Projeção de diagnóstico; nunca altera o arquivo de checkpoint original."""
    from copy import deepcopy
    from .paired import agrupar_registros,agrupar_referencias,_avisos
    from .intelligence import agrupar_variacoes
    inicio_recuperacao=time.perf_counter()
    snap=deepcopy(snapshot);payload=snap.pop('retomada',None)
    estado=validar(payload) if payload else {}
    brutos=snap.get('brutos',estado.get('brutos',[]))
    editoriais=snap.get('registros_editoriais') or snap.get('variacoes_editoriais') or estado.get('editoriais',[])
    from .security import restaurar
    snap.setdefault('segmentos_coleta',estado.get('segmentos',[]))
    snap['bloqueios_seguranca']=list(restaurar(snap.get('bloqueios_seguranca',estado.get('bloqueios',{}))).values())
    nomes=list(snap.get('ambientes',{}));a=nomes[0] if nomes else estado.get('configuracao',{}).get('nome_a','A')
    b=nomes[1] if len(nomes)>1 else estado.get('configuracao',{}).get('nome_b','B')
    fila=estado.get('fila',snap.get('fila_pendente',[]));visitados=estado.get('visitados',snap.get('pares_visitados',[]))
    andam=dict(snap.get('andamento',{}))
    andam.update(pares_descobertos=len(estado['pares_enfileirados']) if estado else andam.get('pares_descobertos',max((x.get('visitadas',0)+x.get('pendentes',0) for x in snap.get('meta_varredura',{}).values()),default=0)),
        pares_visitados=len(visitados) if estado else andam.get('pares_visitados',max((x.get('visitadas',0) for x in snap.get('meta_varredura',{}).values()),default=0)),
        pares_comparados=sum(p['estado']=='comparado' for p in estado['estados_pares']) if 'estados_pares' in estado else len(estado['paginas_a']) if estado else andam.get('pares_comparados',max(snap.get('paginas',{}).values(),default=0)),
        pares_pendentes=len(fila) if estado else andam.get('pares_pendentes',max((x.get('pendentes',0) for x in snap.get('meta_varredura',{}).values()),default=0)),
        pares_com_falha=len(estado['pares_falhos']) if 'pares_falhos' in estado else len({x.get('url') for x in snap.get('falhas',estado.get('falhas',[]))}))
    snap.update(andamento=andam,fila_pendente=fila,pares_visitados=visitados,
        divergencias=agrupar_registros(brutos),registros_editoriais=editoriais,
        variacoes_dados=snap.get('variacoes_dados') or agrupar_variacoes(editoriais,snap.get('ambiente_desatualizado','')),
        itens_editoriais_agrupados=len(editoriais),ocorrencias_brutas=len(brutos)+len(editoriais),
        referencias_pendentes=snap.get('referencias_pendentes') or agrupar_referencias(estado.get('refs',[])),
        avisos_tecnicos=snap.get('avisos_tecnicos') or _avisos(snap.get('falhas',[]),snap.get('meta_varredura',{})))
    for registro in snap['divergencias']:
        registro.update(estado.get('evidencias_preservadas',{}).get(registro['id'],{}))
    snap['estados_pares']=estado.get('estados_pares',snap.get('estados_pares',[]))
    tempos=snap.setdefault('metricas',{}).setdefault('tempos_segundos',{})
    tempos['checkpoint_recuperacao_em_falha']=round(time.perf_counter()-inicio_recuperacao,6)
    return snap
