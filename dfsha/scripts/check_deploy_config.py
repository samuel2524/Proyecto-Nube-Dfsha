"""Renderiza los cuatro paquetes AWS con Compose, sin crear recursos ni revelar env."""
import importlib.util
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('package_only', 'deploy/desplegar.py')
module = importlib.util.module_from_spec(spec)
sys.modules.setdefault('boto3', SimpleNamespace())  # discover/main no se ejecutan en esta comprobación
spec.loader.exec_module(module)
hosts = {name + '.dfsha.internal': f'10.0.0.{i+10}'
         for i, (_, names) in enumerate(module.ROLES.values()) for name in names}
for vm in module.ROLES:
    with tempfile.TemporaryDirectory(dir=Path.cwd(), prefix='.compose-check-') as temp:
        with tarfile.open(fileobj=io.BytesIO(module.package(vm, hosts)), mode='r:gz') as archive:
            archive.extractall(temp, filter='data')
        environment = {k:v for k,v in os.environ.items()
                       if k not in ('COMPOSE_PROFILES','ETCD_NAME','META_ID','DN_ID','BLOCK_SIZE')}
        subprocess.run(['docker','compose','-f','docker-compose.yml','-f','hosts.generated.json',
                        'config','--quiet'], cwd=Path(temp)/'deploy', env=environment, check=True)
        print(vm, ': Compose y extra_hosts válidos')
