# DFSha: sistema de archivos distribuido

Proyecto 1, Fase II de Arquitecturas de Nube y Sistemas Distribuidos, Universidad Pontificia Bolivariana.

**Integrantes:** Andrés Felipe Martínez Velasquez, Juan José García Duque y Samuel Parra Cadavid.

## Arquitectura

Cliente/servidor con comunicación S2S sobre una red privada:

- Dos coordinadores equivalentes y tres miembros etcd/Raft para metadatos, sesiones y publicación de versiones.
- Cuatro nodos de datos; el cliente transfiere bloques directamente a los nodos, que replican entre servidores.
- Bloques de hasta 8 MiB, tres réplicas objetivo y dos confirmaciones persistentes distintas por bloque antes de publicar.
- REST/HTTPS para control y gRPC/mTLS para datos; cifrado AES-GCM y recibos firmados por nodo.

## Instalación, ejecución y pruebas

Las instrucciones completas de dependencias, Docker, CLI, despliegue en AWS Academy y pruebas están en
[`dfsha/README.md`](dfsha/README.md). Los comandos de aplicación se ejecutan desde la subcarpeta `dfsha/`.

```text
DFSha_FaseII/
├── README.md
├── DFSha_FaseII_Informe_Grupal.pdf
├── dfsha/       # Código, contratos, dependencias, despliegue, pruebas y resultados
└── informe/     # Comparación, decisiones, figuras y fuentes del informe
```

## Informe y decisiones

- [Informe técnico final en PDF](DFSha_FaseII_Informe_Grupal.pdf).
- [Comparación de las tres propuestas individuales](informe/COMPARACION_PROPUESTAS.md).
- [Registro de decisiones arquitectónicas](informe/ADR_REVISION.md).

El PDF contiene la explicación del servicio, arquitectura, APIs, ejemplos, garantías, pruebas, resultados y referencias.

## Evidencias

[El índice de resultados](dfsha/resultados/README.md) identifica las ejecuciones que respaldan la entrega.
Se conservan la regresión AWS de 19 casos, las 80 muestras del benchmark completo, el registro de caídas
y la corrida fallida que documenta la corrección de reintentos. Las comprobaciones locales se distinguen de AWS.

Las pruebas remotas detienen contenedores de servicios en cuatro VMs EC2; no equivalen a apagar una VM completa.

## Fuentes y comprobación del informe

La entrega incluye únicamente el PDF. El generador y sus pruebas se conservan para reproducir el contenido:

```bash
python -m pip install -r informe/requirements.txt
python informe/construir_informe.py
python -m unittest discover -s informe -p "test_documento_academico.py" -v
```

Estos comandos son opcionales para la documentación, no para arrancar DFSha. El generador produce un DOCX
intermedio que las pruebas de formato necesitan y que Git ignora; no forma parte de la entrega.
No reemplaza el PDF automáticamente ni reproduce necesariamente los ajustes manuales de la versión final.

## Configuración local

`.env`, `meta.env`, certificados, CA y llaves SSH se generan o configuran localmente. Están excluidos de Git
y deben quedar fuera del ZIP de entrega. Se mantienen los generadores de identidades y la configuración fuente
necesarios para preparar una instalación nueva.
