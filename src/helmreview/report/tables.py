"""Tablas de capacidad y almacenamiento, compartidas por todos los formatos."""

from __future__ import annotations

from helmreview.models import ChartReport
from helmreview.quantities import fmt_cpu, fmt_mem

CAP_HEADERS = [
    "Recurso",
    "Réplicas",
    "CPU req/lim (pod)",
    "Mem req/lim (pod)",
    "Req total CPU/Mem",
    "Req total a máx. HPA",
]
STO_HEADERS = ["Recurso", "Tamaño", "Copias", "Total", "StorageClass", "AccessModes"]


def capacity_rows(rep: ChartReport) -> tuple[list[list[str]], dict[str, float]]:
    rows = []
    tot = {"cpu_b": 0.0, "mem_b": 0.0, "cpu_m": 0.0, "mem_m": 0.0, "ds_cpu": 0.0, "ds_mem": 0.0}
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
        rows.append(
            [
                c.resource,
                c.replicas,
                f"{fmt_cpu(c.cpu_req_m)} / {fmt_cpu(c.cpu_lim_m)}",
                f"{fmt_mem(c.mem_req_b)} / {fmt_mem(c.mem_lim_b)}",
                tb,
                tm,
            ]
        )
    return rows, tot


def storage_rows(rep: ChartReport) -> tuple[list[list[str]], float]:
    rows, total = [], 0.0
    for s in rep.storage:
        rows.append(
            [
                s.resource,
                fmt_mem(s.size_b),
                str(s.copies),
                fmt_mem(s.size_b * s.copies),
                s.storage_class,
                s.access_modes,
            ]
        )
        total += s.size_b * s.copies
    return rows, total


def totals_line(tot: dict[str, float]) -> str:
    return (
        f"TOTAL requests (base): CPU {fmt_cpu(tot['cpu_b'])}, Mem {fmt_mem(tot['mem_b'])}"
        f"  |  a máx. HPA: CPU {fmt_cpu(tot['cpu_m'])}, Mem {fmt_mem(tot['mem_m'])}"
    )


def daemonset_line(tot: dict[str, float]) -> str | None:
    if tot["ds_cpu"] or tot["ds_mem"]:
        return f"DaemonSets (por cada nodo): CPU {fmt_cpu(tot['ds_cpu'])}, Mem {fmt_mem(tot['ds_mem'])}"
    return None
