#!/bin/bash
# Estado del clúster etcd visto desde una VM (por defecto vm2): miembro, líder, término Raft e índice.
# Uso: bash tests/etcd_estado.sh [vm]
ssh -n -o LogLevel=ERROR "${1:-vm2}" docker exec dfsha-etcd etcdctl \
  --endpoints=https://etcd1.dfsha.internal:2379,https://etcd2.dfsha.internal:2379,https://etcd3.dfsha.internal:2379 \
  --cacert /certs/ca.crt --cert /certs/node.crt --key /certs/node.key endpoint status -w json 2>/dev/null |
python3 -c '
import json, sys
fila = "{:<36}{:<8}{:<9}{}"
print(fila.format("miembro", "lider", "termino", "indice"))
for e in json.load(sys.stdin):
    s = e["Status"]
    lider = "si" if s["header"]["member_id"] == s["leader"] else "no"
    print(fila.format(e["Endpoint"], lider, s["raftTerm"], s["raftIndex"]))
'
