"""Consistency registry sweep — run after milestone batches.

Walks every ``.py`` file in ``src/`` and flags:
- CR-001: error codes raised in src that are not in ``ERROR_REGISTRY``.
- CR-002: ``audit.record("string_literal"...)`` call sites that skip
  the :class:`AuditAction` enum.
- CR-003: ``notifications.send("string_literal"...)`` or ``send_batch``
  call sites that skip the :class:`NotificationTemplate` enum.
"""

from __future__ import annotations

import pathlib
import re
import sys

from app.core.errors import ERROR_REGISTRY


ROOT = pathlib.Path(__file__).resolve().parents[1] / "src"


def _normalize(path: pathlib.Path) -> str:
    return str(path).replace("\\", "/")


def check_cr_001() -> list[str]:
    """Return error codes raised in src that are not in the registry."""
    raised_re = re.compile(r"""raise\s+\w*Error\(\s*['"]([A-Z_]+\d*)['"]""")
    raised: set[str] = set()
    for p in ROOT.rglob("*.py"):
        for match in raised_re.finditer(p.read_text(encoding="utf-8")):
            raised.add(match.group(1))
    registry = set(ERROR_REGISTRY.keys())
    return sorted(raised - registry)


def check_cr_002() -> list[str]:
    """Return audit.record call sites using a string-literal first arg."""
    record_re = re.compile(r"""\.record\(\s*['"]""")
    violations: list[str] = []
    for p in ROOT.rglob("*.py"):
        if "domain/audit" in _normalize(p):
            continue
        for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if record_re.search(line):
                violations.append(f"{_normalize(p)}:{line_no}: {line.strip()[:80]}")
    return violations


def check_cr_003() -> list[str]:
    """Return notifications.send call sites using a string-literal template."""
    send_re = re.compile(r"""\.send(_batch)?\(\s*['"]""")
    violations: list[str] = []
    for p in ROOT.rglob("*.py"):
        if "domain/notifications" in _normalize(p) or "infra/email" in _normalize(p):
            continue
        for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if send_re.search(line):
                violations.append(f"{_normalize(p)}:{line_no}: {line.strip()[:80]}")
    return violations


def main() -> int:
    """Run the sweep and exit non-zero on any violation."""
    cr1 = check_cr_001()
    cr2 = check_cr_002()
    cr3 = check_cr_003()

    print(f"CR-001 unregistered codes: {cr1 or 'OK'}")
    print(f"CR-002 audit string literals: {len(cr2)} violation(s)")
    for v in cr2:
        print(f"  {v}")
    print(f"CR-003 notification string literals: {len(cr3)} violation(s)")
    for v in cr3:
        print(f"  {v}")

    return 0 if not (cr1 or cr2 or cr3) else 1


if __name__ == "__main__":
    sys.exit(main())
