"""Utilidades para trabajar con objetos de Kubernetes ya parseados (dicts)."""

from __future__ import annotations


def to_int(v, default: int = 1) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def rid(obj: dict) -> str:
    """Identificador legible: Kind/nombre."""
    return f"{obj.get('kind')}/{(obj.get('metadata') or {}).get('name', '?')}"


def image_ref(image: str) -> tuple[str, str]:
    """Clasifica la referencia de imagen: ('digest'|'tag'|'none', valor)."""
    if "@" in image:
        return "digest", image.split("@", 1)[1]
    last = image.rsplit("/", 1)[-1]  # evita confundir el puerto del registry con un tag
    if ":" in last:
        return "tag", last.split(":", 1)[1]
    return "none", ""


def selector_matches(selector: dict | None, labels: dict) -> bool:
    """Evalúa un LabelSelector de Kubernetes contra un set de labels."""
    if selector is None:
        return False
    ml = selector.get("matchLabels") or {}
    exprs = selector.get("matchExpressions") or []
    if not ml and not exprs:
        return True  # selector vacío = todos los pods del namespace
    if any(labels.get(k) != v for k, v in ml.items()):
        return False
    for e in exprs:
        key, op, vals = e.get("key"), e.get("operator"), e.get("values") or []
        if op == "In" and labels.get(key) not in vals:
            return False
        if op == "NotIn" and labels.get(key) in vals:
            return False
        if op == "Exists" and key not in labels:
            return False
        if op == "DoesNotExist" and key in labels:
            return False
    return True


def pod_template(obj: dict) -> tuple[dict, dict]:
    """Devuelve (metadata, spec) del pod de cualquier workload."""
    kind, spec = obj["kind"], obj.get("spec") or {}
    if kind == "Pod":
        return obj.get("metadata") or {}, spec
    if kind == "CronJob":
        tpl = ((spec.get("jobTemplate") or {}).get("spec") or {}).get("template") or {}
    else:
        tpl = spec.get("template") or {}
    return tpl.get("metadata") or {}, tpl.get("spec") or {}
