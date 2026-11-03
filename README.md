# Proyecto Nube — DFSha

Proyecto universitario de sistema de archivos distribuido, opción cliente/servidor S2S.

## Carpetas

- [`dfsha/`](dfsha/README.md): aplicación, contratos, configuración, pruebas e instrucciones de ejecución.
- `informe/`: comparación de propuestas, decisiones y generador del informe grupal.
- `CAMBIOS_CORRECCIONES_DFSHA.md`: correcciones técnicas y límites de la validación realizada.
- [`COMMITS_EQUIPO.md`](COMMITS_EQUIPO.md): integración de los módulos y revisiones por integrante.

La arquitectura tiene dos coordinadores equivalentes, tres miembros etcd/Raft y cuatro nodos de datos.
Las correcciones se probaron en Docker local; el despliegue y las evidencias finales deben repetirse en AWS Academy.
No se presenta la ejecución local como una validación de AWS.

## Integración del repositorio

Los módulos se incorporan mediante commits separados. Los primeros dos corresponden a cliente/CLI y
pruebas/documentación; los módulos restantes se integran siguiendo `COMMITS_EQUIPO.md`.
Un clon intermedio no es todavía la entrega ejecutable completa: comprobar que se hayan integrado control,
datos, contratos y configuración antes de construir el clúster.

## Secretos y contribuciones

Nunca subir `.env`, `meta.env`, `certs/`, llaves SSH, certificados privados o archivos binarios de prueba.
Las instrucciones generan credenciales de laboratorio localmente. El ZIP de intercambio tampoco los incluye.

Cada integrante debe revisar, probar y describir sus aportes reales al integrar el prototipo asistido.
La fecha/autor de un commit de integración no se presenta como prueba de una autoría previa que no se verificó.
