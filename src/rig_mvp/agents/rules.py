from __future__ import annotations

from pathlib import Path
import re


def load_agent_rules(repo_root: Path) -> dict[str, list[str]]:
    file_path = repo_root / "AGENTS.md"
    if not file_path.exists():
        return {}

    sections: dict[str, list[str]] = {}
    current = "General"
    sections[current] = []

    for raw_line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            current = line.lstrip("#").strip() or "General"
            sections.setdefault(current, [])
            continue
        if line.startswith("-"):
            sections.setdefault(current, []).append(line[1:].strip())

    return sections


def flatten_rules(sections: dict[str, list[str]]) -> list[str]:
    rules: list[str] = []
    for name, items in sections.items():
        for item in items:
            rules.append(f"[{name}] {item}")
    return rules


def extract_critical_region_patterns(sections: dict[str, list[str]]) -> list[str]:
    patterns: set[str] = set()
    for section_name, items in sections.items():
        if section_name.lower().strip() != "critical regions":
            continue
        for item in items:
            for fenced in re.findall(r"`([^`]+)`", item):
                cleaned = fenced.strip().replace("\\", "/").lstrip("/")
                if cleaned:
                    patterns.add(cleaned)

            lowered = item.lower()
            if ".azure/" in lowered:
                patterns.add(".azure/")
            if "workflow" in lowered and "ci" in lowered:
                patterns.add(".github/workflows/")

            under_match = re.search(r"under\s+([\w./-]+)", item, flags=re.IGNORECASE)
            if under_match:
                candidate = under_match.group(1).replace("\\", "/").lstrip("/")
                if candidate:
                    patterns.add(candidate)

    return sorted(patterns)


def is_protected_path(relative_path: str, patterns: list[str]) -> bool:
    normalized = relative_path.replace("\\", "/").lstrip("/")
    for pattern in patterns:
        check = pattern.replace("\\", "/").lstrip("/")
        if not check:
            continue
        if check.endswith("/"):
            if normalized.startswith(check):
                return True
        elif normalized == check or normalized.startswith(f"{check}/"):
            return True
    return False
