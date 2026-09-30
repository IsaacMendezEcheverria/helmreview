"""Punto de entrada de alto nivel: revisar un chart con unas opciones dadas.

Uso como librería:

    from helmreview.review import review_chart
    from helmreview.options import ReviewOptions

    rep = review_chart("./mychart", ReviewOptions(values=["prod.yaml"], platform="openshift"))
    for f in rep.findings:
        print(f.severity, f.check, f.message)
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import yaml

from helmreview import helm
from helmreview.checks import analyze, check_chart_meta
from helmreview.external import run_external
from helmreview.models import ChartReport
from helmreview.options import ReviewOptions


def review_chart(chart: str, opts: ReviewOptions) -> ChartReport:
    rep = ChartReport(chart=chart, ignored=set(opts.ignore))

    try:
        meta = helm.load_chart_yaml(chart, opts.version)
    except yaml.YAMLError as e:
        meta = None
        rep.add("HIGH", "chart-yaml", "Chart.yaml", f"Chart.yaml inválido: {e}")
    if meta:
        check_chart_meta(rep, chart, meta)
    elif Path(chart).is_dir():
        rep.add("HIGH", "chart-yaml", "chart", "No se encontró Chart.yaml")

    if opts.rendered:
        text = Path(opts.rendered).read_text(encoding="utf-8")
    else:
        release = helm.sanitize_release(opts.release or (meta or {}).get("name") or Path(chart).name.split(".tgz")[0])
        if opts.dep_update:
            helm.dependency_build(rep, chart)
        if not opts.skip_lint and Path(chart).is_dir():
            helm.lint(rep, chart, opts)
        rc, out, err = helm.template(chart, release, opts)
        if rc != 0:
            rep.error = err.strip()
            rep.add("HIGH", "helm-template", "chart", f"helm template falló: {err.strip()[:800]}")
            return rep
        text = out

    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", rep.name or Path(chart).name)
    if opts.save_rendered:
        Path(opts.save_rendered).mkdir(parents=True, exist_ok=True)
        Path(opts.save_rendered, f"{safe}.rendered.yaml").write_text(text, encoding="utf-8")

    analyze(rep, helm.parse_manifests(text), opts.namespace, opts.platform)

    if opts.external:
        with tempfile.TemporaryDirectory() as td:
            rp = Path(td, f"{safe}.yaml")
            rp.write_text(text, encoding="utf-8")
            run_external(rep, chart, str(rp), opts.kube_version)
    return rep
