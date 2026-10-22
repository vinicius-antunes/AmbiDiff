"""Janela de logs com cursor monotônico. A execução mantém arquivo completo local."""
from datetime import datetime

class Logs:
    def __init__(self,limite=200):self.limite=limite;self.seq=0;self.eventos=[]
    def adicionar(self,texto):
        self.seq+=1
        self.eventos.append({'id':self.seq,'texto':str(texto)[:700],'horario':datetime.now().astimezone().isoformat()})
        self.eventos=self.eventos[-self.limite:]
    def consultar(self,cursor=0):
        primeiro=self.eventos[0]['id'] if self.eventos else self.seq+1
        return {'eventos_logs':[dict(x) for x in self.eventos if x['id']>(0 if cursor>self.seq else cursor)],
                'cursor_logs':self.seq,'primeiro_log_disponivel':primeiro,
                'lacuna_logs':bool(cursor and (cursor<primeiro-1 or cursor>self.seq))}
