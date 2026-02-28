from __future__ import annotations

import re
from pathlib import Path

from ..graph_store import GraphStore
from ..models import Edge, Node


TARGET_PATTERN = re.compile(r"(?:add_executable|add_library)\s*\(([^\s\)]+)", re.IGNORECASE)
LINK_PATTERN = re.compile(r"target_link_libraries\s*\(([^\)]+)\)", re.IGNORECASE)
GRADLE_PROJECT_DEP = re.compile(r"project\(['\"]:([^'\"]+)['\"]\)")
GRADLE_EXT_DEP = re.compile(r"(?:implementation|api|runtimeOnly|compileOnly|testImplementation|testRuntimeOnly)\s*\(?\s*['\"]([^'\"]+)['\"]\s*\)?")
ADD_TEST_PATTERN = re.compile(r"add_test\s*\(([^\)]+)\)", re.IGNORECASE)


def extract_build_graph(repo_root: Path, store: GraphStore) -> None:
    for cmake_file in repo_root.rglob("CMakeLists.txt"):
        _extract_cmake(cmake_file, store)

    for gradle_file in list(repo_root.rglob("build.gradle")) + list(repo_root.rglob("build.gradle.kts")):
        _extract_gradle(gradle_file, store)


def _extract_cmake(cmake_file: Path, store: GraphStore) -> None:
    text = cmake_file.read_text(encoding="utf-8", errors="ignore")
    targets: set[str] = set(TARGET_PATTERN.findall(text))
    target_nodes: dict[str, Node] = {}

    for target in sorted(targets):
        node = store.upsert_node(
            Node(
                kind="Target",
                name=f"cmake::{target}",
                properties={"build_system": "cmake", "file": str(cmake_file)},
                evidence=[str(cmake_file)],
            )
        )
        target_nodes[target] = node

    for match in LINK_PATTERN.findall(text):
        parts = [part.strip() for part in match.split() if part.strip()]
        if len(parts) < 2:
            continue
        source_name = parts[0]
        source_node = target_nodes.get(source_name)
        if source_node is None:
            source_node = store.upsert_node(
                Node(
                    kind="Target",
                    name=f"cmake::{source_name}",
                    properties={"build_system": "cmake", "file": str(cmake_file)},
                    evidence=[str(cmake_file)],
                )
            )

        for dependency in parts[1:]:
            if dependency.upper() in {"PRIVATE", "PUBLIC", "INTERFACE"}:
                continue
            target = target_nodes.get(dependency)
            if target is None:
                target = store.upsert_node(
                    Node(
                        kind="ExternalDependency",
                        name=f"cmake-ext::{dependency}",
                        properties={"build_system": "cmake", "file": str(cmake_file)},
                        evidence=[str(cmake_file)],
                    )
                )
            store.upsert_edge(
                Edge(
                    source=source_node.id,
                    target=target.id,
                    relation="depends_on",
                    properties={"confidence": "high", "evidence_type": "build"},
                    evidence=[str(cmake_file)],
                )
            )

    for test_def in ADD_TEST_PATTERN.findall(text):
        parts = [part.strip() for part in test_def.split() if part.strip()]
        if len(parts) < 2:
            continue
        test_name = parts[0] if parts[0].upper() != "NAME" else (parts[1] if len(parts) > 1 else "unknown")
        command_name = parts[-1]

        test_node = store.upsert_node(
            Node(
                kind="Test",
                name=f"cmake-test::{test_name}",
                properties={"build_system": "cmake", "file": str(cmake_file)},
                evidence=[str(cmake_file)],
            )
        )
        target_node = target_nodes.get(command_name)
        if target_node is None:
            target_node = store.upsert_node(
                Node(
                    kind="Target",
                    name=f"cmake::{command_name}",
                    properties={"build_system": "cmake", "file": str(cmake_file)},
                    evidence=[str(cmake_file)],
                )
            )
        store.upsert_edge(
            Edge(
                source=target_node.id,
                target=test_node.id,
                relation="tested_by",
                properties={"confidence": "high", "evidence_type": "build-test"},
                evidence=[str(cmake_file)],
            )
        )


def _extract_gradle(gradle_file: Path, store: GraphStore) -> None:
    text = gradle_file.read_text(encoding="utf-8", errors="ignore")
    module_name = gradle_file.parent.name
    module_node = store.upsert_node(
        Node(
            kind="Target",
            name=f"gradle::{module_name}",
            properties={"build_system": "gradle", "file": str(gradle_file)},
            evidence=[str(gradle_file)],
        )
    )

    for dep in sorted(set(GRADLE_PROJECT_DEP.findall(text))):
        dep_node = store.upsert_node(
            Node(
                kind="Target",
                name=f"gradle::{dep.replace(':', '/')}",
                properties={"build_system": "gradle", "file": str(gradle_file)},
                evidence=[str(gradle_file)],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=dep_node.id,
                relation="depends_on",
                properties={"confidence": "high", "evidence_type": "build"},
                evidence=[str(gradle_file)],
            )
        )

    for ext in sorted(set(GRADLE_EXT_DEP.findall(text))):
        dep_name = ext.split(":")[1] if ":" in ext and len(ext.split(":")) >= 2 else ext
        dep_node = store.upsert_node(
            Node(
                kind="ExternalDependency",
                name=f"maven::{dep_name}",
                properties={"build_system": "gradle", "coordinate": ext, "file": str(gradle_file)},
                evidence=[str(gradle_file)],
            )
        )
        store.upsert_edge(
            Edge(
                source=module_node.id,
                target=dep_node.id,
                relation="depends_on",
                properties={"confidence": "high", "evidence_type": "build"},
                evidence=[str(gradle_file)],
            )
        )
