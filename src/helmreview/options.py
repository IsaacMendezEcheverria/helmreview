"""Opciones de una revisión (independientes del CLI, para poder usar helmreview como librería)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReviewOptions:
    values: list[str] = field(default_factory=list)  # archivos -f, en orden
    set_values: list[str] = field(default_factory=list)  # valores --set
    release: str | None = None
    namespace: str = "default"
    version: str | None = None  # versión del chart (remotos/OCI)
    kube_version: str | None = None
    api_versions: list[str] = field(default_factory=list)
    platform: str = "kubernetes"  # kubernetes | openshift
    ocp_version: str | None = None
    rendered: str | None = None  # YAML ya renderizado (omite helm template)
    dep_update: bool = False
    skip_lint: bool = False
    external: bool = False
    save_rendered: str | None = None
    ignore: set[str] = field(default_factory=set)  # IDs de checks a omitir

    @property
    def is_openshift(self) -> bool:
        return self.platform == "openshift"
