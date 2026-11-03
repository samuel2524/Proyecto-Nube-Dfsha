"""Registra verificaciones no destructivas de la revisión en un run separado."""
import ast
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


root = Path(__file__).resolve().parents[1]
timestamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
directory = root/'resultados'/('revision-checks-' + timestamp)
directory.mkdir(parents=True, exist_ok=False)
records = []


def check(label, command):
    process = subprocess.run(command, cwd=root, capture_output=True, text=True)
    records.append({'check': label, 'command': command, 'returncode': process.returncode,
                    'stdout': process.stdout, 'stderr': process.stderr})
    (directory/'checks.json').write_text(json.dumps({'environment': 'local Docker; no AWS',
        'records': records}, indent=2), encoding='utf-8')
    if process.returncode:
        raise RuntimeError(process.stdout + process.stderr)
    print(label, ': OK')


files = list(root.rglob('*.py'))
for path in files:
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
records.append({'check': 'syntax', 'files': len(files), 'returncode': 0})
check('contract and statistics', ['docker','run','--rm','--env-file','.env',
    '-e','CERTS=/certs','-e','ETCD_ENDPOINTS=https://unused:2379',
    '--mount', f'type=bind,source={root / "certs/meta1"},target=/certs,readonly',
    '--mount', f'type=bind,source={root / "tests"},target=/app/tests,readonly',
    'dfsha:revision','python','-m','unittest','-v','tests.unit_contract','tests.test_statistics'])
check('deployment package isolation', ['docker','run','--rm',
    '--mount', f'type=bind,source={root},target=/workspace,readonly', '--workdir','/workspace',
    'dfsha:revision','python','-m','tests.test_deploy'])
check('four AWS Compose configurations', [sys.executable, 'scripts/check_deploy_config.py'])
check('image identifier', ['docker','image','inspect','dfsha:revision','--format','{{.Id}}'])
check('mTLS rejects missing client certificate', ['docker','compose','-p','dfsha-revision',
    '-f','docker-compose.local.yml','exec','-T','cliente','python','-m','unittest','-v',
    'tests.regression.Regression.test_mtls_rejects_missing_client_certificate'])
print('Registro:',directory)
