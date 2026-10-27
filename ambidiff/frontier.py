"""Fila estável por relevância, com cota de antiguidade para evitar inanição."""
from collections import deque
import heapq
import re
from .core import normalizar


def prioridade(par):
    texto=normalizar(par[-1][-1]+' '+par[0]) if par[-1] else normalizar(par[0])
    if len(par[-1])==1:return 0
    from .strategy import IMPORTANTES
    if re.search(IMPORTANTES,texto):return 1
    if re.search(r'pr[oó]xim|voltar|anterior|[?&](?:page|pagina|p_p_state|start)=',texto):return 5
    if re.search(r'not[ií]cia|/w/|/blog/|hist[oó]ric|imprensa',texto):return 4
    if re.search(r'institucional|estrutura|conselho|organograma|quem somos',texto):return 1
    if re.search(r'servi[cç]o|cidad[aã]o|atendimento',texto):return 2
    return 3


class Fila:
    def __init__(self,pares=()):
        self.heap=[];self.antigos=deque();self.ativos={};self.seq=0;self.saidas=0
        self.adiados=[]
        for par in pares:self.append(par)
    def append(self,par):
        n=self.seq;self.seq+=1;self.ativos[n]=par
        heapq.heappush(self.heap,(prioridade(par),n));self.antigos.append(n)
    def popleft(self):
        self.saidas+=1
        if self.saidas%8==0:
            while self.antigos:
                n=self.antigos.popleft()
                if n in self.ativos:return self.ativos.pop(n)
        while self.heap:
            _,n=heapq.heappop(self.heap)
            if n in self.ativos:return self.ativos.pop(n)
        raise IndexError('Fila vazia')
    def adiar(self,par):self.adiados.append(par)
    def __len__(self):return len(self.ativos)+len(self.adiados)
    def __iter__(self):return iter([*self.ativos.values(),*self.adiados])
