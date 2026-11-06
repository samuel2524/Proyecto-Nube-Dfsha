"""Plano de control: planes verificados, snapshots con lease y publicación CAS acotada.

Todos los cambios de referencias/namespace comparan EPOCH. El GC toma primero ese
epoch y no borra si hubo un cambio concurrente. Los locks de una sesión comparten
su lease; adquirir/liberar uno actualiza la sesión en la misma transacción. Así el
commit compara una revisión de sesión (no miles de locks en una única txn).
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import posixpath
import threading
import time
import uuid

import grpc
import jwt
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import dfsha_pb2 as pb, dfsha_pb2_grpc as rpc
from .common import BLOCK_SIZE, MAX_BLOCKS, CERTS, GRPC_OPTS, Etcd, grpc_creds, mint, sign, verify, verify_node, manifest_hash

ME = os.environ.get('NODE_ID', 'meta1')
GRACE = float(os.environ.get('GC_GRACE', 600))
LEASE_TTL = int(os.environ.get('SESSION_TTL', 60))
NODE_ADDRS = json.loads(os.environ.get('DATA_NODES', '{}'))
VIVO, CAIDO = 10, 30
KEK = AESGCM(bytes.fromhex(os.environ['KEK']))
EPOCH = '/system/epoch'
etcd = Etcd()
app = FastAPI(title='DFSha — contrato corregido v2')
cmp, put, delete = Etcd.cmp, Etcd.op_put, Etcd.op_del
log = logging.getLogger(ME)


def err(status, code, msg, **extra):
    raise HTTPException(status, {'code': code, 'msg': msg, **extra})


def epoch():
    value = etcd.get(EPOCH)
    return value['mod'] if value else 0


def tx(revision, guards, ops):
    return etcd.txn([cmp(EPOCH, 'MOD', revision), *guards],
                    [*ops, put(EPOCH, uuid.uuid4().hex)])[0]


@app.middleware('http')
async def audit(request: Request, call_next):
    try:
        response = await call_next(request)
    except requests.RequestException:
        response = JSONResponse(status_code=503, content={'detail': {
            'code': 'CATALOG_UNAVAILABLE', 'msg': 'catálogo no disponible; consulte el estado de la operación'}})
    log.info('AUDIT %s %s %s -> %s', request.client.host, request.method,
             request.url.path, response.status_code)
    return response


@app.get('/health')
def health():
    etcd.get(EPOCH)
    return {'node': ME, 'status': 'ready'}


def _hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=3,
                          maxmem=128 * 1024 * 1024).hex()


def bootstrap_users():
    for spec in filter(None, os.environ.get('USERS', '').split(',')):
        uid, password, role = spec.split(':')
        if not uid.isalnum() or role not in ('user', 'admin'):
            raise ValueError('USERS inválido')
        salt = os.urandom(16)
        etcd.txn([cmp(f'/usuarios/{uid}', 'CREATE', 0)],
                 [put(f'/usuarios/{uid}', {'salt': salt.hex(), 'hash': _hash(password, salt), 'rol': role})])


def user(authorization: str = Header(None)):
    try:
        value = verify(authorization.removeprefix('Bearer '), 'auth.pub', 'dfsha-user')
        if not value['sub'].isalnum():
            raise ValueError()
        return value
    except (jwt.PyJWTError, AttributeError, KeyError, ValueError):
        err(401, 'UNAUTHENTICATED', 'token ausente, inválido o vencido')


class Login(BaseModel):
    user: str
    password: str


@app.post('/v1/auth/login')
def login(body: Login):
    found = etcd.get(f'/usuarios/{body.user}') if body.user.isalnum() else None
    if not found or not hmac.compare_digest(found['value']['hash'],
            _hash(body.password, bytes.fromhex(found['value']['salt']))):
        err(401, 'UNAUTHENTICATED', 'usuario o contraseña incorrectos')
    return {'token': sign({'sub': body.user, 'rol': found['value']['rol']},
                          'auth.key', 'dfsha-user', 900), 'expira_en': 900}


def norm(path):
    if not path or not path.startswith('/') or '\x00' in path:
        err(400, 'BAD_PATH', 'se requiere ruta absoluta válida')
    return posixpath.normpath(path).replace('//', '/')


def key(u, path):
    return f'/ns/{u["sub"]}{path}'


def entry(u, path):
    return {'value': {'type': 'dir'}, 'mod': 0} if path == '/' else etcd.get(key(u, path))


def need_dir(u, path):
    found = entry(u, path)
    if not found:
        err(404, 'NOT_FOUND', 'directorio inexistente')
    if found['value']['type'] != 'dir':
        err(409, 'NOT_A_DIR', 'no es un directorio')


def active(inode):
    return [s for s in etcd.prefix('/sesiones/') if s['value']['inode'] == inode]


@app.get('/v1/fs/ls')
def ls(path: str = '/', u=Depends(user)):
    path = norm(path)
    need_dir(u, path)
    pre = key(u, path.rstrip('/')) + '/'
    result = []
    for row in etcd.prefix(pre):
        name = row['key'][len(pre):]
        if '/' in name:
            continue
        value = row['value']
        inode = etcd.get(f'/inodos/{value["inode"]}') if value['type'] == 'file' else None
        if value['type'] == 'file' and not inode:
            continue  # eliminación concurrente: nunca dereferenciar None
        result.append({'name': name, 'type': value['type'], 'mtime': value['mtime'],
                       'size': inode['value']['size'] if inode else 0,
                       'version': inode['value']['version'] if inode else None})
    return {'path': path, 'entries': result}


class PathB(BaseModel):
    path: str


@app.post('/v1/fs/mkdir', status_code=201)
def mkdir(body: PathB, u=Depends(user)):
    path = norm(body.path)
    if path == '/':
        err(409, 'EXISTS', 'la raíz ya existe')
    for _ in range(12):
        revision = epoch()
        need_dir(u, posixpath.dirname(path))
        if entry(u, path):
            err(409, 'EXISTS', 'la entrada ya existe')
        if tx(revision, [cmp(key(u, path), 'MOD', 0)],
              [put(key(u, path), {'type': 'dir', 'mtime': time.time()})]):
            return {'path': path}
    err(409, 'RETRY', 'namespace ocupado')


@app.delete('/v1/fs/rmdir', status_code=204)
def rmdir(path: str, u=Depends(user)):
    path = norm(path)
    if path == '/':
        err(409, 'DIR_NOT_EMPTY', 'no se borra la raíz')
    for _ in range(12):
        revision = epoch()
        need_dir(u, path)
        if etcd.prefix(key(u, path) + '/'):
            err(409, 'DIR_NOT_EMPTY', 'directorio no vacío')
        if tx(revision, [], [delete(key(u, path))]):
            return
    err(409, 'RETRY', 'namespace ocupado')


@app.delete('/v1/fs/rm', status_code=204)
def rm(path: str, u=Depends(user)):
    path = norm(path)
    for _ in range(12):
        revision = epoch()
        found = entry(u, path)
        if not found or found['value']['type'] != 'file':
            err(404, 'NOT_FOUND', 'archivo inexistente')
        inode = found['value']['inode']
        if active(inode):
            err(423, 'FILE_BUSY', 'cierre las sesiones escritoras antes de borrar')
        # La DEK/versiones se conservan mientras haya lectores. El GC las retira.
        if tx(revision, [cmp(key(u, path), 'MOD', found['mod'])],
              [delete(key(u, path)), delete(f'/inodos/{inode}')]):
            return
    err(409, 'RETRY', 'namespace ocupado')


class Rename(BaseModel):
    src: str
    dst: str


@app.post('/v1/fs/rename', status_code=204)
def rename(body: Rename, u=Depends(user)):
    source, destination = norm(body.src), norm(body.dst)
    if source == '/' or destination.startswith(source + '/'):
        err(400, 'BAD_PATH', 'movimiento inválido')
    for _ in range(12):
        revision = epoch()
        found = entry(u, source)
        if not found:
            err(404, 'NOT_FOUND', 'origen inexistente')
        if entry(u, destination):
            err(409, 'EXISTS', 'destino existente')
        need_dir(u, posixpath.dirname(destination))
        rows = [{**found, 'key': key(u, source)}]
        if found['value']['type'] == 'dir':
            rows += etcd.prefix(key(u, source) + '/')
        if len(rows) > 48:
            err(413, 'RENAME_LIMIT', 'máximo 48 entradas por rename atómico')
        inodes = {r['value']['inode'] for r in rows if r['value']['type'] == 'file'}
        if any(s['value']['inode'] in inodes or (s['value']['uid'] == u['sub'] and
               (s['value']['path'] == source or s['value']['path'].startswith(source + '/')))
               for s in etcd.prefix('/sesiones/')):
            err(423, 'FILE_BUSY', 'hay escritores activos bajo el origen')
        ops = []
        for row in rows:
            dst = key(u, destination) + row['key'][len(key(u, source)):]
            ops += [put(dst, row['value']), delete(row['key'])]
        if tx(revision, [], ops):
            return
    err(409, 'RETRY', 'namespace ocupado')


def nodos():
    result = {}
    for row in etcd.prefix('/nodos/'):
        value = row['value']
        delay = time.time() - value['ts']
        identifier = row['key'].rsplit('/', 1)[1]
        result[identifier] = {**value, 'id': identifier, 'hace_s': round(delay, 1),
            'estado': 'vivo' if delay < VIVO else 'sospechoso' if delay < CAIDO else 'caido'}
    return result


class Heartbeat(BaseModel):
    proof: str


@app.post('/v1/internal/heartbeat')
def heartbeat(body: Heartbeat):
    try:
        untrusted = jwt.decode(body.proof, options={'verify_signature': False})
        node = untrusted['node']
        value = verify_node(body.proof, node)
        if (value['op'] != 'heartbeat' or NODE_ADDRS.get(node) != value['addr'] or
                time.time() - value['iat'] > 15):
            raise ValueError()
    except (jwt.PyJWTError, KeyError, ValueError):
        err(401, 'BAD_NODE', 'identidad de nodo inválida')
    etcd.put(f'/nodos/{node}', {k: value[k] for k in ('addr', 'libre', 'total', 'bloques')} |
             {'ts': time.time()})
    return {'ok': True}


def wrap(dek):
    nonce = os.urandom(12)
    return base64.b64encode(nonce + KEK.encrypt(nonce, dek, None)).decode()


def unwrap(value):
    raw = base64.b64decode(value)
    return KEK.decrypt(raw[:12], raw[12:], None)


def block_rows(ids):
    rows = etcd.get_many([f'/bloques/{bid}' for bid in ids])
    if any(not row or row['value']['state'] == 'deleting' for row in rows):
        err(503, 'BLOCK_UNAVAILABLE', 'manifiesto sin bloques disponibles')
    return rows


def blocks_view(inode, uid):
    ns = nodos()
    output = []
    for i, (bid, row) in enumerate(zip(inode['blocks'], block_rows(inode['blocks']))):
        block = row['value']
        alive = [{'id': n, 'addr': ns[n]['addr']} for n in block['replicas']
                 if ns.get(n, {}).get('estado') == 'vivo']
        if alive:
            k = i % len(alive)
            alive = alive[k:] + alive[:k]
        output.append({'i': i, 'block_id': bid, 'sha256': block['sha256'], 'size': block['size'],
                       'replicas': alive, 'todas': block['replicas'],
                       'token': mint(b=bid, op='r', u=uid)})
    return output


def session(fd, u, read=False):
    row = etcd.get(f'/lecturas/{fd}' if read else f'/sesiones/{fd}')
    if not row or row['value']['uid'] != u['sub']:
        err(410, 'SESSION_EXPIRED', 'sesión inexistente o vencida')
    return row


class Open(BaseModel):
    path: str
    mode: str = 'r'
    create: bool = False
    replicas: int = 3
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


def open_reply(value, fd):
    inode = value['snapshot']
    blocks = blocks_view(inode, value['uid'])
    return {'fd': fd, 'version': inode['version'], 'size': inode['size'], 'sha256': inode.get('sha256'),
            'block_size': BLOCK_SIZE, 'max_blocks': MAX_BLOCKS,
            'dek': base64.b64encode(unwrap(value['dek'])).decode(),
            'blocks': blocks, 'manifest_sha256': inode.get('manifest_sha256') or manifest_hash(inode['size'], blocks),
            'ttl': LEASE_TTL}


@app.post('/v1/files/open')
def open_(body: Open, u=Depends(user)):
    if body.mode not in ('r', 'rw', 'w', 'a') or body.replicas not in (2, 3):
        err(400, 'BAD_MODE', 'modo inválido; solo R=2 experimental o R=3')
    path = norm(body.path)
    fd = uuid.uuid5(uuid.NAMESPACE_URL, u['sub'] + ':' + body.request_id).hex
    session_key = f'/lecturas/{fd}' if body.mode == 'r' else f'/sesiones/{fd}'
    for _ in range(20):
        revision = epoch()
        existing = etcd.get(session_key)
        if existing:
            value = existing['value']
            if value['path'] != path or value['mode'] != body.mode:
                err(409, 'REQUEST_REUSED', 'request_id ya utilizado')
            return open_reply(value, fd)
        found = entry(u, path)
        if found and found['value']['type'] != 'file':
            err(409, 'IS_DIR', 'la ruta es un directorio')
        if not found and (body.mode == 'r' or not body.create):
            err(404, 'NOT_FOUND', 'archivo inexistente')
        need_dir(u, posixpath.dirname(path))
        inode_id = found['value']['inode'] if found else uuid.uuid4().hex
        current = etcd.get(f'/inodos/{inode_id}') if found else None
        if found and not current:
            continue
        snapshot = current['value'] if current else {'version': 0, 'size': 0, 'sha256': None, 'blocks': []}
        if body.mode != 'r':
            writers = active(inode_id)
            if any(s['value']['mode'] in ('w', 'a') for s in writers) or (body.mode in ('w', 'a') and writers):
                err(423, 'FILE_BUSY', 'truncado/anexado requiere exclusión de escritores')
        encrypted = etcd.get(f'/dek/{inode_id}')['value'] if found else wrap(os.urandom(32))
        lease = etcd.grant(LEASE_TTL)
        value = {'uid': u['sub'], 'inode': inode_id, 'path': path, 'mode': body.mode,
                 'snapshot': snapshot, 'entry_mod': found['mod'] if found else 0,
                 'nuevo': not found, 'dek': encrypted, 'r': body.replicas,
                 'lease': lease, 'held': {}, 'plans': {}}
        if tx(revision, [cmp(session_key, 'CREATE', 0)], [put(session_key, value, lease)]):
            return open_reply(value, fd)
        etcd.revoke(lease)
    err(409, 'RETRY', 'no se pudo abrir por concurrencia')


@app.post('/v1/files/{fd}/keepalive')
def keepalive(fd: str, u=Depends(user)):
    row = etcd.get(f'/lecturas/{fd}')
    read = bool(row and row['value']['uid'] == u['sub'])
    value = session(fd, u, read)['value']
    if not etcd.keepalive(value['lease']):
        err(410, 'SESSION_EXPIRED', 'lease vencido')
    return {'ttl': LEASE_TTL}


@app.get('/v1/files/{fd}/manifest')
def manifest(fd: str, u=Depends(user)):
    row = etcd.get(f'/lecturas/{fd}')
    read = bool(row and row['value']['uid'] == u['sub'])
    return open_reply(session(fd, u, read)['value'], fd)


def acquire(fd, u, indices):
    if len(indices) > 48:
        err(413, 'LOCK_RANGE_LIMIT', 'máximo 48 bloques por lock; use rangos menores')
    for _ in range(20):
        revision = epoch()
        row = session(fd, u)
        value = row['value']
        current = etcd.get(f'/inodos/{value["inode"]}')
        cur_blocks = current['value']['blocks'] if current else []
        held = dict(value['held'])
        ops, guards = [], [cmp(f'/sesiones/{fd}', 'MOD', row['mod'])]
        for index in indices:
            if index < 0 or index >= MAX_BLOCKS:
                err(400, 'BAD_RANGE', 'índice fuera de límites')
            lock_key = f'/locks/{value["inode"]}/{index}'
            found = etcd.get(lock_key)
            if found and found['value']['fd'] != fd:
                err(423, 'BLOCK_LOCKED', 'otro escritor posee el bloque', retry_after=1)
            if value['mode'] == 'rw' and str(index) not in held:
                base = value['snapshot']['blocks']
                expected = base[index] if index < len(base) else None
                actual = cur_blocks[index] if index < len(cur_blocks) else None
                if expected != actual:
                    err(409, 'VERSION_CONFLICT', 'el bloque cambió desde open; vuelva a abrir')
            if not found:
                guards.append(cmp(lock_key, 'CREATE', 0))
                ops.append(put(lock_key, {'fd': fd}, value['lease']))
            held[str(index)] = True
        if tx(revision, guards, [*ops, put(f'/sesiones/{fd}', {**value, 'held': held}, value['lease'])]):
            return {i: etcd.get(f'/locks/{value["inode"]}/{i}')['create'] for i in indices}
    err(409, 'RETRY', 'lock en conflicto')


class LockB(BaseModel):
    desde: int = Field(ge=0)
    hasta: int = Field(gt=0)
    esperar: bool = False


@app.post('/v1/files/{fd}/lock')
def lock(fd: str, body: LockB, u=Depends(user)):
    if body.hasta <= body.desde or body.hasta > MAX_BLOCKS * BLOCK_SIZE:
        err(400, 'BAD_RANGE', 'rango inválido')
    indices = list(range(body.desde // BLOCK_SIZE, (body.hasta - 1) // BLOCK_SIZE + 1))
    deadline = time.monotonic() + (30 if body.esperar else 0)
    while True:
        try:
            return {'fencing': acquire(fd, u, indices)}
        except HTTPException as exc:
            if exc.status_code != 423 or time.monotonic() >= deadline:
                raise
            time.sleep(.25)


@app.post('/v1/files/{fd}/unlock', status_code=204)
def unlock(fd: str, body: LockB, u=Depends(user)):
    if body.hasta <= body.desde:
        err(400, 'BAD_RANGE', 'rango inválido')
    for _ in range(20):
        revision = epoch()
        row = session(fd, u)
        value = row['value']
        indices = list(range(body.desde // BLOCK_SIZE, (body.hasta - 1) // BLOCK_SIZE + 1))
        if any(str(i) in value['plans'] for i in indices):
            err(409, 'BLOCK_PENDING', 'no se libera un bloque con carga preparada; cierre o aborte')
        held = dict(value['held'])
        ops = []
        for index in indices:
            if held.pop(str(index), None):
                ops.append(delete(f'/locks/{value["inode"]}/{index}'))
        if len(ops) > 48:
            err(413, 'LOCK_RANGE_LIMIT', 'rango demasiado grande')
        if tx(revision, [cmp(f'/sesiones/{fd}', 'MOD', row['mod'])],
              [*ops, put(f'/sesiones/{fd}', {**value, 'held': held}, value['lease'])]):
            return
    err(409, 'RETRY', 'unlock en conflicto')


class BlockB(BaseModel):
    index: int = Field(ge=0)
    excluir: list[str] = Field(default_factory=list)
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


@app.post('/v1/files/{fd}/blocks')
def new_block(fd: str, body: BlockB, u=Depends(user)):
    fencing = acquire(fd, u, [body.index])[body.index]
    bid = uuid.uuid5(uuid.NAMESPACE_URL, fd + ':' + body.request_id).hex
    for _ in range(20):
        revision = epoch()
        row = session(fd, u)
        value = row['value']
        existing = etcd.get(f'/bloques/{bid}')
        if existing:
            plan = existing['value']
            if plan['fd'] != fd or plan['index'] != body.index:
                err(409, 'REQUEST_REUSED', 'request_id usado para otro bloque')
            return {'block_id': bid, 'fencing': fencing, 'w': 2, 'pipeline': plan['pipeline']}
        alive = sorted((n for n in nodos().values() if n['estado'] == 'vivo'
                        and n['id'] not in body.excluir and n['libre'] > BLOCK_SIZE + 28),
                       key=lambda n: (n['bloques'], -n['libre'], n['id']))
        if len(alive) < 2:
            err(503, 'INSUFFICIENT_REPLICAS', 'se requieren dos nodos con capacidad')
        start = (body.index + int(value['inode'][:8], 16)) % len(alive)
        chosen = (alive[start:] + alive[:start])[:value['r']]
        pipeline = [f'{n["id"]}@{n["addr"]}' for n in chosen]
        plan = {'fd': fd, 'uid': u['sub'], 'inode': value['inode'], 'index': body.index,
                'pipeline': pipeline, 'r': value['r'], 'state': 'allocated', 'replicas': [],
                'created': time.time()}
        plans = {**value['plans'], str(body.index): bid}
        if tx(revision, [cmp(f'/sesiones/{fd}', 'MOD', row['mod']), cmp(f'/bloques/{bid}', 'CREATE', 0)],
              [put(f'/bloques/{bid}', plan), put(f'/sesiones/{fd}', {**value, 'plans': plans}, value['lease'])]):
            return {'block_id': bid, 'fencing': fencing, 'w': 2, 'pipeline': pipeline}
    err(409, 'RETRY', 'asignación en conflicto')


class Authorize(BaseModel):
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    size: int = Field(ge=28, le=BLOCK_SIZE + 28)


def own_plan(fd, bid, u):
    session(fd, u)
    row = etcd.get(f'/bloques/{bid}')
    if not row or row['value'].get('fd') != fd or row['value'].get('uid') != u['sub']:
        err(404, 'NOT_FOUND', 'plan inexistente')
    return row


@app.post('/v1/files/{fd}/blocks/{bid}/authorize')
def authorize(fd: str, bid: str, body: Authorize, u=Depends(user)):
    for _ in range(20):
        row = own_plan(fd, bid, u)
        plan = row['value']
        if plan['state'] not in ('allocated', 'authorized', 'prepared'):
            err(409, 'BAD_STATE', 'bloque ya cerrado')
        if 'sha256' in plan and (plan['sha256'] != body.sha256 or plan['size'] != body.size):
            err(409, 'IMMUTABLE_PLAN', 'hash/tamaño ya fijados')
        plan = {**plan, 'sha256': body.sha256, 'size': body.size,
                'authorized_until': time.time() + 300,
                'state': 'prepared' if plan['state'] == 'prepared' else 'authorized'}
        if etcd.txn([cmp(f'/bloques/{bid}', 'MOD', row['mod'])], [put(f'/bloques/{bid}', plan)])[0]:
            return {'token': mint(b=bid, op='w', u=u['sub'], sha256=body.sha256, size=body.size,
                                  operation=fd, nodes=[p.split('@')[0] for p in plan['pipeline']],
                                  targets=plan['pipeline'])}
    err(409, 'RETRY', 'autorización en conflicto')


class Receipts(BaseModel):
    receipts: list[str] = Field(min_length=2, max_length=3)


def validated_receipts(bid, plan, receipts):
    nodes = set()
    allowed = {p.split('@')[0] for p in plan['pipeline']}
    for token in receipts:
        try:
            hint = jwt.decode(token, options={'verify_signature': False})
            proof = verify_node(token, hint['node'])
            node = proof['node']
            if (node in nodes or node not in allowed or proof['op'] != 'stored' or
                    proof['b'] != bid or proof['sha256'] != plan['sha256'] or
                    proof['size'] != plan['size'] or proof['operation'] != plan['fd']):
                raise ValueError()
            nodes.add(node)
        except (jwt.PyJWTError, KeyError, ValueError):
            err(409, 'BAD_RECEIPT', 'confirmación falsa, duplicada o fuera del plan')
    if len(nodes) < 2:
        err(503, 'INSUFFICIENT_REPLICAS', 'faltan dos confirmaciones persistentes distintas')
    return sorted(nodes)


@app.post('/v1/files/{fd}/blocks/{bid}/prepared')
def prepared(fd: str, bid: str, body: Receipts, u=Depends(user)):
    for _ in range(20):
        revision = epoch()
        row = own_plan(fd, bid, u)
        plan = row['value']
        if plan['state'] not in ('authorized', 'prepared'):
            err(409, 'BAD_STATE', 'bloque no autorizado')
        nodes = validated_receipts(bid, plan, body.receipts)
        if tx(revision, [cmp(f'/bloques/{bid}', 'MOD', row['mod'])],
              [put(f'/bloques/{bid}', {**plan, 'state': 'prepared', 'replicas': nodes})]):
            return {'block_id': bid, 'replicas': nodes}
    err(409, 'RETRY', 'preparación en conflicto')


class Done(BaseModel):
    block_id: str
    fencing: int


class Close(BaseModel):
    blocks: dict[int, Done] = Field(default_factory=dict)
    size: int = Field(default=0, ge=0, le=MAX_BLOCKS * BLOCK_SIZE)
    sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')


@app.post('/v1/files/{fd}/close')
def close(fd: str, body: Close, u=Depends(user)):
    digest = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    result_key = f'/results/{fd}'
    for _ in range(30):
        revision = epoch()
        result = etcd.get(result_key)
        if result:
            if result['value']['uid'] != u['sub'] or result['value']['digest'] != digest:
                err(409, 'OPERATION_REUSED', 'operación cerrada con otro contenido')
            return result['value']['result']
        read = etcd.get(f'/lecturas/{fd}')
        if read and read['value']['uid'] == u['sub']:
            read_result = {'version': read['value']['snapshot']['version']}
            if tx(revision, [cmp(f'/lecturas/{fd}', 'MOD', read['mod'])],
                  [delete(f'/lecturas/{fd}'), put(result_key, {'uid': u['sub'], 'digest': digest, 'result': read_result})]):
                etcd.revoke(read['value']['lease'])
                return read_result
            continue
        row = session(fd, u)
        value = row['value']
        ino_key, ns_key = f'/inodos/{value["inode"]}', key(u, value['path'])
        need_dir(u, posixpath.dirname(value['path']))
        found = etcd.get(ns_key)
        current = etcd.get(ino_key)
        if value['nuevo']:
            if found:
                err(409, 'EXISTS', 'otra operación creó la ruta')
        elif not found or found['value'].get('inode') != value['inode'] or not current:
            err(409, 'NAMESPACE_CHANGED', 'archivo eliminado o renombrado')
        if {str(i): d.block_id for i, d in body.blocks.items()} != value['plans']:
            err(409, 'BAD_BLOCKS', 'el cierre debe usar exactamente los planes vigentes')
        blocks = [] if value['mode'] == 'w' else list(current['value']['blocks'] if current else [])
        for index, done in sorted(body.blocks.items()):
            plan = etcd.get(f'/bloques/{done.block_id}')
            lk = etcd.get(f'/locks/{value["inode"]}/{index}')
            if (not plan or plan['value']['state'] != 'prepared' or plan['value']['fd'] != fd or
                    len(set(plan['value']['replicas'])) < 2 or not lk or lk['value']['fd'] != fd or
                    lk['create'] != done.fencing or str(index) not in value['held']):
                err(409, 'UNPREPARED_BLOCK', 'bloque no preparado o lock perdido')
            if index < len(blocks):
                blocks[index] = done.block_id
            elif index == len(blocks):
                blocks.append(done.block_id)
            else:
                err(400, 'BAD_BLOCKS', 'no se permiten huecos')
        size = body.size if value['mode'] in ('w', 'a') else max(current['value']['size'] if current else 0, body.size)
        rows = block_rows(blocks)
        sizes = [r['value']['size'] - 28 for r in rows]
        if (sum(sizes) != size or any(n != BLOCK_SIZE for n in sizes[:-1]) or
                (sizes and sizes[-1] == 0) or (not sizes and size != 0)):
            err(400, 'BAD_MANIFEST', 'tamaño final y bloques incompatibles')
        if len(blocks) > MAX_BLOCKS:
            err(413, 'FILE_TOO_LARGE', 'archivo supera el límite configurado')
        changed = bool(body.blocks) or value['mode'] == 'w' or value['nuevo']
        version = (current['value']['version'] if current else 0) + int(changed)
        result = {'version': version}
        ops = [delete(f'/sesiones/{fd}'), put(result_key, {'uid': u['sub'], 'digest': digest, 'result': result})]
        if changed:
            inode = {'version': version, 'size': size, 'blocks': blocks,
                     'sha256': body.sha256 if value['mode'] == 'w' else None, 'mtime': time.time()}
            inode['manifest_sha256'] = manifest_hash(size, [
                {'block_id': bid, 'sha256': row['value']['sha256'], 'size': row['value']['size']}
                for bid, row in zip(blocks, rows)])
            ops += [put(ino_key, inode), put(f'/versions/{value["inode"]}/{version}', inode),
                    put(ns_key, {'type': 'file', 'inode': value['inode'], 'mtime': time.time()})]
            if value['nuevo']:
                ops.append(put(f'/dek/{value["inode"]}', value['dek']))
        # Acotado: no hay una operación ni comparación transaccional por bloque.
        # Session MOD asegura que unlock/adquisiciones no cambiaron; expiración
        # elimina simultáneamente la sesión y todos sus locks por el lease común.
        if tx(revision, [cmp(f'/sesiones/{fd}', 'MOD', row['mod']), cmp(result_key, 'CREATE', 0)], ops):
            etcd.revoke(value['lease'])
            return result
    err(409, 'RETRY', 'publicación en conflicto; reintente con el mismo fd/cuerpo')


@app.post('/v1/files/{fd}/abort', status_code=204)
def abort(fd: str, u=Depends(user)):
    row = etcd.get(f'/lecturas/{fd}')
    read = bool(row and row['value']['uid'] == u['sub'])
    value = session(fd, u, read)['value']
    etcd.revoke(value['lease'])
    # La expiración no aumenta referencias; GC nunca introduce bloques nuevos.


@app.get('/v1/files/{fd}/status')
def operation_status(fd: str, u=Depends(user)):
    result = etcd.get(f'/results/{fd}')
    if result and result['value']['uid'] == u['sub']:
        return {'state': 'closed', **result['value']['result']}
    row = etcd.get(f'/sesiones/{fd}') or etcd.get(f'/lecturas/{fd}')
    if row and row['value']['uid'] == u['sub']:
        return {'state': 'open', 'version': row['value']['snapshot']['version']}
    err(410, 'SESSION_EXPIRED', 'sin sesión vigente ni resultado retenido')


@app.get('/v1/files/stat')
def stat(path: str, u=Depends(user)):
    path = norm(path)
    found = entry(u, path)
    if not found or found['value']['type'] != 'file':
        err(404, 'NOT_FOUND', 'archivo inexistente')
    row = etcd.get(f'/inodos/{found["value"]["inode"]}')
    if not row:
        err(404, 'NOT_FOUND', 'archivo eliminado')
    return {'path': path, **row['value'], 'blocks': blocks_view(row['value'], u['sub'])}


@app.get('/v1/admin/nodes')
def admin_nodes(u=Depends(user)):
    if u['rol'] != 'admin':
        err(403, 'FORBIDDEN', 'se requiere admin')
    ns = nodos()
    blocks = etcd.prefix('/bloques/')
    sub = sum(1 for row in blocks if row['value']['state'] == 'prepared' and
              len([n for n in row['value']['replicas'] if ns.get(n, {}).get('estado') == 'vivo']) < row['value']['r'])
    leader = etcd.get('/monitor/lider')
    return {'nodos': list(ns.values()), 'bloques': len(blocks), 'subreplicados': sub,
            'monitor': leader['value'] if leader else None, 'atendido_por': ME}


def stub(addr):
    return rpc.DataNodeStub(grpc.secure_channel(addr, grpc_creds(), GRPC_OPTS))


def repair(ns, is_leader=lambda: True):
    scan_revision = epoch()
    alive = {n: v for n, v in ns.items() if v['estado'] == 'vivo'}
    referenced = {bid for row in etcd.prefix('/inodos/') for bid in row['value']['blocks']}
    for row in etcd.prefix('/lecturas/') + etcd.prefix('/sesiones/'):
        referenced.update(row['value']['snapshot']['blocks'])
        referenced.update(row['value'].get('plans', {}).values())
    for row in etcd.prefix('/bloques/'):
        if not is_leader():
            return
        value, bid = row['value'], row['key'].rsplit('/', 1)[1]
        if value['state'] != 'prepared' or bid not in referenced:
            continue
        reps = [n for n in value['replicas'] if ns.get(n, {}).get('estado') != 'caido']
        for dest in sorted(alive, key=lambda n: alive[n]['bloques']):
            if len(reps) >= value['r'] or not is_leader():
                break
            if dest in reps or alive[dest]['libre'] <= value['size']:
                continue
            for source in list(reps):
                if source not in alive:
                    continue
                # Registrar el destino ANTES del RPC: GC debe conocer incluso una
                # copia que termine después de perderse la respuesta o borrarse la ruta.
                target = f'{dest}@{alive[dest]["addr"]}'
                value = {**value, 'authorized_until': time.time() + 300,
                         'pipeline': list(dict.fromkeys([*value['pipeline'], target]))}
                ok, _ = etcd.txn([cmp(EPOCH, 'MOD', scan_revision), cmp(row['key'], 'MOD', row['mod'])],
                                 [put(row['key'], value)])
                if not ok:
                    return
                row = etcd.get(row['key'])
                token = mint(op='admin', action='replicate', b=bid, sha256=value['sha256'],
                             size=value['size'], operation=value['fd'], nodes=[source, dest],
                             targets=[target])
                try:
                    ack = stub(alive[source]['addr']).ReplicateBlock(pb.ReplicateReq(
                        block_id=bid, target=target, token=token,
                        sha256=value['sha256'], size=value['size']), timeout=30)
                    proof = verify_node(ack.receipts[0], dest)
                    if (proof.get('op') != 'stored' or proof.get('node') != dest or
                            proof.get('b') != bid or proof.get('sha256') != value['sha256'] or
                            proof.get('size') != value['size'] or proof.get('operation') != value['fd']):
                        raise ValueError('recibo de reparación inválido')
                    reps.append(dest)
                    break
                except grpc.RpcError as exc:
                    if exc.code() in (grpc.StatusCode.DATA_LOSS, grpc.StatusCode.NOT_FOUND):
                        reps.remove(source)
                    log.warning('reparación %s: %s', bid, exc.code())
                except (ValueError, jwt.PyJWTError, IndexError):
                    log.warning('recibo de reparación inválido')
        if is_leader():
            etcd.txn([cmp(row['key'], 'MOD', row['mod'])], [put(row['key'], {**value, 'replicas': reps})])


def gc(ns, is_leader=lambda: True):
    revision = epoch()  # antes de consultar cualquier referencia
    inodes = etcd.prefix('/inodos/')
    reads = etcd.prefix('/lecturas/')
    writers = etcd.prefix('/sesiones/')
    used = {bid for row in inodes for bid in row['value']['blocks']}
    for row in reads + writers:
        used.update(row['value']['snapshot']['blocks'])
        used.update(row['value'].get('plans', {}).values())
    # GC falla cerrado: si algún escritor/lector se abrió o publicó, reintentar después.
    for row in etcd.prefix('/bloques/'):
        if not is_leader():
            return
        bid, value = row['key'].rsplit('/', 1)[1], row['value']
        if bid in used:
            if 'orphan_at' in value:
                clean = {k: v for k, v in value.items() if k != 'orphan_at'}
                etcd.txn([cmp(EPOCH, 'MOD', revision), cmp(row['key'], 'MOD', row['mod'])], [put(row['key'], clean)])
            continue
        if 'orphan_at' not in value:
            etcd.txn([cmp(EPOCH, 'MOD', revision), cmp(row['key'], 'MOD', row['mod'])],
                     [put(row['key'], {**value, 'orphan_at': time.time()})])
            continue  # nunca borrar en el ciclo que lo marca
        if time.time() - value['orphan_at'] < GRACE:
            continue
        if time.time() < value.get('authorized_until', 0) + 120:
            continue  # no borrar mientras un token emitido permita terminar un RPC
        if value['state'] != 'deleting':
            ok, _ = etcd.txn([cmp(EPOCH, 'MOD', revision), cmp(row['key'], 'MOD', row['mod'])],
                             [put(row['key'], {**value, 'state': 'deleting'})])
            if not ok:
                continue
        if not is_leader():
            return
        remaining = False
        for node in {p.split('@')[0] for p in value['pipeline']} | set(value['replicas']):
            if ns.get(node, {}).get('estado') != 'vivo':
                remaining = True
                continue
            try:
                stub(ns[node]['addr']).DeleteBlock(pb.BlockReq(block_id=bid,
                    token=mint(op='admin', action='delete', b=bid)), timeout=5)
            except grpc.RpcError:
                remaining = True
        if not remaining:
            etcd.delete(row['key'])
    # Versiones ya no referenciadas y DEK de inodos borrados: limpieza acotada.
    pinned = {(r['value']['inode'], r['value']['snapshot']['version']) for r in reads + writers}
    pinned.update((r['key'].rsplit('/', 1)[1], r['value']['version']) for r in inodes)
    if epoch() == revision and is_leader():
        for row in etcd.prefix('/versions/'):
            _, _, inode, version = row['key'].split('/')
            if (inode, int(version)) not in pinned:
                etcd.txn([cmp(EPOCH, 'MOD', revision)], [delete(row['key'])])
        kept = {r['key'].rsplit('/', 1)[1] for r in inodes} | {r['value']['inode'] for r in reads + writers}
        for row in etcd.prefix('/dek/'):
            if row['key'].rsplit('/', 1)[1] not in kept:
                etcd.txn([cmp(EPOCH, 'MOD', revision)], [delete(row['key'])])


def monitor():
    while True:
        lease = None
        stop = threading.Event()
        try:
            lease = etcd.grant(15)
            ok, token = etcd.txn([cmp('/monitor/lider', 'CREATE', 0)], [put('/monitor/lider', ME, lease)])
            if not ok:
                etcd.revoke(lease)
                time.sleep(5)
                continue
            def renew(stop_event=stop, lease_id=lease):
                while not stop_event.wait(3):
                    try:
                        if not etcd.keepalive(lease_id):
                            stop_event.set()
                    except requests.RequestException:
                        stop_event.set()
            thread = threading.Thread(target=renew, daemon=True)
            thread.start()
            def leader():
                row = etcd.get('/monitor/lider')
                return not stop.is_set() and row is not None and row['create'] == token
            while leader():
                ns = nodos()
                repair(ns, leader)
                gc(ns, leader)
                stop.wait(5)
        except Exception:
            log.exception('monitor')
        finally:
            stop.set()
            if lease:
                try:
                    etcd.revoke(lease)
                except requests.RequestException:
                    pass
        time.sleep(2)


def main():
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    for attempt in range(30):
        try:
            bootstrap_users()
            break
        except requests.RequestException:
            if attempt == 29:
                raise
            time.sleep(2)
    threading.Thread(target=monitor, daemon=True).start()
    uvicorn.run(app, host='0.0.0.0', port=8443,
                ssl_certfile=str(CERTS / 'node.crt'), ssl_keyfile=str(CERTS / 'node.key'))


if __name__ == '__main__':
    main()
