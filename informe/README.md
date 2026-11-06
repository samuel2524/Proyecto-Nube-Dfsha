# Informe grupal de la revisión

- `construir_informe.py` invoca el generador vigente `documento_academico.py`. Requiere las dependencias de esta carpeta.
- `COMPARACION_PROPUESTAS.md` y `ADR_REVISION.md` documentan procedencia, decisiones y ratificación pendiente.
- `GUION_VIDEO.md` ordena la grabación de 10–15 minutos y `GUION_DEFENSA.md` prepara las preguntas orales.
- Las figuras vigentes son `figuras/componentes_revision.png` y `figuras/despliegue_revision.png`.
- `historico/` conserva el Word/PDF previos, con sus capturas y resultados originales. No usarlos como informe de la revisión.
- `estilo.py`, `diagrama_despliegue.py` y las figuras sin sufijo `_revision` pertenecen al generador anterior;
  se conservaron para trazabilidad y no forman parte del informe regenerado.

El informe es autónomo: contiene portada de estudiante con criterios APA 7, comparación, decisiones,
contratos y ejemplos de API, resultados AWS y sus límites. No remite al profesor a documentos internos.
Las referencias bibliográficas mantienen la numeración IEEE existente. El tiempo de recuperación se calcula
con timestamps del registro, no sumando solo la duración de sondeos. Faltan ratificar decisiones,
completar comparaciones/instrumentación y registrar video/defensa; no se dan por hechos.
