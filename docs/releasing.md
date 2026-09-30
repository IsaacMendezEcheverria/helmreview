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

El pipeline de GitLab (`.gitlab-ci.yml`) hace lo siguiente al detectar un tag `v*`:

1. Corre lint y tests.
2. Construye el wheel y el sdist (`make build`).
3. Los adjunta como artifacts del job y, si está configurado, los publica en el Package Registry del proyecto.

## Verificación posterior

```bash
python -m venv /tmp/hr && . /tmp/hr/bin/activate
pip install dist/helmreview-1.1.0-py3-none-any.whl
helmreview --version
helmreview tests/fixtures/charts/sample --ocp-version 4.16 --fail-on medium
```
