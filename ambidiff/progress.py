"""Progresso observado e cancelamento cooperativo, sem matar o processo."""
from datetime import datetime, timezone
import time

TEMPO_PAR_SEGUNDOS = 90


class InterrupcaoSolicitada(BaseException):
    """Não deve ser convertida em falha de navegação por except Exception."""


class TempoParExcedido(BaseException):
    pass


def verificar_interrupcao(parar):
    if parar is not None and parar.is_set():
        raise InterrupcaoSolicitada()


def esperar(page, milissegundos, parar=None):
    restante = milissegundos
    while restante > 0:
        verificar_interrupcao(parar)
        passo = min(restante, 100)
        page.wait_for_timeout(passo)
        restante -= passo
    verificar_interrupcao(parar)


class Acompanhamento:
    def __init__(self, parar, callback=None):
        self.parar = parar
        self.callback = callback or (lambda **kw: None)
        self.dados = {'ultimo_par_processado':0, 'par_atual':None,
                      'pares_pendentes':0, 'etapa':'Preparando navegador'}
        self.inicio_par = None

    def informar(self, etapa, limite_segundos=None, **kw):
        agora=datetime.now(timezone.utc).isoformat()
        self.dados.update(kw, etapa=etapa,ultima_atividade=agora,
                          etapa_iniciada_em=agora,
                          limite_operacao_segundos=limite_segundos)
        self.callback(**self.dados)

    def iniciar_par(self, numero, pendentes):
        self.inicio_par = time.monotonic()
        self.informar('Iniciando par', TEMPO_PAR_SEGUNDOS,
                      par_atual=numero, pares_pendentes=pendentes)

    def verificar(self):
        verificar_interrupcao(self.parar)
        if self.inicio_par is not None and time.monotonic()-self.inicio_par >= TEMPO_PAR_SEGUNDOS:
            raise TempoParExcedido()

    def is_set(self):
        self.verificar()
        return False

    def concluir_par(self, pendentes):
        self.inicio_par = None
        self.informar('Par processado', ultimo_par_processado=self.dados['par_atual'],
                      par_atual=None, pares_pendentes=pendentes)
