"""Relatório v2 com detalhes locais separados; leitura do formato v1 preservada."""
from copy import deepcopy

TECNICOS=('metricas','otimizacao','documentos_verificados','verificacoes_destinos',
          'resultados_funcionais','diferencas_esteticas','eventos_diagnostico','falhas',
          'bloqueios_seguranca','registros_originais','editoriais_classificados','editoriais_preservados')


def separar(dados):
    principal={k:v for k,v in dados.items() if k not in TECNICOS}
    detalhes={k:dados[k] for k in TECNICOS if k in dados}
    # Métricas sintéticas no principal; releituras com DOM ficam nos detalhes.
    m=dados.get('metricas',{})
    principal['metricas']={k:v for k,v in m.items() if k!='releituras'}
    principal['resumo_tecnico']={k:len(dados.get(k,[])) for k in TECNICOS if isinstance(dados.get(k),list)}
    principal['formato_relatorio']=2
    return principal,detalhes


def falhas_categorizadas(falhas):
    acesso=[];automacao=[];bloqueios=[]
    for f in falhas:
        tipo=f.get('tipo_erro','')
        (bloqueios if tipo=='POLITICA_SEGURANCA' else acesso if tipo in ('HTTP','DNS','CERTIFICADO_TLS','NAVEGACAO_INTERROMPIDA') else automacao).append(deepcopy(f))
    return {'falhas_acesso_observadas':acesso,'falhas_automacao':automacao,'bloqueios_legados':bloqueios}
