from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import Edge, Node


class GraphStore:
    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: dict[tuple[str, str, str], Edge] = {}

    @property
    def nodes(self) -> dict[str, Node]:
        return self._nodes

    @property
    def edges(self) -> dict[tuple[str, str, str], Edge]:
        return self._edges

    def upsert_node(self, node: Node) -> Node:
        current = self._nodes.get(node.id)
        if current is None:
            self._nodes[node.id] = node
            return node

        current.properties.update(node.properties)
        for item in node.evidence:
            if item not in current.evidence:
                current.evidence.append(item)
        return current

    def upsert_edge(self, edge: Edge) -> Edge:
        current = self._edges.get(edge.key)
        if current is None:
            self._edges[edge.key] = edge
            return edge

        current.properties.update(edge.properties)
        for item in edge.evidence:
            if item not in current.evidence:
                current.evidence.append(item)
        return current

    def to_dict(self) -> dict[str, object]:
        nodes = sorted(self._nodes.values(), key=lambda node: node.id)
        edges = sorted(self._edges.values(), key=lambda edge: edge.key)
        confidence_counts = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
        for edge in edges:
            confidence = edge.properties.get("confidence") if isinstance(edge.properties, dict) else None
            key = str(confidence).lower() if confidence else "unknown"
            if key not in confidence_counts:
                key = "unknown"
            confidence_counts[key] += 1
        return {
            "nodes": [asdict(node) for node in nodes],
            "edges": [asdict(edge) for edge in edges],
            "metadata": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "deterministic": True,
                "confidence_counts": confidence_counts,
            },
        }

    def write_json(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
