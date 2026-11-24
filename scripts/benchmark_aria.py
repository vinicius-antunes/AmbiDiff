"""Compara reconhecimento e custo com HTML fixo, Chromium e portais loopback."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys
import threading
from time import perf_counter
from unittest.mock import patch
from urllib.parse import urlsplit

from playwright.sync_api import ElementHandle, Locator, sync_playwright


def pico_rss():
    if sys.platform not in ('linux', 'darwin'):
        return None
    import resource
    valor = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return valor if sys.platform == 'darwin' else valor * 1024


def mediana(amostras):
    return {chave: median(a[chave] for a in amostras) for chave in amostras[0]}


def main():
    raiz = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codigo', type=Path, default=raiz, help='Checkout ou exportação do código a medir.')
    parser.add_argument('--repeticoes', type=int, default=3)
    parser.add_argument('--elementos', type=int, default=600, help='Controles extras por página no cenário de escala.')
    args = parser.parse_args()
    if args.repeticoes < 1 or args.elementos < 1:
        parser.error('Informe números positivos de repetições e elementos.')

    sys.path[:0] = [str(args.codigo.resolve()), str(raiz / 'tests')]
    from ambidiff.paired import _extrair_page, _link_pairs, executar_pareado
    from ambidiff.relevance import classificar
    from ambidiff.smart import Inteligencia, Metricas
    from fixtures_aria import DIFERENCAS, EQUIVALENTES, INCONCLUSIVOS, pagina_aria, portais_aria

    contagem = 0

    def medir_cliques(original):
        def click(self, *a, **kw):
            nonlocal contagem
            contagem += 1
            return original(self, *a, **kw)
        return click

    amostras = []
    with portais_aria() as (bases, requisicoes), patch.object(Locator, 'click', medir_cliques(Locator.click)), \
            patch.object(ElementHandle, 'click', medir_cliques(ElementHandle.click)):
        for _ in range(args.repeticoes):
            contagem = 0
            inicio = perf_counter()
            r = executar_pareado(*bases, 'PRD', 'DES', threading.Event(), lambda _: None, lambda _: None,
                                 varredura_inteligente=True, navegacao_assincrona=False)
            total = perf_counter() - inicio
            metricas = r['metricas']['tempos_segundos']
            amostras.append({'total_segundos':total,'extracao_segundos':metricas['extracao'],
                             'comparacao_segundos':metricas['comparacao'],'links_segundos':metricas['links'],
                             'cliques_tentados':contagem})
        assert all(metodo in ('GET', 'HEAD') for _, metodo, _ in requisicoes)
    equivalencias = {e['elemento'] for e in r['otimizacao']['equivalencias_verificadas']}
    inconclusivos = {e['elemento'] for e in r['otimizacao']['equivalencias_inconclusivas']}
    divergencias = []
    for d in r['divergencias']:
        relevancia = classificar(d)[0]
        if relevancia == 'inconclusivo':
            inconclusivos.add(d['elemento'])
        divergencias.append((d['id'], d['elemento'], d['tipo'], relevancia))
    expectativas = EQUIVALENTES | INCONCLUSIVOS | DIFERENCAS
    preservadas = {e for _, e, _, classe in divergencias if classe=='relevante'} & DIFERENCAS
    qualidade = dict(acertos=sorted(equivalencias & EQUIVALENTES),
        falsos_positivos=sorted((equivalencias & expectativas) - EQUIVALENTES),
        falsos_negativos=sorted(EQUIVALENTES - equivalencias), preservadas=sorted(preservadas),
        inconclusivos_esperados_observados=sorted(INCONCLUSIVOS & inconclusivos),
        divergencias=divergencias, pares=r['andamento']['pares_comparados'],
        falhas=r['andamento']['pares_com_falha'],
        rotas=[urlsplit(estado['par'][0]).path for estado in r['estados_pares']])

    escala = {}
    with sync_playwright() as pw, pw.chromium.launch() as chromium:
        pages = [chromium.new_page() for _ in range(2)]
        bases = ('https://prd.test/', 'https://des.test/')
        for variante in ('heterogenea', 'nativa'):
            tempos = []
            for page, base, lado in zip(pages, bases, ('PRD', 'DES')):
                html = pagina_aria(lado, escala=args.elementos, escala_nativa=variante=='nativa')
                page.set_content(f'<base href="{base}">' + html)
            for _ in range(args.repeticoes):
                inicio = perf_counter()
                pa, pb = [_extrair_page(page, base, ['Início'], lambda _: None, profunda=False)
                          for page, base in zip(pages, bases)]
                extraido = perf_counter()
                motor = Inteligencia(Metricas())
                motor.comparar(pa.itens,pb.itens,pa,pb,'PRD','DES',*bases)
                _link_pairs(pa,pb,True,*bases)
                tempos.append(dict(extracao_segundos=extraido-inicio,comparacao_com_links_segundos=perf_counter()-extraido))
            escala[variante] = dict(medianas=mediana(tempos),controles_extras_por_pagina=args.elementos,
                                   itens=[len(pa.itens),len(pb.itens)],equivalencias=len(motor.equivalencias))
        estado_acessivel = pages[1].locator('body').aria_snapshot()
        cruzamento = dict(menuitem='menuitem "Atendimento"' in estado_acessivel,
            botao='button "Preferências do portal"' in estado_acessivel,
            tab='tab "Resumo"' in estado_acessivel, url='/servicos' in estado_acessivel,
            id_painel='resumo-b' in estado_acessivel)
    print(json.dumps(dict(medianas=mediana(amostras),amostras=amostras,qualidade=qualidade,
        escala=escala,
        sinais_em_aria_snapshot=cruzamento,pico_rss_python_bytes=pico_rss()),
        ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
