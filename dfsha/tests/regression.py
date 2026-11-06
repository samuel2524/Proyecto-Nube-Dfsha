"""Regresión de contrato por HTTPS/gRPC contra un clúster real.

No detiene nodos ni borra datos externos. Cada ejecución usa un directorio nuevo.
    python -m tests.regression
"""
import hashlib
import json
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path

import grpc

from dfsha import dfsha_pb2 as pb
from dfsha import dfsha_pb2_grpc as rpc
from dfsha.client import DFS, Error, cifrar


class Regression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = '/regression-' + uuid.uuid4().hex[:12]
        cls.dfs = DFS()
        for attempt in range(30):
            try:
                cls.dfs.login('andres', 'clave123')
                admin = DFS()
                admin.login('admin', 'admin123')
                if len([n for n in admin.nodes()['nodos'] if n['estado'] == 'vivo']) == 4:
                    break
            except Error:
                pass
            time.sleep(2)
        else:
            raise RuntimeError('el clúster no quedó saludable')
        cls.dfs.mkdir(cls.path)

    def setUp(self):
        self.opened = []
        self.file = self.path + '/' + self._testMethodName

    def tearDown(self):
        for file in self.opened:
            if file.fd:
                file.abort()

    def opened_file(self, path=None, mode='r', create=False):
        file = self.dfs.open(path or self.file, mode, create=create)
        self.opened.append(file)
        return file

    def seed(self, data=b'0000'):
        file = self.opened_file(mode='w', create=True)
        file.write(0, data)
        file.close()

    def expect(self, status, function, *args, **kwargs):
        with self.assertRaises(Error) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.status, status, str(caught.exception))

    def test_roundtrip_and_snapshot_without_cache(self):
        self.seed(b'old snapshot')
        reader = self.opened_file()
        writer = self.opened_file(mode='w')
        writer.write(0, b'new snapshot')
        writer.close()
        # Primera lectura del snapshot viejo DESPUÉS de publicar: no hay caché.
        self.assertEqual(reader.read(0, 100), b'old snapshot')
        reader.refresh()
        self.assertEqual(self.opened_file().read(0, 100), b'new snapshot')

    def test_stale_block_is_rejected(self):
        self.seed()
        a, b = self.opened_file(mode='rw'), self.opened_file(mode='rw')
        a.write(0, b'A')
        a.close()
        self.expect(409, b.write, 1, b'B')
        self.assertEqual(self.opened_file().read(0, 4), b'A000')

    def test_distinct_blocks_preserve_both_changes(self):
        self.seed(b'0' * ((8 << 20) + 10))
        a, b = self.opened_file(mode='rw'), self.opened_file(mode='rw')
        a.write(0, b'A')
        b.write(a.bs, b'B')
        b.close()
        a.close()
        reader = self.opened_file()
        self.assertEqual(reader.read(0, 1), b'A')
        self.assertEqual(reader.read(a.bs, 1), b'B')

    def test_empty_replacement(self):
        self.seed(b'nonempty')
        empty = self.opened_file(mode='w')
        version = empty.close()
        self.assertEqual(version, 2)
        reader = self.opened_file()
        self.assertEqual(reader.size, 0)
        self.assertEqual(reader.read(0, 1), b'')

    def test_rm_and_rename_reject_active_writer(self):
        self.seed()
        writer = self.opened_file(mode='rw')
        writer.write(0, b'A')
        self.expect(423, self.dfs.rm, self.file)
        self.expect(423, self.dfs.mv, self.file, self.file + '-renamed')
        writer.close()
        self.dfs.mv(self.file, self.file + '-renamed')
        self.expect(404, self.dfs.stat, self.file)

    def test_cli_failed_write_releases_session(self):
        from dfsha import cli
        self.seed()
        holder = self.opened_file(mode='rw')
        holder.write(0, b'H')                       # toma el lock del bloque 0
        cli.guardar({'cwd': '/', 'token': self.dfs.token})
        self.assertEqual(cli.main(['write', self.file, '0', 'X']), 1)   # 423: el bloque está tomado
        holder.close()
        self.dfs.rm(self.file)                      # sin abort, la sesión fallida seguiría viva y rm daría 423

    def test_append_and_truncate_are_exclusive(self):
        self.seed(b'a')
        writer = self.opened_file(mode='a')
        self.expect(423, self.dfs.open, self.file, 'a')
        self.expect(423, self.dfs.open, self.file, 'w')
        writer.write(0, b'b')
        writer.close()
        self.assertEqual(self.opened_file().read(0, 100), b'ab')

    def test_commit_retry_is_idempotent(self):
        file = self.opened_file(mode='w', create=True)
        file.write(0, b'idempotent')
        fd = file.fd
        version = file.close()
        self.assertEqual(self.dfs.req('POST', f'/v1/files/{fd}/close', json=file._closed_body)['version'], version)
        self.assertEqual(self.dfs.stat(self.file)['version'], version)
        self.assertEqual(self.dfs.req('GET', f'/v1/files/{fd}/status')['version'], version)
        altered = {**file._closed_body, 'size': 999}
        self.expect(409, self.dfs.req, 'POST', f'/v1/files/{fd}/close', json=altered)

    def plan(self):
        file = self.opened_file(mode='w', create=True)
        plan = self.dfs.req('POST', f'/v1/files/{file.fd}/blocks', json={'index': 0})
        data = cifrar(file.dek, plan['block_id'], b'valid')
        sha = hashlib.sha256(data).hexdigest()
        token = self.dfs.req('POST', f'/v1/files/{file.fd}/blocks/{plan["block_id"]}/authorize',
                             json={'sha256': sha, 'size': len(data)})['token']
        return file, plan, data, sha, token

    def send(self, file, plan, data, sha, token):
        chunk = pb.WriteChunk(block_id=plan['block_id'], token=token, pipeline=plan['pipeline'],
                              sha256=sha, size=len(data), operation_id=file.fd, data=data)
        addr = plan['pipeline'][0].split('@')[1]
        return self.dfs.stub(addr).WriteBlock(iter([chunk]), timeout=30)

    def test_forged_and_duplicate_receipts_rejected(self):
        file, plan, data, sha, token = self.plan()
        endpoint = f'/v1/files/{file.fd}/blocks/{plan["block_id"]}/prepared'
        self.expect(409, self.dfs.req, 'POST', endpoint, json={'receipts': ['fake', 'fake']})
        ack = self.send(file, plan, data, sha, token)
        self.expect(409, self.dfs.req, 'POST', endpoint,
                    json={'receipts': [ack.receipts[0], ack.receipts[0]]})

    def test_unprepared_commit_rejected(self):
        file, plan, data, sha, token = self.plan()
        self.expect(409, self.dfs.req, 'POST', f'/v1/files/{file.fd}/close', json={
            'blocks': {'0': {'block_id': plan['block_id'], 'fencing': plan['fencing']}}, 'size': 5})
        self.expect(404, self.dfs.stat, self.file)

    def test_block_replay_cannot_change_contents(self):
        file, plan, data, sha, token = self.plan()
        first = self.send(file, plan, data, sha, token)
        second = self.send(file, plan, data, sha, token)
        self.assertEqual(list(first.stored), list(second.stored))
        damaged = data[:-1] + bytes([data[-1] ^ 1])
        with self.assertRaises(grpc.RpcError) as caught:
            self.send(file, plan, damaged, sha, token)
        self.assertEqual(caught.exception.code(), grpc.StatusCode.DATA_LOSS)

    def test_partial_stream_never_prepares_a_block(self):
        file, plan, data, sha, token = self.plan()
        chunk = pb.WriteChunk(block_id=plan['block_id'], token=token, pipeline=plan['pipeline'],
                              sha256=sha, size=len(data), operation_id=file.fd, data=data[:5])
        with self.assertRaises(grpc.RpcError) as caught:
            self.dfs.stub(plan['pipeline'][0].split('@')[1]).WriteBlock(iter([chunk]), timeout=10)
        self.assertEqual(caught.exception.code(), grpc.StatusCode.DATA_LOSS)
        self.expect(409, self.dfs.req, 'POST', f'/v1/files/{file.fd}/close', json={
            'blocks': {'0': {'block_id': plan['block_id'], 'fencing': plan['fencing']}}, 'size': 5})
        self.expect(404, self.dfs.stat, self.file)

    def test_client_has_no_catalog_or_signing_secrets(self):
        for filename in ('etcd.key', 'auth.key', 'capability.key', 'receipt.key'):
            self.assertFalse((Path('/certs')/filename).exists(), filename)
        self.assertNotIn('KEK', os.environ)
        self.assertNotIn('USERS', os.environ)

    def test_mtls_rejects_missing_client_certificate(self):
        file, plan, data, sha, token = self.plan()
        addr = plan['pipeline'][0].split('@')[1]
        credentials = grpc.ssl_channel_credentials(Path('/certs/ca.crt').read_bytes())
        with grpc.secure_channel(addr, credentials) as channel:
            chunk = pb.WriteChunk(block_id=plan['block_id'], token=token, pipeline=plan['pipeline'],
                                  sha256=sha, size=len(data), operation_id=file.fd, data=data)
            with self.assertRaises(grpc.RpcError):
                rpc.DataNodeStub(channel).WriteBlock(iter([chunk]), timeout=5)

    def test_partial_write_has_manifest_hash(self):
        self.seed(b'abcdef')
        writer = self.opened_file(mode='rw')
        writer.write(1, b'Z')
        writer.close()
        reader = self.opened_file()
        self.assertEqual(reader.read(0, 6), b'aZcdef')
        self.assertIsNone(reader.sha256)
        self.assertEqual(len(self.dfs.stat(self.file)['manifest_sha256']), 64)

    def test_invalid_ranges_and_r1(self):
        self.seed()
        reader = self.opened_file()
        self.expect(400, reader.read, -1, 1)
        self.expect(400, self.dfs.open, self.file, 'w', replicas=1)
        file = self.opened_file(mode='rw')
        self.expect(400, file.write, -1, b'x')

    def test_user_isolation(self):
        self.seed()
        other = DFS()
        other.login('laura', 'clave123')
        self.expect(404, other.stat, self.file)
        self.expect(403, other.nodes)

    @unittest.skipUnless(os.environ.get('RUN_LARGE') == '1', 'activar RUN_LARGE=1 para 1 GiB')
    def test_large_file_beyond_128_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp)/'large', Path(temp)/'download'
            # 129 bloques de 8 MiB: ejercita el límite de txn antiguo sin RAM proporcional.
            with source.open('wb') as output:
                for _ in range(129):
                    output.write(b'X' * (8 << 20))
            result = self.dfs.put(str(source), self.file)
            recovered = self.dfs.get(self.file, str(target))
            self.assertEqual(result['sha256'], recovered['sha256'])
            self.assertEqual(result['bloques'], 129)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Regression)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    directory = Path('resultados') / ('revision-' + time.strftime('%Y%m%d-%H%M%S'))
    directory.mkdir(parents=True, exist_ok=False)
    source_hash = hashlib.sha256()
    for path in sorted(Path('dfsha').glob('*.py')):
        source_hash.update(path.name.encode() + path.read_bytes())
    (directory/'regression.json').write_text(json.dumps({
        'environment': os.environ.get('TEST_ENVIRONMENT', 'local Docker (no AWS)'),
        'source_sha256': source_hash.hexdigest(),
        'tests': result.testsRun, 'failures': len(result.failures),
        'errors': len(result.errors), 'skipped': len(result.skipped),
        'successful': result.wasSuccessful()}, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
