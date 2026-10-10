"""Protect the independent deployments from accidental direct cross-service imports."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(("service", "forbidden"), [("app", "mock_bank"), ("mock_bank", "app")])
def test_services_do_not_import_each_other(service: str, forbidden: str) -> None:
    for path in (ROOT / service).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                modules = [node.module or ""]
            else:
                continue
            assert all(module.split(".")[0] != forbidden for module in modules), (
                f"{path.relative_to(ROOT)}:{node.lineno} imports {forbidden} directly"
            )
