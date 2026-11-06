# Guion del video demostrativo (10–15 minutos)

El video debe mostrar arquitectura, ejecución distribuida, fallos y resultados medidos. No se puede
presentar la corrida local como si fuera AWS: si la entrega se graba antes de desplegar en Academy,
se dice explícitamente y se muestran los registros versionados como evidencia local.

## Antes de grabar

1. Docker Desktop corriendo y el repo clonado en `Proyecto-Nube-Dfsha/`.
2. Clúster levantado y sano:

   ```bash
   cd dfsha
   docker build -t dfsha:revision .
   docker run --rm -v "$PWD:/workspace" -w /workspace dfsha:revision python scripts/init_local.py
   docker compose -p dfsha-revision -f docker-compose.local.yml up -d --no-build
   docker compose -p dfsha-revision -f docker-compose.local.yml exec cliente python -m dfsha.cli login andres clave123
   docker compose -p dfsha-revision -f docker-compose.local.yml exec cliente python -m dfsha.cli nodes
   ```

   En PowerShell, el `docker run` de inicialización usa:

   ```powershell
   docker run --rm --mount "type=bind,source=$((Get-Location).Path),target=/workspace" --workdir /workspace dfsha:revision python scripts/init_local.py
   ```

3. Cuatro terminales abiertas: `A` para comandos del cliente, `B` para `docker compose stop/start`,
   `C` para logs (`docker compose logs -f meta1`), `D` para el editor con el código.
4. Tener abiertos de antemano: `informe/figuras/componentes_revision.png`,
   `dfsha/resultados/revision-bench-20261103T062822Z-73ae1d/summary.csv` y
   `dfsha/resultados/revision-20261103T062535/regression.json`.
5. Grabar a 1080p, micrófono cerca, notificaciones silenciadas y zoom del editor en 120 %. Duración
   objetivo: 13 minutos. Ensayar una vez completo antes de la toma final.

## Reparto

| Bloque | Quién | Minutos |
|---|---|---|
| Presentación y alcance | Juan José | 1:00 |
| Arquitectura y decisiones | Andrés | 2:30 |
| Recorrido de código | Samuel | 2:30 |
| Demo funcional | Juan José | 3:00 |
| Fallos y consistencia | Andrés | 3:00 |
| Métricas y límites | Samuel | 2:00 |
| Cierre y contribuciones | Juan José | 1:00 |

Todos deben poder responder por cualquier bloque; el reparto es solo para ordenar la grabación.

## Bloque 1 — Presentación (0:00–1:00)

Decir, sin leer:

> Somos Andrés, Juan José y Samuel. Este es el proyecto DFSha, opción 1: cliente/servidor con
> comunicación servidor a servidor. El video muestra la arquitectura, una ejecución real del clúster,
> qué pasa cuando se cae un nodo y las mediciones que quedaron registradas. Aclaramos desde ya que la
> validación de esta versión es local, en Docker; el despliegue en AWS Academy está pendiente y no lo
> vamos a presentar como hecho.

Mostrar en pantalla el árbol del repo (`README.md`, `dfsha/`, `informe/`) y el commit propio.

## Bloque 2 — Arquitectura (1:00–3:30)

Mostrar `informe/figuras/componentes_revision.png` y recorrer de izquierda a derecha:

- El cliente no conoce direcciones de nodos: habla con dos APIs equivalentes por REST/HTTPS.
- Las dos APIs comparten catálogo en tres etcd con Raft. Con dos de tres hay cuórum; al perder dos,
  las operaciones fallan cerrado.
- Hay cuatro nodos de datos. Cada bloque se parte a 8 MiB y se replica a tres nodos; el cierre exige
  dos recibos firmados por nodos distintos.
- El plano de datos usa gRPC con mTLS. La capacidad la firma el coordinador y cada nodo devuelve un
  recibo Ed25519 con bloque, operación, tamaño y hash.
- La KEK solo se carga en los coordinadores. El cliente cifra con una DEK por archivo y nunca recibe
  credenciales de etcd.

Justificar en una frase: dos APIs para no depender de un coordinador único, tres etcd para tolerar
una caída manteniendo consenso, cuatro nodos para sostener R=3 y seguir leyendo con uno caído.

## Bloque 3 — Recorrido de código (3:30–6:00)

Mostrar tres puntos cortos, sin perderse en funciones auxiliares:

1. `dfsha/dfsha/client.py`, `put()`: parte el archivo, cifra cada bloque con AES-256-GCM usando el
   `block_id` como AAD, pide capacidades y sube en paralelo.
2. `dfsha/dfsha/datanode.py`, `WriteBlock()`: valida capacidad, tamaño y hash; escribe temporal,
   sincroniza a disco, replica al siguiente nodo y solo entonces firma el recibo.
3. `dfsha/dfsha/metadata.py`, `open_()` y `close()`: snapshot con lease, locks por bloque, CAS de
   sesión y publicación con al menos dos recibos verificados.

Mencionar `dfsha/proto/dfsha.proto` como contrato explícito: `WriteBlock`, `ReadBlock`,
`ReplicateBlock`, `DeleteBlock`, `ListBlocks`.

## Bloque 4 — Demo funcional (6:00–9:00)

En la terminal `A`, con el alias `dc="docker compose -p dfsha-revision -f docker-compose.local.yml"`:

```bash
# archivo de 10 MiB dentro del contenedor
dc exec -T cliente python -c "import os;open('/tmp/demo.bin','wb').write(os.urandom(10*1024*1024))"

# subir y ver el reparto
dc exec -T cliente python -m dfsha.cli put /tmp/demo.bin /demo.bin
dc exec -T cliente python -m dfsha.cli stat /demo.bin

# recuperar y comparar hash
dc exec -T cliente python -m dfsha.cli get /demo.bin /tmp/salida.bin
dc exec -T cliente sh -c "sha256sum /tmp/demo.bin /tmp/salida.bin"
```

Salida esperada: `put 10.00 MiB en 2 bloques ... sha256 <hash>`, un `stat` con dos bloques y tres
réplicas por bloque, y dos hashes iguales en `sha256sum`.

Concurrencia, en dos terminales:

```bash
# terminal 1: sostiene el lock 20 s
dc exec -T cliente python -m dfsha.cli lock /demo.bin 0 1 --segundos 20

# terminal 2: debe responder 423 FILE_BUSY
dc exec -T cliente python -m dfsha.cli write /demo.bin 0 X
```

Explicar: el lock es por bloque; bloques distintos pueden avanzar en paralelo, pero `rm`/`mv` sobre
un archivo con escritores activos responde 423 hasta que cierren o venza el lease.

## Bloque 5 — Fallos y consistencia (9:00–12:00)

Terminal `B`:

```bash
dc stop dn1
dc exec -T cliente python -m dfsha.cli nodes
dc exec -T cliente python -m dfsha.cli get /demo.bin /tmp/tras-fallo.bin
dc start dn1
```

Mostrar que `nodes` marca `dn1 caído`, que la lectura sigue funcionando con las otras réplicas y que
al volver el nodo el monitor lo repara con el hash autorizado.

Luego, cuórum:

```bash
dc stop etcd1
dc exec -T cliente python -m dfsha.cli put /tmp/demo.bin /con-etcd1-caido.bin   # funciona: 2 de 3
dc stop etcd2
dc exec -T cliente python -m dfsha.cli put /tmp/demo.bin /sin-cuorum.bin        # 503
dc start etcd1 etcd2
```

Cerrar el bloque con la regla: una escritura se considera confirmada cuando el cierre publica la
versión con dos recibos distintos y el CAS de sesión; con pérdida de cuórum se falla cerrado, no se
promete disponibilidad.

## Bloque 6 — Métricas (12:00–14:00)

Abrir `summary.csv` y explicar la tabla del informe:

- E1, R=3: put 0.99 s y 10.3 MiB/s; get 0.53 s y 20.1 MiB/s.
- E2, R=2 frente a R=3 con W=2: el put mejora cerca de 7 %, no es el doble.
- E3, dos clientes: la tasa agregada sube (14.8 MiB/s en put), pero la latencia por operación también;
  no se presenta como escalabilidad lineal.
- Cinco repeticiones: el p95 es el máximo observado, sirve como prueba de humo, no para caracterizar
  colas.

Cerrar con lo que falta medir en AWS: 10/100/500 MiB y borde 1 GiB, comparación 3/4 nodos, 4/8 MiB en
clústeres separados, CPU/memoria/disco/NIC y tiempo de reparación.

## Bloque 7 — Cierre (14:00–15:00)

- Límites: catálogo v2 sin migración, `MAX_BLOCKS=8192`, rename atómico hasta 48 entradas, época
  global que prioriza corrección sobre paralelismo masivo, réplica secuencial.
- Evidencia: `regression.json` con 16 casos y hash `9632b34f...`, seis chequeos, registro de caídas y
  benchmark con muestras crudas.
- Contribuciones: cada integrante muestra su commit en GitHub.
- Pendiente real: AWS Academy, video final y ratificación del equipo.

## Frases que no se deben decir

- “Esto ya corrió en AWS” si no está desplegado.
- “Es linealmente escalable” o “no tiene cuello de botella”.
- “Raft lo implementamos nosotros”: se usa etcd, no se reimplementa consenso.
- “El pipeline replica en paralelo”: la réplica de esta revisión es secuencial.
- “Los datos están cifrados de extremo a extremo sin confiar en el servidor”: el coordinador ve la
  DEK mientras atiende la sesión; el cliente no entrega la KEK.

## Plan B si algo falla en vivo

- Si Docker no arranca: mostrar `docker version` con el error, pasar a los registros versionados y
  explicar los comandos que los generaron. No improvisar una corrida falsa.
- Si un contenedor queda inestable: `docker compose -p dfsha-revision -f docker-compose.local.yml ps`
  y `logs --tail 50 <servicio>`; si no se recupera, reiniciar el proyecto y continuar desde el bloque 5.
- Si el archivo de 10 MiB tarda: bajar a 2 MiB y decir el tamaño real que se está usando.

## Checklist de edición

- [ ] Audio inteligible y sin cortes entre bloques.
- [ ] Se ve el comando y la salida completa (no solo el resultado).
- [ ] Los hashes de `put`/`get` coinciden en pantalla.
- [ ] Se muestra al menos una caída de nodo de datos y una de etcd.
- [ ] Se muestra el `summary.csv` real, no una tabla inventada.
- [ ] Se aclara local vs AWS al inicio y al cierre.
- [ ] Exportar en 1080p como `DFSha_FaseII_Video_Grupo.mp4` y subirlo al enlace de entrega.
