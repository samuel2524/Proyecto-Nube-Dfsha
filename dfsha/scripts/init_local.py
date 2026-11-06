"""Inicialización explícita: genera secretos locales sin reemplazar los existentes."""
import secrets
from pathlib import Path

from gen_certs import generate

if not Path('certs').exists():
    generate('certs')
env = Path('.env')
if not env.exists():
    env.write_text('KEK=' + secrets.token_hex(32) + '\n'
                   'USERS=andres:clave123:user,laura:clave123:user,admin:admin123:admin\n',
                   encoding='utf-8')
    env.chmod(0o600)
    print('.env generado para laboratorio; cambiar contraseñas para el despliegue.')
else:
    print('.env conservado sin modificaciones.')
