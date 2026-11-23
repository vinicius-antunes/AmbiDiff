"""Persistência experimental com fixtures, Chromium loopback e subprocessos locais."""
from base64 import b64decode
from contextlib import closing
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ambidiff import checkpoints
from ambidiff.checkpoint_sqlite import CheckpointSQLite, ErroCheckpointSQLite
from ambidiff.core import _abrir, comparacao
from ambidiff.paired import executar_pareado
from fixtures_perf import portais_perf
from test_intermat import A, B
from test_update18 import cadeia, executar
from test_update19 import run


ROOT = Path(__file__).resolve().parents[1]
RID = '20261123_100000_aaaaaa'
RETOMADA = '20261123_100001_bbbbbb'
PNG = b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGMwKNjwHwAEdAJQlfj/pwAAAABJRU5ErkJggg==')


def ids(relatorio):
    return {registro['elemento']: registro['id'] for registro in relatorio['divergencias']}


class CheckpointSQLiteTests(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.banco = CheckpointSQLite(self.pasta, RID)

    def interromper(self, callback):
        parar = threading.Event()

        def log(mensagem):
            if mensagem.startswith('[PRD/DES] 1 pares'):
                parar.set()

        relatorio, abertas, _ = executar(cadeia(4), parar=parar, ao_log=log, checkpoint=callback)
        self.assertEqual(relatorio['andamento']['pares_comparados'], 1)
        return relatorio, abertas

    def snapshot(self):
        snapshots = []
        self.interromper(lambda dados: snapshots.append(copy.deepcopy(dados)))
        return dict(snapshots[-1], id=RID)

    def subprocesso(self, codigo, *args, entrada=None, timeout=30):
        return subprocess.run([sys.executable, '-B', '-c', codigo, *map(str, args)],
                              cwd=ROOT, input=entrada, capture_output=True, text=True,
                              encoding='utf-8', timeout=timeout)

    def test_interrupcao_reabre_e_retomada_sem_duplicar_ids(self):
        interrompido, abertas = self.interromper(self.banco.gravar)
        self.assertFalse(self.banco.caminho.with_suffix('.json').exists())
        if os.name == 'posix':
            self.assertEqual(self.banco.caminho.stat().st_mode & 0o077, 0)
        reaberto = CheckpointSQLite(self.pasta, RID)
        processo = self.subprocesso("""
import json, sys
from ambidiff.checkpoint_sqlite import CheckpointSQLite
print(json.dumps(CheckpointSQLite(*sys.argv[1:]).ler()))
""", self.pasta, RID)
        self.assertEqual(processo.returncode, 0, processo.stderr)
        snapshot = json.loads(processo.stdout)
        estado = checkpoints.validar(snapshot['retomada'])
        self.assertEqual(estado['visitados'], [[A, B]])
        self.assertEqual(estado['fila'], [[A + '1', B + '1', ['Página inicial', 'Próximo']]])
        self.assertEqual(ids(reaberto.recuperar()), ids(interrompido))

        destino = CheckpointSQLite(self.pasta, RETOMADA)
        final, outras, _ = executar(cadeia(4), retomada=copy.deepcopy(snapshot['retomada']),
                                    checkpoint=destino.gravar)
        self.assertEqual(final['andamento']['pares_comparados'], 4)
        self.assertEqual(final['andamento']['pares_pendentes'], 0)
        self.assertFalse(set(abertas) & set(outras))
        self.assertEqual(ids(final), ids(interrompido))
        self.assertEqual(sum(d['elemento'] == 'ÁUDIOS' for d in final['divergencias']), 1)
        self.assertEqual(destino.ler()['andamento']['pares_comparados'], 4)
        self.assertEqual(reaberto.ler(), snapshot)

    def test_json_v1_permanece_legivel_e_pertence_a_execucao_original(self):
        snapshot = self.snapshot()
        legado = self.banco.caminho.with_suffix('.json')
        checkpoints.gravar(legado, snapshot)
        original = legado.read_bytes()
        with self.assertRaisesRegex(ErroCheckpointSQLite, 'já tem um checkpoint JSON'):
            self.banco.gravar(snapshot)
        self.assertFalse(self.banco.caminho.exists())

        destino = CheckpointSQLite(self.pasta, RETOMADA)
        with self.assertRaisesRegex(ErroCheckpointSQLite, 'outra execução'):
            destino.gravar(snapshot)
        retomada = json.loads(original)['retomada']
        checkpoints.validar(retomada)
        final, abertas, _ = executar(cadeia(4), retomada=retomada, checkpoint=destino.gravar)
        self.assertNotIn(A, abertas)
        self.assertEqual(final['andamento']['pares_comparados'], 4)
        self.assertEqual(ids(final), ids(checkpoints.recuperar(snapshot)))
        self.assertEqual(legado.read_bytes(), original)

    def test_falha_automacao_preserva_resultados_confirmados_e_par_pendente(self):
        def comparar(*args, **kwargs):
            if args[2].url == A + '1':
                raise RuntimeError('Falha sintética durante comparação')
            return comparacao(*args, **kwargs)

        with self.assertRaisesRegex(RuntimeError, 'Falha sintética'):
            run(n=3, comparar=comparar, checkpoints=SimpleNamespace(append=self.banco.gravar))
        snapshot = self.banco.ler()
        estado = checkpoints.validar(snapshot['retomada'])
        self.assertEqual(snapshot['motivo_checkpoint'], 'falha_fatal')
        self.assertEqual(estado['visitados'], [[A, B]])
        self.assertIn([A + '1', B + '1'], [par[:2] for par in estado['fila']])
        self.assertEqual(len(estado['brutos']), 1)
        final, _, abertas = run(n=3, retomada=snapshot['retomada'])
        self.assertEqual(final['andamento']['pares_comparados'], 3)
        self.assertNotIn(A, abertas)
        self.assertEqual(ids(final), ids(self.banco.recuperar()))

    def test_chromium_fechado_reabre_checkpoint_e_termina_no_motor_assincrono(self):
        fechado = False
        parar = threading.Event()

        def abrir(pagina, url):
            nonlocal fechado
            if not fechado and url.endswith('/pagina/1'):
                fechado = True
                pagina.context.browser.close()
            return _abrir(pagina, url)

        def checkpoint(snapshot):
            self.banco.gravar(snapshot)
            if snapshot['motivo_checkpoint'] == 'falha_recurso':
                parar.set()

        def executar_local(bases, evento, **kwargs):
            return executar_pareado(*bases, 'PRD', 'DES', evento, lambda _: None, lambda _: None, **kwargs)

        with portais_perf(3) as (bases, requisicoes):
            with patch('ambidiff.paired._abrir', side_effect=abrir):
                interrompido = executar_local(bases, parar, checkpoint=checkpoint)
            self.assertTrue(fechado)
            self.assertEqual(interrompido['andamento']['pares_comparados'], 1)
            self.assertGreater(interrompido['andamento']['pares_pendentes'], 0)
            snapshot = CheckpointSQLite(self.pasta, RID).ler()
            estado = checkpoints.validar(snapshot['retomada'])
            self.assertEqual(estado['visitados'], [bases])
            self.assertTrue(estado['diagnosticos_pares'])
            requisicoes.clear()
            destino = CheckpointSQLite(self.pasta, RETOMADA)
            final = executar_local(bases, threading.Event(), navegacao_assincrona=True,
                                  retomada=snapshot['retomada'], checkpoint=destino.gravar)
            self.assertNotIn('/', [caminho for _, caminho in requisicoes])
        self.assertEqual(final['andamento']['pares_comparados'], 3)
        self.assertEqual(final['andamento']['pares_pendentes'], 0)
        for elemento, ident in ids(interrompido).items():
            self.assertEqual(ids(final)[elemento], ident)
        self.assertEqual(len({d['id'] for d in final['divergencias']}), len(final['divergencias']))

    def test_processo_encerrado_antes_de_confirmar_preserva_estado_nos_dois_formatos(self):
        anterior = self.snapshot()
        snapshots = []
        resultado, _, _ = executar(cadeia(4), retomada=copy.deepcopy(anterior['retomada']),
                                   checkpoint=lambda dados: snapshots.append(copy.deepcopy(dados)))
        self.assertEqual(resultado['andamento']['pares_comparados'], 4)
        novo = dict(snapshots[-1], id=RID, carga='x' * (2 << 20))
        programa = """
import json, os, sqlite3, sys
from ambidiff import checkpoints
from ambidiff.checkpoint_sqlite import CheckpointSQLite

pasta, rid, formato = sys.argv[1:]
banco = CheckpointSQLite(pasta, rid)
snapshot = json.load(sys.stdin)
if formato == 'sqlite':
    conectar = sqlite3.connect
    def conexao(*args, **kwargs):
        con = conectar(*args, **kwargs)
        con.execute('PRAGMA cache_size=16')
        con.set_trace_callback(lambda sql: os._exit(73) if sql == 'COMMIT' else None)
        return con
    sqlite3.connect = conexao
    banco.gravar(snapshot)
else:
    checkpoints.os.replace = lambda *_: os._exit(73)
    checkpoints.gravar(banco.caminho.with_suffix('.json'), snapshot)
"""
        for formato in ('sqlite', 'json'):
            with self.subTest(formato=formato):
                pasta = self.pasta / formato
                pasta.mkdir()
                banco = CheckpointSQLite(pasta, RID)
                legado = banco.caminho.with_suffix('.json')
                if formato == 'sqlite':
                    banco.gravar(anterior)
                else:
                    checkpoints.gravar(legado, anterior)
                processo = self.subprocesso(programa, pasta, RID, formato, entrada=json.dumps(novo))
                self.assertEqual(processo.returncode, 73, processo.stderr)
                salvo = banco.ler() if formato == 'sqlite' else json.loads(legado.read_bytes())
                self.assertEqual(salvo, anterior)
                estado = checkpoints.validar(salvo['retomada'])
                self.assertEqual(estado['visitados'], [[A, B]])
                self.assertTrue(estado['fila'])
                self.assertEqual(ids(checkpoints.recuperar(salvo)), ids(checkpoints.recuperar(anterior)))

    def test_bloqueio_disco_cheio_e_falha_escrita_preservam_commit_anterior(self):
        anterior = self.snapshot()
        self.banco.gravar(anterior)
        novo = dict(anterior, carga='x' * (2 << 20))

        with closing(sqlite3.connect(self.banco.caminho)) as outra:
            outra.execute('BEGIN IMMEDIATE')
            with self.assertRaisesRegex(ErroCheckpointSQLite, 'bloqueado'):
                self.banco.gravar(novo)
        self.assertEqual(self.banco.ler(), anterior)

        conectar = sqlite3.connect

        def sem_espaco(caminho, **kwargs):
            con = conectar(caminho, **kwargs)
            paginas, = con.execute('PRAGMA page_count').fetchone()
            con.execute(f'PRAGMA max_page_count={paginas}')
            return con

        with patch('ambidiff.checkpoint_sqlite.sqlite3.connect', side_effect=sem_espaco):
            with self.assertRaisesRegex(ErroCheckpointSQLite, 'Disco cheio'):
                self.banco.gravar(novo)
        self.assertEqual(self.banco.ler(), anterior)

        def somente_leitura(caminho, **kwargs):
            return conectar(caminho.replace('mode=rw', 'mode=ro'), **kwargs)

        with patch('ambidiff.checkpoint_sqlite.sqlite3.connect', side_effect=somente_leitura):
            with self.assertRaisesRegex(ErroCheckpointSQLite, 'Falha de leitura ou escrita'):
                self.banco.gravar(novo)
        self.assertEqual(self.banco.ler(), anterior)

    def test_recusa_conteudo_alterado_e_banco_corrompido(self):
        snapshot = self.snapshot()
        self.banco.gravar(snapshot)
        with closing(sqlite3.connect(self.banco.caminho)) as con, con:
            con.execute('UPDATE checkpoint SET dados=?', (b'{}',))
        with self.assertRaisesRegex(ErroCheckpointSQLite, 'Integridade'):
            self.banco.ler()

        self.banco.caminho.write_bytes(b'arquivo de teste corrompido')
        with self.assertRaisesRegex(ErroCheckpointSQLite, 'corrompido'):
            self.banco.recuperar()
        with self.assertRaisesRegex(ErroCheckpointSQLite, 'corrompido'):
            self.banco.gravar(snapshot)

    def test_relatorio_parcial_e_exportacoes_apos_reinicio_com_retomada_invalida(self):
        snapshot = self.snapshot()
        id_audio = ids(checkpoints.recuperar(snapshot))['ÁUDIOS']
        evidencia = f'evidencias_{RID}/{id_audio}.png'
        captura = self.pasta / evidencia
        captura.parent.mkdir()
        captura.write_bytes(PNG)
        snapshot['evidencias_preservadas'][id_audio] = {'evidencia': evidencia}
        snapshot['retomada']['sha256_estado'] = 'invalido'
        self.banco.gravar(snapshot)

        primeiro = self.subprocesso("""
import sys
from pathlib import Path
from ambidiff.checkpoint_sqlite import CheckpointSQLite
from ambidiff.reports import exportar

pasta, rid, id_audio, evidencia = sys.argv[1:]
banco = CheckpointSQLite(pasta, rid)
try:
    banco.ler()
except ValueError:
    pass
else:
    raise AssertionError('Retomada inválida foi aceita')
parcial = banco.recuperar()
assert parcial['situacao_analise'] == 'parcial'
assert parcial['andamento']['pares_comparados'] == 1
assert parcial['andamento']['pares_pendentes'] == 1
assert any(d['id'] == id_audio and d['evidencia'] == evidencia for d in parcial['divergencias'])
assert 'retomada' not in parcial
exportar(parcial, Path(pasta), rid)
""", self.pasta, RID, id_audio, evidencia)
        self.assertEqual(primeiro.returncode, 0, primeiro.stderr)
        self.banco.caminho.write_bytes(b'banco ilegivel apos materializacao')

        reinicio = self.subprocesso("""
import sys
from pathlib import Path
from web import server

pasta, rid, id_audio, evidencia = sys.argv[1:]
server.PASTA = Path(pasta)
server.HISTORY_PATH = server.PASTA / 'historico.json'
with server.app.test_client() as cliente:
    resposta = cliente.get(f'/api/relatorio/{rid}')
    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    relatorio = resposta.get_json()
    assert any(d['id'] == id_audio and d['evidencia'] == evidencia for d in relatorio['divergencias'])
    imagem = cliente.get(f'/evidencia/{rid}/{id_audio}.png', buffered=True)
    assert imagem.status_code == 200 and imagem.get_data() == (server.PASTA / evidencia).read_bytes()
    for ext in ('json', 'csv', 'html', 'pdf'):
        resposta = cliente.get(f'/download/{rid}/{ext}', buffered=True)
        assert resposta.status_code == 200, (ext, resposta.status_code, resposta.get_data()[:300])
        corpo = resposta.get_data()
        if ext == 'pdf':
            assert corpo.startswith(b'%PDF')
        else:
            assert id_audio.encode() in corpo, ext
        if ext == 'html':
            assert b'data:image/png;base64,' in corpo
""", self.pasta, RID, id_audio, evidencia, timeout=90)
        self.assertEqual(reinicio.returncode, 0, reinicio.stderr)
