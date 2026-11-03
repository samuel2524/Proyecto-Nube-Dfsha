"""P6: un nodo de datos rechaza lecturas sin token, con token alterado o sin TLS.
Uso: python -m tests.token_nodo /ruta/archivo"""
import sys

import grpc

from dfsha import dfsha_pb2 as pb, dfsha_pb2_grpc as rpc
from dfsha.client import DFS
from dfsha.common import grpc_creds

d = DFS()
d.login('andres', 'clave123')
reader = d.open(sys.argv[1] if len(sys.argv) > 1 else '/p1/grande.bin', 'r')
b = reader.blocks[0]
addr = b['replicas'][0]['addr']
stub = rpc.DataNodeStub(grpc.secure_channel(addr, grpc_creds()))
for nombre, tok in [('token válido', b['token']), ('sin token', ''), ('token alterado', b['token'][:-4] + 'abcd')]:
    try:
        n = sum(len(c.data) for c in stub.ReadBlock(pb.BlockReq(block_id=b['block_id'], token=tok), timeout=10))
        assert nombre == 'token válido' and n > 0, 'acceso inválido aceptado'
        print(f'{addr} con {nombre}: OK, {n} bytes cifrados')
    except grpc.RpcError as e:
        assert nombre != 'token válido' and e.code() == grpc.StatusCode.UNAUTHENTICATED
        print(f'{addr} con {nombre}: {e.code().name} ({e.details()})')
try:
    next(rpc.DataNodeStub(grpc.insecure_channel(addr)).ReadBlock(
        pb.BlockReq(block_id=b['block_id'], token=b['token']), timeout=5))
    raise AssertionError('conexión sin TLS aceptada')
except grpc.RpcError as e:
    print(f'{addr} sin TLS: {e.code().name}')
reader.close()
