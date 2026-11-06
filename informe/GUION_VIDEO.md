# Guion del video demostrativo (10 a 15 minutos)

El video muestra la arquitectura y la ejecución distribuida en las cuatro VMs de AWS Academy.
Usar los resultados del 6 de noviembre de 2026: regresión de 19 casos y benchmark completo de 80 muestras.
Las pruebas locales anteriores sirven para desarrollo, no se presentan como si fueran AWS.

## Preparación

1. Iniciar el Learner Lab, verificar las cuatro instancias y las IP actuales.
2. Abrir dos sesiones SSH al bastión y una terminal del administrador para controlar servicios.
3. En cada terminal del bastión, preparar el cliente Bash:

   ```bash
   cd ~/dfsha
   export CERTS="$PWD/certs/cliente"
   export CA_CERT="$PWD/certs/cliente/ca.crt"
   export DFSHA_META=https://meta1.dfsha.internal:8443,https://meta2.dfsha.internal:8443
   dfsha() { .venv/bin/python -m dfsha.cli "$@"; }
   ```

4. Consultar salud con el rol correcto y regresar al usuario de la demo:

   ```bash
   dfsha login admin admin123
   dfsha nodes
   dfsha login andres clave123
   ```

5. Mostrar las figuras y tablas del informe, con zoom legible. Tener disponible el resumen AWS final:

   ```bash
   cat resultados/revision-20261106-023859/regression.json
   cat resultados/revision-bench-20261106T022920Z-5b3b1b/summary.csv
   ```

Las contraseñas de ejemplo corresponden al laboratorio. Si cambiaron al desplegar, usar las reales sin mostrar
claves de AWS, llaves privadas ni el contenido de archivos de secretos. La CLI comparte el estado de login
entre las sesiones SSH del mismo usuario Linux: no cambiar de usuario durante la demo concurrente.

## Distribución sugerida

| Tiempo | Responsable | Contenido |
|---|---|---|
| 0:00 a 1:00 | Juan José | Objetivo, opción 1 y entorno AWS |
| 1:00 a 3:00 | Andrés | Arquitectura, metadatos y elección de propuestas |
| 3:00 a 6:00 | Samuel | Carga/descarga, hashes, lectura y modificación |
| 6:00 a 9:00 | Juan José | Concurrencia y seguridad |
| 9:00 a 12:00 | Andrés | Caída, reparación, failover y cuórum |
| 12:00 a 14:00 | Samuel | Métricas, límites y resultados |
| 14:00 a 15:00 | Los tres | Contribuciones y cierre |

## 1. Presentación

Explicar con sus palabras:

> DFSha es un sistema de archivos distribuido cliente/servidor con comunicación S2S. Separamos control y datos:
> dos coordinadores organizan operaciones sobre un catálogo etcd de tres miembros y cuatro nodos almacenan
> los bloques. Mostramos la ejecución en AWS Academy y las pruebas registradas por el equipo.

Mostrar servicios y direcciones privadas de las cuatro VMs. La presencia de contenedores encendidos se
complementa con operaciones entre nodos; por sí sola no demuestra integridad ni disponibilidad.

## 2. Arquitectura

Recorrer las figuras 1 y 2 del informe:

- Cliente a coordinadores por HTTPS; transferencia directa de bloques por gRPC/mTLS.
- Dos APIs equivalentes; el cuórum está en los tres miembros etcd, no entre las dos APIs.
- Bloques de hasta 8 MiB, tres copias objetivo y dos recibos firmados distintos para preparar cada bloque.
- El cierre publica la versión mediante CAS; recibir dos ACK no publica automáticamente el archivo.
- rw permite bloques distintos en paralelo y comprueba la versión base; w/a son exclusivos entre escritores.
- El lector mantiene un snapshot con lease renovable; el GC respeta referencias vigentes.
- S2S es secuencial desde un bloque validado. No afirmar que la réplica está solapada en pipeline.

Explicar el aporte de las propuestas: base de Andrés, validación de base de García y retención por sesiones
lectoras de Samuel. Las decisiones coincidentes, como S2S y snapshots, se reconocen como coincidencias.

## 3. Operaciones funcionales

En el bastión:

```bash
dfsha login andres clave123
dfsha mkdir /video
head -c 10485760 /dev/urandom > /tmp/demo.bin
dfsha put /tmp/demo.bin /video/demo.bin
dfsha stat /video/demo.bin
dfsha get /video/demo.bin /tmp/salida.bin
sha256sum /tmp/demo.bin /tmp/salida.bin
cmp /tmp/demo.bin /tmp/salida.bin
dfsha write /video/notas.txt 0 'hola mundo'
dfsha write /video/notas.txt 5 'MUNDO'
dfsha append /video/notas.txt ' desde AWS'
dfsha cat /video/notas.txt
```

Un archivo de 10 MiB tiene dos bloques a esta configuración: 8 MiB y 2 MiB, antes del overhead de cifrado.
Los hashes de origen y destino deben coincidir. Mostrar que el estado lista ubicaciones en varios nodos.
Si `/video` ya existe, explicar el 409 o utilizar una ruta nueva; no ocultar fallos inesperados.

## 4. Concurrencia y seguridad

Con el mismo usuario de aplicación en las dos terminales:

```bash
# Terminal A
dfsha write /video/demo.bin 0 'CLIENTE-A' --mantener 12

# Terminal B, mientras A mantiene el lock
dfsha write /video/demo.bin 0 'CLIENTE-B'
```

Esperado: `423 BLOCK_LOCKED`. En otro intento con `--esperar`, si A publicó desde el open de B,
B puede recibir `409 VERSION_CONFLICT`: debe reabrir/releer. No explicar ese conflicto como
una pérdida de datos. La prueba registrada de bloques distintos muestra que ambos cambios se conservan.

Para seguridad, ejecutar la secuencia cuando ya terminaron los escritores:

```bash
dfsha logout
dfsha ls /
dfsha login laura clave123
dfsha stat /video/demo.bin
dfsha nodes
dfsha login andres clave123
```

Resultados: 401 sin sesión, 404 para archivo ajeno y 403 al consultar administración sin rol admin.
Mostrar la captura de mTLS/tokens y explicar que KEK y credenciales etcd no están en el cliente.

## 5. Fallos y reparación

Desde el administrador, detener únicamente el servicio previsto:

```bash
ssh -i "<llave.pem>" ubuntu@<IP_VM1> 'sudo docker stop dfsha-dn'
```

En el bastión, recuperar y comparar el archivo. La consulta de nodos requiere iniciar sesión como admin;
debe observarse la transición: sospechoso a los 10 s y caído a los 30 s, no inmediatamente.
Mostrar después la reparación con tres réplicas válidas sin dn1, y restaurar:

```bash
ssh -i "<llave.pem>" ubuntu@<IP_VM1> 'sudo docker start dfsha-dn'
```

Para respetar el tiempo del video, usar también el registro completo ya ejecutado: caída de meta1,
un miembro etcd y pérdida de cuórum al detener dos miembros, con 503 y lectura correcta al restaurar.
Decir que se detuvieron contenedores de servicios en VMs reales; no afirmar que se apagó una VM completa.

**Métrica que se explica:** la primera sonda exitosa se obtuvo aproximadamente 41,4 s después de finalizar
la detención de dn1. Incluye detección y esperas. No decir que la reparación tardó exactamente siete segundos
ni que se conoce el instante exacto entre consultas.

## 6. Métricas y límites

Usar la tabla AWS del informe:

- 500 MiB: aproximadamente 30,2 MiB/s de escritura y 96,5 MiB/s de lectura.
- R=2/W=2: 37,2 MiB/s; R=3/W=2: 31,4 MiB/s. Describir la reducción medida, sin extrapolar a algoritmos no probados.
- Escritura agregada con un cliente: 29,5 MiB/s; con ocho: 19,0 MiB/s. La contención es una explicación
  compatible con RETRY, pero no se midió por separado CPU, NIC, disco o tiempo de reintentos.
- Cinco repeticiones por condición: el p95 por rango cercano es el máximo observado.
- Se conserva la corrida fallida y la corrección posterior; no se mezclan con la corrida completa.

Pendiente experimental: 4/8 MiB, 3/4 nodos y métricas de recursos. El video no debe anunciar esas comparaciones como hechas.

## Cierre

Cada integrante explica su integración y revisión registrada en Git. Los tres deben defender cualquier componente.
El enlace del video final debe quedar accesible al profesor. Un guion o una captura de un archivo JSON no reemplazan
la demostración distribuida y la explicación de las garantías.
