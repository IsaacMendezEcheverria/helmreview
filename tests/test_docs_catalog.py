"""Garantiza que cada ID de check usado en el código esté documentado en docs/checks.md."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Primer argumento = severidad (literal o expresión sin comas), segundo = ID del check.
PATTERN = re.compile(r'(?:rep\.add|\badd)\(\s*[^,()]+?,\s*f?"([a-z0-9{}-]+)"', re.S)


def _ids_in_code() -> set[str]:
    ids = set()
    for p in (ROOT / "src").rglob("*.py"):
        ids |= set(PATTERN.findall(p.read_text(encoding="utf-8")))
    ids.discard("ext-{name}")
    ids |= {"ext-kubeconform", "ext-kube-linter", "ext-trivy"}
    return ids


def test_all_checks_are_documented():
    doc = (ROOT / "docs" / "checks.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| `([a-z0-9-]+)`", doc, re.M))
    missing = _ids_in_code() - documented
    assert not missing, f"Checks sin documentar en docs/checks.md: {sorted(missing)}"


def test_no_stale_documentation():
    doc = (ROOT / "docs" / "checks.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| `([a-z0-9-]+)`", doc, re.M))
    stale = documented - _ids_in_code()
    assert not stale, f"Checks documentados que ya no existen en el código: {sorted(stale)}"
