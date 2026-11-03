"""P5c: un lector con el archivo abierto no ve una escritura hasta su próximo open (close-to-open).
Uso: python -m tests.close_to_open /ruta/archivo.txt"""
import sys

from dfsha.client import DFS

ruta = sys.argv[1] if len(sys.argv) > 1 else '/p5/v.txt'
a, b = DFS(), DFS()
a.login('andres', 'clave123')
b.login('andres', 'clave123')
w0 = b.open(ruta, 'w', create=True)
w0.write(0, b'version-1')
w0.close()
lector = a.open(ruta, 'r')
print('lector abre la versión', lector.version, '(sin llenar caché)')
w = b.open(ruta, 'rw')
w.write(0, b'version-2')
print('escritor: write hecho, todavía sin close')
temporal = a.open(ruta, 'r')
assert temporal.read(0, 20) == b'version-1'
temporal.close()
print('escritor: close publica la versión', w.close())
assert lector.read(0, 20) == b'version-1'
lector.close()
nuevo = a.open(ruta, 'r')
assert nuevo.read(0, 20) == b'version-2'
nuevo.close()
print('OK: snapshots comprobados con aserciones y sin caché previa.')
