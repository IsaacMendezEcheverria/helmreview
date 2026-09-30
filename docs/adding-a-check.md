# Cómo agregar o modificar un check

## 1. Decide dónde va

| El check evalúa... | Archivo |
|---|---|
| Chart.yaml o archivos del chart | `checks/chart_meta.py` |
| Un Kind que no es workload (Ingress, Route, Role, PVC...) | `checks/manifests.py` → función `_check_<kind>` registrada en `KIND_CHECKS` |
| Pods, contenedores, réplicas o seguridad de workloads | `checks/workloads.py` |
| Algo que depende de varios recursos (por ejemplo, PDB ↔ Deployment) | Agrega los datos a `Context` en `manifests._build_context()` y úsalos en el check |
| Un dato de referencia (API, versión, capability) | `constants.py` |

## 2. Elige ID y severidad

- ID en minúsculas con guiones, único y descriptivo (`ocp-route-tls`, `pdb-bloqueo`). Prefijo `ocp-` si solo
  aplica a OpenShift.
- Severidad:
  - **HIGH**: el despliegue falla o hay un riesgo de seguridad claro.
  - **MEDIUM**: riesgo operativo real (caída, OOM, drain bloqueado).
  - **LOW**: buena práctica.
  - **INFO**: contexto útil que no requiere acción.

## 3. Implementa

Ejemplo: advertir cuando un CronJob no define `concurrencyPolicy`.

```python
# checks/workloads.py, dentro de analyze_workload(), después de _check_ha(...)
if kind == "CronJob" and not spec.get("concurrencyPolicy"):
    rep.add("LOW", "cronjob-concurrency", r,
            "CronJob sin concurrencyPolicy: pueden solaparse ejecuciones (default Allow)", source=src)
```

Ejemplo de un Kind nuevo:

```python
# checks/manifests.py
def _check_configmap(rep, obj, src, ctx):
    data = obj.get("data") or {}
    if sum(len(str(v)) for v in data.values()) > 900_000:
        rep.add("MEDIUM", "configmap-size", rid(obj), "ConfigMap cercano al límite de 1MiB de etcd", source=src)

KIND_CHECKS["ConfigMap"] = _check_configmap   # o agrégalo directamente al diccionario
```

Reglas:

- Usa siempre `rep.add(...)`. No agregues a `rep.findings` directamente, porque eso salta `--ignore`.
- Pasa `source=src` para que el reporte indique el template de origen.
- Tolera manifiestos incompletos: `(obj.get("spec") or {}).get(...)`.
- Si el check depende de la plataforma, consulta `ctx.openshift` (en workloads, el parámetro `openshift`).

## 4. Testea

Agrega el caso positivo y el negativo en `tests/test_kubernetes_checks.py` o `tests/test_openshift_checks.py`:

```python
def test_cronjob_concurrency():
    rep = analyze_text("""
apiVersion: batch/v1
kind: CronJob
metadata: {name: c}
spec:
  schedule: "* * * * *"
  jobTemplate: {spec: {template: {spec: {containers: [{name: c, image: a:1}]}}}}
""")
    assert "cronjob-concurrency" in checks_for(rep, "CronJob/c")
```

Si el check debería cumplirse en un chart bien hecho, verifica que `tests/fixtures/rendered/good.yaml` y el chart
`tests/fixtures/charts/sample` sigan sin hallazgos MEDIUM o HIGH. Si no es así, corrige el fixture.

## 5. Documenta

1. Agrega una fila en [checks.md](checks.md). `test_docs_catalog` falla si falta.
2. Agrega una línea en `CHANGELOG.md` → `## [Sin publicar]` → **Agregado**.

## Modificar un check existente

- Cambiar el mensaje o afinar la lógica: es una versión PATCH o MINOR y va en **Cambiado**.
- Subir la severidad de un check puede romper pipelines que usan `--fail-on`: menciónalo explícitamente en el
  CHANGELOG.
- **Nunca renombres un ID.** Crea el nuevo, elimina el viejo y regístralo en **Eliminado**. Es un cambio MAJOR.
