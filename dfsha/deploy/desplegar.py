"""Despliegue revisado: paquetes mínimos por rol y resolución en contenedores.

Requiere cuatro VMs del Learner Lab etiquetadas, Docker/Compose y SSH. No crea
recursos ni copia una llave SSH administrativa al bastión. Falta validar en AWS.
"""
import argparse
import io
import json
import shlex
import subprocess
import tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3

ROLES = {
    'vm1': ('etcd,meta,dn', ['etcd1', 'meta1', 'meta', 'dn1']),
    'vm2': ('etcd,meta,dn', ['etcd2', 'meta2', 'dn2']),
    'vm3': ('etcd,dn', ['etcd3', 'dn3']),
    'vm4': ('dn', ['dn4', 'cliente']),
}


def discover(region):
    ec2 = boto3.client('ec2', region_name=region)
    result = {}
    paginator = ec2.get_paginator('describe_instances')
    for page in paginator.paginate(Filters=[{'Name': 'tag:Proyecto', 'Values': ['DFSha']},
                                            {'Name': 'instance-state-name', 'Values': ['running']}]):
        for reservation in page['Reservations']:
            for instance in reservation['Instances']:
                name = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Name'), '')
                name = name.removeprefix('dfsha-')
                if name in ROLES:
                    if name in result:
                        raise RuntimeError('Etiqueta duplicada: ' + name)
                    result[name] = {'priv': instance['PrivateIpAddress'], 'pub': instance.get('PublicIpAddress')}
    if set(result) != set(ROLES) or any(not v['pub'] for v in result.values()):
        raise RuntimeError('Se requieren vm1..vm4 accesibles por SSH; para subred privada use ProxyJump/VPN explícito.')
    return result


def package(vm, hosts):
    profiles, names = ROLES[vm]
    roles = [n for n in names if n != 'meta']
    data = io.BytesIO()
    settings = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines()
                    if '=' in line and not line.startswith('#'))
    block_size = settings.get('BLOCK_SIZE', '8388608')
    if block_size not in ('4194304', '8388608'):
        raise ValueError('BLOCK_SIZE debe ser 4 u 8 MiB para los experimentos acordados')
    def filter_entry(info):
        if any(p in info.name for p in ('__pycache__', '_pb2', '.git')):
            return None
        info.mode = 0o755 if info.isdir() else 0o600 if info.name.endswith(('.key', '.env')) else 0o644
        return info
    with tarfile.open(fileobj=data, mode='w:gz') as archive:
        for name in ('dfsha', 'proto', 'tests', 'scripts', 'Dockerfile', 'requirements.txt'):
            archive.add(name, filter=filter_entry)
        archive.add('deploy/docker-compose.yml', filter=filter_entry)
        for role in roles:
            archive.add('certs/' + role, filter=filter_entry)
        # Compose requiere el archivo incluso si el perfil meta está inactivo:
        # en esas VMs se entrega VACÍO, no la KEK ni contraseñas.
        secret = Path('.env').read_bytes() if 'meta' in profiles else b''
        generated = {
            '.format-v2': b'DFSha revision 2\n',
            'deploy/meta.env': secret,
            'deploy/hosts.generated.json': json.dumps({'services': {
                name: {'extra_hosts': hosts} for name in ('etcd', 'meta', 'dn')}}).encode(),
            'deploy/.env': ('COMPOSE_PROFILES=' + profiles + '\n' +
                           'BLOCK_SIZE=' + block_size + '\n' +
                           'ETCD_NAME=' + next((n for n in names if n.startswith('etcd')), 'unused') + '\n' +
                           'META_ID=' + next((n for n in names if n.startswith('meta') and n != 'meta'), 'unused') + '\n' +
                           'DN_ID=' + next(n for n in names if n.startswith('dn')) + '\n').encode(),
        }
        for filename, content in generated.items():
            info = tarfile.TarInfo(filename)
            info.size, info.mode = len(content), 0o600
            archive.addfile(info, io.BytesIO(content))
    return data.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key', required=True)
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()
    instances = discover(args.region)
    hosts = {f'{name}.dfsha.internal': instances[vm]['priv']
             for vm, (_, names) in ROLES.items() for name in names}
    host_lines = ''.join(f'{instances[vm]["priv"]} {vm} ' +
        ' '.join(n + '.dfsha.internal' for n in names) + '\n' for vm, (_, names) in ROLES.items())
    ssh = ['ssh', '-i', args.key, '-o', 'StrictHostKeyChecking=accept-new', '-o', 'ConnectTimeout=15']
    def deploy(vm):
        target = f'ubuntu@{instances[vm]["pub"]}'
        preflight = ('if test -d ~/dfsha && test -n "$(ls -A ~/dfsha)" && '
                     'test ! -f ~/dfsha/.format-v2; then '
                     'echo "Instalación antigua: preparar un directorio/volúmenes v2 separados" >&2; exit 1; fi; '
                     'mkdir -p ~/dfsha && tar xzf - -C ~/dfsha')
        subprocess.run(ssh + [target, preflight],
                       input=package(vm, hosts), check=True)
        script = ('set -eu\ncloud-init status --wait >/dev/null\n'
                  "sudo sed -i '/dfsha.internal/d' /etc/hosts\n"
                  'printf %s ' + shlex.quote(host_lines) + ' | sudo tee -a /etc/hosts >/dev/null\n'
                  'cd ~/dfsha\nsudo docker build -t dfsha:revision .\n'
                  'cd deploy\nsudo docker compose -f docker-compose.yml -f hosts.generated.json config --quiet\n'
                  'sudo docker compose -f docker-compose.yml -f hosts.generated.json up -d\n'
                  'sudo docker exec dfsha-dn python -c "import socket; '
                  "print(socket.gethostbyname('meta1.dfsha.internal'))" + '"\n')
        subprocess.run(ssh + [target, 'bash -s'], input=script.encode(), check=True)
        return vm
    with ThreadPoolExecutor(4) as pool:
        for vm in pool.map(deploy, ROLES):
            print('Desplegado:', vm)
    print('Falta ejecutar salud, pruebas y mediciones en AWS. No se registró aprobación/éxito remoto automáticamente.')


if __name__ == '__main__':
    main()
