# helmreview

[![CI](https://github.com/IsaacMendezEcheverria/helmreview/actions/workflows/ci.yml/badge.svg)](https://github.com/IsaacMendezEcheverria/helmreview/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/helmreview)](https://pypi.org/project/helmreview/)
[![Python](https://img.shields.io/pypi/pyversions/helmreview)](https://pypi.org/project/helmreview/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Revisión **estática y local** de Helm charts para Kubernetes y OpenShift. El chart se renderiza con
`helm template` en tu propia estación: no se necesita acceso al cluster y no se sube nada a servicios externos.

A partir del render, la herramienta:

- **Mide la capacidad configurada**: requests y limits de CPU/memoria por pod, totales con las réplicas base y con
  el máximo del HPA, DaemonSets por nodo y almacenamiento (PVC y volumeClaimTemplates).
- **Detecta problemas** de alta disponibilidad, probes, seguridad, imágenes, RBAC, red, APIs eliminadas y metadatos
  del chart.
- **Valida compatibilidad con OpenShift** (`--ocp-version`): SCC `restricted-v2`, Routes, DeploymentConfig y RBAC
  sobre SCC.
- **Genera reportes** en consola, Markdown (para tickets o pull/merge requests) y JSON (para integraciones).
- **Integra con CI**: `--fail-on` devuelve el exit code 2 si hay hallazgos a partir de la severidad indicada.

El catálogo completo de checks está en [docs/checks.md](docs/checks.md).

---

## Requisitos

| Componente | Versión | Notas |
|---|---|---|
| Python | 3.9 o superior | |
| helm | 3.x o 4.x en el `PATH` | Solo se usa `helm lint`, `helm template` y `helm show` |
| kubeconform, kube-linter, trivy | opcionales | Solo si usas `--external` |

## Instalación

```bash
pip install helmreview                 # desde PyPI
# pipx install helmreview              # recomendado para CLIs: entorno aislado
helmreview --version
```

Otras formas:

```bash
# Directo desde el repositorio (GitHub, GitLab o Secure Source Manager), fijando un tag
pip install "git+https://github.com/IsaacMendezEcheverria/helmreview.git@v1.0.0"

# Desde el código fuente
git clone https://github.com/IsaacMendezEcheverria/helmreview.git && cd helmreview
python3 -m venv .venv
source .venv/bin/activate            # Windows: .\.venv\Scripts\Activate.ps1
pip install .                        # usuarios
# pip install -e ".[dev]"            # desarrolladores (tests, linter, pre-commit)

# Desde el wheel generado con `make build`
pip install dist/helmreview-1.0.0-py3-none-any.whl
```

Si tu organización publica el paquete en su registro interno (Package Registry de GitLab o Artifact Registry de
Google Cloud), mira [docs/ci-platforms.md](docs/ci-platforms.md) para el `--index-url` correspondiente.

## Uso rápido

```bash
# Kubernetes genérico con los values de producción
helmreview ./mychart -f values.yaml -f values-prod.yaml --kube-version 1.30 --report revision.md

# OpenShift 4.16 (fija la versión de K8s y activa los checks de SCC y Routes)
helmreview ./mychart -f values-ocp.yaml --ocp-version 4.16 --report revision.md

# Todos los charts de un directorio, mostrando solo severidad media o alta
helmreview ./charts/* --ocp-version 4.16 --min-severity medium --json revision.json

# Chart remoto en un registry OCI (requiere `helm registry login` antes)
helmreview oci://harbor.local/charts/app --chart-version 1.4.2 -f prod.yaml

# Analizar un YAML ya renderizado, sin ejecutar helm
helmreview ./mychart --rendered render.yaml

# Omitir checks aceptados como excepción
helmreview ./mychart --ignore serviceaccount,chart-schema
```

También se puede ejecutar como `python -m helmreview ...`.

### Opciones principales

| Opción | Descripción |
|---|---|
| `-f, --values` | Archivo de values. Se puede repetir y se aplica en orden, igual que en helm |
| `--set` | Valor `--set` de helm (repetible) |
| `-n, --namespace` | Namespace del render (default: `default`) |
| `--kube-version` | Versión de Kubernetes objetivo (afecta `.Capabilities`) |
| `--ocp-version` | Versión de OpenShift. Implica `--platform openshift` y fija `--kube-version` |
| `--platform` | `kubernetes` (default) u `openshift` |
| `--api-versions` | API adicional disponible en el cluster, por ejemplo `monitoring.coreos.com/v1` (repetible) |
| `--chart-version` | Versión del chart en charts remotos u OCI |
| `--dep-update` | Ejecuta `helm dependency build/update` antes del render |
| `--rendered` | Analiza un YAML ya renderizado (un solo chart) |
| `--external` | Ejecuta kubeconform, kube-linter y trivy si están instalados |
| `--ignore` | IDs de checks a omitir, separados por coma |
| `--min-severity` | `high`, `medium`, `low` (default) o `info` |
| `--report` / `--json` | Escribe el reporte Markdown o JSON |
| `--save-rendered` | Guarda el YAML renderizado en un directorio |
| `--fail-on` | `high`, `medium`, `low` o `none` (default). Exit code 2 si se cumple |

### Códigos de salida

| Código | Significado |
|---|---|
| 0 | Revisión completada; no se alcanzó el umbral de `--fail-on` |
| 1 | Error de ejecución: helm no instalado, render fallido o archivo de values inexistente |
| 2 | Hay hallazgos con severidad igual o mayor a `--fail-on` |

## Lectura del reporte

- **Capacidad configurada**:
  - *Req total* = request por pod × réplicas base.
  - *Req total a máx. HPA* = request por pod × `maxReplicas`. Este es el valor que hay que cubrir con cuota o
    con nodos.
  - Los DaemonSets se muestran *por nodo*.
  - Si un contenedor no define request pero sí limit, se usa el limit, igual que hace Kubernetes.
  - Los initContainers cuentan como el máximo, no como la suma.
- **Hallazgos**: cada uno incluye severidad, recurso, contenedor, ID del check y el template de origen
  (`# Source:`), para ir directo al archivo a corregir.

## OpenShift: qué valida y qué no

La herramienta valida lo que se ve en los manifiestos: compatibilidad con `restricted-v2` (UID/GID fijos,
capabilities, privileged, host*, puertos < 1024), Routes y RBAC sobre SCC.

**No puede validar la imagen.** Para funcionar con UID arbitrario, los directorios donde la aplicación escribe
deben pertenecer al grupo 0 con permisos `g=u`. Eso se revisa en el Dockerfile o probando el pod en un namespace
con `restricted-v2`.

## Integración en CI

`--fail-on` hace fallar el job si hay hallazgos a partir de la severidad indicada, y el reporte Markdown
queda como artefacto para revisarlo en el PR/MR.

**GitHub Actions**

```yaml
jobs:
  helm-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with: { python-version: "3.12" }
      - uses: azure/setup-helm@v4
      - run: pip install helmreview==1.0.0
      - run: helmreview charts/* --ocp-version 4.16 -f values-prod.yaml --report revision.md --fail-on high
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: helm-review, path: revision.md }
```

**GitLab CI**

```yaml
helm-review:
  image: python:3.12-slim
  before_script:
    - apt-get update -qq && apt-get install -y -qq curl > /dev/null
    - curl -fsSL https://get.helm.sh/helm-v3.16.2-linux-amd64.tar.gz | tar xz -C /tmp && mv /tmp/linux-amd64/helm /usr/local/bin/
    - pip install helmreview==1.0.0
  script:
    - helmreview charts/* --ocp-version 4.16 -f values-prod.yaml --report revision.md --fail-on high
  artifacts:
    when: always
    paths: [revision.md]
```

**Google Cloud Build**

```yaml
steps:
  - name: python:3.12-slim
    entrypoint: bash
    args:
      - -ceu
      - |
        apt-get update -qq && apt-get install -y -qq curl > /dev/null
        curl -fsSL https://get.helm.sh/helm-v3.16.2-linux-amd64.tar.gz | tar xz -C /tmp && mv /tmp/linux-amd64/helm /usr/local/bin/
        pip install -q helmreview==1.0.0
        helmreview charts/* --ocp-version 4.16 -f values-prod.yaml --report revision.md --fail-on high
options:
  logging: CLOUD_LOGGING_ONLY
```

## Uso como librería

```python
from helmreview.options import ReviewOptions
from helmreview.review import review_chart

rep = review_chart("./mychart", ReviewOptions(values=["prod.yaml"], platform="openshift", kube_version="1.29"))
for f in rep.filtered("MEDIUM"):
    print(f.severity, f.check, f.resource, f.message)
```

## Desarrollo y mantenimiento

| Documento | Contenido |
|---|---|
| [CONTRIBUTING.md](CONTRIBUTING.md) | Entorno de desarrollo, convenciones de commits y ramas, flujo de pull/merge requests |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Código de conducta de la comunidad |
| [SECURITY.md](SECURITY.md) | Cómo reportar vulnerabilidades |
| [docs/ci-platforms.md](docs/ci-platforms.md) | CI y publicación en GitHub, GitLab y Google Cloud; espejos entre plataformas |
| [docs/architecture.md](docs/architecture.md) | Estructura del código y flujo de ejecución |
| [docs/adding-a-check.md](docs/adding-a-check.md) | Cómo agregar o modificar un check, paso a paso |
| [docs/checks.md](docs/checks.md) | Catálogo de checks con sus IDs |
| [docs/releasing.md](docs/releasing.md) | Cómo publicar una nueva versión |
| [CHANGELOG.md](CHANGELOG.md) | Historial de cambios |

Comandos frecuentes:

```bash
make dev      # crea .venv e instala dependencias de desarrollo + pre-commit
make test     # pytest con cobertura
make lint     # ruff check + ruff format --check
make build    # wheel y sdist en dist/
```

## Versionado

Se usa [Semantic Versioning](https://semver.org/lang/es/). La versión vive en un solo lugar:
`src/helmreview/__init__.py`. Los cambios se registran en [CHANGELOG.md](CHANGELOG.md).

## Contribuir

Las contribuciones son bienvenidas: reportes de bugs, checks nuevos, soporte para nuevas versiones de
Kubernetes/OpenShift y mejoras en la documentación. Lee [CONTRIBUTING.md](CONTRIBUTING.md) antes de abrir un
pull request y respeta el [código de conducta](CODE_OF_CONDUCT.md). Para temas de seguridad, sigue
[SECURITY.md](SECURITY.md).

## Mantenedores

- Isaac Mendez — isaac.mendez@siproset.com

## Licencia

Distribuido bajo la licencia [MIT](LICENSE). © 2026 Isaac Mendez.
