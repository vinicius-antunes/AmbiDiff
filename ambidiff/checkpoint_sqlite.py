"""Persistência experimental de checkpoints v1, fora do worker padrão."""
from contextlib import closing, contextmanager
from errno import ENOSPC
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from time import perf_counter

from . import checkpoints
from .storage import valid_run


APLICACAO = 0x414D4244  # AMBD
VERSAO_BANCO = 1


class ErroCheckpointSQLite(ValueError):
    """Falha local de persistência ou leitura do checkpoint experimental."""


def _mensagem(exc):
    # O Python 3.10 ainda não expõe sqlite_errorname.
    codigo = getattr(exc, 'sqlite_errorname', '')
    texto = str(exc).casefold()
    if codigo.startswith(('SQLITE_BUSY', 'SQLITE_LOCKED')) or 'locked' in texto:
        return 'Banco de checkpoint bloqueado por outra operação.'
    if codigo == 'SQLITE_FULL' or getattr(exc, 'errno', None) == ENOSPC or 'disk is full' in texto:
        return 'Disco cheio durante a persistência do checkpoint.'
    if codigo.startswith(('SQLITE_CORRUPT', 'SQLITE_NOTADB')) or any(
            termo in texto for termo in ('malformed', 'not a database')):
        return 'Banco de checkpoint corrompido ou ilegível.'
    return 'Falha de leitura ou escrita do banco de checkpoint.'


class CheckpointSQLite:
    """Um banco por execução e um único snapshot confirmado por banco."""

    def __init__(self, pasta, run_id, *, timeout=0.25):
        if not valid_run(run_id):
            raise ValueError('ID de execução inválido.')
        self.run_id = run_id
        self.caminho = Path(pasta) / f'checkpoint_{run_id}.sqlite3'
        self.timeout = timeout

    @contextmanager
    def _conexao(self):
        try:
            # mode=rw permite recuperar o journal após uma queda sem criar
            # arquivo pela leitura nem contornar as permissões da criação.
            uri = self.caminho.resolve().as_uri() + '?mode=rw'
            with closing(sqlite3.connect(uri, uri=True, timeout=self.timeout)) as con:
                con.execute('PRAGMA trusted_schema=OFF')
                yield con
        except (sqlite3.Error, OSError) as exc:
            raise ErroCheckpointSQLite(_mensagem(exc)) from exc

    @staticmethod
    def _verificar_formato(con, *, iniciar=False):
        aplicacao, = con.execute('PRAGMA application_id').fetchone()
        versao, = con.execute('PRAGMA user_version').fetchone()
        if (aplicacao, versao) == (APLICACAO, VERSAO_BANCO):
            return
        if (not iniciar or (aplicacao, versao) != (0, 0)
                or con.execute('SELECT 1 FROM sqlite_schema LIMIT 1').fetchone()):
            raise ErroCheckpointSQLite('Banco de checkpoint incompatível ou sem transação confirmada.')
        con.execute('''CREATE TABLE checkpoint (
            slot INTEGER PRIMARY KEY CHECK (slot = 1),
            execucao TEXT NOT NULL,
            dados BLOB NOT NULL,
            integridade BLOB NOT NULL
        )''')
        con.execute(f'PRAGMA application_id={APLICACAO}')
        con.execute(f'PRAGMA user_version={VERSAO_BANCO}')

    def gravar(self, snapshot):
        """Callback do scanner. A operação anterior permanece após rollback."""
        legado = self.caminho.with_suffix('.json')
        if legado.exists() or legado.is_symlink():
            raise ErroCheckpointSQLite('A execução já tem um checkpoint JSON. Use outro ID no experimento.')
        if snapshot.get('id', self.run_id) != self.run_id:
            raise ErroCheckpointSQLite('Checkpoint de outra execução.')
        retomada = snapshot.get('retomada')
        if not isinstance(retomada, dict) or retomada.get('versao_checkpoint') != checkpoints.VERSAO:
            raise ErroCheckpointSQLite('Snapshot de checkpoint v1 obrigatório.')

        inicio = perf_counter()
        dados = json.dumps(dict(snapshot, id=self.run_id), ensure_ascii=False,
                           separators=(',', ':'), allow_nan=False).encode('utf-8')
        integridade = sha256(dados).digest()
        serializacao = perf_counter() - inicio
        inicio = perf_counter()
        try:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            try:
                self.caminho.touch(mode=0o600, exist_ok=False)
            except FileExistsError:
                pass
        except OSError as exc:
            raise ErroCheckpointSQLite(_mensagem(exc)) from exc
        with self._conexao() as con, con:
            con.execute('PRAGMA synchronous=FULL')
            con.execute('BEGIN IMMEDIATE')
            self._verificar_formato(con, iniciar=True)
            atualizacao = con.execute('''INSERT INTO checkpoint VALUES (1, ?, ?, ?)
                ON CONFLICT(slot) DO UPDATE SET dados=excluded.dados, integridade=excluded.integridade
                WHERE checkpoint.execucao=excluded.execucao''', (self.run_id, dados, integridade))
            if atualizacao.rowcount != 1:
                raise ErroCheckpointSQLite('Banco pertence a outra execução.')
        return {'serializacao_json': serializacao, 'gravacao': perf_counter() - inicio,
                'bytes': len(dados)}

    def _snapshot(self):
        if not self.caminho.is_file():
            raise FileNotFoundError('Banco de checkpoint não encontrado.')
        with self._conexao() as con:
            self._verificar_formato(con)
            row = con.execute('SELECT execucao, dados, integridade FROM checkpoint WHERE slot=1').fetchone()
        if row is None:
            raise ErroCheckpointSQLite('Banco sem checkpoint confirmado.')
        execucao, dados, integridade = row
        if execucao != self.run_id:
            raise ErroCheckpointSQLite('Banco pertence a outra execução.')
        if not isinstance(dados, bytes) or sha256(dados).digest() != integridade:
            raise ErroCheckpointSQLite('Integridade do snapshot não confirmada.')
        try:
            snapshot = json.loads(dados)
        except ValueError as exc:
            raise ErroCheckpointSQLite('Conteúdo do snapshot inválido.') from exc
        if not isinstance(snapshot, dict) or snapshot.get('id') != self.run_id:
            raise ErroCheckpointSQLite('Identificação do snapshot inválida.')
        return snapshot

    def ler(self):
        """Lê o snapshot integral e valida o estado antes de entregá-lo à retomada."""
        snapshot = self._snapshot()
        checkpoints.validar(snapshot.get('retomada'))
        return snapshot

    def recuperar(self):
        """Projeta um relatório pelo mecanismo existente, inclusive sem fila retomável."""
        snapshot = self._snapshot()
        try:
            return checkpoints.recuperar(snapshot)
        except (ValueError, TypeError, KeyError):
            # O hash do banco protege também o resultado parcial externo ao
            # pacote v1. A projeção usa esses dados se o pacote for incompatível.
            brutos = snapshot.get('brutos')
            if not isinstance(brutos, list) or any(not isinstance(r, dict) for r in brutos):
                raise
            snapshot.pop('retomada', None)
            snapshot.update(estado_execucao='falha', situacao_analise='parcial',
                            motivo_recuperacao='Resultados do último snapshot confirmado. Pacote de retomada incompatível.')
            parcial = checkpoints.recuperar(snapshot)
            evidencias = snapshot.get('evidencias_preservadas', {})
            for registro in parcial['divergencias']:
                registro.update(evidencias.get(registro['id'], {}))
            return parcial
