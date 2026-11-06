#!/bin/sh
# Bastión, desde ~/dfsha. No requiere secretos de metadatos.
set -eu
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m grpc_tools.protoc -Iproto --python_out=dfsha --grpc_python_out=dfsha proto/dfsha.proto
sed -i 's/^import dfsha_pb2/from . import dfsha_pb2/' dfsha/dfsha_pb2_grpc.py
echo 'Ejecute desde esta carpeta:'
echo 'export CERTS="$PWD/certs/cliente" CA_CERT="$PWD/certs/cliente/ca.crt"'
echo 'export DFSHA_META=https://meta1.dfsha.internal:8443,https://meta2.dfsha.internal:8443'
echo '.venv/bin/python -m dfsha.cli login <usuario> <contraseña>'
