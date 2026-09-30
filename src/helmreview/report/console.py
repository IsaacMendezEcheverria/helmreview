"""Salida por consola."""

from __future__ import annotations

from helmreview.models import SEV_ES, SEVERITIES, ChartReport
from helmreview.quantities import fmt_mem
from helmreview.report.tables import CAP_HEADERS, STO_HEADERS, capacity_rows, daemonset_line, storage_rows, totals_line

SEV_COLOR = {"HIGH": "\033[31m", "MEDIUM": "\033[33m", "LOW": "\033[36m", "INFO": "\033[90m"}
RESET, BOLD = "\033[0m", "\033[1m"


def text_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    out = ["  ".join(h.ljust(w) for h, w in zip(headers, widths)), "  ".join("-" * w for w in widths)]
    out += ["  ".join(str(x).ljust(w) for x, w in zip(row, widths)) for row in rows]
    return "\n".join(out)


def print_console(reports: list[ChartReport], min_sev: str, color: bool) -> None:
    def c(code: str, s: str) -> str:
        return f"{code}{s}{RESET}" if color else s

    for rep in reports:
        print()
        print(c(BOLD, "=" * 100))
        title = f"Chart: {rep.chart}"
        if rep.name:
            title += f"  |  {rep.name} {rep.version} (app {rep.app_version or '-'})"
        print(c(BOLD, title))
        print(c(BOLD, "=" * 100))
        counts = rep.counts()
        print("Hallazgos: " + "  ".join(c(SEV_COLOR[s], f"{SEV_ES[s]}={counts[s]}") for s in SEVERITIES))
        if rep.resources_count:
            print("Recursos renderizados: " + ", ".join(f"{k}={v}" for k, v in rep.resources_count.items()))

        if rep.capacity:
            rows, tot = capacity_rows(rep)
            print("\n" + c(BOLD, "Capacidad configurada"))
            print(text_table(CAP_HEADERS, rows))
            print(totals_line(tot))
            if ds := daemonset_line(tot):
                print(ds)
        if rep.storage:
            rows, total = storage_rows(rep)
            print("\n" + c(BOLD, "Almacenamiento"))
            print(text_table(STO_HEADERS, rows))
            print(f"TOTAL almacenamiento solicitado: {fmt_mem(total)}")

        shown = rep.filtered(min_sev)
        if shown:
            print("\n" + c(BOLD, f"Hallazgos (severidad >= {SEV_ES[min_sev]})"))
            for f in shown:
                where = f.resource + (f" [{f.container}]" if f.container else "")
                print(f"  {c(SEV_COLOR[f.severity], SEV_ES[f.severity].ljust(5))} {where}: {f.message}  ({f.check})")
        for name, res in rep.external.items():
            if res["rc"] is None:
                continue
            print("\n" + c(BOLD, f"{name} (rc={res['rc']})"))
            print(res["output"][-2000:] or "(sin salida)")
