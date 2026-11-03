# Repositorio y contribuciones verificables

La consigna exige un repositorio GitHub accesible, código reproducible y aportes identificables.
La integración actual se organiza en dos commits de Samuel y dos bloques pendientes por compañero.
Ver [COMMITS_EQUIPO.md](COMMITS_EQUIPO.md) para las rutas, comandos y comprobaciones.

## Qué registrar

- Importación inicial del prototipo existente con una descripción honesta de su procedencia.
- Correcciones reales revisadas por el equipo: problema, archivos, prueba que falla antes y pasa después.
- Revisión y ejecución de pruebas por cada integrante, con resultados enlazados al commit correspondiente.
- Acta o PR donde los tres revisen el contrato final y sus consecuencias.

No repartir archivos ya generados para simular autoría previa. Un commit de carga no demuestra que
esa persona haya diseñado o probado el componente. Cada integrante debe explicar toda la arquitectura.

## Organización recomendada

La raíz elegida es **`DFSha_FaseII/`**, con `dfsha/` como subcarpeta de aplicación.
Antes de subir, revisar `.gitignore`: nunca versionar `certs/`, `.env`, `meta.env`,
llaves SSH, contraseñas, dumps del catálogo o archivos de prueba grandes.

Los resultados históricos tienen inconsistencias señaladas en la auditoría; deben mantenerse identificados
como históricos, no presentarse como validación de la revisión actual. Los registros nuevos indican entorno
local o AWS, versión y corrida. No reemplazar esa distinción por capturas seleccionadas.

## Pendiente del equipo

1. Confirmar repositorio y permisos de acceso del profesor.
2. Revisar las correcciones y registrar aportes reales mediante commits/PR.
3. Repetir el despliegue y las pruebas en AWS Academy.
4. Grabar el video de 10–15 minutos y preparar la defensa individual.

No se crean commits ni se hace `push` sin la instrucción del propietario del repositorio.
