#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
helm_review.py - Revisión local de Helm charts (sin subir nada a ningún servicio).

Qué hace:
  1. Lee Chart.yaml y valida metadatos (apiVersion, kubeVersion, dependencias fijadas, schema).
  2. Ejecuta `helm lint` y `helm template` con los values que indiques.
  3. Analiza el YAML renderizado: recursos (requests/limits), réplicas/HPA/PDB, probes,
     securityContext, imágenes, secretos, Ingress/Service, RBAC, APIs deprecadas, storage.
  4. Calcula la capacidad configurada (CPU/memoria por pod y totales, almacenamiento).
  5. Opcional (--external): ejecuta kubeconform, kube-linter y trivy si están en el PATH.

Requisitos:
  - Python 3.9+
  - PyYAML:  pip install pyyaml
  - helm en el PATH (no se necesita acceso al cluster: helm template trabaja offline)

Ejemplos:
  python helm_review.py ./mychart -f values-prod.yaml
  python helm_review.py ./mychart -f values.yaml -f values-prod.yaml --kube-version 1.30 --report rev.md
  python helm_review.py ./charts/* --min-severity medium --json rev.json --fail-on high
  python helm_review.py oci://harbor.local/charts/app --version 1.4.2 -f prod.yaml
  python helm_review.py ./mychart --rendered render.yaml        # analiza un YAML ya renderizado
  python helm_review.py ./mychart --external --save-rendered ./out

Códigos de salida: 0 = OK, 1 = error de ejecución, 2 = hallazgos >= --fail-on
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("Falta PyYAML. Instala con: pip install pyyaml")

# --------------------------------------------------------------------------------------
# Modelo
# --------------------------------------------------------------------------------------
SEVERITIES = ["HIGH", "MEDIUM", "LOW", "INFO"]
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}  # menor número = más grave
SEV_ES = {"HIGH": "ALTA", "MEDIUM": "MEDIA", "LOW": "BAJA", "INFO": "INFO"}
SEV_COLOR = {"HIGH": "\033[31m", "MEDIUM": "\033[33m", "LOW": "\033[36m", "INFO": "\033[90m"}
RESET, BOLD = "\033[0m", "\033[1m"

WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob", "Pod"}

# apiVersion -> versión de Kubernetes en la que se eliminó
DEPRECATED_APIS = {
    "extensions/v1beta1": "1.22",
    "apps/v1beta1": "1.16",
    "apps/v1beta2": "1.16",
    "networking.k8s.io/v1beta1": "1.22",
    "rbac.authorization.k8s.io/v1beta1": "1.22",
    "apiextensions.k8s.io/v1beta1": "1.22",
    "admissionregistration.k8s.io/v1beta1": "1.22",
    "scheduling.k8s.io/v1beta1": "1.22",
    "certificates.k8s.io/v1beta1": "1.22",
    "coordination.k8s.io/v1beta1": "1.22",
    "storage.k8s.io/v1beta1": "1.22 (CSIStorageCapacity: 1.27)",
    "policy/v1beta1": "1.25",
    "batch/v1beta1": "1.25",
    "autoscaling/v2beta1": "1.25",
    "autoscaling/v2beta2": "1.26",
    "discovery.k8s.io/v1beta1": "1.25",
    "events.k8s.io/v1beta1": "1.25",
    "node.k8s.io/v1beta1": "1.25",
    "flowcontrol.apiserver.k8s.io/v1beta1": "1.26",
    "flowcontrol.apiserver.k8s.io/v1beta2": "1.29",
    "flowcontrol.apiserver.k8s.io/v1beta3": "1.32",
}

SECRET_ENV = re.compile(r"(PASSWORD|PASSWD|\bPWD\b|SECRET|TOKEN|API_?KEY|PRIVATE_?KEY|CREDENTIALS?)", re.I)
DANGEROUS_CAPS = {"ALL", "SYS_ADMIN", "NET_ADMIN", "SYS_PTRACE", "SYS_MODULE", "DAC_READ_SEARCH", "BPF"}
PINNED_SEMVER = re.compile(r"^v?\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")


@dataclass
class Finding:
    severity: str
    check: str
    resource: str
    message: str
    container: str = ""
    source: str = ""


@dataclass
class Capacity:
    resource: str
    replicas: str
    replicas_base: int
    replicas_max: int
    per_node: bool
    cpu_req_m: float
    cpu_lim_m: float
    mem_req_b: float
    mem_lim_b: float


@dataclass
class Storage:
    resource: str
    size_b: float
    copies: int
    storage_class: str
    access_modes: str


@dataclass
class ChartReport:
    chart: str
    name: str = ""
    version: str = ""
    app_version: str = ""
    findings: list = field(default_factory=list)
    capacity: list = field(default_factory=list)
    storage: list = field(default_factory=list)
    resources_count: dict = field(default_factory=dict)
    external: dict = field(default_factory=dict)
    error: str = ""

    def add(self, sev, check, resource, message, container="", source=""):
        self.findings.append(Finding(sev, check, resource, message, container, source))


# --------------------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------------------
def run(cmd, timeout=300):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"No se encontró el ejecutable: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timeout ejecutando: {' '.join(cmd)}"


_MEM_SUFFIX = [("Ki", 2**10), ("Mi", 2**20), ("Gi", 2**30), ("Ti", 2**40), ("Pi", 2**50), ("Ei", 2**60),
               ("k", 1e3), ("K", 1e3), ("M", 1e6), ("G", 1e9), ("T", 1e12), ("P", 1e15), ("E", 1e18),
               ("m", 1e-3)]


def parse_mem(v):
    """Cantidad de memoria/almacenamiento de Kubernetes -> bytes (None si no es válida)."""
    if v is None:
        return None
    s = str(v).strip()
    for suf, mult in _MEM_SUFFIX:
        if s.endswith(suf):
            try:
                return float(s[: -len(suf)]) * mult
            except ValueError:
                return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_cpu(v):
    """Cantidad de CPU -> milicores (None si no es válida)."""
    if v is None:
        return None
    s = str(v).strip()
    try:
        return float(s[:-1]) if s.endswith("m") else float(s) * 1000
    except ValueError:
        return None


def fmt_cpu(m):
    if not m:
        return "-"
    if m < 1000:
        return f"{m:.0f}m"
    return f"{m / 1000:.2f}".rstrip("0").rstrip(".")


def fmt_mem(b):
    if not b:
        return "-"
    for suf, mult in (("Ti", 2**40), ("Gi", 2**30), ("Mi", 2**20), ("Ki", 2**10)):
        if b >= mult:
            return f"{b / mult:.2f}".rstrip("0").rstrip(".") + suf
    return f"{b:.0f}"


def to_int(v, default=1):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def rid(obj):
    return f"{obj.get('kind')}/{(obj.get('metadata') or {}).get('name', '?')}"


def image_ref(image):
    """Devuelve ('digest'|'tag'|'none', valor)."""
    if "@" in image:
        return "digest", image.split("@", 1)[1]
    last = image.rsplit("/", 1)[-1]
    if ":" in last:
        return "tag", last.split(":", 1)[1]
    return "none", ""


def selector_matches(selector, labels):
    """Evalúa un LabelSelector de Kubernetes contra un set de labels."""
    if selector is None:
        return False
    ml = selector.get("matchLabels") or {}
    exprs = selector.get("matchExpressions") or []
    if not ml and not exprs:
        return True  # selector vacío = todos los pods del namespace
    if any(labels.get(k) != v for k, v in ml.items()):
        return False
    for e in exprs:
        key, op, vals = e.get("key"), e.get("operator"), e.get("values") or []
        if op == "In" and labels.get(key) not in vals:
            return False
        if op == "NotIn" and labels.get(key) in vals:
            return False
        if op == "Exists" and key not in labels:
            return False
        if op == "DoesNotExist" and key in labels:
            return False
    return True


def pod_template(obj):
    kind, spec = obj["kind"], obj.get("spec") or {}
    if kind == "Pod":
        return obj.get("metadata") or {}, spec
    if kind == "CronJob":
        tpl = ((spec.get("jobTemplate") or {}).get("spec") or {}).get("template") or {}
    else:
        tpl = spec.get("template") or {}
    return tpl.get("metadata") or {}, tpl.get("spec") or {}


def sanitize_release(name):
    name = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    return (name or "release")[:53]


# --------------------------------------------------------------------------------------
# Helm
# --------------------------------------------------------------------------------------
def load_chart_yaml(chart, version=None):
    p = Path(chart)
    if p.is_dir():
        f = p / "Chart.yaml"
        return yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else None
    cmd = ["helm", "show", "chart", chart] + (["--version", version] if version else [])
    rc, out, _ = run(cmd)
    return yaml.safe_load(out) if rc == 0 else None


def helm_value_args(args):
    out = []
    for v in args.values:
        out += ["-f", v]
    for s in args.set:
        out += ["--set", s]
    return out


def helm_dep_build(rep, chart):
    if not Path(chart).is_dir():
        return
    rc, _, err = run(["helm", "dependency", "build", chart])
    if rc != 0:
        rc, _, err = run(["helm", "dependency", "update", chart])
    if rc != 0:
        rep.add("HIGH", "helm-dependency", "chart", f"No se pudieron resolver dependencias: {err.strip()[:500]}")


def helm_lint(args, rep, chart):
    cmd = ["helm", "lint", chart] + helm_value_args(args)
    rc, out, err = run(cmd)
    found = False
    for line in (out + "\n" + err).splitlines():
        m = re.match(r"\s*\[(ERROR|WARNING|INFO)\]\s*(.*)", line)
        if m:
            found = True
            sev = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "INFO"}[m.group(1)]
            rep.add(sev, "helm-lint", "chart", m.group(2).strip())
    if rc != 0 and not found:
        rep.add("HIGH", "helm-lint", "chart", f"helm lint falló: {(err or out).strip()[:500]}")


def helm_template(args, chart, release):
    cmd = ["helm", "template", release, chart, "--namespace", args.namespace, "--include-crds"]
    cmd += helm_value_args(args)
    if args.version:
        cmd += ["--version", args.version]
    if args.kube_version:
        cmd += ["--kube-version", args.kube_version]
    for a in args.api_versions:
        cmd += ["--api-versions", a]
    return run(cmd)


def parse_manifests(text):
    docs = []
    for chunk in re.split(r"^---\s*$", text, flags=re.M):
        if not chunk.strip():
            continue
        m = re.search(r"^# Source:\s*(.+)$", chunk, re.M)
        src = m.group(1).strip() if m else ""
        try:
            for obj in yaml.safe_load_all(chunk):
                if not isinstance(obj, dict) or not obj.get("kind"):
                    continue
                if obj["kind"].endswith("List") and isinstance(obj.get("items"), list):
                    docs += [(it, src) for it in obj["items"] if isinstance(it, dict) and it.get("kind")]
                else:
                    docs.append((obj, src))
        except yaml.YAMLError as e:
            docs.append(({"kind": "__YAML_ERROR__", "error": str(e)}, src))
    return docs


# --------------------------------------------------------------------------------------
# Checks de Chart.yaml
# --------------------------------------------------------------------------------------
def check_chart_meta(rep, chart, meta):
    rep.name = str(meta.get("name", ""))
    rep.version = str(meta.get("version", ""))
    rep.app_version = str(meta.get("appVersion", ""))
    if meta.get("apiVersion") != "v2":
        rep.add("MEDIUM", "chart-apiversion", "Chart.yaml",
                f"apiVersion '{meta.get('apiVersion')}' (formato Helm 2). Migrar a apiVersion: v2")
    if not meta.get("kubeVersion"):
        rep.add("LOW", "chart-kubeversion", "Chart.yaml",
                "Sin kubeVersion: el chart no declara con qué versiones de Kubernetes es compatible")
    if not meta.get("appVersion"):
        rep.add("INFO", "chart-appversion", "Chart.yaml", "Sin appVersion")
    deps = meta.get("dependencies") or []
    for d in deps:
        ver = str(d.get("version", "")).strip()
        name = d.get("name", "?")
        if not ver or not PINNED_SEMVER.match(ver):
            rep.add("MEDIUM", "chart-dependency", "Chart.yaml",
                    f"Dependencia '{name}' con versión no fijada ('{ver or 'vacía'}'): builds no reproducibles")
        repo = str(d.get("repository", ""))
        if repo.startswith("http://"):
            rep.add("LOW", "chart-dependency", "Chart.yaml", f"Dependencia '{name}' desde repositorio HTTP sin TLS")
    p = Path(chart)
    if p.is_dir():
        if not (p / "values.schema.json").exists():
            rep.add("LOW", "chart-schema", "chart",
                    "Sin values.schema.json: los values no se validan (errores de tipeo pasan silenciosos)")
        if deps and not (p / "Chart.lock").exists():
            rep.add("LOW", "chart-lock", "chart", "Tiene dependencias pero no hay Chart.lock versionado")


# --------------------------------------------------------------------------------------
# Análisis del YAML renderizado
# --------------------------------------------------------------------------------------
def analyze(rep, docs, namespace):
    by_kind = {}
    for obj, src in docs:
        by_kind.setdefault(obj["kind"], []).append((obj, src))

    for obj, src in by_kind.pop("__YAML_ERROR__", []):
        rep.add("HIGH", "yaml", "render", f"YAML inválido: {obj['error'][:300]}", source=src)
    rep.resources_count = {k: len(v) for k, v in sorted(by_kind.items())}

    hpas = {}
    for obj, src in by_kind.get("HorizontalPodAutoscaler", []):
        spec = obj.get("spec") or {}
        ref = spec.get("scaleTargetRef") or {}
        hpas[(ref.get("kind"), ref.get("name"))] = (to_int(spec.get("minReplicas"), 1),
                                                     to_int(spec.get("maxReplicas"), 0))
    pdbs = [o for o, _ in by_kind.get("PodDisruptionBudget", [])]
    netpols = [o for o, _ in by_kind.get("NetworkPolicy", [])]
    workload_keys = {(o["kind"], (o.get("metadata") or {}).get("name"))
                     for o, _ in docs if o["kind"] in WORKLOADS}

    for obj, src in docs:
        if obj["kind"] == "__YAML_ERROR__":
            continue
        kind, r = obj["kind"], rid(obj)
        meta = obj.get("metadata") or {}
        api = obj.get("apiVersion", "")
        if api in DEPRECATED_APIS:
            rep.add("HIGH", "api-deprecada", r, f"apiVersion {api} eliminada en Kubernetes {DEPRECATED_APIS[api]}",
                    source=src)
        ns = meta.get("namespace")
        if ns and ns != namespace:
            rep.add("LOW", "namespace-fijo", r,
                    f"Namespace fijo '{ns}' en el template (ignora el namespace del release '{namespace}')",
                    source=src)

        if kind in WORKLOADS:
            analyze_workload(rep, obj, src, hpas, pdbs, netpols)
        elif kind == "Secret":
            if (obj.get("data") or obj.get("stringData")) and obj.get("type") != "kubernetes.io/service-account-token":
                rep.add("MEDIUM", "secret-embebido", r,
                        "Secret con datos renderizados desde el chart: verificar que no haya valores reales en "
                        "values versionados (preferir External Secrets / Sealed Secrets / SOPS)", source=src)
        elif kind == "Ingress":
            spec = obj.get("spec") or {}
            if not spec.get("tls"):
                rep.add("MEDIUM", "ingress-tls", r, "Ingress sin bloque tls (tráfico HTTP sin cifrar)", source=src)
            ann = meta.get("annotations") or {}
            if not spec.get("ingressClassName") and "kubernetes.io/ingress.class" not in ann:
                rep.add("LOW", "ingress-class", r, "Sin ingressClassName: depende de la IngressClass por defecto",
                        source=src)
        elif kind == "Service":
            spec = obj.get("spec") or {}
            stype = spec.get("type", "ClusterIP")
            if stype == "NodePort":
                rep.add("LOW", "service-type", r, "Service NodePort: expone puertos en todos los nodos", source=src)
            elif stype == "LoadBalancer":
                rep.add("INFO", "service-type", r, "Service LoadBalancer: requiere LB/MetalLB en el cluster",
                        source=src)
            if spec.get("externalIPs"):
                rep.add("MEDIUM", "service-externalips", r, f"externalIPs definidos: {spec['externalIPs']}",
                        source=src)
        elif kind in ("ClusterRoleBinding", "RoleBinding"):
            if (obj.get("roleRef") or {}).get("name") == "cluster-admin":
                rep.add("HIGH", "rbac", r, "Binding a cluster-admin", source=src)
        elif kind in ("ClusterRole", "Role"):
            for rule in obj.get("rules") or []:
                verbs = set(rule.get("verbs") or [])
                resources = set(rule.get("resources") or [])
                groups = set(rule.get("apiGroups") or [])
                if "*" in verbs or "*" in resources or "*" in groups:
                    rep.add("MEDIUM", "rbac-wildcard", r,
                            f"Regla con comodín: apiGroups={sorted(groups)} resources={sorted(resources)} "
                            f"verbs={sorted(verbs)}", source=src)
                if kind == "ClusterRole" and "secrets" in resources and verbs & {"get", "list", "watch", "*"}:
                    rep.add("MEDIUM", "rbac-secrets", r, "Lectura de Secrets a nivel de cluster", source=src)
        elif kind == "PersistentVolumeClaim":
            spec = obj.get("spec") or {}
            size = parse_mem(((spec.get("resources") or {}).get("requests") or {}).get("storage")) or 0
            sc = spec.get("storageClassName")
            rep.storage.append(Storage(r, size, 1, sc if sc is not None else "(default)",
                                       ",".join(spec.get("accessModes") or [])))
            if sc is None:
                rep.add("INFO", "storageclass", r, "Sin storageClassName: usa la StorageClass por defecto",
                        source=src)
        elif kind == "HorizontalPodAutoscaler":
            spec = obj.get("spec") or {}
            ref = spec.get("scaleTargetRef") or {}
            if (ref.get("kind"), ref.get("name")) not in workload_keys:
                rep.add("MEDIUM", "hpa-target", r,
                        f"HPA apunta a {ref.get('kind')}/{ref.get('name')}, que no está en el chart", source=src)
            if to_int(spec.get("minReplicas"), 1) < 2:
                rep.add("LOW", "hpa-min", r, "HPA con minReplicas < 2: puede escalar a una sola réplica",
                        source=src)

    if any(k in by_kind for k in ("Deployment", "StatefulSet", "DaemonSet")) and not netpols:
        rep.add("LOW", "networkpolicy", "chart",
                "El chart no define NetworkPolicy: el aislamiento depende de la política de red del cluster")


def analyze_workload(rep, obj, src, hpas, pdbs, netpols):
    kind, r = obj["kind"], rid(obj)
    spec = obj.get("spec") or {}
    name = (obj.get("metadata") or {}).get("name")
    pmeta, pspec = pod_template(obj)
    labels = pmeta.get("labels") or {}
    hpa = hpas.get((kind, name))
    is_batch = kind in ("Job", "CronJob")
    per_node = kind == "DaemonSet"

    # ---- Réplicas / HA ----
    if kind in ("Deployment", "StatefulSet", "ReplicaSet"):
        base = to_int(spec.get("replicas"), hpa[0] if hpa else 1)
        rmax = hpa[1] if hpa and hpa[1] else base
        rtxt = str(base) + (f" (HPA {hpa[0]}-{hpa[1]})" if hpa else "")
    elif kind == "Job":
        base = rmax = to_int(spec.get("parallelism"), 1)
        rtxt = f"{base} (Job)"
    elif kind == "CronJob":
        jspec = (spec.get("jobTemplate") or {}).get("spec") or {}
        base = rmax = to_int(jspec.get("parallelism"), 1)
        rtxt = f"{base} por ejecución"
    elif per_node:
        base = rmax = 1
        rtxt = "1 por nodo"
    else:
        base = rmax = 1
        rtxt = "1"

    if kind in ("Deployment", "StatefulSet"):
        if not hpa and base < 2:
            rep.add("MEDIUM", "replicas", r, f"{base} réplica(s) sin HPA: sin alta disponibilidad", source=src)
        if hpa and spec.get("replicas") is not None:
            rep.add("LOW", "replicas-hpa", r,
                    "Define spec.replicas y además tiene HPA: cada helm upgrade reinicia el número de réplicas",
                    source=src)
        multi = base > 1 or bool(hpa)
        if multi:
            anti = (pspec.get("affinity") or {}).get("podAntiAffinity")
            if not anti and not pspec.get("topologySpreadConstraints"):
                rep.add("LOW", "distribucion", r,
                        "Varias réplicas sin podAntiAffinity ni topologySpreadConstraints: pueden caer en el mismo nodo",
                        source=src)
        matching = [p for p in pdbs if selector_matches((p.get("spec") or {}).get("selector"), labels)]
        if multi and not matching:
            rep.add("LOW", "pdb", r, "Sin PodDisruptionBudget: un drain puede bajar todas las réplicas", source=src)
        eff_min = hpa[0] if hpa else base
        for p in matching:
            ps = p.get("spec") or {}
            min_av, max_un = ps.get("minAvailable"), ps.get("maxUnavailable")
            blocks = (isinstance(min_av, int) and min_av >= eff_min) or min_av == "100%" or max_un in (0, "0%")
            if blocks:
                rep.add("MEDIUM", "pdb-bloqueo", r,
                        f"{rid(p)} (minAvailable={min_av}, maxUnavailable={max_un}) con {eff_min} réplica(s) mínima(s): "
                        "bloquea drains/upgrades de nodos", source=src)

    # ---- Seguridad a nivel de pod ----
    for fld in ("hostNetwork", "hostPID", "hostIPC"):
        if pspec.get(fld):
            rep.add("HIGH", "host-namespaces", r, f"{fld}: true", source=src)
    for vol in pspec.get("volumes") or []:
        if "hostPath" in vol:
            path = (vol.get("hostPath") or {}).get("path")
            rep.add("MEDIUM" if per_node else "HIGH", "hostpath", r,
                    f"Volumen hostPath '{path}' (acceso al filesystem del nodo)", source=src)
    sa = pspec.get("serviceAccountName") or pspec.get("serviceAccount")
    if not sa or sa == "default":
        rep.add("LOW", "serviceaccount", r, "Usa el ServiceAccount 'default' del namespace", source=src)
    if netpols and not any(selector_matches((n.get("spec") or {}).get("podSelector"), labels) for n in netpols):
        rep.add("LOW", "networkpolicy", r, "Ninguna NetworkPolicy del chart selecciona estos pods", source=src)

    # checksum para rollout automático al cambiar config
    uses_cfg = any("configMap" in v or "secret" in v for v in pspec.get("volumes") or [])
    for c in pspec.get("containers") or []:
        uses_cfg = uses_cfg or any("configMapRef" in e or "secretRef" in e for e in c.get("envFrom") or [])
    ann = pmeta.get("annotations") or {}
    if uses_cfg and not any(k.startswith("checksum/") for k in ann):
        rep.add("INFO", "checksum-config", r,
                "Monta ConfigMap/Secret sin anotación checksum/*: cambios de config no reinician los pods",
                source=src)

    psc = pspec.get("securityContext") or {}

    # ---- Contenedores ----
    sum_cpu_r = sum_cpu_l = sum_mem_r = sum_mem_l = 0.0
    init_cpu_r = init_mem_r = init_cpu_l = init_mem_l = 0.0
    all_containers = [(c, False) for c in pspec.get("containers") or []] + \
                     [(c, True) for c in pspec.get("initContainers") or []]

    for c, is_init in all_containers:
        cn = c.get("name", "?") + (" (init)" if is_init else "")

        def add(sev, check, msg):
            rep.add(sev, check, r, msg, container=cn, source=src)

        # Imagen
        image = str(c.get("image", ""))
        itype, ival = image_ref(image)
        if itype == "none":
            add("HIGH", "image-tag", f"Imagen '{image}' sin tag (usa 'latest' implícito)")
        elif itype == "tag" and ival == "latest":
            add("HIGH", "image-tag", f"Imagen '{image}' con tag 'latest'")

        # Recursos
        res = c.get("resources") or {}
        req, lim = res.get("requests") or {}, res.get("limits") or {}
        cpu_r, mem_r = parse_cpu(req.get("cpu")), parse_mem(req.get("memory"))
        cpu_l, mem_l = parse_cpu(lim.get("cpu")), parse_mem(lim.get("memory"))
        for label, raw, parsed in (("requests.cpu", req.get("cpu"), cpu_r), ("requests.memory", req.get("memory"), mem_r),
                                   ("limits.cpu", lim.get("cpu"), cpu_l), ("limits.memory", lim.get("memory"), mem_l)):
            if raw is not None and parsed is None:
                add("HIGH", "resources-invalido", f"{label} con valor inválido: '{raw}'")
        if not req and not lim:
            add("HIGH", "resources", "Sin requests ni limits (QoS BestEffort: primer candidato a eviction)")
        else:
            if req.get("cpu") is None:
                if cpu_l is not None:
                    add("LOW", "resources", "Sin requests.cpu: Kubernetes asume request = limit")
                else:
                    add("MEDIUM", "resources", "Sin requests.cpu: el scheduler no reserva CPU")
            if req.get("memory") is None:
                if mem_l is not None:
                    add("LOW", "resources", "Sin requests.memory: Kubernetes asume request = limit")
                else:
                    add("MEDIUM", "resources", "Sin requests.memory: el scheduler no reserva memoria")
            if lim.get("memory") is None:
                add("MEDIUM", "resources", "Sin limits.memory: puede consumir memoria del nodo sin tope")
            if lim.get("cpu") is None:
                add("INFO", "resources", "Sin limits.cpu (válido si es intencional para evitar throttling)")
        if cpu_r and cpu_l and cpu_r > cpu_l:
            add("HIGH", "resources", f"requests.cpu ({fmt_cpu(cpu_r)}) > limits.cpu ({fmt_cpu(cpu_l)}): manifiesto inválido")
        if mem_r and mem_l and mem_r > mem_l:
            add("HIGH", "resources", f"requests.memory ({fmt_mem(mem_r)}) > limits.memory ({fmt_mem(mem_l)}): manifiesto inválido")
        if mem_r and mem_l and mem_l / mem_r > 4:
            add("LOW", "resources", f"limits.memory es {mem_l / mem_r:.1f}x el request: sobre-compromiso alto de memoria")

        eff_cpu_r = cpu_r if cpu_r is not None else (cpu_l or 0)
        eff_mem_r = mem_r if mem_r is not None else (mem_l or 0)
        if is_init:
            init_cpu_r, init_mem_r = max(init_cpu_r, eff_cpu_r), max(init_mem_r, eff_mem_r)
            init_cpu_l, init_mem_l = max(init_cpu_l, cpu_l or 0), max(init_mem_l, mem_l or 0)
        else:
            sum_cpu_r += eff_cpu_r
            sum_mem_r += eff_mem_r
            sum_cpu_l += cpu_l or 0
            sum_mem_l += mem_l or 0

        # Probes
        if not is_init and not is_batch:
            rp, lp = c.get("readinessProbe"), c.get("livenessProbe")
            if not rp:
                add("MEDIUM", "probes", "Sin readinessProbe: recibe tráfico antes de estar listo")
            if not lp:
                add("LOW", "probes", "Sin livenessProbe: no se reinicia si se cuelga")
            if rp and lp and rp == lp:
                add("LOW", "probes", "livenessProbe idéntica a readinessProbe: riesgo de reinicios en cascada")

        # securityContext
        csc = c.get("securityContext") or {}

        def eff(key):
            return csc.get(key, psc.get(key))

        if csc.get("privileged"):
            add("HIGH", "security", "Contenedor privileged: true")
        if csc.get("allowPrivilegeEscalation") is not False:
            add("MEDIUM", "security", "allowPrivilegeEscalation no está en false")
        run_user = eff("runAsUser")
        if run_user == 0:
            add("HIGH", "security", "Corre como root (runAsUser: 0)")
        elif eff("runAsNonRoot") is not True and not (isinstance(run_user, int) and run_user > 0):
            add("MEDIUM", "security", "No garantiza ejecución como no-root (runAsNonRoot/runAsUser)")
        if csc.get("readOnlyRootFilesystem") is not True:
            add("LOW", "security", "readOnlyRootFilesystem no está en true")
        caps = csc.get("capabilities") or {}
        drop = {str(x).upper() for x in caps.get("drop") or []}
        added = {str(x).upper() for x in caps.get("add") or []}
        if "ALL" not in drop:
            add("LOW", "security", "No hace drop de ALL capabilities")
        if added & DANGEROUS_CAPS:
            add("HIGH", "security", f"Agrega capabilities peligrosas: {sorted(added & DANGEROUS_CAPS)}")
        if not eff("seccompProfile"):
            add("LOW", "security", "Sin seccompProfile (recomendado: RuntimeDefault)")

        # Variables sensibles en texto plano
        for e in c.get("env") or []:
            if e.get("value") not in (None, "") and SECRET_ENV.search(str(e.get("name", ""))):
                add("HIGH", "secret-en-env", f"Variable '{e.get('name')}' con valor literal: usar secretKeyRef")

        # hostPort
        for p in c.get("ports") or []:
            if p.get("hostPort"):
                add("MEDIUM", "hostport", f"hostPort {p['hostPort']} (limita scheduling y expone el nodo)")

    # Request efectivo del pod = max(init más grande, suma de contenedores)
    rep.capacity.append(Capacity(
        resource=r, replicas=rtxt, replicas_base=base, replicas_max=rmax, per_node=per_node,
        cpu_req_m=max(sum_cpu_r, init_cpu_r), cpu_lim_m=max(sum_cpu_l, init_cpu_l),
        mem_req_b=max(sum_mem_r, init_mem_r), mem_lim_b=max(sum_mem_l, init_mem_l)))

    # Almacenamiento de StatefulSet
    if kind == "StatefulSet":
        for vct in spec.get("volumeClaimTemplates") or []:
            vspec = vct.get("spec") or {}
            size = parse_mem(((vspec.get("resources") or {}).get("requests") or {}).get("storage")) or 0
            sc = vspec.get("storageClassName")
            rep.storage.append(Storage(f"{r} [{(vct.get('metadata') or {}).get('name', '?')}]", size, rmax,
                                       sc if sc is not None else "(default)",
                                       ",".join(vspec.get("accessModes") or [])))


# --------------------------------------------------------------------------------------
# Herramientas externas
# --------------------------------------------------------------------------------------
def run_external(rep, chart, render_path, kube_version):
    tools = {}
    if shutil.which("kubeconform"):
        cmd = ["kubeconform", "-strict", "-summary", "-ignore-missing-schemas"]
        if kube_version:
            kv = kube_version.lstrip("v")
            kv = kv + ".0" if kv.count(".") == 1 else kv
            cmd += ["-kubernetes-version", kv]
        tools["kubeconform"] = cmd + [render_path]
    if shutil.which("kube-linter"):
        tools["kube-linter"] = ["kube-linter", "lint", render_path]
    if shutil.which("trivy"):
        target = chart if Path(chart).is_dir() else str(Path(render_path).parent)
        tools["trivy"] = ["trivy", "config", "--quiet", target]
    for name in ("kubeconform", "kube-linter", "trivy"):
        if name not in tools:
            rep.external[name] = {"rc": None, "output": "no instalado"}
            continue
        rc, out, err = run(tools[name], timeout=600)
        rep.external[name] = {"rc": rc, "output": (out + err).strip()[-6000:]}
        if rc not in (0, None):
            rep.add("MEDIUM", f"ext-{name}", "chart", f"{name} reportó problemas (rc={rc}); ver sección de herramientas")


# --------------------------------------------------------------------------------------
# Reportes
# --------------------------------------------------------------------------------------
def capacity_rows(rep):
    rows, tot = [], {"cpu_b": 0.0, "mem_b": 0.0, "cpu_m": 0.0, "mem_m": 0.0, "ds_cpu": 0.0, "ds_mem": 0.0}
    for c in rep.capacity:
        if c.per_node:
            tb = tm = "por nodo"
            tot["ds_cpu"] += c.cpu_req_m
            tot["ds_mem"] += c.mem_req_b
        else:
            tb = f"{fmt_cpu(c.cpu_req_m * c.replicas_base)} / {fmt_mem(c.mem_req_b * c.replicas_base)}"
            tm = f"{fmt_cpu(c.cpu_req_m * c.replicas_max)} / {fmt_mem(c.mem_req_b * c.replicas_max)}"
            tot["cpu_b"] += c.cpu_req_m * c.replicas_base
            tot["mem_b"] += c.mem_req_b * c.replicas_base
            tot["cpu_m"] += c.cpu_req_m * c.replicas_max
            tot["mem_m"] += c.mem_req_b * c.replicas_max
        rows.append([c.resource, c.replicas,
                     f"{fmt_cpu(c.cpu_req_m)} / {fmt_cpu(c.cpu_lim_m)}",
                     f"{fmt_mem(c.mem_req_b)} / {fmt_mem(c.mem_lim_b)}", tb, tm])
    return rows, tot


CAP_HEADERS = ["Recurso", "Réplicas", "CPU req/lim (pod)", "Mem req/lim (pod)",
               "Req total CPU/Mem", "Req total a máx. HPA"]
STO_HEADERS = ["Recurso", "Tamaño", "Copias", "Total", "StorageClass", "AccessModes"]


def storage_rows(rep):
    rows, total = [], 0.0
    for s in rep.storage:
        rows.append([s.resource, fmt_mem(s.size_b), str(s.copies), fmt_mem(s.size_b * s.copies),
                     s.storage_class, s.access_modes])
        total += s.size_b * s.copies
    return rows, total


def text_table(headers, rows):
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    out = [line, "  ".join("-" * w for w in widths)]
    out += ["  ".join(str(x).ljust(w) for x, w in zip(row, widths)) for row in rows]
    return "\n".join(out)


def sev_counts(rep):
    return {s: sum(1 for f in rep.findings if f.severity == s) for s in SEVERITIES}


def print_console(reports, min_sev, color):
    c = (lambda code, s: f"{code}{s}{RESET}") if color else (lambda code, s: s)
    for rep in reports:
        print()
        print(c(BOLD, "=" * 100))
        title = f"Chart: {rep.chart}"
        if rep.name:
            title += f"  |  {rep.name} {rep.version} (app {rep.app_version or '-'})"
        print(c(BOLD, title))
        print(c(BOLD, "=" * 100))
        counts = sev_counts(rep)
        print("Hallazgos: " + "  ".join(c(SEV_COLOR[s], f"{SEV_ES[s]}={counts[s]}") for s in SEVERITIES))
        if rep.resources_count:
            print("Recursos renderizados: " + ", ".join(f"{k}={v}" for k, v in rep.resources_count.items()))

        if rep.capacity:
            rows, tot = capacity_rows(rep)
            print("\n" + c(BOLD, "Capacidad configurada"))
            print(text_table(CAP_HEADERS, rows))
            print(f"TOTAL requests (base): CPU {fmt_cpu(tot['cpu_b'])}, Mem {fmt_mem(tot['mem_b'])}"
                  f"  |  a máx. HPA: CPU {fmt_cpu(tot['cpu_m'])}, Mem {fmt_mem(tot['mem_m'])}")
            if tot["ds_cpu"] or tot["ds_mem"]:
                print(f"DaemonSets (por cada nodo): CPU {fmt_cpu(tot['ds_cpu'])}, Mem {fmt_mem(tot['ds_mem'])}")
        if rep.storage:
            rows, total = storage_rows(rep)
            print("\n" + c(BOLD, "Almacenamiento"))
            print(text_table(STO_HEADERS, rows))
            print(f"TOTAL almacenamiento solicitado: {fmt_mem(total)}")

        shown = [f for f in rep.findings if SEV_RANK[f.severity] <= SEV_RANK[min_sev]]
        shown.sort(key=lambda f: (SEV_RANK[f.severity], f.resource, f.container))
        if shown:
            print("\n" + c(BOLD, f"Hallazgos (severidad >= {SEV_ES[min_sev]})"))
            for f in shown:
                where = f.resource + (f" [{f.container}]" if f.container else "")
                print(f"  {c(SEV_COLOR[f.severity], SEV_ES[f.severity].ljust(5))} {where}: {f.message}"
                      f"  ({f.check})")
        for name, res in rep.external.items():
            if res["rc"] is None:
                continue
            print("\n" + c(BOLD, f"{name} (rc={res['rc']})"))
            print(res["output"][-2000:] or "(sin salida)")


def md_escape(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def write_markdown(reports, path, min_sev, args):
    L = ["# Revisión de Helm charts", "",
         f"- Namespace de render: `{args.namespace}`",
         f"- Values: {', '.join(f'`{v}`' for v in args.values) or '(defaults del chart)'}",
         f"- Kubernetes objetivo: `{args.kube_version or 'default de helm'}`", "",
         "## Resumen", "", "| Chart | Versión | ALTA | MEDIA | BAJA | INFO |", "|---|---|---|---|---|---|"]
    for rep in reports:
        cnt = sev_counts(rep)
        L.append(f"| {md_escape(rep.name or rep.chart)} | {rep.version or '-'} | "
                 + " | ".join(str(cnt[s]) for s in SEVERITIES) + " |")
    for rep in reports:
        L += ["", f"## {md_escape(rep.name or rep.chart)}", "", f"Ruta: `{rep.chart}`  ",
              f"Versión: `{rep.version or '-'}`, appVersion: `{rep.app_version or '-'}`", ""]
        if rep.resources_count:
            L += ["Recursos: " + ", ".join(f"{k}={v}" for k, v in rep.resources_count.items()), ""]
        if rep.capacity:
            rows, tot = capacity_rows(rep)
            L += ["### Capacidad configurada", "", "| " + " | ".join(CAP_HEADERS) + " |",
                  "|" + "---|" * len(CAP_HEADERS)]
            L += ["| " + " | ".join(md_escape(x) for x in row) + " |" for row in rows]
            L += ["", f"**Total requests (base):** CPU {fmt_cpu(tot['cpu_b'])}, Mem {fmt_mem(tot['mem_b'])} — "
                      f"**a máx. HPA:** CPU {fmt_cpu(tot['cpu_m'])}, Mem {fmt_mem(tot['mem_m'])}"]
            if tot["ds_cpu"] or tot["ds_mem"]:
                L.append(f"\n**DaemonSets por nodo:** CPU {fmt_cpu(tot['ds_cpu'])}, Mem {fmt_mem(tot['ds_mem'])}")
            L.append("")
        if rep.storage:
            rows, total = storage_rows(rep)
            L += ["### Almacenamiento", "", "| " + " | ".join(STO_HEADERS) + " |", "|" + "---|" * len(STO_HEADERS)]
            L += ["| " + " | ".join(md_escape(x) for x in row) + " |" for row in rows]
            L += ["", f"**Total:** {fmt_mem(total)}", ""]
        shown = sorted([f for f in rep.findings if SEV_RANK[f.severity] <= SEV_RANK[min_sev]],
                       key=lambda f: (SEV_RANK[f.severity], f.resource, f.container))
        L += ["### Hallazgos", ""]
        if shown:
            L += ["| Severidad | Recurso | Contenedor | Check | Detalle | Template |", "|---|---|---|---|---|---|"]
            L += [f"| {SEV_ES[f.severity]} | {md_escape(f.resource)} | {md_escape(f.container)} | {f.check} | "
                  f"{md_escape(f.message)} | {md_escape(f.source)} |" for f in shown]
        else:
            L.append("Sin hallazgos en el nivel seleccionado.")
        for name, res in rep.external.items():
            if res["rc"] is None:
                continue
            L += ["", f"### {name} (rc={res['rc']})", "", "```", res["output"] or "(sin salida)", "```"]
    Path(path).write_text("\n".join(L) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def review_chart(args, chart):
    rep = ChartReport(chart=chart)
    try:
        meta = load_chart_yaml(chart, args.version)
    except yaml.YAMLError as e:
        meta = None
        rep.add("HIGH", "chart-yaml", "Chart.yaml", f"Chart.yaml inválido: {e}")
    if meta:
        check_chart_meta(rep, chart, meta)
    elif Path(chart).is_dir():
        rep.add("HIGH", "chart-yaml", "chart", "No se encontró Chart.yaml")

    if args.rendered:
        text = Path(args.rendered).read_text(encoding="utf-8")
    else:
        release = sanitize_release(args.release or (meta or {}).get("name") or Path(chart).name.split(".tgz")[0])
        if args.dep_update:
            helm_dep_build(rep, chart)
        if not args.skip_lint and Path(chart).is_dir():
            helm_lint(args, rep, chart)
        rc, out, err = helm_template(args, chart, release)
        if rc != 0:
            rep.error = err.strip()
            rep.add("HIGH", "helm-template", "chart", f"helm template falló: {err.strip()[:800]}")
            return rep
        text = out

    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", rep.name or Path(chart).name)
    if args.save_rendered:
        Path(args.save_rendered).mkdir(parents=True, exist_ok=True)
        Path(args.save_rendered, f"{safe}.rendered.yaml").write_text(text, encoding="utf-8")

    analyze(rep, parse_manifests(text), args.namespace)

    if args.external:
        with tempfile.TemporaryDirectory() as td:
            rp = Path(td, f"{safe}.yaml")
            rp.write_text(text, encoding="utf-8")
            run_external(rep, chart, str(rp), args.kube_version)
    return rep


def main():
    ap = argparse.ArgumentParser(description="Revisión local de Helm charts (lint, render y análisis de manifiestos).",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("charts", nargs="+", help="Directorio del chart, .tgz, repo/chart u oci://...")
    ap.add_argument("-f", "--values", action="append", default=[], help="Archivo de values (repetible, en orden)")
    ap.add_argument("--set", action="append", default=[], help="Valor --set de helm (repetible)")
    ap.add_argument("--release", help="Nombre del release (default: nombre del chart)")
    ap.add_argument("-n", "--namespace", default="default", help="Namespace para el render (default: default)")
    ap.add_argument("--version", help="Versión del chart (para charts remotos/OCI)")
    ap.add_argument("--kube-version", help="Versión de Kubernetes objetivo, ej. 1.30 (afecta .Capabilities)")
    ap.add_argument("--api-versions", action="append", default=[],
                    help="API disponible en el cluster para .Capabilities, ej. monitoring.coreos.com/v1 (repetible)")
    ap.add_argument("--rendered", help="Analizar un YAML ya renderizado en vez de ejecutar helm template (1 chart)")
    ap.add_argument("--dep-update", action="store_true", help="Ejecutar helm dependency build/update antes")
    ap.add_argument("--skip-lint", action="store_true", help="No ejecutar helm lint")
    ap.add_argument("--external", action="store_true", help="Ejecutar kubeconform/kube-linter/trivy si existen")
    ap.add_argument("--min-severity", default="low", choices=[s.lower() for s in SEVERITIES],
                    help="Severidad mínima a mostrar (default: low)")
    ap.add_argument("--report", help="Escribir reporte Markdown en esta ruta")
    ap.add_argument("--json", help="Escribir resultado completo en JSON")
    ap.add_argument("--save-rendered", help="Directorio donde guardar el YAML renderizado")
    ap.add_argument("--fail-on", default="none", choices=["high", "medium", "low", "none"],
                    help="Exit code 2 si hay hallazgos de esta severidad o mayor (para CI)")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    if args.rendered and len(args.charts) != 1:
        ap.error("--rendered solo admite un chart")
    if not args.rendered and not shutil.which("helm"):
        sys.exit("No se encontró 'helm' en el PATH. Instálalo o usa --rendered con un YAML ya renderizado.")
    for v in args.values:
        if not Path(v).exists():
            sys.exit(f"No existe el archivo de values: {v}")

    min_sev = args.min_severity.upper()
    reports = [review_chart(args, ch) for ch in args.charts]

    print_console(reports, min_sev, color=sys.stdout.isatty() and not args.no_color)
    if args.report:
        write_markdown(reports, args.report, min_sev, args)
        print(f"\nReporte Markdown: {args.report}")
    if args.json:
        Path(args.json).write_text(json.dumps([asdict(r) for r in reports], indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        print(f"Reporte JSON: {args.json}")

    if any(r.error for r in reports):
        return 1
    if args.fail_on != "none":
        limit = SEV_RANK[args.fail_on.upper()]
        if any(SEV_RANK[f.severity] <= limit for r in reports for f in r.findings):
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
