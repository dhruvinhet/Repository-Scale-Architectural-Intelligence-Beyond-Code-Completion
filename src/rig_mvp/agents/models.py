from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SubTask:
    id: str
    title: str
    description: str
    impacted_hints: list[str] = field(default_factory=list)
    agent_role: str = "generator"
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass(slots=True)
class IntentPlan:
    intent: str
    constraints: list[str] = field(default_factory=list)
    subtasks: list[SubTask] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "constraints": self.constraints,
            "subtasks": [
                {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "impacted_hints": task.impacted_hints,
                    "agent_role": task.agent_role,
                    "acceptance_criteria": task.acceptance_criteria,
                }
                for task in self.subtasks
            ],
        }
