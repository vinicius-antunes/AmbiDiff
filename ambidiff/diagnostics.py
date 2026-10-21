"""Diagnóstico local explicável, sem confundir falhas da automação com defeitos do site."""
from __future__ import annotations
from datetime import datetime
import json
import re
from pathlib import Path
from collections import Counter

CATALOGO={
 'DNS':('O nome do servidor não foi resolvido.','Verificar DNS, acesso à rede corporativa e a URL.'),
 'CERTIFICADO_TLS':('O certificado TLS não foi aceito pelo navegador automatizado.','Revisar cadeia de certificação na máquina, sem desativar a proteção global.'),
 'TIMEOUT':('O carregamento excedeu o limite de tempo.','Repetir a coleta da página e conferir lentidão/carregamento dinâmico.'),
 'HTTP':('O servidor respondeu com um status HTTP de erro.','Verificar a rota e o status HTTP; não presumir que o ambiente inteiro esteja fora do ar.'),
 'NAVEGACAO_INTERROMPIDA':('Outra navegação ou página de erro interrompeu a tentativa.','Abrir a rota manualmente e verificar redirecionamentos.'),
 'DOWNLOAD_DE_DOCUMENTO':('A rota iniciou o download de um arquivo em vez de carregar uma página HTML.','Separar como documento; não contabilizar como falha consecutiva de página.'),
 'EXTRACAO':('Não foi possível extrair com segurança o DOM carregado.','Revisar console e comportamento de renderização; repetir a leitura.'),
 'DESCONHECIDO':('O erro não corresponde ao catálogo conhecido.','Usar a mensagem técnica registrada para investigação.'),
}

def classificar_erro(erro:str)->dict:
    texto=str(erro or '').lower()
    if 'download is starting' in texto or 'arquivo para download' in texto:tipo='DOWNLOAD_DE_DOCUMENTO'
    elif 'err_name_not_resolved' in texto or 'dns' in texto:tipo='DNS'
    elif 'err_cert_' in texto or 'certificate' in texto:tipo='CERTIFICADO_TLS'
    elif 'timeout' in texto or 'tempo esgotado' in texto:tipo='TIMEOUT'
    elif re.search(r'\bhttp\s*[45]\d\d\b',texto):tipo='HTTP'
    elif 'interrupted by another navigation' in texto or 'chrome-error://' in texto:tipo='NAVEGACAO_INTERROMPIDA'
    elif 'extração' in texto or 'extracao' in texto or 'extract' in texto:tipo='EXTRACAO'
    else:tipo='DESCONHECIDO'
    descr,acao=CATALOGO[tipo]
    return {'tipo_erro':tipo,'possivel_causa':descr,'orientacao':acao,'causa_confirmada':False}


def montar_diagnostico(resultado:dict,logs:list[str]|None=None)->dict:
    from .relevance import preparar
    resultado=preparar(resultado)
    eventos=resultado.get('eventos_diagnostico',[])
    falhas=resultado.get('falhas',[])
    erros_por_tipo=Counter()
    for f in falhas:erros_por_tipo[f.get('tipo_erro') or classificar_erro(f.get('erro',''))['tipo_erro']]+=1
    for e in eventos:
        if e.get('tipo')=='DOWNLOAD_DE_DOCUMENTO':erros_por_tipo['DOWNLOAD_DE_DOCUMENTO']+=1
    metas=resultado.get('meta_varredura',{})
    motivos={env:d.get('motivo_parada','') for env,d in metas.items() if d.get('motivo_parada')}
    return {'diferencas_completas':resultado.get('divergencias',[]),'editoriais':resultado.get('editoriais_preservados',[]),'resumo_relevancia':resultado.get('resumo_relevancia',{}),'versao':'1.5','gerado_em':datetime.now().isoformat(timespec='seconds'),
      'site_nome':resultado.get('site_nome',''),'ambientes':resultado.get('ambientes',{}),
      'situacao_analise':resultado.get('situacao_analise','inconclusivo'),
      'modo_varredura':resultado.get('modo_varredura','atual'),
      'metricas':resultado.get('metricas',{}),'otimizacao':resultado.get('otimizacao',{}),
      'documentos_verificados':resultado.get('documentos_verificados',[]),
      'interrupcao':{'ocorreu':bool(motivos),'motivos':motivos,
          'pares_visitados':max((x.get('visitadas',0) for x in metas.values()),default=0),
          'pares_na_fila':max((x.get('pendentes',0) for x in metas.values()),default=0)},
      'divergencias_preservadas':len(resultado.get('divergencias',[])),
      'variacoes_editoriais_agrupadas':resultado.get('itens_editoriais_agrupados',0),
      'falhas_por_tipo':dict(erros_por_tipo),'falhas':falhas,
      'eventos':eventos,'avisos':resultado.get('avisos_tecnicos',[]),
      'mensagens_de_execucao':list(logs or [])[-250:],
      'nota':'A hipótese de causa não comprova defeito no site. Downloads não representam páginas HTML.'}


def exportar_diagnostico(dados:dict,pasta:Path,run_id:str)->dict:
    pasta.mkdir(parents=True,exist_ok=True)
    destino_json=pasta/f'diagnostico_{run_id}.json'
    destino_txt=pasta/f'log_{run_id}.txt'
    destino_json.write_text(json.dumps(dados,ensure_ascii=False,indent=2),encoding='utf-8')
    linhas=['AMBIDIFF 1.5 — DIAGNÓSTICO DE VARREDURA',
            'Site: '+str(dados.get('site_nome','')),
            'Estado: '+str(dados.get('situacao_analise','')),
            'Pares visitados: '+str(dados.get('interrupcao',{}).get('pares_visitados',0)),
            'Pares pendentes: '+str(dados.get('interrupcao',{}).get('pares_na_fila',0)),
            'Divergências preservadas: '+str(dados.get('divergencias_preservadas',0)),
            'Motivos de parada: '+str(dados.get('interrupcao',{}).get('motivos',{})),'',
            'TIPOS DE EVENTOS:']
    linhas.extend(f'  {k}: {v}' for k,v in dados.get('falhas_por_tipo',{}).items())
    linhas+=['','MÉTRICAS E COBERTURA:',json.dumps(dados.get('metricas',{}),ensure_ascii=False),
             json.dumps(dados.get('otimizacao',{}),ensure_ascii=False),
             'DOCUMENTOS (SOMENTE METADADOS):',json.dumps(dados.get('documentos_verificados',[]),ensure_ascii=False)]
    linhas+=['','FALHAS:']
    for f in dados.get('falhas',[]):
        info=classificar_erro(f.get('erro',''))
        linhas.extend((f"- [{f.get('ambiente','?')}] {f.get('url','')}",
                       f"  Tipo: {info['tipo_erro']}",f"  Possível causa: {info['possivel_causa']}",
                       f"  Ação sugerida: {info['orientacao']}",f"  Mensagem técnica: {f.get('erro','')[:500]}"))
    linhas+=['','ÚLTIMOS EVENTOS:']
    for ev in dados.get('eventos',[])[-120:]:linhas.append('- '+json.dumps(ev,ensure_ascii=False)[:950])
    linhas+=['','REGISTRO DO TERMINAL:']
    linhas.extend(dados.get('mensagens_de_execucao',[]))
    destino_txt.write_text('\n'.join(linhas),encoding='utf-8')
    return {'json':str(destino_json),'txt':str(destino_txt)}
