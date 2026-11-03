# Estado de estas evidencias

Los archivos `P1.txt`–`P8.txt`, `AWS.txt`, `DESPLIEGUE.txt`, `bench.csv` y el intento OOM
pertenecen al prototipo previo. Se conservan sin editar para trazabilidad.

**No validan la revisión actual ni deben presentarse como resultados recién obtenidos.**
`bench.csv` tiene una inconsistencia demostrable: en E3, cuatro clientes, put, n=5,
media 3.064 s y p95 3.05 s. Con el cálculo declarado ese p95 es el máximo y no puede
ser menor que la media. No se arreglaron números manualmente.

Los directorios `revision-*` son nuevas ejecuciones. Cada uno identifica si es local
o AWS y conserva muestras o registros. Solo una repetición real en AWS puede producir
la evidencia distribuida final de la Fase II; no convertir una prueba local en una
captura que diga AWS.
