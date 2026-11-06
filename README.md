# Proyecto Nube — DFSha

Proyecto universitario de sistema de archivos distribuido, opción cliente/servidor S2S.

## Carpetas

- [`dfsha/`](dfsha/README.md): aplicación, contratos, configuración, pruebas e instrucciones de ejecución.
- `informe/`: comparación de propuestas, decisiones y generador del informe grupal.
- `CAMBIOS_CORRECCIONES_DFSHA.md`: correcciones técnicas y límites de la validación realizada.
- [`COMMITS_EQUIPO.md`](COMMITS_EQUIPO.md): integración de los módulos y revisiones por integrante.

La arquitectura tiene dos coordinadores equivalentes, tres miembros etcd/Raft y cuatro nodos de datos.
El repositorio contiene el cliente, control, datos, contratos y configuración. Además de pruebas locales,
incluye registros y capturas aportados de AWS Academy del 6 de noviembre de 2026: regresión de 19 casos,
caídas de servicios y benchmark completo. No se confunden esas corridas con las pruebas locales previas.

## Integración del repositorio

Los módulos ya se integraron mediante commits separados de los tres participantes. `COMMITS_EQUIPO.md`
conserva el plan de integración original; para ejecutar la versión actual se utiliza `dfsha/README.md`.

## Secretos y contribuciones

Nunca subir `.env`, `meta.env`, `certs/`, llaves SSH, certificados privados o archivos binarios de prueba.
Las instrucciones generan credenciales de laboratorio localmente. El ZIP de intercambio tampoco los incluye.

Cada integrante debe revisar, probar y describir sus aportes reales al integrar el prototipo asistido.
La fecha/autor de un commit de integración no se presenta como prueba de una autoría previa que no se verificó.
