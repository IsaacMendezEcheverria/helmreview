"""Checks sobre el chart y los manifiestos renderizados.

- chart_meta: Chart.yaml y archivos del chart.
- manifests: recursos no-workload (Ingress, Route, RBAC, SCC, PVC, HPA...) y orquestación.
- workloads: pods (recursos, probes, HA, seguridad, SCC restricted-v2).
"""

from helmreview.checks.chart_meta import check_chart_meta
from helmreview.checks.manifests import analyze

__all__ = ["analyze", "check_chart_meta"]
