"""Parseo y formato de cantidades de Kubernetes (CPU y memoria/almacenamiento)."""

from __future__ import annotations

_MEM_SUFFIX = [
    ("Ki", 2**10), ("Mi", 2**20), ("Gi", 2**30), ("Ti", 2**40), ("Pi", 2**50), ("Ei", 2**60),
    ("k", 1e3), ("K", 1e3), ("M", 1e6), ("G", 1e9), ("T", 1e12), ("P", 1e15), ("E", 1e18),
    ("m", 1e-3),
]  # fmt: skip


def parse_mem(v) -> float | None:
    """Cantidad de memoria/almacenamiento -> bytes. None si el valor no es válido."""
    if v is None:
        return None
    s = str(v).strip()
    for suf, mult in _MEM_SUFFIX:
        if s.endswith(suf):
            try:
                return float(s[: -len(suf)]) * mult
            except ValueError:
                return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_cpu(v) -> float | None:
    """Cantidad de CPU -> milicores. None si el valor no es válido."""
    if v is None:
        return None
    s = str(v).strip()
    try:
        return float(s[:-1]) if s.endswith("m") else float(s) * 1000
    except ValueError:
        return None


def fmt_cpu(m: float | None) -> str:
    if not m:
        return "-"
    if m < 1000:
        return f"{m:.0f}m"
    return f"{m / 1000:.2f}".rstrip("0").rstrip(".")


def fmt_mem(b: float | None) -> str:
    if not b:
        return "-"
    for suf, mult in (("Ti", 2**40), ("Gi", 2**30), ("Mi", 2**20), ("Ki", 2**10)):
        if b >= mult:
            return f"{b / mult:.2f}".rstrip("0").rstrip(".") + suf
    return f"{b:.0f}"
