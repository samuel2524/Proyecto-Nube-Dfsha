# Integración del proyecto por commits — Samuel, Juan José y Andrés

Repositorio: <https://github.com/samuel2524/Proyecto-Nube-Dfsha>

**Raíz correcta:** esta carpeta, `DFSha_FaseII/`. Dentro está la subcarpeta `dfsha/`.
No crear una segunda carpeta `DFSha_FaseII` dentro del clon.

Se trata de integrar y validar un prototipo asistido que ya existe. Cada integrante debe revisar y
probar el bloque que suba, e indicar qué corrigió o comprobó. No se atribuye desarrollo autónomo
previo simplemente porque alguien copie los archivos y haga un commit.

## 1. Dos commits de Samuel

### S1 — Cliente y CLI

Mensaje: `feat(cliente): incorporar cliente DFSha y CLI`

- `.gitignore`
- `dfsha/.gitignore`
- `dfsha/.gitattributes`
- `dfsha/dfsha/__init__.py`
- `dfsha/dfsha/client.py`
- `dfsha/dfsha/cli.py`

Contenido: partición, cifrado, snapshots, sesiones, preparación de bloques, cierre idempotente,
descarga atómica y comandos del usuario.

### S2 — Pruebas y documentación de uso

Mensaje: `test: incorporar regresiones y documentación de uso`

- `README.md`, `GUIA_COMMITS.md`, `COMMITS_EQUIPO.md`.
- `dfsha/README.md`.
- `dfsha/tests/`: regresión, contrato, estadística, pruebas de paquete, sondas y utilidades.
- `dfsha/scripts/verify_local.py`, `record_checks.py`, `check_deploy_config.py`.
- `dfsha/resultados/LEER_ANTES_DE_USAR.md`.
- Última evidencia local coherente: `revision-20261103-062535/`,
  `revision-checks-20261103T064125Z/`, `revision-failures-8360fe3f7eb4/`,
  `revision-bench-20261103T062822Z-73ae1d/`.

No incluye las mediciones antiguas incompatibles ni todas las corridas de desarrollo.

**Dependencias:** estos dos commits por sí solos no traen los servidores ni los contratos generados.
La ejecución completa se comprueba cuando se incorporen J1/J2/A1/A2.

## 2. Preparación común para los compañeros

El propietario debe agregarlos como colaboradores de GitHub antes de hacer `push`.
Cada uno usa su propia cuenta e identidad Git configurada; no cambiar de identidad para simular al otro.

```bash
git clone https://github.com/samuel2524/Proyecto-Nube-Dfsha.git
```

Abrir terminal en el clon. Extraer el ZIP fuera del clon y copiar **solo los archivos de su bloque**,
respetando las rutas de abajo. No copiar `.git`, `.env`, `certs/` ni carpetas completas que sobrescriban
el trabajo integrado por el otro. Antes de cada bloque:

```bash
git pull --ff-only origin main
git status --short
```

Si el ZIP tiene una carpeta contenedora, sus archivos `README.md`, `dfsha/` e `informe/` deben quedar
directamente en la raíz del clon, no anidados un nivel extra.

## 3. Juan José — dos bloques

### J1 — Nodo de datos, contrato gRPC y construcción

Revisar: recepción incremental, tamaño/hash, publicación create-once, recibos firmados,
réplica S2S, acciones autorizadas y exigencia de certificado de cliente.

Copiar y después ejecutar:

```bash
git add dfsha/dfsha/datanode.py dfsha/proto/dfsha.proto dfsha/Dockerfile dfsha/.dockerignore
git diff --cached --check
git diff --cached --stat
git commit -m "feat(datos): integrar nodo de datos y contrato gRPC"
git push origin main
```

### J2 — Identidades por rol y clúster de desarrollo

Copiar los generadores/configuración, **no las credenciales generadas**.

```bash
git pull --ff-only origin main
git add dfsha/scripts/gen_certs.py dfsha/scripts/init_local.py dfsha/docker-compose.local.yml
git diff --cached --check
git diff --cached --stat
git commit -m "feat(seguridad): integrar identidades por rol y clúster local"
git push origin main
```

Verificaciones que debe documentar cuando A1 esté integrado: certificados distintos por servicio,
cliente/nodos sin claves del catálogo, mTLS rechazando cliente sin certificado y permisos del paquete.

## 4. Andrés — dos bloques

### A1 — Control, catálogo y primitivas compartidas

Revisar: dos recibos distintos verificables, base esperada por bloque, exclusión w/a, leases lectores,
CAS de sesión/referencias, idempotencia, retención/GC y reparación sin propagar corrupción.

```bash
git pull --ff-only origin main
git add dfsha/dfsha/common.py dfsha/dfsha/metadata.py dfsha/requirements.txt
git diff --cached --check
git diff --cached --stat
git commit -m "feat(control): integrar catálogo y publicación verificada"
git push origin main
```

### A2 — Despliegue, decisiones e informe revisado

```bash
git pull --ff-only origin main
git add dfsha/deploy/desplegar.py dfsha/deploy/docker-compose.yml dfsha/deploy/requirements.txt dfsha/scripts/setup_cliente.sh
git add informe/construir_informe.py informe/requirements.txt informe/README.md informe/ADR_REVISION.md informe/COMPARACION_PROPUESTAS.md
git add informe/figuras/componentes_revision.png informe/figuras/despliegue_revision.png
git add CAMBIOS_CORRECCIONES_DFSHA.md DFSha_FaseII_Informe_Grupal.docx DFSha_FaseII_Informe_Grupal.pdf
git diff --cached --check
git diff --cached --stat
git commit -m "docs(despliegue): integrar configuración AWS e informe revisado"
git push origin main
```

No subir `informe/historico/`, capturas antiguas ni certificados. La configuración AWS se ha renderizado,
pero **no se ha revalidado en AWS**: ejecutar y registrar esa validación antes de cambiar la afirmación.

## 5. Orden sugerido de integración

1. S1 y S2 (Samuel).
2. J1 y J2 (Juan José).
3. A1 y A2 (Andrés).
4. Los tres revisan el clon completo y ejecutan las pruebas.

Este orden evita que los dos compañeros intenten publicar sobre la misma punta sin actualizar.
Si trabajan en paralelo, usar ramas/PR y resolver la integración; no usar `push --force`.
Si un push es rechazado por cambios nuevos, revisar y actualizar antes de volver a subir; no sobrescribir.

La integración en seis bloques es organizativa. No significa que todos los commits intermedios puedan
ejecutar el sistema completo. No etiquetar ni presentar como entrega hasta terminar la integración.

## 6. Validación desde el clon completo

Abrir terminal en `dfsha/` (ahora sí, la subcarpeta de aplicación):

```bash
docker build -t dfsha:revision .
```

Inicializar secretos con el comando del README para su shell; después:

```bash
docker compose -p dfsha-revision -f docker-compose.local.yml up -d --no-build
docker compose -p dfsha-revision -f docker-compose.local.yml exec -T -e RUN_LARGE=1 cliente python -m tests.regression
python scripts/record_checks.py
python scripts/verify_local.py --project dfsha-revision
```

La prueba grande usa varios GiB de disco. Los registros existentes son locales y del código indicado
por sus hashes; agregar sus propias corridas y asociarlas al commit realmente probado.

Luego faltan AWS Academy, decisiones ratificadas, video de 10–15 minutos y defensa individual.
Dos commits por persona no reemplazan las verificaciones y aportes reales que evalúa el profesor.

## 7. Qué lleva el ZIP de intercambio

- Código completo de la revisión, pruebas, configuración fuente y documentación vigente.
- Word/PDF grupales corregidos, figuras vigentes y últimos registros locales seleccionados.
- No contiene `.git`, `.env`, `meta.env`, certificados/CA/llaves, binarios de prueba,
  `__pycache__`, históricos ni el CSV antiguo incompatible.

Antes de ejecutar, cada compañero genera sus secretos de laboratorio. No copiar las claves de otro equipo.
