"""Checks sobre Chart.yaml y la estructura del chart."""

from __future__ import annotations

from pathlib import Path

from helmreview.constants import PINNED_SEMVER
from helmreview.models import ChartReport


def check_chart_meta(rep: ChartReport, chart: str, meta: dict) -> None:
    rep.name = str(meta.get("name", ""))
    rep.version = str(meta.get("version", ""))
    rep.app_version = str(meta.get("appVersion", "") or "")

    if meta.get("apiVersion") != "v2":
        rep.add(
            "MEDIUM",
            "chart-apiversion",
            "Chart.yaml",
            f"apiVersion '{meta.get('apiVersion')}' (formato Helm 2). Migrar a apiVersion: v2",
        )
    if not meta.get("kubeVersion"):
        rep.add(
            "LOW",
            "chart-kubeversion",
            "Chart.yaml",
            "Sin kubeVersion: el chart no declara con qué versiones de Kubernetes es compatible",
        )
    if not meta.get("appVersion"):
        rep.add("INFO", "chart-appversion", "Chart.yaml", "Sin appVersion")

    deps = meta.get("dependencies") or []
    for d in deps:
        ver = str(d.get("version", "")).strip()
        name = d.get("name", "?")
        if not ver or not PINNED_SEMVER.match(ver):
            rep.add(
                "MEDIUM",
                "chart-dependency",
                "Chart.yaml",
                f"Dependencia '{name}' con versión no fijada ('{ver or 'vacía'}'): builds no reproducibles",
            )
        if str(d.get("repository", "")).startswith("http://"):
            rep.add("LOW", "chart-dependency", "Chart.yaml", f"Dependencia '{name}' desde repositorio HTTP sin TLS")

    p = Path(chart)
    if p.is_dir():
        if not (p / "values.schema.json").exists():
            rep.add(
                "LOW",
                "chart-schema",
                "chart",
                "Sin values.schema.json: los values no se validan (errores de tipeo pasan silenciosos)",
            )
        if deps and not (p / "Chart.lock").exists():
            rep.add("LOW", "chart-lock", "chart", "Tiene dependencias pero no hay Chart.lock versionado")
