# Preparación de la defensa

La defensa es individual aunque el producto sea grupal: el profesor puede preguntar a cualquiera
sobre cualquier componente. Regla de oro: cada integrante explica la arquitectura completa y solo
entra en detalle en lo que le tocó revisar. Nadie lee diapositivas ni respuestas memorizadas.

## Respuestas de 30 segundos

### ¿Por qué la opción 1 y no un diseño tipo HDFS?

Porque la opción asignada es cliente/servidor S2S y el prototipo ya separa control y datos. El
cliente hace partición y cifrado; dos APIs equivalentes concentran metadatos; cuatro nodos guardan
bloques y se comunican entre sí. Se parece a HDFS en separar metadatos de datos, pero no se copia su
modelo de un único NameNode: aquí hay dos coordinadores y consenso con etcd.

### ¿Por qué dos APIs y tres etcd?

Dos APIs evitan un único punto de fallo en el plano de control; ambas son equivalentes y comparten
catálogo. Tres etcd permiten tolerar una caída manteniendo cuórum (2 de 3). Con dos coordinadores no
se necesita que ambos estén vivos para leer el catálogo, y el cliente reintenta contra el otro
endpoint lógico.

### ¿Por qué cuatro nodos de datos?

Con R=3 se necesitan al menos tres copias por bloque; el cuarto nodo permite seguir aceptando
escrituras y reparando cuando uno se cae, sin bajar de dos réplicas disponibles. Menos nodos
obligarían a R=2 o a degradar disponibilidad.

### ¿Qué significa exactamente “escritura confirmada”?

Que el cierre publicó la versión con al menos dos recibos Ed25519 de nodos distintos, que el
coordinador verificó identidad, plan, bloque, operación, tamaño y hash, y que el CAS de sesión y
referencias tuvo éxito. Antes de eso, los bloques son temporales o no publicados.

### ¿Es linealizable?

No se declara linealizable. Se ofrece consistencia por bloque: lectores trabajan sobre un snapshot
con lease; escritores usan locks por bloque y reciben 409 si la base cambió desde `open`. La
publicación es un CAS sobre el catálogo. Es una garantía comprobable y más débil que linealizabilidad
global, y así se dice en el informe.

### ¿Qué pasa si se cae un nodo de datos?

El monitor deja de recibir latidos firmados: sospechoso a los 10 s, caído a los 30 s. Las lecturas
usan las réplicas vivas del snapshot; el monitor repara el nodo con el hash autorizado del catálogo.
Si el nodo vuelve con contenido distinto, no se registra como reparado.

### ¿Y si se pierde el cuórum de etcd?

Las operaciones de catálogo fallan cerrado con 503. No se aceptan escrituras “a medias” ni se inventa
un catálogo local. Al volver el cuórum, el servicio se recupera.

### ¿El cliente confía en lo que dicen los nodos?

No. Cada nodo firma su recibo y el coordinador exige dos firmantes distintos. Un recibo duplicado o
falso recibe 409 `BAD_RECEIPT` y no se publica. El cliente tampoco puede declarar W por su cuenta: el
plan queda registrado por bloque.

## Preguntas por bloque

| Pregunta probable | Respuesta corta | Dónde mostrarlo |
|---|---|---|
| ¿Cómo se parte un archivo? | Bloques de 8 MiB; el último puede ser menor; `MAX_BLOCKS=8192` limita 64 GiB. | `common.py`, `client.py` |
| ¿Cómo se elige el nodo? | El coordinador devuelve destinos y capacidades; el cliente no conoce IPs. | `metadata.py` `open`/`manifest` |
| ¿Qué pasa si se reenvía el mismo bloque? | Es idempotente si el contenido coincide; si difiere, se rechaza. | `datanode.py` `WriteBlock` |
| ¿Cómo se evita un lector de un bloque borrado? | El GC espera gracia y vencimiento de capacidades, y revalida referencias antes de borrar. | `metadata.py` GC |
| ¿Cómo se libera un lock si el cliente muere? | El lease de la sesión vence a los 60 s y elimina sesión y locks juntos. | `metadata.py`, ADR R03 |
| ¿Por qué 423 y no 409 en `rm`/`rename`? | 423 indica recurso bloqueado por sesión activa; 409 se usa para conflicto de versión. | `metadata.py` |
| ¿`rename` es atómico? | Hasta 48 entradas por operación; por encima responde 413. | `metadata.py` `rename` |
| ¿`close` es idempotente? | Mismo `fd` y mismo cuerpo recuperan la versión publicada; otro cuerpo recibe 409. | `metadata.py` `close` |
| ¿Cómo se protege la KEK? | Solo se carga en coordinadores; nodos y clientes no la reciben. | `gen_certs.py`, `docker-compose` |
| ¿Qué contiene un certificado? | Identidad por servicio; la CA de etcd solo emite a miembros y coordinadores. | `scripts/gen_certs.py` |
| ¿Cómo se autentica un usuario? | Login con scrypt (N=32768, r=8, p=3) y JWT EdDSA de 15 min sobre TLS. | `metadata.py`, `common.py` |
| ¿Qué pasa si roban un nodo? | No obtiene KEK ni credenciales de etcd; solo ve bloques cifrados y su propia llave. | informe §7 |
| ¿El hash global se mantiene tras `rw`? | No: queda `null` y se dice explícitamente; se valida el manifiesto. | `dfsha/README.md` |
| ¿Por qué el p95 es el máximo? | Con cinco muestras el percentil por rango cercano cae en el máximo; no caracteriza colas. | informe §9 |
| ¿Por qué R=2 no duplica el rendimiento? | El cuello está en coordinación, cifrado y publicación, no solo en una réplica menos. | `summary.csv` |
| ¿Qué falta para AWS? | Despliegue real, caídas de VM, red privada, benchmark final y video. | informe §11 |

## Preguntas trampa y cómo salir

- **“Demuéstreme que esto corrió en AWS”.** No se puede: la versión está validada en Docker local.
  Mostrar `regression.json` con `environment: local Docker (no AWS)` y decir que el despliegue en
  Academy sigue pendiente. Inventar una captura sería peor que reconocerlo.
- **“¿Implementaron Raft?”.** No. Se usa etcd, que implementa Raft; el aporte es el contrato de
  metadatos, las capacidades y la verificación de recibos.
- **“¿Entonces el cifrado no sirve porque el servidor ve la DEK?”.** El modelo protege el canal, el
  almacenamiento en nodos y el acceso por rol; el coordinador descifra mientras atiende la sesión.
  No se promete cifrado extremo a extremo resistente al servidor.
- **“¿Por qué no hay pipeline paralelo?”.** La réplica S2S de esta revisión es secuencial desde un
  bloque validado; se declara como límite y como costo a medir, no como virtud.
- **“¿Cómo sé que el commit que subió es suyo?”.** Mostrar `git log --author` y explicar qué revisó,
  qué probó y qué cambió; el commit de carga no sustituye la explicación.
- **“¿Qué pasa con dos escritores en bloques distintos?”.** Avanzan en paralelo; el lock es por
  bloque. El conflicto aparece al publicar si la base cambió, y se resuelve reabriendo.
- **“¿Qué pasa si se cae el coordinador que atiende?”.** El cliente reintenta contra el otro endpoint
  con IDs estables; la sesión y el catálogo viven en etcd, no en memoria del proceso.
- **“¿Por qué no PostgreSQL como en otra propuesta?”.** Se comparó: PostgreSQL activo/pasivo no daba
  consenso de catálogo ni toleraba la caída del primario sin intervención. etcd/Raft ya resuelve
  elección y quórum; el equipo priorizó corrección y disponibilidad del catálogo.

## Demostración mínima para tener abierta

```bash
cd dfsha
docker compose -p dfsha-revision -f docker-compose.local.yml ps
docker compose -p dfsha-revision -f docker-compose.local.yml exec cliente python -m dfsha.cli nodes
docker compose -p dfsha-revision -f docker-compose.local.yml exec cliente python -m dfsha.cli stat /demo.bin
```

Y en el editor: `metadata.py` (`open_`, `close`, GC), `datanode.py` (`WriteBlock`), `client.py`
(`put`), `common.py` (`sign`, `verify_node`). Tener también abiertos `informe/ADR_REVISION.md` y
`summary.csv`.

## Ensayo

1. Ronda de 20 minutos: cada uno responde tres preguntas al azar de la tabla, sin mirar el informe.
2. Ronda de 10 minutos: explicar la figura de componentes en el tablero, en menos de dos minutos.
3. Ronda de 5 minutos: cada uno cuenta su aporte real y el de los compañeros, con commit y prueba.
4. Ajustar solo las respuestas que quedaron largas; no memorizar texto.

## Errores que bajan la nota

- Decir “está en AWS” sin despliegue.
- Confundir 409 (conflicto de versión) con 423 (recurso bloqueado) o con 503 (sin cuórum).
- Afirmar que el cliente guarda la KEK o que los nodos ven el texto plano.
- Presentar el benchmark de 5 muestras como caracterización de colas.
- No saber qué archivo o commit propio defender.
