from __future__ import annotations

from dataclasses import dataclass
import fnmatch
from pathlib import Path
import json
import re
import shutil

from ..graph_store import GraphStore
from .models import IntentPlan, SubTask
from .verification import VerificationReport


@dataclass(slots=True)
class TaskExecutionResult:
    task_id: str
    title: str
    status: str
    impacted_nodes: list[str]
    candidate_files: list[str]
    actions: list[str]
    artifact_path: str
    applied_files: list[str]
    skipped_files: list[str]
    critic_issues: list[str]
    repair_actions: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "status": self.status,
            "impacted_nodes": self.impacted_nodes,
            "candidate_files": self.candidate_files,
            "actions": self.actions,
            "artifact_path": self.artifact_path,
            "applied_files": self.applied_files,
            "skipped_files": self.skipped_files,
            "critic_issues": self.critic_issues,
            "repair_actions": self.repair_actions,
        }


@dataclass(slots=True)
class GenerateWorkflowReport:
    intent: str
    constraints_count: int
    rig_node_count: int
    rig_edge_count: int
    executions: list[TaskExecutionResult]
    verification: VerificationReport

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "constraints_count": self.constraints_count,
            "rig": {
                "nodes": self.rig_node_count,
                "edges": self.rig_edge_count,
            },
            "executions": [execution.to_dict() for execution in self.executions],
            "verification": self.verification.to_dict(),
        }


def execute_task_agents(
    repo_root: Path,
    plan: IntentPlan,
    rig: GraphStore,
    artifact_dir: Path,
    apply: bool = False,
    protected_patterns: list[str] | None = None,
    apply_includes: list[str] | None = None,
    apply_excludes: list[str] | None = None,
    backup_dir: Path | None = None,
    dry_run_apply: bool = False,
) -> list[TaskExecutionResult]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    results: list[TaskExecutionResult] = []
    protected_patterns = protected_patterns or []
    apply_includes = apply_includes or []
    apply_excludes = apply_excludes or []
    backup_dir = backup_dir or (artifact_dir / "_backups")

    for task in plan.subtasks:
        impacted = _resolve_impacted_nodes(task, plan.intent, rig)
        candidate_files = _candidate_files_for_nodes(rig, impacted)
        actions = _build_actions(task, candidate_files)
        applied_files: list[str] = []
        skipped_files: list[str] = []
        critic_issues: list[str] = _critic_review(task, candidate_files)
        repair_actions: list[str] = []
        if critic_issues:
            repair_actions = _repair_plan(task, critic_issues)
            actions.extend(repair_actions)

        if apply:
            applied_files, skipped_files = _apply_task_to_candidates(
                repo_root=repo_root,
                intent=plan.intent,
                task=task,
                candidate_files=candidate_files,
                protected_patterns=protected_patterns,
                apply_includes=apply_includes,
                apply_excludes=apply_excludes,
                backup_dir=backup_dir,
                dry_run_apply=dry_run_apply,
            )

        artifact_path = artifact_dir / f"{task.id.lower()}-changeset.json"
        artifact_payload = {
            "task_id": task.id,
            "title": task.title,
            "description": task.description,
            "intent": plan.intent,
            "impacted_nodes": impacted,
            "candidate_files": candidate_files,
            "actions": actions,
            "apply_mode": "deterministic-dry-run" if (apply and dry_run_apply) else ("deterministic-apply" if apply else "proposal-only"),
            "applied_files": applied_files,
            "skipped_files": skipped_files,
            "critic_issues": critic_issues,
            "repair_actions": repair_actions,
        }
        artifact_path.write_text(json.dumps(artifact_payload, indent=2), encoding="utf-8")

        results.append(
            TaskExecutionResult(
                task_id=task.id,
                title=task.title,
                status="completed",
                impacted_nodes=impacted,
                candidate_files=candidate_files,
                actions=actions,
                artifact_path=str(artifact_path),
                applied_files=applied_files,
                skipped_files=skipped_files,
                critic_issues=critic_issues,
                repair_actions=repair_actions,
            )
        )

    return results


def _resolve_impacted_nodes(task: SubTask, intent: str, rig: GraphStore) -> list[str]:
    explicit = list(task.impacted_hints)
    if explicit:
        return explicit[:10]

    tokens = _tokenize(f"{intent} {task.title} {task.description}")
    scored: list[tuple[int, str]] = []
    for node in rig.nodes.values():
        lowered = node.name.lower()
        score = sum(1 for token in tokens if token in lowered)
        if score > 0:
            scored.append((score, node.name))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _, name in scored[:10]]


def _candidate_files_for_nodes(rig: GraphStore, node_names: list[str]) -> list[str]:
    names = set(node_names)
    paths: set[str] = set()
    ignored_fragments = {".venv/", "venv/", "__pycache__/", ".dist/", ".git/", "site-packages/"}
    for node in rig.nodes.values():
        if node.name not in names:
            continue
        path = _resolve_node_path(rig, node)
        if isinstance(path, str):
            normalized = path.replace("\\", "/")
            if any(fragment in normalized for fragment in ignored_fragments):
                continue
            paths.add(path)
    return sorted(paths)


def _resolve_node_path(rig: GraphStore, node: object) -> str | None:
    if not hasattr(node, "properties"):
        return None
    properties = getattr(node, "properties")
    path = properties.get("path")
    if isinstance(path, str):
        return path
    module_name = properties.get("module")
    if not isinstance(module_name, str):
        return None
    for candidate in rig.nodes.values():
        if candidate.kind == "Module" and candidate.name == module_name:
            candidate_path = candidate.properties.get("path")
            if isinstance(candidate_path, str):
                return candidate_path
    return None


def _build_actions(task: SubTask, candidate_files: list[str]) -> list[str]:
    if not candidate_files:
        return [
            f"Inspect RIG neighborhood for {task.id}.",
            "No candidate files auto-detected; requires targeted repository query.",
        ]
    return [
        f"Review {len(candidate_files)} candidate file(s) for {task.id}.",
        f"Agent role: {task.agent_role}.",
        "Prepare multi-file patch aligned with AGENTS.md constraints.",
        "Run verification loop after patch generation.",
    ]


def _critic_review(task: SubTask, candidate_files: list[str]) -> list[str]:
    issues: list[str] = []
    if not candidate_files:
        issues.append("No candidate files were found; impact scope may be incomplete.")
    if not task.acceptance_criteria:
        issues.append("Acceptance criteria are missing for this task.")
    if task.agent_role == "critic" and len(candidate_files) < 1:
        issues.append("Testing-related task has no explicit test file candidates.")
    return issues


def _repair_plan(task: SubTask, issues: list[str]) -> list[str]:
    actions: list[str] = []
    for issue in issues:
        if "No candidate files" in issue:
            actions.append(f"Repair: broaden RIG neighborhood search for {task.id}.")
        elif "Acceptance criteria" in issue:
            actions.append(f"Repair: inject default acceptance criteria for {task.id}.")
        elif "test file candidates" in issue:
            actions.append(f"Repair: include test modules in candidate expansion for {task.id}.")
    return actions


def _tokenize(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-zA-Z0-9]+", text.lower()) if len(token) >= 3}


def _apply_task_to_candidates(
    repo_root: Path,
    intent: str,
    task: SubTask,
    candidate_files: list[str],
    protected_patterns: list[str],
    apply_includes: list[str],
    apply_excludes: list[str],
    backup_dir: Path,
    dry_run_apply: bool,
) -> tuple[list[str], list[str]]:
    applied: list[str] = []
    skipped: list[str] = []

    for relative in candidate_files:
        normalized = relative.replace("\\", "/").lstrip("/")
        if apply_includes and not _matches_any(normalized, apply_includes):
            skipped.append(f"{normalized}:not-included")
            continue
        if apply_excludes and _matches_any(normalized, apply_excludes):
            skipped.append(f"{normalized}:excluded")
            continue
        if _is_protected(normalized, protected_patterns):
            skipped.append(f"{normalized}:protected")
            continue

        target = (repo_root / normalized).resolve()
        if not target.exists() or not target.is_file():
            skipped.append(f"{normalized}:missing")
            continue

        if target.suffix.lower() not in {".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".ini"}:
            skipped.append(f"{normalized}:unsupported")
            continue

        did_change = _apply_refactor_with_backup(
            file_path=target,
            relative_path=normalized,
            task=task,
            intent=intent,
            backup_dir=backup_dir,
            repo_root=repo_root,
            dry_run_apply=dry_run_apply,
        )
        if did_change:
            applied.append(f"{normalized}:dry-run" if dry_run_apply else normalized)
        else:
            skipped.append(f"{normalized}:no-change")

    return applied, skipped


def _is_protected(relative_path: str, patterns: list[str]) -> bool:
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


def _upsert_task_block(file_path: Path, relative_path: str, task: SubTask, intent: str) -> None:
    existing = file_path.read_text(encoding="utf-8", errors="ignore")
    start, end, block = _build_task_block(file_path.suffix.lower(), relative_path, task, intent)

    pattern = re.compile(rf"{re.escape(start)}.*?{re.escape(end)}", flags=re.DOTALL)
    if pattern.search(existing):
        updated = pattern.sub(block, existing)
    else:
        separator = "\n" if existing.endswith("\n") else "\n\n"
        updated = f"{existing}{separator}{block}\n"

    file_path.write_text(updated, encoding="utf-8")


def _apply_refactor_with_backup(
    file_path: Path,
    relative_path: str,
    task: SubTask,
    intent: str,
    backup_dir: Path,
    repo_root: Path,
    dry_run_apply: bool,
) -> bool:
    original = file_path.read_text(encoding="utf-8", errors="ignore")
    updated = _apply_intent_refactor(original, intent, file_path.suffix.lower())

    if updated == original:
        updated = _materialize_audit_marker(original, file_path.suffix.lower(), relative_path, task, intent)
        if updated == original:
            return False

    if dry_run_apply:
        return True

    _create_backup(file_path=file_path, relative_path=relative_path, backup_dir=backup_dir)
    file_path.write_text(updated, encoding="utf-8")
    return True


def _apply_intent_refactor(content: str, intent: str, suffix: str) -> str:
    if suffix not in {".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".ini"}:
        return content

    migration = re.search(r"migrate\s+([a-zA-Z0-9_./-]+)\s+to\s+([a-zA-Z0-9_./-]+)", intent, flags=re.IGNORECASE)
    if not migration:
        return content

    old = migration.group(1)
    new = migration.group(2)
    if old.lower() == new.lower():
        return content

    patterns = [
        (rf"\b{re.escape(old)}\b", new),
        (rf"\b{re.escape(old.lower())}\b", new.lower()),
        (rf"\b{re.escape(old.upper())}\b", new.upper()),
        (rf"\b{re.escape(old.title())}\b", new.title()),
    ]

    updated = content
    for pattern, replacement in patterns:
        updated = re.sub(pattern, replacement, updated)
    return updated


def _materialize_audit_marker(content: str, suffix: str, relative_path: str, task: SubTask, intent: str) -> str:
    start, end, block = _build_task_block(suffix, relative_path, task, intent)
    pattern = re.compile(rf"{re.escape(start)}.*?{re.escape(end)}", flags=re.DOTALL)
    if pattern.search(content):
        return pattern.sub(block, content)
    separator = "\n" if content.endswith("\n") else "\n\n"
    return f"{content}{separator}{block}\n"


def _create_backup(file_path: Path, relative_path: str, backup_dir: Path) -> None:
    backup_path = backup_dir / f"{relative_path}.bak"
    if backup_path.exists():
        return
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, backup_path)


def rollback_from_backups(repo_root: Path, backup_dir: Path) -> int:
    if not backup_dir.exists():
        return 0

    restored = 0
    for backup_file in backup_dir.rglob("*.bak"):
        relative = backup_file.relative_to(backup_dir).as_posix()
        original_rel = relative.removesuffix(".bak")
        target = repo_root / original_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_file, target)
        restored += 1
    return restored


def _build_task_block(suffix: str, relative_path: str, task: SubTask, intent: str) -> tuple[str, str, str]:
    body = [
        f"task={task.id}",
        f"title={task.title}",
        f"intent={intent}",
        f"file={relative_path}",
    ]

    if suffix == ".md":
        start = f"<!-- RIG-AUTO-START:{task.id} -->"
        end = f"<!-- RIG-AUTO-END:{task.id} -->"
        inner = "\n".join(f"{line}" for line in body)
        block = f"{start}\n{inner}\n{end}"
        return start, end, block

    start = f"# RIG-AUTO-START:{task.id}"
    end = f"# RIG-AUTO-END:{task.id}"
    inner = "\n".join(f"# {line}" for line in body)
    block = f"{start}\n{inner}\n{end}"
    return start, end, block


def _matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("/")
    for pattern in patterns:
        check = pattern.replace("\\", "/").lstrip("/")
        if fnmatch.fnmatch(normalized, check):
            return True
    return False
