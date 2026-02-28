from __future__ import annotations

import json
from pathlib import Path


def diff_rig_snapshots(old_path: Path, new_path: Path) -> dict[str, object]:
    old_payload = json.loads(old_path.read_text(encoding="utf-8"))
    new_payload = json.loads(new_path.read_text(encoding="utf-8"))

    old_nodes = {
        str(node.get("id")): str(node.get("name"))
        for node in old_payload.get("nodes", [])
        if isinstance(node, dict)
    }
    new_nodes = {
        str(node.get("id")): str(node.get("name"))
        for node in new_payload.get("nodes", [])
        if isinstance(node, dict)
    }

    old_edges = {
        f"{edge.get('source')}|{edge.get('relation')}|{edge.get('target')}"
        for edge in old_payload.get("edges", [])
        if isinstance(edge, dict)
    }
    new_edges = {
        f"{edge.get('source')}|{edge.get('relation')}|{edge.get('target')}"
        for edge in new_payload.get("edges", [])
        if isinstance(edge, dict)
    }

    added_node_ids = sorted(set(new_nodes) - set(old_nodes))
    removed_node_ids = sorted(set(old_nodes) - set(new_nodes))

    report = {
        "old": str(old_path),
        "new": str(new_path),
        "node_delta": {
            "added_count": len(added_node_ids),
            "removed_count": len(removed_node_ids),
            "added": [new_nodes[node_id] for node_id in added_node_ids[:200]],
            "removed": [old_nodes[node_id] for node_id in removed_node_ids[:200]],
        },
        "edge_delta": {
            "added_count": len(new_edges - old_edges),
            "removed_count": len(old_edges - new_edges),
            "added": sorted(new_edges - old_edges)[:300],
            "removed": sorted(old_edges - new_edges)[:300],
        },
    }
    return report
