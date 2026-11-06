"""TLS, capacidades asimétricas y acceso transaccional al catálogo."""
import base64
import json
import hashlib
import os
import time
from pathlib import Path

import jwt
import requests

BLOCK_SIZE = int(os.environ.get('BLOCK_SIZE', 8 * 1024 * 1024))
MAX_BLOCKS = int(os.environ.get('MAX_BLOCKS', 8192))
CERTS = Path(os.environ.get('CERTS', '/certs'))
GRPC_OPTS = [('grpc.max_send_message_length', 2 << 20),
             ('grpc.max_receive_message_length', 2 << 20)]


def manifest_hash(size, blocks):
    canonical = {'size': size, 'blocks': [
        {'id': b['block_id'], 'sha256': b['sha256'], 'size': b['size']} for b in blocks]}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _b64(value):
    return base64.b64encode(value.encode() if isinstance(value, str) else value).decode()


def _end(prefix):
    value = bytearray(prefix.encode())
    value[-1] += 1
    return _b64(bytes(value))


def sign(claims, key, audience, ttl=300):
    now = int(time.time())
    return jwt.encode({**claims, 'iat': now, 'exp': now + ttl, 'aud': audience},
                      (CERTS / key).read_bytes(), algorithm='EdDSA')


def verify(token, key, audience):
    return jwt.decode(token, (CERTS / key).read_bytes(), algorithms=['EdDSA'],
                      audience=audience, options={'require': ['exp', 'iat', 'aud']})


def mint(**claims):
    return sign(claims, 'capability.key', 'dfsha-block')


def check(token, block_id=None, ops=('r',)):
    try:
        claims = verify(token, 'capability.pub', 'dfsha-block')
        if claims.get('op') not in ops or (claims['op'] != 'admin' and claims.get('b') != block_id):
            return None
        return claims
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def node_proof(claims):
    return sign(claims, 'receipt.key', 'dfsha-node', ttl=3600)


def verify_node(token, node):
    keys = json.loads((CERTS / 'receipts.json').read_text())
    return jwt.decode(token, keys[node], algorithms=['EdDSA'], audience='dfsha-node',
                      options={'require': ['exp', 'iat', 'aud']})


def grpc_creds():
    import grpc
    return grpc.ssl_channel_credentials(
        (CERTS / 'ca.crt').read_bytes(),
        (CERTS / 'node.key').read_bytes(), (CERTS / 'node.crt').read_bytes())


class Etcd:
    def __init__(self, endpoints=None):
        self.eps = (endpoints or os.environ['ETCD_ENDPOINTS']).split(',')
        self.s = requests.Session()
        self.s.trust_env = False
        self.s.cert = (str(CERTS / 'etcd.crt'), str(CERTS / 'etcd.key'))
        self.s.verify = str(CERTS / 'etcd-ca.crt')

    def _post(self, path, body):
        error = None
        for ep in tuple(self.eps):
            try:
                response = self.s.post(ep + path, json=body, timeout=5)
                response.raise_for_status()
                data = response.json()
                if 'error' in data:
                    raise requests.RequestException(str(data['error']))
                return data
            except requests.RequestException as exc:
                error = exc
        raise error

    @staticmethod
    def _kv(kv):
        return {'key': base64.b64decode(kv['key']).decode(),
                'value': json.loads(base64.b64decode(kv.get('value', '')) or 'null'),
                'mod': int(kv.get('mod_revision', 0)), 'create': int(kv.get('create_revision', 0))}

    def get(self, key):
        values = self._post('/v3/kv/range', {'key': _b64(key)}).get('kvs', [])
        return self._kv(values[0]) if values else None

    def get_many(self, keys):
        result = []
        for i in range(0, len(keys), 64):
            ops = [{'request_range': {'key': _b64(k)}} for k in keys[i:i + 64]]
            if not ops:
                continue
            data = self._post('/v3/kv/txn', {'success': ops})
            for response in data.get('responses', []):
                values = response.get('response_range', {}).get('kvs', [])
                result.append(self._kv(values[0]) if values else None)
        return result

    def prefix(self, prefix):
        data = self._post('/v3/kv/range', {'key': _b64(prefix), 'range_end': _end(prefix)})
        return [self._kv(kv) for kv in data.get('kvs', [])]

    def put(self, key, value, lease=None):
        data = self._post('/v3/kv/put', self.op_put(key, value, lease)['request_put'])
        return int(data['header']['revision'])

    def delete(self, key):
        self._post('/v3/kv/deleterange', {'key': _b64(key)})

    @staticmethod
    def cmp(key, target, value):
        return {'key': _b64(key), 'result': 'EQUAL', 'target': target,
                f'{target.lower()}_revision': str(value)}

    @staticmethod
    def op_put(key, value, lease=None):
        data = {'key': _b64(key), 'value': _b64(json.dumps(value))}
        if lease:
            data['lease'] = str(lease)
        return {'request_put': data}

    @staticmethod
    def op_del(key):
        return {'request_delete_range': {'key': _b64(key)}}

    def txn(self, compare, success, failure=()):
        data = self._post('/v3/kv/txn', {'compare': compare, 'success': success, 'failure': list(failure)})
        return bool(data.get('succeeded')), int(data['header']['revision'])

    def grant(self, ttl):
        return int(self._post('/v3/lease/grant', {'TTL': str(ttl)})['ID'])

    def keepalive(self, lease):
        data = self._post('/v3/lease/keepalive', {'ID': str(lease)})
        return int(data.get('result', {}).get('TTL', 0)) > 0

    def revoke(self, lease):
        self._post('/v3/lease/revoke', {'ID': str(lease)})
