"""Estado local versionado, sem pickle ou execução de conteúdo do checkpoint."""
import hashlib
import json
import math
from datetime import datetime
from .core import Pagina,Item,validacao_inicial,permitido

VERSAO=1


def assinar(estado):
    return hashlib.sha256(json.dumps(estado,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def empacotar(estado):
    return {'versao_checkpoint':VERSAO,'salvo_em':datetime.now().astimezone().isoformat(),
            'sha256_estado':assinar(estado),'estado':estado}


def validar(payload,urls=None):
    if not isinstance(payload,dict) or payload.get('versao_checkpoint')!=VERSAO:
        raise ValueError('Checkpoint incompatível: versão não suportada; relatório anterior preservado.')
    estado=payload.get('estado')
    if not isinstance(estado,dict) or payload.get('sha256_estado')!=assinar(estado):
        raise ValueError('Checkpoint inválido: integridade do estado não confirmada.')
    params=estado.get('configuracao',{})
    if not isinstance(params,dict) or set(params)!={'url_a','url_b','nome_a','nome_b','site_nome','auditar_externos','verificar_cliques','varredura_inteligente','ambiente_desatualizado'}:
        raise ValueError('Configuração incompleta/incompatível no checkpoint.')
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
    for par in fila:
        if not isinstance(par,list) or len(par)!=3 or not isinstance(par[2],list) or not all(isinstance(x,str) for x in par[2]):raise ValueError('Par inválido no checkpoint.')
        if not permitido(par[0],a) or not permitido(par[1],b):raise ValueError('Par fora do escopo autorizado.')
        key=tuple(par[:2])
        if key in vistos:raise ValueError('Fila duplicada no checkpoint.')
        vistos.add(key)
    if any(not isinstance(p,list) or len(p)!=2 for p in visitados):raise ValueError('Visitados inválidos.')
    if any(not isinstance(u,str) for p in visitados for u in p):raise ValueError('URLs visitadas inválidas.')
    if len(set(map(tuple,visitados)))!=len(visitados):raise ValueError('Visitados duplicados.')
    if not isinstance(estado.get('pares_enfileirados'),list):raise ValueError('Descobertas ausentes.')
    if any(not isinstance(p,list) or len(p)!=2 or not all(isinstance(u,str) for u in p) for p in estado['pares_enfileirados']):raise ValueError('Descobertas inválidas.')
    descobertos=set(map(tuple,estado['pares_enfileirados']))
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
