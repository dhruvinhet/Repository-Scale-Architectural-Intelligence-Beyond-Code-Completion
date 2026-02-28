from __future__ import annotations

from collections import defaultdict

from ..graph_store import GraphStore
from .models import IntentPlan, SubTask


def create_intent_plan(intent: str, rig: GraphStore, constraints: list[str] | None = None) -> IntentPlan:
    plan = IntentPlan(intent=intent, constraints=constraints or [])

    technologies = _detect_stack(rig)
    base_titles = ["Analyze impact scope", "Define interface and contracts", "Implement code changes", "Update tests and fixtures", "Run verification and repair"]
    if "python" in technologies:
        base_titles.insert(2, "Update Python dependencies and packaging metadata")
    if "cmake" in technologies:
        base_titles.insert(2, "Update CMake targets/dependencies and test wiring")
    if "gradle" in technologies:
        base_titles.insert(2, "Update Gradle module and external dependency graph")

    hints = _infer_impacted_hints(intent, rig)
    for index, title in enumerate(base_titles, start=1):
        plan.subtasks.append(
            SubTask(
                id=f"T{index}",
                title=title,
                description=f"{title} for intent: {intent}",
                impacted_hints=hints,
                agent_role=_role_for_title(title),
                acceptance_criteria=_criteria_for_title(title),
            )
        )

    return plan


def _infer_impacted_hints(intent: str, rig: GraphStore) -> list[str]:
    tokens = {token.lower() for token in intent.replace("_", " ").replace("-", " ").split() if len(token) > 2}
    score: dict[str, int] = defaultdict(int)

    for node in rig.nodes.values():
        lowered = node.name.lower()
        for token in tokens:
            if token in lowered:
                score[node.name] += 1

    ranked = sorted(score.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, _ in ranked[:8]]


def _detect_stack(rig: GraphStore) -> set[str]:
    technologies: set[str] = set()
    for node in rig.nodes.values():
        build_system = node.properties.get("build_system") if isinstance(node.properties, dict) else None
        language = node.properties.get("language") if isinstance(node.properties, dict) else None
        if isinstance(build_system, str):
            technologies.add(build_system.lower())
        if isinstance(language, str):
            technologies.add(language.lower())
    return technologies


def _role_for_title(title: str) -> str:
    lowered = title.lower()
    if "analyze" in lowered:
        return "decomposer"
    if "verify" in lowered or "repair" in lowered:
        return "repair"
    if "test" in lowered:
        return "critic"
    return "generator"


def _criteria_for_title(title: str) -> list[str]:
    lowered = title.lower()
    if "analyze" in lowered:
        return ["Impacted modules are identified", "Dependencies and dependents are listed"]
    if "interface" in lowered:
        return ["Public contracts are stable", "Backward compatibility risk is documented"]
    if "cmake" in lowered:
        return ["CMake target graph remains buildable", "CMake test wiring remains valid"]
    if "gradle" in lowered:
        return ["Gradle project deps are consistent", "External coordinates are pinned/known"]
    if "python" in lowered:
        return ["Python dependency metadata is updated", "Import/module compatibility preserved"]
    if "test" in lowered:
        return ["Relevant tests are updated", "No coverage regressions in touched scope"]
    if "verify" in lowered or "repair" in lowered:
        return ["Verification passes", "Repair loop converges without violating constraints"]
    return ["Change compiles/interprets", "Change respects repository constraints"]
