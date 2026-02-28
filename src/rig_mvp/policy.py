from __future__ import annotations

import json
from pathlib import Path

DEP_RELATIONS = {"depends_on", "imports", "calls"}

def evaluate_policies(rig_path: Path, forbid_rules: list[str] | None = None) -> dict[str, object]:
    payload = json.loads(rig_path.read_text(encoding="utf-8"))
    nodes = {str(node.get("id")): node for node in payload.get("nodes", []) if isinstance(node, dict)}
    edges = [edge for edge in payload.get("edges", []) if isinstance(edge, dict)]

    graph: dict[str, list[str]] = {}
    for edge in edges:
        relation = str(edge.get("relation", ""))
        if relation not in DEP_RELATIONS:
            continue
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        graph.setdefault(source, []).append(target)

    cycles = _find_cycles(graph)
    parsed_rules = _parse_forbid_rules(forbid_rules or [])
    forbidden_violations = _find_forbidden_edges(edges, nodes, parsed_rules)

    return {
        "rig": str(rig_path),
        "checks": {
            "dependency_cycles": {
                "count": len(cycles),
                "samples": cycles[:50],
            },
            "forbidden_dependency_directions": {
                "count": len(forbidden_violations),
                "samples": forbidden_violations[:100],
                "rules": forbid_rules or [],
            },
        },
        "passed": len(cycles) == 0 and len(forbidden_violations) == 0,
    }

def _find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    visited: set[str] = set()
    stack: list[str] = []
    in_stack: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        visited.add(node)
        stack.append(node)
        in_stack.add(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in in_stack:
                idx = stack.index(neighbor)
                cycle = stack[idx:] + [neighbor]
                cycles.append(cycle)

        stack.pop()
        in_stack.remove(node)

    for node in list(graph.keys()):
        if node not in visited:
            dfs(node)

    dedup: set[str] = set()
    normalized: list[list[str]] = []
    for cycle in cycles:
        key = "->".join(cycle)
        if key in dedup:
            continue
        dedup.add(key)
        normalized.append(cycle)
    return normalized

def _parse_forbid_rules(rules: list[str]) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for rule in rules:
        if "->" not in rule:
            continue
        left, right = rule.split("->", 1)
        parsed.append((left.strip(), right.strip()))
    return parsed

def _find_forbidden_edges(
    edges: list[dict[str, object]],
    nodes: dict[str, dict[str, object]],
    rules: list[tuple[str, str]],
) -> list[dict[str, str]]:
    if not rules:
        return []

    violations: list[dict[str, str]] = []
    for edge in edges:
        relation = str(edge.get("relation", ""))
        if relation not in DEP_RELATIONS:
            continue

        source_id = str(edge.get("source", ""))
        target_id = str(edge.get("target", ""))
        source_name = str(nodes.get(source_id, {}).get("name", ""))
        target_name = str(nodes.get(target_id, {}).get("name", ""))

        for left, right in rules:
            if source_name.startswith(left) and target_name.startswith(right):
                violations.append(
                    {
                        "rule": f"{left}->{right}",
                        "source": source_name,
                        "relation": relation,
                        "target": target_name,
                    }
                )
    return violations
