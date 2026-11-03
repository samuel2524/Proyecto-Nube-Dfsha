"""Mediciones crudas y resúmenes reconstruibles; nunca sobrescribe bench.csv histórico."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import platform
import importlib.metadata
import statistics
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def summarize(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row['experiment'], row['condition'], row['operation'], row['MiB']), []).append(float(row['seconds']))
    output = []
    for (exp, condition, operation, mb), values in groups.items():
        ordered = sorted(values)
        output.append({'experiment': exp, 'condition': condition, 'operation': operation, 'MiB': mb,
                       'n': len(values), 'mean_s': statistics.mean(values),
                       'std_s': statistics.stdev(values) if len(values) > 1 else 0,
                       'p50_s': statistics.median(values), 'p95_s': ordered[math.ceil(.95 * len(values)) - 1],
                       'MiB_s': statistics.mean(float(mb) / s for s in values)})
    return output


def validate_summary(path):
    """Detecta errores matemáticos; no certifica la procedencia de las mediciones."""
    errors = []
    with Path(path).open(newline='', encoding='utf-8') as file:
        for number, row in enumerate(csv.DictReader(file), 2):
            n = int(row['n'])
            mean = float(row.get('mean_s', row.get('lat_media_s')))
            maximum = float(row['p95_s'])
            if n <= 19 and maximum + .001 < mean:
                errors.append(f'fila {number}: p95 (máximo para n={n}) menor que media')
    return errors


def write_csv(path, rows):
    if rows:
        with path.open('w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def run(args):
    from dfsha.client import DFS
    from dfsha.common import BLOCK_SIZE
    directory = Path('resultados') / ('revision-bench-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    directory.mkdir(parents=True, exist_ok=False)
    source_hash = hashlib.sha256()
    for path in sorted(Path('dfsha').glob('*.py')):
        source_hash.update(path.name.encode() + path.read_bytes())
    metadata = {'environment': args.environment, 'source_sha256': source_hash.hexdigest(),
                'python': platform.python_version(), 'host': platform.node(), 'parameters': vars(args),
                'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'status': 'running'}
    metadata['dependencies'] = {name: importlib.metadata.version(name) for name in
        ('fastapi', 'grpcio', 'cryptography', 'PyJWT', 'requests', 'pydantic')}
    samples = []
    def client():
        dfs = DFS()
        dfs.login(os.environ.get('BENCH_USER', 'andres'), os.environ.get('BENCH_PASSWORD', 'clave123'))
        return dfs
    dfs = client()
    remote = '/bench-' + uuid.uuid4().hex[:10]
    dfs.mkdir(remote)
    sources = {}
    def source(mb):
        if mb not in sources:
            path = directory / f'source-{mb}.bin'
            with path.open('wb') as file:
                for _ in range(mb):
                    file.write(os.urandom(1 << 20))
            sources[mb] = path
        return str(sources[mb])
    probe = dfs.open(remote + '/configuration', 'w', create=True)
    metadata.update(block_size=probe.bs, max_blocks=probe.max_blocks)
    probe.abort()
    def record(exp, condition, operation, mb, repetition, seconds):
        samples.append({'experiment': exp, 'condition': condition, 'operation': operation,
                        'MiB': mb, 'repetition': repetition, 'seconds': seconds,
                        'timestamp_utc': dt.datetime.now(dt.timezone.utc).isoformat()})
        write_csv(directory/'samples.csv', samples)
        write_csv(directory/'summary.csv', summarize(samples))
    try:
        for mb in args.sizes:
            for repetition in range(args.repetitions):
                sent = dfs.put(source(mb), remote + f'/size-{mb}')
                got = dfs.get(remote + f'/size-{mb}', str(directory/'download.bin'))
                assert sent['sha256'] == got['sha256']
                record('E1', f'R=3;bytes={mb}', 'put', mb, repetition, sent['segundos'])
                record('E1', f'R=3;bytes={mb}', 'get', mb, repetition, got['segundos'])
        for replicas in (2, 3):
            for repetition in range(args.repetitions):
                sent = dfs.put(source(args.replication_size), remote + f'/replicas-{replicas}', replicas=replicas)
                record('E2', f'R={replicas};W=2', 'put', args.replication_size, repetition, sent['segundos'])
        for count in args.clients:
            clients = [client() for _ in range(count)]
            concurrent_source = source(args.concurrent_size)
            for operation in ('put', 'get'):
                for repetition in range(args.repetitions):
                    started = time.perf_counter()
                    with ThreadPoolExecutor(count) as pool:
                        if operation == 'put':
                            list(pool.map(lambda k: clients[k].put(concurrent_source, remote + f'/parallel-{k}'), range(count)))
                        else:
                            list(pool.map(lambda k: clients[k].get(remote + f'/parallel-{k}', str(directory/f'download-{k}.bin')), range(count)))
                    record('E3', f'clients={count}', operation, count * args.concurrent_size,
                           repetition, time.perf_counter() - started)
        metadata['status'] = 'complete'
    finally:
        metadata['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        if metadata['status'] != 'complete':
            metadata['status'] = 'failed'
        (directory/'run.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        for path in directory.glob('*.bin'):
            path.unlink()
    print('Muestras y resumen:', directory)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--environment', required=True, choices=('local', 'aws'))
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--sizes', type=int, nargs='+', default=[10, 100, 500])
    parser.add_argument('--clients', type=int, nargs='+', default=[1, 2, 4, 8])
    parser.add_argument('--replication-size', type=int, default=100)
    parser.add_argument('--concurrent-size', type=int, default=50)
    args = parser.parse_args()
    if args.repetitions < 5 or min(args.sizes + args.clients + [args.replication_size, args.concurrent_size]) < 1:
        parser.error('al menos cinco repeticiones y parámetros positivos')
    run(args)
