# Preparación de la defensa grupal e individual

Responder con el contrato actual y las evidencias AWS del 6 de noviembre de 2026.
La suite final aportada reporta 19 casos sin fallos, errores u omitidos; el benchmark completo tiene 80 muestras.
Todos deben poder explicar cualquier componente, no solo la carpeta que integraron.

## Preguntas principales

### ¿Qué arquitectura escogimos y por qué?

Cliente/servidor S2S con control y datos separados. Dos APIs equivalentes comparten un catálogo etcd/Raft de
tres miembros; cuatro nodos almacenan bloques. La base de Andrés facilita HA del catálogo y paralelismo,
reforzada por versión esperada de García y sesiones lectoras renovables de Samuel. Se tomó una combinación
de mecanismos; ninguna propuesta se considera perfecta por sí sola.

### ¿Qué relación tiene con HDFS?

La separación de metadatos y transferencia de datos es una referencia común. DFSha usa etcd/Raft para su catálogo
y un contrato propio de sesiones, capacidades y recibos. HDFS no es una alternativa a la opción 1: también es un
sistema distribuido cliente/servidor. No reducir HDFS moderno a un único NameNode sin alta disponibilidad.

### ¿Por qué dos coordinadores y tres etcd?

Un coordinador disponible puede atender solicitudes. Los tres etcd votan y requieren mayoría de dos para operar;
no hay un cuórum de dos coordinadores. El cliente puede cambiar al otro endpoint de control.

### ¿Por qué cuatro nodos de datos?

Tres nodos permiten R=3 inicialmente, pero si uno cae solo quedan dos para almacenar copias. El cuarto permite
restaurar tres copias en nodos vivos tras una caída. No decir que tres nodos obligan a R=2 en operación normal.

### ¿Cuándo se confirma una escritura?

Cuando los bloques afectados están preparados con dos recibos persistentes de nodos distintos verificados por el
coordinador y el cierre publica el manifiesto mediante CAS. Los recibos solos no hacen visible una versión.

### ¿Qué evita una base vieja?

Al adquirir el lock de un bloque en rw, se compara su ID actual con el observado en open. Si cambió, se devuelve
409 VERSION_CONFLICT y el cliente debe reabrir/releer. Bloques distintos pueden avanzar y fusionarse al publicar;
no hay que rechazar una escritura solo porque cambió otro bloque del archivo.

### ¿Cuál es la consistencia ofrecida?

Catálogo consistente mediante etcd, publicación atómica y lecturas sobre un snapshot fijado en open. Las aperturas
posteriores a la confirmación ven la versión nueva. No se presume semántica POSIX completa ni linealizabilidad
global de todas las operaciones sin una especificación y verificación formal adicionales.

### ¿Qué ocurre si desaparece un cliente?

Su sesión y locks comparten un lease de 60 s renovado cada 10 s. Al vencer no puede publicar. El lector que deja
de renovar pierde el derecho a retener indefinidamente su snapshot. La gracia del GC complementa las referencias;
no las reemplaza.

### ¿Qué fallos se probaron en AWS?

Detención de dn1, de meta1, de un miembro etcd y luego de dos miembros. Se comprobaron lectura/escritura con
réplicas disponibles, reparación, uso del otro coordinador, 503 sin cuórum y lectura posterior al restaurar.
Se detuvieron contenedores, no instancias EC2 completas ni discos.

### ¿Cuánto tardó la reparación?

La primera confirmación exitosa aparece unos 41,4 s después de finalizar el comando que detuvo dn1. Incluye
detección y espera entre sondeos; no es el tiempo puro de copia ni el instante exacto de restauración.
Los 6,83 s sumados de consultas fallidas no son una medición válida de ese intervalo.

### ¿Ya se demostró AWS?

Se aportaron capturas de servicios y operaciones entre cuatro VMs, regresión de 19 casos, registro de fallos y
benchmark completo con muestras. Mostrar esa evidencia y explicar cómo se produjo. No usar la corrida local como
si fuera AWS y no afirmar que una captura garantiza propiedades que la prueba no ejercitó.

## Respuestas técnicas breves

| Tema | Respuesta |
|---|---|
| Tamaño de bloque | Hasta 8 MiB; último menor. No se probó aún superioridad frente a 4 MiB. |
| R y W | R=3 objetivo; W=2 recibos persistentes distintos para preparar. R=2 solo comparación declarada. |
| Recibo falso | El coordinador valida firma, nodo, bloque, operación, tamaño y hash; rechaza con BAD_RECEIPT. |
| Inmutabilidad | Un ID publicado no cambia de contenido. Cada modificación crea otro bloque. |
| w/rw/a | w trunca, rw modifica por bloques y a anexa. w/a excluyen otros escritores. |
| rm/rename | 423 mientras haya escritores activos; lectores previos pueden conservar snapshot vigente. |
| Cierre repetido | Mismo fd/cuerpo devuelve resultado ya publicado; otro cuerpo recibe conflicto. |
| RETRY | Se reintenta con el mismo pedido y espera aleatoria acotada. VERSION_CONFLICT no se oculta. |
| Protección de claves | Cliente y nodos no reciben KEK ni credenciales del catálogo. |
| DEK | El coordinador la entrega al cliente autorizado; el modelo confía en ese servicio. |
| Hash global tras rw/a | No se recalcula; se declara null. Se mantienen hashes de bloques y manifiesto y GCM. |
| P95 | Con cinco muestras y rango cercano, es el máximo de la muestra. |
| Rendimiento | Exponer tasas medidas; no atribuir CPU/red como causa concluyente sin instrumentación. |
| Límite de metadatos | El epoch global prioriza corrección, pero causa contención y debe medirse bajo carga. |
| Comparación pendiente | 3/4 nodos, 4/8 MiB y recursos; variar clientes no equivale a variar nodos. |

## Ensayo

1. Cada uno explica la figura de componentes y una secuencia completa de escritura en dos minutos.
2. Otro integrante pregunta por un fallo: base vieja, ACK falso, lease vencido, bloque parcial o pérdida de cuórum.
3. Mostrar un comando y su salida esperada; distinguir 401, 403, 404, 409, 423 y 503.
4. Relacionar cada resultado del informe con su prueba y las limitaciones de esa evidencia.
5. Revisar contribuciones reales y tener el repositorio y el video accesibles al profesor.
