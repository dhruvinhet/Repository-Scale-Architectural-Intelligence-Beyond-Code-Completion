from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agents.orchestrator import create_intent_plan
from .agents.rules import extract_critical_region_patterns, flatten_rules, load_agent_rules
from .agents.verification import VerificationAgent
from .agents.workflow import GenerateWorkflowReport, execute_task_agents, rollback_from_backups
from .neo4j_export import export_neo4j_artifacts
from .pipeline import build_rig
from .policy import evaluate_policies
from .query import RigQueryEngine
from .rig_diff import diff_rig_snapshots
from .viewer import build_html_view, build_workflow_html_view, serve_html


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repository Intelligence Graph platform with advanced multi-agent orchestration and multi-stack enforcement (Python/CMake/Gradle/JS/Maven/.NET)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Build deterministic RIG JSON.")
    build_parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root to analyze.")
    build_parser.add_argument("--out", type=Path, default=Path(".dist/rig.json"), help="Output JSON path.")

    plan_parser = subparsers.add_parser("plan", help="Create decomposition plan for a high-level intent.")
    plan_parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root to analyze.")
    plan_parser.add_argument("--intent", type=str, required=True, help="High-level intent request.")
    plan_parser.add_argument(
        "--out",
        type=Path,
        default=Path(".dist/intent-plan.json"),
        help="Output JSON path for plan.",
    )

    verify_parser = subparsers.add_parser("verify", help="Run static+test verification with repair loop.")
    verify_parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root to analyze.")
    verify_parser.add_argument(
        "--python",
        type=str,
        default="python",
        help="Python executable used to run checks.",
    )
    verify_parser.add_argument("--max-rounds", type=int, default=2, help="Max verification-repair rounds.")
    verify_parser.add_argument(
        "--auto-repair",
        action="store_true",
        help="Enable safe deterministic auto-repair attempts.",
    )
    verify_parser.add_argument(
        "--out",
        type=Path,
        default=Path(".dist/verification-report.json"),
        help="Output JSON path for verification report.",
    )

    generate_parser = subparsers.add_parser("generate", help="Run plan -> task agents -> verify workflow.")
    generate_parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root to analyze.")
    generate_parser.add_argument("--intent", type=str, required=True, help="High-level intent request.")
    generate_parser.add_argument(
        "--python",
        type=str,
        default="python",
        help="Python executable used to run checks.",
    )
    generate_parser.add_argument("--max-rounds", type=int, default=2, help="Max verification-repair rounds.")
    generate_parser.add_argument(
        "--auto-repair",
        action="store_true",
        help="Enable safe deterministic auto-repair attempts.",
    )
    generate_parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path(".dist/change-sets"),
        help="Directory for per-task execution artifacts.",
    )
    generate_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deterministic, auditable edits to candidate files.",
    )
    generate_parser.add_argument(
        "--dry-run-apply",
        action="store_true",
        help="Preview apply changes without writing files.",
    )
    generate_parser.add_argument(
        "--apply-include",
        action="append",
        default=[],
        help="Glob pattern to include paths for apply mode (repeatable).",
    )
    generate_parser.add_argument(
        "--apply-exclude",
        action="append",
        default=[],
        help="Glob pattern to exclude paths for apply mode (repeatable).",
    )
    generate_parser.add_argument(
        "--out",
        type=Path,
        default=Path(".dist/generate-report.json"),
        help="Output JSON path for generate workflow report.",
    )
    generate_parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path(".dist/backups"),
        help="Backup directory used for rollback when apply mode is enabled.",
    )

    view_parser = subparsers.add_parser("view", help="Generate interactive HTML view from RIG JSON.")
    view_parser.add_argument(
        "--rig",
        type=Path,
        default=Path(".dist/rig.json"),
        help="Input RIG JSON path.",
    )
    view_parser.add_argument(
        "--out",
        type=Path,
        default=Path(".dist/rig-view.html"),
        help="Output HTML path.",
    )

    workflow_view_parser = subparsers.add_parser(
        "workflow-view",
        help="Generate HTML dashboard for intent decomposition and multi-agent execution artifacts.",
    )
    workflow_view_parser.add_argument(
        "--plan",
        type=Path,
        default=Path(".dist/intent-plan.json"),
        help="Input intent plan JSON path.",
    )
    workflow_view_parser.add_argument(
        "--report",
        type=Path,
        default=Path(".dist/generate-report.json"),
        help="Input generate workflow report JSON path.",
    )
    workflow_view_parser.add_argument(
        "--out",
        type=Path,
        default=Path(".dist/workflow-view.html"),
        help="Output HTML path.",
    )

    serve_parser = subparsers.add_parser("serve", help="Serve existing RIG viewer HTML over HTTP.")
    serve_parser.add_argument("--html", type=Path, default=Path(".dist/rig-view.html"), help="HTML file to serve.")
    serve_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface.")
    serve_parser.add_argument("--port", type=int, default=8000, help="HTTP port.")
    serve_parser.add_argument("--open", action="store_true", help="Open browser automatically.")

    query_parser = subparsers.add_parser("query", help="Run architectural queries against RIG JSON.")
    query_parser.add_argument("--rig", type=Path, default=Path(".dist/rig.json"), help="Input RIG JSON path.")
    query_parser.add_argument(
        "--mode",
        type=str,
        choices=["find", "dependencies", "dependents", "tests", "impact"],
        required=True,
        help="Query mode.",
    )
    query_parser.add_argument("--name", type=str, required=True, help="Node name (or substring for find).")
    query_parser.add_argument("--explain", action="store_true", help="Include edge-level explanation paths.")
    query_parser.add_argument(
        "--relation-filter",
        action="append",
        default=[],
        help="Relation filter (repeatable), e.g. depends_on,imports,calls,tested_by.",
    )
    query_parser.add_argument(
        "--path-limit",
        type=int,
        default=0,
        help="Maximum number of paths/results to return (0 = unlimited).",
    )
    query_parser.add_argument(
        "--min-confidence",
        type=str,
        choices=["low", "medium", "high"],
        default="low",
        help="Minimum edge confidence to include.",
    )
    query_parser.add_argument("--out", type=Path, help="Optional output file path.")

    neo4j_parser = subparsers.add_parser("neo4j-export", help="Export RIG into Neo4j import artifacts.")
    neo4j_parser.add_argument("--rig", type=Path, default=Path(".dist/rig.json"), help="Input RIG JSON path.")
    neo4j_parser.add_argument("--out-dir", type=Path, default=Path(".dist/neo4j"), help="Output directory.")

    diff_parser = subparsers.add_parser("diff", help="Compare two RIG snapshots and report architectural drift.")
    diff_parser.add_argument(
        "--old",
        "--base",
        dest="old",
        type=Path,
        default=Path(".rig/baseline-rig.json"),
        help="Baseline RIG JSON path.",
    )
    diff_parser.add_argument(
        "--new",
        type=Path,
        default=Path(".dist/rig.json"),
        help="Current RIG JSON path.",
    )
    diff_parser.add_argument("--out", type=Path, default=Path(".dist/rig-diff.json"), help="Output diff report path.")

    policy_parser = subparsers.add_parser("policy", help="Run architecture policy checks against RIG JSON.")
    policy_parser.add_argument("--rig", type=Path, default=Path(".dist/rig.json"), help="Input RIG JSON path.")
    policy_parser.add_argument(
        "--forbid",
        action="append",
        default=[],
        help="Forbidden dependency direction rule, e.g. ui.->data.",
    )
    policy_parser.add_argument(
        "--forbid-file",
        type=Path,
        action="append",
        help="Path to file containing forbidden rules (one rule per line).",
    )
    policy_parser.add_argument("--out", type=Path, default=Path(".dist/policy-report.json"), help="Output report path.")
    policy_parser.add_argument("--fail-on-violation", action="store_true", help="Exit non-zero when policy fails.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "build":
        repo_root = args.repo.resolve()
        store = build_rig(repo_root)
        output_path = args.out.resolve() if not args.out.is_absolute() else args.out
        store.write_json(output_path)
        data = store.to_dict()
        print(f"RIG built for: {repo_root}")
        print(f"Nodes: {data['metadata']['node_count']}")
        print(f"Edges: {data['metadata']['edge_count']}")
        print(f"Output: {output_path}")
        return

    if args.command == "plan":
        repo_root = args.repo.resolve()
        store = build_rig(repo_root)
        constraints = flatten_rules(load_agent_rules(repo_root))
        plan = create_intent_plan(args.intent, store, constraints)
        output_path = args.out.resolve() if not args.out.is_absolute() else args.out
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
        print(f"Plan generated for intent: {args.intent}")
        print(f"Constraints loaded: {len(constraints)}")
        print(f"Output: {output_path}")
        return

    if args.command == "verify":
        repo_root = args.repo.resolve()
        verifier = VerificationAgent(repo_root=repo_root, python_executable=args.python)
        report = verifier.run(max_rounds=args.max_rounds, auto_repair=args.auto_repair)
        output_path = args.out.resolve() if not args.out.is_absolute() else args.out
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"Verification repo: {repo_root}")
        print(f"Passed: {report.passed}")
        print(f"Rounds: {report.rounds}")
        print(f"Auto-repairs attempted: {report.auto_repairs_attempted}")
        print(f"Output: {output_path}")
        if not report.passed:
            raise SystemExit(1)
        return

    if args.command == "generate":
        repo_root = args.repo.resolve()
        rig = build_rig(repo_root)

        apply_mode = args.apply or args.dry_run_apply

        sections = load_agent_rules(repo_root)
        constraints = flatten_rules(sections)
        protected_patterns = extract_critical_region_patterns(sections)
        plan = create_intent_plan(args.intent, rig, constraints)

        artifact_dir = args.artifact_dir.resolve() if not args.artifact_dir.is_absolute() else args.artifact_dir
        executions = execute_task_agents(
            repo_root=repo_root,
            plan=plan,
            rig=rig,
            artifact_dir=artifact_dir,
            apply=apply_mode,
            protected_patterns=protected_patterns,
            apply_includes=args.apply_include,
            apply_excludes=args.apply_exclude,
            backup_dir=args.backup_dir.resolve() if not args.backup_dir.is_absolute() else args.backup_dir,
            dry_run_apply=args.dry_run_apply,
        )

        verifier = VerificationAgent(repo_root=repo_root, python_executable=args.python)
        verification = verifier.run(max_rounds=args.max_rounds, auto_repair=args.auto_repair)

        rig_payload = rig.to_dict()
        report = GenerateWorkflowReport(
            intent=args.intent,
            constraints_count=len(constraints),
            rig_node_count=int(rig_payload["metadata"]["node_count"]),
            rig_edge_count=int(rig_payload["metadata"]["edge_count"]),
            executions=executions,
            verification=verification,
        )

        output_path = args.out.resolve() if not args.out.is_absolute() else args.out
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

        print(f"Generate workflow repo: {repo_root}")
        print(f"Intent: {args.intent}")
        print(f"Apply mode: {apply_mode}")
        print(f"Dry-run apply: {args.dry_run_apply}")
        if apply_mode:
            print(f"Apply include filters: {args.apply_include or ['<none>']}")
            print(f"Apply exclude filters: {args.apply_exclude or ['<none>']}")
            print(f"Backup dir: {args.backup_dir}")
        print(f"Task artifacts: {artifact_dir}")
        print(f"Verification passed: {verification.passed}")
        print(f"Output: {output_path}")
        if not verification.passed:
            if apply_mode and not args.dry_run_apply:
                backup_dir = args.backup_dir.resolve() if not args.backup_dir.is_absolute() else args.backup_dir
                restored = rollback_from_backups(repo_root=repo_root, backup_dir=backup_dir)
                print(f"Rollback restored files: {restored}")
            raise SystemExit(1)
        return

    if args.command == "view":
        rig_path = args.rig.resolve() if not args.rig.is_absolute() else args.rig
        out_path = args.out.resolve() if not args.out.is_absolute() else args.out
        if not rig_path.exists():
            raise SystemExit(f"RIG JSON not found: {rig_path}")
        html_path = build_html_view(rig_path, out_path)
        print(f"RIG input: {rig_path}")
        print(f"Viewer output: {html_path}")
        return

    if args.command == "workflow-view":
        plan_path = args.plan.resolve() if not args.plan.is_absolute() else args.plan
        report_path = args.report.resolve() if not args.report.is_absolute() else args.report
        out_path = args.out.resolve() if not args.out.is_absolute() else args.out
        if not plan_path.exists():
            raise SystemExit(f"Intent plan JSON not found: {plan_path}")
        if not report_path.exists():
            raise SystemExit(f"Generate report JSON not found: {report_path}")
        html_path = build_workflow_html_view(
            plan_json_path=plan_path,
            generate_report_path=report_path,
            out_html_path=out_path,
        )
        print(f"Plan input: {plan_path}")
        print(f"Report input: {report_path}")
        print(f"Workflow viewer output: {html_path}")
        return

    if args.command == "serve":
        html_path = args.html.resolve() if not args.html.is_absolute() else args.html
        if not html_path.exists():
            raise SystemExit(f"Viewer HTML not found: {html_path}")
        serve_html(html_path=html_path, host=args.host, port=args.port, open_browser=args.open)
        return

    if args.command == "query":
        rig_path = args.rig.resolve() if not args.rig.is_absolute() else args.rig
        if not rig_path.exists():
            raise SystemExit(f"RIG JSON not found: {rig_path}")

        engine = RigQueryEngine.from_path(rig_path)
        relation_values: list[str] = []
        for raw in args.relation_filter:
            relation_values.extend(part.strip() for part in raw.split(",") if part.strip())
        relation_filter = set(relation_values) if relation_values else None
        path_limit = args.path_limit if args.path_limit and args.path_limit > 0 else None
        min_confidence = args.min_confidence
        resolved_name = engine.resolve_name(args.name)
        query_name = resolved_name or args.name
        hints: list[str] = []
        if resolved_name is None and args.mode != "find":
            hints = engine.find_nodes(args.name)[:10]
        if args.mode == "find":
            payload: dict[str, object] = {"mode": "find", "name": args.name, "matches": engine.find_nodes(args.name)}
        elif args.mode == "dependencies":
            payload = {
                "mode": "dependencies",
                "name": args.name,
                "matches": engine.dependencies_of(
                    query_name,
                    relation_filter=relation_filter,
                    min_confidence=min_confidence,
                    path_limit=path_limit,
                ),
            }
            if args.explain:
                payload["explain"] = engine.dependencies_of_explain(
                    query_name,
                    relation_filter=relation_filter,
                    min_confidence=min_confidence,
                    path_limit=path_limit,
                )
        elif args.mode == "dependents":
            payload = {
                "mode": "dependents",
                "name": args.name,
                "matches": engine.dependents_of(
                    query_name,
                    relation_filter=relation_filter,
                    min_confidence=min_confidence,
                    path_limit=path_limit,
                ),
            }
            if args.explain:
                payload["explain"] = engine.dependents_of_explain(
                    query_name,
                    relation_filter=relation_filter,
                    min_confidence=min_confidence,
                    path_limit=path_limit,
                )
        elif args.mode == "tests":
            payload = {
                "mode": "tests",
                "name": args.name,
                "matches": engine.tests_for(
                    query_name,
                    relation_filter=relation_filter,
                    min_confidence=min_confidence,
                    path_limit=path_limit,
                ),
            }
            if args.explain:
                payload["explain"] = engine.tests_for_explain(
                    query_name,
                    relation_filter=relation_filter,
                    min_confidence=min_confidence,
                    path_limit=path_limit,
                )
        else:
            payload = {
                "mode": "impact",
                "name": args.name,
                "impact": engine.impact_of(
                    query_name,
                    relation_filter=relation_filter,
                    min_confidence=min_confidence,
                    path_limit=path_limit,
                ),
            }
            if args.explain:
                payload["explain"] = engine.impact_of_explain(
                    query_name,
                    relation_filter=relation_filter,
                    min_confidence=min_confidence,
                    path_limit=path_limit,
                )

        if args.mode != "find":
            payload["resolved_name"] = resolved_name
            if hints:
                payload["hints"] = hints

        output = json.dumps(payload, indent=2)
        if args.out:
            out_path = args.out.resolve() if not args.out.is_absolute() else args.out
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output, encoding="utf-8")
            print(f"Query output: {out_path}")
        else:
            print(output)
        return

    if args.command == "neo4j-export":
        rig_path = args.rig.resolve() if not args.rig.is_absolute() else args.rig
        out_dir = args.out_dir.resolve() if not args.out_dir.is_absolute() else args.out_dir
        if not rig_path.exists():
            raise SystemExit(f"RIG JSON not found: {rig_path}")
        artifacts = export_neo4j_artifacts(rig_json_path=rig_path, out_dir=out_dir)
        print("Neo4j artifacts:")
        for key, value in artifacts.items():
            print(f"- {key}: {value}")
        return

    if args.command == "diff":
        old_path = args.old.resolve() if not args.old.is_absolute() else args.old
        new_path = args.new.resolve() if not args.new.is_absolute() else args.new
        if not old_path.exists():
            raise SystemExit(f"Old snapshot not found: {old_path}")
        if not new_path.exists():
            raise SystemExit(f"New snapshot not found: {new_path}")
        payload = diff_rig_snapshots(old_path=old_path, new_path=new_path)
        out_path = args.out.resolve() if not args.out.is_absolute() else args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"RIG diff output: {out_path}")
        print(f"Added nodes: {payload['node_delta']['added_count']}")
        print(f"Removed nodes: {payload['node_delta']['removed_count']}")
        print(f"Added edges: {payload['edge_delta']['added_count']}")
        print(f"Removed edges: {payload['edge_delta']['removed_count']}")
        return

    if args.command == "policy":
        rig_path = args.rig.resolve() if not args.rig.is_absolute() else args.rig
        if not rig_path.exists():
            raise SystemExit(f"RIG JSON not found: {rig_path}")

        forbid_rules = list(args.forbid)
        if args.forbid_file:
            for path in args.forbid_file:
                file_path = path.resolve() if not path.is_absolute() else path
                if not file_path.exists():
                    raise SystemExit(f"Policy rules file not found: {file_path}")
                for raw in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    forbid_rules.append(line)

        payload = evaluate_policies(rig_path=rig_path, forbid_rules=forbid_rules)
        out_path = args.out.resolve() if not args.out.is_absolute() else args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Policy report: {out_path}")
        print(f"Policy passed: {payload['passed']}")
        if args.fail_on_violation and not payload["passed"]:
            raise SystemExit(1)
        return


if __name__ == "__main__":
    main()
