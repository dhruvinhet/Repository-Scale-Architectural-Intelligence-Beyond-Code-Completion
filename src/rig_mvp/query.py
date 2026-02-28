from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class QueryResult:
    query: str
    focus: str
    matches: list[str]

    def to_dict(self) -> dict[str, object]:
        return {"query": self.query, "focus": self.focus, "matches": self.matches}


class RigQueryEngine:
    def __init__(self, rig_json: dict[str, object]) -> None:
        raw_nodes = rig_json.get("nodes", [])
        raw_edges = rig_json.get("edges", [])

        self.nodes_by_id: dict[str, dict[str, object]] = {
            node["id"]: node for node in raw_nodes if isinstance(node, dict) and "id" in node
        }
        self.id_by_name: dict[str, str] = {
            str(node.get("name")): str(node.get("id"))
            for node in raw_nodes
            if isinstance(node, dict) and node.get("name") and node.get("id")
        }

        self.edges = [edge for edge in raw_edges if isinstance(edge, dict)]
        self.forward: dict[str, list[tuple[str, str, str]]] = {}
        self.reverse: dict[str, list[tuple[str, str, str]]] = {}
        for edge in self.edges:
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            relation = str(edge.get("relation", ""))
            properties = edge.get("properties", {}) if isinstance(edge, dict) else {}
            confidence = "unknown"
            if isinstance(properties, dict):
                raw_confidence = properties.get("confidence")
                if isinstance(raw_confidence, str):
                    confidence = raw_confidence.lower()
            self.forward.setdefault(source, []).append((relation, target, confidence))
            self.reverse.setdefault(target, []).append((relation, source, confidence))

    @classmethod
    def from_path(cls, rig_json_path: Path) -> "RigQueryEngine":
        payload = json.loads(rig_json_path.read_text(encoding="utf-8"))
        return cls(payload)

    def find_nodes(self, name_query: str) -> list[str]:
        lowered = name_query.lower()
        names = [name for name in self.id_by_name if lowered in name.lower()]
        return sorted(names)

    def resolve_name(self, name: str) -> str | None:
        node_id = self._resolve_id(name)
        if not node_id:
            return None
        return self._name_for_id(node_id)

    def dependencies_of(
        self,
        name: str,
        relation_filter: set[str] | None = None,
        min_confidence: str = "low",
        path_limit: int | None = None,
    ) -> list[str]:
        node_id = self._resolve_id(name)
        if not node_id:
            return []
        allowed = relation_filter or {"depends_on", "imports", "calls"}
        values = [
            target
            for relation, target, confidence in self.forward.get(node_id, [])
            if relation in allowed and self._confidence_allowed(confidence, min_confidence)
        ]
        if path_limit and path_limit > 0:
            values = values[:path_limit]
        return self._names(values)

    def dependencies_of_explain(
        self,
        name: str,
        relation_filter: set[str] | None = None,
        min_confidence: str = "low",
        path_limit: int | None = None,
    ) -> list[dict[str, str]]:
        node_id = self._resolve_id(name)
        if not node_id:
            return []
        source_name = self._name_for_id(node_id)
        allowed = relation_filter or {"depends_on", "imports", "calls"}
        explanations: list[dict[str, str]] = []
        for relation, target, confidence in self.forward.get(node_id, []):
            if relation not in allowed:
                continue
            if not self._confidence_allowed(confidence, min_confidence):
                continue
            target_name = self._name_for_id(target)
            if not source_name or not target_name:
                continue
            explanations.append({"from": source_name, "relation": relation, "to": target_name, "confidence": confidence})
        explanations = sorted(explanations, key=lambda item: (item["relation"], item["to"]))
        if path_limit and path_limit > 0:
            explanations = explanations[:path_limit]
        return explanations

    def dependents_of(
        self,
        name: str,
        relation_filter: set[str] | None = None,
        min_confidence: str = "low",
        path_limit: int | None = None,
    ) -> list[str]:
        node_id = self._resolve_id(name)
        if not node_id:
            return []
        allowed = relation_filter or {"depends_on", "imports", "calls"}
        values = [
            source
            for relation, source, confidence in self.reverse.get(node_id, [])
            if relation in allowed and self._confidence_allowed(confidence, min_confidence)
        ]
        if path_limit and path_limit > 0:
            values = values[:path_limit]
        return self._names(values)

    def dependents_of_explain(
        self,
        name: str,
        relation_filter: set[str] | None = None,
        min_confidence: str = "low",
        path_limit: int | None = None,
    ) -> list[dict[str, str]]:
        node_id = self._resolve_id(name)
        if not node_id:
            return []
        target_name = self._name_for_id(node_id)
        allowed = relation_filter or {"depends_on", "imports", "calls"}
        explanations: list[dict[str, str]] = []
        for relation, source, confidence in self.reverse.get(node_id, []):
            if relation not in allowed:
                continue
            if not self._confidence_allowed(confidence, min_confidence):
                continue
            source_name = self._name_for_id(source)
            if not source_name or not target_name:
                continue
            explanations.append({"from": source_name, "relation": relation, "to": target_name, "confidence": confidence})
        explanations = sorted(explanations, key=lambda item: (item["relation"], item["from"]))
        if path_limit and path_limit > 0:
            explanations = explanations[:path_limit]
        return explanations

    def tests_for(
        self,
        name: str,
        relation_filter: set[str] | None = None,
        min_confidence: str = "low",
        path_limit: int | None = None,
    ) -> list[str]:
        node_id = self._resolve_id(name)
        if not node_id:
            return []
        if relation_filter is None:
            allowed = {"tested_by"}
        else:
            allowed = {relation for relation in relation_filter if relation == "tested_by"}
            if not allowed:
                return []
        direct = [
            target
            for relation, target, confidence in self.forward.get(node_id, [])
            if relation in allowed and self._confidence_allowed(confidence, min_confidence)
        ]
        reverse = [
            source
            for relation, source, confidence in self.reverse.get(node_id, [])
            if relation in allowed and self._confidence_allowed(confidence, min_confidence)
        ]
        values = direct + reverse
        if path_limit and path_limit > 0:
            values = values[:path_limit]
        return self._names(values)

    def tests_for_explain(
        self,
        name: str,
        relation_filter: set[str] | None = None,
        min_confidence: str = "low",
        path_limit: int | None = None,
    ) -> list[dict[str, str]]:
        node_id = self._resolve_id(name)
        if not node_id:
            return []
        focus_name = self._name_for_id(node_id)
        if relation_filter is None:
            allowed = {"tested_by"}
        else:
            allowed = {relation for relation in relation_filter if relation == "tested_by"}
            if not allowed:
                return []
        explanations: list[dict[str, str]] = []
        for relation, target, confidence in self.forward.get(node_id, []):
            if relation not in allowed:
                continue
            if not self._confidence_allowed(confidence, min_confidence):
                continue
            target_name = self._name_for_id(target)
            if not focus_name or not target_name:
                continue
            explanations.append({"from": focus_name, "relation": relation, "to": target_name, "confidence": confidence})
        for relation, source, confidence in self.reverse.get(node_id, []):
            if relation not in allowed:
                continue
            if not self._confidence_allowed(confidence, min_confidence):
                continue
            source_name = self._name_for_id(source)
            if not source_name or not focus_name:
                continue
            explanations.append({"from": source_name, "relation": relation, "to": focus_name, "confidence": confidence})
        explanations = sorted(explanations, key=lambda item: (item["from"], item["to"]))
        if path_limit and path_limit > 0:
            explanations = explanations[:path_limit]
        return explanations

    def impact_of(
        self,
        name: str,
        relation_filter: set[str] | None = None,
        min_confidence: str = "low",
        path_limit: int | None = None,
    ) -> dict[str, list[str]]:
        return {
            "dependencies": self.dependencies_of(name, relation_filter=relation_filter, min_confidence=min_confidence, path_limit=path_limit),
            "dependents": self.dependents_of(name, relation_filter=relation_filter, min_confidence=min_confidence, path_limit=path_limit),
            "tests": self.tests_for(name, relation_filter=relation_filter, min_confidence=min_confidence, path_limit=path_limit),
        }

    def impact_of_explain(
        self,
        name: str,
        relation_filter: set[str] | None = None,
        min_confidence: str = "low",
        path_limit: int | None = None,
    ) -> dict[str, list[dict[str, str]]]:
        return {
            "dependencies": self.dependencies_of_explain(name, relation_filter=relation_filter, min_confidence=min_confidence, path_limit=path_limit),
            "dependents": self.dependents_of_explain(name, relation_filter=relation_filter, min_confidence=min_confidence, path_limit=path_limit),
            "tests": self.tests_for_explain(name, relation_filter=relation_filter, min_confidence=min_confidence, path_limit=path_limit),
        }

    def _resolve_id(self, name: str) -> str | None:
        if name in self.id_by_name:
            return self.id_by_name[name]
        exact = next((candidate for candidate in self.id_by_name if candidate.lower() == name.lower()), None)
        if exact:
            return self.id_by_name[exact]
        dot_suffix = f".{name}"
        scope_suffix = f"::{name}"
        slash_suffix = f"/{name}"
        suffix_matches = [
            candidate
            for candidate in self.id_by_name
            if candidate.endswith(dot_suffix) or candidate.endswith(scope_suffix) or candidate.endswith(slash_suffix)
        ]
        if len(suffix_matches) == 1:
            return self.id_by_name[suffix_matches[0]]
        contains_matches = [candidate for candidate in self.id_by_name if name.lower() in candidate.lower()]
        if len(contains_matches) == 1:
            return self.id_by_name[contains_matches[0]]
        return None

    def _names(self, ids: list[str]) -> list[str]:
        names: list[str] = []
        for node_id in ids:
            node = self.nodes_by_id.get(node_id)
            if not node:
                continue
            name = node.get("name")
            if isinstance(name, str):
                names.append(name)
        return sorted(set(names))

    def _name_for_id(self, node_id: str) -> str | None:
        node = self.nodes_by_id.get(node_id)
        if not node:
            return None
        name = node.get("name")
        return name if isinstance(name, str) else None

    def _confidence_allowed(self, candidate: str, min_confidence: str) -> bool:
        rank = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
        candidate_rank = rank.get(candidate.lower(), 0)
        required_rank = rank.get(min_confidence.lower(), 1)
        return candidate_rank >= required_rank
