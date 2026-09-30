"""Orquestación del análisis y checks de recursos que no son workloads.

Para agregar un check de un nuevo tipo de recurso: escribir una función
`_check_<kind>(rep, obj, src, ctx)` y registrarla en KIND_CHECKS (ver docs/adding-a-check.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from helmreview.checks.workloads import analyze_workload
from helmreview.constants import DEPRECATED_APIS, WORKLOADS
from helmreview.k8s import rid, to_int
from helmreview.models import ChartReport, Storage
from helmreview.quantities import parse_mem


@dataclass
class Context:
    """Información cruzada entre recursos del mismo render."""

    namespace: str
    openshift: bool
    hpas: dict = field(default_factory=dict)  # (kind, name) -> (min, max)
    pdbs: list = field(default_factory=list)
    netpols: list = field(default_factory=list)
    workload_keys: set = field(default_factory=set)


# --------------------------------------------------------------------------------------
# Checks por tipo de recurso
# --------------------------------------------------------------------------------------
def _check_secret(rep, obj, src, ctx):
    if (obj.get("data") or obj.get("stringData")) and obj.get("type") != "kubernetes.io/service-account-token":
        rep.add(
            "MEDIUM",
            "secret-embebido",
            rid(obj),
            "Secret con datos renderizados desde el chart: verificar que no haya valores reales en values "
            "versionados (preferir External Secrets / Sealed Secrets / SOPS)",
            source=src,
        )


def _check_ingress(rep, obj, src, ctx):
    r, spec = rid(obj), obj.get("spec") or {}
    ann = (obj.get("metadata") or {}).get("annotations") or {}
    if not spec.get("tls") and not (ctx.openshift and ann.get("route.openshift.io/termination")):
        rep.add("MEDIUM", "ingress-tls", r, "Ingress sin bloque tls (tráfico HTTP sin cifrar)", source=src)
    if ctx.openshift:
        rep.add(
            "INFO",
            "ocp-ingress",
            r,
            "OpenShift convierte este Ingress en Route automáticamente; la terminación TLS se controla con la "
            "anotación route.openshift.io/termination",
            source=src,
        )
    elif not spec.get("ingressClassName") and "kubernetes.io/ingress.class" not in ann:
        rep.add("LOW", "ingress-class", r, "Sin ingressClassName: depende de la IngressClass por defecto", source=src)


def _check_route(rep, obj, src, ctx):
    r, spec = rid(obj), obj.get("spec") or {}
    tls = spec.get("tls") or {}
    if not tls:
        rep.add("MEDIUM", "ocp-route-tls", r, "Route sin TLS (tráfico HTTP sin cifrar)", source=src)
    else:
        term = tls.get("termination")
        if term not in ("edge", "reencrypt", "passthrough"):
            rep.add("MEDIUM", "ocp-route-tls", r, f"Route con termination inválida o vacía: '{term}'", source=src)
        if tls.get("insecureEdgeTerminationPolicy") == "Allow":
            rep.add(
                "MEDIUM",
                "ocp-route-tls",
                r,
                "insecureEdgeTerminationPolicy: Allow (acepta HTTP); usar Redirect",
                source=src,
            )
        if tls.get("key") or tls.get("certificate"):
            rep.add(
                "MEDIUM",
                "ocp-route-cert",
                r,
                "Certificado/llave embebidos en la Route: verificar que no estén en values versionados",
                source=src,
            )
    if not (spec.get("to") or {}).get("name"):
        rep.add("HIGH", "ocp-route", r, "Route sin spec.to.name (no apunta a ningún Service)", source=src)


def _check_service(rep, obj, src, ctx):
    r, spec = rid(obj), obj.get("spec") or {}
    stype = spec.get("type", "ClusterIP")
    if stype == "NodePort":
        rep.add("LOW", "service-type", r, "Service NodePort: expone puertos en todos los nodos", source=src)
    elif stype == "LoadBalancer":
        rep.add("INFO", "service-type", r, "Service LoadBalancer: requiere LB/MetalLB en el cluster", source=src)
    if spec.get("externalIPs"):
        rep.add("MEDIUM", "service-externalips", r, f"externalIPs definidos: {spec['externalIPs']}", source=src)


def _check_binding(rep, obj, src, ctx):
    r = rid(obj)
    role = (obj.get("roleRef") or {}).get("name", "")
    if role == "cluster-admin":
        rep.add("HIGH", "rbac", r, "Binding a cluster-admin", source=src)
    if role.startswith("system:openshift:scc:"):
        rep.add(
            "HIGH",
            "ocp-scc-rbac",
            r,
            f"Asigna la SCC '{role.rsplit(':', 1)[-1]}' al ServiceAccount: verificar aprobación",
            source=src,
        )


def _check_role(rep, obj, src, ctx):
    r, kind = rid(obj), obj["kind"]
    for rule in obj.get("rules") or []:
        verbs = set(rule.get("verbs") or [])
        resources = set(rule.get("resources") or [])
        groups = set(rule.get("apiGroups") or [])
        if "*" in verbs or "*" in resources or "*" in groups:
            rep.add(
                "MEDIUM",
                "rbac-wildcard",
                r,
                f"Regla con comodín: apiGroups={sorted(groups)} resources={sorted(resources)} verbs={sorted(verbs)}",
                source=src,
            )
        if kind == "ClusterRole" and "secrets" in resources and verbs & {"get", "list", "watch", "*"}:
            rep.add("MEDIUM", "rbac-secrets", r, "Lectura de Secrets a nivel de cluster", source=src)
        if "securitycontextconstraints" in resources and verbs & {"use", "*"}:
            names = rule.get("resourceNames") or ["(todas)"]
            rep.add(
                "HIGH",
                "ocp-scc-rbac",
                r,
                f"Otorga 'use' sobre SCC: {', '.join(names)}. Verificar que esté aprobado por seguridad",
                source=src,
            )


def _check_pvc(rep, obj, src, ctx):
    r, spec = rid(obj), obj.get("spec") or {}
    size = parse_mem(((spec.get("resources") or {}).get("requests") or {}).get("storage")) or 0
    sc = spec.get("storageClassName")
    rep.storage.append(
        Storage(r, size, 1, sc if sc is not None else "(default)", ",".join(spec.get("accessModes") or []))
    )
    if sc is None:
        rep.add("INFO", "storageclass", r, "Sin storageClassName: usa la StorageClass por defecto", source=src)


def _check_hpa(rep, obj, src, ctx):
    r, spec = rid(obj), obj.get("spec") or {}
    ref = spec.get("scaleTargetRef") or {}
    if (ref.get("kind"), ref.get("name")) not in ctx.workload_keys:
        rep.add(
            "MEDIUM",
            "hpa-target",
            r,
            f"HPA apunta a {ref.get('kind')}/{ref.get('name')}, que no está en el chart",
            source=src,
        )
    if to_int(spec.get("minReplicas"), 1) < 2:
        rep.add("LOW", "hpa-min", r, "HPA con minReplicas < 2: puede escalar a una sola réplica", source=src)


def _check_scc(rep, obj, src, ctx):
    flags = [
        k
        for k in (
            "allowPrivilegedContainer",
            "allowHostNetwork",
            "allowHostPID",
            "allowHostIPC",
            "allowHostDirVolumePlugin",
            "allowHostPorts",
        )
        if obj.get(k)
    ]
    if (obj.get("runAsUser") or {}).get("type") == "RunAsAny":
        flags.append("runAsUser: RunAsAny")
    rep.add(
        "HIGH",
        "ocp-scc",
        rid(obj),
        "El chart crea una SCC (requiere cluster-admin y aprobación de seguridad)"
        + (f"; permisos amplios: {', '.join(flags)}" if flags else ""),
        source=src,
    )


def _check_build(rep, obj, src, ctx):
    rep.add(
        "INFO",
        "ocp-build",
        rid(obj),
        f"{obj['kind']} en un chart de despliegue: revisar si corresponde al pipeline",
        source=src,
    )


def _check_namespace(rep, obj, src, ctx):
    rep.add(
        "LOW",
        "namespace-en-chart",
        rid(obj),
        "El chart crea el namespace/proyecto: normalmente se crea aparte (oc new-project / GitOps)",
        source=src,
    )


KIND_CHECKS = {
    "Secret": _check_secret,
    "Ingress": _check_ingress,
    "Route": _check_route,
    "Service": _check_service,
    "ClusterRoleBinding": _check_binding,
    "RoleBinding": _check_binding,
    "ClusterRole": _check_role,
    "Role": _check_role,
    "PersistentVolumeClaim": _check_pvc,
    "HorizontalPodAutoscaler": _check_hpa,
    "SecurityContextConstraints": _check_scc,
    "BuildConfig": _check_build,
    "ImageStream": _check_build,
    "Namespace": _check_namespace,
    "Project": _check_namespace,
    "ProjectRequest": _check_namespace,
}


# --------------------------------------------------------------------------------------
# Orquestación
# --------------------------------------------------------------------------------------
def _build_context(docs, namespace, openshift) -> Context:
    ctx = Context(namespace=namespace, openshift=openshift)
    for obj, _ in docs:
        kind = obj["kind"]
        if kind == "HorizontalPodAutoscaler":
            spec = obj.get("spec") or {}
            ref = spec.get("scaleTargetRef") or {}
            ctx.hpas[(ref.get("kind"), ref.get("name"))] = (
                to_int(spec.get("minReplicas"), 1),
                to_int(spec.get("maxReplicas"), 0),
            )
        elif kind == "PodDisruptionBudget":
            ctx.pdbs.append(obj)
        elif kind == "NetworkPolicy":
            ctx.netpols.append(obj)
        elif kind in WORKLOADS:
            ctx.workload_keys.add((kind, (obj.get("metadata") or {}).get("name")))
    return ctx


def analyze(rep: ChartReport, docs: list[tuple[dict, str]], namespace: str, platform: str = "kubernetes") -> None:
    """Ejecuta todos los checks sobre los manifiestos renderizados."""
    valid = []
    for obj, src in docs:
        if obj["kind"] == "__YAML_ERROR__":
            rep.add("HIGH", "yaml", "render", f"YAML inválido: {obj['error'][:300]}", source=src)
        else:
            valid.append((obj, src))

    counts: dict[str, int] = {}
    for obj, _ in valid:
        counts[obj["kind"]] = counts.get(obj["kind"], 0) + 1
    rep.resources_count = dict(sorted(counts.items()))

    ctx = _build_context(valid, namespace, platform == "openshift")

    for obj, src in valid:
        kind, r = obj["kind"], rid(obj)
        api = obj.get("apiVersion", "")
        if api in DEPRECATED_APIS:
            rep.add(
                "HIGH",
                "api-deprecada",
                r,
                f"apiVersion {api} eliminada en Kubernetes {DEPRECATED_APIS[api]}",
                source=src,
            )
        ns = (obj.get("metadata") or {}).get("namespace")
        if ns and ns != namespace:
            rep.add(
                "LOW",
                "namespace-fijo",
                r,
                f"Namespace fijo '{ns}' en el template (ignora el namespace del release '{namespace}')",
                source=src,
            )

        if kind in WORKLOADS:
            analyze_workload(rep, obj, src, ctx)
            if kind == "DeploymentConfig":
                rep.add(
                    "MEDIUM",
                    "ocp-deploymentconfig",
                    r,
                    "DeploymentConfig está deprecado desde OpenShift 4.14: migrar a Deployment",
                    source=src,
                )
        elif kind in KIND_CHECKS:
            KIND_CHECKS[kind](rep, obj, src, ctx)

    if any(k in counts for k in ("Deployment", "DeploymentConfig", "StatefulSet", "DaemonSet")) and not ctx.netpols:
        rep.add(
            "LOW",
            "networkpolicy",
            "chart",
            "El chart no define NetworkPolicy: el aislamiento depende de la política de red del cluster",
        )
