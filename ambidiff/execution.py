"""Semântica de fila admitida; independente da cobertura integral do portal."""
import math


def contadores(dados):
    def inteiro(chave):return max(0,int(dados.get(chave,0) or 0))
    total=inteiro('pares_descobertos') or inteiro('pares_admitidos_html')
    pendentes=inteiro('pares_pendentes');comparados=inteiro('pares_comparados');falhos=inteiro('pares_com_falha')
    concluidos=inteiro('pares_concluidos') if 'pares_concluidos' in dados else min(max(0,total-pendentes),comparados+falhos)
    concluidos=min(total,concluidos)
    ativos=min(1,max(0,total-concluidos-pendentes)) if dados.get('etapa') not in ('falha','interrompido','encerramento') else 0
    nao_analisados=max(0,total-concluidos)
    return {'pares_admitidos':total,'pares_concluidos':concluidos,'pares_comparados':comparados,
            'pares_com_falha':falhos,'pares_pendentes':pendentes,'pares_em_processamento':ativos,
            'pares_nao_analisados':nao_analisados,
            'percentual_fila':math.floor(100*concluidos/total) if total else 0}


def resumir(resultado):
    d=contadores(resultado.get('andamento',{}))
    if resultado.get('estado_execucao')=='interrompido':estado='interrompida'
    elif resultado.get('estado_execucao')=='falha' or d['pares_nao_analisados'] or not d['pares_admitidos']:estado='parcial'
    elif resultado.get('falhas') or d['pares_com_falha']:estado='concluida_com_falhas'
    else:estado='concluida'
    return {'estado':estado,**d,'cobertura_integral':False,
            'nota':'Conclusão refere-se somente aos pares admitidos; consulte as limitações de cobertura e verificações inconclusivas.'}
