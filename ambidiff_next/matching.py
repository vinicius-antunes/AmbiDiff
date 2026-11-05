"""Pareamento explicável por semântica observável; nenhuma posição prova equivalência."""
import re
from .models import normalized
from .policy import equivalent_url


_STOP={'de','do','da','dos','das','ao','a','o','e','para','em','um','uma'}
_ALIASES={'consultar':'consulta','consultas':'consulta','processos':'processo',
          'processual':'processo','processuais':'processo','servicos':'servico',
          'cidadaos':'cidadao','requerimentos':'requerimento','documentos':'documento'}


def tokens(value):
    return {_ALIASES.get(v,v) for v in re.findall(r'[a-z0-9]+',normalized(value)) if v not in _STOP}


def similarity(a,b):
    aa,bb=tokens(a),tokens(b)
    return len(aa&bb)/len(aa|bb) if aa and bb else 0.0


def _compatible(a,b):
    aliases={'a':'link','opcao':'link','option':'link','document':'link','documento':'link','button':'button','botao':'button'}
    ak=aliases.get(normalized(a.kind),normalized(a.kind));bk=aliases.get(normalized(b.kind),normalized(b.kind))
    return ak==bk and (not a.role or not b.role or a.role==b.role)


def match_elements(a,b,roots):
    """Associa candidatos somente quando a melhor escolha é mútua e inequívoca.

    Confiança intermediária é uma hipótese: o consumidor deve corroborar o
    destino/comportamento antes de afirmar identidade funcional.
    """
    pending_a={e.id:e for e in a.elements};pending_b={e.id:e for e in b.elements}
    matches=[];ambiguous=[]
    def pairs(phase):
        choices={}
        for x in pending_a.values():
            candidates=[]
            for y in pending_b.values():
                if not _compatible(x,y):continue
                name=normalized(x.name)==normalized(y.name) and bool(normalized(x.name))
                route=bool(x.url and y.url and equivalent_url(x.url,y.url,roots))
                context=similarity(x.section,y.section)
                if phase==0 and name and route:score=1.0
                elif phase==1 and name:score=.95 if context>=.5 else .86
                elif phase==2 and route and (similarity(x.name,y.name)>=.4 or context>=.5):score=.84
                elif phase==3 and similarity(x.name,y.name)>=.75 and context>=.5:score=.77
                else:continue
                # Ao repetir "Consultar", o contexto distingue os serviços.
                score+=min(context*.02,.02)
                candidates.append((round(score,4),y.id))
            if candidates:choices[x.id]=sorted(candidates,reverse=True)
        accepted=[]
        for aid,values in choices.items():
            score,bid=values[0]
            if len(values)>1 and score-values[1][0]<.01:continue
            reverse=sorted([(vs[0][0],aa) for aa,vs in choices.items() if vs[0][1]==bid],reverse=True)
            if reverse[0][1]!=aid or (len(reverse)>1 and reverse[0][0]-reverse[1][0]<.01):continue
            accepted.append((aid,bid,score))
        for aid,bid,score in accepted:
            matches.append({'a':aid,'b':bid,'confidence':'alta' if phase<2 else 'intermediaria','score':score,
                            'criteria':('nome_e_destino','nome_tipo_contexto','destino_e_rotulo_compativel','rotulo_semantico_e_contexto')[phase]})
            pending_a.pop(aid);pending_b.pop(bid)
    for phase in range(4):pairs(phase)
    for x in pending_a.values():
        candidates=[y.id for y in pending_b.values() if _compatible(x,y) and similarity(x.name,y.name)>=.6]
        if candidates:ambiguous.append({'a':x.id,'candidates_b':candidates,'reason':'Sem melhor correspondência mútua inequívoca; equivalência não presumida'})
    return {'matches':matches,'unmatched_a':list(pending_a),'unmatched_b':list(pending_b),'ambiguous':ambiguous}
