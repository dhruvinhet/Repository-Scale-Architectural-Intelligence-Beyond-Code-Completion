from __future__ import annotations

from pathlib import Path
import re
import tomllib

from ..graph_store import GraphStore
from ..models import Edge, Node


REQ_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


def extract_python_build_metadata(repo_root: Path, store: GraphStore) -> None:
    _extract_pyproject(repo_root, store)
    _extract_requirements(repo_root, store)
    _extract_setup_cfg(repo_root, store)


def _extract_pyproject(repo_root: Path, store: GraphStore) -> None:
    file_path = repo_root / "pyproject.toml"
    if not file_path.exists():
        return

    payload = tomllib.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
    project = payload.get("project", {}) if isinstance(payload, dict) else {}
    if not isinstance(project, dict):
        return

    project_name = str(project.get("name") or repo_root.name)
    project_node = store.upsert_node(
        Node(
            kind="Target",
            name=f"python::{project_name}",
            properties={"build_system": "python", "file": str(file_path)},
            evidence=[str(file_path)],
        )
    )

    dependencies = project.get("dependencies", [])
    if isinstance(dependencies, list):
        for dependency in dependencies:
            if not isinstance(dependency, str):
                continue
            name = _normalize_dep_name(dependency)
            dep_node = _upsert_python_dep_node(store, name, file_path)
            store.upsert_edge(
                Edge(
                    source=project_node.id,
                    target=dep_node.id,
                    relation="depends_on",
                    properties={"confidence": "high", "evidence_type": "python-build"},
                    evidence=[str(file_path)],
                )
            )


def _extract_requirements(repo_root: Path, store: GraphStore) -> None:
    req_files = list(repo_root.rglob("requirements*.txt"))
    for req_file in req_files:
        req_relative = req_file.relative_to(repo_root).as_posix()
        req_target = store.upsert_node(
            Node(
                kind="Target",
                name=f"python-req::{req_relative}",
                properties={"build_system": "python", "file": str(req_file)},
                evidence=[str(req_file)],
            )
        )

        for raw in req_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = REQ_PATTERN.match(line)
            if not match:
                continue
            dep_name = match.group(1)
            dep_node = _upsert_python_dep_node(store, dep_name, req_file)
            store.upsert_edge(
                Edge(
                    source=req_target.id,
                    target=dep_node.id,
                    relation="depends_on",
                    properties={"confidence": "high", "evidence_type": "python-build"},
                    evidence=[str(req_file)],
                )
            )


def _extract_setup_cfg(repo_root: Path, store: GraphStore) -> None:
    file_path = repo_root / "setup.cfg"
    if not file_path.exists():
        return

    text = file_path.read_text(encoding="utf-8", errors="ignore")
    project_node = store.upsert_node(
        Node(
            kind="Target",
            name=f"python-setup::{repo_root.name}",
            properties={"build_system": "python", "file": str(file_path)},
            evidence=[str(file_path)],
        )
    )

    in_options = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_options = line.lower() == "[options]"
            continue
        if not in_options or not line.startswith("install_requires"):
            continue

        _, _, value = line.partition("=")
        for dep in value.split():
            name = _normalize_dep_name(dep)
            dep_node = _upsert_python_dep_node(store, name, file_path)
            store.upsert_edge(
                Edge(
                    source=project_node.id,
                    target=dep_node.id,
                    relation="depends_on",
                    properties={"confidence": "medium", "evidence_type": "python-build"},
                    evidence=[str(file_path)],
                )
            )


def _normalize_dep_name(raw: str) -> str:
    splitters = ["[", "=", "<", ">", "~", "!", ";"]
    result = raw.strip()
    for splitter in splitters:
        if splitter in result:
            result = result.split(splitter, 1)[0]
    return result.strip()


def _upsert_python_dep_node(store: GraphStore, dep_name: str, evidence_file: Path) -> Node:
    return store.upsert_node(
        Node(
            kind="ExternalDependency",
            name=f"pypi::{dep_name}",
            properties={"ecosystem": "python", "file": str(evidence_file)},
            evidence=[str(evidence_file)],
        )
    )
