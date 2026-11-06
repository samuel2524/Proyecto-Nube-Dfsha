"""Regenera el informe de la versión v2 a partir de los resultados versionados en dfsha/resultados.

Las cifras de pruebas, caídas y rendimiento se leen de los registros de AWS; no se escriben a mano.
Ejecutar desde cualquier directorio: python informe/construir_informe.py
"""
import csv
import json
import shutil
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIG = HERE/'figuras'
FIG.mkdir(exist_ok=True)

REFERENCES = [
    '[1] S. Ghemawat, H. Gobioff y S.-T. Leung, "The Google file system," en Proc. 19th ACM Symp. '
    'Operating Systems Principles, 2003, pp. 29-43.',
    '[2] K. Shvachko, H. Kuang, S. Radia y R. Chansler, "The Hadoop distributed file system," en Proc. '
    'IEEE MSST, 2010, pp. 1-10.',
    '[3] etcd Authors, "etcd documentation," 2026. Disponible: https://etcd.io/docs/',
    '[4] A. Ospina Sanjuan, "gRPC: de la invocación local a los microservicios modernos," diapositivas de '
    'clase, Universidad Pontificia Bolivariana, 2026.',
    '[5] J. H. Howard et al., "Scale and performance in a distributed file system," ACM Trans. Computer '
    'Systems, vol. 6, no. 1, pp. 51-81, 1988.',
    '[6] M. Jones, J. Bradley y N. Sakimura, "JSON Web Token (JWT)," RFC 7519, IETF, 2015.',
    '[7] E. Rescorla, "The Transport Layer Security (TLS) protocol version 1.3," RFC 8446, IETF, 2018.',
    '[8] M. Dworkin, "Recommendation for block cipher modes of operation: Galois/Counter Mode (GCM) and '
    'GMAC," NIST SP 800-38D, 2007.',
    '[9] D. Ongaro y J. Ousterhout, "In search of an understandable consensus algorithm," en Proc. USENIX '
    'ATC, 2014, pp. 305-319.',
    '[10] E. Brewer, "CAP twelve years later: How the \'rules\' have changed," Computer, vol. 45, no. 2, '
    'pp. 23-29, 2012.',
    '[11] M. van Steen y A. S. Tanenbaum, Distributed Systems, 4.ª ed. distributed-systems.net, 2023.',
]


def font(size, bold=False):
    windows = Path('C:/Windows/Fonts')/('timesbd.ttf' if bold else 'times.ttf')
    linux = Path('/usr/share/fonts/truetype/dejavu')/('DejaVuSerif-Bold.ttf' if bold else 'DejaVuSerif.ttf')
    return ImageFont.truetype(str(windows if windows.exists() else linux), size * 2)


class Drawing:
    def __init__(self, width, height):
        self.image = Image.new('RGB', (width * 2, height * 2), 'white')
        self.draw = ImageDraw.Draw(self.image)
    def text(self, x, y, value, size=15, bold=False):
        self.draw.multiline_text((x*2, y*2), value, font=font(size, bold), fill='#000000', spacing=8)
    def box(self, x, y, w, h, value, fill='#f2f2f2'):
        self.draw.rounded_rectangle((x*2,y*2,(x+w)*2,(y+h)*2), radius=18,
                                   fill=fill, outline='#000000', width=3)
        self.text(x+12,y+12,value,14)
    def line(self, points, color='#000000'):
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
    drawing.box(20,175,210,140,'Cliente CLI / API\nPartición y cifrado\nSnapshot renovable','#f2f2f2')
    drawing.box(285,105,440,190,'Plano de control · APIs equivalentes\n\nC1 y C2: permisos, planes y locks\nRecibos firmados y publicación CAS\nSesiones de lectura/escritura')
    drawing.box(795,115,280,160,'etcd × 3 · Raft\nNamespace y sesiones\nManifiestos y resultados\nVolúmenes persistentes')
    drawing.line([(230,210),(285,210)])
    drawing.text(236,178,'HTTPS',11)
    drawing.line([(725,200),(795,200)])
    drawing.text(730,145,'mTLS',12)
    for i,x in enumerate((285,485,685,885),1):
        drawing.box(x,410,185,115,f'D{i} · bloques create-once\nHash + AES-GCM\nRecibo propio firmado','#f2f2f2')
    drawing.text(895,380,'nodo adicional del clúster',11)
    drawing.line([(125,315),(125,465),(285,465)],'#000000')
    drawing.text(20,350,'gRPC / mTLS\nCapacidad por bloque',13)
    drawing.line([(500,410),(500,295)])
    drawing.text(515,330,'Heartbeat firmado\nHTTPS: nodo a control',13)
    drawing.line([(470,490),(485,490)],'#000000')
    drawing.line([(670,490),(685,490)],'#000000')
    drawing.text(300,550,'S2S desde bloque validado · R=3 objetivo · W=2 recibos distintos\nGC conserva lectores/planes y espera gracia + vencimiento de capacidades.',14)
    drawing.save('componentes_revision.png')
    drawing = Drawing(1100,650)
    drawing.text(25,20,'DFSha · despliegue en AWS Academy',24,True)
    drawing.text(25,62,'Cuatro VMs EC2 t3.small (us-east-1a) · red de servicios privada · Docker por rol.',14)
    for i,x in enumerate((30,300,570,840),1):
        roles = ('etcd1 + meta1 + dn1','etcd2 + meta2 + dn2','etcd3 + dn3','dn4 + cliente/bastión')[i-1]
        drawing.box(x,160,230,310,f'VM {i}\n\n{roles}\n\nDocker: roles separados\nVolúmenes propios\nIdentidades por rol\nSin CA privada\n\nNombres: extra_hosts')
    drawing.box(80,505,940,95,'Red privada: etcd mTLS entre votantes/coordinadores · datos gRPC/mTLS · control HTTPS\nAdministración por SSH restringido. No se copia la llave administrativa al bastión.','#f2f2f2')
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
    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)
    def times(style, bold):
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        style.font.bold = bold
        style.font.italic = False
        style.font.color.rgb = RGBColor(0, 0, 0)
        fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        for attribute in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
            fonts.set(qn(attribute), 'Times New Roman')
        for attribute in ('w:asciiTheme', 'w:hAnsiTheme', 'w:cstheme', 'w:eastAsiaTheme'):
            fonts.attrib.pop(qn(attribute), None)
    times(doc.styles['Normal'], False)
    doc.styles['Normal'].paragraph_format.space_after = Pt(4)
    for style in ('Title', 'Heading 1', 'Heading 2'):
        times(doc.styles[style], True)
        doc.styles[style].paragraph_format.space_before = Pt(10)
        doc.styles[style].paragraph_format.space_after = Pt(4)
    def p(text):
        doc.add_paragraph(text)
    def h(text):
        doc.add_heading(text, level=1)
    def table(headers, rows):
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = 'Table Grid'
        t.autofit = False
        for c,v in zip(t.rows[0].cells,headers):
            c.text=v
        for row in rows:
            for c,v in zip(t.add_row().cells,row):
                c.text=str(v)
        for row in t.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_after = Pt(1)
                    for run in paragraph.runs:
                        run.font.size = Pt(12)
        if len(headers) == 2:
            for row in t.rows:
                row.cells[0].width = Inches(1.8)
                row.cells[1].width = Inches(4.9)
        for index, row in enumerate(t.rows):
            properties = row._tr.get_or_add_trPr()
            properties.append(OxmlElement('w:cantSplit'))
            if index == 0:
                properties.append(OxmlElement('w:tblHeader'))
    doc.add_heading('DFSha — Fase II',1)
    p('Revisión técnica del prototipo grupal · opción 1: cliente/servidor S2S')
    p('Andrés Felipe Martínez Velasquez · Juan José García Duque · Samuel Parra Cadavid')
    p('Universidad Pontificia Bolivariana · Profesor Álvaro Ospina Sanjuan')
    p('Estado: desplegado y validado en AWS Academy (cuatro VMs EC2). Evidencias en dfsha/resultados.')
    h('1. Alcance y estado verificable')
    p('Esta versión corrige el prototipo tras contrastarlo con la consigna y los tres diseños individuales. '
      'Se desplegó en cuatro VMs EC2 de AWS Academy con deploy/desplegar.py y allí se ejecutaron la suite de '
      'regresión, las caídas de servicios y el benchmark. Las capturas son de la terminal del equipo conectada '
      'por SSH al bastión. Las mediciones de la versión anterior se conservan como históricas.')
    h('2. Comparación y elección arquitectónica')
    table(['Criterio','Andrés','García','Samuel','Revisión'],[
        ['Control','2 APIs + etcd/Raft','PostgreSQL activo/pasivo','3 coordinadores + etcd','2 APIs + 3 etcd'],
        ['Bloque','8 MiB','4 MiB','4 MiB','8 MiB; comparación pendiente'],
        ['Réplicas','R3/W2','R2/W2','R3/W2','R3/W2, recibos verificados'],
        ['Concurrencia','Por bloque','Bloque + versión esperada','Por archivo + CAS','rw por bloque; w/a exclusivos'],
        ['Lectores','Snapshot; gracia','Manifiesto estable','Lectores renovables','Lease + retención por referencia'],
        ['Seguridad','Argon2id/RS256/mTLS','Argon2id/RS256/mTLS','Argon2id/TLS/mTLS','scrypt/EdDSA/identidades separadas']])
    p('La topología de Andrés es una base defendible por disponibilidad del catálogo y paralelismo. Se incorporan la validación de base de García y los leases lectores de Samuel. S2S y snapshots son decisiones coincidentes: no se atribuyen exclusivamente a una persona. El detalle con las secciones originales de cada propuesta está en COMPARACION_PROPUESTAS.md.')
    h('3. Decisiones y límites del contrato')
    p('Se mantiene REST/HTTPS para control, gRPC/mTLS para datos, tres etcd [3], dos APIs equivalentes y cuatro nodos, con separación de planos inspirada en GFS/HDFS [1], [2]. Los bloques miden hasta 8 MiB; el objetivo es R=3 y la preparación exige dos recibos de nodos distintos. La réplica S2S se hace desde un bloque validado, secuencialmente: no se presenta como pipeline solapado. ADR_REVISION.md documenta los cambios y sus costos.')
    p('La publicación usa un epoch global y CAS de sesión/referencias. Esto prioriza corrección, pero introduce contención de metadatos y no promete escalabilidad ilimitada. MAX_BLOCKS=8192; lock y rename atómicos hasta 48 bloques/entradas. El catálogo v2 no migra automáticamente el formato previo.')
    h('4. Componentes y despliegue')
    doc.add_picture(str(FIG/'componentes_revision.png'),width=Inches(5.3))
    p('Figura 1. Componentes corregidos: nodos sin acceso al catálogo, recibos firmados y lectores con lease.')
    doc.add_picture(str(FIG/'despliegue_revision.png'),width=Inches(5.3))
    p('Figura 2. Despliegue en AWS Academy: tres etcd, dos APIs y cuatro nodos de datos en cuatro VMs.')
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
    p('RF1 se cubre con login y el árbol por usuario; RF2 con put/get de archivo completo; RF3 con '
      'open/close/read/write/lock y la semántica declarada: create-once por bloque, rw con lock, w/a '
      'exclusivos y append sin pasar EOF.')
    p('API: /v1/auth/login; /v1/fs/ls,mkdir,rmdir,rm,rename; /v1/files/open; /v1/files/{fd}/keepalive,manifest,lock,unlock,blocks,close,abort,status. Las rutas /blocks/{bid}/authorize y /prepared separan autorización y confirmación. El contrato gRPC [4] está en proto/dfsha.proto.')
    p('Ejemplo: POST /v1/files/{fd}/blocks con {"index":0,"request_id":"op-b0"}; authorize fija hash y tamaño; WriteBlock devuelve recibos firmados; prepared recibe {"receipts":["firma-dn1","firma-dn2"]}. Un recibo duplicado/falso recibe 409 BAD_RECEIPT. close con el mismo fd/cuerpo devuelve la versión publicada, sin publicar otra.')
    h('6. Consistencia, concurrencia y fallos')
    p('rw comprueba el ID base de cada bloque al adquirir el lock. Si otro escritor cambió ese bloque desde open, responde 409 y exige reabrir/releer; bloques distintos pueden avanzar en paralelo. w y a son exclusivos respecto a otros escritores. rm/rename rechazan escritores activos con 423. La expiración de la sesión elimina sus locks; el commit compara la revisión de sesión y no puede publicar con una sesión vencida.')
    p('Un lector abierto conserva snapshot con lease renovable [11]; la visibilidad entre aperturas sigue el modelo close-to-open [5]. Al cerrar o vencer, sus referencias dejan de proteger bloques obsoletos. La gracia no sustituye el seguimiento de lectores. El GC no elimina en el ciclo de marcado y espera el horizonte de capacidades para no permitir un replay tras borrar el ID.')
    p('Heartbeats firmados cada 3 s: sospechoso a 10 s y caído a 30 s. El monitor renueva liderazgo en paralelo, verifica que siga vigente y replica usando el hash autorizado del catálogo. Una fuente corrupta no se registra como reparada. Raft [9] mantiene el catálogo; con pérdida de cuórum, las operaciones fallan cerrado, priorizando consistencia [10]. No se promete disponibilidad ante cualquier combinación de fallos.')
    h('7. Seguridad e integridad')
    p('Cada servicio tiene certificado propio. La CA de etcd solo habilita miembros y coordinadores; nodos y cliente no reciben sus credenciales ni KEK. gRPC exige mTLS y capacidad. JWT y capacidades tienen firmantes separados, y cada nodo firma sus recibos. La KEK se carga solo en metadatos. El hash de contraseña usa scrypt con sal (N=32768,r=8,p=3). Estos cambios deben revisarse con el equipo y el profesor cuando corresponda.')
    p('AES-256-GCM [8] usa AAD=block_id; JWT [6] transporta identidad y capacidades, sobre canales TLS [7]. Cada bloque se valida por tamaño/hash; todas las versiones tienen hash canónico de manifiesto. put/w añade el SHA-256 plano global; rw/a no lo recalculan y lo declaran null. El hash de manifiesto no se presenta como hash de todo el archivo plano. Descargas usan temporal y solo reemplazan destino tras validar.')
    resultados = ROOT/'dfsha/resultados'
    n_fig = [2]
    def figura(nombre, titulo):
        if (FIG/nombre).exists():
            n_fig[0] += 1
            doc.add_picture(str(FIG/nombre), width=Inches(6.0))
            p(f'Figura {n_fig[0]}. {titulo}')
    h('8. Pruebas en AWS Academy')
    p('Las cuatro VMs EC2 t3.small corren Ubuntu 24.04 y Docker. deploy/desplegar.py entrega a cada VM solo '
      'los certificados de sus roles, construye la imagen y levanta los servicios con la red del host. La '
      'figura siguiente muestra los contenedores de cada VM, el clúster etcd con su líder y los cuatro nodos vivos.')
    figura('aws_despliegue.png', 'Contenedores por VM, estado de etcd y de los nodos de datos en AWS.')
    regresiones = [r for r in sorted(resultados.glob('revision-*/regression.json'))
                   if 'AWS' in json.loads(r.read_text(encoding='utf-8'))['environment'] and json.loads(r.read_text(encoding='utf-8'))['successful']]
    if regresiones:
        final = max(regresiones, key=lambda r: json.loads(r.read_text(encoding='utf-8'))['tests'])
        data = json.loads(final.read_text(encoding='utf-8'))
        p(f'La suite de regresión se ejecutó en el bastión contra el clúster real ({final.parent.name}): '
          f'{data["tests"]} casos, {data["failures"]} fallos, {data["errors"]} errores y {data["skipped"]} omitidos. '
          'Cubre recibos falsos y duplicados, contenido inmutable, snapshot sin caché, base vieja, bloques '
          'distintos en paralelo, truncado vacío, rm/rename con escritores activos, idempotencia del cierre, '
          'rangos inválidos, aislamiento por usuario, mTLS sin certificado, clientes concurrentes y la '
          'transferencia de 129 bloques (1032 MiB) con hash coincidente.')
    figura('aws_regresion.png', 'Suite de regresión ejecutada en el bastión de AWS.')
    p('RF1, RF2 y RF3 desde la CLI: carga y descarga de un archivo grande con el mismo SHA-256, bloques repartidos '
      'entre los cuatro nodos, y write/append/cat con la semántica declarada.')
    figura('aws_rf.png', 'RF1-RF3 en AWS: put, stat, get, write, append y cat.')
    p('Concurrencia: el segundo escritor del mismo bloque recibe 423. Si espera el lock (--esperar), recibe 409 '
      'VERSION_CONFLICT porque el bloque cambió desde su open y debe reabrir: nunca sobrescribe sobre una base '
      'vieja. Dos escritores en bloques distintos del mismo archivo publican los dos cambios.')
    figura('aws_concurrencia.png', 'Dos clientes sobre el mismo bloque y sobre bloques distintos.')
    caidas = sorted(resultados.glob('revision-failures-aws-*/run.json'))
    if caidas:
        registro = json.loads(caidas[-1].read_text(encoding='utf-8'))['records']
        pasos = [r for r in registro if not r['polling'] or r['returncode'] == 0]
        p(f'scripts/verify_aws.py detuvo contenedores reales por SSH y comprobó cada efecto con sondas desde el '
          f'bastión ({caidas[-1].parent.name}, {len(registro)} pasos registrados, todo restaurado al final):')
        filas = [[f'{r["vm"]}: {r["step"]}', (r['stdout'][:70] or 'OK') if r['returncode'] == 0 else 'falló']
                 for r in pasos]
        table(['Paso', 'Resultado'], filas)
        espera = sum(r['seconds'] for r in registro if r['polling'] and r['returncode'] != 0)
        p(f'Con dn1 caído el archivo se leyó y se escribió sin errores, y el monitor rehízo tres copias sin dn1 '
          f'(la sonda esperó {espera:.0f} s de reparación). Con meta1 caído el cliente usó meta2. Con un miembro de '
          'etcd menos el catálogo siguió operando; con dos, las operaciones fallaron cerrado con 503, priorizando '
          'consistencia [10].')
    figura('aws_caidas.png', 'Registro de las caídas ejecutadas en AWS.')
    p('Seguridad: sin sesión o con clave incorrecta la respuesta es 401; otro usuario recibe 404 y sin rol admin '
      '403; un nodo rechaza tokens de bloque ausentes o alterados y conexiones sin TLS; openssl confirma TLS 1.3.')
    figura('aws_seguridad.png', 'Accesos denegados, token alterado y TLS 1.3 en AWS.')
    h('9. Métricas en AWS')
    corridas = []
    for run in sorted(resultados.glob('revision-bench-*/run.json')):
        meta = json.loads(run.read_text(encoding='utf-8'))
        if meta['environment'] == 'aws' and meta['status'] == 'complete':
            corridas.append(run.parent)
    if corridas:
        bench = corridas[-1]
        filas = list(csv.DictReader((bench/'summary.csv').open(encoding='utf-8')))
        def v(exp, cond, op):
            return next(float(r['MiB_s']) for r in filas
                        if r['experiment'] == exp and r['condition'] == cond and r['operation'] == op)
        p(f'Corrida {bench.name}: cinco repeticiones por condición desde el bastión, con muestras crudas, resumen, '
          'parámetros y hash del código. El throughput incluye cifrado, hashes, recibos firmados y publicación.')
        table(['Exp.', 'Condición', 'Op.', 'MiB', 'Media (s)', 'p95 (s)', 'MiB/s'],
              [[r['experiment'], r['condition'], r['operation'], r['MiB'], f'{float(r["mean_s"]):.2f}',
                f'{float(r["p95_s"]):.2f}', f'{float(r["MiB_s"]):.1f}'] for r in filas])
        r2, r3 = v('E2', 'R=2;W=2', 'put'), v('E2', 'R=3;W=2', 'put')
        p(f'E1: con 500 MiB la escritura llega a {v("E1", "R=3;bytes=500", "put"):.1f} MiB/s y la lectura a '
          f'{v("E1", "R=3;bytes=500", "get"):.1f} MiB/s; la lectura es más rápida porque no replica y descarga '
          f'de réplicas distintas en paralelo. E2: R=2 sube a {r2:.1f} MiB/s y R=3 a {r3:.1f} MiB/s; la tercera '
          'copia cuesta poco porque la hace el nodo por S2S después de validar el bloque, no el cliente. '
          f'E3: el throughput agregado de escritura pasa de {v("E3", "clients=1", "put"):.1f} MiB/s con un cliente '
          f'a {v("E3", "clients=8", "put"):.1f} MiB/s con ocho, y el de lectura de {v("E3", "clients=1", "get"):.1f} '
          f'a {v("E3", "clients=8", "get"):.1f} MiB/s. La lectura escala hasta saturar el bastión (2 vCPU, que '
          'también es nodo de datos); la escritura agregada baja con más clientes porque cada reserva, '
          'autorización y publicación compite por el epoch global del catálogo (R06): los conflictos se '
          'reintentan con espera aleatoria y se pierde tiempo en ellos. Es el costo medido de priorizar la '
          'corrección del catálogo; repartir el epoch por inodo es la mejora natural. La primera corrida en AWS '
          'falló justamente por ese motivo (409 RETRY sin reintento en el cliente) y se conserva en resultados. '
          'Con cinco muestras el p95 es el máximo observado.')
    figura('aws_benchmark.png', 'Resumen del benchmark en AWS consultado en el bastión.')
    h('10. Escenarios obligatorios de razonamiento')
    table(['Escenario','Respuesta y comprobación'],[
        ['Mismo bloque simultáneo','Un lock excluye al segundo escritor (423). Si abrió sobre base anterior, se rechaza con 409 al adquirir. Se preserva contenido; se probó la base vieja y bloques distintos.'],
        ['Réplica desconectada','La publicación exige dos recibos distintos, firmados y persistentes. Una sola copia no basta. El monitor repara con hash autorizado; los lectores usan réplicas de su snapshot.'],
        ['Caída a mitad de bloque','El temporal no obtiene recibo ni se publica. La regresión envía un stream incompleto, comprueba DATA_LOSS y rechazo del commit. Reintento usa un plan nuevo.'],
        ['Ubicación desconocida','El cliente usa nombres lógicos de coordinadores; open/manifest devuelve destinos y capacidades. El refresco conserva el mismo snapshot. extra_hosts se configura dentro de cada contenedor.']])
    h('11. Entrega, contribuciones y defensa')
    p('Cada integrante registra sus aportes mediante commits en el repositorio del equipo. El guion del video de '
      '10–15 minutos y la preparación de la defensa están en informe/GUION_VIDEO.md e informe/GUION_DEFENSA.md. '
      'Las simplificaciones declaradas en ADR_REVISION.md se someten a aprobación del profesor.')
    h('Referencias y fuentes de comparación')
    p('Los documentos individuales de la Fase I son las fuentes de la comparación.')
    for reference in REFERENCES:
        paragraph = doc.add_paragraph(reference)
        paragraph.paragraph_format.space_after = Pt(1)
        paragraph.runs[0].font.size = Pt(12)
    target=ROOT/'DFSha_FaseII_Informe_Grupal.docx'
    doc.save(target)
    print('Informe regenerado:',target)
    print('Exportar a PDF desde Word.')


if __name__ == '__main__':
    build()
