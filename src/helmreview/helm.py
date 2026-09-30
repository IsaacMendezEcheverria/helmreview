"""Interacción con el binario `helm` y parseo del YAML renderizado."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

from helmreview.constants import OCP_API_VERSIONS
from helmreview.models import ChartReport
from helmreview.options import ReviewOptions


def run(cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
    """Ejecuta un comando y devuelve (rc, stdout, stderr) sin lanzar excepciones."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"No se encontró el ejecutable: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timeout ejecutando: {' '.join(cmd)}"


def sanitize_release(name: str) -> str:
    name = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    return (name or "release")[:53]


def load_chart_yaml(chart: str, version: str | None = None) -> dict | None:
    """Lee Chart.yaml de un directorio, o vía `helm show chart` para .tgz/repo/OCI."""
    p = Path(chart)
    if p.is_dir():
        f = p / "Chart.yaml"
        return yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else None
    cmd = ["helm", "show", "chart", chart] + (["--version", version] if version else [])
    rc, out, _ = run(cmd)
    return yaml.safe_load(out) if rc == 0 else None


def value_args(opts: ReviewOptions) -> list[str]:
    out: list[str] = []
    for v in opts.values:
        out += ["-f", v]
    for s in opts.set_values:
        out += ["--set", s]
    return out


def dependency_build(rep: ChartReport, chart: str) -> None:
    if not Path(chart).is_dir():
        return
    rc, _, err = run(["helm", "dependency", "build", chart])
    if rc != 0:
        rc, _, err = run(["helm", "dependency", "update", chart])
    if rc != 0:
        rep.add("HIGH", "helm-dependency", "chart", f"No se pudieron resolver dependencias: {err.strip()[:500]}")


def lint(rep: ChartReport, chart: str, opts: ReviewOptions) -> None:
    """Ejecuta `helm lint` y convierte su salida en hallazgos."""
    rc, out, err = run(["helm", "lint", chart] + value_args(opts))
    found = False
    for line in (out + "\n" + err).splitlines():
        m = re.match(r"\s*\[(ERROR|WARNING|INFO)\]\s*(.*)", line)
        if m:
            found = True
            sev = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "INFO"}[m.group(1)]
            rep.add(sev, "helm-lint", "chart", m.group(2).strip())
    if rc != 0 and not found:
        rep.add("HIGH", "helm-lint", "chart", f"helm lint falló: {(err or out).strip()[:500]}")


def template_cmd(chart: str, release: str, opts: ReviewOptions) -> list[str]:
    cmd = ["helm", "template", release, chart, "--namespace", opts.namespace, "--include-crds"]
    cmd += value_args(opts)
    if opts.version:
        cmd += ["--version", opts.version]
    if opts.kube_version:
        cmd += ["--kube-version", opts.kube_version]
    apis = list(opts.api_versions)
    if opts.is_openshift:
        apis += [a for a in OCP_API_VERSIONS if a not in apis]
    for a in apis:
        cmd += ["--api-versions", a]
    return cmd


def template(chart: str, release: str, opts: ReviewOptions) -> tuple[int, str, str]:
    return run(template_cmd(chart, release, opts))


def parse_manifests(text: str) -> list[tuple[dict, str]]:
    """Separa el YAML multi-documento en (objeto, template_origen).

    Los errores de YAML se devuelven como objetos de kind "__YAML_ERROR__".
    """
    docs: list[tuple[dict, str]] = []
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
