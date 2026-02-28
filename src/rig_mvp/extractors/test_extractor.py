from __future__ import annotations

import ast
from pathlib import Path

from ..graph_store import GraphStore
from ..models import Edge, Node


def extract_test_wiring(repo_root: Path, store: GraphStore) -> None:
    for py_file in repo_root.rglob("*.py"):
        if _is_ignored(py_file):
            continue
        if not _is_test_file(py_file):
            continue
        _extract_test_file(repo_root, py_file, store)


def _is_test_file(path: Path) -> bool:
    name = path.name
    parts = set(path.parts)
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in parts
        or "test" in parts
    )


def _is_ignored(path: Path) -> bool:
    ignored_parts = {".venv", "venv", "__pycache__", ".git", ".dist"}
    return any(part in ignored_parts for part in path.parts)


def _extract_test_file(repo_root: Path, py_file: Path, store: GraphStore) -> None:
    relative = py_file.relative_to(repo_root).as_posix()
    source = py_file.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return

    test_module_name = relative.removesuffix(".py").replace("/", ".")
    test_module = store.upsert_node(
        Node(
            kind="Test",
            name=test_module_name,
            properties={"path": relative, "language": "python"},
            evidence=[relative],
        )
    )

    imported_modules: set[str] = set()
    called_symbols: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_symbols.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_symbols.add(node.func.attr)

    for module in sorted(imported_modules):
        module_node = store.upsert_node(
            Node(
                kind="Module",
                name=module,
                properties={"from_test": True},
                evidence=[relative],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=test_module.id,
                relation="tested_by",
                properties={"confidence": "high", "evidence_type": "test"},
                evidence=[relative],
            )
        )

    for symbol in sorted(called_symbols):
        function_node = store.upsert_node(
            Node(
                kind="Function",
                name=symbol,
                properties={"from_test": True},
                evidence=[relative],
            )
        )
        store.upsert_edge(
            Edge(
                source=function_node.id,
                target=test_module.id,
                relation="tested_by",
                properties={"confidence": "medium", "evidence_type": "test"},
                evidence=[relative],
            )
        )
