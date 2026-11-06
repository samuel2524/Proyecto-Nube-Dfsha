"""Caídas reales en AWS Academy: detiene contenedores por SSH y comprueba con las sondas desde el bastión.

Uso, en la máquina del administrador y desde dfsha/ (mismas VMs y llave que deploy/desplegar.py):
    python scripts/verify_aws.py --key <llave.pem>
Restaura en `finally` todo lo que detuvo. No crea ni borra instancias ni volúmenes.
"""
import argparse
import datetime as dt
import importlib.util
import json
import subprocess
import time
import uuid
from pathlib import Path

spec = importlib.util.spec_from_file_location('desplegar', 'deploy/desplegar.py')
desplegar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desplegar)

SONDA = ('cd ~/dfsha && CERTS=$HOME/dfsha/certs/cliente CA_CERT=$HOME/dfsha/certs/cliente/ca.crt '
         'DFSHA_META=https://meta1.dfsha.internal:8443,https://meta2.dfsha.internal:8443 '
         '.venv/bin/python -m tests.fault_probe')


def restore_all(stopped, start):
    """Intentar TODOS los reinicios aunque uno falle; conservar errores para informar."""
    errors = []
    for vm, service in list(reversed(stopped)):
        try:
            start(vm, service)
        except Exception as exc:
            errors.append((vm, service, str(exc)))
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key', required=True)
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()
    vms = desplegar.discover(args.region)
    ssh = ['ssh', '-i', args.key, '-o', 'StrictHostKeyChecking=accept-new', '-o', 'ConnectTimeout=15']
    remote = '/failure-' + uuid.uuid4().hex[:10]
    directory = Path('resultados') / ('revision-failures-aws-' + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True, exist_ok=False)
    records, stopped = [], []

    def run(vm, command, check=True, label=None):
        start = time.perf_counter()
        process = subprocess.run(ssh + [f'ubuntu@{vms[vm]["pub"]}', command], capture_output=True,
                                 text=True, encoding='utf-8', errors='replace')
        records.append({'vm': vm, 'step': label or command, 'seconds': round(time.perf_counter() - start, 2),
                        'returncode': process.returncode, 'polling': not check,
                        'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                        'stdout': process.stdout.strip(), 'stderr': process.stderr.strip()[-500:]})
        (directory / 'run.json').write_text(json.dumps({'environment': 'AWS Academy (4 VMs EC2)',
            'path': remote, 'records': records}, indent=2), encoding='utf-8')
        print(f'[{vm}] {label or command} -> {process.returncode} {process.stdout.strip()}', flush=True)
        if process.returncode and check:
            raise RuntimeError(process.stdout + process.stderr)
        return process.returncode == 0

    def probe(action, check=True):
        return run('vm4', f'{SONDA} {action} {remote}', check, f'sonda {action}')

    def stop(vm, service):
        # Registrar intención antes de SSH: si se pierde la respuesta después de
        # detenerlo, finally debe intentar restaurarlo igualmente.
        if (vm, service) not in stopped:
            stopped.append((vm, service))
        run(vm, f'sudo docker stop dfsha-{service}', label=f'detener {service}')

    def start(vm, service):
        run(vm, f'sudo docker start dfsha-{service}', label=f'iniciar {service}')
        stopped.remove((vm, service))

    try:
        probe('seed')
        stop('vm1', 'dn')                        # nodo de datos dn1 caído
        time.sleep(12)
        probe('check')
        probe('write')
        deadline = time.monotonic() + 240
        while not probe('repaired', check=False):
            if time.monotonic() > deadline:
                raise RuntimeError('no se restauraron tres réplicas sin dn1 en 240 s')
            time.sleep(5)
        start('vm1', 'dn')
        stop('vm1', 'meta')                      # coordinador meta1 caído: el cliente usa meta2
        probe('check')
        start('vm1', 'meta')
        stop('vm1', 'etcd')                      # un miembro etcd menos: 2 de 3 mantienen quórum
        time.sleep(4)
        probe('check')
        stop('vm2', 'etcd')                      # 1 de 3: sin quórum, el catálogo falla cerrado
        probe('unavailable')
    finally:
        restore_errors = restore_all(stopped, start)
        if restore_errors:
            # Todos se intentaron antes de informar; no abandonar otros etcd detenidos.
            details = '; '.join(f'{vm}/{service}: {error}' for vm, service, error in restore_errors)
            raise RuntimeError('Servicios que no se pudieron restaurar: ' + details)
    time.sleep(10)
    probe('check')
    print('Caídas en AWS verificadas. Registro:', directory)


if __name__ == '__main__':
    main()
