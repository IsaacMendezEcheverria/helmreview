# Changelog

Todos los cambios relevantes del proyecto se documentan en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[Semantic Versioning](https://semver.org/lang/es/).

Tipos de cambio: **Agregado**, **Cambiado**, **Obsoleto**, **Eliminado**, **Corregido**, **Seguridad**.

## [Sin publicar]

## [1.0.2] - 2026-09-30

### Agregado
- Publicación en PyPI (`pip install helmreview`) con Trusted Publishing.

### Cambiado
- README: el ejemplo de GitHub Actions usa las versiones actuales (checkout v7, setup-python v7, setup-helm v5, upload-artifact v7).

## [1.0.1] - 2026-09-30

### Agregado
- Licencia MIT (`LICENSE`) y publicación como proyecto open source.
- Archivos de comunidad: `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1) y `SECURITY.md`.
- CI y release en GitHub Actions (`.github/workflows/ci.yml` y `release.yml`): matriz de Python 3.9 a 3.13,
  GitHub Release con las notas del CHANGELOG y publicación en PyPI con Trusted Publishing.
- CI y release en Google Cloud Build (`.cloudbuild/`), con triggers para Secure Source Manager y publicación en
  Artifact Registry.
- Plantillas de issues y de PR/MR para GitHub (`.github/`) y GitLab (`.gitlab/`), y Dependabot.
- `docs/ci-platforms.md`: configuración de las tres plataformas y espejos entre ellas.

### Cambiado
- `pyproject.toml`: licencia SPDX (`MIT`), keywords, clasificadores, `[project.urls]` y `twine` en `dev`.
  El build requiere `setuptools>=77`.
- GitLab CI: `twine check` en el build, tests también en Python 3.13, y job opcional `publish-pypi` con
  Trusted Publishing (se activa con `PUBLISH_PYPI=true`). El job de publicación al Package Registry se renombra
  a `publish-gitlab`.
- README: instalación desde PyPI, ejemplos de integración para GitHub Actions, GitLab CI y Cloud Build, y
  secciones de contribución y licencia.
- CONTRIBUTING: flujo con fork para colaboradores externos y terminología neutral (PR/MR).
- `make build` ejecuta `twine check --strict`.

### Corregido
- El ejemplo de chart OCI en `helmreview --help` usaba `--version` en lugar de `--chart-version`.

## [1.0.0] - 2026-09-30

Primera versión como proyecto mantenible. El script `helm_review.py` se reestructura como el paquete Python
`helmreview`, instalable con pip.

### Agregado
- Paquete instalable con el comando `helmreview` y soporte para `python -m helmreview`.
- Código separado en módulos: `helm`, `checks` (chart_meta, manifests, workloads), `report` (console, markdown,
  json), `external`, `cli`, `options` y `models`.
- API de librería: `helmreview.review.review_chart(chart, ReviewOptions(...))`.
- Opción `--ignore` para omitir checks por ID.
- Opción `--version`.
- El reporte Markdown incluye la versión de helmreview y los checks ignorados.
- El JSON ahora tiene el formato `{"tool", "version", "charts": [...]}`.
- Catálogo de checks en `docs/checks.md`, con un test que garantiza que esté sincronizado con el código.
- Suite de tests con pytest, incluidos fixtures para Kubernetes y OpenShift y tests de integración con helm (se
  omiten si helm no está instalado).
- Tooling: ruff, pre-commit, Makefile, pipeline de GitLab CI, `.editorconfig`.
- Documentación: README, CONTRIBUTING, arquitectura, guía para agregar checks y guía de releases.

### Cambiado
- **Incompatible con el script 0.x:** la versión de un chart remoto ahora se pasa con `--chart-version` (antes
  `--version`, que ahora muestra la versión de la herramienta).
- **Incompatible con el script 0.x:** el JSON de salida envuelve la lista de charts en la clave `charts`.
- Los checks de recursos no-workload se registran en una tabla (`KIND_CHECKS`), lo que facilita agregar tipos nuevos.

## [0.2.0] - 2026-09-30

### Agregado
- Modo OpenShift (`--platform openshift` / `--ocp-version`):
  - Pasa a `helm template` las APIs de OpenShift para que `.Capabilities` renderice las Routes.
  - Mapa de versiones OCP → Kubernetes (4.12 a 4.20).
  - Validación contra la SCC `restricted-v2`: UID/GID/fsGroup fijos, capabilities, privileged, host*, puertos
    < 1024 y resumen de las SCC requeridas por workload.
  - Checks de Route (TLS, `insecureEdgeTerminationPolicy`, certificados embebidos).
  - Detección de SCC creadas por el chart y de RBAC sobre SCC.
  - Soporte de DeploymentConfig (análisis de capacidad y aviso de deprecación).

### Cambiado
- En modo OpenShift ya no se pide `runAsNonRoot`/`runAsUser`, y `allowPrivilegeEscalation` baja a severidad BAJA
  porque la SCC lo aplica.

## [0.1.0] - 2026-09-30

### Agregado
- Script `helm_review.py` inicial: `helm lint` + `helm template` y análisis del render.
- Checks de Chart.yaml, recursos, réplicas/HPA/PDB, probes, securityContext, imágenes, secretos, Ingress,
  Service, RBAC, APIs deprecadas y almacenamiento.
- Cálculo de la capacidad configurada.
- Reportes en consola, Markdown y JSON; `--fail-on` para CI; integración opcional con kubeconform, kube-linter y
  trivy.

[Sin publicar]: https://github.com/IsaacMendezEcheverria/helmreview/compare/v1.0.2...HEAD
[1.0.2]: https://github.com/IsaacMendezEcheverria/helmreview/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/IsaacMendezEcheverria/helmreview/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/IsaacMendezEcheverria/helmreview/compare/v0.2.0...v1.0.0
[0.2.0]: https://github.com/IsaacMendezEcheverria/helmreview/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/IsaacMendezEcheverria/helmreview/releases/tag/v0.1.0
