"""CLI de DFSha. La sesión (token y carpeta actual) se guarda en ~/.dfsha/sesion.json."""
import argparse
import json
import posixpath
import sys
import time
from pathlib import Path

from .client import DFS, Error

SES = Path.home() / '.dfsha' / 'sesion.json'


def cargar():
    return json.loads(SES.read_text()) if SES.exists() else {'cwd': '/'}


def guardar(s):
    SES.parent.mkdir(exist_ok=True)
    SES.write_text(json.dumps(s))


def mib(n):
    return f'{n / 2**20:.2f} MiB' if n >= 2**20 else f'{n} B'


def main(argv=None):
    ap = argparse.ArgumentParser(prog='dfsha')
    sp = ap.add_subparsers(dest='cmd', required=True)
    sp.add_parser('login').add_argument('user'); sp.choices['login'].add_argument('password')
    for c in ('pwd', 'whoami', 'nodes', 'logout'):
        sp.add_parser(c)
    for c in ('cd', 'mkdir', 'rmdir', 'rm', 'stat'):
        sp.add_parser(c).add_argument('path')
    sp.add_parser('ls').add_argument('path', nargs='?', default='.')
    mv = sp.add_parser('mv'); mv.add_argument('src'); mv.add_argument('dst')
    put = sp.add_parser('put'); put.add_argument('local'); put.add_argument('remoto', nargs='?')
    put.add_argument('--replicas', type=int, choices=(2, 3), default=3)
    get = sp.add_parser('get'); get.add_argument('remoto'); get.add_argument('local', nargs='?')
    cat = sp.add_parser('cat'); cat.add_argument('path')
    cat.add_argument('--offset', type=int, default=0); cat.add_argument('-n', type=int, default=1 << 30)
    w = sp.add_parser('write', help='modifica en un offset sin truncar (modo rw)')
    w.add_argument('path'); w.add_argument('offset', type=int); w.add_argument('texto')
    w.add_argument('--mantener', type=float, default=0, help='segundos antes del close')
    w.add_argument('--esperar', action='store_true', help='esperar el lock en vez de 423')
    a = sp.add_parser('append'); a.add_argument('path'); a.add_argument('texto')
    lk = sp.add_parser('lock', help='toma un lock sobre un rango y lo sostiene')
    lk.add_argument('path'); lk.add_argument('desde', type=int); lk.add_argument('hasta', type=int)
    lk.add_argument('--segundos', type=float, default=20); lk.add_argument('--esperar', action='store_true')
    args = ap.parse_args(argv)

    s = cargar()
    dfs = DFS(s.get('token'))
    ruta = lambda p: posixpath.normpath(posixpath.join(s['cwd'], p))
    try:
        c = args.cmd
        if c == 'login':
            s.update(token=dfs.login(args.user, args.password), user=args.user, cwd='/')
            print(f'sesión iniciada como {args.user} (token válido 15 min)')
        elif c == 'logout':
            s = {'cwd': '/'}                # se descarta el token (el finally guarda la sesión vacía)
        elif c == 'whoami':
            print(s.get('user', '(sin sesión)'))
        elif c == 'pwd':
            print(s['cwd'])
        elif c == 'cd':
            p = ruta(args.path)
            dfs.ls(p)                      # valida que exista y sea carpeta
            s['cwd'] = p
        elif c == 'ls':
            for e in dfs.ls(ruta(args.path)):
                t = time.strftime('%Y-%m-%d %H:%M', time.localtime(e['mtime']))
                tam = mib(e['size']) if e['type'] == 'file' else '-'
                print(f"{'d' if e['type'] == 'dir' else '-'}  {tam:>12}  v{e['version'] or '-':<3} {t}  {e['name']}")
        elif c == 'mkdir':
            dfs.mkdir(ruta(args.path))
        elif c == 'rmdir':
            dfs.rmdir(ruta(args.path))
        elif c == 'rm':
            dfs.rm(ruta(args.path))
        elif c == 'mv':
            dfs.mv(ruta(args.src), ruta(args.dst))
        elif c == 'stat':
            st = dfs.stat(ruta(args.path))
            print(f"{st['path']}  versión {st['version']}  {mib(st['size'])}  sha256 {st['sha256']}")
            for b in st['blocks']:
                vivas = [r['id'] for r in b['replicas']]
                print(f"  bloque {b['i']:>3}  {b['block_id'][:12]}  {mib(b['size'])}  réplicas {b['todas']}  vivas {vivas}")
        elif c == 'put':
            r = dfs.put(args.local, ruta(args.remoto or Path(args.local).name), args.replicas)
            print(f"put {mib(r['bytes'])} en {r['bloques']} bloques, {r['segundos']:.2f} s, "
                  f"{r['bytes'] / 2**20 / r['segundos']:.1f} MiB/s, sha256 {r['sha256']}")
        elif c == 'get':
            r = dfs.get(ruta(args.remoto), args.local or posixpath.basename(args.remoto))
            print(f"get {mib(r['bytes'])} (versión {r['version']}) en {r['segundos']:.2f} s, "
                  f"{r['bytes'] / 2**20 / max(r['segundos'], 1e-9):.1f} MiB/s, sha256 {r['sha256']} verificado")
        elif c == 'cat':
            f = dfs.open(ruta(args.path), 'r')
            try:
                sys.stdout.buffer.write(f.read(args.offset, args.n) + b'\n')
            finally:
                f.close()
        elif c in ('write', 'append'):
            f = dfs.open(ruta(args.path), 'a' if c == 'append' else 'rw', create=True)
            try:
                f.write(0 if c == 'append' else args.offset, args.texto.encode(),
                        esperar=getattr(args, 'esperar', False))
                print(f'lock obtenido, fencing {f.fencing}')
                if getattr(args, 'mantener', 0):
                    print(f'manteniendo el lock {args.mantener} s antes de close...', flush=True)
                    time.sleep(args.mantener)
                print(f'close: publicada versión {f.close()}')
            finally:
                f.abort()                  # si algo falló, libera sesión y locks ya (tras close no hace nada)
        elif c == 'lock':
            f = dfs.open(ruta(args.path), 'rw')
            try:
                print(f'lock concedido, fencing {f.lock(args.desde, args.hasta, args.esperar)}', flush=True)
                time.sleep(args.segundos)
                f.close()
                print('lock liberado')
            finally:
                f.abort()
        elif c == 'nodes':
            r = dfs.nodes()
            print(f"atendido por {r['atendido_por']}, monitor líder {r['monitor']}, "
                  f"bloques {r['bloques']}, subreplicados {r['subreplicados']}")
            for n in sorted(r['nodos'], key=lambda n: n['id']):
                print(f"  {n['id']:<4} {n['estado']:<10} {n['addr']:<28} bloques {n['bloques']:>4}  "
                      f"último latido hace {n['hace_s']} s")
    except Error as e:
        print(f'ERROR {e}', file=sys.stderr)
        return 1
    finally:
        guardar(s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
