"""Política dinâmica padrão e compatibilidade das estratégias anteriores."""
from collections import Counter
import math
import re
import time
from urllib.parse import urlsplit
from .core import normalizar


IMPORTANTES=r'servi[cç]o|sistema|consulta|legisla|jurisprud|portaria|normativ|institucional|organograma|conselho|[aá]udios'
LIMITE_PARES_HTML=1000
EDITORIAL=r'(?:^|/)(noticias?|notícias?|news|w|blog|galerias?|fotos)(?:/|$)'


def opcoes(estrategia,orcamento):
    if estrategia not in ('dinamica','progressiva','profunda'):raise ValueError('Estratégia interna inválida.')
    if type(orcamento) not in (int,float) or not math.isfinite(orcamento) or not 0<=orcamento<=1440:
        raise ValueError('Orçamento deve ser um número de 0 a 1440 minutos; 0 remove o limite.')
    return estrategia,float(orcamento)


def grupo_editorial(par,observados=()):
    # Usa rota e rótulo atual; ancestrais como "Serviços" não anulam uma notícia.
    atual=normalizar(par[2][-1] if par[2] else '')
    paths=[normalizar(urlsplit(u).path) for u in par[:2]]
    if re.search(IMPORTANTES,atual) or any(re.search(IMPORTANTES,p) for p in paths):return None
    grupos=[]
    for path in paths:
        m=re.search(EDITORIAL,path)
        if not m:return None
        # /w/ do Liferay também publica páginas institucionais. Só a rota não
        # autoriza amostragem: exige contexto editorial observado na origem.
        if m[1]=='w' and tuple(par[:2]) not in observados:return None
        grupos.append(path[:m.end()].rstrip('/'))
    return tuple(grupos)


class Escopo:
    def __init__(self,estrategia='dinamica',orcamento=0):
        self.estrategia,self.orcamento=opcoes(estrategia,orcamento)
        self.inicio=time.perf_counter();self.amostras=Counter();self.representantes=[];self.editoriais_observados=set()
    def restante(self):
        if self.estrategia=='dinamica':return None
        return max(0,self.orcamento*60-(time.perf_counter()-self.inicio)) if self.orcamento else None
    def expirou(self):return self.estrategia!='dinamica' and self.orcamento>0 and self.restante()<=0
    def adiar(self,par):
        grupo=grupo_editorial(par,self.editoriais_observados)
        if not grupo:return False
        if self.estrategia=='dinamica':
            if self.amostras[grupo]<3:
                self.amostras[grupo]+=1
                self.representantes.append({'url_a':par[0],'url_b':par[1],'grupo':list(grupo),'nivel':'Representante antecipado; demais pares continuam automaticamente'})
            return False
        if self.estrategia!='progressiva':return False
        if self.amostras[grupo]>=3:return True
        self.amostras[grupo]+=1
        self.representantes.append({'url_a':par[0],'url_b':par[1],'grupo':list(grupo),'nivel':'Representante escolhido; resultado individual no relatório'})
        return False
