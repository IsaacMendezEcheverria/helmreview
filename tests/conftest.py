from __future__ import annotations

from pathlib import Path

import pytest

from helmreview.checks import analyze
from helmreview.helm import parse_manifests
from helmreview.models import ChartReport

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def analyze_text(text: str, platform: str = "kubernetes", namespace: str = "default") -> ChartReport:
    """Analiza un YAML en texto y devuelve el reporte (sin helm)."""
    rep = ChartReport(chart="test")
    analyze(rep, parse_manifests(text), namespace, platform)
    return rep


def analyze_file(name: str, platform: str = "kubernetes") -> ChartReport:
    return analyze_text((FIXTURES / "rendered" / name).read_text(encoding="utf-8"), platform)


def checks_for(rep: ChartReport, resource: str | None = None, severity: str | None = None) -> set[str]:
    """IDs de checks presentes, opcionalmente filtrados por recurso y severidad."""
    return {
        f.check
        for f in rep.findings
        if (resource is None or f.resource == resource) and (severity is None or f.severity == severity)
    }
