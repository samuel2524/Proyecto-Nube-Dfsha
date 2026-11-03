"""Verifica paquete por rol sin credenciales AWS, sin SSH y sin revelar secretos."""
import importlib.util
import io
import json
import sys
import tarfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class Packages(unittest.TestCase):
    def test_roles_do_not_receive_foreign_secrets_and_have_container_hosts(self):
        spec = importlib.util.spec_from_file_location('deploy_under_test', 'deploy/desplegar.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'boto3': SimpleNamespace()}):
            spec.loader.exec_module(module)
        for vm in module.ROLES:
            payload = module.package(vm, {'meta1.dfsha.internal': '10.0.0.1'})
            with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
                names = archive.getnames()
                self.assertNotIn('.env', names)
                self.assertFalse(any('/private/' in name for name in names))
                config = json.load(archive.extractfile('deploy/hosts.generated.json'))
                self.assertEqual(config['services']['dn']['extra_hosts']['meta1.dfsha.internal'], '10.0.0.1')
                meta_env = archive.extractfile('deploy/meta.env').read()
                if vm in ('vm3', 'vm4'):
                    self.assertEqual(meta_env, b'')
                    self.assertFalse(any(name.endswith(('auth.key','capability.key','etcd.key')) for name in names))
                else:
                    self.assertIn(b'KEK=', meta_env)


if __name__ == '__main__':
    unittest.main(verbosity=2)
