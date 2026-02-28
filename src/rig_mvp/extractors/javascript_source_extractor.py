from __future__ import annotations

import re
from pathlib import Path

from ..graph_store import GraphStore
from ..models import Edge, Node

_SOURCE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}
_IGNORED_PARTS = {"node_modules", ".git", ".dist", ".venv", "venv", "__pycache__", "dist", "build"}

_IMPORT_RE = re.compile(
    r"^\s*import\s+(?:.+?\s+from\s+)?[\"']([^\"']+)[\"']\s*;?",
    flags=re.MULTILINE,
)

_EXPORT_DEFAULT_FUNCTION_RE = re.compile(
    r"export\s+default\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    flags=re.MULTILINE,
)

_NAMED_FUNCTION_RE = re.compile(
    r"(?:export\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    flags=re.MULTILINE,
)

_CONST_COMPONENT_RE = re.compile(
    r"(?:export\s+)?const\s+([A-Z][A-Za-z0-9_]*)\s*=\s*(?:\([^)]*\)|[A-Za-z_][A-Za-z0-9_]*)\s*=>",
    flags=re.MULTILINE,
)

_CLASS_COMPONENT_RE = re.compile(
    r"class\s+([A-Z][A-Za-z0-9_]*)\s+extends\s+(?:React\.)?Component",
    flags=re.MULTILINE,
)

_HOOK_RE = re.compile(r"(?:export\s+)?function\s+(use[A-Z][A-Za-z0-9_]*)\s*\(", flags=re.MULTILINE)
_ROUTE_ELEMENT_RE = re.compile(r"<Route[^>]*element=\{<([A-Z][A-Za-z0-9_]*)", flags=re.MULTILINE)
_JSX_COMPONENT_USAGE_RE = re.compile(r"<([A-Z][A-Za-z0-9_]*)\b")


def extract_javascript_source_graph(repo_root: Path, store: GraphStore) -> None:
    source_files = [
        path
        for path in repo_root.rglob("*")
        if path.is_file() and path.suffix.lower() in _SOURCE_EXTENSIONS and not _is_ignored(path)
    ]
    source_files = sorted(source_files)

    module_node_by_file: dict[Path, Node] = {}
    package_node_by_dir: dict[Path, Node] = {}

    for source_file in source_files:
        module_node = _upsert_module_node(repo_root, source_file, store)
        module_node_by_file[source_file] = module_node

        package_file = _find_nearest_package_json(source_file, repo_root)
        if package_file:
            package_dir = package_file.parent
            package_node = package_node_by_dir.get(package_dir)
            if package_node is None:
                package_node = _upsert_package_target(package_file, package_dir, store)
                package_node_by_dir[package_dir] = package_node
            store.upsert_edge(
                Edge(
                    source=package_node.id,
                    target=module_node.id,
                    relation="contains",
                    properties={"confidence": "medium", "evidence_type": "javascript-source"},
                    evidence=[str(source_file)],
                )
            )

    file_lookup = {path.resolve(): node for path, node in module_node_by_file.items()}

    for source_file in source_files:
        module_node = module_node_by_file[source_file]
        content = source_file.read_text(encoding="utf-8", errors="ignore")

        _extract_import_edges(repo_root, source_file, module_node, file_lookup, content, store)
        _extract_symbol_nodes(source_file, module_node, content, store)
        _extract_usage_edges(source_file, module_node, content, store)


def _upsert_module_node(repo_root: Path, source_file: Path, store: GraphStore) -> Node:
    relative = source_file.relative_to(repo_root).as_posix()
    without_ext = relative.rsplit(".", 1)[0]
    module_name = without_ext.replace("/", ".")

    return store.upsert_node(
        Node(
            kind="Module",
            name=module_name,
            properties={"language": "javascript", "file": str(source_file)},
            evidence=[str(source_file)],
        )
    )


def _upsert_package_target(package_file: Path, package_dir: Path, store: GraphStore) -> Node:
    package_name = package_dir.name
    try:
        import json

        payload = json.loads(package_file.read_text(encoding="utf-8", errors="ignore"))
        if isinstance(payload, dict):
            raw_name = payload.get("name")
            if isinstance(raw_name, str) and raw_name.strip():
                package_name = raw_name.strip()
    except Exception:
        pass

    return store.upsert_node(
        Node(
            kind="Target",
            name=f"npm::{package_name}",
            properties={"build_system": "npm", "file": str(package_file)},
            evidence=[str(package_file)],
        )
    )


def _extract_import_edges(
    repo_root: Path,
    source_file: Path,
    module_node: Node,
    file_lookup: dict[Path, Node],
    content: str,
    store: GraphStore,
) -> None:
    for imported_path in _IMPORT_RE.findall(content):
        if imported_path.startswith("."):
            resolved = _resolve_relative_import(source_file, imported_path)
            if resolved and resolved.resolve() in file_lookup:
                target_node = file_lookup[resolved.resolve()]
                store.upsert_edge(
                    Edge(
                        source=module_node.id,
                        target=target_node.id,
                        relation="imports",
                        properties={"confidence": "high", "evidence_type": "javascript-source"},
                        evidence=[str(source_file)],
                    )
                )
            else:
                fallback_name = _to_module_name(repo_root, resolved) if resolved else imported_path
                target_node = store.upsert_node(
                    Node(
                        kind="Module",
                        name=fallback_name,
                        properties={"inferred": True, "language": "javascript"},
                        evidence=[str(source_file)],
                    )
                )
                store.upsert_edge(
                    Edge(
                        source=module_node.id,
                        target=target_node.id,
                        relation="imports",
                        properties={"confidence": "medium", "evidence_type": "javascript-source"},
                        evidence=[str(source_file)],
                    )
                )
            continue

        dep_node = store.upsert_node(
            Node(
                kind="ExternalDependency",
                name=f"npm-pkg::{imported_path}",
                properties={"ecosystem": "npm", "file": str(source_file)},
                evidence=[str(source_file)],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=dep_node.id,
                relation="depends_on",
                properties={"confidence": "high", "evidence_type": "javascript-import"},
                evidence=[str(source_file)],
            )
        )


def _extract_symbol_nodes(source_file: Path, module_node: Node, content: str, store: GraphStore) -> None:
    symbol_names: set[str] = set()

    for name in _EXPORT_DEFAULT_FUNCTION_RE.findall(content):
        symbol_names.add(name)
    for name in _NAMED_FUNCTION_RE.findall(content):
        symbol_names.add(name)
    for name in _CONST_COMPONENT_RE.findall(content):
        symbol_names.add(name)
    for name in _CLASS_COMPONENT_RE.findall(content):
        symbol_names.add(name)
    for name in _HOOK_RE.findall(content):
        symbol_names.add(name)

    for symbol in sorted(symbol_names):
        kind = "Function"
        if symbol.startswith("use"):
            kind = "Function"
        elif symbol[:1].isupper():
            kind = "Class"

        symbol_node = store.upsert_node(
            Node(
                kind=kind,
                name=symbol,
                properties={"file": str(source_file), "language": "javascript"},
                evidence=[str(source_file)],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=symbol_node.id,
                relation="contains",
                properties={"confidence": "medium", "evidence_type": "javascript-symbol"},
                evidence=[str(source_file)],
            )
        )


def _extract_usage_edges(source_file: Path, module_node: Node, content: str, store: GraphStore) -> None:
    symbols = set(_ROUTE_ELEMENT_RE.findall(content))
    symbols.update(_JSX_COMPONENT_USAGE_RE.findall(content))

    for symbol in sorted(symbols):
        if symbol == "Route":
            continue
        target_node = store.upsert_node(
            Node(
                kind="Class",
                name=symbol,
                properties={"language": "javascript", "inferred": True},
                evidence=[str(source_file)],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=target_node.id,
                relation="calls",
                properties={"confidence": "low", "evidence_type": "jsx-usage"},
                evidence=[str(source_file)],
            )
        )


def _resolve_relative_import(source_file: Path, import_path: str) -> Path | None:
    base = (source_file.parent / import_path).resolve()

    candidate_files = [
        base,
        base.with_suffix(".ts"),
        base.with_suffix(".tsx"),
        base.with_suffix(".js"),
        base.with_suffix(".jsx"),
        base / "index.ts",
        base / "index.tsx",
        base / "index.js",
        base / "index.jsx",
    ]

    for candidate in candidate_files:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _to_module_name(repo_root: Path, source_file: Path | None) -> str:
    if not source_file:
        return "unknown-js-module"
    try:
        relative = source_file.relative_to(repo_root).as_posix()
    except ValueError:
        return source_file.as_posix()
    without_ext = relative.rsplit(".", 1)[0]
    return without_ext.replace("/", ".")


def _find_nearest_package_json(source_file: Path, repo_root: Path) -> Path | None:
    cursor = source_file.parent
    while True:
        package = cursor / "package.json"
        if package.exists() and package.is_file():
            return package
        if cursor == repo_root or cursor.parent == cursor:
            break
        cursor = cursor.parent
    return None


def _is_ignored(path: Path) -> bool:
    return any(part in _IGNORED_PARTS for part in path.parts)
