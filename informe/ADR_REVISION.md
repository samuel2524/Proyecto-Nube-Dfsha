# Decisiones de corrección del prototipo

Estos ADR describen las decisiones implementadas en la revisión.

| ID | Decisión | Razón / consecuencia |
|---|---|---|
| R01 | Recibos Ed25519 por nodo; capacidades de contenido firmadas por coordinadores | El cliente no puede declarar que dos réplicas persistieron sin pruebas auténticas. Cada recibo queda ligado a bloque, operación, hash y longitud. |
| R02 | Bloques create-once y réplica desde un bloque validado | El reintento idéntico se acepta; un contenido distinto no sustituye el publicado. El pipeline ahora es secuencial y debe medirse de nuevo. |
| R03 | Sesiones lectoras y escritoras con lease común de 60 s, renovable | Los lectores retienen snapshots; la caducidad es explícita. El cliente renueva también mientras close sube datos. |
| R04 | rw por bloque; w/a exclusivos; rm/rename rechazan escritores | Preserva paralelismo de bloques distintos sin truncados/anexados que cambien la estructura bajo otros escritores. |
| R05 | Validar el ID base del bloque al tomar lock | Un cliente que abrió antes no puede perder cambios de otro al obtener el lock después. Reabrir/releer ante 409. |
| R06 | Epoch global y CAS de sesión para publicación y namespace | Acota la transacción y protege GC/refs. Introduce un punto de contención de metadatos, explícito en límites. No se promete escala ilimitada. |
| R07 | Fichas preparadas por bloque, versión publicada por transacción pequeña | Permite superar 128 bloques sin aumentar el límite de operaciones de etcd. MAX_BLOCKS limita valores JSON. |
| R08 | Resultado idempotente por fd/cuerpo | Si se pierde la respuesta, el mismo cierre recupera la versión. Otro cuerpo para el mismo fd recibe 409. |
| R09 | GC por referencias, marca temporal y horizonte de capacidades | Nunca borra en el primer ciclo ni mientras snapshot/plan esté fijado. El borrado físico conserva tombstone si un nodo está caído. |
| R10 | Identidades por rol y dos CA; llaves firmantes separadas | Nodos/clientes no reciben KEK, contraseñas de bootstrap o credenciales etcd. gRPC exige mTLS. |
| R11 | Scrypt N=32768,r=8,p=3 y JWT EdDSA | Se mantiene hash de contraseña con sal; se elimina el secreto HMAC compartido entre usuario, nodos y capacidades. Cambio a validar por el equipo. |
| R12 | Hash canónico de manifiesto en todas las versiones | Complementa hashes de bloques y longitudes. No se confunde con SHA-256 global del texto plano, que solo se mantiene en put/w. |
| R13 | No migración automática del catálogo antiguo | El formato y las capacidades son incompatibles. Respaldar/exportar antes de instalar en volúmenes nuevos. |
| R14 | Evidencias históricas conservadas, nuevos runs separados | El CSV incompatible no se retoca ni se usa para generar conclusiones de la revisión. Solo mediciones reales nuevas se publican como tales. |

Estado: implementado, con pruebas locales y registros aportados de AWS Academy del 6 de noviembre de 2026
(regresión, caídas de servicios y benchmark). La ratificación del equipo y las aprobaciones de cambios de alcance
deben registrarse cuando correspondan; las comparaciones 4/8 MiB y 3/4 nodos siguen pendientes.
