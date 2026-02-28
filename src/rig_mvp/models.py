from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256


def stable_id(kind: str, name: str) -> str:
    digest = sha256(f"{kind}:{name}".encode("utf-8")).hexdigest()[:16]
    return f"{kind.lower()}:{digest}"


@dataclass(slots=True)
class Node:
    kind: str
    name: str
    properties: dict[str, object] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        self.id = stable_id(self.kind, self.name)


@dataclass(slots=True)
class Edge:
    source: str
    target: str
    relation: str
    properties: dict[str, object] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source, self.relation, self.target)
