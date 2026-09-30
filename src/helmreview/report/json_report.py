"""Reporte JSON (para integrar con otras herramientas o dashboards)."""

from __future__ import annotations

import json
from pathlib import Path

from helmreview import __version__
from helmreview.models import ChartReport


def write_json(reports: list[ChartReport], path: str) -> None:
    data = {"tool": "helmreview", "version": __version__, "charts": [r.to_dict() for r in reports]}
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
