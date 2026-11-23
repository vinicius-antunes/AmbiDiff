"""Regressões da triagem de textos e dos contratos que ela deve preservar."""
from difflib import SequenceMatcher
from functools import partial
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ambidiff.core import Item, Pagina, _parear_textos, comparacao, normalizar, titulo_normalizado
from ambidiff.intelligence import separar_editoriais
from ambidiff.paired import _link_pairs, agrupar_registros
from test_navigation_async import portais, varrer


A = 'https://a.test/'
B = 'https://b.test/'


def item(nome, local='Serviços', *, tipo='Texto', destino='', chave=None, **kwargs):
    return Item(tipo, nome if chave is None else chave, nome, local=local, destino=destino, **kwargs)


def paginas(a, b):
    return Pagina(A, '@inicio', 'Portal', a), Pagina(B, '@inicio', 'Portal', b)


def comparar(a, b):
    return comparacao(a, b, *paginas(a, b), 'PRD', 'DES')


def pares_legados(a, b):
    """Seleção da Etapa 3, usada como oráculo de desempate e orientação."""
    usados = set()
    for ia, x in enumerate(a):
        if x.tipo != 'Texto' or len(x.nome) < 24:
            continue
        notas = []
        for ib, y in enumerate(b):
            if ib in usados or y.tipo != 'Texto' or len(y.nome) < 24:
                continue
            if x.local and y.local and titulo_normalizado(x.local) != titulo_normalizado(y.local):
                continue
            notas.append((SequenceMatcher(None, normalizar(x.nome), normalizar(y.nome)).ratio(), ib))
        if notas:
            nota, ib = max(notas, key=lambda t: t[0])
            if nota >= .82:
                usados.add(ib)
                yield ia, ib


class RapidFuzzTests(unittest.TestCase):
    def test_textos_exatos_com_normalizacao_existente(self):
        a = [item('  Informações sobre serviços  PÚBLICOS')]
        b = [item('informações sobre serviços públicos')]
        with patch('ambidiff.core.process.extract_iter', side_effect=AssertionError('comparação aproximada')):
            self.assertEqual(comparar(a, b), [])

    def test_variacao_no_limiar_original_e_contexto_normalizado(self):
        prefixo = 'abcdefghij' * 4 + 'k'
        a = item(prefixo + 'p' * 9, 'Serviços Públicos')
        b = item(prefixo + 'q' * 9, 'Servicos/Publicos')
        self.assertEqual(SequenceMatcher(None, a.nome, b.nome).ratio(), .82)
        d, = comparar([a], [b])
        self.assertEqual((d['situacao'], d['texto_a'], d['texto_b']), ('Texto diferente', a.nome, b.nome))

    def test_indel_alto_para_assuntos_distintos_exige_confirmacao(self):
        a = item('Consultar autorização ambiental para transporte de resíduos')
        b = item('Consultar autorização ambiental para armazenamento de produtos')
        resultados = comparar([a], [b])
        self.assertEqual({d['presente_em'] for d in resultados}, {'PRD', 'DES'})
        self.assertEqual({d['elemento'] for d in resultados}, {a.nome, b.nome})
        self.assertTrue(all('texto_b' not in d for d in resultados))

    def test_ambiguidade_e_duplicacao_respeitam_a_ordem_historica(self):
        base = 'O atendimento público será realizado na sala '
        a = [item(base + 'A.', 'Serviços'), item(base + 'D.', 'Serviços')]
        b = [item(base + 'B.', '', chave='primeiro'), item(base + 'C.', 'Serviços'),
             item(base + 'C.', 'Serviços', chave='repetido')]
        self.assertEqual(list(_parear_textos(a, b)), [(0, 0), (1, 1)])
        divergencias = comparar(a, b)
        self.assertEqual([d['situacao'] for d in divergencias],
                         ['Texto diferente', 'Texto diferente', 'Divergência para revisão'])
        self.assertEqual(divergencias[-1]['presente_em'], 'DES')

    def test_triagem_coincide_com_selecao_legada_em_entradas_variadas(self):
        rng = random.Random(947)
        trechos = ['Informações para solicitar licença ambiental hoje.',
                   'Informações para solicitar licença ambiental amanhã.',
                   'Informações para solicitar documento ambiental hoje.',
                   'Procedimento interno para técnicos estaduais disponível.',
                   'Suporte público é oferecido no portal de serviços.',
                   'abreviação', 'z' * 230 + 'dois tipos de formulário',
                   'z' * 230 + 'dois tipos de formulários', ' ' * 24]
        locais = ['Serviços', 'Servicos', '', ' ', '!!', 'Documentação']
        for _ in range(60):
            criar = partial(item, tipo='Texto')
            a = [criar(rng.choice(trechos), rng.choice(locais)) for _ in range(rng.randrange(1, 15))]
            b = [criar(rng.choice(trechos), rng.choice(locais)) for _ in range(rng.randrange(1, 15))]
            for esquerda, direita in ((a, b), (b, a)):
                self.assertEqual(list(_parear_textos(esquerda, direita)),
                                 list(pares_legados(esquerda, direita)))

    def test_menus_reposicionados_e_opcoes_duplicadas_usam_contexto_e_rota(self):
        opcao = partial(item, tipo='Opção')
        a = [opcao('Serviços ao cidadão', 'Menu principal', destino=A+'servicos'),
             opcao('Consultar', 'Menu lateral', destino=A+'consulta'),
             opcao('Consultar', 'Rodapé', destino=A+'rodape')]
        b = [opcao('Consultar', 'Rodapé', destino=B+'rodape'),
             opcao('Serviços ao cidadão', 'Cabeçalho', destino=B+'servicos'),
             opcao('Consultar', 'Menu lateral', destino=B+'consulta')]
        self.assertCountEqual(_link_pairs(*paginas(a, b), aceitar_rotulos=True),
                              [(a[0], b[1]), (a[1], b[2]), (a[2], b[0])])

    def test_rotulos_de_servicos_e_titulos_das_portarias_nao_substituem_destinos(self):
        a = [item('Consultar solicitação de atendimento', tipo='Opção', destino=A+'solicitacao',
                  funcao='link', estrutura='estrutura'),
             item('Portaria 100 de regulamentação estadual', 'Legislação',
                  tipo='Documento', destino=A+'portaria100.pdf', funcao='link', estrutura='estrutura')]
        b = [item('Consultar solicitações de atendimento', tipo='Opção', destino=B+'andamento',
                  funcao='link', estrutura='estrutura'),
             item('Portaria 101 de regulamentação estadual', 'Legislação',
                  tipo='Documento', destino=B+'portaria101.pdf', funcao='link', estrutura='estrutura')]
        self.assertEqual(_link_pairs(*paginas(a, b), aceitar_rotulos=True), [])
        d = comparar(a, b)
        self.assertCountEqual([r['referencia'] for r in d], [i.destino for i in a+b])
        self.assertTrue(all('texto_b' not in r for r in d))

    def test_diferenca_editorial_e_divs_estruturais_preservam_seus_ids(self):
        edital = 'A publicação do edital ocorreu às quinze horas.'
        a = [item(edital, 'Notícias', natureza='editorial'),
             item('ÁUDIOS', 'Menu', tipo='Opção', destino=A+'audios')]
        b = [item(edital.replace('quinze', 'dezesseis'), 'Notícias', natureza='editorial'),
             item('VÍDEOS', 'Menu', tipo='Opção', destino=B+'videos')]
        pa, pb = paginas(a, b)
        dados = comparar(a, b)
        regs, editoriais = separar_editoriais(dados, pa, pb, a, b, ('PRD', 'DES'), '')
        alteracao, = editoriais
        self.assertEqual((alteracao['texto_a'], alteracao['texto_b']), (a[0].nome, b[0].nome))
        divs = agrupar_registros(regs)
        with patch('ambidiff.core._parear_textos', side_effect=pares_legados):
            regs_legados, _ = separar_editoriais(comparar(a, b), pa, pb, a, b, ('PRD', 'DES'), '')
        self.assertEqual(divs, agrupar_registros(regs_legados))
        self.assertEqual({r['elemento'] for r in divs}, {'ÁUDIOS', 'VÍDEOS'})
        self.assertEqual({r['tag_tecnica'] for r in divs}, {'OPCAO_AUSENTE'})

    def test_fluxo_playwright_sincrono_e_assincrono_preserva_evidencias(self):
        def responder(lado, rota, _):
            html = '<main><h1>Portal institucional</h1>'
            if rota == '/':
                prazo = 'quinze' if lado else 'dezoito'
                html += f'<p>O prazo de atendimento presencial termina às {prazo} horas.</p>'
                if lado:
                    html += '<button id="audios">ÁUDIOS</button>'
                html += '<nav><a href="/atalho">Consultar detalhes</a></nav>'
            elif rota == '/atalho':
                return 302, {'Location': '/destino-b' if lado else '/destino-a'}, ''
            return 200, {}, html + '</main>'

        with portais(responder) as bases, TemporaryDirectory() as anterior, TemporaryDirectory() as novo:
            sync = varrer(bases, async_=False, evidencias_dir=Path(anterior)/'evidencias')
            async_ = varrer(bases, evidencias_dir=Path(novo)/'evidencias')
            self.assertEqual(sync['divergencias'], async_['divergencias'])
            self.assertEqual(sync['estados_pares'], async_['estados_pares'])
            tipos = {d['tipo'] for d in async_['divergencias']}
            self.assertTrue({'Texto', 'Opção', 'Redirecionamento'} <= tipos)
            audio = next(d for d in async_['divergencias'] if d['elemento'] == 'ÁUDIOS')
            self.assertEqual(audio['presente_em'], 'DES')
            for d in async_['divergencias']:
                self.assertEqual(set(d['evidencias']), {'PRD', 'DES'})
                for nome in d['evidencias'].values():
                    arquivo = (Path(novo)/nome).read_bytes()
                    self.assertTrue(arquivo.startswith(b'\x89PNG\r\n\x1a\n'))
                    self.assertEqual(arquivo, (Path(anterior)/nome).read_bytes())
