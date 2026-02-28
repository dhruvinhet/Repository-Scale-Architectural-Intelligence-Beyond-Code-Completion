from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from ..graph_store import GraphStore
from ..models import Edge, Node


def extract_maven_metadata(repo_root: Path, store: GraphStore) -> None:
    for pom_file in repo_root.rglob("pom.xml"):
        if _is_ignored(pom_file):
            continue
        _extract_pom(pom_file, store)


def _extract_pom(pom_file: Path, store: GraphStore) -> None:
    try:
        tree = ET.parse(pom_file)
    except ET.ParseError:
        return

    root = tree.getroot()
    ns = _namespace(root.tag)

    artifact = _find_text(root, f"{ns}artifactId") or pom_file.parent.name
    group = _find_text(root, f"{ns}groupId") or "unknown-group"
    module_name = f"maven::{group}:{artifact}"

    module_node = store.upsert_node(
        Node(
            kind="Target",
            name=module_name,
            properties={"build_system": "maven", "file": str(pom_file)},
            evidence=[str(pom_file)],
        )
    )

    for dep in root.findall(f".//{ns}dependency"):
        dep_group = _find_text(dep, f"{ns}groupId") or "unknown-group"
        dep_artifact = _find_text(dep, f"{ns}artifactId") or "unknown-artifact"
        scope = _find_text(dep, f"{ns}scope") or "compile"

        dep_node = store.upsert_node(
            Node(
                kind="ExternalDependency",
                name=f"maven-pkg::{dep_group}:{dep_artifact}",
                properties={"scope": scope, "file": str(pom_file)},
                evidence=[str(pom_file)],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=dep_node.id,
                relation="depends_on",
                properties={"confidence": "high", "evidence_type": "maven-build"},
                evidence=[str(pom_file)],
            )
        )

        if scope == "test":
            test_node = store.upsert_node(
                Node(
                    kind="Test",
                    name=f"maven-test::{group}:{artifact}",
                    properties={"file": str(pom_file)},
                    evidence=[str(pom_file)],
                )
            )
            store.upsert_edge(
                Edge(
                    source=module_node.id,
                    target=test_node.id,
                    relation="tested_by",
                    properties={"confidence": "medium", "evidence_type": "maven-test"},
                    evidence=[str(pom_file)],
                )
            )

    for module in root.findall(f".//{ns}modules/{ns}module"):
        module_text = (module.text or "").strip()
        if not module_text:
            continue
        child_node = store.upsert_node(
            Node(
                kind="Target",
                name=f"maven-module::{module_text}",
                properties={"build_system": "maven", "file": str(pom_file)},
                evidence=[str(pom_file)],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=child_node.id,
                relation="contains",
                properties={"confidence": "high", "evidence_type": "maven-module"},
                evidence=[str(pom_file)],
            )
        )


def _namespace(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[: tag.index("}") + 1]
    return ""


def _find_text(node: ET.Element, path: str) -> str | None:
    child = node.find(path)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _is_ignored(path: Path) -> bool:
    ignored_parts = {".git", ".dist", "target", "build", "node_modules", ".venv", "venv"}
    return any(part in ignored_parts for part in path.parts)
