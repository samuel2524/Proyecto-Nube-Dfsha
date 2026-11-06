"""Almacén create-once de bloques cifrados, recibos firmados y replicación S2S."""
import hashlib
import itertools
import logging
import os
import queue
import shutil
import threading
import time
import uuid
from concurrent import futures
from pathlib import Path

import grpc
import requests

from . import dfsha_pb2 as pb, dfsha_pb2_grpc as rpc
from .common import BLOCK_SIZE, CERTS, GRPC_OPTS, check, grpc_creds, node_proof

ID = os.environ['NODE_ID']
ADDR = os.environ['NODE_ADDR']
DATA = Path(os.environ.get('DATA_DIR', '/data'))
SLOW = DATA / 'slow'
CHUNK = 1 << 20
log = logging.getLogger(ID)
_locks = [threading.Lock() for _ in range(256)]
_active_parts = set()
_parts_lock = threading.Lock()


def _path(bid):
    if len(bid) != 32 or any(c not in '0123456789abcdef' for c in bid):
        raise ValueError('block_id inválido')
    return DATA / 'blocks' / f'{bid}.blk'


def _disk_sync():
    if os.name != 'nt':
        fd = os.open(DATA / 'blocks', os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _receipt(bid, sha, size, operation):
    return node_proof({'node': ID, 'op': 'stored', 'b': bid, 'sha256': sha,
                       'size': size, 'operation': operation})


class DataNode(rpc.DataNodeServicer):
    def WriteBlock(self, iterator, ctx):
        first = next(iterator, None)
        if first is None:
            ctx.abort(grpc.StatusCode.INVALID_ARGUMENT, 'stream vacío')
        claims = check(first.token, first.block_id, ops=('w', 'admin'))
        if not claims:
            ctx.abort(grpc.StatusCode.UNAUTHENTICATED, 'capacidad inválida')
        pipeline_ids = [p.split('@', 1)[0] for p in first.pipeline]
        if (first.size > BLOCK_SIZE + 28 or first.size < 28 or
                len(first.sha256) != 64 or first.size != claims.get('size') or
                first.sha256 != claims.get('sha256') or first.operation_id != claims.get('operation') or
                ID not in claims.get('nodes', []) or claims.get('b') != first.block_id or
                not pipeline_ids or pipeline_ids[0] != ID or len(pipeline_ids) > 4 or
                len(set(pipeline_ids)) != len(pipeline_ids) or
                any(p not in claims.get('targets', []) for p in first.pipeline) or
                (claims['op'] == 'admin' and claims.get('action') != 'replicate')):
            ctx.abort(grpc.StatusCode.INVALID_ARGUMENT, 'bloque fuera del plan autorizado')
        try:
            final = _path(first.block_id)
        except ValueError as exc:
            ctx.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        if SLOW.exists():
            time.sleep(min(float(SLOW.read_text() or 0), 120))
        part = final.with_name(f'{first.block_id}.{uuid.uuid4().hex}.part')
        with _parts_lock:
            _active_parts.add(part)
        size, digest = 0, hashlib.sha256()
        # El stream se consume incrementalmente; no se materializa [first, *iterator].
        try:
            with open(part, 'xb') as file:
                for chunk in itertools.chain((first,), iterator):
                    size += len(chunk.data)
                    if size > first.size or len(chunk.data) > CHUNK:
                        ctx.abort(grpc.StatusCode.INVALID_ARGUMENT, 'tamaño excedido')
                    file.write(chunk.data)
                    digest.update(chunk.data)
                if size != first.size or digest.hexdigest() != first.sha256:
                    ctx.abort(grpc.StatusCode.DATA_LOSS, 'tamaño o SHA-256 no coincide')
                file.flush()
                os.fsync(file.fileno())
            with _locks[int(first.block_id[:2], 16)]:
                if final.exists():
                    if final.stat().st_size != size or hashlib.sha256(final.read_bytes()).hexdigest() != first.sha256:
                        ctx.abort(grpc.StatusCode.ALREADY_EXISTS, 'bloque inmutable: contenido distinto')
                else:
                    # link crea el destino solo si no existe; no sobrescribe otro .blk.
                    os.link(part, final)
                    _disk_sync()
        finally:
            part.unlink(missing_ok=True)
            with _parts_lock:
                _active_parts.discard(part)
        stored = [ID]
        receipts = [_receipt(first.block_id, first.sha256, size, first.operation_id)]
        # Réplica S2S desde el bloque validado. Ya no se promete pipeline solapado.
        rest = list(first.pipeline[1:])
        if rest:
            target, addr = rest[0].split('@', 1)
            if target not in claims['nodes']:
                ctx.abort(grpc.StatusCode.PERMISSION_DENIED, 'destino fuera del plan')
            try:
                ack = self._send(final, rest, first.token, first.sha256, size, first.operation_id)
                stored.extend(ack.stored)
                receipts.extend(ack.receipts)
            except grpc.RpcError as exc:
                log.warning('réplica %s falló: %s', target, exc.code())
        return pb.WriteAck(stored=stored, receipts=receipts)

    @staticmethod
    def _send(path, pipeline, token, sha, size, operation):
        def chunks():
            with open(path, 'rb') as file:
                yield pb.WriteChunk(block_id=path.stem, token=token, pipeline=pipeline,
                                    sha256=sha, size=size, operation_id=operation, data=file.read(CHUNK))
                while data := file.read(CHUNK):
                    yield pb.WriteChunk(data=data)
        with grpc.secure_channel(pipeline[0].split('@', 1)[1], grpc_creds(), GRPC_OPTS) as channel:
            return rpc.DataNodeStub(channel).WriteBlock(chunks(), timeout=25)

    def ReadBlock(self, req, ctx):
        if not check(req.token, req.block_id, ops=('r',)):
            ctx.abort(grpc.StatusCode.UNAUTHENTICATED, 'capacidad inválida')
        try:
            path = _path(req.block_id)
        except ValueError as exc:
            ctx.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        if not path.exists():
            ctx.abort(grpc.StatusCode.NOT_FOUND, 'bloque no existe')
        with open(path, 'rb') as file:
            while data := file.read(CHUNK):
                yield pb.Chunk(data=data)

    def ReplicateBlock(self, req, ctx):
        claims = check(req.token, req.block_id, ops=('admin',))
        if (not claims or claims.get('b') != req.block_id or claims.get('action') != 'replicate' or
                req.target not in claims.get('targets', []) or claims.get('sha256') != req.sha256 or
                claims.get('size') != req.size):
            ctx.abort(grpc.StatusCode.UNAUTHENTICATED, 'orden interna inválida')
        path = _path(req.block_id)
        if not path.exists():
            ctx.abort(grpc.StatusCode.NOT_FOUND, 'fuente no tiene el bloque')
        if path.stat().st_size != req.size or hashlib.sha256(path.read_bytes()).hexdigest() != req.sha256:
            ctx.abort(grpc.StatusCode.DATA_LOSS, 'fuente corrupta: no se replica')
        return self._send(path, [req.target], req.token, req.sha256, req.size, claims['operation'])

    def DeleteBlock(self, req, ctx):
        claims = check(req.token, ops=('admin',))
        if not claims or claims.get('action') != 'delete' or claims.get('b') != req.block_id:
            ctx.abort(grpc.StatusCode.UNAUTHENTICATED, 'orden de borrado inválida')
        _path(req.block_id).unlink(missing_ok=True)
        _disk_sync()
        return pb.Empty()

    def ListBlocks(self, req, ctx):
        claims = check(req.token, ops=('admin',))
        if not claims or claims.get('action') != 'list':
            ctx.abort(grpc.StatusCode.UNAUTHENTICATED, 'orden de inventario inválida')
        return pb.BlockList(block_ids=[p.stem for p in (DATA / 'blocks').glob('*.blk')
                                      if p.stat().st_mtime < time.time() - req.older_than])


def heartbeat():
    endpoints = os.environ['META_ENDPOINTS'].split(',')
    session = requests.Session()
    session.trust_env = False
    while True:
        usage = shutil.disk_usage(DATA)
        payload = {'node': ID, 'addr': ADDR, 'libre': usage.free, 'total': usage.total,
                   'bloques': sum(1 for _ in (DATA / 'blocks').glob('*.blk'))}
        proof = node_proof({**payload, 'op': 'heartbeat'})
        for endpoint in endpoints:
            try:
                response = session.post(endpoint + '/v1/internal/heartbeat', json={'proof': proof},
                                        verify=str(CERTS / 'ca.crt'), timeout=5)
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                log.warning('heartbeat: %s', exc)
        time.sleep(3)


def cleanup_parts():
    while True:
        with _parts_lock:
            for path in (DATA / 'blocks').glob('*.part'):
                if path not in _active_parts and time.time() - path.stat().st_mtime > 600:
                    path.unlink(missing_ok=True)
        time.sleep(30)


def main():
    logging.basicConfig(level=logging.INFO)
    (DATA / 'blocks').mkdir(parents=True, exist_ok=True)
    for path in (DATA / 'blocks').glob('*.part'):
        path.unlink()
    threading.Thread(target=heartbeat, daemon=True).start()
    threading.Thread(target=cleanup_parts, daemon=True).start()
    server = grpc.server(futures.ThreadPoolExecutor(16), options=GRPC_OPTS)
    rpc.add_DataNodeServicer_to_server(DataNode(), server)
    creds = grpc.ssl_server_credentials(
        [((CERTS / 'node.key').read_bytes(), (CERTS / 'node.crt').read_bytes())],
        root_certificates=(CERTS / 'ca.crt').read_bytes(), require_client_auth=True)
    server.add_secure_port(f'0.0.0.0:{ADDR.rsplit(":", 1)[1]}', creds)
    server.start()
    server.wait_for_termination()


if __name__ == '__main__':
    main()
