# Evidencias de ejecución

## AWS Academy

Las siguientes carpetas contienen los registros aportados de ejecución en cuatro VMs EC2 t3.small:

| Carpeta | Contenido y alcance |
|---|---|
| `revision-20261106-023859/` | Regresión final: 19 casos, cero fallos/errores/omitidos, incluida la transferencia de 129 bloques con `RUN_LARGE=1`. |
| `revision-bench-20261106T022920Z-5b3b1b/` | Benchmark completo: 80 muestras, 16 condiciones y cinco repeticiones por condición. Incluye `samples.csv`, `summary.csv` y `run.json`. |
| `revision-failures-aws-abe1be38f48a/` | Detención/reinicio de dn1, meta1 y miembros etcd, lectura/escritura, reparación y rechazo por pérdida de cuórum. |
| `revision-bench-20261106T022424Z-4026b2/` | Corrida interrumpida previa a la corrección de reintentos. Estado `failed`; se conserva para trazabilidad, sin mezclarla con el benchmark completo. |

La regresión final y el benchmark completo declaran la misma huella de código:
`651c058b66f26fa9aecccc7268d285a3af3afef8cc621da424083131ce6eb3ea`.

Los resúmenes se reconstruyen desde las muestras. Con cinco repeticiones, el p95 por rango más cercano es el máximo
observado. Las caídas detienen contenedores dentro de VMs reales, no las instancias EC2 completas.

## Comprobaciones locales complementarias

`revision-checks-20261103T064125Z/checks.json` conserva los comandos y salidas de pruebas de contrato/estadística,
aislamiento de paquetes, configuración Compose y rechazo mTLS. Identifica el entorno local y corresponde a esa
versión de desarrollo; no se presenta como una ejecución AWS ni se mezcla con sus métricas.

## Repetir pruebas

Las instrucciones están en el README de la aplicación. Los scripts crean un directorio nuevo por ejecución;
conservar entorno, configuración, huella de código y muestras para vincular cada resultado con la versión probada.
Los ensayos antiguos y respaldos internos se archivaron fuera de la entrega. El informe final utiliza las evidencias
AWS listadas arriba y las nueve figuras conservadas en su carpeta de fuentes.
