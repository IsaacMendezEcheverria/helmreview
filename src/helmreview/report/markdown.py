"""Reporte Markdown (para adjuntar a tickets, MRs o wikis)."""

from __future__ import annotations

from pathlib import Path

from helmreview import __version__
from helmreview.models import SEV_ES, SEVERITIES, ChartReport
from helmreview.options import ReviewOptions
from helmreview.quantities import fmt_mem
from helmreview.report.tables import CAP_HEADERS, STO_HEADERS, capacity_rows, daemonset_line, storage_rows, totals_line


def md_escape(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(md_escape(x) for x in row) + " |" for row in rows]
    return out


def render_markdown(reports: list[ChartReport], min_sev: str, opts: ReviewOptions) -> str:
    plat = f"`{opts.platform}`" + (f" (OCP {opts.ocp_version})" if opts.ocp_version else "")
    L = [
        "# Revisión de Helm charts",
        "",
        f"- Generado por: helmreview {__version__}",
        f"- Plataforma: {plat}",
        f"- Namespace de render: `{opts.namespace}`",
        f"- Values: {', '.join(f'`{v}`' for v in opts.values) or '(defaults del chart)'}",
        f"- Kubernetes objetivo: `{opts.kube_version or 'default de helm'}`",
        f"- Checks ignorados: {', '.join(sorted(opts.ignore)) or 'ninguno'}",
        "",
        "## Resumen",
        "",
    ]
    L += _table(
        ["Chart", "Versión"] + [SEV_ES[s] for s in SEVERITIES],
        [[r.name or r.chart, r.version or "-"] + [str(r.counts()[s]) for s in SEVERITIES] for r in reports],
    )

    for rep in reports:
        L += [
            "",
            f"## {md_escape(rep.name or rep.chart)}",
            "",
            f"Ruta: `{rep.chart}`  ",
            f"Versión: `{rep.version or '-'}`, appVersion: `{rep.app_version or '-'}`",
            "",
        ]
        if rep.resources_count:
            L += ["Recursos: " + ", ".join(f"{k}={v}" for k, v in rep.resources_count.items()), ""]
        if rep.capacity:
            rows, tot = capacity_rows(rep)
            L += ["### Capacidad configurada", ""] + _table(CAP_HEADERS, rows) + ["", f"**{totals_line(tot)}**"]
            if ds := daemonset_line(tot):
                L += ["", f"**{ds}**"]
            L.append("")
        if rep.storage:
            rows, total = storage_rows(rep)
            L += ["### Almacenamiento", ""] + _table(STO_HEADERS, rows) + ["", f"**Total:** {fmt_mem(total)}", ""]
        L += ["### Hallazgos", ""]
        shown = rep.filtered(min_sev)
        if shown:
            L += _table(
                ["Severidad", "Recurso", "Contenedor", "Check", "Detalle", "Template"],
                [[SEV_ES[f.severity], f.resource, f.container, f.check, f.message, f.source] for f in shown],
            )
        else:
            L.append("Sin hallazgos en el nivel seleccionado.")
        for name, res in rep.external.items():
            if res["rc"] is None:
                continue
            L += ["", f"### {name} (rc={res['rc']})", "", "```", res["output"] or "(sin salida)", "```"]
    return "\n".join(L) + "\n"


def write_markdown(reports: list[ChartReport], path: str, min_sev: str, opts: ReviewOptions) -> None:
    Path(path).write_text(render_markdown(reports, min_sev, opts), encoding="utf-8")
