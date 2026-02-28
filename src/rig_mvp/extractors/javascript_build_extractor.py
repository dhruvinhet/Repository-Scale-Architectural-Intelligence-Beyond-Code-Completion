from __future__ import annotations

import json
from pathlib import Path

from ..graph_store import GraphStore
from ..models import Edge, Node


def extract_javascript_build_metadata(repo_root: Path, store: GraphStore) -> None:
    for package_file in repo_root.rglob("package.json"):
        if _is_ignored(package_file):
            continue
        _extract_package_json(package_file, store)


def _extract_package_json(package_file: Path, store: GraphStore) -> None:
    try:
        payload = json.loads(package_file.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return

    package_name = payload.get("name") or package_file.parent.name
    package_node = store.upsert_node(
        Node(
            kind="Target",
            name=f"npm::{package_name}",
            properties={"build_system": "npm", "file": str(package_file)},
            evidence=[str(package_file)],
        )
    )

    _extract_dep_map(store, package_node, package_file, payload.get("dependencies", {}), confidence="high")
    _extract_dep_map(store, package_node, package_file, payload.get("devDependencies", {}), confidence="medium")
    _extract_dep_map(store, package_node, package_file, payload.get("peerDependencies", {}), confidence="medium")

    scripts = payload.get("scripts", {})
    if isinstance(scripts, dict):
        for script_name, script_cmd in scripts.items():
            if not isinstance(script_name, str):
                continue
            if "test" not in script_name.lower():
                continue
            test_node = store.upsert_node(
                Node(
                    kind="Test",
                    name=f"npm-test::{package_name}:{script_name}",
                    properties={"command": str(script_cmd), "file": str(package_file)},
                    evidence=[str(package_file)],
                )
            )
            store.upsert_edge(
                Edge(
                    source=package_node.id,
                    target=test_node.id,
                    relation="tested_by",
                    properties={"confidence": "high", "evidence_type": "build-test"},
                    evidence=[str(package_file)],
                )
            )


def _extract_dep_map(
    store: GraphStore,
    source_node: Node,
    package_file: Path,
    dep_map: object,
    confidence: str,
) -> None:
    if not isinstance(dep_map, dict):
        return

    for dep_name, dep_version in dep_map.items():
        if not isinstance(dep_name, str):
            continue
        dep_node = store.upsert_node(
            Node(
                kind="ExternalDependency",
                name=f"npm-pkg::{dep_name}",
                properties={"ecosystem": "npm", "version": str(dep_version), "file": str(package_file)},
                evidence=[str(package_file)],
            )
        )
        store.upsert_edge(
            Edge(
                source=source_node.id,
                target=dep_node.id,
                relation="depends_on",
                properties={"confidence": confidence, "evidence_type": "javascript-build"},
                evidence=[str(package_file)],
            )
        )


def _is_ignored(path: Path) -> bool:
    ignored_parts = {"node_modules", ".git", ".dist", ".venv", "venv", "__pycache__"}
    return any(part in ignored_parts for part in path.parts)
