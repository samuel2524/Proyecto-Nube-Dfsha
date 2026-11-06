# Correcciones realizadas a DFSha — Fase II

## 1. Resumen y alcance

Corregimos el prototipo después de revisar el código contra la consigna y los tres informes individuales.
Se conservó la opción cliente/servidor S2S: dos APIs equivalentes, tres miembros etcd/Raft y cuatro nodos de datos.

**Estado comprobado:** compilación de imagen, integración con servicios reales en Docker local, regresiones,
fallos de servicios, benchmark pequeño con muestras crudas y regeneración del informe grupal.
**Estas correcciones todavía no se han probado en AWS Academy.**

Los documentos individuales no se modificaron.
El Word y PDF grupales anteriores se preservaron en `informe/historico/` antes de regenerarlos.

## 2. Correcciones por hallazgo

| Auditoría | Corrección implementada | Archivos principales / comprobación |
|---|---|---|
| H01: W confiado al cliente | Plan registrado por bloque; capacidad ligada a contenido/destinos; recibos Ed25519 por nodo; verificación de dos firmantes distintos. El cierre solo acepta planes preparados por el servidor. | `metadata.py`, `common.py`, `datanode.py`, `proto/dfsha.proto`; pruebas de ACK falso, duplicado y commit sin preparación. |
| H02: base vieja pierde cambios | `rw` comprueba el ID base del bloque al adquirir lock. Si cambió desde open, responde 409; no aplica un bloque construido sobre datos viejos. Bloques distintos conservan paralelismo. | `metadata.py`, `client.py`; base vieja rechazada y modificaciones de dos bloques preservadas. |
| H03: GC inseguro y lectores sin protección | Sesiones lectoras renovables; snapshots/versiones retenidos por referencia; marca de huérfano y ciclo posterior; horizonte de capacidades antes de borrar; CAS de epoch para no eliminar bajo referencias cambiantes. | `metadata.py`; pruebas de GC, lector sin caché y refresco de snapshot. |
| H04: sobrescritura de ID publicado | Escritura incremental a temporal único; SHA/longitud, fsync y creación del destino sin reemplazarlo. Reintento idéntico es válido; contenido distinto no sustituye el existente. | `datanode.py`; replay válido y cambio de contenido rechazado. |
| H05: resurrección tras rm/rename | `rm/rename` rechazan escritores activos. Namespace se valida mediante epoch/CAS; close verifica identidad/ruta y existencia de padre. La DEK no se borra mientras lectores la necesiten. | `metadata.py`; rm/rename concurrentes rechazados, renombrado posterior correcto. |
| H06: vacío/manifiesto | `w` vacío publica una nueva versión de tamaño cero. Se validan continuidad, número de bloques y tamaños. Hash canónico del manifiesto en todas las versiones; hash plano global solo en put/w, sin prometer su recálculo en rw/a. | `metadata.py`, `common.py`, `client.py`; vacío y modificación parcial con hash de manifiesto. |
| H07: límite de transacción | Fichas preparadas antes de publicar; commit con cantidad acotada de operaciones. Se conserva CAS de sesión/referencias en vez de añadir una operación por bloque. | Prueba de componente de 129 bloques y transferencia/recuperación real de **1032 MiB**. |
| H08: idempotencia/lease | Resultado persistido por fd y digest del cuerpo; repetir close recupera la misma versión. Estado consultable por `/status`. Renovación continúa durante las cargas de close; reintentos de conexión/timeout con IDs estables. | `metadata.py`, `client.py`; cierre repetido y cuerpo distinto rechazado. |
| H09: secretos compartidos | Dos CA, identidades por servicio, firmantes separados para JWT/capacidades y un firmante por nodo. KEK/USERS solo en metadatos; cliente/nodos sin credencial etcd. No hay clave HMAC pública por defecto. | `gen_certs.py`, Compose, `common.py`, despliegue; aislamiento de paquete y entorno cliente comprobado. |
| H10: despliegue incompleto | `extra_hosts` por contenedor; paquetes de secretos mínimos por rol; requisito boto3 separado; validación de etiquetas y errores SSH; no se copia la llave administrativa al bastión. Se rechaza sobreescribir una instalación antigua sin preparar v2. | `deploy/desplegar.py`, Compose AWS, requisitos y README. Paquete/configuración revisados; AWS real pendiente. |
| H11: estadísticas incompatibles | Benchmark nuevo guarda cada repetición, resumen reconstruible, entorno, parámetros, dependencias y hash del código. Nuevos directorios por corrida. El CSV antiguo no fue maquillado ni reutilizado. | `tests/bench.py`, `test_statistics.py`, `resultados/LEER_ANTES_DE_USAR.md`. |

### Otros cambios de corrección

- Namespace: `mkdir/rmdir/rename` coordinados por epoch; no se publica un archivo bajo un padre ya eliminado.
- `w/a` requieren exclusión respecto a otros escritores para proteger tamaño/EOF; `rw` mantiene locks finos.
- El monitor renueva el lease de liderazgo en paralelo y verifica que siga vigente antes de efectos.
- Reparación: compara hash/tamaño del catálogo, verifica el recibo del destino y registra el destino **antes** del RPC.
  El GC conoce así copias que terminen tarde o cuya respuesta se pierda.
- El nodo verifica tamaño máximo, índice/plan, destinos autorizados y acción de capacidades administrativas.
- gRPC exige certificado de cliente; una prueba real comprueba el rechazo sin él.
- Se eliminó `[first, *iterator]`: recepción incremental sin materializar todo el stream.
- Temporales únicos; limpieza segura al terminar o de residuos no activos. No se borra un temporal que está recibiendo.
- Rangos negativos y lecturas que no avanzan se rechazan; un manifiesto incoherente no queda en un bucle infinito.
- R=1 se retiró del contrato normal. La comparación declarada usa R=2 frente a R=3, ambos W=2.
- Colocación considera capacidad libre y conteo de bloques, con primario rotativo.
- Descargas a temporal y reemplazo del destino solo tras validar longitud/integridad; close libera la sesión lectora.
- Las pruebas de snapshots y seguridad ahora tienen aserciones; la lectura vieja se comprueba sin llenar caché antes.
- Las pruebas de caídas locales restauran los servicios en `finally` y verifican recuperación posterior.

## 3. Cambios arquitectónicos explícitos que el equipo debe revisar

No son simples cambios de formato:

1. Firmas **Ed25519/EdDSA** separadas sustituyen el secreto HMAC común. El cliente no puede producir sus propios JWT/ACK.
2. Dos CA: catálogo solo para coordinadores/miembros; transporte de aplicación para clientes/nodos. Certificado propio por rol.
3. Lease de sesión de **60 s por defecto**, renovado cada 10 s; no se promete un snapshot válido indefinidamente sin renovación.
4. `rw` admite paralelismo por bloque, pero `w/a` son exclusivos por archivo. Un cliente con base vieja debe reabrir/releer.
5. GC basado en referencias y estado, con gracia adicional. El tiempo fijo ya no es la única protección.
6. Un epoch global simplifica la prueba de corrección y acota el commit; introduce contención de metadatos que debe medirse.
7. La réplica es S2S **secuencial desde bloque validado**, no pipeline solapado. No se conservan conclusiones de rendimiento del pipeline anterior.
8. Se conserva 8 MiB; comparar 4/8 MiB y crecimiento 3/4 nodos sigue siendo parte del plan experimental.
9. Límite declarado: 8192 bloques por archivo (64 GiB a 8 MiB), 48 bloques por adquisición de lock y 48 entradas por rename atómico.
10. Nuevo formato de catálogo/capacidades. No migrar datos antiguos automáticamente; usar una instalación nueva y conservar/exportar lo anterior.

La comparación fiel de los tres originales y la procedencia de las decisiones están en
[`informe/COMPARACION_PROPUESTAS.md`](informe/COMPARACION_PROPUESTAS.md) y los ADR en
[`informe/ADR_REVISION.md`](informe/ADR_REVISION.md). El equipo revisa y ratifica estas decisiones antes de la entrega.

## 4. Pruebas ejecutadas realmente

### 4.1 Integración con el clúster local completo

```text
Docker: 3 etcd + 2 coordinadores + 4 nodos + cliente
16 pruebas de integración: OK, cero fallos/errores/omitidos
Incluye 129 bloques de 8 MiB: 1032 MiB subidos y recuperados con hash coincidente
```

Registro: `dfsha/resultados/revision-20261103-062535/regression.json`.
Hash del código ejecutado (incluye stubs generados):
`9632b34fadbb8ad670ebc8f5b2f5281a02712b03be680a664b41bafcc05e9e8e`.

Después se añadió y ejecutó por separado la prueba negativa de certificado mTLS, que también pasó.
La suite actual contiene 17 casos; el caso de archivo grande se habilita con `RUN_LARGE=1`.

### 4.2 Contrato y seguridad del paquete

- Cinco pruebas de componente: GC, referencias, horizonte de tokens, commit de 129 bloques acotado y reparación.
- Una prueba estadística: resumen reconstruible y rechazo de p95 imposible.
- Una prueba de aislamiento del paquete: vm3/vm4 sin KEK/firmantes ni llaves etcd de coordinador; hosts de contenedor presentes.
- Renderizado válido con Docker Compose de los cuatro paquetes AWS generados, sin ejecutar SSH/AWS.
- Una prueba de red: conexión gRPC sin certificado de cliente rechazada.
- Análisis sintáctico Python y construcción del contrato protobuf durante el build.

Comandos, salidas y digest de imagen:
`dfsha/resultados/revision-checks-20261103T064125Z/checks.json`.

### 4.3 Caídas de servicios reales en Docker local

Comprobadas con aserciones:

1. Lectura y escritura durante la caída de dn1.
2. Recuperación de tres copias válidas del archivo de prueba, sin dn1.
3. Lectura con meta1 detenido, usando meta2.
4. Lectura con un miembro etcd detenido.
5. Rechazo con 503 cuando se detienen dos miembros y se pierde cuórum.
6. Restauración de servicios y lectura posterior correcta.

Registro: `dfsha/resultados/revision-failures-8360fe3f7eb4/run.json`.
Los intentos fallidos de sondeo mientras repara se etiquetan `polling: true`: son espera de recuperación,
no se ocultan ni se convierten en resultados positivos.

### 4.4 Benchmark nuevo

Corrida **local**, no AWS:

```text
5 repeticiones; archivo 10 MiB
E1: put/get
E2: R=2 y R=3 con W=2
E3: 1 y 2 clientes, put/get
40 muestras crudas; 8 resúmenes
```

Ruta: `dfsha/resultados/revision-bench-20261103T062822Z-73ae1d/`.
Contiene `samples.csv`, `summary.csv`, `run.json`, parámetros, dependencias y el mismo hash de código de la integración.
No se extrapolan estos resultados pequeños a archivos de 500 MiB, ocho clientes o un despliegue AWS.

Se conservaron también los runs anteriores de desarrollo, incluyendo un fallo de regresión detectado durante
la implementación y corregido después. No representan el resultado final ni deben confundirse con la última corrida.

## 5. Documentación y artefactos

- `DFSha_FaseII_Informe_Grupal.docx`: regenerado para describir el contrato revisado y distinguir validación local de AWS pendiente.
- `DFSha_FaseII_Informe_Grupal.pdf`: exportado desde Word a partir del documento corregido.
  La versión regenerada ocupa **7 páginas reales**; la extensión individual no se aplica al informe grupal.
- `informe/figuras/componentes_revision.png` y `despliegue_revision.png`: reflejan el protocolo real revisado.
- `informe/historico/DFSha_FaseII_Informe_Grupal.docx/.pdf`: originales previos, preservados antes de regenerar.
- `informe/construir_informe.py`: ya no genera un informe que presente capturas/estadísticas históricas como prueba de la revisión.
- `dfsha/README.md`: instalación, API, pruebas, roles, incompatibilidad y límites documentados.
- `.gitignore` y `.dockerignore`: excluyen secretos, certificados, temporales y datos binarios de prueba del repositorio/imagen.
- `dfsha/resultados/LEER_ANTES_DE_USAR.md`: distingue evidencias históricas y nuevas.

### Índice de archivos de código/configuración principales

```text
dfsha/dfsha/common.py             firmas, capacidades, recibos, hash de manifiesto y etcd
dfsha/dfsha/metadata.py           sesiones, CAS, namespace, preparación, commit, GC y reparación
dfsha/dfsha/datanode.py           almacenamiento inmutable, mTLS y recibos propios
dfsha/dfsha/client.py             renovación, snapshot, preparación y descarga atómica
dfsha/dfsha/cli.py                rangos/réplicas y cierre de lectores
dfsha/proto/dfsha.proto           tamaño, operación y recibos en el contrato de datos
dfsha/scripts/gen_certs.py        identidades por rol y CA separadas
dfsha/scripts/init_local.py       inicialización explícita sin reemplazar secretos existentes
dfsha/scripts/setup_cliente.sh    cliente AWS sin secretos del catálogo
dfsha/scripts/verify_local.py     fallos locales con restauración
dfsha/scripts/record_checks.py    registro verificable de comprobaciones
dfsha/scripts/check_deploy_config.py  renderizado seguro de los cuatro paquetes Compose AWS
dfsha/deploy/desplegar.py         paquetes mínimos por VM y resolución de nombres
dfsha/deploy/docker-compose.yml  roles AWS corregidos
dfsha/docker-compose.local.yml   clúster local aislado
dfsha/deploy/requirements.txt     dependencia boto3 del administrador
dfsha/tests/regression.py        regresiones de contrato e integración
dfsha/tests/unit_contract.py     invariantes de GC, reparación y commit
dfsha/tests/fault_probe.py       sondas de datos y disponibilidad
dfsha/tests/bench.py             muestras crudas y resumen derivado
dfsha/tests/test_statistics.py   comprobación de estadística
dfsha/tests/test_deploy.py       aislamiento de secretos por paquete
dfsha/tests/close_to_open.py     snapshot sin caché previa, con aserciones
dfsha/tests/token_nodo.py        accesos correctos/denegados con aserciones
dfsha/tests/pruebas.sh           ejecución estricta de regresión/estadística
```

## 6. Reproducción resumida

Desde `DFSha_FaseII/dfsha/`:

```bash
docker build -t dfsha:revision .
docker run --rm -v "$PWD:/workspace" -w /workspace dfsha:revision python scripts/init_local.py
docker compose -p dfsha-revision -f docker-compose.local.yml up -d --no-build
docker compose -p dfsha-revision -f docker-compose.local.yml exec -T -e RUN_LARGE=1 cliente python -m tests.regression
python scripts/record_checks.py
python scripts/verify_local.py --project dfsha-revision
docker compose -p dfsha-revision -f docker-compose.local.yml exec -T cliente python -m tests.bench --environment local --repetitions 5
```

El README incluye la variante PowerShell del montaje para inicializar. La prueba de componente se ejecuta en
un contenedor temporal con identidad de prueba de meta1; `record_checks.py` deja el comando completo sin imprimir secretos.

`certs/` y `.env` se generaron para el laboratorio local y están ignorados por Git. No distribuirlos ni publicarlos.
El clúster local usa el nombre de proyecto `dfsha-revision`, separado de otros proyectos Docker.
Al terminar las pruebas conviene retirar sus contenedores y volúmenes de datos de prueba, que ocupan varios GiB;
los registros JSON/CSV se conservan. Para ejecutarlo otra vez, seguir `up` del README.

## 7. Qué todavía falta para la entrega grupal

Pendientes:

- Ratificar el contrato revisado entre los tres y registrar decisiones/aprobaciones del profesor cuando apliquen.
- Repetir instalación limpia, fallos de VM completa, seguridad y mediciones en **AWS Academy**.
- Completar comparación 4/8 MiB y 3/4 nodos; ensayar la carga completa prevista, no solo el benchmark local de humo.
- Medir CPU/memoria/disco/NIC y disponibilidad/tiempo de reparación con procedimiento controlado antes de atribuir cuellos de botella.
- Definir respaldo de catálogo/KEK, retención operativa de resultados idempotentes y migración si desean conservar datos del prototipo anterior.
- Revisar los límites de epoch global y tamaño máximo bajo mayor concurrencia; no asumir escalabilidad ilimitada.
- Verificar que el profesor tenga acceso al repositorio **GitHub** del equipo.
- Grabar el video final de 10–15 minutos y preparar defensa individual de toda la arquitectura.

**Conclusión:** se corrigieron los bloqueantes de código detectados y se añadió validación local reproducible.
Falta repetir la validación en AWS Academy, que es el siguiente paso del equipo.
