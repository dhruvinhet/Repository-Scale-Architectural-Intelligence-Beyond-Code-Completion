from __future__ import annotations

from pathlib import Path

from .extractors.ast_extractor import extract_python_ast
from .extractors.build_extractor import extract_build_graph
from .extractors.dotnet_extractor import extract_dotnet_metadata
from .extractors.javascript_build_extractor import extract_javascript_build_metadata
from .extractors.javascript_source_extractor import extract_javascript_source_graph
from .extractors.maven_extractor import extract_maven_metadata
from .extractors.python_build_extractor import extract_python_build_metadata
from .extractors.test_extractor import extract_test_wiring
from .graph_store import GraphStore


def build_rig(repo_root: Path) -> GraphStore:
    store = GraphStore()
    extract_build_graph(repo_root, store)
    extract_python_build_metadata(repo_root, store)
    extract_javascript_build_metadata(repo_root, store)
    extract_javascript_source_graph(repo_root, store)
    extract_maven_metadata(repo_root, store)
    extract_dotnet_metadata(repo_root, store)
    extract_python_ast(repo_root, store)
    extract_test_wiring(repo_root, store)
    return store
