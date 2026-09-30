# Plataformas: GitHub, GitLab y Google Cloud

El repositorio trae la configuración lista para las tres plataformas. Todas ejecutan lo mismo (lint con ruff,
tests con pytest y helm real, build del wheel y sdist con `twine check`) y se diferencian en dónde publican.

| Plataforma | Archivos | CI en PR/MR y `main` | Release en tag `vX.Y.Z` |
|---|---|---|---|
| **GitHub** | `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/dependabot.yml` | GitHub Actions, Python 3.9 a 3.13 | GitHub Release con los archivos + PyPI (si `PUBLISH_PYPI=true`) |
| **GitLab** | `.gitlab-ci.yml`, `.gitlab/issue_templates/`, `.gitlab/merge_request_templates/` | GitLab CI, Python 3.9, 3.12 y 3.13 | Package Registry del proyecto + PyPI (si `PUBLISH_PYPI=true`) |
| **Google Cloud** | `.cloudbuild/cloudbuild.yaml`, `.cloudbuild/release.yaml`, `.cloudbuild/triggers.yaml` | Cloud Build, Python 3.9 y 3.12 | Repositorio Python de Artifact Registry |

Cada plataforma ignora los archivos de las otras, así que pueden convivir en el mismo repositorio sin conflicto.

## Estrategia recomendada: un repositorio canónico y espejos

1. **Canónico:** donde la comunidad abre issues y pull requests. Para un proyecto open source se recomienda
   **GitHub**. Las URLs de `pyproject.toml`, `CHANGELOG.md` y `README.md` apuntan ahí.
2. **Espejos:** GitLab (por ejemplo, la instancia interna de la empresa) y Google Secure Source Manager reciben
   los mismos commits y tags, y cada uno corre su propio CI y publica en su registro interno.
3. **PyPI desde una sola plataforma.** PyPI rechaza volver a subir una versión que ya existe, así que
   `PUBLISH_PYPI=true` se activa solo en una. Por defecto está apagado en todas.

Si prefieres que el canónico sea GitLab, cambia las URLs de `pyproject.toml` (`[project.urls]`) y los enlaces
al final de `CHANGELOG.md`, y activa `PUBLISH_PYPI` en GitLab en lugar de GitHub.

## Empujar a varias plataformas a la vez

Con un solo `git push` se actualizan todos los remotos:

```bash
# Remotos individuales (útiles para fetch o para empujar a uno solo)
git remote add github git@github.com:IsaacMendezEcheverria/helmreview.git
git remote add gitlab git@gitlab.com:TU_GRUPO/helmreview.git
git remote add google https://INSTANCIA-NUMERO_PROYECTO-git.REGION.sourcemanager.dev/TU_PROYECTO/helmreview.git

# "origin" hace fetch de GitHub y push a los tres
git remote add origin git@github.com:IsaacMendezEcheverria/helmreview.git      # o set-url si ya existe
git remote set-url --add --push origin git@github.com:IsaacMendezEcheverria/helmreview.git
git remote set-url --add --push origin git@gitlab.com:TU_GRUPO/helmreview.git
git remote set-url --add --push origin https://INSTANCIA-NUMERO_PROYECTO-git.REGION.sourcemanager.dev/TU_PROYECTO/helmreview.git

git remote -v
git push origin main --follow-tags
```

Alternativa sin depender de tu estación: en GitLab, *Settings → Repository → Mirroring repositories* permite
configurar un push mirror hacia GitHub (o un pull mirror desde GitHub, según tu plan de GitLab).

---

## GitHub

1. Crea el repositorio **público** y vacío (sin README, licencia ni .gitignore):
   ```bash
   gh repo create IsaacMendezEcheverria/helmreview --public --description "Revisión estática local de Helm charts para Kubernetes y OpenShift"
   ```
2. Empuja `main` y los tags.
3. *Settings → General*: activa Issues y Discussions. En *Settings → Code security*, activa
   *Private vulnerability reporting*, *Dependabot alerts* y *Secret scanning*.
4. *Settings → Branches* (o *Rules → Rulesets*): protege `main`, exige PR y que pasen los checks `lint`,
   `test` y `build`.
5. **PyPI con Trusted Publishing** (no se guarda ningún token):
   - En <https://pypi.org/manage/account/publishing/> agrega un *pending publisher* de GitHub con
     owner `IsaacMendezEcheverria`, repositorio `helmreview`, workflow `release.yml` y environment `pypi`.
   - En GitHub, *Settings → Environments*: crea `pypi` (opcional: exige aprobación manual).
   - *Settings → Secrets and variables → Actions → Variables*: agrega `PUBLISH_PYPI` = `true`.
6. *About* (engranaje en la portada del repo): agrega los topics `helm`, `kubernetes`, `openshift`, `devops`,
   `python`, `cli` y `linter`.

## GitLab

1. Crea el proyecto (público o interno) y empuja `main` y los tags. El pipeline arranca solo.
2. *Settings → Repository → Protected branches/tags*: protege `main` y los tags `v*`.
3. *Settings → Merge requests*: activa *Pipelines must succeed* y el *squash* por defecto.
4. **Package Registry:** los tags publican solos en el registro del proyecto. Para instalar:
   ```bash
   pip install --index-url https://gitlab.com/api/v4/projects/ID_PROYECTO/packages/pypi/simple helmreview
   ```
   Para un proyecto privado, agrega credenciales a la URL (`https://__token__:TOKEN@...`) con un token de
   `read_api`.
5. **PyPI (opcional, solo si GitLab es quien publica):** registra un *trusted publisher* de GitLab en PyPI
   (namespace, proyecto, archivo `.gitlab-ci.yml` y environment `pypi`) y define la variable CI/CD
   `PUBLISH_PYPI` = `true`.

## Google Cloud (Secure Source Manager + Cloud Build + Artifact Registry)

> Cloud Source Repositories no acepta clientes nuevos desde junio de 2024. Su reemplazo es
> **Secure Source Manager (SSM)**, que es lo que se describe aquí. Los mismos archivos de `.cloudbuild/`
> también sirven con triggers de Cloud Build conectados a GitHub o GitLab.

1. **Service account para los builds:**
   ```bash
   PROJECT=TU_PROYECTO
   gcloud iam service-accounts create cloudbuild-helmreview --project $PROJECT
   SA=cloudbuild-helmreview@$PROJECT.iam.gserviceaccount.com
   gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$SA --role=roles/logging.logWriter
   ```
2. **Repositorio Python en Artifact Registry** (destino del release):
   ```bash
   gcloud artifacts repositories create helmreview --repository-format=python \
     --location=us-central1 --project $PROJECT
   gcloud artifacts repositories add-iam-policy-binding helmreview --location=us-central1 \
     --member=serviceAccount:$SA --role=roles/artifactregistry.writer --project $PROJECT
   ```
3. **Repositorio en SSM:** créalo en tu instancia, configura git con
   `git config --global credential.'https://*.*.sourcemanager.dev'.helper gcloud.sh` y empuja. Copia la URL
   exacta del repositorio desde la consola.
4. **Triggers:** edita `.cloudbuild/triggers.yaml` (reemplaza `TU_PROYECTO` y la service account). SSM lo lee
   de la rama por defecto y crea los triggers: PR hacia `main`, push a `main` y tags `vX.Y.Z`. Si tu
   instancia no dispara builds por tag, ejecuta el release a mano:
   ```bash
   gcloud builds submit --config .cloudbuild/release.yaml \
     --substitutions=_AR_LOCATION=us-central1,_AR_REPO=helmreview .
   ```
5. **Con GitHub o GitLab en lugar de SSM:** conecta el repositorio en *Cloud Build → Repositories* y crea los
   triggers apuntando a `.cloudbuild/cloudbuild.yaml` (PR y `main`) y a `.cloudbuild/release.yaml` (tag
   `^v\d+\.\d+\.\d+$`). `triggers.yaml` solo lo usa SSM.
6. **Instalación desde Artifact Registry:**
   ```bash
   pip install keyrings.google-artifactregistry-auth
   pip install --index-url https://us-central1-python.pkg.dev/TU_PROYECTO/helmreview/simple/ helmreview
   ```

## Mantener la paridad entre plataformas

Si cambias un paso del CI (versión de helm, versiones de Python o un comando de lint), cámbialo en los tres
lugares: `.github/workflows/`, `.gitlab-ci.yml` y `.cloudbuild/`. La versión de helm está en `HELM_VERSION`
(GitHub y GitLab) y en `_HELM_VERSION` (Cloud Build).
