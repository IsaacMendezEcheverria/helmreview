"""Checks sobre workloads: réplicas/HA, recursos, probes, seguridad y compatibilidad con SCC."""

from __future__ import annotations

from typing import TYPE_CHECKING

from helmreview.constants import DANGEROUS_CAPS, OCP_ALLOWED_CAPS, SCALABLE, SECRET_ENV, WORKLOADS
from helmreview.k8s import image_ref, pod_template, rid, selector_matches, to_int
from helmreview.models import Capacity, ChartReport, Storage
from helmreview.quantities import fmt_cpu, fmt_mem, parse_cpu, parse_mem

if TYPE_CHECKING:
    from helmreview.checks.manifests import Context

assert set(SCALABLE) <= WORKLOADS


def _replicas(kind: str, spec: dict, hpa) -> tuple[int, int, str]:
    """Devuelve (réplicas base, réplicas máximas, texto)."""
    if kind in SCALABLE:
        base = to_int(spec.get("replicas"), hpa[0] if hpa else 1)
        rmax = hpa[1] if hpa and hpa[1] else base
        return base, rmax, str(base) + (f" (HPA {hpa[0]}-{hpa[1]})" if hpa else "")
    if kind == "Job":
        n = to_int(spec.get("parallelism"), 1)
        return n, n, f"{n} (Job)"
    if kind == "CronJob":
        n = to_int(((spec.get("jobTemplate") or {}).get("spec") or {}).get("parallelism"), 1)
        return n, n, f"{n} por ejecución"
    if kind == "DaemonSet":
        return 1, 1, "1 por nodo"
    return 1, 1, "1"


def _check_ha(rep, obj, src, ctx, pspec, labels, hpa, base) -> None:
    kind, r, spec = obj["kind"], rid(obj), obj.get("spec") or {}
    if kind not in ("Deployment", "DeploymentConfig", "StatefulSet"):
        return
    if not hpa and base < 2:
        rep.add("MEDIUM", "replicas", r, f"{base} réplica(s) sin HPA: sin alta disponibilidad", source=src)
    if hpa and spec.get("replicas") is not None:
        rep.add(
            "LOW",
            "replicas-hpa",
            r,
            "Define spec.replicas y además tiene HPA: cada helm upgrade reinicia el número de réplicas",
            source=src,
        )
    multi = base > 1 or bool(hpa)
    if multi:
        anti = (pspec.get("affinity") or {}).get("podAntiAffinity")
        if not anti and not pspec.get("topologySpreadConstraints"):
            rep.add(
                "LOW",
                "distribucion",
                r,
                "Varias réplicas sin podAntiAffinity ni topologySpreadConstraints: pueden caer en el mismo nodo",
                source=src,
            )
    matching = [p for p in ctx.pdbs if selector_matches((p.get("spec") or {}).get("selector"), labels)]
    if multi and not matching:
        rep.add("LOW", "pdb", r, "Sin PodDisruptionBudget: un drain puede bajar todas las réplicas", source=src)
    eff_min = hpa[0] if hpa else base
    for p in matching:
        ps = p.get("spec") or {}
        min_av, max_un = ps.get("minAvailable"), ps.get("maxUnavailable")
        if (isinstance(min_av, int) and min_av >= eff_min) or min_av == "100%" or max_un in (0, "0%"):
            rep.add(
                "MEDIUM",
                "pdb-bloqueo",
                r,
                f"{rid(p)} (minAvailable={min_av}, maxUnavailable={max_un}) con {eff_min} réplica(s) mínima(s): "
                "bloquea drains/upgrades de nodos",
                source=src,
            )


def _check_pod(rep, obj, src, ctx, pmeta, pspec, labels, scc_needed: set) -> None:
    r, per_node = rid(obj), obj["kind"] == "DaemonSet"
    for fld in ("hostNetwork", "hostPID", "hostIPC"):
        if pspec.get(fld):
            rep.add("HIGH", "host-namespaces", r, f"{fld}: true", source=src)
    for vol in pspec.get("volumes") or []:
        if "hostPath" in vol:
            path = (vol.get("hostPath") or {}).get("path")
            rep.add(
                "MEDIUM" if per_node else "HIGH",
                "hostpath",
                r,
                f"Volumen hostPath '{path}' (acceso al filesystem del nodo)",
                source=src,
            )
    sa = pspec.get("serviceAccountName") or pspec.get("serviceAccount")
    if not sa or sa == "default":
        rep.add("LOW", "serviceaccount", r, "Usa el ServiceAccount 'default' del namespace", source=src)
    if ctx.netpols and not any(selector_matches((n.get("spec") or {}).get("podSelector"), labels) for n in ctx.netpols):
        rep.add("LOW", "networkpolicy", r, "Ninguna NetworkPolicy del chart selecciona estos pods", source=src)

    uses_cfg = any("configMap" in v or "secret" in v for v in pspec.get("volumes") or [])
    for c in pspec.get("containers") or []:
        uses_cfg = uses_cfg or any("configMapRef" in e or "secretRef" in e for e in c.get("envFrom") or [])
    if uses_cfg and not any(k.startswith("checksum/") for k in (pmeta.get("annotations") or {})):
        rep.add(
            "INFO",
            "checksum-config",
            r,
            "Monta ConfigMap/Secret sin anotación checksum/*: cambios de config no reinician los pods",
            source=src,
        )

    if ctx.openshift:
        _check_pod_openshift(rep, r, src, pspec, scc_needed)


def _check_pod_openshift(rep, r, src, pspec, scc_needed: set) -> None:
    """Compatibilidad del pod con la SCC restricted-v2."""
    psc = pspec.get("securityContext") or {}
    if pspec.get("hostNetwork"):
        scc_needed.add("hostnetwork-v2")
    if pspec.get("hostPID") or pspec.get("hostIPC"):
        scc_needed.add("privileged")
    if any("hostPath" in v for v in pspec.get("volumes") or []):
        scc_needed.add("hostmount-anyuid")
    ru = psc.get("runAsUser")
    if isinstance(ru, int) and ru > 0:
        scc_needed.add("nonroot-v2")
        rep.add(
            "HIGH",
            "ocp-uid",
            r,
            f"securityContext.runAsUser: {ru} fijo a nivel de pod. restricted-v2 asigna un UID aleatorio del rango "
            "del namespace y rechaza UIDs fuera de él. Quitar runAsUser (y no asumir un UID en la imagen)",
            source=src,
        )
    for key in ("runAsGroup", "fsGroup"):
        if isinstance(psc.get(key), int):
            rep.add(
                "MEDIUM",
                "ocp-uid",
                r,
                f"securityContext.{key}: {psc[key]} fijo: fuera del rango del namespace es rechazado por "
                "restricted-v2. Omitirlo y dejar que OpenShift lo asigne",
                source=src,
            )
    if psc.get("supplementalGroups"):
        rep.add(
            "MEDIUM",
            "ocp-uid",
            r,
            f"supplementalGroups fijos {psc['supplementalGroups']}: deben estar en el rango del namespace",
            source=src,
        )
    if psc.get("seLinuxOptions"):
        rep.add("MEDIUM", "ocp-selinux", r, "seLinuxOptions personalizado: restricted-v2 usa MustRunAs", source=src)


def _check_container(rep, r, src, c, is_init, is_batch, psc, openshift, scc_needed: set):
    """Checks de un contenedor. Devuelve (cpu_req, cpu_lim, mem_req, mem_lim) efectivos."""
    cn = c.get("name", "?") + (" (init)" if is_init else "")

    def add(sev, check, msg):
        rep.add(sev, check, r, msg, container=cn, source=src)

    # ---- Imagen ----
    image = str(c.get("image", ""))
    itype, ival = image_ref(image)
    if itype == "none":
        add("HIGH", "image-tag", f"Imagen '{image}' sin tag (usa 'latest' implícito)")
    elif itype == "tag" and ival == "latest":
        add("HIGH", "image-tag", f"Imagen '{image}' con tag 'latest'")

    # ---- Recursos ----
    res = c.get("resources") or {}
    req, lim = res.get("requests") or {}, res.get("limits") or {}
    cpu_r, mem_r = parse_cpu(req.get("cpu")), parse_mem(req.get("memory"))
    cpu_l, mem_l = parse_cpu(lim.get("cpu")), parse_mem(lim.get("memory"))
    for label, raw, parsed in (
        ("requests.cpu", req.get("cpu"), cpu_r),
        ("requests.memory", req.get("memory"), mem_r),
        ("limits.cpu", lim.get("cpu"), cpu_l),
        ("limits.memory", lim.get("memory"), mem_l),
    ):
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
        add(
            "HIGH", "resources", f"requests.cpu ({fmt_cpu(cpu_r)}) > limits.cpu ({fmt_cpu(cpu_l)}): manifiesto inválido"
        )
    if mem_r and mem_l and mem_r > mem_l:
        add(
            "HIGH",
            "resources",
            f"requests.memory ({fmt_mem(mem_r)}) > limits.memory ({fmt_mem(mem_l)}): manifiesto inválido",
        )
    if mem_r and mem_l and mem_l / mem_r > 4:
        add("LOW", "resources", f"limits.memory es {mem_l / mem_r:.1f}x el request: sobre-compromiso alto de memoria")

    # ---- Probes ----
    if not is_init and not is_batch:
        rp, lp = c.get("readinessProbe"), c.get("livenessProbe")
        if not rp:
            add("MEDIUM", "probes", "Sin readinessProbe: recibe tráfico antes de estar listo")
        if not lp:
            add("LOW", "probes", "Sin livenessProbe: no se reinicia si se cuelga")
        if rp and lp and rp == lp:
            add("LOW", "probes", "livenessProbe idéntica a readinessProbe: riesgo de reinicios en cascada")

    # ---- securityContext ----
    csc = c.get("securityContext") or {}

    def eff(key):
        return csc.get(key, psc.get(key))

    if csc.get("privileged"):
        add("HIGH", "security", "Contenedor privileged: true")
        scc_needed.add("privileged")
    if csc.get("allowPrivilegeEscalation") is not False:
        if openshift:
            add(
                "LOW",
                "security",
                "allowPrivilegeEscalation no explícito en false (la SCC lo fuerza, pero la Pod "
                "Security Admission 'restricted' generará warnings)",
            )
        else:
            add("MEDIUM", "security", "allowPrivilegeEscalation no está en false")
    run_user, c_ru = eff("runAsUser"), csc.get("runAsUser")
    if run_user == 0:
        add("HIGH", "security", "Corre como root (runAsUser: 0)")
        scc_needed.add("anyuid")
    elif openshift:
        # En OpenShift NO se debe fijar el UID: restricted-v2 garantiza no-root por sí misma.
        if isinstance(c_ru, int) and c_ru > 0:
            scc_needed.add("nonroot-v2")
            add(
                "HIGH",
                "ocp-uid",
                f"runAsUser: {c_ru} fijo en el contenedor: rechazado por restricted-v2 "
                "(UID aleatorio del namespace). Quitarlo",
            )
        if isinstance(csc.get("runAsGroup"), int):
            add("MEDIUM", "ocp-uid", f"runAsGroup: {csc['runAsGroup']} fijo en el contenedor")
    elif eff("runAsNonRoot") is not True and not (isinstance(run_user, int) and run_user > 0):
        add("MEDIUM", "security", "No garantiza ejecución como no-root (runAsNonRoot/runAsUser)")
    if csc.get("readOnlyRootFilesystem") is not True:
        add("LOW", "security", "readOnlyRootFilesystem no está en true")
    caps = csc.get("capabilities") or {}
    drop = {str(x).upper() for x in caps.get("drop") or []}
    added = {str(x).upper().removeprefix("CAP_") for x in caps.get("add") or []}
    if "ALL" not in drop:
        add("LOW", "security", "No hace drop de ALL capabilities")
    if openshift and added - OCP_ALLOWED_CAPS:
        add(
            "HIGH",
            "ocp-caps",
            f"Agrega capabilities {sorted(added - OCP_ALLOWED_CAPS)}: restricted-v2 solo permite "
            "NET_BIND_SERVICE; el pod será rechazado sin una SCC adicional",
        )
        scc_needed.add("SCC personalizada (capabilities)")
    elif added & DANGEROUS_CAPS:
        add("HIGH", "security", f"Agrega capabilities peligrosas: {sorted(added & DANGEROUS_CAPS)}")
    if not eff("seccompProfile"):
        add("LOW", "security", "Sin seccompProfile (recomendado: RuntimeDefault)")

    # ---- Variables sensibles en texto plano ----
    for e in c.get("env") or []:
        if e.get("value") not in (None, "") and SECRET_ENV.search(str(e.get("name", ""))):
            add("HIGH", "secret-en-env", f"Variable '{e.get('name')}' con valor literal: usar secretKeyRef")

    # ---- Puertos ----
    for p in c.get("ports") or []:
        if p.get("hostPort"):
            add("MEDIUM", "hostport", f"hostPort {p['hostPort']} (limita scheduling y expone el nodo)")
            if openshift:
                scc_needed.add("hostnetwork-v2")
        cport = p.get("containerPort")
        if (
            openshift
            and isinstance(cport, int)
            and cport < 1024
            and "NET_BIND_SERVICE" not in added
            and not csc.get("privileged")
        ):
            add(
                "MEDIUM",
                "ocp-puerto",
                f"containerPort {cport} < 1024: con UID no-root no podrá hacer bind. "
                "Usar puerto >= 1024 (ej. 8080) o agregar NET_BIND_SERVICE",
            )

    eff_cpu_r = cpu_r if cpu_r is not None else (cpu_l or 0)  # sin request => request = limit
    eff_mem_r = mem_r if mem_r is not None else (mem_l or 0)
    return eff_cpu_r, cpu_l or 0, eff_mem_r, mem_l or 0


def analyze_workload(rep: ChartReport, obj: dict, src: str, ctx: Context) -> None:
    kind, r = obj["kind"], rid(obj)
    spec = obj.get("spec") or {}
    name = (obj.get("metadata") or {}).get("name")
    pmeta, pspec = pod_template(obj)
    labels = pmeta.get("labels") or {}
    hpa = ctx.hpas.get((kind, name))
    psc = pspec.get("securityContext") or {}
    scc_needed: set[str] = set()  # SCC distintas de restricted-v2 que el pod necesitaría (OpenShift)

    base, rmax, rtxt = _replicas(kind, spec, hpa)
    _check_ha(rep, obj, src, ctx, pspec, labels, hpa, base)
    _check_pod(rep, obj, src, ctx, pmeta, pspec, labels, scc_needed)

    # Request efectivo del pod = max(init más grande, suma de contenedores)
    main = [0.0, 0.0, 0.0, 0.0]
    init = [0.0, 0.0, 0.0, 0.0]
    containers = [(c, False) for c in pspec.get("containers") or []]
    containers += [(c, True) for c in pspec.get("initContainers") or []]
    for c, is_init in containers:
        vals = _check_container(rep, r, src, c, is_init, kind in ("Job", "CronJob"), psc, ctx.openshift, scc_needed)
        if is_init:
            init = [max(a, b) for a, b in zip(init, vals)]
        else:
            main = [a + b for a, b in zip(main, vals)]
    cpu_r, cpu_l, mem_r, mem_l = (max(a, b) for a, b in zip(main, init))

    if ctx.openshift and scc_needed:
        rep.add(
            "HIGH",
            "ocp-scc",
            r,
            f"No es compatible con la SCC restricted-v2; requeriría: {', '.join(sorted(scc_needed))}. Verificar "
            "que el ServiceAccount tenga esa SCC aprobada (oc adm policy add-scc-to-user) o ajustar el chart",
            source=src,
        )

    rep.capacity.append(
        Capacity(
            resource=r,
            replicas=rtxt,
            replicas_base=base,
            replicas_max=rmax,
            per_node=kind == "DaemonSet",
            cpu_req_m=cpu_r,
            cpu_lim_m=cpu_l,
            mem_req_b=mem_r,
            mem_lim_b=mem_l,
        )
    )

    if kind == "StatefulSet":
        for vct in spec.get("volumeClaimTemplates") or []:
            vspec = vct.get("spec") or {}
            size = parse_mem(((vspec.get("resources") or {}).get("requests") or {}).get("storage")) or 0
            sc = vspec.get("storageClassName")
            rep.storage.append(
                Storage(
                    f"{r} [{(vct.get('metadata') or {}).get('name', '?')}]",
                    size,
                    rmax,
                    sc if sc is not None else "(default)",
                    ",".join(vspec.get("accessModes") or []),
                )
            )
