# Guía de contribución

## Entorno de desarrollo

```bash
git clone <url-del-repo> helmreview && cd helmreview
make dev                 # crea .venv, instala ".[dev]" y los hooks de pre-commit
source .venv/bin/activate
make test lint           # debe pasar antes de cualquier merge request
```

Sin `make` (por ejemplo en Windows):

```bash
python -m venv .venv && .venv/Scripts/activate      # o: source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest && ruff check src tests && ruff format --check src tests
```

Para correr los tests de integración con helm, `helm` debe estar en el `PATH`. Si no está, esos tests se
omiten (salen como `skipped`).

## Flujo de trabajo

1. Crea un issue o ticket describiendo el cambio.
2. Crea una rama desde `main` con uno de estos prefijos:
   - `feat/<descripcion-corta>`: funcionalidad nueva o check nuevo.
   - `fix/<descripcion-corta>`: corrección.
   - `docs/<descripcion-corta>`, `chore/<descripcion-corta>`, `refactor/<descripcion-corta>`.
3. Haz commits siguiendo [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/):
   ```
   feat(openshift): detectar Routes sin TLS
   fix(resources): no contar initContainers como suma
   docs: actualizar catálogo de checks
   feat!: renombrar opción --version a --chart-version     # "!" = cambio incompatible
   ```
4. Agrega tu cambio en la sección `## [Sin publicar]` del [CHANGELOG.md](CHANGELOG.md).
5. Abre un merge request hacia `main`. El pipeline debe pasar (lint + tests).
6. Se requiere al menos una aprobación. Se integra con *squash merge*, usando el título del MR en formato
   Conventional Commits.

## Checklist del merge request

- [ ] `make test lint` pasa localmente.
- [ ] Si se agregó o cambió un check:
  - [ ] Tiene tests (caso positivo y negativo).
  - [ ] Está en [docs/checks.md](docs/checks.md). El test `test_docs_catalog` lo verifica.
  - [ ] No se reutilizó ni renombró el ID de un check existente.
- [ ] El CHANGELOG está actualizado en `[Sin publicar]`.
- [ ] Si cambia el uso de la herramienta, el README está actualizado.
- [ ] Los cambios incompatibles (opciones de CLI, formato del JSON, IDs) están marcados como **Cambiado**
  o **Eliminado** en el CHANGELOG y con `!` en el commit.

## Convenciones de código

- Python 3.9 o superior. No uses sintaxis más nueva (por ejemplo `match` o `type X = ...`).
- Formato y lint con **ruff** (configuración en `pyproject.toml`); pre-commit lo aplica solo.
- La única dependencia de runtime es PyYAML. Agregar otra requiere justificarla en el MR.
- Los mensajes al usuario van en español. Los IDs de checks van en minúsculas con guiones.
- Los checks no deben lanzar excepciones ante manifiestos incompletos: usa `(x or {}).get(...)`.
- Las tablas de referencia (APIs deprecadas, mapa OCP → K8s, capabilities) viven en `constants.py`, no dispersas
  en el código.

## Tareas de mantenimiento periódicas

| Cuándo | Qué | Dónde |
|---|---|---|
| Cada versión nueva de Kubernetes | Agregar APIs eliminadas | `constants.DEPRECATED_APIS` |
| Cada versión nueva de OpenShift | Agregar la versión al mapa OCP → K8s | `constants.OCP_KUBE_MAP` |
| Cambios en SCC por defecto de OpenShift | Revisar `OCP_ALLOWED_CAPS` y los checks `ocp-*` | `constants.py`, `checks/workloads.py` |
| Trimestral | Actualizar las versiones de los hooks de pre-commit | `pre-commit autoupdate` |
