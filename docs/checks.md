# Catálogo de checks

Cada hallazgo tiene un **ID estable** (columna *Check*). Sirve para:

- Omitir un check con `--ignore <id>[,<id>...]`.
- Filtrar el JSON o el reporte Markdown.
- Referenciar el check en tickets o excepciones aprobadas.

> **Regla de mantenimiento:** no cambies el ID de un check existente, porque rompe los `--ignore` que la gente ya
> tenga configurados en sus pipelines. Si un check cambia de significado, crea uno nuevo y marca el viejo como
> eliminado en el CHANGELOG. El test `tests/test_docs_catalog.py` falla si un ID del código no está en esta
> tabla, o si la tabla tiene IDs que ya no existen.

Severidades: **ALTA** (HIGH), **MEDIA** (MEDIUM), **BAJA** (LOW), **INFO**. La plataforma indica en qué modo
aplica el check (`k8s` = siempre, `ocp` = solo con `--platform openshift` / `--ocp-version`).

## Chart y ejecución de helm

| Check | Severidad | Plataforma | Qué detecta |
|---|---|---|---|
| `chart-yaml` | ALTA | k8s | Chart.yaml ausente o con YAML inválido |
| `chart-apiversion` | MEDIA | k8s | Chart con `apiVersion: v1` (formato Helm 2) |
| `chart-kubeversion` | BAJA | k8s | Chart.yaml sin `kubeVersion` |
| `chart-appversion` | INFO | k8s | Chart.yaml sin `appVersion` |
| `chart-dependency` | MEDIA / BAJA | k8s | Dependencia sin versión exacta (MEDIA) o desde repositorio `http://` (BAJA) |
| `chart-schema` | BAJA | k8s | Falta `values.schema.json` |
| `chart-lock` | BAJA | k8s | Tiene dependencias y no hay `Chart.lock` |
| `helm-lint` | ALTA / MEDIA / INFO | k8s | Salida de `helm lint` (ERROR / WARNING / INFO) |
| `helm-dependency` | ALTA | k8s | `helm dependency build/update` falló (con `--dep-update`) |
| `helm-template` | ALTA | k8s | `helm template` falló: no se pudo renderizar |
| `yaml` | ALTA | k8s | Documento YAML inválido en el render |

## Recursos y capacidad

| Check | Severidad | Plataforma | Qué detecta |
|---|---|---|---|
| `resources` | ALTA / MEDIA / BAJA / INFO | k8s | Sin requests ni limits (ALTA); falta request o `limits.memory` (MEDIA); request implícito = limit o sobre-compromiso > 4x (BAJA); sin `limits.cpu` (INFO). También request > limit (ALTA) |
| `resources-invalido` | ALTA | k8s | Cantidad de CPU o memoria no parseable |
| `replicas` | MEDIA | k8s | Deployment/StatefulSet/DeploymentConfig con 1 réplica y sin HPA |
| `replicas-hpa` | BAJA | k8s | Define `spec.replicas` y además tiene HPA (cada upgrade reinicia el conteo) |
| `hpa-target` | MEDIA | k8s | HPA que apunta a un workload que no está en el chart |
| `hpa-min` | BAJA | k8s | HPA con `minReplicas` < 2 |
| `distribucion` | BAJA | k8s | Varias réplicas sin podAntiAffinity ni topologySpreadConstraints |
| `pdb` | BAJA | k8s | Varias réplicas sin PodDisruptionBudget |
| `pdb-bloqueo` | MEDIA | k8s | PDB que impide cualquier eviction (bloquea el drain de nodos) |
| `storageclass` | INFO | k8s | PVC sin `storageClassName` (usa la StorageClass por defecto) |

## Salud

| Check | Severidad | Plataforma | Qué detecta |
|---|---|---|---|
| `probes` | MEDIA / BAJA | k8s | Sin readinessProbe (MEDIA); sin livenessProbe o liveness idéntica a readiness (BAJA). No aplica a Jobs ni initContainers |

## Seguridad (general)

| Check | Severidad | Plataforma | Qué detecta |
|---|---|---|---|
| `image-tag` | ALTA | k8s | Imagen sin tag o con `latest` |
| `security` | ALTA / MEDIA / BAJA | k8s | privileged, root, capabilities peligrosas (ALTA); allowPrivilegeEscalation, no garantiza no-root (MEDIA); readOnlyRootFilesystem, drop ALL, seccomp (BAJA) |
| `host-namespaces` | ALTA | k8s | `hostNetwork`, `hostPID` o `hostIPC` |
| `hostpath` | ALTA / MEDIA | k8s | Volumen hostPath (MEDIA en DaemonSets) |
| `hostport` | MEDIA | k8s | Contenedor con `hostPort` |
| `secret-en-env` | ALTA | k8s | Variable sensible (PASSWORD, TOKEN, ...) con valor literal |
| `secret-embebido` | MEDIA | k8s | Secret con datos renderizados desde el chart |
| `serviceaccount` | BAJA | k8s | Usa el ServiceAccount `default` |
| `checksum-config` | INFO | k8s | Monta ConfigMap/Secret sin anotación `checksum/*` (no hay rollout al cambiar config) |
| `rbac` | ALTA | k8s | Binding a `cluster-admin` |
| `rbac-wildcard` | MEDIA | k8s | Regla RBAC con `*` |
| `rbac-secrets` | MEDIA | k8s | ClusterRole que lee Secrets |

## Red y exposición

| Check | Severidad | Plataforma | Qué detecta |
|---|---|---|---|
| `ingress-tls` | MEDIA | k8s | Ingress sin TLS |
| `ingress-class` | BAJA | k8s | Ingress sin `ingressClassName` (solo en modo Kubernetes) |
| `service-type` | BAJA / INFO | k8s | Service NodePort (BAJA) o LoadBalancer (INFO) |
| `service-externalips` | MEDIA | k8s | Service con `externalIPs` |
| `networkpolicy` | BAJA | k8s | El chart no define NetworkPolicy, o ninguna selecciona el pod |

## Compatibilidad y estructura

| Check | Severidad | Plataforma | Qué detecta |
|---|---|---|---|
| `api-deprecada` | ALTA | k8s | apiVersion eliminada en Kubernetes (tabla en `constants.py`) |
| `namespace-fijo` | BAJA | k8s | Recurso con namespace fijo distinto al del release |
| `namespace-en-chart` | BAJA | k8s | El chart crea Namespace/Project |

## OpenShift

| Check | Severidad | Plataforma | Qué detecta |
|---|---|---|---|
| `ocp-scc` | ALTA | ocp | Workload incompatible con `restricted-v2` (lista las SCC que requeriría), o el chart crea una SCC |
| `ocp-uid` | ALTA / MEDIA | ocp | `runAsUser` fijo (ALTA); `runAsGroup`, `fsGroup` o `supplementalGroups` fijos (MEDIA) |
| `ocp-caps` | ALTA | ocp | Capabilities distintas de `NET_BIND_SERVICE` |
| `ocp-puerto` | MEDIA | ocp | `containerPort` < 1024 sin `NET_BIND_SERVICE` |
| `ocp-selinux` | MEDIA | ocp | `seLinuxOptions` personalizado |
| `ocp-scc-rbac` | ALTA | ocp | Binding a `system:openshift:scc:*` o regla con `use` sobre SCC |
| `ocp-route` | ALTA | ocp | Route sin `spec.to.name` |
| `ocp-route-tls` | MEDIA | ocp | Route sin TLS, con termination inválida o con `insecureEdgeTerminationPolicy: Allow` |
| `ocp-route-cert` | MEDIA | ocp | Certificado o llave embebidos en la Route |
| `ocp-deploymentconfig` | MEDIA | ocp | Uso de DeploymentConfig (deprecado desde OCP 4.14) |
| `ocp-ingress` | INFO | ocp | Ingress que OpenShift convertirá en Route |
| `ocp-build` | INFO | ocp | BuildConfig o ImageStream dentro de un chart de despliegue |

## Herramientas externas (`--external`)

| Check | Severidad | Plataforma | Qué detecta |
|---|---|---|---|
| `ext-kubeconform` | MEDIA | k8s | kubeconform terminó con error (el detalle va en el reporte) |
| `ext-kube-linter` | MEDIA | k8s | kube-linter reportó problemas |
| `ext-trivy` | MEDIA | k8s | trivy config reportó problemas |
