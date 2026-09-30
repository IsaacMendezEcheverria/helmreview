# Proceso de release

## Qué número de versión usar (SemVer)

| Cambio | Versión |
|---|---|
| Se renombra o elimina una opción del CLI, un ID de check o un campo del JSON | **MAJOR** (2.0.0) |
| Checks nuevos, opciones nuevas, soporte de una nueva versión de OCP/K8s | **MINOR** (1.1.0) |
| Correcciones, ajustes de mensajes, documentación | **PATCH** (1.0.1) |

Subir la severidad de un check existente es técnicamente MINOR, pero puede romper pipelines con `--fail-on`.
Destácalo en el CHANGELOG.

## Pasos

```bash
git checkout main && git pull
make test lint                                   # todo en verde

# 1. Actualiza la versión (fuente única)
#    src/helmreview/__init__.py  ->  __version__ = "1.1.0"

# 2. En CHANGELOG.md:
#    - renombra "## [Sin publicar]" a "## [1.1.0] - AAAA-MM-DD"
#    - crea una sección "## [Sin publicar]" vacía arriba
#    - actualiza los links de comparación al final del archivo

# 3. Commit y tag anotado
git commit -am "chore(release): 1.1.0"
git tag -a v1.1.0 -m "helmreview 1.1.0"
git push origin main --follow-tags
```

Si `origin` tiene configurados varios push URLs (ver [ci-platforms.md](ci-platforms.md)), el mismo push llega a
GitHub, GitLab y Google Secure Source Manager, y cada plataforma hace su parte al detectar el tag `vX.Y.Z`:

| Plataforma | Qué hace con el tag |
|---|---|
| GitHub (`.github/workflows/release.yml`) | Verifica que el tag coincida con `__version__`, construye, crea el GitHub Release con las notas del CHANGELOG y publica en **PyPI** si `PUBLISH_PYPI=true` |
| GitLab (`.gitlab-ci.yml`) | Lint, tests y build; publica en el Package Registry del proyecto y en PyPI si `PUBLISH_PYPI=true` |
| Google Cloud Build (`.cloudbuild/release.yaml`) | Verifica la versión, construye y publica en Artifact Registry |

**PyPI se publica desde una sola plataforma.** Una versión subida a PyPI no se puede reemplazar: si algo sale
mal, publica una versión PATCH nueva.

Para probar el paquete antes de un release real, súbelo a TestPyPI:

```bash
make build
.venv/bin/twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ helmreview
```

## Verificación posterior

```bash
python -m venv /tmp/hr && . /tmp/hr/bin/activate
pip install dist/helmreview-1.1.0-py3-none-any.whl
helmreview --version
helmreview tests/fixtures/charts/sample --ocp-version 4.16 --fail-on medium
```
