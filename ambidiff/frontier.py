"""Fila estável por relevância, com cota de antiguidade para evitar inanição."""
from collections import deque
import heapq
import re
from urllib.parse import urlsplit
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


def categoria(par,contexto=''):
    """Rótulo/rota/contexto observados; prioridade não prova equivalência."""
    texto=normalizar(' '.join([par[2][-1] if par[2] else '',*(urlsplit(u).path for u in par[:2])]))
    contexto=normalizar(contexto)
    if len(par[2])==1 or re.search(r'menu|navegação|navegacao|cabeçalho|cabecalho|rodapé|rodape',contexto):return 0
    if re.search(r'servi[cç]o|sistema|consulta|atendimento|[aá]udios',texto):return 1
    if re.search(r'hist[oó]ric|arquivo morto|acervo',texto):return 5
    if re.search(r'not[ií]cia|/w/|/blog/|galeria|imprensa',texto):return 2
    if re.search(r'legisla|jurisprud|portaria|normativ|decreto|resolu',texto):return 3
    return 4


class Fila:
    def __init__(self,pares=(),dinamica=False,categorias=None):
        self.heap=[];self.antigos=deque();self.ativos={};self.seq=0;self.saidas=0
        self.adiados=[]
        self.dinamica=dinamica;self.categorias=categorias if categorias is not None else {}
        self.rodada=0
        for par in pares:self.append(par)
    def append(self,par):
        n=self.seq;self.seq+=1;self.ativos[n]=par
        rank=self.categorias.get(tuple(par[:2])) if self.dinamica else prioridade(par)
        if rank is None:rank=categoria(par)
        heapq.heappush(self.heap,(rank,n))
        if not self.dinamica:self.antigos.append(n)
    def popleft(self):
        self.saidas+=1
        # A cada oito saídas, roda entre as categorias presentes. Notícias
        # numerosas não monopolizam admissão nem impedem páginas institucionais.
        if self.dinamica and self.saidas%8==0:
            presentes=sorted({rank for rank,n in self.heap if n in self.ativos})
            if presentes:
                rank=presentes[self.rodada%len(presentes)];self.rodada+=1
                n=min(n for r,n in self.heap if r==rank and n in self.ativos)
                return self.ativos.pop(n)
        if not self.dinamica and self.saidas%8==0:
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
