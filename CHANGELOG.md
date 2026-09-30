# Changelog

Todos los cambios relevantes del proyecto se documentan en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[Semantic Versioning](https://semver.org/lang/es/).

Tipos de cambio: **Agregado**, **Cambiado**, **Obsoleto**, **Eliminado**, **Corregido**, **Seguridad**.

## [Sin publicar]

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

[Sin publicar]: https://gitlab.example.com/infra/helmreview/-/compare/v1.0.0...HEAD
[1.0.0]: https://gitlab.example.com/infra/helmreview/-/compare/v0.2.0...v1.0.0
[0.2.0]: https://gitlab.example.com/infra/helmreview/-/compare/v0.1.0...v0.2.0
[0.1.0]: https://gitlab.example.com/infra/helmreview/-/tags/v0.1.0
