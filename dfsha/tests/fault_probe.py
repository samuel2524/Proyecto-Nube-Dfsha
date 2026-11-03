"""Sondas con aserciones que usa el orquestador de fallos local."""
import argparse
import hashlib
import tempfile
from pathlib import Path

from dfsha.client import DFS, Error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('seed', 'check', 'write', 'unavailable', 'repaired'))
    parser.add_argument('path')
    args = parser.parse_args()
    dfs = DFS()
    expected = hashlib.sha256(b'F' * (9 << 20)).hexdigest()
    if args.action == 'unavailable':
        try:
            dfs.login('andres', 'clave123')
            dfs.open(args.path + '/file', 'r')
        except Error as exc:
            assert exc.status == 503, str(exc)
            print('OK: pérdida de cuórum rechazada con 503')
            return
        raise AssertionError('catálogo sin cuórum permitió abrir una versión')
    dfs.login('andres', 'clave123')
    if args.action in ('seed', 'write'):
        if args.action == 'seed':
            dfs.mkdir(args.path)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'file'
            path.write_bytes(b'F' * (9 << 20))
            result = dfs.put(str(path), args.path + ('/file' if args.action == 'seed' else '/during-fault'))
            assert result['sha256'] == expected
    elif args.action == 'repaired':
        stat = dfs.stat(args.path + '/file')
        assert all(len(set(b['todas'])) >= 3 and 'dn1' not in b['todas'] for b in stat['blocks'])
    else:
        with tempfile.TemporaryDirectory() as directory:
            result = dfs.get(args.path + '/file', str(Path(directory)/'download'))
            assert result['sha256'] == expected
    print('OK:', args.action)


if __name__ == '__main__':
    main()
