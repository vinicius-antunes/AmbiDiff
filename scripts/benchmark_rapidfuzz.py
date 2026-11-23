"""Compara a triagem sobre elementos sintéticos e um checkout anterior."""
import argparse
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import platform
import random
from statistics import median
import subprocess
import sys
from time import perf_counter
import tracemalloc


RAIZ = Path(__file__).resolve().parents[1]
CASOS = [
    ('flexão', True, 'Informações sobre serviços públicos', 'Informações sobre serviço público'),
    ('digitação', True, 'Emita o comprovante de regularidade cadastral', 'Emita o comprovante de regularidade cadstral'),
    ('prazo', True, 'O prazo para interposição do recurso é de cinco dias úteis.',
     'O prazo para interposição do recurso é de dez dias úteis.'),
    ('ampliação', True, 'O atendimento presencial exige agendamento prévio.',
     'O atendimento presencial exige agendamento prévio, válido somente para a unidade central.'),
    ('reorganização', True, 'Protocolo eletrônico para documentos de licenciamento ambiental',
     'Licenciamento ambiental documentos para protocolo eletrônico'),
    ('reescrita', True, 'O suporte técnico funciona das oito às dezessete horas.',
     'Horário do atendimento técnico: das 8h até as 17h.'),
    ('assuntos', False, 'Agendamento de visita técnica para escolas da rede estadual',
     'Agendamento de vistoria técnica para obras da rede estadual'),
    ('perfis', False, 'O cidadão consulta a autorização do servidor no painel',
     'O servidor consulta a autorização do cidadão no painel'),
    ('objetos', False, 'Consultar autorização ambiental para transporte de resíduos',
     'Consultar autorização ambiental para armazenamento de produtos'),
    ('aviso e guia', False, 'A unidade publica os resultados do edital de benefícios.',
     'Unidade de apoio publica guia para receber benefícios.'),
    ('próximo do corte', True, 'abcdefghijabcdefghijabcdez', 'abcdefghijabcdefghijxyzvu'),
    ('subconjunto', False, 'Cadastro de agentes culturais do Estado',
     'O manual de cadastro de agentes culturais do Estado inclui regras de edição e faturamento.'),
]


def qualidade(observados, esperados):
    return {'corretos': len(observados & esperados), 'falsos_positivos': len(observados - esperados),
            'falsos_negativos': len(esperados - observados)}


def calibrar():
    from ambidiff.core import normalizar
    from rapidfuzz import fuzz
    from rapidfuzz.distance import Indel, Levenshtein

    algoritmos = {
        'SequenceMatcher': lambda a, b: SequenceMatcher(None, a, b).ratio(),
        'Indel': Indel.normalized_similarity,
        'Levenshtein': Levenshtein.normalized_similarity,
        'token_sort_ratio': lambda a, b: fuzz.token_sort_ratio(a, b)/100,
        'token_set_ratio': lambda a, b: fuzz.token_set_ratio(a, b)/100,
    }
    esperado = {nome for nome, positivo, _, _ in CASOS if positivo}
    saida = {}
    for nome, algoritmo in algoritmos.items():
        notas = {caso: round(algoritmo(normalizar(a), normalizar(b)), 12) for caso, _, a, b in CASOS}
        cortes = [.82] if nome == 'SequenceMatcher' else [n/100 for n in range(50, 100)]
        resultados = [(corte, qualidade({k for k, v in notas.items() if v >= corte}, esperado)) for corte in cortes]
        corte, qualidade_corte = min(resultados, key=lambda t: (
            t[1]['falsos_positivos'] + t[1]['falsos_negativos'], t[1]['falsos_positivos'], abs(t[0]-.82)))
        saida[nome] = {'corte_no_painel': corte, **qualidade_corte, 'notas': notas}
    return saida


def elementos(cenario):
    from ambidiff.core import Item

    a, b, esperados = [], [], set()
    for local, positivo, x, y in CASOS:
        a.append(Item('Texto', x, x, local))
        b.append(Item('Texto', y, y, local))
        if positivo:
            esperados.add((x, y))

    base = 'O atendimento da unidade acontecerá na sala '
    a.append(Item('Texto', 'aviso', base+'A.', 'Salas'))
    b.extend(Item('Texto', chave, base+letra+'.', 'Salas') for chave, letra in (
        ('primeiro', 'B'), ('segundo', 'C'), ('segundo duplicado', 'C')))
    ambiguos = {base+'A.'}

    for lado, itens in enumerate((a, b)):
        itens.extend([
            Item('Texto', 'Exato', 'Orientações de atendimento público', 'Serviços'),
            Item('Opção', 'Consultar', 'Consultar', 'Menu' if not lado else 'Rodapé',
                 f'https://{lado}.test/consulta'),
            Item('Documento', f'Portaria 10{lado}', f'Portaria 10{lado} de regulamentação',
                 'Legislação', f'https://{lado}.test/portaria10{lado}.pdf'),
        ])
    a.append(Item('Opção', 'ÁUDIOS', 'ÁUDIOS', 'Menu'))
    x = 'O edital de atendimento foi publicado às quinze horas.'
    y = x.replace('quinze', 'dezoito')
    a.append(Item('Texto', x, x, 'Notícias', natureza='editorial'))
    b.append(Item('Texto', y, y, 'Notícias', natureza='editorial'))
    esperados.add((x, y))

    if cenario != 'pequeno':
        rng = random.Random(4204)
        termos = ('planejamento saúde controle pesquisa política orçamento segurança intercâmbio laboratório '
                  'formulário viagens arquivo circulação moradores arquitetura escola conservação espaço '
                  'licença patrimônio museu visitas código cuidado benefício direitos audiência cadastro '
                  'avaliação relatório publicação protocolo cálculo resíduos inventário prazos').split()
        for i in range(440 if cenario == 'grande' else 120):
            local = f'Seção {i%4}' if cenario == 'grande' else 'Acervo'
            if cenario == 'grande':
                x = ' '.join(rng.sample(termos, 8)).capitalize()
            else:
                x = f'O processamento da solicitação seguirá para a unidade responsável pelo protocolo {i:03}.'
            y = x + ' Em revisão.'
            a.append(Item('Texto', x, x, local))
            b.append(Item('Texto', y, y, local))
            esperados.add((x, y))
        rng.shuffle(a)
        rng.shuffle(b)
    return a, b, esperados, ambiguos


def medir(checkout, cenario, repeticoes):
    sys.path.insert(0, str(checkout))
    from ambidiff.core import Pagina, comparacao
    from ambidiff.intelligence import separar_editoriais
    from ambidiff.paired import _link_pairs, agrupar_registros
    from ambidiff.relevance import classificar

    a, b, esperados, ambiguos = elementos(cenario)
    pa, pb = (Pagina(f'https://{lado}.test/', '@inicio', 'Portal de teste', itens)
              for lado, itens in enumerate((a, b)))
    tempos = []
    for _ in range(repeticoes):
        inicio = perf_counter()
        divs = comparacao(a, b, pa, pb, 'PRD', 'DES')
        tempos.append(perf_counter() - inicio)
    tracemalloc.start()
    divisao = comparacao(a, b, pa, pb, 'PRD', 'DES')
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert divisao == divs
    pares = {(d['texto_a'], d['texto_b']) for d in divs if 'texto_b' in d and d['texto_a'] not in ambiguos}
    estrutural, editorial = separar_editoriais(divs, pa, pb, a, b, ('PRD', 'DES'), '')
    registros = agrupar_registros(estrutural)
    classes = [classificar(d)[0] for d in registros]
    links = [(x.nome, y.nome, x.destino, y.destino) for x, y in _link_pairs(pa, pb, aceitar_rotulos=True)]
    hash_saida = hashlib.sha256(json.dumps([registros, editorial, classes, links], sort_keys=True).encode()).hexdigest()
    try:
        import resource
    except ImportError:
        rss = None
    else:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 if sys.platform == 'darwin' else 1)
    return {
        'elementos': [len(a), len(b)], 'amostras_segundos': tempos, 'mediana_segundos': median(tempos),
        'pico_python_kib': pico/1024, 'pico_rss_processo_kib': rss,
        'associacoes': qualidade(pares, esperados),
        'grupos_com_ambiguidade': sum(d.get('texto_a') in ambiguos for d in divs),
        'divs': len(registros), 'editoriais': len(editorial), 'classificacoes': dict(Counter(classes)),
        'sha256_resultado': hash_saida,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--repeticoes', type=int, default=5)
    parser.add_argument('--medir', nargs=2, metavar=('CHECKOUT', 'CENARIO'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeticoes < 1:
        parser.error('Informe pelo menos uma repetição.')
    if args.medir:
        checkout, cenario = args.medir
        print(json.dumps(medir(Path(checkout), cenario, args.repeticoes), ensure_ascii=False))
        return
    if not args.baseline:
        parser.error('Informe o checkout da referência com --baseline.')
    sys.path.insert(0, str(RAIZ))
    resultados = {'python': platform.python_version(), 'calibracao': calibrar(), 'cenarios': {}}
    for cenario in ('pequeno', 'grande', 'denso'):
        runs = {}
        print(f'Medindo {cenario}', file=sys.stderr, flush=True)
        for versao, checkout in (('anterior', args.baseline.resolve()), ('rapidfuzz', RAIZ)):
            dados = subprocess.check_output([sys.executable, '-B', __file__, '--medir', str(checkout), cenario,
                                            '--repeticoes', str(args.repeticoes)], text=True)
            runs[versao] = json.loads(dados)
        runs['mesma_saida'] = runs['anterior']['sha256_resultado'] == runs['rapidfuzz']['sha256_resultado']
        resultados['cenarios'][cenario] = runs
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
