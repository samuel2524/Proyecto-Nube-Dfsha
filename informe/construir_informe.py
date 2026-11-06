"""Regenera informe coherente con v2; preserva los documentos previos en historico/.

No reutiliza estadísticas antiguas ni afirma que las correcciones se probaron en AWS.
Ejecutar desde cualquier directorio: python informe/construir_informe.py
"""
import json
import shutil
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIG = HERE/'figuras'
FIG.mkdir(exist_ok=True)


def font(size, bold=False):
    windows = Path('C:/Windows/Fonts')/('calibrib.ttf' if bold else 'calibri.ttf')
    linux = Path('/usr/share/fonts/truetype/dejavu')/('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')
    return ImageFont.truetype(str(windows if windows.exists() else linux), size * 2)


class Drawing:
    def __init__(self, width, height):
        self.image = Image.new('RGB', (width * 2, height * 2), 'white')
        self.draw = ImageDraw.Draw(self.image)
    def text(self, x, y, value, size=15, bold=False):
        self.draw.multiline_text((x*2, y*2), value, font=font(size, bold), fill='#18314b', spacing=8)
    def box(self, x, y, w, h, value, fill='#eaf2fb'):
        self.draw.rounded_rectangle((x*2,y*2,(x+w)*2,(y+h)*2), radius=18,
                                   fill=fill, outline='#406b92', width=3)
        self.text(x+12,y+12,value,14)
    def line(self, points, color='#406b92'):
        scaled = [(x*2,y*2) for x,y in points]
        self.draw.line(scaled, fill=color, width=4)
        x,y = scaled[-1]
        px,py = scaled[-2]
        if abs(x-px) >= abs(y-py):
            sign = 1 if x>px else -1
            triangle = [(x,y),(x-sign*16,y-8),(x-sign*16,y+8)]
        else:
            sign = 1 if y>py else -1
            triangle = [(x,y),(x-8,y-sign*16),(x+8,y-sign*16)]
        self.draw.polygon(triangle, fill=color)
    def save(self, name):
        self.image.save(FIG/name)


def figures():
    drawing = Drawing(1100,610)
    drawing.text(25,20,'DFSha · componentes de la revisión',25,True)
    drawing.box(20,175,210,140,'Cliente CLI / API\nPartición y cifrado\nSnapshot renovable','#fff2d6')
    drawing.box(285,105,440,190,'Plano de control · APIs equivalentes\n\nC1 y C2: permisos, planes y locks\nRecibos firmados y publicación CAS\nSesiones de lectura/escritura')
    drawing.box(795,115,280,160,'etcd × 3 · Raft\nNamespace y sesiones\nManifiestos y resultados\nVolúmenes persistentes')
    drawing.line([(230,210),(285,210)])
    drawing.text(228,140,'HTTPS\nPlanes/recibos',12)
    drawing.line([(725,200),(795,200)])
    drawing.text(730,145,'mTLS',12)
    for i,x in enumerate((285,485,685,885),1):
        drawing.box(x,410,185,115,f'D{i} · bloques create-once\nHash + AES-GCM\nRecibo propio firmado','#e8f6f0')
    drawing.line([(125,315),(125,465),(285,465)],'#218272')
    drawing.text(20,350,'gRPC / mTLS\nCapacidad por bloque',13)
    drawing.line([(500,410),(500,295)])
    drawing.text(515,330,'Heartbeat firmado\nHTTPS: nodo a control',13)
    drawing.line([(470,490),(485,490)],'#218272')
    drawing.line([(670,490),(685,490)],'#218272')
    drawing.text(300,550,'S2S desde bloque validado · R=3 objetivo · W=2 recibos distintos\nGC conserva lectores/planes y espera gracia + vencimiento de capacidades.',14)
    drawing.save('componentes_revision.png')
    drawing = Drawing(1100,650)
    drawing.text(25,20,'DFSha · despliegue previsto en AWS Academy',24,True)
    drawing.text(25,62,'Cuatro VMs Linux · red de servicios privada · esta revisión requiere repetir la validación AWS.',14)
    for i,x in enumerate((30,300,570,840),1):
        roles = ('etcd1 + meta1 + dn1','etcd2 + meta2 + dn2','etcd3 + dn3','dn4 + cliente/bastión')[i-1]
        drawing.box(x,160,230,310,f'VM {i}\n\n{roles}\n\nDocker: roles separados\nVolúmenes propios\nIdentidades por rol\nSin CA privada\n\nNombres: extra_hosts')
    drawing.box(80,505,940,95,'Red privada: etcd mTLS entre votantes/coordinadores · datos gRPC/mTLS · control HTTPS\nAdministración por SSH restringido. No se copia la llave administrativa al bastión.','#e8f6f0')
    for x in (145,415,685,955):
        drawing.line([(x,470),(x,505)])
    drawing.text(30,110,'Votantes Raft: 3, cuórum 2/3. Réplicas de un bloque en VMs distintas.',16,True)
    drawing.save('despliegue_revision.png')


def build():
    figures()
    historical = HERE/'historico'
    historical.mkdir(exist_ok=True)
    for suffix in ('docx','pdf'):
        previous = ROOT/f'DFSha_FaseII_Informe_Grupal.{suffix}'
        if previous.exists() and not (historical/previous.name).exists():
            shutil.copy2(previous, historical/previous.name)
    doc = Document()
    for style in ('Normal',):
        doc.styles[style].font.name = 'Calibri'
        doc.styles[style].font.size = Pt(11)
        doc.styles[style].paragraph_format.space_after = Pt(4)
    for style in ('Title','Heading 1','Heading 2'):
        doc.styles[style].font.name = 'Calibri Light'
        doc.styles[style].font.color.rgb = RGBColor(0,0,0)
        doc.styles[style].font.bold = True
    def p(text):
        doc.add_paragraph(text)
    def h(text):
        doc.add_heading(text, level=1)
    def table(headers, rows):
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = 'Table Grid'
        for c,v in zip(t.rows[0].cells,headers):
            c.text=v
        for row in rows:
            for c,v in zip(t.add_row().cells,row):
                c.text=str(v)
    doc.add_heading('DFSha — Fase II',0)
    p('Revisión técnica del prototipo grupal · opción 1: cliente/servidor S2S')
    p('Andrés Felipe Martínez Velasquez · Juan José García Duque · Samuel Parra Cadavid')
    p('Universidad Pontificia Bolivariana · Profesor Álvaro Ospina Sanjuan')
    p('Estado: correcciones y validación local. Pendiente ratificación del equipo, aprobación de simplificaciones cuando aplique y repetición de evidencias en AWS Academy.')
    h('1. Alcance y estado verificable')
    p('Esta revisión corrige el prototipo tras contrastarlo con la consigna y los tres diseños individuales. Las pruebas de esta versión se hicieron en Docker local; la validación en AWS Academy está pendiente. Las capturas y mediciones de la versión anterior se conservan como históricas, con sus anomalías señaladas.')
    h('2. Comparación y elección arquitectónica')
    table(['Criterio','Andrés','García','Samuel','Revisión'],[
        ['Control','2 APIs + etcd/Raft','PostgreSQL activo/pasivo','3 coordinadores + etcd','2 APIs + 3 etcd'],
        ['Bloque','8 MiB','4 MiB','4 MiB','8 MiB; comparación pendiente'],
        ['Réplicas','R3/W2','R2/W2','R3/W2','R3/W2, recibos verificados'],
        ['Concurrencia','Por bloque','Bloque + versión esperada','Por archivo + CAS','rw por bloque; w/a exclusivos'],
        ['Lectores','Snapshot; gracia','Manifiesto estable','Lectores renovables','Lease + retención por referencia'],
        ['Seguridad','Argon2id/RS256/mTLS','Argon2id/RS256/mTLS','Argon2id/TLS/mTLS','scrypt/EdDSA/identidades separadas']])
    p('La topología de Andrés es una base defendible por disponibilidad del catálogo y paralelismo. Se incorporan la validación de base de García y los leases lectores de Samuel. S2S y snapshots son decisiones coincidentes: no se atribuyen exclusivamente a una persona. El detalle con secciones originales y acuerdo pendiente está en COMPARACION_PROPUESTAS.md.')
    h('3. Decisiones y límites del contrato')
    p('Se mantiene REST/HTTPS para control, gRPC/mTLS para datos, tres etcd [3], dos APIs equivalentes y cuatro nodos, con separación de planos inspirada en GFS/HDFS [1], [2]. Los bloques miden hasta 8 MiB; el objetivo es R=3 y la preparación exige dos recibos de nodos distintos. La réplica S2S se hace desde un bloque validado, secuencialmente: no se presenta como pipeline solapado. ADR_REVISION.md documenta los cambios y sus costos.')
    p('La publicación usa un epoch global y CAS de sesión/referencias. Esto prioriza corrección, pero introduce contención de metadatos y no promete escalabilidad ilimitada. MAX_BLOCKS=8192; lock y rename atómicos hasta 48 bloques/entradas. El catálogo v2 no migra automáticamente el formato previo.')
    h('4. Componentes y despliegue')
    doc.add_picture(str(FIG/'componentes_revision.png'),width=Inches(6))
    p('Figura 1. Componentes corregidos: nodos sin acceso al catálogo, recibos firmados y lectores con lease.')
    doc.add_picture(str(FIG/'despliegue_revision.png'),width=Inches(6))
    p('Figura 2. Despliegue previsto; la ejecución local no sustituye la demostración distribuida en AWS.')
    h('5. Protocolos, datos y algoritmos')
    table(['Estado/operación','Contrato revisado'],[
        ['open','Valida propietario; fija snapshot; crea sesión con lease de 60 s renovable.'],
        ['Reserva','Asigna ID nuevo y destinos; registra plan por bloque.'],
        ['authorize','Fija SHA-256 y tamaño cifrado; emite capacidad ligada a operación y nodos.'],
        ['WriteBlock','Consume stream incremental, valida, fsync, create-once y firma recibo por nodo.'],
        ['prepared','Verifica firmas, nodos distintos y contenido del plan; persiste ficha preparada.'],
        ['close','Valida planes/locks, tamaños y CAS; publica versión y resultado idempotente en txn acotada.'],
        ['read','Lee snapshot; refresca ubicaciones/capacidades sin cambiar versión; valida hashes y GCM.'],
        ['GC','Retiene referencias actuales, lectores y planes; marca, espera y valida antes del borrado.']])
    p('API: /v1/auth/login; /v1/fs/ls,mkdir,rmdir,rm,rename; /v1/files/open; /v1/files/{fd}/keepalive,manifest,lock,unlock,blocks,close,abort,status. Las rutas /blocks/{bid}/authorize y /prepared separan autorización y confirmación. El contrato gRPC está en proto/dfsha.proto.')
    p('Ejemplo: POST /v1/files/{fd}/blocks con {"index":0,"request_id":"op-b0"}; authorize fija hash y tamaño; WriteBlock devuelve recibos firmados; prepared recibe {"receipts":["firma-dn1","firma-dn2"]}. Un recibo duplicado/falso recibe 409 BAD_RECEIPT. close con el mismo fd/cuerpo devuelve la versión publicada, sin publicar otra.')
    h('6. Consistencia, concurrencia y fallos')
    p('rw comprueba el ID base de cada bloque al adquirir el lock. Si otro escritor cambió ese bloque desde open, responde 409 y exige reabrir/releer; bloques distintos pueden avanzar en paralelo. w y a son exclusivos respecto a otros escritores. rm/rename rechazan escritores activos con 423. La expiración de la sesión elimina sus locks; el commit compara la revisión de sesión y no puede publicar con una sesión vencida.')
    p('Un lector abierto conserva snapshot con lease renovable; la visibilidad entre aperturas sigue el modelo close-to-open [5]. Al cerrar o vencer, sus referencias dejan de proteger bloques obsoletos. La gracia no sustituye el seguimiento de lectores. El GC no elimina en el ciclo de marcado y espera el horizonte de capacidades para no permitir un replay tras borrar el ID.')
    p('Heartbeats firmados cada 3 s: sospechoso a 10 s y caído a 30 s. El monitor renueva liderazgo en paralelo, verifica que siga vigente y replica usando el hash autorizado del catálogo. Una fuente corrupta no se registra como reparada. Raft [9] mantiene el catálogo; con pérdida de cuórum, las operaciones fallan cerrado, priorizando consistencia [10]. No se promete disponibilidad ante cualquier combinación de fallos.')
    h('7. Seguridad e integridad')
    p('Cada servicio tiene certificado propio. La CA de etcd solo habilita miembros y coordinadores; nodos y cliente no reciben sus credenciales ni KEK. gRPC exige mTLS y capacidad. JWT y capacidades tienen firmantes separados, y cada nodo firma sus recibos. La KEK se carga solo en metadatos. El hash de contraseña usa scrypt con sal (N=32768,r=8,p=3). Estos cambios deben revisarse con el equipo y el profesor cuando corresponda.')
    p('AES-256-GCM [8] usa AAD=block_id; JWT [6] transporta identidad y capacidades, sobre canales TLS [7]. Cada bloque se valida por tamaño/hash; todas las versiones tienen hash canónico de manifiesto. put/w añade el SHA-256 plano global; rw/a no lo recalculan y lo declaran null. El hash de manifiesto no se presenta como hash de todo el archivo plano. Descargas usan temporal y solo reemplazan destino tras validar.')
    h('8. Pruebas ejecutadas y evidencia pendiente')
    runs = sorted((ROOT/'dfsha/resultados').glob('revision-*/regression.json'))
    for run in runs:
        data=json.loads(run.read_text())
        p(f'{run.parent.name}: {data["tests"]} casos; fallos={data["failures"]}, errores={data["errors"]}, omitidos={data["skipped"]}. Estado satisfactorio={data["successful"]}. Los runs fallidos se conservan, no se ocultan.')
    p('Las pruebas verifican recibos falsos/duplicados, contenido inmutable, snapshot sin caché, base vieja, bloques distintos, truncado vacío, rm/rename, idempotencia, rangos, aislamiento y transferencia de 129 bloques (1032 MiB). Hay pruebas de componente para GC, reparación y tamaño constante de txn. El registro de cambios identifica qué comandos y runs se ejecutaron realmente.')
    p('scripts/verify_local.py detiene y restaura servicios del proyecto de laboratorio, verifica lectura/escritura con nodo caído, reparación, failover de API/etcd y rechazo por pérdida de cuórum. Son contenedores locales, no caídas de VMs AWS. Las pruebas de VM completa, red privada, recuperación y mediciones finales deben repetirse allí.')
    h('9. Métricas reproducibles')
    p('Cada benchmark nuevo guarda samples.csv, summary.csv y run.json con entorno, timestamp, parámetros y hash del código. p50/p95 y desviación se reconstruyen desde muestras. R=2 frente a R=3 conserva W=2. Con cinco muestras, el p95 de rango cercano es el máximo; se recomienda ampliar la muestra para colas. No se usa bench.csv antiguo por su incompatibilidad media/p95.')
    p('Pendiente en AWS: 10/100/500 MiB y borde 1 GiB, concurrencia, comparación 3/4 nodos, 4/8 MiB en clústeres separados, disponibilidad y tiempo de reparación, CPU/memoria/disco/NIC. No se atribuye un cuello de botella a CPU/red sin mediciones específicas.')
    h('10. Escenarios obligatorios de razonamiento')
    table(['Escenario','Respuesta y comprobación'],[
        ['Mismo bloque simultáneo','Un lock excluye al segundo escritor (423). Si abrió sobre base anterior, se rechaza con 409 al adquirir. Se preserva contenido; se probó la base vieja y bloques distintos.'],
        ['Réplica desconectada','La publicación exige dos recibos distintos, firmados y persistentes. Una sola copia no basta. El monitor repara con hash autorizado; los lectores usan réplicas de su snapshot.'],
        ['Caída a mitad de bloque','El temporal no obtiene recibo ni se publica. La regresión envía un stream incompleto, comprueba DATA_LOSS y rechazo del commit. Reintento usa un plan nuevo.'],
        ['Ubicación desconocida','El cliente usa nombres lógicos de coordinadores; open/manifest devuelve destinos y capacidades. El refresco conserva el mismo snapshot. extra_hosts se configura dentro de cada contenedor.']])
    h('11. Entrega, contribuciones y defensa')
    p('Cada integrante registra sus aportes mediante commits en el repositorio del equipo. Faltan la evidencia en AWS de esta versión, las aprobaciones aplicables y el video final de 10–15 minutos.')
    h('Referencias y fuentes de comparación')
    p('Se conservan las referencias del informe previo sin atribuirles resultados experimentales nuevos. Los documentos originales individuales son las fuentes de la comparación; las diapositivas deben estar disponibles para el equipo.')
    prior = historical/'DFSha_FaseII_Informe_Grupal.docx'
    if prior.exists():
        old=Document(prior)
        for paragraph in old.paragraphs:
            if paragraph.text.strip().startswith(tuple(f'[{i}]' for i in range(1,12))):
                p(paragraph.text)
    target=ROOT/'DFSha_FaseII_Informe_Grupal.docx'
    doc.save(target)
    print('Informe regenerado:',target)
    print('Exportar a PDF desde Word; no usar un PDF histórico como si fuera esta revisión.')


if __name__ == '__main__':
    build()
