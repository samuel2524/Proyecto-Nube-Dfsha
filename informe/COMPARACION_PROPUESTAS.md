# Comparación revisada de las tres propuestas individuales

Fuentes cotejadas: `ANDRES.pdf` (10 páginas), `GARCIA.pdf` (12 páginas) y
`Proyecto1_Individual.pdf`/Word de Samuel. Los archivos originales deben acompañar
el registro del equipo; esta comparación no inventa acuerdos ni aprobación del profesor.

| Criterio | Andrés | García | Samuel | Síntesis de la revisión |
|---|---|---|---|---|
| Control | Dos APIs sin estado + etcd/Raft de tres miembros (§3) | PostgreSQL 16, activo/pasivo sujeto al tiempo (§8.5) | Tres coordinadores + etcd/Raft (§2) | Dos APIs equivalentes y tres etcd en VMs diferentes. Base de Andrés, coincidente con HA propuesta por Samuel. |
| Datos | Cuatro nodos, S2S en cadena (§§3–4) | Tres nodos; propone S2S pero sus secuencias también envían la segunda copia desde cliente (§§2.3,3.1) | Cuatro nodos y réplica S2S (§§2–3) | Cuatro nodos; el cliente manda una copia y el nodo replica después de validarla. Ya no se promete pipeline solapado. |
| Bloques | 8 MiB (§4) | 4 MiB y justificación de memoria/amplificación (§4.2) | 4 MiB (§3.1) | Se conserva 8 MiB; falta comparación experimental 4/8 para afirmar una mejora. |
| Réplicas | R=3/W=2 (§7) | R=2, confirman ambas (§6.3) | R=3/W=2 (§3.3) | R=3/W=2, con recibos firmados de dos nodos distintos. R=2 solo experimento explícito. |
| Locks | Por bloque, lease/fencing (§7) | Por bloque y versión esperada (§6.4) | Por archivo y CAS (§5) | `rw`: lock fino y versión esperada del bloque. `w/a`: exclusión de estructura por archivo. |
| Lectores | Snapshot y gracia de diez minutos al borrar (§§6,10.5) | Manifiesto estable (§6.3) | Lectores con vigencia renovable (§5.3) | Leases lectores renovables, manifiestos versionados y GC por referencias, no solo por tiempo. |
| Publicación | Tabla API separa commit/close pero semántica los une (§§5.1,6) | Versión esperada y publicación confirmada (§6.3) | Transacción de bloqueo/versión base (§5.3) | Se elige publicar en close; resultado recuperable por operación y transacción acotada. |
| Integridad | SHA por bloque/global, GCM (§§4,7) | SHA por bloque/global y reconciliación (§§4.5,8.4) | SHA por bloque/global (§3.5) | Hash de bloque cifrado, GCM, hash de manifiesto; hash plano global en put/w. No se afirma recalcularlo en rw/a. |
| Seguridad | Argon2id, RS256, DEK/KEK, mTLS (§9) | Argon2id, RS256, DEK/KEK y AAD (§9) | Argon2id, TLS/mTLS, AES-GCM (§7) | scrypt parametrizado, firmas Ed25519 separadas, CA de catálogo aislada y KEK solo en metadatos. Requiere revisión del equipo/profesor. |
| Pruebas | Cinco repeticiones; 1 GiB; 3/4 nodos (§11) | Calentamiento y 30 mediciones (§10) | Cinco repeticiones y métricas de fallos (§8) | Regresión con aserciones, 129 bloques, fallos locales y muestras crudas; repetir y completar en AWS. |

## Decisiones y consecuencias

- Elegir la topología de Andrés es defendible por HA y paralelismo; no significa que su propuesta resuelva todos los casos.
- La versión esperada de García y los leases lectores de Samuel corrigen pérdidas importantes del primer prototipo.
- S2S, snapshots y W=2 son coincidencias entre propuestas; no se atribuyen artificialmente a una sola persona.
- No hay obligación de conservar cuotas, POSIX completo o anexado. Si el equipo mantiene append, debe mantener su exclusión de estructura.
- La consigna no exige un algoritmo concreto de contraseñas o firma, pero sí protección real y justificación de cambios.

## Acuerdo pendiente, sin simulación de consenso

- [ ] Los tres revisaron el contrato y los límites de la revisión.
- [ ] Confirmaron 8 MiB o acordaron repetir comparación 4/8 MiB.
- [ ] Confirmaron locks finos + exclusión de w/a y errores por base vieja.
- [ ] Revisaron seguridad y cambios frente a sus propuestas.
- [ ] Solicitaron y registraron aprobación de simplificaciones cuando corresponda.
- [ ] Registraron aportes, pruebas y decisiones mediante commits/PR reales.

Fecha, participantes, enlaces y conclusión: **por completar por el equipo**, no por la herramienta.
