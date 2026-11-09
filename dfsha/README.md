# DFSha — revisión técnica del prototipo grupal

Opción 1: cliente/servidor con comunicación S2S en red privada. Se incluyen pruebas locales y registros
aportados de AWS Academy del 6 de noviembre de 2026: 19 casos de regresión, caídas de servicios
y benchmark completo. Las evidencias del prototipo previo no se reutilizan como validación de esta versión.

## Arquitectura y contrato

- Dos APIs FastAPI equivalentes; tres miembros etcd/Raft persistentes; cuatro nodos de datos.
- Control REST/HTTPS; bloques gRPC con mTLS y capacidad firmada; replicación S2S desde el primer nodo.
- Bloques de 8 MiB (último menor); R=3 objetivo, W=2 persistentes distintos. R=2 solo comparación declarada.
- Cada nodo firma su recibo con Ed25519. El coordinador valida identidad, plan, bloque, operación, tamaño y hash.
- Bloques create-once; repetir el mismo contenido es idempotente, sustituirlo no está permitido.
- `open(r)` fija snapshot y lease renovable. `read` conserva esa versión y refresca capacidades/ubicaciones.
- `rw` usa locks por bloque y rechaza una base modificada desde `open`. Bloques diferentes pueden avanzar en paralelo.
- `w` (truncado) y `a` (anexado) requieren exclusión de escritores sobre el archivo. No se escribe más allá de EOF.
- `close` publica mediante CAS de sesión/referencias; repetir el mismo `fd`/cuerpo recupera el resultado ya publicado.
- `rm/rename` rechazan escritores activos (423). Lectores previos mantienen sus bloques mientras el lease esté vigente.
- GC marca huérfanos, espera gracia **y** vencimiento de capacidades, y vuelve a comprobar referencias antes de borrar.
- Confirmaciones/fichas se preparan por bloque; el commit tiene número acotado de operaciones, no una por bloque.

### Integridad declarada

Todos los bloques tienen SHA-256 del texto cifrado y autenticación GCM con AAD=block_id.
`put/w` registra además SHA-256 del archivo plano completo y `get` lo compara cuando existe.
Después de `rw/a` ese hash global es `null`: no se promete una verificación global que no se recalcula.
En todos los casos se validan orden, tamaño final y tamaños por bloque, y se registra un hash canónico del
manifiesto (`manifest_sha256`) que el cliente verifica. No se presenta ese hash de manifiesto como si fuera
el SHA-256 de todos los bytes planos; la versión autorizada fija el manifiesto.

### Seguridad por rol

La CA de etcd solo emite identidades para sus miembros y los coordinadores. Nodos/clientes
no reciben credenciales de catálogo. La CA de aplicación protege HTTPS/gRPC; cada servicio tiene certificado propio.
El cliente necesita su identidad de transporte y token de usuario, no la KEK ni llaves de firma.
JWT/capacidades usan claves asimétricas separadas; recibos tienen una llave por nodo. Contraseñas: scrypt con sal,
N=32768, r=8, p=3. La KEK de AES-GCM solo se carga en los coordinadores.

## Ejecución local, desde esta carpeta

Requiere Docker Engine y Compose v2. El nombre de proyecto separa estos servicios de otros del equipo.

```bash
docker build -t dfsha:revision .
docker run --rm -v "$PWD:/workspace" -w /workspace dfsha:revision python scripts/init_local.py
docker compose -p dfsha-revision -f docker-compose.local.yml up -d --no-build
docker compose -p dfsha-revision -f docker-compose.local.yml exec cliente python -m dfsha.cli login andres clave123
docker compose -p dfsha-revision -f docker-compose.local.yml exec cliente python -m dfsha.cli ls /
```

En PowerShell, para inicializar usar:

```powershell
docker run --rm --mount "type=bind,source=$((Get-Location).Path),target=/workspace" --workdir /workspace dfsha:revision python scripts/init_local.py
```

`init_local.py` genera `certs/` y `.env` si no existen, no reemplaza secretos existentes.
Las contraseñas incluidas son exclusivamente de laboratorio. Nunca subir estos archivos a GitHub.
La CA privada se conserva en `certs/private/` y no se monta en servicios ni se empaqueta para AWS.

**Incompatibilidad de formato:** el catálogo/capacidades del prototipo previo no son una migración automática.
Usar un proyecto/volúmenes nuevos y conservar cualquier dato previo hasta planear su migración/exportación.
No ejecutar `down -v` sobre volúmenes que contengan datos que se quieran guardar.

## API principal revisada

| Operación | Rutas / efecto |
|---|---|
| Login y árbol | `/v1/auth/login`, `/v1/fs/ls`, `/mkdir`, `/rmdir`, `/rm`, `/rename` |
| Abrir | `POST /v1/files/open` con `path`, `mode`, `create`, `request_id`; devuelve `fd`, snapshot y TTL |
| Renovar/refrescar | `POST /v1/files/{fd}/keepalive`; `GET /v1/files/{fd}/manifest` |
| Lock | `POST /v1/files/{fd}/lock` y `/unlock`; máximo 48 bloques por adquisición atómica |
| Reservar bloque | `POST /v1/files/{fd}/blocks`, índice y `request_id` |
| Autorizar contenido | `POST /v1/files/{fd}/blocks/{bid}/authorize`, SHA-256 y longitud cifrada |
| Transferir | `WriteBlock` gRPC, tamaño/hash/capacidad/operación; devuelve recibos firmados |
| Preparar | `POST /v1/files/{fd}/blocks/{bid}/prepared`, al menos dos recibos distintos |
| Publicar | `POST /v1/files/{fd}/close`, lista de IDs/fencing; el servidor usa los planes verificados |
| Abortar | `POST /v1/files/{fd}/abort`; deja residuos no publicados para GC |
| Consultar resultado | `GET /v1/files/{fd}/status`; estado abierto/cerrado o 410 |
| Salud/administración | `/health`; `/v1/admin/nodes` requiere rol admin |

El servidor aplica comparaciones y actualizaciones al namespace y referencias. Borrar/renombrar no invalida silenciosamente
escritores abiertos: responde 423 hasta que cierren o expiren. El lease dura 60 s por defecto, renovado cada 10 s.
Si expira un lector, debe volver a abrir: no se garantiza mantener indefinidamente un descriptor sin renovación.

## Pruebas que sí deben ejecutarse

```bash
docker compose -p dfsha-revision -f docker-compose.local.yml exec -T cliente python -m tests.regression
docker compose -p dfsha-revision -f docker-compose.local.yml exec -T -e RUN_LARGE=1 cliente python -m tests.regression
docker compose -p dfsha-revision -f docker-compose.local.yml exec -T cliente python -m tests.test_statistics
python scripts/verify_local.py --project dfsha-revision
```

La prueba grande transfiere y recupera 129 bloques (1032 MiB con la configuración de 8 MiB).
Consume varios GiB de disco por la replicación. El orquestador de fallos solo detiene servicios del proyecto Compose
indicado y los restaura en `finally`; nunca llama a AWS/SSH ni elimina volúmenes.

`python scripts/record_checks.py` registra las pruebas de contrato del GC con etcd en memoria, estadística,
aislamiento de paquetes y configuración. Usa un contenedor temporal con identidad de prueba de `meta1` para las
pruebas aisladas y el clúster local levantado para la comprobación mTLS. No ejecuta las pruebas de memoria contra AWS.

### Benchmark corregido

```bash
docker compose -p dfsha-revision -f docker-compose.local.yml exec -T cliente python -m tests.bench --environment local --repetitions 5
```

Cada corrida crea `resultados/revision-bench-<UTC>-<id>/` con `samples.csv`, `summary.csv` y `run.json`.
Guarda cada repetición y el hash del código. Cinco muestras hacen que p95 por rango más cercano sea el máximo;
para caracterizar colas conviene aumentar las repeticiones. E2 compara R=2 y R=3 con W=2.
Cada ejecución se conserva por separado; el índice de resultados distingue la corrida AWS fallida de la completa.

La comparación 4/8 MiB exige clústeres separados y vacíos con la misma carga; cambiar `BLOCK_SIZE` sobre datos
existentes no es compatible. La comparación por número de nodos y las métricas de CPU/disco/NIC quedan explícitas
en el plan del informe: no se presenta concurrencia de clientes como si midiera crecimiento de nodos.

## AWS Academy

1. Instalar dependencias del administrador: `pip install -r deploy/requirements.txt`.
2. Preparar cuatro Ubuntu 24.04, Docker y Compose, con etiquetas `Proyecto=DFSha`, `Name=dfsha-vm1..vm4`.
3. Acceso SSH desde el administrador; puertos de servicios solo entre roles autorizados por el security group.
4. Generar identidades/configuración, cambiar contraseñas de laboratorio y respaldar la KEK.
5. Ejecutar `python deploy/desplegar.py --key <llave>`. Requiere directorios nuevos/v2, no sobreescribe una instalación antigua.

| VM | Servicios |
|---|---|
| vm1 | etcd1, meta1, dn1 |
| vm2 | etcd2, meta2, dn2 |
| vm3 | etcd3, dn3 |
| vm4 | dn4 y cliente/bastión |

Se genera `extra_hosts` por contenedor además del archivo de hosts del anfitrión. No se anuncia un DNS con salud
que no esté instalado. La CLI tiene dos endpoints lógicos y reintenta errores de conexión/timeout con IDs estables.
El script distribuye solo certificados/secretos del rol; no copia la llave SSH administrativa al bastión.
En vm4 instalar cliente con `sh scripts/setup_cliente.sh`. La administración de caídas se realiza desde la máquina
administradora, no entregando su llave privada al cliente.

**Alcance de la evidencia AWS:** están registrados regresión, benchmark y detención de contenedores de servicios.
No equivale a la pérdida completa de una VM o de su disco. Siguen pendientes comparar 4/8 MiB y 3/4 nodos,
instrumentar recursos y ratificar decisiones/entregables finales. El script requiere SSH directo a las cuatro
instancias; para solo bastión público se debe configurar ProxyJump/VPN. La red de servicios sigue siendo privada.

## Límites explícitos

- Catálogo v2; no migración automática del prototipo anterior.
- `MAX_BLOCKS=8192` por archivo (64 GiB a 8 MiB); rename atómico hasta 48 entradas; lock atómico hasta 48 bloques.
- Epoch global del catálogo: prioriza corrección frente a paralelismo de metadatos masivo. No se promete escalabilidad ilimitada.
- Resultados idempotentes y manifiestos requieren política de retención/backup a largo plazo; no hay cuotas ni POSIX completo.
- No hay garantía ante pérdida de todas las copias ni pérdida de cuórum; se falla cerrado en operaciones de catálogo.
- AES-GCM/hash no sustituyen control de concurrencia. `rw/a` no recalculan hash plano global.
- La réplica S2S de esta revisión es secuencial desde un bloque validado, no un pipeline solapado. Medir el costo real.
- El acuerdo del equipo, aprobaciones, aportes reales, repositorio y video los debe completar el equipo.

Ver [evidencias de ejecución](resultados/README.md), [comparación de propuestas](../informe/COMPARACION_PROPUESTAS.md)
y [decisiones arquitectónicas](../informe/ADR_REVISION.md).
