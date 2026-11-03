"""Fallos solo del proyecto Compose indicado; siempre restaura los servicios.

No invoca AWS/SSH y no elimina volúmenes. Requiere el clúster ya levantado.
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import time
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', default='dfsha-revision')
    args = parser.parse_args()
    if not re.fullmatch(r'dfsha-[a-z0-9-]+', args.project):
        parser.error('use un proyecto de laboratorio con prefijo dfsha-')
    compose = ['docker', 'compose', '-p', args.project, '-f', 'docker-compose.local.yml']
    run_id = 'revision-failures-' + uuid.uuid4().hex[:12]
    remote = '/failure-' + uuid.uuid4().hex[:10]
    directory = Path('resultados')/run_id
    directory.mkdir(parents=True, exist_ok=False)
    records = []
    stopped = set()
    def command(arguments, check=True):
        start = time.perf_counter()
        process = subprocess.run(compose + arguments, text=True, capture_output=True)
        records.append({'command': arguments, 'seconds': time.perf_counter() - start,
                        'returncode': process.returncode, 'polling': not check,
                        'stdout': process.stdout, 'stderr': process.stderr})
        (directory/'run.json').write_text(json.dumps({'environment': 'local Docker; no AWS',
            'project': args.project, 'records': records}, indent=2), encoding='utf-8')
        if process.returncode and check:
            raise RuntimeError(process.stdout + process.stderr)
        print(process.stdout.strip(), flush=True)
        return process.returncode == 0
    def probe(action, check=True):
        return command(['exec', '-T', 'cliente', 'python', '-m', 'tests.fault_probe', action, remote], check)
    try:
        probe('seed')
        command(['stop', 'dn1'])
        stopped.add('dn1')
        time.sleep(12)
        probe('check')
        probe('write')
        deadline = time.monotonic() + 180
        while not probe('repaired', check=False):
            if time.monotonic() > deadline:
                raise RuntimeError('no se restauraron réplicas de la sonda en 180 s')
            time.sleep(5)
        command(['start', 'dn1'])
        stopped.remove('dn1')
        command(['stop', 'meta1'])
        stopped.add('meta1')
        probe('check')
        command(['start', 'meta1'])
        stopped.remove('meta1')
        command(['stop', 'etcd1'])
        stopped.add('etcd1')
        time.sleep(4)
        probe('check')
        command(['stop', 'etcd2'])
        stopped.add('etcd2')
        probe('unavailable')
    finally:
        if stopped:
            command(['start', *sorted(stopped)])
    time.sleep(4)
    probe('check')
    print('Fallos locales verificados. Registro:', directory)


if __name__ == '__main__':
    main()
