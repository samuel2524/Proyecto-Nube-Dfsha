"""Librería cliente: parte, cifra, sube y reconstruye archivos. No conoce IPs de nodos."""
import hashlib
import os
import random
import threading
import time
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import grpc
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import dfsha_pb2 as pb, dfsha_pb2_grpc as rpc
from .common import GRPC_OPTS, grpc_creds, manifest_hash

import base64

CHUNK = 1 << 20
PARALELO = int(os.environ.get('DFSHA_PARALELO', 4))


class Error(Exception):
    def __init__(self, status, code, msg=''):
        super().__init__(f'{status} {code}: {msg}')
        self.status, self.code = status, code


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def cifrar(dek, bid, plano):
    n = os.urandom(12)
    return n + AESGCM(dek).encrypt(n, plano, bid.encode())   # AES-256-GCM, el block_id va como AAD


def descifrar(dek, bid, ct):
    return AESGCM(dek).decrypt(ct[:12], ct[12:], bid.encode())


class DFS:
    def __init__(self, token=None):
        # Nombres lógicos (DNS privado); ninguna IP queda escrita en el cliente (RNF7).
        self.metas = os.environ.get('DFSHA_META', 'https://meta.dfsha.internal:8443').split(',')
        self.s = requests.Session()
        self.s.trust_env = False
        self.s.verify = os.environ.get('CA_CERT', 'certs/ca.crt')
        self.token = token
        self._stubs = {}

    # ---- plano de control ----
    def req(self, method, path, **kw):
        """409 RETRY = el catálogo perdió la carrera por el epoch global; se reenvía el MISMO pedido
        (mismo request_id/cuerpo, que el servidor trata como idempotente) con espera aleatoria creciente."""
        for intento in range(8):
            try:
                return self._req_una_vez(method, path, **kw)
            except Error as e:
                if e.status != 409 or e.code != 'RETRY' or intento == 7:
                    raise
                time.sleep(random.uniform(0, 0.05 * 2 ** intento))   # hasta ~6 s en el último intento

    def _req_una_vez(self, method, path, **kw):
        h = {'Authorization': f'Bearer {self.token}'} if self.token else {}
        err = None
        for i, m in enumerate(tuple(self.metas)):
            try:
                r = self.s.request(method, m + path, headers=h, timeout=60, **kw)
            except (requests.ConnectionError, requests.Timeout) as e:
                err = e
                continue
            if i:
                self.metas.insert(0, self.metas.pop(i))
            if r.status_code >= 400:
                try:
                    d = r.json().get('detail', {})
                except ValueError:
                    d = {'code': 'HTTP_ERROR', 'msg': r.text[:200]}
                if not isinstance(d, (dict, list)):
                    d = {'code': 'HTTP_ERROR', 'msg': str(d)}
                if isinstance(d, list):               # validación de FastAPI
                    d = {'code': 'BAD_REQUEST', 'msg': str(d)}
                if r.status_code in (502, 503, 504) and i + 1 < len(self.metas):
                    err = d
                    continue
                raise Error(r.status_code, d.get('code', '?'), d.get('msg', ''))
            return r.json() if r.content else None
        raise Error(503, 'META_UNAVAILABLE', f'ninguna instancia de metadatos responde: {err}')

    def login(self, user, password):
        self.token = self.req('POST', '/v1/auth/login', json={'user': user, 'password': password})['token']
        return self.token

    def ls(self, p):
        return self.req('GET', '/v1/fs/ls', params={'path': p})['entries']

    def mkdir(self, p):
        self.req('POST', '/v1/fs/mkdir', json={'path': p})

    def rmdir(self, p):
        self.req('DELETE', '/v1/fs/rmdir', params={'path': p})

    def rm(self, p):
        self.req('DELETE', '/v1/fs/rm', params={'path': p})

    def mv(self, s, d):
        self.req('POST', '/v1/fs/rename', json={'src': s, 'dst': d})

    def stat(self, p):
        return self.req('GET', '/v1/files/stat', params={'path': p})

    def nodes(self):
        return self.req('GET', '/v1/admin/nodes')

    def open(self, p, mode='r', create=False, replicas=3):
        info = self.req('POST', '/v1/files/open',
                         json={'path': p, 'mode': mode, 'create': create, 'replicas': replicas,
                               'request_id': uuid.uuid4().hex})
        return File(self, p, mode, info)

    # ---- plano de datos ----
    def stub(self, addr):
        if addr not in self._stubs:
            self._stubs[addr] = rpc.DataNodeStub(grpc.secure_channel(addr, grpc_creds(), GRPC_OPTS))
        return self._stubs[addr]

    def upload(self, fd, i, plano, dek):
        """Sube un bloque por la cadena de réplicas; reintenta con otra cadena si no llega a W."""
        excluir = []
        for _ in range(3):
            nb = self.req('POST', f'/v1/files/{fd}/blocks', json={
                'index': i, 'excluir': excluir, 'request_id': uuid.uuid4().hex})
            ct = cifrar(dek, nb['block_id'], plano)
            sha = _sha(ct)
            auth = self.req('POST', f'/v1/files/{fd}/blocks/{nb["block_id"]}/authorize',
                            json={'sha256': sha, 'size': len(ct)})

            def gen():
                yield pb.WriteChunk(block_id=nb['block_id'], token=auth['token'], pipeline=nb['pipeline'],
                                    sha256=sha, size=len(ct), operation_id=fd, data=ct[:CHUNK])
                for o in range(CHUNK, len(ct), CHUNK):
                    yield pb.WriteChunk(data=ct[o:o + CHUNK])
            try:
                ack = self.stub(nb['pipeline'][0].split('@')[1]).WriteBlock(gen(), timeout=120)
                stored = list(ack.stored)
            except grpc.RpcError:
                stored = []
            if len(stored) >= nb['w']:
                self.req('POST', f'/v1/files/{fd}/blocks/{nb["block_id"]}/prepared',
                         json={'receipts': list(ack.receipts)})
                return {'block_id': nb['block_id'], 'fencing': nb['fencing']}
            # la cadena se cortó en el primer nodo que no confirmó: solo ese se excluye
            caido = next((n.split('@')[0] for n in nb['pipeline'] if n.split('@')[0] not in stored), None)
            if caido is None:               # todos confirmaron y aun así no alcanza W: no hay a quién excluir
                break
            excluir.append(caido)
        raise Error(503, 'INSUFFICIENT_REPLICAS', f'el bloque {i} no alcanzó {nb["w"]} réplicas')

    def download(self, b, dek):
        """Pide el bloque a sus réplicas en orden; si una falla o está dañada, pasa a la siguiente."""
        for rep in b['replicas']:
            try:
                ct = b''.join(c.data for c in self.stub(rep['addr']).ReadBlock(
                    pb.BlockReq(block_id=b['block_id'], token=b['token']), timeout=30))
            except grpc.RpcError:
                continue
            if _sha(ct) == b['sha256']:
                try:
                    return descifrar(dek, b['block_id'], ct)
                except Exception:
                    continue
        raise Error(503, 'BLOCK_UNAVAILABLE', f'ninguna réplica del bloque {b["i"]} responde bien')

    # ---- RF2: archivos completos ----
    def put(self, local, remoto, replicas=3):
        t0 = time.time()
        f = self.open(remoto, 'w', create=True, replicas=replicas)
        if os.path.getsize(local) > f.bs * f.max_blocks:
            f.abort()
            raise Error(413, 'FILE_TOO_LARGE', 'archivo supera el límite configurado')
        h, n = hashlib.sha256(), 0
        try:
            with open(local, 'rb') as src, ThreadPoolExecutor(PARALELO) as pool:
                while True:
                    lote = [src.read(f.bs) for _ in range(PARALELO)]
                    lote = [c for c in lote if c]
                    if not lote:
                        break
                    for c in lote:
                        h.update(c)
                    futs = [pool.submit(self.upload, f.fd, n + k, c, f.dek) for k, c in enumerate(lote)]
                    for k, fu in enumerate(futs):
                        f.done[n + k] = fu.result()
                    n += len(lote)
                    f.size += sum(map(len, lote))
            f.close(sha256=h.hexdigest())
        except Exception:
            f.abort()
            raise
        return {'bytes': f.size, 'bloques': n, 'segundos': time.time() - t0, 'sha256': h.hexdigest()}

    def get(self, remoto, local):
        t0 = time.time()
        f = self.open(remoto, 'r')
        h = hashlib.sha256()
        temp = Path(str(local) + '.' + uuid.uuid4().hex + '.part')
        count = 0
        try:
            with open(temp, 'xb') as dst, ThreadPoolExecutor(PARALELO) as pool:
                for i in range(0, len(f.blocks), PARALELO):
                    for data in pool.map(f.bajar, range(i, min(i + PARALELO, len(f.blocks)))):
                        dst.write(data)
                        count += len(data)
                        h.update(data)
                dst.flush()
                os.fsync(dst.fileno())
            if count != f.size or (f.sha256 and h.hexdigest() != f.sha256):
                raise Error(500, 'INTEGRITY', 'tamaño o SHA-256 del archivo no coincide')
            os.replace(temp, local)
        finally:
            temp.unlink(missing_ok=True)
            f.close()
        return {'bytes': f.size, 'bloques': len(f.blocks), 'segundos': time.time() - t0,
                'sha256': h.hexdigest(), 'version': f.version}


class File:
    """RF3: open/read/write/lock/close con semántica close-to-open."""

    def __init__(self, dfs, path, mode, info):
        if manifest_hash(info['size'], info['blocks']) != info['manifest_sha256']:
            raise Error(500, 'INTEGRITY', 'hash del manifiesto no coincide')
        self.dfs, self.path, self.mode, self.fd = dfs, path, mode, info['fd']
        self.bs, self.dek, self.version = info['block_size'], base64.b64decode(info['dek']), info['version']
        self.max_blocks = info.get('max_blocks', 8192)
        self.sha256 = info['sha256']
        self.blocks = [] if mode == 'w' else info['blocks']
        self.size = 0 if mode == 'w' else info['size']
        self.pending, self.done, self.fencing, self.cache = {}, {}, {}, {}
        self._stop = threading.Event()
        self._closed_body = None
        self._lost = False
        if self.fd:
            threading.Thread(target=self._renovar, daemon=True).start()

    def _renovar(self):                     # la sesión dura 60 s; se renueva cada 10 s
        while not self._stop.wait(10):
            try:
                self.dfs.req('POST', f'/v1/files/{self.fd}/keepalive')
            except Error as exc:
                if exc.status in (401, 410):
                    self._lost = True
                    return

    def refresh(self):
        if self._lost or not self.fd:
            raise Error(410, 'SESSION_EXPIRED', 'la sesión lectora/escritora no está vigente')
        info = self.dfs.req('GET', f'/v1/files/{self.fd}/manifest')
        if info['version'] != self.version:
            raise Error(409, 'SNAPSHOT_CHANGED', 'el servidor cambió el snapshot')
        if manifest_hash(info['size'], info['blocks']) != info['manifest_sha256']:
            raise Error(500, 'INTEGRITY', 'hash del manifiesto no coincide')
        if self.mode != 'w':
            self.blocks = info['blocks']

    def _block(self, i):
        if i in self.pending:
            return self.pending[i]
        if i >= len(self.blocks):
            return b''
        if i not in self.cache:
            self.cache[i] = self.bajar(i)
        return self.cache[i]

    def bajar(self, i):
        """Descarga el bloque i de la versión abierta. El índice (manifiesto) solo se vuelve a pedir si la
        descarga falla, por permisos vencidos o réplicas movidas, y se reintenta una vez."""
        try:
            return self.dfs.download(self.blocks[i], self.dek)
        except Error:
            self.refresh()                  # misma versión: nuevos permisos y ubicaciones
            return self.dfs.download(self.blocks[i], self.dek)

    def read(self, offset, n):
        if offset < 0 or n < 0:
            raise Error(400, 'BAD_RANGE', 'offset y longitud deben ser no negativos')
        if self._lost:
            raise Error(410, 'SESSION_EXPIRED', 'sesión vencida; vuelva a abrir')
        out, pos, fin = [], offset, min(offset + n, self.size)
        while pos < fin:
            i, o = divmod(pos, self.bs)
            parte = self._block(i)[o:o + fin - pos]
            if not parte:
                raise Error(500, 'INTEGRITY', 'bloque no permite avanzar hasta el tamaño declarado')
            out.append(parte)
            pos += len(parte)
        return b''.join(out)

    def lock(self, desde, hasta, esperar=False):
        r = self.dfs.req('POST', f'/v1/files/{self.fd}/lock',
                         json={'desde': desde, 'hasta': hasta, 'esperar': esperar})
        self.fencing.update({int(k): v for k, v in r['fencing'].items()})
        return r['fencing']

    def unlock(self, desde, hasta):
        self.dfs.req('POST', f'/v1/files/{self.fd}/unlock', json={'desde': desde, 'hasta': hasta})
        for i in range(desde // self.bs, (hasta - 1) // self.bs + 1):
            self.fencing.pop(i, None)

    def write(self, offset, data, esperar=False):
        if offset < 0:
            raise Error(400, 'BAD_RANGE', 'offset negativo')
        if self.mode == 'r':
            raise Error(400, 'READ_ONLY', 'archivo abierto en modo r')
        if self.mode == 'a':
            offset = self.size
        if offset > self.size:
            raise Error(400, 'BEYOND_EOF', f'offset {offset} > tamaño {self.size}')
        if offset + len(data) > self.max_blocks * self.bs:
            raise Error(413, 'FILE_TOO_LARGE', 'archivo supera el límite configurado')
        if data:                            # toma el lock de los bloques que toca (423 si otro lo tiene)
            ini, fin = offset // self.bs, (offset + len(data) - 1) // self.bs
            if any(i not in self.fencing for i in range(ini, fin + 1)):
                self.lock(offset, offset + len(data), esperar)
        pos, k = offset, 0
        while k < len(data):
            i, o = divmod(pos, self.bs)
            trozo = data[k:k + self.bs - o]
            base = self._block(i)
            self.pending[i] = base[:o] + trozo + base[o + len(trozo):]   # copy-on-write del bloque
            pos += len(trozo)
            k += len(trozo)
        self.size = max(self.size, offset + len(data))
        return len(data)

    def close(self, sha256=None):
        if not self.fd:
            return None
        # Mantener renovación hasta recibir resultado, incluso con cadena lenta.
        if self._closed_body is None:
            with ThreadPoolExecutor(PARALELO) as pool:
                futs = {i: pool.submit(self.dfs.upload, self.fd, i, d, self.dek) for i, d in self.pending.items()}
                for i, fu in futs.items():
                    self.done[i] = fu.result()
            if self.mode == 'w' and sha256 is None:
                sha256 = _sha(b''.join(self.pending[i] for i in sorted(self.pending)))
            self._closed_body = {'blocks': self.done, 'size': self.size, 'sha256': sha256}
        r = self.dfs.req('POST', f'/v1/files/{self.fd}/close', json=self._closed_body)
        self._stop.set()
        self.fd = None
        return r['version']

    def abort(self):
        if self.fd:
            try:
                self.dfs.req('POST', f'/v1/files/{self.fd}/abort')
            except Error:
                pass
        self._stop.set()
        self.fd = None
