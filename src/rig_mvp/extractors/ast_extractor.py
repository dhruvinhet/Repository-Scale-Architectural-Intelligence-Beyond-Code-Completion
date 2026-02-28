from __future__ import annotations

import ast
import builtins
from pathlib import Path

from ..graph_store import GraphStore
from ..models import Edge, Node


class PythonSymbolVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.classes: list[str] = []
        self.functions: list[str] = []
        self.imports: list[str] = []
        self.calls: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.append(node.module)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.append(node.func.attr)
        self.generic_visit(node)


def extract_python_ast(repo_root: Path, store: GraphStore) -> None:
    for py_file in repo_root.rglob("*.py"):
        if _is_ignored(py_file):
            continue
        _extract_python_file(repo_root, py_file, store)


def _is_ignored(path: Path) -> bool:
    ignored_parts = {".venv", "venv", "__pycache__", ".git", ".dist"}
    return any(part in ignored_parts for part in path.parts)


def _extract_python_file(repo_root: Path, py_file: Path, store: GraphStore) -> None:
    relative = py_file.relative_to(repo_root).as_posix()
    source = py_file.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return

    visitor = PythonSymbolVisitor()
    visitor.visit(tree)

    module_name = relative.removesuffix(".py").replace("/", ".")
    module_node = store.upsert_node(
        Node(
            kind="Module",
            name=module_name,
            properties={"path": relative, "language": "python"},
            evidence=[relative],
        )
    )

    for class_name in sorted(set(visitor.classes)):
        class_node = store.upsert_node(
            Node(
                kind="Class",
                name=f"{module_name}.{class_name}",
                properties={"module": module_name},
                evidence=[relative],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=class_node.id,
                relation="contains",
                properties={"confidence": "high", "evidence_type": "ast"},
                evidence=[relative],
            )
        )

    for function_name in sorted(set(visitor.functions)):
        function_node = store.upsert_node(
            Node(
                kind="Function",
                name=f"{module_name}.{function_name}",
                properties={"module": module_name},
                evidence=[relative],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=function_node.id,
                relation="contains",
                properties={"confidence": "high", "evidence_type": "ast"},
                evidence=[relative],
            )
        )

    for imported in sorted(set(visitor.imports)):
        import_node = store.upsert_node(
            Node(
                kind="Module",
                name=imported,
                properties={"external": True},
                evidence=[relative],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=import_node.id,
                relation="imports",
                properties={"confidence": "high", "evidence_type": "ast"},
                evidence=[relative],
            )
        )

    for call in sorted(set(visitor.calls)):
        if _is_noisy_call(call):
            continue
        call_node = store.upsert_node(
            Node(
                kind="Function",
                name=call,
                properties={"inferred": True},
                evidence=[relative],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=call_node.id,
                relation="calls",
                properties={"confidence": "low", "evidence_type": "ast-inferred"},
                evidence=[relative],
            )
        )


def _is_noisy_call(call_name: str) -> bool:
    if not call_name or len(call_name) < 3:
        return True
    if call_name.startswith("__") and call_name.endswith("__"):
        return True

    builtin_names = set(dir(builtins))
    noisy_builtins = {
        "print",
        "len",
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "range",
        "enumerate",
        "zip",
        "map",
        "filter",
        "open",
        "isinstance",
        "getattr",
        "setattr",
        "hasattr",
        "sum",
        "min",
        "max",
        "sorted",
        "all",
        "any",
    }

    lowered = call_name.lower()
    if call_name in builtin_names and lowered in noisy_builtins:
        return True
    return False
