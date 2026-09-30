"""Modelos de datos del reporte y definición de severidades."""

from __future__ import annotations

from dataclasses import dataclass, field

SEVERITIES = ["HIGH", "MEDIUM", "LOW", "INFO"]
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}  # menor número = más grave
SEV_ES = {"HIGH": "ALTA", "MEDIUM": "MEDIA", "LOW": "BAJA", "INFO": "INFO"}


@dataclass
class Finding:
    """Un hallazgo de la revisión."""

    severity: str  # HIGH | MEDIUM | LOW | INFO
    check: str  # ID estable del check (ver docs/checks.md)
    resource: str  # Kind/nombre, "chart" o "Chart.yaml"
    message: str
    container: str = ""
    source: str = ""  # template de origen (comentario "# Source:" de helm)


@dataclass
class Capacity:
    """Capacidad configurada de un workload (por pod y réplicas)."""

    resource: str
    replicas: str  # texto para mostrar, ej. "3 (HPA 3-10)"
    replicas_base: int
    replicas_max: int
    per_node: bool  # DaemonSet
    cpu_req_m: float  # milicores por pod
    cpu_lim_m: float
    mem_req_b: float  # bytes por pod
    mem_lim_b: float


@dataclass
class Storage:
    """Almacenamiento solicitado (PVC o volumeClaimTemplate)."""

    resource: str
    size_b: float
    copies: int
    storage_class: str
    access_modes: str


@dataclass
class ChartReport:
    """Resultado de revisar un chart."""

    chart: str
    name: str = ""
    version: str = ""
    app_version: str = ""
    findings: list[Finding] = field(default_factory=list)
    capacity: list[Capacity] = field(default_factory=list)
    storage: list[Storage] = field(default_factory=list)
    resources_count: dict[str, int] = field(default_factory=dict)
    external: dict[str, dict] = field(default_factory=dict)
    error: str = ""
    ignored: set[str] = field(default_factory=set, repr=False)

    def add(self, sev: str, check: str, resource: str, message: str, container: str = "", source: str = "") -> None:
        if check in self.ignored:
            return
        self.findings.append(Finding(sev, check, resource, message, container, source))

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for f in self.findings if f.severity == s) for s in SEVERITIES}

    def filtered(self, min_sev: str) -> list[Finding]:
        """Hallazgos con severidad >= min_sev, ordenados por gravedad y recurso."""
        shown = [f for f in self.findings if SEV_RANK[f.severity] <= SEV_RANK[min_sev]]
        return sorted(shown, key=lambda f: (SEV_RANK[f.severity], f.resource, f.container))

    def to_dict(self) -> dict:
        from dataclasses import asdict

        d = asdict(self)
        d.pop("ignored", None)
        return d
