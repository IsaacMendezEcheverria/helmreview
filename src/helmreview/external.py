"""Integración opcional con kubeconform, kube-linter y trivy (solo si están en el PATH)."""

from __future__ import annotations

import shutil
from pathlib import Path

from helmreview.helm import run
from helmreview.models import ChartReport

TOOLS = ("kubeconform", "kube-linter", "trivy")


def _kubeconform_version(kube_version: str) -> str:
    kv = kube_version.lstrip("v")
    return kv + ".0" if kv.count(".") == 1 else kv


def build_commands(chart: str, render_path: str, kube_version: str | None) -> dict[str, list[str]]:
    cmds: dict[str, list[str]] = {}
    if shutil.which("kubeconform"):
        cmd = ["kubeconform", "-strict", "-summary", "-ignore-missing-schemas"]
        if kube_version:
            cmd += ["-kubernetes-version", _kubeconform_version(kube_version)]
        cmds["kubeconform"] = cmd + [render_path]
    if shutil.which("kube-linter"):
        cmds["kube-linter"] = ["kube-linter", "lint", render_path]
    if shutil.which("trivy"):
        target = chart if Path(chart).is_dir() else str(Path(render_path).parent)
        cmds["trivy"] = ["trivy", "config", "--quiet", target]
    return cmds


def run_external(rep: ChartReport, chart: str, render_path: str, kube_version: str | None) -> None:
    cmds = build_commands(chart, render_path, kube_version)
    for name in TOOLS:
        if name not in cmds:
            rep.external[name] = {"rc": None, "output": "no instalado"}
            continue
        rc, out, err = run(cmds[name], timeout=600)
        rep.external[name] = {"rc": rc, "output": (out + err).strip()[-6000:]}
        if rc != 0:
            rep.add(
                "MEDIUM", f"ext-{name}", "chart", f"{name} reportó problemas (rc={rc}); ver sección de herramientas"
            )
