"""Taxonomia aditiva: observações, hipóteses e vínculos sem apagar IDs."""
from copy import deepcopy
from collections import defaultdict
import hashlib
import json

TAGS={'OPCAO_AUSENTE','ROTULO_DIVERGENTE','FUNCAO_DIVERGENTE','DESTINO_DIVERGENTE',
      'COMPONENTE_DIVERGENTE','ESTRUTURA_DIVERGENTE','DOCUMENTO_DIVERGENTE',
      'FALHA_FUNCIONAL_VERIFICADA','DADOS_VARIAVEIS','COLETA_INCONCLUSIVA'}

def enriquecer(rows):
    saida=deepcopy(rows)
    for row in saida:
        tipo=row.get('tipo','');tags=[];nivel='possivel';evidencia='Observação do DOM; correspondência e causa requerem revisão.'
        if tipo=='Rótulo':tags=['ROTULO_DIVERGENTE'];nivel='confirmada_propriedade';evidencia='Correspondência única por destino, contexto e papel; rótulos observados distintos.'
        elif tipo=='Função':tags=['FUNCAO_DIVERGENTE']
        elif tipo=='Clique':
            tags=['FALHA_FUNCIONAL_VERIFICADA' if row.get('teste_funcional_executado') else 'FUNCAO_DIVERGENTE']
            if row.get('teste_funcional_executado'):nivel='confirmada_observacao';evidencia='Comportamentos distintos no teste limitado executado; não determina qual é correto.'
        elif tipo in ('Opção','Botão'):tags=['OPCAO_AUSENTE']
        elif tipo=='Documento':tags=['DOCUMENTO_DIVERGENTE']
        elif tipo=='Redirecionamento':
            tags=['DESTINO_DIVERGENTE']
            if row.get('categoria')=='Documentos' or any(str(row.get(k,'')).split('?')[0].lower().endswith(('.pdf','.doc','.docx','.xlsx','.odt')) for k in ('destino_a','destino_b')):tags.append('DOCUMENTO_DIVERGENTE')
            if row.get('destino_a') and row.get('destino_b'):
                nivel='confirmada_referencia';evidencia='Destinos explicitamente observados; conteúdo e correção dos destinos não comprovados.'
        elif tipo in ('Estrutura editorial','Ordem'):tags=['ESTRUTURA_DIVERGENTE']
        elif tipo=='Contexto':tags=['COLETA_INCONCLUSIVA'];nivel='inconclusiva'
        elif tipo in ('Imagem','Ícone','Layout'):tags=['COMPONENTE_DIVERGENTE']
        else:tags=['COMPONENTE_DIVERGENTE']
        if row.get('classificacao')=='editorial':tags=['DADOS_VARIAVEIS'];nivel='diferenca_dados'
        if row.get('classificacao')=='inconclusivo':nivel='inconclusiva'
        if row.get('situacao')=='Código do ícone diferente — revisão visual':nivel='inconclusiva';evidencia='Código distinto; aparência visual e função não comprovadas.'
        row.setdefault('tags',tags);row.setdefault('tag_tecnica',tags[0])
        row.setdefault('grau_confianca',nivel);row.setdefault('justificativa_evidencia',evidencia)
        row.setdefault('teste_funcional_executado',False)
    return saida

def relacionar(rows):
    """Somente ancestral DOM explicitamente coletado; mesma página não basta."""
    buckets=defaultdict(dict)
    for row in rows:
        for occ in row.get('ocorrencias') or [row]:
            for kind,key in (('componente','componente_id'),('secao','secao_id')):
                region=occ.get(key)
                if not region:continue
                urls=tuple(sorted({u for u in (occ.get('url_presente',''),occ.get('url_comparada','')) if u}))
                scope=(kind,urls,region)
                buckets[scope][row.get('id')]=row
    groups=[]
    for (kind,urls,region),members in sorted(buckets.items()):
        if len(members)<2:continue
        if kind=='secao' and len({r.get('tipo') for r in members.values()})<2:continue
        digest=hashlib.sha256(json.dumps([kind,urls,region],ensure_ascii=False).encode()).hexdigest()[:12]
        groups.append({'id':'GRP-'+digest,'tipo':kind,'ids':sorted(members),
            'url':urls[0] if urls else '', 'urls':list(urls),'ancestral_dom':region,'evidencia':'Ancestral DOM comum explicitamente extraído nesta página.',
            'hipotese':'As diferenças podem refletir uma alteração comum do componente ou seção.',
            'causa_confirmada':False})
    return groups
