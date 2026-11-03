"""Pruebas de invariantes de GC y tamaño del commit con etcd en memoria.

Ejecutar en un contenedor de metadatos (identidad de prueba, nunca AWS real).
"""
import base64
import copy
import json
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from fastapi import HTTPException
from dfsha import metadata as m


class MemoryEtcd:
    def __init__(self):
        self.rows = {}
        self.revision = 1
        self.max_ops = 0

    def get(self, key):
        return copy.deepcopy(self.rows.get(key))

    def prefix(self, prefix):
        return [copy.deepcopy(v) for k, v in self.rows.items() if k.startswith(prefix)]

    def get_many(self, keys):
        return [self.get(k) for k in keys]

    def put(self, key, value, lease=None):
        self.revision += 1
        old = self.rows.get(key)
        self.rows[key] = {'key': key, 'value': copy.deepcopy(value), 'mod': self.revision,
                          'create': old['create'] if old else self.revision}
        return self.revision

    def delete(self, key):
        self.rows.pop(key, None)

    def revoke(self, lease):
        pass

    def txn(self, guards, operations, failure=()):
        self.max_ops = max(self.max_ops, len(operations), len(guards))
        for guard in guards:
            key = base64.b64decode(guard['key']).decode()
            target = guard['target'].lower() + '_revision'
            row = self.get(key)
            actual = (row['mod' if target == 'mod_revision' else 'create'] if row else 0)
            if actual != int(guard[target]):
                return False, self.revision
        for operation in operations:
            if 'request_put' in operation:
                data = operation['request_put']
                self.put(base64.b64decode(data['key']).decode(), json.loads(base64.b64decode(data['value'])))
            else:
                self.delete(base64.b64decode(operation['request_delete_range']['key']).decode())
        return True, self.revision


class Contract(unittest.TestCase):
    def setUp(self):
        self.store = MemoryEtcd()
        self.patcher = patch.object(m, 'etcd', self.store)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.ns = {'dn1': {'estado': 'vivo', 'addr': 'dn1'}}
        self.deleted = []
        self.stub = NS(DeleteBlock=lambda req, **kw: self.deleted.append(req.block_id))

    def block(self, bid='a' * 32, **extra):
        self.store.put('/bloques/' + bid, {'state': 'prepared', 'pipeline': ['dn1@dn1'],
            'replicas': ['dn1'], 'fd': 'f', 'size': m.BLOCK_SIZE + 28, 'sha256': 'a' * 64, 'r': 3, **extra})
        return bid

    def test_gc_marks_without_deleting_first_cycle(self):
        bid = self.block()
        with patch.object(m, 'stub', return_value=self.stub), patch.object(m, 'mint', return_value='token'):
            m.gc(self.ns)
            self.assertEqual(self.deleted, [])
            self.assertIn('orphan_at', self.store.get('/bloques/' + bid)['value'])

    def test_gc_preserves_reader_and_prepared_session(self):
        bid = self.block()
        self.store.put('/lecturas/r', {'inode': 'i', 'snapshot': {'version': 1, 'blocks': [bid]}})
        with patch.object(m, 'stub', return_value=self.stub), patch.object(m, 'mint', return_value='token'):
            m.gc(self.ns)
            self.assertEqual(self.deleted, [])
            self.assertNotIn('orphan_at', self.store.get('/bloques/' + bid)['value'])
        self.store.delete('/lecturas/r')
        self.store.put('/sesiones/f', {'inode': 'i', 'snapshot': {'version': 0, 'blocks': []}, 'plans': {'0': bid}})
        m.gc(self.ns)
        self.assertNotIn('orphan_at', self.store.get('/bloques/' + bid)['value'])

    def test_gc_deletes_after_grace_not_during_token_lifetime(self):
        bid = self.block(orphan_at=time.time() - 10000, authorized_until=time.time() + 10)
        with patch.object(m, 'stub', return_value=self.stub), patch.object(m, 'mint', return_value='token'):
            m.gc(self.ns)
            self.assertEqual(self.deleted, [])
            value = self.store.get('/bloques/' + bid)['value']
            self.store.put('/bloques/' + bid, {**value, 'authorized_until': 0})
            m.gc(self.ns)
            self.assertEqual(self.deleted, [bid])

    def test_commit_129_blocks_uses_bounded_transaction(self):
        ids = [f'{i:032x}' for i in range(129)]
        for i, bid in enumerate(ids):
            self.block(bid, replicas=['dn1', 'dn2'])
            self.store.put(f'/locks/inode/{i}', {'fd': 'f'})
        self.store.put('/sesiones/f', {'uid': 'u', 'inode': 'inode', 'path': '/large',
            'mode': 'w', 'snapshot': {'version': 0, 'blocks': []}, 'nuevo': True,
            'lease': 1, 'dek': 'wrapped', 'held': {str(i): True for i in range(129)},
            'plans': {str(i): bid for i, bid in enumerate(ids)}})
        body = m.Close(blocks={i: m.Done(block_id=bid,
            fencing=self.store.get(f'/locks/inode/{i}')['create']) for i, bid in enumerate(ids)},
            size=129 * m.BLOCK_SIZE)
        result = m.close('f', body, {'sub': 'u'})
        self.assertEqual(result['version'], 1)
        self.assertLess(self.store.max_ops, 16)

    def test_repair_checks_authoritative_hash_and_receipt(self):
        bid = self.block(replicas=['dn1'], sha256='a' * 64, fd='f', size=60)
        self.store.put('/inodos/i', {'blocks': [bid]})
        ns = {**self.ns, 'dn2': {'estado': 'vivo', 'addr': 'dn2', 'libre': 1000, 'bloques': 0}}
        ns['dn1'] = {**ns['dn1'], 'libre': 1000, 'bloques': 1}
        def replicate(req, **kw):
            self.assertEqual(req.sha256, 'a' * 64)
            return NS(receipts=['receipt'])
        with patch.object(m, 'stub', return_value=NS(ReplicateBlock=replicate)), \
             patch.object(m, 'mint', return_value='token'), \
             patch.object(m, 'verify_node', return_value={'node': 'dn2', 'op': 'stored', 'b': bid, 'sha256': 'WRONG', 'size': 60, 'operation': 'f'}):
            m.repair(ns)
        self.assertEqual(self.store.get('/bloques/' + bid)['value']['replicas'], ['dn1'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
