from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from ..graph_store import GraphStore
from ..models import Edge, Node


def extract_dotnet_metadata(repo_root: Path, store: GraphStore) -> None:
    for project_file in repo_root.rglob("*.csproj"):
        if _is_ignored(project_file):
            continue
        _extract_csproj(project_file, store)


def _extract_csproj(project_file: Path, store: GraphStore) -> None:
    try:
        tree = ET.parse(project_file)
    except ET.ParseError:
        return

    root = tree.getroot()
    project_name = project_file.stem

    project_node = store.upsert_node(
        Node(
            kind="Target",
            name=f"dotnet::{project_name}",
            properties={"build_system": "dotnet", "file": str(project_file)},
            evidence=[str(project_file)],
        )
    )

    for package_ref in root.findall(".//PackageReference"):
        include = package_ref.attrib.get("Include")
        version = package_ref.attrib.get("Version", "")
        if not include:
            continue
        dep_node = store.upsert_node(
            Node(
                kind="ExternalDependency",
                name=f"nuget::{include}",
                properties={"version": version, "file": str(project_file)},
                evidence=[str(project_file)],
            )
        )
        store.upsert_edge(
            Edge(
                source=project_node.id,
                target=dep_node.id,
                relation="depends_on",
                properties={"confidence": "high", "evidence_type": "dotnet-build"},
                evidence=[str(project_file)],
            )
        )

    for project_ref in root.findall(".//ProjectReference"):
        include = project_ref.attrib.get("Include")
        if not include:
            continue
        ref_name = Path(include).stem
        ref_node = store.upsert_node(
            Node(
                kind="Target",
                name=f"dotnet::{ref_name}",
                properties={"build_system": "dotnet", "file": str(project_file)},
                evidence=[str(project_file)],
            )
        )
        store.upsert_edge(
            Edge(
                source=project_node.id,
                target=ref_node.id,
                relation="depends_on",
                properties={"confidence": "high", "evidence_type": "dotnet-build"},
                evidence=[str(project_file)],
            )
        )

    if _looks_like_test_project(project_name, root):
        test_node = store.upsert_node(
            Node(
                kind="Test",
                name=f"dotnet-test::{project_name}",
                properties={"file": str(project_file)},
                evidence=[str(project_file)],
            )
        )
        store.upsert_edge(
            Edge(
                source=project_node.id,
                target=test_node.id,
                relation="tested_by",
                properties={"confidence": "high", "evidence_type": "dotnet-test"},
                evidence=[str(project_file)],
            )
        )


def _looks_like_test_project(project_name: str, root: ET.Element) -> bool:
    lowered = project_name.lower()
    if "test" in lowered or "tests" in lowered:
        return True
    for package_ref in root.findall(".//PackageReference"):
        include = (package_ref.attrib.get("Include") or "").lower()
        if "xunit" in include or "nunit" in include or "mstest" in include:
            return True
    return False


def _is_ignored(path: Path) -> bool:
    ignored_parts = {".git", ".dist", "bin", "obj", "node_modules", ".venv", "venv"}
    return any(part in ignored_parts for part in path.parts)
