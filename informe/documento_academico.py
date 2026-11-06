"""Contenido y formato del informe de DFSha; métricas derivadas de registros."""
import csv
import datetime as dt
import json
import shutil
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIG = HERE / 'figuras'
RESULTS = ROOT / 'dfsha/resultados'
AUTHORS = ['Andrés Felipe Martínez Velasquez', 'Juan José García Duque', 'Samuel Parra Cadavid']
DELIVERY_DATE = '6 de noviembre de 2026'
REPOSITORY = 'https://github.com/samuel2524/Proyecto-Nube-Dfsha'
REFERENCES = [
    '[1] S. Ghemawat, H. Gobioff y S.-T. Leung, "The Google file system," en Proc. 19th ACM Symp. Operating Systems Principles, 2003, pp. 29-43.',
    '[2] K. Shvachko, H. Kuang, S. Radia y R. Chansler, "The Hadoop distributed file system," en Proc. IEEE MSST, 2010, pp. 1-10.',
    '[3] etcd Authors, "etcd documentation," 2026. Disponible: https://etcd.io/docs/',
    '[4] A. Ospina Sanjuan, "gRPC: de la invocación local a los microservicios modernos," diapositivas de clase, Universidad Pontificia Bolivariana, 2026.',
    '[5] J. H. Howard et al., "Scale and performance in a distributed file system," ACM Trans. Computer Systems, vol. 6, no. 1, pp. 51-81, 1988.',
    '[6] M. Jones, J. Bradley y N. Sakimura, "JSON Web Token (JWT)," RFC 7519, IETF, 2015.',
    '[7] E. Rescorla, "The Transport Layer Security (TLS) protocol version 1.3," RFC 8446, IETF, 2018.',
    '[8] M. Dworkin, "Recommendation for block cipher modes of operation: Galois/Counter Mode (GCM) and GMAC," NIST SP 800-38D, 2007.',
    '[9] D. Ongaro y J. Ousterhout, "In search of an understandable consensus algorithm," en Proc. USENIX ATC, 2014, pp. 305-319.',
    '[10] E. Brewer, "CAP twelve years later: How the \'rules\' have changed," Computer, vol. 45, no. 2, pp. 23-29, 2012.',
    '[11] M. van Steen y A. S. Tanenbaum, Distributed Systems, 4.ª ed. distributed-systems.net, 2023.',
]


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def select_evidence():
    benchmarks = [(path, read_json(path)) for path in RESULTS.glob('revision-bench-*/run.json')]
    benchmarks = [(path, value) for path, value in benchmarks
                  if value.get('environment') == 'aws' and value.get('status') == 'complete']
    bench_path, bench = max(benchmarks, key=lambda item: item[1]['finished_utc'])
    regressions = [(path, read_json(path)) for path in RESULTS.glob('revision-*/regression.json')]
    regressions = [(path, value) for path, value in regressions if value.get('successful')
                   and 'AWS' in value.get('environment', '')
                   and value.get('source_sha256') == bench['source_sha256']]
    # Seleccionar por corrida/huella, nunca por el máximo número de pruebas.
    regression_path, regression = max(regressions, key=lambda item: item[0].parent.name)
    failures = [(path, read_json(path)) for path in RESULTS.glob('revision-failures-aws-*/run.json')]
    failure_path, failure = max(failures, key=lambda item: item[1]['records'][-1]['utc'])
    with (bench_path.parent / 'summary.csv').open(encoding='utf-8') as source:
        rows = list(csv.DictReader(source))
    return bench, regression, failure['records'], rows


def observed_recovery(records):
    stopped = next(row for row in records if row['vm'] == 'vm1' and row['step'] == 'detener dn')
    repaired = next(row for row in records if row['step'] == 'sonda repaired' and row['returncode'] == 0)
    start = dt.datetime.fromisoformat(stopped['utc'])
    end = dt.datetime.fromisoformat(repaired['utc'])
    elapsed = (end - start).total_seconds()
    if elapsed < 0:
        raise ValueError('Timestamps de reparación fuera de orden')
    return start, end, elapsed


def build():
    bench, regression, records, measurements = select_evidence()
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup = HERE / 'historico' / ('antes_edicion_academica_' + stamp)
    backup.mkdir(parents=True, exist_ok=False)
    for suffix in ('docx', 'pdf'):
        source = ROOT / f'DFSha_FaseII_Informe_Grupal.{suffix}'
        if source.exists():
            shutil.copy2(source, backup / source.name)

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Cm(2.54)
    section.header_distance = Cm(1.27)
    for style_name in ('Normal', 'Title', 'Heading 1', 'Heading 2', 'Heading 3'):
        style = doc.styles[style_name]
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.bold = style_name != 'Normal'
        style.font.italic = False
        fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
            fonts.set(qn(attr), 'Times New Roman')
        for attr in ('w:asciiTheme', 'w:hAnsiTheme', 'w:cstheme', 'w:eastAsiaTheme'):
            fonts.attrib.pop(qn(attr), None)
    normal = doc.styles['Normal'].paragraph_format
    normal.line_spacing, normal.space_after = 1.15, Pt(5)
    for style_name in ('Heading 1', 'Heading 2', 'Heading 3'):
        fmt = doc.styles[style_name].paragraph_format
        fmt.space_before, fmt.space_after = Pt(10), Pt(4)
        fmt.keep_with_next = True
    doc.styles['Heading 2'].font.underline = True

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    header._p.append(field)
    doc.core_properties.title = 'DFSha: diseño, implementación y validación de un sistema de archivos distribuido'
    doc.core_properties.author = '; '.join(AUTHORS)
    doc.core_properties.subject = 'Proyecto 1, Fase II, implementación y validación grupal'

    def p(text):
        return doc.add_paragraph(text)

    def heading(text, level=1):
        return doc.add_heading(text, level=level)

    def label(title, text):
        paragraph = doc.add_paragraph()
        run = paragraph.add_run(title + ' ')
        run.bold, run.underline = True, True
        paragraph.add_run(text)
        return paragraph

    def code(text):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(2)
        paragraph.paragraph_format.space_after = Pt(6)
        paragraph.paragraph_format.line_spacing = 1
        paragraph.paragraph_format.keep_together = True
        run = paragraph.add_run(text)
        run.font.name, run.font.size = 'Consolas', Pt(10)
        return paragraph

    table_number = 0
    def table(title, headers, rows, widths=None):
        nonlocal table_number
        table_number += 1
        caption = p(f'Tabla {table_number}. {title}')
        caption.runs[0].bold = True
        caption.paragraph_format.keep_with_next = True
        element = doc.add_table(rows=1, cols=len(headers))
        element.style = 'Table Grid'
        element.autofit = False
        if widths:
            for column, width in zip(element.columns, widths):
                column.width = Inches(width)
        for cell, value in zip(element.rows[0].cells, headers):
            cell.text = value
        for values in rows:
            for cell, value in zip(element.add_row().cells, values):
                cell.text = str(value)
        for index, row in enumerate(element.rows):
            props = row._tr.get_or_add_trPr()
            props.append(OxmlElement('w:cantSplit'))
            if index == 0:
                props.append(OxmlElement('w:tblHeader'))
            if widths:
                for cell, width in zip(row.cells, widths):
                    cell.width = Inches(width)
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_after = Pt(2)
                    paragraph.paragraph_format.line_spacing = 1
                    if len(element.rows) <= 6 and index < len(element.rows) - 1:
                        paragraph.paragraph_format.keep_with_next = True
                    for run in paragraph.runs:
                        run.font.name, run.font.size = 'Times New Roman', Pt(11)
                        run.bold = index == 0

    figure_number = 0
    def figure(filename, caption, width=6.3):
        nonlocal figure_number
        path = FIG / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        figure_number += 1
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.keep_with_next = True
        paragraph.add_run().add_picture(str(path), width=Inches(width))
        caption_paragraph = p(f'Figura {figure_number}. {caption}')
        caption_paragraph.paragraph_format.keep_together = True
        caption_paragraph.runs[0].italic = True

    # Portada APA 7 de estudiante: número superior derecho, título centrado en
    # negrita, autores/afiliación/curso/docente/fecha y espaciado doble.
    cover = [
        ('DFSha: sistema de archivos distribuido\nDiseño, implementación y validación grupal\nProyecto 1, Fase II', True),
        ('', False),
        *[(name, False) for name in AUTHORS],
        ('Universidad Pontificia Bolivariana', False),
        ('Arquitecturas de Nube y Sistemas Distribuidos', False),
        ('Álvaro Ospina Sanjuan', False),
        (DELIVERY_DATE, False),
    ]
    for index, (text, bold) in enumerate(cover):
        paragraph = p(text)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.line_spacing = 2
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.space_before = Pt(72) if index == 0 else Pt(0)
        for run in paragraph.runs:
            run.bold = bold
    doc.add_page_break()

    heading('1. Introducción y alcance')
    p('DFSha es un sistema de archivos distribuido cliente/servidor con comunicación entre servidores (S2S), '
      'correspondiente a la opción 1 del proyecto. Separa la coordinación de operaciones del almacenamiento de '
      'bloques, siguiendo principios utilizados en GFS y HDFS [1], [2]. El cliente administra archivos y '
      'directorios dentro del espacio privado de cada usuario, sin conocer su ubicación física.')
    p('Esta fase integra las tres propuestas individuales y presenta la arquitectura implementada, sus '
      'protocolos, las garantías de concurrencia y las pruebas aportadas por el equipo. El prototipo se '
      'desplegó en cuatro máquinas virtuales EC2 de AWS Academy. Allí se registraron pruebas funcionales, '
      'caídas de servicios y mediciones de rendimiento. Las pruebas de fallo detuvieron contenedores dentro '
      'de las máquinas; no simularon la pérdida completa de una instancia EC2 ni de su disco.')

    heading('2. Comparación de las propuestas individuales')
    table('Comparación y selección arquitectónica', ['Criterio', 'Andrés Martínez', 'Juan José García', 'Samuel Parra', 'Solución grupal'], [
        ['Control', 'Dos APIs y tres etcd/Raft', 'PostgreSQL con propuesta activo/pasivo', 'Tres coordinadores y tres etcd/Raft', 'Dos APIs equivalentes y tres etcd/Raft'],
        ['Bloque', '8 MiB', '4 MiB', '4 MiB', '8 MiB; último bloque menor'],
        ['Replicación', 'R=3, W=2; S2S', 'R=2; confirman ambas', 'R=3, W=2; S2S', 'R=3 objetivo; W=2 verificado'],
        ['Concurrencia', 'Lock por bloque y fencing', 'Lock por bloque y versión esperada', 'Lock por archivo y CAS', 'rw por bloque; w/a exclusivos'],
        ['Lectores', 'Versión fijada y gracia', 'Manifiesto estable', 'Sesiones renovables', 'Snapshot con lease y retención por referencias'],
        ['Seguridad', 'Argon2id, RS256 y mTLS', 'Argon2id, RS256 y mTLS', 'Argon2id, TLS/mTLS y AES-GCM', 'scrypt, firmas EdDSA, mTLS y AES-GCM'],
    ], [1.0, 1.3, 1.3, 1.3, 1.6])
    p('La topología de Andrés se adoptó como base porque especifica dos servicios de metadatos sin estado '
      'y un catálogo con consenso, sin depender de un controlador único. De García se incorpora la '
      'validación de la versión esperada del bloque; de Samuel, las sesiones lectoras renovables que '
      'permiten conservar versiones mientras se utilizan. La réplica S2S y la lectura por versión son '
      'decisiones coincidentes entre propuestas.')
    p('La solución PostgreSQL activo/pasivo de García es una alternativa válida, pero su propuesta dejaba '
      'el failover sujeto al tiempo disponible y contemplaba replicación asíncrona. Para el prototipo se '
      'prefirió el catálogo etcd/Raft con leases y transacciones [3]. El lock por archivo de Samuel se '
      'reservó para truncar o anexar; la modificación de bloques distintos conserva paralelismo. Se '
      'mantuvieron bloques de 8 MiB, aunque las pruebas disponibles no comparan todavía su rendimiento '
      'con 4 MiB y no permiten afirmar que sea el tamaño óptimo.')

    heading('3. Decisiones arquitectónicas y límites')
    table('Decisiones implementadas y sus consecuencias', ['Decisión', 'Justificación y compromiso'], [
        ['Separación de planos', 'Las APIs organizan permisos, rutas y versiones; los bytes viajan directamente entre cliente y nodos.'],
        ['Preparación con W=2', 'Se exigen recibos firmados de dos nodos distintos antes de publicar; una tercera réplica puede quedar pendiente.'],
        ['Bloques inmutables', 'Cada modificación crea un identificador nuevo. Un reintento idéntico es idempotente; no reemplaza contenido publicado.'],
        ['Locks y versión esperada', 'rw bloquea los bloques afectados y rechaza bases viejas. w y a requieren exclusión entre escritores del archivo.'],
        ['Snapshots renovables', 'Un lease mantiene las referencias de lectura; el GC no depende exclusivamente de un tiempo fijo de gracia.'],
        ['Commit acotado', 'Las fichas se preparan por bloque; la publicación compara sesión y epoch sin añadir una operación transaccional por bloque.'],
        ['Resultados idempotentes', 'Repetir el mismo cierre devuelve la versión ya publicada; otro cuerpo para la misma operación recibe conflicto.'],
        ['Identidades separadas', 'Firmantes de usuario, capacidades y recibos distintos; CA de catálogo aislada y KEK solo en coordinadores.'],
    ], [1.6, 4.9])
    p('El epoch global simplifica la coordinación de referencias y del namespace, pero introduce '
      'contención entre operaciones de metadatos. No se promete escalabilidad ilimitada. El límite '
      'configurado es 8192 bloques por archivo, equivalentes a 64 GiB con bloques de 8 MiB. Una '
      'adquisición atómica de lock admite hasta 48 bloques y un rename atómico, hasta 48 entradas. '
      'El formato de catálogo de esta revisión no migra automáticamente los datos de versiones previas.')
    p('La replicación S2S se realiza secuencialmente desde un bloque validado. El nodo receptor verifica '
      'el contenido, lo persiste y después lo transmite al siguiente destino. No se declara un pipeline '
      'solapado. Tampoco se presupone semántica POSIX completa, compartición entre usuarios o cuotas.')

    heading('4. Componentes, metadatos y despliegue')
    p('El plano de control tiene dos APIs FastAPI equivalentes. Ambas usan tres miembros etcd '
      'replicados mediante Raft [9], con cuórum de dos de tres. El catálogo conserva usuarios, rutas, '
      'inodos, versiones, sesiones, locks, planes de bloque, réplicas y resultados de operaciones. '
      'El plano de datos tiene cuatro nodos que almacenan bloques cifrados en volúmenes persistentes.')
    figure('componentes_revision.png', 'Componentes de DFSha: control separado de datos, snapshots y recibos verificados.', 6.3)
    table('Distribución de servicios en AWS Academy', ['Máquina', 'Servicios', 'Persistencia'], [
        ['VM1', 'etcd1, coordinador meta1 y nodo dn1', 'Volúmenes separados de catálogo y bloques'],
        ['VM2', 'etcd2, coordinador meta2 y nodo dn2', 'Volúmenes separados de catálogo y bloques'],
        ['VM3', 'etcd3 y nodo dn3', 'Volúmenes separados de catálogo y bloques'],
        ['VM4', 'Nodo dn4 y cliente/bastión', 'Volumen de bloques y espacio de trabajo del cliente'],
    ], [0.85, 2.5, 3.15])
    p('Las cuatro máquinas usan Ubuntu 24.04 y contenedores Docker con red del anfitrión. Los nombres '
      'de servicio se resuelven con entradas de hosts configuradas también dentro de cada contenedor; '
      'no se presenta este mecanismo como un DNS con comprobaciones de salud. El cliente recibe las '
      'ubicaciones actuales de sus bloques en el manifiesto. Cada réplica de un bloque reside en una '
      'máquina distinta, al igual que los tres votantes de etcd.')
    figure('despliegue_revision.png', 'Despliegue de tres miembros etcd, dos coordinadores y cuatro nodos en cuatro VMs EC2.', 6.3)

    heading('5. Requisitos funcionales, protocolos y APIs')
    heading('5.1. Operaciones del servicio', 2)
    label('RF1. Gestión jerárquica.', 'ls lista entradas; cd mantiene la ruta actual del cliente y valida '
          'el directorio; mkdir crea directorios; rmdir elimina solo directorios vacíos y rm retira archivos. '
          'rename permite mover o renombrar entradas. Cada usuario autenticado trabaja en su propio espacio lógico.')
    label('RF2. Transferencia completa.', 'put, equivalente a send, divide, cifra y distribuye un archivo '
          'completo. get, equivalente a receive/recv, recupera sus bloques en orden y comprueba su integridad '
          'antes de reemplazar el destino local.')
    label('RF3. Acceso a archivos.', 'open fija una versión; read consulta rangos de esa versión; lock '
          'reserva bloques; write admite creación, reemplazo, modificación parcial y anexado según el modo; '
          'close publica las escrituras pendientes o libera una lectura. La inmutabilidad se aplica a cada '
          'identificador de bloque, no impide modificar el archivo lógico.')
    table('Modos de apertura y escritura', ['Modo', 'Semántica y concurrencia'], [
        ['r', 'Lectura de un snapshot con lease renovable; no admite write.'],
        ['w', 'Reemplazo desde cero, incluido archivo vacío; excluye otros escritores. Con create permite crear el archivo.'],
        ['rw', 'Modificación parcial por bloques. Rechaza cambios sobre una base que otro escritor ya modificó.'],
        ['a', 'Anexa desde EOF y puede aumentar el tamaño. Excluye otros escritores para coordinar la posición final.'],
    ], [0.6, 5.9])
    p('Una escritura por posición requiere offset menor o igual al tamaño actual: no se permiten huecos '
      'más allá de EOF. Los cambios generan bloques nuevos mediante copia sobre escritura. La '
      'autenticación y autorización protegen RF1, RF2 y RF3.')

    heading('5.2. API del plano de control', 2)
    p('El control usa REST sobre HTTPS y cuerpos JSON. Las operaciones autenticadas llevan un JWT '
      'en Authorization. Los siguientes endpoints describen el contrato implementado; los códigos '
      'de error permiten distinguir sesión inválida, recurso bloqueado, conflicto e indisponibilidad.')
    table('Operaciones REST', ['Método y ruta', 'Función y respuesta principal'], [
        ['POST /v1/auth/login', 'Autenticar. 200 con token; 401 con credenciales inválidas.'],
        ['GET /v1/fs/ls?path=...', 'Listar entradas autorizadas. 200; 404 si no existe.'],
        ['POST /v1/fs/mkdir', 'Crear directorio. 201; 409 si existe.'],
        ['DELETE /v1/fs/rmdir?path=...', 'Eliminar directorio vacío. 204; 409 si contiene entradas.'],
        ['DELETE /v1/fs/rm?path=...', 'Retirar archivo. 204; 423 si hay escritores activos.'],
        ['POST /v1/fs/rename', 'Mover/renombrar. 204; 409 por destino existente, 423 por escritores activos.'],
        ['POST /v1/files/open', 'Abrir y fijar versión. 200 con fd, versión, manifiesto, DEK y TTL.'],
        ['POST /v1/files/{fd}/keepalive', 'Renovar lease. 200; 410 si venció.'],
        ['GET /v1/files/{fd}/manifest', 'Refrescar destinos/capacidades del mismo snapshot. 200.'],
        ['POST /v1/files/{fd}/lock', 'Reservar rango. 200; 423 si está ocupado, 409 con base vieja.'],
        ['POST /v1/files/{fd}/unlock', 'Liberar un rango sin carga pendiente. 204; 409 si tiene plan pendiente.'],
        ['POST /v1/files/{fd}/blocks', 'Reservar ID, destinos y fencing. 200; 503 sin dos nodos disponibles.'],
        ['POST /v1/files/{fd}/blocks/{bid}/authorize', 'Fijar hash/tamaño y emitir capacidad. 200; 409 si cambia un plan ya fijado.'],
        ['POST /v1/files/{fd}/blocks/{bid}/prepared', 'Verificar recibos. 200; 409 BAD_RECEIPT si son inválidos o duplicados.'],
        ['POST /v1/files/{fd}/close', 'Publicar/recuperar resultado del cierre. 200; 409 por conflicto, 410 por sesión vencida.'],
        ['POST /v1/files/{fd}/abort', 'Abortar la sesión y dejar residuos no publicados para GC. 204.'],
        ['GET /v1/files/{fd}/status', 'Consultar operación abierta/cerrada. 200; 410 si no hay sesión o resultado.'],
        ['GET /v1/files/stat?path=...', 'Consultar versión, tamaño y réplicas. 200; 404.'],
        ['GET /v1/admin/nodes', 'Consultar estado del clúster. 200; 403 sin rol admin.'],
    ], [3.2, 3.3])

    heading('5.3. API del plano de datos', 2)
    p('Los bloques viajan por gRPC con streaming y mTLS [4]. Una capacidad firmada autoriza '
      'operación, bloque, contenido y destinos. La escritura incluye identificador del bloque, '
      'identificador de operación, tamaño cifrado esperado, SHA-256 y cadena de destinos.')
    table('Operaciones gRPC', ['RPC', 'Emisor y efecto'], [
        ['WriteBlock', 'Cliente o nodo anterior. Recibe fragmentos, valida, hace fsync, crea el bloque sin sobrescribir y devuelve recibos firmados.'],
        ['ReadBlock', 'Cliente. Entrega fragmentos cifrados; el cliente valida SHA-256 y la etiqueta GCM.'],
        ['ReplicateBlock', 'Coordinador. Ordena una copia S2S con tamaño y hash del catálogo; una fuente corrupta se rechaza.'],
        ['DeleteBlock', 'Recolector autorizado. Elimina una copia de un bloque sin referencias válidas.'],
        ['ListBlocks', 'Servicio autorizado. Obtiene inventario de bloques según el contrato de mantenimiento.'],
    ], [1.35, 5.15])

    heading('5.4. Ejemplo de solicitud, éxito y error', 2)
    p('El siguiente intercambio reserva el bloque 0 de una sesión ya abierta. Los identificadores '
      'y firmas son ilustrativos; los recibos reales se generan con la clave de cada nodo.')
    label('Solicitud de reserva.', 'El cliente conserva el request_id si repite la misma petición.')
    code('POST /v1/files/{fd}/blocks\n'
         '{"index": 0, "request_id": "op-b0"}')
    label('Respuesta exitosa.', 'El coordinador asigna el bloque y los nodos autorizados.')
    code('200 OK\n{\n'
         '  "block_id": "0123456789abcdef0123456789abcdef",\n'
         '  "fencing": 1234,\n'
         '  "w": 2,\n'
         '  "pipeline": ["dn1@dn1.dfsha.internal:50051",\n'
         '               "dn2@dn2.dfsha.internal:50051",\n'
         '               "dn3@dn3.dfsha.internal:50051"]\n}')
    label('Preparación y publicación.', 'El cliente cifra el bloque, fija su hash y tamaño mediante '
          'authorize y lo transfiere por WriteBlock. Después remite los recibos a prepared. El '
          'coordinador comprueba al menos dos firmantes distintos antes de permitir el cierre.')
    code('POST /v1/files/{fd}/blocks/{bid}/prepared\n'
         '{"receipts": ["firma_dn1", "firma_dn2"]}')
    label('Respuesta de error.', 'Un recibo duplicado, falso o ajeno al plan no prepara el bloque.')
    code('409 Conflict\n{\n  "detail": {\n    "code": "BAD_RECEIPT",\n'
         '    "msg": "confirmación falsa, duplicada o fuera del plan"\n  }\n}')
    p('close solo publica los bloques de los planes vigentes y preparados. Repetir el mismo '
      'fd y cuerpo devuelve la versión ya publicada; un cuerpo diferente para la operación '
      'cerrada recibe conflicto. Un 409 RETRY del catálogo se reintenta con espera aleatoria '
      'acotada. Un 409 VERSION_CONFLICT exige reabrir o releer y no se oculta con reintentos.')

    heading('6. Consistencia, concurrencia y tolerancia a fallos')
    heading('6.1. Publicación y lectores', 2)
    p('Los metadatos se coordinan mediante transacciones de etcd [3], [9]. Para publicar, el '
      'servidor comprueba los planes preparados, los locks, la sesión y los tamaños del manifiesto. '
      'La nueva versión aparece mediante una transacción CAS; antes del éxito no es visible. '
      'Las nuevas aperturas observan la última versión confirmada. Los lectores que abrieron '
      'antes conservan su snapshot, según la visibilidad close-to-open [5].')
    p('Las sesiones tienen un lease de 60 s, renovado cada 10 s. Una sesión lectora vigente '
      'mantiene referencias a sus bloques y permite renovar capacidades sin cambiar la versión. '
      'Al cerrar o expirar, deja de retener los bloques obsoletos. El GC marca huérfanos, espera '
      'gracia y vencimiento de capacidades, y revalida referencias antes de borrar. El plazo '
      'de gracia no sustituye el seguimiento de lectores [11].')
    heading('6.2. Escrituras concurrentes', 2)
    p('En rw, adquirir el lock también verifica el identificador del bloque base. Otro escritor '
      'que lo haya modificado desde open provoca 409 VERSION_CONFLICT. Dos clientes que afectan '
      'bloques distintos pueden preparar sus cambios en paralelo y el cierre conserva ambas '
      'modificaciones. w y a excluyen otros escritores para coordinar truncado y EOF. rm y rename '
      'responden 423 mientras haya escritores activos.')
    p('Todos los locks de una sesión comparten su lease. Si el cliente desaparece, vencen junto '
      'con la sesión; un cierre posterior no puede publicar. La renovación continúa mientras '
      'close transfiere pendientes. El resultado del cierre queda asociado a la operación '
      'para que una respuesta perdida no produzca una publicación duplicada.')
    heading('6.3. Detección, reparación y disponibilidad', 2)
    p('Los nodos envían heartbeats firmados cada 3 s. Sin latido durante 10 s pasan a sospechosos '
      'y dejan de recibir nuevas asignaciones; a los 30 s se consideran caídos. El monitor '
      'renueva su liderazgo en paralelo y repara desde una fuente cuyo hash/tamaño coinciden '
      'con el catálogo. El destino se registra antes del RPC para que el GC conozca posibles '
      'copias que terminen tarde. Una fuente corrupta no se anuncia como reparación válida.')
    p('Con dos miembros etcd comunicados se mantiene el cuórum. Sin mayoría, las operaciones '
      'de catálogo fallan cerrado con 503; no se publica una versión sobre un catálogo '
      'inconsistente [10]. Una lectura ya abierta puede utilizar réplicas disponibles dentro '
      'de la vigencia de su sesión y capacidades. No se garantiza operación ante cualquier '
      'combinación de fallos o pérdida de todas las copias de un bloque.')

    heading('7. Seguridad e integridad')
    p('Cada servicio tiene una identidad de transporte propia. La CA de etcd habilita a los '
      'miembros del catálogo y coordinadores; nodos y clientes no reciben sus credenciales ni '
      'la KEK. gRPC exige certificado de cliente y capacidad de bloque. JWT de usuario y '
      'capacidades tienen claves EdDSA separadas; cada nodo firma sus recibos con Ed25519. '
      'Las contraseñas usan scrypt con sal y parámetros N=32768, r=8, p=3. Los JWT duran '
      '15 minutos [6].')
    p('TLS protege las comunicaciones [7]. En reposo, el cliente cifra los bloques con '
      'AES-256-GCM y AAD igual al block_id [8]. La DEK de cada archivo está envuelta con '
      'la KEK disponible en los coordinadores. El modelo confía en el coordinador para '
      'autorizar y entregar la DEK; no declara cifrado extremo a extremo resistente al servidor.')
    p('Se comprueban tamaño y SHA-256 del bloque cifrado, etiqueta GCM y hash canónico del '
      'manifiesto. put/w registra además el SHA-256 de todos los bytes planos; rw/a lo deja '
      'en null porque no lo recalcula. El hash de manifiesto no se confunde con el hash '
      'plano global. get escribe un temporal y reemplaza el archivo de destino solo después '
      'de validar la longitud y la integridad.')

    heading('8. Validación en AWS Academy')
    p('Los registros aportados por el equipo corresponden a cuatro VMs EC2 t3.small en '
      'us-east-1a. La Figura 3 muestra los contenedores por VM y sus direcciones privadas. '
      'La evidencia funcional posterior incluye la consulta de los cuatro nodos de datos '
      'y la distribución de bloques. Las capturas se conservan junto a los resultados de '
      'la misma etapa de validación.')
    figure('aws_despliegue.png', 'Distribución de contenedores y direcciones privadas de las cuatro VMs.')
    p(f'La regresión final del 6 de noviembre de 2026 reporta {regression["tests"]} casos, '
      f'{regression["failures"]} fallos, {regression["errors"]} errores y {regression["skipped"]} '
      'omitidos. Comparte huella de código con el benchmark completo seleccionado. Incluye '
      'recibos falsos/duplicados, inmutabilidad, snapshot sin caché, base vieja, modificación '
      'de bloques distintos, vacío, rm/rename, cierre idempotente, rangos, aislamiento, '
      'mTLS y clientes concurrentes. La prueba grande transfiere y recupera 129 bloques '
      'de 8 MiB, equivalentes a 1032 MiB, con hash coincidente.')
    figure('aws_regresion.png', f'Resultado de la regresión en el bastión: {regression["tests"]} casos satisfactorios.')
    p('La demostración funcional carga, consulta y descarga un archivo de 200 MiB con SHA-256 '
      'coincidente; también modifica, anexa y lee contenido desde la CLI. La consulta de '
      'estado identifica los nodos donde se almacenan las copias.')
    figure('aws_rf.png', 'Gestión del espacio de usuario y acceso RF1, RF2 y RF3 en AWS.')
    p('El segundo escritor sobre el mismo bloque recibe 423 BLOCK_LOCKED. Si espera el lock '
      'y el primero publica, recibe 409 VERSION_CONFLICT porque la base observada en open '
      'ya cambió. Debe reabrir/releer. En bloques distintos, las dos modificaciones quedan '
      'publicadas. Estas salidas corresponden a la política de locks y versión esperada.')
    figure('aws_concurrencia.png', 'Conflicto sobre un mismo bloque y publicación de cambios en bloques distintos.')

    heading('8.1. Caídas de servicios y recuperación observada', 2)
    table('Resultado de las sondas durante los fallos', ['Condición', 'Observación registrada'], [
        ['dn1 detenido', 'La lectura y una carga nueva completan; las réplicas del archivo de prueba se restauran sin dn1.'],
        ['meta1 detenido', 'La lectura continúa mediante meta2.'],
        ['Un etcd detenido', 'La lectura se completa con dos votantes comunicados.'],
        ['Dos etcd detenidos', 'El catálogo rechaza la operación con 503 por pérdida de cuórum.'],
        ['Servicios reiniciados', 'La sonda de lectura posterior vuelve a completar.'],
    ], [1.65, 4.85])
    start, end, elapsed = observed_recovery(records)
    p(f'El comando que detuvo dn1 finalizó a las {start.strftime("%H:%M:%S.%f")[:-3]} UTC. '
      f'La primera sonda que confirmó tres copias sin dn1 terminó a las '
      f'{end.strftime("%H:%M:%S.%f")[:-3]} UTC. El intervalo observado fue de '
      f'{elapsed:.1f} segundos. Incluye detección del fallo, reparación y espera entre sondeos; '
      'no mide exclusivamente la transferencia de réplicas ni fija el instante exacto de '
      'restauración, que pudo ocurrir entre consultas.')
    p('Se conservaron tres sondeos de reparación fallidos antes del exitoso. Todos los pasos '
      'no asociados a esa espera terminaron con código cero y el registro muestra el reinicio '
      'de los servicios y una lectura final correcta. Estas pruebas detienen procesos Docker '
      'en VMs reales; la caída completa de una VM con todos sus roles es un escenario distinto.')
    figure('aws_caidas.png', 'Secuencia registrada de detención, sondeo, reparación y reinicio de servicios.')
    p('Las pruebas de seguridad muestran 401 sin sesión o con contraseña incorrecta, 404 '
      'para una ruta ajena y 403 al consultar administración sin ese rol. Un nodo rechaza '
      'tokens de bloque ausentes o alterados y conexiones sin TLS. Las capturas muestran '
      'negociación TLS 1.3; no demuestran por sí solas rechazo de todas las versiones anteriores.')
    figure('aws_seguridad.png', 'Accesos denegados y comprobación del canal TLS en AWS.')

    heading('9. Resultados de rendimiento y análisis')
    started = dt.datetime.fromisoformat(bench['started_utc'])
    finished = dt.datetime.fromisoformat(bench['finished_utc'])
    sample_count = sum(int(row['n']) for row in measurements)
    p(f'El benchmark completo comenzó el 6 de noviembre de 2026 a las {started:%H:%M} UTC y finalizó '
      f'a las {finished:%H:%M} UTC. Contiene {sample_count} muestras: '
      f'{bench["parameters"]["repetitions"]} repeticiones en cada una de {len(measurements)} condiciones '
      'de operación. Se registraron tamaños, concurrencia, replicación, dependencias y huella '
      'de código. Los resúmenes se obtienen de las muestras; el throughput es la media del '
      'tamaño dividido por la duración de cada repetición. E1/E2 incluyen cifrado, hashes, '
      'recibos y publicación; E3 mide el tiempo de pared de los clientes concurrentes.')
    def metric(exp, condition, op):
        return next(float(row['MiB_s']) for row in measurements
                    if row['experiment'] == exp and row['condition'] == condition and row['operation'] == op)
    def condition(value):
        return value.replace('R=3;bytes=', 'R3; ').replace('clients=', 'Clientes: ').replace(';W=', '/W')
    table('Latencia y throughput medidos en AWS', ['Exp.', 'Condición', 'Op.', 'MiB', 'Media s', 'p95 s', 'MiB/s'], [
        [row['experiment'], condition(row['condition']), row['operation'], row['MiB'],
         f'{float(row["mean_s"]):.2f}', f'{float(row["p95_s"]):.2f}', f'{float(row["MiB_s"]):.1f}']
        for row in measurements], [0.65, 1.45, 0.55, 0.55, 1.0, 1.0, 1.3])
    r2, r3 = metric('E2', 'R=2;W=2', 'put'), metric('E2', 'R=3;W=2', 'put')
    drop = 100 * (1 - r3 / r2)
    p(f'E1: para 500 MiB, la escritura alcanzó {metric("E1", "R=3;bytes=500", "put"):.1f} '
      f'MiB/s y la lectura {metric("E1", "R=3;bytes=500", "get"):.1f} MiB/s. La lectura '
      'no necesita producir nuevas réplicas. E2: con W=2, R=2 obtuvo '
      f'{r2:.1f} MiB/s y R=3 obtuvo {r3:.1f} MiB/s, una reducción observada de '
      f'{drop:.1f} %. Esta comparación cuantifica la diferencia entre esas configuraciones; '
      'no permite deducir cuánto costaría otro algoritmo de replicación no medido.')
    p(f'E3: la escritura agregada pasó de {metric("E3", "clients=1", "put"):.1f} MiB/s '
      f'con un cliente a {metric("E3", "clients=8", "put"):.1f} MiB/s con ocho; la lectura '
      f'pasó de {metric("E3", "clients=1", "get"):.1f} a '
      f'{metric("E3", "clients=8", "get"):.1f} MiB/s. La contención del epoch global es '
      'una explicación compatible con los conflictos RETRY y motivó reintentos con espera '
      'aleatoria. Como no se registraron contadores de reintentos ni series de CPU, disco '
      'y NIC, no se atribuye de forma concluyente a un recurso el costo observado.')
    p('La primera corrida AWS se conserva con estado fallido; la siguiente finalizó después '
      'de la corrección de reintentos del cliente. No se mezclan muestras de ambas. Con '
      'cinco repeticiones el p95 calculado por rango más cercano es el máximo de la muestra; '
      'se interpreta como observación de esa corrida y no como caracterización robusta de colas.')
    figure('aws_benchmark.png', 'Resumen del benchmark completo consultado en el bastión.')

    heading('10. Escenarios obligatorios de razonamiento')
    table('Respuesta del diseño a los cuatro escenarios', ['Escenario', 'Comportamiento y evidencia'], [
        ['Dos procesos escriben el mismo bloque', 'Solo un lock vigente permite preparar. El segundo recibe 423 o, tras esperar y cambiar la base, 409. Los cambios de bloques distintos pueden fusionarse.'],
        ['Una réplica se desconecta durante la escritura', 'La publicación exige dos recibos auténticos y distintos de cada bloque preparado. Si falta la tercera copia se repara; con menos de dos no se publica. Lectores conservan su versión.'],
        ['Un nodo falla tras recibir parte del bloque', 'El temporal incompleto no obtiene recibo ni se publica. La regresión envía un stream incompleto, comprueba DATA_LOSS y rechazo del cierre.'],
        ['El cliente desconoce las ubicaciones físicas', 'Consulta coordinadores por nombres lógicos; open/manifest devuelve ubicaciones y capacidades. Ante fallo refresca el mismo snapshot y prueba réplicas autorizadas.'],
    ], [2.0, 4.5])

    heading('11. Contribuciones, limitaciones y cierre')
    table('Integración y revisión identificables en el repositorio', ['Integrante', 'Ámbito registrado', 'Commits representativos'], [
        ['Samuel Parra Cadavid', 'Cliente, CLI, regresiones y documentación de uso', '3116445; 9d41958'],
        ['Juan José García Duque', 'Nodo de datos, contrato gRPC, identidades, clúster local y guiones', '558a8d0; c503e80; 32fdf44'],
        ['Andrés Felipe Martínez Velasquez', 'Control y catálogo, despliegue, correcciones del cliente, pruebas AWS e informe', 'e20d902; 3da88d5; 87836a9; 6f765cc; b076042'],
    ], [1.6, 3.0, 1.9])
    p('Los commits identifican integración y revisión de componentes; cada integrante debe '
      'poder explicar la arquitectura completa y las pruebas asociadas. El repositorio '
      'del equipo está disponible en ' + REPOSITORY + '.')
    p('Quedan como límites y trabajo experimental adicional la comparación 4/8 MiB y 3/4 nodos, '
      'instrumentar CPU/memoria/disco/NIC, estudiar el epoch global bajo mayor carga y probar '
      'la pérdida completa de una VM. El catálogo necesita políticas operativas de respaldo '
      'y retención; no hay migración automática del prototipo anterior ni cuotas por usuario.')
    p('La comparación de propuestas y los cambios de alcance se describen en las secciones '
      '2 y 3 de este informe. Las limitaciones de RF3 y de las garantías no funcionales '
      'se declaran para su revisión conforme al alcance asignado. El video '
      'final de 10 a 15 minutos y la defensa individual son entregables complementarios '
      'que deben mostrar ejecución distribuida, fallos, resultados y explicación de decisiones.')

    heading('Referencias')
    for reference in REFERENCES:
        paragraph = p(reference)
        paragraph.paragraph_format.first_line_indent = Cm(-0.7)
        paragraph.paragraph_format.left_indent = Cm(0.7)
        paragraph.paragraph_format.space_after = Pt(4)
    target = ROOT / 'DFSha_FaseII_Informe_Grupal.docx'
    doc.save(target)
    print('Word generado:', target)
    print('Respaldo anterior:', backup)
    print(f'Intervalo de recuperación observado: {elapsed:.3f} s; portada APA 7; referencias IEEE conservadas.')
    return target
