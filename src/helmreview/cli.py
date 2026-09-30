"""Interfaz de línea de comandos de helmreview."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from helmreview import __version__
from helmreview.constants import OCP_KUBE_MAP
from helmreview.models import SEV_RANK, SEVERITIES
from helmreview.options import ReviewOptions
from helmreview.report import print_console, write_json, write_markdown
from helmreview.review import review_chart

EPILOG = """\
Ejemplos:
  helmreview ./mychart -f values-prod.yaml
  helmreview ./mychart -f values.yaml -f values-prod.yaml --kube-version 1.30 --report rev.md
  helmreview ./charts/* --min-severity medium --json rev.json --fail-on high
  helmreview oci://harbor.local/charts/app --version 1.4.2 -f prod.yaml
  helmreview ./mychart -f values-ocp.yaml --ocp-version 4.16 --report rev.md
  helmreview ./mychart --rendered render.yaml
  helmreview ./mychart --ignore serviceaccount,chart-schema

Códigos de salida: 0 = OK, 1 = error de ejecución, 2 = hallazgos >= --fail-on
Catálogo de checks: docs/checks.md
"""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="helmreview",
        description="Revisión estática local de Helm charts (lint, render y análisis de manifiestos).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("charts", nargs="+", help="Directorio del chart, .tgz, repo/chart u oci://...")
    ap.add_argument("-f", "--values", action="append", default=[], help="Archivo de values (repetible, en orden)")
    ap.add_argument("--set", dest="set_values", action="append", default=[], help="Valor --set de helm (repetible)")
    ap.add_argument("--release", help="Nombre del release (default: nombre del chart)")
    ap.add_argument("-n", "--namespace", default="default", help="Namespace para el render (default: default)")
    ap.add_argument("--chart-version", dest="chart_version", help="Versión del chart (para charts remotos/OCI)")
    ap.add_argument("--kube-version", help="Versión de Kubernetes objetivo, ej. 1.30 (afecta .Capabilities)")
    ap.add_argument(
        "--platform",
        default="kubernetes",
        choices=["kubernetes", "openshift"],
        help="Plataforma destino: 'openshift' activa checks de SCC restricted-v2, Routes, etc.",
    )
    ap.add_argument(
        "--ocp-version",
        help="Versión de OpenShift (implica --platform openshift y fija --kube-version). "
        f"Conocidas: {', '.join(OCP_KUBE_MAP)}",
    )
    ap.add_argument(
        "--api-versions",
        action="append",
        default=[],
        help="API disponible en el cluster para .Capabilities, ej. monitoring.coreos.com/v1 (repetible)",
    )
    ap.add_argument("--rendered", help="Analizar un YAML ya renderizado en vez de ejecutar helm template (1 chart)")
    ap.add_argument("--dep-update", action="store_true", help="Ejecutar helm dependency build/update antes")
    ap.add_argument("--skip-lint", action="store_true", help="No ejecutar helm lint")
    ap.add_argument("--external", action="store_true", help="Ejecutar kubeconform/kube-linter/trivy si existen")
    ap.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="IDs de checks a omitir, separados por coma (repetible). Ver docs/checks.md",
    )
    ap.add_argument(
        "--min-severity",
        default="low",
        choices=[s.lower() for s in SEVERITIES],
        help="Severidad mínima a mostrar (default: low)",
    )
    ap.add_argument("--report", help="Escribir reporte Markdown en esta ruta")
    ap.add_argument("--json", help="Escribir resultado completo en JSON")
    ap.add_argument("--save-rendered", help="Directorio donde guardar el YAML renderizado")
    ap.add_argument(
        "--fail-on",
        default="none",
        choices=["high", "medium", "low", "none"],
        help="Exit code 2 si hay hallazgos de esta severidad o mayor (para CI)",
    )
    ap.add_argument("--no-color", action="store_true")
    return ap


def options_from_args(args: argparse.Namespace, ap: argparse.ArgumentParser) -> ReviewOptions:
    platform, kube_version = args.platform, args.kube_version
    if args.ocp_version:
        platform = "openshift"
        ocpv = ".".join(args.ocp_version.lstrip("v").split(".")[:2])
        if not kube_version:
            if ocpv not in OCP_KUBE_MAP:
                ap.error(f"Versión OCP '{args.ocp_version}' no mapeada; indica --kube-version manualmente")
            kube_version = OCP_KUBE_MAP[ocpv]
    ignore = {i.strip() for group in args.ignore for i in group.split(",") if i.strip()}
    return ReviewOptions(
        values=args.values,
        set_values=args.set_values,
        release=args.release,
        namespace=args.namespace,
        version=args.chart_version,
        kube_version=kube_version,
        api_versions=args.api_versions,
        platform=platform,
        ocp_version=args.ocp_version,
        rendered=args.rendered,
        dep_update=args.dep_update,
        skip_lint=args.skip_lint,
        external=args.external,
        save_rendered=args.save_rendered,
        ignore=ignore,
    )


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)

    if args.rendered and len(args.charts) != 1:
        ap.error("--rendered solo admite un chart")
    if not args.rendered and not shutil.which("helm"):
        print(
            "No se encontró 'helm' en el PATH. Instálalo o usa --rendered con un YAML ya renderizado.", file=sys.stderr
        )
        return 1
    for v in args.values:
        if not Path(v).exists():
            print(f"No existe el archivo de values: {v}", file=sys.stderr)
            return 1

    opts = options_from_args(args, ap)
    min_sev = args.min_severity.upper()
    reports = [review_chart(ch, opts) for ch in args.charts]

    print_console(reports, min_sev, color=sys.stdout.isatty() and not args.no_color)
    if args.report:
        write_markdown(reports, args.report, min_sev, opts)
        print(f"\nReporte Markdown: {args.report}")
    if args.json:
        write_json(reports, args.json)
        print(f"Reporte JSON: {args.json}")

    if any(r.error for r in reports):
        return 1
    if args.fail_on != "none":
        limit = SEV_RANK[args.fail_on.upper()]
        if any(SEV_RANK[f.severity] <= limit for r in reports for f in r.findings):
            return 2
    return 0
